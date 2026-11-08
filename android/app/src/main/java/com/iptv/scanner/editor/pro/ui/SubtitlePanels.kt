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
// 字幕设置面板
// -----------------------------------------------------------------

/**
 * 字幕设置面板：与 PC 端 controllers/subtitle_controller.py 对齐。
 *
 * 功能：
 * - 字幕轨选择
 * - 字幕显示开关
 * - 字幕延迟（-10~10s）
 * - 字幕缩放（0.5~3.0）
 * - 字幕位置（0~100）
 * - 加载外挂字幕（文件选择器）
 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun SubtitleSettingsPanel(viewModel: AppViewModel) {
    val mpv = viewModel.mpv
    val fileLoaded by mpv.fileLoaded.collectAsState()
    val trackListJson by mpv.trackListJson.collectAsState()

    // 字幕轨列表
    val subTracks = remember(trackListJson) { parseTracks(trackListJson, "sub") }
    var currentSid by remember { mutableStateOf(0) }
    var subVisible by remember { mutableStateOf(mpv.getPropertyBoolean("sub-visibility") ?: true) }
    var subDelay by remember { mutableStateOf(mpv.getPropertyDouble("sub-delay") ?: 0.0) }
    var subScale by remember { mutableStateOf(mpv.getPropertyDouble("sub-scale") ?: 1.0) }
    var subPos by remember { mutableStateOf(mpv.getPropertyInt("sub-pos") ?: 0) }
    // 字幕样式（与 PC 端 SubtitleStyleDialog 对齐）
    var subFontSize by remember { mutableStateOf((mpv.getPropertyInt("sub-font-size") ?: 55)) }
    var subColor by remember { mutableStateOf(mpv.getPropertyString("sub-color") ?: "#FFFFFFFF") }
    var subBorderColor by remember { mutableStateOf(mpv.getPropertyString("sub-border-color") ?: "#FF000000") }
    var subBorderSize by remember { mutableStateOf((mpv.getPropertyDouble("sub-border-size") ?: 2.5)) }
    var subShadowOffset by remember { mutableStateOf((mpv.getPropertyDouble("sub-shadow-offset") ?: 0.0)) }
    var subBold by remember { mutableStateOf((mpv.getPropertyInt("sub-bold") ?: 1) == 1) }
    var subItalic by remember { mutableStateOf((mpv.getPropertyInt("sub-italic") ?: 0) == 1) }

    // 文件选择器（加载外挂字幕）
    val subLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) viewModel.loadSubtitleFile(uri)
    }

    LaunchedEffect(trackListJson) {
        currentSid = mpv.getPropertyInt("sid") ?: 0
    }

    PanelScaffold(
        title = "字幕设置",
        subtitle = "轨道 / 延迟 / 缩放 / 位置 / 样式 / 加载",
        onClose = { viewModel.toggleSubtitleSettings() },
        actions = {
            // 在线搜索字幕按钮
            IconButton(onClick = {
                viewModel.toggleSubtitleSettings()
                viewModel.toggleSubtitleSearchPanel()
            }, modifier = Modifier.tvFocusBorder()) {
                Icon(Icons.Default.Search, contentDescription = "在线搜索字幕", tint = MaterialTheme.colorScheme.onSurface)
            }
            // 加载外挂字幕按钮
            IconButton(onClick = {
                subLauncher.launch(arrayOf(
                    "application/x-subrip", "text/plain", "application/octet-stream",
                    "application/x-srt", "application/x-ass", "application/x-ssa"
                ))
            }, modifier = Modifier.tvFocusBorder()) {
                Icon(Icons.Default.Subtitles, contentDescription = "加载字幕", tint = MaterialTheme.colorScheme.onSurface)
            }
            TextButton(
                onClick = {
                    subDelay = 0.0; mpv.setSubDelay(0.0)
                    subScale = 1.0; mpv.setSubScale(1.0)
                    subPos = 0; mpv.setSubPos(0)
                    // 重置字幕样式为默认值
                    subFontSize = 55; mpv.setPropertyString("sub-font-size", "55")
                    subColor = "#FFFFFFFF"; mpv.setPropertyString("sub-color", "#FFFFFFFF")
                    subBorderColor = "#FF000000"; mpv.setPropertyString("sub-border-color", "#FF000000")
                    subBorderSize = 2.5; mpv.setPropertyString("sub-border-size", "2.5")
                    subShadowOffset = 0.0; mpv.setPropertyString("sub-shadow-offset", "0")
                    subBold = true; mpv.setPropertyString("sub-bold", "1")
                    subItalic = false; mpv.setPropertyString("sub-italic", "0")
                    viewModel.showOsd("字幕设置", "已重置")
                },
                modifier = Modifier.tvFocusBorder()
            ) { Text("重置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
        }
    ) {
        if (!fileLoaded) {
            Text("未在播放", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }

        // 字幕显示开关
        SettingsGroup("字幕显示") {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("显示字幕", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                Switch(
                    checked = subVisible,
                    onCheckedChange = { subVisible = it; mpv.setSubVisibility(it) },
                    modifier = Modifier.tvFocusBorder()
                )
            }
        }

        SettingsGroup("字幕轨") {
            if (subTracks.isEmpty()) {
                DescText("无内置字幕轨，可点击右上角图标加载外挂字幕")
            } else {
                SelectionGroup(
                    title = "字幕轨",
                    options = subTracks.map { (id, title) -> id.toString() to title },
                    selectedKey = currentSid.toString(),
                    onSelect = { key -> currentSid = key.toInt(); mpv.setSubTrack(key.toInt()) }
                )
            }
        }

        SettingsGroup("字幕延迟") {
            LabeledSlider(
                label = "延迟（秒）",
                value = subDelay.toFloat(),
                range = -10f..10f,
                valueText = "${"%.1f".format(subDelay)}s",
                onValueChange = { subDelay = it.toDouble(); mpv.setSubDelay(subDelay) },
                onReset = { subDelay = 0.0; mpv.setSubDelay(0.0) }
            )
        }

        SettingsGroup("字幕缩放") {
            LabeledSlider(
                label = "缩放",
                value = subScale.toFloat(),
                range = 0.5f..3.0f,
                valueText = "${"%.1f".format(subScale)}x",
                onValueChange = { subScale = it.toDouble(); mpv.setSubScale(subScale) },
                onReset = { subScale = 1.0; mpv.setSubScale(1.0) }
            )
        }

        SettingsGroup("字幕位置（距底部 %）") {
            LabeledSlider(
                label = "位置",
                value = subPos.toFloat(),
                range = 0f..100f,
                valueText = "$subPos%",
                onValueChange = { subPos = it.toInt(); mpv.setSubPos(subPos) },
                onReset = { subPos = 0; mpv.setSubPos(0) }
            )
        }

        // -----------------------------------------------------------------
        // 字幕样式（与 PC 端 SubtitleStyleDialog 对齐）
        // -----------------------------------------------------------------
        SettingsGroup("字幕样式") {
            DescText("颜色/字体/边框/阴影高级设置")

            // 快速预设
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf(
                    "默认" to mapOf(
                        "font-size" to "55", "color" to "#FFFFFFFF",
                        "border-color" to "#FF000000", "border-size" to "2.5",
                        "bold" to "1", "italic" to "0", "shadow-offset" to "0"
                    ),
                    "黄字黑边" to mapOf(
                        "font-size" to "55", "color" to "#FFFFFF00",
                        "border-color" to "#FF000000", "border-size" to "2.5",
                        "bold" to "1", "italic" to "0", "shadow-offset" to "0"
                    ),
                    "白字大号" to mapOf(
                        "font-size" to "72", "color" to "#FFFFFFFF",
                        "border-color" to "#FF000000", "border-size" to "3",
                        "bold" to "1", "italic" to "0", "shadow-offset" to "0"
                    ),
                    "无边框带阴影" to mapOf(
                        "font-size" to "55", "color" to "#FFFFFFFF",
                        "border-color" to "#FF000000", "border-size" to "0",
                        "bold" to "1", "italic" to "0", "shadow-offset" to "2"
                    )
                ).forEach { (name, style) ->
                    OutlinedButton(
                        onClick = {
                            subFontSize = style["font-size"]?.toIntOrNull() ?: 55
                            subColor = style["color"] ?: "#FFFFFFFF"
                            subBorderColor = style["border-color"] ?: "#FF000000"
                            subBorderSize = style["border-size"]?.toDoubleOrNull() ?: 2.5
                            subShadowOffset = style["shadow-offset"]?.toDoubleOrNull() ?: 0.0
                            subBold = style["bold"] == "1"
                            subItalic = style["italic"] == "1"
                            style.forEach { (k, v) -> mpv.setPropertyString("sub-$k", v) }
                            viewModel.showOsd("字幕样式", name)
                        },
                        modifier = Modifier.tvFocusBorder()
                    ) { Text(name, fontSize = 11.sp) }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 字体大小
            LabeledSlider(
                label = "字体大小",
                value = subFontSize.toFloat(),
                range = 10f..100f,
                valueText = subFontSize.toString(),
                onValueChange = { subFontSize = it.toInt(); mpv.setPropertyString("sub-font-size", subFontSize.toString()) },
                onReset = { subFontSize = 55; mpv.setPropertyString("sub-font-size", "55") }
            )

            // 边框粗细
            LabeledSlider(
                label = "边框粗细",
                value = subBorderSize.toFloat(),
                range = 0f..10f,
                valueText = "${"%.1f".format(subBorderSize)}",
                onValueChange = { subBorderSize = it.toDouble(); mpv.setPropertyString("sub-border-size", "%.1f".format(subBorderSize)) },
                onReset = { subBorderSize = 2.5; mpv.setPropertyString("sub-border-size", "2.5") }
            )

            // 阴影偏移
            LabeledSlider(
                label = "阴影偏移",
                value = subShadowOffset.toFloat(),
                range = 0f..10f,
                valueText = "${"%.1f".format(subShadowOffset)}",
                onValueChange = { subShadowOffset = it.toDouble(); mpv.setPropertyString("sub-shadow-offset", "%.1f".format(subShadowOffset)) },
                onReset = { subShadowOffset = 0.0; mpv.setPropertyString("sub-shadow-offset", "0") }
            )

            // 字幕颜色选择（预设色块）
            Text("字幕颜色", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 4.dp)) {
                listOf(
                    "#FFFFFFFF" to MaterialTheme.colorScheme.onSurface, "#FFFFFF00" to Color.Yellow,
                    "#FFFF0000" to Color.Red, "#FF00FF00" to Color.Green,
                    "#FF00FFFF" to Color.Cyan, "#FF000000" to Color.Black
                ).forEach { (hex, color) ->
                    Surface(
                        color = color,
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier
                            .size(28.dp)
                            .clickable {
                                subColor = hex
                                mpv.setPropertyString("sub-color", hex)
                            }
                            .tvFocusBorder()
                    ) {
                        if (subColor.equals(hex, ignoreCase = true)) {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Text("✓", color = if (color == Color.Black) MaterialTheme.colorScheme.onSurface else Color.Black, fontSize = 14.sp)
                            }
                        }
                    }
                }
            }

            // 边框颜色选择（预设色块）
            Text("边框颜色", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 4.dp)) {
                listOf(
                    "#FF000000" to Color.Black, "#FFFFFFFF" to MaterialTheme.colorScheme.onSurface,
                    "#FFFF0000" to Color.Red, "#FF0000FF" to Color.Blue,
                    "#FF00FF00" to Color.Green, "#00000000" to Color.Transparent
                ).forEach { (hex, color) ->
                    Surface(
                        color = color,
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier
                            .size(28.dp)
                            .clickable {
                                subBorderColor = hex
                                mpv.setPropertyString("sub-border-color", hex)
                            }
                            .tvFocusBorder()
                    ) {
                        if (subBorderColor.equals(hex, ignoreCase = true)) {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Text("✓", color = if (color == Color.Black) MaterialTheme.colorScheme.onSurface else Color.Black, fontSize = 14.sp)
                            }
                        }
                    }
                }
            }

            // 加粗 / 斜体开关
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("加粗", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                    Switch(
                        checked = subBold,
                        onCheckedChange = { subBold = it; mpv.setPropertyString("sub-bold", if (it) "1" else "0") },
                        modifier = Modifier.tvFocusBorder()
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("斜体", color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
                    Spacer(modifier = Modifier.width(8.dp))
                    Switch(
                        checked = subItalic,
                        onCheckedChange = { subItalic = it; mpv.setPropertyString("sub-italic", if (it) "1" else "0") },
                        modifier = Modifier.tvFocusBorder()
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(32.dp))
    }
}
// -----------------------------------------------------------------
// 字幕在线搜索面板
// 与 PC 端 subtitle_download_service.py 对齐：SubHD / SubtitleCat / OpenSubtitles 三源
// -----------------------------------------------------------------

@Composable
fun SubtitleSearchPanel(viewModel: AppViewModel) {
    val searching by viewModel.subtitleSearching.collectAsState()
    val results by viewModel.subtitleSearchResults.collectAsState()
    val error by viewModel.subtitleSearchError.collectAsState()
    val downloading by viewModel.subtitleDownloading.collectAsState()

    var query by remember { mutableStateOf("") }
    var selectedLang by remember { mutableStateOf("all") }

    val languages = listOf(
        "all" to "全部",
        "chi" to "中文",
        "eng" to "英语",
        "jpn" to "日语",
        "kor" to "韩语"
    )

    PanelScaffold(
        title = "字幕搜索",
        subtitle = "SubHD / SubtitleCat / OpenSubtitles",
        onClose = { viewModel.toggleSubtitleSearchPanel() },
        scrollable = false
    ) {
        // 搜索框
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = { Text("输入片名或关键词...", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp) },
            trailingIcon = {
                if (query.isNotEmpty()) {
                    IconButton(
                        onClick = { query = "" },
                        modifier = Modifier.tvFocusBorder()
                    ) {
                        Icon(Icons.Default.Close, contentDescription = "清空", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp)
                .tvTextField(),
            shape = RoundedCornerShape(8.dp),
            singleLine = true
        )

        // 语言选择
        SelectionGroup(
            title = "语言",
            options = languages,
            selectedKey = selectedLang,
            onSelect = { code -> selectedLang = code }
        )

        // 搜索按钮
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp),
            contentAlignment = Alignment.Center
        ) {
            if (searching) {
                CircularProgressIndicator(
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp)
                )
            } else {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(MaterialTheme.colorScheme.primary)
                        // tvFocusBorder 在 clickable 之前（外层）才能收到焦点事件
                        .tvFocusBorder()
                        .clickable { viewModel.searchSubtitles(query, selectedLang) }
                        .padding(vertical = 10.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Default.Search, contentDescription = null, tint = MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("搜索", color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                }
            }
        }

        // 错误提示
        if (error.isNotEmpty() && results.isEmpty() && !searching) {
            Text(
                text = error,
                color = tvPalette.dangerSoft,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
            )
        }

        // 搜索结果
        if (results.isNotEmpty()) {
            LazyColumn(
                modifier = Modifier.fillMaxWidth(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 4.dp)
            ) {
                items(items = results, key = { it.source + "_" + it.id + "_" + it.fileName }) { item ->
                    SubtitleResultRow(
                        item = item,
                        downloading = downloading,
                        onDownload = { viewModel.downloadAndLoadSubtitle(item) },
                        onOpenInBrowser = { url ->
                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                            intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
                            try {
                                viewModel.getApplication<android.app.Application>().startActivity(intent)
                            } catch (e: Exception) {
                                viewModel.showOsd("字幕搜索", "无法打开浏览器")
                            }
                        }
                    )
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                }
            }
        } else if (!searching && query.isNotEmpty() && error.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Text("点击搜索按钮开始查找", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            }
        }
    }
}
@Composable
private fun SubtitleResultRow(
    item: SubtitleItem,
    downloading: Boolean,
    onDownload: () -> Unit,
    onOpenInBrowser: (String) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            // 第一行：文件名
            Text(
                text = item.fileName.ifBlank { item.title },
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 13.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            // 第二行：来源 + 语言 + 评分
            Row(
                modifier = Modifier.padding(top = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                SourceBadge(item.source)
                if (item.language.isNotEmpty()) {
                    Text(item.language, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                if (item.score > 0) {
                    Text("★ ${item.score}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
            }
        }

        Spacer(modifier = Modifier.width(8.dp))

        // 操作按钮
        if (downloading) {
            CircularProgressIndicator(
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp)
            )
        } else if (item.autoDownload) {
            // 可自动下载（OpenSubtitles / SubtitleCat）
            TextButton(
                onClick = onDownload,
                modifier = Modifier.tvFocusBorder()
            ) {
                Text("下载", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
            }
        } else {
            // 需浏览器打开（SubHD）
            TextButton(
                onClick = { onOpenInBrowser(item.detailUrl.ifBlank { item.downloadLink }) },
                modifier = Modifier.tvFocusBorder()
            ) {
                Text("浏览器", color = MaterialTheme.colorScheme.tertiary, fontSize = 12.sp)
            }
        }
    }
}
