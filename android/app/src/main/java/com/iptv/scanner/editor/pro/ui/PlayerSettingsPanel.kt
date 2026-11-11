package com.iptv.scanner.editor.pro.ui

import android.content.res.Configuration
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.foundation.background
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.player.PlayerType
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvFocusLayoutScale

/**
 * 播放器设置面板（全屏覆盖）。
 *
 * 仅 MPV 内核设置（与 PC 端统一）：
 * 1. 视频输出（vo）：gpu / gpu-next / mediacodec_embed
 * 2. 硬件解码（hwdec）：必须与 vo 匹配
 * 3. 反交错、HDR 模式、RTSP 传输协议、日志等级
 *
 * 兜底方案：当黑屏检测不可靠时（如 estimated-vfps 仍有值但渲染黑屏），
 * 用户可手动切换 vo（gpu / gpu-next / mediacodec_embed），立即生效并持久化。
 *
 * - vo：video output，gpu / gpu-next（EGL 渲染）或 mediacodec_embed（MediaCodec 直写 Surface）
 * - hwdec：硬件解码，auto-copy / mediacodec / no（必须与 vo 匹配）
 *   电视/盒子（arm32）硬解固定 mediacodec_embed + mediacodec，不再提供 copy-back 选项
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PlayerSettingsPanel(viewModel: AppViewModel) {
    if (LocalAptvStyle.current) {
        PlayerSettingsPanelAptv(viewModel)
        return
    }
    val currentVo by viewModel.currentVo.collectAsState()
    val currentHwdec by viewModel.currentHwdec.collectAsState()
    val actualHwdec by viewModel.actualHwdec.collectAsState()
    val hwdecBlacklisted by viewModel.hwdecBlacklisted.collectAsState()
    val currentRtspTransport by viewModel.currentRtspTransport.collectAsState()
    val currentDeinterlace by viewModel.currentDeinterlace.collectAsState()
    val logLevel by viewModel.logLevel.collectAsState()
    val hdrMode by viewModel.hdrMode.collectAsState()
    val hardwareDecode by viewModel.hardwareDecode.collectAsState()

    // 面板打开时主动抢焦点，避免焦点回落到下层统一面板的菜单项
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        runCatching { closeFocusRequester.requestFocus() }
    }

    BoxWithConstraints(
        modifier = Modifier.fillMaxSize()
    ) {
        val useDualColumn = maxWidth > 500.dp

        // 弹窗玻璃底座由 PortraitPanelDialog 提供（TV/横屏静态玻璃、竖屏底部 sheet），
        // 此处根容器必须透明，否则会盖住磨砂质感变回实底面板
        Surface(
            color = Color.Transparent,
            modifier = Modifier.fillMaxSize()
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .focusGroup()
                    .systemBarsPadding()
                    .padding(16.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "播放器设置",
                        style = MaterialTheme.typography.headlineSmall,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = { viewModel.resetPlayerSettings() }, modifier = Modifier.tvFocusBorder()) {
                            Icon(Icons.Default.Refresh, contentDescription = "重置", tint = MaterialTheme.colorScheme.onSurface)
                        }
                        IconButton(onClick = { viewModel.togglePlayerSettings() }, modifier = Modifier.tvFocusBorder().focusRequester(closeFocusRequester)) {
                            Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                if (useDualColumn) {
                    Row(
                        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            PlayerSettingsLeftColumn(viewModel)
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            PlayerSettingsRightColumn(viewModel)
                        }
                    }
                } else {
                    Column(
                        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                    ) {
                        PlayerSettingsLeftColumn(viewModel)
                        PlayerSettingsRightColumn(viewModel)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PlayerSettingsLeftColumn(viewModel: AppViewModel) {
    val currentPlayerType by viewModel.playerType.collectAsState()
    val currentVo by viewModel.currentVo.collectAsState()
    val currentHwdec by viewModel.currentHwdec.collectAsState()
    val actualHwdec by viewModel.actualHwdec.collectAsState()
    val hwdecBlacklisted by viewModel.hwdecBlacklisted.collectAsState()
    val actualVo by viewModel.actualVo.collectAsState()
    val renderPathReason by viewModel.renderPathReason.collectAsState()
    val voAutoFallback by viewModel.voAutoFallback.collectAsState()
    val colorCompatMode by viewModel.colorCompatMode.collectAsState()
    val hardwareDecode by viewModel.hardwareDecode.collectAsState()
    val timeoutSwitch by viewModel.timeoutSwitchSource.collectAsState()
    val reconnectIdx by viewModel.reconnectIndex.collectAsState()
    val screenLocked by viewModel.screenLock.collectAsState()

    // 内核选择行的焦点：纳入独立 focusGroup + 打开面板时把初始焦点放到当前内核 chip。
    // 之前这一行只有 tvFocusBorder 画边框、没有焦点锚点，遥控器从上方菜单向下移动时
    // 会跳过 EXO chip，用户看到的是「焦点对不上 EXO 模块」。
    val mpvChipFocus = remember { FocusRequester() }
    val exoChipFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        runCatching {
            if (currentPlayerType == PlayerType.EXO) exoChipFocus.requestFocus()
            else mpvChipFocus.requestFocus()
        }
    }

    SectionTitle("播放器内核")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("切换播放器内核。MPV 功能最完整，ExoPlayer 兼容性好。两者都支持硬解/软解切换")
    Spacer(modifier = Modifier.height(8.dp))
    FlowRow(
        modifier = Modifier
            .fillMaxWidth()
            .focusGroup(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        FilterChip(
            selected = currentPlayerType == PlayerType.MPV,
            onClick = { viewModel.switchPlayerType(PlayerType.MPV) },
            label = { Text("MPV（推荐）") },
            modifier = Modifier
                .tvFocusBorder()
                .tvFocusLayoutScale()
                .focusRequester(mpvChipFocus),
            border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.50f))
        )
        FilterChip(
            selected = currentPlayerType == PlayerType.EXO,
            onClick = { viewModel.switchPlayerType(PlayerType.EXO) },
            label = { Text("ExoPlayer") },
            modifier = Modifier
                .tvFocusBorder()
                .tvFocusLayoutScale()
                .focusRequester(exoChipFocus),
            border = androidx.compose.foundation.BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.50f))
        )
    }
    Spacer(modifier = Modifier.height(6.dp))
    Text(
        text = currentPlayerType.description,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 12.sp,
        modifier = Modifier.padding(horizontal = 4.dp)
    )
    Spacer(modifier = Modifier.height(20.dp))


    // ExoPlayer 视频渲染视图切换（SurfaceView 兼容性更好；TextureView 部分设备 GPU 渲染异常）
    if (currentPlayerType == PlayerType.EXO) {
        val exoSurfaceView by viewModel.exoSurfaceView.collectAsState()
        SectionTitle("视频渲染（ExoPlayer）")
        Spacer(modifier = Modifier.height(4.dp))
        SectionDesc("画面黑屏或停在第一帧时切换渲染视图。SurfaceView 兼容性最好")
        Spacer(modifier = Modifier.height(8.dp))
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            FilterChip(
                selected = exoSurfaceView,
                onClick = { if (!exoSurfaceView) viewModel.setExoSurfaceView(true) },
                label = { Text("SurfaceView（推荐）") },
                modifier = Modifier.tvFocusBorder()
            )
            FilterChip(
                selected = !exoSurfaceView,
                onClick = { if (exoSurfaceView) viewModel.setExoSurfaceView(false) },
                label = { Text("TextureView") },
                modifier = Modifier.tvFocusBorder()
            )
        }
        Spacer(modifier = Modifier.height(20.dp))
    }

    SectionTitle("播放增强")
    Spacer(modifier = Modifier.height(8.dp))
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        FilterChip(
            selected = false,
            onClick = { viewModel.setTimeoutSwitchSource((timeoutSwitch + 1) % 6) },
            label = { Text("超时换源: ${listOf("5s","8s","12s","15s","20s","30s")[timeoutSwitch]}") },
            modifier = Modifier.tvFocusBorder()
        )
        FilterChip(
            selected = false,
            onClick = { viewModel.setReconnectIndex((reconnectIdx + 1) % 6) },
            label = { Text("断线重连: ${listOf("关闭","3s","5s","10s","15s","20s")[reconnectIdx]}") },
            modifier = Modifier.tvFocusBorder()
        )
    }
    Spacer(modifier = Modifier.height(8.dp))
    // 半透明小卡：透出弹窗玻璃底座，保持磨砂层次感
    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.55f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth().tvFocusBorder().focusable().padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(text = "画面锁定（换源不黑屏）", color = MaterialTheme.colorScheme.primary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    Text(text = "切换频道时保持上一帧画面，避免黑屏闪烁", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                Switch(checked = screenLocked, onCheckedChange = { viewModel.setScreenLock(it) })
            }

        }
    }
    Spacer(modifier = Modifier.height(20.dp))

    if (currentPlayerType == PlayerType.MPV) {
        SectionTitle("视频输出（VO）")
        Spacer(modifier = Modifier.height(4.dp))
        SectionDesc("决定画面如何渲染到屏幕。默认走 GPU；黑屏有声音时可尝试 MediaCodec 直写 Surface（实验性，重启播放器后生效）")
        Spacer(modifier = Modifier.height(8.dp))
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            FilterChip(selected = currentVo == "gpu", onClick = { viewModel.setPlayerVo("gpu") }, label = { Text("GPU（EGL）") }, modifier = Modifier.tvFocusBorder())
            FilterChip(selected = currentVo == "gpu-next", onClick = { viewModel.setPlayerVo("gpu-next") }, label = { Text("GPU-Next（EGL）") }, modifier = Modifier.tvFocusBorder())
            FilterChip(selected = currentVo == "mediacodec_embed", onClick = { viewModel.setPlayerVo("mediacodec_embed") }, label = { Text("MediaCodec（实验）") }, modifier = Modifier.tvFocusBorder())
        }
        Spacer(modifier = Modifier.height(6.dp))
        val voDesc = when (currentVo) {
            "gpu" -> "GPU 渲染：经典 EGL 后端，支持 HDR/OSD/shader，兼容大多数 GPU。部分 GPU（如 Mali-G76）可能黑屏"
            "gpu-next" -> "GPU-Next 渲染：新一代 EGL 后端（render API），渲染路径与 GPU 不同。支持 HDR/OSD/shader，GPU 黑屏时可尝试此选项"
            "mediacodec_embed" -> "实验性：MediaCodec 直接写 Surface（零拷贝，不占 GPU 滤镜），需重启播放器后生效。部分电视冷启动会随机退出，遇到时重启并切回 GPU。App 侧弹窗与 OSD 正常；mpv 画面层不可用：字幕不显示、截图失败、翻转/裁剪等视频滤镜无效。"
            else -> "未知 vo: $currentVo"
        }
        Text(text = voDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = voActualText(actualVo, currentVo, voAutoFallback),
            color = if (voAutoFallback) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
            modifier = Modifier.padding(horizontal = 4.dp)
        )
        renderPathText(actualVo, renderPathReason)?.let { pathText ->
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = pathText,
                color = MaterialTheme.colorScheme.primary,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 4.dp)
            )
        }
        Spacer(modifier = Modifier.height(20.dp))

        SectionTitle("硬件解码（HWDEC）")
        Spacer(modifier = Modifier.height(4.dp))
        SectionDesc("决定视频解码方式。必须与 vo 匹配")
        Spacer(modifier = Modifier.height(8.dp))
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            when (currentVo) {
                "gpu", "gpu-next" -> {
                    // 电视/盒子：AImageReader 直通与 auto-copy 都会崩，只保留软解；
                    // 需要硬解时切到 MediaCodec（mediacodec_embed 直写 Surface）
                    if (!viewModel.isArm32TvDevice) {
                        FilterChip(selected = currentHwdec == "mediacodec", onClick = { viewModel.setPlayerHwdec("mediacodec") }, label = { Text("mediacodec（硬解）") }, modifier = Modifier.tvFocusBorder())
                        FilterChip(selected = currentHwdec == "auto-copy", onClick = { viewModel.setPlayerHwdec("auto-copy") }, label = { Text("auto-copy（兼容）") }, modifier = Modifier.tvFocusBorder())
                        FilterChip(selected = currentHwdec == "auto", onClick = { viewModel.setPlayerHwdec("auto") }, label = { Text("auto（4K HDR）") }, modifier = Modifier.tvFocusBorder())
                    }
                    FilterChip(selected = currentHwdec == "no", onClick = { viewModel.setPlayerHwdec("no") }, label = { Text("no（软解）") }, modifier = Modifier.tvFocusBorder())
                }
                "mediacodec_embed" -> {
                    FilterChip(selected = currentHwdec == "mediacodec", onClick = { viewModel.setPlayerHwdec("mediacodec") }, label = { Text("mediacodec（固定）") }, modifier = Modifier.tvFocusBorder())
                }
            }
        }
        if (hwdecBlacklisted) {
            Spacer(modifier = Modifier.height(6.dp))
            FilterChip(
                selected = false,
                onClick = {
                    // 用户显式重试硬解：解除黑名单 + 清除会话降级，只给这一次机会
                    viewModel.setPlayerHwdec("mediacodec")
                },
                label = { Text("重试硬件解码") },
                modifier = Modifier.tvFocusBorder()
            )
        }
        Spacer(modifier = Modifier.height(6.dp))
        val hwdecDesc = when (currentHwdec) {
            "auto-copy" -> "自动选择硬件解码器，解码后拷贝到 CPU 内存再上传 GPU。兼容性好，支持视频滤镜（翻转/裁剪/360°）。4K HDR 可能卡顿"
            "auto" -> "自动选择最佳硬解，优先直接输出（零拷贝）。4K HDR 流畅，但视频翻转/裁剪/360° 滤镜可能不可用"
            "mediacodec" -> "MediaCodec 硬件解码：与 vo=mediacodec_embed 配合时解码器直接写 Surface（电视可选直写路径）；vo=gpu/gpu-next 时经 AImageReader 直通（手机默认路径）"
            "no" -> "纯软件解码。兼容性最好但耗电，CPU 解码可能慢"
            else -> "未知 hwdec: $currentHwdec"
        }
        Text(text = hwdecDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = hwdecActualText(actualHwdec, hwdecBlacklisted),
            color = if (actualHwdec == "no" && currentHwdec != "no") MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
            modifier = Modifier.padding(horizontal = 4.dp)
        )
        Spacer(modifier = Modifier.height(20.dp))
    }

    if (currentPlayerType == PlayerType.EXO) {
        SectionTitle("解码模式")
        Spacer(modifier = Modifier.height(4.dp))
        SectionDesc("硬解使用 GPU MediaCodec 加速，软解使用 CPU 软件编解码器。软解兼容性更好但更耗电")
        Spacer(modifier = Modifier.height(8.dp))
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            FilterChip(selected = hardwareDecode, onClick = { viewModel.setHardwareDecode(true) }, label = { Text("硬件解码（推荐）") }, modifier = Modifier.tvFocusBorder())
            FilterChip(selected = !hardwareDecode, onClick = { viewModel.setHardwareDecode(false) }, label = { Text("软件解码") }, modifier = Modifier.tvFocusBorder())
        }
        Spacer(modifier = Modifier.height(6.dp))
        Text(
            text = if (hardwareDecode) "硬件解码：使用 Android MediaCodec 硬件加速解码。功耗低、速度快，但部分 4K/HDR 流可能不兼容。遇到花屏/卡顿时可尝试软解" else "软件解码：使用 Android 系统自带的软件编解码器（如 OMX.google.*）。兼容性更好，不依赖 GPU，但 CPU 负载高、可能发热。适合硬解不兼容的流",
            color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp)
        )
        Spacer(modifier = Modifier.height(20.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PlayerSettingsRightColumn(viewModel: AppViewModel) {
    val currentDeinterlace by viewModel.currentDeinterlace.collectAsState()
    val hdrMode by viewModel.hdrMode.collectAsState()
    val currentRtspTransport by viewModel.currentRtspTransport.collectAsState()
    val logLevel by viewModel.logLevel.collectAsState()
    val currentVo by viewModel.currentVo.collectAsState()
    val actualVo by viewModel.actualVo.collectAsState()
    val colorCompatMode by viewModel.colorCompatMode.collectAsState()
    val epgTz by viewModel.epgTimezoneOffset.collectAsState()
    val epgCache by viewModel.epgCacheSchedule.collectAsState()
    val groupMd by viewModel.groupMode.collectAsState()
    val perChannelEnabled by viewModel.perChannelSettingsEnabled.collectAsState()

    SectionTitle("EPG 设置")
    Spacer(modifier = Modifier.height(8.dp))
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        FilterChip(
            selected = false,
            onClick = { viewModel.setEpgTimezoneOffset((epgTz + 1) % 26) },
            label = { Text("时区: ${if (epgTz == 0) "默认" else "UTC${if (epgTz > 13) "-" else "+"}${if (epgTz > 13) (26 - epgTz) else epgTz}"}") },
            modifier = Modifier.tvFocusBorder()
        )
        FilterChip(
            selected = false,
            onClick = { viewModel.setEpgCacheSchedule((epgCache + 1) % 12) },
            label = { Text("缓存: ${listOf("关闭","1h","2h","3h","4h","6h","8h","12h","24h","48h","72h","7d")[epgCache]}") },
            modifier = Modifier.tvFocusBorder()
        )
        FilterChip(
            selected = false,
            onClick = { viewModel.setGroupMode((groupMd + 1) % 4) },
            label = { Text("分组: ${listOf("默认","二级分组","紧凑","展开")[groupMd]}") },
            modifier = Modifier.tvFocusBorder()
        )
    }
    Spacer(modifier = Modifier.height(20.dp))

    SectionTitle("反交错（Deinterlace）")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("消除隔行扫描视频（如 1080i TV 流）的横线梳齿。自动模式由 mpv 检测隔行内容")
    Spacer(modifier = Modifier.height(8.dp))
    val surfaceDirect = actualVo == "mediacodec_embed"
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(selected = currentDeinterlace == "no", onClick = { viewModel.setDeinterlace("no") }, label = { Text("关闭") }, modifier = Modifier.tvFocusBorder())
        FilterChip(
            selected = currentDeinterlace == "auto",
            onClick = { if (!surfaceDirect) viewModel.setDeinterlace("auto") },
            enabled = !surfaceDirect,
            label = { Text("自动") },
            modifier = Modifier.tvFocusBorder()
        )
    }
    if (surfaceDirect) {
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "当前为直写 Surface 播放，反交错不可用；下次换台会自动切到 GPU 路径并恢复",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
            modifier = Modifier.padding(horizontal = 4.dp)
        )
    }
    Spacer(modifier = Modifier.height(6.dp))
    val deinterlaceDesc = when (currentDeinterlace) {
        "no" -> "关闭反交错：逐行视频不受影响，隔行视频可能出现梳齿。适合所有逐行视频源（大部分网络流均为逐行）"
        "auto" -> "自动反交错：mpv 自动检测隔行内容并应用 yadif 滤镜。逐行视频不受影响，隔行视频（1080i TV）消除梳齿。与 hwdec=auto（直接输出）模式可能不兼容，需用 auto-copy 或 no"
        else -> "未知设置: $currentDeinterlace"
    }
    Text(text = deinterlaceDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    Spacer(modifier = Modifier.height(20.dp))

    SectionTitle("HDR 输出模式")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("HDR 视频的色彩处理方式。仅对 HDR 视频生效，非 HDR 视频不受影响")
    Spacer(modifier = Modifier.height(8.dp))
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        FilterChip(selected = hdrMode == HdrMode.DISABLE, onClick = { viewModel.setHdrMode(HdrMode.DISABLE) }, label = { Text("禁用") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = hdrMode == HdrMode.AUTO, onClick = { viewModel.setHdrMode(HdrMode.AUTO) }, label = { Text("自动") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = hdrMode == HdrMode.TONEMAP, onClick = { viewModel.setHdrMode(HdrMode.TONEMAP) }, label = { Text("色调映射") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = hdrMode == HdrMode.PASSTHROUGH, onClick = { viewModel.setHdrMode(HdrMode.PASSTHROUGH) }, label = { Text("直通") }, modifier = Modifier.tvFocusBorder())
    }
    Spacer(modifier = Modifier.height(6.dp))
    val hdrDesc = when (hdrMode) {
        HdrMode.DISABLE -> "禁用 HDR：强制 SDR 输出。所有视频按 bt.709/bt.1886 渲染，HDR 视频可能高光过曝"
        HdrMode.AUTO -> "自动模式：检测设备 HDR 能力，支持则交给系统自动切换 HDR 显示（直通），不支持则色调映射到 SDR"
        HdrMode.TONEMAP -> "HDR→SDR 色调映射：HDR 视频映射到 bt.709/bt.1886。信任 HDR10+ 动态元数据，自动选择算法（HDR10+→st2094-40, HDR10/HLG→bt.2390）"
        HdrMode.PASSTHROUGH -> "HDR 直通：HDR 视频按 bt.2020/pq 输出。需要显示器支持 HDR，否则画面可能过暗或色彩异常"
    }
    Text(text = hdrDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    Spacer(modifier = Modifier.height(20.dp))

    SectionTitle("色彩兼容模式")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("个别设备出现 HDR 过曝/发灰/偏色时开启。默认关闭，不改变现有正常画面；仅对 gpu / gpu-next 生效")
    Spacer(modifier = Modifier.height(8.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(
            checked = colorCompatMode,
            onCheckedChange = { viewModel.setColorCompatMode(it) },
            modifier = Modifier.tvFocusBorder()
        )
        Spacer(modifier = Modifier.width(12.dp))
        Text(
            text = if (colorCompatMode) "已开启（clip 映射 + bt.709 + 关闭 HDR hint）"
            else "已关闭（按 HDR 模式自动选择）",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp
        )
    }
    Spacer(modifier = Modifier.height(6.dp))
    // 颜色管线诊断：用户反馈过曝/发灰时直接看这行对号（不依赖信息弹窗里新增字段）
    val colorDiag = remember(colorCompatMode, actualVo) {
        runCatching {
            val p = viewModel.mpv
            val tm = p.getPropertyString("tone-mapping") ?: "-"
            val levels = p.getPropertyString("video-output-levels") ?: "-"
            val gamma = p.getPropertyString("video-params/gamma") ?: "-"
            // mpv 的源范围属性是 colorlevels；color-range 不是标准子属性，
            // 旧版本/旧构建若只认旧键，保留兜底避免诊断行整行失效
            val range = p.getPropertyString("video-params/colorlevels")
                ?: p.getPropertyString("video-params/color-range")
                ?: "-"
            val prim = p.getPropertyString("video-params/primaries") ?: "-"
            val vo = p.getPropertyString("vo") ?: "-"
            val hwdec = p.getPropertyString("hwdec-current") ?: "-"
            val targetPrim = p.getPropertyString("target-prim") ?: "-"
            val targetTrc = p.getPropertyString("target-trc") ?: "-"
            "当前画面：vo=$vo · 解码=$hwdec · 传输=$gamma · 色域=$prim · 色彩范围=$range · " +
                "色调映射=$tm · 输出范围=$levels · 目标原色=$targetPrim · 目标传输=$targetTrc"
        }.getOrDefault("当前画面：未开始播放")
    }
    Text(
        text = colorDiag,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 11.sp,
        modifier = Modifier.padding(horizontal = 4.dp)
    )
    Spacer(modifier = Modifier.height(20.dp))

    SectionTitle("RTSP 传输协议")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("RTSP 流的传输方式。TCP 更稳定（防火墙穿透），UDP 延迟更低但可能丢包")
    Spacer(modifier = Modifier.height(8.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(selected = currentRtspTransport == "tcp", onClick = { viewModel.setRtspTransport("tcp") }, label = { Text("TCP（推荐）") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = currentRtspTransport == "udp", onClick = { viewModel.setRtspTransport("udp") }, label = { Text("UDP（低延迟）") }, modifier = Modifier.tvFocusBorder())
    }
    Spacer(modifier = Modifier.height(6.dp))
    val rtspDesc = when (currentRtspTransport) {
        "tcp" -> "TCP 传输：RTSP over TCP，数据通过 TCP 通道传输。更稳定，防火墙穿透好，适合网络不稳定的环境。延迟略高"
        "udp" -> "UDP 传输：RTSP over UDP，数据通过 UDP 通道传输。延迟更低，但网络不稳定时可能丢包导致花屏。需要良好的网络环境"
        else -> "未知传输协议: $currentRtspTransport"
    }
    Text(text = rtspDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    Spacer(modifier = Modifier.height(20.dp))

    SectionTitle("日志等级")
    Spacer(modifier = Modifier.height(4.dp))
    SectionDesc("控制日志输出等级（app.log + logcat）。立即生效，无需重启")
    Spacer(modifier = Modifier.height(8.dp))
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        FilterChip(selected = logLevel == "error", onClick = { viewModel.setLogLevel("error") }, label = { Text("错误") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = logLevel == "warn", onClick = { viewModel.setLogLevel("warn") }, label = { Text("警告") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = logLevel == "info", onClick = { viewModel.setLogLevel("info") }, label = { Text("信息") }, modifier = Modifier.tvFocusBorder())
        FilterChip(selected = logLevel == "debug", onClick = { viewModel.setLogLevel("debug") }, label = { Text("调试") }, modifier = Modifier.tvFocusBorder())
    }
    Spacer(modifier = Modifier.height(6.dp))
    val logLevelDesc = when (logLevel) {
        "error" -> "仅输出错误信息。适合正式使用，日志量最小"
        "warn" -> "输出警告和错误。适合日常使用"
        "info" -> "输出信息、警告和错误（默认）。适合一般调试"
        "debug" -> "输出全部日志（含 trace）。适合深度调试，日志量很大"
        else -> "未知等级: $logLevel"
    }
    Text(text = logLevelDesc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 4.dp))
    Spacer(modifier = Modifier.height(20.dp))

    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.55f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().tvFocusBorder().focusable().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(text = "频道记忆", color = MaterialTheme.colorScheme.primary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = "开启后，每个频道会自动记忆各自的输出/解码/HDR 设置。切换频道时自动应用，无需手动保存。在主菜单「清除频道专属设置」可重置当前频道。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp, lineHeight = 15.sp
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
            Switch(checked = perChannelEnabled, onCheckedChange = { viewModel.setPerChannelSettingsEnabled(it) })
        }
    }
    Spacer(modifier = Modifier.height(20.dp))

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(text = "使用说明", color = MaterialTheme.colorScheme.primary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "1. MPV 功能最完整（EQ/AB循环/逐帧/截图/HDR）\n2. 黑屏有声音时切换 vo 到 mediacodec_embed\n3. 切换 vo 后会自动重新加载当前频道\n4. 点击右上角重置按钮可恢复默认值",
                color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, lineHeight = 18.sp
            )
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        color = MaterialTheme.colorScheme.primary,
        fontSize = 14.sp,
        fontWeight = FontWeight.SemiBold
    )
}

@Composable
private fun SectionDesc(text: String) {
    Text(
        text = text,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 12.sp
    )
}
/**
 * APTV（iOS 风格）播放器设置面板：单列布局，圆角分组卡片 + iOS 选择行 + 开关行。
 * 仅在竖屏 APTV 模式下使用，横屏/TV 仍走 [PlayerSettingsPanel] 原有双列布局。
 */
@Composable
private fun PlayerSettingsPanelAptv(viewModel: AppViewModel) {
    val currentPlayerType by viewModel.playerType.collectAsState()
    val currentVo by viewModel.currentVo.collectAsState()
    val currentHwdec by viewModel.currentHwdec.collectAsState()
    val actualHwdec by viewModel.actualHwdec.collectAsState()
    val hwdecBlacklisted by viewModel.hwdecBlacklisted.collectAsState()
    val currentRtspTransport by viewModel.currentRtspTransport.collectAsState()
    val currentDeinterlace by viewModel.currentDeinterlace.collectAsState()
    val logLevel by viewModel.logLevel.collectAsState()
    val hdrMode by viewModel.hdrMode.collectAsState()
    val hardwareDecode by viewModel.hardwareDecode.collectAsState()
    val timeoutSwitch by viewModel.timeoutSwitchSource.collectAsState()
    val reconnectIdx by viewModel.reconnectIndex.collectAsState()
    val screenLocked by viewModel.screenLock.collectAsState()
    val actualVo by viewModel.actualVo.collectAsState()
    val renderPathReason by viewModel.renderPathReason.collectAsState()

    val exoSurfaceView by viewModel.exoSurfaceView.collectAsState()
    val epgTz by viewModel.epgTimezoneOffset.collectAsState()
    val epgCache by viewModel.epgCacheSchedule.collectAsState()
    val groupMd by viewModel.groupMode.collectAsState()
    val perChannelEnabled by viewModel.perChannelSettingsEnabled.collectAsState()

    // 全屏覆盖页（竖屏弹窗）：Dialog 独立窗口无法采样主窗口背景 —— 静态光泽玻璃，可模糊透出下层界面观感。
    // 分屏详情宿主内（LocalSplitDetailEmbedded）：不包整块玻璃底座，让 SettingsGroup 分组卡片一块一块呈现
    val liquidGlass = com.iptv.scanner.editor.pro.ui.LocalLiquidGlass.current
    val useGlass = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported() &&
        android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S
    val embedded = LocalSplitDetailEmbedded.current
    val body: @Composable () -> Unit = {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .verticalScroll(rememberScrollState())
        ) {
            AptvPanelHeader(
                title = "播放器设置",
                subtitle = "内核 / 解码 / 输出 / 增强",
                onClose = { viewModel.togglePlayerSettings() }
            )

            SettingsGroup("播放器内核") {
                SelectionGroup(
                    title = "内核",
                    options = listOf("MPV" to "MPV（推荐）", "EXO" to "ExoPlayer"),
                    selectedKey = currentPlayerType.name,
                    onSelect = { key ->
                        if (key == "MPV") viewModel.switchPlayerType(PlayerType.MPV)
                        else viewModel.switchPlayerType(PlayerType.EXO)
                    }
                )
                AptvRowDivider()
                Text(
                    text = currentPlayerType.description,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }


            if (currentPlayerType == PlayerType.EXO) {
                SettingsGroup("视频渲染") {
                    SelectionGroup(
                        title = "渲染视图",
                        options = listOf("true" to "SurfaceView（推荐）", "false" to "TextureView"),
                        selectedKey = exoSurfaceView.toString(),
                        onSelect = { viewModel.setExoSurfaceView(it.toBoolean()) }
                    )
                    AptvRowDivider()
                    Text(
                        text = "画面黑屏或停在第一帧时切换渲染视图。SurfaceView 兼容性最好",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                }
            }

            SettingsGroup("播放增强") {
                SelectionGroup(
                    title = "超时换源",
                    options = listOf(
                        "0" to "5s", "1" to "8s", "2" to "12s",
                        "3" to "15s", "4" to "20s", "5" to "30s"
                    ),
                    selectedKey = timeoutSwitch.toString(),
                    onSelect = { viewModel.setTimeoutSwitchSource(it.toInt()) }
                )
                AptvRowDivider()
                SelectionGroup(
                    title = "断线重连",
                    options = listOf(
                        "0" to "关闭", "1" to "3s", "2" to "5s",
                        "3" to "10s", "4" to "15s", "5" to "20s"
                    ),
                    selectedKey = reconnectIdx.toString(),
                    onSelect = { viewModel.setReconnectIndex(it.toInt()) }
                )
                AptvRowDivider()
                SwitchRow(
                    title = "画面锁定（换源不黑屏）",
                    checked = screenLocked,
                    onCheckedChange = { viewModel.setScreenLock(it) }
                )

            }

            if (currentPlayerType == PlayerType.MPV) {
                SettingsGroup("视频输出") {
                    SelectionGroup(
                        title = "VO",
                        options = listOf(
                            "gpu" to "GPU（EGL）",
                            "gpu-next" to "GPU-Next（EGL）",
                            "mediacodec_embed" to "MediaCodec（实验）"
                        ),
                        selectedKey = currentVo,
                        onSelect = { viewModel.setPlayerVo(it) }
                    )
                    AptvRowDivider()
                    val voDesc = when (currentVo) {
                        "gpu" -> "GPU 渲染：经典 EGL 后端，支持 HDR/OSD/shader，兼容大多数 GPU。部分 GPU（如 Mali-G76）可能黑屏"
                        "gpu-next" -> "GPU-Next 渲染：新一代 EGL 后端（render API），渲染路径与 GPU 不同。支持 HDR/OSD/shader，GPU 黑屏时可尝试此选项"
                        "mediacodec_embed" -> "实验性：MediaCodec 直接写 Surface（零拷贝，不占 GPU 滤镜），需重启播放器后生效。部分电视冷启动会随机退出，遇到时重启并切回 GPU。App 侧弹窗与 OSD 正常；mpv 画面层不可用：字幕不显示、截图失败、翻转/裁剪等视频滤镜无效。"
                        else -> "未知 vo: $currentVo"
                    }
                    Text(
                        text = voDesc,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                    renderPathText(actualVo, renderPathReason)?.let { pathText ->
                        Text(
                            text = pathText,
                            color = MaterialTheme.colorScheme.primary,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                    }
                }

                SettingsGroup("硬件解码") {
                    val hwdecOptions = when (currentVo) {
                        "mediacodec_embed" -> listOf("mediacodec" to "mediacodec（固定）")
                        // 电视/盒子：copy-back 与 AImageReader 直通都会崩，只保留软解
                        else -> if (viewModel.isArm32TvDevice) {
                            listOf("no" to "no（软解）")
                        } else if (viewModel.isHandheldDevice) {
                            // 手机/平板：mediacodec 经 AImageReader 直通，不回落 CPU
                            listOf(
                                "mediacodec" to "mediacodec（直通，推荐）",
                                "auto-copy" to "auto-copy（兼容）",
                                "no" to "no（软解）"
                            )
                        } else listOf(
                            "auto-copy" to "auto-copy（推荐）",
                            "auto" to "auto（4K HDR）",
                            "no" to "no（软解）"
                        )
                    }
                    SelectionGroup(
                        title = "HWDEC",
                        options = hwdecOptions,
                        selectedKey = currentHwdec,
                        onSelect = { viewModel.setPlayerHwdec(it) }
                    )
                    AptvRowDivider()
                    val hwdecDesc = when (currentHwdec) {
                        "auto-copy" -> "自动选择硬件解码器，解码后拷贝到 CPU 内存再上传 GPU。兼容性好，支持视频滤镜（翻转/裁剪/360°）。4K HDR 可能卡顿"
                        "auto" -> "自动选择最佳硬解，优先直接输出（零拷贝）。4K HDR 流畅，但视频翻转/裁剪/360° 滤镜可能不可用"
                        "mediacodec" -> "MediaCodec 硬件解码：vo=mediacodec_embed 时直接写 Surface（实验性，重启生效）；vo=gpu/gpu-next 时经 AImageReader 直通，不回落 CPU"
                        "no" -> "纯软件解码。兼容性最好但耗电，CPU 解码可能慢"
                        else -> "未知 hwdec: $currentHwdec"
                    }
                    Text(
                        text = hwdecDesc,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                    Text(
                        text = hwdecActualText(actualHwdec, hwdecBlacklisted),
                        color = if (actualHwdec == "no" && currentHwdec != "no") MaterialTheme.colorScheme.error
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                }
            }

            if (currentPlayerType == PlayerType.EXO) {
                SettingsGroup("解码模式") {
                    SelectionGroup(
                        title = "模式",
                        options = listOf("true" to "硬件解码（推荐）", "false" to "软件解码"),
                        selectedKey = hardwareDecode.toString(),
                        onSelect = { viewModel.setHardwareDecode(it.toBoolean()) }
                    )
                    AptvRowDivider()
                    Text(
                        text = if (hardwareDecode) "硬件解码：使用 Android MediaCodec 硬件加速解码。功耗低、速度快，但部分 4K/HDR 流可能不兼容。遇到花屏/卡顿时可尝试软解" else "软件解码：使用 Android 系统自带的软件编解码器（如 OMX.google.*）。兼容性更好，不依赖 GPU，但 CPU 负载高、可能发热。适合硬解不兼容的流",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                }
            }

            SettingsGroup("EPG 设置") {
                val tzOptions = (0..25).map { i ->
                    i.toString() to (if (i == 0) "默认" else "UTC${if (i > 13) "-" else "+"}${if (i > 13) (26 - i) else i}")
                }
                SelectionGroup(
                    title = "时区",
                    options = tzOptions,
                    selectedKey = epgTz.toString(),
                    onSelect = { viewModel.setEpgTimezoneOffset(it.toInt()) }
                )
                AptvRowDivider()
                val cacheOptions = listOf(
                    "0" to "关闭", "1" to "1h", "2" to "2h", "3" to "3h",
                    "4" to "4h", "5" to "6h", "6" to "8h", "7" to "12h",
                    "8" to "24h", "9" to "48h", "10" to "72h", "11" to "7d"
                )
                SelectionGroup(
                    title = "缓存",
                    options = cacheOptions,
                    selectedKey = epgCache.toString(),
                    onSelect = { viewModel.setEpgCacheSchedule(it.toInt()) }
                )
                AptvRowDivider()
                val groupOptions = listOf("0" to "默认", "1" to "二级分组", "2" to "紧凑", "3" to "展开")
                SelectionGroup(
                    title = "分组",
                    options = groupOptions,
                    selectedKey = groupMd.toString(),
                    onSelect = { viewModel.setGroupMode(it.toInt()) }
                )
            }

            SettingsGroup("反交错") {
                SelectionGroup(
                    title = "模式",
                    options = listOf("no" to "关闭", "auto" to "自动"),
                    selectedKey = currentDeinterlace,
                    onSelect = { viewModel.setDeinterlace(it) }
                )
                AptvRowDivider()
                val deinterlaceDesc = when (currentDeinterlace) {
                    "no" -> "关闭反交错：逐行视频不受影响，隔行视频可能出现梳齿。适合所有逐行视频源（大部分网络流均为逐行）"
                    "auto" -> "自动反交错：mpv 自动检测隔行内容并应用 yadif 滤镜。逐行视频不受影响，隔行视频（1080i TV）消除梳齿。与 hwdec=auto（直接输出）模式可能不兼容，需用 auto-copy 或 no"
                    else -> "未知设置: $currentDeinterlace"
                }
                Text(
                    text = deinterlaceDesc,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            SettingsGroup("HDR 输出模式") {
                SelectionGroup(
                    title = "模式",
                    options = listOf(
                        "DISABLE" to "禁用",
                        "AUTO" to "自动",
                        "TONEMAP" to "色调映射",
                        "PASSTHROUGH" to "直通"
                    ),
                    selectedKey = hdrMode.name,
                    onSelect = { key -> viewModel.setHdrMode(HdrMode.valueOf(key)) }
                )
                AptvRowDivider()
                val hdrDesc = when (hdrMode) {
                    HdrMode.DISABLE -> "禁用 HDR：强制 SDR 输出。所有视频按 bt.709/bt.1886 渲染，HDR 视频可能高光过曝"
                    HdrMode.AUTO -> "自动模式：检测设备 HDR 能力，支持则交给系统自动切换 HDR 显示（直通），不支持则色调映射到 SDR"
                    HdrMode.TONEMAP -> "HDR→SDR 色调映射：HDR 视频映射到 bt.709/bt.1886。信任 HDR10+ 动态元数据，自动选择算法（HDR10+→st2094-40, HDR10/HLG→bt.2390）"
                    HdrMode.PASSTHROUGH -> "HDR 直通：HDR 视频按 bt.2020/pq 输出。需要显示器支持 HDR，否则画面可能过暗或色彩异常"
                }
                Text(
                    text = hdrDesc,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            SettingsGroup("RTSP 传输协议") {
                SelectionGroup(
                    title = "协议",
                    options = listOf("tcp" to "TCP（推荐）", "udp" to "UDP（低延迟）"),
                    selectedKey = currentRtspTransport,
                    onSelect = { viewModel.setRtspTransport(it) }
                )
                AptvRowDivider()
                val rtspDesc = when (currentRtspTransport) {
                    "tcp" -> "TCP 传输：RTSP over TCP，数据通过 TCP 通道传输。更稳定，防火墙穿透好，适合网络不稳定的环境。延迟略高"
                    "udp" -> "UDP 传输：RTSP over UDP，数据通过 UDP 通道传输。延迟更低，但网络不稳定时可能丢包导致花屏。需要良好的网络环境"
                    else -> "未知传输协议: $currentRtspTransport"
                }
                Text(
                    text = rtspDesc,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            SettingsGroup("日志等级") {
                SelectionGroup(
                    title = "等级",
                    options = listOf(
                        "error" to "错误",
                        "warn" to "警告",
                        "info" to "信息",
                        "debug" to "调试"
                    ),
                    selectedKey = logLevel,
                    onSelect = { viewModel.setLogLevel(it) }
                )
                AptvRowDivider()
                val logLevelDesc = when (logLevel) {
                    "error" -> "仅输出错误信息。适合正式使用，日志量最小"
                    "warn" -> "输出警告和错误。适合日常使用"
                    "info" -> "输出信息、警告和错误（默认）。适合一般调试"
                    "debug" -> "输出全部日志（含 trace）。适合深度调试，日志量很大"
                    else -> "未知等级: $logLevel"
                }
                Text(
                    text = logLevelDesc,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            SettingsGroup("频道记忆") {
                SwitchRow(
                    title = "启用频道专属设置",
                    checked = perChannelEnabled,
                    onCheckedChange = { viewModel.setPerChannelSettingsEnabled(it) }
                )
                AptvRowDivider()
                Text(
                    text = "开启后，每个频道会自动记忆各自的输出/解码/HDR 设置。切换频道时自动应用，无需手动保存。在主菜单「清除频道专属设置」可重置当前频道。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    lineHeight = 16.sp,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }

            Spacer(modifier = Modifier.height(20.dp))
        }
    }
    if (embedded) {
        // 分屏详情宿主内：透出画布，SettingsGroup 分组卡片直接一块一块呈现
        body()
    } else {
        // 竖屏弹窗：整块静态玻璃底座（Dialog 独立窗口无法采样主窗口背景）
        com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
            enabled = useGlass,
            cornerRadius = 0.dp,
            staticGlass = true,
            fallbackColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.surface.copy(alpha = if (useGlass) 0.82f else 1f))
        ) { body() }
    }
}

/** 实际生效的 vo 展示文案 */
private fun voActualText(actual: String, selected: String, autoFallback: Boolean): String {
    val actualPart = if (actual.isBlank()) "实际生效：未知（尚未开始播放）" else "实际生效：$actual"
    return when {
        autoFallback -> "$actualPart · 直写 Surface 起播失败，已自动回退到 GPU（重新选择即可重试）"
        actual.isNotBlank() && actual != selected -> "$actualPart（设置值：$selected）"
        else -> actualPart
    }
}

/** 「当前为什么走这条渲染路径」：自适应切 GPU 时给出原因，直写时提示不可用的能力 */
private fun renderPathText(actualVo: String, reason: String?): String? = when (reason) {
    "subtitle" -> "当前路径：GPU 路径（当前内容有字幕轨，需要 mpv 渲染字幕）"
    "filter" -> "当前路径：GPU 路径（已启用去色带/反交错/超分等滤镜）"
    "fallback" -> "当前路径：GPU 路径（直写 Surface 起播失败，已自动回退）"
    else -> when (actualVo) {
        "mediacodec_embed" -> "当前路径：直写 Surface（无字幕/无滤镜；字幕、滤镜、截图暂不可用）"
        "gpu", "gpu-next" -> "当前路径：GPU 路径（手动选择）"
        else -> null
    }
}

/** 实际生效的 hwdec 展示文案（读取 mpv hwdec-current） */
private fun hwdecActualText(actual: String, blacklisted: Boolean): String {
    val actualPart = when {
        actual.isBlank() -> "实际生效：未知（尚未开始播放）"
        actual == "no" -> "实际生效：软解（no）"
        else -> "实际生效：$actual"
    }
    return if (blacklisted) {
        "$actualPart · 上次硬解异常退出，已自动降级为软解；可点「重试硬件解码」再试一次"
    } else {
        actualPart
    }
}
