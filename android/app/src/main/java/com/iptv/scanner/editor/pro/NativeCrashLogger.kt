package com.iptv.scanner.editor.pro

import android.content.Context
import android.os.Build
import android.util.Log
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.data.store.PlayerSettingsStore
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 原生崩溃（SIGSEGV/SIGABRT 等）日志收集器。
 *
 * ACRA 只能捕获 Java 层异常（UncaughtExceptionHandler），无法捕获 native 信号崩溃。
 * 本类通过后台 logcat 进程记录日志，下次启动时检测上次是否异常退出，
 * 若是则将 logcat 日志保存为崩溃报告。
 *
 * 工作原理：
 * 1. 应用启动时调用 [checkPreviousCrash]：检查 "session_alive" 标记文件
 *    - 若内容以 "true" 开头，说明上次没有正常退出（被 SIGSEGV 杀死）
 *    - 将日志缓冲区中的崩溃日志 + 系统缓冲区 dump 保存到崩溃报告目录
 *    - 若上次会话运行在硬解模式，则加入「硬解崩溃设备黑名单」强制软解
 * 2. 仅在进程真正退出时调用 [markCleanExit]：标记文件写入 "false"
 *    （Activity 因深浅色/语言/密度等配置变化销毁时不得标记，否则同进程内的
 *    后续 native 崩溃会永久漏报）
 * 3. 后台线程周期性 dump logcat（不按 pid 过滤，保留 debuggerd/system 侧栈），
 *    以环形缓冲方式写入临时文件，避免孤儿进程与无限增长
 *
 * 崩溃报告保存路径：getFilesDir()/crash-reports/crash_<timestamp>.txt
 *
 * 与 ACRA 配合：
 * - Java 异常 → ACRA 捕获，保存到 getFilesDir()/ACRA/
 * - Native 崩溃 → 本类捕获，保存到 getFilesDir()/crash-reports/
 * - 两种报告都可在 设置 > 崩溃日志 中查看
 */
object NativeCrashLogger {
    private const val TAG = "NativeCrashLogger"

    /** 会话标记文件（标记上次会话是否正常退出，可携带上次生效的 hwdec） */
    private const val SESSION_FILE = "session_alive"

    /** logcat 临时文件（后台线程周期性写入） */
    private const val LOGCAT_TEMP_FILE = "logcat_buffer.txt"

    /** logcat 临时文件最大大小（512KB，超出后只保留尾部） */
    private const val MAX_LOGCAT_FILE_SIZE = 512L * 1024

    /** 崩溃报告目录名 */
    private const val CRASH_DIR = "crash-reports"

    /** 最多保留的崩溃报告数量 */
    private const val MAX_CRASH_FILES = 20

    /** 日志采集周期（毫秒） */
    private const val COLLECT_INTERVAL_MS = 5000L

    /** 每次从系统缓冲区 dump 的行数（不按 pid 过滤，含 debuggerd/system 日志） */
    private const val DUMP_LINES = 800

    @Volatile
    private var collectorRunning = false

    private var collectorThread: Thread? = null

    /**
     * 停止日志采集线程，释放资源。
     * 仅在进程真正退出时调用（Activity.onDestroy 中不要调用）。
     */
    fun stop() {
        collectorRunning = false
        collectorThread?.interrupt()
        collectorThread = null
    }

    /**
     * 在 Application.onCreate 中调用。
     *
     * 1. 检查上次会话是否异常退出，若是则保存崩溃日志
     * 2. 启动后台日志采集
     * 3. 标记本次会话为 "alive"（未正常退出状态）
     */
    fun init(context: Context) {
        checkPreviousCrash(context)
        startLogcatCapture(context)
        markSessionAlive(context)
    }

    /**
     * 检查上次会话是否异常退出。
     * 若 session_alive 文件内容以 "true" 开头，说明上次没有调用 markCleanExit（被 native 崩溃杀死）。
     */
    private fun checkPreviousCrash(context: Context) {
        try {
            val sessionFile = File(context.filesDir, SESSION_FILE)
            if (sessionFile.exists()) {
                val content = sessionFile.readText().trim()
                if (content.startsWith("true")) {
                    // playing=0 表示上次退出时并不在播放：更可能是按 Home 后被系统回收，
                    // 不是硬解 native 崩溃。此时不写崩溃报告、也不拉黑硬解。
                    // 旧格式没有 playing=，按原来的崩溃处理，避免升级后漏掉真实崩溃。
                    val playingFlag = if (content.contains("playing=")) {
                        content.substringAfter("playing=").substringBefore("|").trim()
                    } else {
                        null
                    }
                    if (playingFlag == "0") {
                        Log.i(TAG, "previous session ended while idle (likely background kill), " +
                            "skip crash report and hwdec blacklist")
                    } else {
                        // 上次会话异常退出（native 崩溃），保存日志缓冲区 + 系统缓冲区 dump
                        saveCrashReport(context)
                        // 上次会话是硬解：说明该 vo+hwdec 组合可能导致 native 崩溃，
                        // 加入设备黑名单（按组合记录），本次会话强制软解（用户手动切回硬解时解除）
                        val crashedHwdec = content.substringAfter("hwdec=", "")
                            .substringBefore("|").trim()
                        val crashedVo = content.substringAfter("vo=", "")
                            .substringBefore("|").trim()
                        if (crashedHwdec.isNotEmpty() && crashedHwdec != "no") {
                            // 直接写 SharedPreferences：此时 UserPrefs 门面尚未 init
                            prefs(context).edit()
                                .putBoolean(PlayerSettingsStore.KEY_HWDEC_CRASH_BLACKLIST, true)
                                // 旧格式没有 vo=：不写组合，由 isHwdecComboBlacklisted 按遗留规则
                                // 只挡 gpu+auto-copy，避免历史 auto-copy 崩溃挡住新的直写 Surface 方案
                                .apply {
                                    if (crashedVo.isNotEmpty()) {
                                        putString(
                                            PlayerSettingsStore.KEY_HWDEC_CRASH_COMBO,
                                            "$crashedVo|$crashedHwdec"
                                        )
                                    } else {
                                        remove(PlayerSettingsStore.KEY_HWDEC_CRASH_COMBO)
                                    }
                                }
                                .apply()
                            Log.w(TAG, "previous session crashed with vo=${crashedVo.ifEmpty { "?" }} " +
                                "hwdec=$crashedHwdec, this combo blacklisted for this device")
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "checkPreviousCrash failed: ${e.message}")
        }
    }

    /**
     * 保存崩溃报告。
     * 从日志缓冲区读取最近日志（取尾部，不截断崩溃点），并额外 dump 系统缓冲区
     * （不按 pid 过滤，保留 debuggerd/system_server 侧调用栈）。
     */
    private fun saveCrashReport(context: Context) {
        try {
            val crashDir = File(context.filesDir, CRASH_DIR).apply { mkdirs() }
            val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
            val crashFile = File(crashDir, "crash_$timestamp.txt")

            // 从临时文件读取尾部：崩溃点位于日志末尾，截取头部会把关键信息丢掉
            val tempLogcat = File(context.filesDir, LOGCAT_TEMP_FILE)
            val logcatContent = if (tempLogcat.exists()) {
                readTail(tempLogcat, MAX_LOGCAT_FILE_SIZE.toInt())
            } else {
                "(logcat buffer not found)"
            }

            // 系统缓冲区 dump：crash 缓冲区（tombstone/debuggerd）+ 全量最近日志，
            // 不按 pid 过滤，避免丢掉系统侧有用栈
            val dumpLogcat = dumpRecent(dumpCrashBuffer = true, lines = 3000)

            // 组装崩溃报告
            val report = buildString {
                appendLine("=== ISEP Native Crash Report ===")
                appendLine("Time: ${Date()}")
                appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL}")
                appendLine("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
                appendLine("ABI: ${Build.SUPPORTED_ABIS.joinToString(", ")}")
                appendLine("App Version: ${getAppVersion(context)}")
                appendLine()
                appendLine("=== Logcat Buffer (tail, from background collector) ===")
                appendLine(logcatContent)
                appendLine()
                appendLine("=== Logcat Dump (system + crash buffers, unfiltered) ===")
                appendLine(dumpLogcat)
            }

            crashFile.writeText(report)
            Log.i(TAG, "Crash report saved: ${crashFile.absolutePath}")

            // 清理临时日志文件
            tempLogcat.delete()

            // 清理过旧的崩溃报告
            cleanupOldCrashReports(crashDir)
        } catch (e: Exception) {
            Log.e(TAG, "saveCrashReport failed", e)
        }
    }

    /** 读取文件尾部 maxBytes 字节（避免截断崩溃点所在的尾部内容） */
    private fun readTail(file: File, maxBytes: Int): String {
        return try {
            val length = file.length()
            if (length <= maxBytes) {
                file.readText()
            } else {
                java.io.RandomAccessFile(file, "r").use { raf ->
                    raf.seek(length - maxBytes)
                    val buf = ByteArray(maxBytes)
                    val read = raf.read(buf)
                    String(buf, 0, read, Charsets.UTF_8)
                }
            }
        } catch (e: Exception) {
            "(read logcat tail failed: ${e.message})"
        }
    }

    /**
     * dump 系统日志缓冲区（不按 pid 过滤）。
     * @param dumpCrashBuffer 是否先 dump crash 缓冲区（debuggerd/tombstone）
     */
    private fun dumpRecent(dumpCrashBuffer: Boolean, lines: Int): String {
        val sb = StringBuilder()
        if (dumpCrashBuffer) {
            sb.appendLine("--- buffer: crash ---")
            sb.append(runLogcat(arrayOf("logcat", "-d", "-b", "crash", "-v", "threadtime")))
            sb.appendLine()
        }
        sb.appendLine("--- buffers: main, system, crash (last $lines lines, no pid filter) ---")
        sb.append(
            runLogcat(
                arrayOf(
                    "logcat", "-d", "-v", "threadtime",
                    "-b", "main", "-b", "system", "-b", "crash",
                    "-t", lines.toString()
                )
            )
        )
        return sb.toString()
    }

    private fun runLogcat(cmd: Array<String>): String {
        return try {
            val proc = ProcessBuilder(*cmd).redirectErrorStream(true).start()
            val text = proc.inputStream.bufferedReader().readText()
            proc.waitFor()
            text
        } catch (e: Exception) {
            "(logcat dump failed: ${e.message})"
        }
    }

    /**
     * 启动后台日志采集线程：周期性 dump 系统日志并追加到临时文件。
     * 使用周期性 dump 而非常驻 logcat 进程，避免进程被杀后留下孤儿进程。
     * 不按 pid 过滤，保留 debuggerd/system 侧日志。
     */
    private fun startLogcatCapture(context: Context) {
        val appContext = context.applicationContext
        val tempLogcat = File(appContext.filesDir, LOGCAT_TEMP_FILE)
        // 截断旧文件（避免上次残留无限增长）
        if (tempLogcat.exists() && tempLogcat.length() > MAX_LOGCAT_FILE_SIZE) {
            tempLogcat.delete()
        }
        if (collectorRunning) return
        collectorRunning = true
        collectorThread = Thread({
            while (collectorRunning) {
                try {
                    val text = dumpRecent(dumpCrashBuffer = false, lines = DUMP_LINES)
                    if (text.isNotBlank()) {
                        tempLogcat.appendText(text)
                        // 环形缓冲：超过上限时只保留尾部
                        if (tempLogcat.length() > MAX_LOGCAT_FILE_SIZE) {
                            val tail = readTail(tempLogcat, MAX_LOGCAT_FILE_SIZE.toInt())
                            tempLogcat.writeText(tail)
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "logcat collect failed: ${e.message}")
                }
                try {
                    Thread.sleep(COLLECT_INTERVAL_MS)
                } catch (e: InterruptedException) {
                    break
                }
            }
        }, "native-crash-logcat").apply { isDaemon = true; start() }
        Log.i(TAG, "Logcat collector started (file=${tempLogcat.absolutePath})")
    }

    /**
     * 记录当前生效的 vo+hwdec 组合，供下次启动判断「哪条渲染/解码路径导致崩溃」。
     * 按频道切换 vo/hwdec 时也会更新，保证崩溃时记录的是真实生效值。
     * 保留已有的 playing 标记，避免切换时把「播放中」误清成空闲。
     */
    fun setActiveDecode(context: Context, vo: String, hwdec: String) {
        try {
            val appContext = context.applicationContext
            val file = File(appContext.filesDir, SESSION_FILE)
            val playing = try {
                if (file.exists()) {
                    val content = file.readText()
                    if (content.startsWith("true")) {
                        content.substringAfter("playing=", "0").substringBefore("|").trim()
                    } else {
                        "0"
                    }
                } else {
                    "0"
                }
            } catch (_: Throwable) {
                "0"
            }
            file.writeText("true|vo=$vo|hwdec=$hwdec|playing=${playing.ifEmpty { "0" }}")
        } catch (e: Exception) {
            Log.w(TAG, "setActiveDecode failed: ${e.message}")
        }
    }

    /**
     * 标记当前是否处于「播放中」。
     *
     * 崩溃判定只认「播放中异常退出」：按 Home 后进程被系统回收时播放早已停止，
     * 不应被当成硬解崩溃而拉黑硬解。
     */
    fun setPlaybackActive(context: Context, active: Boolean) {
        try {
            val appContext = context.applicationContext
            val file = File(appContext.filesDir, SESSION_FILE)
            if (!file.exists()) return
            val content = file.readText()
            // 已正常退出（false）后不再改写，避免把干净会话重新标成 alive
            if (!content.startsWith("true")) return
            val hwdec = content.substringAfter("hwdec=", "unknown").substringBefore("|").trim()
            val vo = content.substringAfter("vo=", "unknown").substringBefore("|").trim()
            file.writeText(
                "true|vo=${vo.ifEmpty { "unknown" }}|hwdec=${hwdec.ifEmpty { "unknown" }}" +
                    "|playing=${if (active) 1 else 0}"
            )
        } catch (e: Exception) {
            Log.w(TAG, "setPlaybackActive failed: ${e.message}")
        }
    }

    /**
     * 标记本次会话为 "alive"（未正常退出），并记录当前 hwdec 设置。
     * 若下次启动时此标记仍以 "true" 开头，说明本次被 native 崩溃杀死。
     */
    private fun markSessionAlive(context: Context) {
        try {
            val hwdec = try {
                prefs(context)
                    .getString(PlayerSettingsStore.KEY_HWDEC, null)
                    ?.takeIf { it.isNotEmpty() } ?: "unknown"
            } catch (e: Exception) {
                "unknown"
            }
            val vo = try {
                prefs(context)
                    .getString(PlayerSettingsStore.KEY_VO, null)
                    ?.takeIf { it.isNotEmpty() } ?: "unknown"
            } catch (e: Exception) {
                "unknown"
            }
            File(context.filesDir, SESSION_FILE).writeText("true|vo=$vo|hwdec=$hwdec|playing=0")
        } catch (e: Exception) {
            Log.w(TAG, "markSessionAlive failed: ${e.message}")
        }
    }

    /** 启动早期使用（UserPrefs 门面尚未 init） */
    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(UserPrefs.PREFS_NAME, Context.MODE_PRIVATE)

    /**
     * 标记正常退出（仅在进程真正退出时调用）。
     * 写入 "false"，下次启动时不会误报崩溃。
     *
     * 注意：Activity 因配置变化（深浅色/语言/字体缩放/密度）销毁时进程仍然存活，
     * 此时不得调用本方法，否则同进程内后续的 native 崩溃会被永久漏报。
     */
    fun markCleanExit(context: Context) {
        try {
            File(context.filesDir, SESSION_FILE).writeText("false")
        } catch (e: Exception) {
            Log.w(TAG, "markCleanExit failed: ${e.message}")
        }
    }

    /**
     * 获取所有崩溃报告文件列表（按修改时间降序，最新的在前）。
     */
    fun getCrashReports(context: Context): List<File> {
        val dir = File(context.filesDir, CRASH_DIR)
        if (!dir.exists()) return emptyList()
        return dir.listFiles()
            ?.filter { it.isFile && it.name.startsWith("crash_") }
            ?.sortedByDescending { it.lastModified() }
            ?: emptyList()
    }

    /**
     * 读取指定崩溃报告的内容。
     */
    fun readCrashReport(file: File): String {
        return try {
            file.readText()
        } catch (e: IOException) {
            "读取失败: ${e.message}"
        }
    }

    /**
     * 删除指定崩溃报告。
     */
    fun deleteCrashReport(file: File): Boolean {
        return file.delete()
    }

    /**
     * 清除所有崩溃报告。
     */
    fun clearAllCrashReports(context: Context) {
        val dir = File(context.filesDir, CRASH_DIR)
        dir.listFiles()?.filter { it.isFile }?.forEach { it.delete() }
    }

    /**
     * 清理过旧的崩溃报告，只保留最近的 MAX_CRASH_FILES 条。
     */
    private fun cleanupOldCrashReports(crashDir: File) {
        val files = crashDir.listFiles()
            ?.filter { it.isFile && it.name.startsWith("crash_") }
            ?.sortedByDescending { it.lastModified() }
            ?: return
        if (files.size > MAX_CRASH_FILES) {
            files.drop(MAX_CRASH_FILES).forEach { it.delete() }
        }
    }

    private fun getAppVersion(context: Context): String {
        return try {
            val pm = context.packageManager
            val info = pm.getPackageInfo(context.packageName, 0)
            "${info.versionName} (${info.longVersionCode})"
        } catch (e: Exception) {
            "unknown"
        }
    }
}
