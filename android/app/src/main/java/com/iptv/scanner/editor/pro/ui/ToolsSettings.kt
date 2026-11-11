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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AspectRatio
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Brightness4
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CropFree
import androidx.compose.material.icons.filled.Devices
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.movableContentOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
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
import kotlinx.coroutines.launch
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
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
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
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.WifiTethering
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Bookmarks
import androidx.compose.material.icons.filled.AvTimer
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material.icons.filled.Subtitles
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Wallpaper
import androidx.compose.material.icons.filled.CloudSync
import androidx.compose.material.icons.filled.CompareArrows
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.SwapHoriz
import java.io.File

// -----------------------------------------------------------------

// 工具页（APTV 配置中心式：源卡片 + 文件/工具/高级 分组）
// -----------------------------------------------------------------

@Composable
internal fun PortraitToolsScreen(
    viewModel: AppViewModel,
    playlistLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>,
    videoLauncher: androidx.activity.result.ActivityResultLauncher<Array<String>>
) {
    val sources by viewModel.sources.collectAsState()
    val epgSources by viewModel.epgSources.collectAsState()
    val channels by viewModel.channels.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    // 横屏（TV/平板）首页：面板入口走右侧详情路由（master-detail），竖屏走弹窗
    val isLandscape = androidx.compose.ui.platform.LocalConfiguration.current.orientation ==
        android.content.res.Configuration.ORIENTATION_LANDSCAPE

    LaunchedEffect(Unit) {
        viewModel.loadSources()
        viewModel.loadEpgSources()
    }

    // 底栏 TAB 的 UP 需要落点：把工具页首项（本地频道卡）注册为内容区焦点入口
    val entryFocus = remember { FocusRequester() }
    DisposableEffect(Unit) {
        HomeContentFocusEntry.register(PortraitTab.TOOLS, entryFocus)
        onDispose { HomeContentFocusEntry.unregister(PortraitTab.TOOLS, entryFocus) }
    }

    // 与设置页一致：玻璃卡片组件读取 LocalLiquidGlass，需在本页提供开关值
    androidx.compose.runtime.CompositionLocalProvider(LocalLiquidGlass provides liquidGlass) {
    // 编辑模式（APTV 配置中心：编辑态显示删除按钮）
    var editMode by remember { mutableStateOf(false) }
    var deleteTargetIdx by remember { mutableStateOf(-1) }
    var deleteEpgIdx by remember { mutableStateOf(-1) }
    var showAddForm by remember { mutableStateOf(false) }
    var newUrl by remember { mutableStateOf("") }
    var newName by remember { mutableStateOf("") }
    var showEpgAddForm by remember { mutableStateOf(false) }
    var newEpgUrl by remember { mutableStateOf("") }
    var newEpgName by remember { mutableStateOf("") }
    val toolsScrollState = rememberScrollState()

    // EPG 表单展开后「添加」按钮会落到悬浮底部 Tab 栏下面，不滑动点不到：
    // 展开时等布局完成再把页面滚到底（末尾已有 130dp 占位，按钮会移到 Tab 栏上方）
    LaunchedEffect(showEpgAddForm) {
        if (showEpgAddForm) {
            kotlinx.coroutines.delay(100)
            toolsScrollState.animateScrollTo(toolsScrollState.maxValue)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            // 不铺不透明底：透出内容区的环境画布（深/浅渐变+光斑）
            .verticalScroll(toolsScrollState)
    ) {
        // 头部：编辑（左） + 刷新/添加（右）
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 编辑/完成：玻璃胶囊按钮（与右侧刷新钮同风格）
            AptvGlassChip(cornerRadius = 16.dp) {
                Text(
                    text = if (editMode) "完成" else stringResource(R.string.settings_edit),
                    color = tvPalette.accentText,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier
                        .tvFocusBorder(cornerRadius = 12)
                        .clickable { editMode = !editMode }
                        .padding(horizontal = 14.dp, vertical = 7.dp)
                )
            }
            Spacer(modifier = Modifier.weight(1f))
            // 刷新源与频道：玻璃圆形按钮
            AptvGlassChip(cornerRadius = 16.dp, modifier = Modifier.size(32.dp).tvFocusBorder(cornerRadius = 16, focusedScale = 1.18f)) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .clickable {
                            viewModel.loadSources()
                            viewModel.loadEpgSources()
                            viewModel.loadChannels()
                        },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        Icons.Default.Refresh,
                        contentDescription = "刷新源与频道",
                        tint = tvPalette.accentGraphic,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }

        }
        Text(
            text = stringResource(R.string.aptv_config_center),
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 26.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 16.dp)
        )


        // 本地频道卡（固定第一）
        AptvSectionHeader(stringResource(R.string.aptv_group_local))
        AptvGroupCard {
            val localCount = channels.count { it.source.isEmpty() }
            Row(
                modifier = Modifier
                    .focusRequester(entryFocus)
                    .fillMaxWidth()
                    .tvFocusBorder(cornerRadius = 10)
                    .clickable {
                        viewModel.setListSourceTab(ListSourceTab.LOCAL)
                        viewModel.setPortraitTab(PortraitTab.CHANNELS)
                    }
                    .padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(RoundedCornerShape(9.dp))
                        .background(tvPalette.accentFill),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Folder, contentDescription = null, tint = tvPalette.accentOn, modifier = Modifier.size(19.dp))
                }
                Spacer(modifier = Modifier.width(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(stringResource(R.string.tools_local_channels), color = MaterialTheme.colorScheme.onSurface, fontSize = 15.sp)
                    Text(
                        stringResource(R.string.aptv_channels_count, localCount),
                        color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp
                    )
                }
                Icon(
                    Icons.Default.ChevronRight, contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.55f),
                    modifier = Modifier.size(18.dp)
                )
            }
        }

        // 订阅源卡片（APTV 配置中心样式：名称/频道数/启停/删除）
        AptvSectionHeader(stringResource(R.string.aptv_group_sources))
        AptvGroupCard {
            if (sources.isEmpty()) {
                Text(
                    text = stringResource(R.string.aptv_no_sources),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp)
                )
            }
            sources.forEachIndexed { idx, s ->
                val name = s.name.ifEmpty { s.url.substringAfterLast('/').take(28) }
                val count = channels.count { it.source == s.url }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .tvFocusBorder(cornerRadius = 10)
                        .clickable(enabled = !editMode) {
                            viewModel.setListSourceTab(ListSourceTab.SUBSCRIPTION)
                            viewModel.setSelectedSource(s.url)
                            viewModel.setPortraitTab(PortraitTab.CHANNELS)
                        }
                        .padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            name,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 15.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                stringResource(R.string.aptv_channels_count, count),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Icon(
                                Icons.Default.CheckCircle,
                                contentDescription = null,
                                tint = if (s.enabled) tvPalette.success else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                                modifier = Modifier.size(13.dp)
                            )
                        }
                    }
                    // 启停开关（APTV 配置的启停语义）
                    androidx.compose.material3.Switch(
                        checked = s.enabled,
                        onCheckedChange = { viewModel.toggleSourceEnabled(idx, it) },
                        modifier = Modifier
                            .tvFocusBorder(cornerRadius = 14, focusedScale = 1.2f)
                            .padding(end = 4.dp)
                    )
                    // 编辑模式：删除
                    if (editMode) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "删除订阅源",
                            tint = MaterialTheme.colorScheme.error,
                            modifier = Modifier
                                .size(22.dp)
                                .tvFocusBorder(cornerRadius = 11, focusedScale = 1.25f)
                                .clickable { deleteTargetIdx = idx }
                        )
                    }
                }
            }
            // 添加订阅源（与 EPG 源统一：卡片内底部行）
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .tvFocusBorder(cornerRadius = 10)
                    .clickable { showAddForm = !showAddForm }
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Default.Add,
                    contentDescription = null,
                    tint = tvPalette.accentGraphic,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    "添加订阅源",
                    color = tvPalette.accentText,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium
                )
            }
            if (showAddForm) {
                androidx.compose.material3.TextField(
                    value = newUrl,
                    onValueChange = { newUrl = it },
                    placeholder = { Text("输入 M3U 订阅源 URL", fontSize = 14.sp) },
                    singleLine = true,
                    colors = androidx.compose.material3.TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = tvPalette.accentText
                    ),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp
                    ),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp).tvTextField()
                )
                androidx.compose.material3.TextField(
                    value = newName,
                    onValueChange = { newName = it },
                    placeholder = { Text("名称（可选）", fontSize = 14.sp) },
                    singleLine = true,
                    colors = androidx.compose.material3.TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = tvPalette.accentText
                    ),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp
                    ),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp).tvTextField()
                )
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.End
                ) {
                    Text(
                        text = stringResource(R.string.aptv_action_add),
                        color = tvPalette.accentText,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier
                            .tvFocusBorder(cornerRadius = 12)
                            .clickable {
                                viewModel.addSource(newUrl.trim(), newName.trim())
                                newUrl = ""
                                newName = ""
                                showAddForm = false
                            }
                            .padding(horizontal = 12.dp, vertical = 6.dp)
                    )
                }
            }
        }

        // EPG 源（APTV 配置中心：订阅 EPG 的增删）
        AptvSectionHeader(stringResource(R.string.aptv_group_epg))
        AptvGroupCard {
            if (epgSources.isEmpty()) {
                Text(
                    text = stringResource(R.string.aptv_no_epg_sources),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp)
                )
            }
            epgSources.forEachIndexed { idx, e ->
                val name = e.name.ifEmpty { e.url.substringAfterLast('/').take(28) }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            name,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 15.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = (e.lastUpdate ?: stringResource(R.string.aptv_epg_not_updated))
                                .take(24),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp
                        )
                    }
                    if (editMode) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "删除 EPG 源",
                            tint = MaterialTheme.colorScheme.error,
                            modifier = Modifier
                                .size(22.dp)
                                .tvFocusBorder(cornerRadius = 11, focusedScale = 1.25f)
                                .clickable { deleteEpgIdx = idx }
                        )
                    }
                }
            }
            // 内联添加 EPG 源
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .tvFocusBorder(cornerRadius = 10)
                    .clickable { showEpgAddForm = !showEpgAddForm }
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Default.Add,
                    contentDescription = null,
                    tint = tvPalette.accentGraphic,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    stringResource(R.string.aptv_add_epg),
                    color = tvPalette.accentText,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium
                )
            }
            if (showEpgAddForm) {
                androidx.compose.material3.TextField(
                    value = newEpgUrl,
                    onValueChange = { newEpgUrl = it },
                    placeholder = { Text(stringResource(R.string.aptv_epg_url_hint), fontSize = 14.sp) },
                    singleLine = true,
                    colors = androidx.compose.material3.TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = tvPalette.accentText
                    ),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp
                    ),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp).tvTextField()
                )
                androidx.compose.material3.TextField(
                    value = newEpgName,
                    onValueChange = { newEpgName = it },
                    placeholder = { Text(stringResource(R.string.aptv_epg_name_hint), fontSize = 14.sp) },
                    singleLine = true,
                    colors = androidx.compose.material3.TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = tvPalette.accentText
                    ),
                    textStyle = androidx.compose.ui.text.TextStyle(
                        color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp
                    ),
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp).tvTextField()
                )
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.End
                ) {
                    Text(
                        text = stringResource(R.string.aptv_action_add),
                        color = tvPalette.accentText,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier
                            .tvFocusBorder(cornerRadius = 12)
                            .clickable {
                                viewModel.addEpgSource(newEpgUrl.trim(), newEpgName.trim())
                                newEpgUrl = ""
                                newEpgName = ""
                                showEpgAddForm = false
                            }
                            .padding(horizontal = 12.dp, vertical = 6.dp)
                    )
                }
            }
        }

        // 频道工具（扫描/导出等与频道内容相关的操作）
        AptvSectionHeader(stringResource(R.string.aptv_group_channel_tools))
        AptvGroupCard {
            AptvRow(Icons.Default.WifiTethering, stringResource(R.string.tools_url_scan), stringResource(R.string.tools_url_scan_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.scanPanelOpen, { ScanPanel(viewModel = viewModel) }) { viewModel.toggleScanPanel() }
            }
            AptvRow(Icons.Default.Save, stringResource(R.string.tools_save_as_m3u), stringResource(R.string.tools_save_as_m3u_desc)) {
                viewModel.saveAsM3u()
            }
            AptvRow(Icons.Default.CompareArrows, stringResource(R.string.settings_mapping), stringResource(R.string.settings_mapping_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.mappingPanelOpen, { MappingPanel(viewModel = viewModel) }) { viewModel.toggleMappingPanel() }
            }
            AptvRow(Icons.Default.Wifi, stringResource(R.string.settings_network), stringResource(R.string.settings_network_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.networkPanelOpen, { NetworkPanel(viewModel = viewModel) }) { viewModel.toggleNetworkPanel() }
            }
        }

        // 文件分组（原工具功能保留，入口移到此处）
        AptvSectionHeader(stringResource(R.string.tools_file))
        AptvGroupCard {
            AptvRow(Icons.Default.VideoLibrary, stringResource(R.string.tools_open_local_file), stringResource(R.string.tools_open_local_file_desc)) {
                if (!viewModel.isSafAvailable()) viewModel.showMediaFileBrowser()
                else videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
            }
            AptvRow(Icons.Default.PlaylistAdd, stringResource(R.string.tools_open_playlist), stringResource(R.string.tools_open_playlist_desc)) {
                if (!viewModel.isSafAvailable()) viewModel.showFileBrowser()
                else playlistLauncher.launch(arrayOf(
                    "application/x-mpegurl", "application/vnd.apple.mpegurl",
                    "audio/x-mpegurl", "video/x-mpegurl",
                    "text/plain", "application/octet-stream"
                ))
            }
            AptvRow(Icons.Default.Link, stringResource(R.string.tools_open_network_stream), stringResource(R.string.tools_open_network_stream_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.openUrlDialogOpen, { OpenUrlPanelContent(viewModel) }) { viewModel.toggleOpenUrlDialog() }
            }
            AptvRow(Icons.Default.History, stringResource(R.string.tools_recent), stringResource(R.string.tools_recent_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.recentPanelOpen, { RecentFilesPanel(viewModel = viewModel) }) { viewModel.toggleRecentPanel() }
            }
        }

        // 播放工具（截图/切片/EPG时间轴/搜索/提醒等，播放时也可从控制浮层进入）
        AptvSectionHeader(stringResource(R.string.aptv_group_player_tools))
        AptvGroupCard {
            AptvRow(Icons.Default.Tune, stringResource(R.string.aptv_player_tools), stringResource(R.string.aptv_player_tools_desc)) {
                splitDetailOrToggle(isLandscape, viewModel.playerToolsOpen, { PlayerToolsPanel(viewModel = viewModel) }) { viewModel.togglePlayerToolsPanel() }
            }
        }

        Spacer(modifier = Modifier.height(130.dp))
    }

    // 删除确认（频道源 / EPG 源）— iOS 风格圆角卡片弹窗
    if (deleteTargetIdx >= 0) {
        AptvAlertDialog(
            title = stringResource(R.string.aptv_delete_source_title),
            message = stringResource(R.string.aptv_delete_source_confirm),
            confirmText = stringResource(R.string.aptv_action_delete),
            dismissText = stringResource(R.string.aptv_action_cancel),
            destructive = true,
            onConfirm = {
                viewModel.deleteSource(deleteTargetIdx)
                deleteTargetIdx = -1
            },
            onDismiss = { deleteTargetIdx = -1 }
        )
    }
    if (deleteEpgIdx >= 0) {
        AptvAlertDialog(
            title = stringResource(R.string.aptv_delete_epg_title),
            message = stringResource(R.string.aptv_delete_epg_confirm),
            confirmText = stringResource(R.string.aptv_action_delete),
            dismissText = stringResource(R.string.aptv_action_cancel),
            destructive = true,
            onConfirm = {
                viewModel.deleteEpgSource(deleteEpgIdx)
                deleteEpgIdx = -1
            },
            onDismiss = { deleteEpgIdx = -1 }
        )
    }
    }   // CompositionLocalProvider（液态玻璃开关）闭合
}


// -----------------------------------------------------------------
// 设置内容（竖屏 Tab，APTV/iOS 分组卡片式）
@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun PortraitSettingsContent(viewModel: AppViewModel) {
    val themeMode by viewModel.themeMode.collectAsState()
    val autoResume by viewModel.autoResume.collectAsState()
    val playerType by viewModel.playerType.collectAsState()
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val bootStart by viewModel.bootStart.collectAsState()
    val bottomBarStyle by viewModel.bottomBarStyle.collectAsState()
    val screenSaverEnabled by viewModel.screenSaverEnabled.collectAsState()
    val screenSaverTimeout by viewModel.screenSaverTimeoutMinutes.collectAsState()
    val uiModePref by viewModel.uiModePref.collectAsState()
    val currentUiMode by viewModel.uiMode.collectAsState()
    val isMpv = playerType == PlayerType.MPV
    // 横屏（TV/平板）首页：面板入口走右侧详情路由（master-detail），竖屏走弹窗
    val isLandscape = androidx.compose.ui.platform.LocalConfiguration.current.orientation ==
        android.content.res.Configuration.ORIENTATION_LANDSCAPE

    // 底栏 TAB 的 UP 落点 + 详情关闭后的焦点回归：设置列表每一行都挂 FocusRequester。
    // - 底栏居中悬浮、正上方是 Mini 播放条，几何 UP 永远只会回到播放条，入口必须显式注册；
    // - BACK 关闭右侧详情后，焦点回到「进入详情前那一行」，而不是永远回第一项。
    val rowFocuses = remember { List(18) { FocusRequester() } }
    val rowBrings = remember { List(18) { BringIntoViewRequester() } }
    var lastFocusedRow by remember { mutableStateOf(0) }
    val scrollScope = rememberCoroutineScope()
    // 行序号：0-5 通用（主题/界面模式/续播/底栏样式/玻璃/自启），6-12 播放，13-14 频道，15-16 屏保，17 关于
    // 显式接管上下键：目标行在可视区外时几何焦点搜索命中不了（整列滚动的视口外节点），
    // 只靠 bringIntoView 会「先要焦点再滚动」形成死锁，到了「视图设置」就停住。
    fun moveRowFocus(from: Int, dir: Int) {
        scrollScope.launch {
            var target = from + dir
            while (target in rowFocuses.indices) {
                val moved = runCatching {
                    rowBrings[target].bringIntoView()
                    rowFocuses[target].requestFocus()
                }.isSuccess
                if (moved) return@launch
                target += dir
            }
        }
    }
    fun rowModifier(index: Int): Modifier = Modifier
        .focusRequester(rowFocuses[index])
        .bringIntoViewRequester(rowBrings[index])
        .onFocusChanged {
            if (it.isFocused) {
                lastFocusedRow = index
                // 行比窗口高时，方向键移动后把该行滚进可视区
                scrollScope.launch { rowBrings[index].bringIntoView() }
            }
        }
        .onPreviewKeyEvent { ev ->
            if (ev.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
            val dir = when (ev.key) {
                Key.DirectionDown -> 1
                Key.DirectionUp -> -1
                else -> return@onPreviewKeyEvent false
            }
            if (index + dir !in rowFocuses.indices) return@onPreviewKeyEvent false
            moveRowFocus(index, dir)
            true
        }
    var contentHasFocus by remember { mutableStateOf(false) }
    var detailWasOpen by remember { mutableStateOf(false) }
    val entryFocus = rowFocuses[0]
    DisposableEffect(Unit) {
        HomeContentFocusEntry.register(PortraitTab.SETTINGS, entryFocus)
        onDispose { HomeContentFocusEntry.unregister(PortraitTab.SETTINGS, entryFocus) }
    }
    // 右侧详情面板关闭后把焦点还回进入前那一行；已有聚焦项时不抢占
    val detailOpen = LandscapeSplitDetail.stack.isNotEmpty()
    LaunchedEffect(detailOpen) {
        if (detailOpen) {
            detailWasOpen = true
            return@LaunchedEffect
        }
        if (!detailWasOpen) return@LaunchedEffect
        detailWasOpen = false
        // 详情关闭会移除焦点节点、焦点被清空；节点回收有延迟，多次重试避免单次 requestFocus 落空
        delay(60)
        if (contentHasFocus) return@LaunchedEffect
        repeat(10) { attempt ->
            if (attempt > 0) delay(80)
            if (runCatching { rowFocuses[lastFocusedRow].requestFocus() }.isSuccess) {
                return@LaunchedEffect
            }
        }
    }

    androidx.compose.runtime.CompositionLocalProvider(LocalLiquidGlass provides liquidGlass) {
    // 用整列滚动而不是 LazyColumn：设置行数固定（18 行），一次性组合能保证分组之间
    // 没有「尚未组合的间隙」，遥控器 UP/DOWN 可在整列中连续移动；LazyColumn 跨 item
    // 的焦点搜索在未组合区域会断裂，焦点会从「开机自启」直接逃逸到底栏。
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .onFocusChanged { contentHasFocus = it.hasFocus }
    ) {
        Text(
            text = stringResource(R.string.tab_settings),
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 26.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
        )

        AptvSectionHeader(stringResource(R.string.settings_general))
        AptvGroupCard {
                val themeLabel = when (themeMode) { "light" -> stringResource(R.string.settings_theme_light); "system" -> stringResource(R.string.settings_theme_system); else -> stringResource(R.string.settings_theme_dark) }
                AptvRow(
                    Icons.Default.DarkMode,
                    stringResource(R.string.settings_theme),
                    value = themeLabel,
                    modifier = rowModifier(0)
                ) {
                    val next = when (themeMode) { "dark" -> "light"; "light" -> "system"; else -> "dark" }
                    viewModel.setThemeMode(next)
                }
                // 界面模式：自动沿用设备判定，或强制按手机/平板/TV 形态渲染
                AptvRow(
                    Icons.Default.Devices,
                    "界面模式",
                    value = if (uiModePref == UiModePreference.AUTO)
                        "自动 · 当前${currentUiMode.displayName}"
                    else "手动 · 强制${uiModePref.label.removePrefix("强制")}",
                    modifier = rowModifier(1)
                ) {
                    viewModel.setUiModePreference(UiModePreference.next(uiModePref))
                }
                AptvRow(Icons.Default.Replay, stringResource(R.string.settings_auto_resume), value = if (autoResume) stringResource(R.string.settings_enabled) else stringResource(R.string.settings_disabled), modifier = rowModifier(2)) {
                    viewModel.setAutoResume(!autoResume)
                }
                // 横屏全屏播放页底栏布局样式（点击循环切换，右侧迷你预览当前样式结构）
                AptvRow(Icons.Default.AspectRatio, "全屏底栏样式", trailing = {
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = TV_BOTTOM_BAR_STYLES.firstOrNull { it.first == bottomBarStyle }?.second
                                ?: "信息详情式",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        BottomBarStyleMiniPreview(bottomBarStyle, modifier = Modifier.width(88.dp))
                    }
                }, modifier = rowModifier(3)) {
                    viewModel.setBottomBarStyle((bottomBarStyle + 1) % TV_BOTTOM_BAR_STYLES.size)
                }
                AptvSwitchRow(Icons.Default.AutoAwesome, "液态玻璃", checked = liquidGlass, onCheckedChange = { viewModel.setLiquidGlass(it) }, modifier = rowModifier(4))
                AptvSwitchRow(Icons.Default.PowerSettingsNew, "开机自启动", checked = bootStart, onCheckedChange = { viewModel.setBootStart(it) }, modifier = rowModifier(5))
            }

        AptvSectionHeader(stringResource(R.string.settings_playback))
        AptvGroupCard {
            AptvRow(Icons.Default.PlayCircle, stringResource(R.string.settings_player), value = playerType.displayName, modifier = rowModifier(6)) {
                splitDetailOrToggle(isLandscape, viewModel.playerSettingsOpen, { PlayerSettingsPanel(viewModel = viewModel) }) { viewModel.togglePlayerSettings() }
            }
            AptvRow(Icons.Default.Tv, stringResource(R.string.settings_video), modifier = rowModifier(7)) {
                splitDetailOrToggle(isLandscape, viewModel.videoSettingsOpen, { VideoSettingsPanel(viewModel = viewModel) }) { viewModel.toggleVideoSettings() }
            }
            AptvRow(Icons.Default.VolumeUp, stringResource(R.string.settings_audio), modifier = rowModifier(8)) {
                splitDetailOrToggle(isLandscape, viewModel.audioSettingsOpen, { AudioSettingsPanel(viewModel = viewModel) }) { viewModel.toggleAudioSettings() }
            }
            AptvRow(Icons.Default.Subtitles, stringResource(R.string.settings_subtitle), disabled = !isMpv, modifier = rowModifier(9)) {
                splitDetailOrToggle(isLandscape, viewModel.subtitleSettingsOpen, { SubtitleSettingsPanel(viewModel = viewModel) }) { viewModel.toggleSubtitleSettings() }
            }
            AptvRow(Icons.Default.Tune, stringResource(R.string.settings_playback_settings), modifier = rowModifier(10)) {
                splitDetailOrToggle(isLandscape, viewModel.playbackPanelOpen, { PlaybackPanel(viewModel = viewModel) }) { viewModel.togglePlaybackPanel() }
            }
            AptvRow(Icons.Default.PhotoCamera, stringResource(R.string.settings_screenshot), disabled = !isMpv, modifier = rowModifier(11)) {
                splitDetailOrToggle(isLandscape, viewModel.screenshotPanelOpen, { ScreenshotPanel(viewModel = viewModel) }) { viewModel.toggleScreenshotPanel() }
            }
            AptvRow(Icons.Default.Wallpaper, stringResource(R.string.settings_view), modifier = rowModifier(12)) {
                splitDetailOrToggle(isLandscape, viewModel.viewSettingsOpen, { ViewSettingsPanel(viewModel = viewModel) }) { viewModel.toggleViewSettings() }
            }
        }

        AptvSectionHeader(stringResource(R.string.settings_channels))
        AptvGroupCard {
            AptvRow(Icons.Default.CompareArrows, stringResource(R.string.settings_mapping), modifier = rowModifier(13)) {
                splitDetailOrToggle(isLandscape, viewModel.mappingPanelOpen, { MappingPanel(viewModel = viewModel) }) { viewModel.toggleMappingPanel() }
            }
            AptvRow(Icons.Default.Wifi, stringResource(R.string.settings_network), modifier = rowModifier(14)) {
                splitDetailOrToggle(isLandscape, viewModel.networkPanelOpen, { NetworkPanel(viewModel = viewModel) }) { viewModel.toggleNetworkPanel() }
            }
        }

        AptvSectionHeader("屏保")
        AptvGroupCard {
            AptvSwitchRow(
                Icons.Default.Bedtime,
                "屏保",
                checked = screenSaverEnabled,
                onCheckedChange = { viewModel.setScreenSaverEnabled(it) },
                modifier = rowModifier(15)
            )
            AptvRow(
                Icons.Default.Schedule,
                "屏保等待",
                value = "$screenSaverTimeout 分钟",
                disabled = !screenSaverEnabled,
                modifier = rowModifier(16)
            ) {
                val next = when (screenSaverTimeout) {
                    1 -> 5
                    5 -> 10
                    10 -> 30
                    30 -> 60
                    else -> 1
                }
                viewModel.setScreenSaverTimeoutMinutes(next)
            }
        }

        AptvSectionHeader(stringResource(R.string.aptv_group_about))
        AptvGroupCard {
            AptvRow(Icons.Default.Info, stringResource(R.string.settings_about), modifier = rowModifier(17)) {
                splitDetailOrToggle(isLandscape, viewModel.aboutPanelOpen, { AboutPanel(viewModel = viewModel) }) { viewModel.toggleAboutPanel() }
            }
        }
        // 悬浮底栏遮挡预留（原 LazyColumn contentPadding(bottom = 130.dp)）
        Spacer(modifier = Modifier.height(130.dp))
    }
    }
}

// ============================================================
// 竖屏新布局 V2 组件
