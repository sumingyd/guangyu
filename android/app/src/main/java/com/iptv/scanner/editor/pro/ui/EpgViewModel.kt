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

internal fun AppViewModel.toggleReminder(program: IptvEpgProgram, channel: IptvChannel?) {
    val startMs = program.startTs * 1000L
    val stopMs = program.stopTs * 1000L
    if (startMs <= 0) {
        showOsd("提醒", "节目时间无效")
        return
    }
    val chIdx = _currentIdx.value
    val id = "${chIdx}_${program.title}_${startMs}"

    if (userPrefs.hasReminder(id)) {
        // 已存在 → 取消
        userPrefs.removeReminder(id)
        notifiedReminderIds.remove(id)
        _reminders.value = userPrefs.getReminders()
        showOsd("提醒", "已取消: ${program.title}")
        return
    }

    // 新增
    val item = ReminderItem(
        id = id,
        channelIdx = chIdx,
        channelName = channel?.name ?: "",
        tvgId = channel?.tvgId ?: "",
        programTitle = program.title,
        startTs = startMs,
        stopTs = stopMs,
        createdAt = System.currentTimeMillis(),
    )
    if (userPrefs.addReminder(item)) {
        _reminders.value = userPrefs.getReminders()
        val now = System.currentTimeMillis()
        val remainingMin = (startMs - now) / 60_000
        val msg = if (remainingMin > 0) "将在 $remainingMin 分钟后开始" else "即将开始"
        showOsd("提醒已设置", "${program.title} $msg")
    }
}

internal fun AppViewModel.isReminderSet(program: IptvEpgProgram): Boolean {
    val chIdx = _currentIdx.value
    val startMs = program.startTs * 1000L
    val id = "${chIdx}_${program.title}_${startMs}"
    _reminders.value
    return userPrefs.hasReminder(id)
}

internal fun AppViewModel.toggleReminderPanel() {
    _reminderPanelOpen.value = !_reminderPanelOpen.value
    if (!_reminderPanelOpen.value) {
        showControlsAutoHide()
    } else {
        // 刷新最新数据
        _reminders.value = userPrefs.getReminders()
    }
}

internal fun AppViewModel.removeReminder(id: String) {
    if (userPrefs.removeReminder(id)) {
        _reminders.value = userPrefs.getReminders()
        notifiedReminderIds.remove(id)
        showOsd("提醒", "已删除")
    }
}

internal fun AppViewModel.clearReminders() {
    userPrefs.clearReminders()
    _reminders.value = emptyList()
    notifiedReminderIds.clear()
    showOsd("提醒", "已清空")
}

internal fun AppViewModel.acceptTriggeredReminder() {
    val item = _triggeredReminder.value ?: return
    _triggeredReminder.value = null
    val chIdx = item.channelIdx
    if (chIdx in _channels.value.indices) {
        playChannel(chIdx)
        showOsd("提醒", "已切换到 ${item.channelName}")
    } else {
        showOsd("提醒", "频道不可用（可能已下线）")
    }
}

internal fun AppViewModel.dismissTriggeredReminder() {
    _triggeredReminder.value = null
}

internal fun AppViewModel.startReminderCheck() {
    reminderCheckJob?.cancel()
    reminderCheckJob = viewModelScope.launch {
        while (isActive) {
            delay(10_000)
            try {
                checkReminders()
            } catch (e: Exception) {
                Log.w(AppViewModel.TAG, "reminder check failed: ${e.message}")
            }
        }
    }
}

internal fun AppViewModel.stopReminderCheck() {
    reminderCheckJob?.cancel()
    reminderCheckJob = null
}

internal fun AppViewModel.toggleResumePanel() {
    _resumePanelOpen.value = !_resumePanelOpen.value
    if (!_resumePanelOpen.value) {
        showControlsAutoHide()
    } else {
        _resumeList.value = userPrefs.getResumeList()
    }
}

internal fun AppViewModel.removeResume(url: String) {
    if (userPrefs.removeResume(url)) {
        _resumeList.value = userPrefs.getResumeList()
        showOsd("续播", "已删除")
    }
}

internal fun AppViewModel.clearResumeList() {
    userPrefs.clearResume()
    _resumeList.value = emptyList()
    showOsd("续播", "已清空")
}

internal fun AppViewModel.playResume(item: ResumeItem) {
    _resumePanelOpen.value = false
    showControlsAutoHide()
    // 跳过自动恢复，避免 seek 被覆盖
    skipNextResumeFlag = false  // 我们要主动 seek，不需要跳过
    if (item.channelIdx >= 0 && item.channelIdx in _channels.value.indices) {
        // 频道：切台后延迟 seek
        playChannel(item.channelIdx)
        viewModelScope.launch {
            delay(800)  // 等待 fileLoaded
            mpv.seekAbsolute(item.position.toDouble())
            showOsd("续播", "${item.name} · ${formatDuration(item.position)} / ${formatDuration(item.duration)}")
        }
    } else {
        // 本地视频：直接 playFile 后延迟 seek
        currentPlaybackUrl = item.url
        currentPlaybackName = item.name
        currentIsLocalFile = true
        _currentIdx.value = -1
        _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
        mpv.playFile(item.url)
        viewModelScope.launch {
            delay(800)
            mpv.seekAbsolute(item.position.toDouble())
            showOsd("续播", "${item.name} · ${formatDuration(item.position)} / ${formatDuration(item.duration)}")
        }
    }
}

internal fun AppViewModel.skipNextResume() {
    skipNextResumeFlag = true
}

internal fun AppViewModel.getCurrentPlaybackUrl(): String = currentPlaybackUrl

/**
 * 文件加载完成时尝试恢复位置（由播放器回调触发）。
 * - 跳过标志为 true 时直接消费并返回
 * - 位置 <5s 或距结尾 <3s 不恢复
 * - 延迟 400ms 后 seek（与 PC 端 _on_file_loaded 对齐）
 */
internal fun AppViewModel.onFileLoadedForResume(url: String) {
    if (skipNextResumeFlag) {
        skipNextResumeFlag = false
        Log.i(AppViewModel.TAG, "resume: skip flag consumed for $url")
        return
    }
    // 仅本地文件恢复续播位置（直播/网络流不恢复，避免 seek 到错误位置）
    if (!ProgressHelper.isLocalFile(url)) return
    val resume = userPrefs.getResume(url) ?: return
    if (resume.position < 5) return
    if (resume.duration > 0 && resume.position + 3 >= resume.duration) return
    viewModelScope.launch {
        delay(400)
        mpv.seekAbsolute(resume.position.toDouble())
        Log.i(AppViewModel.TAG, "resume: restored ${resume.name} to ${resume.position}s")
        showOsd("续播", "${resume.name} · 已恢复到 ${formatDuration(resume.position)}")
    }
}

internal fun AppViewModel.startResumeAutoSave() {
    resumeSaveJob?.cancel()
    resumeSaveJob = viewModelScope.launch {
        while (isActive) {
            delay(10_000)
            try {
                autoSaveResume()
            } catch (e: Exception) {
                Log.w(AppViewModel.TAG, "resume auto-save failed: ${e.message}")
            }
        }
    }
}

internal fun AppViewModel.stopResumeAutoSave() {
    resumeSaveJob?.cancel()
    resumeSaveJob = null
}

internal fun AppViewModel.autoSaveResume() {
    if (currentPlaybackUrl.isEmpty()) return
    // 仅本地文件保存续播位置（直播/网络流不保存）
    if (!ProgressHelper.isLocalFile(currentPlaybackUrl)) return
    val pos = mpv.timePos.value
    val dur = mpv.duration.value
    if (dur <= 0 || dur > 86400) return
    if (pos < 1) return

    val item = ResumeItem(
        id = currentPlaybackUrl,
        url = currentPlaybackUrl,
        name = currentPlaybackName,
        channelIdx = if (currentIsLocalFile) -1 else _currentIdx.value,
        position = pos.toLong(),
        duration = dur.toLong(),
        updatedAt = System.currentTimeMillis(),
    )
    val newList = userPrefs.saveResume(item)
    _resumeList.value = newList
}

internal fun AppViewModel.formatDuration(sec: Long): String {
    if (sec <= 0) return "00:00"
    val h = sec / 3600
    val m = (sec % 3600) / 60
    val s = sec % 60
    return if (h > 0) "%02d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
}

internal fun AppViewModel.toggleBookmarkPanel() {
    _bookmarkPanelOpen.value = !_bookmarkPanelOpen.value
    if (!_bookmarkPanelOpen.value) {
        showControlsAutoHide()
    } else {
        // 刷新数据
        _currentBookmarks.value = userPrefs.getBookmarks(currentPlaybackUrl)
        _allBookmarks.value = userPrefs.getAllBookmarks()
    }
}

internal fun AppViewModel.setBookmarkShowCurrent(show: Boolean) {
    _bookmarkShowCurrent.value = show
}

internal fun AppViewModel.addBookmark(name: String = "") {
    if (currentPlaybackUrl.isEmpty()) {
        showOsd("书签", "未在播放")
        return
    }
    val pos = mpv.timePos.value
    if (pos < 1) {
        showOsd("书签", "位置无效")
        return
    }
    val finalName = if (name.isBlank()) {
        "${currentPlaybackName} @${formatDuration(pos.toLong())}"
    } else name
    val list = userPrefs.addBookmark(currentPlaybackUrl, pos.toLong(), finalName)
    _currentBookmarks.value = list
    _allBookmarks.value = userPrefs.getAllBookmarks()
    showOsd("书签已添加", "$finalName @${formatDuration(pos.toLong())}")
}

internal fun AppViewModel.gotoBookmark(item: BookmarkItem) {
    if (item.url == currentPlaybackUrl) {
        // 同 URL 直接 seek
        mpv.seekAbsolute(item.position.toDouble())
        showOsd("书签", "${item.name} @${formatDuration(item.position)}")
        _bookmarkPanelOpen.value = false
        showControlsAutoHide()
        return
    }
    // 跨 URL：在频道列表中查找
    val chIdx = _channels.value.indexOfFirst { it.url == item.url }
    if (chIdx >= 0) {
        // 频道：切台后延迟 seek
        skipNextResume()  // 避免续播位置覆盖书签位置
        playChannel(chIdx, silent = true)
        viewModelScope.launch {
            delay(800)
            mpv.seekAbsolute(item.position.toDouble())
            showOsd("书签", "${item.name} @${formatDuration(item.position)}")
        }
        _bookmarkPanelOpen.value = false
        showControlsAutoHide()
    } else {
        // 本地视频或网络流（不在频道列表中）
        skipNextResume()
        currentPlaybackUrl = item.url
        currentPlaybackName = item.name
        currentIsLocalFile = true
        _currentIdx.value = -1
        _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
        mpv.playFile(item.url)
        viewModelScope.launch {
            delay(800)
            mpv.seekAbsolute(item.position.toDouble())
            showOsd("书签", "${item.name} @${formatDuration(item.position)}")
        }
        _bookmarkPanelOpen.value = false
        showControlsAutoHide()
    }
}

internal fun AppViewModel.deleteBookmark(item: BookmarkItem) {
    if (userPrefs.deleteBookmark(item.url, item.position)) {
        _currentBookmarks.value = userPrefs.getBookmarks(currentPlaybackUrl)
        _allBookmarks.value = userPrefs.getAllBookmarks()
        showOsd("书签", "已删除")
    }
}

internal fun AppViewModel.clearCurrentBookmarks() {
    if (currentPlaybackUrl.isEmpty()) return
    userPrefs.clearBookmarks(currentPlaybackUrl)
    _currentBookmarks.value = emptyList()
    _allBookmarks.value = userPrefs.getAllBookmarks()
    showOsd("书签", "已清除当前文件书签")
}

internal fun AppViewModel.clearAllBookmarks() {
    userPrefs.clearAllBookmarks()
    _currentBookmarks.value = emptyList()
    _allBookmarks.value = emptyList()
    showOsd("书签", "已清空全部")
}

internal fun AppViewModel.refreshCurrentBookmarks() {
    _currentBookmarks.value = userPrefs.getBookmarks(currentPlaybackUrl)
    _allBookmarks.value = userPrefs.getAllBookmarks()
}

internal fun AppViewModel.checkReminders() {
    val now = System.currentTimeMillis()
    val list = userPrefs.getReminders()
    if (list.isEmpty()) {
        if (_reminders.value.isNotEmpty()) _reminders.value = emptyList()
        return
    }

    val ONE_HOUR = 60 * 60 * 1000L
    val mutable = list.toMutableList()
    var changed = false

    // 1) 清理过期（节目结束超 1 小时）
    val expired = mutable.filter { it.stopTs in 1..(now - ONE_HOUR) }
    if (expired.isNotEmpty()) {
        expired.forEach { notifiedReminderIds.remove(it.id) }
        mutable.removeAll(expired)
        changed = true
    }

    // 2) 触发即将开始的提醒（60 秒提前）
    val triggered = mutable.firstOrNull { item ->
        val remaining = item.startTs - now
        remaining in 0..60_000 && item.id !in notifiedReminderIds &&
                _triggeredReminder.value?.id != item.id
    }
    if (triggered != null) {
        notifiedReminderIds.add(triggered.id)
        _triggeredReminder.value = triggered
        Log.i(AppViewModel.TAG, "reminder triggered: ${triggered.programTitle} (ch=${triggered.channelName})")
        // 后台兜底：应用不在前台时由系统通知提醒（前台仍有应用内弹窗）
        com.iptv.scanner.editor.pro.EpgReminderNotifier.notifyProgramStart(
            getApplication(), triggered.channelName, triggered.programTitle
        )
    }

    // 3) 持久化清理结果
    if (changed) {
        userPrefs.setReminders(mutable)
        _reminders.value = mutable
    }
}

internal fun AppViewModel.toggleEpgTimelinePanel() {
    _epgTimelineOpen.value = !_epgTimelineOpen.value
    if (!_epgTimelineOpen.value) {
        showControlsAutoHide()
    } else {
        // 首次打开自动加载
        if (_epgTimelineRows.value.isEmpty()) {
            loadEpgTimeline()
        }
    }
}

internal fun AppViewModel.setEpgTimelineRange(range: EpgTimelineRange) {
    if (_epgTimelineRange.value == range) return
    _epgTimelineRange.value = range
    loadEpgTimeline()
}

internal fun AppViewModel.setEpgTimelineDateOffset(offset: Int) {
    val clamped = offset.coerceIn(-7, 7)
    if (_epgTimelineDateOffset.value == clamped) return
    _epgTimelineDateOffset.value = clamped
    loadEpgTimeline()
}

internal fun AppViewModel.loadEpgTimeline() {
    val channels = _channels.value
    if (channels.isEmpty()) {
        _epgTimelineStatus.value = "无频道数据"
        _epgTimelineRows.value = emptyList()
        return
    }

    val selectedChannels = when (_epgTimelineRange.value) {
        EpgTimelineRange.ALL -> channels
        EpgTimelineRange.FAVORITES -> _favorites.value
            .mapNotNull { idx -> channels.getOrNull(idx) }
        EpgTimelineRange.CURRENT_GROUP -> {
            val group = _selectedGroup.value
            if (group.isEmpty()) channels
            else channels.filter { it.group == group }
        }
    }

    if (selectedChannels.isEmpty()) {
        _epgTimelineStatus.value = "所选范围无频道"
        _epgTimelineRows.value = emptyList()
        return
    }

    // 懒加载优化：只建空行骨架（不解析任何 EPG），节目数据由 TimelineGrid 可视窗口
    // 触发 ensureEpgTimelineRowsLoaded 按需填充。此前一次性为全部频道解析/过滤 EPG，
    // 频道多时切 tab/开面板明显卡顿；行骨架本身可即时渲染（台标/频道名不依赖 EPG）。
    epgTimelineGeneration++
    epgTimelinePendingRows.clear()
    _epgTimelineLoading.value = false
    _epgTimelineRows.value = selectedChannels.map { channel ->
        EpgTimelineRow(
            channelIdx = channels.indexOf(channel),
            channelName = channel.name,
            programs = emptyList(),
            programsLoaded = false
        )
    }
    _epgTimelineStatus.value = "${selectedChannels.size} 频道 · 节目滚动加载"
}

/**
 * EPG 时间线按行懒加载：填充 [fromRow, toRow] 可视窗口内未加载的节目数据。
 * 由 TimelineGrid 可视行窗口变化时调用；命中 epgCache 直接复用，
 * 未命中走 repository.getEpg（与 preloadEpgForAllChannels 共用缓存）。
 */
internal fun AppViewModel.ensureEpgTimelineRowsLoaded(fromRow: Int, toRow: Int) {
    val rows = _epgTimelineRows.value
    if (rows.isEmpty() || fromRow > toRow) return
    val upper = toRow.coerceAtMost(rows.size - 1)
    val targets = (fromRow.coerceAtLeast(0)..upper).filter { i ->
        !rows[i].programsLoaded && i !in epgTimelinePendingRows
    }
    if (targets.isEmpty()) return
    synchronized(epgTimelinePendingRows) { epgTimelinePendingRows.addAll(targets) }
    val gen = epgTimelineGeneration

    viewModelScope.launch {
        val channels = _channels.value
        // 选中日期的 [dayStartMs, dayEndMs) 时间范围（与行骨架同日）
        val cal = java.util.Calendar.getInstance().apply {
            add(java.util.Calendar.DAY_OF_MONTH, _epgTimelineDateOffset.value)
            set(java.util.Calendar.HOUR_OF_DAY, 0)
            set(java.util.Calendar.MINUTE, 0)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }
        val dayStartMs = cal.timeInMillis
        val dayEndMs = dayStartMs + 24 * 60 * 60 * 1000L

        for (i in targets) {
            // 代次已变（用户切了范围/日期）：丢弃剩余加载，避免写入过期数据
            if (epgTimelineGeneration != gen) break
            val row = _epgTimelineRows.value.getOrNull(i) ?: continue
            if (row.programsLoaded) continue
            // 行内的 channelIdx 是 loadEpgTimeline 建骨架时的 _channels 快照索引；
            // 订阅源重载后 _channels 会被整体替换，索引可能漂移甚至越界。
            // 因此优先按索引取值并校验频道名，不一致时按频道名兜底解析，
            // 否则 channel 为 null 会被当成"无节目"永久标记已加载（时间线整块空白）。
            // 兜底只在名称唯一时生效：同一频道多路流（同名不同地址）时
            // firstOrNull 会把另一路流的节目挂到本行上。
            val channel = channels.getOrNull(row.channelIdx)
                ?.takeIf { it.name == row.channelName }
                ?: channels.filter { it.name == row.channelName }
                    .takeIf { it.size == 1 }?.first()
            if (channel == null) {
                // 频道确实已不存在（源被删除）：只解除 pending，不标记已加载，
                // 等 loadChannels 重建行骨架后再重新请求
                synchronized(epgTimelinePendingRows) { epgTimelinePendingRows.remove(i) }
                continue
            }
            val cacheIdx = channels.indexOf(channel)
            // 区分"桥接失败"与"确实无节目"：原来用 getOrDefault 会把超时/异常
            // 当成空列表并置 programsLoaded=true，之后可视窗口不再重试 → 永久空白。
            var programs: List<IptvEpgProgram>? = null
            var attempt = 0
            while (programs == null && attempt < 3) {
                if (epgTimelineGeneration != gen) return@launch
                if (attempt > 0) delay(1500L)
                attempt++
                programs = withContext(Dispatchers.IO) {
                    epgCache[cacheIdx] ?: run {
                        repository.getEpg(
                            channelName = channel.name,
                            tvgId = channel.tvgId,
                            tvgName = channel.tvgName,
                            commaName = channel.name
                        ).getOrNull()?.programmes?.also {
                            if (it.isNotEmpty()) epgCache[cacheIdx] = it
                        }
                    }
                }
            }
            if (programs == null) {
                // 重试仍有界失败（EPG 尚未解析完成/桥接超时）：解除 pending 但不标记已加载，
                // 可视窗口下次变化会重新请求，避免时间线被永久判死
                synchronized(epgTimelinePendingRows) { epgTimelinePendingRows.remove(i) }
                continue
            }
            if (epgTimelineGeneration != gen) break
            // 按日期过滤（与当天有交集的节目）
            val filtered = programs.filter { p ->
                val startMs = parseEpgTimeMs(p.start, p.startTs)
                val endMs = parseEpgTimeMs(p.end.ifEmpty { p.stop }, p.stopTs)
                if (startMs <= 0 || endMs <= 0) false
                else startMs < dayEndMs && endMs > dayStartMs
            }
            markEpgTimelineRowLoaded(i, row.channelIdx, row.channelName, filtered)
        }
    }
}

/** 将行 i 标记为已加载并写入节目数据（行若已被重建/填充则跳过写入，仅解除 pending 标记） */
private fun AppViewModel.markEpgTimelineRowLoaded(
    i: Int, channelIdx: Int, channelName: String, programs: List<IptvEpgProgram>
) {
    val cur = _epgTimelineRows.value
    val row = cur.getOrNull(i)
    if (row != null && !row.programsLoaded &&
        row.channelIdx == channelIdx && row.channelName == channelName
    ) {
        _epgTimelineRows.value = cur.toMutableList().also {
            it[i] = row.copy(programs = programs, programsLoaded = true)
        }
    }
    synchronized(epgTimelinePendingRows) { epgTimelinePendingRows.remove(i) }
}

internal fun AppViewModel.parseEpgTimeMs(iso: String, ts: Long): Long {
    if (ts > 0) return ts * 1000L
    if (iso.isEmpty()) return 0
    val patterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd HH:mm"
    )
    for (pattern in patterns) {
        try {
            return SimpleDateFormat(pattern, Locale.US).parse(iso)?.time ?: continue
        } catch (_: Exception) {
        }
    }
    return iso.toLongOrNull()?.let { if (it > 1_000_000_000_000L) it else it * 1000 } ?: 0
}

internal fun AppViewModel.toggleSearchPanel() {
    _searchPanelOpen.value = !_searchPanelOpen.value
    if (!_searchPanelOpen.value) {
        showControlsAutoHide()
        searchJob?.cancel()
    }
}

internal fun AppViewModel.setSearchScope(scope: SearchScope) {
    if (_searchScope.value == scope) return
    _searchScope.value = scope
}

internal fun AppViewModel.performSearch(query: String) {
    searchJob?.cancel()
    if (query.isBlank()) {
        _searchResults.value = emptyList()
        _searchLoading.value = false
        return
    }
    _searchLoading.value = true
    searchJob = viewModelScope.launch {
        delay(250)  // 防抖
        val q = query.trim()
        val scope = _searchScope.value
        val results = mutableListOf<SearchResult>()

        // 频道搜索（主线程快速过滤）
        if (scope == SearchScope.ALL || scope == SearchScope.CHANNELS) {
            val channels = _channels.value
            val seenUrls = HashSet<String>()
            channels.forEachIndexed { idx, ch ->
                if (ch.name.contains(q, ignoreCase = true) ||
                    ch.group.contains(q, ignoreCase = true) ||
                    ch.url.contains(q, ignoreCase = true)
                ) {
                    if (seenUrls.add(ch.url)) {  // 按 url 去重（与 PC 端一致）
                        results.add(SearchResult.ChannelResult(idx, ch))
                    }
                }
            }
        }

        // 节目搜索（异步遍历 epgCache）
        if (scope == SearchScope.ALL || scope == SearchScope.PROGRAMS) {
            val channels = _channels.value
            val maxResults = 200  // 与 PC 端 MAX_RESULTS 一致
            for ((channelIdx, programs) in epgCache) {
                if (results.size >= maxResults) break
                val channel = channels.getOrNull(channelIdx) ?: continue
                for (p in programs) {
                    if (results.size >= maxResults) break
                    if (p.title.contains(q, ignoreCase = true) ||
                        p.desc.contains(q, ignoreCase = true)
                    ) {
                        results.add(
                            SearchResult.ProgramResult(channelIdx, channel.name, p)
                        )
                    }
                }
            }
        }

        _searchResults.value = results
        _searchLoading.value = false
    }
}

internal fun AppViewModel.onSearchResultClick(result: SearchResult) {
    when (result) {
        is SearchResult.ChannelResult -> {
            playChannel(result.idx, silent = true)
            closeAllPanels()
        }
        is SearchResult.ProgramResult -> {
            playChannel(result.channelIdx, silent = true)
            // 判断是否为过去节目（与 PC 端 _on_epg_search_program_selected 对齐）
            val now = System.currentTimeMillis()
            val startMs = parseEpgTimeMs(result.program.start, result.program.startTs)
            val endMs = parseEpgTimeMs(
                result.program.end.ifEmpty { result.program.stop }, result.program.stopTs
            )
            if (startMs in 1 until now && endMs in 1 until now && endMs < now) {
                // 过去节目：延迟触发 catchup（等频道切换完成）
                viewModelScope.launch {
                    delay(800)
                    startCatchup(result.program)
                }
            }
            closeAllPanels()
        }
    }
}

internal fun AppViewModel.toggleStreamQualityPanel() {
    _streamQualityPanelOpen.value = !_streamQualityPanelOpen.value
    if (!_streamQualityPanelOpen.value) {
        showControlsAutoHide()
    }
}

internal fun AppViewModel.enterPip() {
    onEnterPip?.invoke() ?: showOsd("画中画", "当前环境不支持")
}

internal fun AppViewModel.setThemeMode(mode: String) {
    _themeMode.value = mode
    userPrefs.setThemeMode(mode)
    val name = when (mode) {
        "light" -> "浅色"
        "system" -> "跟随系统"
        else -> "深色"
    }
    showOsd("主题", name)
}

internal fun AppViewModel.toggleRecentPanel() {
    _recentPanelOpen.value = !_recentPanelOpen.value
    if (_recentPanelOpen.value) {
        _recentFiles.value = userPrefs.getRecentFiles()
    } else {
        showControlsAutoHide()
    }
}

internal fun AppViewModel.addRecentFile(uri: String, name: String, type: String) {
    userPrefs.addRecentFile(RecentEntry(uri, name, type, System.currentTimeMillis()))
    _recentFiles.value = userPrefs.getRecentFiles()
}

internal fun AppViewModel.removeRecentFile(uri: String) {
    userPrefs.removeRecentFile(uri)
    _recentFiles.value = userPrefs.getRecentFiles()
}

internal fun AppViewModel.clearRecentFiles() {
    userPrefs.clearRecentFiles()
    _recentFiles.value = emptyList()
    showOsd("最近打开", "已清空")
}

internal fun AppViewModel.playRecent(entry: RecentEntry) {
    closeAllPanels()
    when (entry.type) {
        "playlist" -> openPlaylistFromUri(entry.uri, entry.name)
        "url" -> {
            _currentIdx.value = -1
            _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
            currentPlaybackUrl = entry.uri
            currentPlaybackName = entry.name
            currentIsLocalFile = true
            mpv.playFile(entry.uri)
            showOsd("播放", entry.name)
        }
        "video" -> playLocalVideo(entry.uri)
    }
}

internal fun AppViewModel.saveAsM3u() {
    viewModelScope.launch {
        try {
            val channels = _channels.value
            if (channels.isEmpty()) {
                showOsd("另存为", "频道列表为空")
                return@launch
            }
            showOsd("另存为", "正在导出...")
            val m3uContent = buildM3uContent(channels)
            val written = withContext(Dispatchers.IO) { writeM3uToFile(m3uContent) }
            if (written) {
                showOsd("另存为", "已导出到下载目录")
            } else {
                showOsd("另存为", "导出失败")
            }
        } catch (e: Exception) {
            Log.e(AppViewModel.TAG, "saveAsM3u failed: ${e.message}", e)
            showOsd("另存为", "导出失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.buildM3uContent(channels: List<IptvChannel>): String {
    val sb = StringBuilder()
    sb.append("#EXTM3U\n")
    channels.forEach { ch ->
        val attrs = StringBuilder()
        if (ch.tvgId.isNotEmpty()) attrs.append(" tvg-id=\"${ch.tvgId}\"")
        if (ch.tvgName.isNotEmpty()) attrs.append(" tvg-name=\"${ch.tvgName}\"")
        if (ch.logo.isNotEmpty()) attrs.append(" tvg-logo=\"${ch.logo}\"")
        if (ch.group.isNotEmpty()) attrs.append(" group-title=\"${ch.group}\"")
        sb.append("#EXTINF:-1$attrs,${ch.name}\n")
        sb.append("${ch.url}\n")
    }
    return sb.toString()
}

internal fun AppViewModel.writeM3uToFile(content: String): Boolean {
    val now = java.text.SimpleDateFormat("yyyyMMdd_HHmmss", java.util.Locale.US).format(java.util.Date())
    val filename = "GuangYu_export_$now.m3u"
    return try {
        val app = getApplication<Application>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = app.contentResolver
            val values = android.content.ContentValues().apply {
                put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, filename)
                put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "audio/x-mpegurl")
                put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, android.os.Environment.DIRECTORY_DOWNLOADS)
            }
            val uri = resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return false
            resolver.openOutputStream(uri)?.use { it.write(content.toByteArray()) } ?: return false
        } else {
            @Suppress("DEPRECATION")
            val dir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
            if (!dir.exists()) dir.mkdirs()
            java.io.File(dir, filename).writeText(content)
        }
        true
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "writeM3uToFile failed", e)
        false
    }
}

internal fun AppViewModel.refreshUi() {
    if (_refreshing.value) return
    _refreshing.value = true
    viewModelScope.launch {
        showOsd("刷新", "正在重新加载...")
        try {
            loadChannels()
            fetchEpgForChannel(_currentIdx.value)
            showOsd("刷新", "已完成")
        } catch (e: Exception) {
            showOsd("刷新", "失败: ${e.message}")
        } finally {
            _refreshing.value = false
        }
    }
}

internal fun AppViewModel.cycleAspectRatio() {
    _aspectRatioIdx.value = (_aspectRatioIdx.value + 1) % aspectRatioModes.size
    val (label, value) = aspectRatioModes[_aspectRatioIdx.value]
    when (value) {
        null -> {
            // 默认：恢复 keepaspect + 取消 pan-scan
            mpv.setPropertyString("keepaspect", "yes")
            mpv.setPropertyString("video-unscaled", "no")
            mpv.setPropertyString("video-zoom", "0")
        }
        "stretch" -> {
            // 拉伸：关闭 keepaspect，填满画面
            mpv.setPropertyString("keepaspect", "no")
            mpv.setPropertyString("video-unscaled", "no")
            mpv.setPropertyString("video-zoom", "0")
        }
        else -> {
            // 指定比例：keepaspect + video-aspect-override
            mpv.setPropertyString("keepaspect", "yes")
            mpv.setPropertyString("video-aspect-override", value)
            mpv.setPropertyString("video-unscaled", "no")
            mpv.setPropertyString("video-zoom", "0")
        }
    }
    showOsd("画面比例", label)
}

internal fun AppViewModel.toggleClipExportPanel() {
    _clipExportPanelOpen.value = !_clipExportPanelOpen.value
    if (!_clipExportPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.exportClip(startTime: Double, duration: Double, format: String) {
    val url = currentPlaybackUrl.ifBlank { return }
    if (duration <= 0 || startTime < 0) {
        showOsd("切片导出", "参数无效")
        return
    }
    viewModelScope.launch {
        _clipExportStatus.value = "准备中..."
        _clipExportProgress.value = 0
        try {
            val app = getApplication<Application>()
            val now = java.text.SimpleDateFormat("yyyyMMdd_HHmmss", java.util.Locale.US).format(java.util.Date())
            val ext = when (format) { "gif" -> "gif"; "mp3" -> "mp3"; else -> "mp4" }
            val filename = "GuangYu_clip_$now.$ext"

            // 获取输出路径
            val outFile = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val resolver = app.contentResolver
                val mimeType = when (format) {
                    "gif" -> "image/gif"
                    "mp3" -> "audio/mpeg"
                    else -> "video/mp4"
                }
                val values = android.content.ContentValues().apply {
                    put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, filename)
                    put(android.provider.MediaStore.MediaColumns.MIME_TYPE, mimeType)
                    put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, android.os.Environment.DIRECTORY_DOWNLOADS)
                }
                val uri = resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                uri?.let { resolver.openOutputStream(it) }?.let { java.io.File.createTempFile("clip_tmp", ".$ext", app.cacheDir).also { tmp -> tmp.outputStream().use { _ -> } } }
            } else {
                @Suppress("DEPRECATION")
                val dir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
                if (!dir.exists()) dir.mkdirs()
                java.io.File(dir, filename)
            }

            if (outFile == null) {
                _clipExportStatus.value = "无法创建输出文件"
                return@launch
            }

            _clipExportStatus.value = "正在导出..."

            // 构建 ffmpeg 命令
            val ffmpegDir = java.io.File(app.applicationInfo.nativeLibraryDir, "ffmpeg")
            val ffmpegBin = if (ffmpegDir.exists()) ffmpegDir.absolutePath else "ffmpeg"

            val cmd = mutableListOf(ffmpegBin, "-y")
            cmd.addAll(listOf("-ss", startTime.toString()))
            cmd.addAll(listOf("-i", url))
            cmd.addAll(listOf("-t", duration.toString()))

            when (format) {
                "gif" -> {
                    cmd.addAll(listOf("-vf", "fps=10,scale=480:-1:flags=lanczos"))
                    cmd.addAll(listOf("-loop", "0"))
                }
                "mp3" -> {
                    cmd.addAll(listOf("-vn", "-acodec", "libmp3lame", "-q:a", "2"))
                }
                else -> {
                    cmd.addAll(listOf("-c", "copy", "-avoid_negative_ts", "make_zero"))
                }
            }
            cmd.add(outFile.absolutePath)

            val process = ProcessBuilder(cmd).redirectErrorStream(true).start()
            val reader = java.io.BufferedReader(java.io.InputStreamReader(process.inputStream))
            var line: String?
            var progress = 0
            while (reader.readLine().also { line = it } != null) {
                Log.d(AppViewModel.TAG, "ffmpeg: $line")
                progress = (progress + 5) % 100
                _clipExportProgress.value = progress
            }
            val exitCode = process.waitFor()
            if (exitCode == 0) {
                _clipExportProgress.value = 100
                _clipExportStatus.value = "导出成功: $filename"
                showOsd("切片导出", "已导出到下载目录")
            } else {
                _clipExportStatus.value = "导出失败 (exit=$exitCode)"
                showOsd("切片导出", "导出失败")
            }
        } catch (e: Exception) {
            Log.e(AppViewModel.TAG, "exportClip failed", e)
            _clipExportStatus.value = "错误: ${e.message}"
            showOsd("切片导出", "错误: ${e.message}")
        }
    }
}

internal fun AppViewModel.toggleAudioVisualizer() {
    _audioVisualizerOpen.value = !_audioVisualizerOpen.value
    if (!_audioVisualizerOpen.value) {
        stopSpectrumSampling()
        showControlsAutoHide()
    }
    // 权限请求与采样启动由 AudioVisualizerPanel 在组合时处理
}

internal fun AppViewModel.startSpectrumSampling() {
    spectrumRefs++
    spectrumJob?.cancel()
    // 尝试用 Android Visualizer API 获取真实音频频谱
    var visualizerStarted = false
    try {
        visualizer?.release()
        // 获取当前播放器的音频会话 ID
        val audioSessionId = try {
            mpv.getAudioSessionId()
        } catch (_: Exception) { 0 }
        
        visualizer = android.media.audiofx.Visualizer(audioSessionId)
        visualizer?.captureSize = android.media.audiofx.Visualizer.getCaptureSizeRange()[1]
        visualizer?.setDataCaptureListener(object : android.media.audiofx.Visualizer.OnDataCaptureListener {
            override fun onWaveFormDataCapture(v: android.media.audiofx.Visualizer?, waveform: ByteArray?, samplingRate: Int) {
                if (waveform == null) return
                // 波形数据不用做频谱，FFT 更适合。这里不处理。
            }
            override fun onFftDataCapture(v: android.media.audiofx.Visualizer?, fft: ByteArray?, samplingRate: Int) {
                if (fft == null) return
                val bands = AppViewModel.AUDIO_SPECTRUM_BANDS
                val spectrum = FloatArray(bands) { 0f }
                val n = fft.size / 2  // FFT bin 数量（不含 DC）
                // bin 0 为 DC 分量（无意义），从 bin 1 开始。
                // 几何（对数）分布：band i 覆盖 [lo, hi)，并 coerceAtLeast(lo+1)
                // 保证每个频段至少 1 个 bin——旧公式 pow(n, i/bands)+1 在低频段
                // 会出现 hi<=lo 的空区间，导致左侧低频柱恒为零
                val minBin = 1
                val maxBin = n - 1
                for (i in 0 until bands) {
                    val lo = minBin + Math.floor(Math.pow((maxBin - minBin).toDouble(), i.toDouble() / bands)).toInt()
                    val hi = (minBin + Math.floor(Math.pow((maxBin - minBin).toDouble(), (i + 1).toDouble() / bands)))
                        .toInt().coerceAtLeast(lo + 1).coerceAtMost(maxBin + 1)
                    var maxMag = 0f
                    for (j in lo until hi) {
                        val idx = j * 2
                        if (idx + 1 < fft.size) {
                            val re = fft[idx].toFloat()
                            val im = fft[idx + 1].toFloat()
                            val mag = kotlin.math.sqrt(re * re + im * im)
                            if (mag > maxMag) maxMag = mag
                        }
                    }
                    // 对数缩放映射到 0~1（FFT 幅值实际峰值量级约几千）
                    val normalized = if (maxMag > 0.1f) {
                        (kotlin.math.log10(maxMag + 1) / kotlin.math.log10(4000f)).coerceIn(0f, 1f)
                    } else 0f
                    spectrum[i] = normalized
                }
                // 空闲停绘：有音频能量时立即苏醒；空闲期间不再推送新帧（避免 20Hz 重组/重绘）
                var maxAmp = 0f
                for (a in spectrum) if (a > maxAmp) maxAmp = a
                if (maxAmp > AppViewModel.AUDIO_ACTIVE_THRESHOLD) {
                    lastAudioAt = android.os.SystemClock.elapsedRealtime()
                    if (_idle.value) {
                        _idle.value = false
                        Log.i(AppViewModel.TAG, "[IDLE] exit reason=audio droppedFrames=${spectrumFramesDropped.get()}")
                    }
                }
                if (_idle.value) {
                    spectrumFramesDropped.incrementAndGet()
                    return
                }
                _audioSpectrum.value = spectrum
            }
        }, android.media.audiofx.Visualizer.getMaxCaptureRate(), false, true)
        // 只用 FFT 数据（waveform=false, fft=true），最大采样率实现 60fps
        visualizer?.enabled = true
        visualizerStarted = true
        Log.i(AppViewModel.TAG, "Visualizer started for real-time spectrum")
    } catch (e: Exception) {
        Log.w(AppViewModel.TAG, "Visualizer not available: ${e.message}, using MPV peak level")
        visualizerStarted = false
    }
    
    if (!visualizerStarted) {
        // Visualizer 不可用（缺 RECORD_AUDIO 权限/音频接口异常）：给出明确提示。
        // 绝不提供模拟数据——假频谱会误导用户以为听到了真实声音
        _audioSpectrum.value = FloatArray(AppViewModel.AUDIO_SPECTRUM_BANDS) { 0f }
        _audioSpectrumError.value = "无法获取实时音频数据\n系统 Visualizer 接口不可用（需要麦克风权限）"
        Log.w(AppViewModel.TAG, "Visualizer unavailable, showing error state")
    } else {
        _audioSpectrumError.value = ""
    }
}

