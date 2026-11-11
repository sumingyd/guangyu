package com.iptv.scanner.editor.pro

import android.util.Log
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.imageLoader
import coil.memory.MemoryCache
import coil.request.CachePolicy
import com.chaquo.python.android.PyApplication
import org.acra.ACRA
import org.acra.config.CoreConfigurationBuilder
import org.acra.data.StringFormat
import java.io.File

/**
 * 自定义 Application 类，继承 Chaquopy 的 [PyApplication]。
 *
 * 职责：
 * 1. 调用 super.onCreate() 完成 Chaquopy Python 初始化
 * 2. 初始化 ACRA（Java 异常崩溃捕获）
 * 3. 初始化 NativeCrashLogger（native SIGSEGV 崩溃捕获）
 * 4. 配置 Coil ImageLoader（台标缓存上限 50MB + 磁盘缓存 100MB）
 * 5. 内存压力处理：onTrimMemory 回调低内存时清理缓存
 * 6. 崩溃报告检测：启动时检查上次崩溃报告并提示用户
 *
 * 崩溃报告路径：
 * - Java 异常：getFilesDir()/ACRA/（ACRA 管理）
 * - Native 崩溃：getFilesDir()/crash-reports/（NativeCrashLogger 管理）
 */
class IptvApplication : PyApplication(), ImageLoaderFactory {

    companion object {
        private const val TAG = "IptvApplication"

        /** Coil 内存缓存上限（bytes），约 50MB */
        private const val COIL_MEMORY_CACHE_BYTES = 50L * 1024 * 1024

        /** Coil 磁盘缓存上限（bytes），约 100MB */
        private const val COIL_DISK_CACHE_BYTES = 100L * 1024 * 1024

        /** volatile 标记：上次崩溃报告路径，供 UI 检测并提示用户 */
        @Volatile
        var lastCrashReportPath: String? = null
            private set
    }

    override fun onCreate() {
        super.onCreate()

        // 拷贝 AV3A(Audio Vivid) 解码器运行时模型到 filesDir
        // libavs3a_decoder 初始化时会 fopen("model.bin")，找不到会初始化失败，
        // 其 C 层回退路径固定为 /data/data/<pkg>/files/model.bin
        copyAv3aModelIfNeeded()

        // 初始化 ACRA（Java 异常崩溃捕获）
        try {
            val config = CoreConfigurationBuilder()
                .withBuildConfigClass(BuildConfig::class.java)
                .withReportFormat(StringFormat.JSON)
            ACRA.init(this, config)
            Log.i(TAG, "ACRA initialized")
        } catch (e: Exception) {
            Log.e(TAG, "ACRA initialization failed", e)
        }

        // 初始化原生崩溃日志收集（SIGSEGV 等）
        try {
            NativeCrashLogger.init(this)
            Log.i(TAG, "NativeCrashLogger initialized")
        } catch (e: Exception) {
            Log.e(TAG, "NativeCrashLogger initialization failed", e)
        }

        // 原生信号 handler：崩溃瞬间把 backtrace 直接写到 crash-reports（不依赖 logcat）
        try {
            NativeSignalHandler.install(this)
        } catch (e: Exception) {
            Log.e(TAG, "NativeSignalHandler initialization failed", e)
        }

        // 检查上次崩溃报告
        checkLastCrashReport()
    }

    // -----------------------------------------------------------------
    // AV3A 解码模型：assets/model.bin → filesDir/model.bin
    //
    // mpv-android-avs 的 libavs3a_decoder.so 在 Avs3AllocDecoder() 内部
    // 通过 fopen("model.bin") 读取模型，其 C 层回退目录固定为
    // /data/data/<pkg>/files。应用启动时从 assets 拷贝一份过去，
    // 文件已存在且大小一致时跳过（升级 APK 后大小变化会自动覆盖）。
    // -----------------------------------------------------------------
    private fun copyAv3aModelIfNeeded() {
        try {
            val model = File(filesDir, "model.bin")
            val tmp = File(filesDir, "model.bin.tmp")
            assets.open("model.bin").use { input ->
                tmp.outputStream().use { output -> input.copyTo(output) }
            }
            if (model.exists() && model.length() == tmp.length()) {
                tmp.delete()
                Log.d(TAG, "AV3A model.bin already up to date")
                return
            }
            if (model.exists() && !model.delete()) {
                throw java.io.IOException("cannot replace stale model.bin")
            }
            if (!tmp.renameTo(model)) {
                throw java.io.IOException("rename model.bin.tmp failed")
            }
            Log.i(TAG, "AV3A model.bin copied to filesDir (${model.length()} bytes)")
        } catch (e: Exception) {
            // assets 中无 model.bin（旧版构建流程）或拷贝失败：
            // 仅影响 AV3A 音频解码，不阻塞应用启动
            Log.w(TAG, "copyAv3aModelIfNeeded failed (AV3A audio unavailable)", e)
        }
    }

    // -----------------------------------------------------------------
    // Coil ImageLoader 工厂：自定义内存/磁盘缓存上限 + 台标预加载策略
    //
    // 默认 Coil 内存缓存为可用内存的 25%，对于台标密集的频道列表可能不够。
    // 这里设置固定 50MB 内存缓存 + 100MB 磁盘缓存，并启用内存和磁盘缓存。
    //
    // 台标预加载策略：通过 Coil 的 crossfade + 磁盘缓存实现。
    // 频道列表滚动时 AsyncImage 自动使用缓存，首次加载后后续命中缓存。
    // -----------------------------------------------------------------
    override fun newImageLoader(): ImageLoader {
        return ImageLoader.Builder(this)
            .crossfade(true)
            .crossfade(200)
            // 内存缓存：50MB 上限
            .memoryCache {
                MemoryCache.Builder(this)
                    .maxSizeBytes(COIL_MEMORY_CACHE_BYTES.toInt())
                    .build()
            }
            // 磁盘缓存：100MB 上限，存放在 cacheDir/coil 目录
            .diskCache {
                DiskCache.Builder()
                    .directory(File(cacheDir, "coil_cache"))
                    .maxSizeBytes(COIL_DISK_CACHE_BYTES)
                    .build()
            }
            // 允许内存和磁盘缓存
            .memoryCachePolicy(CachePolicy.ENABLED)
            .diskCachePolicy(CachePolicy.ENABLED)
            .respectCacheHeaders(false)
            .build()
    }

    // -----------------------------------------------------------------
    // 内存压力处理：onTrimMemory 回调
    //
    // Android 系统在内存不足时调用 onTrimMemory，应用应释放非关键资源。
    //
    // 处理策略：
    // - TRIM_MEMORY_RUNNING_LOW：清空 Coil 内存缓存
    // - TRIM_MEMORY_RUNNING_CRITICAL：清空 Coil 内存缓存 + 缩略图缓存
    // - TRIM_MEMORY_MODERATE / TRIM_MEMORY_COMPLETE：清空所有缓存 + 释放副播放器
    //
    // 通过单例 ViewModel 的 onTrimMemoryRequested 回调通知 ViewModel 释放资源。
    // -----------------------------------------------------------------
    private var trimMemoryCallback: ((Int) -> Unit)? = null

    fun setTrimMemoryCallback(callback: (Int) -> Unit) {
        trimMemoryCallback = callback
    }

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        Log.i(TAG, "onTrimMemory: level=$level")

        when (level) {
            TRIM_MEMORY_RUNNING_LOW -> {
                // 系统内存低：清空 Coil 内存缓存
                val loader = applicationContext.imageLoader
                loader.memoryCache?.clear()
                Log.i(TAG, "onTrimMemory: cleared Coil memory cache (RUNNING_LOW)")
            }
            TRIM_MEMORY_RUNNING_CRITICAL -> {
                // 系统内存严重不足：清空所有内存缓存
                val loader = applicationContext.imageLoader
                loader.memoryCache?.clear()
                Log.w(TAG, "onTrimMemory: cleared Coil memory cache (RUNNING_CRITICAL)")
            }
            TRIM_MEMORY_MODERATE, TRIM_MEMORY_COMPLETE -> {
                // 应用在后台且系统需要回收内存：清空所有缓存
                val loader = applicationContext.imageLoader
                loader.memoryCache?.clear()
                loader.diskCache?.clear()
                Log.w(TAG, "onTrimMemory: cleared all caches (level=$level)")
                // 后台低内存回收不是硬解崩溃：先标记非播放中，
                // 避免下次启动把系统回收误判成 MediaCodec 崩溃而拉黑硬解。
                NativeCrashLogger.setPlaybackActive(this, false)
            }
        }

        // 通知 ViewModel 释放副播放器等资源
        trimMemoryCallback?.invoke(level)
    }

    // -----------------------------------------------------------------
    // 崩溃报告检测：启动时检查上次是否有崩溃报告
    //
    // 检查路径：
    // - ACRA 报告目录：getFilesDir()/ACRA/
    // - Native 崩溃报告：getFilesDir()/crash-reports/
    //
    // 如果找到崩溃报告，保存路径到 lastCrashReportPath，
    // AppViewModel 初始化后检测此字段并提示用户。
    // -----------------------------------------------------------------
    private fun checkLastCrashReport() {
        try {
            // 检查 ACRA 报告
            val acraDir = File(filesDir, "ACRA")
            if (acraDir.exists()) {
                val reports = acraDir.listFiles { f ->
                    f.isFile && (f.name.endsWith(".json") || f.name.endsWith(".stacktrace"))
                }
                if (reports != null && reports.isNotEmpty()) {
                    // 按最后修改时间排序，取最新的
                    val latest = reports.maxByOrNull { it.lastModified() }
                    if (latest != null) {
                        lastCrashReportPath = latest.absolutePath
                        Log.w(TAG, "Last crash report found: ${latest.name}")
                    }
                }
            }

            // 检查 Native 崩溃报告
            if (lastCrashReportPath == null) {
                val nativeDir = File(filesDir, "crash-reports")
                if (nativeDir.exists()) {
                    val reports = nativeDir.listFiles { f -> f.isFile && f.name.endsWith(".txt") }
                    if (reports != null && reports.isNotEmpty()) {
                        val latest = reports.maxByOrNull { it.lastModified() }
                        if (latest != null) {
                            lastCrashReportPath = latest.absolutePath
                            Log.w(TAG, "Last native crash report found: ${latest.name}")
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "checkLastCrashReport failed", e)
        }
    }

    /** 标记崩溃报告为已处理（用户查看或忽略后调用） */
    fun markCrashReportHandled() {
        lastCrashReportPath = null
    }

    /** 导出崩溃报告到指定目录（用户分享日志时调用） */
    fun exportCrashReports(destDir: File): Int {
        var count = 0
        try {
            // 复制 ACRA 报告
            val acraDir = File(filesDir, "ACRA")
            if (acraDir.exists()) {
                acraDir.listFiles()?.forEach { f ->
                    if (f.isFile) {
                        f.copyTo(File(destDir, "acra_${f.name}"), overwrite = true)
                        count++
                    }
                }
            }
            // 复制 Native 崩溃报告
            val nativeDir = File(filesDir, "crash-reports")
            if (nativeDir.exists()) {
                nativeDir.listFiles()?.forEach { f ->
                    if (f.isFile) {
                        f.copyTo(File(destDir, "native_${f.name}"), overwrite = true)
                        count++
                    }
                }
            }
            // 复制 app.log
            val appLog = File(filesDir, "ISEP/app.log")
            if (appLog.exists()) {
                appLog.copyTo(File(destDir, "app.log"), overwrite = true)
                count++
            }
        } catch (e: Exception) {
            Log.e(TAG, "exportCrashReports failed", e)
        }
        return count
    }
}
