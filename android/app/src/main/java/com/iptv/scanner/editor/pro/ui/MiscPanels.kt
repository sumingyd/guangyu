package com.iptv.scanner.editor.pro.ui

import android.content.Intent
import android.content.res.Configuration
import android.net.Uri
import android.os.Build
import android.util.Log
import com.iptv.scanner.editor.pro.data.BookmarkItem
import com.iptv.scanner.editor.pro.data.ReminderItem
import com.iptv.scanner.editor.pro.data.ResumeItem
import com.iptv.scanner.editor.pro.data.ScanResult
import com.iptv.scanner.editor.pro.data.SubtitleItem
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.foundation.verticalScroll
import kotlin.math.sqrt
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Radar
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Subtitles
import androidx.compose.material.icons.filled.SyncAlt
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FileOpen
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.MappingEntry
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField
import com.iptv.scanner.editor.pro.ui.theme.rememberPlayerOverlayColors
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
// -----------------------------------------------------------------
// 打开网络流 URL 对话框
// -----------------------------------------------------------------

@Composable
fun OpenUrlDialog(viewModel: AppViewModel) {
    val open by viewModel.openUrlDialogOpen.collectAsState()
    if (!open) return

    var url by remember { mutableStateOf("") }
    val isAptv = LocalConfiguration.current.orientation == Configuration.ORIENTATION_PORTRAIT

    if (isAptv) {
        // iOS APTV 风格：居中圆角卡片 + 输入框
        androidx.compose.ui.window.Dialog(
            onDismissRequest = { viewModel.toggleOpenUrlDialog() },
            properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)
        ) {
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 6.dp,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 40.dp)
            ) {
                Column(modifier = Modifier.padding(24.dp)) {
                    Text(
                        text = "打开网络流",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "输入 M3U/M3U8/HLS/RTSP/RTMP 等协议 URL",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        placeholder = { Text("https://example.com/stream.m3u8") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().tvTextField()
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "取消",
                            fontSize = 16.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier
                                .tvFocusBorder(cornerRadius = 10)
                                .clickable { viewModel.toggleOpenUrlDialog() }
                                .padding(horizontal = 12.dp, vertical = 8.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "播放",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium,
                            color = tvPalette.accentText,
                            modifier = Modifier
                                .tvFocusBorder(cornerRadius = 10)
                                .clickable {
                                    viewModel.playUrl(url.trim())
                                    url = ""
                                }
                                .padding(horizontal = 12.dp, vertical = 8.dp)
                        )
                    }
                }
            }
        }
    } else {
        // 横屏/TV：走统一玻璃弹窗容器（原为原生 AlertDialog 实底，与整体玻璃风格不符）
        PortraitPanelDialog(onDismiss = { viewModel.toggleOpenUrlDialog() }) {
            androidx.compose.foundation.layout.Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Column(modifier = Modifier.fillMaxWidth(0.55f)) {
                    Text(
                        text = "打开网络流",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "输入 M3U/M3U8/HLS/RTSP/RTMP 等协议 URL",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        placeholder = { Text("https://example.com/stream.m3u8") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().tvTextField()
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextButton(
                            onClick = { viewModel.toggleOpenUrlDialog() },
                            modifier = Modifier.tvFocusBorder()
                        ) { Text("取消", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        Spacer(modifier = Modifier.width(8.dp))
                        TextButton(
                            onClick = {
                                viewModel.playUrl(url.trim())
                                url = ""
                            },
                            modifier = Modifier.tvFocusBorder()
                        ) { Text("播放", color = tvPalette.accentText) }
                    }
                }
            }
        }
    }
}
/**
 * 打开网络流面板内容（横屏分屏详情路由用，非 Dialog）：
 * 与 [OpenUrlDialog] 横屏分支内容一致，但渲染为右侧详情面板（自带标题/关闭钮）。
 */
@Composable
fun OpenUrlPanelContent(viewModel: AppViewModel) {
    var url by remember { mutableStateOf("") }
    PanelScaffold(
        title = "打开网络流",
        subtitle = "输入 M3U/M3U8/HLS/RTSP/RTMP 等协议 URL",
        onClose = { viewModel.toggleOpenUrlDialog() }
    ) {
        SettingsGroup("流地址") {
            OutlinedTextField(
                value = url,
                onValueChange = { url = it },
                placeholder = { Text("https://example.com/stream.m3u8") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().tvTextField()
            )
        }
        Spacer(modifier = Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedButton(
                onClick = { viewModel.toggleOpenUrlDialog() },
                modifier = Modifier.tvFocusBorder()
            ) { Text("取消", color = MaterialTheme.colorScheme.onSurfaceVariant) }
            Spacer(modifier = Modifier.width(8.dp))
            OutlinedButton(
                onClick = {
                    if (url.isNotBlank()) {
                        viewModel.playUrl(url.trim())
                        url = ""
                    }
                },
                modifier = Modifier.tvFocusBorder()
            ) { Text("播放", color = MaterialTheme.colorScheme.primary) }
        }
    }
}
/**
 * 退出确认对话框：按 BACK 键退出时提示选择退出方式。
 * - 进入画中画：继续在小窗口中观看
 * - 立即退出：直接退出应用
 * - 打开设置：不退出，转而打开播放器设置面板
 * - 取消：继续使用
 */
@Composable
fun ExitConfirmDialog(viewModel: AppViewModel) {
    val open by viewModel.exitConfirmOpen.collectAsState()
    if (!open) return

    val context = androidx.compose.ui.platform.LocalContext.current
    val activity = context as? android.app.Activity
    val isAptv = LocalConfiguration.current.orientation == Configuration.ORIENTATION_PORTRAIT

    // 遥控器操作：弹窗出现后把焦点默认落到「取消」（安全项，避免误按 OK 直接退出），
    // 并把整列选项设为焦点组，方向键在弹窗内上下切换。此前没有任何初始焦点，
    // 电视端打开后焦点仍留在背后的播放页，遥控器无法确认/取消。
    val cancelFocusRequester = remember { FocusRequester() }

    // iOS 风格玻璃退出弹窗：圆角玻璃卡片 + 居中标题 + 竖排选项（独立窗口走静态玻璃）
        val glass = LocalLiquidGlass.current &&
            com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported() &&
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
        Dialog(onDismissRequest = { viewModel.dismissExitConfirm() }) {
            LaunchedEffect(Unit) {
                kotlinx.coroutines.delay(50)
                runCatching { cancelFocusRequester.requestFocus() }
            }
            com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
                enabled = glass,
                cornerRadius = 22.dp,
                staticGlass = true,
                fallbackColor = MaterialTheme.colorScheme.surface,
                // 注意：这里不能再叠加 modifier.background —— 方角背景画在圆角裁剪之外，
                // 会在弹窗圆角外露出黑色直角；非玻璃态由 fallbackColor 提供圆角实底
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(top = 22.dp, bottom = 12.dp).focusGroup()
                ) {
                    Text("退出应用", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "您正在退出应用，请选择退出方式：",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                    Spacer(Modifier.height(14.dp))
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                    // 画中画
                    if (activity != null &&
                        Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                        activity.packageManager.hasSystemFeature("android.software.picture_in_picture")
                    ) {
                        ExitOptionRow("画中画") {
                            viewModel.dismissExitConfirm()
                            try {
                                val builder = android.app.PictureInPictureParams.Builder()
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                                    builder.setAutoEnterEnabled(true)
                                    builder.setSeamlessResizeEnabled(true)
                                }
                                activity.enterPictureInPictureMode(builder.build())
                            } catch (e: Exception) {
                                Log.e("ExitConfirmDialog", "PiP failed", e)
                            }
                        }
                        HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                    }
                    // 打开设置：不退出，转而打开播放器设置面板
                    ExitOptionRow("打开设置") {
                        viewModel.dismissExitConfirm()
                        viewModel.togglePlayerSettings()
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                    // 立即退出（红色强调）
                    ExitOptionRow("立即退出", tint = if (isAptv) AptvAccentText else tvPalette.danger) {
                        viewModel.dismissExitConfirm()
                        // 先停止播放，避免 Activity finish 后 mpv 在后台继续播放
                        viewModel.stopPlay()
                        activity?.finishAffinity()
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                    // 取消（加粗）
                    ExitOptionRow("取消", bold = true, modifier = Modifier.focusRequester(cancelFocusRequester)) {
                        viewModel.dismissExitConfirm()
                    }
                }
            }
        }
}

/** 退出弹窗选项行：全宽点击 + 居中文字（iOS ActionSheet 样式） */
@Composable
private fun ExitOptionRow(
    label: String,
    tint: Color = Color.Unspecified,
    bold: Boolean = false,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .tvFocusBorder(cornerRadius = 10)
            .clickable { onClick() }
            .padding(vertical = 15.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            label,
            color = if (tint == Color.Unspecified) MaterialTheme.colorScheme.onSurface else tint,
            fontSize = 16.sp,
            fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal
        )
    }
}

/**
 * DLNA 投屏设备面板：SSDP 搜索局域网电视/盒子，点击设备把当前频道投播到电视。
 * 玻璃弹窗风格与退出确认弹窗一致（独立窗口走静态玻璃）。
 */
@Composable
fun DlnaCastPanel(viewModel: AppViewModel) {
    val open by viewModel.dlnaPanelOpen.collectAsState()
    if (!open) return

    val devices by viewModel.dlnaDevices.collectAsState()
    val scanning by viewModel.dlnaScanning.collectAsState()
    val connected by viewModel.dlnaConnected.collectAsState()

    var manualMode by remember { mutableStateOf(false) }
    var manualIp by remember { mutableStateOf("") }
    // 搜索到设备后收起手动输入区
    LaunchedEffect(devices) {
        if (devices.isNotEmpty()) manualMode = false
    }
    val submitManual: () -> Unit = {
        val ip = manualIp.trim()
        if (Regex("""^(\d{1,3}\.){3}\d{1,3}$""").matches(ip)) {
            viewModel.scanDlna(ip)
        } else {
            viewModel.showOsd("投屏", "请输入正确的电视 IP，例如 192.168.1.100")
        }
    }

    val glass = LocalLiquidGlass.current &&
        com.iptv.scanner.editor.pro.ui.theme.isLiquidBlurSupported() &&
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    Dialog(
        onDismissRequest = { viewModel.dismissDlnaPanel() },
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        // 与其它面板一致的遮罩：此前投屏面板没有 scrim，底层视频/页面不压暗
        val scrim = if (com.iptv.scanner.editor.pro.ui.theme.isDarkTheme())
            Color.Black.copy(alpha = 0.62f) else Color.Black.copy(alpha = 0.42f)
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(scrim)
                .clickable { viewModel.dismissDlnaPanel() },
            contentAlignment = Alignment.Center
        ) {
        com.iptv.scanner.editor.pro.ui.theme.LiquidGlassSurface(
            enabled = glass,
            cornerRadius = 22.dp,
            staticGlass = true,
            fallbackColor = MaterialTheme.colorScheme.surface,
            // 顺序要点：
            // 1) padding 放在最外层 —— 写在 widthIn 之后会把玻璃面本身缩掉 48dp
            //    （实测可见面板只有 512dp），只能用作屏边留白；
            // 2) widthIn 必须在 fillMaxWidth 之前 —— 顺序反过来时 fillMaxWidth
            //    已把 min/max 都钉成父宽度，widthIn 的 max 会被约束夹回父宽度而不生效
            modifier = Modifier
                .padding(horizontal = 24.dp)
                .widthIn(max = 560.dp)
                .fillMaxWidth()
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(top = 20.dp, bottom = 10.dp)
            ) {
                // Dialog 内没有 Surface 提供 LocalContentColor（默认黑色），
                // 深色模式下必须显式使用主题色，否则标题在暗玻璃上不可读
                Text(
                    "投屏到电视",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 17.sp
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    if (scanning) "正在搜索局域网设备..." else "点击设备开始投播当前频道",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp
                )
                Spacer(Modifier.height(12.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                // 设备列表（最多显示区域限制，超出滚动）
                if (devices.isEmpty()) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            if (scanning) "搜索中..." else "未发现设备",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 14.sp
                        )
                        if (!scanning) {
                            Spacer(Modifier.height(4.dp))
                            Text(
                                "请确认电视与本机在同一 Wi-Fi，不同网段可手动输入电视 IP",
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                                fontSize = 12.sp,
                                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                modifier = Modifier.padding(horizontal = 24.dp)
                            )
                        }
                    }
                } else {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 260.dp)
                            .verticalScroll(rememberScrollState())
                    ) {
                        devices.forEach { device ->
                            val isConnected = connected?.host == device.host && connected?.name == device.name
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .tvFocusBorder(cornerRadius = 10)
                                    .clickable {
                                        if (isConnected) viewModel.stopDlnaCast() else viewModel.castToDevice(device)
                                    }
                                    .padding(horizontal = 20.dp, vertical = 13.dp)
                            ) {
                                Text(
                                    if (isConnected) "${device.name}（投播中，点击断开）" else device.name,
                                    color = if (isConnected) tvPalette.accentText else MaterialTheme.colorScheme.onSurface,
                                    fontSize = 15.sp,
                                    fontWeight = if (isConnected) FontWeight.SemiBold else FontWeight.Normal
                                )
                                Text(
                                    device.host,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 12.sp
                                )
                            }
                            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.15f))
                        }
                    }
                }
                // 手动输入电视 IP：组播被路由器/模拟器 NAT 拦截时的兜底搜索
                if (manualMode) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.15f))
                    OutlinedTextField(
                        value = manualIp,
                        onValueChange = { manualIp = it.filter { c -> c.isDigit() || c == '.' } },
                        singleLine = true,
                        placeholder = { Text("电视 IP，例如 192.168.1.100", fontSize = 13.sp) },
                        textStyle = MaterialTheme.typography.bodyMedium,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 20.dp, vertical = 8.dp)
                            .tvTextField()
                    )
                    if (!scanning) {
                        ExitOptionRow("搜索该 IP") { submitManual() }
                    }
                } else if (!scanning) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.15f))
                    ExitOptionRow("手动输入电视 IP") { manualMode = true }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                // 重新搜索
                ExitOptionRow(if (scanning) "搜索中..." else "重新搜索") {
                    if (!scanning) viewModel.scanDlna()
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.25f))
                ExitOptionRow("取消", bold = true) {
                    viewModel.dismissDlnaPanel()
                }
            }
        }
        }
    }
}
// =================================================================
// 工具面板
// =================================================================

/**
 * 工具面板：工具入口列表，与 PC 端"工具"菜单组对齐。
 * 点击各工具项跳转到对应面板或显示 OSD 提示。
 */
@Composable
fun ToolsPanel(viewModel: AppViewModel) {
    // SAF 文件选择器 —— 打开播放列表
    val playlistLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.importPlaylist(uri)
    }

    // SAF 文件选择器 —— 打开本地视频/音频
    val videoLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.playLocalVideo(uri.toString())
    }

    PanelScaffold(
        title = "工具",
        subtitle = "搜索 / EPG时间线 / 提醒 / 续播 / 书签 / 映射 / 扫描 / 流质量",
        onClose = { viewModel.toggleToolsPanel() },
        scrollable = false
    ) {
        val tools = listOf(
            // —— 文件快捷入口 ——
            ToolEntry("打开播放列表", "选择设备上的 M3U/M3U8 文件", Icons.Default.FileOpen) {
                viewModel.toggleToolsPanel()
                if (!viewModel.isSafAvailable()) {
                    viewModel.showFileBrowser()
                } else {
                    playlistLauncher.launch(arrayOf(
                        "application/x-mpegurl", "application/vnd.apple.mpegurl",
                        "audio/x-mpegurl", "video/x-mpegurl",
                        "text/plain", "application/octet-stream"
                    ))
                }
            },
            ToolEntry("打开本地文件", "播放设备上的视频/音频文件", Icons.Default.Movie) {
                viewModel.toggleToolsPanel()
                if (!viewModel.isSafAvailable()) {
                    viewModel.showMediaFileBrowser()
                } else {
                    videoLauncher.launch(arrayOf("video/*", "audio/*", "application/x-matroska", "application/octet-stream"))
                }
            },
            // —— 原有工具 ——
            ToolEntry("搜索", "全局搜索频道和节目", Icons.Default.Search) {
                viewModel.toggleSearchPanel()
            },
            ToolEntry("EPG 时间线", "节目时间线视图", Icons.Default.CalendarMonth) {
                viewModel.toggleEpgTimelinePanel()
            },
            ToolEntry("提醒管理", "节目提醒列表", Icons.Default.Notifications) {
                viewModel.toggleReminderPanel()
            },
            ToolEntry("续播位置", "本地文件/点播断点续播", Icons.Default.History) {
                viewModel.toggleResumePanel()
            },
            ToolEntry("书签管理", "播放位置书签（增删查/跳转）", Icons.Default.Bookmark) {
                viewModel.toggleBookmarkPanel()
            },
            ToolEntry("频道映射", "远程映射 + 用户映射管理", Icons.Default.SyncAlt) {
                viewModel.toggleMappingPanel()
            },
            ToolEntry("扫描整理", "URL 范围扫描（StandaloneScanner）", Icons.Default.Radar) {
                viewModel.toggleScanPanel()
            },
            ToolEntry("流质量检测", "码率 / 分辨率 / 编解码器", Icons.Default.Analytics) {
                viewModel.toggleStreamQualityPanel()
            }
        )
        LazyColumn(modifier = Modifier.fillMaxWidth()) {
            items(tools) { tool ->
                ToolEntryRow(tool)
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
            }
        }
    }
}
private data class ToolEntry(
    val title: String,
    val desc: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val onClick: () -> Unit
)

@Composable
private fun ToolEntryRow(tool: ToolEntry, compact: Boolean = false) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            // tvFocusBorder 在 clickable 之前（外层）才能收到焦点事件
            .tvFocusBorder()
            .clickable { tool.onClick() }
            // 横屏两列时行距收一点，9 个工具刚好一屏放下、不会卡半行
            .padding(vertical = if (compact) 8.dp else 12.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = tool.icon,
            contentDescription = tool.title,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(28.dp)
        )
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(text = tool.title, color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Text(text = tool.desc, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
    }
}

/**
 * 播放工具面板：播放时常用工具入口（截图/切片/EPG时间线/搜索/提醒/续播/书签/可视化/歌词）。
 * 从控制条"播放工具"按钮或设置页"播放工具"项进入，与 [ToolsPanel] 的通用工具列表互补。
 * 横屏分屏详情内：工具项点击 push 到第三列（左列表 + 中工具面板 + 右子面板）；
 * 竖屏/弹窗场景保持原 toggle 弹窗行为。
 */
@Composable
fun PlayerToolsPanel(viewModel: AppViewModel) {
    PanelScaffold(
        title = "播放工具",
        subtitle = "截图 / 切片 / EPG时间线 / 搜索 / 提醒 / 续播 / 书签",
        onClose = { viewModel.togglePlayerToolsPanel() },
        scrollable = false
    ) {
        // 分屏详情内二级入口走第三列 push；否则原弹窗 toggle
        val embedded = LocalSplitDetailEmbedded.current
        fun routeOrToggle(flow: kotlinx.coroutines.flow.StateFlow<Boolean>, panel: @Composable () -> Unit, toggle: () -> Unit) {
            if (embedded) splitDetailPush(flow, panel, toggle) else toggle()
        }
        val tools = listOf(
            ToolEntry("截图", "截取当前画面", Icons.Default.CameraAlt) {
                routeOrToggle(viewModel.screenshotPanelOpen, { ScreenshotPanel(viewModel) }) { viewModel.toggleScreenshotPanel() }
            },
            ToolEntry("切片导出", "截取视频片段", Icons.Default.Movie) {
                routeOrToggle(viewModel.clipExportPanelOpen, { ClipExportPanel(viewModel) }) { viewModel.toggleClipExportPanel() }
            },
            ToolEntry("EPG 时间线", "节目时间线视图", Icons.Default.CalendarMonth) {
                routeOrToggle(viewModel.epgTimelineOpen, { EpgTimelinePanel(viewModel = viewModel) }) { viewModel.toggleEpgTimelinePanel() }
            },
            ToolEntry("搜索", "全局搜索频道和节目", Icons.Default.Search) {
                routeOrToggle(viewModel.searchPanelOpen, { SearchPanel(viewModel) }) { viewModel.toggleSearchPanel() }
            },
            ToolEntry("提醒管理", "节目提醒列表", Icons.Default.Notifications) {
                routeOrToggle(viewModel.reminderPanelOpen, { ReminderPanel(viewModel) }) { viewModel.toggleReminderPanel() }
            },
            ToolEntry("续播位置", "本地文件/点播断点续播", Icons.Default.History) {
                routeOrToggle(viewModel.resumePanelOpen, { ResumePanel(viewModel) }) { viewModel.toggleResumePanel() }
            },
            ToolEntry("书签管理", "播放位置书签", Icons.Default.Bookmark) {
                routeOrToggle(viewModel.bookmarkPanelOpen, { BookmarkPanel(viewModel) }) { viewModel.toggleBookmarkPanel() }
            },
            ToolEntry("音频可视化", "频谱/波形可视化", Icons.Default.Analytics) {
                routeOrToggle(viewModel.audioVisualizerOpen, { AudioVisualizerPanel(viewModel) }) { viewModel.toggleAudioVisualizer() }
            },
            ToolEntry("歌词", "加载/显示歌词", Icons.Default.Subtitles) {
                routeOrToggle(viewModel.lyricsOpen, { LyricsPanel(viewModel = viewModel) }) { viewModel.toggleLyricsPanel() }
            }
        )
        SettingsGroup("工具列表") {
            // 横屏分屏 / TV：单列 9 行在宽卡片里两侧全是空白，看起来仍是竖屏排版，
            // 这里按两列铺开；竖屏保持单列。
            val config = LocalConfiguration.current
            val wide = config.orientation == Configuration.ORIENTATION_LANDSCAPE &&
                config.screenWidthDp >= 600
            LazyColumn(modifier = Modifier.fillMaxWidth()) {
                if (wide) {
                    items(tools.chunked(2)) { pair ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            pair.forEachIndexed { index, tool ->
                                if (index > 0) {
                                    Box(
                                        modifier = Modifier
                                            .width(1.dp)
                                            .height(40.dp)
                                            .background(MaterialTheme.colorScheme.surfaceVariant)
                                    )
                                }
                                Box(modifier = Modifier.weight(1f)) { ToolEntryRow(tool, compact = true) }
                            }
                            // 奇数个时右侧补等宽空位，保证两列对齐
                            if (pair.size == 1) Spacer(modifier = Modifier.weight(1f))
                        }
                        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                    }
                } else {
                    items(tools) { tool ->
                        ToolEntryRow(tool)
                        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                    }
                }
            }
        }
    }
}

// -----------------------------------------------------------------
// 节目提醒管理面板（与 PC 端 ui/dialogs/reminder_manager_dialog.py 对齐）
// -----------------------------------------------------------------

/**
 * 提醒管理面板：列出所有已设置的节目提醒，支持删除/清空。
 *
 * - 顶部显示总数和清空按钮
 * - 列表项显示频道名 / 节目标题 / 开始时间 / 倒计时
 * - 即将开始（<5 分钟）的提醒高亮显示
 * - 空列表显示占位提示
 */
@Composable
fun ReminderPanel(viewModel: AppViewModel) {
    val reminders by viewModel.reminders.collectAsState()
    val now = System.currentTimeMillis()
    val timeFmt = remember { SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()) }

    PanelScaffold(
        title = "节目提醒",
        subtitle = "已设置 ${reminders.size} 条提醒",
        onClose = { viewModel.toggleReminderPanel() },
        actions = {
            if (reminders.isNotEmpty()) {
                OutlinedButton(
                    onClick = { viewModel.clearReminders() },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Close, contentDescription = null, tint = tvPalette.danger)
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("清空", color = tvPalette.danger)
                }
            }
        }
    ) {
        if (reminders.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().padding(top = 60.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.Notifications,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("暂无节目提醒", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "在节目单中点击当前或未来节目可设置提醒",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }
            return@PanelScaffold
        }

        // 按开始时间升序排序
        val sorted = remember(reminders) { reminders.sortedBy { it.startTs } }

        SettingsGroup("提醒列表") {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)
            ) {
                items(sorted, key = { it.id }) { item ->
                    ReminderRow(
                        item = item,
                        now = now,
                        timeFmt = timeFmt,
                        onDelete = { viewModel.removeReminder(item.id) }
                    )
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        }
    }
}
@Composable
private fun ReminderRow(
    item: ReminderItem,
    now: Long,
    timeFmt: SimpleDateFormat,
    onDelete: () -> Unit
) {
    val remainingMs = item.startTs - now
    val isUpcoming = remainingMs in 0..5 * 60 * 1000L  // 5 分钟内即将开始
    val isPast = remainingMs < 0  // 已开始（但未结束）

    val titleColor = when {
        isUpcoming -> tvPalette.warning  // 黄色高亮
        isPast -> MaterialTheme.colorScheme.onSurfaceVariant
        else -> MaterialTheme.colorScheme.onSurface
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            // 节目标题
            Text(
                text = item.programTitle.ifBlank { "（未命名节目）" },
                color = titleColor,
                fontSize = 14.sp,
                fontWeight = if (isUpcoming) FontWeight.Medium else FontWeight.Normal,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            // 频道名
            if (item.channelName.isNotEmpty()) {
                Text(
                    text = item.channelName,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
            // 时间 + 倒计时
            Row(
                modifier = Modifier.padding(top = 3.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = timeFmt.format(Date(item.startTs)),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
                val remainingText = when {
                    remainingMs > 0 -> {
                        val min = remainingMs / 60_000
                        if (min > 0) "${min}分钟后" else "即将开始"
                    }
                    remainingMs > -60 * 60 * 1000L -> "已开始"  // 1 小时内
                    else -> "已过期"
                }
                val remainingColor = when {
                    isUpcoming -> tvPalette.warning
                    isPast -> MaterialTheme.colorScheme.onSurfaceVariant
                    else -> MaterialTheme.colorScheme.primary
                }
                Text(remainingText, color = remainingColor, fontSize = 11.sp)
            }
        }
        IconButton(onClick = onDelete, modifier = Modifier.size(32.dp).tvFocusBorder()) {
            Icon(
                Icons.Default.Close,
                contentDescription = "删除",
                tint = tvPalette.dangerSoft,
                modifier = Modifier.size(16.dp)
            )
        }
    }
}
// -----------------------------------------------------------------
// 续播位置管理面板（与 PC 端 ui/dialogs/resume_position_dialog.py 对齐）
// -----------------------------------------------------------------

/**
 * 续播位置面板：列出所有已保存的播放断点，支持恢复/删除/清空。
 *
 * - 顶部显示总数和清空按钮
 * - 列表项显示名称 + 位置/时长 + 更新时间
 * - 点击"恢复"调用 playResume 切换并 seek
 * - 空列表显示占位提示
 */
@Composable
fun ResumePanel(viewModel: AppViewModel) {
    val resumeList by viewModel.resumeList.collectAsState()
    val timeFmt = remember { SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()) }

    PanelScaffold(
        title = "续播位置",
        subtitle = "已保存 ${resumeList.size} 条断点",
        onClose = { viewModel.toggleResumePanel() },
        actions = {
            if (resumeList.isNotEmpty()) {
                OutlinedButton(
                    onClick = { viewModel.clearResumeList() },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Close, contentDescription = null, tint = tvPalette.danger)
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("清空", color = tvPalette.danger)
                }
            }
        }
    ) {
        if (resumeList.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().padding(top = 60.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.History,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("暂无续播记录", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "播放本地文件或点播流时自动保存断点",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }
            return@PanelScaffold
        }

        // 按更新时间降序排序（最近观看在前）
        val sorted = remember(resumeList) { resumeList.sortedByDescending { it.updatedAt } }

        SettingsGroup("断点列表") {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)
            ) {
                items(sorted, key = { it.id }) { item ->
                    ResumeRow(
                        item = item,
                        timeFmt = timeFmt,
                        onPlay = { viewModel.playResume(item) },
                        onDelete = { viewModel.removeResume(item.url) }
                    )
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        }
    }
}
@Composable
private fun ResumeRow(
    item: ResumeItem,
    timeFmt: SimpleDateFormat,
    onPlay: () -> Unit,
    onDelete: () -> Unit
) {
    // 格式化时长 mm:ss 或 hh:mm:ss
    fun fmt(sec: Long): String {
        if (sec <= 0) return "00:00"
        val h = sec / 3600
        val m = (sec % 3600) / 60
        val s = sec % 60
        return if (h > 0) "%02d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            // 名称
            Text(
                text = item.name.ifBlank { item.url },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            // 位置 / 时长
            Row(
                modifier = Modifier.padding(top = 3.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val progress = if (item.duration > 0) {
                    (item.position.toFloat() / item.duration.toFloat()).coerceIn(0f, 1f)
                } else 0f
                Text(
                    text = "${fmt(item.position)} / ${fmt(item.duration)}",
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 11.sp
                )
                if (progress > 0) {
                    Text(
                        text = "${(progress * 100).toInt()}%",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }
            // 更新时间 + URL
            Row(
                modifier = Modifier.padding(top = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = timeFmt.format(Date(item.updatedAt)),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
                if (item.channelIdx >= 0) {
                    Surface(
                        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                        shape = RoundedCornerShape(3.dp)
                    ) {
                        Text(
                            text = "频道",
                            color = MaterialTheme.colorScheme.primary,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }
                } else {
                    Surface(
                        color = tvPalette.success.copy(alpha = 0.15f),
                        shape = RoundedCornerShape(3.dp)
                    ) {
                        Text(
                            text = "本地",
                            color = tvPalette.success,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }
                }
            }
        }
        // 恢复按钮
        OutlinedButton(
            onClick = onPlay,
            modifier = Modifier.tvFocusBorder()
        ) {
            Text("恢复", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
        }
        Spacer(modifier = Modifier.width(4.dp))
        IconButton(onClick = onDelete, modifier = Modifier.size(32.dp).tvFocusBorder()) {
            Icon(
                Icons.Default.Close,
                contentDescription = "删除",
                tint = tvPalette.dangerSoft,
                modifier = Modifier.size(16.dp)
            )
        }
    }
}
// -----------------------------------------------------------------
// 书签管理面板（与 PC 端 ui/dialogs/bookmark_dialog.py 对齐）
// -----------------------------------------------------------------

/**
 * 书签面板：添加/跳转/删除/清空书签。
 *
 * - 顶部：添加书签按钮 + 视图切换（当前文件/所有文件）
 * - 列表：书签项显示名称 + 位置时间 + 创建时间 + 跳转/删除按钮
 * - 底部：清除当前/清除全部
 * - 空列表显示占位提示
 */
@Composable
fun BookmarkPanel(viewModel: AppViewModel) {
    val showCurrent by viewModel.bookmarkShowCurrent.collectAsState()
    val currentBookmarks by viewModel.currentBookmarks.collectAsState()
    val allBookmarks by viewModel.allBookmarks.collectAsState()
    val timeFmt = remember { SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()) }

    val displayList = if (showCurrent) currentBookmarks else allBookmarks

    PanelScaffold(
        title = "书签",
        subtitle = "已保存 ${displayList.size} 条书签",
        onClose = { viewModel.toggleBookmarkPanel() },
        actions = {
            if (displayList.isNotEmpty()) {
                OutlinedButton(
                    onClick = {
                        if (showCurrent) viewModel.clearCurrentBookmarks()
                        else viewModel.clearAllBookmarks()
                    },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Close, contentDescription = null, tint = tvPalette.danger)
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        if (showCurrent) "清除当前" else "清空全部",
                        color = tvPalette.danger
                    )
                }
            }
        }
    ) {
        // 添加书签按钮
        OutlinedButton(
            onClick = { viewModel.addBookmark() },
            modifier = Modifier.fillMaxWidth().tvFocusBorder()
        ) {
            Icon(Icons.Default.Bookmark, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(modifier = Modifier.width(6.dp))
            Text("在当前位置添加书签", color = MaterialTheme.colorScheme.primary)
        }

        Spacer(modifier = Modifier.height(12.dp))

        // 视图切换
        SelectionGroup(
            title = "视图",
            options = listOf(
                "current" to "当前文件 (${currentBookmarks.size})",
                "all" to "所有文件 (${allBookmarks.size})"
            ),
            selectedKey = if (showCurrent) "current" else "all",
            onSelect = { key -> viewModel.setBookmarkShowCurrent(key == "current") }
        )

        Spacer(modifier = Modifier.height(12.dp))

        if (displayList.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().padding(top = 40.dp),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.Bookmark,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        if (showCurrent) "当前文件暂无书签" else "暂无任何书签",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        "点击上方按钮在当前位置添加书签",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }
            return@PanelScaffold
        }

        SettingsGroup("书签列表") {
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)
            ) {
                items(displayList, key = { it.id }) { item ->
                    BookmarkRow(
                        item = item,
                        timeFmt = timeFmt,
                        onGoto = { viewModel.gotoBookmark(item) },
                        onDelete = { viewModel.deleteBookmark(item) }
                    )
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        }
    }
}
@Composable
private fun BookmarkRow(
    item: BookmarkItem,
    timeFmt: SimpleDateFormat,
    onGoto: () -> Unit,
    onDelete: () -> Unit
) {
    // 格式化秒为 mm:ss 或 hh:mm:ss
    fun fmt(sec: Long): String {
        if (sec <= 0) return "00:00"
        val h = sec / 3600
        val m = (sec % 3600) / 60
        val s = sec % 60
        return if (h > 0) "%02d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            // 名称
            Text(
                text = item.name.ifBlank { "书签 @${fmt(item.position)}" },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            // 位置时间
            Row(
                modifier = Modifier.padding(top = 3.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.15f),
                    shape = RoundedCornerShape(3.dp)
                ) {
                    Text(
                        text = fmt(item.position),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                    )
                }
                Text(
                    text = timeFmt.format(Date(item.createdAt)),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp
                )
            }
            // URL（所有文件视图下显示）
            if (item.url.isNotEmpty()) {
                Text(
                    text = item.url,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
        }
        // 跳转按钮
        OutlinedButton(
            onClick = onGoto,
            modifier = Modifier.tvFocusBorder()
        ) {
            Text("跳转", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
        }
        Spacer(modifier = Modifier.width(4.dp))
        IconButton(onClick = onDelete, modifier = Modifier.size(32.dp).tvFocusBorder()) {
            Icon(
                Icons.Default.Close,
                contentDescription = "删除",
                tint = tvPalette.dangerSoft,
                modifier = Modifier.size(16.dp)
            )
        }
    }
}
/**
 * 经典频谱仪画布：底部升起的渐变柱 + 顶部缓降峰值点。
 * 供音频可视化面板与播放信息 Tab 共用。
 */
@Composable
internal fun SpectrumCanvas(spectrum: FloatArray, modifier: Modifier = Modifier) {
    // 峰值缓存：经典频谱仪的缓降峰值标记（60fps 下每帧回落 0.009）
    // 尺寸跟随频谱频段数（64），避免频段数变化后越界/不匹配
    val peaks = remember(spectrum.size) { FloatArray(spectrum.size) { 0f } }
    val outlineColor = MaterialTheme.colorScheme.outlineVariant
    Canvas(modifier) {
        val barCount = spectrum.size
        if (barCount == 0) return@Canvas
        val barWidth = size.width / barCount
        // 64 频段下柱条更细：间隙占槽位 45%（柱条实宽 55%），视觉更精致
        val gap = barWidth * 0.45f
        val actualBarWidth = barWidth - gap
        val bottomY = size.height * 0.92f
        val maxBarHeight = size.height * 0.82f
        // 垂直渐变：底部强调色 → 顶部亮强调色（原来顶部用 warning #FF9800，
        // 在浅色底上只有 1.71:1，视觉上像一排虚线）
        val barBrush = androidx.compose.ui.graphics.Brush.verticalGradient(
            colors = listOf(
                tvPalette.accentText,
                tvPalette.accentGraphic,
                tvPalette.accentGraphic
            ),
            startY = bottomY - maxBarHeight,
            endY = bottomY
        )
        // 底部基线
        drawLine(
            color = outlineColor.copy(alpha = 0.25f),
            start = androidx.compose.ui.geometry.Offset(0f, bottomY),
            end = androidx.compose.ui.geometry.Offset(size.width, bottomY),
            strokeWidth = 1.5f
        )

        spectrum.forEachIndexed { i, amplitude ->
            val x = i * barWidth + gap / 2
            // 感知压缩：原始振幅普遍只有 0.05~0.2，线性映射后只有十几像素，
            // 看起来像一排虚线；sqrt 让弱信号也能占住可用高度
            val shaped = sqrt(amplitude.coerceIn(0f, 1f))
            val barHeight = (shaped * maxBarHeight).coerceAtLeast(maxBarHeight * 0.05f)
            // 柱子从底部长出
            drawRoundRect(
                brush = barBrush,
                topLeft = androidx.compose.ui.geometry.Offset(x, bottomY - barHeight),
                size = androidx.compose.ui.geometry.Size(actualBarWidth, barHeight),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(actualBarWidth * 0.35f, actualBarWidth * 0.35f)
            )
            // 顶部缓降峰值点：升起即时跟随，回落缓慢（约 1.8 秒落底）
            peaks[i] = maxOf(peaks[i] - 0.009f, shaped)
            val peakY = bottomY - (peaks[i] * maxBarHeight).coerceAtLeast(3f) - actualBarWidth * 0.9f
            drawRoundRect(
                color = tvPalette.accentText.copy(alpha = 0.9f),
                topLeft = androidx.compose.ui.geometry.Offset(x, peakY),
                size = androidx.compose.ui.geometry.Size(actualBarWidth, actualBarWidth * 0.28f),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(actualBarWidth * 0.14f, actualBarWidth * 0.14f)
            )
        }
    }
}
/**
 * 音频可视化面板（与 PC 端 audio_visual 对齐）。
 * 实时频谱波形 Canvas 绘制。
 */
@Composable
fun AudioVisualizerPanel(viewModel: AppViewModel) {
    val spectrum by viewModel.audioSpectrum.collectAsState()
    val spectrumError by viewModel.audioSpectrumError.collectAsState()
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()

    // RECORD_AUDIO 是系统 Visualizer（真频谱）的硬性权限要求，
    // 打开面板时请求，授权后立即启动采样
    val context = LocalContext.current
    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            viewModel.startSpectrumSampling()
        } else {
            viewModel.setAudioSpectrumError("未授予麦克风权限\n系统 Visualizer 接口需要该权限才能获取真实频谱")
        }
    }
    LaunchedEffect(Unit) {
        val granted = androidx.core.content.ContextCompat.checkSelfPermission(
            context, android.Manifest.permission.RECORD_AUDIO
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED
        if (granted) {
            viewModel.startSpectrumSampling()
        } else {
            permLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
        }
    }

    PanelScaffold(
        title = "音频可视化",
        onClose = { viewModel.toggleAudioVisualizer() }
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (!fileLoaded) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text("请先加载音视频", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                }
                return@PanelScaffold
            }

        // 在 Canvas 外部提取颜色（Canvas 内部不能调用 @Composable）
        val primaryColor = MaterialTheme.colorScheme.primary
        val outlineColor = MaterialTheme.colorScheme.outlineVariant

        if (spectrumError.isNotEmpty()) {
            // 真频谱不可用：明确提示原因（不提供模拟数据）
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp)
                    .background(
                        MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(12.dp)
                    )
                    .clip(RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    spectrumError,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 14.sp,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
            }
        } else {
            SpectrumCanvas(
                spectrum = spectrum,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp)
                    .background(
                        MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(12.dp)
                    )
                    .clip(RoundedCornerShape(12.dp))
            )
        }

            // 信息行
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                val volume = mpv.getPropertyDouble("volume") ?: 100.0
                Text("音量: ${volume.toInt()}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Text("频段: ${spectrum.size}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
        }
    }
}
/**
 * 歌词面板（与 PC 端 LyricsWidget 对齐）。
 * 支持 LRC 格式歌词加载、显示和同步高亮。
 */
@Composable
fun LyricsPanel(viewModel: AppViewModel) {
    val lyricsLines by viewModel.lyricsLines.collectAsState()
    val currentLine by viewModel.currentLyricLine.collectAsState()
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()

    // SAF 文件选择器（选择 .lrc 文件）
    val filePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            viewModel.loadLyricsFromUri(uri.toString())
        }
    }

    PanelScaffold(
        title = "歌词",
        onClose = { viewModel.toggleLyricsPanel() }
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // 操作栏
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = { filePicker.launch(arrayOf("application/octet-stream", "text/plain", "*/*")) },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.UploadFile, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("加载 LRC", fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { viewModel.clearLyrics() },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("清除", fontSize = 12.sp, color = tvPalette.dangerSoft)
                }
            }

            if (lyricsLines.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.MusicNote,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(48.dp)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text("点击「加载 LRC」导入歌词文件", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                        if (fileLoaded) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text("播放时将自动同步高亮", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                        }
                    }
                }
                return@Column
            }

            // 歌词列表
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .weight(1f),
                contentPadding = PaddingValues(vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                itemsIndexed(lyricsLines) { index, line ->
                    val isCurrent = index == currentLine
                    val isPast = index < currentLine
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // 时间标签
                        val min = line.time / 60000
                        val sec = (line.time % 60000) / 1000
                        Text(
                            text = String.format("%02d:%05.2f", min, sec),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            modifier = Modifier.width(56.dp)
                        )
                        Text(
                            text = line.text,
                            color = when {
                                isCurrent -> tvPalette.success
                                isPast -> MaterialTheme.colorScheme.onSurfaceVariant
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            },
                            fontSize = if (isCurrent) 16.sp else 14.sp,
                            fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f)
                        )
                    }
                }
            }
        }
    }
}
