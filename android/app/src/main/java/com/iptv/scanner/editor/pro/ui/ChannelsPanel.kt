package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.runtime.collectAsState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.IptvChannel
import com.iptv.scanner.editor.pro.player.ProgressHelper
import com.iptv.scanner.editor.pro.ui.ChannelTab
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField

/**
 * 频道列表面板：4 个 tab + 搜索 + 分组过滤 + LazyColumn。
 *
 * 与 PC 端 panelChannels 对齐：
 * - 4 个 tab：订阅/本地/收藏/历史
 * - 搜索框：输入即过滤（name/group 包含关键字）
 * - 分组过滤器（仅 SUB/LOCAL tab 显示）
 * - 列表项：圆点 + 名称 + 分组 meta + 当前播放高亮
 * - 点击列表项 → playChannel(idx)
 *
 * 布局：右侧抽屉（380dp 宽），双列（左分组 + 右频道）。
 * TV 模式也可从统一面板菜单进入此面板（DPAD 焦点导航）。
 */
@Composable
fun ChannelsPanel(viewModel: AppViewModel, inline: Boolean = false, compact: Boolean = false, noSearch: Boolean = false) {
    val tab by viewModel.channelsTab.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()
    val selectedGroup by viewModel.selectedGroup.collectAsState()
    val allGroups by viewModel.groups.collectAsState()
    val channels by viewModel.channels.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val history by viewModel.history.collectAsState()

    // 订阅源加载态：服务端状态 + 本地重载标志，任一为真即视为加载中
    val iptvStatus by viewModel.iptvStatus.collectAsState()
    val localSourceLoading by viewModel.sourceLoading.collectAsState()

    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(50)
        kotlin.runCatching { closeFocusRequester.requestFocus() }
    }

    // 根据 tab 过滤分组（与 TvUnifiedPanel 对齐）：
    // - LOCAL tab：只显示本地频道的分组，避免显示订阅分组误导用户
    // - SUB tab：显示所有分组
    val groups = remember(allGroups, channels, tab) {
        if (tab == ChannelTab.LOCAL) {
            channels
                .filter { it.source.isEmpty() || ProgressHelper.isLocalFile(it.url) }
                .map { it.group }
                .filter { it.isNotEmpty() }
                .distinct()
        } else {
            allGroups
        }
    }

    val showGroups = (tab == ChannelTab.SUB || tab == ChannelTab.LOCAL) && groups.isNotEmpty()

    val filteredChannels = remember(tab, searchQuery, selectedGroup, channels, favorites, history) {
        viewModel.getFilteredChannels()
    }

    // compact 模式：横屏抽屉，宽度 1/4，无标题无搜索
    // inline 模式：竖屏内联，填满父容器，无标题有搜索
    // 默认模式：全屏抽屉，有标题有搜索
    val surfaceModifier = when {
        compact -> Modifier
            .fillMaxHeight()
            .fillMaxWidth(0.25f)
        inline -> Modifier.fillMaxSize()
        else -> Modifier
            .fillMaxHeight()
            .fillMaxWidth(0.92f)
            .widthIn(max = 380.dp)
    }

    Surface(
        color = MaterialTheme.colorScheme.surface,
        modifier = surfaceModifier
    ) {
        Column(modifier = Modifier.fillMaxSize().then(if (inline || compact) Modifier else Modifier.systemBarsPadding())) {
            // -----------------------------------------------------------------
            // 标题栏：compact 和 inline 模式不显示标题
            // -----------------------------------------------------------------
            if (!inline && !compact) {
                PanelHeader(
                    title = "频道列表",
                    subtitle = "${channels.size} 个频道",
                    onClose = { viewModel.toggleChannelsPanel() },
                    closeFocusRequester = closeFocusRequester
                )
            }

            // -----------------------------------------------------------------
            // 5 个 Tab
            // -----------------------------------------------------------------
            ChannelTabsRow(
                currentTab = tab,
                onTabSelected = { viewModel.setChannelsTab(it) }
            )

            // -----------------------------------------------------------------
            // 搜索框（compact 和 noSearch 模式不显示）
            // -----------------------------------------------------------------
            if (!compact && !noSearch) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { viewModel.setSearchQuery(it) },
                    placeholder = { Text("搜索频道...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp) },
                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant) },
                    trailingIcon = {
                        if (searchQuery.isNotEmpty()) {
                            IconButton(onClick = { viewModel.setSearchQuery("") }, modifier = Modifier.tvFocusBorder()) {
                                Icon(Icons.Default.Close, contentDescription = "清空", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 6.dp)
                        .tvTextField(),
                    shape = RoundedCornerShape(8.dp),
                    singleLine = true
                )
            }

            Divider(color = MaterialTheme.colorScheme.surfaceVariant)

            // -----------------------------------------------------------------
            // 主体区域：左列分组 + 右列频道（双列布局）
            // 收藏/历史 tab 无分组数据，直接全宽显示频道列表
            // -----------------------------------------------------------------
            if (showGroups) {
                Row(modifier = Modifier.fillMaxSize()) {
                    // 左列：分组列表
                    GroupListColumn(
                        groups = groups,
                        selectedGroup = selectedGroup,
                        onGroupSelected = { viewModel.setSelectedGroup(it) },
                        modifier = Modifier.weight(0.38f)
                    )

                    // 分隔线
                    Box(
                        modifier = Modifier
                            .fillMaxHeight()
                            .width(1.dp)
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                    )

                    // 右列：频道列表
                    ChannelListContent(
                        filteredChannels = filteredChannels,
                        currentIdx = currentIdx,
                        favorites = favorites,
                        tab = tab,
                        selectedGroup = selectedGroup,
                        sourceLoading = iptvStatus?.sourceLoading == true || localSourceLoading,
                        sourceWarning = iptvStatus?.sourceWarning.orEmpty(),
                        onAddSource = { viewModel.toggleSourceManager() },
                        onRefresh = { viewModel.reloadSources() },
                        onPlay = { viewModel.playChannel(it) },
                        modifier = Modifier.weight(0.62f)
                    )
                }
            } else {
                ChannelListContent(
                    filteredChannels = filteredChannels,
                    currentIdx = currentIdx,
                    favorites = favorites,
                    tab = tab,
                    selectedGroup = selectedGroup,
                    sourceLoading = iptvStatus?.sourceLoading == true || localSourceLoading,
                    sourceWarning = iptvStatus?.sourceWarning.orEmpty(),
                    onAddSource = { viewModel.toggleSourceManager() },
                    onRefresh = { viewModel.reloadSources() },
                    onPlay = { viewModel.playChannel(it) }
                )
            }
        }
    }
}

/**
 * 频道列表分页加载常量。
 *
 * 频道列表超过 PAGINATION_THRESHOLD 条时启用分页加载：
 * - 初始加载 INITIAL_LOAD 条
 * - 滚动到底部时预取 PREFETCH_SIZE 条
 * - 平滑增量加载，避免一次性渲染数千项导致卡顿
 */
private const val PAGINATION_THRESHOLD = 1000
private const val INITIAL_LOAD = 200
private const val PREFETCH_SIZE = 100

/**
 * 频道列表内容（空态 + LazyColumn）。
 *
 * 分页加载优化：频道超过 1000 条时，初始只渲染 200 条，
 * 滚动到底部时预取下一批 100 条，避免一次性渲染全部项。
 */
@Composable
private fun ChannelListContent(
    filteredChannels: List<Pair<IptvChannel, Int>>,
    currentIdx: Int,
    favorites: Set<Int>,
    tab: ChannelTab,
    selectedGroup: String,
    sourceLoading: Boolean,
    sourceWarning: String,
    onAddSource: () -> Unit,
    onRefresh: () -> Unit,
    onPlay: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    if (filteredChannels.isEmpty()) {
        ChannelEmptyState(
            tab = tab,
            loading = sourceLoading,
            sourceWarning = sourceWarning,
            groupName = if (tab == ChannelTab.SUB || tab == ChannelTab.LOCAL) selectedGroup else "",
            onAddSource = onAddSource,
            onRefresh = onRefresh,
            modifier = modifier
        )
    } else {
        // 分页加载：频道数超过阈值时启用增量加载
        val usePagination = filteredChannels.size > PAGINATION_THRESHOLD
        var visibleCount by remember(filteredChannels.size) {
            mutableStateOf(if (usePagination) INITIAL_LOAD else filteredChannels.size)
        }
        val listState = rememberLazyListState()

        // 监听滚动位置，接近底部时加载更多
        LaunchedEffect(listState, filteredChannels.size) {
            snapshotFlow {
                val lastVisible = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
                lastVisible >= visibleCount - 5
            }.collect { nearEnd ->
                if (nearEnd && visibleCount < filteredChannels.size) {
                    // 加载下一批
                    visibleCount = minOf(visibleCount + PREFETCH_SIZE, filteredChannels.size)
                }
            }
        }

        val displayedChannels = if (usePagination) {
            filteredChannels.take(visibleCount)
        } else {
            filteredChannels
        }

        // 列表 key：以频道 URL 作为稳定身份，分页追加/过滤切换时不会错位
        val channelItemKeys = remember(displayedChannels) { buildChannelItemKeys(displayedChannels) }

        LazyColumn(
            state = if (usePagination) listState else rememberLazyListState(),
            modifier = modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 4.dp)
        ) {
            itemsIndexed(
                items = displayedChannels,
                key = { index, _ -> channelItemKeys[index] }
            ) { _, (channel, idx) ->
                ChannelListItem(
                    channel = channel,
                    isPlaying = idx == currentIdx,
                    isFavorite = favorites.contains(idx),
                    showGroupMeta = tab == ChannelTab.SUB || tab == ChannelTab.LOCAL,
                    onClick = { onPlay(idx) }
                )
            }
            // 分页加载指示器
            if (usePagination && visibleCount < filteredChannels.size) {
                item {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            strokeWidth = 2.dp
                        )
                    }
                }
            }
        }
    }
}

/**
 * 左列：分组纵向滚动列表。
 * 使用 tvFocusBorder 确保 TV 模式下 DPAD 焦点可见。
 */
@Composable
private fun GroupListColumn(
    groups: List<String>,
    selectedGroup: String,
    onGroupSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val allItems = remember(groups) { listOf("") + groups }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = modifier.fillMaxHeight()
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 4.dp)
        ) {
            items(allItems, key = { it }) { group ->
                val isSelected = selectedGroup == group
                val label = if (group.isEmpty()) "全部" else group
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .tvFocusBorder()
                        .clickable { onGroupSelected(group) }
                        .padding(horizontal = 10.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // 左侧选中指示条
                    Box(
                        modifier = Modifier
                            .width(3.dp)
                            .height(16.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(if (isSelected) MaterialTheme.colorScheme.primary else Color.Transparent)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = label,
                        color = if (isSelected) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

/**
 * 面板标题栏（统一组件）。
 *
 * @param closeFocusRequester 可选的 FocusRequester，绑定到关闭按钮。
 *        TV 模式下面板打开时需要初始焦点，否则 DPAD 无法操作。
 *        传入时关闭按钮会绑定此 requester，调用方用 LaunchedEffect 请求焦点。
 */
@Composable
fun PanelHeader(
    title: String,
    subtitle: String = "",
    onClose: () -> Unit,
    closeFocusRequester: FocusRequester? = null
) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.SemiBold
                )
                if (subtitle.isNotEmpty()) {
                    Text(
                        text = subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            IconButton(
                onClick = onClose,
                modifier = Modifier
                    .tvFocusBorder()
                    .then(
                        if (closeFocusRequester != null) Modifier.focusRequester(closeFocusRequester)
                        else Modifier
                    )
            ) {
                Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
            }
        }
    }
}

/**
 * 4 个 Tab 行（订阅/本地/收藏/历史）。
 */
@Composable
fun ChannelTabsRow(
    currentTab: ChannelTab,
    onTabSelected: (ChannelTab) -> Unit
) {
    val tabs = listOf(
        ChannelTab.SUB to "订阅",
        ChannelTab.LOCAL to "本地",
        ChannelTab.FAV to "收藏",
        ChannelTab.HIST to "历史"
    )
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            tabs.forEach { (tab, label) ->
                val isSelected = currentTab == tab
                FilterChip(
                    selected = isSelected,
                    onClick = { onTabSelected(tab) },
                    label = { Text(label, fontSize = 12.sp) },
                    modifier = Modifier.weight(1f),
                    colors = androidx.compose.material3.FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primary,
                        selectedLabelColor = MaterialTheme.colorScheme.onSurface,
                        containerColor = Color.Transparent,
                        labelColor = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                )
            }
        }
    }
}

/**
 * 频道列表项。
 */
@Composable
private fun ChannelListItem(
    channel: IptvChannel,
    isPlaying: Boolean,
    isFavorite: Boolean,
    showGroupMeta: Boolean,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .tvFocusBorder()
            .clickable { onClick() }
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 圆点（playing 时高亮蓝色，否则灰色）
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(if (isPlaying) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline)
        )

        Spacer(modifier = Modifier.width(10.dp))

        // 频道名 + 分组 meta
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = channel.name,
                color = if (isPlaying) MaterialTheme.colorScheme.secondary else MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = if (isPlaying) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (showGroupMeta && channel.group.isNotEmpty()) {
                Text(
                    text = channel.group,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }

        // 收藏标记
        if (isFavorite) {
            Spacer(modifier = Modifier.width(8.dp))
            Text("★", color = MaterialTheme.colorScheme.tertiary, fontSize = 12.sp)
        }
    }
}


