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

internal fun AppViewModel.stopSpectrumSampling() {
    // 引用计数：仍有其他面板（分屏左列常驻频谱/音频可视化/屏保）在使用时不真正停止
    spectrumRefs = (spectrumRefs - 1).coerceAtLeast(0)
    if (spectrumRefs > 0) return
    spectrumJob?.cancel()
    spectrumJob = null
    visualizer?.enabled = false
    visualizer?.release()
    visualizer = null
    _audioSpectrum.value = FloatArray(AppViewModel.AUDIO_SPECTRUM_BANDS) { 0f }
}

internal fun AppViewModel.toggleLyricsPanel() {
    _lyricsOpen.value = !_lyricsOpen.value
    if (_lyricsOpen.value) {
        startLyricsSync()
    } else {
        stopLyricsSync()
        showControlsAutoHide()
    }
}

internal fun AppViewModel.loadLyricsFromUri(uri: String) {
    viewModelScope.launch {
        try {
            val app = getApplication<Application>()
            val content = withContext(kotlinx.coroutines.Dispatchers.IO) {
                if (uri.startsWith("content://")) {
                    app.contentResolver.openInputStream(android.net.Uri.parse(uri))?.bufferedReader()?.use { it.readText() }
                } else if (uri.startsWith("http")) {
                    java.net.URL(uri).readText()
                } else {
                    java.io.File(uri).readText()
                }
            } ?: run {
                showOsd("歌词", "无法读取文件")
                return@launch
            }
            parseLrc(content)
            showOsd("歌词", "已加载 ${_lyricsLines.value.size} 行")
        } catch (e: Exception) {
            showOsd("歌词", "加载失败: ${e.message}")
        }
    }
}

internal fun AppViewModel.parseLrc(content: String) {
    val lines = mutableListOf<LyricsLine>()
    val pattern = Regex("""\[(\d+):(\d+)(?:\.(\d+))?\](.*)""")
    content.lines().forEach { line ->
        val matches = pattern.findAll(line)
        val text = if (matches.none()) line.trim() else {
            val lastMatch = matches.last()
            lastMatch.groupValues[4].trim()
        }
        matches.forEach { m ->
            val min = m.groupValues[1].toLongOrNull() ?: 0L
            val sec = m.groupValues[2].toLongOrNull() ?: 0L
            val ms = m.groupValues[3].let { if (it.isNotEmpty()) (it.toLongOrNull() ?: 0L) else 0L }
            val time = (min * 60 + sec) * 1000 + ms
            val lyricText = m.groupValues[4].trim()
            if (lyricText.isNotEmpty()) {
                lines.add(LyricsLine(time, lyricText))
            }
        }
        // 无时间标签的行（如歌曲信息）
        if (matches.none() && text.isNotEmpty()) {
            lines.add(LyricsLine(0, text))
        }
    }
    lines.sortBy { it.time }
    _lyricsLines.value = lines
}

internal fun AppViewModel.startLyricsSync() {
    lyricsSyncJob?.cancel()
    lyricsSyncJob = viewModelScope.launch {
        while (_lyricsOpen.value) {
            try {
                if (mpv.fileLoaded.value && _lyricsLines.value.isNotEmpty()) {
                    val posMs = (mpv.timePos.value * 1000).toLong()
                    val idx = _lyricsLines.value.indexOfLast { it.time <= posMs }
                    if (idx != _currentLyricLine.value) {
                        _currentLyricLine.value = idx
                    }
                }
            } catch (e: Exception) {
                // 忽略
            }
            kotlinx.coroutines.delay(200)
        }
    }
}

internal fun AppViewModel.stopLyricsSync() {
    lyricsSyncJob?.cancel()
    lyricsSyncJob = null
    _currentLyricLine.value = -1
}

internal fun AppViewModel.clearLyrics() {
    _lyricsLines.value = emptyList()
    _currentLyricLine.value = -1
    showOsd("歌词", "已清除")
}

internal fun AppViewModel.openPlaylistFromUri(uri: String, name: String) {
    if (uri.startsWith("content://") || uri.startsWith("file://")) {
        val parsed = android.net.Uri.parse(uri)
        importPlaylist(parsed)
        return
    }
    viewModelScope.launch {
        showOsd("打开播放列表", name)
        try {
            val added = withContext(kotlinx.coroutines.Dispatchers.IO) {
                // addSource(url, name)：url 必须是内容 URI，name 是显示名
                repository.addSource(uri, name)
            }
            if (added.isSuccess) {
                addRecentFile(uri, name, "playlist")
                loadSources()
                loadChannels()
                showOsd("播放列表", "已导入: $name")
            } else {
                showOsd("播放列表", "导入失败")
            }
        } catch (e: Exception) {
            showOsd("播放列表", "错误: ${e.message}")
        }
    }
}

internal fun AppViewModel.setHdrMode(mode: HdrMode) {
    if (_hdrMode.value == mode) return
    userPrefs.setHdrMode(mode.name.lowercase())
    _hdrMode.value = mode
    // 立即应用到当前已加载的视频
    if (mpv.fileLoaded.value) {
        applyHdrOnFileLoaded()
    }
    val modeName = when (mode) {
        HdrMode.DISABLE -> "禁用 HDR（强制 SDR）"
        HdrMode.AUTO -> "自动（按设备能力选择直通或色调映射）"
        HdrMode.TONEMAP -> "HDR→SDR 色调映射"
        HdrMode.PASSTHROUGH -> "HDR 直通（系统自动切换 HDR 显示）"
    }
    showOsd("HDR 模式：$modeName")
    Log.i(AppViewModel.TAG, "HDR 模式切换：$mode")
}

internal fun AppViewModel.setColorCompatMode(enabled: Boolean) {
    if (_colorCompatMode.value == enabled) return
    userPrefs.setColorCompatMode(enabled)
    _colorCompatMode.value = enabled
    // 立即应用到当前已加载的视频（仅 gpu/gpu-next 生效；mediacodec_embed 没有色调映射属性）
    if (mpv.fileLoaded.value) {
        applyHdrOnFileLoaded()
    }
    showOsd("色彩兼容模式：${if (enabled) "开启" else "关闭"}")
    Log.i(AppViewModel.TAG, "色彩兼容模式切换：$enabled")
}

internal fun AppViewModel.applyHdrOnFileLoaded() {
    val mode = _hdrMode.value
    val mpv = this.mpv
    if (!mpv.fileLoaded.value) return

    val currentVo = try { mpv.getPropertyString("vo") ?: "" } catch (_: Throwable) { "" }
    if (currentVo == "mediacodec_embed") {
        Log.i(AppViewModel.TAG, "HDR 配置：跳过，vo=mediacodec_embed 不支持 GPU 色调映射属性")
        return
    }

    // 色彩兼容模式：强制保守的 SDR 参数（默认关闭，不影响现有正常用户画面）
    if (_colorCompatMode.value) {
        applyColorCompatConfig(mpv)
        Log.i(AppViewModel.TAG, "HDR 配置：色彩兼容模式 → 保守 SDR 参数（不做 HDR 直通）")
        return
    }

    try {
        // 检测视频是否 HDR（与 PC 端统一逻辑）
        val gamma = (mpv.getPropertyString("video-params/gamma") ?: "").lowercase()
        val prim = (mpv.getPropertyString("video-params/primaries") ?: "").lowercase()
        val cm = (mpv.getPropertyString("video-params/colormatrix") ?: "").lowercase()
        val peak = mpv.getPropertyDouble("video-params/sig-peak") ?: 0.0
        val vf = (mpv.getPropertyString("video-format") ?: "").lowercase()

        val isPq = gamma.contains("pq") || gamma.contains("smpte2084")
        val isHlg = gamma.contains("hlg") || gamma.contains("arib-std-b67")
        val hasDovi = vf.contains("dovi") || vf.contains("dolbyvision") ||
            vf.contains("dvhe") || vf.contains("dvh1") || vf.contains("dav1")
        val isBt2020 = cm.contains("bt.2020") || cm.contains("bt2020") ||
            cm.contains("bt.2100") || prim.contains("bt.2020") ||
            prim.contains("bt2020") || prim.contains("bt.2100")
        val isHdr = isPq || isHlg || hasDovi
        val isWcg = !isHdr && isBt2020

        Log.i(AppViewModel.TAG, "HDR 检测：gamma=$gamma, primaries=$prim, sig_peak=$peak, " +
            "isHdr=$isHdr, isWcg=$isWcg, isPq=$isPq, isHlg=$isHlg, hasDovi=$hasDovi")

        // WCG 视频无论 hdr_mode 如何都必须保持 bt.2020 色域
        if (isWcg) {
            // WCG 视频（宽色域 SDR）：保持 bt.2020 色域（与 PC 端 _apply_wcg_config 对齐）
            applyWcgConfig(mpv)
            Log.i(AppViewModel.TAG, "HDR 配置：WCG 视频 → 保持 bt.2020 色域")
            return
        }

        if (!isHdr) {
            // 非 HDR 视频也重置 SDR 参数（避免残留上次 HDR 配置）
            resetHdrParams(mpv)
            Log.i(AppViewModel.TAG, "HDR 配置：非 HDR 视频 → 重置 SDR 默认值")
            return
        }

        // hdr10-opt 设置
        safeSetProperty(mpv, "hdr10-opt", if (isPq) "yes" else "no")

        // disable 模式：HDR 视频仍需 tonemap 到 SDR（保持 bt.2020 色域）
        if (mode == HdrMode.DISABLE) {
            applyTonemapConfig(mpv, isPq, isHlg)
            Log.i(AppViewModel.TAG, "HDR 配置：disable → HDR 视频 tonemap 到 SDR (bt.2020)")
            return
        }

        when (mode) {
            HdrMode.TONEMAP -> applyTonemapConfig(mpv, isPq, isHlg)
            HdrMode.PASSTHROUGH -> applyPassthroughConfig(mpv, isPq)
            HdrMode.AUTO -> {
                // AUTO 模式：检测设备 HDR 能力
                if (isDeviceHdrSupported()) {
                    applyPassthroughConfig(mpv, isPq)
                    Log.i(AppViewModel.TAG, "HDR 配置：AUTO → 设备支持 HDR，使用直通")
                } else {
                    applyTonemapConfig(mpv, isPq, isHlg)
                    Log.i(AppViewModel.TAG, "HDR 配置：AUTO → 设备不支持 HDR，使用色调映射")
                }
            }
            else -> resetHdrParams(mpv)
        }
        Log.i(AppViewModel.TAG, "HDR 配置：mode=$mode 应用完成")
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "应用 HDR 设置失败", e)
    }
}

internal fun AppViewModel.isDeviceHdrSupported(): Boolean {
    return try {
        val display = (getApplication() as android.app.Application)
            .getSystemService(android.content.Context.WINDOW_SERVICE)
            .let { it as? android.view.WindowManager }
            ?.defaultDisplay
        if (display == null) return false
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
            val caps = display.hdrCapabilities
            val types = caps?.supportedHdrTypes ?: IntArray(0)
            // HDR_TYPE_DOLBY_VISION=1, HDR_TYPE_HDR10=2, HDR_TYPE_HLG=3, HDR_TYPE_HDR10_PLUS=4
            types.isNotEmpty()
        } else {
            false
        }
    } catch (e: Exception) {
        Log.w(AppViewModel.TAG, "HDR 能力检测失败: ${e.message}")
        false
    }
}

internal fun AppViewModel.safeSetProperty(mpv: Player, name: String, value: String) {
    try {
        mpv.setPropertyString(name, value)
    } catch (e: Throwable) {
        // 属性不存在或格式不支持，静默忽略（mediacodec_embed VO 不支持 GPU 色调映射属性）
    }
}

internal fun AppViewModel.resetHdrParams(mpv: Player) {
    safeSetProperty(mpv, "tone-mapping", "")
    safeSetProperty(mpv, "tone-mapping-mode", "")
    safeSetProperty(mpv, "tone-mapping-desat", "")
    safeSetProperty(mpv, "hdr-compute-peak", "")
    safeSetProperty(mpv, "hdr10-opt", "no")
    safeSetProperty(mpv, "target-prim", "bt.709")
    safeSetProperty(mpv, "target-trc", "bt.1886")
    safeSetProperty(mpv, "target-colorspace-hint", "no")
    safeSetProperty(mpv, "gamut-mapping-mode", "auto")
}

/**
 * 色彩兼容模式：强制最保守的 SDR 输出参数。
 *
 * 只对 gpu/gpu-next 生效（mediacodec_embed 没有这些属性）。
 * 默认不启用；启用后 HDR 内容统一按 clip 映射到 bt.709，牺牲观感换取稳定，
 * 用于个别设备过曝/发灰时的排障（用户本机无过曝，因此不作为默认值）。
 */
internal fun AppViewModel.applyColorCompatConfig(mpv: Player) {
    safeSetProperty(mpv, "tone-mapping", "clip")
    safeSetProperty(mpv, "tone-mapping-mode", "auto")
    safeSetProperty(mpv, "hdr-compute-peak", "no")
    safeSetProperty(mpv, "hdr10-opt", "no")
    safeSetProperty(mpv, "video-output-levels", "auto")
    safeSetProperty(mpv, "target-prim", "bt.709")
    safeSetProperty(mpv, "target-trc", "bt.1886")
    safeSetProperty(mpv, "target-colorspace-hint", "no")
    safeSetProperty(mpv, "gamut-mapping-mode", "clip")
}

internal fun AppViewModel.applyWcgConfig(mpv: Player) {
    // WCG 视频（宽色域 SDR）：保持 bt.2020 色域，SDR 亮度（与 PC 端 _apply_wcg_config 对齐）
    // 显式设置所有参数（不用空字符串重置，避免残留 HDR 参数）
    safeSetProperty(mpv, "tone-mapping", "auto")  // 与 SDR/HLG 统一, 避免 clip 触发不同渲染路径
    safeSetProperty(mpv, "tone-mapping-mode", "auto")
    safeSetProperty(mpv, "tone-mapping-desat", "0")
    safeSetProperty(mpv, "hdr-compute-peak", "no")
    safeSetProperty(mpv, "hdr10-opt", "no")
    safeSetProperty(mpv, "target-prim", "bt.2020")
    safeSetProperty(mpv, "target-trc", "bt.1886")
    safeSetProperty(mpv, "target-colorspace-hint", "no")
    safeSetProperty(mpv, "target-peak", "100")
    safeSetProperty(mpv, "gamut-mapping-mode", "relative")
}

internal fun AppViewModel.applyTonemapConfig(mpv: Player, isPq: Boolean, isHlg: Boolean = false) {
    // HDR→SDR 色调映射（与 PC 端 _apply_tonemap_config 统一）
    // target-prim=bt.2020 保留广色域（WCG），在支持广色域的设备上显示更丰富色彩
    // target-trc=bt.1886 SDR 伽马，确保 SDR 显示正确
    // hdr10-opt=yes(仅PQ) 传递 HDR10+ 动态元数据
    // gamut-mapping-mode=perceptual 感知映射，减少色域裁剪损失
    // HLG 视频去饱和度降为 0，避免整体发灰
    val desat = if (isHlg) "0" else "0.5"
    if (isHlg) {
        // HLG tonemap: auto (gpu-next 选 spline, 感知均匀, 保留中间调亮度)
        // hdr-compute-peak=yes: HLG 无嵌入 maxCLL, 需动态计算场景峰值
        // 避免用 bt.2390 (线性扩展段压缩中间调, 比 spline 更暗)
        safeSetProperty(mpv, "tone-mapping", "auto")
        safeSetProperty(mpv, "hdr-compute-peak", "yes")
    } else {
        safeSetProperty(mpv, "tone-mapping", "auto")
        safeSetProperty(mpv, "hdr-compute-peak", "no")
    }
    safeSetProperty(mpv, "tone-mapping-mode", "auto")
    safeSetProperty(mpv, "tone-mapping-desat", desat)
    safeSetProperty(mpv, "hdr10-opt", if (isPq) "yes" else "no")
    safeSetProperty(mpv, "target-prim", "bt.2020")
    safeSetProperty(mpv, "target-trc", "bt.1886")
    safeSetProperty(mpv, "target-colorspace-hint", "no")
    safeSetProperty(mpv, "gamut-mapping-mode", "perceptual")
}

internal fun AppViewModel.applyPassthroughConfig(mpv: Player, isPq: Boolean) {
    safeSetProperty(mpv, "tone-mapping", if (isPq) "clip" else "auto")
    safeSetProperty(mpv, "tone-mapping-mode", "")
    safeSetProperty(mpv, "tone-mapping-desat", "0")
    safeSetProperty(mpv, "hdr-compute-peak", "no")  // PQ 用 maxCLL, HLG 用 sig_peak
    safeSetProperty(mpv, "hdr10-opt", if (isPq) "yes" else "no")
    // 清空 target 参数，让 mpv 直通视频原生色彩空间（PQ/HLG 不转换）
    safeSetProperty(mpv, "target-prim", "")
    safeSetProperty(mpv, "target-trc", "")
    // 关键：启用 target-colorspace-hint 让 Android 系统自动切换 HDR 显示模式
    // mpv 会通过 SurfaceView 传递 HDR 元数据给系统，系统自动切换到 HDR 显示
    safeSetProperty(mpv, "target-colorspace-hint", "yes")
    safeSetProperty(mpv, "gamut-mapping-mode", "clip")
}

internal fun AppViewModel.isSafAvailable(): Boolean {
    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
        addCategory(Intent.CATEGORY_OPENABLE)
        type = "*/*"
    }
    val pm = getApplication<Application>().packageManager
    // Android TV 系统可能注册了 frameworkpackagestubs 桩 activity，
    // 它声明能处理 ACTION_OPEN_DOCUMENT 但实际启动时会提示"没有可执行的应用"。
    // 需要排除此类 stub，只认可真实的文件管理器 activity。
    val realActivities = pm.queryIntentActivities(intent, 0).filter { ri ->
        val name = ri.activityInfo.name
        val pkg = ri.activityInfo.packageName
        val isStub = name.contains("Stub", ignoreCase = true) ||
            pkg.contains("frameworkpackagestubs", ignoreCase = true)
        !isStub
    }
    Log.i(AppViewModel.TAG, "isSafAvailable: ${realActivities.size} real activities found (filtered out stubs)")
    return realActivities.isNotEmpty()
}

internal fun AppViewModel.playLocalVideo(uri: String) {
    Log.i(AppViewModel.TAG, "playLocalVideo: $uri")

    // 检测是否为 M3U/M3U8 播放列表文件：
    // 用户通过"本地文件"按钮选择 M3U 文件时，应解析为频道列表而非当作视频播放。
    // 检测方式：MIME 类型包含 mpegurl，或文件名以 .m3u/.m3u8 结尾。
    val app = getApplication<Application>()
    val parsedUri = Uri.parse(uri)
    val isM3u = try {
        val mime = app.contentResolver.getType(parsedUri)
        val isM3uMime = mime != null && mime.contains("mpegurl", ignoreCase = true)
        val fileName = parsedUri.lastPathSegment ?: ""
        val isM3uExt = fileName.endsWith(".m3u", ignoreCase = true) ||
                       fileName.endsWith(".m3u8", ignoreCase = true)
        isM3uMime || isM3uExt
    } catch (_: Exception) {
        val fileName = parsedUri.lastPathSegment ?: ""
        fileName.endsWith(".m3u", ignoreCase = true) ||
        fileName.endsWith(".m3u8", ignoreCase = true)
    }
    if (isM3u) {
        Log.i(AppViewModel.TAG, "playLocalVideo: detected M3U/M3U8 file, redirecting to importPlaylist")
        importPlaylist(parsedUri)
        return
    }

    viewModelScope.launch {
        _currentIdx.value = -1
        _channelDisplayInfo.value = ChannelDisplayInfo(
            name = uri.substringAfterLast('/').substringAfterLast('%'),
            idx = -1, isLocal = true
        )
        _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
        currentIsLocalFile = true

        // content:// URI 需要拷贝到缓存文件；file:// 和绝对路径直接用
        val playPath = withContext(Dispatchers.IO) {
            if (uri.startsWith("content://")) {
                try {
                    val app = getApplication<Application>()
                    val resolver = app.contentResolver
                    val cacheDir = app.cacheDir
                    // 从 MIME 类型推断扩展名（mpv 需要正确扩展名识别容器格式）
                    val mime = try { resolver.getType(Uri.parse(uri)) } catch (_: Exception) { null }
                    val ext = when {
                        mime == null -> ".mp4"
                        mime.contains("matroska") -> ".mkv"
                        mime.contains("mp4") -> ".mp4"
                        mime.contains("mpeg") -> ".mpg"
                        mime.contains("webm") -> ".webm"
                        mime.contains("audio/mpeg") -> ".mp3"
                        mime.contains("audio/") -> ".m4a"
                        else -> ".mp4"
                    }
                    val tempFile = File(cacheDir, "local_video_${System.currentTimeMillis()}$ext")
                    resolver.openInputStream(Uri.parse(uri))?.use { input ->
                        tempFile.outputStream().use { input.copyTo(it) }
                    } ?: return@withContext null
                    tempFile.absolutePath
                } catch (e: Exception) {
                    Log.e(AppViewModel.TAG, "playLocalVideo copy content:// failed", e)
                    null
                }
            } else {
                // file:// 或绝对路径，去除 file:// 前缀
                uri.removePrefix("file://")
            }
        }

        if (playPath == null) {
            showOsd("播放失败", "无法读取文件")
            return@launch
        }

        // 续播位置：记录本地文件信息（用缓存文件路径，便于下次恢复）
        currentPlaybackUrl = playPath
        currentPlaybackName = playPath.substringAfterLast('/').substringAfterLast('%')
        refreshCurrentBookmarks()

        try {
            mpv.playFile(playPath)
            showOsd("本地文件", currentPlaybackName)
            closeAllPanels()
            _showHome.value = false  // 切换到播放器界面

            // 保存到历史记录和本地频道列表（source='' 标记为本地）
            try {
                val fileName = currentPlaybackName.ifBlank { playPath.substringAfterLast('/') }
                val existingIdx = _channels.value.indexOfFirst { it.url == playPath }
                if (existingIdx < 0) {
                    // 新文件：添加为本地频道（同步等待完成）
                    val addResult = repository.addChannel(playPath, fileName, "本地视频")
                    addResult.onSuccess { addedIdx ->
                        // 直接在当前频道列表中追加，不依赖异步 loadChannels
                        val newChannel = IptvChannel(
                            name = fileName, url = playPath, group = "本地视频",
                            source = ""
                        )
                        _channels.value = _channels.value + newChannel
                        val newIdx = _channels.value.indexOfLast { it.url == playPath }
                        if (newIdx >= 0) {
                            _currentIdx.value = newIdx
                            _channelDisplayInfo.value = ChannelDisplayInfo(
                                name = fileName, group = "本地视频", idx = newIdx, isLocal = true
                            )

                            userPrefs.addToHistory(newIdx)
                            _history.value = userPrefs.getHistory()
                            Log.i(AppViewModel.TAG, "playLocalVideo: added local channel idx=$newIdx, name=$fileName")
                        }
                    }.onFailure { e ->
                        Log.w(AppViewModel.TAG, "playLocalVideo: addChannel failed: ${e.message}")
                    }
                } else {
                    userPrefs.addToHistory(existingIdx)
                    _history.value = userPrefs.getHistory()
                    _currentIdx.value = existingIdx
                    _channelDisplayInfo.value = ChannelDisplayInfo(
                        name = _channels.value.getOrNull(existingIdx)?.name ?: "",
                        group = "本地视频", idx = existingIdx, isLocal = true
                    )

                    Log.i(AppViewModel.TAG, "playLocalVideo: existing channel idx=$existingIdx")
                }
            } catch (e: Exception) {
                Log.w(AppViewModel.TAG, "playLocalVideo: failed to save history: ${e.message}")
            }
        } catch (e: Throwable) {
            Log.e(AppViewModel.TAG, "playLocalVideo mpv.playFile failed", e)
            showOsd("播放失败", e.message ?: "无法播放此文件")
        }
    }
}

internal fun AppViewModel.playUrl(url: String) {
    if (url.isBlank()) {
        showOsd("请输入 URL")
        return
    }
    Log.i(AppViewModel.TAG, "playUrl: $url")
    _channelDisplayInfo.value = ChannelDisplayInfo(
        name = url.substringAfterLast('/').takeIf { it.isNotEmpty() } ?: url,
        idx = -1, isLocal = true
    )
    // 添加到本地频道列表（如果尚未存在）
    viewModelScope.launch {
        val existing = _channels.value.find { it.url == url }
        if (existing == null) {
            val name = url.substringAfterLast('/').takeIf { it.isNotEmpty() } ?: url
            repository.addChannel(url, name, "本地").onSuccess { idx ->
                loadChannels()
                _currentIdx.value = idx
            }
        } else {
            _currentIdx.value = _channels.value.indexOfFirst { it.url == url }
        }
    }
    _playbackState.value = PlaybackState(mode = PlayMode.LIVE)
    currentPlaybackUrl = url
    currentPlaybackName = url
    currentIsLocalFile = true
    refreshCurrentBookmarks()
    // MPV 支持全部协议，直接播放
    mpv.playFile(url)
    showOsd("网络流", url)
    closeAllPanels()
    _showHome.value = false  // 切换到播放器界面
}

internal fun AppViewModel.importPlaylist(uri: Uri) {
    viewModelScope.launch {
        showOsd("正在导入播放列表...")
        val content = withContext(Dispatchers.IO) {
            try {
                getApplication<Application>().contentResolver.openInputStream(uri)?.use {
                    it.bufferedReader().readText()
                }
            } catch (e: Exception) {
                Log.e(AppViewModel.TAG, "importPlaylist read failed", e)
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

/** mpv 支持的外挂字幕扩展名（按真实扩展名保存，不能一律改写成 .srt） */
private val SUPPORTED_SUBTITLE_EXTS = setOf(
    "srt", "ass", "ssa", "vtt", "sub", "idx", "sup", "ttml", "dfxp", "lrc"
)

/** 通过 SAF 查询用户所选文件的真实显示名（含真实扩展名） */
private fun querySubtitleDisplayName(
    resolver: android.content.ContentResolver,
    uri: Uri
): String? {
    return try {
        resolver.query(uri, arrayOf(android.provider.OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }
    } catch (e: Exception) {
        Log.w(AppViewModel.TAG, "querySubtitleDisplayName failed: ${e.message}")
        null
    }
}

internal fun AppViewModel.loadSubtitleFile(uri: Uri) {
    viewModelScope.launch {
        val resolver = getApplication<Application>().contentResolver
        val displayName = querySubtitleDisplayName(resolver, uri)
        // 优先用 SAF 显示名的扩展名，其次退回 URI 末段
        val rawName = displayName ?: uri.lastPathSegment ?: ""
        val ext = rawName.substringAfterLast('.', "").lowercase().trim()

        // 格式校验：扩展名不在支持列表时如实失败，不保存成 .srt 假装成功
        if (ext.isEmpty() || ext !in SUPPORTED_SUBTITLE_EXTS) {
            showOsd("字幕加载失败", if (ext.isEmpty()) "无法识别字幕格式" else "不支持的格式 .$ext")
            return@launch
        }

        // SAF 返回的 content:// URI 需要拷贝到缓存目录才能给 mpv 用；保留真实扩展名
        val subFile = withContext(Dispatchers.IO) {
            try {
                val cacheDir = getApplication<Application>().cacheDir
                val tempFile = File(cacheDir, "subtitle_${System.currentTimeMillis()}.$ext")
                resolver.openInputStream(uri)?.use { input ->
                    tempFile.outputStream().use { input.copyTo(it) }
                }
                tempFile.absolutePath
            } catch (e: Exception) {
                Log.e(AppViewModel.TAG, "loadSubtitleFile copy failed", e)
                null
            }
        } ?: run {
            showOsd("字幕加载失败", "无法读取文件")
            return@launch
        }

        // 记录 sub-add 前的轨道列表，用实际变化判断是否真的加载成功，而不是无条件提示成功
        val beforeTracks = mpv.trackListJson.value
        if (!mpv.addSubtitleFile(subFile)) {
            showOsd("字幕加载失败", "播放器未就绪")
            return@launch
        }
        val loaded = withTimeoutOrNull(2000) {
            while (mpv.trackListJson.value == beforeTracks) delay(100)
            true
        } ?: false
        if (loaded) {
            showOsd("字幕已加载", displayName ?: subFile.substringAfterLast('/'))
        } else {
            showOsd("字幕加载失败", "无法解析该字幕文件")
        }
    }
}

internal fun AppViewModel.takeScreenshot(mode: String = "video") {
    // mediacodec_embed 让解码器直接写 Surface，mpv 画面层（screenshot 命令）拿不到帧
    if (_currentVo.value == "mediacodec_embed") {
        showOsd("截图不可用", "当前为 MediaCodec 直写渲染，请先在播放器设置切回 GPU 渲染")
        return
    }
    viewModelScope.launch {
        val now = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val filename = "screenshot_$now.png"

        val savedPath = withContext(Dispatchers.IO) {
            try {
                val app = getApplication<Application>()
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    // Android 10+ 用 MediaStore 写到 Pictures 目录
                    val resolver = app.contentResolver
                    val values = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
                        put(MediaStore.MediaColumns.MIME_TYPE, "image/png")
                        put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/IPTV_Screenshots")
                    }
                    val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                        ?: return@withContext null
                    // mpv screenshot-to-file 需要文件路径，不能直接写 content:// URI
                    // 先截到缓存目录，再复制到 MediaStore
                    val cacheFile = File(app.cacheDir, filename)
                    mpv.screenshotToFile(cacheFile.absolutePath, mode)
                    // 等待截图文件写入（mpv 异步执行）
                    var retry = 0
                    while (!cacheFile.exists() && retry < 10) {
                        Thread.sleep(200)
                        retry++
                    }
                    if (cacheFile.exists()) {
                        resolver.openOutputStream(uri)?.use { out ->
                            cacheFile.inputStream().use { it.copyTo(out) }
                        }
                        cacheFile.delete()
                        "Pictures/IPTV_Screenshots/$filename"
                    } else null
                } else {
                    // Android 9 及以下，直接写到公共目录
                    @Suppress("DEPRECATION")
                    val dir = File(
                        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
                        "IPTV_Screenshots"
                    )
                    if (!dir.exists()) dir.mkdirs()
                    val file = File(dir, filename)
                    mpv.screenshotToFile(file.absolutePath, mode)
                    var retry = 0
                    while (!file.exists() && retry < 10) {
                        Thread.sleep(200)
                        retry++
                    }
                    if (file.exists()) file.absolutePath else null
                }
            } catch (e: Exception) {
                Log.e(AppViewModel.TAG, "takeScreenshot failed", e)
                null
            }
        }
        if (savedPath != null) {
            showOsd("截图已保存", savedPath)
        } else {
            showOsd("截图失败")
        }
    }
}

internal fun AppViewModel.startBurstScreenshot(intervalSec: Double, total: Int, mode: String = "video") {
    if (_burstActive.value) return
    _burstActive.value = true
    _burstCount.value = 0
    _burstTotal.value = total
    showOsd("连拍截图", "开始：间隔 ${intervalSec}s，共 $total 张")
    burstJob = viewModelScope.launch {
        for (i in 1..total) {
            if (!isActive) break
            _burstCount.value = i
            takeScreenshot(mode)
            if (i < total) {
                kotlinx.coroutines.delay((intervalSec * 1000).toLong())
            }
        }
        _burstActive.value = false
        showOsd("连拍截图", "完成：$total 张已保存到 Pictures/IPTV_Screenshots")
    }
}

internal fun AppViewModel.stopBurstScreenshot() {
    burstJob?.cancel()
    burstJob = null
    _burstActive.value = false
    showOsd("连拍截图", "已停止（已拍 ${_burstCount.value} 张）")
}

/** 是否处于「没有任何频道」状态：后端无频道且本地列表为空、且不在加载订阅源 */
internal fun AppViewModel.isZeroChannelState(): Boolean {
    val status = _iptvStatus.value ?: return false
    return status.inited && !status.sourceLoading && status.channelsTotal == 0 && _channels.value.isEmpty()
}

/** 零频道播放页按 OK：直接打开订阅源管理面板，并把初始焦点放到 URL 输入框 */
internal fun AppViewModel.openSourceManagerForAdd() {
    if (!_sourceManagerOpen.value) toggleSourceManager()
    // toggleSourceManager 打开时会重置为默认焦点，这里再置为直达 URL 输入框
    _sourceManagerFocusUrl.value = true
}

internal fun AppViewModel.toggleSourceManager() {
    _sourceManagerOpen.value = !_sourceManagerOpen.value
    if (_sourceManagerOpen.value) {
        // 普通入口（统一面板等）保持默认初始焦点
        _sourceManagerFocusUrl.value = false
        loadSources()
        loadEpgSources()
        // 刷新频道列表：用户可能通过局域网管理页面在电脑端添加了订阅源，
        // 服务器端已自动加载频道，这里同步到 Android 端
        loadChannels()
        refreshAdminServerStatus()
    } else {
        // 关闭面板时自动显示控制层；并清掉「直达 URL 输入框」标记，
        // 避免下次从统一面板进入时继承该初始焦点
        _sourceManagerFocusUrl.value = false
        showControlsAutoHide()
    }
}

internal fun AppViewModel.setSourceTab(tab: SourceTab) { _sourceTab.value = tab }

internal fun AppViewModel.togglePlayerSettings() {
    _playerSettingsOpen.value = !_playerSettingsOpen.value
    Log.i(AppViewModel.TAG, "togglePlayerSettings: open=${_playerSettingsOpen.value}")
    if (!_playerSettingsOpen.value) showControlsAutoHide()
}

internal fun AppViewModel.setPlayerVo(vo: String) {
    userPrefs.setVo(vo)
    _currentVo.value = vo
    // 用户显式重选 vo：清掉本进程「已自动回退」记忆，允许再次尝试默认 mediacodec_embed 路径
    mpvSingleton.resetVoFallbackForUser()
    val hwdec = when {
        vo == "mediacodec_embed" -> "mediacodec"
        // arm32 电视/盒子：gpu/gpu-next 只允许软解（AImageReader 直通与 copy-back 都会崩）
        userPrefs.isTvEmbedRequired() && _currentHwdec.value != "no" -> "no"
        else -> userPrefs.getHwdec()
    }
    if (vo == "mediacodec_embed") {
        // 切换到 mediacodec_embed 时，hwdec 也应为 mediacodec
        userPrefs.setHwdec(hwdec)
        _currentHwdec.value = hwdec
        // 标记已 fallback（不需要再黑屏检测）
        userPrefs.setVoFallbackConfirmed(true)
    } else if (vo == "gpu" || vo == "gpu-next") {
        // 切换到 gpu / gpu-next 时，清除 fallback 标记，重新启用黑屏检测
        userPrefs.setVoFallbackConfirmed(false)
        if (hwdec != _currentHwdec.value) {
            userPrefs.setHwdec(hwdec)
            _currentHwdec.value = hwdec
        }
    }
    // vo 切换只在 MPV 模式下有意义（其他播放器无 vo 概念）
    val hasFile = (_player.value as? MpvController)?.setVoAndHwdec(vo, hwdec)
    val suffix = (if (hasFile != null) "，已重新加载" else "（重启后生效）") +
        if (vo == "mediacodec_embed") "；此模式不支持字幕/截图" else ""
    showOsd("播放器设置", "vo=$vo$suffix")
}

internal fun AppViewModel.setPlayerHwdec(hwdec: String, byUser: Boolean = true) {
    // arm32 电视/盒子：硬解只允许 mediacodec 直写 Surface；用户点「重试硬件解码」时
    // 必须带上 mediacodec_embed，不能停在 gpu + mediacodec（AImageReader 路径）。
    var vo = _currentVo.value
    if (hwdec != "no" && userPrefs.isTvEmbedRequired() && vo != "mediacodec_embed") {
        vo = "mediacodec_embed"
    }
    if (vo != _currentVo.value) {
        userPrefs.setVo(vo)
        _currentVo.value = vo
        mpvSingleton.resetVoFallbackForUser()
    }
    userPrefs.setHwdec(hwdec)
    _currentHwdec.value = hwdec
    // 用户显式选择硬解：解除崩溃黑名单 + 清会话降级，给一次干净的重试机会
    if (byUser) {
        (_player.value as? MpvController)?.confirmHardwareDecodeSelection(hwdec)
    }
    (_player.value as? MpvController)?.setVoAndHwdec(vo, hwdec)
    showOsd("播放器设置", "vo=$vo，hwdec=$hwdec")
}

internal fun AppViewModel.setRtspTransport(transport: String) {
    userPrefs.setRtspTransport(transport)
    _currentRtspTransport.value = transport
    showOsd("播放器设置", "RTSP 传输: $transport")
}

/** 切换 ExoPlayer 视频渲染视图（SurfaceView/TextureView）。
 * 播放器视图层（updatePlayerView）按 tag 比对自动重建渲染视图，播放不中断。 */
internal fun AppViewModel.setExoSurfaceView(useSurfaceView: Boolean) {
    _exoSurfaceView.value = useSurfaceView
    userPrefs.setExoSurfaceView(useSurfaceView)
}

internal fun AppViewModel.setHardwareDecode(enabled: Boolean) {
    val player = _player.value ?: return
    val success = try {
        player.setHardwareDecode(enabled)
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "setHardwareDecode failed", e)
        false
    }
    if (success) {
        // MPV 模式下同步更新 vo/hwdec 状态（UI 显示用）
        if (player is MpvController) {
            // 电视/盒子硬解固定 mediacodec_embed + mediacodec；手机 gpu-next + mediacodec 直通；
            // 软解时 mediacodec_embed 没有解码器直渲，vo 退回 gpu。
            val newVo = userPrefs.voForHardwareDecode(enabled, _currentVo.value)
            val newHwdec = userPrefs.hwdecForHardwareDecode(enabled, _currentHwdec.value)
            if (newVo != _currentVo.value) {
                userPrefs.setVo(newVo)
                _currentVo.value = newVo
            }
            userPrefs.setHwdec(newHwdec)
            _currentHwdec.value = newHwdec
        }
        // 更新通用硬件解码状态（UI 自动响应）
        _hardwareDecode.value = enabled
        showOsd("播放器设置", if (enabled) "硬件解码" else "软件解码")
    } else {
        showOsd("播放器设置", "切换失败（当前 vo 不支持软解）")
    }
}

internal fun AppViewModel.applyVoChange(vo: String) {
    val player = _player.value ?: return
    if (player !is MpvController) return
    try {
        player.setVoAndHwdec(vo, userPrefs.getHwdec())
        _currentVo.value = vo
        userPrefs.setVo(vo)
        // 重新加载当前频道
        val url = currentPlaybackUrl
        if (url.isNotEmpty()) {
            player.playFile(url)
        }
        Log.i(AppViewModel.TAG, "applyVoChange: vo=$vo, reloading $url")
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "applyVoChange failed", e)
        showOsd("播放器设置", "切换失败: ${e.message}")
    }
}

internal fun AppViewModel.isHardwareDecodeEnabled(): Boolean {
    return _player.value?.isHardwareDecodeEnabled() ?: true
}

internal fun AppViewModel.resetPlayerSettings() {
    userPrefs.resetPlayerSettings()
    _currentVo.value = userPrefs.getVo()
    _currentHwdec.value = userPrefs.getHwdec()
    _currentDeinterlace.value = userPrefs.getDeinterlace()
    _hdrMode.value = HdrMode.DISABLE
    // 恢复默认应立即生效
    (_player.value as? MpvController)?.setVoAndHwdec(_currentVo.value, _currentHwdec.value)
    (_player.value as? MpvController)?.setDeinterlace(_currentDeinterlace.value)
    // 已加载视频时立即应用重置后的 HDR 配置（disable → SDR 默认值）
    if (mpv.fileLoaded.value) {
        applyHdrOnFileLoaded()
    }
    showOsd("播放器设置", "已重置为默认值")
}

internal fun AppViewModel.exportConfig() {
    viewModelScope.launch {
        showOsd("备份", "正在导出配置...")
        val pyConfig = withContext(Dispatchers.IO) { repository.exportConfig() }
        pyConfig.fold(
            onSuccess = { pyJson ->
                val fullBackup = buildFullBackup(pyJson)
                val written = writeBackupToFile(fullBackup)
                if (written) {
                    showOsd("备份", "已导出到下载目录")
                } else {
                    showOsd("备份", "导出失败：无法写入文件")
                }
            },
            onFailure = { showOsd("备份", "导出失败", it.message ?: "") }
        )
    }
}

internal fun AppViewModel.importConfig(uri: Uri) {
    viewModelScope.launch {
        showOsd("恢复", "正在导入配置...")
        val result = withContext(Dispatchers.IO) {
            val json = readBackupFromFile(uri)
                ?: return@withContext Result.failure<Unit>(Exception("读取文件失败"))
            restoreFullBackup(json)
        }
        result.fold(
            onSuccess = {
                showOsd("恢复", "配置已恢复，正在加载频道...")
                loadSources()
                loadEpgSources()
                loadChannels()
                loadUserPrefs()
            },
            onFailure = { showOsd("恢复", "恢复失败", it.message ?: "") }
        )
    }
}

internal fun AppViewModel.buildFullBackup(pyConfigJson: String): String {
    val now = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())
    val pyConfig = JSONObject(pyConfigJson)
    val backup = JSONObject().apply {
        put("backup_version", 1)
        put("backup_time", now)
        // Python 配置（订阅源 + EPG 源）
        put("playlist_sources", pyConfig.optJSONArray("playlist_sources") ?: JSONArray())
        put("epg_sources", pyConfig.optJSONArray("epg_sources") ?: JSONArray())
        // UserPrefs 配置（收藏/历史/队列；URL 版为持久真相源，idx 版向后兼容）
        put("favorites", JSONArray(userPrefs.getFavorites().toList()))
        put("favorites_urls", JSONArray(userPrefs.getFavoriteUrls().toList()))
        put("history", JSONArray(userPrefs.getHistory()))
        put("history_urls", JSONArray(userPrefs.getHistoryUrls()))
        put("queue", JSONArray(userPrefs.getQueue()))
        put("queue_urls", JSONArray(userPrefs.getQueueUrls()))
        // 播放器设置
        put("player_vo", userPrefs.getVo())
        put("player_hwdec", userPrefs.getHwdec())
        put("player_vo_fallback", userPrefs.isVoFallbackConfirmed())
    }
    return backup.toString(2)
}

internal suspend fun AppViewModel.restoreFullBackup(json: String): Result<Unit> {
    return try {
        val backup = JSONObject(json)
        // 构造 Python import_config 需要的 JSON（只含 playlist_sources + epg_sources）
        val pyConfig = JSONObject().apply {
            put("playlist_sources", backup.optJSONArray("playlist_sources") ?: JSONArray())
            put("epg_sources", backup.optJSONArray("epg_sources") ?: JSONArray())
        }
        val pyResult = repository.importConfig(pyConfig.toString())
        if (pyResult.isFailure) return pyResult

        // 恢复 UserPrefs（URL 版优先：频道重排后仍能按 URL 匹配）
        backup.optJSONArray("favorites_urls")?.let { arr ->
            val set = (0 until arr.length()).mapNotNull { arr.optString(it, "").takeIf { s -> s.isNotEmpty() } }.toSet()
            userPrefs.setFavoriteUrls(set)
        }
        backup.optJSONArray("favorites")?.let { arr ->
            val set = (0 until arr.length()).mapNotNull { arr.optInt(it, -1).takeIf { i -> i >= 0 } }.toSet()
            userPrefs.setFavorites(set)
        }
        backup.optJSONArray("history_urls")?.let { arr ->
            val list = (0 until arr.length()).mapNotNull { arr.optString(it, "").takeIf { s -> s.isNotEmpty() } }
            userPrefs.setHistoryUrls(list)
        }
        backup.optJSONArray("history")?.let { arr ->
            val list = (0 until arr.length()).mapNotNull { arr.optInt(it, -1).takeIf { i -> i >= 0 } }
            userPrefs.setHistory(list)
        }
        backup.optJSONArray("queue_urls")?.let { arr ->
            val list = (0 until arr.length()).mapNotNull { arr.optString(it, "").takeIf { s -> s.isNotEmpty() } }
            userPrefs.setQueueUrls(list)
        }
        backup.optJSONArray("queue")?.let { arr ->
            val list = (0 until arr.length()).mapNotNull { arr.optInt(it, -1).takeIf { i -> i >= 0 } }
            userPrefs.setQueue(list)
        }
        backup.optString("player_vo").takeIf { it.isNotEmpty() }?.let { userPrefs.setVo(it) }
        backup.optString("player_hwdec").takeIf { it.isNotEmpty() }?.let { userPrefs.setHwdec(it) }
        if (backup.has("player_vo_fallback")) {
            userPrefs.setVoFallbackConfirmed(backup.optBoolean("player_vo_fallback"))
        }

        Result.success(Unit)
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "restoreFullBackup failed", e)
        Result.failure(e)
    }
}

internal fun AppViewModel.writeBackupToFile(json: String): Boolean {
    val now = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
    val filename = "IPTV_backup_$now.json"
    return try {
        val app = getApplication<Application>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = app.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
                put(MediaStore.MediaColumns.MIME_TYPE, "application/json")
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return false
            resolver.openOutputStream(uri)?.use { it.write(json.toByteArray()) } ?: return false
        } else {
            @Suppress("DEPRECATION")
            val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!dir.exists()) dir.mkdirs()
            File(dir, filename).writeText(json)
        }
        Log.i(AppViewModel.TAG, "Backup written to Downloads/$filename")
        true
    } catch (e: Exception) {
        Log.e(AppViewModel.TAG, "writeBackupToFile failed", e)
        false
    }
}



internal fun AppViewModel.setLogLevel(level: String) {
if (_logLevel.value == level) return
userPrefs.setLogLevel(level)
_logLevel.value = level
// 运行时切换 MPV 日志等级（立即生效，无需重启）
mpvSingleton.setMpvLogLevel(level)
// 同步切换 Python 日志等级（影响 app.log 文件和 logcat 输出）
viewModelScope.launch {
    withContext(Dispatchers.IO) {
        repository.setLogLevel(level)
    }
}
val levelName = when (level) {
"debug" -> "调试"
"info" -> "信息"
"warn" -> "警告"
"error" -> "错误"
else -> level
}
showOsd("播放器设置", "日志等级: $levelName")
}


internal fun AppViewModel.setPortraitTab(tab: PortraitTab) {
        _portraitTab.value = tab
    }


internal fun AppViewModel.setListSourceTab(tab: ListSourceTab) {
    _listSourceTab.value = tab
}

/** 订阅 / 本地两页签的真实频道数（以实际列表数据为准，不看加载状态与缓存计数） */
internal fun AppViewModel.listSourceCounts(): Pair<Int, Int> {
    val all = _channels.value
    val local = all.count { it.source.isEmpty() }
    return (all.size - local) to local
}

/**
 * 自动校正列表页签（订阅 / 本地），与桌面端 `_ensure_playlist_tab_has_content` 一致：
 * 只有"当前页签实际为空、另一页签实际有数据"时才切换，非空页签不会被后台刷新抢走。
 *
 * 额外区分"刚刚变空"与"用户主动停在空页签"：若该页签上次校正时也为空，
 * 说明是用户手动选中的空页签，保持不动，避免刷新把用户的选择抢走。
 */
internal fun AppViewModel.reconcileListSourceTab() {
    val all = _channels.value
    if (all.isEmpty()) return
    val counts = listSourceCounts()
    val previous = listSourceTabCounts
    listSourceTabCounts = counts
    val current = _listSourceTab.value
    val currentEmpty = if (current == ListSourceTab.SUBSCRIPTION) counts.first == 0 else counts.second == 0
    val otherHasData = if (current == ListSourceTab.SUBSCRIPTION) counts.second > 0 else counts.first > 0
    if (!currentEmpty || !otherHasData) return
    val previouslyEmpty = when (current) {
        ListSourceTab.SUBSCRIPTION -> previous?.first == 0
        ListSourceTab.LOCAL -> previous?.second == 0
    }
    if (previouslyEmpty) return
    val target = if (current == ListSourceTab.SUBSCRIPTION) ListSourceTab.LOCAL else ListSourceTab.SUBSCRIPTION
    Log.i(AppViewModel.TAG, "reconcileListSourceTab: ${current.name}(空) -> ${target.name}, sub=${counts.first}, local=${counts.second}")
    _listSourceTab.value = target
}

