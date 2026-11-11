/*
 * 原生信号崩溃取证：SIGSEGV / SIGABRT / SIGBUS / SIGILL / SIGFPE / SIGTRAP。
 *
 * 与 NativeCrashLogger 的分工：
 * - NativeCrashLogger 通过后台 logcat + 系统 crash 缓冲区取证（tombstone/debuggerd），
 *   依赖 logcat 可读、且崩溃后日志未被轮转；盒子现场经常拿不到。
 * - 本 handler 在信号发生的同一线程上直接写文件（不走 logcat），
 *   把信号、fault 地址、寄存器与实时调用栈落到 filesDir/crash-reports/crash_native_*.txt，
 *   同时镜像一份到 getExternalFilesDir()/crash-reports/（无需 root，adb pull 即可取回）。
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
#define REPORT_BUF_SIZE 16384

static char g_crash_dir[CRASH_DIR_MAX];
static char g_crash_dir_ext[CRASH_DIR_MAX];
static char g_alt_stack[64 * 1024];
static volatile sig_atomic_t g_in_handler = 0;

/**
 * 取证内容先攒进静态缓冲，最后一次性写两份（私有目录 + 外部目录），
 * 避免重复 unwind，也不引入 malloc/stdio。
 */
typedef struct {
    int fd_app;
    int fd_ext;
    int len;
    char buf[REPORT_BUF_SIZE];
} report_t;

static report_t g_report;

static void buf_append(report_t *r, const char *s, int n) {
    if (r == NULL || s == NULL || n <= 0) return;
    if (n > REPORT_BUF_SIZE - r->len) n = REPORT_BUF_SIZE - r->len;
    if (n <= 0) return;
    memcpy(r->buf + r->len, s, (size_t) n);
    r->len += n;
}

static void put_str(report_t *r, const char *s) {
    if (s == NULL) return;
    size_t len = strlen(s);
    if (len > 0) buf_append(r, s, (int) len);
}

static void put_hex(report_t *r, unsigned long long value) {
    char buf[2 + 16];
    buf[0] = '0';
    buf[1] = 'x';
    for (int i = 0; i < 16; i++) {
        int shift = (15 - i) * 4;
        int digit = (int) ((value >> shift) & 0xF);
        buf[2 + i] = (char) (digit < 10 ? ('0' + digit) : ('a' + digit - 10));
    }
    buf_append(r, buf, (int) sizeof(buf));
}

static void put_dec(report_t *r, long long value) {
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
    buf_append(r, buf + pos, (int) sizeof(buf) - pos);
}

static void put_signal_name(report_t *r, int sig) {
    switch (sig) {
        case SIGSEGV: put_str(r, "SIGSEGV"); break;
        case SIGABRT: put_str(r, "SIGABRT"); break;
        case SIGBUS:  put_str(r, "SIGBUS"); break;
        case SIGILL:  put_str(r, "SIGILL"); break;
        case SIGFPE:  put_str(r, "SIGFPE"); break;
        case SIGTRAP: put_str(r, "SIGTRAP"); break;
        default:      put_str(r, "SIG?"); break;
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
    report_t *report;
    int index;
} frame_ctx_t;

/** _Unwind_Backtrace 回调：每个栈帧写一行 `#序号 pc=0x.. 模块+偏移`。 */
static _Unwind_Reason_Code frame_callback(struct _Unwind_Context *ctx, void *arg) {
    frame_ctx_t *frame = (frame_ctx_t *) arg;
    if (frame->index >= MAX_FRAMES) return _URC_END_OF_STACK;
    uintptr_t pc = _Unwind_GetIP(ctx);
    if (pc == 0) return _URC_END_OF_STACK;

    report_t *r = frame->report;
    put_str(r, "#");
    put_dec(r, frame->index);
    put_str(r, " pc=");
    put_hex(r, (unsigned long long) pc);

    Dl_info info;
    if (dladdr((void *) pc, &info) != 0 && info.dli_fname != NULL) {
        const char *name = info.dli_fname;
        const char *slash = strrchr(name, '/');
        if (slash != NULL) name = slash + 1;
        put_str(r, " ");
        put_str(r, name);
        put_str(r, "+");
        put_hex(r, (unsigned long long) (pc - (uintptr_t) info.dli_fbase));
    } else {
        put_str(r, " ?");
    }
    put_str(r, "\n");
    frame->index++;
    return _URC_NO_REASON;
}

/** 在 dir 下拼 crash_native_<pid>_<tid>_<sig>_<time>.txt；dir 为空时 path 置空。 */
static void build_crash_path(char *path, const char *dir, long long pid, long long tid, int sig) {
    path[0] = '\0';
    if (dir == NULL || dir[0] == '\0') return;
    int pos = 0;
    for (int i = 0; dir[i] != '\0' && pos < PATH_MAX_LEN - 1; i++) path[pos++] = dir[i];
    if (pos < PATH_MAX_LEN - 1) path[pos++] = '/';
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
}

/** 写 `模块名+偏移`（用 dladdr 解析地址所属 so 与偏移） */
static void put_symbol(report_t *r, unsigned long long addr) {
    Dl_info info;
    if (addr != 0 && dladdr((void *) (uintptr_t) addr, &info) != 0 && info.dli_fname != NULL) {
        const char *name = info.dli_fname;
        const char *slash = strrchr(name, '/');
        if (slash != NULL) name = slash + 1;
        put_str(r, name);
        put_str(r, "+");
        put_hex(r, (unsigned long long) ((uintptr_t) addr - (uintptr_t) info.dli_fbase));
    } else {
        put_str(r, "?");
    }
}

/** 读崩溃线程名（/proc/self/task/<tid>/comm） */
static void put_thread_name(report_t *r, long long tid) {
    char path[64];
    int pos = 0;
    const char *prefix = "/proc/self/task/";
    for (const char *p = prefix; *p != '\0' && pos < 60; p++) path[pos++] = *p;
    path[pos] = '\0';
    append_dec(path, &pos, 64, (unsigned long long) tid);
    if (pos < 63) path[pos++] = '/';
    path[pos] = '\0';
    const char *suffix = "comm";
    for (const char *p = suffix; *p != '\0' && pos < 63; p++) path[pos++] = *p;
    path[pos] = '\0';

    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        put_str(r, "?");
        return;
    }
    char buf[32];
    ssize_t n = read(fd, buf, sizeof(buf));
    (void) close(fd);
    if (n <= 0) {
        put_str(r, "?");
        return;
    }
    int len = 0;
    while (len < (int) n && buf[len] != '\n') len++;
    buf_append(r, buf, len);
}

/**
 * 从崩溃时的 sp 向上扫描栈内存，把其中能解析到模块的地址打印成伪栈。
 * ARM 栈向下生长，sp 以上是调用者的栈帧；_Unwind 在信号栈上拿不到真实调用链，
 * 这里用不可回溯的内存扫描补一份「谁调用到崩溃点」的证据。
 */
static void scan_stack(report_t *r, unsigned long long sp) {
    if (sp == 0) return;
    const uintptr_t *words = (const uintptr_t *) (uintptr_t) sp;
    put_str(r, "stack scan (sp+offset -> module+off):\n");
    for (int i = 0; i < 128; i++) {
        uintptr_t value = words[i];
        if (value < 0x1000) continue;
        Dl_info info;
        if (dladdr((void *) value, &info) == 0 || info.dli_fname == NULL) continue;
        const char *name = info.dli_fname;
        const char *slash = strrchr(name, '/');
        if (slash != NULL) name = slash + 1;
        put_str(r, "  [");
        put_dec(r, i * 4);
        put_str(r, "] ");
        put_str(r, name);
        put_str(r, "+");
        put_hex(r, (unsigned long long) (value - (uintptr_t) info.dli_fbase));
        put_str(r, "\n");
    }
}

/** 信号处理函数：只做取证（私有目录 + 外部目录各一份） + 交回系统默认处理。 */
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

    char path_app[PATH_MAX_LEN];
    char path_ext[PATH_MAX_LEN];
    build_crash_path(path_app, g_crash_dir, pid, tid, sig);
    build_crash_path(path_ext, g_crash_dir_ext, pid, tid, sig);

    report_t *r = &g_report;
    r->len = 0;
    r->fd_app = path_app[0] != '\0' ? open(path_app, O_WRONLY | O_CREAT | O_TRUNC, 0600) : -1;
    // 外部目录通常无需 root 就能 adb pull；打不开（无外部存储）时只写私有目录
    r->fd_ext = path_ext[0] != '\0' ? open(path_ext, O_WRONLY | O_CREAT | O_TRUNC, 0600) : -1;

    put_str(r, "=== ISEP Native Signal Crash ===\n");
    put_str(r, "signal: ");
    put_dec(r, sig);
    put_str(r, " (");
    put_signal_name(r, sig);
    put_str(r, ")\ncode: ");
    put_dec(r, si != NULL ? si->si_code : 0);
    put_str(r, "\nfault addr: ");
    put_hex(r, si != NULL ? (unsigned long long) (uintptr_t) si->si_addr : 0ULL);
    put_str(r, "\npid: ");
    put_dec(r, pid);
    put_str(r, "\ntid: ");
    put_dec(r, tid);
    put_str(r, "\ntime: ");
    put_dec(r, (long long) time(NULL));
    put_str(r, "\npc: ");
    put_hex(r, (unsigned long long) UC_PC(uc));
    put_str(r, "\nsp: ");
    put_hex(r, (unsigned long long) UC_SP(uc));
    put_str(r, "\nlr: ");
    put_hex(r, (unsigned long long) UC_LR(uc));
    put_str(r, "\nthread: ");
    put_thread_name(r, tid);
    put_str(r, "\npc_sym: ");
    put_symbol(r, (unsigned long long) UC_PC(uc));
    put_str(r, "\nlr_sym: ");
    put_symbol(r, (unsigned long long) UC_LR(uc));
    scan_stack(r, (unsigned long long) UC_SP(uc));
    put_str(r, "\nbacktrace:\n");

    // 注意：_Unwind_Backtrace / dladdr 不是严格 async-signal-safe，
    // 若崩溃恰好发生在其内部可能拿不到完整栈；信号头信息已先写入缓冲。
    frame_ctx_t frame = {.report = r, .index = 0};
    _Unwind_Backtrace(frame_callback, &frame);

    if (r->fd_app >= 0) {
        (void) write(r->fd_app, r->buf, (size_t) r->len);
        (void) close(r->fd_app);
    }
    if (r->fd_ext >= 0) {
        (void) write(r->fd_ext, r->buf, (size_t) r->len);
        (void) close(r->fd_ext);
    }

    // 交回系统默认处理：debuggerd 照常产出 tombstone，NativeCrashLogger 的逻辑不受影响
    signal(sig, SIG_DFL);
    raise(sig);
    _exit(1);
}

/** 把一个 Java 字符串目录拷进定长缓冲；空串/超长视为无效。 */
static int copy_dir(JNIEnv *env, jstring jdir, char *dst) {
    if (jdir == NULL) return 0;
    const char *utf = (*env)->GetStringUTFChars(env, jdir, NULL);
    if (utf == NULL) return 0;
    size_t len = strlen(utf);
    if (len == 0 || len >= CRASH_DIR_MAX) {
        (*env)->ReleaseStringUTFChars(env, jdir, utf);
        return 0;
    }
    memcpy(dst, utf, len);
    dst[len] = '\0';
    (*env)->ReleaseStringUTFChars(env, jdir, utf);
    return 1;
}

/** 安装信号处理（由 Kotlin 侧调用）。返回是否安装成功。 */
JNIEXPORT jboolean JNICALL
Java_com_iptv_scanner_editor_pro_NativeSignalHandler_nativeInstall(JNIEnv *env, jobject thiz,
                                                                   jstring dir, jstring extDir) {
    (void) thiz;
    g_crash_dir[0] = '\0';
    g_crash_dir_ext[0] = '\0';
    int ok = copy_dir(env, dir, g_crash_dir);
    (void) copy_dir(env, extDir, g_crash_dir_ext);
    if (!ok) return JNI_FALSE;

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
