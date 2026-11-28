package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.imageLoader
import com.iptv.scanner.editor.pro.data.IptvRepository
import com.iptv.scanner.editor.pro.data.LogoSourceOption
import kotlinx.coroutines.launch

/**
 * 台标来源设置面板（安卓端）。
 *
 * 与 PC 共用 services.logo_resolver 和同一份 config.ini：
 * - 只勾选一个来源 = 固定使用该来源；
 * - 勾选多个来源 = 按列表顺序逐级兜底。
 *
 * 行高与间距做了压缩，保证默认打开时四个来源、模板输入和按钮一屏可见。
 */
@Composable
internal fun LogoSourcePanel(
    viewModel: AppViewModel,
    onClose: () -> Unit,
) {
    val repo = remember { IptvRepository.getInstance() }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    var allSources by remember { mutableStateOf<List<LogoSourceOption>>(emptyList()) }
    var order by remember { mutableStateOf<List<String>>(emptyList()) }
    var template by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(true) }
    var saving by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        repo.getLogoSettings().fold(
            onSuccess = { settings ->
                allSources = settings.sources
                order = settings.order
                template = settings.ruleTemplate
                loading = false
            },
            onFailure = {
                status = "读取失败：${it.message}"
                loading = false
            },
        )
    }

    fun labelOf(key: String): String =
        allSources.firstOrNull { it.key == key }?.label ?: key

    fun move(index: Int, delta: Int) {
        val target = index + delta
        if (target < 0 || target >= order.size) return
        val list = order.toMutableList()
        val item = list.removeAt(index)
        list.add(target, item)
        order = list
    }

    PanelScaffold(
        title = "台标来源",
        onClose = onClose,
    ) {
        Text(
            text = "只勾一个＝固定用该来源；勾多个＝按顺序逐级兜底。↑/↓ 调顺序，本地读 logos/img 同名图片。",
            fontSize = 11.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 4.dp),
        )

        if (loading) {
            Text("正在读取…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            return@PanelScaffold
        }

        // 来源行与规则模板合并进同一张卡片：少一个分组标题和一段间距，
        // 矮屏手机（640dp 高）默认打开时也能一屏放下四行 + 输入框 + 按钮。
        SettingsGroup("来源与规则") {
            val disabled = allSources.filter { it.key !in order }
            order.forEachIndexed { index, key ->
                SourceRow(
                    checked = true,
                    label = "${index + 1}. ${labelOf(key)}",
                    canUp = index > 0,
                    canDown = index < order.lastIndex,
                    onToggle = { order = order.filterNot { it == key } },
                    onUp = { move(index, -1) },
                    onDown = { move(index, 1) },
                )
            }
            disabled.forEach { source ->
                SourceRow(
                    checked = false,
                    label = source.label,
                    canUp = false,
                    canDown = false,
                    onToggle = { order = order + source.key },
                    onUp = {},
                    onDown = {},
                )
            }
            AptvRowDivider()
            Text(
                text = "规则模板 · 404/空内容自动切下一级",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 4.dp, start = 2.dp),
            )
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp)
                    .height(32.dp)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f),
                        RoundedCornerShape(8.dp),
                    )
                    .padding(horizontal = 10.dp),
                contentAlignment = Alignment.CenterStart,
            ) {
                if (template.isEmpty()) {
                    Text(
                        text = "https://example.com/[name].png",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                BasicTextField(
                    value = template,
                    onValueChange = { template = it },
                    singleLine = true,
                    textStyle = TextStyle(
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 13.sp,
                    ),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CompactButton(
                    text = if (saving) "保存中…" else "保存",
                    enabled = !saving,
                ) {
                    if (order.isEmpty()) {
                        status = "请至少选择一个来源"
                        return@CompactButton
                    }
                    saving = true
                    scope.launch {
                        repo.setLogoSettings(order, template.trim()).fold(
                            onSuccess = { saved ->
                                order = saved.order
                                template = saved.ruleTemplate
                                status = "已保存，正在刷新台标"
                                viewModel.loadChannels()
                            },
                            onFailure = { status = "保存失败：${it.message}" },
                        )
                        saving = false
                    }
                }
                CompactButton(text = "清空缓存", enabled = !saving) {
                    scope.launch {
                        status = "正在清空台标缓存…"
                        repo.clearCache("logo").fold(
                            onSuccess = {
                                context.imageLoader.memoryCache?.clear()
                                viewModel.loadChannels()
                                status = "台标缓存已清空"
                            },
                            onFailure = { status = "清空失败：${it.message}" },
                        )
                    }
                }
            }
        }

        if (status.isNotEmpty()) {
            Text(
                text = status,
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

@Composable
private fun SourceRow(
    checked: Boolean,
    label: String,
    canUp: Boolean,
    canDown: Boolean,
    onToggle: () -> Unit,
    onUp: () -> Unit,
    onDown: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().height(30.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier.size(30.dp).clickable { onToggle() },
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (checked) Icons.Default.CheckCircle else Icons.Default.RadioButtonUnchecked,
                contentDescription = if (checked) "已启用" else "未启用",
                modifier = Modifier.size(17.dp),
                tint = if (checked) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            text = label,
            fontSize = 13.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(start = 4.dp),
        )
        if (checked) {
            ReorderButton(Icons.Default.KeyboardArrowUp, canUp, onUp, "上移")
            ReorderButton(Icons.Default.KeyboardArrowDown, canDown, onDown, "下移")
        } else {
            Spacer(Modifier.width(52.dp))
        }
    }
}

@Composable
private fun ReorderButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    enabled: Boolean,
    onClick: () -> Unit,
    description: String,
) {
    Box(
        modifier = Modifier
            .size(26.dp)
            .then(if (enabled) Modifier.clickable { onClick() } else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = description,
            modifier = Modifier.size(18.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(
                alpha = if (enabled) 1f else 0.3f,
            ),
        )
    }
}

@Composable
private fun CompactButton(
    text: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    TextButton(
        onClick = onClick,
        enabled = enabled,
        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
        modifier = Modifier.height(30.dp),
    ) {
        Text(text, fontSize = 13.sp)
    }
}
