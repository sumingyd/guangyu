package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.imageLoader
import androidx.compose.ui.platform.LocalContext
import com.iptv.scanner.editor.pro.data.IptvRepository
import com.iptv.scanner.editor.pro.data.LogoSourceOption
import kotlinx.coroutines.launch

/**
 * 台标来源设置面板（安卓端）。
 *
 * 与 PC 共用 services.logo_resolver 和同一份 config.ini：
 * - 只勾选一个来源 = 固定使用该来源；
 * - 勾选多个来源 = 按列表顺序逐级兜底。
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
                status = "读取台标设置失败：${it.message}"
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
        subtitle = "本地 / M3U / EPG / 规则",
        onClose = onClose,
    ) {
        DescText(
            "只勾选一个来源＝固定只用它，不再往下找。勾选多个＝按下面顺序逐级兜底，" +
                "前一级取不到台标时才用下一级；用 ↑/↓ 调整顺序。"
        )
        DescText("本地来源会到配置目录的 logos / img 目录下找与频道同名的图片。")

        if (loading) {
            Text("正在读取…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            return@PanelScaffold
        }

        SettingsGroup("已启用（顺序即兜底优先级）") {
            if (order.isEmpty()) {
                DescText("当前没有启用任何来源，请至少勾选一个。")
            }
            order.forEachIndexed { index, key ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(
                        checked = true,
                        onCheckedChange = { order = order.filterNot { it == key } },
                    )
                    Text(
                        text = "${index + 1}. ${labelOf(key)}",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.padding(start = 6.dp),
                    )
                    Spacer(Modifier.weight(1f))
                    IconButton(
                        onClick = { move(index, -1) },
                        enabled = index > 0,
                        modifier = Modifier.size(36.dp),
                    ) {
                        Icon(Icons.Default.KeyboardArrowUp, contentDescription = "上移")
                    }
                    IconButton(
                        onClick = { move(index, 1) },
                        enabled = index < order.lastIndex,
                        modifier = Modifier.size(36.dp),
                    ) {
                        Icon(Icons.Default.KeyboardArrowDown, contentDescription = "下移")
                    }
                }
            }

            val disabled = allSources.filter { it.key !in order }
            if (disabled.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                DescText("未启用（勾选后加到顺序末尾）")
                disabled.forEach { source ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(
                            checked = false,
                            onCheckedChange = { order = order + source.key },
                        )
                        Text(
                            text = source.label,
                            fontSize = 14.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(start = 6.dp),
                        )
                    }
                }
            }
        }

        SettingsGroup("规则模板地址") {
            OutlinedTextField(
                value = template,
                onValueChange = { template = it },
                singleLine = true,
                label = { Text("规则地址") },
                placeholder = { Text("https://example.com/[name].png") },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(6.dp))
            DescText(
                "[name] 会替换成频道名。地址返回 404、空内容或解码失败时，" +
                    "会自动记录失败并切到下一级；清空台标缓存可重新尝试。"
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(
                enabled = !saving,
                onClick = {
                    if (order.isEmpty()) {
                        status = "请至少选择一个台标来源"
                        return@TextButton
                    }
                    if (saving) return@TextButton
                    saving = true
                    scope.launch {
                        val result = repo.setLogoSettings(order, template.trim())
                        result.fold(
                            onSuccess = { saved ->
                                order = saved.order
                                template = saved.ruleTemplate
                                status = "已保存，正在按新顺序刷新台标"
                                viewModel.loadChannels()
                            },
                            onFailure = { status = "保存失败：${it.message}" },
                        )
                        saving = false
                    }
                },
            ) {
                Text(if (saving) "保存中…" else "保存")
            }

            OutlinedButton(
                enabled = !saving,
                onClick = {
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
                },
            ) {
                Text("清空台标缓存")
            }
        }

        if (status.isNotEmpty()) {
            Text(
                text = status,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}
