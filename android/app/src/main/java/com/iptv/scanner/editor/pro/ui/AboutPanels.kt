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
import androidx.compose.foundation.verticalScroll
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
// 关于面板
// -----------------------------------------------------------------

/**
 * 关于面板：版本信息 + 检查更新 + 功能说明。
 */
@Composable
fun AboutPanel(viewModel: AppViewModel) {
    val currentVersion = remember { viewModel.getCurrentVersion() }
    val updateState by viewModel.updateState.collectAsState()

    PanelScaffold(
        title = "关于",
        subtitle = "光屿",
        onClose = { viewModel.toggleAboutPanel() }
    ) {
        SettingsGroup("版本信息") {
            // SettingsGroup 在 APTV 模式下已自带玻璃卡容器，此处直接排 InfoRow，避免双层嵌套
            Column(modifier = Modifier.fillMaxWidth()) {
                InfoRow("应用名称", "光屿 GuangYu")
                InfoRow("版本", currentVersion)
                InfoRow("播放引擎", "mpv (libmpv)")
                InfoRow("UI 框架", "Jetpack Compose")
                InfoRow("Python 引擎", "Chaquopy")
            }
        }

        SettingsGroup("版本检查") {
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedButton(
                    onClick = { viewModel.checkForUpdates(auto = false) },
                    enabled = updateState !is UpdateState.Checking,
                    modifier = Modifier.tvFocusBorder()
                ) {
                    if (updateState is UpdateState.Checking) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("检查中...")
                    } else {
                        Text("检查更新")
                    }
                }
                when (updateState) {
                    is UpdateState.Checking -> {}
                    is UpdateState.UpToDate -> {
                        Text("当前已是最新版本", color = tvPalette.success, fontSize = 13.sp)
                    }
                    is UpdateState.UpdateAvailable -> {
                        val info = updateState as UpdateState.UpdateAvailable
                        Text(
                            "发现新版本 v${info.latestVersion}（当前 v$currentVersion）",
                            color = MaterialTheme.colorScheme.tertiary,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                    is UpdateState.Error -> {
                        val err = updateState as UpdateState.Error
                        Text("检查失败: ${err.message}", color = tvPalette.danger, fontSize = 13.sp)
                    }
                    else -> {}
                }
            }
        }

        SettingsGroup("功能特性") {
            val features = listOf(
                "频道播放：支持 HLS/RTSP/RTMP/HTTP 等协议",
                "订阅源管理：M3U 播放列表 CRUD + 自动加载",
                "EPG 节目单：XMLTV 格式，按频道/日期/搜索",
                "回看/时移：catchup-source 支持，EPG 过去节目回看",
                "视频调整：亮度/对比度/饱和度/色调/Gamma/旋转/翻转",
                "音频调整：音轨切换/延迟/10段EQ预设",
                "字幕：轨道切换/延迟/缩放/位置/外挂加载",
                "截图：仅画面/含字幕/含 OSD",
                "播放控制：循环/AB循环/逐帧/速度/章节",
                "局域网管理：TV 端遥控器扫码管理（5分钟自动停止）",
                "备份恢复：订阅源/EPG源/收藏/历史/队列/播放器设置",
                "TV 适配：DPAD 遥控器/手机触摸双模式"
            )
            features.forEach { feature ->
                Text(
                    text = "• $feature",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 2.dp, horizontal = 4.dp)
                )
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
/**
 * 更新提示对话框：发现新版本时弹出，提供应用内直接下载安装功能。
 *
 * 与 PC 端 UpdateController 的更新提示对齐。
 * 改进：TV 端跳转浏览器不便，改为通过 DownloadManager 直接下载 APK 并调起系统安装器。
 *
 * UI 状态：
 * - Idle / UpdateAvailable：显示「立即更新」按钮
 * - Downloading(progress)：显示进度条 + 「取消」按钮（禁用关闭）
 * - Completed：显示「立即安装」按钮（自动调起安装，按钮作为备用入口）
 * - Error：显示错误信息 + 「重试」按钮
 */
@Composable
fun UpdateDialog(viewModel: AppViewModel) {
    val open by viewModel.updateDialogOpen.collectAsState()
    if (!open) return

    val updateState by viewModel.updateState.collectAsState()
    val currentVersion = remember { viewModel.getCurrentVersion() }
    val apkState by viewModel.apkDownloadState.collectAsState()

    val info = updateState as? UpdateState.UpdateAvailable
    if (info == null) {
        viewModel.dismissUpdateDialog()
        return
    }

    val isDownloading = apkState is ApkDownloadState.Downloading
    val progress = (apkState as? ApkDownloadState.Downloading)?.progress ?: 0
    val isAptv = LocalConfiguration.current.orientation == Configuration.ORIENTATION_PORTRAIT
    val accentColor = if (isAptv) tvPalette.accentText else MaterialTheme.colorScheme.primary
    val isTv = viewModel.uiMode.collectAsState().value.isTV
    val context = androidx.compose.ui.platform.LocalContext.current

    // 遥控器操作：弹窗打开后必须把焦点落到按钮上，并把按钮整组设为焦点组，
    // 否则方向键/OK 会漏到背后播放页的全局按键逻辑（OK 会打开/关闭面板），
    // 表现为「按 OK 弹窗就消失、按钮点不到」。与退出确认弹窗同一套修法：
    // FocusRequester + 默认焦点 + focusGroup()。
    val primaryFocus = remember { FocusRequester() }
    var urlCopied by remember { mutableStateOf(false) }
    val phase = when (apkState) {
        is ApkDownloadState.Idle -> "idle"
        is ApkDownloadState.Downloading -> "downloading"
        is ApkDownloadState.Completed -> "completed"
        is ApkDownloadState.Error -> "error"
    }
    LaunchedEffect(phase) {
        kotlinx.coroutines.delay(50)
        runCatching { primaryFocus.requestFocus() }
    }

    AlertDialog(
        onDismissRequest = {
            // 下载中不允许点外部关闭（防止误触中断下载）
            if (!isDownloading) viewModel.dismissUpdateDialog()
        },
        title = { Text("发现新版本", fontWeight = FontWeight.Bold) },
        text = {
            Column {
                Text(
                    "新版本 v${info.latestVersion} 已发布",
                    color = if (isAptv) tvPalette.accentText else MaterialTheme.colorScheme.tertiary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    "当前版本：v$currentVersion",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp
                )
                Spacer(modifier = Modifier.height(12.dp))

                when (val s = apkState) {
                    is ApkDownloadState.Idle -> {
                        Text(
                            "点击「立即更新」开始下载并安装最新版 APK。",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp
                        )
                    }
                    is ApkDownloadState.Downloading -> {
                        Text(
                            "正在下载更新包… ${s.progress}%",
                            color = accentColor,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        LinearProgressIndicator(
                            progress = { s.progress / 100f },
                            modifier = Modifier.fillMaxWidth(),
                            color = accentColor,
                            trackColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            "下载过程中请保持网络畅通，完成后将自动弹出安装界面。",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp
                        )
                    }
                    is ApkDownloadState.Completed -> {
                        Text(
                            "下载完成，正在启动安装程序…",
                            color = tvPalette.success,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            "若安装界面未自动弹出，请点击「立即安装」重试。",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp
                        )
                    }
                    is ApkDownloadState.Error -> {
                        Text(
                            s.message,
                            color = tvPalette.dangerSoft,
                            fontSize = 13.sp
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        if (isTv) {
                            // TV 上没有可用浏览器（系统 VIEW 仅落到 BrowserStub），
                            // 所以改为展示完整地址 + 提醒到手机/电脑打开，并支持一键复制。
                            Text(
                                "请先重试；若仍失败，请在手机或电脑浏览器中打开下方地址下载：",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                info.downloadUrl,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp
                            )
                            if (urlCopied) {
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    "已复制下载地址，可在手机/电脑浏览器中粘贴打开。",
                                    color = tvPalette.success,
                                    fontSize = 11.sp
                                )
                            }
                        } else {
                            Text(
                                "请重试，或点击「浏览器下载」跳转 GitHub 手动安装。",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            // 所有按钮放在同一焦点组内：方向键在组内循环切换，OK 触发当前焦点项，
            // 不让按键漏到弹窗背后的播放页全局逻辑。
            Row(
                modifier = Modifier.focusGroup(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                when (apkState) {
                    is ApkDownloadState.Idle -> {
                        TextButton(
                            onClick = { viewModel.dismissUpdateDialog() },
                            modifier = Modifier.tvFocusBorder()
                        ) { Text("稍后提醒") }
                        TextButton(
                            onClick = { viewModel.downloadAndInstallApk(info.downloadUrl) },
                            modifier = Modifier.tvFocusBorder().focusRequester(primaryFocus)
                        ) { Text("立即更新", color = accentColor) }
                    }
                    is ApkDownloadState.Downloading -> {
                        // 下载中只显示取消按钮
                        TextButton(
                            onClick = { viewModel.cancelApkDownload() },
                            modifier = Modifier.tvFocusBorder().focusRequester(primaryFocus)
                        ) { Text("取消下载", color = tvPalette.dangerSoft) }
                    }
                    is ApkDownloadState.Completed -> {
                        TextButton(
                            onClick = { viewModel.dismissUpdateDialog() },
                            modifier = Modifier.tvFocusBorder()
                        ) { Text("关闭") }
                        TextButton(
                            onClick = { viewModel.installDownloadedApk() },
                            modifier = Modifier.tvFocusBorder().focusRequester(primaryFocus)
                        ) { Text("立即安装") }
                    }
                    is ApkDownloadState.Error -> {
                        TextButton(
                            onClick = { viewModel.dismissUpdateDialog() },
                            modifier = Modifier.tvFocusBorder()
                        ) { Text("关闭") }
                        if (isTv) {
                            // TV 无可用浏览器：改为复制下载地址（地址已在正文展示）
                            TextButton(
                                onClick = {
                                    val cm = context.getSystemService(
                                        android.content.Context.CLIPBOARD_SERVICE
                                    ) as? android.content.ClipboardManager
                                    cm?.setPrimaryClip(
                                        android.content.ClipData.newPlainText(
                                            "更新下载地址", info.downloadUrl
                                        )
                                    )
                                    urlCopied = true
                                },
                                modifier = Modifier.tvFocusBorder()
                            ) { Text(if (urlCopied) "已复制" else "复制链接") }
                        } else {
                            TextButton(
                                onClick = {
                                    // 备用方案：跳转浏览器（用于下载失败或特殊场景）
                                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(info.downloadUrl))
                                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    try {
                                        context.startActivity(intent)
                                        viewModel.dismissUpdateDialog()
                                    } catch (e: Exception) {
                                        Log.e("UpdateDialog", "open browser failed", e)
                                    }
                                },
                                modifier = Modifier.tvFocusBorder()
                            ) { Text("浏览器下载") }
                        }
                        TextButton(
                            onClick = { viewModel.downloadAndInstallApk(info.downloadUrl) },
                            modifier = Modifier.tvFocusBorder().focusRequester(primaryFocus)
                        ) { Text("重试") }
                    }
                }
            }
        }
    )
}
