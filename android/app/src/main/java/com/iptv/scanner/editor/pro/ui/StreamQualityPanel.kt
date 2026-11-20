package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.focusable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.ui.UiMode
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.PlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import kotlinx.coroutines.delay

/**
 * 流质量检测面板：与 PC 端 get_live_media_info + Web 端 stream_quality 面板对齐。
 *
 * 详细展示 mpv 实时流信息（只读，每秒刷新）：
 * - 视频：codec / 分辨率 / 帧率 / 码率 / 像素格式 / 颜色空间 / HDR
 * - 音频：codec / 声道 / 采样率 / 码率 / 位深
 * - 网络：容器 / 协议 / 缓存速度 / 缓存大小 / 丢帧
 * - 硬件：hwdec / vo
 *
 * 数据来源：mpv.getPropertyString/Int/Double（通过 Player 接口统一访问）。
 */
@Composable
fun StreamQualityPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()
    val oc = rememberPlayerOverlayColors()
    val isTv = androidx.compose.ui.platform.LocalConfiguration.current.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE

    // 每秒刷新（与 Web 端 setInterval 1000ms 一致）
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(fileLoaded) {
        while (fileLoaded) {
            tick++
            delay(1000)
        }
    }

    Surface(color = Color.Transparent, modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
            // -----------------------------------------------------------------
            // 标题栏
            // -----------------------------------------------------------------
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "流质量检测",
                        style = MaterialTheme.typography.headlineSmall,
color = oc.textPrimary
)
Text(
text = "实时流信息（每秒刷新）",
color = oc.textSecondary,
                        fontSize = 12.sp
                    )
                }
                IconButton(
                    onClick = { tick++ },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = oc.iconTint)
                }
                IconButton(
                    onClick = { viewModel.toggleStreamQualityPanel() },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Close, contentDescription = "关闭", tint = oc.iconTint)
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (!fileLoaded) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "未在播放，请先选择频道或打开视频",
color = oc.textSecondary,
fontSize = 13.sp
                    )
                }
                return@Surface
            }

            // -----------------------------------------------------------------
            // 信息列表（每秒刷新）
            // -----------------------------------------------------------------
            // tick 作为 remember key 触发重新读取 mpv 属性
            val info = remember(tick, fileLoaded) { readStreamInfo(mpv) }

            // TV 端：初始焦点在第一个 InfoRow，DPAD 上下逐行聚焦并触发 LazyColumn 滚动
            val firstRowFocus = remember { FocusRequester() }
            LaunchedEffect(fileLoaded) {
                if (fileLoaded) {
                    // 延迟请求焦点，确保 LazyColumn 布局完成
                    kotlinx.coroutines.delay(150)
                    kotlin.runCatching { firstRowFocus.requestFocus() }
                }
            }

            // TV 端：使用 LazyColumn + 可聚焦子项，方向键可逐行聚焦并触发滚动
            LazyColumn(
                modifier = Modifier.fillMaxSize()
            ) {
                // 视频信息
                item {
                    SettingsGroup("视频") {
                        InfoRow("编解码器", info.videoCodec, focusRequester = firstRowFocus, isTv = isTv)
                        InfoRow("分辨率", info.resolution, isTv = isTv)
                        InfoRow("显示分辨率", info.displayResolution, isTv = isTv)
                        InfoRow("帧率", info.fps, isTv = isTv)
                        InfoRow("视频码率", info.videoBitrate, isTv = isTv)
                        InfoRow("像素格式", info.pixelFormat, isTv = isTv)
                        InfoRow("色彩矩阵", info.colormatrix, isTv = isTv)
                        InfoRow("色彩原色", info.primaries, isTv = isTv)
                        InfoRow("传输特性", info.gamma, isTv = isTv)
                        InfoRow("HDR 类型", info.hdrType, isTv = isTv)
                        InfoRow("视频位深", info.videoDepth, isTv = isTv)
                        InfoRow("宽高比", info.aspectRatio, isTv = isTv)
                    }
                }

                item { Spacer(modifier = Modifier.height(16.dp)) }

                // 音频信息
                item {
                    SettingsGroup("音频") {
                        InfoRow("编解码器", info.audioCodec, isTv = isTv)
                        InfoRow("声道数", info.audioChannels, isTv = isTv)
                        InfoRow("声道布局", info.audioLayout, isTv = isTv)
                        InfoRow("采样率", info.sampleRate, isTv = isTv)
                        InfoRow("音频码率", info.audioBitrate, isTv = isTv)
                        InfoRow("音频位深", info.audioDepth, isTv = isTv)
                    }
                }

                item { Spacer(modifier = Modifier.height(16.dp)) }

                // 网络与缓存
                item {
                    SettingsGroup("网络与缓存") {
                        InfoRow("容器格式", info.container, isTv = isTv)
                        InfoRow("协议", info.protocol, isTv = isTv)
                        InfoRow("解复用器", info.demuxer, isTv = isTv)
                        InfoRow("缓存时长", info.cacheDuration, isTv = isTv)
                        InfoRow("缓存大小", info.cacheSize, isTv = isTv)
                        InfoRow("缓存速度", info.cacheSpeed, isTv = isTv)
                        InfoRow("缓冲状态", info.buffering, isTv = isTv)
                        InfoRow("解复用码率", info.demuxerBitrate, isTv = isTv)
                    }
                }

                item { Spacer(modifier = Modifier.height(16.dp)) }

                // 丢帧统计
                item {
                    SettingsGroup("丢帧统计") {
                        InfoRow("VO 丢帧", info.voDropCount, isTv = isTv)
                        InfoRow("解码器丢帧", info.decoderDropCount, isTv = isTv)
                        InfoRow("音视频偏差", info.avdiff, isTv = isTv)
                    }
                }

                item { Spacer(modifier = Modifier.height(16.dp)) }

                // 硬件与渲染
                item {
                    SettingsGroup("硬件与渲染") {
                        InfoRow("硬解", info.hwdec, isTv = isTv)
                        InfoRow("视频输出", info.vo, isTv = isTv)
                    }
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 数据读取
// -----------------------------------------------------------------

/** 流信息快照（每次刷新重新读取） */
private data class StreamInfo(
    // 视频
    val videoCodec: String = "",
    val resolution: String = "",
    val displayResolution: String = "",
    val fps: String = "",
    val videoBitrate: String = "",
    val pixelFormat: String = "",
    val colormatrix: String = "",
    val primaries: String = "",
    val gamma: String = "",
    val hdrType: String = "",
    val videoDepth: String = "",
    val aspectRatio: String = "",
    // 音频
    val audioCodec: String = "",
    val audioChannels: String = "",
    val audioLayout: String = "",
    val sampleRate: String = "",
    val audioBitrate: String = "",
    val audioDepth: String = "",
    // 网络
    val container: String = "",
    val protocol: String = "",
    val demuxer: String = "",
    val cacheDuration: String = "",
    val cacheSize: String = "",
    val cacheSpeed: String = "",
    val buffering: String = "",
    val demuxerBitrate: String = "",
    // 丢帧
    val voDropCount: String = "",
    val decoderDropCount: String = "",
    val avdiff: String = "",
    // 硬件
    val hwdec: String = "",
    val vo: String = ""
)

/** 从 mpv 读取流信息（与 PC 端 get_live_media_info + Web 端 updateStreamQuality 对齐） */
private fun readStreamInfo(mpv: com.iptv.scanner.editor.pro.player.Player): StreamInfo {
    fun gs(name: String): String = mpv.getPropertyString(name) ?: ""
    fun gi(name: String): String = mpv.getPropertyInt(name)?.toString() ?: ""
    fun gd(name: String): String = mpv.getPropertyDouble(name)?.let { "%.2f".format(it) } ?: ""

    val width = mpv.getPropertyInt("width") ?: 0
    val height = mpv.getPropertyInt("height") ?: 0
    val dwidth = mpv.getPropertyInt("dwidth") ?: 0
    val dheight = mpv.getPropertyInt("dheight") ?: 0

    // 帧率：container-fps 优先（mpv-android 不支持 estimated-vf-fps，桌面版才有）
    val fps = gs("container-fps")

    // 视频码率：video-bitrate 优先，回退 video-params/bitrate
    val vBitrate = mpv.getPropertyInt("video-bitrate")?.let { formatBitrate(it) }
        ?: gs("video-params/bitrate").toIntOrNull()?.let { formatBitrate(it) }
        ?: "N/A"

    // 音频码率
    val aBitrate = mpv.getPropertyInt("audio-bitrate")?.let { formatBitrate(it) }
        ?: gs("audio-params/bitrate").toIntOrNull()?.let { formatBitrate(it) }
        ?: "N/A"

    // HDR 类型检测（与 PC 端 detect_hdr_type 逻辑统一对齐）
    val gamma = gs("video-params/gamma")
    val sigPeak = mpv.getPropertyDouble("video-params/sig-peak") ?: 0.0
    val hdrType = detectHdrType(
        gamma, sigPeak,
        gs("video-params/colormatrix"), gs("video-params/primaries")
    )

    // 缓存速度
    val cacheSpeed = mpv.getPropertyDouble("cache-speed")?.let { formatBytesPerSecond(it.toLong()) } ?: "N/A"
    val cacheSize = mpv.getPropertyInt("demuxer-cache-state/total-bytes")?.let { formatBytes(it.toLong()) }
        ?: gi("demuxer-cache-state-bytes").let { if (it.isNotEmpty() && it != "0") formatBytes(it.toLong()) else "N/A" }

    return StreamInfo(
        // 视频
        videoCodec = gs("video-codec").ifEmpty { gs("video-format") }.ifEmpty { "N/A" },
        resolution = if (width > 0 && height > 0) "${width}x${height}" else "N/A",
        displayResolution = if (dwidth > 0 && dheight > 0) "${dwidth}x${dheight}" else "N/A",
        fps = if (fps.isNotEmpty()) "${fps}fps" else "N/A",
        videoBitrate = vBitrate,
        pixelFormat = gs("video-params/pixelformat").ifEmpty { "N/A" },
        colormatrix = gs("video-params/colormatrix").ifEmpty { "N/A" },
        primaries = gs("video-params/primaries").ifEmpty { "N/A" },
        gamma = gamma.ifEmpty { "N/A" },
        hdrType = hdrType,
        videoDepth = gs("video-params/bits-per-component").let { if (it.isEmpty()) "N/A" else "$it bit" },
        aspectRatio = gs("video-params/aspect").ifEmpty { "N/A" },
        // 音频
        audioCodec = gs("audio-codec").ifEmpty { gs("audio-codec-name") }.ifEmpty { "N/A" },
        audioChannels = gi("audio-params/channel-count").ifEmpty { "N/A" } + " ch",
        audioLayout = gs("audio-params/channel-layout").ifEmpty { "N/A" },
        sampleRate = gi("audio-params/samplerate").ifEmpty { "N/A" } + " Hz",
        audioBitrate = aBitrate,
        audioDepth = gi("audio-params/bits-per-sample").ifEmpty { "N/A" } + " bit",
        // 网络
        container = gs("file-format").ifEmpty { "N/A" },
        // 注意：mpv-android 不支持 protocol 和 demuxer-bitrate 属性（桌面版才有）。
        // protocol 从 file-format 推断，demuxer-bitrate 用 video-bitrate+audio-bitrate 替代。
        protocol = gs("file-format").ifEmpty { "N/A" },
        demuxer = gs("demuxer").ifEmpty { "N/A" },
        cacheDuration = gd("demuxer-cache-duration").ifEmpty { gd("demuxer-cache-time") }.ifEmpty { "N/A" } + " s",
        cacheSize = cacheSize,
        cacheSpeed = cacheSpeed,
        buffering = gi("cache-buffering-state").let { if (it.isNotEmpty() && it != "0") "$it%" else "无缓冲" },
        demuxerBitrate = "N/A",
        // 丢帧
        voDropCount = gi("vo-drop-frame-count").ifEmpty { gi("frame-drop-count") }.ifEmpty { "0" },
        decoderDropCount = gi("decoder-drop-frame-count").ifEmpty { gi("decoder-frame-drop-count") }.ifEmpty { "0" },
        avdiff = gd("total-avsync-change").ifEmpty { "0.00" },
        // 硬件
        hwdec = gs("hwdec-current").ifEmpty { "off" },
        vo = gs("vo").ifEmpty { "N/A" }
    )
}

/**
 * HDR 类型检测（与 PC 端 detect_hdr_type 逻辑统一对齐）
 *
 * 检测优先级：PQ(HDR10) → HLG → WCG → SDR
 * 注意：mpv 运行时无法区分 HDR10 与 HDR10+（ST.2094-40 动态元数据不暴露为属性），
 * 统一返回 HDR10。HDR10+ 仅在 ffprobe 扫描阶段通过 side_data 检测。
 * 播放期无法拿到可靠 DV 标记，不再返回 DV；DV 片源按 HDR10 基础层显示。
 */
private fun detectHdrType(
    gamma: String, sigPeak: Double,
    colormatrix: String = "", primaries: String = ""
): String {
    val g = gamma.lowercase()
    val cm = colormatrix.lowercase()
    val prim = primaries.lowercase()

    val isPq = g.contains("pq") || g.contains("smpte2084")
    val isHlg = g.contains("hlg") || g.contains("arib-std-b67")
    val isBt2020 = cm.contains("bt.2020") || cm.contains("bt2020") || cm.contains("bt.2100") ||
        prim.contains("bt.2020") || prim.contains("bt2020") || prim.contains("bt.2100")

    return when {
        isPq -> "HDR10"
        isHlg -> "HLG"
        isBt2020 && sigPeak <= 1.0 -> "WCG"
        isBt2020 && sigPeak > 1.0 -> "HLG"
        else -> "SDR"
    }
}

/** 码率格式化（bps → Kbps/Mbps，与 PC 端 format_bitrate 对齐） */
private fun formatBitrate(bps: Int): String {
    if (bps <= 0) return "N/A"
    return if (bps >= 1_000_000) {
        "%.2f Mbps".format(bps / 1_000_000.0)
    } else {
        "${bps / 1000} kbps"
    }
}

/** 字节数格式化（与 PC 端 format_bytes_per_second 对齐） */
private fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = arrayOf("B", "KB", "MB", "GB")
    var size = bytes.toDouble()
    var unitIdx = 0
    while (size >= 1024 && unitIdx < units.size - 1) {
        size /= 1024
        unitIdx++
    }
    return if (unitIdx == 0) "${bytes} ${units[unitIdx]}" else "%.2f ${units[unitIdx]}".format(size)
}

/** 缓存速度格式化（字节/秒） */
private fun formatBytesPerSecond(bytesPerSec: Long): String {
    return formatBytes(bytesPerSec) + "/s"
}

// -----------------------------------------------------------------
// UI 组件
// -----------------------------------------------------------------

@Composable
private fun SectionLabel(text: String, oc: PlayerOverlayColors = rememberPlayerOverlayColors()) {
    Text(
        text = text,
        color = oc.accent,
        fontSize = 14.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
    )
}

@Composable
private fun InfoRow(
    label: String,
    value: String,
    focusRequester: FocusRequester? = null,
    isTv: Boolean = false,
    oc: PlayerOverlayColors = rememberPlayerOverlayColors()
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .then(if (isTv) Modifier.tvFocusBorder().focusable() else Modifier)
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            color = oc.textSecondary,
            fontSize = 12.sp,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = value,
            color = oc.textPrimary,
            fontSize = 12.sp,
            modifier = Modifier.weight(1.5f),
            fontWeight = FontWeight.Medium
        )
    }
}
