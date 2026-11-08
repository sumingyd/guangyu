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
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalView
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
/**
 * 更多功能面板集合：与 PC 端 controllers 对齐，直接调 MpvController。
 *
 * 包含：
 * - [OpenUrlDialog]：打开网络流 URL 输入对话框
 * - [VideoSettingsPanel]：视频设置（图像调整/旋转/翻转）
 * - [AudioSettingsPanel]：音频设置（音轨/延迟/EQ 预设）
 * - [SubtitleSettingsPanel]：字幕设置（轨/样式/延迟/位置/加载）
 * - [PlaybackPanel]：播放设置（循环/AB/逐帧/速度）
 * - [ScreenshotPanel]：截图（模式选择）
 * - [ViewSettingsPanel]：视图设置（视频比例）
 * - [AboutPanel]：关于
 *
 * 所有面板都是全屏覆盖式 Surface，与 [PlayerSettingsPanel] 风格一致。
 */

// -----------------------------------------------------------------
// 通用组件
// -----------------------------------------------------------------

/**
 * 设置面板脚手架：标题栏 + 可滚动内容区域。
 * 与 PlayerSettingsPanel 风格统一，避免每个面板重复写标题栏代码。
 * 横屏模式下自动限制内容宽度（65%），居中显示，避免设置项过宽。
 */
@Composable
internal fun PanelScaffold(
title: String,
subtitle: String = "",
onClose: () -> Unit,
actions: @Composable (() -> Unit) = {},
scrollable: Boolean = true,
content: @Composable () -> Unit
) {
val oc = rememberPlayerOverlayColors()
val aptvStyle = LocalAptvStyle.current
    // 面板打开时主动抢焦点，避免焦点回落到下层统一面板的菜单项导致无法操作子面板。
    // focusGroup() 让 DPAD 导航限制在面板内部，不外溢到下层。
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        runCatching { closeFocusRequester.requestFocus() }
    }
    // 面板关闭后焦点会随面板节点一起从焦点树移除，遥控器焦点框直接消失。
    // TV 内联弹窗与主界面同处一棵 Compose 焦点树，系统不会自动把焦点还给下层，
    // 因此等本帧节点真正摘除后，把焦点交还给下层第一个可聚焦元素。
    val focusManager = LocalFocusManager.current
    val rootView = LocalView.current
    DisposableEffect(Unit) {
        onDispose {
            rootView.post {
                val moved = runCatching {
                    focusManager.moveFocus(FocusDirection.Next)
                }.getOrDefault(false)
                if (!moved) {
                    runCatching { focusManager.moveFocus(FocusDirection.Down) }
                }
            }
        }
    }
    Surface(
        color = Color.Transparent,
        modifier = Modifier.fillMaxSize()
    ) {
            Column(
                modifier = Modifier.fillMaxSize()
                    .focusGroup()
                    .systemBarsPadding()
                    .padding(16.dp)
            ) {
            if (aptvStyle) {
                // 竖屏 APTV 样式标题栏：大标题 + 红色副标题 + 关闭图标
                AptvPanelHeader(
                    title = title,
                    subtitle = subtitle,
                    onClose = onClose,
                    modifier = Modifier.focusRequester(closeFocusRequester)
                ) { actions() }
            } else {
            // 标题栏
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.headlineSmall,
                        color = oc.textPrimary,
                        maxLines = 1
                    )
                    if (subtitle.isNotEmpty()) {
                        Text(
                            text = subtitle,
                            color = oc.textSecondary,
                            fontSize = 12.sp
                        )
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    actions()
                    IconButton(
                        onClick = onClose,
                        modifier = Modifier.tvFocusBorder().focusRequester(closeFocusRequester)
                    ) {
                        Icon(Icons.Default.Close, contentDescription = "关闭", tint = oc.iconTint)
                    }
                }
            }
            }
            Spacer(modifier = Modifier.height(16.dp))
            // 内容区域：scrollable=true 时用 verticalScroll（适用于普通 Column 内容），
            // scrollable=false 时不加 verticalScroll（适用于内含 LazyColumn 的面板，避免无限高度约束崩溃）
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .then(if (scrollable) Modifier.verticalScroll(rememberScrollState()) else Modifier)
            ) {
                content()
            }

        }
    }
}
@Composable
internal fun SectionLabel(text: String) {
    val aptvStyle = LocalAptvStyle.current
    Text(
        text = text,
        color = if (aptvStyle) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary,
        fontSize = if (aptvStyle) 13.sp else 14.sp,
        fontWeight = if (aptvStyle) FontWeight.Normal else FontWeight.SemiBold,
        modifier = Modifier.padding(top = 12.dp, bottom = 4.dp)
    )
}
@Composable
internal fun DescText(text: String) {
    Text(
        text = text,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 12.sp,
        modifier = Modifier.padding(bottom = 8.dp)
    )
}

/**
 * 设置分组容器：APTV 模式下用 AptvSectionHeader + AptvGroupCard（圆角卡片）包裹，
 * 非 APTV 模式下用 SectionLabel + 扁平内容，保持横屏/TV 原样不变。
 */
@Composable
internal fun SettingsGroup(
    title: String,
    content: @Composable ColumnScope.() -> Unit
) {
    if (LocalAptvStyle.current) {
        AptvSectionHeader(title)
        AptvGroupCard {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                content = content
            )
        }
    } else {
        SectionLabel(title)
        Column(content = content)
    }
}

/**
 * APTV 模式下在卡片内行与行之间加细分隔线；非 APTV 模式不渲染。
 */
@Composable
internal fun AptvRowDivider() {
    if (LocalAptvStyle.current) {
        HorizontalDivider(
            modifier = Modifier.padding(horizontal = 0.dp),
            thickness = 0.5.dp,
            color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.4f)
        )
    }
}
/**
 * 带标签和重置按钮的滑块。
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
internal fun LabeledSlider(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    valueText: String,
    onValueChange: (Float) -> Unit,
    onReset: () -> Unit
) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(text = label, color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = valueText,
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 13.sp,
                    modifier = Modifier.width(60.dp),
                    fontWeight = FontWeight.Medium
                )
                TextButton(onClick = onReset, modifier = Modifier.padding(start = 0.dp).tvFocusBorder()) {
                    Text("重置", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        val oc = rememberPlayerOverlayColors()
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = range,
            modifier = Modifier.fillMaxWidth().tvFocusBorder(),
            thumb = {
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(oc.accent, androidx.compose.foundation.shape.CircleShape)
                        .then(Modifier.border(2.dp, oc.accent.copy(alpha = 0.3f), androidx.compose.foundation.shape.CircleShape))
                )
            },
            colors = SliderDefaults.colors(
                thumbColor = oc.accent,
                activeTrackColor = oc.accent,
                inactiveTrackColor = oc.trackInactive,
                disabledThumbColor = oc.accent.copy(alpha = 0.5f),
                disabledActiveTrackColor = oc.accent.copy(alpha = 0.5f),
                disabledInactiveTrackColor = oc.trackInactive
            )
        )
    }
}
// -----------------------------------------------------------------

/** 解析 mpv track-list JSON，提取指定类型的轨道 */
internal fun parseTracks(trackListJson: String, type: String): List<Pair<Int, String>> {
    if (trackListJson.isBlank()) return emptyList()
    return try {
        val arr = JSONArray(trackListJson)
        (0 until arr.length()).mapNotNull { i ->
            val obj = arr.getJSONObject(i)
            if (obj.optString("type") == type) {
                val id = obj.optInt("id")
                val title = obj.optString("title").ifEmpty { obj.optString("lang").ifEmpty { "轨道 $id" } }
                id to title
            } else null
        }
    } catch (e: Exception) {
        emptyList()
    }
}
@Composable
internal fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(text = label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Text(text = value, color = MaterialTheme.colorScheme.onSurface, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}
/**
 * A/V 同步波形图：自绘 Canvas，中线为 avdiff=0，
 * 颜色随偏差变化（绿/黄/红），自适应范围。
 * 与 PC 端 AVSyncWaveWidget.paintEvent 对齐。
 */
@Composable
internal fun AvSyncWaveform(
    history: List<Float>,
    modifier: Modifier = Modifier
) {
    val accentColor = MaterialTheme.colorScheme.primary
    val outlineColor = MaterialTheme.colorScheme.outline
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = modifier
    ) {
        Canvas(modifier = Modifier.fillMaxSize().padding(4.dp)) {
            val w = size.width
            val h = size.height
            val midY = h / 2f
            // 中线
            drawLine(
                color = outlineColor,
                start = Offset(0f, midY),
                end = Offset(w, midY),
                strokeWidth = 1f
            )
            if (history.size < 2) return@Canvas
            // 自适应范围：取历史数据最大绝对值的 1.5 倍，最小 0.1
            val maxAbs = history.maxOfOrNull { kotlin.math.abs(it) } ?: 0.1f
            val range = (maxAbs * 1.5f).coerceAtLeast(0.1f)
            val stepX = w / (history.size - 1).coerceAtLeast(1)
            // 绘制波形
            val path = Path()
            history.forEachIndexed { i, value ->
                val x = i * stepX
                val y = midY - (value / range).coerceIn(-1f, 1f) * (h / 2f)
                if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            drawPath(
                path = path,
                color = accentColor,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2f)
            )
            // 最新的点
            val lastVal = history.last()
            val lastColor = when {
                kotlin.math.abs(lastVal) < 0.04f -> tvPalette.success
                kotlin.math.abs(lastVal) < 0.2f -> tvPalette.warning
                else -> tvPalette.danger
            }
            drawCircle(
                color = lastColor,
                radius = 4f,
                center = Offset((history.size - 1) * stepX, midY - (lastVal / range).coerceIn(-1f, 1f) * (h / 2f))
            )
        }
    }
}
@Composable
internal fun SourceBadge(source: String) {
    val color = when (source) {
        "OpenSubtitles" -> tvPalette.success
        "SubHD" -> MaterialTheme.colorScheme.surfaceVariant
        "SubtitleCat" -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(
        color = color.copy(alpha = 0.2f),
        shape = RoundedCornerShape(3.dp)
    ) {
        Text(
            text = source,
            color = color,
            fontSize = 10.sp,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
        )
    }
}
/** 格式化秒为 mm:ss 或 h:mm:ss */
internal fun formatTime(seconds: Double): String {
    if (seconds <= 0) return "00:00"
    val totalSec = seconds.toLong()
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return if (h > 0) String.format("%d:%02d:%02d", h, m, s) else String.format("%02d:%02d", m, s)
}
