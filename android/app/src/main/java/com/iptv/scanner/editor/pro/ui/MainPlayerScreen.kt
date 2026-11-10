package com.iptv.scanner.editor.pro.ui

import android.content.Context
import android.content.res.Configuration
import android.util.Log
import androidx.compose.runtime.key
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.draw.shadow
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.Brightness4
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material.icons.filled.PictureInPicture
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.RadioButton
import androidx.activity.compose.BackHandler
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.movableContentOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import com.iptv.scanner.editor.pro.R
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import com.iptv.scanner.editor.pro.data.ReminderItem
import com.iptv.scanner.editor.pro.data.UserPrefs
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.mpv.MPVView
import com.iptv.scanner.editor.pro.mpv.MPVViewLike
import com.iptv.scanner.editor.pro.player.PlayerType
import com.iptv.scanner.editor.pro.player.ProgressHelper
import com.iptv.scanner.editor.pro.ui.ChannelTab
import com.iptv.scanner.editor.pro.ui.theme.LocalHazeState
import com.iptv.scanner.editor.pro.ui.theme.PlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.liquidGlassSource
import com.iptv.scanner.editor.pro.ui.theme.rememberLiquidHazeState
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import androidx.media3.ui.PlayerView
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material3.AlertDialog
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.foundation.layout.PaddingValues
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import android.net.Uri
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Web
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.ViewList
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import com.iptv.scanner.editor.pro.player.CatchupHelper
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.material3.SheetState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.SwapHoriz
import java.io.File

/**
 * 主播放屏：MPVView + 透明控制层 + 面板抽屉 + OSD 浮层。
 *
 * 层次结构（从底到顶）：
 * 1. MPVView（全屏视频渲染，SurfaceView，默认 Z-order：渲染在普通 View 下方，通过透明 "打孔" 显示视频）
 * 2. 透明点击层（点击切换控制层显示/隐藏，仅当无面板打开时启用）
 * 3. 控制层（顶部侧边栏按钮 + 底部 ControlPanel，仅当 controlsVisible=true 且无面板打开时显示）
 * 4. 面板层（ChannelsPanel 右抽屉 / EpgPanel 左抽屉 / MainMenuPanel 全屏覆盖）
 * 5. OSD 浮层（顶部居中，3 秒自动隐藏，最顶层确保反馈可见）
 *
 * 与 PC 端主框架对齐：
 * - 点击视频区域切换控制层
 * - 控制层显示时，顶部有 3 个面板入口（频道列表/EPG/菜单）
 * - 控制层底部是 ControlPanel（3 行布局）
 * - 面板打开时控制层自动隐藏
 */
/** EXO 播放器渲染视图 tag（SurfaceView/TextureView 切换时按 tag 重建子 View） */
private const val TAG_EXO_SURFACE = "exo_surface"
private const val TAG_EXO_TEXTURE = "exo_texture"

@Composable
fun MainPlayerScreen(viewModel: AppViewModel) {
    val uiMode by viewModel.uiMode.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()


    val controlsVisible by viewModel.controlsVisible.collectAsState()
    val channelsPanelOpen by viewModel.channelsPanelOpen.collectAsState()
    val epgPanelOpen by viewModel.epgPanelOpen.collectAsState()
    val menuPanelOpen by viewModel.menuPanelOpen.collectAsState()
    val tvUnifiedPanelOpen by viewModel.tvUnifiedPanelOpen.collectAsState()
    val fileBrowserOpen by viewModel.fileBrowserOpen.collectAsState()
    val sourceManagerOpen by viewModel.sourceManagerOpen.collectAsState()
    val playerSettingsOpen by viewModel.playerSettingsOpen.collectAsState()
    val videoSettingsOpen by viewModel.videoSettingsOpen.collectAsState()
    val audioSettingsOpen by viewModel.audioSettingsOpen.collectAsState()
    val subtitleSettingsOpen by viewModel.subtitleSettingsOpen.collectAsState()
    val subtitleSearchOpen by viewModel.subtitleSearchOpen.collectAsState()
    val playbackPanelOpen by viewModel.playbackPanelOpen.collectAsState()
    val screenshotPanelOpen by viewModel.screenshotPanelOpen.collectAsState()
    val viewSettingsOpen by viewModel.viewSettingsOpen.collectAsState()
    val aboutPanelOpen by viewModel.aboutPanelOpen.collectAsState()
    val mappingPanelOpen by viewModel.mappingPanelOpen.collectAsState()
    val avSyncPanelOpen by viewModel.avSyncPanelOpen.collectAsState()
    val networkPanelOpen by viewModel.networkPanelOpen.collectAsState()
    val toolsPanelOpen by viewModel.toolsPanelOpen.collectAsState()
    val playerToolsOpen by viewModel.playerToolsOpen.collectAsState()
    val scanPanelOpen by viewModel.scanPanelOpen.collectAsState()
    val reminderPanelOpen by viewModel.reminderPanelOpen.collectAsState()
    val resumePanelOpen by viewModel.resumePanelOpen.collectAsState()
    val bookmarkPanelOpen by viewModel.bookmarkPanelOpen.collectAsState()
    val epgTimelineOpen by viewModel.epgTimelineOpen.collectAsState()
    val searchPanelOpen by viewModel.searchPanelOpen.collectAsState()
    val streamQualityPanelOpen by viewModel.streamQualityPanelOpen.collectAsState()
    val recentPanelOpen by viewModel.recentPanelOpen.collectAsState()
    val clipExportPanelOpen by viewModel.clipExportPanelOpen.collectAsState()
    val audioVisualizerOpen by viewModel.audioVisualizerOpen.collectAsState()
    val lyricsOpen by viewModel.lyricsOpen.collectAsState()
    val exitConfirmOpen by viewModel.exitConfirmOpen.collectAsState()
    val channelInfoOpen by viewModel.channelInfoOpen.collectAsState()
    val openUrlDialogOpen by viewModel.openUrlDialogOpen.collectAsState()
    val updateDialogOpen by viewModel.updateDialogOpen.collectAsState()
    val triggeredReminder by viewModel.triggeredReminder.collectAsState()
    val osd by viewModel.osd.collectAsState()
    // 零频道播放页直达订阅源管理时，让面板初始焦点落到 URL 输入框
    val sourceManagerFocusUrl by viewModel.sourceManagerFocusUrl.collectAsState()

    val player = viewModel.mpv  // 当前 Player 实例（类型为 Player 接口）
    val paused by player.paused.collectAsState()
    val fileLoaded by player.fileLoaded.collectAsState()
    val showHome by viewModel.showHome.collectAsState()
    val portraitTab by viewModel.portraitTab.collectAsState()
    val landscapeSidebarVisible by viewModel.landscapeSidebarVisible.collectAsState()
    val multiViewState by viewModel.multiViewState.collectAsState()
    // 应用内伪全屏：大屏设备忽略 requestedOrientation 时仍渲染横屏布局
    val forceLandscape by viewModel.forceLandscapeLayout.collectAsState()

    // 横竖屏判定（供 BACK 处理使用；横屏 TV 风格无首页 UI）
    val isLandscape =
        androidx.compose.ui.platform.LocalConfiguration.current.orientation ==
        android.content.res.Configuration.ORIENTATION_LANDSCAPE
    /** 布局横屏 = 真实横屏 或 应用内伪全屏 */
    val layoutLandscape = isLandscape || forceLandscape

    // 系统返回键处理：右侧详情面板→侧边栏→退出伪全屏→退出多画面→返回首页→退出确认
    BackHandler(enabled = true) {
        when {
            LandscapeSplitDetail.stack.isNotEmpty() -> {
                // 横屏首页右侧详情面板（设置/工具 master-detail）：BACK 逐级返回（三列→两列→概览）
                LandscapeSplitDetail.pop()
            }
            landscapeSidebarVisible || channelsPanelOpen || epgPanelOpen || menuPanelOpen || tvUnifiedPanelOpen ||
            fileBrowserOpen || sourceManagerOpen || playerSettingsOpen || videoSettingsOpen ||
            audioSettingsOpen || subtitleSettingsOpen || subtitleSearchOpen || playbackPanelOpen ||
            screenshotPanelOpen || viewSettingsOpen || aboutPanelOpen || mappingPanelOpen ||
            avSyncPanelOpen || networkPanelOpen || toolsPanelOpen || playerToolsOpen || scanPanelOpen ||
            reminderPanelOpen || resumePanelOpen || bookmarkPanelOpen || epgTimelineOpen ||
            searchPanelOpen || streamQualityPanelOpen || recentPanelOpen || clipExportPanelOpen ||
            audioVisualizerOpen || lyricsOpen || channelInfoOpen || openUrlDialogOpen -> {
                viewModel.closeAllPanels()
            }
            forceLandscape && !isLandscape -> {
                // 伪全屏（物理竖屏 + 横屏布局）：BACK 先退出伪全屏回竖屏布局
                viewModel.setForceLandscapeLayout(false)
            }
            multiViewState.active -> {
                viewModel.exitMultiView()
            }
            !showHome -> {
                // 竖屏有首页可回；横屏（TV 风格）：全屏→分屏→首页→退出确认
                // TV 无独立首页：全屏即主页，分屏是最后一层，退回全屏后再按 BACK 进入退出确认
                // （不能重新打开侧边栏，否则 BACK 会在关/开侧边栏之间死循环）
                if (uiMode.isTV) {
                    if (viewModel.landscapeSplitMode.value) {
                        viewModel.setLandscapeSplitMode(false)
                    } else {
                        viewModel.showExitConfirm()
                    }
                } else if (layoutLandscape) {
                    if (!viewModel.landscapeSplitMode.value) {
                        viewModel.setLandscapeSplitMode(true)
                    } else {
                        viewModel.showHomeScreen()
                    }
                } else {
                    viewModel.showHomeScreen()
                }
            }
            else -> {
                if (exitConfirmOpen) {
                    viewModel.dismissExitConfirm()
                } else {
                    viewModel.showExitConfirm()
                }
            }
        }
    }

    // 兜底：横屏首页详情路由下，面板内 X（toggle）会把 open 状态残留为 true（弹窗已被
    // suppress 不显示）；离开首页进入播放页时统一清掉，避免残留弹窗在播放页突然出现
    LaunchedEffect(showHome) {
        if (!showHome) viewModel.closeAllPanels()
    }

    // SAF 文件选择器 —— 打开播放列表（M3U/M3U8）
    val playlistLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.importPlaylist(uri)
    }

    // SAF 文件选择器 —— 打开本地视频/音频
    val videoLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.playLocalVideo(uri.toString())
    }

    // 主题自适应覆盖颜色
    val oc = rememberPlayerOverlayColors()


    // 文件加载完成时触发续播位置恢复（与 PC 端 _on_file_loaded 对齐）
    // 同时应用 HDR 配置（与 PC 端 _apply_hdr_on_file_loaded 对齐）
    LaunchedEffect(fileLoaded) {
        if (fileLoaded) {
            val url = viewModel.getCurrentPlaybackUrl()
            if (url.isNotEmpty()) {
                viewModel.onFileLoadedForResume(url)
            }
            // 应用 HDR 配置（检测视频是否 HDR 并按当前模式应用）
            viewModel.applyHdrOnFileLoaded()
        }
    }

    // 所有模式初始自动隐藏控制面板（几秒后自动隐藏，避免一直显示）
    LaunchedEffect(uiMode) {
        // TV 无独立首页：_showHome 初始为 true（竖屏首页用），TV 组合后立即纠正为 false，
        // 让 DPAD 按键走全局切台/面板逻辑（而非发给不存在的首页焦点树）
        if (uiMode.isTV && viewModel.showHome.value) {
            viewModel.showPlayerScreen()
        }
        viewModel.showControlsAutoHide()
    }


    val anyPanelOpen by viewModel.anyPanelOpenFlow.collectAsState()
    val showControls = controlsVisible && !anyPanelOpen

    // 横屏/TV 模式：启动时若无频道加载且无面板打开，自动弹出频道列表面板供用户选择
    // 修复：关闭自动续播后横屏启动直接进入空白播放页面的问题
    // 使用 landscapeSidebarVisible（与触控分区一致），避免 tvUnifiedPanelOpen 造成双重侧边栏
    // 仅在首次进入时触发一次，用户关闭后不再自动弹出
    // 首页（showHome）可见时不弹：首页左右双屏已提供频道选择（TV 无首页概念，不受此限制）
    val currentIdx by viewModel.currentIdx.collectAsState()
    var autoSidebarTriggered by remember { mutableStateOf(false) }
    LaunchedEffect(isLandscape, fileLoaded, currentIdx) {
        if (!autoSidebarTriggered && isLandscape && currentIdx < 0 && !fileLoaded && !multiViewState.active && (!showHome || uiMode.isTV)) {
            autoSidebarTriggered = true
            viewModel.setLandscapeSidebarVisible(true)
        }
    }

    // 旋转到竖屏时关闭横屏专属侧边栏：landscapeSidebarVisible 在 anyPanelOpen
    // 组合列表里，横屏开着侧边栏旋转到竖屏后该 flag 卡在 true（竖屏 UI 不渲染
    // 侧边栏），会让竖屏视频覆盖层被 !anyPanelOpen 条件隐藏，点击视频无法
    // 呼出暂停/全屏按钮
    LaunchedEffect(isLandscape) {
        if (!isLandscape && viewModel.landscapeSidebarVisible.value) {
            viewModel.setLandscapeSidebarVisible(false)
        }
    }

    val anyFullScreenPanel by remember {
        derivedStateOf {
            menuPanelOpen || sourceManagerOpen || playerSettingsOpen ||
                    videoSettingsOpen || audioSettingsOpen || subtitleSettingsOpen || subtitleSearchOpen ||
                    playbackPanelOpen || screenshotPanelOpen || viewSettingsOpen || aboutPanelOpen ||
                    mappingPanelOpen || avSyncPanelOpen || networkPanelOpen || toolsPanelOpen || playerToolsOpen || scanPanelOpen ||
                    reminderPanelOpen || resumePanelOpen || bookmarkPanelOpen ||
                    epgTimelineOpen || searchPanelOpen || streamQualityPanelOpen ||
                    recentPanelOpen || clipExportPanelOpen || audioVisualizerOpen || lyricsOpen ||
                    exitConfirmOpen || openUrlDialogOpen || updateDialogOpen ||
                    channelInfoOpen
        }
    }
    val configuration = LocalConfiguration.current
    val isPortrait = configuration.orientation == Configuration.ORIENTATION_PORTRAIT
    // 竖屏：手机竖屏观看
    // 横屏：手机横屏 + TV横屏，统一侧边栏风格，支持触控+遥控器
    val portraitSplit = isPortrait && !multiViewState.active && !forceLandscape

    // 全局EPG预加载（竖屏+横屏统一）：频道加载后立即预加载，15秒后重试
    val globalChannels by viewModel.channels.collectAsState()
    LaunchedEffect(globalChannels.size) {
        if (globalChannels.isNotEmpty()) {
            viewModel.preloadEpgForAllChannels()
            kotlinx.coroutines.delay(15000)
            viewModel.preloadEpgForAllChannels()
        }
    }

// -----------------------------------------------------------------
// 屏幕旋转修复：检测方向变化，恢复播放
//
// 优化策略：
// 1. 使用 remember（无 key）保持同一个 movableContentOf，避免旋转时重建 AndroidView
// 2. 旋转只触发 surfaceDestroyed → surfaceCreated 生命周期
// 3. surfaceCreated 中检测到 path 非空会自动恢复渲染
// 4. 本 LaunchedEffect 作为快速兜底：缩短等待时间至 300ms，
//    使用渐进式重试（300ms → 500ms → 800ms），减少旋转中断时间
// -----------------------------------------------------------------
LaunchedEffect(isPortrait) {
if (viewModel.playerType.value == PlayerType.MPV && viewModel.mpv.fileLoaded.value) {
Log.i("MainPlayerScreen", "Rotation detected: isPortrait=$isPortrait")
// 快速检测：300ms 后检查视频是否恢复（surfaceCreated 通常在 100-200ms 内完成）
kotlinx.coroutines.delay(300)
var path = viewModel.mpvGetPath()
var w = viewModel.mpv.videoWidth.value
var h = viewModel.mpv.videoHeight.value
Log.i("MainPlayerScreen", "After rotation (300ms): path=$path, ${w}x${h}")
if (path.isNotEmpty() && (w == 0 || h == 0)) {
// 第一次重试：等待 200ms 后再次检查
kotlinx.coroutines.delay(200)
w = viewModel.mpv.videoWidth.value
h = viewModel.mpv.videoHeight.value
if (w == 0 || h == 0) {
Log.i("MainPlayerScreen", "Video not restored after 500ms, reloading: $path")
viewModel.mpvSuppressFileError()
viewModel.mpv.playFile(path)
kotlinx.coroutines.delay(300)
viewModel.mpvClearSuppressFileError()
}
} else if (path.isEmpty()) {
val savedPath = com.iptv.scanner.editor.pro.mpv.MPVView.sharedState.savedPlaybackPath
if (savedPath != null) {
Log.i("MainPlayerScreen", "Path empty after rotation, restoring from saved: $savedPath")
viewModel.mpvSuppressFileError()
viewModel.mpv.playFile(savedPath)
kotlinx.coroutines.delay(500)
viewModel.mpvClearSuppressFileError()
}
}
// 恢复音量和静音状态（MPV 属性在 loadfile 后可能被重置）
val savedVol = viewModel.mpv.volume.value
val savedMute = viewModel.mpv.muted.value
if (savedVol > 0) viewModel.mpv.setVolume(savedVol)
viewModel.mpv.setMute(savedMute)
}
// ExoPlayer: 旋转后检查播放状态，恢复音频和音量
if (viewModel.playerType.value == PlayerType.EXO && viewModel.mpv.fileLoaded.value) {
Log.i("MainPlayerScreen", "Rotation detected (EXO): isPortrait=$isPortrait")
kotlinx.coroutines.delay(300)
if (viewModel.mpv.paused.value) {
Log.i("MainPlayerScreen", "EXO paused after rotation, resuming")
viewModel.mpv.setPause(false)
}
// 恢复音量和静音状态
val savedVol = viewModel.mpv.volume.value
val savedMute = viewModel.mpv.muted.value
if (savedVol > 0) viewModel.mpv.setVolume(savedVol)
viewModel.mpv.setMute(savedMute)
}
}

    // 液态玻璃：背景采样源状态（视频层标记 hazeSource，玻璃面板 hazeEffect 取景模糊）
    val hazeState = rememberLiquidHazeState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            // 关键：不能设置不透明 background！
            // SurfaceView 默认 Z-order 在普通 View 后面，不透明 background 会遮挡视频画面
            // 黑色背景由 Activity window background + SurfaceView 自身提供
    ) {
        val playerType by viewModel.playerType.collectAsState()
        // rememberUpdatedState：确保 movableContentOf 内部的 lambda 始终引用最新的 playerType
        // （movableContentOf 被 remember 缓存后，内部 lambda 不会随外层 recompose 自动更新）
        val playerTypeUpdated = rememberUpdatedState(playerType)
        // ExoPlayer 视频渲染视图（true=SurfaceView, false=TextureView），变化时触发 update 回调重建
        val exoSurfaceView by viewModel.exoSurfaceView.collectAsState()
        val exoSurfaceViewUpdated = rememberUpdatedState(exoSurfaceView)

        // -----------------------------------------------------------------
        // 1. 底层：播放器 View 容器
        //
        // 关键设计：不使用 key(playerType) 重建视图！
        // 而是用一个 FrameLayout 容器，根据 playerType 动态切换子 View。
        // 这样切换内核时视图不会销毁重建，只是替换子 View + attachView。
        // -----------------------------------------------------------------
        val createPlayerView: (android.content.Context) -> android.view.View = { ctx ->
            // 创建容器
            val container = android.widget.FrameLayout(ctx)
            container
        }

        // update 回调：每次 playerType 变化时执行，动态替换子 View
        val updatePlayerView: (android.view.View) -> Unit = view@ { container ->
            if (container !is android.widget.FrameLayout) return@view
            val ctx = container.context
            val pType = playerTypeUpdated.value
            val player = viewModel.mpv

            // 检查当前容器中的子 View 是否已匹配 playerType（EXO 还需匹配渲染视图类型）
            val currentChild = container.getChildAt(0)
            val expectedExoTag = if (exoSurfaceViewUpdated.value) TAG_EXO_SURFACE else TAG_EXO_TEXTURE
            val childMatches = when {
                currentChild is MPVViewLike -> pType == PlayerType.MPV
                currentChild is PlayerView -> pType == PlayerType.EXO && currentChild.tag == expectedExoTag
                else -> false
            }
            if (childMatches) return@view  // 已匹配，无需切换

            // 移除旧子 View（不调用 detach/destroy，只从容器移除）
            if (currentChild != null) {
                container.removeView(currentChild)
                Log.i("MainPlayerScreen", "Removed old player view: ${currentChild.javaClass.simpleName}")
            }

            // 创建新子 View 并 attach
            when (pType) {
                PlayerType.MPV -> {
                    // 始终使用 SurfaceView（MPVView）。
                    // TextureView 在部分设备上 GPU vo 无法渲染（如华为 LYA-AL00），
                    // SurfaceView + mediacodec_embed 可以直接用 MediaCodec 渲染到 Surface。
                    val mpvView: MPVViewLike = MPVView(ctx)
                    val configDir = ctx.getDir("mpv_config", Context.MODE_PRIVATE).absolutePath
                    val cacheDir = ctx.cacheDir.absolutePath
                    val userPrefs = UserPrefs.getInstance()
                    try {
                        mpvView.initialize(configDir, cacheDir, vo = userPrefs.getVo(), hwdec = userPrefs.getHwdec())
                        player.attachView(mpvView)
                        Log.i("MainPlayerScreen", "MPVView attached in container")
                    } catch (e: Throwable) {
                        Log.e("MainPlayerScreen", "MPVView init failed", e)
                    }
                    val view = mpvView.asView()
                    container.addView(view, android.widget.FrameLayout.LayoutParams(
                        android.widget.FrameLayout.LayoutParams.MATCH_PARENT,
                        android.widget.FrameLayout.LayoutParams.MATCH_PARENT
                    ))
                    // attachView 完成后，检查是否有待播放的 URL
                    val pendingUrl = viewModel.pendingSwitchPlayUrl.value
                    if (pendingUrl.isNotEmpty()) {
                        viewModel.clearPendingSwitchPlayUrl()
                        view.post {
                            Log.i("MainPlayerScreen", "playFile after MPV attach: $pendingUrl")
                            // 内核切换会重建 View 并重新 loadfile，旧端点可能已被代理回收；
                            // 恢复播放前强制重发 JOIN（同址也重发）
                            viewModel.fccService.resendJoin(pendingUrl)
                            viewModel.mpv.playFile(pendingUrl)
                        }
                    }
                }
                PlayerType.EXO -> {
                    val useSurface = exoSurfaceViewUpdated.value
                    val layoutRes = if (useSurface) com.iptv.scanner.editor.pro.R.layout.exo_player_surface_view
                    else com.iptv.scanner.editor.pro.R.layout.exo_player_texture_view
                    val exoView = android.view.LayoutInflater.from(ctx)
                        .inflate(layoutRes, null) as PlayerView
                    exoView.tag = if (useSurface) TAG_EXO_SURFACE else TAG_EXO_TEXTURE
                    player.attachView(exoView)
                    Log.i("MainPlayerScreen", "PlayerView (surface=$useSurface) attached in container, type=$pType")
                    container.addView(exoView, android.widget.FrameLayout.LayoutParams(
                        android.widget.FrameLayout.LayoutParams.MATCH_PARENT,
                        android.widget.FrameLayout.LayoutParams.MATCH_PARENT
                    ))
                    // attachView 完成后，检查是否有待播放的 URL
                    val pendingUrl = viewModel.pendingSwitchPlayUrl.value
                    if (pendingUrl.isNotEmpty()) {
                        viewModel.clearPendingSwitchPlayUrl()
                        exoView.post {
                            Log.i("MainPlayerScreen", "playFile after EXO attach: $pendingUrl")
                            // 同 MPV：内核切换恢复播放前强制重发 JOIN
                            viewModel.fccService.resendJoin(pendingUrl)
                            viewModel.mpv.playFile(pendingUrl)
                        }
                    }
                }
            }
        }

        val onReleasePlayer: (android.view.View) -> Unit = { container ->
            // 容器销毁时，清理子 View
            if (container is android.widget.FrameLayout) {
                for (i in 0 until container.childCount) {
                    val child = container.getChildAt(i)
                    when (child) {
                        is MPVViewLike -> child.destroy()
                        is PlayerView -> child.player = null
                    }
                }
                container.removeAllViews()
            }
            Log.i("MainPlayerScreen", "onRelease: container destroyed")
        }

        // 关键：不使用 remember(portraitSplit)！
        // portraitSplit 变化（竖屏→横屏旋转）时会创建新的 movableContentOf，
        // 导致旧的 AndroidView 被 dispose（onRelease → MPVView.destroy() → stop + playlist-clear），
        // 新的 AndroidView 创建新 MPVView 但文件已被 stop，surfaceCreated 时 path 为空 → 黑屏。
        //
        // 使用 remember（无 key）让同一个 movableContentOf 在竖屏/横屏布局之间移动，
        // SurfaceView 被 reparent 时只触发 surfaceDestroyed → surfaceCreated 生命周期，
        // MPVView 在 surfaceCreated 中检测到 path 非空会自动恢复渲染，无需重新 loadfile。
        val primaryPlayer = remember {
            movableContentOf {
                AndroidView(
                    factory = createPlayerView,
                    update = updatePlayerView,
                    onRelease = onReleasePlayer,
                    modifier = Modifier.fillMaxSize()
                )
            }
        }

            // -----------------------------------------------------------------
            // 布局：PHONE 竖屏 = 上下分屏 | PHONE 横屏 / TV = 全屏 + 抽屉
            //
            // 竖屏分屏：视频 16:9（fillMaxWidth + aspectRatio）+ 频道列表填满剩余
            // 横屏全屏：视频居中 + compact 抽屉（频道/EPG 宽度 1/4，无标题无搜索）
            // TV 全屏：视频居中 + 统一面板（DPAD 导航）
            // -----------------------------------------------------------------
            if (portraitSplit) {

                // ---- 竖屏布局 ----
                // 播放器始终在固定位置渲染（16:9 视频区域），不移动。
                // showHome=true 时首页 UI 覆盖播放器（不透明背景完全遮盖，但 Surface 活跃）。
                // showHome=false 时播放器正常显示。
                // 这避免了 movableContentOf 移动 SurfaceView 导致的 surface 销毁/重建，
                // 彻底解决返回播放页无画面问题。
                Box(modifier = Modifier.fillMaxSize().systemBarsPadding()) {
                    // 整页环境画布：标题栏/视频窗口/控制条/面板都浮在同一块画布上
                    val canvasDark = MaterialTheme.colorScheme.background.luminance() < 0.5f
                    Box(
                        modifier = Modifier
                            .matchParentSize()
                            .drawBehind {
                                drawRect(
                                    androidx.compose.ui.graphics.Brush.verticalGradient(
                                        listOf(tvPalette.canvasStart, tvPalette.canvasEnd)
                                    )
                                )
                                val g = if (canvasDark) 0.32f else 0.15f
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
                    ) {}
                    // 播放器 + 控制栏（始终在组合树中，Surface 不被销毁）
                    // 整列都浮在画布上：玻璃统一走 canvas 模式（磨砂减淡，避免叠加发白）
                    androidx.compose.runtime.CompositionLocalProvider(
                        com.iptv.scanner.editor.pro.ui.theme.LocalGlassOnCanvas provides true
                    ) {
                    Column(modifier = Modifier.fillMaxSize()) {
                        PortraitInfoBarV2(viewModel = viewModel)
                        // 视频渲染层：画布上的圆角视频窗口（边距/圆角与玻璃条一致；
                        // API31+ SurfaceView 支持按 View outline 圆角裁剪）
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 8.dp)
                                .aspectRatio(16f / 9f)
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color.Black)
                        ) {
                            primaryPlayer()
                            // 竖屏视频覆盖层：单击切换控制层 + 双击全屏 + 上下滑动换台
                            if (!showHome && !anyPanelOpen) {
                                var controlsVisible by remember { mutableStateOf(false) }
                                val pausedState by viewModel.mpv.paused.collectAsState()
                                val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
                                Box(
                                    modifier = Modifier
                                        .fillMaxSize()
                                        .pointerInput(Unit) {
                                            detectTapGestures(
                                                onTap = { controlsVisible = !controlsVisible },
                                                onDoubleTap = {
                                                    viewModel.toggleFullscreen()
                                                    controlsVisible = false
                                                }
                                            )
                                        }
                                        .pointerInput(Unit) {
                                            var totalY = 0f
                                            var triggered = false
                                            detectVerticalDragGestures(
                                                onDragStart = {
                                                    totalY = 0f
                                                    triggered = false
                                                },
                                                onDragEnd = {
                                                    totalY = 0f
                                                    triggered = false
                                                },
                                                onVerticalDrag = { change, dragAmount ->
                                                    change.consume()
                                                    totalY += dragAmount
                                                    val threshold = 80f
                                                    if (!triggered && kotlin.math.abs(totalY) > threshold) {
                                                        triggered = true
                                                        if (totalY < 0) {
                                                            viewModel.prevChannel()
                                                        } else {
                                                            viewModel.nextChannel()
                                                        }
                                                        haptic.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.LongPress)
                                                    }
                                                }
                                            )
                                        }
                                )
                                if (controlsVisible) {
                                    Box(
                                        modifier = Modifier
                                            .fillMaxSize()
                                            .background(Color.Black.copy(alpha = 0.3f))
                                            .clickable { controlsVisible = false }
                                    ) {
                                        IconButton(
                                            onClick = { viewModel.mpv.togglePause() },
                                            modifier = Modifier
                                                .align(Alignment.Center)
                                                .size(56.dp)
                                        ) {
                                            Icon(
                                                imageVector = if (pausedState) Icons.Default.PlayArrow else Icons.Default.Pause,
                                                contentDescription = if (pausedState) "播放" else "暂停",
                                                tint = Color.White,
                                                modifier = Modifier.size(48.dp)
                                            )
                                        }
                                        IconButton(
                                            onClick = { viewModel.enterPip(); controlsVisible = false },
                                            modifier = Modifier
                                                .align(Alignment.TopEnd)
                                                .padding(8.dp)
                                        ) {
                                            Icon(
                                                Icons.Default.PictureInPicture,
                                                contentDescription = "画中画",
                                                tint = Color.White,
                                                modifier = Modifier.size(24.dp)
                                            )
                                        }
                                        IconButton(
                                            onClick = { viewModel.toggleFullscreen(); controlsVisible = false },
                                            modifier = Modifier
                                                .align(Alignment.BottomEnd)
                                                .padding(8.dp)
                                        ) {
                                            Icon(
                                                Icons.Default.Fullscreen,
                                                contentDescription = "全屏",
                                                tint = Color.White,
                                                modifier = Modifier.size(24.dp)
                                            )
                                        }
                                    }
                                }
                            }
                        }
                        PortraitMediaInfoBar(viewModel = viewModel)
                        PortraitControlsV2(viewModel = viewModel)
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f)
                        ) {
                            androidx.compose.runtime.CompositionLocalProvider(
                                LocalAptvStyle provides true,
                                com.iptv.scanner.editor.pro.ui.theme.LocalGlassOnCanvas provides true
                            ) {
                                // 面板次要文字/图标提亮（玻璃底上可读）
                                val panelScheme = MaterialTheme.colorScheme.copy(
                                    onSurfaceVariant = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.78f)
                                )
                                MaterialTheme(colorScheme = panelScheme) {
                                    PortraitPlayerDynamicContent(viewModel = viewModel)
                                }
                            }
                        }
                    }
                    }   // LocalGlassOnCanvas provider 闭合

                    if (showHome) {
                        // 首页 UI 覆盖播放器（不透明背景完全遮盖播放器）
                        Column(
                            modifier = Modifier
                                .fillMaxSize()
                                .background(MaterialTheme.colorScheme.background)
                        ) {
                            // 迷你播放器条
                            val fileLoaded2 by viewModel.mpv.fileLoaded.collectAsState()
                            val currentCh by viewModel.currentChannel.collectAsState()
                            val displayInfo by viewModel.channelDisplayInfo.collectAsState()
                            val paused2 by viewModel.mpv.paused.collectAsState()
                            // 频道播放：currentCh 不为 null；本地视频：currentCh 为 null 但 displayInfo.name 有值
                            val hasMini = fileLoaded2 && (currentCh != null || displayInfo.name.isNotEmpty())
                            if (hasMini) {
                                // Mini 条在内容区 provider 之外，需单独提供玻璃开关
                                androidx.compose.runtime.CompositionLocalProvider(
                                    LocalLiquidGlass provides liquidGlass
                                ) {
                                    MiniPlayerBar(
                                        viewModel = viewModel,
                                        channelName = currentCh?.name ?: displayInfo.name,
                                        channelLogo = currentCh?.logo ?: "",
                                        groupName = currentCh?.group ?: "",
                                        isPaused = paused2,
                                        onClick = { viewModel.showPlayerScreen() },
                                        onPlayPause = { viewModel.mpv.togglePause() }
                                    )
                                }
                            }
                            // 内容区域（iOS 式淡入淡出转场）
                            // 内容延伸到底部，底部 tab 栏悬浮其上 —— tab 栏对滚动内容实时真模糊
                            // 液态玻璃采样源只挂内容 Box：hazeEffect（tab 栏）必须不在 source 子树内
                            // 注意：不可挂在 movableContentOf 的视频层上 —— movable 移动
                            // 时 Haze 节点注册失效会随机崩溃；且视频是 SurfaceView 本就不可采样
                            Box(
                                modifier = Modifier.weight(1f)
                            ) {
                                Box(
                                    modifier = Modifier
                                        .matchParentSize()
                                        .liquidGlassSource(hazeState)
                                ) {
                                    // 环境背景画布：深/浅主题渐变底 + 三色环境光斑。
                                    // 4 个 tab 页面的玻璃卡在此画布上只做磨砂透出，不再各自带底色
                                    val canvasDark = MaterialTheme.colorScheme.background.luminance() < 0.5f
                                    Box(
                                        modifier = Modifier
                                            .matchParentSize()
                                            .drawBehind {
                                                drawRect(
                                                    androidx.compose.ui.graphics.Brush.verticalGradient(
                                                        listOf(tvPalette.canvasStart, tvPalette.canvasEnd)
                                                    )
                                                )
                                                // 浅色画布光斑需更明显：白底上淡光斑易被吞没，玻璃无内容可透会失去质感
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
                                    ) {}
                                    androidx.compose.runtime.CompositionLocalProvider(
                                        LocalAptvStyle provides true,
                                        // 覆盖全部 4 个竖屏 tab 内容：玻璃卡片/按钮组件统一读取开关
                                        LocalLiquidGlass provides liquidGlass,
                                        // 画布模式：玻璃卡磨砂减淡，只透上面的环境画布
                                        com.iptv.scanner.editor.pro.ui.theme.LocalGlassOnCanvas provides true
                                    ) {
                                        val aptvScheme = MaterialTheme.colorScheme.copy(
                                            primary = tvPalette.accentGraphic,
                                            onPrimary = tvPalette.accentOn,
                                            primaryContainer = tvPalette.accentFill.copy(alpha = 0.15f),
                                            onPrimaryContainer = tvPalette.accentText,
                                            // 玻璃页面上次要文字提亮，保证磨砂底上的可读性
                                            onSurfaceVariant = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.78f),
                                        )
                                        MaterialTheme(colorScheme = aptvScheme) {
                                            androidx.compose.animation.Crossfade(
                                                targetState = portraitTab,
                                                animationSpec = androidx.compose.animation.core.tween(durationMillis = 200),
                                                label = "portraitTab"
                                            ) { tab ->
                                                when (tab) {
                                                    PortraitTab.CHANNELS -> PortraitListScreen(
                                                        viewModel = viewModel,
                                                        playlistLauncher = playlistLauncher,
                                                        videoLauncher = videoLauncher
                                                    )
                                                    PortraitTab.FAVORITES -> PortraitFavoritesScreen(
                                                        viewModel = viewModel,
                                                        playlistLauncher = playlistLauncher,
                                                        videoLauncher = videoLauncher
                                                    )
                                                    PortraitTab.TOOLS -> PortraitToolsScreen(
                                                        viewModel = viewModel,
                                                        playlistLauncher = playlistLauncher,
                                                        videoLauncher = videoLauncher
                                                    )
                                                    PortraitTab.SETTINGS -> PortraitSettingsContent(viewModel = viewModel)
                                                }
                                            }
                                        }
                                    }
                                }
                                // 悬浮底部 tab 栏：提供 HazeState 以启用背后内容的实时真模糊
                                Box(modifier = Modifier.align(Alignment.BottomCenter)) {
                                    androidx.compose.runtime.CompositionLocalProvider(LocalHazeState provides hazeState) {
                                        PortraitBottomTabBar(viewModel = viewModel)
                                    }
                                }
                            }
                        }
                    }
                }
            } else {
                // ---- 横屏模式（手机横屏 + TV横屏统一） ----

                // 视频宽高比：用于 SurfaceView 比例保持（解决视频被拉长铺满的问题）。
                // 根因：vo=mediacodec_embed 直接用 MediaCodec 渲染到 Surface buffer，不经过
                // GPU 渲染管线，mpv 的 keepaspect 选项不生效；Surface buffer 会按 SurfaceView
                // 尺寸拉伸视频。用 aspectRatio 限制 SurfaceView 外框，让 buffer 匹配视频比例。
                // 仅横屏/TV 需要：放到竖屏分支外会让 videoWidth/videoHeight 的变化在竖屏
                // 换台时触发整页重组，故只在横屏分支内按需订阅。
                val videoWidth by player.videoWidth.collectAsState()
                val videoHeight by player.videoHeight.collectAsState()
                val aspectRatio = if (videoWidth > 0 && videoHeight > 0) {
                    videoWidth.toFloat() / videoHeight.toFloat()
                } else {
                    16f / 9f  // 默认 16:9（未加载时）
                }

                if (multiViewState.active) {
                    // ---- 多画面模式：沉浸式侧边栏 + 底栏 ----
                    TvPlayerLayout(
                        viewModel = viewModel,
                        primaryPlayer = {
                            MultiViewOverlay(
                                state = multiViewState,
                                primaryContent = { primaryPlayer() },
                                getSubPlayer = { idx -> viewModel.getSubPlayer(idx) },
                                onViewportClick = { idx ->
                                    viewModel.setFocusedViewport(idx)
                                },
                                onViewportClose = { idx -> viewModel.removeFromMultiView(idx) },
                                onToggleMute = { idx -> viewModel.toggleMultiViewMute(idx) },
                                onExit = { viewModel.exitMultiView() }
                            )
                        },
                        videoAspectRatio = aspectRatio
                    )
                } else {
                // ---- 单画面模式：侧边栏风格沉浸式侧边栏 + 底栏 ----
                Box(modifier = Modifier.fillMaxSize()) {
                    TvPlayerLayout(
                        viewModel = viewModel,
                        primaryPlayer = { primaryPlayer() },
                        videoAspectRatio = aspectRatio,
                        homeOverlay = showHome && !uiMode.isTV
                    )
                    // 横屏首页：左右双屏（左宫格 + 右EPG + 玻璃TAB），覆盖在播放层上
                    // （播放器保持组合树中，Surface 不销毁，与竖屏首页策略一致）
                    // TV 无独立首页：直接进入全屏模式（全屏自带频道列表/菜单/底栏）
                    if (showHome && !uiMode.isTV) {
                        // DPI 自适应缩放（基准 900dp、下限 0.60）：
                        // 手机横屏/小平板进一步缩小整页 UI 提升内容密度，TV 端 ≥900dp 不缩放
                        val homeOrigDensity = androidx.compose.ui.platform.LocalDensity.current
                        val homeDpiScale = (configuration.screenHeightDp / 900f).coerceIn(0.60f, 1f)
                        androidx.compose.runtime.CompositionLocalProvider(
                            androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(
                                homeOrigDensity.density * homeDpiScale,
                                homeOrigDensity.fontScale
                            )
                        ) {
                            LandscapeHomeScreen(
                                viewModel = viewModel,
                                playlistLauncher = playlistLauncher,
                                videoLauncher = videoLauncher,
                                hazeState = hazeState
                            )
                        }
                    }
                }
            }
            }

        androidx.compose.runtime.CompositionLocalProvider(
            LocalLiquidGlass provides liquidGlass,
            LocalHazeState provides hazeState
        ) {
        // 主菜单 — PHONE 全屏覆盖 / TV 侧边栏风格右侧菜单
        if (menuPanelOpen) {
            MainMenuPanel(viewModel = viewModel)
        }

        // TV 端频道列表（侧边栏风格左侧面板：分组 + 频道 + EPG + 描述）
        if (tvUnifiedPanelOpen) {
            val origDensity = androidx.compose.ui.platform.LocalDensity.current
            val dpiScale = (configuration.screenHeightDp / 720f).coerceIn(0.70f, 1f)
            val scaledDensity = androidx.compose.ui.unit.Density(origDensity.density * dpiScale, origDensity.fontScale)
            androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalDensity provides scaledDensity) {
                TvUnifiedPanel(viewModel = viewModel)
            }
        }

        // 频道列表面板（菜单 → 频道列表）
        // 渲染在 TvUnifiedPanel 之后，覆盖在视频之上；自带的 PanelHeader 提供关闭按钮
        if (channelsPanelOpen) {
            ChannelsPanel(viewModel = viewModel)
        }

        // 节目单面板：竖屏用底部弹层玻璃样式，横屏/TV 保持左侧抽屉
        if (epgPanelOpen) {
            if (isLandscape) {
                EpgPanel(viewModel = viewModel)
            } else {
                PortraitEpgBottomSheet(viewModel = viewModel)
            }
        }

        // 文件浏览器（全屏覆盖，SAF 不可用时的替代方案）
        if (fileBrowserOpen) {
            FileBrowserPanel(viewModel = viewModel)
        }

        // 横屏（真实横屏）首页：设置/工具子面板渲染到右侧详情区（LandscapeSplitDetail），
        // 不再弹中央 Dialog；竖屏/伪横屏/播放页保持弹窗行为
        if (!(isLandscape && showHome)) {
        // 订阅源管理
        if (sourceManagerOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleSourceManager() }) {
                SourceManagerPanel(viewModel = viewModel, focusUrlInput = sourceManagerFocusUrl)
            }
        }

        // 播放器设置
        if (playerSettingsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.togglePlayerSettings() }) {
                PlayerSettingsPanel(viewModel = viewModel)
            }
        }

        // 视频设置
        if (videoSettingsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleVideoSettings() }) {
                VideoSettingsPanel(viewModel = viewModel)
            }
        }

        // 音频设置
        if (audioSettingsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleAudioSettings() }) {
                AudioSettingsPanel(viewModel = viewModel)
            }
        }

        // 字幕设置
        if (subtitleSettingsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleSubtitleSettings() }) {
                SubtitleSettingsPanel(viewModel = viewModel)
            }
        }
        if (subtitleSearchOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleSubtitleSearchPanel() }) {
                SubtitleSearchPanel(viewModel = viewModel)
            }
        }

        // 播放设置
        if (playbackPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.togglePlaybackPanel() }) {
                PlaybackPanel(viewModel = viewModel)
            }
        }

        // 截图
        if (screenshotPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleScreenshotPanel() }) {
                ScreenshotPanel(viewModel = viewModel)
            }
        }

        // 视图设置
        if (viewSettingsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleViewSettings() }) {
                ViewSettingsPanel(viewModel = viewModel)
            }
        }

        // 关于
        if (aboutPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleAboutPanel() }) {
                AboutPanel(viewModel = viewModel)
            }
        }

        // 频道映射
        if (mappingPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleMappingPanel() }) {
                MappingPanel(viewModel = viewModel)
            }
        }

        // A/V 同步监控
        if (avSyncPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleAvSyncPanel() }) {
                AvSyncPanel(viewModel = viewModel)
            }
        }

        // 网络增强
        if (networkPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleNetworkPanel() }) {
                NetworkPanel(viewModel = viewModel)
            }
        }

        // 工具
        if (toolsPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleToolsPanel() }) {
                ToolsPanel(viewModel = viewModel)
            }
        }

        // 播放工具（截图/切片/EPG时间线/搜索/提醒等，从控制条 MoreVert 按钮进入）
        if (playerToolsOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.togglePlayerToolsPanel() }) {
                PlayerToolsPanel(viewModel = viewModel)
            }
        }

        // URL 范围扫描
        if (scanPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleScanPanel() }) {
                ScanPanel(viewModel = viewModel)
            }
        }

        // 节目提醒管理
        if (reminderPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleReminderPanel() }) {
                ReminderPanel(viewModel = viewModel)
            }
        }

        // 续播位置管理
        if (resumePanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleResumePanel() }) {
                ResumePanel(viewModel = viewModel)
            }
        }

        // 书签管理
        if (bookmarkPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleBookmarkPanel() }) {
                BookmarkPanel(viewModel = viewModel)
            }
        }

        // EPG 时间线视图
        if (epgTimelineOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleEpgTimelinePanel() }) {
                EpgTimelinePanel(viewModel = viewModel)
            }
        }

        // 全局搜索
        if (searchPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleSearchPanel() }) {
                SearchPanel(viewModel = viewModel)
            }
        }

        // 流质量检测
        if (streamQualityPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleStreamQualityPanel() }) {
                StreamQualityPanel(viewModel = viewModel)
            }
        }

        // 最近打开
        if (recentPanelOpen) {
            PortraitPanelDialog(onDismiss = { viewModel.toggleRecentPanel() }) {
                RecentFilesPanel(viewModel = viewModel)
            }
        }

// 切片导出
if (clipExportPanelOpen) {
    PortraitPanelDialog(onDismiss = { viewModel.toggleClipExportPanel() }) {
        ClipExportPanel(viewModel = viewModel)
    }
}

// 音频可视化
if (audioVisualizerOpen) {
    PortraitPanelDialog(onDismiss = { viewModel.toggleAudioVisualizer() }) {
        AudioVisualizerPanel(viewModel = viewModel)
    }
}

// 歌词
if (lyricsOpen) {
    PortraitPanelDialog(onDismiss = { viewModel.toggleLyricsPanel() }) {
        LyricsPanel(viewModel = viewModel)
    }
}
        }   // 横屏首页 suppress 面板弹窗闭合（设置/工具子面板走右侧详情路由）

        // 提醒触发弹窗（节目即将开始时弹出，全屏遮罩）
        if (triggeredReminder != null) {
            ReminderPopup(
                reminder = triggeredReminder!!,
                onAccept = { viewModel.acceptTriggeredReminder() },
                onDismiss = { viewModel.dismissTriggeredReminder() }
            )
        }

        // 打开网络流 URL 对话框（AlertDialog，独立 window，自身控制可见性）
        // 横屏首页：入口已路由到右侧详情（OpenUrlPanelContent），不再弹窗
        if (!(isLandscape && showHome)) {
            OpenUrlDialog(viewModel = viewModel)
        }

        // 新版本更新提示对话框（发现新版本时自动弹出，也可从"关于"面板手动触发）
        UpdateDialog(viewModel = viewModel)

        // 退出确认对话框（BACK 键退出时提示：立即退出 / 进入 PiP）
        ExitConfirmDialog(viewModel = viewModel)

        // DLNA 投屏设备面板（信息栏/底部栏"投屏"按钮触发）
        DlnaCastPanel(viewModel = viewModel)

        // 频道信息详情对话框（信息栏"信息"按钮触发）
        if (channelInfoOpen) {
            ChannelInfoDialog(viewModel = viewModel)
        }

        // -----------------------------------------------------------------
        // 5. OSD 浮层（顶部居中，最顶层）— 竖屏模式下不显示
        // -----------------------------------------------------------------
        if (!portraitSplit) {
        AnimatedVisibility(
            visible = osd != null,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.TopCenter)
        ) {
            osd?.let { info ->
                OsdView(
                    title = info.title,
                    subtitle = info.subtitle,
                    extra = info.extra
                )
            }
        }
        }
        }   // CompositionLocalProvider（液态玻璃开关 + HazeState）闭合
    }
}

// -----------------------------------------------------------------
// 顶部信息条 + 面板入口按钮
