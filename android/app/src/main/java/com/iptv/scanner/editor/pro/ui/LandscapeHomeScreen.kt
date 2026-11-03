package com.iptv.scanner.editor.pro.ui

import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.rememberModalBottomSheetState
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.R
import com.iptv.scanner.editor.pro.ui.theme.LocalHazeState
import com.iptv.scanner.editor.pro.ui.theme.liquidGlassSource
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField
import dev.chrisbanes.haze.HazeState
import java.io.File

/**
 * TV/横屏首页（左右双屏，参考图1）：
 * - 顶部：迷你播放条（有播放时）——玻璃底座
 * - 内容区（频道 tab）：左 1/3 宫格频道卡片（复用竖屏 ChannelThumbnailPanel）
 *   + 右 2/3 EPG 时间轴（复用 EpgTimelinePanel）
 * - 收藏/工具/设置 tab：复用竖屏对应页面（画布模式自适应）
 * - 底部：竖屏同款玻璃悬浮 TAB 栏（PortraitBottomTabBar，复用 portraitTab 状态）
 *
 * 画布模式：整页统一渐变+光斑背景，玻璃卡片只做磨砂透出（与竖屏首页一致）。
 */
@Composable
internal fun LandscapeHomeScreen(
    viewModel: AppViewModel,
    playlistLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    videoLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    hazeState: HazeState
) {
    val liquidGlass by viewModel.liquidGlass.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .systemBarsPadding()
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            val fileLoaded2 by viewModel.mpv.fileLoaded.collectAsState()
            val currentCh by viewModel.currentChannel.collectAsState()
            val displayInfo by viewModel.channelDisplayInfo.collectAsState()
            val paused2 by viewModel.mpv.paused.collectAsState()
            val hasMini = fileLoaded2 && (currentCh != null || displayInfo.name.isNotEmpty())

            // 内容区（玻璃采样源挂固定内容层，不挂视频层）
            // Mini 播放条不再占布局行：改为顶部居中悬浮胶囊 overlay（悬浮在 0~48dp 带），
            // 内容（Crossfade）整体下移避让，胶囊不再遮挡 EPG 头部
            // 注意：必须 fillMaxWidth —— Column 子项默认 wrap 宽度，唯一子项 matchParentSize
            // 不贡献尺寸，缺 fillMaxWidth 会导致整个内容区宽度折叠为 0 而不可见
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
            ) {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .liquidGlassSource(hazeState)
                ) {
                    // 环境画布：深/浅主题渐变底 + 三色光斑（与竖屏首页一致）
                    val canvasDark = MaterialTheme.colorScheme.background.luminance() < 0.5f
                    Box(
                        modifier = Modifier
                            .matchParentSize()
                            .drawBehind {
                                drawRect(
                                    androidx.compose.ui.graphics.Brush.verticalGradient(
                                        if (canvasDark) listOf(
                                            androidx.compose.ui.graphics.Color(0xFF0B0F1A),
                                            androidx.compose.ui.graphics.Color(0xFF151B2C)
                                        ) else listOf(
                                            androidx.compose.ui.graphics.Color(0xFFE9EEF7),
                                            androidx.compose.ui.graphics.Color(0xFFF9FBFF)
                                        )
                                    )
                                )
                                val g = if (canvasDark) 0.32f else 0.24f
                                drawCircle(
                                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                                        listOf(androidx.compose.ui.graphics.Color(0x5B8CFF).copy(alpha = g), androidx.compose.ui.graphics.Color.Transparent)
                                    ),
                                    radius = size.width * 0.85f,
                                    center = androidx.compose.ui.geometry.Offset(size.width * 0.15f, size.height * 0.12f)
                                )
                                drawCircle(
                                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                                        listOf(androidx.compose.ui.graphics.Color(0xC084FC).copy(alpha = g * 0.85f), androidx.compose.ui.graphics.Color.Transparent)
                                    ),
                                    radius = size.width * 0.75f,
                                    center = androidx.compose.ui.geometry.Offset(size.width * 0.95f, size.height * 0.52f)
                                )
                                drawCircle(
                                    brush = androidx.compose.ui.graphics.Brush.radialGradient(
                                        listOf(androidx.compose.ui.graphics.Color(0x34D399).copy(alpha = g * 0.7f), androidx.compose.ui.graphics.Color.Transparent)
                                    ),
                                    radius = size.width * 0.7f,
                                    center = androidx.compose.ui.geometry.Offset(size.width * 0.2f, size.height * 0.95f)
                                )
                            }
                    ) {}

                    androidx.compose.runtime.CompositionLocalProvider(
                        LocalAptvStyle provides true,
                        LocalLiquidGlass provides liquidGlass,
                        com.iptv.scanner.editor.pro.ui.theme.LocalGlassOnCanvas provides true
                    ) {
                        val aptvScheme = MaterialTheme.colorScheme.copy(
                            primary = AptvAccent,
                            onPrimary = Color.White,
                            primaryContainer = AptvAccent.copy(alpha = 0.15f),
                            onPrimaryContainer = AptvAccent,
                            onSurfaceVariant = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.78f)
                        )
                        MaterialTheme(colorScheme = aptvScheme) {
                            val homeTab = viewModel.portraitTab.collectAsState().value
                            // EPG 范围随 tab 联动：收藏页→仅收藏，其他页→全部频道
                            // 切 tab 时清掉右侧详情面板（详情仅在同一 tab 内有效）
                            LaunchedEffect(homeTab) {
                                LandscapeSplitDetail.clear()
                                viewModel.setEpgTimelineRange(
                                    if (homeTab == PortraitTab.FAVORITES) EpgTimelineRange.FAVORITES
                                    else EpgTimelineRange.ALL
                                )
                            }
                            Crossfade(
                                targetState = homeTab,
                                animationSpec = tween(durationMillis = 200),
                                label = "landscapeHomeTab",
                                // 内容下移避让顶部悬浮 Mini 胶囊（48dp 高 + 4dp 间距）
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(top = if (hasMini) 54.dp else 0.dp)
                            ) { tab ->
                                when (tab) {
                                    PortraitTab.CHANNELS -> LandscapeChannelSplitContent(viewModel = viewModel)
                                    // 其余 3 个 tab 统一左右分屏：左 1/3 原页面内容 + 右 2/3 详情面板
                                    PortraitTab.FAVORITES -> LandscapeSplitScaffold(
                                        right = { EpgTimelinePanel(viewModel = viewModel, glassContainer = true) }
                                    ) {
                                        PortraitFavoritesScreen(
                                            viewModel = viewModel,
                                            playlistLauncher = playlistLauncher,
                                            videoLauncher = videoLauncher
                                        )
                                    }
                                    PortraitTab.TOOLS -> LandscapeSplitScaffold(
                                        right = { SplitDetailHost(viewModel = viewModel) }
                                    ) {
                                        PortraitToolsScreen(
                                            viewModel = viewModel,
                                            playlistLauncher = playlistLauncher,
                                            videoLauncher = videoLauncher
                                        )
                                    }
                                    PortraitTab.SETTINGS -> LandscapeSplitScaffold(
                                        right = { SplitDetailHost(viewModel = viewModel) }
                                    ) {
                                        PortraitSettingsContent(viewModel = viewModel)
                                    }
                                }
                            }
                        }
                    }
                }

                // 顶部居中悬浮 Mini 播放胶囊：按内容收缩宽度，overlay 不占布局行
                if (hasMini) {
                    androidx.compose.runtime.CompositionLocalProvider(LocalLiquidGlass provides liquidGlass) {
                        Box(modifier = Modifier.align(Alignment.TopCenter)) {
                            MiniPlayerBar(
                                viewModel = viewModel,
                                channelName = currentCh?.name ?: displayInfo.name,
                                channelLogo = currentCh?.logo ?: "",
                                groupName = currentCh?.group ?: "",
                                isPaused = paused2,
                                onClick = { viewModel.showPlayerScreen() },
                                onPlayPause = { viewModel.mpv.togglePause() },
                                floating = true
                            )
                        }
                    }
                }

                // 底部悬浮玻璃 TAB 栏：overlay 在内容区之上（不占布局行），真模糊取景下方内容
                androidx.compose.runtime.CompositionLocalProvider(LocalHazeState provides hazeState) {
                    PortraitBottomTabBar(
                        viewModel = viewModel,
                        modifier = Modifier.align(Alignment.BottomCenter),
                        centered = true
                    )
                }
            }
        }
    }
}

/**
 * 频道 tab 的左右分屏内容：左 1/3 宫格频道（分组入口+搜索+卡片）+ 右 2/3 EPG 时间轴。
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun LandscapeChannelSplitContent(viewModel: AppViewModel) {
    val channels by viewModel.channels.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val selectedGroup by viewModel.selectedGroup.collectAsState()
    val listSourceTab by viewModel.listSourceTab.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    val sources by viewModel.sources.collectAsState()
    val selectedSource by viewModel.selectedSource.collectAsState()
    val thumbnailPaths by viewModel.thumbnailPaths.collectAsState()
    val scanResults by viewModel.scanResults.collectAsState()
    val liveLatencyMap by viewModel.liveLatencyMap.collectAsState()
    val thumbnailEnabled by viewModel.thumbnailEnabled.collectAsState()
    val mediaInfoMap by viewModel.mediaInfoMap.collectAsState()

    // 预加载（缩略图/EPG/媒体信息，与竖屏列表页一致）
    LaunchedEffect(channels.size) {
        if (channels.isNotEmpty()) {
            viewModel.preloadEpgForAllChannels()
            viewModel.loadThumbnailPaths()
            viewModel.loadScanResultsCache()
            kotlinx.coroutines.delay(3000)
            viewModel.fetchMediaInfoForChannels(channels)
        }
    }

    val latencyMap = remember(scanResults, liveLatencyMap) {
        val merged = mutableMapOf<String, Int>()
        scanResults.forEach { if (it.latency > 0) merged[it.url] = it.latency }
        liveLatencyMap.forEach { (url, lat) -> if (lat > 0) merged[url] = lat }
        merged
    }

    // 数据源过滤 + 分组 + 搜索（与竖屏 PortraitListScreen 一致）
    val filteredChannels = remember(channels, listSourceTab, selectedSource) {
        when (listSourceTab) {
            ListSourceTab.SUBSCRIPTION -> {
                val sub = channels.filter { it.source.isNotEmpty() }
                if (selectedSource.isNotEmpty()) sub.filter { it.source == selectedSource } else sub
            }
            ListSourceTab.LOCAL -> channels.filter { it.source.isEmpty() }
        }
    }
    val groupList = remember(filteredChannels) {
        val groupOrder = filteredChannels.map { it.group.ifEmpty { "未分组" } }.distinct()
        val groupCounts = filteredChannels.groupingBy { it.group.ifEmpty { "未分组" } }.eachCount()
        groupOrder.map { it to (groupCounts[it] ?: 0) }
    }
    val displayChannels = remember(filteredChannels, selectedGroup) {
        if (selectedGroup.isEmpty()) filteredChannels
        else filteredChannels.filter { it.group == selectedGroup }
    }
    // TV 遥控器初始焦点：进入首页（或切分组/搜索导致列表重建）后请求到宫格第一张卡。
    // 延迟等待宫格首帧组合完成；列表为空时 FocusRequester 未附加，静默忽略。
    val firstCardFocus = remember { androidx.compose.ui.focus.FocusRequester() }
    LaunchedEffect(displayChannels.isNotEmpty()) {
        if (displayChannels.isNotEmpty()) {
            kotlinx.coroutines.delay(600)
            try {
                firstCardFocus.requestFocus()
            } catch (_: IllegalStateException) {
            }
        }
    }
    var searchQuery by remember { mutableStateOf("") }
    val searchedChannels = remember(displayChannels, searchQuery) {
        if (searchQuery.isBlank()) displayChannels
        else displayChannels.filter { it.name.contains(searchQuery.trim(), ignoreCase = true) }
    }

    Row(modifier = Modifier.fillMaxSize()) {
        // ==================== 左列（约1/3）：宫格频道 ====================
        Column(
            modifier = Modifier
                .weight(0.34f)
                .fillMaxHeight()
                .padding(start = 8.dp, top = 4.dp, bottom = 4.dp)
        ) {
            // 头部：分组入口 + 源切换 + 刷新（玻璃胶囊，图1左上角样式）
            var showGroupSheet by remember { mutableStateOf(false) }
            var showSourceSheet by remember { mutableStateOf(false) }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                AptvGlassChip(cornerRadius = 14.dp) {
                    Text(
                        text = if (selectedGroup.isEmpty()) "全部频道" else selectedGroup,
                        color = AptvAccent,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier
                            // TV 遥控器焦点高亮（clickable 外层，确保收到焦点事件）；小元素用更大倍数
                            .tvFocusBorder(cornerRadius = 10, focusedScale = 1.12f)
                            .clickable { showGroupSheet = true }
                            .padding(horizontal = 10.dp, vertical = 6.dp)
                    )
                }
                Spacer(modifier = Modifier.weight(1f))
                AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(36.dp).tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)) {
                    IconButton(onClick = { showSourceSheet = true }, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.Default.SwapHoriz, "切换订阅源", tint = AptvAccent, modifier = Modifier.size(18.dp))
                    }
                }
                Spacer(modifier = Modifier.width(6.dp))
                AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(36.dp).tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)) {
                    IconButton(onClick = { viewModel.loadChannels() }, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.Default.Refresh, "刷新频道", tint = AptvAccent, modifier = Modifier.size(18.dp))
                    }
                }
            }
            // 搜索框（玻璃底座）
            AptvGlassChip(
                cornerRadius = 10.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 4.dp)
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 0.dp)
                ) {
                    Icon(Icons.Default.Search, null, tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    TextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = { Text("搜索频道", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp) },
                        singleLine = true,
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color.Transparent,
                            unfocusedContainerColor = Color.Transparent,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            cursorColor = AptvAccent
                        ),
                        textStyle = TextStyle(color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp),
                        // TV 焦点导航：搜索框内按 UP/DOWN 直接移出焦点（否则方向键被输入框吞掉，遥控器切不出来）
                        modifier = Modifier.fillMaxWidth().tvTextField()
                    )
                }
            }

            // 宫格频道卡（复用竖屏缩略图宫格：2列玻璃卡）
            if (searchedChannels.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    // 订阅源仍在后台加载时显示加载提示，避免被误认为无频道
                    val status by viewModel.iptvStatus.collectAsState()
                    Text(
                        when {
                            searchQuery.isNotBlank() -> "无匹配频道"
                            status?.sourceLoading == true -> "正在加载订阅源..."
                            !status?.sourceWarning.isNullOrBlank() -> status?.sourceWarning ?: "暂无频道"
                            else -> "暂无频道"
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp
                    )
                }
            } else {
                ChannelThumbnailPanel(
                    displayChannels = searchedChannels,
                    channels = channels,
                    currentIdx = currentIdx,
                    fileLoaded = fileLoaded,
                    favorites = favorites,
                    thumbnailPaths = thumbnailPaths,
                    thumbnailEnabled = thumbnailEnabled,
                    viewModel = viewModel,
                    showDelete = false,
                    onDelete = {},
                    latencyMap = latencyMap,
                    groupList = groupList,
                    mediaInfoMap = mediaInfoMap,
                    // 横屏 TAB 悬浮于内容之上，底部预留让最后一张卡可滚出遮挡区
                    bottomContentPadding = 64.dp,
                    // TV 遥控器：首页组合后把初始焦点请求到宫格第一张卡，
                    // 方向键即可直接在卡片间导航（否则首焦点会落到顶栏按钮上）
                    firstCardFocusRequester = firstCardFocus
                )
            }

            // 分组选择弹窗（与竖屏同款静态玻璃底部弹窗）
            if (showGroupSheet) {
                val sheetState = rememberModalBottomSheetState()
                ModalBottomSheet(
                    onDismissRequest = { showGroupSheet = false },
                    sheetState = sheetState,
                    containerColor = Color.Transparent
                ) {
                    com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                        enabled = LocalLiquidGlass.current && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                        cornerRadius = 28.dp,
                        staticGlass = true,
                        fallbackColor = MaterialTheme.colorScheme.surface,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.78f))
                    ) {
                        androidx.compose.foundation.lazy.LazyColumn(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            item {
                                Text(
                                    "选择分组",
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.padding(vertical = 8.dp)
                                )
                            }
                            item {
                                Surface(
                                    color = if (selectedGroup.isEmpty()) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
                                    shape = RoundedCornerShape(8.dp),
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                        viewModel.setSelectedGroup("")
                                        showGroupSheet = false
                                    }
                                ) {
                                    Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text("全部频道", fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface)
                                        Text("${filteredChannels.size}", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                            items(groupList) { (group, count) ->
                                Surface(
                                    color = if (selectedGroup == group) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
                                    shape = RoundedCornerShape(8.dp),
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                        viewModel.setSelectedGroup(group)
                                        showGroupSheet = false
                                    }
                                ) {
                                    Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(group, fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                        Text("$count", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 订阅源切换弹窗
            if (showSourceSheet) {
                val sourceSheetState = rememberModalBottomSheetState()
                val sourceChannelCounts = remember(channels, sources) {
                    sources.associate { src -> src.url to channels.count { it.source == src.url } }
                }
                ModalBottomSheet(
                    onDismissRequest = { showSourceSheet = false },
                    sheetState = sourceSheetState,
                    containerColor = Color.Transparent
                ) {
                    com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                        enabled = LocalLiquidGlass.current && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                        cornerRadius = 28.dp,
                        staticGlass = true,
                        fallbackColor = MaterialTheme.colorScheme.surface,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.78f))
                    ) {
                        androidx.compose.foundation.lazy.LazyColumn(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            item {
                                Text(
                                    "切换源",
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.padding(vertical = 8.dp)
                                )
                            }
                            item {
                                Surface(
                                    color = if (selectedSource.isEmpty() && listSourceTab == ListSourceTab.SUBSCRIPTION) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
                                    shape = RoundedCornerShape(8.dp),
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                        viewModel.setListSourceTab(ListSourceTab.SUBSCRIPTION)
                                        viewModel.setSelectedSource("")
                                        showSourceSheet = false
                                    }
                                ) {
                                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp).fillMaxWidth()) {
                                        Text("全部订阅", fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface)
                                        Text("${channels.count { it.source.isNotEmpty() }} 个频道", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                            item {
                                Surface(
                                    color = if (listSourceTab == ListSourceTab.LOCAL) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
                                    shape = RoundedCornerShape(8.dp),
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                        viewModel.setListSourceTab(ListSourceTab.LOCAL)
                                        showSourceSheet = false
                                    }
                                ) {
                                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp).fillMaxWidth()) {
                                        Text("本地频道", fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface)
                                        Text("${channels.count { it.source.isEmpty() }} 个频道", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                            items(sources) { src ->
                                val name = src.name.ifEmpty { src.url.substringAfterLast("/").take(30) }
                                val count = sourceChannelCounts[src.url] ?: 0
                                Surface(
                                    color = if (selectedSource == src.url && listSourceTab == ListSourceTab.SUBSCRIPTION) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
                                    shape = RoundedCornerShape(8.dp),
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                        viewModel.setListSourceTab(ListSourceTab.SUBSCRIPTION)
                                        viewModel.setSelectedSource(src.url)
                                        showSourceSheet = false
                                    }
                                ) {
                                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp).fillMaxWidth()) {
                                        Text(name, fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text("$count 个频道", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ==================== 右列（约2/3）：EPG 时间轴 ====================
        Column(
            modifier = Modifier
                .weight(0.66f)
                .fillMaxHeight()
                .padding(start = 4.dp, end = 8.dp, top = 4.dp, bottom = 68.dp)
        ) {
            // 首次组合自动加载：竖屏流程由 toggleEpgTimelinePanel 触发首次加载，
            // 横屏首页为直接嵌入面板，不走 toggle，需在此自行触发（延迟等频道列表就绪）
            LaunchedEffect(Unit) {
                kotlinx.coroutines.delay(300)
                if (viewModel.epgTimelineRows.value.isEmpty()) {
                    viewModel.loadEpgTimeline()
                }
            }
            EpgTimelinePanel(viewModel = viewModel, glassContainer = true)
        }
    }
}

/**
 * 收藏/工具/设置 tab 的统一左右分屏骨架：
 * 左 1/3 放原竖屏页面内容（窄列自适应），右 2/3 放信息面板。
 * 右列底部预留悬浮 TAB 高度，避免最后一行被遮挡。
 */
@Composable
private fun LandscapeSplitScaffold(
    right: @Composable () -> Unit,
    left: @Composable () -> Unit
) {
    Row(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .weight(0.34f)
                .fillMaxHeight()
                .padding(start = 8.dp, top = 4.dp, bottom = 4.dp)
        ) {
            left()
        }
        Column(
            modifier = Modifier
                .weight(0.66f)
                .fillMaxHeight()
                .padding(start = 4.dp, end = 8.dp, top = 4.dp, bottom = 68.dp)
        ) {
            right()
        }
    }
}

/**
 * 工具/设置 tab 的右侧信息面板：系统概览（统计宫格 + 当前播放）。
 * 与竖屏工具页同款玻璃卡片风格（AptvGroupCard）。
 */
@Composable
private fun LandscapeSystemOverviewPanel(viewModel: AppViewModel) {
    val channels by viewModel.channels.collectAsState()
    val sources by viewModel.sources.collectAsState()
    val epgSources by viewModel.epgSources.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val currentCh by viewModel.currentChannel.collectAsState()
    val currentEpgList by viewModel.currentEpg.collectAsState()
    val currentIdxOverview by viewModel.currentIdx.collectAsState()
    val currentEpgProgram = remember(currentEpgList, currentIdxOverview) {
        viewModel.getCachedCurrentProgram(currentIdxOverview)
    }
    val groupCount = remember(channels) {
        channels.map { it.group.ifEmpty { "未分组" } }.distinct().size
    }

    // ==================== 运行日志（app.log 尾部，5 秒自动刷新） ====================
    val context = androidx.compose.ui.platform.LocalContext.current
    val appLogFile = remember(context) {
        // 与 Python 端 _setup_android_paths 的目录解析顺序一致：
        // /sdcard/ISEP/ → getExternalFilesDir()/ISEP/ → filesDir/ISEP/
        listOf(
            java.io.File("/sdcard/ISEP/app.log"),
            context.getExternalFilesDir(null)?.let { java.io.File(it, "ISEP/app.log") },
            java.io.File(context.filesDir, "ISEP/app.log")
        ).firstOrNull { it != null && it.exists() }
    }
    var logTick by remember { mutableStateOf(0) }
    var logText by remember { mutableStateOf("正在加载日志...") }
    LaunchedEffect(logTick) {
        while (true) {
            logText = readLogTail(appLogFile)
            kotlinx.coroutines.delay(5000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        Text(
            text = "系统概览",
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(start = 12.dp, top = 2.dp, bottom = 4.dp)
        )

        // 统计 2x2 宫格
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            Box(modifier = Modifier.weight(1f)) { OverviewStatCard("频道总数", "${channels.size}") }
            Box(modifier = Modifier.weight(1f)) { OverviewStatCard("分组数", "$groupCount") }
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            Box(modifier = Modifier.weight(1f)) { OverviewStatCard("收藏频道", "${favorites.size}") }
            Box(modifier = Modifier.weight(1f)) { OverviewStatCard("订阅源", "${sources.size}") }
        }

        Spacer(modifier = Modifier.height(6.dp))

        // 当前播放卡
        AptvGroupCard {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(RoundedCornerShape(9.dp))
                        .background(AptvAccent.copy(alpha = 0.90f)),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Filled.PlayArrow,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(19.dp)
                    )
                }
                Spacer(modifier = Modifier.width(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "正在播放",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                    Text(
                        text = currentCh?.name ?: "未在播放",
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (currentEpgProgram != null) {
                        Text(
                            text = currentEpgProgram.title,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }

        // ==================== 订阅源状态 ====================
        if (sources.isNotEmpty()) {
            AptvSectionHeader("订阅源状态")
            AptvGroupCard {
                Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                    sources.forEachIndexed { i, src ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            // 启停状态点：绿=启用 灰=停用
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(androidx.compose.foundation.shape.CircleShape)
                                    .background(
                                        if (src.enabled) Color(0xFF34D399)
                                        else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f)
                                    )
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = src.name.ifEmpty { "订阅源 ${i + 1}" },
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 13.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            Text(
                                text = if (src.enabled) "启用中" else "已停用",
                                color = if (src.enabled) Color(0xFF34D399)
                                        else MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        }
                        if (i != sources.lastIndex) {
                            HorizontalDivider(
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.12f),
                                thickness = 0.5.dp
                            )
                        }
                    }
                }
            }
        }

        // EPG 源
        if (epgSources.isNotEmpty()) {
            AptvSectionHeader("EPG 源")
            AptvGroupCard {
                Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                    epgSources.forEachIndexed { i, src ->
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(androidx.compose.foundation.shape.CircleShape)
                                    .background(Color(0xFF8CFFDA).copy(alpha = 0.85f))
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = src.name.ifEmpty { "EPG 源 ${i + 1}" },
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 13.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            Text(
                                text = "当前频道 ${currentEpgList.size} 节目",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        }
                        if (i != epgSources.lastIndex) {
                            HorizontalDivider(
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.12f),
                                thickness = 0.5.dp
                            )
                        }
                    }
                }
            }
        }

        // ==================== 运行日志 ====================
        AptvSectionHeader("运行日志")
        AptvGroupCard {
            Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "app.log 尾部 · 每 5 秒自动刷新",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        modifier = Modifier.weight(1f)
                    )
                    IconButton(onClick = { logTick++ }, modifier = Modifier.size(28.dp)) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "刷新日志",
                            tint = AptvAccent,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                }
                Text(
                    text = logText,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                    lineHeight = 14.sp,
                    fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 280.dp)
                        .verticalScroll(rememberScrollState())
                )
            }
        }
    }
}

/** 读取日志文件尾部（最多 32KB / 200 行），文件不存在或读取失败返回提示文本 */
private fun readLogTail(file: java.io.File?, maxBytes: Int = 32 * 1024, maxLines: Int = 200): String {
    if (file == null || !file.exists()) return "暂无日志（app.log 尚未生成）"
    return try {
        val raf = java.io.RandomAccessFile(file, "r")
        val len = raf.length()
        val start = (len - maxBytes).coerceAtLeast(0)
        raf.seek(start)
        val buf = ByteArray((len - start).toInt())
        raf.readFully(buf)
        raf.close()
        val text = String(buf, Charsets.UTF_8)
        val lines = text.lines()
        // 从文件中部截断时丢弃可能不完整的首行
        val body = if (start > 0 && lines.isNotEmpty()) lines.drop(1) else lines
        val tail = body.takeLast(maxLines)
        if (tail.isEmpty()) "暂无日志" else tail.joinToString("\n")
    } catch (e: Exception) {
        "读取日志失败: ${e.message}"
    }
}

/** 系统概览统计卡：数值 + 标签 */
@Composable
private fun OverviewStatCard(label: String, value: String) {
    AptvGroupCard {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 14.dp)
        ) {
            Text(
                text = value,
                color = AptvAccent,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = label,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp
            )
        }
    }
}

// -----------------------------------------------------------------
// 分屏详情路由（master-detail）
// -----------------------------------------------------------------

/**
 * 分屏详情宿主内渲染标记：面板据此省去整块玻璃底座（让 SettingsGroup 分组卡片直接呈现），
 * 二级工具项点击时路由到第三列（splitDetailPush）而非弹窗。
 */
internal val LocalSplitDetailEmbedded = androidx.compose.runtime.compositionLocalOf { false }

/**
 * 横屏分屏详情路由（栈结构）：设置/工具页点击左侧项 → 子面板内容渲染到右侧详情区，
 * 而不是弹中央 Dialog；竖屏仍走 PortraitPanelDialog 弹窗。
 * 二级入口（面板内工具项）push 到栈顶 → 宿主渲染三列（左列表 + 中一级面板 + 右子面板）。
 * 关闭时机：BACK（逐级 pop）/ 切 tab（homeTab effect 清栈）/
 * 面板内 X（open 流变 false，SplitDetailHost 联动移除该级及其后条目）。
 */
internal object LandscapeSplitDetail {
    class Entry(
        val panel: @Composable () -> Unit,
        /** 关联的 open 状态流（面板内 X → toggle → false → 宿主联动移除）；无则仅 BACK 关闭 */
        val openFlow: kotlinx.coroutines.flow.StateFlow<Boolean>?
    )
    val stack = androidx.compose.runtime.mutableStateListOf<Entry>()

    fun push(panel: @Composable () -> Unit, openFlow: kotlinx.coroutines.flow.StateFlow<Boolean>?) {
        stack.add(Entry(panel, openFlow))
    }

    /** 弹出栈顶（BACK 返回上一级） */
    fun pop() {
        if (stack.isNotEmpty()) stack.removeAt(stack.lastIndex)
    }

    /** 移除指定索引及其后的所有条目（面板 X 关闭联动） */
    fun removeFrom(index: Int) {
        while (stack.size > index) stack.removeAt(stack.lastIndex)
    }

    fun clear() {
        stack.clear()
    }
}

/**
 * 面板入口点击分流（一级入口）：横屏（真实横屏布局的首页）→ 清栈后压入右侧详情路由
 * （并确保 open=true，使面板内 X 的 toggle 能正确翻转为关闭）；竖屏/伪横屏 → 原弹窗 toggle。
 */
internal fun splitDetailOrToggle(
    isLandscape: Boolean,
    openFlow: kotlinx.coroutines.flow.StateFlow<Boolean>,
    panel: @Composable () -> Unit,
    toggle: () -> Unit
) {
    if (!isLandscape) {
        toggle()
        return
    }
    LandscapeSplitDetail.clear()
    LandscapeSplitDetail.push(panel, openFlow)
    if (!openFlow.value) toggle()
}

/**
 * 面板内二级入口（三列展开）：不清栈，把子面板压入第三列。
 * 子面板 open 流当前为 false 时先调 ensureOpen 置 true，保证 X 关闭联动正确。
 */
internal fun splitDetailPush(
    openFlow: kotlinx.coroutines.flow.StateFlow<Boolean>,
    panel: @Composable () -> Unit,
    ensureOpen: () -> Unit
) {
    LandscapeSplitDetail.push(panel, openFlow)
    if (!openFlow.value) ensureOpen()
}

/**
 * 设置/工具页右侧详情宿主：栈空显示系统概览；
 * 1 级详情渲染单列；≥2 级渲染三列（中列 = 前一级面板，右列 = 最后压入的子面板）。
 * 面板内 X 关闭（open→false）时自动移除该级及其后条目，回落概览。
 */
@Composable
private fun SplitDetailHost(viewModel: AppViewModel) {
    val stack = LandscapeSplitDetail.stack
    // open 联动：任一级面板内 X 关闭（open→false）→ 移除该级及其后的所有条目
    stack.forEachIndexed { idx, entry ->
        val flow = entry.openFlow ?: return@forEachIndexed
        val open by flow.collectAsState()
        androidx.compose.runtime.LaunchedEffect(open, idx, stack.size) {
            if (!open) LandscapeSplitDetail.removeFrom(idx)
        }
    }
    if (stack.isEmpty()) {
        LandscapeSystemOverviewPanel(viewModel = viewModel)
        return
    }
    // 不包整块玻璃底座：面板内 SettingsGroup 在 APTV 作用域下已自动分组卡片化，
    // 整块玻璃会把卡片底衬盖平（观感 = 一大块板），此处透出画布让分组卡片「一块一块」呈现
    androidx.compose.runtime.CompositionLocalProvider(LocalSplitDetailEmbedded provides true) {
        if (stack.size == 1) {
            Box(modifier = Modifier.fillMaxSize()) { stack[0].panel() }
        } else {
            // 三列：中列 = 前一级面板（点击二级项的面板），右列 = 最后压入的子面板
            Row(modifier = Modifier.fillMaxSize()) {
                Box(modifier = Modifier.weight(0.46f).fillMaxHeight()) {
                    stack[stack.size - 2].panel()
                }
                Spacer(modifier = Modifier.width(10.dp))
                Box(modifier = Modifier.weight(0.54f).fillMaxHeight()) {
                    stack.last().panel()
                }
            }
        }
    }
}
