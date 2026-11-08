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
import androidx.compose.foundation.layout.imePadding
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
// =================================================================
// 频道映射面板
// =================================================================

/**
 * 频道映射面板：远程映射 + 用户映射管理。
 * 与 PC 端 mapping_manager_dialog.py 对齐：
 * - 列表展示映射条目（标准名 ← 原始名 + 分组/Logo/tvg-id 等）
 * - 搜索过滤（标准名 / 原始名 / 分组）
 * - 添加用户映射 / 删除 / 刷新远程缓存
 *
 * 约束（项目记忆）：不得显示"远程URL：未配置"
 */
@Composable
fun MappingPanel(viewModel: AppViewModel) {
    val mappingList by viewModel.mappingList.collectAsState()
    val mappingLoading by viewModel.mappingLoading.collectAsState()
    val statusText by viewModel.mappingStatusText.collectAsState()
    var searchQuery by remember { mutableStateOf("") }
    var showAddDialog by remember { mutableStateOf(false) }

    PanelScaffold(
        title = "频道映射",
        subtitle = "远程映射 + 用户映射管理",
        onClose = { viewModel.toggleMappingPanel() },
        actions = {
            OutlinedButton(
                onClick = { viewModel.refreshMappings() },
                enabled = !mappingLoading,
                modifier = Modifier.tvFocusBorder()
            ) {
                Text("刷新远程", color = MaterialTheme.colorScheme.onSurface, fontSize = 12.sp)
            }
            Spacer(modifier = Modifier.width(8.dp))
            OutlinedButton(
                onClick = { showAddDialog = true },
                modifier = Modifier.tvFocusBorder()
            ) {
                Text("添加", color = MaterialTheme.colorScheme.onSurface, fontSize = 12.sp)
            }
        }
    ) {
        Text(text = statusText, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)

        SettingsGroup("搜索过滤") {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                label = { Text("搜索（标准名 / 原始名 / 分组）") },
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).tvTextField(),
                singleLine = true
            )
        }

        if (mappingLoading) {
            Box(
                modifier = Modifier.fillMaxWidth().padding(32.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
        } else {
            val filtered = if (searchQuery.isBlank()) {
                mappingList
            } else {
                mappingList.filter { entry ->
                    entry.standardName.contains(searchQuery, ignoreCase = true) ||
                    entry.rawName.contains(searchQuery, ignoreCase = true) ||
                    (entry.groupName?.contains(searchQuery, ignoreCase = true) ?: false)
                }
            }
            SettingsGroup("映射列表") {
                DescText("共 ${filtered.size} 条${if (searchQuery.isNotBlank()) "（已过滤）" else ""}")
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)
                ) {
                    items(filtered) { entry ->
                        MappingEntryRow(
                            entry = entry,
                            onDelete = { viewModel.deleteMapping(entry.standardName, entry.rawName) }
                        )
                    }
                }
            }
        }
    }

    if (showAddDialog) {
        AddMappingDialog(
            onDismiss = { showAddDialog = false },
            onAdd = { raw, std, logo, group ->
                viewModel.addMapping(raw, std, logo, group)
                showAddDialog = false
            }
        )
    }
}
@Composable
private fun MappingEntryRow(
    entry: MappingEntry,
    onDelete: () -> Unit
) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = entry.standardName,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "← ${entry.rawName}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                val extras = listOfNotNull(
                    entry.groupName?.takeIf { it.isNotBlank() }?.let { "分组: $it" },
                    entry.tvgId?.takeIf { it.isNotBlank() }?.let { "tvg-id: $it" }
                ).joinToString("  |  ")
                if (extras.isNotEmpty()) {
                    Text(text = extras, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, maxLines = 1)
                }
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(32.dp).tvFocusBorder()) {
                Icon(Icons.Default.Close, contentDescription = "删除", tint = Color(0xFFE57373), modifier = Modifier.size(16.dp))
            }
        }
    }
}
@Composable
private fun AddMappingDialog(
    onDismiss: () -> Unit,
    onAdd: (rawName: String, standardName: String, logoUrl: String, groupName: String) -> Unit
) {
    var rawName by remember { mutableStateOf("") }
    var standardName by remember { mutableStateOf("") }
    var logoUrl by remember { mutableStateOf("") }
    var groupName by remember { mutableStateOf("") }

    // 遥控器：进入弹窗先把焦点落到第一个输入框（用户要用方向键+OK 输内容），
    // 输入框与按钮各自成焦点组，避免按键漏到弹窗背后的播放页/外层面板；
    // 等比延迟等待 Dialog 窗口真正拿到焦点后再 requestFocus，失败时重试一次。
    val firstFieldFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(100)
        if (runCatching { firstFieldFocus.requestFocus() }.isFailure) {
            kotlinx.coroutines.delay(200)
            runCatching { firstFieldFocus.requestFocus() }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("添加用户映射") },
        text = {
            // verticalScroll + imePadding：键盘弹出压缩窗口时可滚动，输入框不被遮挡
            Column(
                modifier = Modifier
                    .focusGroup()
                    .verticalScroll(rememberScrollState())
                    .imePadding()
            ) {
                OutlinedTextField(
                    value = rawName, onValueChange = { rawName = it },
                    label = { Text("原始频道名") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                        .tvTextField().focusRequester(firstFieldFocus),
                    singleLine = true
                )
                OutlinedTextField(
                    value = standardName, onValueChange = { standardName = it },
                    label = { Text("标准频道名") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).tvTextField(),
                    singleLine = true
                )
                OutlinedTextField(
                    value = logoUrl, onValueChange = { logoUrl = it },
                    label = { Text("Logo URL（可选）") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).tvTextField(),
                    singleLine = true
                )
                OutlinedTextField(
                    value = groupName, onValueChange = { groupName = it },
                    label = { Text("分组名（可选）") },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp).tvTextField(),
                    singleLine = true
                )
            }
        },
        // 两个按钮合并到同一焦点组：方向键可在「取消」「添加」间切换，OK 触发
        confirmButton = {
            Row(
                modifier = Modifier.focusGroup(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.tvFocusBorder()
                ) { Text("取消") }
                TextButton(
                    onClick = { onAdd(rawName, standardName, logoUrl, groupName) },
                    enabled = rawName.isNotBlank() && standardName.isNotBlank(),
                    modifier = Modifier.tvFocusBorder()
                ) { Text("添加") }
            }
        }
    )
}
// -----------------------------------------------------------------
// URL 范围扫描面板
// -----------------------------------------------------------------

/**
 * URL 范围扫描面板：与 PC 端扫描功能对齐，后端为 StandaloneScanner。
 *
 * 功能：
 * - 输入基础 URL（支持 [1-255] 范围表达式）
 * - 调整超时和线程数
 * - 实时显示扫描进度（已扫描/有效/无效）
 * - 显示扫描结果列表
 *
 * 扫描完成后，有效频道会自动追加到频道列表（分组"扫描结果"），由后端 StandaloneScanner 处理。
 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ScanPanel(viewModel: AppViewModel) {
    val scanStatus by viewModel.scanStatus.collectAsState()
    val scanResults by viewModel.scanResults.collectAsState()
    val scanLoading by viewModel.scanLoading.collectAsState()
    val scanError by viewModel.scanError.collectAsState()

    var baseUrl by remember { mutableStateOf("http://192.168.1.[1-255]:8080") }
    var timeout by remember { mutableStateOf(10) }
    var threads by remember { mutableStateOf(4) }

    // 结果整理：筛选与排序
    var validOnly by remember { mutableStateOf(false) }
    var sortByLatency by remember { mutableStateOf(false) }

    val running = scanStatus?.running == true

    // 应用筛选与排序
    val displayedResults = remember(scanResults, validOnly, sortByLatency) {
        var list = if (validOnly) scanResults.filter { it.valid } else scanResults
        if (sortByLatency) {
            list = list.sortedWith(compareByDescending<ScanResult> { it.latency }
                .thenBy { it.name })
        }
        list
    }

    PanelScaffold(
        title = "URL 范围扫描",
        subtitle = "扫描 IP 范围内的 IPTV 服务（支持方括号范围表达式）",
        onClose = { viewModel.toggleScanPanel() }
    ) {
        // 参数表单
        SettingsGroup("扫描参数") {
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = { Text("基础 URL") },
                placeholder = { Text("rtp://239.1.1.[1-255]:5002 或 http://x.com/[1-100:n]/{n}.m3u8") },
                singleLine = true,
                enabled = !running,
                modifier = Modifier.fillMaxWidth().tvTextField()
            )
            DescText("支持方括号范围表达式：")
            DescText("· [1-255] 数字范围（如 192.168.1.[1-255]）")
            DescText("· [1,5,10] 列表枚举")
            DescText("· [1-10,20-30] 范围与列表混合")
            DescText("· [1-255:n] 命名变量，可用 {n} 在 URL 其他位置引用并同步变化")
            DescText("· 多个独立表达式按笛卡尔积展开")

            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val oc2 = rememberPlayerOverlayColors()
                Column(modifier = Modifier.weight(1f)) {
                    Text("超时: ${timeout}s", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    Slider(
                        value = timeout.toFloat(),
                        onValueChange = { timeout = it.toInt().coerceIn(3, 30) },
                        valueRange = 3f..30f,
                        enabled = !running,
                        modifier = Modifier.fillMaxWidth().tvFocusBorder(),
                        thumb = {
                            Box(
                                modifier = Modifier
                                    .size(16.dp)
                                    .background(oc2.accent, androidx.compose.foundation.shape.CircleShape)
                                    .then(Modifier.border(2.dp, oc2.accent.copy(alpha = 0.3f), androidx.compose.foundation.shape.CircleShape))
                            )
                        },
                        colors = SliderDefaults.colors(
                            thumbColor = oc2.accent,
                            activeTrackColor = oc2.accent,
                            inactiveTrackColor = oc2.trackInactive
                        )
                    )
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text("线程: ${threads}", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    Slider(
                        value = threads.toFloat(),
                        onValueChange = { threads = it.toInt().coerceIn(1, 16) },
                        valueRange = 1f..16f,
                        enabled = !running,
                        modifier = Modifier.fillMaxWidth().tvFocusBorder(),
                        thumb = {
                            Box(
                                modifier = Modifier
                                    .size(16.dp)
                                    .background(oc2.accent, androidx.compose.foundation.shape.CircleShape)
                                    .then(Modifier.border(2.dp, oc2.accent.copy(alpha = 0.3f), androidx.compose.foundation.shape.CircleShape))
                            )
                        },
                        colors = SliderDefaults.colors(
                            thumbColor = oc2.accent,
                            activeTrackColor = oc2.accent,
                            inactiveTrackColor = oc2.trackInactive
                        )
                    )
                }
            }

            // 控制按钮
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (running) {
                    OutlinedButton(
                        onClick = { viewModel.stopScan() },
                        modifier = Modifier.tvFocusBorder()
                    ) {
                        Icon(Icons.Default.Close, contentDescription = null, tint = Color(0xFFFF5252))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("停止扫描", color = Color(0xFFFF5252))
                    }
                } else {
                    OutlinedButton(
                        onClick = { viewModel.startScan(baseUrl.trim(), timeout, threads) },
                        enabled = !scanLoading,
                        modifier = Modifier.tvFocusBorder()
                    ) {
                        if (scanLoading) {
                            CircularProgressIndicator(
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(16.dp)
                            )
                        } else {
                            Icon(Icons.Default.Radar, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("开始扫描", color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }

            // 错误提示
            if (scanError.isNotEmpty()) {
                Text(
                    text = scanError,
                    color = Color(0xFFFF5252),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(vertical = 4.dp)
                )
            }
        }

        // 进度
        scanStatus?.let { status ->
            SettingsGroup("进度") {
                val progress = if (status.total > 0) {
                    status.scanned.toFloat() / status.total
                } else 0f
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("已扫描: ${status.scanned}/${status.total}", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    Text("有效: ${status.valid}", color = Color(0xFF4CAF50), fontSize = 13.sp)
                    Text("无效: ${status.invalid}", color = Color(0xFFFF5252), fontSize = 13.sp)
                }
                LinearProgressIndicator(
                    progress = { progress },
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    color = MaterialTheme.colorScheme.primary,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant
                )
                if (status.message.isNotEmpty()) {
                    Text(status.message, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
            }
        }

        // 结果列表
        if (scanResults.isNotEmpty()) {
            // 工具栏：筛选 / 排序 / 导出 / 清空
            Row(
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "扫描结果（${scanResults.size} 条，有效 ${scanResults.count { it.valid }}）",
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f)
                )
                // 筛选：仅有效
                FilterChip(
                    selected = validOnly,
                    onClick = { validOnly = !validOnly },
                    label = { Text("仅有效", fontSize = 11.sp) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.3f),
                        selectedLabelColor = MaterialTheme.colorScheme.primary
                    )
                )
                // 排序：按延迟
                FilterChip(
                    selected = sortByLatency,
                    onClick = { sortByLatency = !sortByLatency },
                    label = { Text("按延迟", fontSize = 11.sp) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.3f),
                        selectedLabelColor = MaterialTheme.colorScheme.primary
                    )
                )
                // 导入到播放列表
                OutlinedButton(
                    onClick = { viewModel.importScanResultsToChannels() },
                    enabled = !scanLoading,
                    modifier = Modifier.tvFocusBorder().height(32.dp)
                ) {
                    Icon(Icons.Default.PlaylistAdd, contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("导入", color = MaterialTheme.colorScheme.primary, fontSize = 11.sp)
                }
                // 导出为 M3U 文件
                OutlinedButton(
                    onClick = { viewModel.exportScanResultsAsM3u() },
                    modifier = Modifier.tvFocusBorder().height(32.dp)
                ) {
                    Icon(Icons.Default.FileDownload, contentDescription = null,
                        tint = Color(0xFF4CAF50), modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("导出", color = Color(0xFF4CAF50), fontSize = 11.sp)
                }
                // 清空结果
                IconButton(
                    onClick = { viewModel.clearScanResults() },
                    modifier = Modifier.tvFocusBorder().size(32.dp)
                ) {
                    Icon(Icons.Default.DeleteOutline, contentDescription = "清空结果",
                        tint = Color(0xFFFF5252), modifier = Modifier.size(18.dp))
                }
            }
            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 400.dp)
            ) {
                items(displayedResults, key = { it.url }) { result ->
                    ScanResultRow(result, onDelete = { viewModel.deleteScanResult(result.url) })
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        }
    }
}
@Composable
private fun ScanResultRow(result: ScanResult, onDelete: () -> Unit = {}) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = result.name.ifBlank { result.url },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 13.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Row(
                modifier = Modifier.padding(top = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    color = if (result.valid) Color(0xFF4CAF50).copy(alpha = 0.2f)
                            else Color(0xFFFF5252).copy(alpha = 0.2f),
                    shape = RoundedCornerShape(3.dp)
                ) {
                    Text(
                        text = if (result.valid) "有效" else "无效",
                        color = if (result.valid) Color(0xFF4CAF50) else Color(0xFFFF5252),
                        fontSize = 10.sp,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                    )
                }
                if (result.latency > 0) {
                    Text("${result.latency}ms", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                if (result.status.isNotEmpty()) {
                    Text(result.status, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Text(
                text = result.url,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
        // 删除单条结果
        IconButton(
            onClick = onDelete,
            modifier = Modifier.tvFocusBorder().size(28.dp)
        ) {
            Icon(Icons.Default.Close, contentDescription = "删除",
                tint = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.size(16.dp))
        }
    }
}
// =================================================================
// 新增功能面板
// =================================================================

/**
 * 最近打开文件面板（与 PC 端 recent_menu 对齐）。
 * 显示最近打开的播放列表文件、网络流 URL、本地视频文件。
 */
@Composable
fun RecentFilesPanel(viewModel: AppViewModel) {
    val recentFiles by viewModel.recentFiles.collectAsState()

    PanelScaffold(
        title = "最近打开",
        onClose = { viewModel.toggleRecentPanel() }
    ) {
        if (recentFiles.isEmpty()) {
            // 空状态也包分组玻璃卡片，与有内容时观感一致（不出现整块空白）
            SettingsGroup("最近文件") {
                Box(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 28.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.History,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(40.dp)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("暂无最近打开记录", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
                    }
                }
            }
            return@PanelScaffold
        }

        SettingsGroup("最近文件") {
            Column(
                modifier = Modifier
                    .fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                // 清空按钮
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    OutlinedButton(
                        onClick = { viewModel.clearRecentFiles() },
                        modifier = Modifier.tvFocusBorder()
                    ) {
                        Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("清空", color = Color(0xFFE57373), fontSize = 12.sp)
                    }
                }
            // 最近打开列表
            recentFiles.forEach { entry ->
                val typeIcon = when (entry.type) {
                    "playlist" -> Icons.Default.VideoLibrary
                    "url" -> Icons.Default.Link
                    else -> Icons.Default.PlayCircle
                }
                val typeLabel = when (entry.type) {
                    "playlist" -> "播放列表"
                    "url" -> "网络流"
                    else -> "视频"
                }
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        // tvFocusBorder 在 clickable 之前（外层）才能收到焦点事件
                        .tvFocusBorder()
                        .clickable { viewModel.playRecent(entry) }
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            typeIcon,
                            contentDescription = typeLabel,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = entry.name,
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = "$typeLabel · ${entry.uri.take(60)}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                        IconButton(
                            onClick = { viewModel.removeRecentFile(entry.uri) },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "移除",
                                tint = Color(0xFFE57373),
                                modifier = Modifier.size(16.dp)
                            )
                        }
                    }
                }
            }
        }
        }
    }
}