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
import androidx.compose.foundation.lazy.LazyListState
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
import androidx.compose.material.icons.filled.Devices
import androidx.compose.material.icons.filled.Equalizer
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Info
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
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.BlurOn
import androidx.compose.material.icons.filled.CloudSync
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
import androidx.compose.ui.draw.alpha
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
 * 横屏两列菜单的分组（自上而下）：
 * - 订阅源：启用中的源列表 → 订阅源管理 → EPG 订阅源 → 打开网络流 → 打开播放列表
 * - 频道管理：频道列表 / 节目单 EPG / 频道映射 / 收藏
 * - 播放设置：播放器设置 / 字幕 / 视频 / 音频 / 播放
 * - 多画面：双画面 / 四画面 / 九画面（已激活时为切换 + 退出）
 * - 外观：主题（三态合并为一行，弹单选）/ 液态玻璃 / 折射 / 界面模式 / 全屏底栏样式
 * - 界面显示：视图 / 显示时间 / 显示网速 / 隐藏序号 / 列表图标 / 底部图标 / 关闭EPG / 关闭收藏
 * - 网络：网络增强 / GitHub 加速代理
 * - 工具设置：工具 / 截图 / A/V 同步 / 切片导出 / 音频可视化 / 歌词
 * - 文件：打开本地文件 / 最近打开 / 另存为 M3U
 * - 系统：自动续播 / 开机自启动 / 屏保 / 屏保等待 / 刷新 / 关于 / 画中画 / 退出
 *
 * 布局自适应：
 * - 竖屏：单列列表（图标 + 标题 + 副标题）
 * - 横屏：右侧两列浮动菜单（分组 + 条目），超过可视高度时跟随选中项滚动
 */
@Composable
fun MainMenuPanel(viewModel: AppViewModel) {
    val currentChannel by viewModel.currentChannel.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val glassRefraction by viewModel.glassRefraction.collectAsState()
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
    // 界面模式：TV 端唯一可切换手机/平板/TV 形态的入口（电视没有竖屏设置页）
    val uiModePref by viewModel.uiModePref.collectAsState()
    // 频道专属设置：决定「清除频道专属设置」是否出现在频道管理组
    val perChannelEnabled by viewModel.perChannelSettingsEnabled.collectAsState()
    val hasChannelSettings = remember(currentIdx, perChannelEnabled) {
        currentIdx >= 0 && viewModel.hasChannelSettings(currentIdx)
    }
    // GitHub 加速代理：与设置页同一份配置，全屏菜单「网络」组提供直达入口
    val githubProxyEnabled by viewModel.githubProxyEnabled.collectAsState()
    val githubProxySelected by viewModel.githubProxySelected.collectAsState()
    // 启动与屏保：与手机端设置页共用同一份配置，电视端此前只能在手机端改
    val autoResume by viewModel.autoResume.collectAsState()
    val bootStart by viewModel.bootStart.collectAsState()
    val screenSaverEnabled by viewModel.screenSaverEnabled.collectAsState()
    val screenSaverTimeout by viewModel.screenSaverTimeoutMinutes.collectAsState()
    // 当前渲染路径：直写 Surface 时 mpv 字幕/滤镜/截图入口置灰（仍可见）
    val actualVo by viewModel.actualVo.collectAsState()
    val surfaceDirect = actualVo == "mediacodec_embed"

    val isFavorite = currentIdx >= 0 && favorites.contains(currentIdx)

    // 全屏底栏样式选择弹窗：条目点击后弹出单选列表（选中态高亮、选择后保持打开可连续切换）
    // 开关状态放 ViewModel：BACK 键在 Activity.onKeyDown 统一处理（按键分发下
    // Compose BackHandler 不生效），需跨层读取
    val showStylePicker by viewModel.stylePickerOpen.collectAsState()
    // 弹窗选中项提升到面板层：按键路由统一走外层菜单 Box 的 onPreviewKeyEvent，
    // 不依赖弹窗卡片自身抢焦点（实测 requestFocus 在菜单 GlassPanel 持有焦点时不可靠，
    // 焦点会漂移到全屏遮罩的 clickable 上，导致 OK 键误触发 onDismiss 关闭弹窗）
    var stylePickerIdx by remember { mutableStateOf(bottomBarStyle) }

    // 界面模式：点击弹出单选列表，不再点一下循环一格
    var showUiModePicker by remember { mutableStateOf(false) }
    if (showUiModePicker) {
        UiModePickerDialog(
            current = uiModePref,
            onPick = { pref ->
                showUiModePicker = false
                if (pref != uiModePref) {
                    viewModel.setUiModePreference(pref)
                    viewModel.toggleMenuPanel()
                }
            },
            onDismiss = { showUiModePicker = false }
        )
    }

    // 主题：三态合并为一行，点击弹单选（与设置页一致）。
    // 三个选项写入的值与原「深色模式 / 浅色模式 / 跟随系统」三个独立入口完全一致。
    var showThemePicker by remember { mutableStateOf(false) }
    if (showThemePicker) {
        ThemePickerDialog(
            current = themeMode,
            onPick = { mode ->
                showThemePicker = false
                viewModel.setThemeMode(mode)
            },
            onDismiss = { showThemePicker = false }
        )
    }

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

    // 菜单宿主：右侧玻璃面板只负责「关面板」和需要 Activity/Launcher 的动作，
    // 其余动作统一由 MenuCatalog 的动作表派发。
    val menuHost = MenuHost(
        kind = MenuHostKind.RIGHT_PANEL,
        closeHost = { viewModel.toggleMenuPanel() },
        launchPlaylist = {
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
        launchVideo = {
            if (!viewModel.isSafAvailable()) {
                viewModel.toggleMenuPanel()
                viewModel.showMediaFileBrowser()
            } else {
                videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
            }
        },
        // 主题三态合并为一行：点击弹单选，写值与原来三个独立入口一致
        openThemePicker = { showThemePicker = true },
        openUiModePicker = { showUiModePicker = true },
        openBottomBarStylePicker = {
            stylePickerIdx = bottomBarStyle
            // 打开弹窗即进入实时预览：底栏显示出来并按当前样式渲染，
            // 后续随弹窗焦点切换实时变化（BACK 未确定则恢复原样式）
            viewModel.setStylePreview(bottomBarStyle)
            viewModel.showControlsAutoHide()
            viewModel.setStylePickerOpen(true)
        }
    )

    val menuState = MenuRuntimeState(
        surfaceDirect = surfaceDirect,
        hasChannel = currentChannel != null,
        isFavorite = isFavorite,
        themeMode = themeMode,
        uiModeLabel = uiModePref.label,
        bottomBarStyleLabel = TV_BOTTOM_BAR_STYLES.firstOrNull { it.first == bottomBarStyle }?.second
            ?: "信息详情式",
        liquidGlass = liquidGlass,
        glassRefraction = glassRefraction,
        showTime = osdShowTime,
        showNetSpeed = osdShowNetSpeed,
        hideChannelNum = osdHideChannelNum,
        disableEpg = osdDisableEpg,
        disableFavorite = osdDisableFavorite,
        showListIcon = osdShowListIcon,
        showBottomIcon = osdShowBottomIcon,
        sources = sources,
        selectedSource = selectedSource,
        multiViewLayout = if (multiViewState.active) multiViewState.layout else null,
        perChannelEnabled = perChannelEnabled,
        hasChannelSettings = hasChannelSettings,
        githubProxyEnabled = githubProxyEnabled,
        githubProxySelected = githubProxySelected,
        autoResume = autoResume,
        bootStart = bootStart,
        screenSaverEnabled = screenSaverEnabled,
        screenSaverTimeout = screenSaverTimeout
    )
    val sections = MenuCatalog.sections(menuState, MenuSurface.RIGHT_ONLY)

    fun fireEntry(entry: MenuEntryModel) {
        entry.action?.let { viewModel.dispatchMenuAction(it, menuHost) }
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
        // 平板模式：菜单是从分屏页/首页叠上来的，底下的 EPG 网格/频道宫格仍持有焦点，
        // 单次 requestFocus 常被时序吃掉 → 方向键全被下层消费，菜单看起来"按了没反应"。
        // 小步重试直到菜单真正拿到焦点。
        LaunchedEffect(Unit) {
            repeat(12) { attempt ->
                if (attempt > 0) kotlinx.coroutines.delay(80)
                if (kotlin.runCatching { menuFocusRequester.requestFocus() }.isSuccess) return@LaunchedEffect
            }
        }

        // 两列各自维护滚动状态：选中项是手绘焦点（上下键由外层 onPreviewKeyEvent 消费，
        // 不走 Compose 焦点系统），所以不会自动触发 bringIntoView，必须显式滚动，
        // 否则条目超出可视高度后高亮会跑到视口外看不见。
        val sectionListState = rememberLazyListState()
        val entryListState = rememberLazyListState()

        fun isFullyVisible(state: LazyListState, index: Int): Boolean {
            val item = state.layoutInfo.visibleItemsInfo.firstOrNull { it.index == index } ?: return false
            val start = state.layoutInfo.viewportStartOffset
            val end = state.layoutInfo.viewportEndOffset
            return item.offset >= start && item.offset + item.size <= end
        }

        // 切换分组：左列（条目的那一列）滚回顶部并重置选中索引，
        // 避免继承上一组的滚动偏移导致「换组后从中间开始显示」。
        LaunchedEffect(currentSection?.title) {
            leftSelectedIdx = 0
            if (currentSection != null && currentSection.entries.isNotEmpty()) {
                entryListState.scrollToItem(0)
            }
        }
        // 选中项不在可视区才滚动：可视区内每步都滚会让列表不停跳动
        LaunchedEffect(safeLeftIdx, activeColumn, currentSection?.title) {
            if (activeColumn == 1 && currentSection != null && currentSection.entries.isNotEmpty() &&
                !isFullyVisible(entryListState, safeLeftIdx)
            ) {
                entryListState.animateScrollToItem(safeLeftIdx)
            }
        }
        LaunchedEffect(safeIdx) {
            if (!isFullyVisible(sectionListState, safeIdx)) {
                sectionListState.animateScrollToItem(safeIdx)
            }
        }

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
                                // 边界即停（不回绕）：回绕会让选中项跑到视口外后突然跳回首项
                                selectedSectionIdx = (safeIdx + 1).coerceAtMost(sections.lastIndex)
                            } else if (currentSection != null && currentSection.entries.isNotEmpty()) {
                                leftSelectedIdx = (safeLeftIdx + 1).coerceAtMost(currentSection.entries.lastIndex)
                            }
                            true
                        }
                        Key.DirectionUp -> {
                            if (activeColumn == 0) {
                                selectedSectionIdx = (safeIdx - 1).coerceAtLeast(0)
                            } else if (currentSection != null && currentSection.entries.isNotEmpty()) {
                                leftSelectedIdx = (safeLeftIdx - 1).coerceAtLeast(0)
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
                                currentSection.entries.getOrNull(safeLeftIdx)
                                    ?.takeIf { it.enabled }?.let(::fireEntry)
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
                            state = entryListState,
                            modifier = Modifier.fillMaxHeight().width(150.dp),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 6.dp)
                        ) {
                            itemsIndexed(
                                items = currentSection.entries,
                                key = { _, entry -> entry.id }
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
                                        // 遥控焦点描边：与其余页面一致（2dp 主题色），
                                        // 选中底色之外再给一圈明确的焦点框
                                        .then(
                                            if (isRightSelected) Modifier.border(
                                                2.dp,
                                                MaterialTheme.colorScheme.primary.copy(alpha = 0.9f),
                                                RoundedCornerShape(6.dp)
                                            ) else Modifier
                                        )
                                        .alpha(if (entry.enabled) 1f else 0.38f)
                                        .clickable(enabled = entry.enabled) {
                                            activeColumn = 1
                                            leftSelectedIdx = idx
                                            fireEntry(entry)
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
                                    if (!entry.enabled && entry.disabledReason.isNotEmpty()) {
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = "不可用",
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            fontSize = 10.sp,
                                            maxLines = 1
                                        )
                                    } else if (entry.isToggle) {
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
                        state = sectionListState,
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
                                    // 一级分组列：当前列有遥控焦点时给描边（与左列一致）
                                    .then(
                                        if (isLeftActive) Modifier.border(
                                            2.dp,
                                            MaterialTheme.colorScheme.primary.copy(alpha = 0.9f),
                                            RoundedCornerShape(6.dp)
                                        ) else Modifier
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
                    LandscapeMenuGrid(sections = sections, onEntryClick = ::fireEntry)
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
                            key = { entry -> entry.id }
                        ) { entry ->
                            MenuEntryItem(
                                entry = entry,
                                onClick = { fireEntry(entry) }
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
private fun LandscapeMenuGrid(
    sections: List<MenuSection>,
    onEntryClick: (MenuEntryModel) -> Unit
) {
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
                                onClick = { onEntryClick(entry) },
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
            .height(if (entry.enabled) 72.dp else 84.dp)
            .clip(RoundedCornerShape(8.dp))
            .alpha(if (entry.enabled) 1f else 0.42f)
            .clickable(enabled = entry.enabled, onClick = onClick)
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
            // 置灰原因（入口保留，只提示当前不可用）
            if (!entry.enabled && entry.disabledReason.isNotEmpty()) {
                Text(
                    text = "直写 Surface 下不可用",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 9.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}

// -----------------------------------------------------------------
// 菜单数据模型：共享定义见 MenuCatalog.kt，这里只保留渲染侧别名
// -----------------------------------------------------------------

private typealias MenuEntry = MenuEntryModel
private typealias MenuSection = MenuSectionModel

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
            .alpha(if (entry.enabled) 1f else 0.38f)
            .clickable(enabled = entry.enabled, onClick = onClick)
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

// -----------------------------------------------------------------
// 主题选择弹窗
// -----------------------------------------------------------------

/**
 * 主题选择弹窗：深色 / 浅色 / 跟随系统。
 *
 * 与原「深色模式 / 浅色模式 / 跟随系统」三个独立菜单项完全等价——只是把三行入口
 * 收成一行「主题：当前值」+ 单选弹窗，写入 ViewModel 的值仍是 dark / light / system。
 */
@Composable
internal fun ThemePickerDialog(
    current: String,
    onPick: (String) -> Unit,
    onDismiss: () -> Unit
) {
    val options = listOf(
        "dark" to "深色模式",
        "light" to "浅色模式",
        "system" to "跟随系统"
    )
    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(current) { runCatching { focusRequester.requestFocus() } }
    androidx.compose.ui.window.Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
            modifier = Modifier.width(340.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "主题",
                    fontSize = 17.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(modifier = Modifier.height(12.dp))
                options.forEach { (mode, label) ->
                    val selected = mode == current
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .then(if (selected) Modifier.tvGlassSelected(8) else Modifier)
                            .then(if (selected) Modifier.focusRequester(focusRequester) else Modifier)
                            .tvFocusBorder()
                            .clickable { onPick(mode) }
                            .padding(horizontal = 10.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(16.dp)
                                .clip(CircleShape)
                                .background(if (selected) MaterialTheme.colorScheme.primary else Color.Transparent)
                                .border(1.5.dp, MaterialTheme.colorScheme.outline, CircleShape)
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(
                            text = label,
                            fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.width(190.dp)
                        )
                        if (selected) {
                            Text("当前", fontSize = 11.sp, color = tvPalette.accentText)
                        }
                    }
                    Spacer(modifier = Modifier.height(6.dp))
                }
                Text(
                    text = "OK 确认 · 返回键取消",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.End
                )
            }
        }
    }
}
