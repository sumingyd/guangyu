package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.graphics.toArgb
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.IptvEpgProgram
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * EPG 时间线视图：多频道 × 24h 横向网格。
 *
 * 与 PC 端 EpgTimelineDialog + Web 端 renderEpgTimeline 对齐：
 * - 左侧频道名列表（固定宽度，与主网格同步垂直滚动）
 * - 顶部时间刻度（固定高度，与主网格同步水平滚动）
 * - 主网格 Canvas 自绘（节目块 + 网格线 + 当前时间竖线）
 * - 节目块点击：过去→回看，当前/未来→提醒（与 EpgPanel handleProgramClick 一致）
 * - 日期切换（±7 天）
 * - 频道范围筛选（全部/收藏/当前分组，最多 30 频道）
 */
@Composable
fun EpgTimelinePanel(viewModel: AppViewModel, glassContainer: Boolean = false) {
    if (LocalAptvStyle.current) {
        EpgTimelinePanelAptv(viewModel, glassContainer)
        return
    }
    if (glassContainer) {
        // 拟态玻璃底座：与 TAB 栏一致的真模糊玻璃（haze 实时取景，非静态发暗玻璃）
        val liquidGlass by viewModel.liquidGlass.collectAsState()
        com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
            enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
            cornerRadius = 20.dp,
            fallbackColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.90f),
            modifier = Modifier.fillMaxSize()
        ) {
            EpgTimelinePanelInner(viewModel)
        }
        return
    }
    EpgTimelinePanelInner(viewModel)
}

/** EPG 面板主体（非 APTV 分支内容） */
@Composable
private fun EpgTimelinePanelInner(viewModel: AppViewModel) {
    val rows by viewModel.epgTimelineRows.collectAsState()
    val loading by viewModel.epgTimelineLoading.collectAsState()
    val range by viewModel.epgTimelineRange.collectAsState()
    val dateOffset by viewModel.epgTimelineDateOffset.collectAsState()
    val status by viewModel.epgTimelineStatus.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val density = LocalDensity.current
    val channelsCh by viewModel.channels.collectAsState()

    // TV 焦点管理：面板打开时请求焦点到关闭按钮，确保 DPAD 可操作。
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(50)
        kotlin.runCatching { closeFocusRequester.requestFocus() }
    }

    // 选中日期（基于今天 + offset）
    val selectedDate = remember(dateOffset) {
        val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_MONTH, dateOffset) }
        SimpleDateFormat("yyyy-MM-dd E", Locale.CHINA).format(Date(cal.timeInMillis))
    }

    // 滚动状态（频道名列 + 主网格共享垂直滚动；时间刻度 + 主网格共享水平滚动）
    val horizontalScroll = rememberScrollState()
    val verticalScroll = rememberScrollState()

    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(60_000L)
            now = System.currentTimeMillis()
        }
    }

    // 自动滚动到当前时间（首次加载或日期变化时，仅今天滚动）
    LaunchedEffect(rows, dateOffset) {
        if (rows.isNotEmpty() && dateOffset == 0) {
            val cal = Calendar.getInstance().apply {
                set(Calendar.HOUR_OF_DAY, 0)
                set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }
            val dayStartMs = cal.timeInMillis
            if (now in dayStartMs until (dayStartMs + 24 * 3600 * 1000L)) {
                val hoursFromStart = (now - dayStartMs) / 3600000.0
                val hourWidthPx = with(density) { HOUR_WIDTH_DP.toPx() }
                val targetPx = (hoursFromStart * hourWidthPx).toInt() - 200
                horizontalScroll.scrollTo(targetPx.coerceAtLeast(0))
            }
        }
    }

    Surface(color = Color.Transparent, modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
            // -----------------------------------------------------------------
            // 标题栏 + 工具栏
            // -----------------------------------------------------------------
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
Text(
text = "EPG 时间线",
style = MaterialTheme.typography.headlineSmall,
color = MaterialTheme.colorScheme.onSurface,
maxLines = 1
)
Text(
text = "$selectedDate  |  $status",
color = MaterialTheme.colorScheme.onSurfaceVariant,
fontSize = 12.sp,
maxLines = 1
)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // 日期切换（小图标按钮放大倍数加大，焦点视觉更明显）
                    IconButton(
                        onClick = { viewModel.setEpgTimelineDateOffset(dateOffset - 1) },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Text("◀", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                    }
                    Text(
                        text = when (dateOffset) {
                            0 -> "今天"
                            -1 -> "昨天"
                            1 -> "明天"
                            else -> "${dateOffset}天"
                        },
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 6.dp)
                    )
                    IconButton(
                        onClick = { viewModel.setEpgTimelineDateOffset(dateOffset + 1) },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Text("▶", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    // 刷新
                    IconButton(
                        onClick = { viewModel.loadEpgTimeline() },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = MaterialTheme.colorScheme.onSurface)
                    }
                    // 关闭
                    IconButton(
                        onClick = { viewModel.toggleEpgTimelinePanel() },
                        modifier = Modifier
                            .tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                            .focusRequester(closeFocusRequester)
                    ) {
                        Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 频道范围 FilterChip
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = range == EpgTimelineRange.ALL,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.ALL) },
                    label = { Text("全部频道", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
                FilterChip(
                    selected = range == EpgTimelineRange.FAVORITES,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.FAVORITES) },
                    label = { Text("仅收藏", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
                FilterChip(
                    selected = range == EpgTimelineRange.CURRENT_GROUP,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.CURRENT_GROUP) },
                    label = { Text("当前分组", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // -----------------------------------------------------------------
            // 主体：时间线网格
            // -----------------------------------------------------------------
            when {
                loading && rows.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("加载 EPG 数据...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                        }
                    }
                }
                rows.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = status.ifEmpty { "暂无 EPG 数据\n请在主菜单 > 文件 > EPG 订阅源 添加" },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp,
                            lineHeight = 20.sp
                        )
                    }
                }
                else -> {
                    // 显式占满标题/筛选后的剩余高度：分屏/内嵌场景下父 Column 的非 weight 子项
                    // 高度易被压成 0，导致时间线整块不可见
                    TimelineGrid(
                        modifier = Modifier.weight(1f),
                        rows = rows,
                        currentIdx = currentIdx,
                        dateOffset = dateOffset,
                        horizontalScroll = horizontalScroll,
                        verticalScroll = verticalScroll,
                        channels = channelsCh,
                        onVisibleRows = { from, to ->
                            viewModel.ensureEpgTimelineRowsLoaded(from, to)
                        },
                        onProgramClick = { program ->
                            handleTimelineProgramClick(program, viewModel)
                        },
                        // 平板（含电视切平板）：打开 EPG 时间线即把焦点交给网格
                        autoFocusOnShow = viewModel.uiMode.collectAsState().value == UiMode.TABLET
                    )
                }            }
        }
    }
}

// -----------------------------------------------------------------
// APTV（iOS 风格）版本
// -----------------------------------------------------------------

/**
 * APTV（iOS 风格）EPG 时间线面板：单列布局，圆角分组卡片 + iOS 选择行。
 * 仅在竖屏 APTV 模式下使用，横屏/TV 仍走 [EpgTimelinePanel] 原有布局。
 */
@Composable
private fun EpgTimelinePanelAptv(viewModel: AppViewModel, glassContainer: Boolean = false) {
    if (glassContainer) {
        // 拟态玻璃底座：与 TAB 栏一致的真模糊玻璃（haze 实时取景，非静态发暗玻璃）
        val liquidGlass by viewModel.liquidGlass.collectAsState()
        com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
            enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
            cornerRadius = 20.dp,
            fallbackColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.90f),
            modifier = Modifier.fillMaxSize()
        ) {
            EpgTimelinePanelAptvInner(viewModel, glassContainer = true)
        }
        return
    }
    EpgTimelinePanelAptvInner(viewModel)
}

/** EPG 面板主体（APTV 分支内容） */
@Composable
private fun EpgTimelinePanelAptvInner(viewModel: AppViewModel, glassContainer: Boolean = false) {
    val rows by viewModel.epgTimelineRows.collectAsState()
    val loading by viewModel.epgTimelineLoading.collectAsState()
    val range by viewModel.epgTimelineRange.collectAsState()
    val dateOffset by viewModel.epgTimelineDateOffset.collectAsState()
    val status by viewModel.epgTimelineStatus.collectAsState()
    val currentIdx by viewModel.currentIdx.collectAsState()
    val density = LocalDensity.current
    val channelsCh by viewModel.channels.collectAsState()

    // 选中日期（基于今天 + offset）
    val selectedDate = remember(dateOffset) {
        val cal = Calendar.getInstance().apply { add(Calendar.DAY_OF_MONTH, dateOffset) }
        SimpleDateFormat("yyyy-MM-dd E", Locale.CHINA).format(Date(cal.timeInMillis))
    }

    // 滚动状态（频道名列 + 主网格共享垂直滚动；时间刻度 + 主网格共享水平滚动）
    val horizontalScroll = rememberScrollState()
    val verticalScroll = rememberScrollState()

    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(60_000L)
            now = System.currentTimeMillis()
        }
    }

    // 自动滚动到当前时间（首次加载或日期变化时，仅今天滚动）
    LaunchedEffect(rows, dateOffset) {
        if (rows.isNotEmpty() && dateOffset == 0) {
            val cal = Calendar.getInstance().apply {
                set(Calendar.HOUR_OF_DAY, 0)
                set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }
            val dayStartMs = cal.timeInMillis
            if (now in dayStartMs until (dayStartMs + 24 * 3600 * 1000L)) {
                val hoursFromStart = (now - dayStartMs) / 3600000.0
                val hourWidthPx = with(density) { HOUR_WIDTH_DP.toPx() }
                val targetPx = (hoursFromStart * hourWidthPx).toInt() - 200
                horizontalScroll.scrollTo(targetPx.coerceAtLeast(0))
            }
        }
    }

    // 玻璃容器场景透出磨砂玻璃（外层 LiquidGlassSurface 提供底），否则自持实底
    Surface(
        color = if (glassContainer) Color.Transparent
        else MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
        modifier = Modifier.fillMaxSize()
    ) {
        Column(modifier = Modifier.fillMaxSize().systemBarsPadding()) {
            // 标题栏 + 工具栏（日期切换 / 刷新 / 关闭）
            AptvPanelHeader(
                title = "EPG 时间线",
                subtitle = "$selectedDate  |  $status",
                onClose = { viewModel.toggleEpgTimelinePanel() },
                actions = {
                    // 日期切换
                    IconButton(
                        onClick = { viewModel.setEpgTimelineDateOffset(dateOffset - 1) },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Text("◀", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                    }
                    Text(
                        text = when (dateOffset) {
                            0 -> "今天"
                            -1 -> "昨天"
                            1 -> "明天"
                            else -> "${dateOffset}天"
                        },
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 6.dp)
                    )
                    IconButton(
                        onClick = { viewModel.setEpgTimelineDateOffset(dateOffset + 1) },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Text("▶", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    // 刷新
                    IconButton(
                        onClick = { viewModel.loadEpgTimeline() },
                        modifier = Modifier.tvFocusBorder(cornerRadius = 20, focusedScale = 1.18f)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = "刷新", tint = MaterialTheme.colorScheme.onSurface)
                    }
                }
            )

            // 频道范围（紧凑 FilterChip 行，节省垂直空间）
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "频道范围",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
                FilterChip(
                    selected = range == EpgTimelineRange.ALL,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.ALL) },
                    label = { Text("全部频道", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
                FilterChip(
                    selected = range == EpgTimelineRange.FAVORITES,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.FAVORITES) },
                    label = { Text("仅收藏", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
                FilterChip(
                    selected = range == EpgTimelineRange.CURRENT_GROUP,
                    onClick = { viewModel.setEpgTimelineRange(EpgTimelineRange.CURRENT_GROUP) },
                    label = { Text("当前分组", fontSize = 11.sp) },
                    modifier = Modifier.tvFocusBorder(cornerRadius = 8, focusedScale = 1.15f)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // -----------------------------------------------------------------
            // 主体：时间线网格
            // -----------------------------------------------------------------
            when {
                loading && rows.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("加载 EPG 数据...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                        }
                    }
                }
                rows.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = status.ifEmpty { "暂无 EPG 数据\n请在主菜单 > 文件 > EPG 订阅源 添加" },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp,
                            lineHeight = 20.sp
                        )
                    }
                }
                else -> {
                    // 显式占满标题/筛选后的剩余高度：分屏/内嵌场景下父 Column 的非 weight 子项
                    // 高度易被压成 0，导致时间线整块不可见
                    TimelineGrid(
                        modifier = Modifier.weight(1f),
                        rows = rows,
                        currentIdx = currentIdx,
                        dateOffset = dateOffset,
                        horizontalScroll = horizontalScroll,
                        verticalScroll = verticalScroll,
                        channels = channelsCh,
                        onVisibleRows = { from, to ->
                            viewModel.ensureEpgTimelineRowsLoaded(from, to)
                        },
                        onProgramClick = { program ->
                            handleTimelineProgramClick(program, viewModel)
                        },
                        // 平板（含电视切平板）：打开 EPG 时间线即把焦点交给网格
                        autoFocusOnShow = viewModel.uiMode.collectAsState().value == UiMode.TABLET
                    )
                }            }
        }
    }
}

// -----------------------------------------------------------------
// 时间线网格
// -----------------------------------------------------------------

/** 网格常量（与 PC 端 HOUR_WIDTH=120 对齐，手机端窄一些；行高压缩提升单屏频道数） */
private val HOUR_WIDTH_DP = 54.dp
private val ROW_HEIGHT_DP = 30.dp
private val CHANNEL_NAME_WIDTH_DP = 118.dp
private val TIME_HEADER_HEIGHT_DP = 24.dp
// 横屏（TV/平板）加大行高与频道列提升可读性；竖屏保持紧凑密度
private val ROW_HEIGHT_DP_LAND = 80.dp
// 频道列宽：156dp 时扣除台号(26)/台标(34)/间距(7)/左右内边距(12) 后只剩 77dp，
// 13sp 中文约 5 个字，「CCTV-1 综合」「湖南卫视高清」这类名字会被省略成「CCTV-…」。
// 加宽到 196dp 后正文可用 ~123dp（约 9 字/行），配合频道名允许 2 行，绝大多数台名完整显示。
// 代价：时间轴可视宽度减少 40dp ≈ 0.74 小时（HOUR_WIDTH_DP=54），时间轴本身可横向滚动。
private val CHANNEL_NAME_WIDTH_DP_LAND = 196.dp

/**
 * 时间线网格布局：
 * - 左上角空白（频道名列与时间刻度交叉处）
 * - 顶部时间刻度（水平滚动）
 * - 左侧频道名列（垂直滚动）
 * - 主网格 Canvas（双向滚动 + 点击检测 + TV 方向键导航）
 *
 * TV 焦点导航：
 * - 网格 Box 可聚焦，方向键移动选中节目（selectedRow + selectedProgramIdx）
 * - DPAD_CENTER/ENTER 触发 onProgramClick
 * - 触摸模式仍可用 detectTapGestures 点击
 */
@Composable
private fun TimelineGrid(
    rows: List<EpgTimelineRow>,
    currentIdx: Int,
    dateOffset: Int,
    horizontalScroll: androidx.compose.foundation.ScrollState,
    verticalScroll: androidx.compose.foundation.ScrollState,
    channels: List<com.iptv.scanner.editor.pro.data.IptvChannel> = emptyList(),
    onVisibleRows: (Int, Int) -> Unit = { _, _ -> },
    onProgramClick: (IptvEpgProgram) -> Unit,
    autoFocusOnShow: Boolean = false,
    modifier: Modifier = Modifier
) {
    val density = LocalDensity.current
    // 横屏用加大行高/频道列，竖屏保持紧凑
    val isLandscape = androidx.compose.ui.platform.LocalConfiguration.current.orientation ==
        android.content.res.Configuration.ORIENTATION_LANDSCAPE
    val rowHeightDp = if (isLandscape) ROW_HEIGHT_DP_LAND else ROW_HEIGHT_DP
    val channelNameWidthDp = if (isLandscape) CHANNEL_NAME_WIDTH_DP_LAND else CHANNEL_NAME_WIDTH_DP
    val hourWidthPx = with(density) { HOUR_WIDTH_DP.toPx() }
    val rowHeightPx = with(density) { rowHeightDp.toPx() }
    val scope = rememberCoroutineScope()

    // TV 焦点状态：选中的行索引和该行内的节目索引
    // （MutableState 承载：方向键处理抽为顶层函数时可直接传引用，避免超长方法触发 VerifyError）
    val selectedRowState = remember { mutableStateOf(-1) }
    val selectedProgramIdxState = remember { mutableStateOf(-1) }
    var selectedRow by selectedRowState
    var selectedProgramIdx by selectedProgramIdxState
    val gridFocusRequester = remember { FocusRequester() }
    // 平板模式：面板打开后把焦点直接放进网格，遥控器上来就能左右跨时间、上下跨频道
    // （TV 模式仍落在右上角关闭按钮，保持原有行为）。
    LaunchedEffect(autoFocusOnShow) {
        if (!autoFocusOnShow) return@LaunchedEffect
        kotlinx.coroutines.delay(180)
        kotlin.runCatching { gridFocusRequester.requestFocus() }
    }

    // 选中日期的 0:00 时间戳（毫秒）
    val dayStartMs = remember(dateOffset) {
        val cal = Calendar.getInstance().apply {
            add(Calendar.DAY_OF_MONTH, dateOffset)
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        cal.timeInMillis
    }
    val now = System.currentTimeMillis()

    // 网格总尺寸
    val gridWidthPx = hourWidthPx * 24
    val gridHeightPx = rowHeightPx * rows.size

    // 主题颜色捕获（添加为 remember key，主题切换时重新创建 Paint）
    val onSurfaceColor = MaterialTheme.colorScheme.onSurface
    val onSurfaceVariantColor = MaterialTheme.colorScheme.onSurfaceVariant
    val outlineColor = MaterialTheme.colorScheme.outline
    val secondaryColor = MaterialTheme.colorScheme.secondary
    val surfaceVariantArgb = MaterialTheme.colorScheme.surfaceVariant.toArgb()
    val errorColor = MaterialTheme.colorScheme.error
    // 强调色当文字 / 当底承白字：不能直接复用 primary（#E8455F 在浅底只有 2.8~3.5:1）
    val accentTextColor = tvPalette.accentText
    val accentFillColor = tvPalette.accentFill
    // 选中块用深琥珀底承白字（原 tertiary #FF9800 上白字仅 2.2:1）
    val warningFillColor = tvPalette.warningText
    val onSurfaceVariantArgb = onSurfaceVariantColor.toArgb()
    val outlineArgb = outlineColor.toArgb()

    // 文本画笔（避免在 Canvas 内重复创建）；横屏大行高下字号同步放大
    val timeTextPaint = remember(density, onSurfaceVariantArgb) {
        android.graphics.Paint().apply {
            color = onSurfaceVariantArgb
            textSize = with(density) { (if (isLandscape) 13.sp else 11.sp).toPx() }
            isAntiAlias = true
        }
    }
    val programTextPaint = remember(density, onSurfaceColor) {
        android.graphics.Paint().apply {
            color = onSurfaceColor.toArgb()
            textSize = with(density) { (if (isLandscape) 13.sp else 10.sp).toPx() }
            isAntiAlias = true
        }
    }
    // 当前/选中节目块为橙红底（primary/tertiary），浅色主题下 onSurface 深字对比不足，
    // 固定使用白字（深浅主题下橙红底均适配白字）
    val programTextPaintCurrent = remember(density) {
        android.graphics.Paint().apply {
            color = android.graphics.Color.WHITE
            textSize = with(density) { (if (isLandscape) 13.sp else 10.sp).toPx() }
            isFakeBoldText = true
            isAntiAlias = true
        }
    }
    val programTextPaintSelected = remember(density) {
        android.graphics.Paint().apply {
            color = android.graphics.Color.WHITE
            textSize = with(density) { (if (isLandscape) 13.sp else 10.sp).toPx() }
            isAntiAlias = true
        }
    }
    val nowLabelPaint = remember(density) {
        android.graphics.Paint().apply {
            color = errorColor.toArgb()
            textSize = with(density) { (if (isLandscape) 13.sp else 10.sp).toPx() }
            isFakeBoldText = true
            isAntiAlias = true
        }
    }

    Column(modifier = modifier.fillMaxSize()) {
        // -----------------------------------------------------------------
        // 顶部：时间刻度行（左上角空白 + 时间刻度水平滚动）
        // -----------------------------------------------------------------
        Row(modifier = Modifier.fillMaxWidth()) {
            // 左上角空白（半透明衬底：玻璃容器下透出磨砂玻璃，不再自带实底色块）
            Box(
                modifier = Modifier
                    .width(channelNameWidthDp)
                    .height(TIME_HEADER_HEIGHT_DP)
                    .background(Color(surfaceVariantArgb).copy(alpha = 0.35f))
            )
            // 时间刻度（水平滚动同步）
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(TIME_HEADER_HEIGHT_DP)
                    .horizontalScroll(horizontalScroll)
            ) {
                Canvas(
                    modifier = Modifier.size(
                        width = with(density) { gridWidthPx.toDp() },
                        height = TIME_HEADER_HEIGHT_DP
                    )
                ) {
                    // 背景（半透明：玻璃容器下透出磨砂玻璃）
                    drawRect(Color(surfaceVariantArgb).copy(alpha = 0.35f))
                    // 每 2 小时一刻度
                    drawIntoCanvas { canvas ->
                        for (h in 0..24 step 2) {
                            val x = h * hourWidthPx
                            // 刻度线
                            drawLine(
                            color = Color(outlineArgb),
                            start = Offset(x, size.height - 4),
                                end = Offset(x, size.height),
                                strokeWidth = 1f
                            )
                            // 文本 HH:00
                            canvas.nativeCanvas.drawText(
                                String.format(Locale.US, "%02d:00", h % 24),
                                x + 4,
                                size.height / 2 + timeTextPaint.textSize / 3,
                                timeTextPaint
                            )
                        }
                    }
                }
            }
        }

        // -----------------------------------------------------------------
        // 主体：频道名列 + 网格（同步垂直滚动）
        // -----------------------------------------------------------------
        Row(modifier = Modifier.weight(1f)) {
            // 左侧频道名列（垂直滚动同步）；视口高度由 onSizeChanged 记录，
            // 供频道列窗口化渲染与 EPG 数据懒加载使用
            val channelViewPortHeight = remember { mutableStateOf(0f) }
            Box(
                modifier = Modifier
                    .width(channelNameWidthDp)
                    .onSizeChanged { channelViewPortHeight.value = it.height.toFloat() }
                    .verticalScroll(verticalScroll)
            ) {
                TimelineChannelColumn(
                    rows = rows,
                    currentIdx = currentIdx,
                    channels = channels,
                    rowHeightDp = rowHeightDp,
                    isLandscape = isLandscape,
                    surfaceVariantArgb = surfaceVariantArgb,
                    verticalScroll = verticalScroll,
                    viewPortHeightState = channelViewPortHeight,
                    onVisibleRows = onVisibleRows
                )
            }

            // 主网格 Canvas（双向滚动 + 点击检测 + TV 方向键导航）
            // onSizeChanged 放在 scroll 之前：记录的是视口尺寸（非滚动内容尺寸），
            // 供 Canvas 绘制时裁剪可视区外行/节目块，避免全量绘制造成切 tab 卡顿
            var gridViewPortWidth by remember { mutableStateOf(0f) }
            var gridViewPortHeight by remember { mutableStateOf(0f) }
            // 分屏/首帧时视口宽度还是 0，此时 scrollTo 会被 ScrollState 以 maxValue=0 截断，
            // 页面级「定位到当前时间」的滚动会丢失，时间线停在 00:00，看起来像空白。
            // 等视口真正测量出来后再补一次初始定位。
            var didInitialScroll by remember(dateOffset, rows.size) { mutableStateOf(false) }
            LaunchedEffect(gridViewPortWidth, dateOffset, rows.size) {
                if (didInitialScroll || gridViewPortWidth <= 0f || rows.isEmpty()) return@LaunchedEffect
                if (dateOffset == 0) {
                    val hours = (System.currentTimeMillis() - dayStartMs) / 3600000.0
                    horizontalScroll.scrollTo((hours * hourWidthPx).toInt().coerceAtLeast(0))
                }
                didInitialScroll = true
            }
            Box(
                modifier = Modifier
                    .weight(1f)
                    .onSizeChanged { gridViewPortWidth = it.width.toFloat(); gridViewPortHeight = it.height.toFloat() }
                    .horizontalScroll(horizontalScroll)
                    .verticalScroll(verticalScroll)
                    .focusRequester(gridFocusRequester)
                    .focusable()
                    .onPreviewKeyEvent { e ->
                        // OK 键在 KeyUp 统一触发点击（KeyDown 仅消费）。
                        // 原因：若在 KeyDown 直接 onProgramClick，回看/提醒等面板打开后焦点会落到
                        // 其标题栏关闭按钮（PanelScaffold 打开时自动抢焦点），同一次按键的 KeyUp
                        // 会让该按钮的 clickable 再次点击 → 面板刚打开就被关闭（闪一下消失）。
                        if (e.type == KeyEventType.KeyUp) {
                            if (e.key == Key.DirectionCenter || e.key == Key.Enter) {
                                val prog = rows.getOrNull(selectedRow)?.programs?.getOrNull(selectedProgramIdx)
                                if (prog != null) {
                                    onProgramClick(prog)
                                    return@onPreviewKeyEvent true
                                }
                            }
                            return@onPreviewKeyEvent false
                        }
                        // 方向键导航抽为顶层函数（避免超长方法触发 VerifyError）
                        handleTimelineNavKey(
                            e = e,
                            rows = rows,
                            rowHeightPx = rowHeightPx,
                            hourWidthPx = hourWidthPx,
                            dayStartMs = dayStartMs,
                            verticalScroll = verticalScroll,
                            horizontalScroll = horizontalScroll,
                            scope = scope,
                            selectedRowState = selectedRowState,
                            selectedProgramIdxState = selectedProgramIdxState
                        )
                    }
            ) {
                Canvas(
                    modifier = Modifier
                        .size(
                            width = with(density) { gridWidthPx.toDp() },
                            height = with(density) { gridHeightPx.toDp() }
                        )
                        .pointerInput(rows, dateOffset) {
                            detectTapGestures { offset ->
                                // 触摸点击时也更新选中状态
                                val rowIdx = (offset.y / rowHeightPx).toInt()
                                if (rowIdx in rows.indices) {
                                    selectedRow = rowIdx
                                    val row = rows[rowIdx]
                                    val tapMs = dayStartMs + (offset.x / hourWidthPx * 3600000L).toLong()
                                    val progIdx = row.programs.indexOfFirst { p ->
                                        val s = parseTimelineTimeMs(p.start, p.startTs)
                                        val e = parseTimelineTimeMs(p.end.ifEmpty { p.stop }, p.stopTs)
                                        s > 0 && e > s && tapMs >= s && tapMs < e
                                    }
                                    if (progIdx >= 0) selectedProgramIdx = progIdx
                                }
                                handleGridTap(
                                    offset = offset,
                                    rows = rows,
                                    dayStartMs = dayStartMs,
                                    hourWidthPx = hourWidthPx,
                                    rowHeightPx = rowHeightPx,
                                    onProgramClick = onProgramClick
                                )
                            }
                        }
                ) {
                    // 背景：不再铺实底色（玻璃容器下透出磨砂玻璃，非玻璃场景透出面板底色）
                    // 可视行范围裁剪：只绘制滚动视口内的行（±1 行余量），避免全量绘制卡顿。
                    // 分屏/首帧时视口可能尚未测量（=0），此时若照旧裁剪会把节目块全部裁掉，
                    // 表现为整块时间线空白；未测量时退回全量绘制，测量后下一帧自然收窄。
                    val measuredHeight = gridViewPortHeight > 0f
                    val measuredWidth = gridViewPortWidth > 0f
                    val firstVisibleRow = if (measuredHeight) {
                        ((verticalScroll.value / rowHeightPx).toInt() - 1).coerceAtLeast(0)
                    } else 0
                    val lastVisibleRow = if (measuredHeight) {
                        (((verticalScroll.value + gridViewPortHeight) / rowHeightPx).toInt() + 1)
                            .coerceIn(0, rows.size - 1)
                    } else rows.size - 1

                    // 网格线 + 节目块抽为 DrawScope 扩展函数（避免超长方法触发 VerifyError）
                    drawTimelineGridLines(
                        firstVisibleRow = firstVisibleRow,
                        lastVisibleRow = lastVisibleRow,
                        rowsSize = rows.size,
                        gridWidthPx = gridWidthPx,
                        gridHeightPx = gridHeightPx,
                        rowHeightPx = rowHeightPx,
                        hourWidthPx = hourWidthPx,
                        surfaceVariantArgb = surfaceVariantArgb,
                        outlineArgb = outlineArgb
                    )
                    drawTimelineProgramBlocks(
                        rows = rows,
                        firstVisibleRow = firstVisibleRow,
                        lastVisibleRow = lastVisibleRow,
                        dayStartMs = dayStartMs,
                        now = now,
                        hourWidthPx = hourWidthPx,
                        rowHeightPx = rowHeightPx,
                        scrollX = horizontalScroll.value.toFloat(),
                        // 视口宽度未测量时不做右侧裁剪（否则分屏下会整屏空白）
                        viewRight = if (measuredWidth) horizontalScroll.value.toFloat() + gridViewPortWidth
                        else Float.MAX_VALUE,
                        selectedRow = selectedRow,
                        selectedProgramIdx = selectedProgramIdx,
                        surfaceVariantArgb = surfaceVariantArgb,
                        accentFillColor = accentFillColor,
                        warningFillColor = warningFillColor,
                        secondaryColor = secondaryColor,
                        onSurfaceColor = onSurfaceColor,
                        programTextPaint = programTextPaint,
                        programTextPaintCurrent = programTextPaintCurrent,
                        programTextPaintSelected = programTextPaintSelected
                    )

                    // 当前时间竖线（仅今天显示）
                    val dayEndMs = dayStartMs + 24 * 3600000L
                    if (now in dayStartMs until dayEndMs) {
                        val nowX = ((now - dayStartMs) / 3600000.0).toFloat() * hourWidthPx
                        drawLine(
                            color = errorColor,
                            start = Offset(nowX, 0f),
                            end = Offset(nowX, gridHeightPx),
                            strokeWidth = 2f
                        )
                        // 当前时间标签
                        drawIntoCanvas { canvas ->
                            val timeLabel = SimpleDateFormat("HH:mm", Locale.US).format(Date(now))
                            canvas.nativeCanvas.drawText(timeLabel, nowX + 4f, 12f, nowLabelPaint)
                        }
                    }
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 时间线子组件/绘制函数（从 TimelineGrid 拆出：单方法寄存器超 255 会触发
// dalvik VerifyError "copy1 v46<-v272"，必须保持每个方法精简）
// -----------------------------------------------------------------

/** 频道列：台号 + 台标 + 频道名三段式，行高与网格行同步。
 *  窗口化渲染：仅组合可视行（±3 行余量），其余用 Spacer 占位——
 *  每行含 AsyncImage 台标，频道多时全量组合会明显卡顿。
 *  同时以可视窗口回调驱动 EPG 节目数据按行懒加载。 */
@Composable
private fun TimelineChannelColumn(
    rows: List<EpgTimelineRow>,
    currentIdx: Int,
    channels: List<com.iptv.scanner.editor.pro.data.IptvChannel>,
    rowHeightDp: androidx.compose.ui.unit.Dp,
    isLandscape: Boolean,
    surfaceVariantArgb: Int,
    verticalScroll: androidx.compose.foundation.ScrollState,
    viewPortHeightState: androidx.compose.runtime.State<Float>,
    onVisibleRows: (Int, Int) -> Unit
) {
    val onSurfaceVariantColor = MaterialTheme.colorScheme.onSurfaceVariant
    // 当前行台号/频道名用「强调色当文字」token：浅色 #A81C34 在 #F3DCE4 上 5.6:1，
    // 深色 #FF8A9B 在 #3A2A30 上 >4.5:1；直接用 primary(#E8455F) 只有 2.9:1
    val accentTextColor = tvPalette.accentText
    val density = LocalDensity.current
    val rowHeightPx = with(density) { rowHeightDp.toPx() }
    val viewPortHeightPx = viewPortHeightState.value
    // 可见行窗口（±3 行余量）：滚动位置变化时本 composable 重组合，窗口随之收窄/扩张
    val firstVisible = (((verticalScroll.value / rowHeightPx).toInt()) - 3).coerceAtLeast(0)
    val lastVisible = (((verticalScroll.value + viewPortHeightPx) / rowHeightPx).toInt() + 3)
        .coerceIn(0, rows.size - 1)
    // EPG 数据懒加载触发：窗口变化时通知外层填充该范围未加载的节目数据
    LaunchedEffect(firstVisible, lastVisible, rows) {
        if (rows.isNotEmpty()) onVisibleRows(firstVisible, lastVisible)
    }
    Column {
        if (rows.isEmpty()) return@Column
        // 顶部占位：跳过未进入窗口的行，保持总高度与 rows.size × rowHeight 一致
        if (firstVisible > 0) {
            Spacer(modifier = Modifier.height(with(density) { (firstVisible * rowHeightPx).toDp() }))
        }
        rows.forEachIndexed { idx, row ->
            if (idx < firstVisible || idx > lastVisible) return@forEachIndexed
            val isCurrent = row.channelIdx == currentIdx
            val ch = channels.getOrNull(row.channelIdx)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    // 行高与网格行同步（横屏 80dp/竖屏 30dp），避免频道列与节目条错位
                    // 非当前行半透明衬底：玻璃容器下透出磨砂玻璃，不再自带实底色块
                    .height(rowHeightDp)
                    .background(
                        if (isCurrent) MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                        else Color(surfaceVariantArgb).copy(alpha = 0.35f)
                    )
                    .padding(horizontal = 6.dp),
                contentAlignment = Alignment.CenterStart
            ) {
                // 台号 + 台标 + 频道名（台标带圆角衬底，避免浅色主题下白色 logo 幽灵化）
                // 横屏大行高下台标/字号同步放大，避免 80dp 行内 22dp 小台标显空
                val logoSize = if (isLandscape) 30.dp else 22.dp
                val logoCorner = if (isLandscape) 7.dp else 4.dp
                val numWidth = if (isLandscape) 24.dp else 20.dp
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "${row.channelIdx + 1}",
                        color = if (isCurrent) accentTextColor else onSurfaceVariantColor,
                        fontSize = if (isLandscape) 12.sp else 9.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.width(numWidth)
                    )
                    Box(
                        modifier = Modifier
                            .size(logoSize)
                            .clip(androidx.compose.foundation.shape.RoundedCornerShape(logoCorner))
                            .background(MaterialTheme.colorScheme.background),
                        contentAlignment = Alignment.Center
                    ) {
                        if (!ch?.logo.isNullOrEmpty()) {
                            coil.compose.AsyncImage(
                                model = ch!!.logo,
                                contentDescription = null,
                                contentScale = androidx.compose.ui.layout.ContentScale.Fit,
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(2.dp)
                            )
                        } else {
                            Text(
                                text = row.channelName.take(1),
                                color = onSurfaceVariantColor,
                                fontSize = if (isLandscape) 14.sp else 10.sp
                            )
                        }
                    }
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = row.displayName.ifEmpty { row.channelName },
                        color = if (isCurrent) accentTextColor else onSurfaceVariantColor,
                        fontSize = if (isLandscape) 13.sp else 10.sp,
                        // 允许 2 行：列宽放不下的长台名换成第二行显示，而不是直接省略成「CCTV-…」
                        lineHeight = if (isLandscape) 16.sp else 11.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        fontWeight = if (isCurrent) FontWeight.Medium else FontWeight.Normal
                    )
                }
            }
        }
        // 底部占位
        if (lastVisible < rows.size - 1) {
            Spacer(modifier = Modifier.height(with(density) { ((rows.size - 1 - lastVisible) * rowHeightPx).toDp() }))
        }
    }
}

/** 时间线网格方向键导航：返回 true 表示已消费。OK/Enter 的 KeyDown 仅消费（点击统一在 KeyUp 触发）。 */
private fun handleTimelineNavKey(
    e: androidx.compose.ui.input.key.KeyEvent,
    rows: List<EpgTimelineRow>,
    rowHeightPx: Float,
    hourWidthPx: Float,
    dayStartMs: Long,
    verticalScroll: androidx.compose.foundation.ScrollState,
    horizontalScroll: androidx.compose.foundation.ScrollState,
    scope: kotlinx.coroutines.CoroutineScope,
    selectedRowState: androidx.compose.runtime.MutableState<Int>,
    selectedProgramIdxState: androidx.compose.runtime.MutableState<Int>
): Boolean {
    if (e.type != KeyEventType.KeyDown) return false
    val selectedRow = selectedRowState.value
    val selectedProgramIdx = selectedProgramIdxState.value
    return when (e.key) {
        Key.DirectionUp -> {
            if (selectedRow > 0) {
                selectedRowState.value = selectedRow - 1
                // 选中行的节目数可能不同，clamp selectedProgramIdx
                val progs = rows.getOrNull(selectedRow - 1)?.programs ?: emptyList()
                if (selectedProgramIdx >= progs.size) selectedProgramIdxState.value = (progs.size - 1).coerceAtLeast(0)
                val target = (selectedRow - 1) * rowHeightPx.toInt()
                scope.launch { kotlin.runCatching { verticalScroll.animateScrollTo(target) } }
                true
            } else false
        }
        Key.DirectionDown -> {
            if (selectedRow < rows.size - 1) {
                selectedRowState.value = selectedRow + 1
                val progs = rows.getOrNull(selectedRow + 1)?.programs ?: emptyList()
                if (selectedProgramIdx >= progs.size) selectedProgramIdxState.value = (progs.size - 1).coerceAtLeast(0)
                val target = (selectedRow + 1) * rowHeightPx.toInt()
                scope.launch { kotlin.runCatching { verticalScroll.animateScrollTo(target) } }
                true
            } else false
        }
        Key.DirectionLeft -> {
            val progs = rows.getOrNull(selectedRow)?.programs ?: emptyList()
            if (selectedProgramIdx > 0) {
                selectedProgramIdxState.value = selectedProgramIdx - 1
                // 滚动到选中节目
                val prog = progs.getOrNull(selectedProgramIdx - 1)
                if (prog != null) {
                    val startMs = parseTimelineTimeMs(prog.start, prog.startTs)
                    val x = ((startMs - dayStartMs).coerceAtLeast(0) / 3600000.0).toFloat() * hourWidthPx
                    scope.launch { kotlin.runCatching { horizontalScroll.animateScrollTo((x - 100).toInt().coerceAtLeast(0)) } }
                }
                true
            } else false
        }
        Key.DirectionRight -> {
            val progs = rows.getOrNull(selectedRow)?.programs ?: emptyList()
            if (selectedProgramIdx < progs.size - 1) {
                selectedProgramIdxState.value = selectedProgramIdx + 1
                val prog = progs.getOrNull(selectedProgramIdx + 1)
                if (prog != null) {
                    val startMs = parseTimelineTimeMs(prog.start, prog.startTs)
                    val x = ((startMs - dayStartMs).coerceAtLeast(0) / 3600000.0).toFloat() * hourWidthPx
                    scope.launch { kotlin.runCatching { horizontalScroll.animateScrollTo((x - 100).toInt().coerceAtLeast(0)) } }
                }
                true
            } else false
        }
        Key.DirectionCenter, Key.Enter -> rows.getOrNull(selectedRow)?.programs?.getOrNull(selectedProgramIdx) != null
        else -> false
    }
}

/** 网格线绘制：行分隔线仅画可视行，小时分隔线全高 */
private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawTimelineGridLines(
    firstVisibleRow: Int,
    lastVisibleRow: Int,
    rowsSize: Int,
    gridWidthPx: Float,
    gridHeightPx: Float,
    rowHeightPx: Float,
    hourWidthPx: Float,
    surfaceVariantArgb: Int,
    outlineArgb: Int
) {
    // 水平网格线（行分隔，仅可视行）
    for (i in firstVisibleRow..(lastVisibleRow + 1).coerceAtMost(rowsSize)) {
        val y = i * rowHeightPx
        drawLine(
            color = Color(surfaceVariantArgb),
            start = Offset(0f, y),
            end = Offset(gridWidthPx, y),
            strokeWidth = 1f
        )
    }
    // 垂直网格线（小时分隔，每 2 小时加粗）
    for (h in 0..24) {
        val x = h * hourWidthPx
        val color = if (h % 2 == 0) Color(outlineArgb) else Color(surfaceVariantArgb)
        drawLine(
            color = color,
            start = Offset(x, 0f),
            end = Offset(x, gridHeightPx),
            strokeWidth = if (h % 2 == 0) 1f else 0.8f
        )
    }
}

/** 节目块绘制：仅可视行 + 水平视口裁剪（±1 小时余量），含背景/选中边框/节目标题 */
private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawTimelineProgramBlocks(
    rows: List<EpgTimelineRow>,
    firstVisibleRow: Int,
    lastVisibleRow: Int,
    dayStartMs: Long,
    now: Long,
    hourWidthPx: Float,
    rowHeightPx: Float,
    scrollX: Float,
    viewRight: Float,
    selectedRow: Int,
    selectedProgramIdx: Int,
    surfaceVariantArgb: Int,
    accentFillColor: Color,
    warningFillColor: Color,
    secondaryColor: Color,
    onSurfaceColor: Color,
    programTextPaint: android.graphics.Paint,
    programTextPaintCurrent: android.graphics.Paint,
    programTextPaintSelected: android.graphics.Paint
) {
    drawIntoCanvas { canvas ->
        for (rowIdx in firstVisibleRow..lastVisibleRow) {
            val row = rows[rowIdx]
            val y = rowIdx * rowHeightPx
            row.programs.forEachIndexed { progIdx, program ->
                val startMs = parseTimelineTimeMs(program.start, program.startTs)
                val endMs = parseTimelineTimeMs(
                    program.end.ifEmpty { program.stop }, program.stopTs
                )
                if (startMs <= 0 || endMs <= startMs) return@forEachIndexed

                val x1 = ((startMs - dayStartMs).coerceAtLeast(0) / 3600000.0).toFloat() * hourWidthPx
                val x2 = ((endMs - dayStartMs).coerceAtMost(24 * 3600000L) / 3600000.0).toFloat() * hourWidthPx
                // 水平裁剪：节目块完全在视口外（±1 小时余量）则跳过
                if (x2 < scrollX - hourWidthPx || x1 > viewRight + hourWidthPx) return@forEachIndexed
                val blockWidth = (x2 - x1).coerceAtLeast(1f)
                val isCurrent = now in startMs until endMs
                val isPast = now >= endMs
                val isSelected = rowIdx == selectedRow && progIdx == selectedProgramIdx

                // 节目块背景
                val bgColor = when {
                    isSelected -> warningFillColor  // 选中：深琥珀（承白字 ≥4.5:1）
                    isCurrent -> accentFillColor    // 当前：深强调色（承白字 5.6:1）
                    isPast -> Color(surfaceVariantArgb).copy(alpha = 0.45f)  // 过去：半透明随主题变
                    else -> secondaryColor.copy(alpha = 0.3f)  // 普通：浅蓝
                }
                drawRoundRect(
                    color = bgColor,
                    topLeft = Offset(x1 + 1f, y + 2f),
                    size = Size(blockWidth - 2f, rowHeightPx - 4f),
                    cornerRadius = CornerRadius(3f, 3f)
                )

                // 选中边框（随主题自适应）
                if (isSelected) {
                    drawRoundRect(
                        color = onSurfaceColor,
                        topLeft = Offset(x1 + 1f, y + 2f),
                        size = Size(blockWidth - 2f, rowHeightPx - 4f),
                        cornerRadius = CornerRadius(3f, 3f),
                        style = androidx.compose.ui.graphics.drawscope.Stroke(
                            width = 2f
                        )
                    )
                }

                // 节目标题（宽度 > 40px 才绘制）：多行断行显示（横屏 80dp 行高可容 2-3 行，
                // 竖屏 30dp 自动退化为单行），选中/当前块白字（橙红底），其余随主题
                if (blockWidth > 40f) {
                    val textPaint = when {
                        isSelected -> programTextPaintSelected
                        isCurrent -> programTextPaintCurrent
                        else -> programTextPaint
                    }
                    drawProgramTitleMultiLine(
                        canvas = canvas,
                        title = program.title,
                        paint = textPaint,
                        x = x1 + 4f,
                        blockTop = y + 4f,
                        blockWidth = blockWidth - 8f,
                        blockHeight = rowHeightPx - 8f
                    )
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 点击处理
// -----------------------------------------------------------------

/**
 * 网格点击命中检测：根据点击坐标计算频道行和时间段，查找命中的节目。
 */
private fun handleGridTap(
    offset: Offset,
    rows: List<EpgTimelineRow>,
    dayStartMs: Long,
    hourWidthPx: Float,
    rowHeightPx: Float,
    onProgramClick: (IptvEpgProgram) -> Unit
) {
    val rowIdx = (offset.y / rowHeightPx).toInt()
    if (rowIdx < 0 || rowIdx >= rows.size) return

    val row = rows[rowIdx]
    // 点击位置对应的时间戳（毫秒）
    val tapMs = dayStartMs + (offset.x / hourWidthPx * 3600000L).toLong()

    // 查找包含该时间点的节目
    val hit = row.programs.firstOrNull { p ->
        val startMs = parseTimelineTimeMs(p.start, p.startTs)
        val endMs = parseTimelineTimeMs(p.end.ifEmpty { p.stop }, p.stopTs)
        startMs > 0 && endMs > startMs && tapMs >= startMs && tapMs < endMs
    }
    if (hit != null) {
        onProgramClick(hit)
    }
}

/**
 * 节目点击处理（与 EpgPanel.kt handleProgramClick 对齐）：
 * - past 程序 → startCatchup
 * - current/future 程序 → toggleReminder
 */
private fun handleTimelineProgramClick(program: IptvEpgProgram, viewModel: AppViewModel) {
    val now = System.currentTimeMillis()
    val endMs = parseTimelineTimeMs(program.end.ifEmpty { program.stop }, program.stopTs)
    val startMs = parseTimelineTimeMs(program.start, program.startTs)
    val isPast = endMs > 0 && now >= endMs
    val isCurrent = startMs > 0 && endMs > startMs && now >= startMs && now < endMs

    if (isPast && !isCurrent) {
        viewModel.startCatchup(program)
    } else {
        viewModel.toggleReminder(program, viewModel.currentChannel.value)
    }
}

// -----------------------------------------------------------------
// 工具函数
// -----------------------------------------------------------------

/** 时间解析（与 EpgPanel.kt parseTimeToMs 对齐） */
private fun parseTimelineTimeMs(iso: String, ts: Long): Long {
    if (ts > 0) return ts * 1000L
    if (iso.isEmpty()) return 0
    val patterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd HH:mm"
    )
    for (pattern in patterns) {
        try {
            return SimpleDateFormat(pattern, Locale.US).parse(iso)?.time ?: continue
        } catch (_: Exception) {
        }
    }
    return iso.toLongOrNull()?.let { if (it > 1_000_000_000_000L) it else it * 1000 } ?: 0
}

/** 节目标题多行绘制：按块内宽度断行，块内垂直居中；竖屏矮行高自动退化为单行 */
private fun drawProgramTitleMultiLine(
    canvas: androidx.compose.ui.graphics.Canvas,
    title: String,
    paint: android.graphics.Paint,
    x: Float,
    blockTop: Float,
    blockWidth: Float,
    blockHeight: Float
) {
    if (title.isEmpty() || blockWidth <= 0f || blockHeight <= 0f) return
    val lineHeight = paint.textSize * 1.25f
    val maxLines = (blockHeight / lineHeight).toInt().coerceAtLeast(1)
    val lines = breakTextIntoLines(title, paint, blockWidth, maxLines)
    if (lines.isEmpty()) return
    val fm = paint.fontMetrics
    val lineAscent = -fm.ascent
    val totalHeight = lines.size * lineHeight
    // 首行基线：块内整体垂直居中后下移一个 ascent（fontMetrics 基线定位）
    var textY = blockTop + (blockHeight - totalHeight) / 2f + lineAscent
    for (line in lines) {
        canvas.nativeCanvas.drawText(line, x, textY, paint)
        textY += lineHeight
    }
}

/** 按最大宽度与行数上限断行（CJK 可任意断点）；末行放不下剩余文本时截断加省略号 */
private fun breakTextIntoLines(
    title: String, paint: android.graphics.Paint, maxWidth: Float, maxLines: Int
): List<String> {
    if (paint.measureText(title) <= maxWidth) return listOf(title)
    val lines = mutableListOf<String>()
    var start = 0
    while (start < title.length && lines.size < maxLines) {
        val isLastLine = lines.size == maxLines - 1
        // 找到从 start 起一行能容纳的最大字符数（measureText 的 end 为排他边界）
        var end = start + 1
        while (end <= title.length && paint.measureText(title, start, end) <= maxWidth) {
            end++
        }
        var lineEnd = end - 1
        if (lineEnd <= start) lineEnd = start + 1  // 单字符超宽也强制放下，避免死循环
        if (isLastLine && lineEnd < title.length) {
            // 末行仍放不下剩余文本：回退宽度给省略号
            val ellipsis = "…"
            var le = lineEnd
            while (le > start &&
                paint.measureText(title, start, le) + paint.measureText(ellipsis) > maxWidth
            ) {
                le--
            }
            return if (le > start) lines + listOf(title.substring(start, le) + ellipsis)
            else lines + listOf(ellipsis)
        }
        lines.add(title.substring(start, lineEnd))
        start = lineEnd
    }
    return lines
}
