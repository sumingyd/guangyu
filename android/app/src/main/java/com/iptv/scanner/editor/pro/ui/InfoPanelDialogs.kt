package com.iptv.scanner.editor.pro.ui

import android.content.Context
import android.content.res.Configuration
import android.os.Build
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
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
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

@Composable
internal fun OsdView(
    title: String,
    subtitle: String,
    extra: String,
    modifier: Modifier = Modifier
        .statusBarsPadding()
        .padding(top = 48.dp)
        .padding(horizontal = 16.dp)
) {
    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.9f),
        shape = RoundedCornerShape(8.dp),
        modifier = modifier
    ) {
        Column(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 10.dp)
        ) {
            Text(
                text = title,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium
            )
            if (subtitle.isNotEmpty()) {
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = subtitle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp
                )
            }
            if (extra.isNotEmpty()) {
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = extra,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
            }
        }
    }
}

// -----------------------------------------------------------------
// 提醒触发弹窗（节目即将开始时弹出）
// 与 PC 端 ui/dialogs/reminder_popup.py 对齐
/**
 * 提醒弹窗：节目即将开始时弹出，提供"切换频道"和"稍后"两个选项。
 *
 * - 全屏半透明遮罩
 * - 中央卡片显示节目信息
 * - "切换频道"：切到目标频道并关闭弹窗
 * - "稍后"：仅关闭弹窗
 */
@Composable
internal fun ReminderPopup(
    reminder: ReminderItem,
    onAccept: () -> Unit,
    onDismiss: () -> Unit
) {
    val isAptv = LocalConfiguration.current.orientation == Configuration.ORIENTATION_PORTRAIT
    // 定时自动弹出的提醒必须接管遥控器焦点：出现时把焦点请求到主按钮，并把整个弹窗设为焦点组，
    // 否则焦点仍留在背后的列表上，方向键会在背景里移动且看不到焦点框。
    val acceptFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        delay(50)
        runCatching { acceptFocusRequester.requestFocus() }
    }
    // 弹窗关闭后焦点随弹窗节点一起被移除，需要把焦点交还给下层第一个可聚焦元素，否则焦点框消失。
    val focusManager = LocalFocusManager.current
    val popupHostView = LocalView.current
    DisposableEffect(Unit) {
        onDispose {
            popupHostView.post {
                val moved = runCatching {
                    focusManager.moveFocus(FocusDirection.Next)
                }.getOrDefault(false)
                if (!moved) {
                    runCatching { focusManager.moveFocus(FocusDirection.Down) }
                }
            }
        }
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xAA000000))
            .clickable(enabled = false) {},  // 阻断背景点击
        contentAlignment = Alignment.Center
    ) {
        Surface(
            color = if (isAptv) MaterialTheme.colorScheme.surface else MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(0.85f)
        ) {
            Column(
                modifier = Modifier.padding(20.dp).focusGroup(),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // 顶部图标
                Icon(
                    Icons.Default.Notifications,
                    contentDescription = null,
                    tint = if (isAptv) AptvAccent else tvPalette.favorite,
                    modifier = Modifier
                        .width(48.dp)
                        .height(48.dp)
                )
                Spacer(modifier = Modifier.height(12.dp))

                // 标题
                Text(
                    text = "节目即将开始",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Medium
                )
                Spacer(modifier = Modifier.height(16.dp))

                // 节目信息卡片
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(
                            text = reminder.programTitle.ifBlank { "（未命名节目）" },
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Medium,
                            maxLines = 2
                        )
                        if (reminder.channelName.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "频道: ${reminder.channelName}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                        if (reminder.startTs > 0) {
                            Spacer(modifier = Modifier.height(2.dp))
                            val timeStr = java.text.SimpleDateFormat(
                                "MM-dd HH:mm",
                                java.util.Locale.getDefault()
                            ).format(java.util.Date(reminder.startTs))
                            Text(
                                text = "开始: $timeStr",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 12.sp
                            )
                        }
                    }
                }
                Spacer(modifier = Modifier.height(20.dp))

                // 按钮行
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f).tvFocusBorder()
                    ) {
                        Text("稍后", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Button(
                        onClick = onAccept,
                        modifier = Modifier.weight(1f).tvFocusBorder().focusRequester(acceptFocusRequester)
                    ) {
                        Text("切换频道")
                    }
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 快捷工具栏 (QuickActionBar)
//
// 在视频控制层中提供常用功能的快捷入口，避免每次都要打开主菜单。
// 图标颜色随深色/浅色主题自适应。
/**
 * 频道信息详情对话框
 *
 * 竖屏：保持窄卡片、单列字段。
 * 横屏分屏 / TV：Dialog 默认宽度只有手机尺寸，加上一列十几行字段，在 2000px 宽的
 * 分屏右半屏里又窄又长、两侧大片留白，就是用户说的「竖屏的感觉」。这里改成
 * usePlatformDefaultWidth=false + 居中宽卡片，字段按上下两半左右分列。
 */
@Composable
internal fun ChannelInfoDialog(viewModel: AppViewModel) {
    val currentChannel by viewModel.currentChannel.collectAsState()
    val displayInfo by viewModel.channelDisplayInfo.collectAsState()
    val mpv = viewModel.mpv
    val videoWidth by mpv.videoWidth.collectAsState()
    val videoHeight by mpv.videoHeight.collectAsState()
    val currentProgram = viewModel.getCurrentProgram()
    val epgMeta by viewModel.currentEpgMeta.collectAsState()
    val oc = rememberPlayerOverlayColors()
    val config = LocalConfiguration.current
    val isAptv = config.orientation == Configuration.ORIENTATION_PORTRAIT
    val wide = !isAptv && config.screenWidthDp >= 600
    val accentColor = tvPalette.accentText

    // 字段清单：URL 太长，单独整行；其余短字段宽屏时按上下两半左右分列
    val fields = buildList {
        currentChannel?.let { ch ->
            add("频道名" to ch.name)
            if (ch.group.isNotEmpty()) add("分类" to ch.group)
            // EPG 匹配来源：这个频道的节目单来自哪个 EPG 源、哪个 epg 频道、走哪一级命中。
            // 未匹配的频道明确显示"未匹配"，不留空。
            val meta = epgMeta
            when {
                meta == null -> add("EPG 源" to "查询中…")
                meta.matched -> {
                    add("EPG 源" to meta.sourceName.ifEmpty {
                        meta.sourceUrl.ifEmpty { "未知源" }
                    })
                    add("EPG 频道" to meta.epgName.ifEmpty { meta.epgId })
                    if (meta.epgId.isNotEmpty()) add("EPG ID" to meta.epgId)
                    add("匹配方式" to meta.tier.ifEmpty { "已匹配" })
                }
                else -> {
                    add("EPG 源" to "未匹配")
                    add("EPG 频道" to "—")
                    add("匹配方式" to "—")
                }
            }
            if (ch.tvgId.isNotEmpty()) add("TVG-ID" to ch.tvgId)
            if (ch.tvgName.isNotEmpty()) add("TVG-Name" to ch.tvgName)
            if (ch.tvgChno.isNotEmpty()) add("频道号" to ch.tvgChno)
            if (ch.resolution.isNotEmpty()) add("分辨率" to ch.resolution)
            if (videoWidth > 0 && videoHeight > 0) add("视频尺寸" to "${videoWidth}x${videoHeight}")
            if (ch.catchup.isNotEmpty() && ch.catchup != "none" && ch.catchupDays.isNotEmpty()) {
                add("回看天数" to ch.catchupDays)
            }
            if (ch.source.isNotEmpty()) add("来源" to ch.source)
            // 状态字段仅在有实际状态时显示（去掉“待检测”）
            if (ch.status.isNotEmpty() && ch.status != "待检测") add("状态" to ch.status)
        }
    }
    val urlValue = currentChannel?.url.orEmpty()
    val catchupUrlValue = currentChannel?.let { ch ->
        if (ch.catchup.isNotEmpty() && ch.catchup != "none") {
            if (ch.catchupSource.isNotEmpty()) ch.catchupSource else ch.catchup
        } else ""
    }.orEmpty()

    // 玻璃化弹窗（与退出确认弹窗同模式）：独立 window 走静态玻璃，
    // 非玻璃态由 fallbackColor 提供圆角实底，不叠加 background 防黑直角
    val glass = LocalLiquidGlass.current &&
        com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported() &&
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    // TV/横屏遥控器：弹窗是独立 window，不主动抢焦点时方向键常留在下层界面上
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(wide) {
        // 同 PanelScaffold：遥控器确认键的 KeyUp 若在弹窗出现后立刻落到关闭按钮，
        // 会「打开即关闭」，因此延后到按键序列结束再抢焦点
        if (wide) {
            delay(220)
            runCatching { closeFocusRequester.requestFocus() }
        }
    }

    // 卡片是玻璃/主题色底，不是播放器暗色蒙层，统一用主题色文字保证对比度
    val labelWidth = if (wide) 82.dp else 60.dp

    val fieldsContent: @Composable () -> Unit = {
        if (wide) {
            val half = (fields.size + 1) / 2
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(24.dp)
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    fields.take(half).forEach { (label, value) ->
                        InfoRow(label, value, oc, true, labelWidth)
                    }
                }
                Column(modifier = Modifier.weight(1f)) {
                    fields.drop(half).forEach { (label, value) ->
                        InfoRow(label, value, oc, true, labelWidth)
                    }
                }
            }
            if (urlValue.isNotEmpty()) {
                Spacer(modifier = Modifier.height(6.dp))
                InfoRow("URL", urlValue, oc, true, labelWidth, maxLines = 6)
            }
            if (catchupUrlValue.isNotEmpty()) {
                Spacer(modifier = Modifier.height(6.dp))
                InfoRow("回看URL", catchupUrlValue, oc, true, labelWidth, maxLines = 6)
            }
        } else {
            fields.forEach { (label, value) -> InfoRow(label, value, oc, true) }
            if (urlValue.isNotEmpty()) InfoRow("URL", urlValue, oc, true)
            if (catchupUrlValue.isNotEmpty()) InfoRow("回看URL", catchupUrlValue, oc, true)
        }
        // 当前节目
        if (currentProgram != null && currentProgram.title.isNotEmpty()) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "当前节目",
                color = accentColor,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = currentProgram.title,
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 13.sp,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
    }

    val header: @Composable () -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (currentChannel != null && currentChannel!!.logo.isNotEmpty()) {
                AsyncImage(
                    model = currentChannel!!.logo,
                    contentDescription = null,
                    modifier = Modifier
                        .size(48.dp)
                        .clip(RoundedCornerShape(4.dp)),
                    contentScale = ContentScale.Fit
                )
                Spacer(modifier = Modifier.width(8.dp))
            }
            Text(
                // 标题用带分辨率后缀的显示名：同名多路流在弹窗标题也能区分
                text = displayInfo.name.ifEmpty { currentChannel?.name ?: "频道信息" },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium
            )
        }
    }

    val closeRow: @Composable () -> Unit = {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End
        ) {
            Button(
                onClick = { viewModel.toggleChannelInfo() },
                modifier = Modifier
                    .tvFocusBorder()
                    .then(if (wide) Modifier.focusRequester(closeFocusRequester) else Modifier)
            ) {
                Text("关闭")
            }
        }
    }

    val body: @Composable () -> Unit = {
        if (wide) {
            // 关闭按钮固定在卡片底部，不跟着字段一起滚走
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = (config.screenHeightDp * 0.80f).dp)
                    .padding(24.dp)
                    .focusGroup()
            ) {
                header()
                Spacer(modifier = Modifier.height(12.dp))
                Column(
                    modifier = Modifier
                        .weight(1f, fill = false)
                        .verticalScroll(rememberScrollState())
                ) {
                    if (currentChannel == null) {
                        Text(
                            text = "未选择频道",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp
                        )
                    } else {
                        fieldsContent()
                    }
                }
                Spacer(modifier = Modifier.height(12.dp))
                closeRow()
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
                    .focusGroup()
            ) {
                header()
                Spacer(modifier = Modifier.height(12.dp))
                if (currentChannel == null) {
                    Text(
                        text = "未选择频道",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp
                    )
                } else {
                    fieldsContent()
                }
                Spacer(modifier = Modifier.height(16.dp))
                closeRow()
            }
        }
    }

    if (wide) {
        Dialog(
            onDismissRequest = { viewModel.toggleChannelInfo() },
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                dismissOnBackPress = true,
                dismissOnClickOutside = false
            )
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Color.Black.copy(
                            alpha = if (com.iptv.scanner.editor.pro.ui.theme.isDarkTheme()) 0.62f else 0.42f
                        )
                    ),
                contentAlignment = Alignment.Center
            ) {
                com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                    enabled = glass,
                    cornerRadius = 20.dp,
                    staticGlass = true,
                    fallbackColor = MaterialTheme.colorScheme.surface,
                    modifier = Modifier
                        .widthIn(max = 760.dp)
                        .fillMaxWidth()
                ) {
                    body()
                }
            }
        }
    } else {
        Dialog(onDismissRequest = { viewModel.toggleChannelInfo() }) {
            com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                enabled = glass,
                cornerRadius = 20.dp,
                staticGlass = true,
                fallbackColor = MaterialTheme.colorScheme.surface,
                modifier = Modifier.fillMaxWidth()
            ) {
                body()
            }
        }
    }
}
@Composable
internal fun InfoRow(
    label: String,
    value: String,
    oc: PlayerOverlayColors,
    isAptv: Boolean = false,
    labelWidth: androidx.compose.ui.unit.Dp = 60.dp,
    maxLines: Int = 5
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        verticalAlignment = Alignment.Top
    ) {
        Text(
            text = "$label:",
            color = if (isAptv) MaterialTheme.colorScheme.onSurfaceVariant else oc.textSecondary,
            fontSize = 12.sp,
            modifier = Modifier.width(labelWidth)
        )
        Text(
            text = value,
            color = if (isAptv) MaterialTheme.colorScheme.onSurface else oc.textPrimary,
            fontSize = 12.sp,
            modifier = Modifier.weight(1f),
            maxLines = maxLines,
            overflow = TextOverflow.Ellipsis
        )
    }
}
/**
 * 视频参数信息行：显示视频编码、分辨率、音频编码、HDR/WCG 信息
 */
@Composable
internal fun PortraitMediaInfoBar(viewModel: AppViewModel) {
    val player = viewModel.mpv
    val fileLoaded by player.fileLoaded.collectAsState()
    val videoWidth by player.videoWidth.collectAsState()
    val videoHeight by player.videoHeight.collectAsState()
    val playerType by viewModel.playerType.collectAsState()
    val oc = rememberPlayerOverlayColors()

    // 1秒刷新媒体信息
    var tick by remember { mutableStateOf(0L) }
    LaunchedEffect(fileLoaded) {
        if (fileLoaded) {
            while (true) {
                tick = System.currentTimeMillis()
                delay(2000L)
            }
        }
    }

    val mediaInfo = remember(tick, fileLoaded, videoWidth, videoHeight) {
        // 只有在文件已加载且视频尺寸有效时才获取媒体信息
        // 停止状态（fileLoaded=false）不显示任何媒体信息
        if (fileLoaded && (videoWidth > 0 || videoHeight > 0)) player.getMediaInfo() else emptyMap()
    }

    // 停止状态（未加载文件）不显示媒体信息内容，但保留与信息条一致的高度占位：
    // 换台时 fileLoaded 会短暂为 false，若在此塌成 0dp，下方控制条/Tab/列表会整体
    // 上移再回落，产生可见抖动。
    if (!fileLoaded) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 2.dp)
                .height(28.dp)
        )
        return
    }

    // 媒体信息行：玻璃条（亮磨砂），降级为原实底
    val liquidGlass by viewModel.liquidGlass.collectAsState()
    com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
        enabled = liquidGlass && com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported(),
        cornerRadius = 12.dp,
        staticGlass = true,
        fallbackColor = oc.infoBarBg,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 2.dp)
    ) {
        if (mediaInfo.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(28.dp)
                    .padding(horizontal = 8.dp, vertical = 2.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // 视频编码（清理前缀：video/hevc → HEVC）
                mediaInfo["videoCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
                    val cleanCodec = codec.removePrefix("video/").removePrefix("audio/").uppercase()
                    MediaBadge(label = cleanCodec, oc = oc)
                }
                // 分辨率
                if (videoWidth > 0 && videoHeight > 0) {
                    val resLabel = if (videoHeight >= 2160) "4K"
                        else if (videoHeight >= 1080) "1080P"
                        else if (videoHeight >= 720) "720P"
                        else if (videoHeight >= 480) "480P"
                        else "${videoHeight}P"
                    MediaBadge(label = resLabel, oc = oc)
                    MediaBadge(label = "${videoWidth}×${videoHeight}", oc = oc, isAccent = false)
                }
                // FPS
                mediaInfo["fps"]?.takeIf { it.isNotEmpty() && it != "null" && it != "0" && it != "0.000" }?.let { fps ->
                    val fpsVal = fps.toFloatOrNull()
                    val fpsLabel = if (fpsVal != null) "${fpsVal.toInt()}FPS" else "${fps}FPS"
                    MediaBadge(label = fpsLabel, oc = oc)
                }
                // 音频编码（清理前缀：audio/aac → AAC）
                mediaInfo["audioCodec"]?.takeIf { it.isNotEmpty() && it != "null" }?.let { codec ->
                    val cleanCodec = codec.removePrefix("audio/").removePrefix("video/").uppercase()
                    MediaBadge(label = cleanCodec, oc = oc, isAccent = false)
                }
                // HDR / HLG / WCG 检测
                val primaries = mediaInfo["videoPrimaries"]
                val gamma = mediaInfo["videoGamma"]
                if (primaries == "bt.2020" || primaries == "bt.2100") {
                    when (gamma) {
                        "pq" -> MediaBadge(label = "HDR10", oc = oc, isHighlight = true)
                        "hlg" -> MediaBadge(label = "HLG", oc = oc, isHighlight = true)
                        else -> MediaBadge(label = "WCG", oc = oc)
                    }
                }
                // 硬件解码
                mediaInfo["hwdec"]?.takeIf { it.isNotEmpty() && it != "null" && it != "no" }?.let { hwdec ->
                    MediaBadge(label = "HW", oc = oc, isAccent = false)
                }
            }
        } else {
            // 文件已加载但视频尺寸未知（纯音频流 / 换台瞬间 videoWidth 还没回来），
            // 显示播放器类型。高度必须和有徽章时一致（28dp），否则换台这一瞬会矮 6dp，
            // 下方控制条与面板整体上移再回落，就是竖屏切台那一下抖动。
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(28.dp)
                    .padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "内核: ${playerType.name}",
                    color = oc.textSecondary,
                    fontSize = 10.sp
                )
            }
        }
    }
}
@Composable
private fun MediaBadge(
    label: String,
    oc: PlayerOverlayColors,
    isAccent: Boolean = true,
    isHighlight: Boolean = false
) {
    // 统一颜色：所有 badge 用「强调色当文字」token（浅色 #A81C34 / 深色 #FF8A9B），
    // HDR/HLG 高亮用 warningText；直接用 #E8455F 在浅玻璃上只有 2.8~3.5:1
    val fg = if (isHighlight) tvPalette.warningText
             else tvPalette.accentText
    // 徽章：轻玻璃小卡（随主题的浅描边底 + 语义色文字）
    Surface(
        color = tvPalette.borderSubtle,
        shape = RoundedCornerShape(4.dp),
        border = BorderStroke(1.dp, fg.copy(alpha = 0.28f))
    ) {
        Text(
            text = label.uppercase(),
            color = fg,
            fontSize = 9.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp),
            maxLines = 1
        )
    }
}
/**
 * 竖屏模式面板弹窗包装器：将全屏面板包装为居中弹窗
 * 半透明背景 + 圆角 + 边框，点击外部关闭
 */
@Composable
fun PortraitPanelDialog(
    onDismiss: () -> Unit,
    content: @Composable () -> Unit
) {
    val oc = rememberPlayerOverlayColors()
    val isAndroid12Plus = android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S
    val dialogShape = RoundedCornerShape(20.dp)
    val configuration = androidx.compose.ui.platform.LocalConfiguration.current
    val isLandscape = configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE
    val context = androidx.compose.ui.platform.LocalContext.current
    val isTv = context.packageManager.hasSystemFeature(android.content.pm.PackageManager.FEATURE_LEANBACK)
    val origDensity = androidx.compose.ui.platform.LocalDensity.current
    val dpiScale = if (isTv || isLandscape) (configuration.screenHeightDp / 720f).coerceIn(0.55f, 1f) else 1f
    val scaledDensity = androidx.compose.ui.unit.Density(origDensity.density * dpiScale, origDensity.fontScale)
    val scaledContent: @Composable () -> Unit = {
        androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalDensity provides scaledDensity) {
            content()
        }
    }
    // TV/横屏弹窗统一覆盖：暗玻璃（彩条视频背景上白霜太透）+ 主色橙红（AptvAccent），
    // 内部 Switch/按钮/FilterChip/输入框焦点色自动跟随，不再出现 Material 默认蓝
    val accentScheme = MaterialTheme.colorScheme.copy(
        // 文字类用途（TextButton/Switch 标签）用 accentText；
        // 选中承白字的容器（FilterChip）用 accentFill，白字 5.6:1
        primary = tvPalette.accentText,
        secondary = tvPalette.accentText,
        secondaryContainer = tvPalette.accentFill,
        onSecondaryContainer = tvPalette.accentOn
    )
    val accentedContent: @Composable () -> Unit = {
        MaterialTheme(colorScheme = accentScheme) { scaledContent() }
    }
    // 弹层遮罩：必须有 scrim 才能把底层频道列表/徽章压下去。
    // 浅色主题底层更亮，0.42 足够分离；深色主题需要 0.62 才压得住白字。
    val scrimAlpha = if (com.iptv.scanner.editor.pro.ui.theme.isDarkTheme()) 0.62f else 0.42f
    if (isTv) {
        // TV 端此前是「同窗口覆盖层」：遥控器确认键打开面板时，同一按键序列的 KeyUp
        // 仍落回底栏按钮，一次按键被算成两次 → 面板打开即关闭；改成独立 Dialog 窗口，
        // 与横屏分支一致后按键与焦点都留在新窗口内。
        Dialog(
            onDismissRequest = onDismiss,
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                dismissOnBackPress = true,
                dismissOnClickOutside = false
            )
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = scrimAlpha))
            ) {
            Box(
                modifier = Modifier
                    .align(Alignment.Center)
                    .fillMaxWidth(0.75f)
                    .fillMaxHeight(0.82f)
            ) {
                // TV 模式同样玻璃化：静态玻璃（独立 overlay 无法跨窗口采样，用静态光泽玻璃）
                com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                    enabled = LocalLiquidGlass.current && isAndroid12Plus,
                    cornerRadius = 20.dp,
                    staticGlass = true,
                    overlayDark = true,
                    fallbackColor = oc.topBarBg.copy(alpha = 0.85f),
                    modifier = Modifier.matchParentSize()
                ) {
                    // 暗玻璃弹窗：文字强制白系（浅色主题下 onSurface 会变黑字不可读）
                    com.iptv.scanner.editor.pro.ui.theme.DarkOverlayTheme { accentedContent() }
                }
            }
        }
        }
    } else if (isLandscape) {
        Dialog(
            onDismissRequest = onDismiss,
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                dismissOnBackPress = true,
                dismissOnClickOutside = false
            )
        ) {
            // 横屏弹窗原来只有居中的 75%×82% 玻璃卡片，Dialog 窗口其余区域完全透明，
            // 底层频道列表与徽章会直接透上来。这里补一层全屏 scrim + 居中容器。
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = scrimAlpha)),
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        // 横屏分屏原先 75%×82% 的卡片在 2000px 宽屏上仍然偏窄偏长的「竖屏感」，
                        // 这里放宽到 86%×88%，并给上限避免 TV 大屏无限拉伸
                        .fillMaxWidth(0.86f)
                        .widthIn(max = 1200.dp)
                        .fillMaxHeight(0.88f)
                ) {
                    // Dialog 为独立窗口，无法采样主窗口背景 —— 静态光泽玻璃降级
                    com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                        enabled = LocalLiquidGlass.current && isAndroid12Plus,
                        cornerRadius = 20.dp,
                        staticGlass = true,
                        overlayDark = true,
                        fallbackColor = oc.topBarBg.copy(alpha = 0.80f),
                        modifier = Modifier.matchParentSize()
                    ) {
                        // 暗玻璃弹窗：文字强制白系（浅色主题下 onSurface 会变黑字不可读）
                        com.iptv.scanner.editor.pro.ui.theme.DarkOverlayTheme { accentedContent() }
                    }
                }
            }
        }
    } else {
        // ---- 手机竖屏：APTV 式全屏 push 页（右侧滑入，实底背景，BACK 关闭） ----
        Dialog(
            onDismissRequest = onDismiss,
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                dismissOnBackPress = true,
                dismissOnClickOutside = false
            )
        ) {
            var pushVisible by remember { mutableStateOf(false) }
            LaunchedEffect(Unit) { pushVisible = true }
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.55f))
                    .clickable { onDismiss() }
            ) {
                androidx.compose.animation.AnimatedVisibility(
                    visible = pushVisible,
                    enter = androidx.compose.animation.slideInVertically(
                        initialOffsetY = { it },
                        animationSpec = androidx.compose.animation.core.tween(240)
                    ),
                    exit = androidx.compose.animation.slideOutVertically(
                        targetOffsetY = { it },
                        animationSpec = androidx.compose.animation.core.tween(200)
                    ),
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .fillMaxHeight(0.76f)
                ) {
                    // 底部弹出的 sheet（iOS detents 风格）：从底部滑入，占屏最多 76%，
                    // 全圆角悬浮卡片 —— 静态磨砂+光斑+描边，底层界面透出朦胧可见
                    val liquidGlass = LocalLiquidGlass.current
                    val useGlass = liquidGlass && isAndroid12Plus
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .clickable(
                                interactionSource = remember { androidx.compose.foundation.interaction.MutableInteractionSource() },
                                indication = null
                            ) { }
                            .padding(start = 10.dp, end = 10.dp, top = 0.dp, bottom = 8.dp)
                    ) {
                        com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                            enabled = useGlass,
                            cornerRadius = 24.dp,
                            staticGlass = true,
                            fallbackColor = MaterialTheme.colorScheme.background,
                            modifier = Modifier
                                .fillMaxSize()
                                .background(
                                    if (useGlass) MaterialTheme.colorScheme.background.copy(alpha = 0.82f)
                                    else MaterialTheme.colorScheme.background
                                )
                        ) {
                        // APTV 风格开关：竖屏 push 页内的共用基座组件（PanelScaffold 等）切换 APTV 样式
                        // 同时覆盖 MaterialTheme primary 色为 AptvAccent，让 Switch/RadioButton/FilterChip 等自动适配
                        androidx.compose.runtime.CompositionLocalProvider(LocalAptvStyle provides true) {
                            val aptvScheme = MaterialTheme.colorScheme.copy(
                                // 开关轨道/单选点属于图形用途（≥3.0），用 accentGraphic；
                                // 容器内文字用 accentText（≥4.5），避免 #E8455F 在浅底只有 2.8~3.5:1
                                primary = tvPalette.accentGraphic,
                                onPrimary = tvPalette.accentOn,
                                primaryContainer = tvPalette.accentFill.copy(alpha = 0.15f),
                                onPrimaryContainer = tvPalette.accentText,
                                // 玻璃页面上次要文字提亮，保证磨砂底上的可读性
                                onSurfaceVariant = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.78f),
                            )
                            MaterialTheme(colorScheme = aptvScheme) {
                                scaledContent()
                            }
                        }
                    }
                    // 顶部 grabber：sheet 拖拽指示条
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .padding(top = 6.dp)
                            .size(width = 36.dp, height = 4.dp)
                            .background(
                                MaterialTheme.colorScheme.outline.copy(alpha = 0.45f),
                                RoundedCornerShape(2.dp)
                            )
                    )
                }
            }
        }
    }   // 底部 sheet 外层 scrim Box 闭合
    }   // else（竖屏分支）闭合
}
