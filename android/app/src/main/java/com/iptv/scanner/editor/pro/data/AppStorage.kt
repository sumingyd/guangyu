package com.iptv.scanner.editor.pro.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.util.Log
import java.io.File

/**
 * Android 数据目录解析：共享存储 /sdcard/GuangYu 优先，不可用时回退应用私有目录。
 *
 * 目录结构（根目录下固定五类）：
 * ```
 * GuangYu/
 * ├── config/   配置（config.ini、订阅、断点、书签、映射）
 * ├── logs/     日志（app.log、迁移记录）
 * ├── cache/    缓存（台标、缩略图、截图、字幕、EPG）
 * ├── data/     长期数据（收藏、播放历史）
 * └── exports/  导出（M3U、EPG、备份、切片）
 * ```
 *
 * 共享目录需要 Android 11+ 的「所有文件访问」权限（MANAGE_EXTERNAL_STORAGE），
 * Android 10 及以下需要 WRITE_EXTERNAL_STORAGE 运行时权限；未授权时自动回退到
 * getExternalFilesDir()/GuangYu，覆盖安装不丢失，但文件管理器看不到。
 *
 * 注意：Python 端（utils/app_paths.py）以同一套规则解析路径，本对象只负责
 * 权限判定、候选路径与界面入口，实际生效路径以 Python 回报的 get_storage_info 为准。
 */
object AppStorage {
    private const val TAG = "AppStorage"

    const val DIR_NAME = "GuangYu"
    const val SUB_CONFIG = "config"
    const val SUB_LOGS = "logs"
    const val SUB_CACHE = "cache"
    const val SUB_DATA = "data"
    const val SUB_EXPORTS = "exports"

    val SUB_DIRS = listOf(SUB_CONFIG, SUB_LOGS, SUB_CACHE, SUB_DATA, SUB_EXPORTS)

    /** 共享存储根目录 /sdcard/GuangYu */
    @Suppress("DEPRECATION")
    fun publicRoot(): File =
        File(Environment.getExternalStorageDirectory(), DIR_NAME)

    /** 应用私有根目录 Android/data/<包名>/files/GuangYu */
    fun privateRoot(context: Context): File {
        val base = context.getExternalFilesDir(null) ?: context.filesDir
        return File(base, DIR_NAME)
    }

    /** 所有文件访问权限（Android 11+）或旧版写外部存储权限是否已授予 */
    fun hasStoragePermission(context: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                Environment.isExternalStorageManager()
            } else {
                context.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE) ==
                    android.content.pm.PackageManager.PERMISSION_GRANTED
            }
        } catch (e: Exception) {
            Log.w(TAG, "hasStoragePermission failed: ${e.message}")
            false
        }
    }

    /** 目录是否真实可写（权限声明与实际挂载可能不一致，必须写探针验证） */
    fun isWritable(dir: File): Boolean {
        return try {
            if (!dir.exists() && !dir.mkdirs()) return false
            val probe = File(dir, ".write_probe")
            probe.writeText("")
            probe.delete()
            true
        } catch (e: Exception) {
            false
        }
    }

    /** 当前实际使用的根目录：共享目录可写则用共享，否则用私有目录 */
    fun activeRoot(context: Context): File {
        val public = publicRoot()
        if (hasStoragePermission(context) && isWritable(public)) return public
        return privateRoot(context)
    }

    /** 当前是否使用共享目录（文件管理器可见） */
    fun isUsingShared(context: Context): Boolean =
        activeRoot(context).absolutePath == publicRoot().absolutePath

    fun configDir(context: Context) = File(activeRoot(context), SUB_CONFIG)
    fun logsDir(context: Context) = File(activeRoot(context), SUB_LOGS)
    fun cacheDir(context: Context) = File(activeRoot(context), SUB_CACHE)
    fun dataDir(context: Context) = File(activeRoot(context), SUB_DATA)
    fun exportDir(context: Context) = File(activeRoot(context), SUB_EXPORTS)

    /** 日志文件路径（Python 与 Kotlin 共用同一位置） */
    fun logFile(context: Context) = File(logsDir(context), "app.log")

    /**
     * 导出文件目标：共享目录可用时返回 GuangYu/exports 下的 File；
     * 不可用时返回 null，调用方继续走 MediaStore Downloads（保证用户仍能拿到文件）。
     */
    fun exportFile(context: Context, filename: String): File? {
        if (!isUsingShared(context)) return null
        val dir = exportDir(context)
        if (!dir.exists() && !dir.mkdirs()) return null
        return File(dir, filename)
    }

    /** 把所有子目录建好（幂等） */
    fun ensureLayout(context: Context): File {
        val root = activeRoot(context)
        SUB_DIRS.forEach { File(root, it).mkdirs() }
        return root
    }

    /**
     * 跳转「所有文件访问权限」设置页。Android 11+ 用应用专属页，
     * 失败时退回全部文件访问列表页；更早版本返回 false 由调用方走运行时权限。
     */
    fun openAllFilesAccessSettings(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return false
        val candidates = listOf(
            Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                data = Uri.parse("package:${context.packageName}")
            },
            Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
        )
        for (intent in candidates) {
            try {
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(intent)
                return true
            } catch (e: Exception) {
                Log.w(TAG, "open all files access failed: ${e.message}")
            }
        }
        return false
    }

    /** 用系统文件管理器打开目录；设备无可用文件管理器时返回 false */
    fun openDirectory(context: Context, dir: File): Boolean {
        if (!dir.exists() && !dir.mkdirs()) return false
        // DocumentsUI 的 primary 卷路径格式：document/primary%3AGuangYu
        val relative = dir.absolutePath
            .removePrefix(Environment.getExternalStorageDirectory().absolutePath)
            .trimStart('/')
        val uri = Uri.parse(
            "content://com.android.externalstorage.documents/document/primary%3A" +
                Uri.encode(relative)
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "vnd.android.document/directory")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return try {
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            Log.w(TAG, "openDirectory failed: ${e.message}")
            false
        }
    }

    /** 重启应用（切换数据目录后需要重新初始化 Python 侧路径常量） */
    fun restartApp(context: Context) {
        try {
            val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
                ?: return
            intent.addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_CLEAR_TASK
            )
            context.startActivity(intent)
            Runtime.getRuntime().exit(0)
        } catch (e: Exception) {
            Log.e(TAG, "restartApp failed", e)
        }
    }
}
