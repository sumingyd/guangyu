/*
 * 原生信号崩溃取证：SIGSEGV / SIGABRT / SIGBUS / SIGILL / SIGFPE / SIGTRAP。
 *
 * 与 NativeCrashLogger 的分工：
 * - NativeCrashLogger 通过后台 logcat + 系统 crash 缓冲区取证（tombstone/debuggerd），
 *   依赖 logcat 可读、且崩溃后日志未被轮转；盒子现场经常拿不到。
 * - 本 handler 在信号发生的同一线程上直接写文件（不走 logcat），
 *   把信号、fault 地址、寄存器与实时调用栈落到 filesDir/crash-reports/crash_native_*.txt。
 *
 * 约束：
 * - 尽量 async-signal-safe：只用 open/write/close/raise，不 malloc、不用 stdio、不加锁。
 * - 写完后恢复默认信号处理并 raise(sig)，让 debuggerd 照常产出 tombstone，
 *   不改变现有崩溃上报流程。
 */

#include <jni.h>

#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include <ucontext.h>
#include <unwind.h>

#if defined(__aarch64__)
#define UC_PC(uc) (((ucontext_t *)(uc))->uc_mcontext.pc)
#define UC_SP(uc) (((ucontext_t *)(uc))->uc_mcontext.sp)
#define UC_LR(uc) (((ucontext_t *)(uc))->uc_mcontext.regs[30])
#elif defined(__arm__)
#define UC_PC(uc) (((ucontext_t *)(uc))->uc_mcontext.arm_pc)
#define UC_SP(uc) (((ucontext_t *)(uc))->uc_mcontext.arm_sp)
#define UC_LR(uc) (((ucontext_t *)(uc))->uc_mcontext.arm_lr)
#else
#define UC_PC(uc) (0ULL)
#define UC_SP(uc) (0ULL)
#define UC_LR(uc) (0ULL)
#endif

#define CRASH_DIR_MAX 256
#define PATH_MAX_LEN 384
#define MAX_FRAMES 40

static char g_crash_dir[CRASH_DIR_MAX];
static char g_alt_stack[64 * 1024];
static volatile sig_atomic_t g_in_handler = 0;

static void put_str(int fd, const char *s) {
    if (s == NULL) return;
    size_t len = strlen(s);
    if (len > 0) (void) write(fd, s, len);
}

static void put_hex(int fd, unsigned long long value) {
    char buf[2 + 16];
    buf[0] = '0';
    buf[1] = 'x';
    for (int i = 0; i < 16; i++) {
        int shift = (15 - i) * 4;
        int digit = (int) ((value >> shift) & 0xF);
        buf[2 + i] = (char) (digit < 10 ? ('0' + digit) : ('a' + digit - 10));
    }
    (void) write(fd, buf, sizeof(buf));
}

static void put_dec(int fd, long long value) {
    char buf[24];
    int pos = (int) sizeof(buf);
    int negative = value < 0;
    unsigned long long v = negative ? (unsigned long long) (-value) : (unsigned long long) value;
    if (v == 0) buf[--pos] = '0';
    while (v > 0 && pos > 0) {
        buf[--pos] = (char) ('0' + (int) (v % 10));
        v /= 10;
    }
    if (negative && pos > 0) buf[--pos] = '-';
    (void) write(fd, buf + pos, sizeof(buf) - (size_t) pos);
}

static void put_signal_name(int fd, int sig) {
    switch (sig) {
        case SIGSEGV: put_str(fd, "SIGSEGV"); break;
        case SIGABRT: put_str(fd, "SIGABRT"); break;
        case SIGBUS:  put_str(fd, "SIGBUS"); break;
        case SIGILL:  put_str(fd, "SIGILL"); break;
        case SIGFPE:  put_str(fd, "SIGFPE"); break;
        case SIGTRAP: put_str(fd, "SIGTRAP"); break;
        default:      put_str(fd, "SIG?"); break;
    }
}

/** 把十进制数追加到 path 缓冲区 */
static void append_dec(char *buf, int *pos, int cap, unsigned long long value) {
    char tmp[24];
    int n = 0;
    if (value == 0) tmp[n++] = '0';
    while (value > 0 && n < (int) sizeof(tmp)) {
        tmp[n++] = (char) ('0' + (int) (value % 10));
        value /= 10;
    }
    while (n > 0 && *pos < cap - 1) buf[(*pos)++] = tmp[--n];
    buf[*pos] = '\0';
}

typedef struct {
    int fd;
    int index;
} frame_ctx_t;

/** _Unwind_Backtrace 回调：每个栈帧写一行 `#序号 pc=0x.. 模块+偏移`。 */
static _Unwind_Reason_Code frame_callback(struct _Unwind_Context *ctx, void *arg) {
    frame_ctx_t *frame = (frame_ctx_t *) arg;
    if (frame->index >= MAX_FRAMES) return _URC_END_OF_STACK;
    uintptr_t pc = _Unwind_GetIP(ctx);
    if (pc == 0) return _URC_END_OF_STACK;

    int fd = frame->fd;
    put_str(fd, "#");
    put_dec(fd, frame->index);
    put_str(fd, " pc=");
    put_hex(fd, (unsigned long long) pc);

    Dl_info info;
    if (dladdr((void *) pc, &info) != 0 && info.dli_fname != NULL) {
        const char *name = info.dli_fname;
        const char *slash = strrchr(name, '/');
        if (slash != NULL) name = slash + 1;
        put_str(fd, " ");
        put_str(fd, name);
        put_str(fd, "+");
        put_hex(fd, (unsigned long long) (pc - (uintptr_t) info.dli_fbase));
    } else {
        put_str(fd, " ?");
    }
    put_str(fd, "\n");
    frame->index++;
    return _URC_NO_REASON;
}

/** 信号处理函数：只做取证 + 交回系统默认处理。 */
static void crash_signal_handler(int sig, siginfo_t *si, void *uc) {
    if (g_in_handler) {
        // 二次崩溃：不再取证，直接交回默认处理，避免死循环
        signal(sig, SIG_DFL);
        raise(sig);
        return;
    }
    g_in_handler = 1;

    long long pid = (long long) getpid();
    long long tid = (long long) syscall(SYS_gettid);
    int dir_len = (int) strlen(g_crash_dir);
    int fd = -1;

    if (dir_len > 0 && dir_len < CRASH_DIR_MAX) {
        char path[PATH_MAX_LEN];
        int pos = 0;
        memcpy(path, g_crash_dir, (size_t) dir_len);
        pos = dir_len;
        path[pos++] = '/';
        path[pos] = '\0';

        const char *name = "crash_native_";
        for (const char *p = name; *p != '\0' && pos < PATH_MAX_LEN - 1; p++) path[pos++] = *p;
        path[pos] = '\0';

        append_dec(path, &pos, PATH_MAX_LEN, (unsigned long long) pid);
        if (pos < PATH_MAX_LEN - 1) path[pos++] = '_';
        path[pos] = '\0';
        append_dec(path, &pos, PATH_MAX_LEN, (unsigned long long) tid);
        if (pos < PATH_MAX_LEN - 1) path[pos++] = '_';
        path[pos] = '\0';
        append_dec(path, &pos, PATH_MAX_LEN, (unsigned long long) sig);
        if (pos < PATH_MAX_LEN - 1) path[pos++] = '_';
        path[pos] = '\0';
        append_dec(path, &pos, PATH_MAX_LEN, (unsigned long long) time(NULL));
        const char *suffix = ".txt";
        for (const char *p = suffix; *p != '\0' && pos < PATH_MAX_LEN - 1; p++) path[pos++] = *p;
        path[pos] = '\0';

        fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    }

    if (fd >= 0) {
        put_str(fd, "=== ISEP Native Signal Crash ===\n");
        put_str(fd, "signal: ");
        put_dec(fd, sig);
        put_str(fd, " (");
        put_signal_name(fd, sig);
        put_str(fd, ")\ncode: ");
        put_dec(fd, si != NULL ? si->si_code : 0);
        put_str(fd, "\nfault addr: ");
        put_hex(fd, si != NULL ? (unsigned long long) (uintptr_t) si->si_addr : 0ULL);
        put_str(fd, "\npid: ");
        put_dec(fd, pid);
        put_str(fd, "\ntid: ");
        put_dec(fd, tid);
        put_str(fd, "\ntime: ");
        put_dec(fd, (long long) time(NULL));
        put_str(fd, "\npc: ");
        put_hex(fd, (unsigned long long) UC_PC(uc));
        put_str(fd, "\nsp: ");
        put_hex(fd, (unsigned long long) UC_SP(uc));
        put_str(fd, "\nlr: ");
        put_hex(fd, (unsigned long long) UC_LR(uc));
        put_str(fd, "\nbacktrace:\n");

        // 注意：_Unwind_Backtrace / dladdr 不是严格 async-signal-safe，
        // 若崩溃恰好发生在其内部可能拿不到完整栈；信号头信息已先写入文件。
        frame_ctx_t frame = {.fd = fd, .index = 0};
        _Unwind_Backtrace(frame_callback, &frame);

        (void) close(fd);
    }

    // 交回系统默认处理：debuggerd 照常产出 tombstone，NativeCrashLogger 的逻辑不受影响
    signal(sig, SIG_DFL);
    raise(sig);
    _exit(1);
}

/** 安装信号处理（由 Kotlin 侧调用）。返回是否安装成功。 */
JNIEXPORT jboolean JNICALL
Java_com_iptv_scanner_editor_pro_NativeSignalHandler_nativeInstall(JNIEnv *env, jobject thiz,
                                                                   jstring dir) {
    (void) thiz;
    if (dir == NULL) return JNI_FALSE;
    const char *utf = (*env)->GetStringUTFChars(env, dir, NULL);
    if (utf == NULL) return JNI_FALSE;
    size_t len = strlen(utf);
    if (len == 0 || len >= CRASH_DIR_MAX) {
        (*env)->ReleaseStringUTFChars(env, dir, utf);
        return JNI_FALSE;
    }
    memcpy(g_crash_dir, utf, len);
    g_crash_dir[len] = '\0';
    (*env)->ReleaseStringUTFChars(env, dir, utf);

    stack_t ss;
    memset(&ss, 0, sizeof(ss));
    ss.ss_sp = g_alt_stack;
    ss.ss_size = sizeof(g_alt_stack);
    ss.ss_flags = 0;
    if (sigaltstack(&ss, NULL) != 0) return JNI_FALSE;

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = crash_signal_handler;
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_RESETHAND;
    sigemptyset(&sa.sa_mask);

    const int signals[] = {SIGSEGV, SIGABRT, SIGBUS, SIGILL, SIGFPE, SIGTRAP};
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); i++) {
        if (sigaction(signals[i], &sa, NULL) != 0) return JNI_FALSE;
    }
    return JNI_TRUE;
}
