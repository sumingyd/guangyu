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

internal fun AppViewModel.moveMultiViewFocus(direction: Int): Boolean {
    val state = _multiViewState.value
    if (!state.active) return false
    val current = state.focusedIndex
    val newIdx = when (state.layout) {
        MultiViewLayout.DUAL -> when (direction) {
            0, 2 -> if (current == 0) 1 else 0  // 左右切换
            else -> return false  // 双画面不支持上下
        }
        MultiViewLayout.QUAD -> {
            // 2x2 网格：0 1
            //          2 3
            val row = current / 2
            val col = current % 2
            when (direction) {
                0 -> if (col == 0) return false else current - 1  // 左
                1 -> if (row == 0) return false else current - 2  // 上
                2 -> if (col == 1) return false else current + 1  // 右
                3 -> if (row == 1) return false else current + 2  // 下
                else -> return false
            }
        }
        MultiViewLayout.NINE -> {
            // 3x3 网格：0 1 2
            //          3 4 5
            //          6 7 8
            val cols = 3
            val row = current / cols
            val col = current % cols
            when (direction) {
                0 -> if (col == 0) return false else current - 1  // 左
                1 -> if (row == 0) return false else current - cols  // 上
                2 -> if (col == cols - 1) return false else current + 1  // 右
                3 -> if (row == cols - 1) return false else current + cols  // 下
                else -> return false
            }
        }
        MultiViewLayout.SINGLE -> return false
    }
    if (newIdx !in state.viewports.indices) return false
    setFocusedViewport(newIdx)
    return true
}

internal fun AppViewModel.toggleShuffleMode(): Boolean {
    val newValue = !_shuffleMode.value
    _shuffleMode.value = newValue
    shuffleHistory.clear()
    shuffleBackStack.clear()
    showOsd(if (newValue) "随机播放：开" else "随机播放：关")
    return newValue
}

internal fun AppViewModel.prevChannel() {
    val cur = _currentIdx.value
    val all = _channels.value
    // 停止播放后 _currentIdx=-1：此时播放页只剩黑底，方向键不能变成“无响应”，
    // 直接起播最后一个频道（有频道时），让用户能靠遥控器回到播放状态
    if (cur < 0) {
        if (all.isNotEmpty()) playChannelDebounced(all.lastIndex)
        return
    }
    if (_shuffleMode.value && shuffleBackStack.isNotEmpty()) {
        cur.let { shuffleHistory.add(it) }
        val prev = shuffleBackStack.removeAt(shuffleBackStack.lastIndex)
        playChannelDebounced(prev)
        return
    }
    val channels = _channels.value
    if (channels.isEmpty()) return
    if (channels.size <= 1) return
    // 触屏（手机/车机）：到第一条就停住，不做首尾回绕 —— 回绕会让右侧频道列表
    // 从顶部瞬移到底部，用户分不清列表的头和尾；TV 遥控器保留回绕方便连续换台。
    val wrap = uiMode.value.isTV
    val next = when {
        cur > 0 -> cur - 1
        wrap -> channels.lastIndex
        else -> cur
    }
    if (next != cur && next >= 0 && next < channels.size) playChannelDebounced(next)
}

internal fun AppViewModel.nextChannel() {
    val cur = _currentIdx.value
    val all = _channels.value
    // 同上：未选台（停止后 idx=-1）时按“下一个”起播第一个频道，避免黑屏下按键看似失效
    if (cur < 0) {
        if (all.isNotEmpty()) playChannelDebounced(0)
        return
    }
    if (_shuffleMode.value) {
        val next = pickRandomChannelIdx(cur)
        if (next >= 0 && next != cur) {
            shuffleBackStack.add(cur)
            if (shuffleBackStack.size > shuffleHistoryMax) {
                shuffleBackStack.removeAt(0)
            }
        }
        if (next in _channels.value.indices) playChannelDebounced(next)
        return
    }
    val next = when {
        cur < _channels.value.lastIndex -> cur + 1
        // 同 prevChannel：只有 TV 遥控器保留首尾回绕
        uiMode.value.isTV -> 0
        else -> cur
    }
    if (next != cur && next in _channels.value.indices) playChannelDebounced(next)
}

internal fun AppViewModel.playChannelDebounced(idx: Int) {
    val channel = _channels.value.getOrNull(idx) ?: return
    _currentIdx.value = idx
    _channelDisplayInfo.value = ChannelDisplayInfo(
        name = channel.name, logo = channel.logo, group = channel.group, idx = idx,
        isLocal = channel.source.isEmpty() || ProgressHelper.isLocalFile(channel.url)
    )
    if (uiMode.value.isTV) {
        playChannel(idx, silent = true)
        showControlsAutoHide()
        return
    }
    playChannelDebounceJob?.cancel()
    playChannelDebounceJob = viewModelScope.launch {
        delay(250)
        playChannel(idx, silent = true)
        showOsd(channel.name, channel.group)
    }
}

internal fun AppViewModel.pickRandomChannelIdx(currentIdx: Int): Int {
    // 优先从当前过滤后的可见频道中随机（与用户视角一致）
    val visibleIdxList = getFilteredChannels().map { it.second }.distinct()
    val total = visibleIdxList.size
    if (total <= 1) return currentIdx

    // 清理过长的历史（保留最近一半）
    if (shuffleHistory.size > shuffleHistoryMax) {
        repeat(shuffleHistory.size - shuffleHistoryMax / 2) { shuffleHistory.removeAt(0) }
    }

    // 候选 = 可见频道中排除当前和近期历史的
    var candidates = visibleIdxList.filter { it != currentIdx && it !in shuffleHistory }
    if (candidates.isEmpty()) {
        candidates = visibleIdxList.filter { it != currentIdx }
    }
    if (candidates.isEmpty()) return currentIdx

    val picked = candidates.random()
    shuffleHistory.add(picked)
    return picked
}

internal fun AppViewModel.stopPlay() {
    Log.i(AppViewModel.TAG, "stopPlay")
    fccService.onStop()
    // 停止超时换源定时器
    timeoutSwitchJob?.cancel()
    timeoutSwitchJob = null
    // 停止文件加载错误自动换源
    fileErrorSwitchJob?.cancel()
    fileErrorSwitchJob = null
    // 停止重连定时器
    reconnectJob?.cancel()
    reconnectJob = null
    // 重置连续超时计数器
    consecutiveTimeoutCount = 0
    // 清除当前播放 URL，防止 mpv.stop() 触发的 onFileError 回调自动重连
    currentPlaybackUrl = ""
    // 先置 IDLE 再 stop：确保 mpv.stop() 触发的任何同步事件都能看到已停止状态
    _playbackState.value = PlaybackState(mode = PlayMode.IDLE)
    mpv.stop()
    _currentIdx.value = -1
    _currentEpg.value = emptyList()
    showOsd("已停止")
}

internal fun AppViewModel.startCatchup(program: IptvEpgProgram, channelIdx: Int = Int.MIN_VALUE) {
    // channelIdx：节目单显示的频道与当前播放频道不一致时（统一面板 EPG 列回退/聚焦跟随），
    // 由调用方显式指定回看目标频道；默认仍取当前播放频道
    val idx = if (channelIdx != Int.MIN_VALUE) channelIdx else _currentIdx.value
    if (idx < 0) {
        showOsd("回看", "无当前频道")
        return
    }
    val channel = _channels.value.getOrNull(idx) ?: return
    // 指定频道进入回看时同步 currentIdx（EPG/OSD/切台基准与回看频道保持一致）
    if (idx != _currentIdx.value) _currentIdx.value = idx

    // 检查频道是否支持回看
    if (!CatchupHelper.isCatchupEnabled(channel)) {
        showOsd("回看", "该频道不支持回看")
        return
    }

    // 提取节目时间戳
    val (startMs, endMs) = CatchupHelper.extractProgramTimestamps(program)
    if (startMs <= 0 || endMs <= startMs) {
        showOsd("回看", "节目时间无效")
        return
    }

    // 构建 catchup URL
    val catchupUrl = CatchupHelper.buildCatchupUrl(channel, startMs, endMs)
    if (catchupUrl.isNullOrEmpty()) {
        showOsd("回看", "无法构建回看 URL")
        return
    }

    // 进入 catchup 状态
    val catchupProgram = CatchupProgram(program, startMs, endMs)
    _playbackState.value = _playbackState.value.enterCatchup(channel, catchupProgram, PlayMode.CATCHUP)

    // 关键：取消所有延迟换源/超时定时器，避免 catchup URL 加载期间被干扰
    // 1. fileErrorSwitchJob：onFileError 延迟换源（已在 onFileError 中通过 isCatchup 判断跳过，双保险）
    fileErrorSwitchJob?.cancel()
    fileErrorSwitchJob = null
    // 2. timeoutSwitchJob：直播频道的超时换源定时器仍在运行！
    //    场景：用户在直播频道上点击过去节目 → startCatchup 播放 catchup URL →
    //    catchup URL 加载需要时间 → 直播频道的 timeoutSwitchJob 到期 →
    //    检查 fileLoaded=false（catchup 还没加载完）→ 调用 nextChannel() 切到下一个直播频道。
    //    这就是"点击回看后视频断了一下又接着直播播放"的根因。
    timeoutSwitchJob?.cancel()
    timeoutSwitchJob = null

    // 回看是单播点播流：向旧 FCC 端点补发 LEAVE，避免代理继续推送直播组播
    fccService.onStop()

    // 播放 catchup URL
    mpv.playFile(catchupUrl)

    // 显示 OSD（不调用 closeAllPanels，避免干扰播放器模式下的动态内容区域）
    showOsd("回看", program.title.ifEmpty { channel.name })

    Log.i(AppViewModel.TAG, "startCatchup: ${program.title} ($startMs-$endMs) → $catchupUrl")
}

internal fun AppViewModel.startLiveTimeshift(sliderSec: Double): Boolean {
    val idx = _currentIdx.value
    if (idx < 0) return false
    val channel = _channels.value.getOrNull(idx) ?: return false

    // 检查频道是否支持回看（时移需要 catchup_source）
    if (!CatchupHelper.isCatchupEnabled(channel)) {
        showOsd("时移", "该频道不支持时移")
        return false
    }

    // 计算目标墙钟时间
    val now = System.currentTimeMillis()
    val currentProgram = ProgressHelper.findCurrentProgram(_currentEpg.value, now)
    val hasEpg = currentProgram != null
    val programStartMs = if (currentProgram != null) {
        CatchupHelper.extractProgramTimestamps(currentProgram).first
    } else 0L
    val hourStartMs = CatchupHelper.currentHourStartMs()

    val targetWallclock = CatchupHelper.computeTimeshiftTarget(
        programStartMs, hourStartMs, sliderSec, hasEpg
    )
    if (targetWallclock <= 0) {
        showOsd("时移", "目标时间无效")
        return false
    }

    // 计算 endMs（节目结束 or now+30min）
    val endMs = if (currentProgram != null) {
        val (_, pEnd) = CatchupHelper.extractProgramTimestamps(currentProgram)
        if (pEnd > now) pEnd else now + 30 * 60 * 1000L
    } else {
        hourStartMs + 3600_000L
    }

    // 构建 catchup URL
    val catchupUrl = CatchupHelper.buildCatchupUrl(channel, targetWallclock, endMs)
    if (catchupUrl.isNullOrEmpty()) {
        showOsd("时移", "无法构建时移 URL")
        return false
    }

    // 进入 timeshift 状态
    val offsetSec = ((now - targetWallclock) / 1000).coerceAtLeast(0L)
    val catchupProgram = if (currentProgram != null) {
        CatchupProgram(currentProgram, programStartMs.ifElse(hourStartMs) { programStartMs > 0 }, endMs)
    } else {
        // 无 EPG 时构造一个占位 program
        val placeholder = IptvEpgProgram(title = channel.name, start = "", stop = "")
        CatchupProgram(placeholder, hourStartMs, endMs)
    }
    _playbackState.value = _playbackState.value.enterCatchup(channel, catchupProgram, PlayMode.TIMESHIFT)
        .copy(liveTimeshiftSeconds = offsetSec)

    // 取消所有延迟换源/超时定时器（与 startCatchup 一致）
    fileErrorSwitchJob?.cancel()
    fileErrorSwitchJob = null
    timeoutSwitchJob?.cancel()
    timeoutSwitchJob = null

    // 时移同样是单播点播流：向旧 FCC 端点补发 LEAVE
    fccService.onStop()

    // 播放 timeshift URL
    mpv.playFile(catchupUrl)

    // 显示 OSD
    showOsd("时移", "落后 ${offsetSec} 秒")

    Log.i(AppViewModel.TAG, "startLiveTimeshift: offset=${offsetSec}s target=$targetWallclock → $catchupUrl")
    return true
}

internal fun AppViewModel.exitCatchup() {
    val state = _playbackState.value
    if (!state.mode.isCatchupOrTimeshift) {
        showOsd("回看", "未在回看模式")
        return
    }

    // 清除回看状态（退出后是直播，与 PC 端 exit_catchup 一致）
    _playbackState.value = state.clearCatchup(PlayMode.LIVE)

    // 恢复原始频道直播：走完整的 playChannel 流程
    val idx = _currentIdx.value
    if (idx >= 0) {
        // 先停止 mpv 当前播放（回看 URL 可能已出错/EOF，不 stop 直接 loadfile 可能无法恢复）
        // 与项目约束一致："切换频道前必须先停止 mpv，否则资源泄漏/黑屏"
        mpv.stop()
        playChannel(idx, silent = true)
        showOsd("回看", "已退出，恢复直播")
    } else {
        showOsd("回看", "已退出")
    }
}

internal fun AppViewModel.seekProgress(percent: Float) {
    val state = _playbackState.value
    val channel = currentChannel.value

    when (state.mode) {
        PlayMode.CATCHUP -> {
            // 回看模式：基于 mpv timePos 直接 seek
            val program = state.catchupProgram ?: return
            val targetSec = (percent / 100f * program.durationSec).toDouble()
            mpv.seekAbsolute(targetSec)
        }
        PlayMode.TIMESHIFT, PlayMode.LIVE -> {
            // 无频道（本地视频/网络流）：VOD seek，直接按 duration 比例 seek
            if (channel == null) {
                val duration = mpv.duration.value
                if (duration > 0) {
                    mpv.seekAbsolute((percent / 100f * duration).toDouble())
                }
                return
            }
            // 时移/直播模式：根据缓冲判断走 mpv seek 还是重建 URL
            handleLiveSeek(percent, state, channel)
        }
        PlayMode.IDLE -> { /* 无播放，忽略 */ }
    }
}

internal fun AppViewModel.handleLiveSeek(percent: Float, state: PlaybackState, channel: IptvChannel) {
    val now = System.currentTimeMillis()
    val currentProgram = ProgressHelper.findCurrentProgram(_currentEpg.value, now)
    val hasEpg = currentProgram != null

    // 计算 targetWallclock
    val (startMs, endMs) = if (currentProgram != null) {
        CatchupHelper.extractProgramTimestamps(currentProgram)
    } else {
        val hourStart = CatchupHelper.currentHourStartMs()
        hourStart to hourStart + 3600_000L
    }
    if (startMs <= 0 || endMs <= startMs) return

    val totalSec = ((endMs - startMs) / 1000).coerceAtLeast(1L)
    val sliderSec = (percent / 100f * totalSec).toLong()
    val targetWallclock = (startMs + sliderSec * 1000).coerceAtMost(now - 2_000L)
    val offsetSec = ((now - targetWallclock) / 1000).coerceAtLeast(0L)

    // 缓冲边界判断
    val mpvTimePos = mpv.timePos.value
    val cacheDuration = mpv.getPropertyDouble("demuxer-cache-duration") ?: 0.0
    val cacheTime = mpv.getPropertyDouble("demuxer-cache-time") ?: 0.0
    val (targetPos, inBuffer) = ProgressHelper.computeSeekTarget(offsetSec, mpvTimePos, cacheDuration, cacheTime)

    if (inBuffer && offsetSec <= 2) {
        // 目标在缓冲区内且接近直播：直接 mpv seek，清空 timeshift
        mpv.seekAbsolute(targetPos)
        if (state.mode.isTimeshift) {
            _playbackState.value = state.copy(mode = PlayMode.LIVE, liveTimeshiftSeconds = 0L)
        }
    } else if (inBuffer) {
        // 目标在缓冲区内但有时移偏移：mpv seek + 设置 timeshift 状态
        mpv.seekAbsolute(targetPos)
        if (!state.mode.isTimeshift) {
            _playbackState.value = state.switchToTimeshift(offsetSec)
        } else {
            _playbackState.value = state.copy(liveTimeshiftSeconds = offsetSec)
        }
        showOsd("时移", "落后 ${offsetSec} 秒")
    } else {
        // 目标超出缓冲区：需要重建 catchup URL
        if (!CatchupHelper.isCatchupEnabled(channel)) {
            showOsd("提示", "该频道不支持时移回看")
            return
        }

        // URL 重建冷却检查（与 PC 端 catchup_controller.seek_catchup 对齐）
        val nowSec = System.nanoTime() / 1_000_000_000.0
        if (urlRebuildPending) {
            val elapsed = nowSec - lastUrlRebuildTime
            if (elapsed < urlRebuildCooldown) {
                // 冷却中：保存待执行的 seek 百分比，等冷却结束后执行
                pendingSeekAfterCooldown = percent.toDouble()
                Log.i(AppViewModel.TAG, "时移seek延迟: URL重建后冷却中(${"%.1f".format(elapsed)}s/${urlRebuildCooldown}s)")
                ensureCooldownTimer()
                showOsd("时移", "冷却中，请稍候...")
                return
            } else {
                urlRebuildPending = false
            }
        }

        startLiveTimeshift(sliderSec.toDouble())

        // 记录重建时间，设置 pending 标记
        lastUrlRebuildTime = System.nanoTime() / 1_000_000_000.0
        urlRebuildPending = true
        pendingSeekAfterCooldown = null
        cooldownJob?.cancel()
        cooldownJob = null
    }
}

internal fun AppViewModel.ensureCooldownTimer() {
    if (cooldownJob?.isActive == true) return
    val nowSec = System.nanoTime() / 1_000_000_000.0
    val remaining = ((urlRebuildCooldown - (nowSec - lastUrlRebuildTime)) * 1000).toLong().coerceAtLeast(200)
    cooldownJob = viewModelScope.launch {
        delay(remaining)
        cooldownJob = null
        val pos = pendingSeekAfterCooldown
        pendingSeekAfterCooldown = null
        if (pos != null) {
            val elapsed = System.nanoTime() / 1_000_000_000.0 - lastUrlRebuildTime
            if (elapsed < urlRebuildCooldown) {
                ensureCooldownTimer()
                return@launch
            }
            Log.i(AppViewModel.TAG, "冷却期结束，执行延迟的时移seek: percent=${"%.1f".format(pos)}")
            seekProgress(pos.toFloat())
        }
    }
}

internal fun AppViewModel.continueTimeshift() {
    val state = _playbackState.value
    if (!state.mode.isTimeshift) {
        Log.d(AppViewModel.TAG, "continueTimeshift: not in timeshift mode, skipping")
        return
    }
    val program = state.catchupProgram ?: run {
        Log.w(AppViewModel.TAG, "时移续播失败: 缺少节目信息")
        return
    }
    val channel = state.originalChannel ?: currentChannel.value ?: run {
        Log.w(AppViewModel.TAG, "时移续播失败: 缺少频道信息")
        return
    }

    val programStartMs = program.startMs
    val programEndMs = program.endMs
    val now = System.currentTimeMillis()

    // 计算新的起始时间：基于上次的 catchupStartProgressSec + 实际播放时长
    val elapsedSinceStart = state.catchupStartProgressSec
    val newStartMs = if (elapsedSinceStart > 0) {
        val elapsedReal = now - state.catchupStartMs
        programStartMs + (elapsedSinceStart * 1000).toLong() + elapsedReal
    } else {
        now - 5_000L
    }

    var adjustedStartMs = newStartMs.coerceAtLeast(programStartMs)
    if (adjustedStartMs >= now) {
        adjustedStartMs = now - 5_000L
    }

    val endMs = if (programEndMs > now) programEndMs else now + 30 * 60 * 1000L

    val catchupUrl = CatchupHelper.buildCatchupUrl(channel, adjustedStartMs, endMs)
    if (catchupUrl.isNullOrEmpty()) {
        Log.w(AppViewModel.TAG, "时移续播: 无法构建 URL")
        showOsd("时移", "续播失败")
        return
    }

    Log.i(AppViewModel.TAG, "时移续播 -> new_start=$adjustedStartMs, end=$endMs, url=$catchupUrl")

    // 更新冷却状态
    lastUrlRebuildTime = System.nanoTime() / 1_000_000_000.0
    urlRebuildPending = true

    // 更新 playback state
    _playbackState.value = state.copy(
        catchupStartMs = System.currentTimeMillis(),
        catchupStartProgressSec = 0.0
    )

    mpv.playFile(catchupUrl)
}

internal fun AppViewModel.seekLiveRelative(seconds: Double) {
    val state = _playbackState.value
    val mpvTimePos = mpv.timePos.value
    val cacheTime = mpv.getPropertyDouble("demuxer-cache-time") ?: 0.0

    // 缓冲区信息不可用（刚切换频道，缓冲未建立）
    if (mpvTimePos <= 0 || cacheTime <= 0) {
        if (seconds < 0) {
            showOsd("提示", "缓冲中，请稍候")
        }
        return
    }

    val currentOffset = (cacheTime - mpvTimePos).coerceAtLeast(0.0)

    if (seconds < 0) {
        // 快退：seek 后偏移增大
        mpv.seekRelative(seconds)
        val newOffset = (currentOffset + (-seconds)).toLong()
        if (newOffset > 2) {
            if (!state.mode.isTimeshift) {
                _playbackState.value = state.switchToTimeshift(newOffset)
            } else {
                _playbackState.value = state.copy(liveTimeshiftSeconds = newOffset)
            }
            showOsd("时移", "落后 ${newOffset} 秒")
        }
    } else {
        // 快进
        if (state.mode.isTimeshift) {
            val newOffset = (currentOffset - seconds).toLong().coerceAtLeast(0L)
            if (newOffset <= 2) {
                // 追赶到直播前沿：seek 到前沿并切回 LIVE
                mpv.seekAbsolute(cacheTime - 1)
                _playbackState.value = state.copy(mode = PlayMode.LIVE, liveTimeshiftSeconds = 0L)
                showOsd("直播", "已恢复实时播放")
            } else {
                mpv.seekRelative(seconds)
                _playbackState.value = state.copy(liveTimeshiftSeconds = newOffset)
                showOsd("时移", "落后 ${newOffset} 秒")
            }
        } else {
            // 已在直播前沿，无法快进
            showOsd("提示", "已是最新直播")
        }
    }
}

internal fun AppViewModel.trimEpgNearNow(programs: List<IptvEpgProgram>): List<IptvEpgProgram> {
    if (programs.size <= 30) return programs
    val now = System.currentTimeMillis()
    val pastMs = 2 * 3600_000L
    val futureMs = 12 * 3600_000L
    val hasTimestamps = programs.any { it.startTs > 0 || it.stopTs > 0 }
    val firstWithTs = programs.firstOrNull { it.startTs > 0 }
    val tsScale = if (firstWithTs != null && firstWithTs.startTs > 1_000_000_000_000L) 1L else 1000L
    val trimmed = if (hasTimestamps) {
        programs.filter { p ->
            val start = if (p.startTs > 0) p.startTs * tsScale else 0L
            val stop = if (p.stopTs > 0) p.stopTs * tsScale else Long.MAX_VALUE
            stop > now - pastMs && start < now + futureMs
        }
    } else {
        val centerIdx = programs.indexOfFirst { p ->
            p.start.isNotEmpty() && p.stop.isNotEmpty()
        }.coerceAtLeast(0)
        val from = (centerIdx - 5).coerceAtLeast(0)
        val to = (centerIdx + 25).coerceAtMost(programs.size)
        programs.subList(from, to)
    }
    var result = if (trimmed.isNotEmpty()) trimmed else programs
    if (result.size > 50 && hasTimestamps) {
        val currentIdx = result.indexOfFirst { p ->
            val s = if (p.startTs > 0) p.startTs * tsScale else 0L
            val e = if (p.stopTs > 0) p.stopTs * tsScale else Long.MAX_VALUE
            s <= now && e > now
        }.coerceAtLeast(0)
        val from = (currentIdx - 5).coerceAtLeast(0)
        val to = (currentIdx + 45).coerceAtMost(result.size)
        result = result.subList(from, to)
    }
    Log.d(AppViewModel.TAG, "trimEpgNearNow: ${programs.size} -> ${result.size}")
    return result
}

internal fun AppViewModel.fetchEpgForCurrent() {
    val idx = _currentIdx.value
    if (idx < 0) {
        _currentEpg.value = emptyList()
        return
    }
    val channel = _channels.value.getOrNull(idx) ?: return

    // 优先用缓存（裁剪后给UI，缓存保留完整数据供EPG面板展开用）
    epgCache[idx]?.let { cached ->
        _currentEpg.value = trimEpgNearNow(cached)
        return
    }

    _epgLoading.value = true
    val baseName = channel.name
        .removeSuffix("-4K").removeSuffix("-HDR").removeSuffix("-8K")
        .removeSuffix(" 4K").removeSuffix(" HDR").removeSuffix(" 8K")
    viewModelScope.launch {
        val result = repository.getEpg(
            channelName = baseName,
            tvgId = channel.tvgId,
            tvgName = channel.tvgName,
            commaName = channel.name
        )
        result.fold(
            onSuccess = { epgList ->
                val programs = epgList.programmes
                if (programs.isEmpty()) {
                    // EPG 数据可能还在后台加载，3秒后重试一次
                    Log.w(AppViewModel.TAG, "fetchEpgForCurrent: empty programs, will retry in 3s")
                    delay(3000)
                    val retry = withContext(Dispatchers.IO) {
                        // 重试同样使用去后缀的 baseName，避免写错 keyed 缓存
                        repository.getEpg(baseName, channel.tvgId, channel.tvgName, channel.name)
                    }
                    val retryPrograms = retry.getOrNull()?.programmes ?: emptyList()
                    if (retryPrograms.isNotEmpty()) {
                        epgCache[idx] = retryPrograms
                        _epgCacheVersion.value++
                    }
                    _currentEpg.value = trimEpgNearNow(retryPrograms)
                    Log.i(AppViewModel.TAG, "fetchEpgForCurrent (retry): ${retryPrograms.size} programs for ${channel.name}")
                } else {
                    if (programs.isNotEmpty()) {
                        epgCache[idx] = programs
                        _epgCacheVersion.value++
                    }
                    _currentEpg.value = trimEpgNearNow(programs)
                    Log.i(AppViewModel.TAG, "fetchEpgForCurrent: ${programs.size} programs for ${channel.name}")
                }
            },
            onFailure = { e ->
                Log.w(AppViewModel.TAG, "fetchEpgForCurrent failed: ${e.message}")
                // EPG 服务器可能还没准备好，3秒后重试
                delay(3000)
                try {
                    val retry = withContext(Dispatchers.IO) {
                        repository.getEpg(channel.name, channel.tvgId, channel.tvgName, channel.name)
                    }
                    val retryPrograms = retry.getOrNull()?.programmes ?: emptyList()
                    if (retryPrograms.isNotEmpty()) {
                        epgCache[idx] = retryPrograms
                        _epgCacheVersion.value++
                    }
                    _currentEpg.value = trimEpgNearNow(retryPrograms)
                    Log.i(AppViewModel.TAG, "fetchEpgForCurrent (retry after fail): ${retryPrograms.size} programs for ${channel.name}")
                } catch (e2: Exception) {
                    _currentEpg.value = emptyList()
                }
            }
        )
        _epgLoading.value = false
    }
}

internal fun AppViewModel.getCurrentProgram(): IptvEpgProgram? {
    return ProgressHelper.findCurrentProgram(_currentEpg.value, System.currentTimeMillis())
}

internal fun AppViewModel.getFullEpgForCurrent(): List<IptvEpgProgram> {
    val idx = _currentIdx.value
    if (idx < 0) return emptyList()
    return epgCache[idx] ?: _currentEpg.value
}

internal fun AppViewModel.fetchEpgForChannel(idx: Int) {
    val channel = _channels.value.getOrNull(idx) ?: run {
        _focusedEpg.value = emptyList()
        return
    }
    // 优先用缓存（裁剪后给UI）
    epgCache[idx]?.let { cached ->
        _focusedEpg.value = trimEpgNearNow(cached)
        return
    }
    _focusedEpgLoading.value = true
    val baseName = channel.name
        .removeSuffix("-4K").removeSuffix("-HDR").removeSuffix("-8K")
        .removeSuffix(" 4K").removeSuffix(" HDR").removeSuffix(" 8K")
    viewModelScope.launch {
        val result = repository.getEpg(
            channelName = baseName,
            tvgId = channel.tvgId,
            tvgName = channel.tvgName,
            commaName = channel.name
        )
        result.fold(
            onSuccess = { epgList ->
                val programs = epgList.programmes
                if (programs.isNotEmpty()) {
                    epgCache[idx] = programs
                    _epgCacheVersion.value++
                    _focusedEpg.value = trimEpgNearNow(programs)
                    Log.i(AppViewModel.TAG, "fetchEpgForChannel: ${programs.size} programs for ${channel.name}")
                } else {
                    Log.w(AppViewModel.TAG, "fetchEpgForChannel: empty programs, will retry in 3s")
                    kotlinx.coroutines.delay(3000)
                    val retry = withContext(Dispatchers.IO) {
                        repository.getEpg(baseName, channel.tvgId, channel.tvgName, channel.name)
                    }
                    val retryPrograms = retry.getOrNull()?.programmes ?: emptyList()
                    if (retryPrograms.isNotEmpty()) {
                        epgCache[idx] = retryPrograms
                        _epgCacheVersion.value++
                    }
                    _focusedEpg.value = trimEpgNearNow(retryPrograms)
                    Log.i(AppViewModel.TAG, "fetchEpgForChannel (retry): ${retryPrograms.size} programs for ${channel.name}")
                }
            },
            onFailure = { e ->
                Log.w(AppViewModel.TAG, "fetchEpgForChannel failed: ${e.message}")
                _focusedEpg.value = emptyList()
            }
        )
        _focusedEpgLoading.value = false
    }
}

internal fun AppViewModel.preloadEpgForAllChannels() {
    val channels = _channels.value
    if (channels.isEmpty()) return
    val uncachedIdxs = channels.indices.filter { it !in epgCache }
    if (uncachedIdxs.isEmpty()) return
    Log.i(AppViewModel.TAG, "preloadEpgForAllChannels: ${uncachedIdxs.size} channels need EPG preload")
    viewModelScope.launch {
        // 分批并发，每批 5 个
        uncachedIdxs.chunked(5).forEach { batch ->
            batch.forEach { idx ->
                launch {
                    val channel = channels.getOrNull(idx) ?: return@launch
                    // 与 fetchEpgForChannel/fetchEpgForCurrent 一致：去掉画质后缀再匹配，
                    // 否则 "XXX-4K" 这类频道名匹配不到/错配到其他频道，
                    // 导致频道列表下方"当前节目名"与底栏节目名显示错乱
                    val baseName = channel.name
                        .removeSuffix("-4K").removeSuffix("-HDR").removeSuffix("-8K")
                        .removeSuffix(" 4K").removeSuffix(" HDR").removeSuffix(" 8K")
                    try {
                        val result = repository.getEpg(
                            channelName = baseName,
                            tvgId = channel.tvgId,
                            tvgName = channel.tvgName,
                            commaName = channel.name
                        )
                        result.fold(
                            onSuccess = { epgList ->
                                val programs = epgList.programmes
                                if (programs.isNotEmpty()) {
                                    epgCache[idx] = programs
                                    _epgCacheVersion.value++
                                    Log.d(AppViewModel.TAG, "preloadEpg: ${programs.size} programs for ${channel.name}")
                                }
                            },
                            onFailure = { /* 静默失败，不打扰用户 */ }
                        )
                    } catch (_: Throwable) {}
                }
            }
            // 等待当前批次完成
            kotlinx.coroutines.delay(500)
        }
    }
}

internal fun AppViewModel.showCurrentOsd() {
    // 如果 OSD 已开启且为持久模式，则关闭
    if (_osdPinned.value) {
        hideOsd()
        return
    }
    val channel = currentChannel.value
    if (channel != null) {
        val prog = getCurrentProgram()
        val subtitle = if (prog != null && prog.title.isNotEmpty()) prog.title else channel.group
        // 菜单触发的 OSD 设为持久模式（不自动隐藏，直至再次选中 OSD 关闭）
        _osdPinned.value = true
        _osd.value = OsdInfo(channel.name, subtitle)
        osdHideJob?.cancel()
    }
}

internal fun AppViewModel.computeProgress(): ProgressHelper.ProgressInfo {
    return ProgressHelper.computeProgress(
        state = _playbackState.value,
        channel = currentChannel.value,
        currentProgram = getCurrentProgram(),
        mpvTimePos = mpv.timePos.value,
        mpvDuration = mpv.duration.value,
    )
}

internal fun AppViewModel.toggleFavorite(): Boolean {
    val idx = _currentIdx.value
    if (idx < 0) return false
    val added = userPrefs.toggleFavorite(idx)
    // 双写 URL 版本：订阅重载后按 URL 重锚定，idx 漂移不会错位
    _channels.value.getOrNull(idx)?.let { userPrefs.toggleFavoriteUrl(it.url) }
    _favorites.value = userPrefs.getFavorites()
    showOsd(if (added) "已收藏" else "已取消收藏")
    return added
}

internal fun AppViewModel.addToQueue(idx: Int) {
    userPrefs.addToQueue(idx)
    // 双写 URL 版本（与收藏/历史同一重锚定机制）
    _channels.value.getOrNull(idx)?.let { userPrefs.addToQueueUrl(it.url) }
    _queue.value = userPrefs.getQueue()
    showOsd("已加入队列")
}

internal fun AppViewModel.removeFromQueue(idx: Int) {
    userPrefs.removeFromQueue(idx)
    _channels.value.getOrNull(idx)?.let { userPrefs.removeFromQueueUrl(it.url) }
    _queue.value = userPrefs.getQueue()
}

internal fun AppViewModel.clearHistory() {
    userPrefs.clearHistory()
    userPrefs.setHistoryUrls(emptyList())
    _history.value = emptyList()
    showOsd("历史已清空")
}

internal fun AppViewModel.clearQueue() {
    userPrefs.clearQueue()
    userPrefs.setQueueUrls(emptyList())
    _queue.value = emptyList()
    showOsd("队列已清空")
}

internal fun AppViewModel.showOsd(title: String, subtitle: String = "", extra: String = "") {
    _osd.value = OsdInfo(title, subtitle, extra)
    // 普通触发的 OSD 清除持久模式
    _osdPinned.value = false
    osdHideJob?.cancel()
    osdHideJob = viewModelScope.launch {
        delay(5_000L)
        _osd.value = null
    }
}

internal fun AppViewModel.hideOsd() {
    osdHideJob?.cancel()
    _osdPinned.value = false
    _osd.value = null
}

internal fun AppViewModel.toggleChannelsPanel() {
    _channelsPanelOpen.value = !_channelsPanelOpen.value
    // 关闭面板时自动显示控制层（避免面板关闭后控制层不显示）
    if (!_channelsPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleEpgPanel() {
    _epgPanelOpen.value = !_epgPanelOpen.value
    if (!_epgPanelOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.toggleMenuPanel() {
    _menuPanelOpen.value = !_menuPanelOpen.value
    if (!_menuPanelOpen.value) {
        // 菜单关闭时同步收起菜单内的底栏样式选择弹窗，避免下次打开菜单时残留
        _stylePickerOpen.value = false
        _stylePreview.value = null
        showControlsAutoHide()
    }
}

internal fun AppViewModel.toggleTvUnifiedPanel() {
    _tvUnifiedPanelOpen.value = !_tvUnifiedPanelOpen.value
    if (_tvUnifiedPanelOpen.value) {
        _channelsPanelOpen.value = false
        _epgPanelOpen.value = false
        _menuPanelOpen.value = false
    } else {
        showControlsAutoHide()
    }
}

internal fun AppViewModel.closeTvUnifiedPanel() {
    _tvUnifiedPanelOpen.value = false
}

internal fun AppViewModel.toggleControls() {
    if (_controlsVisible.value) hideControls() else showControls()
}

internal fun AppViewModel.resetAllPanelStates() {
    val wasPlayerSettingsOpen = _playerSettingsOpen.value
    androidx.compose.runtime.snapshots.Snapshot.withMutableSnapshot {
        _channelsPanelOpen.value = false
        _epgPanelOpen.value = false
        _menuPanelOpen.value = false
        _stylePickerOpen.value = false
        _stylePreview.value = null
        _tvUnifiedPanelOpen.value = false
        _fileBrowserOpen.value = false
        _sourceManagerOpen.value = false
        _sourceManagerFocusUrl.value = false
        _playerSettingsOpen.value = false
        _videoSettingsOpen.value = false
        _audioSettingsOpen.value = false
        _subtitleSettingsOpen.value = false
        _subtitleSearchOpen.value = false
        _playbackPanelOpen.value = false
        _screenshotPanelOpen.value = false
        _viewSettingsOpen.value = false
        _aboutPanelOpen.value = false
        _updateDialogOpen.value = false
        _exitConfirmOpen.value = false
        _dlnaPanelOpen.value = false
        _openUrlDialogOpen.value = false
        _mappingPanelOpen.value = false
        _avSyncPanelOpen.value = false
        _networkPanelOpen.value = false
        _toolsPanelOpen.value = false
        _playerToolsOpen.value = false
        _scanPanelOpen.value = false
        _reminderPanelOpen.value = false
        _resumePanelOpen.value = false
        _bookmarkPanelOpen.value = false
        _epgTimelineOpen.value = false
        _searchPanelOpen.value = false
        _streamQualityPanelOpen.value = false
        _recentPanelOpen.value = false
        _clipExportPanelOpen.value = false
        _audioVisualizerOpen.value = false
        _lyricsOpen.value = false
        // anyPanelOpen 含 channelInfo，若遗漏这里会永久卡住 anyPanelOpen=true，
        // 表现为 BACK 每按一次都被“关闭面板”吞掉、方向键/OK 全部无响应
        _channelInfoOpen.value = false
    }
    if (wasPlayerSettingsOpen) {
        Log.w(AppViewModel.TAG, "resetAllPanelStates: closed playerSettings panel!")
    }
}

internal fun AppViewModel.closeAllPanelsExceptSidebar() {
    resetAllPanelStates()
    stopScanPolling()
    stopAvSyncSampling()
    stopSubSync()
    if (!_landscapeSidebarVisible.value) {
        showControlsAutoHide()
    }
}

internal fun AppViewModel.closeAllPanels() {
    resetAllPanelStates()
    _landscapeSidebarVisible.value = false
    stopScanPolling()
    stopAvSyncSampling()
    stopSubSync()
    showControlsAutoHide()
}

internal fun AppViewModel.closeAnyPanel(): Boolean {
    val hadOpen = anyPanelOpen
    // 仅在有面板打开时执行关闭：
    // closeAllPanels 的副作用（showControlsAutoHide 拉起控制条）会让 BACK 键
    // 随即被 controlsVisible 判断消费（拉起→收起），导致退出确认弹窗永远弹不出
    if (hadOpen) {
        closeAllPanels()
    }
    return hadOpen
}



internal fun AppViewModel.generateMissingThumbnails(channelsToGen: List<IptvChannel>) {
    val existingPaths = _thumbnailPaths.value
    val missing = channelsToGen.filter { ch ->
        ch.url.isNotEmpty() && existingPaths[ch.url]?.let { !java.io.File(it).exists() } ?: true
    }
    if (missing.isEmpty()) {
        Log.i(AppViewModel.TAG, "generateMissingThumbnails: no missing thumbnails")
        // 即使没有缺失缩略图，也获取媒体信息
        if (_mediaInfoMap.value.isEmpty()) {
            fetchMediaInfoForChannels(channelsToGen)
        }
        return
    }

    Log.i(AppViewModel.TAG, "generateMissingThumbnails: ${missing.size} channels need thumbnails")

    // 如果当前正在播放的频道也缺缩略图，触发截图
    val currentChannel = _channels.value.getOrNull(_currentIdx.value)
    if (currentChannel != null && missing.any { it.url == currentChannel.url }) {
        Log.i(AppViewModel.TAG, "generateMissingThumbnails: capturing current channel thumbnail")
        captureChannelThumbnail()
    }

    // 用 MediaMetadataRetriever 在后台逐个生成缩略图
    thumbnailJob?.cancel()
    thumbnailJob = viewModelScope.launch {
        _thumbnailGenProgress.value = Pair(0, missing.size)
        val app = getApplication<Application>()
        val thumbDir = java.io.File(app.cacheDir, "thumbnails")
        thumbDir.mkdirs()
        var done = 0
        for (ch in missing) {
            if (!isActive) break
            try {
                // 测量网络延迟
                if (!_liveLatencyMap.value.containsKey(ch.url)) {
                    val lat = withContext(kotlinx.coroutines.Dispatchers.IO) { measureHttpLatency(ch.url) }
                    if (lat > 0) {
                        _liveLatencyMap.value = _liveLatencyMap.value.toMutableMap().apply { put(ch.url, lat) }
                    }
                }
                val bitmap = withContext(kotlinx.coroutines.Dispatchers.IO) {
                    val retriever = MediaMetadataRetriever()
                    try {
                        retriever.setDataSource(ch.url, HashMap<String, String>())
                        retriever.getFrameAtTime(0, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                    } catch (e: Exception) {
                        Log.w(AppViewModel.TAG, "generateMissingThumbnails: failed for ${ch.name}: ${e.message}")
                        null
                    } finally {
                        try { retriever.release() } catch (_: Exception) {}
                    }
                }
                if (bitmap != null) {
                    val thumbFile = java.io.File(thumbDir, "${ch.url.hashCode()}.png")
                    java.io.FileOutputStream(thumbFile).use { fos ->
                        bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 80, fos)
                    }
                    bitmap.recycle()
                    _thumbnailPaths.value = _thumbnailPaths.value.toMutableMap().apply {
                        put(ch.url, thumbFile.absolutePath)
                    }
                }
                // 获取媒体信息
                val mediaInfo = withContext(kotlinx.coroutines.Dispatchers.IO) {
                    val retriever = MediaMetadataRetriever()
                    try {
                        retriever.setDataSource(ch.url, HashMap<String, String>())
                        val w = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
                        val h = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
                        val fps = if (android.os.Build.VERSION.SDK_INT >= 29) retriever.extractMetadata(30)?.toFloatOrNull() else null
                        val br = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toIntOrNull() ?: 0
                        val mimeType = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_MIMETYPE) ?: ""
                        val parts = mutableListOf<String>()
                        // 分辨率
                        if (w > 0 && h > 0) {
                            parts.add(when { w >= 3800 -> "4K"; w >= 1900 -> "1080P"; w >= 1200 -> "720P"; else -> "${h}P" })
                        }
                        // 容器格式
                        if (mimeType.isNotEmpty()) {
                            val container = when {
                                mimeType.contains("mp2ts") -> "TS"
                                mimeType.contains("mp4") -> "MP4"
                                mimeType.contains("matroska") -> "MKV"
                                mimeType.contains("avi") -> "AVI"
                                mimeType.contains("flv") -> "FLV"
                                mimeType.contains("webm") -> "WEBM"
                                else -> ""
                            }
                            if (container.isNotEmpty()) parts.add(container)
                        }
                        // 帧率
                        if (fps != null && fps > 0) parts.add("${fps.toInt()}FPS")
                        // 码率
                        if (br > 0) parts.add("${br / 1000}kbps")
                        // 协议
                        val proto = ch.url.substringBefore("://").lowercase()
                        when (proto) { "http" -> parts.add("HTTP"); "https" -> parts.add("HTTPS"); "rtsp" -> parts.add("RTSP"); "udp" -> parts.add("UDP"); "rtp" -> parts.add("RTP") }
                        parts.joinToString(" ")
                    } catch (e: Exception) { "" } finally {
                        try { retriever.release() } catch (_: Exception) {}
                    }
                }
                if (mediaInfo.isNotEmpty()) {
                    _mediaInfoMap.value = _mediaInfoMap.value.toMutableMap().apply {
                        put(ch.url, mediaInfo)
                    }
                }
            } catch (e: Exception) {
                Log.w(AppViewModel.TAG, "generateMissingThumbnails: error for ${ch.url}: ${e.message}")
            }
            done++
            _thumbnailGenProgress.value = Pair(done, missing.size)
        }
        _thumbnailGenProgress.value = null
        Log.i(AppViewModel.TAG, "generateMissingThumbnails: batch done, $done/${missing.size}")
    }
}


internal fun AppViewModel.captureChannelThumbnail() {
    val idx = _currentIdx.value
    if (idx < 0) return
    val channel = _channels.value.getOrNull(idx) ?: return
    val url = channel.url
    if (url.isEmpty()) return

    thumbnailJob?.cancel()
    thumbnailJob = viewModelScope.launch {
        delay(3000)
        if (!mpv.fileLoaded.value) return@launch
        try {
            val app = getApplication<Application>()
            val cacheFile = File(app.cacheDir, "thumb_${System.currentTimeMillis()}.png")
            mpv.screenshotToFile(cacheFile.absolutePath, "video")
            // 等待截图写入
            var retry = 0
            while (!cacheFile.exists() && retry < 10) {
                delay(200)
                retry++
            }
            if (cacheFile.exists()) {
                // 上传截图到服务器（服务器保存到 cache/thumbnails/ 目录）
                repository.captureThumbnail(url, cacheFile.absolutePath)
                cacheFile.delete()
                // 上传后从服务器刷新路径（服务器会返回正确的缩略图路径）
                val result = repository.getThumbnailPaths(listOf(url))
                result.onSuccess { paths ->
                    if (paths.isNotEmpty()) {
                        _thumbnailPaths.value = _thumbnailPaths.value.toMutableMap().apply {
                            putAll(paths)
                        }
                    }
                }
                Log.i(AppViewModel.TAG, "captureChannelThumbnail: saved for $url")
            }
        } catch (e: Exception) {
            Log.w(AppViewModel.TAG, "captureChannelThumbnail failed: ${e.message}")
        }
    }
}


internal fun AppViewModel.loadThumbnailPaths() {
    val urls = _channels.value.map { it.url }.filter { it.isNotEmpty() }
    if (urls.isEmpty()) return
    viewModelScope.launch {
        try {
            // 先扫描本地缓存的缩略图
            val app = getApplication<Application>()
            val thumbDir = java.io.File(app.cacheDir, "thumbnails")
            val localPaths = mutableMapOf<String, String>()
            if (thumbDir.exists()) {
                thumbDir.listFiles()?.forEach { file ->
                    if (file.isFile && file.name.endsWith(".png")) {
                        // 文件名是 url.hashCode().png，需要匹配频道
                        val hashPart = file.nameWithoutExtension
                        urls.forEach { url ->
                            if (url.hashCode().toString() == hashPart) {
                                localPaths[url] = file.absolutePath
                            }
                        }
                    }
                }
            }
            // 再从服务器加载
            val result = repository.getThumbnailPaths(urls)
            result.onSuccess { serverPaths ->
                _thumbnailPaths.value = localPaths.apply { putAll(serverPaths) }
                Log.i(AppViewModel.TAG, "loadThumbnailPaths: loaded ${localPaths.size} local + ${serverPaths.size} server thumbnails")
            }.onFailure {
                _thumbnailPaths.value = localPaths
                Log.i(AppViewModel.TAG, "loadThumbnailPaths: loaded ${localPaths.size} local thumbnails (server failed)")
            }
        } catch (e: Exception) {
            Log.w(AppViewModel.TAG, "loadThumbnailPaths failed: ${e.message}")
        }
    }
}


internal fun AppViewModel.playChannelAndShowEpg(idx: Int) {
    fetchEpgForChannel(idx)
    showEpgPanel()
}


internal fun AppViewModel.clearAllThumbnails() {
    viewModelScope.launch {
        val app = getApplication<Application>()
        val thumbDir = java.io.File(app.cacheDir, "thumbnails")
        if (thumbDir.exists()) {
            thumbDir.listFiles()?.forEach { it.delete() }
        }
        _thumbnailPaths.value = emptyMap()
        _thumbnailEnabled.value = false
    }
}


internal fun AppViewModel.refreshMissingThumbnails() {
    val channels = _channels.value
    viewModelScope.launch {
        // 清除本地缓存的缩略图文件
        val app = getApplication<Application>()
        val thumbDir = java.io.File(app.cacheDir, "thumbnails")
        if (thumbDir.exists()) {
            thumbDir.listFiles()?.forEach { it.delete() }
        }
        _thumbnailPaths.value = emptyMap()
        // 清除媒体信息和延迟缓存，强制重新获取
        _mediaInfoMap.value = emptyMap()
        _liveLatencyMap.value = emptyMap()
        delay(300)
        generateMissingThumbnails(channels)
    }
}


internal fun AppViewModel.setThumbnailEnabled(enabled: Boolean) {
    _thumbnailEnabled.value = enabled
    if (!enabled) {
        thumbnailJob?.cancel()
        _thumbnailGenProgress.value = null
    }
}


internal fun AppViewModel.setListViewMode(mode: ListViewMode) {
    _listViewMode.value = mode
}

