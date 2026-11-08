package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.ui.theme.tvTextField

/**

 * 收藏 Tab 页：对齐 APTV"我的收藏"——标题 + 刷新 + 搜索 + 双列预览网格。
 * 数据 = 收藏频道（idx 由 reanchorUserListsToChannels 保证 URL 锚定后有效）。
 */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
internal fun PortraitFavoritesScreen(
    viewModel: AppViewModel,
    playlistLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    videoLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>
) {
    val channels by viewModel.channels.collectAsState()
    val favorites by viewModel.favorites.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val fileLoaded by viewModel.mpv.fileLoaded.collectAsState()
    val thumbnailPaths by viewModel.thumbnailPaths.collectAsState()
    val scanResults by viewModel.scanResults.collectAsState()
    val liveLatencyMap by viewModel.liveLatencyMap.collectAsState()

    val latencyMap = remember(scanResults, liveLatencyMap) {
        val merged = mutableMapOf<String, Int>()
        scanResults.forEach { if (it.latency > 0) merged[it.url] = it.latency }
        liveLatencyMap.forEach { (url, lat) -> if (lat > 0) merged[url] = lat }
        merged
    }

    var searchQuery by remember { mutableStateOf("") }

    val favChannels = remember(channels, favorites) {
        favorites.mapNotNull { channels.getOrNull(it) }
    }
    val displayChannels = remember(favChannels, searchQuery) {
        if (searchQuery.isBlank()) favChannels
        else favChannels.filter { it.name.contains(searchQuery, ignoreCase = true) }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
        // 不铺不透明底：透出内容区的环境画布
    ) {
        // APTV 头部：红色源名 + 刷新
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "我的收藏",
                color = AptvAccent,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            Spacer(modifier = Modifier.weight(1f))
            // 刷新预览：玻璃圆形按钮
            AptvGlassChip(cornerRadius = 16.dp, modifier = Modifier.size(32.dp)) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .clickable { viewModel.loadThumbnailPaths() },
                    contentAlignment = androidx.compose.ui.Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Refresh,
                        contentDescription = "刷新预览",
                        tint = AptvAccent,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }
        }

        // 搜索框：玻璃底座
        AptvGlassChip(
            cornerRadius = 10.dp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp)
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

        Spacer(modifier = Modifier.height(6.dp))

        if (favChannels.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.PlayArrow,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        "暂无收藏频道\n在频道列表长按频道可添加收藏",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp,
                        lineHeight = 20.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                }
            }
            return@Column
        }
        if (displayChannels.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("无匹配频道", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
            }
            return@Column
        }

        // 双列预览网格（复用频道页的缩略图卡片）
        val gridState = rememberLazyGridState()
        LazyVerticalGrid(
            state = gridState,
            columns = GridCells.Fixed(2),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 10.dp, top = 4.dp, end = 10.dp, bottom = 130.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            gridItems(displayChannels) { channel ->
                val idx = channels.indexOfFirst { it.url == channel.url }
                PortraitAptvChannelCard(
                    viewModel = viewModel,
                    channel = channel,
                    idx = idx,
                    isCurrent = fileLoaded && idx == currentIdx,
                    thumbnailPaths = thumbnailPaths,
                    latency = latencyMap[channel.url]
                )
            }
        }
    }
}

/**
 * APTV 风格频道卡片：16:9 预览图/台标 + 右上角延迟标签 + 下方频道名(左)台标(右)。
 * 点击播放，长按收藏切换（与频道页行为一致）。
 */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
internal fun PortraitAptvChannelCard(
    viewModel: AppViewModel,
    channel: com.iptv.scanner.editor.pro.data.IptvChannel,
    idx: Int,
    isCurrent: Boolean,
    thumbnailPaths: Map<String, String>,
    latency: Int?
) {
    val thumbPath = thumbnailPaths[channel.url]
    val hasThumb = thumbPath != null && java.io.File(thumbPath).exists()
    val cardBorder = if (isCurrent) AptvAccent else MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f)

    androidx.compose.material3.Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp),
        border = androidx.compose.foundation.BorderStroke(
            if (isCurrent) 1.5.dp else 0.5.dp,
            cardBorder
        ),
        modifier = Modifier
            .fillMaxWidth()
            .combinedClickable(
                onClick = { if (idx >= 0) viewModel.playChannel(idx) },
                onLongClick = { if (idx >= 0) viewModel.toggleFavoriteByIndex(idx) }
            )
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            // 预览图/台标区域（16:9，纯黑底对齐 APTV）
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .background(Color.Black)
            ) {
                when {
                    hasThumb -> coil.compose.AsyncImage(
                        model = thumbPath,
                        contentDescription = channel.name,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop
                    )
                    channel.logo.isNotEmpty() -> coil.compose.AsyncImage(
                        model = channel.logo,
                        contentDescription = channel.name,
                        modifier = Modifier.fillMaxSize().padding(14.dp),
                        contentScale = androidx.compose.ui.layout.ContentScale.Fit
                    )
                    else -> Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.PlayArrow,
                            contentDescription = null,
                            tint = Color.White.copy(alpha = 0.25f),
                            modifier = Modifier.size(30.dp)
                        )
                    }
                }
                // 右上角延迟标签（APTV 招牌元素：绿=快/黄=中/红=慢）
                if (latency != null && latency > 0) {
                    val latColor = when {
                        latency < 200 -> tvPalette.success
                        latency < 500 -> tvPalette.warning
                        else -> tvPalette.danger
                    }
                    androidx.compose.material3.Surface(
                        color = Color.Black.copy(alpha = 0.65f),
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp),
                        modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                    ) {
                        Text(
                            "${latency} ms",
                            color = latColor,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp)
                        )
                    }
                }
                // 播放中标记
                if (isCurrent) {
                    androidx.compose.material3.Surface(
                        color = AptvAccent,
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(4.dp),
                        modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp)
                    ) {
                        Text(
                            "播放中",
                            color = Color.White,
                            fontSize = 8.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }
                }
            }
            // 下方：频道名（左）+ 台标（右）
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 6.dp, vertical = 6.dp)
            ) {
                Text(
                    text = channel.name,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                if (channel.logo.isNotEmpty()) {
                    coil.compose.AsyncImage(
                        model = channel.logo,
                        contentDescription = null,
                        modifier = Modifier
                            .height(14.dp)
                            .padding(start = 4.dp),
                        contentScale = androidx.compose.ui.layout.ContentScale.Fit
                    )
                }
            }
        }
    }
}
