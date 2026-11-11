package com.iptv.scanner.editor.pro

import android.content.Context
import android.util.Log
import java.io.File

/**
 * 原生信号崩溃取证（SIGSEGV/SIGABRT/SIGBUS/SIGILL/SIGFPE/SIGTRAP）。
 *
 * 与 [NativeCrashLogger] 互补、不冲突：
 * - NativeCrashLogger 依赖后台 logcat + 系统 crash 缓冲区，崩溃后若 logcat 不可读或已被
 *   轮转就拿不到栈（盒子现场常见）；
 * - 这里在进程内直接装信号处理（libcrashhandler.so），崩溃瞬间把信号、fault 地址、
 *   寄存器与实时 backtrace 写到 filesDir/crash-reports/crash_native_*.txt；
 *   同时往 getExternalFilesDir()/crash-reports/ 镜像一份，盒子/电视无需 root 即可
 *   用 `adb pull /sdcard/Android/data/<包名>/files/crash-reports/` 取回真实调用栈。
 *
 * handler 写完后会把信号交回系统默认处理，debuggerd/NativeCrashLogger 流程保持不变。
 * 文件以 crash_ 开头，可在「设置 > 崩溃日志」里直接看到。
 */
object NativeSignalHandler {
    private const val TAG = "NativeSignalHandler"

    @Volatile
    private var installed = false

    fun install(context: Context) {
        if (installed) return
        try {
            val dir = File(context.filesDir, "crash-reports").apply { mkdirs() }
            // 外部目录可能不可用（未挂载/被限制），失败时只写私有目录
            val extDir = try {
                context.getExternalFilesDir(null)?.let { File(it, "crash-reports").apply { mkdirs() } }
            } catch (_: Throwable) {
                null
            }
            System.loadLibrary("crashhandler")
            installed = nativeInstall(dir.absolutePath, extDir?.absolutePath ?: "")
            Log.i(TAG, "native signal handler installed=$installed, dir=${dir.absolutePath}, " +
                "externalDir=${extDir?.absolutePath ?: "unavailable"}")
        } catch (e: Throwable) {
            // 该 ABI 没有打进 libcrashhandler（如模拟器 x86）时静默跳过，不影响启动
            Log.w(TAG, "native signal handler unavailable: ${e.message}")
        }
    }

    private external fun nativeInstall(dir: String, extDir: String): Boolean
}
