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
import androidx.compose.runtime.DisposableEffect
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
import androidx.media3.ui.PlayerView
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
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
 * 播放器模式动态内容：多 Tab 布局（频道列表 / 节目单 / 播放信息）
 */
@Composable
internal fun PortraitPlayerDynamicContent(viewModel: AppViewModel) {
    val currentIdx by viewModel.currentIdx.collectAsState()
    val currentChannel by viewModel.currentChannel.collectAsState()
    val player = viewModel.mpv
    val fileLoaded by player.fileLoaded.collectAsState()
    val oc = rememberPlayerOverlayColors()
    // 播放页经 movableContent 移动，在竖屏 provider 之外 —— 需单独读取并提供玻璃开关
    val liquidGlass by viewModel.liquidGlass.collectAsState()

    // 判断是订阅频道还是本地文件
    val isLocalFile = currentChannel == null || currentIdx < 0

    // Tab 状态：订阅频道 = [分类, 频道, 节目, 信息]，本地文件 = [信息, 最近文件]
    // 必须在下方 fileLoaded 提前 return 之前 remember：切台时 mpv 会短暂置
    // fileLoaded=false，若放在 return 之后，状态槽随组合销毁，新频道加载完成后
    // selectedTab 会被重置回「分类」，无法停留在「频道」列表连续选台
    var selectedTab by remember { mutableStateOf(0) }

    if (!fileLoaded) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = stringResource(R.string.not_playing),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 14.sp
            )
        }
        return
    }

    val tabs = if (isLocalFile) {
        listOf(stringResource(R.string.tab_info), stringResource(R.string.tab_recent_files))
    } else {
        listOf(stringResource(R.string.tab_category), stringResource(R.string.tab_channel), stringResource(R.string.tab_program), stringResource(R.string.tab_info))
    }

    // 如果 selectedTab 超出范围（切换模式时），重置为 0
    LaunchedEffect(tabs.size) {
        if (selectedTab >= tabs.size) selectedTab = 0
    }

    androidx.compose.runtime.CompositionLocalProvider(LocalLiquidGlass provides liquidGlass) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Tab 栏（玻璃条：静态磨砂+描边；选中项白底高亮）
        AptvGlassChip(
            cornerRadius = 14.dp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 4.dp, vertical = 2.dp)
            ) {
                tabs.forEachIndexed { index, label ->
                    val isSelected = index == selectedTab
                    // iOS 分段控件式选中：白亮玻璃凸起块（磨砂+白描边+高光），而非描边换色
                    val tabShape = RoundedCornerShape(10.dp)
                    androidx.compose.foundation.layout.Box(
                        modifier = Modifier
                            .weight(1f)
                            .clip(tabShape)
                            .then(
                                if (isSelected) Modifier
                                    .background(Color.White.copy(alpha = 0.20f), tabShape)
                                    .border(1.dp, Color.White.copy(alpha = 0.45f), tabShape)
                                    .background(
                                        androidx.compose.ui.graphics.Brush.verticalGradient(
                                            0f to Color.White.copy(alpha = 0.22f),
                                            1f to Color.Transparent
                                        ),
                                        tabShape
                                    )
                                else Modifier
                            )
                            .tvFocusBorder(cornerRadius = 8)
                            .clickable { selectedTab = index }
                            .padding(vertical = 8.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = label,
                            // 选中态用品牌色文字（白亮玻璃凸起上白字不可读，与底部 TAB 栏一致）
                            color = if (isSelected) AptvAccent else oc.textSecondary,
                            fontSize = 13.sp,
                            fontWeight = if (isSelected) FontWeight.SemiBold else FontWeight.Normal,
                            textAlign = TextAlign.Center,
                            maxLines = 1
                        )
                    }
                }
            }
        }
        // Tab 内容（iOS 式淡入淡出转场）
        Box(modifier = Modifier.fillMaxSize()) {
            if (isLocalFile) {
                androidx.compose.animation.Crossfade(
                    targetState = selectedTab,
                    animationSpec = androidx.compose.animation.core.tween(durationMillis = 200),
                    label = "localTab"
                ) { tab ->
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
                        1 -> PortraitRecentLocalFiles(viewModel = viewModel)
                    }
                }
            } else {
                androidx.compose.animation.Crossfade(
                    targetState = selectedTab,
                    animationSpec = androidx.compose.animation.core.tween(durationMillis = 200),
                    label = "channelTab"
                ) { tab ->
                    when (tab) {
                        0 -> PortraitCategoryContent(viewModel = viewModel, onGroupSelected = { selectedTab = 1 })
                        1 -> PortraitChannelOnlyList(viewModel = viewModel)
                        2 -> PortraitEpgContent(viewModel = viewModel)
                        3 -> {
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
/** 本地文件信息面板 */
@Composable
internal fun PortraitLocalFileInfo(
    viewModel: AppViewModel,
    duration: Double,
    timePos: Double,
    videoWidth: Int,
    videoHeight: Int
) {
    val player = viewModel.mpv
    val channels by viewModel.channels.collectAsState()
    val history by viewModel.history.collectAsState()

    // 获取媒体信息
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(2000L)
        }
    }
    val mediaInfo = remember(tick) { player.getMediaInfo() }

    // 最近播放的本地文件
    val recentLocal = remember(history, channels) {
        history.mapNotNull { idx -> channels.getOrNull(idx) }
            .filter { it.source.isEmpty() }
            .take(10)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp)
    ) {
        // 文件信息卡片（APTV 风格：圆角分组卡）
        item {
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.info_file_info),
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // 媒体信息标识行
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        mediaInfo["videoCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
                            val cleanCodec = codec.removePrefix("video/").removePrefix("audio/").uppercase()
                            MiniBadge(cleanCodec)
                        }
                        if (videoWidth > 0 && videoHeight > 0) {
                            val resLabel = if (videoHeight >= 2160) "4K"
                                else if (videoHeight >= 1080) "1080P"
                                else if (videoHeight >= 720) "720P"
                                else if (videoHeight >= 480) "480P"
                                else "${videoHeight}P"
                            MiniBadge(resLabel)
                            MiniBadge("${videoWidth}×${videoHeight}")
                        }
                        mediaInfo["audioCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
                            MiniBadge(codec.removePrefix("audio/").uppercase())
                        }
                        mediaInfo["fps"]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" && it != "0.000" }?.let { fps ->
                            val fpsVal = fps.toFloatOrNull()
                            MiniBadge(if (fpsVal != null) "${fpsVal.toInt()}FPS" else "${fps}FPS")
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // 播放进度
                    if (duration > 0) {
                        val progress = (timePos / duration * 100).coerceIn(0.0, 100.0)
                        Text(
                            text = stringResource(R.string.info_playback_progress),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        LinearProgressIndicator(
                            progress = { (progress / 100).toFloat() },
                            modifier = Modifier.fillMaxWidth(),
                            color = AptvAccent,
                            trackColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = formatTime(timePos),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                            Text(
                                text = formatTime(duration),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // 文件路径
                    mediaInfo["fileFormat"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { fmt ->
                        InfoRow(stringResource(R.string.info_container_format), fmt.uppercase())
                    }
                    mediaInfo["bitrate"]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" }?.let { br ->
                        val brVal = br.toLongOrNull() ?: 0L
                        InfoRow(stringResource(R.string.info_bitrate), if (brVal > 1000000) "${brVal / 1000000} Mbps" else "${brVal / 1000} kbps")
                    }
                }
            }
        }

        // 音轨/字幕快速切换
        item {
            Spacer(modifier = Modifier.height(12.dp))
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.info_audio_subtitle),
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        TextButton(
                            onClick = { viewModel.toggleAudioSettings() },
                            modifier = Modifier.weight(1f)
                        ) { Text(stringResource(R.string.info_audio_settings), color = AptvAccent) }
                        TextButton(
                            onClick = { viewModel.toggleSubtitleSettings() },
                            modifier = Modifier.weight(1f)
                        ) { Text(stringResource(R.string.info_subtitle_settings), color = AptvAccent) }
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        TextButton(
                            onClick = { viewModel.togglePlaybackPanel() },
                            modifier = Modifier.weight(1f)
                        ) { Text(stringResource(R.string.info_playback_speed), color = AptvAccent) }
                        TextButton(
                            onClick = { viewModel.toggleBookmarkPanel() },
                            modifier = Modifier.weight(1f)
                        ) { Text(stringResource(R.string.info_bookmark_manager), color = AptvAccent) }
                    }
                }
            }
        }

        // 最近播放的本地文件
        if (recentLocal.isNotEmpty()) {
            item {
                Spacer(modifier = Modifier.height(12.dp))
                AptvSectionHeader(stringResource(R.string.info_recent_played))
                Spacer(modifier = Modifier.height(8.dp))
            }
            items(recentLocal) { channel ->
                val idx = channels.indexOfFirst { it.url == channel.url }
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 2.dp)
                        .tvFocusBorder(cornerRadius = 10)
                        .clickable { if (idx >= 0) viewModel.playChannel(idx) }
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.Movie,
                            contentDescription = null,
                            tint = AptvAccent,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(
                            text = channel.name,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 13.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )
                        Icon(
                            Icons.Default.PlayArrow,
                            contentDescription = stringResource(R.string.cd_play),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                }
            }
        }
    }
}



// -----------------------------------------------------------------
// 分类列表（竖屏 Tab — 全屏分组选择）
@Composable
internal fun PortraitCategoryContent(viewModel: AppViewModel, onGroupSelected: () -> Unit = {}) {
    val allGroups by viewModel.groups.collectAsState()
    val selectedGroup by viewModel.selectedGroup.collectAsState()
    val channels by viewModel.channels.collectAsState()
    val channelsTab by viewModel.channelsTab.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()

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

    // 计算每个分组的频道数
    val groupCounts = remember(groups, channels, channelsTab) {
        groups.associateWith { g ->
            if (channelsTab == ChannelTab.LOCAL) {
                channels.count { it.group == g && (it.source.isEmpty() || ProgressHelper.isLocalFile(it.url)) }
            } else {
                channels.count { it.group == g }
            }
        }
    }
    val totalCount = channels.size

    // APTV 风格：圆角分组卡 + AptvAccent 选中高亮（浅红底 + 红字）
    AptvGroupCard(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 4.dp)
        ) {
            item {
                val isSelected = selectedGroup.isEmpty()
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(if (isSelected) Modifier.background(AptvAccent.copy(alpha = 0.12f), RoundedCornerShape(8.dp)) else Modifier)
                        .tvFocusBorder(cornerRadius = 8)
                        .clickable { viewModel.setSelectedGroup(""); onGroupSelected() }
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "全部",
                        color = if (isSelected) AptvAccent else MaterialTheme.colorScheme.onSurface,
                        fontSize = 15.sp,
                        fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = "$totalCount",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                }
            }
            items(groups, key = { it }) { group ->
                val isSelected = selectedGroup == group
                val count = groupCounts[group] ?: 0
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .then(if (isSelected) Modifier.background(AptvAccent.copy(alpha = 0.12f), RoundedCornerShape(8.dp)) else Modifier)
                        .tvFocusBorder(cornerRadius = 8)
                        .clickable { viewModel.setSelectedGroup(group); onGroupSelected() }
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = group,
                        color = if (isSelected) AptvAccent else MaterialTheme.colorScheme.onSurface,
                        fontSize = 15.sp,
                        fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        text = "$count",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 频道列表（竖屏 Tab — 仅频道，无分组列）
@Composable
internal fun PortraitChannelOnlyList(viewModel: AppViewModel) {
    val channels by viewModel.channels.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val selectedGroup by viewModel.selectedGroup.collectAsState()
    val channelsTab by viewModel.channelsTab.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()

    // 订阅源加载态：服务端状态 + 本地重载标志，任一为真即视为加载中
    val iptvStatus by viewModel.iptvStatus.collectAsState()
    val localSourceLoading by viewModel.sourceLoading.collectAsState()

    val filteredChannels = remember(channels, selectedGroup, channelsTab) {
        val all = channels.mapIndexed { idx, c -> c to idx }
        val filtered = if (channelsTab == ChannelTab.LOCAL) {
            all.filter { (c, _) -> c.source.isEmpty() || ProgressHelper.isLocalFile(c.url) }
        } else {
            all
        }
        filtered.filter { (c, _) ->
            selectedGroup.isEmpty() || c.group == selectedGroup
        }
    }

    if (filteredChannels.isEmpty()) {
        ChannelEmptyState(
            tab = channelsTab,
            loading = iptvStatus?.sourceLoading == true || localSourceLoading,
            sourceWarning = iptvStatus?.sourceWarning.orEmpty(),
            groupName = if (channelsTab == ChannelTab.SUB) selectedGroup else "",
            onAddSource = { viewModel.toggleSourceManager() },
            onRefresh = { viewModel.reloadSources() }
        )
    } else {
        // 列表 key：以频道 URL 作为稳定身份，频道增删/过滤后组合状态不会错位
        val channelItemKeys = remember(filteredChannels) { buildChannelItemKeys(filteredChannels) }
        val listState = rememberLazyListState()
        LaunchedEffect(filteredChannels, currentIdx) {
            if (currentIdx >= 0) {
                val scrollTarget = filteredChannels.indexOfFirst { (_, idx) -> idx == currentIdx }
                if (scrollTarget >= 0) {
                    listState.scrollToItem(scrollTarget)
                }
            }
        }
        AptvGroupCard(modifier = Modifier.fillMaxSize()) {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 4.dp)
            ) {
                itemsIndexed(
                    items = filteredChannels,
                    key = { index, _ -> channelItemKeys[index] }
                ) { _, (channel, idx) ->
                    PortraitChannelListItem(
                        channel = channel,
                        channelIdx = idx,
                        isPlaying = idx == currentIdx,

                        viewModel = viewModel,
                        epgCacheVersion = epgCacheVersion,
                        onPlay = { viewModel.playChannel(idx) },
                        onEpg = { viewModel.playChannelAndShowEpg(idx) }
                    )
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// EPG 节目单内容（竖屏 Tab — 日期选择 + 节目列表 + 状态标识）
@Composable
internal fun PortraitEpgContent(viewModel: AppViewModel) {
    val loading by viewModel.epgLoading.collectAsState()
    val currentChannel by viewModel.currentChannel.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val epgCacheVersion by viewModel.epgCacheVersion.collectAsState()
    val playbackState by viewModel.playbackState.collectAsState()
    val oc = rememberPlayerOverlayColors()

    // 使用完整（未截断）的 EPG 数据，而非 trimEpgNearNow 裁剪后的 currentEpg
    val epg = remember(currentIdx, epgCacheVersion) {
        viewModel.getFullEpgForCurrent()
    }

    // 每秒刷新当前时间（用于高亮当前节目）
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000L)
        }
    }

    // 从 EPG 数据中提取所有日期
    val epgDates = remember(epg) {
        epg.mapNotNull { p ->
            val ms = portraitParseTimeMs(p.start, p.startTs)
            if (ms > 0) portraitFormatDate(ms) else null
        }.distinct()
    }

    // 当前选中的日期索引
    var selectedDateIdx by remember { mutableStateOf(0) }
    LaunchedEffect(epgDates.size) {
        if (selectedDateIdx >= epgDates.size) selectedDateIdx = 0
    }

    // 默认选中今天
    LaunchedEffect(epgDates) {
        if (epgDates.isNotEmpty()) {
            val today = portraitFormatDate(System.currentTimeMillis())
            val todayIdx = epgDates.indexOf(today)
            if (todayIdx >= 0) selectedDateIdx = todayIdx
        }
    }

    val selectedDate = if (epgDates.isNotEmpty() && selectedDateIdx < epgDates.size) epgDates[selectedDateIdx] else ""

    // 按日期过滤节目
    val filteredEpg = remember(epg, selectedDate) {
        if (selectedDate.isEmpty()) epg
        else epg.filter { p ->
            val ms = portraitParseTimeMs(p.start, p.startTs)
            if (ms > 0) portraitFormatDate(ms) == selectedDate else false
        }
    }

    // 回看模式下高亮选定的节目，否则高亮当前时间的节目
    val catchupProgram = playbackState.catchupProgram?.program
    val currentProgramIdx = remember(filteredEpg, now, catchupProgram) {
        if (catchupProgram != null) {
            filteredEpg.indexOfFirst { p -> p.start == catchupProgram.start && p.title == catchupProgram.title }
        } else {
            filteredEpg.indexOfFirst { p -> portraitIsCurrentProgram(p, now) }
        }
    }

    val epgListState = rememberLazyListState()
    // 自动滚动到当前/回看节目
    LaunchedEffect(currentProgramIdx, filteredEpg) {
        if (currentProgramIdx >= 0) {
            epgListState.scrollToItem(currentProgramIdx.coerceAtMost(filteredEpg.size - 1))
        }
    }

    // 日期选择器滚动状态
    val dateScrollState = rememberLazyListState()
    // 选中日期变化时滚动使选中项居中
    LaunchedEffect(selectedDateIdx, epgDates) {
        if (epgDates.isNotEmpty() && selectedDateIdx < epgDates.size) {
            dateScrollState.animateScrollToItem(selectedDateIdx)
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // APTV 节目单头部：标题 + 正在播放（红色高亮节目与时段）
        val nowPlayingProgram = if (catchupProgram != null) catchupProgram
            else epg.firstOrNull { portraitIsCurrentProgram(it, now) }
        if (nowPlayingProgram != null) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 14.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.epg_program_title),
                    color = oc.textPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(modifier = Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = "${stringResource(R.string.epg_now_playing)}：${nowPlayingProgram.title}",
                        color = AptvAccent,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis
                    )
                    Text(
                        text = "${portraitFormatTime(nowPlayingProgram.start)} - ${portraitFormatTime(nowPlayingProgram.stop.ifEmpty { nowPlayingProgram.end })}",
                        color = AptvAccent,
                        fontSize = 11.sp
                    )
                }
            }
        }
        when {
            loading -> {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(stringResource(R.string.epg_loading), color = oc.textSecondary, fontSize = 13.sp)
                }
            }
            epg.isEmpty() -> {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(stringResource(R.string.epg_no_info), color = oc.textSecondary, fontSize = 13.sp)
                }
            }
            else -> {
                // 日期选择器（上方水平滚动）
                if (epgDates.isNotEmpty()) {

                    LazyRow(
                        state = dateScrollState,
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(oc.infoBarBg)
                            .padding(vertical = 2.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        contentPadding = PaddingValues(horizontal = 4.dp)
                    ) {
                        items(epgDates.size) { idx ->
                            val isSelected = idx == selectedDateIdx
                            val dateLabel = portraitDateLabel(epgDates[idx], now)
                            Surface(
                                color = if (isSelected) oc.accent.copy(alpha = 0.15f) else Color.Transparent,
                                shape = RoundedCornerShape(6.dp),
                                modifier = Modifier.tvFocusBorder(cornerRadius = 6).clickable { selectedDateIdx = idx }
                            ) {
                                Text(
                                    text = dateLabel,
                                    color = if (isSelected) oc.accent else oc.textSecondary,
                                    fontSize = 11.sp,
                                    fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal,
                                    maxLines = 1,
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                                )
                            }
                        }
                    }
                    Box(modifier = Modifier.fillMaxWidth().height(1.dp).background(oc.divider))
                }
                // 节目列表
                AptvGroupCard(modifier = Modifier.fillMaxSize()) {
                    LazyColumn(
                        state = epgListState,
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(filteredEpg) { program ->
                            val programIdx = filteredEpg.indexOf(program)
                            val isCurrent = programIdx == currentProgramIdx
                            val isPast = portraitIsPastProgram(program, now)
                            val isUpcoming = !isCurrent && !isPast
                            PortraitEpgItem(
                                program = program,
                                isCurrent = isCurrent,
                                isPast = isPast,
                                isUpcoming = isUpcoming,
                                oc = oc,
                                onClick = {
                                    if (isPast && !isCurrent) {
                                        viewModel.startCatchup(program)
                                    } else {
                                        viewModel.toggleReminder(program, currentChannel)
                                    }
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}
@Composable
private fun PortraitEpgItem(
    program: com.iptv.scanner.editor.pro.data.IptvEpgProgram,
    isCurrent: Boolean,
    isPast: Boolean,
    isUpcoming: Boolean,
    oc: PlayerOverlayColors,
    onClick: () -> Unit
) {
    val bg = if (isCurrent) oc.accent.copy(alpha = 0.15f) else Color.Transparent
    val alpha = if (isPast && !isCurrent) 0.5f else 1f
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(bg)
            .tvFocusBorder(cornerRadius = 8)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // 时间
        val timeText = buildString {
            append(portraitFormatTime(program.start))
            if (program.stop.isNotEmpty() || program.end.isNotEmpty()) {
                append(" - ")
                append(portraitFormatTime(program.stop.ifEmpty { program.end }))
            }
        }
        Text(
            text = portraitFormatTime(program.start),
            color = AptvAccent,
            fontSize = 13.sp,
            fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Medium,
            modifier = Modifier.width(56.dp)
        )
        // 节目标题
        Text(
            text = program.title,
            color = if (isCurrent) oc.textPrimary else oc.textSecondary,
            fontSize = 13.sp,
            fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        // 右侧状态标识（APTV 风格：圆角胶囊 badge）
        val statusText = when {
            isCurrent -> stringResource(R.string.epg_status_live)
            isPast -> stringResource(R.string.epg_status_catchup)
            isUpcoming -> stringResource(R.string.epg_status_upcoming)
            else -> ""
        }
        if (statusText.isNotEmpty()) {
            val badgeColor = when {
                isCurrent -> AptvAccent
                isPast -> tvPalette.accentBase
                else -> oc.textSecondary
            }
            Surface(
                color = badgeColor.copy(alpha = 0.15f),
                shape = RoundedCornerShape(4.dp),
                modifier = Modifier.padding(start = 6.dp)
            ) {
                Text(
                    text = statusText,
                    color = badgeColor,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                )
            }
        }
    }
}
@Composable
internal fun PortraitRecentLocalFiles(viewModel: AppViewModel) {
    val channels by viewModel.channels.collectAsState()
    val history by viewModel.history.collectAsState()

    val recentLocal = remember(history, channels) {
        history.mapNotNull { idx -> channels.getOrNull(idx) }
            .filter { it.source.isEmpty() || ProgressHelper.isLocalFile(it.url) }
            .take(20)
    }

    if (recentLocal.isEmpty()) {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(stringResource(R.string.no_recent_local_files), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        }
    } else {
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(recentLocal) { channel ->
                val idx = channels.indexOfFirst { it.url == channel.url }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .tvFocusBorder(cornerRadius = 8)
                        .clickable { if (idx >= 0) viewModel.playChannel(idx) }
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Default.PlayCircle,
                        contentDescription = null,
                        tint = AptvAccent,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = channel.name,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 14.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = channel.url.substringAfterLast("/"),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 播放信息面板（竖屏播放页 Tab）
// 布局：顶部频谱（免开可视化面板即看）+ 两列紧凑信息网格，
// 全部字段中文翻译，面板高度内完整展示无需滑动
@Composable
internal fun PortraitPlayerInfoPanel(
    viewModel: AppViewModel,
    duration: Double,
    timePos: Double,
    videoWidth: Int,
    videoHeight: Int
) {
    val player = viewModel.mpv

    // 获取媒体信息
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(2000L)
        }
    }
    val mediaInfo = remember(tick) { player.getMediaInfo() }

    // 频谱：信息 Tab 打开期间持续采样（离开 Tab 停止）。
    // RECORD_AUDIO 是系统 Visualizer 的硬性要求：未授权时主动弹申请，
    // 此前仅「已授权才启动」导致从未授权的设备频谱恒为零（一排不动的矮条）
    val spectrum by viewModel.audioSpectrum.collectAsState()
    val context = androidx.compose.ui.platform.LocalContext.current
    val spectrumPermLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) viewModel.startSpectrumSampling()
        else viewModel.setAudioSpectrumError("未授予麦克风权限\n系统 Visualizer 接口需要该权限才能获取真实频谱")
    }
    DisposableEffect(Unit) {
        val granted = androidx.core.content.ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.RECORD_AUDIO
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        if (granted) viewModel.startSpectrumSampling()
        else spectrumPermLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
        onDispose { viewModel.stopSpectrumSampling() }
    }

    // ---- 值格式化 ----
    val fmtBitrate: (String?) -> String? = { v ->
        v?.takeIf { it.isNotEmpty() && it != "null" && it != "0" }?.let {
            it.toLongOrNull()?.let { b ->
                if (b > 1_000_000) String.format("%.1f Mbps", b / 1e6) else "${b / 1000} kbps"
            } ?: it
        }
    }
    val fmtSec: (String?) -> String? = { v ->
        v?.takeIf { it.isNotEmpty() && it != "null" }?.let {
            it.toDoubleOrNull()?.let { s -> String.format("%.1f s", s) } ?: it
        }
    }

    // ---- 翻译后的字段列表（label to value，空值跳过）----
    fun v(key: String): String? =
        mediaInfo[key]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" && it != "0.000" }

    val playbackRows = listOf(
        "分辨率" to if (videoWidth > 0) "${videoWidth}×${videoHeight}" else "未知",
        "时长" to formatTime(duration),
        "当前位置" to formatTime(timePos),
        "进度" to (if (duration > 0) "${(timePos / duration * 100).toInt()}%" else "0%")
    )
    val mediaRows = listOfNotNull(
        v("videoCodec")?.let { "视频编码" to it.uppercase() },
        v("audioCodec")?.let { "音频编码" to it.uppercase() },
        v("fps")?.let { "帧率" to (it.toFloatOrNull()?.let { f -> if (f == f.toInt().toFloat()) "${f.toInt()}" else String.format("%.2f", f) } ?: it) },
        v("displayFps")?.let { "屏幕刷新" to String.format("%.1f", it.toDoubleOrNull() ?: 0.0) },
        fmtBitrate(v("bitrate"))?.let { "视频码率" to it },
        fmtBitrate(v("audioBitrate"))?.let { "音频码率" to it },
        fmtSec(v("cacheDuration"))?.let { "缓冲时长" to it },
        v("avdiff")?.let { "音画偏移" to (it.toDoubleOrNull()?.let { d -> String.format("%.0f ms", d * 1000) } ?: it) },
        v("containerFormat")?.let { "封装格式" to it.uppercase() },
        mediaInfo["hwdec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { "解码方式" to if (it == "no") "软解" else "硬解(${it})" },
        v("vo")?.let { "视频输出" to it },
        v("pixelFormat")?.let { "像素格式" to it },
        v("colorspace")?.let { "色彩空间" to it.uppercase() },
        v("videoPrimaries")?.let { "色彩域" to it.uppercase() },
        v("videoGamma")?.let { "传输特性" to when (it) { "pq" -> "PQ(HDR10)"; "hlg" -> "HLG"; else -> it.uppercase() } },
        v("videoColorRange")?.let { "色彩范围" to when (it) { "limited" -> "Limited"; "full" -> "Full"; else -> it } },
        // 音频细节
        v("audioSampleRate")?.let { "采样率" to (it.toDoubleOrNull()?.let { hz -> String.format("%.1f kHz", hz / 1000) } ?: it) },
        v("audioChannels")?.let { "声道" to when (it.lowercase()) { "stereo" -> "立体声"; "mono" -> "单声道"; else -> it } },
        // 流元数据（MPEGTS 广播信息）
        v("serviceName")?.let { "电视台" to it },
        v("serviceProvider")?.let { "运营商" to it },
        v("trackCount")?.let { "轨道数" to it }
    )

    // 网络与渲染性能
    val networkRows = listOfNotNull(
        v("droppedFrames")?.let { "解码丢帧" to "$it 帧" },
        v("renderFps")?.let { "实际帧率" to String.format("%.1f", it.toDoubleOrNull() ?: 0.0) },
        v("cacheSpeed")?.let { "缓存速度" to (it.toDoubleOrNull()?.let { b -> String.format("%.0f KB/s", b / 1024) } ?: it) },
        v("mediaTitle")?.let { "流标题" to it }
    )

    /** 两列信息网格：一行两项，紧凑无滑动 */
    @Composable
    fun TwoColGrid(rows: List<Pair<String, String>>) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            rows.chunked(2).forEach { pair ->
                Row(modifier = Modifier.fillMaxWidth()) {
                    pair.forEach { (label, value) ->
                        Row(
                            modifier = Modifier.weight(1f),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "$label ",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp,
                                maxLines = 1
                            )
                            Text(
                                text = value,
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                    if (pair.size == 1) Spacer(modifier = Modifier.weight(1f))
                }
            }
        }
    }

    AptvGroupCard(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            // 顶部频谱区（玻璃卡内嵌：经典频谱仪样式）；
            // 真频谱不可用（如拒绝麦克风权限）时显示原因，不画误导性的静态条
            val spectrumError by viewModel.audioSpectrumError.collectAsState()
            if (spectrumError.isNotEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(96.dp)
                        .background(
                            MaterialTheme.colorScheme.surface,
                            shape = RoundedCornerShape(10.dp)
                        )
                        .clip(RoundedCornerShape(10.dp)),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = spectrumError,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        modifier = Modifier.padding(horizontal = 12.dp)
                    )
                }
            } else SpectrumCanvas(
                spectrum = spectrum,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(96.dp)
                    .background(
                        MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(10.dp)
                    )
                    .clip(RoundedCornerShape(10.dp))
            )

            Text(
                text = stringResource(R.string.info_playback),
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.Bold
            )
            TwoColGrid(playbackRows)

            Text(
                text = stringResource(R.string.info_media_info),
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.onSurface,
                fontWeight = FontWeight.Bold
            )
            TwoColGrid(mediaRows)

            if (networkRows.isNotEmpty()) {
                Text(
                    text = "网络与性能",
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold
                )
                TwoColGrid(networkRows)
            }
        }
    }
}

// -----------------------------------------------------------------
// 工具内容（竖屏 Tab）
