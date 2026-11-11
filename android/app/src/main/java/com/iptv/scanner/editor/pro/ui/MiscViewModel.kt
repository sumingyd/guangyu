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

internal fun AppViewModel.readBackupFromFile(uri: Uri): String? {
    return try {
        val resolver = getApplication<Application>().contentResolver
        resolver.openInputStream(uri)?.use { it.bufferedReader().readText() }
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "readBackupFromFile failed", e)
        null
    }
}

internal fun AppViewModel.togglePlayerToolsPanel() {
    _playerToolsOpen.value = !_playerToolsOpen.value
    if (!_playerToolsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.loadSources() {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.getSources() }
        result.onSuccess { _sources.value = it }
            .onFailure { showOsd("加载订阅源失败", it.message ?: "") }
    }
}

internal fun AppViewModel.loadEpgSources() {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.getEpgSources() }
        result.onSuccess { _epgSources.value = it }
            .onFailure { showOsd("加载 EPG 源失败", it.message ?: "") }
    }
}

internal fun AppViewModel.addSource(url: String, name: String = "") {
    if (url.isBlank()) {
        showOsd("请输入订阅源 URL")
        return
    }
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.addSource(url, name) }
        result.onSuccess {
            showOsd("订阅源已添加", "正在加载频道...")
            loadSources()
            // 新添加的订阅源默认 enabled=true，自动触发重载以加载频道列表
            reloadSources()
        }.onFailure { showOsd("添加失败", it.message ?: "") }
    }
}

internal fun AppViewModel.addEpgSource(url: String, name: String = "") {
    if (url.isBlank()) {
        showOsd("请输入 EPG 订阅源 URL")
        return
    }
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.addEpgSource(url, name) }
        result.onSuccess {
            showOsd("EPG 源已添加", "正在重载 EPG...")
            loadEpgSources()
            // 自动触发 EPG 重载
            reloadEpgSources()
        }.onFailure { showOsd("添加失败", it.message ?: "") }
    }
}

internal fun AppViewModel.addEpgSourceFromM3u(epgUrl: String) {
    if (epgUrl.isBlank()) return
    viewModelScope.launch {
        // 检查是否已存在相同 URL 的 EPG 源
        val existing = _epgSources.value
        if (existing.any { it.url == epgUrl }) {
            Log.i(AppViewModel.TAG, "addEpgSourceFromM3u: EPG source already exists: $epgUrl")
            return@launch
        }
        val name = "M3U 内嵌 EPG"
        Log.i(AppViewModel.TAG, "addEpgSourceFromM3u: adding EPG source from M3U header: $epgUrl")
        val result = withContext(Dispatchers.IO) { repository.addEpgSource(epgUrl, name) }
        result.onSuccess {
            showOsd("EPG 源已自动添加", "来源：M3U 内嵌 x-tvg-url")
            loadEpgSources()
            reloadEpgSources()
        }.onFailure { e ->
            Log.w(AppViewModel.TAG, "addEpgSourceFromM3u failed: ${e.message}")
        }
    }
}

internal fun AppViewModel.deleteSource(idx: Int) {
    viewModelScope.launch {
        // 先记录被删源的 URL，用于删除后判断是否需要重置选中源
        val deletedUrl = sources.value.getOrNull(idx)?.url
        val result = withContext(Dispatchers.IO) { repository.deleteSource(idx) }
        result.onSuccess {
            showOsd("订阅源已删除")
            loadSources()
            // 若删除的是当前选中源，重置选中态（避免 UI 残留已删源）
            if (deletedUrl != null && deletedUrl == _selectedSource.value) {
                setSelectedSource("")
            }
            // 触发桥端重载：被删源的频道/分组才会从列表中清除
            // （与 updateSource 一致；重载后轮询器检测到频道总数变化会自动 loadChannels 刷新分组）
            reloadSources()
        }.onFailure { showOsd("删除失败", it.message ?: "") }
    }
}

internal fun AppViewModel.updateSource(idx: Int, url: String, name: String) {
    if (url.isBlank()) {
        showOsd("请输入订阅源 URL")
        return
    }
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) {
            repository.updateSource(idx, mapOf("url" to url, "name" to name))
        }
        result.onSuccess {
            showOsd("订阅源已更新", "正在重载...")
            loadSources()
            reloadSources()
        }.onFailure { showOsd("更新失败", it.message ?: "") }
    }
}

internal fun AppViewModel.deleteEpgSource(idx: Int) {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.deleteEpgSource(idx) }
        result.onSuccess {
            showOsd("EPG 源已删除")
            loadEpgSources()
        }.onFailure { showOsd("删除失败", it.message ?: "") }
    }
}

internal fun AppViewModel.updateEpgSource(idx: Int, url: String, name: String) {
    if (url.isBlank()) {
        showOsd("请输入 EPG 订阅源 URL")
        return
    }
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) {
            repository.updateEpgSource(idx, mapOf("url" to url, "name" to name))
        }
        result.onSuccess {
            showOsd("EPG 源已更新", "正在重载 EPG...")
            loadEpgSources()
            reloadEpgSources()
        }.onFailure { showOsd("更新失败", it.message ?: "") }
    }
}

internal fun AppViewModel.toggleSourceEnabled(idx: Int, enabled: Boolean) {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) {
            repository.updateSource(idx, mapOf("enabled" to enabled.toString()))
        }
        result.onSuccess {
            loadSources()
            // 实时更新频道列表，不需要重启 APP
            loadChannels()
        }
            .onFailure { showOsd("更新失败", it.message ?: "") }
    }
}

internal fun AppViewModel.reloadSources(auto: Boolean = false) {
    // 单飞：已有重载在跑时直接合并本次请求，避免并发触发多轮重载（每次都会重下 EPG）
    if (sourceReloadJob?.isActive == true) {
        Log.i(AppViewModel.TAG, "reloadSources: already running, request merged (auto=$auto)")
        return
    }
    sourceReloadJob = viewModelScope.launch {
        _sourceLoading.value = true
        if (!auto) showOsd("正在重载订阅源...")
        val result = withContext(Dispatchers.IO) { repository.reloadSources() }
        result.onSuccess { started ->
            if (started) {
                // 自动（非用户触发）重载只记日志，不打扰用户
                if (!auto) showOsd("订阅源重载已启动", "请稍候...")
                pollSourceStatus(auto = auto)
            } else {
                _sourceLoading.value = false
                if (!auto) showOsd("订阅源重载失败")
            }
        }.onFailure {
            _sourceLoading.value = false
            if (!auto) showOsd("重载失败", it.message ?: "")
        }
    }
}

internal fun AppViewModel.reloadEpgSources(notify: Boolean = true) {
    // 单飞：同一时刻只允许一个 EPG 重载在跑，期间到达的请求直接合并，
    // 避免同一 EPG URL 被并发下载/解析多份（实测 1 分钟内下载 6 次）
    if (epgReloadJob?.isActive == true) {
        Log.i(AppViewModel.TAG, "reloadEpgSources: already running, request merged (notify=$notify)")
        return
    }
    epgReloadJob = viewModelScope.launch {
        if (notify) showOsd("正在重载 EPG...")
        epgCache.clear()
        epgMetaCache.clear()
        _epgCacheVersion.value++
        _focusedEpg.value = emptyList()
        _currentEpg.value = emptyList()
        _currentEpgMeta.value = null
        val result = withContext(Dispatchers.IO) { repository.reloadEpg() }
        result.onSuccess {
            if (notify) showOsd("EPG 重载已启动")
            // 大体积 EPG 解析可能远超 10s，固定延时容易错过刷新 —— 轮询直到 lastUpdate 落盘
            val startTime = System.currentTimeMillis()
            while (isActive) {
                if (System.currentTimeMillis() - startTime > 120_000L) {
                    if (notify) showOsd("EPG 解析超时", "请检查 EPG 源地址是否可达")
                    loadEpgSources()
                    return@launch
                }
                delay(5000L)
                val sources = withContext(Dispatchers.IO) { repository.getEpgSources() }
                    .getOrDefault(emptyList())
                if (sources.any { !it.lastUpdate.isNullOrBlank() }) {
                    break
                }
            }
            epgCache.clear()
            epgMetaCache.clear()
            _epgCacheVersion.value++
            preloadEpgForAllChannels()
            if (_currentIdx.value >= 0) fetchEpgForCurrent()
            fetchEpgForChannel(_currentIdx.value)
            loadEpgSources()
            // 时间线行骨架持有的是旧 epgCache 的加载状态：EPG 更新后重建骨架，
            // 让可视窗口重新拉取节目，否则车机时间线会一直是空白网格。
            if (_epgTimelineRows.value.isNotEmpty()) loadEpgTimeline()
        }
            .onFailure { if (notify) showOsd("EPG 重载失败", it.message ?: "") }
    }
}

internal fun AppViewModel.pollSourceStatus(auto: Boolean = false) {
    viewModelScope.launch {
        val startTime = System.currentTimeMillis()
        while (isActive) {
            if (System.currentTimeMillis() - startTime > 60_000L) {
                _sourceLoading.value = false
                if (!auto) showOsd("订阅源加载超时")
                return@launch
            }
            val result = withContext(Dispatchers.IO) { repository.getSourceStatus() }
            result.onSuccess { status ->
                _sourceLoading.value = status.loading
                _sourceMessage.value = status.message
                if (!status.loading) {
                    // 自动重载（启动期/残留检测触发）不弹 toast，只在日志记录
                    if (!auto) showOsd("订阅源加载完成", "频道数: ${status.channelsTotal}")
                    else Log.i(AppViewModel.TAG, "source load finished (auto): ${status.channelsTotal} channels")
                    loadChannels()
                    // 订阅源可能包含 M3U 内嵌的 x-tvg-url EPG 源：只有 EPG 源列表
                    // 真的变化时才重载 EPG，否则每次订阅源加载完成都会重下 8MB EPG
                    refreshEpgSourcesAndReloadIfChanged()
                    return@launch
                }
            }
            delay(1000L)
        }
    }
}

/**
 * 刷新 EPG 源列表，仅在列表内容真的变化（如新 M3U 内嵌 x-tvg-url）时触发 EPG 重载。
 * 避免订阅源加载完成 → 无条件 reloadEpgSources → 重复下载大文件。
 */
internal fun AppViewModel.refreshEpgSourcesAndReloadIfChanged() {
    viewModelScope.launch {
        val before = _epgSources.value.map { it.url }.filter { it.isNotEmpty() }.toSet()
        val result = withContext(Dispatchers.IO) { repository.getEpgSources() }
        result.onSuccess { list ->
            _epgSources.value = list
            val after = list.map { it.url }.filter { it.isNotEmpty() }.toSet()
            // before 为空表示尚未知（冷启动首刷）：此时不触发重载，
            // 启动期 EPG 已由 Python 侧按缓存有效性决定是否加载
            if (before.isNotEmpty() && after != before) {
                Log.i(AppViewModel.TAG, "EPG sources changed: $before -> $after, reload EPG")
                reloadEpgSources(notify = false)
            }
        }
    }
}

internal fun AppViewModel.toggleAdminServer() {
    if (_adminServerRunning.value) {
        stopAdminServer()
    } else {
        startAdminServer()
    }
}

internal fun AppViewModel.startAdminServer() {
    viewModelScope.launch {
        showOsd("正在启动局域网管理服务器...")
        val result = withContext(Dispatchers.IO) { repository.startAdminServer(8080) }
        result.onSuccess { info ->
            _adminServerUrl.value = info.url
            _adminServerToken.value = info.token
            if (info.running) {
                // server 已启动（可能是 already_running）
                _adminServerRunning.value = true
                showOsd("局域网管理已启动", info.url)
                startAdminCountdown()
            } else {
                // server 正在后台启动（Chaquopy import 中），启动轮询检测
                _adminServerRunning.value = false
                showOsd("正在后台启动...", info.url)
                pollAdminServerStartup(info.url)
            }
        }.onFailure {
            // 记录完整错误到 logcat 方便排查（Python 端 _admin_server_error 包含 traceback）
            Log.e("AppViewModel", "Admin server start failed: ${it.message}", it)
            showOsd("启动失败", it.message ?: "")
        }
    }
}

internal fun AppViewModel.pollAdminServerStartup(url: String) {
    viewModelScope.launch {
        var pollCount = 0
        val maxPolls = 45  // 90 秒 = 45 * 2 秒
        while (pollCount < maxPolls && isActive) {
            delay(2000)
            pollCount++
            val result = withContext(Dispatchers.IO) { repository.getAdminUrl() }
            result.onSuccess { info ->
                if (info.running) {
                    _adminServerUrl.value = info.url
                    _adminServerToken.value = info.token
                    _adminServerRunning.value = true
                    showOsd("局域网管理已启动", info.url)
                    startAdminCountdown()
                    return@launch
                }
                if (info.error.isNotEmpty()) {
                    _adminServerRunning.value = false
                    showOsd("启动失败", info.error)
                    return@launch
                }
            }.onFailure {
                Log.e("AppViewModel", "Admin server poll failed: ${it.message}", it)
            }
        }
        // 超时
        _adminServerRunning.value = false
        showOsd("启动较慢，请稍后刷新状态查看")
    }
}

internal fun AppViewModel.startAdminCountdown() {
    // 启动虚拟遥控器命令轮询（无论是否自动关闭）
    startRemoteCommandPolling()
    // 检查用户是否启用了自动关闭
    if (!userPrefs.getAdminAutoStop()) {
        _adminCountdown.value = 0  // 0 表示不自动关闭
        return
    }
    adminCountdownJob?.cancel()
    _adminCountdown.value = 300
    adminCountdownJob = viewModelScope.launch {
        while (_adminCountdown.value > 0 && isActive) {
            delay(1000)
            _adminCountdown.value -= 1
        }
        if (_adminCountdown.value <= 0 && _adminServerRunning.value) {
            showOsd("局域网管理已自动停止（超时）")
            stopAdminServer()
        }
    }
}

internal fun AppViewModel.setAdminAutoStop(enabled: Boolean) {
    userPrefs.setAdminAutoStop(enabled)
    if (enabled) {
        // 开启自动关闭：如果服务器正在运行，启动倒计时
        if (_adminServerRunning.value && _adminCountdown.value == 0) {
            startAdminCountdown()
        }
    } else {
        // 关闭自动关闭：取消倒计时
        adminCountdownJob?.cancel()
        _adminCountdown.value = 0
        if (_adminServerRunning.value) {
            showOsd("局域网管理", "已关闭自动停止")
        }
    }
}

internal fun AppViewModel.getAdminAutoStop(): Boolean = userPrefs.getAdminAutoStop()

/**
 * 启动虚拟遥控器命令轮询。
 * 每 100ms 轮询 Python 端的命令队列，有命令时执行对应操作。
 * 在 admin 服务器启动后调用，停止时取消轮询。
 */
internal fun AppViewModel.startRemoteCommandPolling() {
    remotePollJob?.cancel()
    remotePollJob = viewModelScope.launch {
        while (isActive) {
            try {
                val result = withContext(Dispatchers.IO) { repository.pollRemoteCommand() }
                result.onSuccess { resp ->
                    resp.cmd?.let { handleRemoteCommand(it) }
                }
            } catch (e: Exception) {
                // 轮询失败不中断，继续下一轮
            }
            delay(200)  // 200ms 轮询（原 100ms 过于频繁，导致 Chaquopy GIL 争用）
        }
    }
    // 同时启动播放状态上报（供 admin 遥控器页面显示）
    startPlayerStatusReport()
}

internal fun AppViewModel.stopRemoteCommandPolling() {
    remotePollJob?.cancel()
    remotePollJob = null
    stopPlayerStatusReport()
}

internal fun AppViewModel.startPlayerStatusReport() {
    playerStatusJob?.cancel()
    playerStatusJob = viewModelScope.launch {
        // 监听 fileLoaded 事件，文件加载后延迟上报
        launch {
            mpv.fileLoaded.collect { loaded ->
                if (loaded) {

                    consecutiveTimeoutCount = 0
                    delay(1500)
                    try { reportPlayerStatus() } catch (e: Exception) { Log.w(AppViewModel.TAG, "reportPlayerStatus failed: ${e.message}") }
                }
            }
        }
        // 定期轮询上报
        while (isActive) {
            try {
                reportPlayerStatus()
            } catch (e: Exception) {
                // 上报失败不中断
            }
            delay(2000)
        }
    }
}

internal fun AppViewModel.stopPlayerStatusReport() {
    playerStatusJob?.cancel()
    playerStatusJob = null
}

internal suspend fun AppViewModel.reportPlayerStatus() {
    val channel = currentChannel.value
    val state = _playbackState.value
    val prog = getCurrentProgram()
    val mediaInfo = mpv.getMediaInfo()
    // HDR 信息：与 PC/Web 端 detect_hdr_type 逻辑统一对齐
    val hdrGamma = (mpv.getPropertyString("video-params/gamma") ?: "").lowercase()
    val hdrPrim = (mpv.getPropertyString("video-params/primaries") ?: "").lowercase()
    val hdrCm = (mpv.getPropertyString("video-params/colormatrix") ?: "").lowercase()
    val hdrVf = (mpv.getPropertyString("video-format") ?: "").lowercase()
    val hdrPeak = mpv.getPropertyDouble("video-params/sig-peak") ?: 0.0
    val hasDovi = hdrVf.contains("dovi") || hdrVf.contains("dolbyvision") ||
        hdrVf.contains("dvhe") || hdrVf.contains("dvh1") || hdrVf.contains("dav1")
    val isPq = hdrGamma.contains("pq") || hdrGamma.contains("smpte2084")
    val isHlg = hdrGamma.contains("hlg") || hdrGamma.contains("arib-std-b67")
    val isBt2020 = hdrCm.contains("bt.2020") || hdrCm.contains("bt2020") || hdrCm.contains("bt.2100") ||
        hdrPrim.contains("bt.2020") || hdrPrim.contains("bt2020") || hdrPrim.contains("bt.2100")
    val hdrInfo = when {
        hasDovi -> "DV (基础层)"
        isPq -> "HDR10"
        isHlg -> "HLG"
        isBt2020 && hdrPeak <= 1.0 -> "WCG"
        isBt2020 && hdrPeak > 1.0 -> "HLG"
        else -> ""
    }
    // 帧率：使用 container-fps（mpv-android 不支持 estimated-vfps）
    val fpsStr = mediaInfo["fps"] ?: ""
    val fps = when {
        fpsStr.isNotEmpty() && fpsStr != "0" && fpsStr != "0.0" -> fpsStr
        else -> {
            val cf = mpv.getPropertyString("container-fps") ?: ""
            val cfNum = cf.toDoubleOrNull() ?: 0.0
            if (cfNum > 0) String.format("%.1f", cfNum) else ""
        }
    }
    val statusJson = buildJsonObject {
        put("channel_name", JsonPrimitive(channel?.name ?: ""))
        put("channel_group", JsonPrimitive(channel?.group ?: ""))
        put("is_playing", JsonPrimitive(mpv.fileLoaded.value && !mpv.paused.value))
        // is_paused 需同时满足 fileLoaded（文件未加载时 paused 可能是初始值 true，
        // 此时显示"已暂停"会误导用户；应为"未播放"）
        put("is_paused", JsonPrimitive(mpv.fileLoaded.value && mpv.paused.value))
        put("player_type", JsonPrimitive(_playerType.value.name))
        put("hardware_decode", JsonPrimitive(_hardwareDecode.value))
        put("play_mode", JsonPrimitive(state.mode.name.lowercase()))
        put("volume", JsonPrimitive(mpv.volume.value))
        put("muted", JsonPrimitive(mpv.muted.value))
        put("current_program", JsonPrimitive(prog?.title ?: ""))
        put("video_res", JsonPrimitive(mediaInfo["videoRes"] ?: ""))
        put("video_codec", JsonPrimitive(mediaInfo["videoCodec"] ?: ""))
        put("audio_codec", JsonPrimitive(mediaInfo["audioCodec"] ?: ""))
        put("fps", JsonPrimitive(fps))
        put("bitrate", JsonPrimitive(mediaInfo["bitrate"] ?: ""))
        put("hdr", JsonPrimitive(hdrInfo))
    }
    withContext(Dispatchers.IO) { repository.setPlayerStatus(statusJson.toString()) }
}

internal fun AppViewModel.handleRemoteCommand(cmd: String) {
    when (cmd) {
        "up" -> prevChannel()
        "down" -> nextChannel()
        "left" -> {
            // 左键：快退（与 MainActivityCompose DPAD_LEFT 对齐）
            val mode = playbackState.value.mode
            if (mode.isCatchup || currentChannel.value == null) {
                mpv.seekRelative(-10.0)
            } else {
                seekLiveRelative(-10.0)
            }
        }
        "right" -> {
            // 右键：快进（与 MainActivityCompose DPAD_RIGHT 对齐）
            val mode = playbackState.value.mode
            if (mode.isCatchup || currentChannel.value == null) {
                mpv.seekRelative(10.0)
            } else {
                seekLiveRelative(10.0)
            }
        }
        "ok" -> {
            if (!controlsVisible.value) {
                showControlsAutoHide()
            } else {
                mpv.togglePause()
            }
        }
        "back" -> {
            if (closeAnyPanel()) return
            if (playbackState.value.mode.isCatchupOrTimeshift) {
                exitCatchup()
            } else if (!_showHome.value) {
                // 竖屏播放器模式，返回首页（视频继续播放）
                showHomeScreen()
            } else {
                showExitConfirm()
            }
        }
        "menu" -> {
            if (uiMode.value.isTV) {
                if (_landscapeSidebarVisible.value) {
                    _landscapeSidebarVisible.value = false
                } else {
                    _landscapeSidebarVisible.value = true
                }
            } else toggleMenuPanel()
        }
        "play" -> mpv.setPause(false)
        "pause" -> mpv.setPause(true)
        "play_pause" -> mpv.togglePause()
        "stop" -> {
            if (playbackState.value.mode.isCatchupOrTimeshift) exitCatchup() else stopPlay()
        }
        "mute" -> mpv.toggleMute()
        "vol_up" -> mpv.adjustVolume(5)
        "vol_down" -> mpv.adjustVolume(-5)
        "seek_forward" -> mpv.seekRelative(30.0)
        "seek_backward" -> mpv.seekRelative(-30.0)
        "osd" -> toggleControlsPinned()
        "prev_channel" -> prevChannel()
        "next_channel" -> nextChannel()
        // 数字键：缓冲输入，1.5 秒无后续输入后切换到对应索引频道
        "num_0", "num_1", "num_2", "num_3", "num_4",
        "num_5", "num_6", "num_7", "num_8", "num_9" -> {
            val digit = cmd.removePrefix("num_").toIntOrNull() ?: return
            _channelInputBuffer = (_channelInputBuffer ?: "") + digit.toString()
            showOsd("频道: " + _channelInputBuffer!!)
            _channelInputJob?.cancel()
            _channelInputJob = viewModelScope.launch {
                kotlinx.coroutines.delay(1500)
                val num = _channelInputBuffer?.toIntOrNull()
                _channelInputBuffer = null
                if (num != null && num > 0) {
                    playChannel(num - 1)
                }
            }
        }
        // 音量绝对值设置（供 Web 遥控器页面音量滑块使用）
        // 命令格式：set_volume:50
        else -> if (cmd.startsWith("set_volume:")) {
            val vol = cmd.removePrefix("set_volume:").toIntOrNull()
            if (vol != null) {
                mpv.setVolume(vol)
                Log.i(AppViewModel.TAG, "Remote set volume: $vol")
            }
        } else if (cmd.startsWith("set_mute:")) {
            val mute = cmd.removePrefix("set_mute:").toBooleanStrictOrNull()
            if (mute != null) {
                mpv.setMute(mute)
                Log.i(AppViewModel.TAG, "Remote set mute: $mute")
            }
        } else if (cmd.startsWith("play_url:")) {
            // 直接播放指定 URL（用于测试）
            val url = cmd.removePrefix("play_url:")
            if (url.isNotEmpty()) {
                Log.i(AppViewModel.TAG, "Remote play_url: $url")
                _currentIdx.value = -1
                _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
                currentPlaybackUrl = url
                currentPlaybackName = "TEST: $url"
                mpv.playFile(url)
                startTimeoutSwitchSource(-1)
                showOsd("测试播放", url)
            }
        } else {
            Log.w(AppViewModel.TAG, "未知遥控命令: $cmd")
        }
    }
}

internal fun AppViewModel.stopAdminServer() {
    adminCountdownJob?.cancel()
    _adminCountdown.value = 0
    // 停止虚拟遥控器命令轮询
    stopRemoteCommandPolling()
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.stopAdminServer() }
        result.onSuccess {
            _adminServerRunning.value = false
            showOsd("局域网管理已停止")
        }.onFailure {
            showOsd("停止失败", it.message ?: "")
        }
    }
}

internal fun AppViewModel.refreshAdminServerStatus() {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.getAdminUrl() }
        result.onSuccess { info ->
            _adminServerUrl.value = info.url
            _adminServerToken.value = info.token
            _adminServerRunning.value = info.running
        }
    }
}

internal fun AppViewModel.setAdminToken(token: String) {
    viewModelScope.launch {
        val result = withContext(Dispatchers.IO) { repository.setAdminToken(token) }
        result.onSuccess { resp ->
            _adminServerToken.value = resp.token
            if (resp.token.isNotEmpty()) {
                showOsd("访问令牌已设置", resp.token)
            } else {
                showOsd("访问令牌", "已清除，启动时自动生成")
            }
        }.onFailure {
            showOsd("设置失败", it.message ?: "")
        }
    }
}

internal fun AppViewModel.loadMappings() {
    viewModelScope.launch {
        _mappingLoading.value = true
        _mappingStatusText.value = "加载中..."
        val result = repository.getMappings()
        _mappingLoading.value = false
        result.onSuccess { list ->
            _mappingList.value = list
            _mappingStatusText.value = "共 ${list.size} 条映射"
        }.onFailure { e ->
            _mappingStatusText.value = "加载失败: ${e.message}"
            Log.e(AppViewModel.TAG, "loadMappings failed", e)
        }
    }
}

internal fun AppViewModel.addMapping(rawName: String, standardName: String, logoUrl: String = "", groupName: String = "") {
    if (rawName.isBlank() || standardName.isBlank()) {
        showOsd("频道映射", "原始名和标准名不能为空")
        return
    }
    viewModelScope.launch {
        _mappingLoading.value = true
        val result = repository.addMapping(rawName, standardName, logoUrl, groupName)
        _mappingLoading.value = false
        result.onSuccess {
            showOsd("频道映射", "已添加: $rawName → $standardName")
            loadMappings()
        }.onFailure { e ->
            showOsd("频道映射", "添加失败: ${e.message}")
            Log.e(AppViewModel.TAG, "addMapping failed", e)
        }
    }
}

internal fun AppViewModel.deleteMapping(standardName: String, rawName: String = "") {
    viewModelScope.launch {
        _mappingLoading.value = true
        val result = repository.deleteMapping(standardName, rawName)
        _mappingLoading.value = false
        result.onSuccess {
            showOsd("频道映射", "已删除")
            loadMappings()
        }.onFailure { e ->
            showOsd("频道映射", "删除失败: ${e.message}")
            Log.e(AppViewModel.TAG, "deleteMapping failed", e)
        }
    }
}

internal fun AppViewModel.refreshMappings() {
    viewModelScope.launch {
        _mappingLoading.value = true
        _mappingStatusText.value = "正在刷新远程映射..."
        val result = repository.refreshMappings()
        _mappingLoading.value = false
        result.onSuccess {
            _mappingStatusText.value = "远程映射已更新"
            showOsd("频道映射", "远程映射已刷新")
            loadMappings()
        }.onFailure { e ->
            _mappingStatusText.value = "刷新失败: ${e.message}"
            showOsd("频道映射", "刷新失败: ${e.message}")
            Log.e(AppViewModel.TAG, "refreshMappings failed", e)
        }
    }
}

internal fun AppViewModel.startAvSyncSampling() {
    avSyncJob?.cancel()
    avSyncJob = viewModelScope.launch {
        while (isActive) {
            // 仅 MPV 播放器支持属性读取
            val mpv = mpvSingleton
            // A/V 同步偏移的正确 mpv 属性是 total-avsync-change（"avdiff" 不存在，恒返回 0）
            val avdiff = mpv.getPropertyDouble("total-avsync-change") ?: 0.0
            val aPts = mpv.getPropertyDouble("audio-pts") ?: 0.0
            val vPts = mpv.getPropertyDouble("video-pts") ?: 0.0
            val aDelay = mpv.getPropertyDouble("audio-delay") ?: 0.0
            _avDiff.value = avdiff
            _audioPts.value = aPts
            _videoPts.value = vPts
            _currentAudioDelay.value = aDelay
            // 追加历史采样（最多 200 点）
            val history = _avDiffHistory.value.toMutableList()
            history.add(avdiff.toFloat())
            while (history.size > 200) history.removeAt(0)
            _avDiffHistory.value = history
            delay(100)
        }
    }
}

internal fun AppViewModel.stopAvSyncSampling() {
    avSyncJob?.cancel()
    avSyncJob = null
}

internal fun AppViewModel.adjustAudioDelay(delta: Double) {
    val newDelay = (_currentAudioDelay.value + delta)
    val player = _player.value
    if (player.capabilities.supportsAudioDelay) {
        if (player.setAudioDelay(newDelay)) {
            _currentAudioDelay.value = newDelay
            showOsd("音频延迟", "${"%.3f".format(newDelay)}s")
        }
    } else {
        showOsd("音频延迟", "当前播放器不支持")
    }
}

internal fun AppViewModel.resetAudioDelay() {
    val player = _player.value
    if (player.capabilities.supportsAudioDelay) {
        if (player.setAudioDelay(0.0)) {
            _currentAudioDelay.value = 0.0
            showOsd("音频延迟", "已重置")
        }
    } else {
        showOsd("音频延迟", "当前播放器不支持")
    }
}

internal fun AppViewModel.toggleSubSync() {
    _subSyncEnabled.value = !_subSyncEnabled.value
    if (_subSyncEnabled.value) {
        startSubSync()
        showOsd("字幕同步", "已开启自动同步")
    } else {
        stopSubSync()
        showOsd("字幕同步", "已关闭自动同步")
    }
}

internal fun AppViewModel.startSubSync() {
    subSyncJob?.cancel()
    subSyncWindow.clear()
    subSyncJob = viewModelScope.launch {
        while (isActive) {
            val avdiff = _avDiff.value.toFloat()
            // 跳过极端值（>1s，可能是 seek/暂停）
            if (kotlin.math.abs(avdiff) < 1.0f) {
                subSyncWindow.addLast(avdiff)
                while (subSyncWindow.size > 6) subSyncWindow.removeFirst()
                // 需要至少 3 个采样点
                if (subSyncWindow.size >= 3) {
                    val avg = subSyncWindow.takeLast(3).average().toFloat()
                    val threshold = 0.05f
                    if (kotlin.math.abs(avg) > threshold) {
                        val gain = 0.30f
                        val delta = avg * gain
                        val mpv = mpvSingleton
                        val currentSubDelay = mpv.getPropertyDouble("sub-delay") ?: 0.0
                        mpv.setSubDelay(currentSubDelay + delta)
                    }
                }
            }
            delay(500)
        }
    }
}

internal fun AppViewModel.stopSubSync() {
    subSyncJob?.cancel()
    subSyncJob = null
    subSyncWindow.clear()
}

internal fun AppViewModel.loadNetworkSettings(): Triple<String, String, String> {
    return Triple(
        userPrefs.getHttpReferer(),
        userPrefs.getHttpProxy(),
        userPrefs.getHttpHeaders()
    )
}

internal fun AppViewModel.applyNetworkSettings(referer: String, proxy: String, headers: String) {
    val mpv = mpvSingleton
    // Referer
    if (referer.isNotBlank()) {
        mpv.setPropertyString("referrer", referer)
    } else {
        mpv.setPropertyString("referrer", "")
    }
    // HTTP Proxy
    if (proxy.isNotBlank()) {
        mpv.setPropertyString("http-proxy", proxy)
    } else {
        mpv.setPropertyString("http-proxy", "")
    }
    // HTTP Headers（每行 "Key: Value"，需逐条设置）
    // mpv 的 http-header-fields 是列表属性，通过 command 设置
    if (headers.isNotBlank()) {
        headers.lines().filter { it.contains(":") }.forEach { line ->
            val parts = line.split(":", limit = 2)
            if (parts.size == 2) {
                val key = parts[0].trim()
                val value = parts[1].trim()
                mpv.command(arrayOf("set", "http-header-fields", "$key: $value"))
            }
        }
    }
    showOsd("网络增强", "已应用（下次加载生效）")
}

internal fun AppViewModel.saveNetworkSettings(referer: String, proxy: String, headers: String) {
    userPrefs.setHttpReferer(referer)
    userPrefs.setHttpProxy(proxy)
    userPrefs.setHttpHeaders(headers)
    applyNetworkSettings(referer, proxy, headers)
}

internal fun AppViewModel.clearNetworkSettings() {
    userPrefs.setHttpReferer("")
    userPrefs.setHttpProxy("")
    userPrefs.setHttpHeaders("")
    val mpv = mpvSingleton
    mpv.setPropertyString("referrer", "")
    mpv.setPropertyString("http-proxy", "")
    showOsd("网络增强", "已清除")
}

internal fun AppViewModel.copyBuiltinShaders(app: Application) {
    try {
        val shadersDir = java.io.File(app.filesDir, "shaders")
        if (!shadersDir.exists()) shadersDir.mkdirs()

        val assetFiles = app.assets.list("shaders") ?: return
        for (name in assetFiles) {
            val target = java.io.File(shadersDir, name)
            if (target.exists()) continue  // 不覆盖已有文件
            app.assets.open("shaders/$name").use { input ->
                java.io.FileOutputStream(target).use { output ->
                    input.copyTo(output)
                }
            }
        }
        Log.i("AppViewModel", "内置着色器文件已复制到 ${shadersDir.absolutePath}")
    } catch (e: Exception) {
        Log.w("AppViewModel", "复制内置着色器失败: ${e.message}")
    }
}

