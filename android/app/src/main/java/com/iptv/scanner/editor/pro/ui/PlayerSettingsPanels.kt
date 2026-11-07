package com.iptv.scanner.editor.pro.ui

import android.content.Intent
import android.content.res.Configuration
import android.net.Uri
import android.os.Build
import android.util.Log
import com.iptv.scanner.editor.pro.data.BookmarkItem
import com.iptv.scanner.editor.pro.data.ReminderItem
import com.iptv.scanner.editor.pro.data.ResumeItem
import com.iptv.scanner.editor.pro.data.ScanResult
import com.iptv.scanner.editor.pro.data.SubtitleItem
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Subtitles
import androidx.compose.material.icons.filled.SyncAlt
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.MappingEntry
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
// -----------------------------------------------------------------
// 视频设置面板
// -----------------------------------------------------------------

/**
 * 视频设置面板：与 PC 端 controllers/video_controller.py 对齐。
 *
 * 功能：
 * - 图像调整：亮度/对比度/饱和度/色调/Gamma
 * - 旋转：0/90/180/270
 * - 翻转：无/水平/垂直/both
 * - 一键重置
 */
@Composable
fun VideoSettingsPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()

    // 读取当前值（面板打开时读取一次）
    var brightness by remember { mutableStateOf(mpv.getPropertyInt("brightness") ?: 0) }
    var contrast by remember { mutableStateOf(mpv.getPropertyInt("contrast") ?: 0) }
    var saturation by remember { mutableStateOf(mpv.getPropertyInt("saturation") ?: 0) }
    var hue by remember { mutableStateOf(mpv.getPropertyInt("hue") ?: 0) }
    var gamma by remember { mutableStateOf(mpv.getPropertyInt("gamma") ?: 0) }
    var rotate by remember { mutableStateOf(mpv.getPropertyInt("video-rotate") ?: 0) }
    var flipMode by remember { mutableStateOf("none") }
    // 3D 立体模式（回填当前值）
    var stereoMode by remember { mutableStateOf(mpv.getVideoStereoMode() ?: "mono") }
    // 360° 视角控制
    var projection by remember { mutableStateOf("equirect") }
    var yaw by remember { mutableStateOf(0.0) }
    var pitch by remember { mutableStateOf(0.0) }
    var roll by remember { mutableStateOf(0.0) }
    // 运动补偿
    var mcStrength by remember { mutableStateOf("off") }
    var mcFps by remember { mutableStateOf(60) }
    // 分辨率提升
    var srScale by remember { mutableStateOf("off") }
    var srDetail by remember { mutableStateOf(0) }
    // 用户着色器
    var shaderPreset by remember { mutableStateOf("off") }

    PanelScaffold(
        title = "视频设置",
        subtitle = "图像调整 / 旋转 / 翻转 / 3D 360",
        onClose = { viewModel.toggleVideoSettings() },
        actions = {
            TextButton(
                onClick = {
                    // 一键重置所有图像参数 + 3D/360
                    brightness = 0; contrast = 0; saturation = 0; hue = 0; gamma = 0
                    rotate = 0; flipMode = "none"
                    stereoMode = "mono"; yaw = 0.0; pitch = 0.0; roll = 0.0
                    mcStrength = "off"; mcFps = 60; srScale = "off"; srDetail = 0; shaderPreset = "off"
                    mpv.setBrightness(0); mpv.setContrast(0); mpv.setSaturation(0)
                    mpv.setHue(0); mpv.setGamma(0); mpv.setVideoRotate(0); mpv.setVideoFlip("")
                    mpv.setVideoStereoMode("mono"); mpv.clear360Filter()
                    mpv.clearMotionCompensation(); mpv.clearSuperResolution(); mpv.clearUserShader()
                    viewModel.showOsd("视频设置", "已重置")
                },
                modifier = Modifier.tvFocusBorder()
            ) { Text("全部重置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
        }
    ) {
        if (!fileLoaded) {
            Text("未在播放，调整将在播放后生效", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }

        SettingsGroup("图像调整") {
            LabeledSlider(
                label = "亮度", value = brightness.toFloat(), range = -100f..100f,
                valueText = brightness.toString(),
                onValueChange = { brightness = it.toInt(); mpv.setBrightness(brightness) },
                onReset = { brightness = 0; mpv.setBrightness(0) }
            )
            LabeledSlider(
                label = "对比度", value = contrast.toFloat(), range = -100f..100f,
                valueText = contrast.toString(),
                onValueChange = { contrast = it.toInt(); mpv.setContrast(contrast) },
                onReset = { contrast = 0; mpv.setContrast(0) }
            )
            LabeledSlider(
                label = "饱和度", value = saturation.toFloat(), range = -100f..100f,
                valueText = saturation.toString(),
                onValueChange = { saturation = it.toInt(); mpv.setSaturation(saturation) },
                onReset = { saturation = 0; mpv.setSaturation(0) }
            )
            LabeledSlider(
                label = "色调", value = hue.toFloat(), range = -100f..100f,
                valueText = hue.toString(),
                onValueChange = { hue = it.toInt(); mpv.setHue(hue) },
                onReset = { hue = 0; mpv.setHue(0) }
            )
            LabeledSlider(
                label = "Gamma", value = gamma.toFloat(), range = -100f..100f,
                valueText = gamma.toString(),
                onValueChange = { gamma = it.toInt(); mpv.setGamma(gamma) },
                onReset = { gamma = 0; mpv.setGamma(0) }
            )
        }

        SettingsGroup("旋转") {
            SelectionGroup(
                title = "角度",
                options = listOf("0" to "0°", "90" to "90°", "180" to "180°", "270" to "270°"),
                selectedKey = rotate.toString(),
                onSelect = { deg -> rotate = deg.toInt(); mpv.setVideoRotate(deg.toInt()) }
            )
        }

        SettingsGroup("翻转") {
            SelectionGroup(
                title = "模式",
                options = listOf("none" to "无", "horizontal" to "水平", "vertical" to "垂直", "both" to "both"),
                selectedKey = flipMode,
                onSelect = { mode -> flipMode = mode; mpv.setVideoFlip(mode) }
            )
        }

        // -----------------------------------------------------------------
        // 3D 立体模式（与 PC 端 _STEREO_MODES / Web 端 stereoMode 对齐）
        // 实时切换：点击即生效
        // -----------------------------------------------------------------
        SettingsGroup("3D 立体模式") {
            SelectionGroup(
                title = "模式",
                options = listOf(
                    "mono" to "2D", "sbs" to "左右(左)", "sbs2" to "左右(右)",
                    "ab" to "上下(上)", "ab2" to "上下(下)"
                ),
                selectedKey = stereoMode,
                onSelect = { mode -> stereoMode = mode; mpv.setVideoStereoMode(mode) }
            )
        }

        // -----------------------------------------------------------------
        // 360° 视角控制（与 PC 端 set_360_view / Web 端 apply360 对齐）
        // 调整滑块后点击"应用"才生效，避免拖动时频繁添加/移除滤镜
        // 注意：panorama 滤镜需 ffmpeg 编译时启用，部分设备可能不可用
        // -----------------------------------------------------------------
        SettingsGroup("360° 视角") {
            DescText("调整后点击「应用」生效。需 ffmpeg panorama 滤镜支持，部分设备不可用")

            SelectionGroup(
                title = "投影",
                options = listOf("flat" to "平面", "equirect" to "等距柱状", "cubemap" to "立方体贴图"),
                selectedKey = projection,
                onSelect = { p -> projection = p }
            )

            LabeledSlider(
                label = "Yaw 偏航", value = yaw.toFloat(), range = -180f..180f,
                valueText = "${yaw.toInt()}°",
                onValueChange = { yaw = it.toDouble() },
                onReset = { yaw = 0.0 }
            )
            LabeledSlider(
                label = "Pitch 俯仰", value = pitch.toFloat(), range = -90f..90f,
                valueText = "${pitch.toInt()}°",
                onValueChange = { pitch = it.toDouble() },
                onReset = { pitch = 0.0 }
            )
            LabeledSlider(
                label = "Roll 滚转", value = roll.toFloat(), range = -180f..180f,
                valueText = "${roll.toInt()}°",
                onValueChange = { roll = it.toDouble() },
                onReset = { roll = 0.0 }
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = {
                        mpv.set360View(yaw, pitch, roll, projection)
                        viewModel.showOsd("360° 视角", "已应用")
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("应用 360°") }
                OutlinedButton(
                    onClick = {
                        mpv.clear360Filter()
                        yaw = 0.0; pitch = 0.0; roll = 0.0
                        viewModel.showOsd("360° 视角", "已清除")
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("清除 360°") }
            }
        }

        // -----------------------------------------------------------------
        // 运动补偿（与 PC 端 set_motion_compensation 对齐）
        // 使用 FFmpeg minterpolate 滤镜，需 copy-back 硬解或软解
        // -----------------------------------------------------------------
        SettingsGroup("运动补偿") {
            DescText("需 copy-back 硬解或软解。高强度会增加 CPU 负载")

            SelectionGroup(
                title = "强度",
                options = listOf(
                    "off" to "关闭", "low" to "轻度",
                    "medium" to "中度", "high" to "强力"
                ),
                selectedKey = mcStrength,
                onSelect = { mode ->
                    mcStrength = mode
                    mpv.setMotionCompensation(mode, mcFps)
                    val label = when (mode) {
                        "off" -> "关闭"; "low" -> "轻度"; "medium" -> "中度"; "high" -> "强力"; else -> mode
                    }
                    viewModel.showOsd("运动补偿", if (mode == "off") "已关闭" else "$label ${mcFps}fps")
                }
            )

            SelectionGroup(
                title = "帧率",
                options = listOf("50" to "50", "60" to "60", "90" to "90", "120" to "120", "144" to "144"),
                selectedKey = mcFps.toString(),
                onSelect = { fps ->
                    mcFps = fps.toInt()
                    if (mcStrength != "off") {
                        mpv.setMotionCompensation(mcStrength, fps.toInt())
                        viewModel.showOsd("运动补偿", "${mcFps}fps")
                    }
                }
            )
        }

        // -----------------------------------------------------------------
        // 分辨率提升（与 PC 端 set_super_resolution 对齐）
        // 缩放算法全局生效；细节增强需 copy-back 硬解或软解
        // -----------------------------------------------------------------
        SettingsGroup("分辨率提升") {
            DescText("缩放算法全局生效；细节增强需 copy-back 硬解或软解")

            SelectionGroup(
                title = "算法",
                options = listOf(
                    "off" to "关闭", "bilinear" to "双线性",
                    "bicubic" to "双三次", "lanczos" to "Lanczos",
                    "spline" to "样条", "ewa_lanczos" to "EWA",
                    "ewa_lanczossharp" to "EWA Sharp"
                ),
                selectedKey = srScale,
                onSelect = { algo ->
                    srScale = algo
                    mpv.setSuperResolution(algo, srDetail)
                    val label = listOf(
                        "off" to "关闭", "bilinear" to "双线性",
                        "bicubic" to "双三次", "lanczos" to "Lanczos",
                        "spline" to "样条", "ewa_lanczos" to "EWA",
                        "ewa_lanczossharp" to "EWA Sharp"
                    ).firstOrNull { it.first == algo }?.second ?: algo
                    viewModel.showOsd("分辨率提升", label)
                }
            )

            LabeledSlider(
                label = "细节增强", value = srDetail.toFloat(), range = 0f..100f,
                valueText = srDetail.toString(),
                onValueChange = {
                    srDetail = it.toInt()
                    mpv.setSuperResolution(srScale, srDetail)
                },
                onReset = {
                    srDetail = 0
                    mpv.setSuperResolution(srScale, 0)
                }
            )
        }

        // -----------------------------------------------------------------
        // AI 超分辨率着色器（GLSL Shader，GPU 加速）
        // 着色器文件放在 app filesDir/shaders/ 目录下
        // -----------------------------------------------------------------
        SettingsGroup("AI 超分辨率着色器") {
            DescText("GLSL 着色器在 GPU 运行，不影响 CPU。请将 .glsl/.hook 文件放在 shaders/ 目录")

            SelectionGroup(
                title = "预设",
                options = listOf(
                    "off" to "关闭",
                    "ravu" to "RAVU",
                    "fsrcnnx" to "FSRCNNX",
                    "anime4k" to "Anime4K",
                    "krig" to "KrigBilateral",
                    "ssim" to "SSim",
                    "esrgan" to "ESRGAN",
                    "adaptive_sharpen" to "锐化"
                ),
                selectedKey = shaderPreset,
                onSelect = { preset ->
                    shaderPreset = preset
                    mpv.setUserShader(preset)
                    val label = listOf(
                        "off" to "关闭", "ravu" to "RAVU", "fsrcnnx" to "FSRCNNX",
                        "anime4k" to "Anime4K", "krig" to "KrigBilateral", "ssim" to "SSim",
                        "esrgan" to "ESRGAN", "adaptive_sharpen" to "锐化"
                    ).firstOrNull { it.first == preset }?.second ?: preset
                    viewModel.showOsd("着色器", label)
                }
            )
        }

        // -----------------------------------------------------------------
        // 智能预设（一键优化）
        // -----------------------------------------------------------------
        SettingsGroup("智能预设") {
            SelectionGroup(
                title = "预设",
                options = listOf(
                    "auto" to "智能推荐",
                    "performance" to "性能优先",
                    "quality" to "画质优先",
                    "anime" to "动画优化",
                    "sports" to "体育直播",
                    "movie" to "电影模式"
                ),
                selectedKey = "",
                onSelect = { preset ->
                    val label = listOf(
                        "auto" to "智能推荐", "performance" to "性能优先",
                        "quality" to "画质优先", "anime" to "动画优化",
                        "sports" to "体育直播", "movie" to "电影模式"
                    ).firstOrNull { it.first == preset }?.second ?: preset
                    when (preset) {
                        "auto" -> {
                            // 根据硬件自动选择
                            val cores = Runtime.getRuntime().availableProcessors()
                            val maxMem = Runtime.getRuntime().maxMemory()
                            if (cores >= 8 && maxMem > 512L * 1024 * 1024) {
                                mcStrength = "medium"; mcFps = 60
                                srScale = "ewa_lanczossharp"; srDetail = 40
                                shaderPreset = "off"
                                mpv.setMotionCompensation("medium", 60)
                                mpv.setSuperResolution("ewa_lanczossharp", 40)
                                mpv.clearUserShader()
                            } else if (cores >= 4) {
                                mcStrength = "low"; mcFps = 60
                                srScale = "lanczos"; srDetail = 20
                                shaderPreset = "off"
                                mpv.setMotionCompensation("low", 60)
                                mpv.setSuperResolution("lanczos", 20)
                                mpv.clearUserShader()
                            } else {
                                mcStrength = "off"; mcFps = 60
                                srScale = "bilinear"; srDetail = 0
                                shaderPreset = "off"
                                mpv.clearMotionCompensation()
                                mpv.setSuperResolution("bilinear", 0)
                                mpv.clearUserShader()
                            }
                        }
                        "performance" -> {
                            mcStrength = "off"; mcFps = 60
                            srScale = "bilinear"; srDetail = 0
                            shaderPreset = "off"
                            mpv.clearMotionCompensation()
                            mpv.setSuperResolution("bilinear", 0)
                            mpv.clearUserShader()
                        }
                        "quality" -> {
                            mcStrength = "medium"; mcFps = 60
                            srScale = "ewa_lanczossharp"; srDetail = 40
                            shaderPreset = "off"
                            mpv.setMotionCompensation("medium", 60)
                            mpv.setSuperResolution("ewa_lanczossharp", 40)
                            mpv.clearUserShader()
                        }
                        "anime" -> {
                            mcStrength = "low"; mcFps = 60
                            srScale = "ewa_lanczos"; srDetail = 20
                            shaderPreset = "anime4k"
                            mpv.setMotionCompensation("low", 60)
                            mpv.setSuperResolution("ewa_lanczos", 20)
                            mpv.setUserShader("anime4k")
                        }
                        "sports" -> {
                            mcStrength = "high"; mcFps = 60
                            srScale = "lanczos"; srDetail = 30
                            shaderPreset = "off"
                            mpv.setMotionCompensation("high", 60)
                            mpv.setSuperResolution("lanczos", 30)
                            mpv.clearUserShader()
                        }
                        "movie" -> {
                            mcStrength = "medium"; mcFps = 60
                            srScale = "ewa_lanczossharp"; srDetail = 40
                            shaderPreset = "off"
                            mpv.setMotionCompensation("medium", 60)
                            mpv.setSuperResolution("ewa_lanczossharp", 40)
                            mpv.clearUserShader()
                        }
                    }
                    viewModel.showOsd("智能预设", label)
                }
            )
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
/**
 * 音频设置面板：与 PC 端 controllers/audio_controller.py 对齐。
 *
 * 功能：
 * - 音轨选择（从 track-list 读取）
 * - 音频延迟（-10~10s）
 * - EQ 预设（正常/低音/高音/人声/流行/古典）
 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun AudioSettingsPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()
    val trackListJson by mpv.trackListJson.collectAsState()

    // 音轨列表
    val audioTracks = remember(trackListJson) { parseTracks(trackListJson, "audio") }
    var currentAid by remember { mutableStateOf(0) }

    // 音频延迟
    var audioDelay by remember { mutableStateOf(mpv.getPropertyDouble("audio-delay") ?: 0.0) }

    // EQ 预设
    var eqPreset by remember { mutableStateOf("normal") }

    // 音调（变调不变速，0.5~2.0，1.0=正常）
    // audio-pitch-correction 是 mpv Flag（yes/no），用 getPropertyString 解析
    var audioPitch by remember {
        mutableStateOf(
            when ((mpv.getPropertyString("audio-pitch-correction") ?: "yes").lowercase()) {
                "no", "false", "0" -> 0.0
                else -> 1.0
            }
        )
    }

    // 周期刷新当前 aid
    LaunchedEffect(trackListJson) {
        currentAid = mpv.getPropertyInt("aid") ?: 0
    }

    val eqPresets = remember {
        mapOf(
            "normal" to listOf(0f, 0f, 0f, 0f, 0f, 0f, 0f, 0f, 0f, 0f),
            "bass" to listOf(6f, 4f, 2f, 0f, 0f, 0f, 0f, 0f, 0f, 0f),
            "treble" to listOf(0f, 0f, 0f, 0f, 0f, 0f, 0f, 2f, 4f, 6f),
            "vocal" to listOf(0f, 0f, 0f, 2f, 4f, 4f, 4f, 2f, 0f, 0f),
            "pop" to listOf(-2f, 0f, 2f, 4f, 4f, 2f, 0f, -2f, -2f, 0f),
            "classic" to listOf(2f, 2f, 0f, 0f, 0f, 0f, 0f, 0f, 2f, 2f)
        )
    }

    PanelScaffold(
        title = "音频设置",
        subtitle = "音轨 / 延迟 / EQ / 音调",
        onClose = { viewModel.toggleAudioSettings() },
        actions = {
            TextButton(
                onClick = {
                    audioDelay = 0.0; mpv.setAudioDelay(0.0)
                    eqPreset = "normal"; mpv.resetAudioEq()
                    audioPitch = 1.0; mpv.setAudioPitch(1.0)
                    viewModel.showOsd("音频设置", "已重置")
                },
                modifier = Modifier.tvFocusBorder()
            ) { Text("重置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
        }
    ) {
        if (!fileLoaded) {
            Text("未在播放", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }

        SettingsGroup("音轨") {
            if (audioTracks.isEmpty()) {
                DescText("无可用音轨（单音频流）")
            } else {
                SelectionGroup(
                    title = "音轨",
                    options = audioTracks.map { (id, title) -> id.toString() to title },
                    selectedKey = currentAid.toString(),
                    onSelect = { id -> currentAid = id.toInt(); mpv.setAudioTrack(id.toInt()) }
                )
            }
        }

        SettingsGroup("音频延迟") {
            LabeledSlider(
                label = "延迟（秒）",
                value = audioDelay.toFloat(),
                range = -10f..10f,
                valueText = "${"%.1f".format(audioDelay)}s",
                onValueChange = { audioDelay = it.toDouble(); mpv.setAudioDelay(audioDelay) },
                onReset = { audioDelay = 0.0; mpv.setAudioDelay(0.0) }
            )
        }

        SettingsGroup("均衡器预设") {
            SelectionGroup(
                title = "预设",
                options = listOf("normal" to "正常", "bass" to "低音", "treble" to "高音",
                    "vocal" to "人声", "pop" to "流行", "classic" to "古典"),
                selectedKey = eqPreset,
                onSelect = { key ->
                    eqPreset = key
                    mpv.setAudioEq(eqPresets[key] ?: emptyList())
                    val label = listOf("normal" to "正常", "bass" to "低音", "treble" to "高音",
                        "vocal" to "人声", "pop" to "流行", "classic" to "古典"
                    ).firstOrNull { it.first == key }?.second ?: key
                    viewModel.showOsd("EQ", label)
                }
            )
        }

        SettingsGroup("音调（变调不变速）") {
            LabeledSlider(
                label = "音调",
                value = audioPitch.toFloat(),
                range = 0.5f..2.0f,
                valueText = "${"%.2f".format(audioPitch)}x",
                onValueChange = { audioPitch = it.toDouble(); mpv.setAudioPitch(audioPitch) },
                onReset = { audioPitch = 1.0; mpv.setAudioPitch(1.0) }
            )
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
// -----------------------------------------------------------------
// 播放设置面板
// -----------------------------------------------------------------

/**
 * 播放设置面板：与 PC 端 controllers/playback_controller.py 对齐。
 *
 * 功能：
 * - 循环模式（单文件/列表/无）
 * - AB 循环（设置 A/B 点，清除）
 * - 逐帧（前进/后退）
 * - 速度调节（0.25~4.0）
 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun PlaybackPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()
    val speed by mpv.speed.collectAsState()
    val chapterCount by mpv.chapterCount.collectAsState()
    val currentChapter by mpv.currentChapter.collectAsState()
    val shuffleMode by viewModel.shuffleMode.collectAsState()

    var loopFile by remember { mutableStateOf("no") }
    var loopPlaylist by remember { mutableStateOf("no") }
    var abLoopA by remember { mutableStateOf<Double?>(null) }
    var abLoopB by remember { mutableStateOf<Double?>(null) }

    PanelScaffold(
        title = "播放设置",
        subtitle = "循环 / 随机 / AB / 逐帧 / 速度",
        onClose = { viewModel.togglePlaybackPanel() },
        actions = {
            TextButton(
                onClick = {
                    loopFile = "no"; loopPlaylist = "no"
                    abLoopA = null; abLoopB = null
                    mpv.setLoopFile("no"); mpv.setLoopPlaylist("no"); mpv.clearAbLoop()
                    mpv.setSpeed(1.0)
                    if (shuffleMode) viewModel.toggleShuffleMode()
                    viewModel.showOsd("播放设置", "已重置")
                },
                modifier = Modifier.tvFocusBorder()
            ) { Text("重置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
        }
    ) {
        if (!fileLoaded) {
            Text("未在播放", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }

        SettingsGroup("播放速度") {
            LabeledSlider(
                label = "速度",
                value = speed.toFloat(),
                range = 0.25f..4.0f,
                valueText = "${"%.2f".format(speed)}x",
                onValueChange = { mpv.setSpeed(it.toDouble()) },
                onReset = { mpv.setSpeed(1.0) }
            )
        }

        SettingsGroup("循环模式") {
            SelectionGroup(
                title = "单文件",
                options = listOf("no" to "不循环", "inf" to "单曲循环", "yes" to "循环一次"),
                selectedKey = loopFile,
                onSelect = { mode -> loopFile = mode; mpv.setLoopFile(mode) }
            )
            Spacer(modifier = Modifier.height(8.dp))
            SelectionGroup(
                title = "列表",
                options = listOf("no" to "列表不循环", "inf" to "列表循环", "force" to "强制列表循环"),
                selectedKey = loopPlaylist,
                onSelect = { mode -> loopPlaylist = mode; mpv.setLoopPlaylist(mode) }
            )
        }

        SettingsGroup("随机播放") {
            DescText("开启后，切换下一频道时在当前可见频道范围内随机选择（避免短期重复）。上一频道可回退到上一个随机频道。")
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Switch(
                    checked = shuffleMode,
                    onCheckedChange = { viewModel.toggleShuffleMode() },
                    modifier = Modifier.tvFocusBorder()
                )
                Text(
                    text = if (shuffleMode) "随机播放：开" else "随机播放：关",
                    color = if (shuffleMode) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp
                )
            }
        }

        SettingsGroup("A/B 循环") {
            DescText("设置 A 点和 B 点后，在该区间内循环播放")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                OutlinedButton(
                    onClick = {
                        abLoopA = mpv.timePos.value
                        mpv.setAbLoopA()
                        viewModel.showOsd("AB 循环", "A 点: ${"%.1f".format(abLoopA)}s")
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("设置 A 点") }
                OutlinedButton(
                    onClick = {
                        abLoopB = mpv.timePos.value
                        mpv.setAbLoopB()
                        viewModel.showOsd("AB 循环", "B 点: ${"%.1f".format(abLoopB)}s")
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("设置 B 点") }
                OutlinedButton(
                    onClick = {
                        abLoopA = null; abLoopB = null
                        mpv.clearAbLoop()
                        viewModel.showOsd("AB 循环", "已清除")
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("清除") }
            }
            if (abLoopA != null || abLoopB != null) {
                Text(
                    "A: ${abLoopA?.let { "%.1f".format(it) + "s" } ?: "未设置"}  " +
                        "B: ${abLoopB?.let { "%.1f".format(it) + "s" } ?: "未设置"}",
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }

        SettingsGroup("逐帧") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = { mpv.frameBackStep() },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("◀ 上一帧") }
                OutlinedButton(
                    onClick = { mpv.frameStep() },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("下一帧 ▶") }
            }
        }

        // 章节（如果有）
        if (chapterCount > 0) {
            SettingsGroup("章节（${chapterCount} 个）") {
                Text(
                    "当前: 第 ${currentChapter + 1} 章",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 13.sp
                )
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = { mpv.chapterPrev() },
                        modifier = Modifier.tvFocusBorder()
                    ) { Text("◀ 上一章") }
                    OutlinedButton(
                        onClick = { mpv.chapterNext() },
                        modifier = Modifier.tvFocusBorder()
                    ) { Text("下一章 ▶") }
                }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
// -----------------------------------------------------------------
// 视图设置面板
// -----------------------------------------------------------------

/**
 * 视图设置面板：与 PC 端 controllers/view_controller.py 对齐。
 *
 * 功能：
 * - 视频比例（自适应/16:9/4:3/拉伸）
 * - OSD 显示
 */
@Composable
fun ViewSettingsPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    var aspectMode by remember { mutableStateOf("auto") }

    PanelScaffold(
        title = "视图设置",
        subtitle = "视频比例 / OSD",
        onClose = { viewModel.toggleViewSettings() }
    ) {
        SettingsGroup("视频比例") {
            SelectionGroup(
                title = "比例",
                options = listOf("auto" to "自适应", "16:9" to "16:9", "4:3" to "4:3", "stretch" to "拉伸"),
                selectedKey = aspectMode,
                onSelect = { mode ->
                    aspectMode = mode
                    when (mode) {
                        "auto" -> {
                            mpv.setPropertyBoolean("keepaspect", true)
                            mpv.setPropertyString("video-aspect-override", "0")
                        }
                        "16:9" -> {
                            mpv.setPropertyBoolean("keepaspect", true)
                            mpv.setPropertyString("video-aspect-override", "1.7778")
                        }
                        "4:3" -> {
                            mpv.setPropertyBoolean("keepaspect", true)
                            mpv.setPropertyString("video-aspect-override", "1.3333")
                        }
                        "stretch" -> {
                            mpv.setPropertyBoolean("keepaspect", false)
                        }
                    }
                    val label = listOf("auto" to "自适应", "16:9" to "16:9", "4:3" to "4:3", "stretch" to "拉伸"
                    ).firstOrNull { it.first == mode }?.second ?: mode
                    viewModel.showOsd("视频比例", label)
                }
            )
        }

        SettingsGroup("OSD") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = { viewModel.showOsd("播放时间", "${"%.0f".format(mpv.timePos.value)}秒") },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Text("显示时间")
                }
                OutlinedButton(
                    onClick = {
                        val filename = mpv.getPropertyString("filename") ?: mpv.getPropertyString("media-title") ?: ""
                        viewModel.showOsd("文件名", filename)
                    },
                    modifier = Modifier.tvFocusBorder()
                ) { Text("显示文件名") }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
// =================================================================
// A/V 同步监控面板
// =================================================================

/**
 * A/V 同步监控面板：实时显示 avdiff / audio-pts / video-pts / audio-delay，
 * 波形图可视化历史趋势，音频延迟调整，字幕自动同步。
 * 与 PC 端 av_sync_dialog.py 对齐。
 *
 * 仅 MPV 播放器支持（其他播放器属性返回 null，显示 N/A）。
 */
@Composable
fun AvSyncPanel(viewModel: AppViewModel) {
    val avDiff by viewModel.avDiff.collectAsState()
    val audioPts by viewModel.audioPts.collectAsState()
    val videoPts by viewModel.videoPts.collectAsState()
    val audioDelay by viewModel.currentAudioDelay.collectAsState()
    val history by viewModel.avDiffHistory.collectAsState()
    val subSyncEnabled by viewModel.subSyncEnabled.collectAsState()
    val capabilities by viewModel.playerCapabilities.collectAsState()

    PanelScaffold(
        title = "A/V 同步监控",
        subtitle = "实时波形 / 音视频差值",
        onClose = { viewModel.toggleAvSyncPanel() }
    ) {
        SettingsGroup("实时数值") {
            InfoRow("avdiff", "%.4f s".format(avDiff))
            InfoRow("audio-pts", "%.3f s".format(audioPts))
            InfoRow("video-pts", "%.3f s".format(videoPts))
            InfoRow("audio-delay", "%.3f s".format(audioDelay))

            // avdiff 状态指示
            val diffAbs = kotlin.math.abs(avDiff)
            val diffColor = when {
                diffAbs < 0.04 -> Color(0xFF4CAF50)  // 绿色：正常
                diffAbs < 0.2 -> Color(0xFFFFC107)   // 黄色：轻微偏差
                else -> Color(0xFFF44336)            // 红色：严重偏差
            }
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("同步状态", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                Text(
                    text = when {
                        diffAbs < 0.04 -> "良好"
                        diffAbs < 0.2 -> "轻微偏差"
                        else -> "严重偏差"
                    },
                    color = diffColor,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        SettingsGroup("历史趋势波形") {
            DescText("绿<0.04s  黄<0.2s  红≥0.2s（最近 200 采样点）")
            AvSyncWaveform(history = history, modifier = Modifier.fillMaxWidth().height(120.dp))
        }

        if (capabilities.supportsAudioDelay) {
            SettingsGroup("音频延迟调整") {
                LabeledSlider(
                    label = "音频延迟",
                    value = audioDelay.toFloat(),
                    range = -10f..10f,
                    valueText = "%.3fs".format(audioDelay),
                    onValueChange = { viewModel.adjustAudioDelay(it.toDouble() - audioDelay) },
                    onReset = { viewModel.resetAudioDelay() }
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(onClick = { viewModel.adjustAudioDelay(-0.1) }, modifier = Modifier.weight(1f).tvFocusBorder()) {
                        Text("-0.1s", color = MaterialTheme.colorScheme.onSurface)
                    }
                    OutlinedButton(onClick = { viewModel.adjustAudioDelay(0.1) }, modifier = Modifier.weight(1f).tvFocusBorder()) {
                        Text("+0.1s", color = MaterialTheme.colorScheme.onSurface)
                    }
                    OutlinedButton(onClick = { viewModel.resetAudioDelay() }, modifier = Modifier.weight(1f).tvFocusBorder()) {
                        Text("重置", color = MaterialTheme.colorScheme.onSurface)
                    }
                }
            }
        } else {
            SettingsGroup("音频延迟调整") {
                DescText("当前播放器不支持音频延迟调整（仅 MPV 支持）")
            }
        }

        SettingsGroup("字幕自动同步") {
            DescText("基于 avdiff 比例控制算法：每 500ms 采样，超阈值(0.05s)时按 gain(0.30) 调整 sub_delay")
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("启用自动同步", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                Switch(
                    checked = subSyncEnabled,
                    onCheckedChange = { viewModel.toggleSubSync() },
                    modifier = Modifier.tvFocusBorder()
                )
            }
        }
    }
}
/**
 * 切片导出面板（与 PC 端 ClipExportDialog 对齐）。
 * 支持视频片段裁剪（MP4/GIF/MP3）。
 */
@Composable
fun ClipExportPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()
    val timePos by mpv.timePos.collectAsState()
    val duration by mpv.duration.collectAsState()
    val exportProgress by viewModel.clipExportProgress.collectAsState()
    val exportStatus by viewModel.clipExportStatus.collectAsState()

    var startTimeText by remember { mutableStateOf("") }
    var durationText by remember { mutableStateOf("30") }
    var selectedFormat by remember { mutableStateOf("mp4") }

    PanelScaffold(
        title = "切片导出",
        onClose = { viewModel.toggleClipExportPanel() }
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (!fileLoaded) {
                Text("请先加载视频", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                return@PanelScaffold
            }

            // 当前播放信息
            val posStr = formatTime(timePos)
            val durStr = formatTime(duration)
            Text(
                text = "当前播放: $posStr / $durStr",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp
            )

            // 开始时间输入
            Text("开始时间（秒）", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = startTimeText,
                    onValueChange = { startTimeText = it.filter { c -> c.isDigit() || c == '.' } },
                    placeholder = { Text("${timePos.toInt()}") },
                    modifier = Modifier.weight(1f).tvTextField(),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
                )
                Spacer(modifier = Modifier.width(8.dp))
                OutlinedButton(
                    onClick = { startTimeText = timePos.toInt().toString() },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Text("当前", fontSize = 12.sp)
                }
            }

            // 持续时间输入
            Text("持续时间（秒）", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            OutlinedTextField(
                value = durationText,
                onValueChange = { durationText = it.filter { c -> c.isDigit() || c == '.' } },
                modifier = Modifier.fillMaxWidth().tvTextField(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number)
            )

            // 格式选择
            Text("输出格式", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                listOf("mp4" to "视频(MP4)", "gif" to "动图(GIF)", "mp3" to "音频(MP3)").forEach { (value, label) ->
                    FilterChip(
                        selected = selectedFormat == value,
                        onClick = { selectedFormat = value },
                        label = { Text(label, fontSize = 12.sp) },
                        modifier = Modifier.tvFocusBorder()
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 导出按钮
            Button(
                onClick = {
                    val start = startTimeText.toDoubleOrNull() ?: timePos
                    val dur = durationText.toDoubleOrNull() ?: 30.0
                    viewModel.exportClip(start, dur, selectedFormat)
                },
                modifier = Modifier.fillMaxWidth().tvFocusBorder(),
                enabled = exportProgress !in 1..99
            ) {
                Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("开始导出")
            }

            // 导出进度
            if (exportProgress > 0 || exportStatus.isNotEmpty()) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        if (exportProgress > 0) {
                            LinearProgressIndicator(
                                progress = { exportProgress / 100f },
                                modifier = Modifier.fillMaxWidth(),
                                color = Color(0xFF4CAF50),
                                trackColor = MaterialTheme.colorScheme.surfaceVariant
                            )
                            Text(
                                text = "进度: $exportProgress%",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                        if (exportStatus.isNotEmpty()) {
                            Text(
                                text = exportStatus,
                                color = if (exportStatus.startsWith("导出成功")) Color(0xFF4CAF50)
                                       else Color(0xFFFFA500),
                                fontSize = 12.sp
                            )
                        }
                    }
                }
            }

            // 说明
            Text(
                text = "说明：导出文件将保存到下载目录（Download/ISEP_*）。" +
                       "MP4 使用流拷贝（快速），GIF 限制 480px 宽 10fps，MP3 提取音轨。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                lineHeight = 16.sp
            )
        }
    }
}
