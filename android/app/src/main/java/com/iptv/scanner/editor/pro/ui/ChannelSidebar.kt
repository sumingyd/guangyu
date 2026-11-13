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
import androidx.compose.material.icons.filled.PictureInPicture
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material.icons.filled.VolumeOff
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
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
import com.iptv.scanner.editor.pro.ui.theme.PlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField
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
import androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import com.iptv.scanner.editor.pro.player.CatchupHelper
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
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
 * 频道卡片徽章黑名单：容器格式（TS/MP4/MKV 等）与传输协议（HTTP/UDP 等）
 * 对用户没有选择价值，不作为徽章显示；仅保留分辨率/帧率/码率等有价值的标识
 */
private val badgeDisplayBlocklist = setOf(
    "TS", "MP4", "MKV", "AVI", "FLV", "WEBM",
    "HTTP", "HTTPS", "RTSP", "UDP", "RTP", "RTMP"
)

/**
 * 竖屏列表页：APTV风格全屏布局，支持分组底部弹窗、订阅源选择、列表/宫格模式
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun PortraitListScreen(
    viewModel: AppViewModel,
    playlistLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    videoLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>
) {
    val channels by viewModel.channels.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val selectedGroup by viewModel.selectedGroup.collectAsState()
    val listSourceTab by viewModel.listSourceTab.collectAsState()
    val viewMode by viewModel.listViewMode.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    val history by viewModel.history.collectAsState()
    val sources by viewModel.sources.collectAsState()
    val selectedSource by viewModel.selectedSource.collectAsState()
    val thumbnailPaths by viewModel.thumbnailPaths.collectAsState()
    val scanResults by viewModel.scanResults.collectAsState()

    // 订阅源加载态：服务端状态 + 本地重载标志，任一为真即视为加载中。
    // 空态分支必须依赖真实加载状态，不能用「列表为空」反推。
    val iptvStatus by viewModel.iptvStatus.collectAsState()
    val localSourceLoading by viewModel.sourceLoading.collectAsState()

    // 延迟映射：url -> latency(ms)，优先使用实时测量值，回退到扫描结果
    val liveLatencyMap by viewModel.liveLatencyMap.collectAsState()
    val latencyMap = remember(scanResults, liveLatencyMap) {
        val merged = mutableMapOf<String, Int>()
        scanResults.forEach { if (it.latency > 0) merged[it.url] = it.latency }
        liveLatencyMap.forEach { (url, lat) -> if (lat > 0) merged[url] = lat }
        merged
    }

    val thumbnailEnabled by viewModel.thumbnailEnabled.collectAsState()
    val thumbnailGenProgress by viewModel.thumbnailGenProgress.collectAsState()
    val mediaInfoMap by viewModel.mediaInfoMap.collectAsState()

    // 预加载 EPG 和缩略图
    LaunchedEffect(channels.size) {
        if (channels.isNotEmpty()) {
            viewModel.preloadEpgForAllChannels()
            viewModel.loadThumbnailPaths()
            viewModel.loadScanResultsCache()
            kotlinx.coroutines.delay(3000)
            viewModel.fetchMediaInfoForChannels(channels)
            kotlinx.coroutines.delay(15000)
            viewModel.preloadEpgForAllChannels()
        }
    }

    // 根据数据源 + 订阅源过滤频道
    val filteredChannels = remember(channels, listSourceTab, selectedSource) {
        when (listSourceTab) {
            ListSourceTab.SUBSCRIPTION -> {
                val sub = channels.filter { it.source.isNotEmpty() }
                if (selectedSource.isNotEmpty()) sub.filter { it.source == selectedSource } else sub
            }
            ListSourceTab.LOCAL -> channels.filter { it.source.isEmpty() }
        }
    }

    // 分组（含频道数量，按 M3U 首次出现顺序排列）
    val groupList = remember(filteredChannels) {
        val groupOrder = filteredChannels.map { it.group.ifEmpty { "未分组" } }.distinct()
        val groupCounts = filteredChannels.groupingBy { it.group.ifEmpty { "未分组" } }.eachCount()
        groupOrder.map { it to (groupCounts[it] ?: 0) }
    }

    // 当前分组下的频道
    val displayChannels = remember(filteredChannels, selectedGroup) {
        if (selectedGroup.isEmpty()) filteredChannels
        else filteredChannels.filter { it.group == selectedGroup }
    }

    // APTV 风格搜索过滤（列表页顶部搜索框）
    var searchQuery by remember { mutableStateOf("") }
    val searchedChannels = remember(displayChannels, searchQuery) {
        if (searchQuery.isBlank()) displayChannels
        else displayChannels.filter { it.name.contains(searchQuery.trim(), ignoreCase = true) }
    }


    // 本地文件历史
    val localHistory = remember(history, channels) {
        history.mapNotNull { idx -> channels.getOrNull(idx) }
            .filter { it.source.isEmpty() }
            .take(20)
    }

    // 订阅源名称映射
    val sourceDisplayName = remember(sources, selectedSource) {
        if (selectedSource.isEmpty()) "全部订阅"
        else sources.find { it.url == selectedSource }?.name?.ifEmpty { selectedSource.substringAfterLast("/").take(20) }
            ?: selectedSource.substringAfterLast("/").take(20)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
        // 不铺不透明底：透出内容区的环境画布
    ) {
        // ---- APTV 头部：分组入口(左,点击弹分组) + 源切换/刷新(右) / 大标题 / 搜索框 ----
        var showGroupSheet by remember { mutableStateOf(false) }
        var showSourceSheet by remember { mutableStateOf(false) }
        var viewMenuExpanded by remember { mutableStateOf(false) }
        // 搜索关键词只有函数级 searchQuery 一份：头部输入框直接写入它，
        // 列表过滤与空态判断都读同一份状态。
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左侧：分组入口（APTV 用源名行做分组切换）—— 玻璃胶囊（包裹内容宽度，不撑满整行）
            AptvGlassChip(cornerRadius = 14.dp) {
                Text(
                    text = if (selectedGroup.isEmpty()) "全部分组" else selectedGroup,
                    color = tvPalette.accentText,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier
                        .clickable { showGroupSheet = true }
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                )
            }
            Spacer(modifier = Modifier.weight(1f))
            // 右侧：源切换（多源切换，对齐 APTV 配置切换）—— 玻璃圆形按钮
            AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(40.dp)) {
                IconButton(onClick = { showSourceSheet = true }, modifier = Modifier.size(40.dp)) {
                    Icon(
                        imageVector = Icons.Default.SwapHoriz,
                        contentDescription = "切换订阅源",
                        tint = AptvAccent,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.width(6.dp))
            // 右侧：视图切换 + 预览图菜单
            AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(40.dp)) {
                IconButton(
                    onClick = {
                        viewModel.setListViewMode(
                            if (viewMode == ListViewMode.LIST) ListViewMode.THUMBNAIL
                            else ListViewMode.LIST
                        )
                    },
                    modifier = Modifier.size(40.dp)
                ) {
                    Icon(
                        imageVector = if (viewMode == ListViewMode.LIST) Icons.Default.GridView else Icons.Default.ViewList,
                        contentDescription = "切换视图",
                        tint = AptvAccent,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.width(2.dp))
            AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(40.dp)) {
                IconButton(onClick = { viewMenuExpanded = true }, modifier = Modifier.size(40.dp)) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "预览图菜单",
                        tint = AptvAccent,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.width(6.dp))
            AptvGlassChip(cornerRadius = 20.dp, modifier = Modifier.size(40.dp)) {
                IconButton(onClick = { viewModel.loadChannels() }, modifier = Modifier.size(40.dp)) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "刷新频道",
                        tint = AptvAccent,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }
        }
        Text(
            text = if (listSourceTab == ListSourceTab.LOCAL) "本地频道"
                   else if (selectedSource.isNotEmpty()) sourceDisplayName
                   else "全部频道",
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 26.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 16.dp)
        )
        // 搜索框：玻璃底座（磨砂+描边），关闭时回落原 surfaceVariant 实底
        AptvGlassChip(
            cornerRadius = 10.dp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 2.dp)
            ) {
                Icon(
                    Icons.Default.Search,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                androidx.compose.material3.TextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    placeholder = {
                        Text("搜索频道", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                    },
                    singleLine = true,
                    colors = androidx.compose.material3.TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = AptvAccent
                    ),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 14.sp
                    ),
                    // TV 焦点导航：搜索框内 UP/DOWN 直接移出焦点，避免遥控器被输入框吞键
                    modifier = Modifier.fillMaxWidth().tvTextField()
                )
            }
        }
        // 缩略图生成进度提示已移除（后台静默执行）

        // 分组选择底部弹窗
        if (showGroupSheet) {
            val sheetState = rememberModalBottomSheetState()
            ModalBottomSheet(
                onDismissRequest = { showGroupSheet = false },
                sheetState = sheetState,
                containerColor = Color.Transparent
            ) {
                // 底部弹窗玻璃化：独立窗口走静态玻璃（磨砂+光斑+描边）
                com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                    enabled = com.iptv.scanner.editor.pro.ui.LocalLiquidGlass.current &&
                        com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                    cornerRadius = 28.dp,
                    staticGlass = true,
                    fallbackColor = MaterialTheme.colorScheme.surface,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.78f))
                ) {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    item {
                        Text(
                            text = "选择分组",
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
                            Row(
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
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
                            Row(
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(group, fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                Text("$count", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                }
            }
        }

        // 订阅源选择底部弹窗
        if (showSourceSheet) {
            val sourceSheetState = rememberModalBottomSheetState()
            val sourceChannelCounts = remember(channels, sources) {
                sources.associate { src ->
                    src.url to channels.count { it.source == src.url }
                }
            }
            ModalBottomSheet(
                onDismissRequest = { showSourceSheet = false },
                sheetState = sourceSheetState,
                containerColor = Color.Transparent
            ) {
                // 底部弹窗玻璃化：独立窗口走静态玻璃（磨砂+光斑+描边）
                com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                    enabled = com.iptv.scanner.editor.pro.ui.LocalLiquidGlass.current &&
                        com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                    cornerRadius = 28.dp,
                    staticGlass = true,
                    fallbackColor = MaterialTheme.colorScheme.surface,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.78f))
                ) {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    item {
                        Text(
                            text = "切换源",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    }
                    item {
                        // 本地频道入口（与 APTV 的"本地配置"对齐）
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
                    item {
                        Surface(
                            color = if (selectedSource.isEmpty()) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
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
                    items(sources) { src ->
                        val name = src.name.ifEmpty { src.url.substringAfterLast("/").take(30) }
                        val count = sourceChannelCounts[src.url] ?: 0
                        Surface(
                            color = if (selectedSource == src.url) AptvAccent.copy(alpha = 0.12f) else Color.Transparent,
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

        // 视图菜单底部弹窗（iOS APTV 风格）
        if (viewMenuExpanded) {
            val viewSheetState = rememberModalBottomSheetState()
            ModalBottomSheet(
                onDismissRequest = { viewMenuExpanded = false },
                sheetState = viewSheetState,
                containerColor = Color.Transparent
            ) {
                // 底部弹窗玻璃化：独立窗口走静态玻璃（磨砂+光斑+描边）
                com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                    enabled = com.iptv.scanner.editor.pro.ui.LocalLiquidGlass.current &&
                        com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                    cornerRadius = 28.dp,
                    staticGlass = true,
                    fallbackColor = MaterialTheme.colorScheme.surface,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.78f))
                ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "预览图管理",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                    val menuItems = mutableListOf<Pair<String, () -> Unit>>()
                    menuItems.add((if (thumbnailGenProgress != null) "停止获取预览图" else "开始获取预览图") to {
                        if (thumbnailGenProgress == null) {
                            viewModel.setThumbnailEnabled(true)
                            viewModel.generateMissingThumbnails(displayChannels)
                        } else {
                            viewModel.setThumbnailEnabled(false)
                        }
                    })
                    menuItems.add("刷新预览图" to {
                        viewModel.setThumbnailEnabled(true)
                        viewModel.refreshMissingThumbnails()
                    })
                    menuItems.add("刷新无预览频道" to {
                        viewModel.setThumbnailEnabled(true)
                        viewModel.generateMissingThumbnails(displayChannels)
                    })
                    menuItems.add("清除预览图" to { viewModel.clearAllThumbnails() })
                    if (listSourceTab == ListSourceTab.LOCAL && filteredChannels.isNotEmpty()) {
                        menuItems.add("清空本地频道" to { viewModel.clearLocalChannels() })
                    }
                    menuItems.forEachIndexed { idx, (label, action) ->
                        val isLast = idx == menuItems.size - 1
                        val isDestructive = label == "清空本地频道"
                        Surface(
                            color = Color.Transparent,
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp).clickable {
                                viewMenuExpanded = false
                                action()
                            }
                        ) {
                            Text(
                                text = label,
                                fontSize = 15.sp,
                                color = if (isDestructive) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp)
                            )
                        }
                        if (!isLast) {
                            HorizontalDivider(
                                color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.3f),
                                modifier = Modifier.padding(horizontal = 16.dp)
                            )
                        }
                    }
                }
                }
            }
        }

        // 本地列表为空时显示快捷入口
        if (listSourceTab == ListSourceTab.LOCAL && filteredChannels.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Spacer(modifier = Modifier.height(32.dp))
                if (localHistory.isNotEmpty()) {
                    Text(
                        text = "最近播放",
                        color = MaterialTheme.colorScheme.onBackground,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    // 最近播放列表同样按同名多路流加分辨率后缀，避免两条 CCTV-1 分不清
                    val historyDuplicateNames = remember(channels) { duplicateChannelNames(channels) }
                    localHistory.forEach { channel ->
                        val idx = channels.indexOfFirst { it.url == channel.url }
                        Surface(
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 3.dp)
                                .clickable { if (idx >= 0) viewModel.playChannel(idx) }
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, tint = AptvAccent, modifier = Modifier.size(24.dp))
                                Spacer(modifier = Modifier.width(10.dp))
                                Text(
                                    text = channelDisplayName(channel, historyDuplicateNames),
                                    color = MaterialTheme.colorScheme.onSurface,
                                    fontSize = 14.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                    }
                }
                Spacer(modifier = Modifier.height(24.dp))
                Text("暂无本地文件\n点击下方按钮打开本地视频/音乐", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                Spacer(modifier = Modifier.height(8.dp))
                TextButton(onClick = {
                    if (!viewModel.isSafAvailable()) viewModel.showMediaFileBrowser()
                    else videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
                }) { Text("打开本地文件") }
                Spacer(modifier = Modifier.height(4.dp))
                TextButton(onClick = {
                    if (!viewModel.isSafAvailable()) viewModel.showFileBrowser()
                    else playlistLauncher.launch(arrayOf(
                        "application/x-mpegurl", "application/vnd.apple.mpegurl",
                        "audio/x-mpegurl", "video/x-mpegurl",
                        "text/plain", "application/octet-stream"
                    ))
                }) { Text("导入播放列表") }
            }
            return
        }

        if (searchedChannels.isEmpty()) {
            ChannelEmptyState(
                tab = if (listSourceTab == ListSourceTab.LOCAL) ChannelTab.LOCAL else ChannelTab.SUB,
                loading = iptvStatus?.sourceLoading == true || localSourceLoading,
                sourceWarning = iptvStatus?.sourceWarning.orEmpty(),
                searchQuery = searchQuery,
                groupName = selectedGroup,
                onAddSource = { viewModel.toggleSourceManager() },
                onRefresh = { viewModel.reloadSources() }
            )
            return
        }

        // ---- APTV风格全宽布局（无左右分栏） ----
        Box(modifier = Modifier.fillMaxSize()) {
            if (viewMode == ListViewMode.LIST) {
                ChannelListPanel(
                    displayChannels = searchedChannels,
                    channels = channels,
                    currentIdx = currentIdx,
                    fileLoaded = fileLoaded,
                    favorites = favorites,
                        epgCacheVersion = epgCacheVersion,
                        thumbnailPaths = thumbnailPaths,
                        thumbnailEnabled = thumbnailEnabled,
                        viewModel = viewModel,
                        showDelete = listSourceTab == ListSourceTab.LOCAL,
                        onDelete = { idx -> viewModel.deleteChannel(idx) },
                        latencyMap = latencyMap,
                        mediaInfoMap = mediaInfoMap
                    )
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
                        showDelete = listSourceTab == ListSourceTab.LOCAL,
                        onDelete = { idx -> viewModel.deleteChannel(idx) },
                        latencyMap = latencyMap,
                        groupList = groupList,
                        mediaInfoMap = mediaInfoMap
                    )
                }
            }

    }
}
/** 右侧频道列表（列表模式） */
@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ChannelListPanel(
    displayChannels: List<IptvChannel>,
    channels: List<IptvChannel>,
    currentIdx: Int,
    fileLoaded: Boolean = false,
    favorites: Set<Int>,
    epgCacheVersion: Int,
    thumbnailPaths: Map<String, String>,
    thumbnailEnabled: Boolean = false,
    viewModel: AppViewModel,
    showDelete: Boolean = false,
    onDelete: (Int) -> Unit = {},
    latencyMap: Map<String, Int> = emptyMap(),
    mediaInfoMap: Map<String, String> = emptyMap()
) {
    // 同名多路流（同一频道的高清/标清等不同码流）在名称后追加分辨率后缀，
    // 否则两条同名频道在列表里完全一样，看起来像少了一条
    val duplicateNames = remember(displayChannels) { duplicateChannelNames(displayChannels) }
    val listState = rememberLazyListState()
    LaunchedEffect(displayChannels, currentIdx) {
        if (currentIdx >= 0) {
            val scrollTarget = displayChannels.indexOfFirst { it == channels.getOrNull(currentIdx) }
            if (scrollTarget >= 0) {
                listState.scrollToItem(scrollTarget)
            }
        }
    }
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        // 底部避让悬浮 tab 栏（62dp 栏体 + 导航栏），末项可滚动到 tab 栏上方
        contentPadding = PaddingValues(bottom = 130.dp, top = 4.dp)
    ) {
        items(displayChannels) { channel ->
            val idx = channels.indexOf(channel)
            val isCurrent = fileLoaded && idx == currentIdx
            val isFav = favorites.contains(idx)
            val canCatchup = CatchupHelper.isCatchupEnabled(channel)
            val currentProgram = if (idx >= 0) {
                remember(epgCacheVersion, idx) { viewModel.getCachedCurrentProgram(idx) }
            } else null
            val thumbPath = thumbnailPaths[channel.url]
            val hasThumb = thumbPath != null && File(thumbPath).exists()
            val latency = latencyMap[channel.url]

            // 频道行：圆角玻璃卡片（磨砂+光斑+描边），当前播放行叠加品牌色高亮
            com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                enabled = LocalLiquidGlass.current && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                cornerRadius = 12.dp,
                staticGlass = true,
                fallbackColor = if (isCurrent) AptvAccent.copy(alpha = 0.12f)
                    else MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 6.dp, vertical = 2.dp)
                    .background(
                        if (isCurrent) AptvAccent.copy(alpha = 0.10f) else Color.Transparent,
                        RoundedCornerShape(12.dp)
                    )
                    // TV 遥控器焦点高亮：必须放在 clickable 之前（外层），否则收不到焦点事件
                    .tvFocusBorder(cornerRadius = 12)
                    .combinedClickable(
                        onClick = { if (idx >= 0) viewModel.playChannel(idx) },
                        onLongClick = {
                            if (idx >= 0) {
                                viewModel.toggleFavoriteByIndex(idx)
                            }
                        }
                    )
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // 第一列：预览图或台标（底部覆盖分组）
                    Box(
                        modifier = Modifier
                            .size(72.dp, 40.dp)
                            .clip(RoundedCornerShape(4.dp))
                            // 用 playerPlaceholder token：浅色下曾是纯黑底板，卡片与分栏间隙相邻时
                            // 会形成一条像「露底」的黑缝
                            .background(tvPalette.playerPlaceholder),
                        contentAlignment = Alignment.Center
                    ) {
                        if (hasThumb) {
                            AsyncImage(
                                model = thumbPath,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize(),
                                contentScale = ContentScale.Crop
                            )
                        } else if (channel.logo.isNotEmpty()) {
                            AsyncImage(
                                model = channel.logo,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize().padding(4.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            Icon(Icons.Default.PlayArrow, contentDescription = null, tint = AptvAccent.copy(alpha = 0.4f), modifier = Modifier.size(20.dp))
                        }
                        // 底部覆盖分组标识
                        Surface(
                            color = Color.Black.copy(alpha = 0.6f),
                            shape = RoundedCornerShape(2.dp),
                            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                        ) {
                            Text(
                                text = channel.group.ifEmpty { "未分组" },
                                color = Color.White,
                                fontSize = 7.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.padding(horizontal = 2.dp, vertical = 0.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    // 第二列：频道名 / 节目名 / 媒体标识
                    Column(modifier = Modifier.weight(1f)) {
                        // 第1行：频道名称 + 延迟
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = channelDisplayName(channel, duplicateNames),
                                color = if (isCurrent) tvPalette.accentText else MaterialTheme.colorScheme.onSurface,
                                fontSize = 14.sp,
                                fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            if (latency != null && latency > 0) {
                                val latColor = when { latency < 200 -> tvPalette.success; latency < 500 -> tvPalette.warning; else -> tvPalette.danger }
                                Text("${latency}ms", color = latColor, fontSize = 10.sp, fontWeight = FontWeight.Medium)
                            }
                        }
                        // 第2行：当前节目名称
                        currentProgram?.let { prog ->
                            Text(
                                text = if (prog.title.isNotEmpty()) prog.title else "精彩节目",
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = if (prog.title.isNotEmpty()) 1f else 0.6f),
                                fontSize = 11.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        } ?: Text("精彩节目", color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f), fontSize = 11.sp, maxLines = 1)
                        // 第3行：媒体标识badge（圆角矩形；协议/容器格式无价值不显示；回看用文字徽章）
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            mediaInfoMap[channel.url]?.split(" ")?.forEach { badge ->
                                if (badge.isNotEmpty() && badge !in badgeDisplayBlocklist) {
                                    Surface(color = AptvAccent.copy(alpha = 0.15f), shape = RoundedCornerShape(4.dp)) {
                                        Text(badge, color = tvPalette.accentText, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp))
                                    }
                                }
                            }
                            if (canCatchup) {
                                // 回看徽章带天数（有天数数据时显示「回看7天」）
                                val catchupText = channel.catchupDays.trim().toIntOrNull()?.let { days ->
                                    if (days > 0) "回看${days}天" else "回看"
                                } ?: "回看"
                                Surface(color = AptvAccent.copy(alpha = 0.15f), shape = RoundedCornerShape(4.dp)) {
                                    Text(catchupText, color = tvPalette.accentText, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp))
                                }
                            }
                            if (isFav) {
                                Surface(color = tvPalette.favorite.copy(alpha = 0.15f), shape = RoundedCornerShape(4.dp)) {
                                    Text("收藏", color = tvPalette.favorite, fontSize = 9.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp))
                                }
                            }
                        }
                    }
                    // 第三列：台标（回看已改为文字徽章）
                    if (channel.logo.isNotEmpty()) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            AsyncImage(
                                model = channel.logo,
                                contentDescription = null,
                                modifier = Modifier.size(22.dp).clip(RoundedCornerShape(2.dp)),
                                contentScale = ContentScale.Fit
                            )
                        }
                    }
                    // 删除按钮
                    if (showDelete && idx >= 0) {
                        Spacer(modifier = Modifier.width(4.dp))
                        Icon(Icons.Default.Close, contentDescription = "删除", tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(18.dp).clickable { onDelete(idx) })
                    }
                }
            }
        }
    }
}
/** 右侧频道列表（缩略图模式）；横屏首页（LandscapeHomeScreen）左列宫格复用 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun ChannelThumbnailPanel(
    displayChannels: List<IptvChannel>,
    channels: List<IptvChannel>,
    currentIdx: Int,
    fileLoaded: Boolean = false,
    favorites: Set<Int>,
    thumbnailPaths: Map<String, String>,
    thumbnailEnabled: Boolean = false,
    viewModel: AppViewModel,
    showDelete: Boolean = false,
    onDelete: (Int) -> Unit = {},
    latencyMap: Map<String, Int> = emptyMap(),
    groupList: List<Pair<String, Int>> = emptyList(),
    mediaInfoMap: Map<String, String> = emptyMap(),
    bottomContentPadding: androidx.compose.ui.unit.Dp = 130.dp,
    // TV 首页初始焦点：非空时请求到宫格第一张卡（遥控器打开首页即可直接方向键导航）
    firstCardFocusRequester: FocusRequester? = null
) {
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    // 同名多路流（同一频道的不同分辨率/码流）在名称后追加分辨率后缀，便于区分
    val duplicateNames = remember(displayChannels) { duplicateChannelNames(displayChannels) }

    LazyVerticalGrid(
        columns = GridCells.Fixed(2),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 6.dp, top = 4.dp, end = 6.dp, bottom = bottomContentPadding),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        gridItemsIndexed(displayChannels) { cardIndex, channel ->
            val idx = channels.indexOf(channel)
            val isCurrent = fileLoaded && idx == currentIdx
            val isFav = favorites.contains(idx)
            val canCatchup = CatchupHelper.isCatchupEnabled(channel)
            val thumbPath = thumbnailPaths[channel.url]
            val hasThumb = thumbPath != null && File(thumbPath).exists()
            val latency = latencyMap[channel.url]
            val currentProgram = if (idx >= 0) {
                remember(epgCacheVersion, idx) { viewModel.getCachedCurrentProgram(idx) }
            } else null
            val channelGroup = channel.group.ifEmpty { "未分组" }

            // 宫格卡：圆角玻璃卡片（磨砂+光斑+描边），当前播放卡叠加品牌色高亮
            com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                enabled = LocalLiquidGlass.current && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
                cornerRadius = 12.dp,
                staticGlass = true,
                fallbackColor = if (isCurrent) AptvAccent.copy(alpha = 0.12f)
                    else MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier
                    .then(
                        if (firstCardFocusRequester != null && cardIndex == 0)
                            Modifier.focusRequester(firstCardFocusRequester) else Modifier
                    )
                    .background(
                        if (isCurrent) AptvAccent.copy(alpha = 0.10f) else Color.Transparent,
                        RoundedCornerShape(12.dp)
                    )
                    // TV 遥控器焦点高亮：必须放在 clickable 之前（外层）——
                    // onFocusChanged 只能观察到链中内层方向的 focus target，
                    // 放在 clickable 之后会收不到焦点事件，高亮和放大动画都不会触发
                    .tvFocusBorder(cornerRadius = 12)
                    .combinedClickable(
                        onClick = { if (idx >= 0) viewModel.playChannel(idx) },
                        onLongClick = {
                            if (idx >= 0) {
                                viewModel.toggleFavoriteByIndex(idx)
                            }
                        }
                    )
            ) {
                // 内缩边距：四周露出玻璃边框，预览图圆角内嵌（iOS 卡片风格）
                Column(modifier = Modifier.fillMaxWidth().padding(5.dp)) {
                    // 预览图/台标区域（16:9）
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .aspectRatio(16f / 9f)
                            .clip(RoundedCornerShape(9.dp))
                            // 纯黑底板在浅色主题下会在分栏边界形成硬黑条（会被误认为露底）
                            .background(tvPalette.playerPlaceholder)
                    ) {
                        if (hasThumb) {
                            AsyncImage(
                                model = thumbPath,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize(),
                                contentScale = ContentScale.Crop
                            )
                        } else if (channel.logo.isNotEmpty()) {
                            AsyncImage(
                                model = channel.logo,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize().padding(12.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null, tint = AptvAccent.copy(alpha = 0.3f), modifier = Modifier.size(28.dp))
                            }
                        }
                        // 左下角延迟标识
                        if (latency != null && latency > 0) {
                            val latColor = when { latency < 200 -> tvPalette.success; latency < 500 -> tvPalette.warning; else -> tvPalette.danger }
                            Surface(
                                color = Color.Black.copy(alpha = 0.6f),
                                shape = RoundedCornerShape(4.dp),
                                modifier = Modifier.align(Alignment.BottomStart).padding(4.dp)
                            ) {
                                Text("${latency}ms", color = latColor, fontSize = 8.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                            }
                        }
                        // 右下角分组悬浮标识（与延迟左下对称）
                        if (channelGroup.isNotEmpty()) {
                            Surface(
                                color = Color.Black.copy(alpha = 0.6f),
                                shape = RoundedCornerShape(4.dp),
                                modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp)
                            ) {
                                Text(
                                    channelGroup,
                                    color = Color.White.copy(alpha = 0.85f),
                                    fontSize = 8.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp).widthIn(max = 72.dp)
                                )
                            }
                        }
                        // 右上角：播放中
                        if (isCurrent) {
                            Surface(
                                color = tvPalette.accentFill,
                                shape = RoundedCornerShape(4.dp),
                                modifier = Modifier.align(Alignment.TopEnd).padding(3.dp)
                            ) {
                                Text("播放中", color = tvPalette.accentOn, fontSize = 8.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                            }
                        }
                        // 删除按钮
                        if (showDelete && idx >= 0) {
                            Box(
                                modifier = Modifier.align(Alignment.TopStart).padding(4.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.6f)).clickable { onDelete(idx) }.padding(4.dp)
                            ) {
                                Icon(Icons.Default.Close, contentDescription = "删除", tint = Color.White, modifier = Modifier.size(14.dp))
                            }
                        }
                    }
                    // 下方紧凑信息区：左侧文字信息 + 右侧台标
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            // 第1行：频道名称
                            Text(
                                text = channelDisplayName(channel, duplicateNames),
                                color = if (isCurrent) tvPalette.accentText else MaterialTheme.colorScheme.onSurface,
                                fontSize = 12.sp,
                                fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            // 第2行：当前节目名称
                            currentProgram?.let { prog ->
                                Text(
                                    text = if (prog.title.isNotEmpty()) prog.title else "精彩节目",
                                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = if (prog.title.isNotEmpty()) 1f else 0.6f),
                                    fontSize = 10.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                            }
                            // 第3行：媒体标识 + 回看 + 收藏（全部文字徽章；协议/容器格式无价值不显示）
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                                mediaInfoMap[channel.url]?.split(" ")?.forEach { badge ->
                                    if (badge.isNotEmpty() && badge !in badgeDisplayBlocklist) {
                                        Surface(color = AptvAccent.copy(alpha = 0.15f), shape = RoundedCornerShape(3.dp)) {
                                            Text(badge, color = tvPalette.accentText, fontSize = 8.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                                        }
                                    }
                                }
                                if (canCatchup) {
                                    // 回看徽章带天数（有天数数据时显示「回看7天」）
                                    val catchupText = channel.catchupDays.trim().toIntOrNull()?.let { days ->
                                        if (days > 0) "回看${days}天" else "回看"
                                    } ?: "回看"
                                    Surface(color = AptvAccent.copy(alpha = 0.15f), shape = RoundedCornerShape(3.dp)) {
                                        Text(catchupText, color = tvPalette.accentText, fontSize = 8.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                                    }
                                }
                                if (isFav) {
                                    Surface(color = tvPalette.favorite.copy(alpha = 0.15f), shape = RoundedCornerShape(3.dp)) {
                                        Text("收藏", color = tvPalette.favorite, fontSize = 8.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                                    }
                                }
                            }
                        }
                        // 右侧台标：占用信息区右侧空白，垂直居中（浅灰衬底防幽灵化）
                        if (channel.logo.isNotEmpty()) {
                            Spacer(modifier = Modifier.width(4.dp))
                            Box(
                                modifier = Modifier
                                    .size(width = 42.dp, height = 26.dp)
                                    .clip(RoundedCornerShape(3.dp))
                                    .background(MaterialTheme.colorScheme.surfaceVariant),
                                contentAlignment = Alignment.Center
                            ) {
                                AsyncImage(
                                    model = channel.logo,
                                    contentDescription = null,
                                    modifier = Modifier.fillMaxSize().padding(2.dp),
                                    contentScale = ContentScale.Fit
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
 * 竖屏频道列表项
 * 台标 + 频道名(+回看标识) + 当前节目名 + 节目单按钮
 */
@Composable
internal fun PortraitChannelListItem(
    channel: IptvChannel,
    channelIdx: Int,
    isPlaying: Boolean,
    viewModel: AppViewModel,
    epgCacheVersion: Int,
    focusRequester: FocusRequester? = null,
    onPlay: () -> Unit,
    onEpg: () -> Unit
) {
    // 同名多路流补分辨率后缀，与频道列表口径一致
    val sidebarChannels by viewModel.channels.collectAsState()
    val dupNames = remember(sidebarChannels) { duplicateChannelNames(sidebarChannels) }
    // 获取缓存的当前节目
    var currentProgram by remember { mutableStateOf<com.iptv.scanner.editor.pro.data.IptvEpgProgram?>(null) }
    LaunchedEffect(channelIdx, epgCacheVersion) {
        currentProgram = viewModel.getCachedCurrentProgram(channelIdx)
        while (true) {
            delay(5_000L)
            currentProgram = viewModel.getCachedCurrentProgram(channelIdx)
        }
    }

    // APTV 风格：播放中用 AptvAccent 浅红底 + 红字 + 圆角，非播放透明
    // 遥控器焦点：tvFocusBorder 放在 clickable 之前（外层）才能收到焦点事件；
    // 平板分屏右栏「频道」页签里这张卡是最主要的可聚焦项，没有描边时焦点是隐形的。
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (isPlaying) Modifier.background(AptvAccent.copy(alpha = 0.12f), RoundedCornerShape(8.dp)) else Modifier)
            .tvFocusBorder(cornerRadius = 8)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .clickable(onClick = onPlay)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 台标（浅灰衬底：防止白色台标在浅色玻璃上幽灵化，与 Mini 播放条一致）
        if (channel.logo.isNotEmpty()) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center
            ) {
                AsyncImage(
                    model = channel.logo,
                    contentDescription = channel.name,
                    modifier = Modifier.fillMaxSize().padding(2.dp),
                    contentScale = ContentScale.Fit
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
        } else {
            // 无台标占位
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = channel.name.take(1),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 14.sp
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
        }

        // 频道名 + 节目名
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = channelDisplayName(channel, dupNames),
                    color = if (isPlaying) tvPalette.accentText else MaterialTheme.colorScheme.onSurface,
                    fontSize = 15.sp,
                    fontWeight = if (isPlaying) FontWeight.Medium else FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            // 当前节目名
            val programTitle = currentProgram?.title
            if (!programTitle.isNullOrEmpty()) {
                Text(
                    text = programTitle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            } else {
                Text(
                    text = "精彩节目",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }

        // 回看标识（居右，节目单按钮左边）
        if (channel.catchup.isNotEmpty() && channel.catchup != "none") {
            Surface(
                color = AptvAccent.copy(alpha = 0.15f),
                shape = RoundedCornerShape(3.dp)
            ) {
                Text(
                    text = "回看",
                    color = tvPalette.accentText,
                    fontSize = 9.sp,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                )
            }
            Spacer(modifier = Modifier.width(2.dp))
        }

        // 节目单按钮
        IconButton(
            onClick = onEpg,
            modifier = Modifier.size(48.dp)
        ) {
            Icon(
                Icons.Default.CalendarMonth,
                    contentDescription = stringResource(R.string.cd_program_guide),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(18.dp)
            )
        }
    }
}

// =====================================================================
// 频道列表公共空态 / 加载态 / 错误态 / key 工具
// =====================================================================

/**
 * 频道列表统一的空态、加载态与错误态。
 *
 * 供 TV 统一面板、横屏侧边栏、竖屏动态面板、频道列表面板共用，
 * 避免各页面各自拼一套文案导致同一场景提示不一致。
 *
 * 判定顺序（互斥）：
 * 1. 加载中 —— 显示进度，不展示「暂无频道」以免误导
 * 2. 有搜索词 —— 无匹配结果
 * 3. 订阅源告警 —— 固定可读文案 + 重试
 * 4. 无明显原因 —— 按 tab/分组给出针对性引导
 *
 * 注意：内部文案目前为硬编码中文，后续需统一迁移到 strings.xml。
 */
@Composable
internal fun ChannelEmptyState(
    tab: ChannelTab,
    loading: Boolean,
    sourceWarning: String,
    searchQuery: String = "",
    groupName: String = "",
    onAddSource: (() -> Unit)? = null,
    onRefresh: (() -> Unit)? = null,
    /** 主操作按钮的焦点入口（横屏底栏 UP 落点用）；为 null 时不挂请求器 */
    firstActionFocusRequester: FocusRequester? = null,
    modifier: Modifier = Modifier
) {
    // 原始告警串只进日志：其中可能包含异常堆栈或订阅源 URL，不适合直接展示给用户
    LaunchedEffect(sourceWarning) {
        if (sourceWarning.isNotBlank()) {
            Log.w("ChannelEmptyState", "订阅源加载告警（原始信息）: $sourceWarning")
        }
    }

    val failed = !loading && sourceWarning.isNotBlank()
    val addSource = onAddSource
    val refresh = onRefresh
    val keyword = searchQuery.trim()

    val primary = when {
        loading -> "正在加载订阅源..."
        searchQuery.isNotBlank() -> "无匹配频道"
        failed -> "网络异常，当前显示缓存频道"
        tab == ChannelTab.LOCAL -> "暂无本地频道"
        tab == ChannelTab.FAV -> "暂无收藏"
        tab == ChannelTab.HIST -> "暂无历史"
        groupName.isNotBlank() -> "该分组暂无频道"
        else -> "暂无频道"
    }
    val secondary = when {
        loading -> "首次加载可能需要几十秒，请稍候"
        searchQuery.isNotBlank() -> "未找到包含「$keyword」的频道，换个关键词再试试"
        failed -> "订阅源刷新失败，可点击下方按钮重试"
        tab == ChannelTab.LOCAL -> "可通过文件浏览导入本地视频或播放列表"
        tab == ChannelTab.FAV -> "在频道列表按星标收藏常看频道"
        tab == ChannelTab.HIST -> "播放过的频道会自动记录在这里"
        groupName.isNotBlank() -> "切换到其他分组或选择「全部」"
        else -> "添加订阅源后会自动同步频道列表"
    }

    // 主次操作互不重复：失败场景主按钮是重试；正常空态主按钮是添加订阅源、次按钮是刷新
    val primaryAction: Pair<String, () -> Unit>? = when {
        loading || searchQuery.isNotBlank() -> null
        failed -> refresh?.let { "重试" to it }
        tab == ChannelTab.SUB -> addSource?.let { "添加订阅源" to it }
        else -> null
    }
    val secondaryAction: Pair<String, () -> Unit>? = when {
        loading || searchQuery.isNotBlank() || failed || tab != ChannelTab.SUB -> null
        else -> refresh?.let { "刷新" to it }
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(28.dp),
                color = MaterialTheme.colorScheme.primary,
                strokeWidth = 2.5.dp
            )
            Spacer(modifier = Modifier.height(14.dp))
        }
        Text(
            text = primary,
            color = MaterialTheme.colorScheme.onSurface,
            fontSize = 15.sp,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = secondary,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
            lineHeight = 18.sp,
            textAlign = TextAlign.Center,
            // 关键词可能很长，限制行数避免撑破空态布局
            maxLines = 3,
            overflow = TextOverflow.Ellipsis
        )
        if (primaryAction != null || secondaryAction != null) {
            Spacer(modifier = Modifier.height(18.dp))
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                primaryAction?.let { (label, action) ->
                    Button(
                        onClick = action,
                        modifier = Modifier
                            .then(
                                if (firstActionFocusRequester != null)
                                    Modifier.focusRequester(firstActionFocusRequester)
                                else Modifier
                            )
                            .tvFocusBorder()
                    ) {
                        Text(label, fontSize = 13.sp)
                    }
                }
                secondaryAction?.let { (label, action) ->
                    OutlinedButton(onClick = action, modifier = Modifier.tvFocusBorder()) {
                        Text(label, fontSize = 13.sp)
                    }
                }
            }
        }
    }
}

/**
 * 为频道列表生成稳定的 LazyColumn key。
 *
 * 使用频道 URL 而非列表下标：频道增删、分组过滤、分页截断后，
 * 同一频道的组合状态与焦点不会错位到别的频道上。
 * 同一 URL 在多个订阅源中重复出现时追加出现序号，保证 key 唯一
 * （LazyColumn 遇到重复 key 会直接抛异常）。
 */
internal fun buildChannelItemKeys(items: List<Pair<IptvChannel, Int>>): List<String> {
    val seen = HashMap<String, Int>()
    return items.map { (channel, idx) ->
        val base = channel.url.ifBlank { "ch_$idx" }
        val hits = (seen[base] ?: 0) + 1
        seen[base] = hits
        if (hits == 1) base else "$base#$hits"
    }
}

/** 分辨率标签：1920x1080 → 1080P，3840x2160 → 4K，720x576 → 576P */
internal fun channelResolutionLabel(resolution: String): String {
    val r = resolution.trim().lowercase()
    if (r.isEmpty()) return ""
    val height = r.substringAfterLast('x', "").filter { it.isDigit() }.toIntOrNull()
        ?: return r.uppercase()
    return when {
        height >= 2160 -> "4K"
        height >= 1080 -> "1080P"
        height >= 720 -> "720P"
        height >= 576 -> "576P"
        height >= 480 -> "480P"
        else -> "${height}P"
    }
}

/**
 * 出现次数 >1 的频道名集合：同名多路流（同一频道的不同分辨率/码流）才需要追加后缀区分。
 *
 * 只统计原始频道名，不参与搜索/匹配/EPG 请求。
 */
internal fun duplicateChannelNames(channels: List<IptvChannel>): Set<String> =
    channels.groupBy { it.name }.filterValues { it.size > 1 }.keys

/**
 * 列表显示名：同名多路流（同一频道的不同分辨率/码流）在名称后追加分辨率后缀，
 * 没有分辨率信息时退回频道号，避免两条同名频道在列表里完全不可区分。
 *
 * 只影响显示文本，不改动频道数据（名称/URL/收藏索引保持原样）。
 */
internal fun channelDisplayName(channel: IptvChannel, duplicateNames: Set<String>): String {
    if (channel.name !in duplicateNames) return channel.name
    val suffix = channelResolutionLabel(channel.resolution).ifEmpty {
        val chno = channel.tvgChno.trim()
        if (chno.isEmpty()) "" else "CH$chno"
    }
    return if (suffix.isEmpty()) channel.name else "${channel.name} · $suffix"
}
