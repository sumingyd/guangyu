package com.iptv.scanner.editor.pro.ui

import android.app.Application
import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.media.MediaMetadataRetriever
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.data.IptvEpgList
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.data.IptvEpgSource
import com.iptv.scanner.editor.pro.data.IptvGroup
import com.iptv.scanner.editor.pro.data.IptvRepository
import com.iptv.scanner.editor.pro.data.IptvSource
import com.iptv.scanner.editor.pro.data.IptvStatus
import com.iptv.scanner.editor.pro.data.MappingEntry
import com.iptv.scanner.editor.pro.data.ReminderItem
import com.iptv.scanner.editor.pro.data.RecentEntry
import com.iptv.scanner.editor.pro.data.ResumeItem
import com.iptv.scanner.editor.pro.data.BookmarkItem
import com.iptv.scanner.editor.pro.data.ChannelPlayerSettings
import com.iptv.scanner.editor.pro.data.ScanResult
import com.iptv.scanner.editor.pro.data.ScanStatus
import com.iptv.scanner.editor.pro.data.SubtitleItem
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.mpv.MpvController
import com.iptv.scanner.editor.pro.player.CatchupHelper
import com.iptv.scanner.editor.pro.player.CatchupProgram
import com.iptv.scanner.editor.pro.player.ExoPlayerWrapper
import com.iptv.scanner.editor.pro.player.PlayMode
import com.iptv.scanner.editor.pro.player.SubPlayer
import com.iptv.scanner.editor.pro.player.SubPlayerState
import com.iptv.scanner.editor.pro.player.PlaybackState
import com.iptv.scanner.editor.pro.player.Player
import com.iptv.scanner.editor.pro.data.SpeedConfig
import com.iptv.scanner.editor.pro.player.PlayerCapabilities
import com.iptv.scanner.editor.pro.player.PlayerType
import com.iptv.scanner.editor.pro.player.ProgressHelper
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

internal fun AppViewModel.showChannelsPanel() { _channelsPanelOpen.value = true }

internal fun AppViewModel.showEpgPanel() { _epgPanelOpen.value = true }

internal fun AppViewModel.showMenuPanel() { _menuPanelOpen.value = true }

internal fun AppViewModel.showFileBrowser() {
    closeAllPanels()
    _fileBrowserMode.value = FileBrowserMode.PLAYLIST
    _fileBrowserOpen.value = true
}

internal fun AppViewModel.showMediaFileBrowser() {
    closeAllPanels()
    _fileBrowserMode.value = FileBrowserMode.MEDIA
    _fileBrowserOpen.value = true
}

internal fun AppViewModel.toggleFileBrowser() {
    _fileBrowserOpen.value = !_fileBrowserOpen.value
    if (!_fileBrowserOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.importPlaylistFromFile(path: String) {
viewModelScope.launch {
showOsd("正在导入播放列表...")
val content = withContext(Dispatchers.IO) {
try {
File(path).readText(charset = Charsets.UTF_8)
} catch (e: Exception) {
Log.e(AppViewModel.TAG, "importPlaylistFromFile read failed: $path", e)
null
}
} ?: run {
showOsd("导入失败", "无法读取文件")
return@launch
}
val result = repository.importChannels(content)
result.fold(
onSuccess = { (count, epgUrl) ->
showOsd("导入成功", "已导入 $count 个频道")
setChannelsTab(ChannelTab.LOCAL)
loadChannels()
// 自动添加 M3U 中定义的 EPG 源
if (epgUrl.isNotEmpty()) {
addEpgSourceFromM3u(epgUrl)
}
},
onFailure = { e ->
showOsd("导入失败", e.message ?: "")
}
)
}
}

internal fun AppViewModel.showControls() { showControlsAutoHide() }

internal fun AppViewModel.showControlsAutoHide() {
    _controlsVisible.value = true
    if (!_controlsPinned.value) {
        tvControlsAutoHideJob?.cancel()
        tvControlsAutoHideJob = viewModelScope.launch {
            delay(4_000L)
            // 底栏样式选择弹窗打开期间：底栏作为实时预览保持显示，不自动隐藏
            if (_stylePickerOpen.value) return@launch
            _controlsVisible.value = false
        }
    }
}

internal fun AppViewModel.toggleControlsPinned() {
    if (_controlsPinned.value) {
        _controlsPinned.value = false
        _controlsVisible.value = false
        tvControlsAutoHideJob?.cancel()
    } else {
        _controlsPinned.value = true
        _controlsVisible.value = true
        tvControlsAutoHideJob?.cancel()
    }
}

internal fun AppViewModel.toggleVideoSettings() {
    _videoSettingsOpen.value = !_videoSettingsOpen.value
    if (!_videoSettingsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleAudioSettings() {
    _audioSettingsOpen.value = !_audioSettingsOpen.value
    if (!_audioSettingsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleSubtitleSettings() {
    _subtitleSettingsOpen.value = !_subtitleSettingsOpen.value
    if (!_subtitleSettingsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleSubtitleSearchPanel() {
    _subtitleSearchOpen.value = !_subtitleSearchOpen.value
    if (!_subtitleSearchOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.searchSubtitles(query: String, language: String = "all") {
    if (query.isBlank()) {
        showOsd("字幕搜索", "请输入搜索关键词")
        return
    }
    viewModelScope.launch {
        _subtitleSearching.value = true
        _subtitleSearchError.value = ""
        _subtitleSearchResults.value = emptyList()
        val result = repository.searchSubtitles(query = query, language = language)
        _subtitleSearching.value = false
        result.onSuccess { response ->
            _subtitleSearchResults.value = response.subtitles
            _subtitleSearchError.value = response.lastError
            if (response.subtitles.isEmpty()) {
                showOsd("字幕搜索", "未找到匹配字幕")
            } else {
                showOsd("字幕搜索", "找到 ${response.subtitles.size} 条结果")
            }
        }.onFailure { e ->
            _subtitleSearchError.value = e.message ?: "搜索失败"
            showOsd("字幕搜索", "搜索失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.downloadAndLoadSubtitle(item: SubtitleItem) {
    viewModelScope.launch {
        _subtitleDownloading.value = true
        val destDir = File(getApplication<Application>().cacheDir, "subtitles").apply { mkdirs() }
        val result = repository.downloadSubtitle(
            downloadLink = item.downloadLink,
            destDir = destDir.absolutePath,
            fileName = item.fileName.ifBlank { "subtitle_${System.currentTimeMillis()}" },
            language = item.languageId.ifBlank { item.language }
        )
        _subtitleDownloading.value = false
        result.onSuccess { path ->
            // 只有命令真正提交给播放器才提示成功，避免播放器未就绪时谎报「已加载」
            if (mpv.addSubtitleFile(path)) {
                showOsd("字幕已加载", path.substringAfterLast('/'))
            } else {
                showOsd("字幕加载失败", "播放器未就绪")
            }
        }.onFailure { e ->
            showOsd("字幕下载失败", e.message ?: "未知错误")
        }
    }
}

internal fun AppViewModel.togglePlaybackPanel() {
    _playbackPanelOpen.value = !_playbackPanelOpen.value
    if (!_playbackPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleScreenshotPanel() {
    _screenshotPanelOpen.value = !_screenshotPanelOpen.value
    if (!_screenshotPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleViewSettings() {
    _viewSettingsOpen.value = !_viewSettingsOpen.value
    if (!_viewSettingsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleAboutPanel() {
    _aboutPanelOpen.value = !_aboutPanelOpen.value
    if (!_aboutPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.getCurrentVersion(): String {
    return try {
        val app = getApplication<Application>()
        val packageInfo = app.packageManager.getPackageInfo(app.packageName, 0)
        packageInfo.versionName ?: "0.0.0.0"
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "getCurrentVersion failed", e)
        "0.0.0.0"
    }
}

internal fun AppViewModel.getBuildDate(): String {
    return try {
        val app = getApplication<Application>()
        val packageInfo = app.packageManager.getPackageInfo(app.packageName, 0)
        val date = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
        date.format(java.util.Date(packageInfo.lastUpdateTime))
    } catch (e: Exception) {
        Log.w(AppViewModel.TAG, "getBuildDate failed", e)
        "unknown"
    }
}

internal fun AppViewModel.checkForUpdates(auto: Boolean = false) {
    if (_updateState.value is UpdateState.Checking) return
    _updateState.value = UpdateState.Checking
    viewModelScope.launch {
        try {
            val currentVersion = getCurrentVersion()
            val (latestVersion, downloadUrl, releaseUrl) = withContext(Dispatchers.IO) {
                fetchLatestRelease()
            }
            if (latestVersion.isNullOrEmpty()) {
                if (!auto) {
                    _updateState.value = UpdateState.Error("获取版本信息失败")
                } else {
                    _updateState.value = UpdateState.Idle
                }
            } else if (isNewerVersion(currentVersion, latestVersion)) {
                _updateState.value = UpdateState.UpdateAvailable(
                    latestVersion,
                    downloadUrl ?: "",
                    releaseUrl ?: ""
                )
                _updateDialogOpen.value = true
                showOsd("发现新版本", "v$latestVersion（当前 v$currentVersion）")
            } else {
                if (!auto) {
                    _updateState.value = UpdateState.UpToDate
                } else {
                    _updateState.value = UpdateState.Idle
                }
            }
        } catch (e: Exception) {
            Log.e(AppViewModel.TAG, "checkForUpdates failed", e)
            if (!auto) {
                _updateState.value = UpdateState.Error(e.message ?: "检查更新失败")
            } else {
                _updateState.value = UpdateState.Idle
            }
        }
    }
}

internal fun AppViewModel.dismissUpdateDialog() {
    _updateDialogOpen.value = false
}

internal fun AppViewModel.downloadAndInstallApk(url: String) {
    if (url.isBlank()) {
        _apkDownloadState.value = ApkDownloadState.Error("下载地址为空")
        return
    }
    // 安全：校验 URL 协议和域名，防止恶意 APK 下载
    val parsedUrl = try {
        android.net.Uri.parse(url)
    } catch (e: Exception) {
        _apkDownloadState.value = ApkDownloadState.Error("无效的下载地址")
        return
    }
    val scheme = parsedUrl.scheme?.lowercase()
    val host = parsedUrl.host?.lowercase() ?: ""
    if (scheme != "https" || (host != "github.com" && !host.endsWith(".github.com") &&
            !host.endsWith(".githubusercontent.com"))) {
        _apkDownloadState.value = ApkDownloadState.Error("仅允许从 GitHub 下载更新")
        Log.w(AppViewModel.TAG, "downloadAndInstallApk: blocked non-GitHub URL: $url")
        return
    }
    if (_apkDownloadState.value is ApkDownloadState.Downloading) {
        Log.w(AppViewModel.TAG, "downloadAndInstallApk: already downloading, ignored")
        return
    }

    val app = getApplication<Application>()
    val downloadManager = app.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager
    if (downloadManager == null) {
        _apkDownloadState.value = ApkDownloadState.Error("下载服务不可用")
        return
    }

    // 清理旧的下载任务（如有）
    cancelApkDownload()

    // 注册下载完成广播接收器
    registerApkDownloadReceiver(app)

    // 准备下载目录：app 专属外部存储（无需存储权限，卸载自动清理）
    val updateDir = File(app.getExternalFilesDir(null), "update").apply {
        if (!exists()) mkdirs()
    }
    val apkFile = File(updateDir, "isep-update.apk")
    // 删除旧文件避免 DownloadManager 报错 FILE_ALREADY_EXISTS
    if (apkFile.exists()) apkFile.delete()

    Log.i(AppViewModel.TAG, "downloadAndInstallApk: starting download, url=$url, target=${apkFile.absolutePath}")

    // 构建下载请求
    val request = try {
        DownloadManager.Request(Uri.parse(url)).apply {
            setTitle("光屿 更新")
            setDescription("正在下载最新版 APK...")
            setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
            setDestinationUri(Uri.fromFile(apkFile))
            // 允许在移动网络和漫游下下载（更新包通常不大，且用户主动触发）
            setAllowedNetworkTypes(DownloadManager.Request.NETWORK_WIFI or DownloadManager.Request.NETWORK_MOBILE)
            setAllowedOverRoaming(true)
        }
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "downloadAndInstallApk: create request failed", e)
        _apkDownloadState.value = ApkDownloadState.Error("创建下载请求失败：${e.message}")
        unregisterApkDownloadReceiver(app)
        return
    }

    try {
        apkDownloadId = downloadManager.enqueue(request)
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "downloadAndInstallApk: enqueue failed", e)
        _apkDownloadState.value = ApkDownloadState.Error("下载服务异常：${e.message}")
        unregisterApkDownloadReceiver(app)
        return
    }
    _apkDownloadState.value = ApkDownloadState.Downloading(0)
    showOsd("应用更新", "开始下载 APK...")

    // 启动进度轮询协程
    apkProgressJob = viewModelScope.launch {
        while (isActive) {
            delay(500)  // 每 500ms 查询一次进度
            try {
                val query = DownloadManager.Query().setFilterById(apkDownloadId)
                val cursor = downloadManager.query(query)
                if (cursor != null && cursor.moveToFirst()) {
                    val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                    when (status) {
                        DownloadManager.STATUS_RUNNING -> {
                            val downloaded = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR))
                            val total = cursor.getLong(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES))
                            if (total > 0) {
                                val progress = ((downloaded * 100) / total).toInt().coerceIn(0, 100)
                                _apkDownloadState.value = ApkDownloadState.Downloading(progress)
                            }
                        }
                        DownloadManager.STATUS_PAUSED -> {
                            // 暂停（等待网络等），UI 仍显示下载中
                        }
                        DownloadManager.STATUS_PENDING -> {
                            // 等待开始
                        }
                        DownloadManager.STATUS_FAILED -> {
                            val reason = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
                            Log.e(AppViewModel.TAG, "downloadAndInstallApk: download failed, reason=$reason")
                            _apkDownloadState.value = ApkDownloadState.Error("下载失败（错误码 $reason）")
                            unregisterApkDownloadReceiver(app)
                            apkDownloadId = -1L
                            cursor.close()
                            return@launch
                        }
                    }
                }
                cursor?.close()
            } catch (e: Throwable) {
                Log.w(AppViewModel.TAG, "downloadAndInstallApk: progress poll error: ${e.message}")
            }
        }
    }
}

internal fun AppViewModel.installDownloadedApk() {
    val app = getApplication<Application>()
    val apkFile = File(app.getExternalFilesDir(null), "update/isep-update.apk")
    if (!apkFile.exists()) {
        _apkDownloadState.value = ApkDownloadState.Error("下载文件不存在")
        return
    }

    try {
        val authority = "${app.packageName}.fileprovider"
        val uri = FileProvider.getUriForFile(app, authority, apkFile)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        // Android 8+ 需要检查未知来源安装权限
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O &&
            !app.packageManager.canRequestPackageInstalls()
        ) {
            Log.w(AppViewModel.TAG, "installDownloadedApk: no install permission, opening settings")
            _apkDownloadState.value = ApkDownloadState.Error("请先允许「安装未知应用」权限")
            // 引导用户到设置页面授权
            val settingsIntent = Intent(
                android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${app.packageName}")
            ).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            try {
                app.startActivity(settingsIntent)
            } catch (e: Exception) {
                Log.e(AppViewModel.TAG, "installDownloadedApk: cannot open unknown sources settings", e)
            }
            return
        }
        app.startActivity(intent)
        Log.i(AppViewModel.TAG, "installDownloadedApk: install intent launched, uri=$uri")
        // 安装界面已弹出，关闭更新对话框
        _updateDialogOpen.value = false
    } catch (e: Throwable) {
        Log.e(AppViewModel.TAG, "installDownloadedApk failed", e)
        _apkDownloadState.value = ApkDownloadState.Error("启动安装失败：${e.message}")
    }
}

internal fun AppViewModel.registerApkDownloadReceiver(context: Context) {
    unregisterApkDownloadReceiver(context)
    val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context?, intent: Intent?) {
            val id = intent?.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L) ?: -1L
            if (id != apkDownloadId) return  // 不是我们的下载任务
            Log.i(AppViewModel.TAG, "APK download complete, id=$id")
            apkProgressJob?.cancel()
            apkProgressJob = null

            val downloadManager = context?.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager
            if (downloadManager == null) {
                _apkDownloadState.value = ApkDownloadState.Error("下载服务不可用")
                unregisterApkDownloadReceiver(context)
                return
            }

            // 查询下载结果
            val query = DownloadManager.Query().setFilterById(id)
            val cursor = downloadManager.query(query)
            if (cursor != null && cursor.moveToFirst()) {
                val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                if (status == DownloadManager.STATUS_SUCCESSFUL) {
                    _apkDownloadState.value = ApkDownloadState.Completed
                    showOsd("应用更新", "下载完成，正在启动安装...")
                    // 稍延迟启动安装（让 UI 先更新）
                    viewModelScope.launch {
                        delay(300)
                        installDownloadedApk()
                    }
                } else {
                    val reason = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON))
                    Log.e(AppViewModel.TAG, "APK download failed on complete, reason=$reason")
                    _apkDownloadState.value = ApkDownloadState.Error("下载失败（错误码 $reason）")
                }
                cursor.close()
            } else {
                _apkDownloadState.value = ApkDownloadState.Error("下载结果查询失败")
            }
            unregisterApkDownloadReceiver(context)
            apkDownloadId = -1L
        }
    }
    context.registerReceiver(
        receiver,
        IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE)
    )
    apkDownloadReceiver = receiver
}

internal fun AppViewModel.unregisterApkDownloadReceiver(context: Context) {
    apkDownloadReceiver?.let {
        try {
            context.unregisterReceiver(it)
        } catch (e: Throwable) {
            Log.w(AppViewModel.TAG, "unregisterApkDownloadReceiver: ${e.message}")
        }
        apkDownloadReceiver = null
    }
}

internal fun AppViewModel.cancelApkDownload() {
    val app = getApplication<Application>()
    apkProgressJob?.cancel()
    apkProgressJob = null
    if (apkDownloadId > 0) {
        try {
            val dm = app.getSystemService(Context.DOWNLOAD_SERVICE) as? DownloadManager
            dm?.remove(apkDownloadId)
        } catch (e: Throwable) {
            Log.w(AppViewModel.TAG, "cancelApkDownload: remove failed: ${e.message}")
        }
        apkDownloadId = -1L
    }
    unregisterApkDownloadReceiver(app)
    _apkDownloadState.value = ApkDownloadState.Idle
}

internal fun AppViewModel.showExitConfirm() {
    _exitConfirmOpen.value = true
}

internal fun AppViewModel.dismissExitConfirm() {
    _exitConfirmOpen.value = false
}

internal fun AppViewModel.fetchLatestRelease(): Triple<String?, String?, String?> {
    val conn = java.net.URL(AppViewModel.GITHUB_LATEST_API).openConnection() as java.net.HttpURLConnection
    try {
        conn.requestMethod = "GET"
        conn.setRequestProperty("User-Agent", "GuangYu")
        conn.setRequestProperty("Accept", "application/vnd.github+json")
        conn.connectTimeout = 10_000
        conn.readTimeout = 10_000
        if (conn.responseCode == 200) {
            val json = conn.inputStream.bufferedReader().use { it.readText() }
            val release = JSONObject(json)
            val tagName = release.optString("tag_name", "").removePrefix("v")
            val releaseUrl = release.optString("html_url", "")

            val assets = release.optJSONArray("assets")
            var downloadUrl = releaseUrl
            if (assets != null) {
                // 收集所有 Android APK asset
                val androidApks = mutableListOf<Pair<String, String>>() // (name, url)
                for (i in 0 until assets.length()) {
                    val asset = assets.optJSONObject(i) ?: continue
                    val name = asset.optString("name", "")
                    if (name.contains("Android", ignoreCase = true) && name.endsWith(".apk")) {
                        androidApks.add(name to asset.optString("browser_download_url", releaseUrl))
                    }
                }

                // 优先匹配通用 APK（无 ABI 后缀或 -universal 后缀，含所有 ABI）
                val universalApk = androidApks.firstOrNull { (name, _) ->
                    name.equals("GuangYu-Android.apk", ignoreCase = true) ||
                    name.equals("GuangYu-Android-universal.apk", ignoreCase = true) ||
                    // 旧版本 APK 文件名兼容（历史 release 仍可被识别升级）
                    name.equals("ISEP-Android.apk", ignoreCase = true) ||
                    name.equals("ISEP-Android-universal.apk", ignoreCase = true) ||
                    name.equals("IPTV Scanner Editor Pro-Android.apk", ignoreCase = true) ||
                    name.equals("IPTV Scanner Editor Pro-Android-universal.apk", ignoreCase = true)
                }
                if (universalApk != null) {
                    downloadUrl = universalApk.second
                } else {
                    // 按 ABI 拆分的 APK：按设备首选 ABI 匹配
                    // 当前命名：arm64-v8a → -arm64.apk，armeabi-v7a → -arm32.apk
                    // 旧版命名：arm64-v8a → -arm64-v8a.apk，armeabi-v7a → -armeabi-v7a.apk
                    val deviceAbis = android.os.Build.SUPPORTED_ABIS.toList()
                    Log.i(AppViewModel.TAG, "fetchLatestRelease: universal APK not found, fallback to ABI-specific, device ABIs=$deviceAbis")
                    downloadUrl = deviceAbis.firstNotNullOfOrNull { abi ->
                        // 标准 ABI 名称 → APK 文件名中使用的所有可能后缀
                        val possibleSuffixes = when (abi) {
                            "arm64-v8a" -> listOf("-arm64-v8a.apk", "-arm64.apk")
                            "armeabi-v7a" -> listOf("-armeabi-v7a.apk", "-arm32.apk")
                            "x86_64" -> listOf("-x86_64.apk", "-x64.apk")
                            "x86" -> listOf("-x86.apk")
                            else -> listOf("-$abi.apk")
                        }
                        androidApks.firstOrNull { (name, _) ->
                            possibleSuffixes.any { suffix -> name.endsWith(suffix, ignoreCase = true) }
                        }?.second
                    } ?: androidApks.firstOrNull()?.second ?: releaseUrl
                }
            }
            Log.i(AppViewModel.TAG, "Latest release: $tagName, downloadUrl=$downloadUrl")
            return Triple(tagName, downloadUrl, releaseUrl)
        } else if (conn.responseCode == 403) {
            Log.w(AppViewModel.TAG, "GitHub API rate limited")
            return Triple(null, null, null)
        }
    } finally {
        conn.disconnect()
    }
    return Triple(null, null, null)
}

internal fun AppViewModel.isNewerVersion(current: String, latest: String): Boolean {
    return try {
        // 清理版本号中的非数字前缀（如 v1.0.0）
        val cleanCurrent = current.trim().trimStart('v', 'V')
        val cleanLatest = latest.trim().trimStart('v', 'V')
        val currentParts = cleanCurrent.split(".").map { it.toIntOrNull() ?: 0 }
        val latestParts = cleanLatest.split(".").map { it.toIntOrNull() ?: 0 }
        val maxLen = maxOf(currentParts.size, latestParts.size)
        val c = currentParts + List(maxLen - currentParts.size) { 0 }
        val l = latestParts + List(maxLen - latestParts.size) { 0 }
        for (i in 0 until maxLen) {
            if (l[i] > c[i]) return true
            if (l[i] < c[i]) return false
        }
        false
    } catch (e: Exception) {
        Log.w(AppViewModel.TAG, "Version comparison failed: current=$current latest=$latest")
        false
    }
}

internal fun AppViewModel.toggleOpenUrlDialog() {
    _openUrlDialogOpen.value = !_openUrlDialogOpen.value
    if (!_openUrlDialogOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleMappingPanel() {
    _mappingPanelOpen.value = !_mappingPanelOpen.value
    if (_mappingPanelOpen.value) {
        loadMappings()
    } else {
        showControlsAutoHide()
    }
}

internal fun AppViewModel.toggleAvSyncPanel() {
    _avSyncPanelOpen.value = !_avSyncPanelOpen.value
    if (_avSyncPanelOpen.value) {
        startAvSyncSampling()
    } else {
        stopAvSyncSampling()
        stopSubSync()
        showControlsAutoHide()
    }
}

internal fun AppViewModel.toggleNetworkPanel() {
    _networkPanelOpen.value = !_networkPanelOpen.value
    if (!_networkPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleToolsPanel() {
    _toolsPanelOpen.value = !_toolsPanelOpen.value
    if (!_toolsPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleScanPanel() {
    _scanPanelOpen.value = !_scanPanelOpen.value
    if (!_scanPanelOpen.value) {
        // 关闭面板时停止轮询（扫描本身仍在后台继续）
        stopScanPolling()
        showControlsAutoHide()
    } else {
        // 打开面板时刷新一次状态（若仍在运行则启动轮询）
        refreshScanStatusOnce()
    }
}

internal fun AppViewModel.startScan(
    baseUrl: String, timeout: Int = 10, threads: Int = 4,
    engine: String = "requests", retry: Boolean = false, append: Boolean = false
) {
    if (baseUrl.isBlank()) {
        showOsd("扫描", "请输入基础 URL")
        return
    }
    viewModelScope.launch {
        _scanLoading.value = true
        _scanError.value = ""
        if (!append) _scanResults.value = emptyList()
        val result = repository.startScan(baseUrl, timeout, threads, engine, retry, append)
        _scanLoading.value = false
        result.onSuccess { started ->
            if (started) {
                showOsd("扫描", "已启动")
                startScanPolling()
            } else {
                _scanError.value = "扫描已在运行"
                showOsd("扫描", "扫描已在运行")
            }
        }.onFailure { e ->
            _scanError.value = e.message ?: "启动失败"
            showOsd("扫描", "启动失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.stopScan() {
    viewModelScope.launch {
        val result = repository.stopScan()
        result.onSuccess {
            showOsd("扫描", "已停止")
        }.onFailure { e ->
            showOsd("扫描", "停止失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.refreshScanStatusOnce() {
    viewModelScope.launch {
        val status = repository.getScanStatus().getOrNull()
        if (status == null) return@launch
        _scanStatus.value = status
        if (status.running) {
            startScanPolling()
        } else if (status.scanned > 0 && _scanResults.value.isEmpty()) {
            // 已完成的扫描但结果未加载，加载结果
            repository.getScanResults().onSuccess { _scanResults.value = it }
        }
    }
}

internal fun AppViewModel.loadScanResultsCache() {
    if (_scanResults.value.isEmpty()) {
        viewModelScope.launch {
            repository.getScanResults().onSuccess { results ->
                if (results.isNotEmpty()) {
                    _scanResults.value = results
                }
            }
        }
    }
}

internal fun AppViewModel.measureHttpLatency(url: String): Int {
    return try {
        val start = System.currentTimeMillis()
        val connection = java.net.URL(url).openConnection() as java.net.HttpURLConnection
        connection.connectTimeout = 3000
        connection.readTimeout = 3000
        connection.requestMethod = "HEAD"
        connection.connect()
        val latency = (System.currentTimeMillis() - start).toInt()
        connection.disconnect()
        latency
    } catch (e: Exception) {
        try {
            val start = System.currentTimeMillis()
            val connection = java.net.URL(url).openConnection()
            connection.connectTimeout = 3000
            connection.readTimeout = 3000
            connection.getInputStream().use { it.read() }
            val latency = (System.currentTimeMillis() - start).toInt()
            latency
        } catch (e2: Exception) { -1 }
    }
}

internal fun AppViewModel.fetchMediaInfoForChannels(channelsToFetch: List<IptvChannel>) {
    thumbnailJob?.cancel()
    thumbnailJob = viewModelScope.launch {
        _thumbnailGenProgress.value = Pair(0, channelsToFetch.size)
        var done = 0
        for (ch in channelsToFetch) {
            if (!isActive) break
            if (ch.url.isEmpty()) {
                done++
                _thumbnailGenProgress.value = Pair(done, channelsToFetch.size)
                continue
            }
            // 测量网络延迟
            if (!_liveLatencyMap.value.containsKey(ch.url)) {
                val lat = withContext(kotlinx.coroutines.Dispatchers.IO) { measureHttpLatency(ch.url) }
                if (lat > 0) {
                    _liveLatencyMap.value = _liveLatencyMap.value.toMutableMap().apply { put(ch.url, lat) }
                }
            }
            if (_mediaInfoMap.value.containsKey(ch.url)) {
                done++
                _thumbnailGenProgress.value = Pair(done, channelsToFetch.size)
                continue
            }
            try {
                val mediaInfo = withContext(kotlinx.coroutines.Dispatchers.IO) {
                    val retriever = MediaMetadataRetriever()
                    try {
                        retriever.setDataSource(ch.url, HashMap<String, String>())
                        val w = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
                        val h = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
                        val fps = if (android.os.Build.VERSION.SDK_INT >= 29) retriever.extractMetadata(30)?.toFloatOrNull() else null
                        val br = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toIntOrNull() ?: 0
                        val mimeType = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_MIMETYPE) ?: ""
                        if (done < 5) Log.i(AppViewModel.TAG, "mediaInfo: ${ch.name} w=$w h=$h fps=$fps br=$br mime=$mimeType")
                        val parts = mutableListOf<String>()
                        if (w > 0 && h > 0) {
                            parts.add(when { w >= 3800 -> "4K"; w >= 1900 -> "1080P"; w >= 1200 -> "720P"; else -> "${h}P" })
                        }
                        if (mimeType.isNotEmpty()) {
                            val container = when {
                                mimeType.contains("mp2ts") -> "TS"
                                mimeType.contains("mp4") -> "MP4"
                                mimeType.contains("matroska") -> "MKV"
                                mimeType.contains("avi") -> "AVI"
                                mimeType.contains("flv") -> "FLV"
                                mimeType.contains("webm") -> "WEBM"
                                else -> mimeType.substringAfter("/").take(4).uppercase()
                            }
                            if (container.isNotEmpty()) parts.add(container)
                        }
                        if (fps != null && fps > 0) parts.add("${fps.toInt()}FPS")
                        if (br > 0) parts.add("${br / 1000}kbps")
                        val proto = ch.url.substringBefore("://").lowercase()
                        when (proto) { "http" -> parts.add("HTTP"); "https" -> parts.add("HTTPS"); "rtsp" -> parts.add("RTSP"); "udp" -> parts.add("UDP"); "rtp" -> parts.add("RTP") }
                        parts.joinToString(" ")
                    } catch (e: Exception) { "" } finally {
                        try { retriever.release() } catch (_: Exception) {}
                    }
                }
                if (mediaInfo.isNotEmpty()) {
                    _mediaInfoMap.value = _mediaInfoMap.value.toMutableMap().apply { put(ch.url, mediaInfo) }
                }
            } catch (e: Exception) {
                Log.w(AppViewModel.TAG, "fetchMediaInfoForAll: error for ${ch.url}: ${e.message}")
            }
            done++
            _thumbnailGenProgress.value = Pair(done, channelsToFetch.size)
        }
        _thumbnailGenProgress.value = null
        Log.i(AppViewModel.TAG, "fetchMediaInfoForAll: done, $done/${channelsToFetch.size}")
    }
}

internal fun AppViewModel.startScanPolling() {
    scanPollJob?.cancel()
    scanPollJob = viewModelScope.launch {
        while (isActive) {
            delay(800)
            val statusResult = repository.getScanStatus()
            val status = statusResult.getOrNull()
            if (status == null) {
                _scanError.value = statusResult.exceptionOrNull()?.message ?: "状态查询失败"
                break
            }
            _scanStatus.value = status
            // 每次轮询都获取最新结果（实时显示，不需等扫描结束）
            repository.getScanResults().onSuccess { _scanResults.value = it }
            if (!status.running) {
                // 扫描结束
                showOsd("扫描", "完成: 共 ${status.total}，有效 ${status.valid}，无效 ${status.invalid}")
                break
            }
        }
    }
}

internal fun AppViewModel.stopScanPolling() {
    scanPollJob?.cancel()
    scanPollJob = null
}

internal fun AppViewModel.deleteScanResult(url: String) {
    _scanResults.value = _scanResults.value.filterNot { it.url == url }
}

internal fun AppViewModel.clearScanResults() {
    _scanResults.value = emptyList()
}

internal fun AppViewModel.startValidate(timeout: Int = 10, threads: Int = 4) {
    viewModelScope.launch {
        _scanLoading.value = true
        _scanError.value = ""
        val result = repository.startValidate(timeout, threads)
        _scanLoading.value = false
        result.onSuccess { started ->
            if (started) {
                showOsd("验证", "已启动频道验证")
                startScanPolling()
            } else {
                _scanError.value = "扫描/验证已在进行中"
                showOsd("验证", "扫描/验证已在进行中")
            }
        }.onFailure { e ->
            _scanError.value = e.message ?: "启动失败"
            showOsd("验证", "启动失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.updateChannel(idx: Int, fields: Map<String, String>) {
    viewModelScope.launch {
        val result = repository.updateChannel(idx, fields)
        result.onSuccess {
            showOsd("编辑", "已保存")
            loadChannels()
        }.onFailure { e ->
            showOsd("编辑", "保存失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.exportScanResultsAsM3u() {
    val validResults = _scanResults.value.filter { it.valid }
    if (validResults.isEmpty()) {
        showOsd("导出", "无有效频道可导出")
        return
    }

    viewModelScope.launch {
        try {
            // 直接从前端 scanResults 构造 M3U 内容，不依赖后端 getM3uText
            val m3uText = buildString {
                appendLine("#EXTM3U")
                for (result in validResults) {
                    val name = result.name.ifBlank { result.url }
                    val group = result.group.ifBlank { "扫描结果" }
                    appendLine("#EXTINF:-1 tvg-name=\"$name\" group-title=\"$group\",$name")
                    appendLine(result.url)
                }
            }
            val channelCount = validResults.size

            val ts = java.text.SimpleDateFormat("yyyyMMdd_HHmmss", java.util.Locale.CHINA)
                .format(java.util.Date())
            val filename = "scan_$ts.m3u"
            val app = getApplication<Application>()
            val written = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val resolver = app.contentResolver
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
                    put(MediaStore.MediaColumns.MIME_TYPE, "audio/x-mpegurl")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                }
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                if (uri == null) false
                else {
                    resolver.openOutputStream(uri)?.use { it.write(m3uText.toByteArray()) } ?: false
                    true
                }
            } else {
                @Suppress("DEPRECATION")
                val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                if (!dir.exists()) dir.mkdirs()
                File(dir, filename).writeText(m3uText)
                true
            }
            if (written) {
                showOsd("导出", "已保存到 Downloads/$filename（$channelCount 个频道）")
                Log.i(AppViewModel.TAG, "Scan results exported to Downloads/$filename ($channelCount channels)")
            } else {
                showOsd("导出", "保存失败")
            }
        } catch (e: Exception) {
            Log.e(AppViewModel.TAG, "exportScanResultsAsM3u failed", e)
            showOsd("导出", "导出失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.importScanResultsToChannels() {
    val validResults = _scanResults.value.filter { it.valid }
    if (validResults.isEmpty()) {
        showOsd("导入", "无有效频道可导入")
        return
    }

    viewModelScope.launch {
        _scanLoading.value = true
        try {
            // 构造 M3U 格式内容
            val m3uContent = buildString {
                appendLine("#EXTM3U")
                for (result in validResults) {
                    val name = result.name.ifBlank { result.url }
                    val group = result.group.ifBlank { "扫描结果" }
                    appendLine("#EXTINF:-1 tvg-name=\"$name\" group-title=\"$group\",$name")
                    appendLine(result.url)
                }
            }

            val importResult = repository.importChannels(m3uContent, "扫描结果导入")
            importResult.onSuccess { count ->
                // 刷新频道列表
                loadChannels()
                showOsd("导入", "已导入 $count 个频道到播放列表")
                Log.i(AppViewModel.TAG, "importScanResultsToChannels: imported $count channels")
            }.onFailure { e ->
                showOsd("导入", "导入失败: ${e.message}")
                Log.e(AppViewModel.TAG, "importScanResultsToChannels failed", e)
            }
        } catch (e: Exception) {
            Log.e(AppViewModel.TAG, "importScanResultsToChannels failed", e)
            showOsd("导入", "导入失败: ${e.message}")
        } finally {
            _scanLoading.value = false
        }
    }
}



internal fun AppViewModel.setSelectedSource(source: String) {
    _selectedSource.value = source
    _selectedGroup.value = ""  // 切换订阅源时重置分组
}

