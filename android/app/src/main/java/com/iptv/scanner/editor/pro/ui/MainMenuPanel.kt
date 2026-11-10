package com.iptv.scanner.editor.pro.ui

import android.content.res.Configuration
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.automirrored.filled.ListAlt
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.Equalizer
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LightMode
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.PictureInPicture
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.ScreenshotMonitor
import androidx.compose.material.icons.filled.SyncAlt
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.VideoSettings
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.ViewModule
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Web
import androidx.compose.material.icons.filled.BrightnessAuto
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip

import androidx.compose.foundation.focusable
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvGlassSelected
import com.iptv.scanner.editor.pro.ui.theme.GlassPanel

// 强调色一律在用到处直接读 tvPalette（getter 每次求值），
// 不能在顶层 val 里缓存：缓存值在类加载时定型，运行时切主题不会刷新。

/**
 * 主菜单面板：与 PC 端主菜单（panelMenu）对齐。
 *
 * 3 个分组：
 * - 快捷（2 项）：频道列表 / 节目单 EPG
 * - 文件（6 项）：打开播放列表 / 打开网络流 / 打开本地视频 / 订阅源管理 / EPG 订阅源 / 频道映射
 * - 播放（13 项）：字幕 / 视频 / 音频 / 播放 / 截图 / A/V 同步 / 网络增强 /
 *   工具 / 视图 / 设置 / 关于 / 收藏 / 退出
 *
 * 布局自适应：
 * - 竖屏：单列列表（图标 + 标题 + 副标题）
 * - 横屏：多列网格（4 列，仅图标 + 标题，更紧凑高效）
 */
@Composable
fun MainMenuPanel(viewModel: AppViewModel) {
    val currentChannel by viewModel.currentChannel.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val bottomBarStyle by viewModel.bottomBarStyle.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val osdShowTime by viewModel.osdShowTime.collectAsState()
    val osdShowNetSpeed by viewModel.osdShowNetSpeed.collectAsState()
    val osdHideChannelNum by viewModel.osdHideChannelNum.collectAsState()
    val osdDisableEpg by viewModel.osdDisableEpg.collectAsState()
    val osdDisableFavorite by viewModel.osdDisableFavorite.collectAsState()
    val osdShowListIcon by viewModel.osdShowListIcon.collectAsState()
    val osdShowBottomIcon by viewModel.osdShowBottomIcon.collectAsState()
    val isTv = androidx.compose.ui.platform.LocalConfiguration.current.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
    val sources by viewModel.sources.collectAsState()
    val selectedSource by viewModel.selectedSource.collectAsState()
    val multiViewState by viewModel.multiViewState.collectAsState()
    // 主题模式只有一路状态：菜单里的高亮必须读同一个 ViewModel 值，
    // 不能写死高亮「深色模式」（会让人误以为切浅色没生效）
    val themeMode by viewModel.themeMode.collectAsState()

    val isFavorite = currentIdx >= 0 && favorites.contains(currentIdx)

    // 全屏底栏样式选择弹窗：条目点击后弹出单选列表（选中态高亮、选择后保持打开可连续切换）
    // 开关状态放 ViewModel：BACK 键在 Activity.onKeyDown 统一处理（按键分发下
    // Compose BackHandler 不生效），需跨层读取
    val showStylePicker by viewModel.stylePickerOpen.collectAsState()
    // 弹窗选中项提升到面板层：按键路由统一走外层菜单 Box 的 onPreviewKeyEvent，
    // 不依赖弹窗卡片自身抢焦点（实测 requestFocus 在菜单 GlassPanel 持有焦点时不可靠，
    // 焦点会漂移到全屏遮罩的 clickable 上，导致 OK 键误触发 onDismiss 关闭弹窗）
    var stylePickerIdx by remember { mutableStateOf(bottomBarStyle) }

    // SAF 文件选择器
    val playlistLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.importPlaylist(uri)
    }

    val videoLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.playLocalVideo(uri.toString())
    }

    val sections = remember(currentIdx, isFavorite, osdShowTime, osdShowNetSpeed, osdHideChannelNum, osdDisableEpg, osdDisableFavorite, osdShowListIcon, osdShowBottomIcon, liquidGlass, sources, selectedSource, multiViewState, themeMode) {
        buildMenuSections(
            themeMode = themeMode,
            onOpenPlaylist = {
                if (!viewModel.isSafAvailable()) {
                    viewModel.toggleMenuPanel()
                    viewModel.showFileBrowser()
                } else {
                    playlistLauncher.launch(arrayOf(
                        "application/x-mpegurl", "application/vnd.apple.mpegurl",
                        "audio/x-mpegurl", "video/x-mpegurl",
                        "text/plain", "application/octet-stream"
                    ))
                }
            },
            onOpenUrl = {
                viewModel.toggleMenuPanel()
                viewModel.toggleOpenUrlDialog()
            },
            onOpenLocalVideo = {
                if (!viewModel.isSafAvailable()) {
                    viewModel.toggleMenuPanel()
                    viewModel.showMediaFileBrowser()
                } else {
                    videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
                }
            },
            onSources = {
                viewModel.setSourceTab(SourceTab.PLAYLIST)
                viewModel.toggleMenuPanel()
                viewModel.toggleSourceManager()
            },
            onEpgSources = {
                viewModel.setSourceTab(SourceTab.EPG)
                viewModel.toggleMenuPanel()
                viewModel.toggleSourceManager()
            },
            onMapping = {
                viewModel.toggleMenuPanel()
                viewModel.toggleMappingPanel()
            },
            onChannels = {
                viewModel.toggleMenuPanel()
                viewModel.showChannelsPanel()
            },
            onEpg = {
                viewModel.toggleMenuPanel()
                viewModel.showEpgPanel()
            },
            onSubtitle = {
                viewModel.toggleMenuPanel()
                viewModel.toggleSubtitleSettings()
            },
            onVideo = {
                viewModel.toggleMenuPanel()
                viewModel.toggleVideoSettings()
            },
            onAudio = {
                viewModel.toggleMenuPanel()
                viewModel.toggleAudioSettings()
            },
            onPlayback = {
                viewModel.toggleMenuPanel()
                viewModel.togglePlaybackPanel()
            },
            onScreenshot = {
                viewModel.toggleMenuPanel()
                viewModel.toggleScreenshotPanel()
            },
            onAvsync = {
                viewModel.toggleMenuPanel()
                viewModel.toggleAvSyncPanel()
            },
            onNetwork = {
                viewModel.toggleMenuPanel()
                viewModel.toggleNetworkPanel()
            },
            onTools = {
                viewModel.toggleMenuPanel()
                viewModel.toggleToolsPanel()
            },
            onView = {
                viewModel.toggleMenuPanel()
                viewModel.toggleViewSettings()
            },
            onSettings = {
                viewModel.toggleMenuPanel()
                viewModel.togglePlayerSettings()
            },
            onAbout = {
                viewModel.toggleMenuPanel()
                viewModel.toggleAboutPanel()
            },
            onToggleFavorite = {
                viewModel.toggleFavorite()
            },
            onQuit = {
                // 真实退出：与遥控器 BACK 键一致的退出确认弹窗（原为仅 OSD 提示，属无效菜单项）
                viewModel.toggleMenuPanel()
                viewModel.showExitConfirm()
            },
            onPip = {
                viewModel.toggleMenuPanel()
                viewModel.enterPip()
            },
            onThemeDark = {
                viewModel.setThemeMode("dark")
            },
            onThemeLight = {
                viewModel.setThemeMode("light")
            },
            onThemeSystem = {
                viewModel.setThemeMode("system")
            },
            onClipExport = {
                viewModel.toggleMenuPanel()
                viewModel.toggleClipExportPanel()
            },
            onAudioVisualizer = {
                viewModel.toggleMenuPanel()
                viewModel.toggleAudioVisualizer()
            },
            onLyrics = {
                viewModel.toggleMenuPanel()
                viewModel.toggleLyricsPanel()
            },
            onSaveAs = {
                viewModel.toggleMenuPanel()
                viewModel.saveAsM3u()
            },
            onRecent = {
                viewModel.toggleMenuPanel()
                viewModel.toggleRecentPanel()
            },
            onRefresh = {
                viewModel.toggleMenuPanel()
                viewModel.refreshUi()
            },
            onSelectSource = { url ->
                viewModel.setSelectedSource(url)
                viewModel.toggleMenuPanel()
                viewModel.refreshUi()
            },
            onToggleShowTime = { viewModel.setOsdShowTime(!osdShowTime) },
            onToggleShowNetSpeed = { viewModel.setOsdShowNetSpeed(!osdShowNetSpeed) },
            onToggleHideChannelNum = { viewModel.setOsdHideChannelNum(!osdHideChannelNum) },
            onToggleDisableEpg = { viewModel.setOsdDisableEpg(!osdDisableEpg) },
            onToggleDisableFavorite = { viewModel.setOsdDisableFavorite(!osdDisableFavorite) },
            onToggleShowListIcon = { viewModel.setOsdShowListIcon(!osdShowListIcon) },
            onToggleShowBottomIcon = { viewModel.setOsdShowBottomIcon(!osdShowBottomIcon) },
            onToggleLiquidGlass = { viewModel.setLiquidGlass(!liquidGlass) },
            showTime = osdShowTime,
            showNetSpeed = osdShowNetSpeed,
            hideChannelNum = osdHideChannelNum,
            disableEpg = osdDisableEpg,
            disableFavorite = osdDisableFavorite,
            showListIcon = osdShowListIcon,
            showBottomIcon = osdShowBottomIcon,
            liquidGlassValue = liquidGlass,
            bottomBarStyleValue = bottomBarStyle,
            onSelectBottomBarStyle = {
                stylePickerIdx = bottomBarStyle
                // 打开弹窗即进入实时预览：底栏显示出来并按当前样式渲染，
                // 后续随弹窗焦点切换实时变化（BACK 未确定则恢复原样式）
                viewModel.setStylePreview(bottomBarStyle)
                viewModel.showControlsAutoHide()
                viewModel.setStylePickerOpen(true)
            },
            hasCurrentChannel = currentChannel != null,
            isFavorite = isFavorite,
            sources = sources,
            selectedSource = selectedSource,
            multiViewActive = multiViewState.active,
            currentMultiViewLayout = if (multiViewState.active) multiViewState.layout else null,
            onEnterMultiView = { layout ->
                viewModel.toggleMenuPanel()
                viewModel.enterMultiView(layout)
            },
            onExitMultiView = {
                viewModel.toggleMenuPanel()
                viewModel.exitMultiView()
            }
        )
    }

    // 横屏模式：侧边栏风格右侧两列浮动菜单（单圆角矩形包含两列）
    if (isTv) {
        var selectedSectionIdx by remember { mutableStateOf(0) }
        val safeIdx = selectedSectionIdx.coerceIn(0, sections.lastIndex)
        val currentSection = sections.getOrNull(safeIdx)

        // DPI自适应缩放（与TvPlayerLayout一致）
        val configuration = LocalConfiguration.current
        val origDensity = LocalDensity.current
        val dpiScale = (configuration.screenHeightDp / 720f).coerceIn(0.70f, 1f)
        val scaledDensity = Density(origDensity.density * dpiScale, origDensity.fontScale)

        var leftSelectedIdx by remember { mutableStateOf(0) }
        var activeColumn by remember { mutableStateOf(0) } // 0=左列(分组), 1=右列(条目)
        val safeLeftIdx = if (currentSection != null) leftSelectedIdx.coerceIn(0, currentSection.entries.lastIndex) else 0
        val menuFocusRequester = remember { FocusRequester() }
        LaunchedEffect(Unit) { menuFocusRequester.requestFocus() }

        CompositionLocalProvider(LocalDensity provides scaledDensity) {
        Box(
            modifier = Modifier.fillMaxSize().onPreviewKeyEvent { event ->
                // 底栏样式选择弹窗打开时：按键由菜单层统一路由给弹窗
                // （上/下/左/右移动选中项，OK 在 KeyUp 应用；选择后弹窗保持打开可连续切换）
                if (showStylePicker) {
                    return@onPreviewKeyEvent handleStylePickerKey(
                        event,
                        onMove = { dir ->
                            stylePickerIdx = (stylePickerIdx + dir + TV_BOTTOM_BAR_STYLES.size) % TV_BOTTOM_BAR_STYLES.size
                            viewModel.setStylePreview(stylePickerIdx)  // 底栏实时跟随焦点预览
                        },
                        onApply = {
                            viewModel.setBottomBarStyle(stylePickerIdx)
                            viewModel.setStylePreview(null)  // 已确定，退出预览态
                        }
                    )
                }
                when (event.type) {
                    KeyEventType.KeyDown -> when (event.key) {
                        Key.DirectionDown -> {
                            if (activeColumn == 0) {
                                selectedSectionIdx = (safeIdx + 1) % sections.size
                            } else if (currentSection != null && currentSection.entries.isNotEmpty()) {
                                leftSelectedIdx = (safeLeftIdx + 1) % currentSection.entries.size
                            }
                            true
                        }
                        Key.DirectionUp -> {
                            if (activeColumn == 0) {
                                selectedSectionIdx = (safeIdx - 1 + sections.size) % sections.size
                            } else if (currentSection != null && currentSection.entries.isNotEmpty()) {
                                leftSelectedIdx = (safeLeftIdx - 1 + currentSection.entries.size) % currentSection.entries.size
                            }
                            true
                        }
                        Key.DirectionRight -> {
                            // 列序镜像后：二级条目列在左、一级分组列在最右；从二级按右键回到一级
                            if (activeColumn == 1) {
                                activeColumn = 0
                                true
                            } else false
                        }
                        Key.DirectionLeft -> {
                            // 从一级（最右列）按左键进入二级条目列（往左一列）
                            if (activeColumn == 0 && currentSection != null && currentSection.entries.isNotEmpty()) {
                                activeColumn = 1
                                true
                            } else false
                        }
                        Key.DirectionCenter, Key.Enter -> {
                            // 按下阶段仅消费事件，点击延迟到 KeyUp 触发（见 KeyUp 分支）。
                            // 若在 KeyDown 直接触发 onClick：菜单关闭 + 子面板打开后，焦点已落到
                            // 子面板标题栏的关闭按钮（PanelScaffold 打开时自动抢焦点），同一次按键
                            // 的 KeyUp 会让该按钮的 clickable 再次触发点击 → 面板刚打开就被关闭
                            // （表现为功能窗口闪一下立即消失，回到未点击前的状态）。
                            activeColumn == 1 && currentSection != null && currentSection.entries.isNotEmpty()
                        }
                        else -> false
                    }
                    KeyEventType.KeyUp -> when (event.key) {
                        Key.DirectionCenter, Key.Enter -> {
                            // 在 KeyUp 统一触发点击：整个按键序列在预览层完整消费，
                            // 不会泄漏到新打开面板中自动获得焦点的控件（如关闭按钮）。
                            if (activeColumn == 1 && currentSection != null && currentSection.entries.isNotEmpty()) {
                                currentSection.entries.getOrNull(safeLeftIdx)?.onClick()
                                true
                            } else false
                        }
                        else -> false
                    }
                    else -> false
                }
            }
        ) {
            GlassPanel(
                liquidGlass = liquidGlass,
                cornerRadius = 10.dp,
                overlayDark = true,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .fillMaxHeight()
                    .padding(end = 16.dp, top = 10.dp, bottom = 10.dp)
                    .focusRequester(menuFocusRequester)
                    .focusable()
            ) {
                // 列序（面板靠右显示，层级从右往左）：最右=一级分组列，往左=二级条目列
                // 不叠加实底 scrim：会盖住玻璃的磨砂/光斑/噪点质感
                Row(
                    modifier = Modifier.wrapContentWidth()
                ) {
                    // 左列：二级条目（当前选中分组下的菜单项）
                    if (currentSection != null && currentSection.entries.isNotEmpty()) {
                        LazyColumn(
                            modifier = Modifier.fillMaxHeight().width(150.dp),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 6.dp)
                        ) {
                            itemsIndexed(
                                items = currentSection.entries,
                                key = { idx, entry -> currentSection.title + "_" + entry.title + "_" + idx }
                            ) { idx, entry ->
                                val isRightSelected = activeColumn == 1 && idx == safeLeftIdx
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 4.dp, vertical = 1.dp)
                                        .clip(RoundedCornerShape(6.dp))
                                        .then(
                                            when {
                                                isRightSelected -> Modifier.tvGlassSelected(6)
                                                entry.highlight -> Modifier.background(AptvAccent.copy(alpha = 0.25f), RoundedCornerShape(6.dp))
                                                else -> Modifier
                                            }
                                        )
                                        .clickable {
                                            activeColumn = 1
                                            leftSelectedIdx = idx
                                            entry.onClick()
                                        }
                                        .padding(horizontal = 12.dp, vertical = 11.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = entry.title,
                                        color = if (isRightSelected || entry.highlight) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 15.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        modifier = Modifier.weight(1f)
                                    )
                                    if (entry.isToggle) {
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Box(
                                            modifier = Modifier
                                                .size(8.dp)
                                                .clip(CircleShape)
                                                .background(if (entry.toggleValue) AptvAccent else tvPalette.borderSubtle)
                                        )
                                    }
                                }
                            }
                        }
                    }
                    // 列间分隔线
                    Box(modifier = Modifier.width(1.dp).fillMaxHeight().background(tvPalette.borderSubtle))

                    // 右列（最右=一级）：主菜单分组
                    LazyColumn(
                        modifier = Modifier.fillMaxHeight().width(130.dp),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 6.dp)
                    ) {
                        itemsIndexed(sections) { idx, section ->
                            val isSelected = idx == safeIdx
                            val isLeftActive = activeColumn == 0 && isSelected
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 4.dp, vertical = 1.dp)
                                    .clip(RoundedCornerShape(6.dp))
                                    .then(
                                        if (isSelected) Modifier.tvGlassSelected(6)
                                        else Modifier.background(Color.Transparent)
                                    )
                                    .clickable {
                                        activeColumn = 0
                                        selectedSectionIdx = idx
                                    }
                                    .padding(horizontal = 12.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = section.title,
                                    color = if (isSelected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 16.sp,
                                    fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                        }
                    }
                }
            }

            // 全屏底栏样式选择弹窗：悬浮在菜单之上，选择后保持打开可连续切换
            if (showStylePicker) {
                BottomBarStylePickerOverlay(
                    current = bottomBarStyle,
                    pickerIdx = stylePickerIdx,
                    liquidGlass = liquidGlass,
                    onSelect = {
                        stylePickerIdx = it
                        viewModel.setBottomBarStyle(it)
                        viewModel.setStylePreview(null)  // 触控点击即确定，退出预览态
                    },
                    onDismiss = { viewModel.setStylePickerOpen(false) }
                )
            }

        }
        } // CompositionLocalProvider
        return
    }

    // PHONE模式：原有全屏覆盖菜单
    BoxWithConstraints(
        modifier = Modifier.fillMaxSize().onPreviewKeyEvent { event ->
            // 底栏样式弹窗打开时同样走统一按键路由（带键盘的平板/手机可用 OK 键确定）
            if (showStylePicker) {
                handleStylePickerKey(
                    event,
                    onMove = { dir ->
                        stylePickerIdx = (stylePickerIdx + dir + TV_BOTTOM_BAR_STYLES.size) % TV_BOTTOM_BAR_STYLES.size
                        viewModel.setStylePreview(stylePickerIdx)
                    },
                    onApply = {
                        viewModel.setBottomBarStyle(stylePickerIdx)
                        viewModel.setStylePreview(null)
                    }
                )
            } else false
        }
    ) {
        val useDualColumn = maxWidth > 500.dp
        // 竖屏同样支持底栏样式选择弹窗
        if (showStylePicker) {
            BottomBarStylePickerOverlay(
                current = bottomBarStyle,
                pickerIdx = stylePickerIdx,
                liquidGlass = liquidGlass,
                onSelect = {
                    stylePickerIdx = it
                    viewModel.setBottomBarStyle(it)
                    viewModel.setStylePreview(null)
                },
                onDismiss = { viewModel.setStylePickerOpen(false) }
            )
        }

        Surface(
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxSize()
        ) {
            Column(modifier = Modifier.fillMaxSize().systemBarsPadding()) {
                // 标题栏
                PanelHeader(
                    title = "主菜单",
                    subtitle = "功能入口",
                    onClose = { viewModel.toggleMenuPanel() }
                )

                if (useDualColumn) {
                    // ---- 横屏：多列网格布局 ----
                    LandscapeMenuGrid(sections = sections)
                } else {
                // ---- 竖屏：单列列表布局 ----
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
                ) {
                    sections.forEach { section ->
                        item(key = "section_header_${section.title}") {
                            SectionHeader(section.title)
                        }
                        items(
                            items = section.entries,
                            key = { entry -> section.title + "_" + entry.title }
                        ) { entry ->
                            MenuEntryItem(
                                entry = entry,
                                onClick = entry.onClick
                            )
                        }
                        item(key = "section_divider_${section.title}") {
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                    }
                }
            }
        }
    }
    }
}

// -----------------------------------------------------------------
// 横屏网格布局
// -----------------------------------------------------------------

/**
 * 横屏主菜单网格：每个分区分组显示，每行 4 列。
 * 每个菜单项为紧凑卡片（图标 + 标题），无副标题。
 */
@Composable
private fun LandscapeMenuGrid(sections: List<MenuSection>) {
    val columnCount = 4

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 4.dp)
    ) {
        sections.forEach { section ->
            item(key = "grid_header_${section.title}") {
                SectionHeader(section.title)
            }
            // 将条目按 columnCount 分行
            section.entries.chunked(columnCount).forEachIndexed { rowIdx, rowEntries ->
                item(key = "grid_row_${section.title}_$rowIdx") {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 3.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        rowEntries.forEach { entry ->
                            MenuGridItem(
                                entry = entry,
                                onClick = entry.onClick,
                                modifier = Modifier.weight(1f)
                            )
                        }
                        // 用空占位填满剩余列（保持等宽）
                        repeat(columnCount - rowEntries.size) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
            item(key = "grid_divider_${section.title}") {
                Spacer(modifier = Modifier.height(6.dp))
            }
        }
    }
}

/**
 * 网格菜单项（横屏紧凑模式）：图标 + 标题
 */
@Composable
private fun MenuGridItem(
    entry: MenuEntry,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = if (entry.highlight) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = modifier
            .height(72.dp)
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(vertical = 8.dp, horizontal = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // 图标
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .clip(CircleShape)
                    .background(
                        if (entry.highlight) MaterialTheme.colorScheme.primary.copy(alpha = 0.2f)
                        else MaterialTheme.colorScheme.surfaceVariant
                    ),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = entry.icon,
                    contentDescription = null,
                    tint = if (entry.highlight) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp)
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            // 标题
            Text(
                text = if (entry.isToggle) "${entry.title}: ${if (entry.toggleValue) "开" else "关"}" else entry.title,
                color = if (entry.highlight) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface,
                fontSize = 11.sp,
                fontWeight = if (entry.highlight) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                textAlign = TextAlign.Center
            )
        }
    }
}

// -----------------------------------------------------------------
// 菜单数据模型
// -----------------------------------------------------------------

private data class MenuEntry(
    val icon: ImageVector,
    val title: String,
    val subtitle: String,
    val onClick: () -> Unit,
    val highlight: Boolean = false,
    val isToggle: Boolean = false,
    val toggleValue: Boolean = false
)

private data class MenuSection(
    val title: String,
    val entries: List<MenuEntry>
)

private fun buildMenuSections(
    themeMode: String = "dark",
    onOpenPlaylist: () -> Unit,
    onOpenUrl: () -> Unit,
    onOpenLocalVideo: () -> Unit,
    onSources: () -> Unit,
    onEpgSources: () -> Unit,
    onMapping: () -> Unit,
    onChannels: () -> Unit,
    onEpg: () -> Unit,
    onSubtitle: () -> Unit,
    onVideo: () -> Unit,
    onAudio: () -> Unit,
    onPlayback: () -> Unit,
    onScreenshot: () -> Unit,
    onAvsync: () -> Unit,
    onNetwork: () -> Unit,
    onTools: () -> Unit,
    onView: () -> Unit,
    onSettings: () -> Unit,
    onAbout: () -> Unit,
    onToggleFavorite: () -> Unit,
    onQuit: () -> Unit,
    onPip: () -> Unit,
    onThemeDark: () -> Unit,
    onThemeLight: () -> Unit,
    onThemeSystem: () -> Unit,
    onClipExport: () -> Unit,
    onAudioVisualizer: () -> Unit,
    onLyrics: () -> Unit,
    onSaveAs: () -> Unit,
    onRecent: () -> Unit,
    onRefresh: () -> Unit,
    onSelectSource: (String) -> Unit,
    onToggleShowTime: () -> Unit,
    onToggleShowNetSpeed: () -> Unit,
    onToggleHideChannelNum: () -> Unit,
    onToggleDisableEpg: () -> Unit,
    onToggleDisableFavorite: () -> Unit,
    onToggleShowListIcon: () -> Unit,
    onToggleShowBottomIcon: () -> Unit,
    onToggleLiquidGlass: () -> Unit,
    bottomBarStyleValue: Int = 0,
    onSelectBottomBarStyle: () -> Unit = {},
    showTime: Boolean,
    showNetSpeed: Boolean,
    hideChannelNum: Boolean,
    disableEpg: Boolean,
    disableFavorite: Boolean,
    showListIcon: Boolean,
    showBottomIcon: Boolean,
    liquidGlassValue: Boolean,
    hasCurrentChannel: Boolean,
    isFavorite: Boolean,
    sources: List<com.iptv.scanner.editor.pro.data.IptvSource>,
    selectedSource: String,
    multiViewActive: Boolean = false,
    currentMultiViewLayout: MultiViewLayout? = null,
    onEnterMultiView: (MultiViewLayout) -> Unit = {},
    onExitMultiView: () -> Unit = {}
): List<MenuSection> {

    // 侧边栏风格分组：订阅源 = 订阅源列表 + 管理入口
    val sourceEntries = mutableListOf<MenuEntry>()
    sources.filter { it.enabled }.forEachIndexed { idx, src ->
        val name = src.name.ifEmpty { "源${idx + 1}" }
        sourceEntries.add(MenuEntry(
            Icons.Default.Web, name, src.url.take(40),
            { onSelectSource(src.url) },
            highlight = src.url == selectedSource
        ))
    }
    sourceEntries.add(MenuEntry(Icons.Default.Settings, "订阅源管理", "添加、编辑、删除 M3U 订阅源", onSources))
    val lineSection = MenuSection(title = "订阅源", entries = sourceEntries)

    // 多画面分组
    val multiViewEntries = mutableListOf<MenuEntry>()
    if (multiViewActive && currentMultiViewLayout != null) {
        val otherLayout = when (currentMultiViewLayout) {
            MultiViewLayout.DUAL -> MultiViewLayout.QUAD
            MultiViewLayout.QUAD -> MultiViewLayout.NINE
            MultiViewLayout.NINE -> MultiViewLayout.DUAL
            else -> MultiViewLayout.DUAL
        }
        multiViewEntries.add(MenuEntry(Icons.Default.ViewModule, "切换为${otherLayout.displayName}", "当前 ${currentMultiViewLayout.displayName}", { onEnterMultiView(otherLayout) }))
        multiViewEntries.add(MenuEntry(Icons.AutoMirrored.Filled.ExitToApp, "退出多画面", "退出多画面模式", onExitMultiView, highlight = true))
    } else {
        multiViewEntries.add(MenuEntry(Icons.Default.ViewModule, "双画面", "左右分屏", { onEnterMultiView(MultiViewLayout.DUAL) }))
        multiViewEntries.add(MenuEntry(Icons.Default.GridView, "四画面", "2x2 网格", { onEnterMultiView(MultiViewLayout.QUAD) }))
        multiViewEntries.add(MenuEntry(Icons.Default.GridView, "九画面", "3x3 网格", { onEnterMultiView(MultiViewLayout.NINE) }))
    }
    val multiViewSection = MenuSection(title = "多画面", entries = multiViewEntries)

    val playbackSettingsSection = MenuSection(
        title = "播放设置",
        entries = listOf(
            MenuEntry(Icons.Default.Settings, "播放器设置", "内核 / VO / HWDEC / HDR", onSettings),
            MenuEntry(Icons.Default.ClosedCaption, "字幕", "轨 / 显示 / 延迟 / 缩放", onSubtitle),
            MenuEntry(Icons.Default.VideoSettings, "视频", "图像调整 / 旋转 / 翻转", onVideo),
            MenuEntry(Icons.Default.Equalizer, "音频", "音轨 / 延迟 / EQ / 音调", onAudio),
            MenuEntry(Icons.Default.PlayCircle, "播放", "速度 / 循环 / 随机 / AB", onPlayback)
        )
    )
    val channelSection = MenuSection(
        title = "频道管理",
        entries = listOf(
            MenuEntry(Icons.AutoMirrored.Filled.ListAlt, "频道列表", "订阅 / 本地 / 收藏 / 历史", onChannels, highlight = true),
            MenuEntry(Icons.Default.CalendarMonth, "节目单 EPG", "当前频道节目 / 日期切换", onEpg),
            MenuEntry(Icons.Default.SyncAlt, "频道映射", "远程映射 + 用户映射管理", onMapping),
            MenuEntry(
                Icons.Default.Favorite,
                if (isFavorite) "取消收藏" else "收藏",
                if (hasCurrentChannel) "当前频道" else "未选择频道",
                onToggleFavorite,
                highlight = hasCurrentChannel
            )
        )
    )
    val subscribeSection = MenuSection(
        title = "订阅管理",
        entries = listOf(
            MenuEntry(Icons.Default.CalendarMonth, "EPG 订阅源", "管理节目单订阅地址", onEpgSources),
            MenuEntry(Icons.Default.Link, "打开网络流", "输入 M3U/M3U8 URL", onOpenUrl),
            MenuEntry(Icons.Default.FileOpen, "打开播放列表", "选择 M3U/M3U8 文件", onOpenPlaylist)
        )
    )
    val displaySection = MenuSection(
        title = "显示设置",
        entries = listOf(
            MenuEntry(Icons.Default.ViewInAr, "视图", "视频比例 / OSD", onView),
            MenuEntry(Icons.Default.DarkMode, "深色模式", "沉浸式播放体验", onThemeDark, highlight = themeMode == "dark"),
            MenuEntry(Icons.Default.LightMode, "浅色模式", "明亮界面", onThemeLight, highlight = themeMode == "light"),
            MenuEntry(Icons.Default.BrightnessAuto, "跟随系统", "随系统暗色/亮色切换", onThemeSystem, highlight = themeMode == "system"),
            MenuEntry(Icons.Default.Info, "显示时间", "右上角时间组", onToggleShowTime, isToggle = true, toggleValue = showTime),
            MenuEntry(Icons.Default.Info, "显示网速", "右下角网速", onToggleShowNetSpeed, isToggle = true, toggleValue = showNetSpeed),
            MenuEntry(Icons.Default.Info, "隐藏序号", "频道列表不显示序号", onToggleHideChannelNum, isToggle = true, toggleValue = hideChannelNum),
            MenuEntry(Icons.Default.Info, "关闭EPG", "不加载节目单", onToggleDisableEpg, isToggle = true, toggleValue = disableEpg),
            MenuEntry(Icons.Default.Info, "关闭收藏", "不显示收藏星标", onToggleDisableFavorite, isToggle = true, toggleValue = disableFavorite),
            MenuEntry(Icons.Default.Info, "列表图标", "频道列表显示台标", onToggleShowListIcon, isToggle = true, toggleValue = showListIcon),
            MenuEntry(Icons.Default.Info, "底部图标", "底部信息栏显示图标", onToggleShowBottomIcon, isToggle = true, toggleValue = showBottomIcon),
            MenuEntry(Icons.Default.AutoAwesome, "液态玻璃", "UI背景半透明玻璃质感", onToggleLiquidGlass, isToggle = true, toggleValue = liquidGlassValue),
            MenuEntry(
                Icons.Default.AspectRatio,
                "全屏底栏样式",
                "当前：" + (TV_BOTTOM_BAR_STYLES.firstOrNull { it.first == bottomBarStyleValue }?.second
                    ?: "信息详情式") + " · 点击选择",
                onSelectBottomBarStyle
            )
        )
    )
    val toolSection = MenuSection(
        title = "工具设置",
        entries = listOf(
            MenuEntry(Icons.Default.Tune, "工具", "搜索 / 提醒 / 续播 / 书签", onTools),
            MenuEntry(Icons.Default.ScreenshotMonitor, "截图", "单张 / 连拍 / 含字幕", onScreenshot),
            MenuEntry(Icons.Default.GraphicEq, "A/V 同步", "实时数值 / 波形", onAvsync),
            MenuEntry(Icons.Default.Public, "网络增强", "Referer / Proxy / Headers", onNetwork),
            MenuEntry(Icons.Default.ContentCut, "切片导出", "裁剪视频片段 / GIF", onClipExport),
            MenuEntry(Icons.Default.GraphicEq, "音频可视化", "实时频谱波形", onAudioVisualizer),
            MenuEntry(Icons.Default.MusicNote, "歌词", "加载 LRC / 同步高亮", onLyrics)
        )
    )
    val otherSection = MenuSection(
        title = "其他设置",
        entries = listOf(
            MenuEntry(Icons.Default.Movie, "打开本地文件", "播放视频/音频文件", onOpenLocalVideo),
            MenuEntry(Icons.Default.History, "最近打开", "最近打开的列表/视频", onRecent),
            MenuEntry(Icons.Default.FileDownload, "另存为 M3U", "导出当前频道列表", onSaveAs),
            MenuEntry(Icons.Default.Refresh, "刷新", "重新加载频道和 EPG", onRefresh),
            MenuEntry(Icons.Default.Info, "关于", "版本信息 / 功能特性", onAbout),
            MenuEntry(Icons.Default.PictureInPicture, "画中画", "进入 PiP 小窗口播放", onPip),
            MenuEntry(Icons.AutoMirrored.Filled.ExitToApp, "退出", "关闭应用", onQuit)
        )
    )

    return listOf(lineSection, multiViewSection, playbackSettingsSection, channelSection, subscribeSection, displaySection, toolSection, otherSection)
}

// -----------------------------------------------------------------
// 菜单组件
// -----------------------------------------------------------------

@Composable
private fun SectionHeader(title: String) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Text(
            text = title,
            color = MaterialTheme.colorScheme.primary,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)
        )
    }
}

@Composable
private fun MenuEntryItem(
    entry: MenuEntry,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .tvFocusBorder()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 图标圆形背景
        Box(
            modifier = Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(
                    if (entry.highlight) MaterialTheme.colorScheme.primary.copy(alpha = 0.2f)
                    else MaterialTheme.colorScheme.surfaceVariant
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = entry.icon,
                contentDescription = null,
                tint = if (entry.highlight) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(20.dp)
            )
        }

        Spacer(modifier = Modifier.width(12.dp))

        // 标题 + 副标题
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = entry.title,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = if (entry.highlight) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (entry.subtitle.isNotEmpty()) {
                Text(
                    text = entry.subtitle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
        // 侧边栏风格：开关项
        if (entry.isToggle) {
            Switch(
                checked = entry.toggleValue,
                onCheckedChange = { onClick() },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = MaterialTheme.colorScheme.secondary,
                    checkedTrackColor = MaterialTheme.colorScheme.secondary.copy(alpha = 0.5f)
                )
            )
        }
    }
}

// -----------------------------------------------------------------
// 全屏底栏样式选择弹窗
// -----------------------------------------------------------------

/**
 * 底栏样式弹窗按键路由（TV/PHONE 模式共用）：
 * 上/下（或左/右）移动选中项并实时预览，OK（DPAD_CENTER/Enter/小键盘Enter）在 KeyUp 应用
 * （应用延迟到 KeyUp，防焦点迁移误触发）。不匹配的按键返回 false 交给外层继续处理。
 */
private fun handleStylePickerKey(
    event: androidx.compose.ui.input.key.KeyEvent,
    onMove: (Int) -> Unit,
    onApply: () -> Unit
): Boolean = when (event.type) {
    KeyEventType.KeyDown -> when (event.key) {
        Key.DirectionUp -> { onMove(-1); true }
        Key.DirectionDown, Key.DirectionLeft, Key.DirectionRight -> { onMove(1); true }
        Key.DirectionCenter, Key.Enter, Key.NumPadEnter -> true
        else -> false
    }
    KeyEventType.KeyUp -> when (event.key) {
        Key.DirectionCenter, Key.Enter, Key.NumPadEnter -> { onApply(); true }
        else -> false
    }
    else -> false
}

/**
 * 全屏底栏样式单选弹窗：替代原「点击循环切换」——循环式无法预知切到哪个样式、
 * 也看不到切换效果，必须关菜单呼底栏验证，重复操作繁琐。
 *
 * 交互：
 * - 点击/OK 键应用样式后弹窗保持打开，可连续切换对比；遮罩点击或 BACK 关闭
 * - 当前选中项高亮（tvGlassSelected 凸起 + 单选点），当前生效样式带「当前」标记
 * - 每行右侧迷你预览该样式底栏结构（BottomBarStyleMiniPreview）
 * - TV 遥控器：上下（或左右）移动选项，OK 应用，BACK 关闭
 */
@Composable
private fun BottomBarStylePickerOverlay(
    current: Int,
    pickerIdx: Int,
    liquidGlass: Boolean,
    onSelect: (Int) -> Unit,
    onDismiss: () -> Unit
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0x66000000))
            .clickable(onClick = onDismiss),
        contentAlignment = Alignment.Center
    ) {
        GlassPanel(
            liquidGlass = liquidGlass,
            cornerRadius = 14.dp,
            overlayDark = true,
            modifier = Modifier
                .width(430.dp)
                .wrapContentWidth()
                // 拦截卡片内点击，避免透传到遮罩误关闭（不添加焦点目标：
                // TV 按键由外层菜单 Box 的 onPreviewKeyEvent 统一路由）
                .clickable(
                    interactionSource = remember { androidx.compose.foundation.interaction.MutableInteractionSource() },
                    indication = null
                ) {}
        ) {
            Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
                Text(
                    text = "全屏底栏样式",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "选择后立即生效，弹窗保持打开可连续对比切换",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
                Spacer(modifier = Modifier.height(10.dp))

                // 全部样式列出（单一数据源 TV_BOTTOM_BAR_STYLES），超出高度可滚动避免溢出；
                // 遥控器环绕移动选中项时列表自动跟随滚动，保证选中项始终可见
                val pickerListState = rememberLazyListState()
                LaunchedEffect(pickerIdx) {
                    if (pickerIdx in TV_BOTTOM_BAR_STYLES.indices) {
                        pickerListState.animateScrollToItem(pickerIdx)
                    }
                }
                LazyColumn(
                    state = pickerListState,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 400.dp)
                ) {
                    itemsIndexed(TV_BOTTOM_BAR_STYLES) { _, entry ->
                        val (style, name) = entry
                        val isSel = style == pickerIdx
                        val isCurrent = style == current
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .then(if (isSel) Modifier.tvGlassSelected(8) else Modifier)
                                .clickable { onSelect(style) }
                                .padding(horizontal = 10.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            // 单选点：选中为实心 accent 圆，未选中为描边空心圆
                            Box(
                                modifier = Modifier
                                    .size(16.dp)
                                    .clip(CircleShape)
                                    .then(
                                        if (isSel) Modifier.background(tvPalette.accentGraphic)
                                        else Modifier.border(1.5.dp, MaterialTheme.colorScheme.onSurfaceVariant, CircleShape)
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                if (isSel) {
                                    Box(modifier = Modifier.size(6.dp).clip(CircleShape).background(MaterialTheme.colorScheme.onSurface))
                                }
                            }
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = name,
                                color = if (isSel) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 15.sp,
                                fontWeight = if (isSel) FontWeight.Medium else FontWeight.Normal,
                                modifier = Modifier.weight(1f)
                            )
                            if (isCurrent) {
                                Text(text = "当前", color = tvPalette.accentText, fontSize = 11.sp)
                                Spacer(modifier = Modifier.width(8.dp))
                            }
                            BottomBarStyleMiniPreview(style, modifier = Modifier.width(110.dp))
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                    }
                }

                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "OK 应用 · 返回键关闭",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    modifier = Modifier.align(Alignment.End)
                )
            }
        }
    }
}
