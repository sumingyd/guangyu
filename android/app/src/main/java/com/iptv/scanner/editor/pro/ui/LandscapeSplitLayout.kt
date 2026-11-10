package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Cast
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Info
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.player.PlayMode
import com.iptv.scanner.editor.pro.player.ProgressHelper
import com.iptv.scanner.editor.pro.ui.theme.GlassPanel
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvFocusable
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import kotlinx.coroutines.delay

/**
 * 横屏分屏播放布局（TV/横屏新默认布局）：
 * - 左列（58%）：顶部频道信息条 + 16:9 视频窗口 + 常驻控制条（节目/进度/播放/切台/工具/全屏）
 * - 右列（42%）：常驻暗玻璃面板 = 顶部收藏/投屏/信息 + 分段控件（分类/频道/节目/信息）+ 内容区
 *   （复用竖屏播放页视频下方4大内容组件）
 *
 * 全屏模式（setLandscapeSplitMode(false)）保持原有 TvPlayerLayout 沉浸式布局不变。
 *
 * 视觉规范（与项目硬约束对齐）：
 * - 右列面板使用 GlassPanel(overlayDark=true)：暗玻璃霜层 + DarkOverlayTheme 白系文字
 * - 主色 AptvAccent 橙红；分段控件选中态白亮玻璃凸起
 * - 视频窗口圆角黑底（与竖屏画布视频窗口一致）；SurfaceView 由 movableContent 移动，不重建
 */
@Composable
internal fun TvSplitLayout(
    viewModel: AppViewModel,
    primaryPlayer: @Composable () -> Unit
) {
    val oc = rememberPlayerOverlayColors()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val focusManager = LocalFocusManager.current
    val displayInfo by viewModel.channelDisplayInfo.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val paused by viewModel.mpv.paused.collectAsState()
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    // 曾成功起播标记：换台加载中 fileLoaded 会短暂为 false，
    // 手势层不能因此整块移除（否则上下滑切台被禁用）。
    var hasEverLoaded by remember { mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(fileLoaded) {
        if (fileLoaded) hasEverLoaded = true
    }
    val muted by viewModel.mpv.muted.collectAsState()
    val currentEpg by viewModel.currentEpg.collectAsState()

    val currentProgram = remember(currentEpg) {
        ProgressHelper.findCurrentProgram(currentEpg, System.currentTimeMillis())
    }
    val isFavorite = currentIdx >= 0 && favorites.contains(currentIdx)

    // 进度数据（1秒刷新）
    var tick by remember { mutableStateOf(0L) }
    androidx.compose.runtime.LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(1000L)
        }
    }

    // TV 遥控器初焦：进入分屏播放页（或从全屏切回）时把焦点请求到视频区。
    // 没有初焦时 Compose 焦点系统无活跃焦点节点，方向键会落到 Activity 兜底
    // （全局切台/seek），右侧面板与控制栏（含全屏按钮）永远无法用遥控器到达。
    val videoFocusRequester = remember { FocusRequester() }
    // 注意：MainPlayerScreen 是常驻组合（首页只是覆盖层），TvSplitLayout 不会 dispose，
    // LaunchedEffect(Unit) 只在首次进入时执行——BACK 回首页再进分屏不会再触发。
    // 因此 key 用 showHome/landscapeSplitMode：每次真正"进入分屏播放页"都重新请求初焦。
    val splitShowHome by viewModel.showHome.collectAsState()
    val splitSplitMode by viewModel.landscapeSplitMode.collectAsState()
    androidx.compose.runtime.LaunchedEffect(splitShowHome, splitSplitMode) {
        if (splitShowHome || !splitSplitMode) return@LaunchedEffect
        repeat(15) {
            delay(150)
            try {
                videoFocusRequester.requestFocus()
                return@LaunchedEffect
            } catch (_: Exception) {
            }
        }
    }
    // 焦点归零兜底：电视端异步加载重组可能清掉初焦，方向键落 Activity 兜底后递增 tick，
    // 这里把焦点重新请求到视频区（按键驱动，不赌加载时序）。
    // 注意：Activity 兜底只在"焦点树真无活跃焦点"时才递增 tick（见 splitTreeHasFocus），
    // 边缘方向搜索失败（焦点还在）不会走到这里，避免焦点被强行拉回视频区。
    val focusResetTick by viewModel.splitFocusResetTick.collectAsState()
    androidx.compose.runtime.LaunchedEffect(focusResetTick) {
        if (focusResetTick > 0L) {
            // 小步重试：电视端重组/异步加载时序下单次 requestFocus 可能抛异常落空
            repeat(10) { attempt ->
                if (attempt > 0) delay(100)
                try {
                    videoFocusRequester.requestFocus()
                    return@LaunchedEffect
                } catch (_: Exception) {
                }
            }
        }
    }

    // TV 遥控器焦点隔离：MainPlayerScreen 是常驻组合，首页只是覆盖层——
    // 首页显示时若不禁用本子树焦点，TAB/方向键会落到被覆盖的返回按钮/视频区/
    // 控制栏等不可见元素上（"切着切着焦点消失"的根源）。
    // 注意：必须用 remember(splitShowHome) 固化 modifier——直接在 focusProperties
    // block 里读委托 state 会被强跳过模式 memoize（modifier 永不更新，canFocus
    // 缓存住首次求值结果），导致分屏内方向键几何搜索把右列全部过滤掉。
    val splitFocusIsolation = remember(splitShowHome) {
        val allowFocus = !splitShowHome
        Modifier.focusProperties { canFocus = allowFocus }
    }
    // 统一画布背景（与横屏首页一致）：深/浅主题渐变底 + 三色光斑。
    // 修复分屏左列无背景透出窗口白底、深色主题下顶栏浅色文字不可见的问题
    val canvasDark = MaterialTheme.colorScheme.background.luminance() < 0.5f
    Row(
        modifier = Modifier
            .fillMaxSize()
            .then(splitFocusIsolation)
            // 同步维护"焦点树是否持有焦点"标记，供 Activity DPAD 兜底区分
            // "真无焦点→归零恢复"与"边缘搜索失败→原地保持"两种情况
            .onFocusChanged { viewModel.splitTreeHasFocus = it.hasFocus }
            .background(MaterialTheme.colorScheme.background)
            .drawBehind {
                drawRect(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        listOf(tvPalette.canvasStart, tvPalette.canvasEnd)
                    )
                )
                val g = if (canvasDark) 0.32f else 0.24f
                drawCircle(
                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                        listOf(tvPalette.spotBlue.copy(alpha = g), androidx.compose.ui.graphics.Color.Transparent)
                    ),
                    radius = size.width * 0.85f,
                    center = androidx.compose.ui.geometry.Offset(size.width * 0.15f, size.height * 0.12f)
                )
                drawCircle(
                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                        listOf(tvPalette.spotPurple.copy(alpha = g * 0.85f), androidx.compose.ui.graphics.Color.Transparent)
                    ),
                    radius = size.width * 0.75f,
                    center = androidx.compose.ui.geometry.Offset(size.width * 0.95f, size.height * 0.52f)
                )
                drawCircle(
                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                        listOf(tvPalette.spotGreen.copy(alpha = g * 0.7f), androidx.compose.ui.graphics.Color.Transparent)
                    ),
                    radius = size.width * 0.7f,
                    center = androidx.compose.ui.geometry.Offset(size.width * 0.2f, size.height * 0.95f)
                )
            }
            .systemBarsPadding()
            .padding(6.dp)
    ) {
        // ==================== 左列：视频 + 控制条 ====================
        Column(
            modifier = Modifier
                .weight(0.58f)
                .fillMaxHeight()
                .padding(end = 6.dp)
        ) {
            // 顶部信息条：返回首页 + 台标 + 频道名 + 分组
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(44.dp)
                    .padding(bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = { viewModel.showHomeScreen() },
                    modifier = Modifier.size(36.dp).tvFocusBorder()
                ) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "返回首页",
                        tint = oc.iconTint,
                        modifier = Modifier.size(22.dp)
                    )
                }
                Spacer(modifier = Modifier.width(4.dp))
                // 台标（浅色主题下白色台标加 surfaceVariant 衬底，避免幽灵化）
                if (displayInfo.logo.isNotEmpty()) {
                    Box(
                        modifier = Modifier
                            .size(34.dp)
                            .clip(RoundedCornerShape(5.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant),
                        contentAlignment = Alignment.Center
                    ) {
                        AsyncImage(
                            model = displayInfo.logo,
                            contentDescription = displayInfo.name,
                            modifier = Modifier.fillMaxSize().padding(3.dp),
                            contentScale = ContentScale.Fit
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Text(
                    text = displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                if (displayInfo.group.isNotEmpty()) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Surface(
                        color = AptvAccent.copy(alpha = 0.12f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = displayInfo.group,
                            color = tvPalette.accentText,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            maxLines = 1
                        )
                    }
                }
            }

            // 视频窗口：圆角黑底（movableContent 移动 SurfaceView，不重建）
            val videoWidth by viewModel.mpv.videoWidth.collectAsState()
            val videoHeight by viewModel.mpv.videoHeight.collectAsState()
            val videoAspectRatio = if (videoWidth > 0 && videoHeight > 0) {
                videoWidth.toFloat() / videoHeight.toFloat()
            } else 16f / 9f
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .focusRequester(videoFocusRequester)
                    // TV 遥控器：视频区可聚焦。UP/DOWN 永不拦截（焦点导航到控制栏/上方）；
                    // 仅回看/本地文件时 LEFT/RIGHT 拦截为 seek，直播时放行给焦点导航（RIGHT 进右列面板）；
                    // OK = 焦点移到正下方控制栏
                    .tvFocusable(cornerRadius = 8, focusedScale = 1f)
                    .onPreviewKeyEvent { ev ->
                        if (ev.type != KeyEventType.KeyDown) {
                            return@onPreviewKeyEvent false
                        }
                        when (ev.key) {
                            Key.DirectionLeft -> {
                                val mode = viewModel.playbackState.value.mode
                                if (mode.isCatchup || viewModel.currentChannel.value == null) {
                                    viewModel.mpv.seekRelative(-10.0)
                                    true
                                } else {
                                    false
                                }
                            }
                            Key.DirectionRight -> {
                                val mode = viewModel.playbackState.value.mode
                                if (mode.isCatchup || viewModel.currentChannel.value == null) {
                                    viewModel.mpv.seekRelative(10.0)
                                    true
                                } else {
                                    false
                                }
                            }
                            // OK 键：焦点移到正下方控制栏（上一频/播放/…/全屏），
                            // 全屏按钮即可通过遥控器 RIGHT+OK 到达；右侧面板可从控制栏 RIGHT 几何进入
                            Key.DirectionCenter, Key.Enter -> {
                                focusManager.moveFocus(FocusDirection.Down)
                                true
                            }
                            else -> false
                        }
                    },
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        .aspectRatio(videoAspectRatio)
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color.Black)
                ) {
                    primaryPlayer()
                    // 视频触控层：单击暂停/恢复 + 双击全屏 + 上下滑切台（与竖屏一致）
                    // 门控放宽：只有「从未起播」才不挂手势层；换台加载中仍允许上下滑切台，
                    // 单击暂停在未起播时忽略。
                    if (fileLoaded || hasEverLoaded) {
                        val haptic = LocalHapticFeedback.current
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .pointerInput(Unit) {
                                    detectTapGestures(
                                        onTap = {
                                            if (!viewModel.mpv.fileLoaded.value) return@detectTapGestures
                                            if (viewModel.mpv.paused.value) viewModel.mpv.setPause(false)
                                            else viewModel.mpv.setPause(true)
                                        },
                                        onDoubleTap = {
                                            viewModel.setLandscapeSplitMode(false)
                                        }
                                    )
                                }
                                .pointerInput(Unit) {
                                    var totalY = 0f
                                    var triggered = false
                                    detectVerticalDragGestures(
                                        onDragStart = { totalY = 0f; triggered = false },
                                        onDragEnd = { totalY = 0f; triggered = false },
                                        onVerticalDrag = { change, dragAmount ->
                                            change.consume()
                                            totalY += dragAmount
                                            val threshold = 80f
                                            if (!triggered && kotlin.math.abs(totalY) > threshold) {
                                                triggered = true
                                                if (totalY < 0) viewModel.prevChannel() else viewModel.nextChannel()
                                                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                                            }
                                        }
                                    )
                                }
                        )
                    }
                }
            }

            // ==================== 视频下方复合面板 ====================
            // 重排后的控制区：徽章标识行 + 最近节目单 + 实时频谱 + 单行核心控制
            // （原信息行/进度行的内容已上移至徽章行与节目单块，控制行精简为单行）
            GlassPanel(
                liquidGlass = liquidGlass,
                cornerRadius = 12.dp,
                overlayDark = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 7.dp)
                ) {
                    // 行1：徽章标识行（频道号/状态/收藏 + 全量媒体传输徽章，横向滚动）
                    SplitBadgeRow(viewModel = viewModel, isFavorite = isFavorite)

                    // 行间分隔条
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 6.dp)
                            .height(1.dp)
                            .background(tvPalette.borderSubtle)
                    )

                    // 行2：最近节目单（当前节目 LIVE + 后续预告）
                    SplitEpgBlock(viewModel = viewModel, currentProgram = currentProgram, tick = tick)

                    // 行间分隔条
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 6.dp)
                            .height(1.dp)
                            .background(tvPalette.borderSubtle)
                    )

                    // 行3：实时频谱（与右侧信息 Tab 共用采样，引用计数共存）
                    SplitSpectrumBlock(viewModel = viewModel)

                    // 行间分隔条
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 6.dp)
                            .height(1.dp)
                            .background(tvPalette.borderSubtle)
                    )

                    // 行4：单行核心控制（上一台/播放/下一台/静音/停止 | 收藏/工具/设置/全屏）
                    Spacer(modifier = Modifier.height(5.dp))
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        // 上一台
                        IconButton(onClick = { viewModel.prevChannel() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(Icons.Default.SkipPrevious, "上一个频道", tint = oc.iconTint, modifier = Modifier.size(18.dp))
                        }
                        // 播放/暂停
                        IconButton(onClick = { viewModel.mpv.setPause(!paused) }, modifier = Modifier.size(38.dp).tvFocusBorder()) {
                            Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(24.dp))
                        }
                        // 下一台
                        IconButton(onClick = { viewModel.nextChannel() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(Icons.Default.SkipNext, "下一个频道", tint = oc.iconTint, modifier = Modifier.size(18.dp))
                        }
                        // 静音
                        IconButton(onClick = { viewModel.mpv.setMute(!muted) }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(
                                if (muted) Icons.Default.VolumeOff else Icons.Default.VolumeUp,
                                contentDescription = if (muted) "取消静音" else "静音",
                                tint = if (muted) oc.iconTintActive else oc.iconTint,
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        // 停止
                        IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(17.dp))
                        }
                        Spacer(modifier = Modifier.weight(1f))
                        // 收藏
                        IconButton(onClick = { viewModel.toggleFavorite() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(
                                if (isFavorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                                contentDescription = "收藏",
                                tint = if (isFavorite) tvPalette.favorite else oc.iconTint,
                                modifier = Modifier.size(17.dp)
                            )
                        }
                        // 播放工具
                        IconButton(onClick = { viewModel.togglePlayerToolsPanel() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(Icons.Default.MoreVert, "播放工具", tint = oc.iconTint, modifier = Modifier.size(17.dp))
                        }
                        // 播放器设置
                        IconButton(onClick = { viewModel.togglePlayerSettings() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(Icons.Default.Settings, "播放器设置", tint = oc.iconTint, modifier = Modifier.size(17.dp))
                        }
                        // 全屏：切回传统全屏布局
                        IconButton(onClick = { viewModel.setLandscapeSplitMode(false) }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                            Icon(
                                Icons.Default.Fullscreen,
                                contentDescription = "全屏",
                                tint = oc.iconTint,
                                modifier = Modifier.size(19.dp)
                            )
                        }
                    }
                }
            }
        }

        // ==================== 右列：常驻面板（竖屏4大内容） ====================
        GlassPanel(
            liquidGlass = liquidGlass,
            cornerRadius = 12.dp,
            overlayDark = true,
            modifier = Modifier
                .weight(0.42f)
                .fillMaxHeight()
        ) {
            SplitSidePanel(viewModel = viewModel)
        }
    }
}

/**
 * 分屏右侧常驻面板：收藏/投屏/信息按钮行 + 分段控件 + 4大内容区。
 * GlassPanel(overlayDark) 内部已是 DarkOverlayTheme 白系作用域。
 */
@Composable
private fun SplitSidePanel(viewModel: AppViewModel) {
    val oc = rememberPlayerOverlayColors()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val currentChannel by viewModel.currentChannel.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val dlnaConnected by viewModel.dlnaConnected.collectAsState()
    val player = viewModel.mpv
    val fileLoaded by player.fileLoaded.collectAsState()

    // 占位条件对齐竖屏 PlayerDynamicContent：只有「首次进入且从未起播」才显示「未在播放」。
    // 换台时 mpv 会短暂置 fileLoaded=false，若整块替换成加载态，分屏右栏的 tab/列表子树
    // 会被销毁重建，导致滚动位置丢失与整块重绘。
    var hasEverLoaded by remember { mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(fileLoaded) {
        if (fileLoaded) hasEverLoaded = true
    }

    // 本地文件 vs 订阅频道（与竖屏 PortraitPlayerDynamicContent 一致）
    val isLocalFile = currentChannel == null || currentIdx < 0

    var selectedTab by remember { mutableStateOf(0) }
    val tabs = if (isLocalFile) {
        listOf("信息", "最近文件")
    } else {
        listOf("分类", "频道", "节目", "信息")
    }
    androidx.compose.runtime.LaunchedEffect(tabs.size) {
        if (selectedTab >= tabs.size) selectedTab = 0
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // 顶行：收藏 / 投屏 / 信息（右侧对齐，图2右上角按钮组）
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
                .padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(
                onClick = { viewModel.toggleFavorite() },
                modifier = Modifier.size(34.dp).tvFocusBorder()
            ) {
                Icon(
                    if (favorites.contains(currentIdx)) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = "收藏",
                    tint = if (favorites.contains(currentIdx)) tvPalette.favorite else oc.iconTint,
                    modifier = Modifier.size(20.dp)
                )
            }
            IconButton(
                onClick = { viewModel.toggleDlnaPanel() },
                modifier = Modifier.size(34.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.Cast,
                    contentDescription = "投屏",
                    tint = if (dlnaConnected != null) tvPalette.accentGraphic else oc.iconTint,
                    modifier = Modifier.size(20.dp)
                )
            }
            IconButton(
                onClick = { viewModel.toggleChannelInfo() },
                modifier = Modifier.size(34.dp).tvFocusBorder()
            ) {
                Icon(Icons.Default.Info, "频道信息", tint = oc.iconTint, modifier = Modifier.size(20.dp))
            }
        }

        // 分段控件：选中态用主题描边/底色（原实现写死白色半透明，
        // 浅色主题下白底白字不可读）
        Surface(
            color = tvPalette.borderSubtle,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 2.dp)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 3.dp, vertical = 3.dp)
            ) {
                tabs.forEachIndexed { index, label ->
                    val isSelected = index == selectedTab
                    val tabShape = RoundedCornerShape(9.dp)
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(tabShape)
                            .then(
                                if (isSelected) Modifier
                                    .background(MaterialTheme.colorScheme.surfaceVariant, tabShape)
                                    .border(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.65f), tabShape)
                                    .background(
                                        androidx.compose.ui.graphics.Brush.verticalGradient(
                                            0f to tvPalette.glassGloss,
                                            1f to Color.Transparent
                                        ),
                                        tabShape
                                    )
                                else Modifier
                            )
                            .tvFocusBorder(cornerRadius = 8)
                            .clickable { selectedTab = index }
                            .padding(vertical = 7.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = label,
                            color = if (isSelected) tvPalette.accentText else oc.textSecondary,
                            fontSize = 13.sp,
                            fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                            textAlign = TextAlign.Center,
                            maxLines = 1
                        )
                    }
                }
            }
        }

        // 内容区：复用竖屏播放页视频下方4大内容
        Box(modifier = Modifier.fillMaxSize()) {
            if (!fileLoaded && !hasEverLoaded) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        text = "未在播放",
                        color = oc.textSecondary,
                        fontSize = 14.sp
                    )
                }
            } else {
                androidx.compose.animation.Crossfade(
                    targetState = selectedTab,
                    animationSpec = androidx.compose.animation.core.tween(durationMillis = 200),
                    label = "splitTab"
                ) { tab ->
                    if (isLocalFile) {
                        when (tab) {
                            0 -> {
                                val duration by player.duration.collectAsState()
                                val timePos by player.timePos.collectAsState()
                                val videoWidth by player.videoWidth.collectAsState()
                                val videoHeight by player.videoHeight.collectAsState()
                                PortraitLocalFileInfo(
                                    viewModel = viewModel,
                                    duration = duration,
                                    timePos = timePos,
                                    videoWidth = videoWidth,
                                    videoHeight = videoHeight
                                )
                            }
                            else -> PortraitRecentLocalFiles(viewModel = viewModel)
                        }
                    } else {
                        when (tab) {
                            0 -> PortraitCategoryContent(viewModel = viewModel, onGroupSelected = { selectedTab = 1 })
                            1 -> PortraitChannelOnlyList(viewModel = viewModel)
                            2 -> PortraitEpgContent(viewModel = viewModel)
                            else -> {
                                val duration by player.duration.collectAsState()
                                val timePos by player.timePos.collectAsState()
                                val videoWidth by player.videoWidth.collectAsState()
                                val videoHeight by player.videoHeight.collectAsState()
                                PortraitPlayerInfoPanel(
                                    viewModel = viewModel,
                                    duration = duration,
                                    timePos = timePos,
                                    videoWidth = videoWidth,
                                    videoHeight = videoHeight
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * 分屏左列徽章标识行：对齐全屏底栏第1行技术标签组 + 竖屏播放页媒体徽章，
 * 能显示的尽量全：频道号/播放状态/暂停/已收藏 + 视频/音频/传输全量徽章（buildSplitAllBadges）。
 * 横向 LazyRow 可滚动，2 秒刷新一次媒体信息。
 */
@Composable
private fun SplitBadgeRow(viewModel: AppViewModel, isFavorite: Boolean) {
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    val playbackState by viewModel.playbackState.collectAsState()
    val showExitCatchup by viewModel.showExitCatchup.collectAsState()
    val paused by viewModel.mpv.paused.collectAsState()
    val videoWidth by viewModel.mpv.videoWidth.collectAsState()
    val videoHeight by viewModel.mpv.videoHeight.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()

    // 媒体信息 2 秒刷新（与竖屏信息 Tab 节奏一致）
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(2000L) } }
    val mediaBadges = if (fileLoaded) remember(tick, videoWidth, videoHeight) {
        buildSplitAllBadges(viewModel.mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl())
    } else emptyList()

    // 播放状态徽章（与全屏底栏一致：直播/时移/回看）
    val statusBadge = when {
        !fileLoaded -> null
        playbackState.mode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
        showExitCatchup -> "回看" to tvPalette.warningText
        else -> "直播" to tvPalette.accentText
    }

    LazyRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (currentIdx >= 0) {
            item { SplitBadge(String.format("%03d", currentIdx + 1), accent = true) }
        }
        statusBadge?.let { (label, color) ->
            item { SplitBadge(label, tint = color) }
        }
        if (paused && fileLoaded) {
            item { SplitBadge("暂停", tint = tvPalette.textDisabled) }
        }
        if (isFavorite) {
            item { SplitBadge("已收藏", tint = tvPalette.favorite) }
        }
        items(mediaBadges.size) { i -> SplitBadge(mediaBadges[i]) }
    }
}

/** 徽章胶囊：轻玻璃底 + 语义色文字（随主题：深色白字 / 浅色深字） */
@Composable
private fun SplitBadge(text: String, accent: Boolean = false, tint: Color = Color.Unspecified) {
    val fg = if (tint == Color.Unspecified) tvPalette.textPrimary else tint
    Surface(
        color = if (accent) AptvAccent.copy(alpha = 0.22f) else fg.copy(alpha = 0.18f),
        shape = RoundedCornerShape(4.dp)
    ) {
        Text(
            text = text,
            color = if (accent) tvPalette.accentText else fg,
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
            maxLines = 1
        )
    }
}

/**
 * 最近节目单块：当前节目（LIVE 徽章 + 时间 + 标题 + 细进度条）+ 后续 2 档预告。
 * 数据源与竖屏节目 Tab 一致：getFullEpgForCurrent() 完整缓存（epgCacheVersion 驱动刷新）；
 * 缓存为空时主动触发 fetchEpgForCurrent()（内部有缓存短路，重复调用安全）。
 */
@Composable
private fun SplitEpgBlock(
    viewModel: AppViewModel,
    currentProgram: IptvEpgProgram?,
    tick: Long
) {
    val oc = rememberPlayerOverlayColors()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }

    // 缓存为空时主动拉取（订阅频道；切台后 idx 变化自动重拉）
    LaunchedEffect(currentIdx) {
        if (currentIdx >= 0 && viewModel.getFullEpgForCurrent().isEmpty()) {
            viewModel.fetchEpgForCurrent()
        }
    }

    val fullEpg = remember(currentIdx, epgCacheVersion) { viewModel.getFullEpgForCurrent() }
    val effectiveProgram = currentProgram ?: ProgressHelper.findCurrentProgram(fullEpg, System.currentTimeMillis())

    val upcoming = remember(fullEpg, effectiveProgram) {
        if (effectiveProgram != null && effectiveProgram.stopTs > 0) {
            fullEpg.filter { it.startTs >= effectiveProgram.stopTs && it.title.isNotEmpty() }.take(2)
        } else emptyList()
    }

    Column(modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
        if (effectiveProgram != null && effectiveProgram.title.isNotEmpty()) {
            // 当前行：LIVE 徽章 + 时间 + 标题 + 细进度条
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Surface(color = tvPalette.danger, shape = RoundedCornerShape(3.dp)) {
                    Text(
                        text = "LIVE",
                        color = Color.White,
                        fontSize = 8.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                    )
                }
                Spacer(modifier = Modifier.width(5.dp))
                Text(
                    text = "${timeFmt.format(java.util.Date(effectiveProgram.startTs * 1000L))} ${effectiveProgram.title}",
                    color = oc.textPrimary,
                    fontSize = 12.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                if (effectiveProgram.stopTs > effectiveProgram.startTs) {
                    val progress = remember(tick, effectiveProgram) {
                        val nowSec = System.currentTimeMillis() / 1000L
                        val total = (effectiveProgram.stopTs - effectiveProgram.startTs).coerceAtLeast(1)
                        (nowSec - effectiveProgram.startTs).coerceIn(0, total).toFloat() / total
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Box(
                        modifier = Modifier
                            .width(90.dp)
                            .height(3.dp)
                            .clip(RoundedCornerShape(1.5.dp))
                            .background(tvPalette.borderSubtle)
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxHeight()
                                .fillMaxWidth(progress)
                                .clip(RoundedCornerShape(1.5.dp))
                                .background(tvPalette.accentGraphic)
                        )
                    }
                }
            }
            // 后续预告行
            upcoming.forEach { prog ->
                Spacer(modifier = Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = timeFmt.format(java.util.Date(prog.startTs * 1000L)),
                        color = oc.textSecondary.copy(alpha = 0.7f),
                        fontSize = 11.sp
                    )
                    Spacer(modifier = Modifier.width(7.dp))
                    Text(
                        text = prog.title,
                        color = oc.textSecondary,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        } else {
            Text(
                text = "暂无节目单信息",
                color = oc.textSecondary.copy(alpha = 0.6f),
                fontSize = 12.sp,
                modifier = Modifier.padding(vertical = 3.dp)
            )
        }
    }
}

/**
 * 实时频谱块（矮条版）：复用 SpectrumCanvas + viewModel.audioSpectrum。
 * RECORD_AUDIO 权限在组合时申请（未授权弹申请/拒绝显示原因）；
 * 采样走引用计数，与右侧信息 Tab / 音频可视化面板共存互不干扰。
 */
@Composable
private fun SplitSpectrumBlock(viewModel: AppViewModel) {
    val oc = rememberPlayerOverlayColors()
    val spectrum by viewModel.audioSpectrum.collectAsState()
    val spectrumError by viewModel.audioSpectrumError.collectAsState()
    val context = LocalContext.current
    val lifecycleOwner = androidx.compose.ui.platform.LocalLifecycleOwner.current
    // 用户拒绝后不再自动弹窗，改为「点击授权」引导
    var denied by remember { mutableStateOf(false) }
    var requestedOnce by remember { mutableStateOf(false) }

    fun hasPermission(): Boolean =
        androidx.core.content.ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.RECORD_AUDIO
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            denied = false
            viewModel.startSpectrumSampling()
        } else {
            denied = true
        }
    }

    // 进入分屏播放页即初始化频谱（不依赖是否打开过「信息」Tab）。
    // 根因：首帧（onCreate → setContent）阶段 Activity 尚未 RESUMED，此时直接
    // launch 权限申请会被系统丢弃，采样永远起不来，频谱只剩「无权限」。
    // 因此先等 RESUMED 再申请；已授权则直接开始采样。
    DisposableEffect(Unit) {
        onDispose { viewModel.stopSpectrumSampling() }
    }
    LaunchedEffect(Unit) {
        if (hasPermission()) {
            viewModel.startSpectrumSampling()
            return@LaunchedEffect
        }
        var waited = 0
        while (waited < 3000 &&
            !lifecycleOwner.lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.RESUMED)
        ) {
            delay(100)
            waited += 100
        }
        if (!requestedOnce) {
            requestedOnce = true
            permLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
        }
    }

    if (spectrumError.isNotEmpty() || denied) {
        // 不用「无权限」这类生硬提示：给出可点击的授权引导；点一下即重新申请/重试
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 6.dp)
                .height(48.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(tvPalette.borderSubtle)
                .clickable {
                    if (hasPermission()) viewModel.startSpectrumSampling()
                    else permLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
                },
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "频谱不可用 · 点按授权麦克风",
                color = oc.textSecondary,
                fontSize = 10.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 10.dp)
            )
        }
    } else {
        SpectrumCanvas(
            spectrum = spectrum,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 6.dp)
                // 默认 48dp（@240dpi ≈ 72px）：40dp 在分屏里偏矮，加上原始振幅小，
                // 视觉上退化成一排虚线
                .height(48.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(tvPalette.borderSubtle)
        )
    }
}

/**
 * 分屏左列全量徽章：在 buildTvMediaBadges（全屏底栏，最多 8 个）基础上不截断并补充
 * 精确分辨率/像素格式/采样率/硬解/轨道数等，尽量多尽量全。
 */
private fun buildSplitAllBadges(
    mpv: com.iptv.scanner.editor.pro.player.Player,
    videoWidth: Int,
    videoHeight: Int,
    playbackUrl: String
): List<String> {
    val result = mutableListOf<String>()
    val mediaInfo = try { mpv.getMediaInfo() } catch (_: Exception) { emptyMap() }
    fun v(key: String) = mediaInfo[key]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" && it != "0.000" }
    // 视频编码
    v("videoCodec")?.let { result.add(it.removePrefix("video/").removePrefix("audio/").uppercase()) }
    // 分辨率档位 + 精确分辨率
    if (videoWidth > 0 && videoHeight > 0) {
        result.add(when { videoWidth >= 3800 -> "4K"; videoWidth >= 1900 -> "1080P"; videoWidth >= 1200 -> "720P"; else -> "${videoHeight}P" })
        result.add("${videoWidth}×${videoHeight}")
    }
    // 视频码率
    val videoBitrate = try { mpv.getPropertyInt("video-bitrate") } catch (_: Exception) { null }
    if (videoBitrate != null && videoBitrate > 0) {
        val kbps = videoBitrate / 1000
        result.add(if (kbps >= 1000) "%.1fMbps".format(kbps / 1000.0) else "${kbps}kbps")
    }
    // HDR（传输特性/色彩域）
    when {
        mediaInfo["videoGamma"] == "hlg" -> result.add("HLG")
        mediaInfo["videoGamma"] == "pq" -> result.add("HDR10")
        mediaInfo["videoPrimaries"] == "bt.2020" -> result.add("HDR")
    }
    // 像素格式
    v("pixelFormat")?.let { result.add(it) }
    // 音频编码
    v("audioCodec")?.let { result.add(it.removePrefix("audio/").uppercase()) }
    // 声道
    val audioCh = try { mpv.getPropertyInt("audio-params/channels") } catch (_: Exception) { null }
    if (audioCh != null && audioCh > 0) {
        result.add(when (audioCh) { 1 -> "单声道"; 2 -> "立体声"; 6 -> "5.1ch"; 8 -> "7.1ch"; else -> "${audioCh}ch" })
    }
    // 采样率
    v("audioSampleRate")?.let { s ->
        s.toDoubleOrNull()?.let { hz -> result.add(String.format("%.1fkHz", hz / 1000)) }
    }
    // 帧率
    v("fps")?.let { s ->
        s.toFloatOrNull()?.let { f -> result.add("${f.toInt()}FPS") }
    }
    // 容器格式
    v("containerFormat")?.let { fmt ->
        val short = fmt.substringAfter("/").substringAfterLast(".")
        if (short.isNotEmpty()) result.add(short.uppercase())
    }
    // 传输协议
    if (playbackUrl.isNotEmpty()) {
        when (playbackUrl.substringBefore("://").lowercase()) {
            "http", "https" -> result.add("HTTP")
            "rtsp" -> result.add("RTSP")
            "udp", "rtp" -> result.add("UDP")
            "file" -> result.add("本地")
        }
    }
    // 解码方式
    mediaInfo["hwdec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let {
        result.add(if (it == "no") "软解" else "硬解")
    }
    // 轨道数
    v("trackCount")?.let { result.add("${it}轨道") }
    return result
}
