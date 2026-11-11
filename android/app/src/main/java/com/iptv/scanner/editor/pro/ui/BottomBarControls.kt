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
import com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface
import com.iptv.scanner.editor.pro.ui.theme.PlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import androidx.media3.ui.PlayerView
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Cast
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
import androidx.compose.material.icons.filled.Language
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import java.io.File

/**
 * 底栏 TAB → 内容区的焦点入口注册表。
 *
 * 底栏是悬浮在内容之上的独立焦点子树，且自身消费 LEFT/RIGHT/DOWN 用于 TAB 循环，
 * 唯一放行的是 UP。但横屏首页里 TAB 栏居中、其正上方是同样居中的 Mini 播放条，
 * 几何搜索的 UP 只会命中 Mini 播放条，内容区（设置/工具列表）永远拿不到焦点。
 * 因此各 TAB 内容在组合时把「首项」的 FocusRequester 注册进来，
 * 底栏 UP 时优先请求该入口；未注册的页（收藏等）保持原来的几何导航。
 * 频道页按渲染形态注册：宫格存在时指向首卡，空态带操作按钮时指向主按钮。
 */
internal object HomeContentFocusEntry {
    private val entries = mutableMapOf<PortraitTab, FocusRequester>()

    fun register(tab: PortraitTab, requester: FocusRequester) {
        entries[tab] = requester
    }

    fun unregister(tab: PortraitTab, requester: FocusRequester) {
        if (entries[tab] === requester) entries.remove(tab)
    }

    /** 入口不可用（未注册/节点未挂载）时返回 false，调用方退回几何搜索 */
    fun request(tab: PortraitTab): Boolean {
        val requester = entries[tab] ?: return false
        return runCatching { requester.requestFocus() }.isSuccess
    }
}

@Composable
internal fun PortraitBottomTabBar(
    viewModel: AppViewModel,
    modifier: Modifier = Modifier,
    centered: Boolean = false
) {
    val portraitTab by viewModel.portraitTab.collectAsState()
    // 直接读开关：MainPlayerScreen 的 LocalLiquidGlass provider 不覆盖 tab 栏子树
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    val bgColor = MaterialTheme.colorScheme.surface
    // APTV 风格竖屏强调色（红粉），不影响横屏/TV 主题
    // 选中 Tab 的文字与图标共用：用 accentText（浅色 #A81C34 / 深色 #FF8A9B），
    // 直接拿 #E8455F 在深色选中胶囊 #404040 上只有 2.69:1
    val accentColor = tvPalette.accentText
    val tabShape = RoundedCornerShape(20.dp)
    val isAndroid12Plus = android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S

    val tabItems = listOf(
        Triple(Icons.Default.Language, stringResource(R.string.tab_home), PortraitTab.CHANNELS),
        Triple(Icons.Default.Favorite, stringResource(R.string.tab_list), PortraitTab.FAVORITES),
        Triple(Icons.Default.Build, stringResource(R.string.tab_tools), PortraitTab.TOOLS),
        Triple(Icons.Default.Settings, stringResource(R.string.tab_settings), PortraitTab.SETTINGS)
    )

    // TV 遥控器 tab 精确切换：每个 tab 一个 FocusRequester + 记录当前焦点索引。
    // 方向键直接按索引循环移动（RIGHT/DOWN=下一个，LEFT=上一个，到端点回绕），
    // 完全绕开几何搜索——修复 moveFocus 在端点清空焦点、或把焦点抢到右侧 EPG 面板的问题。
    val tabFocusRequesters = remember(tabItems.size) { List(tabItems.size) { FocusRequester() } }
    var focusedTabIndex by remember { mutableStateOf(-1) }

    val tabContent: @Composable RowScope.() -> Unit = {
        tabItems.forEachIndexed { index, (icon, label, tab) ->
            val isSelected = portraitTab == tab
            val tint = if (isSelected) accentColor else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.88f)
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .focusRequester(tabFocusRequesters[index])
                    .onFocusChanged { if (it.isFocused) focusedTabIndex = index }
                    .height(54.dp)
                    // TV 焦点放大+白边必须放在 clip 之前（外层）：
                    // 放在 clip 之后放大超出部分会被裁掉，焦点视觉只剩边框没有放大
                    .tvFocusBorder(cornerRadius = 10, focusedScale = 1.10f)
                    .clip(RoundedCornerShape(10.dp))
                    .then(
                        if (isSelected) Modifier
                            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(10.dp))
                            .border(
                                1.dp,
                                MaterialTheme.colorScheme.outline.copy(alpha = 0.65f),
                                RoundedCornerShape(10.dp)
                            )
                            .background(
                                androidx.compose.ui.graphics.Brush.verticalGradient(
                                    0f to tvPalette.glassGloss,
                                    1f to Color.Transparent
                                ),
                                RoundedCornerShape(10.dp)
                            )
                        else Modifier
                    )
                    // TV 遥控器焦点高亮：必须放在 clickable 之前（外层），否则收不到焦点事件
                    // 底栏横向 tab 的按键语义：RIGHT/DOWN=下一个 tab（端点回绕到首页），
                    // LEFT=上一个 tab（回绕到设置）。按索引精确移动焦点。
                    // UP 不放行给几何搜索：横屏首页 TAB 栏居中、正上方是居中的 Mini 播放条，
                    // 几何 UP 只会落回 Mini 播放条形成「播放条↔底栏」死循环，
                    // 改为直接请求内容区注册的首项入口（设置/工具列表）。
                    .onPreviewKeyEvent { ev ->
                        if (ev.type != KeyEventType.KeyDown) {
                            return@onPreviewKeyEvent false
                        }
                        val cur = focusedTabIndex
                        if (cur < 0 || cur >= tabFocusRequesters.size) {
                            return@onPreviewKeyEvent false
                        }
                        when (ev.key) {
                            Key.DirectionRight, Key.DirectionDown ->
                                tabFocusRequesters[(cur + 1) % tabFocusRequesters.size].requestFocus()
                            Key.DirectionLeft ->
                                tabFocusRequesters[(cur - 1 + tabFocusRequesters.size) % tabFocusRequesters.size].requestFocus()
                            // 内容区未注册入口（频道宫格/收藏）时返回 false，保留原来的几何导航
                            Key.DirectionUp -> return@onPreviewKeyEvent HomeContentFocusEntry.request(tab)
                            else -> return@onPreviewKeyEvent false
                        }
                        true
                    }
                    .clickable {
                        viewModel.setPortraitTab(tab)
                    }
                    .padding(horizontal = 18.dp, vertical = 3.dp)
            ) {
                Icon(imageVector = icon, contentDescription = label, tint = tint, modifier = Modifier.size(22.dp))
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = label,
                    color = tint,
                    fontSize = 10.sp,
                    lineHeight = 12.sp,
                    fontWeight = if (isSelected) FontWeight.Medium else FontWeight.Normal
                )
            }
        }
    }

    val useGlass = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported()
    // centered=true：TV/横屏首页用——底部居中悬浮胶囊，只包住 4 个按钮，不占整行；
    // false（默认）：竖屏全宽底栏，含导航栏避让
    val barModifier = if (centered) {
        // 居中胶囊模式：外层 modifier（含父级 align）由包裹 Box 消费，此处从 Modifier 起步避免重复消费
        Modifier
            .widthIn(max = 520.dp)
            .padding(start = 12.dp, end = 12.dp, bottom = 12.dp)
            .height(62.dp)
            .shadow(8.dp, tabShape)
    } else {
        modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp)
            .navigationBarsPadding()
            .padding(bottom = 8.dp)
            .height(62.dp)
            .shadow(8.dp, tabShape)
    }
    val barContent: @Composable () -> Unit = {
        LiquidGlassSurface(
            enabled = useGlass,
            cornerRadius = 20.dp,
            // 真模糊：悬浮于滚动内容之上，hazeEffect 实时取景（HazeState 由 MainPlayerScreen 提供）
            // 关闭/降级：原 90% surface 实底
            fallbackColor = bgColor.copy(alpha = 0.90f),
            modifier = barModifier
        ) {
            Row(
                modifier = Modifier.fillMaxSize(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically,
                content = tabContent
            )
        }
    }
    if (centered) {
        // 包裹 Box 接收外部 modifier（含 BoxScope.align），否则调用方的贴底对齐会被丢弃导致 TAB 悬到顶部
        Box(modifier = modifier.fillMaxWidth(), contentAlignment = Alignment.BottomCenter) {
            barContent()
        }
    } else {
        barContent()
    }
}
/**
 * 第一排：信息栏
 * 居中显示台标+频道名+分类，右侧收藏和信息按钮
 */
@Composable
internal fun PortraitInfoBarV2(viewModel: AppViewModel) {
    val currentChannel by viewModel.currentChannel.collectAsState()
    // 两路同名频道（如 CCTV-1 1080P / 576P）在底栏也要能区分，规则与频道列表一致
    val bottomBarChannels by viewModel.channels.collectAsState()
    val bottomBarDuplicateNames = remember(bottomBarChannels) { duplicateChannelNames(bottomBarChannels) }
    val favorites by viewModel.favorites.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val dlnaConnected by viewModel.dlnaConnected.collectAsState()
    val oc = rememberPlayerOverlayColors()

    // 标题栏：玻璃条（亮磨砂，跟随玻璃开关），降级为原实底
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    LiquidGlassSurface(
        enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
        cornerRadius = 14.dp,
        staticGlass = true,
        fallbackColor = oc.topBarBg.copy(alpha = 0.80f),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(44.dp)
                .padding(horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 左侧：返回首页按钮
            IconButton(
                onClick = { viewModel.showHomeScreen() },
                modifier = Modifier.size(40.dp)
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "返回首页",
                    tint = tvPalette.accentGraphic,
                    modifier = Modifier.size(24.dp)
                )
            }
            // 居中：台标 + 频道名 + 分类
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f),
                horizontalArrangement = Arrangement.Center
            ) {
                // 台标
                if (currentChannel != null && currentChannel!!.logo.isNotEmpty()) {
                    AsyncImage(
                        model = currentChannel!!.logo,
                        contentDescription = currentChannel!!.name,
                        modifier = Modifier
                            .size(28.dp)
                            .clip(RoundedCornerShape(4.dp)),
                        contentScale = ContentScale.Fit
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                }
                // 频道名
                Text(
                    text = currentChannel?.let { channelDisplayName(it, bottomBarDuplicateNames) } ?: "未选择频道",
                    color = oc.textPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                // 分类
                if (currentChannel != null && currentChannel!!.group.isNotEmpty()) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Surface(
                        color = AptvAccent.copy(alpha = 0.12f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = currentChannel!!.group,
                            color = tvPalette.accentText,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            maxLines = 1
                        )
                    }
                }
            }
            // 右侧：收藏 + 投屏 + 信息按钮
            val toastCtx = androidx.compose.ui.platform.LocalContext.current
            IconButton(
                onClick = { viewModel.toggleFavorite() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    imageVector = if (favorites.contains(currentIdx)) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = "收藏",
                    tint = if (favorites.contains(currentIdx)) tvPalette.favorite else oc.iconTint,
                    modifier = Modifier.size(22.dp)
                )
            }
            IconButton(
                onClick = { viewModel.toggleDlnaPanel() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.Cast,
                    contentDescription = "投屏",
                    tint = if (dlnaConnected != null) tvPalette.accentGraphic else oc.iconTint,
                    modifier = Modifier.size(22.dp)
                )
            }
            IconButton(
                onClick = { viewModel.toggleChannelInfo() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.Info,
                    contentDescription = "频道信息",
                    tint = oc.iconTint,
                    modifier = Modifier.size(22.dp)
                )
            }
        }
    }
}
/**
 * 第三排：播放控制栏
 * 播放/停止按钮 + 圆点进度条
 */
@Composable
internal fun PortraitControlsV2(viewModel: AppViewModel) {
    val oc = rememberPlayerOverlayColors()

    // 进度数据（1秒刷新）
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) {
        while (true) {
            tick = System.currentTimeMillis()
            delay(1000L)
        }
    }
    val progressInfo = remember(tick, viewModel.playbackState.value, viewModel.currentChannel.value, viewModel.currentEpg.value) {
        viewModel.computeProgress()
    }
    var dragging by remember { mutableStateOf(false) }
    var dragPercent by remember { mutableStateOf(0f) }

    // 控制条：玻璃条（亮磨砂，跟随玻璃开关），降级为原实底
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    LiquidGlassSurface(
        enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
        cornerRadius = 14.dp,
        staticGlass = true,
        fallbackColor = oc.infoBarBg.copy(alpha = 0.80f),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // 停止按钮（不需要暂停按钮）
            IconButton(
                onClick = { viewModel.stopPlay() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.Stop,
                    contentDescription = "停止",
                    tint = oc.iconTint,
                    modifier = Modifier.size(24.dp)
                )
            }
            // 播放工具按钮：截图/切片/EPG时间轴/搜索/提醒/续播/书签等
            IconButton(
                onClick = { viewModel.togglePlayerToolsPanel() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.MoreVert,
                    contentDescription = "播放工具",
                    tint = oc.iconTint,
                    modifier = Modifier.size(20.dp)
                )
            }
            // 播放器设置按钮：打开完整设置面板（含内核选择/VO/HWDEC/HDR 等）
            IconButton(
                onClick = { viewModel.togglePlayerSettings() },
                modifier = Modifier.size(36.dp).tvFocusBorder()
            ) {
                Icon(
                    Icons.Default.Settings,
                    contentDescription = "播放器设置",
                    tint = oc.iconTint,
                    modifier = Modifier.size(20.dp)
                )
            }
            // 时间标签 - 开始
            Text(
                text = progressInfo.startLabel,
                color = oc.textSecondary,
                fontSize = 10.sp,
                modifier = Modifier.padding(start = 4.dp)
            )
            // 圆点进度条
            DotProgressBar(
                progress = if (dragging) dragPercent else (progressInfo.percent / 100f),
                onSeek = { percent ->
                    dragPercent = percent
                    dragging = true
                },
                onSeekEnd = {
                    viewModel.seekProgress(dragPercent * 100f)
                    dragging = false
                },
                accentColor = tvPalette.accentGraphic,
                trackColor = oc.trackInactive,
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 8.dp)
                    .height(24.dp)
            )
            // 时间标签 - 结束
            Text(
                text = progressInfo.endLabel,
                color = oc.textSecondary,
                fontSize = 10.sp
            )
        }
    }
}
/**
 * 圆点进度条：用 Canvas 绘制轨道 + 圆点指示器
 */
@Composable
private fun DotProgressBar(
    progress: Float,
    onSeek: (Float) -> Unit,
    onSeekEnd: () -> Unit,
    accentColor: Color,
    trackColor: Color,
    modifier: Modifier = Modifier
) {
    val density = androidx.compose.ui.platform.LocalDensity.current
    val trackHeight = with(density) { 3.dp.toPx() }
    val dotRadius = with(density) { 6.dp.toPx() }

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .pointerInput(Unit) {
                detectTapGestures(
                    onTap = { offset ->
                        val w = size.width.toFloat()
                        if (w > 0) {
                            val percent = (offset.x / w).coerceIn(0f, 1f)
                            onSeek(percent)
                            onSeekEnd()
                        }
                    }
                )
            }
    ) {
        val canvasW = size.width
        val canvasH = size.height
        val centerY = canvasH / 2f
        val progressW = canvasW * progress

        // 背景轨道
        drawRoundRect(
            color = trackColor,
            topLeft = androidx.compose.ui.geometry.Offset(0f, centerY - trackHeight / 2),
            size = androidx.compose.ui.geometry.Size(canvasW, trackHeight),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(trackHeight / 2, trackHeight / 2)
        )
        // 已播放轨道
        if (progressW > 0) {
            drawRoundRect(
                color = accentColor,
                topLeft = androidx.compose.ui.geometry.Offset(0f, centerY - trackHeight / 2),
                size = androidx.compose.ui.geometry.Size(progressW, trackHeight),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(trackHeight / 2, trackHeight / 2)
            )
        }
        // 圆点指示器
        drawCircle(
            color = accentColor,
            radius = dotRadius,
            center = androidx.compose.ui.geometry.Offset(progressW.coerceIn(0f, canvasW), centerY)
        )
    }
}
