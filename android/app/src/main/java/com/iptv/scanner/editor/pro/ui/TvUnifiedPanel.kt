package com.iptv.scanner.editor.pro.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
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
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Equalizer
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.ScreenshotMonitor
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SyncAlt
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material.icons.filled.VideoSettings
import androidx.compose.material.icons.filled.ViewInAr
import androidx.compose.material.icons.filled.ViewModule
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Web
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
import androidx.compose.ui.draw.blur
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.player.ProgressHelper
import com.iptv.scanner.editor.pro.ui.ChannelTab
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvGlassSelected
import com.iptv.scanner.editor.pro.ui.theme.GlassPanel
import com.iptv.scanner.editor.pro.ui.theme.DarkOverlayTheme
import com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface
import com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported
import java.util.Locale

// 侧边栏风格配色（主色统一为竖屏 APTV 橙红 AptvAccent）
private val ACCENT_CYAN = tvPalette.info
private val ICON_BG = Color(0x32FFFFFF)

/** 面板可读性底色：玻璃霜层上垫深色底，避免亮色视频背景下文字看不清 */
// 玻璃面板不再叠加实底 scrim：深色可读性由玻璃材质 overlayDark 暗玻璃霜层提供
/** 栏间分隔条颜色 */
private val TV_DIVIDER = Color(0x24FFFFFF)

/**
 * TV 端统一面板：五列布局（控制层 + 分组 + 频道列表 + 节目单 + 节目描述）。
 *
 * 设计目的：
 * - 解决 TV 端遥控器上下键被切频道占用、无法快速打开列表的问题
 * - MENU 键打开统一面板，默认焦点在频道列表，快速切换频道
 *
 * 五列布局（频道列表模式）：
 * - 第一列（72dp）：控制层（订阅 / 本地 / 菜单 / OSD）
 * - 第二列（200dp）：分组列表（纵向）
 * - 第三列（300dp）：频道列表
 * - 第四列（weight 1f）：当前频道的节目单
 * - 第五列（300dp）：选中节目描述
 *
 * 菜单模式：
 * - 第一列（菜单高亮）+ 第二列（MenuColumn）+ 第三~五列占位
 *
 * 焦点导航：
 * - 默认焦点在第三列（频道列表）
 * - DPAD LEFT/RIGHT：在列之间切换焦点（Compose 焦点系统自动处理）
 * - DPAD UP/DOWN：在当前列内导航
 * - BACK：关闭面板
 * - CENTER/ENTER：确认（播放频道 / 打开菜单项 / 选择节目）
 *
 * 与内存规则对齐：
 * - TV remote DPAD navigation: when any panel is open, direction keys + CENTER/ENTER are handled by Compose focus system
 */
@Composable
fun TvUnifiedPanel(viewModel: AppViewModel) {
    val currentIdx by viewModel.currentIdx.collectAsState()
    val channels by viewModel.channels.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val isFavorite = currentIdx >= 0 && favorites.contains(currentIdx)

    // EPG 数据（使用焦点频道的 EPG，而非当前播放频道的 EPG）
    val focusedEpg by viewModel.focusedEpg.collectAsState()
    val focusedEpgLoading by viewModel.focusedEpgLoading.collectAsState()
    val controlsPinned by viewModel.controlsPinned.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    val osdHideChannelNum by viewModel.osdHideChannelNum.collectAsState()
    val osdDisableFavorite by viewModel.osdDisableFavorite.collectAsState()
    val osdDisableEpg by viewModel.osdDisableEpg.collectAsState()

    // 订阅源加载态：服务端状态 + 本地重载标志，任一为真即视为加载中。
    // 频道列空态必须依赖真实加载状态，不能用「列表为空」反推。
    val iptvStatus by viewModel.iptvStatus.collectAsState()
    val localSourceLoading by viewModel.sourceLoading.collectAsState()

    // 多画面状态（多画面模式下点击频道添加到副画面，而非切换主画面）
    val multiViewState by viewModel.multiViewState.collectAsState()

    // 频道列表 tab 与分组（第一列控制层使用）
    val channelsTab by viewModel.channelsTab.collectAsState()
    val allGroups by viewModel.groups.collectAsState()
    // 根据 channelsTab 过滤分组：
    // - SUB tab：显示所有频道的分组（订阅频道 + 本地频道，但本地频道通常无分组或分组独立）
    // - LOCAL tab：只显示本地文件频道的分组，避免显示订阅分组误导用户
    // 根因：viewModel.groups 是从所有频道提取的，未根据 tab 过滤，
    // 导致 LOCAL tab 下仍显示订阅分组。
    val groups = remember(allGroups, channels, channelsTab) {
        if (channelsTab == ChannelTab.LOCAL) {
            channels
                .filter { it.source.isEmpty() || ProgressHelper.isLocalFile(it.url) }
                .map { it.group }
                .filter { it.isNotEmpty() }
                .distinct()
        } else {
            allGroups
        }
    }
    val selectedGroup by viewModel.selectedGroup.collectAsState()

    // 订阅源列表（多源时显示切换列）
    val sources by viewModel.sources.collectAsState()
    val selectedSource by viewModel.selectedSource.collectAsState()
    val enabledSources = remember(sources) { sources.filter { it.enabled } }

    // 统一面板状态
    var unifiedMode by remember { mutableStateOf(UnifiedMode.CHANNELS) }
    var selectedProgram by remember { mutableStateOf<IptvEpgProgram?>(null) }


    // 焦点频道索引（频道列表中当前聚焦的频道，用于 EPG 跟随显示）
    var focusedChannelIdx by remember { mutableStateOf(currentIdx) }
    // EPG 跟随的频道索引：未聚焦/停止播放后（currentIdx=-1）回退到第一个频道，
    // 保证 EPG 列始终显示节目单（否则显示"请选择频道"占位，无法点节目进入回看）
    val epgChannelIdx = if (focusedChannelIdx >= 0) focusedChannelIdx else 0
    val focusedChannel = remember(epgChannelIdx, channels) {
        channels.getOrNull(epgChannelIdx)
    }

    // 焦点管理：初始焦点在第三列（频道列表）
    val sidebarVisible by viewModel.landscapeSidebarVisible.collectAsState()

    // EPG 列延迟加载：侧边栏打开 300ms 后才显示 EPG 列和描述列，减少首次渲染开销
    var epgColumnsReady by remember { mutableStateOf(false) }
    LaunchedEffect(sidebarVisible) {
        if (sidebarVisible) {
            epgColumnsReady = false
            kotlinx.coroutines.delay(300)
            epgColumnsReady = true
        } else {
            epgColumnsReady = false
        }
    }

    val channelListFocus = remember { FocusRequester() }
    // 「全部」分组项焦点：未选择频道时初始焦点落在「全部」，避免 DPAD 几何聚焦到分组列中间项
    val allGroupFocus = remember { FocusRequester() }
    LaunchedEffect(sidebarVisible) {
        if (sidebarVisible) {
            kotlinx.coroutines.delay(300)
            // 自动聚焦当前播放频道，使EPG列显示
            if (focusedChannelIdx < 0 && currentIdx >= 0) {
                focusedChannelIdx = currentIdx
            }
            if (currentIdx >= 0) {
                kotlin.runCatching { channelListFocus.requestFocus() }
            } else {
                // 未选择频道：默认聚焦「全部」分组（分组筛选保持默认全部）
                if (selectedGroup.isNotEmpty()) viewModel.setSelectedGroup("")
                kotlin.runCatching { allGroupFocus.requestFocus() }
            }
        }
    }

    // 焦点频道变化时刷新 EPG（防抖 300ms，避免快速滚动时大量 EPG 请求堆积导致卡死）
    LaunchedEffect(epgChannelIdx, channels) {
        selectedProgram = null
        if (epgChannelIdx >= 0 && channels.getOrNull(epgChannelIdx) != null) {
            // 防抖：快速滚动时 LaunchedEffect 会被下次焦点变化取消，
            // 只有停留超过 300ms 的频道才会真正触发 EPG 请求
            kotlinx.coroutines.delay(300)
            viewModel.fetchEpgForChannel(epgChannelIdx)
        }
    }

    // 文件选择器（主菜单模式使用）
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

    /**
     * 打开全屏覆盖子面板，同时关闭统一面板。
     *
     * 关键：必须关闭统一面板（_landscapeSidebarVisible 和 _tvUnifiedPanelOpen），
     * 让 TvUnifiedPanel 从 Compose 树中移除。
     * - 正常 TV 模式：TvUnifiedPanel 由 _landscapeSidebarVisible 控制渲染（在 TvPlayerLayout 的 AnimatedVisibility 内）
     * - 多画面模式：TvUnifiedPanel 由 _tvUnifiedPanelOpen 控制渲染（在 MainPlayerScreen 顶层）
     * 两种模式都要关闭，确保子面板的 focusGroup() 不被下层 TvUnifiedPanel 的菜单项干扰
     * （底部功能图标在分组列底部，按OK键触发模式切换）。
     *
     * 子面板关闭后回到播放界面，用户按 MENU 键可重新打开主菜单。
     */
    fun openOverlay(action: () -> Unit) {
        viewModel.setLandscapeSidebarVisible(false)
        action()
        viewModel.closeTvUnifiedPanel()
    }


    Surface(
        color = Color.Transparent,
        modifier = Modifier.fillMaxSize()
    ) {
        Row(modifier = Modifier.fillMaxSize().systemBarsPadding()) {
            when (unifiedMode) {
                UnifiedMode.CHANNELS -> {
                    // 是否显示分组列和节目单/描述列
                    val showGroups = groups.isNotEmpty()
                    val showEpg = !osdDisableEpg

                    // -----------------------------------------------------------------
                    // 第0列：快捷菜单列（侧边栏风格竖向图标列）
                    // -----------------------------------------------------------------
                    QuickMenuColumn(
                        channelsTab = channelsTab,
                        controlsPinned = controlsPinned,
                        liquidGlass = liquidGlass,
                        onTabChange = { tab ->
                            viewModel.setChannelsTab(tab)
                            unifiedMode = UnifiedMode.CHANNELS
                            selectedProgram = null
                            focusedChannelIdx = -1
                        },
                        onModeChange = { newMode ->
                            unifiedMode = newMode
                            selectedProgram = null
                        },
                        onOsd = { viewModel.toggleControlsPinned() },
                        modifier = Modifier.width(48.dp)
                    )

                    // -----------------------------------------------------------------
                    // 订阅源切换列（多源时显示，侧边栏风格）
                    // -----------------------------------------------------------------
                    if (enabledSources.size > 1) {
                        SourceSwitchColumn(
                            sources = enabledSources,
                            selectedSource = selectedSource,
                            liquidGlass = liquidGlass,
                            onSourceSelected = { url ->
                                viewModel.setSelectedSource(url)
                                viewModel.refreshUi()
                            },
                            modifier = Modifier.width(72.dp)
                        )
                    }

                    // -----------------------------------------------------------------
                    // 分组+频道+EPG 合并为一个圆角矩形
                    // -----------------------------------------------------------------
                    GlassPanel(
                        liquidGlass = liquidGlass,
                        cornerRadius = 10.dp,
                        overlayDark = true,
                        modifier = Modifier.fillMaxHeight()
                    ) {
                        // 玻璃材质自带暗色霜层（overlayDark），不再叠加实底 scrim ——
                        // 叠加深色底衬会盖住磨砂/光斑/噪点，让玻璃退化成"只有透明度"的观感
                        Row(
                            modifier = Modifier.fillMaxHeight()
                        ) {
                            // 第一列：分组列表
                            if (showGroups) {
                                GroupColumn(
                                    groups = groups,
                                    selectedGroup = selectedGroup,
                                    onGroupSelected = { viewModel.setSelectedGroup(it) },
                                    modifier = Modifier.width(180.dp),
                                    allItemFocus = allGroupFocus
                                )
                            }

                            // 栏间分隔条
                            if (showGroups) {
                                Box(modifier = Modifier.width(1.dp).fillMaxHeight().background(TV_DIVIDER))
                            }

                            // 第二列：频道列表
                            ChannelsColumn(
                                channels = channels,
                                currentIdx = currentIdx,
                                favorites = favorites,
                                channelsTab = channelsTab,
                                selectedGroup = selectedGroup,
                                getCachedCurrentProgram = { idx ->
                                    viewModel.getCachedCurrentProgram(idx)
                                },
                                epgCacheVersion = epgCacheVersion,
                                hideChannelNum = osdHideChannelNum,
                                disableFavorite = osdDisableFavorite,
                                disableEpg = osdDisableEpg,
                                onChannelClick = { idx ->
                                    // 触屏点击不走焦点系统（clickable 不触发焦点回调），
                                    // 必须手动同步 EPG 跟随频道，否则 EPG 列停留在旧频道节目单
                                    focusedChannelIdx = idx
                                    if (multiViewState.active) {
                                        viewModel.addChannelToMultiView(idx)
                                    } else {
                                        viewModel.playChannel(idx)
                                    }
                                },
                                onFocusedChannelChange = { idx -> focusedChannelIdx = idx },
                                sourceLoading = iptvStatus?.sourceLoading == true || localSourceLoading,
                                sourceWarning = iptvStatus?.sourceWarning.orEmpty(),
                                onAddSource = { viewModel.toggleSourceManager() },
                                onRefresh = { viewModel.reloadSources() },
                                modifier = Modifier.width(260.dp).focusRequester(channelListFocus)
                            )

                            // 栏间分隔条
                            Box(modifier = Modifier.width(1.dp).fillMaxHeight().background(TV_DIVIDER))

                            // 第三列：节目单
                            if (showEpg) {
                                if (focusedChannel != null) {
                                    EpgListColumn(
                                        channel = focusedChannel,
                                        epg = focusedEpg,
                                        loading = focusedEpgLoading,
                                        selectedProgram = selectedProgram,
                                        onProgramSelect = { program -> selectedProgram = program },
                                        onProgramClick = { program ->
                                            val nowSec = System.currentTimeMillis() / 1000L
                                            val isLive = program.startTs <= nowSec && program.stopTs >= nowSec
                                            val isPast = program.stopTs < nowSec
                                            // 用 epgChannelIdx 而非 focusedChannelIdx：
                                            // 未聚焦/停止后 EPG 列回退显示第一个频道，
                                            // 此时 focusedChannelIdx=-1，直接用它会导致播放失败
                                            when {
                                                isLive -> viewModel.playChannel(epgChannelIdx)
                                                isPast -> {
                                                    // 直接以 epgChannelIdx 进入回看。不能先 playChannel：
                                                    // 它会加载直播流，与 startCatchup 的回看流形成
                                                    // 双 loadfile 竞态，回看可能被 superseded 跳过播成直播
                                                    openOverlay { viewModel.startCatchup(program, epgChannelIdx) }
                                                }
                                                else -> viewModel.toggleReminder(program, focusedChannel)
                                            }
                                        },
                                        isReminderSet = { program -> viewModel.isReminderSet(program) },
                                        modifier = Modifier.width(260.dp)
                                    )
                                } else {
                                    Box(
                                        modifier = Modifier.width(260.dp).fillMaxHeight(),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            "请选择频道",
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            fontSize = 14.sp
                                        )
                                    }
                                }
                            }
                        }

                    }
                }
                UnifiedMode.MENU -> {
                    // -----------------------------------------------------------------
                    // 菜单模式：第二列显示 MenuColumn，第三~五列占位
                    // -----------------------------------------------------------------
                    MenuColumn(
                        viewModel = viewModel,
                        currentIdx = currentIdx,
                        isFavorite = isFavorite,
                        multiViewActive = multiViewState.active,
                        currentMultiViewLayout = if (multiViewState.active) multiViewState.layout else null,
                        onEnterMultiView = { layout ->
                            // 进入多画面：关闭统一面板，让多画面网格可见
                            viewModel.setLandscapeSidebarVisible(false)
                            viewModel.enterMultiView(layout)
                        },
                        onExitMultiView = {
                            viewModel.exitMultiView()
                            viewModel.setLandscapeSidebarVisible(false)
                        },
                        onOpenPlaylist = {
                            // SAF launcher 注册在 TvUnifiedPanel 内，必须在结果返回时保持面板存活。
                            // 之前用 openOverlay 先关面板再 launch，导致 launcher 被反注册、SAF 结果被丢弃。
                            // 修复：SAF 是系统级浮层会覆盖面板，保持面板打开让 launcher 存活；
                            //       FileBrowser 路径才需要关闭统一面板（FileBrowser 在统一面板之后渲染会被遮挡）。
                            if (!viewModel.isSafAvailable()) {
                                viewModel.setLandscapeSidebarVisible(false)
                                viewModel.showFileBrowser()
                            } else {
                                playlistLauncher.launch(arrayOf(
                                    "application/x-mpegurl", "application/vnd.apple.mpegurl",
                                    "audio/x-mpegurl", "video/x-mpegurl",
                                    "text/plain", "application/octet-stream"
                                ))
                            }
                        },
                        onOpenUrl = { openOverlay { viewModel.toggleOpenUrlDialog() } },
                        onOpenLocalVideo = {
                            // 同 onOpenPlaylist：SAF 路径保持面板打开，FileBrowser 路径关闭面板
                            if (!viewModel.isSafAvailable()) {
                                viewModel.setLandscapeSidebarVisible(false)
                                viewModel.showMediaFileBrowser()
                            } else {
                                videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
                            }
                        },
                        onSources = {
                            openOverlay {
                                viewModel.setSourceTab(SourceTab.PLAYLIST)
                                viewModel.toggleSourceManager()
                            }
                        },
                        onEpgSources = {
                            openOverlay {
                                viewModel.setSourceTab(SourceTab.EPG)
                                viewModel.toggleSourceManager()
                            }
                        },
                        onMapping = { openOverlay { viewModel.toggleMappingPanel() } },
                        onChannels = { openOverlay { viewModel.showChannelsPanel() } },
                        onEpg = { openOverlay { viewModel.showEpgPanel() } },
                        onSubtitle = { openOverlay { viewModel.toggleSubtitleSettings() } },
                        onVideo = { openOverlay { viewModel.toggleVideoSettings() } },
                        onAudio = { openOverlay { viewModel.toggleAudioSettings() } },
                        onPlayback = { openOverlay { viewModel.togglePlaybackPanel() } },
                        onScreenshot = { openOverlay { viewModel.toggleScreenshotPanel() } },
                        onAvsync = { openOverlay { viewModel.toggleAvSyncPanel() } },
                        onNetwork = { openOverlay { viewModel.toggleNetworkPanel() } },
                        onTools = { openOverlay { viewModel.toggleToolsPanel() } },
                        onView = { openOverlay { viewModel.toggleViewSettings() } },
                        onSettings = { openOverlay { viewModel.togglePlayerSettings() } },
                        onAbout = { openOverlay { viewModel.toggleAboutPanel() } },
                        onToggleFavorite = { viewModel.toggleFavorite() },
                        onClearChannelSettings = {
                            val idx = viewModel.currentIdx.value
                            if (idx >= 0) viewModel.clearChannelSettings(idx)
                        },
                        onQuit = { viewModel.showOsd("退出", "请使用系统返回键退出") },
                        modifier = Modifier.width(360.dp).focusRequester(channelListFocus)
                    )
                    // 第三~五列占位
                    Spacer(modifier = Modifier.width(300.dp))
                    Spacer(modifier = Modifier.weight(1f))
                    Spacer(modifier = Modifier.width(300.dp))
                }
            }
        }
    }
}

// =====================================================================
// 模式枚举
// =====================================================================

enum class UnifiedMode { CHANNELS, MENU }

// =====================================================================
// 分组列表列
// =====================================================================

// =====================================================================
// 订阅源切换列（侧边栏风格，多源时显示）
// =====================================================================

@Composable
private fun SourceSwitchColumn(
    sources: List<com.iptv.scanner.editor.pro.data.IptvSource>,
    selectedSource: String,
    liquidGlass: Boolean,
    onSourceSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    LiquidGlassSurface(
        enabled = liquidGlass && isLiquidBlurSupported(),
        cornerRadius = 10.dp,
        staticGlass = true,
        overlayDark = true,
        fallbackColor = tvPalette.panelBackground.copy(alpha = 0.90f),
        modifier = modifier.fillMaxHeight()
    ) {
        DarkOverlayTheme {
            // 轻量单层玻璃：不额外垫深色底衬，避免双层叠加观感
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
            ) {
            items(items = sources, key = { it.url }) { src ->
                val isSelected = src.url == selectedSource
                val sourceName = src.name.ifEmpty { src.url.substringAfterLast('/').take(6) }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(if (isSelected) Modifier.tvGlassSelected(8) else Modifier)
                        .tvFocusBorder(8)
                        .clickable { onSourceSelected(src.url) }
                        .padding(horizontal = 6.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(5.dp)
                            .clip(CircleShape)
                            .background(if (isSelected) AptvAccent else MaterialTheme.colorScheme.outline)
                    )
                    Spacer(modifier = Modifier.width(5.dp))
                    Text(
                        text = sourceName,
                        color = if (isSelected) Color.White else MaterialTheme.colorScheme.onSurface,
                        fontSize = 11.sp,
                        fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
            }
        }
    }
}

// =====================================================================
// 分组列
// =====================================================================

@Composable
private fun GroupColumn(
    groups: List<String>,
    selectedGroup: String,
    onGroupSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
    allItemFocus: FocusRequester? = null
) {
    Surface(
        color = Color.Transparent,
        modifier = modifier.fillMaxHeight()
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            if (groups.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "暂无分组",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp,
                        lineHeight = 20.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
                ) {
                    // "全部" 项
                    item(key = "__all__") {
                        GroupItemRow(
                            label = "全部",
                            selected = selectedGroup.isEmpty(),
                            onClick = { onGroupSelected("") },
                            focusRequester = allItemFocus
                        )
                    }
                    // 各分组
                    items(items = groups, key = { it }) { group ->
                        GroupItemRow(
                            label = group,
                            selected = selectedGroup == group,
                            onClick = { onGroupSelected(group) }
                        )
                    }
                }
            }
        }
    }
}

// =====================================================================
// 快捷菜单列（侧边栏风格竖向图标列）
// =====================================================================

@Composable
private fun QuickMenuColumn(
    channelsTab: ChannelTab,
    controlsPinned: Boolean,
    liquidGlass: Boolean,
    onTabChange: (ChannelTab) -> Unit,
    onModeChange: (UnifiedMode) -> Unit,
    onOsd: () -> Unit,
    modifier: Modifier = Modifier
) {
    // 玻璃化：替换原 0x80222222 实底（与统一面板玻璃卡片同材质）
    LiquidGlassSurface(
        enabled = liquidGlass && isLiquidBlurSupported(),
        cornerRadius = 10.dp,
        staticGlass = true,
        overlayDark = true,
        fallbackColor = tvPalette.panelBackground.copy(alpha = 0.90f),
        modifier = modifier.fillMaxHeight()
    ) {
        DarkOverlayTheme {
            // 轻量单层玻璃：不额外垫深色底衬，避免双层叠加观感
            // （fallbackColor 已提供底色，图标为白色高对比，可读性足够）
            // fillMaxWidth：占满玻璃条宽度，否则 Box 内内容默认靠左上，图标列整体偏左不居中
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight()
                    .padding(vertical = 16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically)
            ) {
                QuickMenuIcon(Icons.Default.Web, "订阅", channelsTab == ChannelTab.SUB) { onTabChange(ChannelTab.SUB) }
                QuickMenuIcon(Icons.Default.VideoLibrary, "本地", channelsTab == ChannelTab.LOCAL) { onTabChange(ChannelTab.LOCAL) }

                QuickMenuIcon(
                    if (controlsPinned) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                    "OSD", controlsPinned, onOsd
                )
            }
        }
    }
}

@Composable
private fun QuickMenuIcon(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    isSelected: Boolean,
    onClick: () -> Unit
) {
    // 固定宽度 + 内容居中排列：玻璃选中块尺寸稳定，图标/文字严格居中不偏移
    // （旧写法 wrap 内容 + Text 行高 descent，导致玻璃块内视觉偏移）
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier
            .width(40.dp)
            .clip(RoundedCornerShape(8.dp))
            .then(if (isSelected) Modifier.tvGlassSelected(8) else Modifier)
            .tvFocusBorder(8)
            .clickable { onClick() }
            .padding(vertical = 8.dp)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = label,
            tint = if (isSelected) Color.White else Color(0xCCFFFFFF),
            modifier = Modifier.size(24.dp)
        )
        Spacer(modifier = Modifier.height(3.dp))
        Text(
            text = label,
            color = if (isSelected) Color.White else Color(0x99FFFFFF),
            fontSize = 9.sp,
            lineHeight = 10.sp
        )
    }
}

@Composable
private fun GroupItemRow(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    focusRequester: FocusRequester? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .then(if (selected) Modifier.tvGlassSelected(8) else Modifier)
            .tvFocusBorder(8)
            .clickable { onClick() }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 选中指示点（主色橙红）
        Box(
            modifier = Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(if (selected) AptvAccent else MaterialTheme.colorScheme.outline)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = label,
            color = if (selected) Color.White else MaterialTheme.colorScheme.onSurface,
            fontSize = 13.sp,
            fontWeight = if (selected) FontWeight.Medium else FontWeight.Normal,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

// =====================================================================
// 第三列：频道列表
// =====================================================================

@Composable
private fun ChannelsColumn(
    channels: List<IptvChannel>,
    currentIdx: Int,
    favorites: Set<Int>,
    channelsTab: ChannelTab,
    selectedGroup: String,
    getCachedCurrentProgram: (Int) -> IptvEpgProgram?,
    epgCacheVersion: Int,
    hideChannelNum: Boolean,
    disableFavorite: Boolean,
    disableEpg: Boolean,
    onChannelClick: (Int) -> Unit,
    onFocusedChannelChange: (Int) -> Unit,
    sourceLoading: Boolean,
    sourceWarning: String,
    onAddSource: () -> Unit,
    onRefresh: () -> Unit,
    modifier: Modifier = Modifier
) {
    // 根据 tab 和分组过滤频道
    // - SUB：全部频道
    // - LOCAL：仅本地文件协议频道
    val filteredChannels = remember(channels, selectedGroup, channelsTab) {
        val all = channels.mapIndexed { idx, c -> c to idx }
        val tabbed = if (channelsTab == ChannelTab.LOCAL) {
            all.filter { (c, _) -> c.source.isEmpty() || ProgressHelper.isLocalFile(c.url) }
        } else {
            all
        }
        if (selectedGroup.isEmpty()) tabbed else tabbed.filter { it.first.group == selectedGroup }
    }

    // 列表 key：以频道 URL 作为稳定身份，频道增删/分组过滤后组合状态与焦点不会错位
    val channelItemKeys = remember(filteredChannels) { buildChannelItemKeys(filteredChannels) }

    // 滚动状态：用于面板打开时自动滚动到当前频道
    val listState = rememberLazyListState()
    // 当前频道项的焦点请求器（面板打开时将 DPAD 焦点移到当前播放频道）
    val currentChannelFocus = remember { FocusRequester() }

    // 面板打开时自动滚动到当前频道（居中显示）并将焦点移到当前频道
    LaunchedEffect(currentIdx, filteredChannels) {
        if (filteredChannels.isNotEmpty() && currentIdx >= 0) {
            val pos = filteredChannels.indexOfFirst { (_, idx) -> idx == currentIdx }
            if (pos >= 0) {
                // 第一阶段：先跳到目标位置（无动画），强制列表布局更新
                listState.scrollToItem(pos)
                kotlinx.coroutines.delay(50)
                // 第二阶段：根据视口高度和列表项高度计算居中偏移
                val layoutInfo = listState.layoutInfo
                val viewportHeight = layoutInfo.viewportSize.height
                val itemHeight = layoutInfo.visibleItemsInfo.firstOrNull()?.size ?: 56
                val visibleCount = if (itemHeight > 0) viewportHeight / itemHeight else 7
                val centeredPos = (pos - visibleCount / 2).coerceAtLeast(0)
                listState.scrollToItem(centeredPos)
                // 第三阶段：将焦点移到当前频道项
                kotlinx.coroutines.delay(30)
                kotlin.runCatching { currentChannelFocus.requestFocus() }
            }
        }
    }

    Surface(
        color = Color.Transparent,
        modifier = modifier.fillMaxHeight()
    ) {
        Column(modifier = Modifier.fillMaxSize()) {

            // 频道列表
            if (filteredChannels.isEmpty()) {
                ChannelEmptyState(
                    tab = channelsTab,
                    loading = sourceLoading,
                    sourceWarning = sourceWarning,
                    groupName = if (channelsTab == ChannelTab.SUB) selectedGroup else "",
                    onAddSource = onAddSource,
                    onRefresh = onRefresh
                )
            } else {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
                ) {
                    itemsIndexed(
                        items = filteredChannels,
                        key = { index, _ -> channelItemKeys[index] }
                    ) { _, (channel, idx) ->
                        // 当前节目名按频道 URL 缓存：同一频道换位置时不重复取 EPG
                        val currentEpgTitle = remember(epgCacheVersion, channel.url) {
                            if (disableEpg) "" else getCachedCurrentProgram(idx)?.title ?: ""
                        }
                        TvChannelItem(
                            channel = channel,
                            channelIdx = idx,
                            isPlaying = idx == currentIdx,
                            isFavorite = !disableFavorite && favorites.contains(idx),
                            currentEpgTitle = currentEpgTitle,
                            hideChannelNum = hideChannelNum,
                            focusRequester = if (idx == currentIdx) currentChannelFocus else null,
                            onClick = { onChannelClick(idx) },
                            onFocusChange = { isFocused ->
                                if (isFocused) onFocusedChannelChange(idx)
                            }
                        )
                    }
                }
            }
        }
    }
}

/**
 * TV 端分组过滤器（横向滚动 chip 行）。
 * DPAD 左右切换分组，OK 选择分组。
 * "全部" chip 在最前，后面跟各分组名。
 *
 * 注意：此组件保留用于其他面板（如 ChannelsPanel），TvUnifiedPanel 已改用 GroupColumn 纵向显示分组。
 */
@Composable
private fun TvGroupFilterRow(
    groups: List<String>,
    selectedGroup: String,
    onGroupSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    LazyRow(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(6.dp)
    ) {
        // "全部" chip
        item(key = "__all__") {
            TvGroupChip(
                label = "全部",
                selected = selectedGroup.isEmpty(),
                onClick = { onGroupSelected("") }
            )
        }
        // 各分组 chip
        items(items = groups, key = { it }) { group ->
            TvGroupChip(
                label = group,
                selected = selectedGroup == group,
                onClick = { onGroupSelected(group) }
            )
        }
    }
}

@Composable
private fun TvGroupChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit
) {
    val bg = if (selected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.surfaceVariant
    val fg = if (selected) MaterialTheme.colorScheme.onSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 4.dp)
    ) {
        Text(
            text = label,
            color = fg,
            fontSize = 12.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
private fun TvChannelItem(
    channel: IptvChannel,
    channelIdx: Int,
    isPlaying: Boolean,
    isFavorite: Boolean,
    currentEpgTitle: String = "",
    hideChannelNum: Boolean = false,
    onClick: () -> Unit,
    onFocusChange: (Boolean) -> Unit = {},
    focusRequester: FocusRequester? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .onFocusChanged { onFocusChange(it.isFocused) }
            .tvFocusBorder()
            // 当前播放频道：主色橙红高亮（竖屏同款 12~16% 底），不再使用绿色实底
            .then(
                if (isPlaying) Modifier.background(
                    AptvAccent.copy(alpha = 0.16f),
                    RoundedCornerShape(10.dp)
                ) else Modifier
            )
            .clickable { onClick() }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 侧边栏风格：序号显示（圆角矩形背景）
        if (!hideChannelNum) {
            Surface(
                color = if (isPlaying) Color.White.copy(alpha = 0.2f) else ICON_BG,
                shape = RoundedCornerShape(4.dp)
            ) {
                Text(
                    text = "${channelIdx + 1}",
                    color = if (isPlaying) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
        }
        // 侧边栏风格：频道台标（logo）：有 logo 显示图片，无 logo 显示首字
        Box(
            modifier = Modifier.size(40.dp).clip(RoundedCornerShape(4.dp)).background(ICON_BG),
            contentAlignment = Alignment.Center
        ) {
            if (channel.logo.isNotEmpty()) {
                coil.compose.AsyncImage(
                    model = channel.logo,
                    contentDescription = channel.name,
                    modifier = Modifier.fillMaxSize().padding(3.dp),
                    contentScale = androidx.compose.ui.layout.ContentScale.Fit
                )
            } else {
                Text(
                    text = channel.name.take(1).ifEmpty { "·" },
                    color = Color.White,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
        Spacer(modifier = Modifier.width(12.dp))
        // 频道名 + 当前节目 + 分组
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = channel.name,
                color = if (isPlaying) Color.White else MaterialTheme.colorScheme.onSurface,
                fontSize = 17.sp,
                fontWeight = if (isPlaying) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            // 侧边栏风格：当前节目名，EPG为空时显示"精彩节目"
            Text(
                text = currentEpgTitle.ifEmpty { "精彩节目" },
                color = Color.White.copy(alpha = 0.6f),
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        // 收藏星标
        if (isFavorite) {
            Icon(
                imageVector = Icons.Default.Favorite,
                contentDescription = "收藏",
                tint = tvPalette.favorite,
                modifier = Modifier.size(14.dp)
            )
        }
    }
}

// =====================================================================
// 第二列（菜单模式）：主菜单
// =====================================================================

@Composable
private fun MenuColumn(
    viewModel: AppViewModel,
    currentIdx: Int,
    isFavorite: Boolean,
    multiViewActive: Boolean,
    currentMultiViewLayout: MultiViewLayout?,
    onEnterMultiView: (MultiViewLayout) -> Unit,
    onExitMultiView: () -> Unit,
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
    onClearChannelSettings: () -> Unit,
    onQuit: () -> Unit,
    modifier: Modifier = Modifier
) {
    val hasCurrentChannel = currentIdx >= 0
    val perChannelEnabled by viewModel.perChannelSettingsEnabled.collectAsState()
    val hasChannelSettings = remember(currentIdx) { currentIdx >= 0 && viewModel.hasChannelSettings(currentIdx) }

    val menuItems = remember(hasCurrentChannel, isFavorite, multiViewActive, currentMultiViewLayout, perChannelEnabled, hasChannelSettings) {
        buildList {
            // 快捷分组
            add(TvMenuItem("频道列表", "订阅 / 本地 / 收藏 / 历史", Icons.AutoMirrored.Filled.ListAlt, onChannels, highlight = true))
            add(TvMenuItem("节目单 EPG", "当前频道节目 / 日期切换 / 提醒", Icons.Default.CalendarMonth, onEpg, highlight = true))
            // 文件分组
            add(TvMenuItem("打开播放列表", "选择 M3U/M3U8 文件", Icons.Default.FileOpen, onOpenPlaylist))
            add(TvMenuItem("打开网络流", "输入订阅源 URL", Icons.Default.Link, onOpenUrl))
            add(TvMenuItem("打开本地文件", "播放设备视频/音频文件", Icons.Default.Movie, onOpenLocalVideo))
            add(TvMenuItem("订阅源管理", "添加 / 编辑 / 删除 M3U", Icons.Default.Web, onSources))
            add(TvMenuItem("EPG 订阅源", "管理节目单订阅地址", Icons.Default.CalendarMonth, onEpgSources))
            add(TvMenuItem("频道映射", "远程 + 用户映射管理", Icons.Default.SyncAlt, onMapping))
            // 播放分组
            add(TvMenuItem("字幕", "轨 / 显示 / 延迟 / 样式", Icons.Default.ClosedCaption, onSubtitle))
            add(TvMenuItem("视频", "图像 / 旋转 / 翻转 / 3D", Icons.Default.VideoSettings, onVideo))
            add(TvMenuItem("音频", "音轨 / 延迟 / EQ / 音调", Icons.Default.Equalizer, onAudio))
            add(TvMenuItem("播放", "速度 / 循环 / 随机 / AB", Icons.Default.PlayCircle, onPlayback))
            add(TvMenuItem("截图", "单张 / 连拍 / 含字幕", Icons.Default.ScreenshotMonitor, onScreenshot))
            add(TvMenuItem("A/V 同步", "数值 / 波形 / 延迟", Icons.Default.GraphicEq, onAvsync))
            add(TvMenuItem("网络增强", "Referer / Proxy / Headers", Icons.Default.Public, onNetwork))
            add(TvMenuItem("工具", "搜索 / 时间线 / 提醒 / 扫描", Icons.Default.Tune, onTools))
            add(TvMenuItem("视图", "视频比例 / OSD", Icons.Default.ViewInAr, onView))
            // 多画面分组（主画面 MPV，副画面 ExoPlayer）
            if (multiViewActive && currentMultiViewLayout != null) {
                // 已激活：在 DUAL → QUAD → NINE → DUAL 之间循环切换
                val otherLayout = when (currentMultiViewLayout) {
                    MultiViewLayout.DUAL -> MultiViewLayout.QUAD
                    MultiViewLayout.QUAD -> MultiViewLayout.NINE
                    MultiViewLayout.NINE -> MultiViewLayout.DUAL
                    else -> MultiViewLayout.DUAL
                }
                add(TvMenuItem(
                    "切换为${otherLayout.displayName}",
                    "当前 ${currentMultiViewLayout.displayName}",
                    Icons.Default.ViewModule,
                    { onEnterMultiView(otherLayout) }
                ))
                add(TvMenuItem("退出多画面", "退出多画面模式", Icons.AutoMirrored.Filled.ExitToApp, onExitMultiView, highlight = true))
            } else {
                add(TvMenuItem("双画面", "左右分屏", Icons.Default.ViewModule, { onEnterMultiView(MultiViewLayout.DUAL) }))
                add(TvMenuItem("四画面", "2x2 网格", Icons.Default.GridView, { onEnterMultiView(MultiViewLayout.QUAD) }))
                add(TvMenuItem("九画面", "3x3 网格", Icons.Default.GridView, { onEnterMultiView(MultiViewLayout.NINE) }))
            }
            // 系统分组
            add(TvMenuItem("设置", "VO / HWDEC / HDR", Icons.Default.Settings, onSettings))
            add(TvMenuItem("关于", "版本 / 功能特性", Icons.Default.Info, onAbout))
            add(TvMenuItem(
                if (isFavorite) "取消收藏" else "收藏",
                if (hasCurrentChannel) "当前频道" else "未选择频道",
                Icons.Default.Favorite,
                onToggleFavorite,
                highlight = hasCurrentChannel
            ))
            // 频道记忆（仅在开启时显示）
            if (perChannelEnabled && hasCurrentChannel) {
                if (hasChannelSettings) {
                    add(TvMenuItem(
                        "清除频道专属设置",
                        "恢复使用全局设置",
                        Icons.Default.Delete,
                        onClearChannelSettings,
                        highlight = true
                    ))
                }
            }
            add(TvMenuItem("退出", "关闭应用", Icons.AutoMirrored.Filled.ExitToApp, onQuit))
        }
    }

    Surface(
        color = Color.Transparent,
        modifier = modifier.fillMaxHeight()
    ) {
        // 玻璃质感由外层 GlassPanel（overlayDark 暗玻璃）提供，此处不再叠加实底 scrim
        Column(
            modifier = Modifier.fillMaxSize()
        ) {
            Text(
                text = "主菜单",
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp)
            )
            Divider(color = Color(0x20FFFFFF))

            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
            ) {
                itemsIndexed(
                    items = menuItems,
                    // 菜单项标题可能重复（如多个「打开文件」入口），用序号+标题保证 key 唯一，
                    // 否则 LazyColumn 会因重复 key 直接抛异常
                    key = { index, item -> "${index}_${item.title}" }
                ) { _, item ->
                    TvMenuItemRow(item)
                }
            }
        }
    }
}

private data class TvMenuItem(
    val title: String,
    val subtitle: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val onClick: () -> Unit,
    val highlight: Boolean = false
)

@Composable
private fun TvMenuItemRow(item: TvMenuItem) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .tvFocusBorder()
            .clickable { item.onClick() }
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = item.icon,
            contentDescription = null,
            tint = if (item.highlight) AptvAccent else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp)
        )
        Spacer(modifier = Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = item.title,
                color = if (item.highlight) AptvAccent else MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = if (item.highlight) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = item.subtitle,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

// =====================================================================
// 第四列：EPG 节目单
// =====================================================================

@Composable
private fun EpgListColumn(
    channel: IptvChannel,
    epg: List<IptvEpgProgram>,
    loading: Boolean,
    selectedProgram: IptvEpgProgram?,
    onProgramSelect: (IptvEpgProgram) -> Unit,
    onProgramClick: (IptvEpgProgram) -> Unit,
    isReminderSet: (IptvEpgProgram) -> Boolean,
    modifier: Modifier = Modifier
) {
    val listState = rememberLazyListState()

    // 每秒刷新 now，确保 LIVE 徽章和过去节目灰显随时间自动更新
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(5_000L)
            now = System.currentTimeMillis()
        }
    }

    // 自动滚动到当前直播节目（居中显示）
    LaunchedEffect(epg) {
        if (epg.isNotEmpty()) {
            val currentNow = System.currentTimeMillis()
            val currentProgIdx = epg.indexOfFirst { p ->
                p.startTs * 1000L <= currentNow && currentNow <= p.stopTs * 1000L
            }
            val targetIdx = if (currentProgIdx >= 0) currentProgIdx else 0
            if (targetIdx < epg.size) {
                // 第一阶段：先跳到目标项（无动画），强制列表布局更新
                listState.scrollToItem(targetIdx)
                // 第二阶段：等待布局完成后获取准确的视口和列表项尺寸
                kotlinx.coroutines.delay(50)
                val layoutInfo = listState.layoutInfo
                val viewportHeight = layoutInfo.viewportSize.height
                val itemHeight = layoutInfo.visibleItemsInfo.firstOrNull()?.size ?: 64
                val visibleCount = if (itemHeight > 0) viewportHeight / itemHeight else 5
                val centeredIdx = (targetIdx - visibleCount / 2).coerceAtLeast(0)
                listState.animateScrollToItem(centeredIdx)
            }
        }
    }

    Surface(
        color = Color.Transparent,
        modifier = modifier.fillMaxHeight()
    ) {
        Column(modifier = Modifier.fillMaxSize()) {

            when {
                loading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("加载节目单...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    }
                }
                epg.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("暂无节目单数据", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    }
                }
                else -> {
                    LazyColumn(
                        state = listState,
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
                    ) {
                        items(
                            items = epg,
                            key = { it.start + it.title }
                        ) { program ->
                            TvEpgItem(
                                program = program,
                                isCurrent = program.startTs * 1000L <= now && now <= program.stopTs * 1000L,
                                isPast = program.stopTs * 1000L < now,
                                isSelected = selectedProgram == program,
                                hasReminder = isReminderSet(program),
                                onClick = { onProgramClick(program) },
                                onSelect = { onProgramSelect(program) }
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TvEpgItem(
    program: IptvEpgProgram,
    isCurrent: Boolean,
    isPast: Boolean,
    isSelected: Boolean,
    hasReminder: Boolean,
    onClick: () -> Unit,
    onSelect: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            // 当前直播节目：主色橙红高亮底
            .then(
                if (isCurrent) Modifier.background(
                    AptvAccent.copy(alpha = 0.14f),
                    RoundedCornerShape(8.dp)
                ) else Modifier
            )
            .tvFocusBorder(8)
            .clickable {
                onSelect()
                onClick()
            }
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 左侧主色边条（当前节目）
        if (isCurrent) {
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .height(36.dp)
                    .background(AptvAccent)
            )
            Spacer(modifier = Modifier.width(8.dp))
        }

        Column(modifier = Modifier.weight(1f)) {
            // 时间行
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "${formatTime(program.start)} - ${formatTime(program.stop)}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp
                )
            }
            Spacer(modifier = Modifier.height(2.dp))
            // 节目标题
            Text(
                text = program.title,
                color = when {
                    isPast -> MaterialTheme.colorScheme.onSurfaceVariant
                    isCurrent -> AptvAccent
                    else -> MaterialTheme.colorScheme.onSurface
                },
                fontSize = 13.sp,
                fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        // 侧边栏风格：回看/直播/预约标签
        if (isPast) {
            Surface(color = ACCENT_CYAN.copy(alpha = 0.2f), shape = RoundedCornerShape(3.dp)) {
                Text("回看", color = ACCENT_CYAN, fontSize = 10.sp, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
            }
        } else if (isCurrent) {
            Surface(color = tvPalette.danger.copy(alpha = 0.2f), shape = RoundedCornerShape(3.dp)) {
                Text("直播", color = tvPalette.danger, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
            }
        } else {
            if (hasReminder) {
                Surface(color = AptvAccent.copy(alpha = 0.2f), shape = RoundedCornerShape(3.dp)) {
                    Text("已预约", color = AptvAccent, fontSize = 10.sp, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                }
            } else {
                Surface(color = Color(0x20FFFFFF), shape = RoundedCornerShape(3.dp)) {
                    Text("预约", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                }
            }
        }
    }
}


// =====================================================================
// 辅助函数
// =====================================================================

private fun formatTime(iso: String): String {
    if (iso.isEmpty()) return ""
    val ms = parseTimeToMs(iso)
    if (ms <= 0) return iso
    val cal = java.util.Calendar.getInstance().apply { timeInMillis = ms }
    return String.format(Locale.US, "%02d:%02d", cal.get(java.util.Calendar.HOUR_OF_DAY), cal.get(java.util.Calendar.MINUTE))
}

/** 解析 ISO 8601 时间字符串为毫秒时间戳（与 EpgPanel.parseTimeToMs 对齐） */
private fun parseTimeToMs(iso: String): Long {
    if (iso.isEmpty()) return 0
    return try {
        // 支持 "2026-07-02T12:30:00" 和 "20260702123000" 两种格式
        val cleaned = iso.replace(" ", "T").substringBefore("+").substringBefore("Z")
        if (cleaned.length >= 15 && !cleaned.contains("-")) {
            // "20260702123000" 格式
            val year = cleaned.substring(0, 4).toInt()
            val month = cleaned.substring(4, 6).toInt() - 1
            val day = cleaned.substring(6, 8).toInt()
            val hour = cleaned.substring(8, 10).toInt()
            val minute = cleaned.substring(10, 12).toInt()
            val second = if (cleaned.length >= 14) cleaned.substring(12, 14).toInt() else 0
            java.util.Calendar.getInstance().apply {
                clear()
                set(year, month, day, hour, minute, second)
            }.timeInMillis
        } else {
            // "2026-07-02T12:30:00" 格式
            val parts = cleaned.split("T")
            val dateParts = parts[0].split("-")
            val timeParts = if (parts.size > 1) parts[1].split(":") else listOf("0", "0", "0")
            java.util.Calendar.getInstance().apply {
                clear()
                set(
                    dateParts[0].toInt(),
                    dateParts[1].toInt() - 1,
                    dateParts[2].toInt(),
                    timeParts.getOrElse(0) { "0" }.toInt(),
                    timeParts.getOrElse(1) { "0" }.toInt(),
                    timeParts.getOrElse(2) { "0" }.substring(0, 2).toInt()
                )
            }.timeInMillis
        }
    } catch (e: Exception) {
        0
    }
}
