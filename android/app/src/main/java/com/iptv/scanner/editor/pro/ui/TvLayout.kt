package com.iptv.scanner.editor.pro.ui

import android.app.Activity
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.core.tween
import androidx.compose.runtime.DisposableEffect

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons

import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.FullscreenExit
import androidx.compose.material.icons.automirrored.filled.Backspace
import androidx.compose.material3.Icon
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.blur
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures

import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.CompositionLocalProvider
import coil.compose.AsyncImage
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.player.PlayMode
import com.iptv.scanner.editor.pro.player.PlaybackState
import com.iptv.scanner.editor.pro.player.ProgressHelper
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.PlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.GlassPanel
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import kotlinx.coroutines.delay
import kotlin.math.abs

/**
 * 根据点击位置计算多画面视口索引。
 * DUAL: 左=0, 右=1
 * QUAD: 左上=0, 右上=1, 左下=2, 右下=3
 * NINE: 3x3网格, 左上=0, ... 右下=8
 */
private fun computeViewportIndex(
    x: Float, y: Float, w: Float, h: Float, layout: MultiViewLayout
): Int {
    if (w <= 0 || h <= 0) return -1
    return when (layout) {
        MultiViewLayout.DUAL -> if (x < w / 2f) 0 else 1
        MultiViewLayout.QUAD -> {
            val col = if (x < w / 2f) 0 else 1
            val row = if (y < h / 2f) 0 else 1
            row * 2 + col
        }
        MultiViewLayout.NINE -> {
            val col = (x / (w / 3f)).toInt().coerceIn(0, 2)
            val row = (y / (h / 3f)).toInt().coerceIn(0, 2)
            row * 3 + col
        }
        MultiViewLayout.SINGLE -> 0
    }
}

// 侧边栏风格配色（主色统一为竖屏 APTV 橙红 AptvAccent）
private val SIDEBAR_GRADIENT_START = Color(0xFF036D80)
private val SIDEBAR_GRADIENT_END = Color(0xFF052D49)
private val ICON_BG = Color(0x32FFFFFF)
private val TIME_BG = Color(0x26000000)
/** 底栏可读性底色：玻璃霜层上垫深色底 */
// 底栏不再叠加实底 scrim：深色可读性由玻璃材质 overlayDark 暗玻璃霜层提供
/** 行间分隔条颜色 */
private val TV_ROW_DIVIDER = Color(0x1FFFFFFF)

@Composable
fun TvPlayerLayout(
    viewModel: AppViewModel,
    primaryPlayer: @Composable () -> Unit,
    videoAspectRatio: Float,
    homeOverlay: Boolean = false
) {
    val oc = rememberPlayerOverlayColors()
    // 横屏分屏模式（默认开启）：左视频+控制条 / 右常驻面板。
    // 多画面模式保持全屏（MultiViewOverlay 需要整个屏幕网格）。
    val splitModePref by viewModel.landscapeSplitMode.collectAsState()
    val multiActive by viewModel.multiViewState.collectAsState()
    val useSplitTarget = splitModePref && !multiActive.active

    // movableContent 视频节点（AndroidView）跨布局迁移必须两帧完成：
    // 同帧「移除旧布局树 + 插入新布局树 + 搬迁节点」会触发 Compose
    // CopyNodesToNewAnchorLocation → insertAt「already has a parent」崩溃
    // （ACRA 实测 IllegalStateException at LayoutNode.insertAt）。
    // 切换时第一帧先摘下视频节点渲染空布局，下一帧再放入新布局；
    // movable 完全离开组合后状态释放，重新放入即全新节点，不会再撞旧父节点。
    val useSplitState = remember { androidx.compose.runtime.mutableStateOf(useSplitTarget) }
    val playerPlacedState = remember { androidx.compose.runtime.mutableStateOf(true) }
    androidx.compose.runtime.LaunchedEffect(useSplitTarget) {
        if (useSplitState.value != useSplitTarget) {
            playerPlacedState.value = false
            useSplitState.value = useSplitTarget
            androidx.compose.runtime.withFrameNanos { }
        }
        playerPlacedState.value = true
    }
    val useSplit = useSplitState.value

    if (useSplit) {
        // ---- 分屏布局：系统栏保持可见（状态栏时间/电量可读） ----
        val context = LocalContext.current
        DisposableEffect(Unit) {
            val activity = context as? Activity
            val controller = activity?.window?.let {
                androidx.core.view.WindowCompat.getInsetsController(it, it.decorView)
            }
            controller?.systemBarsBehavior =
                androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            controller?.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            onDispose { }
        }
        // DPI 自适应缩放（基准 900dp、下限 0.60，与横屏首页一致）：
        // 手机横屏/小平板缩小分屏 UI 提升内容密度，TV 端 ≥900dp 不缩放
        val splitOrigDensity = LocalDensity.current
        val splitDpiScale = (LocalConfiguration.current.screenHeightDp / 900f).coerceIn(0.60f, 1f)
        androidx.compose.runtime.CompositionLocalProvider(
            LocalDensity provides Density(splitOrigDensity.density * splitDpiScale, splitOrigDensity.fontScale)
        ) {
            // 橙红主色作用域：分屏页 accent（播放按钮等）与首页/竖屏 APTV 风格统一
            androidx.compose.runtime.CompositionLocalProvider(LocalAptvStyle provides true) {
                TvSplitLayout(
                    viewModel = viewModel,
                    primaryPlayer = { if (playerPlacedState.value) primaryPlayer() }
                )
            }
        }
        return
    }

    // ---- 以下为传统全屏布局（保持不变） ----
    val sidebarVisible by viewModel.landscapeSidebarVisible.collectAsState()
    val controlsVisible by viewModel.controlsVisible.collectAsState()
    val controlsPinned by viewModel.controlsPinned.collectAsState()
    val displayInfo by viewModel.channelDisplayInfo.collectAsState()
    val paused by viewModel.mpv.paused.collectAsState()
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    val videoWidth by viewModel.mpv.videoWidth.collectAsState()
    val videoHeight by viewModel.mpv.videoHeight.collectAsState()
    val showExitCatchup by viewModel.showExitCatchup.collectAsState()
    val playbackState by viewModel.playbackState.collectAsState()
    val currentEpg by viewModel.currentEpg.collectAsState()
    val channelNumberInput by viewModel.channelNumberInput.collectAsState()
    val channelNumDisplay by viewModel.channelNumDisplay.collectAsState()
    val osdShowTime by viewModel.osdShowTime.collectAsState()
    val osdShowNetSpeed by viewModel.osdShowNetSpeed.collectAsState()
    // 面板是否打开：用于底栏焦点归还（面板关闭时重新把焦点落回底栏，见 TvBottomBar 的 grabFocus）
    val anyPanelOpen by viewModel.anyPanelOpenFlow.collectAsState()

    // 零频道提示条件：后端无频道、本地频道列表为空、且不在加载订阅源
    val iptvStatusHint by viewModel.iptvStatus.collectAsState()
    val allChannels by viewModel.channels.collectAsState()
    val zeroChannels = iptvStatusHint?.let { it.inited && !it.sourceLoading && it.channelsTotal == 0 } == true &&
        allChannels.isEmpty()

    val currentProgram = remember(currentEpg) {
        ProgressHelper.findCurrentProgram(currentEpg, System.currentTimeMillis())
    }

    val showOverlays by derivedStateOf { sidebarVisible || controlsVisible || controlsPinned }
    val multiViewState by viewModel.multiViewState.collectAsState()
    val multiViewStateUpdated = rememberUpdatedState(multiViewState)

    // 横屏全屏：隐藏系统状态栏和导航栏（滑动可临时唤出）；首页覆盖时保持可见
    val context = LocalContext.current
    val bottomBarStyle by viewModel.bottomBarStyle.collectAsState()
    // 弹窗实时预览样式：非 null 时底栏按预览样式渲染（BACK 未确定则恢复已确定样式）
    val stylePreview by viewModel.stylePreview.collectAsState()
    // 样式弹窗打开期间底栏不抢焦点：预览底栏的 requestFocus 会夺走菜单面板焦点，
    // 导致弹窗 onPreviewKeyEvent 的 DOWN/UP/OK 路由失效
    val stylePickerOpen by viewModel.stylePickerOpen.collectAsState()
    DisposableEffect(homeOverlay) {
        val activity = context as? Activity
        val window = activity?.window
        val controller = window?.let {
            androidx.core.view.WindowCompat.getInsetsController(it, it.decorView)
        }
        controller?.systemBarsBehavior =
            androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        if (homeOverlay) {
            controller?.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        } else {
            controller?.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        }
        onDispose {
            controller?.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        }
    }

    // DPI自适应缩放：以TV横屏720dp高度为基准，手机横屏高度不足时缩小UI。
    // 下限 0.55→0.70：0.55 时 Material 48dp 最小触控目标实际仅 ~26dp、
    // 28dp 图标按钮 ~15dp，触控体验不可用；0.70 下视频区缩小有限但
    // 触控目标恢复到可点范围（TV 端 screenHeightDp≥720 不受影响）。
    val configuration = LocalConfiguration.current
    val origDensity = LocalDensity.current
    val dpiScale = (configuration.screenHeightDp / 720f).coerceIn(0.70f, 1f)
    val scaledDensity = Density(origDensity.density * dpiScale, origDensity.fontScale)

    Box(modifier = Modifier.fillMaxSize()) {
        if (playerPlacedState.value) primaryPlayer()

        // 触控分区由 Activity dispatchTouchEvent 处理（Compose 无法拦截 AndroidView 触控）
        // 多画面模式下 dispatchTouchEvent 跳过分区toggle，触控直接传递给 MultiViewOverlay

        CompositionLocalProvider(LocalDensity provides scaledDensity) {
        // 侧边栏风格：右上角时间组（始终显示）
        if (osdShowTime) {
            TvTimeGroup(
                modifier = Modifier.align(Alignment.TopEnd),
                channelNumberInput = channelNumberInput,
                channelNumDisplay = channelNumDisplay
            )
        } else if (channelNumberInput.isNotEmpty() || channelNumDisplay.isNotEmpty()) {
            // 即使关闭时间显示，数字选台/切台时仍显示频道号
            TvTimeGroup(
                modifier = Modifier.align(Alignment.TopEnd),
                channelNumberInput = channelNumberInput,
                channelNumDisplay = channelNumDisplay
            )
        }

        // 侧边栏风格：右下角网速显示
        if (fileLoaded && !sidebarVisible && osdShowNetSpeed) {
            TvNetSpeed(
                modifier = Modifier.align(Alignment.BottomEnd),
                mpv = viewModel.mpv
            )
        }


        AnimatedVisibility(
            visible = sidebarVisible,
            enter = slideInHorizontally(initialOffsetX = { -it / 2 }, animationSpec = tween(150)),
            exit = slideOutHorizontally(targetOffsetX = { -it / 2 }, animationSpec = tween(120)),
            modifier = Modifier.align(Alignment.CenterStart)
        ) {
            val isAndroid12Plus = android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S
            // 底栏与侧边栏互斥显示（showOverlays && !sidebarVisible），无需预留底栏高度，
            // 侧边栏直接贴到屏幕底部，避免底部空出一大块
            Box(modifier = Modifier.fillMaxHeight().fillMaxWidth(0.82f).padding(start = 16.dp, top = 10.dp, bottom = 10.dp)) {
                TvUnifiedPanel(viewModel = viewModel)
            }
        }

        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .width(820.dp)
                .padding(vertical = 8.dp)
        ) {
            AnimatedVisibility(
                visible = showOverlays && !sidebarVisible,
                enter = fadeIn(),
                exit = fadeOut()
            ) {
                TvBottomBar(
                    viewModel = viewModel,
                    displayInfo = displayInfo,
                    paused = paused,
                    fileLoaded = fileLoaded,
                    videoWidth = videoWidth,
                    videoHeight = videoHeight,
                    showExitCatchup = showExitCatchup,
                    playbackMode = playbackState.mode,
                    currentProgram = currentProgram,
                    epgList = currentEpg,
                    style = stylePreview ?: bottomBarStyle,
                    grabFocus = stylePreview == null && !stylePickerOpen && !anyPanelOpen
                )
            }
        }

        // 零频道提示：无频道且无面板打开时，在播放页中央提示添加订阅源（沿用 OSD 卡片样式）
        if (zeroChannels && !anyPanelOpen) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                OsdView(
                    title = "还没有频道",
                    subtitle = "按 OK 添加订阅源",
                    extra = "",
                    modifier = Modifier
                )
            }
        }
        } // CompositionLocalProvider
    }
}

@Composable
private fun TvTimeGroup(modifier: Modifier = Modifier, channelNumberInput: String = "", channelNumDisplay: String = "") {
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val dateText = remember(tick) {
        val fmt = java.text.SimpleDateFormat("MM/dd EE", java.util.Locale.CHINESE)
        fmt.format(java.util.Date(tick))
    }
    val timeText = remember(tick) {
        val fmt = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
        fmt.format(java.util.Date(tick))
    }
    Column(
        modifier = modifier.padding(top = 15.dp, end = 15.dp),
        horizontalAlignment = Alignment.End
    ) {
        // 侧边栏风格：数字选台时显示大字号频道号
        if (channelNumberInput.isNotEmpty()) {
            Surface(
                color = TIME_BG,
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = channelNumberInput,
                    color = AptvAccent,
                    fontSize = 72.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
        } else if (channelNumDisplay.isNotEmpty()) {
            // 切台时显示频道号
            Surface(
                color = TIME_BG,
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = channelNumDisplay,
                    color = AptvAccent,
                    fontSize = 48.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 2.dp)
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
        }
        Surface(
            color = TIME_BG,
            shape = RoundedCornerShape(8.dp)
        ) {
            Column(
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(text = dateText, color = Color.White, fontSize = 11.sp)
                Text(text = timeText, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
        }
    }
}

@Composable
private fun TvNetSpeed(modifier: Modifier = Modifier, mpv: com.iptv.scanner.editor.pro.player.Player) {
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val speedText = remember(tick) {
        val cacheSpeed = mpv.getPropertyDouble("cache-speed") ?: 0.0
        val videoBitrate = mpv.getPropertyInt("video-bitrate") ?: 0
        if (cacheSpeed > 0) {
            formatNetSpeed(cacheSpeed.toLong())
        } else if (videoBitrate > 0) {
            formatNetSpeed(videoBitrate.toLong() / 8)
        } else {
            null
        }
    }
    if (speedText != null) {
        Surface(
            color = TIME_BG,
            shape = RoundedCornerShape(4.dp),
            modifier = modifier.padding(bottom = 12.dp, end = 15.dp)
        ) {
            Text(
                text = speedText,
                color = Color.White,
                fontSize = 11.sp,
                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
            )
        }
    }
}

private fun formatNetSpeed(bytesPerSec: Long): String {
    if (bytesPerSec <= 0) return ""
    val kb = bytesPerSec / 1024.0
    val mb = kb / 1024.0
    return when {
        mb >= 1.0 -> "%.1f MB/s".format(mb)
        kb >= 1.0 -> "%.0f KB/s".format(kb)
        else -> "$bytesPerSec B/s"
    }
}


@Composable
private fun TvBottomBar(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    style: Int = 0,
    grabFocus: Boolean = true
) {
    // 底栏呼出时把焦点落到播放/暂停键：DPAD 直接在底栏内移动焦点（Activity dispatchKeyEvent 已放行），
    // 不再需要 TAB 键临时导航。AnimatedVisibility 内每次呼出都是新组合，effect 重新执行。
    // grabFocus=false（样式弹窗预览态 / 面板打开态）时跳过：面板打开时底栏一旦抢焦点会破坏面板按键路由；
    // 面板关闭后 grabFocus 由 false 变回 true，effect 重新执行，把焦点从已关闭的面板归还到底栏。
    val barFocus = remember { FocusRequester() }
    LaunchedEffect(grabFocus) {
        if (grabFocus) {
            kotlinx.coroutines.delay(80)
            runCatching { barFocus.requestFocus() }
        }
    }
    when (style) {
        1 -> TvBottomBarStyleB(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        2 -> TvBottomBarStyleC(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        3 -> TvBottomBarStyleD(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        4 -> TvBottomBarStyleE(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        5 -> TvBottomBarStyleF(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        6 -> TvBottomBarStyleG(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        7 -> TvBottomBarStyleH(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        8 -> TvBottomBarStyleI(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        9 -> TvBottomBarStyleJ(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        10 -> TvBottomBarStyleK(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        11 -> TvBottomBarStyleL(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        12 -> TvBottomBarStyleM(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        13 -> TvBottomBarStyleN(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        14 -> TvBottomBarStyleO(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        15 -> TvBottomBarStyleP(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        16 -> TvBottomBarStyleQ(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        17 -> TvBottomBarStyleR(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
        else -> TvBottomBarStyleA(viewModel, displayInfo, paused, fileLoaded, videoWidth, videoHeight, showExitCatchup, playbackMode, currentProgram, epgList, barFocus)
    }
}

/** 共享：计算播放进度（直播有 EPG 用节目时间轴，点播用 timePos/duration），无进度返回 null */
private fun computeTvBarProgress(currentProgram: IptvEpgProgram?, timePos: Double, duration: Double): Float? {
    if (currentProgram != null && currentProgram.startTs > 0 && currentProgram.stopTs > currentProgram.startTs) {
        val nowSec = System.currentTimeMillis() / 1000L
        val total = currentProgram.stopTs - currentProgram.startTs
        val elapsed = (nowSec - currentProgram.startTs).coerceIn(0L, total)
        return elapsed.toFloat() / total
    }
    if (duration > 0 && timePos > 0) return (timePos / duration).toFloat().coerceIn(0f, 1f)
    return null
}

@Composable
private fun TvBottomBarStyleA(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()

    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }

    val mediaInfoBadges = if (fileLoaded) remember(tick, videoWidth, videoHeight) {
        buildTvMediaBadges(mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl())
    } else emptyList()

    val isAndroid12Plus = android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val dateFmt = remember { java.text.SimpleDateFormat("MM月dd日 EE", java.util.Locale.CHINESE) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }

    // 侧边栏风格状态标签
    val statusTag = when {
        !fileLoaded -> null
        playbackMode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
        showExitCatchup -> "回看" to tvPalette.warning
        else -> "直播" to AptvAccent
    }

    // 下一节目
    val nextProgram = remember(currentProgram, epgList) {
        if (currentProgram != null && currentProgram.stopTs > 0) {
            epgList.firstOrNull { it.startTs >= currentProgram.stopTs && it.title.isNotEmpty() }
        } else null
    }

    // 距结束时间
    val remainText = remember(tick, currentProgram) {
        if (currentProgram != null && currentProgram.stopTs > 0) {
            val nowSec = tick / 1000L
            val diff = currentProgram.stopTs - nowSec
            if (diff > 0) {
                val min = diff / 60
                if (min > 0) "距结束 ${min}分钟" else "距结束 ${diff}秒"
            } else null
        } else null
    }

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 8.dp, overlayDark = true) {
            // oc 必须在 GlassPanel（DarkOverlayTheme 作用域）内获取：底栏是暗玻璃覆盖层，
            // 浅色主题下若在外层取色会得到黑字/黑图标，落在暗玻璃上不可读
            val oc = rememberPlayerOverlayColors()
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // 台标：置于底栏左侧，随三行内容整体垂直居中（不再嵌在第1行上部）
                // 104dp 宽：适配长条状台标（如 CCTV 组合标），方形标 ContentScale.Fit 自动居中
                Box(
                    modifier = Modifier.size(104.dp, 50.dp).clip(RoundedCornerShape(6.dp)).background(ICON_BG),
                    contentAlignment = Alignment.Center
                ) {
                    if (displayInfo.logo.isNotEmpty()) {
                        AsyncImage(model = displayInfo.logo, contentDescription = displayInfo.name, modifier = Modifier.fillMaxSize().padding(3.dp), contentScale = ContentScale.Fit)
                    } else {
                        Text(
                            text = displayInfo.name.take(2).ifEmpty { "·" },
                            color = Color.White,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
                Spacer(modifier = Modifier.width(14.dp))
                // 竖分隔条：台标列与右侧信息列分隔
                Box(modifier = Modifier.width(1.dp).height(50.dp).background(TV_ROW_DIVIDER))
                Spacer(modifier = Modifier.width(14.dp))
                // 右侧信息列：三行（频道信息 / 当前节目+进度 / 下一档节目）
                Column(modifier = Modifier.weight(1f)) {
                // 第1行：频道号 + 频道名 + spacer + 状态标签 + 技术标签组
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (displayInfo.idx >= 0) {
                        Text(
                            text = String.format("%03d", displayInfo.idx + 1),
                            color = AptvAccent,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.width(5.dp))
                        Box(modifier = Modifier.width(1.dp).height(13.dp).background(Color(0x60FFFFFF)))
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    Text(
                        text = displayInfo.name.ifEmpty { "未选择频道" },
                        color = if (displayInfo.idx >= 0) oc.textPrimary else oc.textSecondary,
                        fontSize = 18.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.weight(1f))
                    if (statusTag != null) {
                        Surface(color = statusTag.second.copy(alpha = 0.25f), shape = RoundedCornerShape(4.dp)) {
                            Text(text = statusTag.first, color = statusTag.second, fontSize = 11.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                        }
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    if (paused && fileLoaded) {
                        Surface(color = Color(0x30FFFFFF), shape = RoundedCornerShape(4.dp)) {
                            Text("暂停", color = Color.White, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp))
                        }
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    mediaInfoBadges.forEach { info: String ->
                        Surface(color = Color(0x30FFFFFF), shape = RoundedCornerShape(4.dp)) {
                            Text(text = info, color = Color(0xCCFFFFFF), fontSize = 11.sp, modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp))
                        }
                        Spacer(modifier = Modifier.width(4.dp))
                    }
                }

                // 行间分隔条
                Box(modifier = Modifier.fillMaxWidth().padding(top = 6.dp).height(1.dp).background(TV_ROW_DIVIDER))

                // 第2行：当前节目时间范围 + 节目名 + 进度条(细线) + 时间戳 + 距结束 + 按钮
                Spacer(modifier = Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                        if (currentProgram != null && currentProgram.title.isNotEmpty()) {
                            if (currentProgram.stopTs > 0) {
                                val timeRange = remember(currentProgram) {
                                    val start = timeFmt.format(java.util.Date(currentProgram.startTs * 1000L))
                                    val end = timeFmt.format(java.util.Date(currentProgram.stopTs * 1000L))
                                    "$start-$end"
                                }
                                Text(text = timeRange, color = tvPalette.textSecondary, fontSize = 13.sp)
                                Spacer(modifier = Modifier.width(8.dp))
                            }
                            Text(
                                text = currentProgram.title,
                                color = oc.textPrimary,
                                fontSize = 14.sp,
                                maxLines = 1, overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                        } else {
                            Text(
                                text = "精彩节目",
                                color = oc.textSecondary.copy(alpha = 0.6f),
                                fontSize = 14.sp,
                                modifier = Modifier.weight(1f)
                            )
                        }
                        val timePos by mpv.timePos.collectAsState()
                        val duration by mpv.duration.collectAsState()
                        val progress = remember(tick, timePos, duration, displayInfo, currentProgram) {
                            val fakeChannel = if (displayInfo.idx >= 0) IptvChannel(
                                name = displayInfo.name,
                                url = if (displayInfo.isLocal) "file:///local" else "http://live",
                                group = displayInfo.group,
                                logo = displayInfo.logo
                            ) else null
                            ProgressHelper.computeProgress(
                                viewModel.playbackState.value,
                                fakeChannel, currentProgram, timePos, duration
                            )
                        }
                        val hasEpg = currentProgram != null && currentProgram.stopTs > 0
                        if (hasEpg) {
                            Spacer(modifier = Modifier.width(8.dp))
                            // 细线进度条
                            Box(
                                modifier = Modifier
                                    .width(180.dp)
                                    .height(3.dp)
                                    .clip(RoundedCornerShape(1.5.dp))
                                    .background(Color(0x30FFFFFF))
                            ) {
                                Box(
                                    modifier = Modifier
                                        .fillMaxHeight()
                                        .width(with(androidx.compose.ui.platform.LocalDensity.current) { (180.dp * (progress.percent / 100f)).toPx().toDp() })
                                        .clip(RoundedCornerShape(1.5.dp))
                                        .background(AptvAccent)
                                )
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        val posText = remember(tick, timePos, playbackMode, showExitCatchup) {
                            if (playbackMode == PlayMode.LIVE && !showExitCatchup) {
                                fullTimeFmt.format(java.util.Date(tick))
                            } else if (timePos > 0) {
                                fullTimeFmt.format(java.util.Date((timePos * 1000L).toLong()))
                            } else ""
                        }
                        if (posText.isNotEmpty()) {
                            Text(text = posText, color = tvPalette.textSecondary, fontSize = 12.sp)
                        }
                        if (remainText != null) {
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(text = remainText, color = AptvAccent, fontSize = 11.sp)
                        }
                        if (showExitCatchup) {
                            Spacer(modifier = Modifier.width(4.dp))
                            IconButton(onClick = { viewModel.exitCatchup() }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                                Icon(Icons.AutoMirrored.Filled.Backspace, "退出回看", tint = oc.accent, modifier = Modifier.size(16.dp))
                            }
                        }
                        Spacer(modifier = Modifier.width(2.dp))
                        // 播放/暂停按钮：原底栏无播放控制，暂停后用户无从恢复
                        // barFocus：底栏呼出时初始焦点落点，DPAD 可直接在底栏内移动
                        IconButton(
                            onClick = { viewModel.mpv.setPause(!paused) },
                            modifier = Modifier
                                .size(30.dp)
                                .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                                .tvFocusBorder()
                        ) {
                            Icon(
                                if (paused) Icons.Default.PlayArrow else Icons.Default.Pause,
                                contentDescription = if (paused) "播放" else "暂停",
                                tint = oc.accent,
                                modifier = Modifier.size(16.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(2.dp))
                        IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                            Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(16.dp))
                        }
                        Spacer(modifier = Modifier.width(2.dp))
                        // 返回分屏：从全屏一键回到左右分屏播放页（不用记忆 BACK 链路）
                        IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                            Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(16.dp))
                        }
                    }

                // 第3行：下一节目时间范围 + 下一节目名
                run {
                    val hasNext = nextProgram != null
                    // 行间分隔条
                    Box(modifier = Modifier.fillMaxWidth().padding(top = 6.dp).height(1.dp).background(TV_ROW_DIVIDER))
                    Spacer(modifier = Modifier.height(3.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                            if (hasNext) {
                                val nextStart = remember(nextProgram) {
                                    timeFmt.format(java.util.Date(nextProgram!!.startTs * 1000L))
                                }
                                val nextEnd = remember(nextProgram) {
                                    timeFmt.format(java.util.Date(nextProgram!!.stopTs * 1000L))
                                }
                                Text(text = "$nextStart-$nextEnd", color = tvPalette.textSecondary, fontSize = 13.sp)
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = nextProgram!!.title,
                                    color = Color(0xB3FFFFFF),
                                    fontSize = 14.sp,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.weight(1f)
                                )
                            } else {
                                val dateText = remember(tick) { dateFmt.format(java.util.Date(tick)) }
                                Text(
                                    text = dateText,
                                    color = tvPalette.textSecondary,
                                    fontSize = 13.sp,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                } // 右侧信息列 Column（三行）
            } // 底栏外层 Row（台标列 + 信息列）

    }
}

}  // TvBottomBarStyleA

/**
 * 底栏样式 B：单行紧凑式 —— 小台标 + 频道号/名 + 状态 + 节目名/进度 + 播放控制一行排布。
 * 适合喜欢信息密度高、底栏不占垂直空间的场景。
 */
@Composable
private fun TvBottomBarStyleB(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    val statusTag = when {
        !fileLoaded -> null
        playbackMode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
        showExitCatchup -> "回看" to tvPalette.warning
        else -> "直播" to AptvAccent
    }

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 8.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 小台标
            Box(
                modifier = Modifier.size(52.dp, 30.dp).clip(RoundedCornerShape(5.dp)).background(ICON_BG),
                contentAlignment = Alignment.Center
            ) {
                if (displayInfo.logo.isNotEmpty()) {
                    AsyncImage(model = displayInfo.logo, contentDescription = displayInfo.name, modifier = Modifier.fillMaxSize().padding(2.dp), contentScale = ContentScale.Fit)
                } else {
                    Text(text = displayInfo.name.take(2).ifEmpty { "·" }, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
            Spacer(modifier = Modifier.width(10.dp))
            // 频道号 + 名
            if (displayInfo.idx >= 0) {
                Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                Spacer(modifier = Modifier.width(5.dp))
            }
            Text(
                text = displayInfo.name.ifEmpty { "未选择频道" },
                color = oc.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(0.9f, fill = false)
            )
            if (statusTag != null) {
                Spacer(modifier = Modifier.width(6.dp))
                Surface(color = statusTag.second.copy(alpha = 0.25f), shape = RoundedCornerShape(4.dp)) {
                    Text(text = statusTag.first, color = statusTag.second, fontSize = 10.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp))
                }
            }
            Spacer(modifier = Modifier.width(4.dp))
            TvBarBadgeTexts(mediaBadges.take(2), sp = 9.sp)
            Spacer(modifier = Modifier.width(8.dp))
            // 节目名 + 细进度（weight 占据剩余空间）
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                    color = oc.textSecondary, fontSize = 12.sp,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                if (progress != null) {
                    Spacer(modifier = Modifier.height(3.dp))
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(2.dp)
                            .clip(RoundedCornerShape(1.dp))
                            .background(Color(0x30FFFFFF))
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxHeight()
                                .fillMaxWidth(progress)
                                .clip(RoundedCornerShape(1.dp))
                                .background(AptvAccent)
                        )
                    }
                }
            }
            Spacer(modifier = Modifier.width(6.dp))
            // 播放控制组（播放/停止/返回分屏）
            IconButton(
                onClick = { viewModel.mpv.setPause(!paused) },
                modifier = Modifier
                    .size(34.dp)
                    .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                    .tvFocusBorder()
            ) {
                Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(18.dp))
            }
            IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(15.dp))
            }
            IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(15.dp))
            }
        }
    }
}

/**
 * 底栏样式 C：居中控制台式 —— 顶部频道信息一行居中，中央大号播放控制按钮组，
 * 底部细进度条。适合遥控器操作（按钮大、居中易定位）。
 */
@Composable
private fun TvBottomBarStyleC(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    val statusTag = when {
        !fileLoaded -> null
        playbackMode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
        showExitCatchup -> "回看" to tvPalette.warning
        else -> "直播" to AptvAccent
    }

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 12.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // 行1：频道号 + 名 + 状态 + 徽章 + 节目时间范围
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (displayInfo.idx >= 0) {
                    Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Spacer(modifier = Modifier.width(6.dp))
                }
                Text(
                    text = displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                if (statusTag != null) {
                    Spacer(modifier = Modifier.width(8.dp))
                    Surface(color = statusTag.second.copy(alpha = 0.25f), shape = RoundedCornerShape(4.dp)) {
                        Text(text = statusTag.first, color = statusTag.second, fontSize = 11.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                    }
                }
                Spacer(modifier = Modifier.width(6.dp))
                TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                if (currentProgram != null && currentProgram.stopTs > 0) {
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "${timeFmt.format(java.util.Date(currentProgram.startTs * 1000L))}-${timeFmt.format(java.util.Date(currentProgram.stopTs * 1000L))}",
                        color = tvPalette.textSecondary, fontSize = 12.sp
                    )
                }
            }
            Spacer(modifier = Modifier.height(8.dp))
            // 行2：居中大号控制按钮组（播放/停止/返回分屏）
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                Surface(color = AptvAccent.copy(alpha = 0.18f), shape = androidx.compose.foundation.shape.CircleShape) {
                    IconButton(
                        onClick = { viewModel.mpv.setPause(!paused) },
                        modifier = Modifier
                            .size(52.dp)
                            .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                            .tvFocusBorder()
                    ) {
                        Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(30.dp))
                    }
                }
                IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(36.dp).tvFocusBorder()) {
                    Icon(Icons.Default.Stop, "停止", tint = oc.textSecondary, modifier = Modifier.size(20.dp))
                }
                IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(36.dp).tvFocusBorder()) {
                    Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.textSecondary, modifier = Modifier.size(20.dp))
                }
            }
            // 行3：居中细进度条 + 时间
            if (progress != null) {
                Spacer(modifier = Modifier.height(8.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth(0.72f)
                        .height(3.dp)
                        .clip(RoundedCornerShape(1.5.dp))
                        .background(Color(0x30FFFFFF))
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxHeight()
                            .fillMaxWidth(progress)
                            .clip(RoundedCornerShape(1.5.dp))
                            .background(AptvAccent)
                    )
                }
            }
        }
    }
}

/**
 * 底栏样式 D：左信息右控制式 —— 左侧两行信息（频道行 + 节目/进度行），
 * 右侧竖分隔线 + 播放控制按钮组。信息与控制分区明确。
 */
@Composable
private fun TvBottomBarStyleD(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    val statusTag = when {
        !fileLoaded -> null
        playbackMode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
        showExitCatchup -> "回看" to tvPalette.warning
        else -> "直播" to AptvAccent
    }

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 8.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左侧信息区（两行）
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (displayInfo.idx >= 0) {
                        Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    Text(
                        text = displayInfo.name.ifEmpty { "未选择频道" },
                        color = oc.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    if (statusTag != null) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Surface(color = statusTag.second.copy(alpha = 0.25f), shape = RoundedCornerShape(4.dp)) {
                            Text(text = statusTag.first, color = statusTag.second, fontSize = 10.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp))
                        }
                    }
                    Spacer(modifier = Modifier.width(6.dp))
                    TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textSecondary, fontSize = 12.sp,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false)
                    )
                    if (progress != null) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Box(
                            modifier = Modifier
                                .width(110.dp)
                                .height(3.dp)
                                .clip(RoundedCornerShape(1.5.dp))
                                .background(Color(0x30FFFFFF))
                        ) {
                            Box(
                                modifier = Modifier
                                    .fillMaxHeight()
                                    .fillMaxWidth(progress)
                                    .clip(RoundedCornerShape(1.5.dp))
                                    .background(AptvAccent)
                            )
                        }
                    }
                }
            }
            // 竖分隔条
            Box(modifier = Modifier.width(1.dp).height(36.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(10.dp))
            // 右侧控制区（暂停/停止/返回分屏）
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                IconButton(
                    onClick = { viewModel.mpv.setPause(!paused) },
                    modifier = Modifier
                        .size(36.dp)
                        .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                        .tvFocusBorder()
                ) {
                    Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(20.dp))
                }
                IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                    Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(16.dp))
                }
                IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(30.dp).tvFocusBorder()) {
                    Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(16.dp))
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 底栏样式清单 + 共享构件（新增样式：在此登记 → TvBottomBar when 分支 →
// BottomBarStyleMiniPreview 缩微预览 三处同步）
// -----------------------------------------------------------------

/** 全屏底栏样式清单：id + 名称（样式弹窗/设置页/迷你预览共用） */
internal val TV_BOTTOM_BAR_STYLES: List<Pair<Int, String>> = listOf(
    0 to "信息详情式",
    1 to "单行紧凑式",
    2 to "居中控制台式",
    3 to "左信息右控制式",
    4 to "居中悬浮式",
    5 to "大台标信息式",
    6 to "进度优先式",
    7 to "左控制右信息式",
    8 to "三段等分式",
    9 to "OSD 大字式",
    10 to "控制台双行式",
    11 to "卡片网格式",
    12 to "广播电视式",
    13 to "机顶盒 OSD 式",
    14 to "影院 EPG 卡式",
    15 to "仪表盘 OSD 式",
    16 to "海报卡片式",
    17 to "节目时间轴式"
)

/** 共享：状态标签（时移/回看/直播），无媒体时 null */
private fun tvBarStatusTag(fileLoaded: Boolean, playbackMode: PlayMode, showExitCatchup: Boolean): Pair<String, Color>? = when {
    !fileLoaded -> null
    playbackMode == PlayMode.TIMESHIFT -> "时移" to tvPalette.info
    showExitCatchup -> "回看" to tvPalette.warning
    else -> "直播" to AptvAccent
}

/** 共享：距当前节目结束的剩余时间文案 */
private fun tvBarRemainText(tick: Long, currentProgram: IptvEpgProgram?): String? {
    if (currentProgram != null && currentProgram.stopTs > 0) {
        val diff = currentProgram.stopTs - tick / 1000L
        if (diff > 0) {
            val min = diff / 60
            return if (min > 0) "距结束 ${min}分钟" else "距结束 ${diff}秒"
        }
    }
    return null
}

/** 共享：当前时间位置文案（直播=系统时间，回看/时移=播放位置） */
private fun tvBarPosText(
    tick: Long, timePos: Double, playbackMode: PlayMode, showExitCatchup: Boolean,
    fmt: java.text.SimpleDateFormat
): String = if (playbackMode == PlayMode.LIVE && !showExitCatchup) {
    fmt.format(java.util.Date(tick))
} else if (timePos > 0) {
    fmt.format(java.util.Date((timePos * 1000L).toLong()))
} else ""

/** 共享：台标块（logo 或频道名前两字兜底），尺寸/字号可调 */
@Composable
private fun TvBarLogo(displayInfo: ChannelDisplayInfo, width: Dp, height: Dp, textSp: TextUnit = 13.sp) {
    Box(
        modifier = Modifier.size(width, height).clip(RoundedCornerShape(5.dp)).background(ICON_BG),
        contentAlignment = Alignment.Center
    ) {
        if (displayInfo.logo.isNotEmpty()) {
            AsyncImage(
                model = displayInfo.logo, contentDescription = displayInfo.name,
                modifier = Modifier.fillMaxSize().padding(3.dp), contentScale = ContentScale.Fit
            )
        } else {
            Text(
                text = displayInfo.name.take(2).ifEmpty { "·" },
                color = Color.White, fontSize = textSp, fontWeight = FontWeight.Bold, maxLines = 1
            )
        }
    }
}

/** 共享：状态+暂停标签组 */
@Composable
private fun TvBarTags(statusTag: Pair<String, Color>?, paused: Boolean, fileLoaded: Boolean, sp: TextUnit = 11.sp) {
    if (statusTag != null) {
        Surface(color = statusTag.second.copy(alpha = 0.25f), shape = RoundedCornerShape(4.dp)) {
            Text(
                text = statusTag.first, color = statusTag.second, fontSize = sp,
                fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
            )
        }
    }
    if (paused && fileLoaded) {
        if (statusTag != null) Spacer(modifier = Modifier.width(4.dp))
        Surface(color = Color(0x30FFFFFF), shape = RoundedCornerShape(4.dp)) {
            Text("暂停", color = Color.White, fontSize = sp, modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp))
        }
    }
}

/** 共享：细进度条（宽度由 modifier 决定） */
@Composable
private fun TvBarThinProgress(progress: Float, modifier: Modifier = Modifier, height: Dp = 3.dp) {
    Box(
        modifier = modifier
            .height(height)
            .clip(RoundedCornerShape(height / 2))
            .background(Color(0x30FFFFFF))
    ) {
        Box(
            modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(progress)
                .clip(RoundedCornerShape(height / 2))
                .background(AptvAccent)
        )
    }
}

/** 共享：横排控制按钮组（播放/停止/返回分屏），barFocus 为初始焦点落点 */
@Composable
private fun TvBarControls(
    viewModel: AppViewModel,
    paused: Boolean,
    barFocus: FocusRequester?,
    oc: PlayerOverlayColors,
    showPrevNext: Boolean = false,
    buttonSize: Dp = 32.dp,
    playSize: Dp = 36.dp,
    iconSize: Dp = 17.dp,
    playIconSize: Dp = 20.dp,
    spacing: Dp = 4.dp
) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(spacing)) {
        if (showPrevNext) {
            IconButton(onClick = { viewModel.prevChannel() }, modifier = Modifier.size(buttonSize).tvFocusBorder()) {
                Icon(Icons.Default.SkipPrevious, "上一个频道", tint = oc.iconTint, modifier = Modifier.size(iconSize))
            }
        }
        IconButton(
            onClick = { viewModel.mpv.setPause(!paused) },
            modifier = Modifier
                .size(playSize)
                .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                .tvFocusBorder()
        ) {
            Icon(
                if (paused) Icons.Default.PlayArrow else Icons.Default.Pause,
                if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(playIconSize)
            )
        }
        if (showPrevNext) {
            IconButton(onClick = { viewModel.nextChannel() }, modifier = Modifier.size(buttonSize).tvFocusBorder()) {
                Icon(Icons.Default.SkipNext, "下一个频道", tint = oc.iconTint, modifier = Modifier.size(iconSize))
            }
        }
        IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(buttonSize).tvFocusBorder()) {
            Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(iconSize))
        }
        IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(buttonSize).tvFocusBorder()) {
            Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(iconSize))
        }
    }
}

/** 共享：下一节目（当前节目结束后第一个有标题的节目） */
private fun tvBarNextProgram(currentProgram: IptvEpgProgram?, epgList: List<IptvEpgProgram>): IptvEpgProgram? {
    if (currentProgram != null && currentProgram.stopTs > 0) {
        return epgList.firstOrNull { it.startTs >= currentProgram.stopTs && it.title.isNotEmpty() }
    }
    return null
}

/** 共享：节目时段文案 "HH:mm-HH:mm"，无效节目返回 null */
private fun tvBarProgramRange(program: IptvEpgProgram?, fmt: java.text.SimpleDateFormat): String? {
    if (program == null || program.stopTs <= 0) return null
    return "${fmt.format(java.util.Date(program.startTs * 1000L))}-${fmt.format(java.util.Date(program.stopTs * 1000L))}"
}

/** 共享：网速文案（cache-speed 优先，其次 video-bitrate），无数据返回 null */
private fun tvBarNetSpeedText(mpv: com.iptv.scanner.editor.pro.player.Player): String? {
    val cacheSpeed = try { mpv.getPropertyDouble("cache-speed") } catch (_: Exception) { null } ?: 0.0
    val videoBitrate = try { mpv.getPropertyInt("video-bitrate") } catch (_: Exception) { null } ?: 0
    return when {
        cacheSpeed > 0 -> formatNetSpeed(cacheSpeed.toLong())
        videoBitrate > 0 -> formatNetSpeed(videoBitrate.toLong() / 8)
        else -> null
    }
}

/** 共享：媒体徽章组（编码/分辨率/码率/HDR/声道/帧率），未加载完成时空列表 */
@Composable
private fun TvBarMediaBadges(
    fileLoaded: Boolean,
    mpv: com.iptv.scanner.editor.pro.player.Player,
    videoWidth: Int,
    videoHeight: Int,
    playbackUrl: String,
    tick: Long
): List<String> = if (fileLoaded) {
    remember(tick, videoWidth, videoHeight) {
        buildTvMediaBadges(mpv, videoWidth, videoHeight, playbackUrl)
    }
} else emptyList()

/** 共享：徽章文本（白底微透胶囊，与样式 A 一致） */
@Composable
private fun TvBarBadgeTexts(badges: List<String>, sp: TextUnit = 11.sp) {
    badges.forEach { info: String ->
        Surface(color = Color(0x30FFFFFF), shape = RoundedCornerShape(4.dp)) {
            Text(text = info, color = Color(0xCCFFFFFF), fontSize = sp, modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp))
        }
        Spacer(modifier = Modifier.width(4.dp))
    }
}

/** 底栏样式 E：居中悬浮胶囊式 —— 屏幕居中胶囊，单行容纳台标/频道/状态/节目/时钟/控制，信息完整且不遮挡两侧画面 */
@Composable
private fun TvBottomBarStyleE(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, viewModel.mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), 0L)
    // wrap 宽度胶囊在 820dp 容器内必须显式居中（Box 默认 TopStart 会贴左）
    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        GlassPanel(liquidGlass = liquidGlass, cornerRadius = 22.dp, overlayDark = true) {
            val oc = rememberPlayerOverlayColors()
            Row(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                TvBarLogo(displayInfo, 44.dp, 26.dp, 11.sp)
                if (displayInfo.idx >= 0) {
                    Text(
                        text = String.format("%03d", displayInfo.idx + 1),
                        color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium
                    )
                }
                Text(
                    text = displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 14.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                TvBarTags(statusTag, paused, fileLoaded, sp = 10.sp)
                Box(modifier = Modifier.width(1.dp).height(22.dp).background(TV_ROW_DIVIDER))
                Text(
                    text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                    color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Box(modifier = Modifier.width(1.dp).height(22.dp).background(TV_ROW_DIVIDER))
                TvBarBadgeTexts(mediaBadges.take(2), sp = 9.sp)
                Box(modifier = Modifier.width(1.dp).height(22.dp).background(TV_ROW_DIVIDER))
                TvBarClockText()
                Box(modifier = Modifier.width(1.dp).height(22.dp).background(TV_ROW_DIVIDER))
                TvBarControls(
                    viewModel, paused, barFocus, oc,
                    buttonSize = 34.dp, playSize = 40.dp, iconSize = 18.dp, playIconSize = 24.dp, spacing = 6.dp
                )
            }
        }
    }
}

/** 共享：秒级刷新时钟文本（HH:mm:ss） */
@Composable
private fun TvBarClockText(color: Color = tvPalette.textTertiary, sp: TextUnit = 13.sp) {
    var tick by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val fmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    Text(text = remember(tick) { fmt.format(java.util.Date(tick)) }, color = color, fontSize = sp, fontWeight = FontWeight.Medium)
}

/** 共享：大时钟块（HH:mm:ss 大字 + 日期星期小字，右对齐），广播电视/OSD 风格用 */
@Composable
private fun TvBarBigClock(sp: TextUnit = 22.sp, color: Color = tvPalette.textPrimary, alignEnd: Boolean = true) {
    var tick by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val dateFmt = remember { java.text.SimpleDateFormat("MM月dd日 EEEE", java.util.Locale.CHINESE) }
    Column(horizontalAlignment = if (alignEnd) Alignment.End else Alignment.Start) {
        Text(text = remember(tick) { timeFmt.format(java.util.Date(tick)) }, color = color, fontSize = sp, fontWeight = FontWeight.Bold)
        Text(text = remember(tick) { dateFmt.format(java.util.Date(tick)) }, color = tvPalette.textSecondary, fontSize = 10.sp)
    }
}

/** 共享：「正在播放:/下一节目: HH:mm - HH:mm 节目名」信息行 */
@Composable
private fun TvBarEpgLine(
    label: String,
    program: IptvEpgProgram?,
    timeFmt: java.text.SimpleDateFormat,
    titleColor: Color,
    labelColor: Color = tvPalette.textSecondary,
    titleSp: TextUnit = 12.sp
) {
    if (program == null || program.title.isEmpty()) return
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(text = "$label: ", color = labelColor, fontSize = titleSp)
        if (program.stopTs > 0) {
            Text(
                text = "${timeFmt.format(java.util.Date(program.startTs * 1000L))} - ${timeFmt.format(java.util.Date(program.stopTs * 1000L))}  ",
                color = labelColor, fontSize = titleSp
            )
        }
        Text(
            text = program.title, color = titleColor, fontSize = titleSp, fontWeight = FontWeight.Medium,
            maxLines = 1, overflow = TextOverflow.Ellipsis
        )
    }
}

/** 共享：节目简介多行文本（desc 为空时跳过） */
@Composable
private fun TvBarDescText(program: IptvEpgProgram?, maxLines: Int = 2, color: Color = Color(0x99FFFFFF)) {
    val desc = program?.desc?.trim().orEmpty()
    if (desc.isEmpty()) return
    Text(
        text = desc, color = color, fontSize = 10.sp, lineHeight = 14.sp,
        maxLines = maxLines, overflow = TextOverflow.Ellipsis
    )
}

/** 共享：REC 直播红点徽章 */
@Composable
private fun TvBarRecBadge() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(modifier = Modifier.size(6.dp).clip(androidx.compose.foundation.shape.CircleShape).background(tvPalette.danger))
        Spacer(modifier = Modifier.width(4.dp))
        Text(text = "REC", color = tvPalette.danger, fontSize = 10.sp, fontWeight = FontWeight.Bold)
    }
}

/** 底栏样式 F：双行大台标式 —— 行1 大台标+频道信息+时钟，行2 当前节目进度+下一节目+控制按钮 */
@Composable
private fun TvBottomBarStyleF(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val dateFmt = remember { java.text.SimpleDateFormat("MM月dd日 EE", java.util.Locale.CHINESE) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 10.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val netSpeed = remember(tick) { tvBarNetSpeedText(mpv) }
        val posText = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt)
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp)) {
            // 行1：大台标 + 频道信息（左） | 日期 + 时钟 + 网速（右）
            Row(verticalAlignment = Alignment.CenterVertically) {
                TvBarLogo(displayInfo, 72.dp, 40.dp, 15.sp)
                Spacer(modifier = Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (displayInfo.idx >= 0) {
                            Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                            Spacer(modifier = Modifier.width(5.dp))
                        }
                        Text(
                            text = displayInfo.name.ifEmpty { "未选择频道" },
                            color = oc.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold,
                            maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        TvBarTags(statusTag, paused, fileLoaded)
                        Spacer(modifier = Modifier.width(4.dp))
                        TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                    }
                    Spacer(modifier = Modifier.height(3.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val range = tvBarProgramRange(currentProgram, timeFmt)
                        if (range != null) {
                            Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                            Spacer(modifier = Modifier.width(6.dp))
                        }
                        Text(
                            text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                            color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                Spacer(modifier = Modifier.width(10.dp))
                // 右侧：日期/时钟/网速 竖排
                Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(1.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(text = remember(tick) { dateFmt.format(java.util.Date(tick)) }, color = tvPalette.textSecondary, fontSize = 10.sp)
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(text = posText, color = tvPalette.textTertiary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    }
                    if (netSpeed != null) Text(text = "↓ $netSpeed", color = Color(0x99FFFFFF), fontSize = 10.sp)
                }
            }
            Spacer(modifier = Modifier.height(6.dp))
            // 行2：进度 + 剩余 + 控制按钮
            Row(verticalAlignment = Alignment.CenterVertically) {
                val remainText = tvBarRemainText(tick, currentProgram)
                if (progress != null) {
                    TvBarThinProgress(progress, Modifier.weight(1f))
                    Spacer(modifier = Modifier.width(8.dp))
                } else {
                    Spacer(modifier = Modifier.weight(1f))
                }
                if (remainText != null) {
                    Text(text = remainText, color = AptvAccent, fontSize = 11.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 30.dp, playSize = 34.dp, iconSize = 16.dp)
            }
            // 行3：下一节目预告
            if (nextProgram != null) {
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(color = Color(0x22FFA500), shape = RoundedCornerShape(3.dp)) {
                        Text("下", color = tvPalette.warning, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                    }
                    Spacer(modifier = Modifier.width(5.dp))
                    Text(
                        text = "${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                        color = Color(0xB3FFFFFF), fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

/** 底栏样式 G：进度优先式 —— 行1 台标+频道+媒体徽章，行2 全宽粗进度条+时间，行3 节目/下一节目+居中按钮组（类 YouTube TV） */
@Composable
private fun TvBottomBarStyleG(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 12.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // 行1：台标 + 频道信息（左） | 媒体徽章（右）
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                TvBarLogo(displayInfo, 64.dp, 32.dp, 13.sp)
                Spacer(modifier = Modifier.width(10.dp))
                if (displayInfo.idx >= 0) {
                    Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Spacer(modifier = Modifier.width(6.dp))
                }
                Text(
                    text = displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.width(8.dp))
                TvBarTags(statusTag, paused, fileLoaded)
                Spacer(modifier = Modifier.weight(1f))
                TvBarBadgeTexts(mediaBadges)
            }
            Spacer(modifier = Modifier.height(7.dp))
            // 行2：时间 + 全宽粗进度条 + 剩余
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                val posText = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt)
                if (posText.isNotEmpty()) {
                    Text(text = posText, color = tvPalette.textSecondary, fontSize = 11.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                if (progress != null) {
                    TvBarThinProgress(progress, Modifier.weight(1f), height = 5.dp)
                    Spacer(modifier = Modifier.width(8.dp))
                } else {
                    Spacer(modifier = Modifier.weight(1f))
                }
                val remainText = tvBarRemainText(tick, currentProgram)
                if (remainText != null) Text(text = remainText, color = AptvAccent, fontSize = 11.sp)
            }
            Spacer(modifier = Modifier.height(6.dp))
            // 行3：当前节目 | 下一节目（左） + 居中按钮组（右）
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val range = tvBarProgramRange(currentProgram, timeFmt)
                        if (range != null) {
                            Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                            Spacer(modifier = Modifier.width(6.dp))
                        }
                        Text(
                            text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                            color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                    }
                    if (nextProgram != null) {
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "下一档 ${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                            color = Color(0x80FFFFFF), fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                Spacer(modifier = Modifier.width(10.dp))
                TvBarControls(
                    viewModel, paused, barFocus, oc,
                    buttonSize = 34.dp, playSize = 44.dp, iconSize = 19.dp, playIconSize = 26.dp, spacing = 10.dp
                )
            }
        }
    }
}

/** 底栏样式 H：左控制右信息式 —— 样式 D 的镜像：左侧按钮组 | 右侧三行信息（频道/节目进度/下一节目） */
@Composable
private fun TvBottomBarStyleH(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 8.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 32.dp, playSize = 36.dp, iconSize = 18.dp)
            Spacer(modifier = Modifier.width(10.dp))
            Box(modifier = Modifier.width(1.dp).height(48.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                // 行1：台标 + 频道号 + 名 + 状态 + 徽章 | 时钟
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TvBarLogo(displayInfo, 44.dp, 24.dp, 10.sp)
                    Spacer(modifier = Modifier.width(7.dp))
                    if (displayInfo.idx >= 0) {
                        Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    Text(
                        text = displayInfo.name.ifEmpty { "未选择频道" },
                        color = oc.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    TvBarTags(statusTag, paused, fileLoaded, sp = 10.sp)
                    Spacer(modifier = Modifier.width(4.dp))
                    TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                    Spacer(modifier = Modifier.weight(1f))
                    Text(
                        text = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt),
                        color = tvPalette.textSecondary, fontSize = 11.sp
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                // 行2：当前节目 + 时段 + 进度 + 剩余
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    if (range != null) {
                        Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false)
                    )
                    if (progress != null) {
                        Spacer(modifier = Modifier.width(8.dp))
                        TvBarThinProgress(progress, Modifier.width(150.dp))
                    }
                    val remainText = tvBarRemainText(tick, currentProgram)
                    if (remainText != null) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                    }
                }
                // 行3：下一节目
                if (nextProgram != null) {
                    Spacer(modifier = Modifier.height(3.dp))
                    Text(
                        text = "下一档 ${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                        color = Color(0x80FFFFFF), fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

/** 底栏样式 I：三段等分式 —— 段1 台标频道（竖排）| 段2 节目进度（竖排）| 段3 时钟+控制（竖排），竖分隔线隔开 */
@Composable
private fun TvBottomBarStyleI(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 10.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 段1：台标 + 频道号名 + 状态标签（竖排居中）
            Column(modifier = Modifier.weight(0.9f), horizontalAlignment = Alignment.CenterHorizontally) {
                TvBarLogo(displayInfo, 64.dp, 30.dp, 12.sp)
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = (if (displayInfo.idx >= 0) "${displayInfo.idx + 1} " else "") + displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 12.sp, fontWeight = FontWeight.Medium,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(3.dp))
                TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
            }
            Box(modifier = Modifier.width(1.dp).height(52.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(10.dp))
            // 段2：当前节目+时段 / 进度+剩余 / 下一节目（竖排）
            Column(modifier = Modifier.weight(1.2f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    if (range != null) {
                        Text(text = range, color = tvPalette.textSecondary, fontSize = 10.sp)
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (progress != null) {
                        TvBarThinProgress(progress, Modifier.weight(1f))
                    } else {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                    val remainText = tvBarRemainText(tick, currentProgram)
                    if (remainText != null) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                    }
                }
                if (nextProgram != null) {
                    Spacer(modifier = Modifier.height(3.dp))
                    Text(
                        text = "下一档 ${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                        color = Color(0x80FFFFFF), fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(modifier = Modifier.height(3.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp) }
            }
            Box(modifier = Modifier.width(1.dp).height(52.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(8.dp))
            // 段3：时钟 + 控制按钮（竖排居中）
            Column(modifier = Modifier.weight(0.9f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt),
                    color = tvPalette.textTertiary, fontSize = 15.sp, fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(4.dp))
                TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 28.dp, playSize = 32.dp, iconSize = 15.dp, playIconSize = 18.dp, spacing = 2.dp)
            }
        }
    }
}

/** 底栏样式 J：OSD 大字式 —— 左侧居中大字频道名+节目信息+进度，右侧竖排控制按钮（换台 OSD 质感） */
@Composable
private fun TvBottomBarStyleJ(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 14.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左侧 OSD 信息区（垂直居中三行）
            Column(modifier = Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                // 行1：频道号（大）+ 频道名（大）+ 状态 + 徽章
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (displayInfo.idx >= 0) {
                        Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    Text(
                        text = displayInfo.name.ifEmpty { "未选择频道" },
                        color = oc.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    TvBarTags(statusTag, paused, fileLoaded, sp = 10.sp)
                    Spacer(modifier = Modifier.width(6.dp))
                    TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                }
                Spacer(modifier = Modifier.height(3.dp))
                // 行2：当前节目 · 时段 · 时钟 · 剩余
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    if (range != null) Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Text(text = "·", color = Color(0x60FFFFFF), fontSize = 11.sp)
                    Text(
                        text = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt),
                        color = tvPalette.textSecondary, fontSize = 11.sp
                    )
                    val remainText = tvBarRemainText(tick, currentProgram)
                    if (remainText != null) Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                }
                Spacer(modifier = Modifier.height(4.dp))
                // 行3：居中细进度条
                if (progress != null) {
                    TvBarThinProgress(progress, Modifier.fillMaxWidth(0.7f), height = 3.dp)
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            Box(modifier = Modifier.width(1.dp).height(52.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(10.dp))
            // 右侧竖排按钮组（播放/停止/返回分屏）
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                IconButton(
                    onClick = { viewModel.mpv.setPause(!paused) },
                    modifier = Modifier
                        .size(32.dp)
                        .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                        .tvFocusBorder()
                ) {
                    Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(18.dp))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(28.dp).tvFocusBorder()) {
                        Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(15.dp))
                    }
                    IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(28.dp).tvFocusBorder()) {
                        Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(15.dp))
                    }
                }
            }
        }
    }
}

/** 底栏样式 K：控制台双行式 —— 行1 居中大按钮组，行2 台标+频道+状态 | 节目+时段+进度+时钟+剩余（样式 C 的倒置） */
@Composable
private fun TvBottomBarStyleK(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 12.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // 行1：居中大按钮组
            TvBarControls(
                viewModel, paused, barFocus, oc,
                buttonSize = 36.dp, playSize = 46.dp, iconSize = 20.dp, playIconSize = 27.dp, spacing = 14.dp
            )
            Spacer(modifier = Modifier.height(6.dp))
            // 行2：台标+频道+状态+徽章 | 节目+时段+进度+时钟+剩余
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                TvBarLogo(displayInfo, 40.dp, 22.dp, 9.sp)
                Spacer(modifier = Modifier.width(7.dp))
                if (displayInfo.idx >= 0) {
                    Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                    Spacer(modifier = Modifier.width(5.dp))
                }
                Text(
                    text = displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.width(6.dp))
                TvBarTags(statusTag, paused, fileLoaded, sp = 10.sp)
                Spacer(modifier = Modifier.width(4.dp))
                TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                Spacer(modifier = Modifier.weight(1f))
                val range = tvBarProgramRange(currentProgram, timeFmt)
                if (range != null) {
                    Text(text = range, color = tvPalette.textSecondary, fontSize = 10.sp)
                    Spacer(modifier = Modifier.width(6.dp))
                }
                Text(
                    text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                    color = oc.textSecondary, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                if (progress != null) {
                    Spacer(modifier = Modifier.width(8.dp))
                    TvBarThinProgress(progress, Modifier.width(110.dp))
                }
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = tvBarPosText(tick, timePos, playbackMode, showExitCatchup, fullTimeFmt),
                    color = tvPalette.textSecondary, fontSize = 10.sp
                )
                val remainText = tvBarRemainText(tick, currentProgram)
                if (remainText != null) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                }
            }
        }
    }
}

/** 底栏样式 L：卡片网格式 —— 左信息块三行（频道/节目进度/下一节目）| 中时钟块 | 右 2x2 按钮网格 + 返回分屏 */
@Composable
private fun TvBottomBarStyleL(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val dateFmt = remember { java.text.SimpleDateFormat("MM月dd日", java.util.Locale.CHINESE) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 10.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val netSpeed = remember(tick) { tvBarNetSpeedText(mpv) }
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左信息块（三行）
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TvBarLogo(displayInfo, 44.dp, 24.dp, 10.sp)
                    Spacer(modifier = Modifier.width(7.dp))
                    if (displayInfo.idx >= 0) {
                        Text(text = String.format("%03d", displayInfo.idx + 1), color = AptvAccent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                        Spacer(modifier = Modifier.width(5.dp))
                    }
                    Text(
                        text = displayInfo.name.ifEmpty { "未选择频道" },
                        color = oc.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    TvBarTags(statusTag, paused, fileLoaded, sp = 10.sp)
                    Spacer(modifier = Modifier.width(4.dp))
                    TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                }
                Spacer(modifier = Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    if (range != null) {
                        Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false)
                    )
                    if (progress != null) {
                        Spacer(modifier = Modifier.width(8.dp))
                        TvBarThinProgress(progress, Modifier.width(110.dp))
                    }
                    val remainText = tvBarRemainText(tick, currentProgram)
                    if (remainText != null) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                    }
                }
                if (nextProgram != null) {
                    Spacer(modifier = Modifier.height(3.dp))
                    Text(
                        text = "下一档 ${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                        color = Color(0x80FFFFFF), fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
            }
            Spacer(modifier = Modifier.width(10.dp))
            Box(modifier = Modifier.width(1.dp).height(52.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(10.dp))
            // 中时钟块：大时钟 + 日期 + 网速
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = remember(tick) { fullTimeFmt.format(java.util.Date(tick)) },
                    color = tvPalette.textTertiary, fontSize = 16.sp, fontWeight = FontWeight.Bold
                )
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(text = remember(tick) { dateFmt.format(java.util.Date(tick)) }, color = tvPalette.textSecondary, fontSize = 9.sp)
                    if (netSpeed != null) Text(text = "↓$netSpeed", color = Color(0x99FFFFFF), fontSize = 9.sp)
                }
            }
            Spacer(modifier = Modifier.width(10.dp))
            Box(modifier = Modifier.width(1.dp).height(52.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(8.dp))
            // 右按钮组（播放/停止 | 返回分屏）
            Column(verticalArrangement = Arrangement.spacedBy(4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    IconButton(
                        onClick = { viewModel.mpv.setPause(!paused) },
                        modifier = Modifier
                            .size(32.dp)
                            .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                            .tvFocusBorder()
                    ) {
                        Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(18.dp))
                    }
                    IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                        Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(16.dp))
                    }
                }
                IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                    Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(17.dp))
                }
            }
        }
    }
}

/** 底栏样式 M：广播电视式 —— 贴底全宽渐变条：左大台标 | 中节目信息列（剩余/正在播放/下一节目/简介）| 右徽章+大时钟日期 */
@Composable
private fun TvBottomBarStyleM(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 0.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)
        val remainText = tvBarRemainText(tick, currentProgram)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左：大台标 + 频道号名
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                TvBarLogo(displayInfo, 104.dp, 46.dp, 16.sp)
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = (if (displayInfo.idx >= 0) "${displayInfo.idx + 1} " else "") + displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 11.sp, fontWeight = FontWeight.Medium,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
            }
            Spacer(modifier = Modifier.width(14.dp))
            // 中：节目信息列
            Column(modifier = Modifier.weight(1.4f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (remainText != null) Text(text = "剩余播放 $remainText", color = AptvAccent, fontSize = 11.sp, fontWeight = FontWeight.Medium)
                    if (paused) TvBarTags(null, true, fileLoaded, sp = 10.sp)
                }
                Spacer(modifier = Modifier.height(3.dp))
                TvBarEpgLine("正在播放", currentProgram, timeFmt, oc.textPrimary, titleSp = 12.sp)
                Spacer(modifier = Modifier.height(2.dp))
                TvBarEpgLine("下一节目", nextProgram, timeFmt, oc.textSecondary, titleSp = 11.sp)
                Spacer(modifier = Modifier.height(3.dp))
                TvBarDescText(currentProgram, maxLines = 2)
                Spacer(modifier = Modifier.height(4.dp))
                TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 26.dp, playSize = 30.dp, iconSize = 14.dp, playIconSize = 16.dp, spacing = 2.dp)
            }
            Spacer(modifier = Modifier.width(12.dp))
            // 右：媒体徽章 + 状态 + 大时钟
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
                    TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                }
                TvBarBigClock(sp = 21.sp, alignEnd = true)
            }
        }
    }
}

/** 底栏样式 N：机顶盒 OSD 式 —— 左大台标+频道号名，右 REC+技术徽章+大时钟，底部技术参数行（分辨率/帧率/码率/网速） */
@Composable
private fun TvBottomBarStyleN(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 6.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)
        val netSpeed = remember(tick) { tvBarNetSpeedText(mpv) }
        val posText = tvBarPosText(tick, 0.0, playbackMode, showExitCatchup, timeFmt)
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp)) {
            // 上区：台标频道 | EPG | 徽章+时钟
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    TvBarLogo(displayInfo, 72.dp, 38.dp, 13.sp)
                    Spacer(modifier = Modifier.height(3.dp))
                    Text(
                        text = (if (displayInfo.idx >= 0) "${displayInfo.idx + 1}. " else "") + displayInfo.name.ifEmpty { "未选择频道" },
                        color = oc.textPrimary, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    TvBarEpgLine("正在播放", currentProgram, timeFmt, oc.textPrimary, titleSp = 11.sp)
                    TvBarEpgLine("下一节目", nextProgram, timeFmt, oc.textSecondary, titleSp = 10.sp)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
                        if (netSpeed != null) Text(text = "↓ $netSpeed", color = tvPalette.success, fontSize = 10.sp)
                        val remainText = tvBarRemainText(tick, currentProgram)
                        if (remainText != null) Text(text = remainText, color = AptvAccent, fontSize = 10.sp)
                    }
                }
                Spacer(modifier = Modifier.width(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        if (fileLoaded && !paused) TvBarRecBadge()
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp) }
                    }
                    TvBarBigClock(sp = 20.sp, color = tvPalette.textPrimary)
                }
            }
            Spacer(modifier = Modifier.height(5.dp))
            // 底部技术参数行：位置时间 | 徽章全列 | 控制按钮
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (posText.isNotEmpty()) {
                    Text(text = posText, color = tvPalette.textDisabled, fontSize = 10.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                }
                Row(modifier = Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(4.dp)) { TvBarBadgeTexts(mediaBadges.drop(3), sp = 9.sp) }
                TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 26.dp, playSize = 30.dp, iconSize = 14.dp, playIconSize = 16.dp, spacing = 2.dp)
            }
        }
    }
}

/** 底栏样式 O：影院 EPG 卡式 —— 居中宽卡：左大台标 | 右频道名+徽章+距结束+正在播放+简介+下一节目+按钮 */
@Composable
private fun TvBottomBarStyleO(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        GlassPanel(liquidGlass = liquidGlass, cornerRadius = 12.dp, overlayDark = true, modifier = Modifier.fillMaxWidth(0.88f)) {
            val oc = rememberPlayerOverlayColors()
            val timePos by mpv.timePos.collectAsState()
            val duration by mpv.duration.collectAsState()
            val progress = computeTvBarProgress(currentProgram, timePos, duration)
            val nextProgram = tvBarNextProgram(currentProgram, epgList)
            val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)
            val remainText = tvBarRemainText(tick, currentProgram)
            val netSpeed = remember(tick) { tvBarNetSpeedText(mpv) }
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                TvBarLogo(displayInfo, 80.dp, 54.dp, 14.sp)
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    // 行1：频道名 + 状态 + 徽章 | 距结束
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = displayInfo.name.ifEmpty { "未选择频道" },
                            color = oc.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold,
                            maxLines = 1, overflow = TextOverflow.Ellipsis
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
                        Spacer(modifier = Modifier.width(6.dp))
                        TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                        Spacer(modifier = Modifier.weight(1f))
                        if (remainText != null) Text(text = "距结束: $remainText", color = AptvAccent, fontSize = 11.sp)
                    }
                    Spacer(modifier = Modifier.height(3.dp))
                    TvBarEpgLine("正在播放", currentProgram, timeFmt, oc.textPrimary, titleSp = 12.sp)
                    Spacer(modifier = Modifier.height(2.dp))
                    TvBarDescText(currentProgram, maxLines = 2)
                    Spacer(modifier = Modifier.height(3.dp))
                    // 行4：下一节目 | 时钟+网速+按钮
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) {
                            TvBarEpgLine("下一节目", nextProgram, timeFmt, oc.textSecondary, titleSp = 11.sp)
                            if (netSpeed != null) {
                                Spacer(modifier = Modifier.height(1.dp))
                                Text(text = "↓ $netSpeed", color = Color(0x80FFFFFF), fontSize = 9.sp)
                            }
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = remember(tick) { fullTimeFmt.format(java.util.Date(tick)) },
                            color = tvPalette.textTertiary, fontSize = 12.sp, fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 26.dp, playSize = 30.dp, iconSize = 14.dp, playIconSize = 16.dp, spacing = 2.dp)
                    }
                    // 底部细进度条
                    if (progress != null) {
                        Spacer(modifier = Modifier.height(4.dp))
                        TvBarThinProgress(progress, Modifier.fillMaxWidth(), height = 2.dp)
                    }
                }
            }
        }
    }
}

/** 底栏样式 P：仪表盘 OSD 式 —— 左大台标+频道+日期 | 中节目+彩色渐变进度条+下一档 | 右徽章+大时钟 */
@Composable
private fun TvBottomBarStyleP(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val dateFmt = remember { java.text.SimpleDateFormat("MM月dd日 EEEE", java.util.Locale.CHINESE) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 6.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val timePos by mpv.timePos.collectAsState()
        val duration by mpv.duration.collectAsState()
        val progress = computeTvBarProgress(currentProgram, timePos, duration)
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)
        val remainText = tvBarRemainText(tick, currentProgram)
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左：大台标 + 频道号名 + 日期
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                TvBarLogo(displayInfo, 96.dp, 48.dp, 15.sp)
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = (if (displayInfo.idx >= 0) "${displayInfo.idx + 1}. " else "") + displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = remember(tick) { dateFmt.format(java.util.Date(tick)) },
                    color = tvPalette.textSecondary, fontSize = 9.sp
                )
            }
            Spacer(modifier = Modifier.width(12.dp))
            // 中：节目 + 彩色渐变进度条 + 下一档 + 按钮
            Column(modifier = Modifier.weight(1.3f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    if (range != null) {
                        Text(text = range, color = tvPalette.textSecondary, fontSize = 11.sp)
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textPrimary, fontSize = 13.sp, fontWeight = FontWeight.Medium,
                        maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.weight(1f))
                    TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
                }
                Spacer(modifier = Modifier.height(4.dp))
                // 彩色渐变进度条（彩虹感）
                if (progress != null) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(5.dp)
                            .clip(RoundedCornerShape(2.5.dp))
                            .background(Color(0x33FFFFFF))
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth(progress)
                                .fillMaxHeight()
                                .clip(RoundedCornerShape(2.5.dp))
                                .background(
                                    Brush.horizontalGradient(
                                        listOf(AptvAccent, tvPalette.info, tvPalette.success)
                                    )
                                )
                        )
                    }
                } else {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(5.dp)
                            .clip(RoundedCornerShape(2.5.dp))
                            .background(Color(0x22FFFFFF))
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (nextProgram != null) {
                        Text(
                            text = "下一档 ${timeFmt.format(java.util.Date(nextProgram.startTs * 1000L))} ${nextProgram.title}",
                            color = Color(0x80FFFFFF), fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )
                    } else {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                    if (remainText != null) Text(text = "+$remainText", color = AptvAccent, fontSize = 10.sp)
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 26.dp, playSize = 30.dp, iconSize = 14.dp, playIconSize = 16.dp, spacing = 2.dp)
                    Spacer(modifier = Modifier.weight(1f))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { TvBarBadgeTexts(mediaBadges, sp = 9.sp) }
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            // 右：大时钟
            TvBarBigClock(sp = 22.sp, color = tvPalette.dangerSoft)
        }
    }
}

/** 底栏样式 Q：海报卡片式 —— 居中小卡：顶部细进度条，左方形台标 | 右频道名+徽章+正在播放+简介+下一节目 | 竖排按钮 */
@Composable
private fun TvBottomBarStyleQ(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val mpv = viewModel.mpv
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)

    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        GlassPanel(liquidGlass = liquidGlass, cornerRadius = 10.dp, overlayDark = true, modifier = Modifier.fillMaxWidth(0.62f)) {
            val oc = rememberPlayerOverlayColors()
            val timePos by mpv.timePos.collectAsState()
            val duration by mpv.duration.collectAsState()
            val progress = computeTvBarProgress(currentProgram, timePos, duration)
            val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
            val mediaBadges = TvBarMediaBadges(fileLoaded, mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), 0L)
            Column(modifier = Modifier.fillMaxWidth()) {
                // 顶部细进度条
                if (progress != null) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(2.dp)
                            .background(Color(0x22FFFFFF))
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth(progress)
                                .fillMaxHeight()
                                .background(AptvAccent)
                        )
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TvBarLogo(displayInfo, 62.dp, 62.dp, 12.sp)
                    Spacer(modifier = Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = displayInfo.name.ifEmpty { "未选择频道" },
                                color = oc.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                                maxLines = 1, overflow = TextOverflow.Ellipsis
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
                            Spacer(modifier = Modifier.weight(1f))
                            TvBarBadgeTexts(mediaBadges.take(3), sp = 9.sp)
                        }
                        Spacer(modifier = Modifier.height(2.dp))
                        TvBarEpgLine("正在播放", currentProgram, timeFmt, oc.textPrimary, titleSp = 11.sp)
                        Spacer(modifier = Modifier.height(1.dp))
                        TvBarDescText(currentProgram, maxLines = 1)
                        Spacer(modifier = Modifier.height(1.dp))
                        TvBarEpgLine("下一节目", tvBarNextProgram(currentProgram, epgList), timeFmt, oc.textSecondary, titleSp = 10.sp)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    // 竖排按钮（播放/停止/返回分屏）
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        IconButton(
                            onClick = { viewModel.mpv.setPause(!paused) },
                            modifier = Modifier
                                .size(26.dp)
                                .then(if (barFocus != null) Modifier.focusRequester(barFocus) else Modifier)
                                .tvFocusBorder()
                        ) {
                            Icon(if (paused) Icons.Default.PlayArrow else Icons.Default.Pause, if (paused) "播放" else "暂停", tint = oc.accent, modifier = Modifier.size(15.dp))
                        }
                        IconButton(onClick = { viewModel.stopPlay() }, modifier = Modifier.size(26.dp).tvFocusBorder()) {
                            Icon(Icons.Default.Stop, "停止", tint = oc.iconTint, modifier = Modifier.size(14.dp))
                        }
                        IconButton(onClick = { viewModel.setLandscapeSplitMode(true) }, modifier = Modifier.size(26.dp).tvFocusBorder()) {
                            Icon(Icons.Default.FullscreenExit, "返回分屏", tint = oc.iconTint, modifier = Modifier.size(14.dp))
                        }
                    }
                }
            }
        }
    }
}

/** 底栏样式 R：节目时间轴式 —— 左频道块 | 中三档节目时间轴（当前高亮/下一/再下一）| 右大时钟+按钮 */
@Composable
private fun TvBottomBarStyleR(
    viewModel: AppViewModel,
    displayInfo: ChannelDisplayInfo,
    paused: Boolean,
    fileLoaded: Boolean,
    videoWidth: Int,
    videoHeight: Int,
    showExitCatchup: Boolean,
    playbackMode: PlayMode,
    currentProgram: IptvEpgProgram?,
    epgList: List<IptvEpgProgram>,
    barFocus: FocusRequester? = null
) {
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { tick = System.currentTimeMillis(); delay(1000L) } }
    val timeFmt = remember { java.text.SimpleDateFormat("HH:mm", java.util.Locale.getDefault()) }
    val fullTimeFmt = remember { java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault()) }
    val statusTag = tvBarStatusTag(fileLoaded, playbackMode, showExitCatchup)
    val mediaBadges = TvBarMediaBadges(fileLoaded, viewModel.mpv, videoWidth, videoHeight, viewModel.getCurrentPlaybackUrl(), tick)

    GlassPanel(liquidGlass = liquidGlass, cornerRadius = 10.dp, overlayDark = true) {
        val oc = rememberPlayerOverlayColors()
        val nextProgram = tvBarNextProgram(currentProgram, epgList)
        val thirdProgram = if (nextProgram != null && nextProgram.stopTs > 0) {
            epgList.firstOrNull { it.startTs >= nextProgram.stopTs && it.title.isNotEmpty() }
        } else null
        val netSpeed = remember(tick) { tvBarNetSpeedText(viewModel.mpv) }
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左：频道块
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                TvBarLogo(displayInfo, 72.dp, 36.dp, 12.sp)
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = (if (displayInfo.idx >= 0) "${displayInfo.idx + 1} " else "") + displayInfo.name.ifEmpty { "未选择频道" },
                    color = oc.textPrimary, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(2.dp))
                TvBarTags(statusTag, paused, fileLoaded, sp = 9.sp)
            }
            Spacer(modifier = Modifier.width(10.dp))
            Box(modifier = Modifier.width(1.dp).height(56.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(10.dp))
            // 中：三档节目时间轴
            Column(modifier = Modifier.weight(1.2f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                // 当前节目（高亮）
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier.size(5.dp).clip(androidx.compose.foundation.shape.CircleShape).background(AptvAccent)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    val range = tvBarProgramRange(currentProgram, timeFmt)
                    Text(text = range ?: "正在播放", color = AptvAccent, fontSize = 10.sp, fontWeight = FontWeight.Medium)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = currentProgram?.title?.ifEmpty { null } ?: "精彩节目",
                        color = oc.textPrimary, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f)
                    )
                    val remainText = tvBarRemainText(tick, currentProgram)
                    if (remainText != null) Text(text = remainText, color = AptvAccent, fontSize = 9.sp)
                }
                // 下一档
                TvBarTimelineSlot(nextProgram, timeFmt, oc.textSecondary)
                // 再下一档
                TvBarTimelineSlot(thirdProgram, timeFmt, Color(0x66FFFFFF))
            }
            Spacer(modifier = Modifier.width(10.dp))
            Box(modifier = Modifier.width(1.dp).height(56.dp).background(TV_ROW_DIVIDER))
            Spacer(modifier = Modifier.width(8.dp))
            // 右：大时钟 + 徽章 + 网速 + 按钮
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(
                    text = remember(tick) { fullTimeFmt.format(java.util.Date(tick)) },
                    color = tvPalette.textTertiary, fontSize = 16.sp, fontWeight = FontWeight.Bold
                )
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { TvBarBadgeTexts(mediaBadges.take(2), sp = 9.sp) }
                if (netSpeed != null) Text(text = "↓ $netSpeed", color = Color(0x99FFFFFF), fontSize = 9.sp)
                TvBarControls(viewModel, paused, barFocus, oc, buttonSize = 26.dp, playSize = 30.dp, iconSize = 14.dp, playIconSize = 16.dp, spacing = 2.dp)
            }
        }
    }
}

/** 共享：时间轴槽位行（时段 + 节目名），无节目时显示占位 */
@Composable
private fun TvBarTimelineSlot(program: IptvEpgProgram?, timeFmt: java.text.SimpleDateFormat, titleColor: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(modifier = Modifier.size(5.dp).clip(androidx.compose.foundation.shape.CircleShape).background(Color(0x33FFFFFF)))
        Spacer(modifier = Modifier.width(6.dp))
        Text(
            text = program?.let { if (it.stopTs > 0) "${timeFmt.format(java.util.Date(it.startTs * 1000L))} - ${timeFmt.format(java.util.Date(it.stopTs * 1000L))}" else "" } ?: "--:-- - --:--",
            color = tvPalette.textDisabled, fontSize = 10.sp
        )
        Spacer(modifier = Modifier.width(6.dp))
        Text(
            text = program?.title?.ifEmpty { null } ?: "暂无节目预告",
            color = titleColor, fontSize = 11.sp,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f)
        )
    }
}

internal fun buildTvMediaBadges(mpv: com.iptv.scanner.editor.pro.player.Player, videoWidth: Int, videoHeight: Int, playbackUrl: String = ""): List<String> {
    val result = mutableListOf<String>()
    val mediaInfo = try { mpv.getMediaInfo() } catch (_: Exception) { emptyMap() }
    // 视频编码
    mediaInfo["videoCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
        result.add(codec.removePrefix("video/").removePrefix("audio/").uppercase())
    }
    // 分辨率
    if (videoWidth > 0 && videoHeight > 0) {
        result.add(when { videoWidth >= 3800 -> "4K"; videoWidth >= 1900 -> "1080P"; videoWidth >= 1200 -> "720P"; else -> "${videoHeight}P" })
    }
    // 视频比特率
    val videoBitrate = try { mpv.getPropertyInt("video-bitrate") } catch (_: Exception) { null }
    if (videoBitrate != null && videoBitrate > 0) {
        val kbps = videoBitrate / 1000
        if (kbps >= 1000) {
            result.add("%.1fMbps".format(kbps / 1000.0))
        } else {
            result.add("${kbps}kbps")
        }
    }
    // HDR
    val gamma = mediaInfo["videoGamma"]
    val primaries = mediaInfo["videoPrimaries"]
    when {
        gamma == "hlg" -> result.add("HLG")
        gamma == "pq" -> result.add("HDR10")
        primaries == "bt.2020" -> result.add("HDR")
    }
    // 音频编码
    mediaInfo["audioCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
        result.add(codec.removePrefix("audio/").uppercase())
    }
    // 音频声道
    val channels = try { mpv.getPropertyInt("audio-params/channels") } catch (_: Exception) { null }
    if (channels != null && channels > 0) {
        result.add(when (channels) { 1 -> "单声道"; 2 -> "立体声"; 6 -> "5.1ch"; 8 -> "7.1ch"; else -> "${channels}ch" })
    }
    // 帧率
    mediaInfo["fps"]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" && it != "0.000" }?.let { fps ->
        val fpsVal = fps.toFloatOrNull()
        result.add(if (fpsVal != null) "${fpsVal.toInt()}FPS" else "${fps}FPS")
    }
    // 容器格式
    mediaInfo["containerFormat"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { fmt ->
        val short = fmt.substringAfter("/").substringAfterLast(".")
        if (short.isNotEmpty()) result.add(short.uppercase())
    }
    // 协议
    if (playbackUrl.isNotEmpty()) {
        val proto = playbackUrl.substringBefore("://").lowercase()
        when (proto) {
            "http", "https" -> result.add("HTTP")
            "rtsp" -> result.add("RTSP")
            "udp", "rtp" -> result.add("UDP")
            "file" -> result.add("LOCAL")
        }
    }
    return result.take(8)
}
