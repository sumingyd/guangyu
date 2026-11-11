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

internal fun AppViewModel.clearPendingSwitchPlayUrl() {
    _pendingSwitchPlayUrl.value = ""
}

internal fun AppViewModel.consumePendingRestore(): Pair<String, Double>? = null

/**
 * 释放旧播放器 View（切换播放器类型时由 MainPlayerScreen onRelease 调用）。
 * 对于 ExoPlayer 需要真正 detach；MPV 单例只 detach 不销毁。
 */
internal fun AppViewModel.detachOldPlayer() {
    // 由 MainPlayerScreen onRelease 回调中调用
    // ExoPlayer 的 View 销毁时需要 detach
    if (_playerType.value != PlayerType.MPV) {
        _player.value.detach()
    }
}

internal fun AppViewModel.getCachedCurrentProgram(idx: Int): IptvEpgProgram? {
    val programs = epgCache[idx] ?: return null
    return ProgressHelper.findCurrentProgram(programs, System.currentTimeMillis())
}

internal fun AppViewModel.toggleChannelInfo() {
    _channelInfoOpen.value = !_channelInfoOpen.value
}

internal fun AppViewModel.isChannelFavorite(idx: Int): Boolean = _favorites.value.contains(idx)

/** 切换指定频道收藏状态 */
internal fun AppViewModel.toggleFavoriteByIndex(idx: Int): Boolean {
    val added = userPrefs.toggleFavorite(idx)
    _favorites.value = userPrefs.getFavorites()
    showOsd(if (added) "已收藏" else "已取消收藏")
    return added
}

internal fun AppViewModel.setLandscapeSidebarVisible(visible: Boolean) {
    _landscapeSidebarVisible.value = visible
    if (visible) {
        _controlsVisible.value = true
    }
}

internal fun AppViewModel.setOsdShowTime(enabled: Boolean) { _osdShowTime.value = enabled; userPrefs.setOsdShowTime(enabled) }

internal fun AppViewModel.setOsdShowNetSpeed(enabled: Boolean) { _osdShowNetSpeed.value = enabled; userPrefs.setOsdShowNetSpeed(enabled) }

internal fun AppViewModel.setOsdHideChannelNum(enabled: Boolean) { _osdHideChannelNum.value = enabled; userPrefs.setOsdHideChannelNum(enabled) }

internal fun AppViewModel.setOsdDisableEpg(enabled: Boolean) { _osdDisableEpg.value = enabled; userPrefs.setOsdDisableEpg(enabled) }

internal fun AppViewModel.setOsdDisableFavorite(enabled: Boolean) { _osdDisableFavorite.value = enabled; userPrefs.setOsdDisableFavorite(enabled) }

internal fun AppViewModel.setOsdShowListIcon(enabled: Boolean) { _osdShowListIcon.value = enabled; userPrefs.setOsdShowListIcon(enabled) }

internal fun AppViewModel.setOsdShowBottomIcon(enabled: Boolean) { _osdShowBottomIcon.value = enabled; userPrefs.setOsdShowBottomIcon(enabled) }

internal fun AppViewModel.startInitialization() {
    if (_initState.value is InitState.Initializing ||
        _initState.value is InitState.Ready
    ) return

    _initState.value = InitState.Initializing
    viewModelScope.launch {
        try {
            // 首次启动时给 ART 一点时间完成初始类加载和 JIT 编译，
            // 避免 Python native 库加载与 JIT 线程冲突导致偶发 SIGSEGV
            delay(300)

            // 1. 初始化 Python + ServerContext 单例（在 IO 线程执行，减少主线程压力）
            // 传递 Android 存储路径给 Python（jnius 不可用时的兜底方案）
            val app = getApplication<Application>()
            val extFilesDir = app.getExternalFilesDir(null)?.absolutePath ?: ""
            val filesDir = app.filesDir.absolutePath
            val nativeLibDir = app.applicationInfo.nativeLibraryDir
            val logLevel = userPrefs.getLogLevel()
            val initResult = withContext(Dispatchers.IO) {
                repository.initContext(extFilesDir, filesDir, logLevel, nativeLibDir)
            }
            if (initResult.isFailure) {
                val msg = initResult.exceptionOrNull()?.message ?: "初始化失败"
                Log.e(AppViewModel.TAG, "initContext failed: $msg")
                _initState.value = InitState.Failed(msg)
                return@launch
            }
            Log.i(AppViewModel.TAG, "initContext OK, start polling status")

            // 1.2 复制内置 GLSL 着色器文件到 filesDir/shaders/
            withContext(Dispatchers.IO) {
                copyBuiltinShaders(app)
            }

            // 1.5 设置应用版本信息（供 Web 界面使用）
            val version = getCurrentVersion()
            val buildDate = getBuildDate()
            withContext(Dispatchers.IO) {
                repository.setAppInfo(version, buildDate)
            }

            // 2. 轮询 getStatus（最长 60 秒）
            val maxWaitMs = 60_000L
            val intervalMs = 1_000L
            val startTime = System.currentTimeMillis()

            while (isActive) {
                val elapsed = System.currentTimeMillis() - startTime
                if (elapsed > maxWaitMs) {
                    _initState.value = InitState.Failed("初始化超时（60 秒）")
                    return@launch
                }

                val statusResult = repository.getStatus()
                statusResult.fold(
                    onSuccess = { status ->
                        _iptvStatus.value = status
                        Log.d(AppViewModel.TAG, "status: inited=${status.inited} loading=${status.sourceLoading} total=${status.channelsTotal}")

                        // 判断是否完成：
                        // - inited=true 即放行进入主界面，不等订阅源加载完成。
                        //   大体积内嵌 EPG 或网络不佳时 source_loading 可能持续数分钟，
                        //   若在此阻塞会触发 60 秒初始化超时导致无法进入 App。
                        //   订阅源后台加载完成后由 startBackgroundStatusRefresh 检测
                        //   channels_total 变化并自动重载频道列表。
                        if (status.inited) {
                            _initState.value = InitState.Ready(status)
                            startBackgroundStatusRefresh()
                            // 加载频道列表和用户偏好
                            loadChannels()
                            loadUserPrefs()
                            // 初始化完成后延迟 5 秒自动检查更新（避免影响启动性能）
                            viewModelScope.launch {
                                delay(5000)
                                checkForUpdates(auto = true)
                            }
                            return@launch
                        }
                    },
                    onFailure = { e ->
                        Log.w(AppViewModel.TAG, "getStatus failed (will retry): ${e.message}")
                    }
                )
                delay(intervalMs)
            }
        } catch (e: CancellationException) {
            // 协程被取消（如 Activity 销毁），不修改状态
            throw e
        } catch (e: Throwable) {
            // 捕获所有异常（包括 Chaquopy 首次启动时的资源解压错误），避免崩溃
            Log.e(AppViewModel.TAG, "startInitialization crashed", e)
            _initState.value = InitState.Failed(e.message ?: "未知错误")
        }
    }
}

internal fun AppViewModel.startBackgroundStatusRefresh() {
    statusPollJob?.cancel()
    statusPollJob = viewModelScope.launch {
        var lastTotal = _iptvStatus.value?.channelsTotal ?: 0
        while (isActive) {
            delay(3_000L)
            repository.getStatus().fold(
                onSuccess = { status ->
                    _iptvStatus.value = status
                    // 订阅源加载完成导致频道数变化时，自动重载频道列表
                    if (status.channelsTotal != lastTotal) {
                        Log.i(AppViewModel.TAG, "channels total changed: $lastTotal → ${status.channelsTotal}, reload")
                        lastTotal = status.channelsTotal
                        loadChannels()
                    }
                },
                onFailure = { /* 静默忽略 */ }
            )
        }
    }
}

internal fun AppViewModel.loadChannels() {
    viewModelScope.launch {
        // 分页拉取全部频道（bridge 端有单页上限，逐页取完以便本地过滤；
        // 翻页展示由 UI 的 LazyColumn 处理）
        val loaded = mutableListOf<IptvChannel>()
        var pageNo = 1
        var total = Int.MAX_VALUE
        var failed = false
        while (loaded.size < total) {
            repository.getChannels(page = pageNo, size = 1_000).fold(
                onSuccess = { page ->
                    total = page.total
                    loaded.addAll(page.channels)
                    if (page.channels.isEmpty()) {
                        // 空页兜底：服务端 total 与实际不一致时防死循环
                        total = loaded.size
                    }
                    pageNo++
                },
                onFailure = { e ->
                    Log.e(AppViewModel.TAG, "loadChannels failed: ${e.message}")
                    failed = true
                }
            )
            if (failed) break
        }
        if (!failed) {
            // 保存当前播放的 URL，防止频道列表更新后 currentChannel 变 null
            val savedUrl = currentPlaybackUrl
            val savedIdx = _currentIdx.value
            _channels.value = loaded
            // 如果当前正在播放，尝试在新列表中找到对应频道
            if (savedIdx >= 0 && savedUrl.isNotEmpty()) {
                val newIdx = loaded.indexOfFirst { it.url == savedUrl }
                if (newIdx >= 0 && newIdx != savedIdx) {
                    _currentIdx.value = newIdx
                    Log.i(AppViewModel.TAG, "loadChannels: current idx updated $savedIdx -> $newIdx")
                } else if (newIdx < 0) {
                    // URL 不在新列表中，保持原 idx 不变（避免显示未选择频道）
                    Log.w(AppViewModel.TAG, "loadChannels: current channel URL not found in new list, keeping idx $savedIdx")
                }
            }
            // 提取分组（保持 M3U 顺序，去重）
            val groupList = loaded
                .map { it.group }
                .filter { it.isNotEmpty() }
                .distinct()
            _groups.value = groupList
            Log.i(AppViewModel.TAG, "Loaded ${loaded.size} channels, ${groupList.size} groups")
            // 残留检测：历史版本删除订阅源时不清理频道缓存，分组列会残留已删源的分组。
            // 频道 source 不属于任何现有源 → 判定为残留，自动重载订阅源（桥端按现有源重建频道缓存）
            //
            // 注意：本地缓存保留的频道（历史订阅源残留）本身就带旧 source，重载失败/进行中时
            // 它们会一直存在，若每轮检测都触发重载就形成「残留→重载→仍残留」的自触发风暴
            // （实测启动期 10 秒内 5 轮、每轮重下 8MB EPG）。因此自动重载必须
            // 单飞 + 冷却 + 进程内次数上限。
            if (loaded.any { it.source.isNotEmpty() }) {
                val knownUrls = withContext(Dispatchers.IO) { repository.getSources() }
                    .getOrNull()?.map { it.url }?.toSet() ?: emptySet()
                if (knownUrls.isNotEmpty() && loaded.any { it.source !in knownUrls }) {
                    val now = System.currentTimeMillis()
                    val throttled = now - lastAutoSourceReloadAt < 60_000L
                    if (autoSourceReloadCount >= 1 || throttled) {
                        Log.w(AppViewModel.TAG,
                            "loadChannels: stale channels detected but auto reload skipped " +
                                    "(count=$autoSourceReloadCount, sinceLast=${
                                        (now - lastAutoSourceReloadAt) / 1000}s)")
                    } else {
                        lastAutoSourceReloadAt = now
                        autoSourceReloadCount++
                        Log.w(AppViewModel.TAG, "loadChannels: stale channels from removed sources detected, auto reload")
                        reloadSources(auto = true)
                    }
                }
            }
            // 收藏/历史/队列按 URL 重锚定（订阅重载后 idx 漂移会错位）
            reanchorUserListsToChannels()
            // 列表数据变化（冷启动/订阅刷新/本地增删）后校正页签：
            // 当前页签实际为空而另一页签有数据时切过去，避免停在空列表上
            reconcileListSourceTab()
        }
    }
}

/**
 * 按 URL 重锚定收藏/历史/队列的 idx。
 *
 * URL 版存储是持久真相源（订阅源更新/频道增删后仍可匹配）；
 * idx 版 StateFlow 仅作展示缓存。旧数据只有 idx 版时一次性迁移
 * （用当前列表尽力转换），此后每次切换频道/收藏都会双写 URL 版。
 */
internal fun AppViewModel.reanchorUserListsToChannels() {
    val all = _channels.value
    if (all.isEmpty()) return
    val urlToIdx = HashMap<String, Int>(all.size * 2)
    all.forEachIndexed { i, c -> urlToIdx.putIfAbsent(c.url, i) }

    // 1) 收藏
    val favUrls = userPrefs.getFavoriteUrls().toMutableSet()
    val legacyFavIdxs = userPrefs.getFavorites()
    if (favUrls.isEmpty() && legacyFavIdxs.isNotEmpty()) {
        legacyFavIdxs.forEach { idx -> all.getOrNull(idx)?.let { favUrls.add(it.url) } }
        userPrefs.setFavoriteUrls(favUrls)
    }
    _favorites.value = all.mapIndexed { i, c -> if (c.url in favUrls) i else null }
        .filterNotNull().toSet()

    // 2) 历史（保持时间倒序：URL 列表本身就是倒序）
    val histUrls = userPrefs.getHistoryUrls().toMutableList()
    val legacyHist = userPrefs.getHistory()
    if (histUrls.isEmpty() && legacyHist.isNotEmpty()) {
        legacyHist.forEach { idx -> all.getOrNull(idx)?.let { histUrls.add(it.url) } }
        userPrefs.setHistoryUrls(histUrls)
    }
    _history.value = histUrls.mapNotNull { urlToIdx[it] }

    // 3) 队列
    val queueUrls = userPrefs.getQueueUrls().toMutableList()
    val legacyQueue = userPrefs.getQueue()
    if (queueUrls.isEmpty() && legacyQueue.isNotEmpty()) {
        legacyQueue.forEach { idx -> all.getOrNull(idx)?.let { queueUrls.add(it.url) } }
        userPrefs.setQueueUrls(queueUrls)
    }
    _queue.value = queueUrls.mapNotNull { urlToIdx[it] }
}

internal fun AppViewModel.deleteChannel(idx: Int) {
    viewModelScope.launch {
        val result = repository.deleteChannel(idx)
        result.fold(
            onSuccess = {
                showOsd("已删除频道")
                loadChannels()
            },
            onFailure = { e ->
                showOsd("删除失败", e.message ?: "")
            }
        )
    }
}

internal fun AppViewModel.clearLocalChannels() {
    viewModelScope.launch {
        val result = repository.clearLocalChannels()
        result.fold(
            onSuccess = { count ->
                showOsd("已清空", "删除 $count 个本地频道")
                loadChannels()
            },
            onFailure = { e ->
                showOsd("清空失败", e.message ?: "")
            }
        )
    }
}

internal fun AppViewModel.restoreLastChannel(autoPlayFirstFallback: Boolean) {
    if (_currentIdx.value >= 0) {
        // 已经在播放（可能被其他逻辑触发），不重复恢复
        return
    }
    // 外部标志文件：如果存在则跳过自动播放（用于测试/调试）
    try {
        val extDir = android.os.Environment.getExternalStorageDirectory()
        val flagFile = java.io.File(extDir, "Android/data/com.iptv.scanner.editor.pro/files/ISEP/skip_auto_resume")
        if (flagFile.exists()) {
            Log.i(AppViewModel.TAG, "restoreLastChannel: skip_auto_resume flag file exists, skipping")
            return
        }
    } catch (e: Exception) {
        // 忽略文件检查错误
    }
    val channels = _channels.value
    if (channels.isEmpty()) return

    // 开启了自动续播且能找到上次频道 → 恢复上次频道
    if (userPrefs.isAutoResumeOnStart()) {
        val lastUrl = userPrefs.getLastChannelUrl()
        if (lastUrl.isNotEmpty()) {
            val lastIdx = channels.indexOfFirst { it.url == lastUrl }
            if (lastIdx >= 0) {
                Log.i(AppViewModel.TAG, "restoreLastChannel: restoring '$lastUrl' at idx=$lastIdx")
                // 恢复的频道可能属于另一页签（订阅为空、上次播放的是本地频道等），
                // 先切到该频道实际所属的页签，保证列表里能看到并高亮
                val targetTab = if (channels[lastIdx].source.isEmpty()) ListSourceTab.LOCAL else ListSourceTab.SUBSCRIPTION
                if (_listSourceTab.value != targetTab) {
                    Log.i(AppViewModel.TAG, "restoreLastChannel: switch list tab to ${targetTab.name}")
                    _listSourceTab.value = targetTab
                }
                playChannel(lastIdx, silent = true)
                // 横屏（TV 风格）：后台恢复播放但停留在首页（Mini 播放条可见），由用户点击进入播放页
                // TV 无独立首页：直接进入全屏播放
                if (autoPlayFirstFallback && _uiMode.value != UiMode.TV) _showHome.value = true
                return
            }
            Log.i(AppViewModel.TAG, "restoreLastChannel: last URL '$lastUrl' not found in ${channels.size} channels, playing first")
        }
    }
    // 回退（未开启续播或找不到上次频道）：仅横屏（TV 风格）默认播放第一个频道，
    // 避免黑屏等待；竖屏停留在频道列表首页，由用户自行选台进入播放页
    // （playChannel 会将 showHome 置 false，竖屏自动播放会直接跳进播放页，体验突兀）
    if (!autoPlayFirstFallback) {
        Log.i(AppViewModel.TAG, "restoreLastChannel: portrait startup, skip auto-play fallback")
        return
    }
    playChannel(0, silent = true)
    // 横屏（TV 风格）：后台播放但停留在首页（Mini 播放条可见），由用户点击进入播放页
    // TV 无独立首页：直接进入全屏播放
    if (_uiMode.value != UiMode.TV) _showHome.value = true
}

internal fun AppViewModel.loadUserPrefs() {
    _favorites.value = userPrefs.getFavorites()
    _history.value = userPrefs.getHistory()
    _queue.value = userPrefs.getQueue()
    _reminders.value = userPrefs.getReminders()
    _resumeList.value = userPrefs.getResumeList()
    _allBookmarks.value = userPrefs.getAllBookmarks()
    // 频道列表若已就绪则按 URL 重锚定（loadChannels 与本函数异步竞态，
    // 两个方向都要兜底保证最终一致）
    reanchorUserListsToChannels()
    // 启动提醒定时检查（与 PC 端 QTimer 10 秒间隔对齐）
    startReminderCheck()
    // 启动续播位置自动保存（10 秒间隔，与 Web 端 autoSaveResume 对齐）
    startResumeAutoSave()
}

internal fun AppViewModel.setChannelsTab(tab: ChannelTab) {
    _channelsTab.value = tab
    _selectedGroup.value = ""  // 切换 tab 时重置分组筛选
}

internal fun AppViewModel.setSearchQuery(query: String) {
    _searchQuery.value = query
}

internal fun AppViewModel.setSelectedGroup(group: String) {
    _selectedGroup.value = group
}

internal fun AppViewModel.getFilteredChannels(): List<Pair<IptvChannel, Int>> {
    val all = _channels.value
    val query = _searchQuery.value.lowercase()
    val group = _selectedGroup.value
    val tab = _channelsTab.value

    val filtered: List<Pair<IptvChannel, Int>> = when (tab) {
        ChannelTab.SUB -> all.mapIndexed { idx, c -> c to idx }
        ChannelTab.LOCAL -> all.mapIndexed { idx, c -> c to idx }
            .filter { (c, _) -> c.source.isEmpty() || ProgressHelper.isLocalFile(c.url) }
        ChannelTab.FAV -> all.mapIndexed { idx, c -> c to idx }
            .filter { (c, idx) -> _favorites.value.contains(idx) }
        ChannelTab.HIST -> _history.value.mapNotNull { idx ->
            all.getOrNull(idx)?.let { it to idx }
        }
    }

    return filtered.filter { (c, _) ->
        // 分组筛选（仅 SUB/LOCAL tab 应用）
        val groupMatch = tab != ChannelTab.SUB && tab != ChannelTab.LOCAL ||
                group.isEmpty() || c.group == group
        // 搜索筛选
        val searchMatch = query.isEmpty() ||
                c.name.lowercase().contains(query) ||
                c.group.lowercase().contains(query)
        groupMatch && searchMatch
    }
}

internal fun AppViewModel.playChannel(idx: Int, silent: Boolean = false) {
    val channel = _channels.value.getOrNull(idx) ?: return
    if (currentPlaybackUrl == channel.url && mpv.fileLoaded.value && _currentIdx.value == idx) {
        // 相同频道已在播：不重复起播，但要离开首页进入播放页
        // （此前直接 return 导致横屏首页点击正在播的频道时只停留在 Mini 播放条，
        //   与「点击频道应进入分屏播放页」的预期不符）
        Log.i(AppViewModel.TAG, "playChannel: same URL already playing, leave home only")
        _showHome.value = false
        return
    }
    Log.i(AppViewModel.TAG, "playChannel: ${channel.name} (${channel.url})")

    val oldIdx = _currentIdx.value
    _channelDisplayInfo.value = ChannelDisplayInfo(
        name = channel.name, logo = channel.logo, group = channel.group, idx = idx,
        isLocal = channel.source.isEmpty() || ProgressHelper.isLocalFile(channel.url)
    )
    _currentIdx.value = idx
    _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
    _showHome.value = false
    currentPlaybackUrl = channel.url
    currentPlaybackName = channel.name
    currentIsLocalFile = false

    // 切台时显示频道号（右上角，3秒自动隐藏）
    _channelNumDisplay.value = String.format("%03d", idx + 1)
    channelNumHideJob?.cancel()
    channelNumHideJob = viewModelScope.launch {
        delay(3_000L)
        _channelNumDisplay.value = ""
    }

    fileErrorSwitchJob?.cancel()
    fileErrorSwitchJob = null
    consecutiveTimeoutCount = 0

    uiUpdateJob?.cancel()
    uiUpdateJob = viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
        // FCC 通知必须在 loadfile 之前发送：
        // rtp2httpd 代理收到 JOIN 后预加入组播组并缓冲流数据，
        // mpv 连接代理时流已就绪，实现秒开换台。
        // 如果在 loadfile 之后发送（旧实现），代理不知道新频道，
        // mpv 连接后代理才开始加入组播，导致数秒延迟。
        fccService.onChannelChange(channel.url)
        // 先应用频道专属设置（vo/hwdec），避免 loadfile 后再重建 VO 触发二次 loadfile。
        // 换台期间抑制 setVoAndHwdec 对旧 URL 的重载：否则会把旧流重新 loadfile，
        // 与「先 JOIN 新组播、再加载新 URL」的 FCC 时序冲突（L6）。
        (_player.value as? MpvController)?.suppressVoReloadOnSwitch()
        // 换台时给硬解一次恢复机会：旧实现里会话级软解降级一旦触发就永不恢复，
        // 用户看到的是“换台后一直卡、改回硬解也没用”。
        (_player.value as? MpvController)?.retryHardwareDecodeIfDegraded("channel switch")
        applyChannelSettingsIfNeeded(idx)
        mpv.playFile(channel.url)
        (_player.value as? MpvController)?.releaseVoReloadSuppression()
        // 超时换源必须在等待加载前启动：加载成功后定时器到点检查
        // fileLoaded 为 true 自动空转；卡死时才能触发换源
        startTimeoutSwitchSource(idx)
        mpv.fileLoaded.first { it }

        if (!silent && !_landscapeSidebarVisible.value) {
            withContext(kotlinx.coroutines.Dispatchers.Main) {
                closeAllPanelsExceptSidebar()
            }
        }
        if (!silent) {
            withContext(kotlinx.coroutines.Dispatchers.Main) {
                if (uiMode.value.isTV) showControlsAutoHide()
            }
        }

        if (userPrefs.isPerChannelPlayerSettings() && oldIdx >= 0 && oldIdx != idx) {
            autoSaveCurrentSettingsToChannel(oldIdx)
        }
        refreshCurrentBookmarks()

        loadPlaybackSettingsFromStore(channel.url)
        userPrefs.addToHistory(idx)
        // 双写 URL 版本：订阅重载后按 URL 重锚定，idx 漂移不会错位
        userPrefs.addToHistoryUrl(channel.url)
        _history.value = userPrefs.getHistory()
        userPrefs.setLastChannelUrl(channel.url)
        fetchEpgForCurrent()
        prefetchAdjacentChannels(idx)
        if (uiMode.value != UiMode.TV) captureChannelThumbnail()
    }
}

internal fun AppViewModel.startTimeoutSwitchSource(idx: Int) {
    timeoutSwitchJob?.cancel()
    timeoutSwitchJob = viewModelScope.launch {
        val configuredTimeout = userPrefs.getTimeoutMs()
        // EXO 的 fileLoaded 在 STATE_READY（完成首段缓冲）才置位，冷启动常超过
        // MPV 秒开级别的配置超时（默认 5s）——直接套用会把正在正常缓冲的流
        // stop 并切台，表现为"停在第一帧不播放"。EXO 超时窗口加下限保护。
        val timeoutMs = if (_playerType.value == PlayerType.EXO) {
            maxOf(configuredTimeout, 20_000L)
        } else {
            configuredTimeout
        }
        delay(timeoutMs)
        // 超时后检查是否已加载
        if (!mpv.fileLoaded.value) {
            consecutiveTimeoutCount++
            Log.w(AppViewModel.TAG, "Timeout switch source: idx=$idx not loaded in ${timeoutMs}ms (consecutive=$consecutiveTimeoutCount)")

            // 关键修复：连续超时 >= 1 次时，stop 命令已无法清除卡死的 demuxer，
            // 必须强制重建 mpv 核心才能恢复播放。
            // 场景：坏流的 demuxer 线程卡在网络读取上（如 TLS 握手失败），
            // stop 命令虽然被接受，但无法真正中断阻塞的 I/O 调用。
            // 后续 loadfile 命令在旧 demuxer 未释放时被发送，
            // 新流也无法加载——导致所有后续频道都无法播放。
            // forceRecreate() 通过 stop + playlist-clear 重置 mpv 内部状态（不终止核心），
            // 下次 playFile() 时 ensureInstanceAlive() 检测到 forceRecreatePending 标志后
            // 直接返回（核心仍存活，idle=yes 保证不会自动 shutdown）。
            if (consecutiveTimeoutCount >= 1 && _playerType.value == PlayerType.MPV) {
                Log.w(AppViewModel.TAG, "Timeout switch: forcing mpv state reset (consecutive=$consecutiveTimeoutCount)")
                mpvSingleton.forceRecreate()
                mpvSingleton.markNeedPreStop()
                delay(500)
            } else {
                mpv.stop()
            }

            // 连续超时保护：如果连续多次超时换源（超过频道总数的 1/3，最多 10 次），
            // 说明可能是网络故障或播放器核心问题，停止自动换源避免死循环。
            // 用户可以手动切台或切换播放器内核来恢复。
            val maxConsecutive = minOf(10, maxOf(3, _channels.value.size / 3))
            if (consecutiveTimeoutCount > maxConsecutive) {
                Log.w(AppViewModel.TAG, "Timeout switch source: stopped after $consecutiveTimeoutCount consecutive timeouts")
                showOsd("自动换源已停止", "连续 ${consecutiveTimeoutCount} 次超时，请检查网络或切换播放器内核")
                consecutiveTimeoutCount = 0
                return@launch
            }

            showOsd("超时换源", "当前源加载超时，自动切换")
            nextChannel()
        }
    }
}

internal fun AppViewModel.startReconnect() {
    val delayMs = userPrefs.getReconnectDelayMs()
    if (delayMs <= 0) return  // 关闭重连
    if (_playbackState.value.mode != PlayMode.LIVE) return  // 仅直播重连

    reconnectJob?.cancel()
    reconnectJob = viewModelScope.launch {
        Log.i(AppViewModel.TAG, "Reconnect in ${delayMs}ms")
        delay(delayMs)
        val url = currentPlaybackUrl
        if (url.isNotEmpty() && _playbackState.value.mode == PlayMode.LIVE) {
            Log.i(AppViewModel.TAG, "Reconnecting: $url")
            mpv.playFile(url)
            showOsd("正在重连...")
        }
    }
}

internal fun AppViewModel.setTimeoutSwitchSource(value: Int) {
    _timeoutSwitchSource.value = value
    userPrefs.setTimeoutSwitchSource(value)
}

internal fun AppViewModel.setReconnectIndex(value: Int) {
    _reconnectIndex.value = value
    userPrefs.setReconnectIndex(value)
}

internal fun AppViewModel.speedUp() {
    val config = _speedConfig.value
    val newSpeed = config.speedUp(mpv.speed.value)
    mpv.setSpeed(newSpeed)
    showOsd("倍速 ${"%.2f".format(newSpeed)}x")
}

internal fun AppViewModel.speedDown() {
    val config = _speedConfig.value
    val newSpeed = config.speedDown(mpv.speed.value)
    mpv.setSpeed(newSpeed)
    showOsd("倍速 ${"%.2f".format(newSpeed)}x")
}

internal fun AppViewModel.speedReset() {
    mpv.setSpeed(1.0)
    showOsd("倍速 1.00x")
}

internal fun AppViewModel.setSpeedParams(params: String) {
    userPrefs.setSpeedParams(params)
    _speedConfig.value = userPrefs.getSpeedConfig()
}

internal fun AppViewModel.setEpgTimezoneOffset(value: Int) {
    _epgTimezoneOffset.value = value
    userPrefs.setEpgTimezoneOffset(value)
    // 清除 EPG 缓存，下次获取时使用新时区
    epgCache.clear()
    epgMetaCache.clear()
    _currentEpg.value = emptyList()
    _currentEpgMeta.value = null
    fetchEpgForCurrent()
}

internal fun AppViewModel.adjustEpgTimestamp(ts: Long): Long {
    val offsetHours = userPrefs.getEpgTimezoneOffsetHours()
    if (offsetHours == 0) return ts
    return ts + offsetHours * 3600_000L
}

internal fun AppViewModel.setEpgCacheSchedule(value: Int) {
    _epgCacheSchedule.value = value
    userPrefs.setEpgCacheSchedule(value)
}

internal fun AppViewModel.setScreenLock(enabled: Boolean) {
    _screenLock.value = enabled
    userPrefs.setScreenLock(enabled)
    // 对 MPV：通过 keep-open 属性控制
    if (_playerType.value == PlayerType.MPV) {
        mpvSingleton.setPropertyBoolean("keep-open", enabled)
    }
}

internal fun AppViewModel.toggleSplitMode() {
    _splitMode.value = !_splitMode.value
    userPrefs.setSplitMode(_splitMode.value)
    if (_splitMode.value) {
        // 开启分屏时关闭频道抽屉（分屏模式下频道列表始终可见）
        _channelsPanelOpen.value = false
    }
    showControlsAutoHide()
}

internal fun AppViewModel.setGroupMode(value: Int) {
    _groupMode.value = value
    userPrefs.setGroupMode(value)
}

internal fun AppViewModel.setBootStart(enabled: Boolean) {
    _bootStart.value = enabled
    userPrefs.setBootStart(enabled)
}

internal fun AppViewModel.setAutoResume(enabled: Boolean) {
    _autoResume.value = enabled
    userPrefs.setAutoResumeOnStart(enabled)
}

internal fun AppViewModel.inputChannelNumber(digit: Int) {
    val current = _channelNumberInput.value
    // 最多 4 位数
    val newInput = if (current.length >= 4) digit.toString() else current + digit.toString()
    _channelNumberInput.value = newInput
    showOsd("选台: $newInput")

    // 重启 2 秒超时定时器
    channelNumberJob?.cancel()
    channelNumberJob = viewModelScope.launch {
        delay(2000)
        commitChannelNumber()
    }
}

internal fun AppViewModel.commitChannelNumber(): Boolean {
    val input = _channelNumberInput.value
    if (input.isEmpty()) return false

    channelNumberJob?.cancel()
    _channelNumberInput.value = ""

    val targetNum = input.toIntOrNull() ?: return false
    if (targetNum <= 0) return false

    // 频道列表按 1-based 索引（第 1 个频道 = 1）
    val targetIdx = targetNum - 1
    val channels = _channels.value
    if (targetIdx in channels.indices) {
        playChannel(targetIdx)
        return true
    } else {
        showOsd("频道 $targetNum 不存在")
        return false
    }
}

internal fun AppViewModel.prefetchAdjacentChannels(currentIdx: Int) {
    val channels = _channels.value
    if (channels.size <= 1) return

    val adjacentUrls = mutableListOf<String>()
    for (delta in intArrayOf(1, -1)) {
        val adjIdx = currentIdx + delta
        if (adjIdx in channels.indices) {
            val url = channels[adjIdx].url
            if (url.isNotEmpty()) adjacentUrls.add(url)
        }
    }
    if (adjacentUrls.isEmpty()) return

    viewModelScope.launch(Dispatchers.IO) {
        for (url in adjacentUrls) {
            try {
                val host = extractHost(url) ?: continue
                // DNS 预解析：InetAddress.getByName 会缓存结果到系统 DNS 缓存
                java.net.InetAddress.getByName(host)
                Log.d(AppViewModel.TAG, "DNS prefetch: $host (from $url)")
            } catch (e: Exception) {
                // DNS 预解析失败不影响正常播放
                Log.d(AppViewModel.TAG, "DNS prefetch failed for $url: ${e.message}")
            }
        }
    }
}

internal fun AppViewModel.extractHost(url: String): String? {
    return try {
        val uri = android.net.Uri.parse(url)
        uri.host
    } catch (e: Exception) {
        null
    }
}

internal fun AppViewModel.applyChannelSettingsIfNeeded(idx: Int) {
    if (!userPrefs.isPerChannelPlayerSettings()) return
    val settings = userPrefs.getChannelSettings(idx) ?: return

    // 1. 应用 vo/hwdec（会触发 mpv 重新加载，随后 playFile 加载新频道）
    settings.vo?.let { vo ->
        if (_currentVo.value != vo) setPlayerVo(vo)
    }
    settings.hwdec?.let { hwdec ->
        val actualHwdec = if (settings.vo == "mediacodec_embed") "mediacodec" else hwdec
        if (_currentHwdec.value != actualHwdec) setPlayerHwdec(actualHwdec, byUser = false)
    }

    // 2. 应用 HDR 模式（只更新状态，由 applyHdrOnFileLoaded 在文件加载后应用）
    settings.hdrMode?.let { modeName ->
        try {
            val mode = HdrMode.valueOf(modeName.uppercase())
            if (_hdrMode.value != mode) {
                userPrefs.setHdrMode(modeName.lowercase())
                _hdrMode.value = mode
            }
        } catch (e: Exception) {
            Log.w(AppViewModel.TAG, "applyChannelSettings: invalid hdrMode=$modeName")
        }
    }

    if (settings.vo != null || settings.hwdec != null || settings.hdrMode != null) {
        Log.i(AppViewModel.TAG, "applyChannelSettings: idx=$idx, settings=$settings")
    }
}

internal fun AppViewModel.autoSaveCurrentSettingsToChannel(idx: Int) {
    val settings = ChannelPlayerSettings(
        playerType = PlayerType.MPV.name,
        vo = _currentVo.value,
        hwdec = _currentHwdec.value,
        hdrMode = _hdrMode.value.name.lowercase()
    )
    userPrefs.setChannelSettings(idx, settings)
    Log.i(AppViewModel.TAG, "autoSaveCurrentSettingsToChannel: idx=$idx, settings=$settings")

    // 同时保存到 PlaybackSettingsStore（按 URL 持久化，#24）
    savePlaybackSettingsToStore(idx)
}

internal fun AppViewModel.savePlaybackSettingsToStore(idx: Int) {
    val channel = _channels.value.getOrNull(idx) ?: return
    val url = channel.url.ifEmpty { return }
    val settings = mutableMapOf<String, String>()
    // 音轨
    val aid = mpv.getPropertyString("aid") ?: ""
    if (aid.isNotEmpty()) settings["aid"] = aid
    // 字幕轨
    val sid = mpv.getPropertyString("sid") ?: ""
    if (sid.isNotEmpty()) settings["sid"] = sid
    // 音量
    settings["volume"] = mpv.volume.value.toInt().toString()
    // 画面比例
    val aspect = mpv.getPropertyString("video-aspect") ?: ""
    if (aspect.isNotEmpty()) settings["video-aspect"] = aspect
    // 翻转
    val flip = mpv.getPropertyString("vf") ?: ""
    if (flip.isNotEmpty()) settings["vf"] = flip
    // 旋转
    val rotate = mpv.getPropertyString("video-rotate") ?: ""
    if (rotate.isNotEmpty() && rotate != "0") settings["video-rotate"] = rotate
    // 倍速
    val speed = mpv.speed.value
    if (speed != 1.0) settings["speed"] = speed.toString()

    if (settings.isNotEmpty()) {
        viewModelScope.launch {
            val jsonStr = buildJsonObject {
                settings.forEach { (k, v) -> put(k, JsonPrimitive(v)) }
            }.toString()
            repository.savePlaybackSettings(url, jsonStr, channel.name)
            Log.d(AppViewModel.TAG, "savePlaybackSettingsToStore: url=$url, settings=$settings")
        }
    }
}

internal fun AppViewModel.loadPlaybackSettingsFromStore(url: String) {
    if (url.isEmpty()) return
    viewModelScope.launch {
        val result = repository.loadPlaybackSettings(url)
        result.onSuccess { resp ->
            val settings = resp.settings
            if (settings.isEmpty()) return@onSuccess
            Log.d(AppViewModel.TAG, "loadPlaybackSettingsFromStore: url=$url, settings=$settings")
            // 等待文件加载后再应用轨道设置
            settings["aid"]?.let { aid ->
                if (aid.isNotEmpty()) {
                    kotlinx.coroutines.delay(500)
                    mpv.setPropertyString("aid", aid)
                }
            }
            settings["sid"]?.let { sid ->
                if (sid.isNotEmpty()) {
                    kotlinx.coroutines.delay(500)
                    mpv.setPropertyString("sid", sid)
                }
            }
            settings["volume"]?.toIntOrNull()?.let { vol ->
                mpv.setVolume(vol)
            }
            settings["video-aspect"]?.let { aspect ->
                if (aspect.isNotEmpty()) mpv.setPropertyString("video-aspect", aspect)
            }
            settings["video-rotate"]?.toIntOrNull()?.let { rotate ->
                if (rotate != 0) mpv.setPropertyString("video-rotate", rotate.toString())
            }
            settings["speed"]?.toDoubleOrNull()?.let { speed ->
                if (speed != 1.0) mpv.setSpeed(speed)
            }
        }.onFailure { e ->
            Log.w(AppViewModel.TAG, "loadPlaybackSettingsFromStore failed: ${e.message}")
        }
    }
}

internal fun AppViewModel.clearChannelSettings(idx: Int) {
    userPrefs.removeChannelSettings(idx)
    showOsd("频道设置", "已清除该频道的专属设置")
    Log.i(AppViewModel.TAG, "clearChannelSettings: idx=$idx")
}

internal fun AppViewModel.hasChannelSettings(idx: Int): Boolean = userPrefs.getChannelSettings(idx) != null

/** 频道记忆开关 */
internal val AppViewModel.perChannelSettingsEnabled: StateFlow<Boolean>
    get() = _perChannelSettingsEnabled.asStateFlow()

internal fun AppViewModel.setPerChannelSettingsEnabled(enabled: Boolean) {
    userPrefs.setPerChannelPlayerSettings(enabled)
    _perChannelSettingsEnabled.value = enabled
    showOsd("频道记忆", if (enabled) "已开启 — 每个频道将记忆各自的播放器设置" else "已关闭 — 所有频道使用全局设置")
}

internal fun AppViewModel.enterMultiView(layout: MultiViewLayout = MultiViewLayout.DUAL) {
    if (_multiViewState.value.active) {
        switchMultiViewLayout(layout)
        return
    }
    val primaryIdx = _currentIdx.value
    val primaryName = currentChannel.value?.name ?: ""
    if (primaryIdx < 0) {
        showOsd("多画面", "请先选择一个频道")
        return
    }
    _multiViewState.value = MultiViewState.create(layout, primaryIdx, primaryName)
    closeAllPanels()
    // 隐藏控制层，让多画面网格完整可见（用户按 CENTER 可重新显示控制层）
    hideControls()
    showOsd("多画面", "已进入${layout.displayName}模式")
}

internal fun AppViewModel.exitMultiView() {
    if (!_multiViewState.value.active) return
    releaseAllSubPlayers()
    _multiViewState.value = MultiViewState()
    _subPlayerStates.value = emptyMap()
    // 退出多画面后显示控制层（自动隐藏），让用户看到操作选项
    showControlsAutoHide()
    showOsd("多画面", "已退出多画面模式")
}

internal fun AppViewModel.switchMultiViewLayout(layout: MultiViewLayout) {
    val current = _multiViewState.value
    if (!current.active || current.layout == layout) return
    // 缩小布局时，释放超出范围的副画面播放器
    if (layout.count < current.layout.count) {
        for (i in layout.count until current.layout.count) {
            releaseSubPlayer(i)
        }
    }
    val newViewports = (0 until layout.count).map { i ->
        current.viewports.getOrNull(i) ?: MultiViewport(index = i)
    }
    _multiViewState.value = current.copy(layout = layout, viewports = newViewports)
    showOsd("多画面", "已切换到${layout.displayName}")
}

internal fun AppViewModel.addChannelToMultiView(channelIdx: Int): Int {
    val state = _multiViewState.value
    if (!state.active) return -1
    val channel = _channels.value.getOrNull(channelIdx) ?: return -1

    val focused = state.focusedViewport
    val targetViewport = if (focused != null && !focused.isPrimary) {
        focused
    } else {
        state.firstEmptyViewport ?: run {
            showOsd("多画面", "画面已满，请先关闭一个画面")
            return -1
        }
    }
    val targetIdx = targetViewport.index

    // 主画面的频道切换走 playChannel
    if (targetIdx == 0) {
        playChannel(channelIdx)
        return 0
    }

    // 副画面：创建/复用 SubPlayer 并播放
    try {
        // 副画面基于 ExoPlayer，不支持 udp/rtp 组播源（主画面的 mpv 才支持）；
        // 提前拦截给出明确提示，而不是让用户看到无解释的"播放错误"
        val scheme = channel.url.trim().lowercase().substringBefore("://")
        if (scheme in setOf("udp", "rtp", "igmp")) {
            showOsd("多画面", "副画面不支持组播源(udp/rtp)，请用 http/https 频道")
            Log.w(AppViewModel.TAG, "addChannelToMultiView: multicast url rejected: ${channel.url}")
            return -1
        }
        val subPlayer = getOrCreateSubPlayer(targetIdx)
        Log.i(AppViewModel.TAG, "addChannelToMultiView: targetIdx=$targetIdx, subPlayer=${subPlayer.hashCode()}, exoPlayer=${subPlayer.getExoPlayer()?.hashCode()}")
        subPlayer.play(channel.url)

        // 更新 _subPlayerStates 触发 Compose 重组（让 SubViewportContent 重新获取 SubPlayer）
        _subPlayerStates.value = _subPlayerStates.value.toMutableMap().apply {
            put(targetIdx, subPlayer.state.value)
        }

        // 更新视口状态
        _multiViewState.value = state.copy(
            viewports = state.viewports.map {
                if (it.index == targetIdx) it.copy(
                    channelIdx = channelIdx,
                    channelName = channel.name,
                    isMuted = true
                ) else it
            }
        )
        showOsd("多画面", "${channel.name} → 画面 ${targetIdx + 1}")

        return targetIdx
    } catch (e: Throwable) {
        Log.e(AppViewModel.TAG, "addChannelToMultiView: failed to play on viewport $targetIdx", e)
        showOsd("多画面", "副画面播放失败: ${e.message}")
        return -1
    }
}

internal fun AppViewModel.toggleMultiViewMute(viewportIndex: Int) {
    val state = _multiViewState.value
    if (!state.active) return
    val viewport = state.viewports.getOrNull(viewportIndex) ?: return
    if (viewport.isEmpty) return  // 空画面无需静音

    val newMuted = !viewport.isMuted

    // 更新 UI 状态
    _multiViewState.value = state.copy(
        viewports = state.viewports.map {
            if (it.index == viewportIndex) it.copy(isMuted = newMuted) else it
        }
    )

    // 应用到 Player
    try {
        if (viewportIndex == 0) {
            _player.value.setMute(newMuted)
        } else {
            subPlayers[viewportIndex]?.setMuted(newMuted)
        }
    } catch (e: Throwable) {
        Log.w(AppViewModel.TAG, "toggleMultiViewMute: viewport=$viewportIndex, failed: ${e.message}")
    }

    Log.i(AppViewModel.TAG, "toggleMultiViewMute: viewport=$viewportIndex, muted=$newMuted")
    showOsd("多画面", "画面 ${viewportIndex + 1} ${if (newMuted) "已静音" else "已取消静音"}")
}

internal fun AppViewModel.removeFromMultiView(viewportIndex: Int) {
    val state = _multiViewState.value
    if (!state.active || viewportIndex == 0) return
    // 释放对应副画面播放器
    releaseSubPlayer(viewportIndex)
    val newViewports = state.viewports.map { vp ->
        if (vp.index == viewportIndex) MultiViewport(index = viewportIndex) else vp
    }
    _multiViewState.value = state.copy(viewports = newViewports)
}

internal fun AppViewModel.getSubPlayer(viewportIndex: Int): SubPlayer? {
    return subPlayers[viewportIndex]
}

internal fun AppViewModel.getOrCreateSubPlayer(viewportIndex: Int): SubPlayer {
    val existing = subPlayers[viewportIndex]
    Log.i(AppViewModel.TAG, "getOrCreateSubPlayer: viewportIndex=$viewportIndex, existing=${existing != null}, currentCount=${subPlayers.size}, keys=${subPlayers.keys}")
    return subPlayers.getOrPut(viewportIndex) {
        val app = getApplication<Application>()
        Log.i(AppViewModel.TAG, "getOrCreateSubPlayer: creating NEW SubPlayer for viewportIndex=$viewportIndex")
        SubPlayer(app).also { it.init() }
    }
}

internal fun AppViewModel.releaseSubPlayer(viewportIndex: Int) {
    subPlayers.remove(viewportIndex)?.release()
    _subPlayerStates.value = _subPlayerStates.value.toMutableMap().apply { remove(viewportIndex) }
}

internal fun AppViewModel.releaseAllSubPlayers() {
    subPlayers.values.forEach { it.release() }
    subPlayers.clear()
}

internal fun AppViewModel.setFocusedViewport(viewportIndex: Int) {
    val state = _multiViewState.value
    if (!state.active) return
    if (viewportIndex !in state.viewports.indices) return
    _multiViewState.value = state.copy(focusedIndex = viewportIndex)
}



internal fun AppViewModel.setDeinterlace(value: String) {
if (_currentDeinterlace.value == value) return
userPrefs.setDeinterlace(value)
_currentDeinterlace.value = value
(_player.value as? MpvController)?.setDeinterlace(value)
showOsd("播放器设置", "反交错: ${if (value == "auto") "自动" else "关闭"}")
}


internal fun AppViewModel.hideControls() {
        _controlsVisible.value = false
        _controlsPinned.value = false
        tvControlsAutoHideJob?.cancel()
    }


internal fun AppViewModel.mpvGetPath(): String {
return if (mpvSingleton == _player.value) mpvSingleton.getPath() else ""
}


internal fun AppViewModel.mpvRefreshSurface() {
if (mpvSingleton == _player.value) mpvSingleton.refreshSurface()
}


internal fun AppViewModel.mpvClearSuppressFileError(delayMs: Long = 800) {
if (mpvSingleton == _player.value) mpvSingleton.clearSuppressFileError(delayMs)
}


internal fun AppViewModel.mpvSuppressFileError() {
if (mpvSingleton == _player.value) mpvSingleton.suppressFileError()
}


internal fun AppViewModel.showHomeScreen() {
    // TV 无独立首页：全屏即主页，打开自带的频道列表侧边栏
    if (_uiMode.value == UiMode.TV) {
        _landscapeSidebarVisible.value = true
        return
    }
_showHome.value = true
// 播放器被移除渲染，需要暂停播放（避免后台播放占用资源）
// 如果需要后台继续播放音频，注释掉这行
// mpv.setPause(true)
}


internal fun AppViewModel.showPlayerScreen() {
    _showHome.value = false
    // 重新打开播放页时重试一次硬解：清除会话级软解降级，避免一次偶发失败导致本轮永久软解
    (_player.value as? MpvController)?.retryHardwareDecodeIfDegraded("reopen player")
    // 播放器固定位置后 Surface 不被销毁，通常无需 refreshSurface。
    // 但作为安全网：若文件已加载则刷新 surface，否则重新加载。
    val url = currentPlaybackUrl
    viewModelScope.launch {
        delay(200)
        if (mpv.fileLoaded.value) {
            mpv.refreshSurface()
        } else if (url.isNotEmpty()) {
            mpv.playFile(url)
        }
    }
}


internal fun AppViewModel.switchPlayerType(newType: PlayerType) {
if (_playerType.value == newType) return
Log.i(AppViewModel.TAG, "switchPlayerType: ${_playerType.value} -> $newType")

        // 保存当前播放状态
        val savedUrl = currentPlaybackUrl
        val savedIdx = _currentIdx.value

        // 取消所有定时器
        timeoutSwitchJob?.cancel()
        timeoutSwitchJob = null
        reconnectJob?.cancel()
        reconnectJob = null
        switchPlayJob?.cancel()
        switchPlayJob = null
        consecutiveTimeoutCount = 0

        // 1. 先停止当前播放器（同步停止，防止旧播放器继续播放声音）
        _player.value.stop()
        _player.value.detach()

        // 2. 先更新 _playerType，触发 Compose 重组
        //    key(playerType) 会销毁旧 View（触发 onRelease）并创建新 View（触发 factory + attachView）
        _playerType.value = newType

        // 3. 创建新播放器实例
        val newPlayer: Player = when (newType) {
            PlayerType.MPV -> {
                // MPV 单例已被 detach，attachView 时会重新绑定
                mpvSingleton
            }
PlayerType.EXO -> {
// 每次都重建 ExoPlayer wrapper，确保渲染器配置正确
exoWrapper?.detach()
exoWrapper = ExoPlayerWrapper(getApplication()).also {
// 继承当前的硬解/软解、音量、静音设置
it.setHardwareDecode(_hardwareDecode.value)
it.setVolume(mpv.volume.value)
it.setMute(mpv.muted.value)
}
exoWrapper!!
}
        }
        _player.value = newPlayer
        userPrefs.setPlayerType(newType.name)

        showOsd("播放器已切换到 ${newType.displayName}")

        // 设置待播放 URL，由 MainPlayerScreen 的 update 回调在 attachView 后播放
        if (savedIdx >= 0 && savedUrl.isNotEmpty()) {
            _pendingSwitchPlayUrl.value = savedUrl
        }
    }

