package com.iptv.scanner.editor.pro.ui

import android.content.res.Configuration
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.QrCode
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.SettingsBackupRestore
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Phonelink
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.focusable
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.data.IptvEpgSource
import com.iptv.scanner.editor.pro.data.IptvSource
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField

/**
 * 订阅源管理面板（全屏覆盖）。
 *
 * 与 PC 端 订阅源管理 对齐：
 * - 频道订阅源 Tab：URL + 名称 + 启用开关 + 删除 + 添加 + 重载
 * - EPG 订阅源 Tab：URL + 名称 + 删除 + 添加 + 重载
 * - 重载后自动轮询加载状态，完成后刷新频道列表
 */
@Composable
fun SourceManagerPanel(viewModel: AppViewModel, focusUrlInput: Boolean = false) {
    if (LocalAptvStyle.current) {
        SourceManagerPanelAptv(viewModel)
        return
    }
    val sourceTab by viewModel.sourceTab.collectAsState()
    val sources by viewModel.sources.collectAsState()
    val epgSources by viewModel.epgSources.collectAsState()
    val sourceLoading by viewModel.sourceLoading.collectAsState()
    val sourceMessage by viewModel.sourceMessage.collectAsState()
    val adminUrl by viewModel.adminServerUrl.collectAsState()
    val adminToken by viewModel.adminServerToken.collectAsState()
    val adminRunning by viewModel.adminServerRunning.collectAsState()
    val adminCountdown by viewModel.adminCountdown.collectAsState()
    var showQrCode by remember { mutableStateOf(false) }

    // server 启动时自动展开二维码（TV 端遥控器操作繁琐，省去额外点击）
    LaunchedEffect(adminRunning) {
        if (adminRunning) showQrCode = true
    }

    // 面板打开时主动抢焦点，避免焦点回落到下层统一面板的菜单项。
    // 默认落到右上关闭按钮；focusUrlInput=true（零频道播放页直达）时落到 URL 输入框
    val closeFocusRequester = remember { FocusRequester() }
    val urlFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        runCatching {
            if (focusUrlInput) urlFocusRequester.requestFocus() else closeFocusRequester.requestFocus()
        }
    }

    Surface(
        color = Color.Transparent,
        modifier = Modifier.fillMaxSize()
    ) {
        Column(
            modifier = Modifier.fillMaxSize().focusGroup().verticalScroll(rememberScrollState()).systemBarsPadding().imePadding().padding(16.dp)
        ) {
            // 标题栏
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "订阅源管理",
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    // 局域网管理按钮（用 Phonelink 图标：表示 TV 与手机连接管理，
                    // 避免与系统栏 Wifi 图标冲突，且暗示启动后会出现二维码供手机扫码）
                    IconButton(onClick = { viewModel.toggleAdminServer() }, modifier = Modifier.tvFocusBorder()) {
                        Icon(
                            Icons.Default.Phonelink,
                            contentDescription = "局域网管理",
                            tint = if (adminRunning) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                        )
                    }
                    // 二维码按钮（仅在服务器运行时显示）
                    if (adminRunning) {
                        IconButton(onClick = { showQrCode = !showQrCode }, modifier = Modifier.tvFocusBorder()) {
                            Icon(
                                Icons.Default.QrCode,
                                contentDescription = "二维码",
                                tint = if (showQrCode) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                            )
                        }
                    }
                    // 重载按钮
                    if (sourceLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = MaterialTheme.colorScheme.primary,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                    } else {
                        IconButton(onClick = {
                            if (sourceTab == SourceTab.PLAYLIST) {
                                viewModel.reloadSources()
                            } else {
                                viewModel.reloadEpgSources()
                            }
                        }, modifier = Modifier.tvFocusBorder()) {
                            Icon(Icons.Default.Refresh, contentDescription = "重载", tint = MaterialTheme.colorScheme.onSurface)
                        }
                    }
                    // 关闭按钮
                    IconButton(onClick = { viewModel.toggleSourceManager() }, modifier = Modifier.tvFocusBorder().focusRequester(closeFocusRequester)) {
                        Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
                    }
                }
            }

            // 订阅源刷新失败但已使用缓存频道：提示用户数据未丢失
            val iptvStatusWarn by viewModel.iptvStatus.collectAsState()
            val sourceWarningMsg = iptvStatusWarn?.sourceWarning.orEmpty()
            if (!sourceLoading && sourceWarningMsg.isNotBlank()) {
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    color = tvPalette.warning.copy(alpha = 0.16f),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.Warning,
                            contentDescription = null,
                            tint = tvPalette.warning,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = sourceWarningMsg,
                            // 固定 #FFDCA8 在浅色底上对比度约 1.2:1，几乎不可读；改用主题正文色
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 13.sp
                        )
                    }
                }
            }

            // 局域网管理提示
            if (adminRunning && adminUrl.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                LanAdminInfoBar(
                    url = adminUrl,
                    token = adminToken,
                    showQrCode = showQrCode,
                    onToggleQr = { showQrCode = it },
                    countdown = adminCountdown
                )
                // 自动关闭开关
                AdminAutoStopToggle(viewModel = viewModel)
            } else if (!adminRunning) {
                Spacer(modifier = Modifier.height(8.dp))
                // 启动提示卡片：可被遥控器焦点选中（tvFocusBorder + focusable）
                // 半透明白替代 surfaceVariant 实底：叠加在暗玻璃弹窗上不突兀
                Surface(
                    color = tvPalette.borderSubtle,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .tvFocusBorder()
                        .focusable()
                        .clickable { viewModel.toggleAdminServer() }
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Phonelink, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                        Spacer(modifier = Modifier.width(8.dp))
                        Column {
                            Text(
                                text = "启动局域网管理",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurface
                            )
                            Text(
                                text = "TV 端用遥控器输入不便，点击启动后用手机浏览器扫码管理",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.secondary
                            )
                        }
                    }
                }
                // 自定义访问令牌输入（启动前设置）
                LanAdminTokenInput(viewModel = viewModel)
                // 自动关闭开关（启动前也可设置）
                AdminAutoStopToggle(viewModel = viewModel)
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 备份与恢复（解决卸载重装/签名切换导致的数据丢失问题）
            BackupRestoreBar(viewModel)

            Spacer(modifier = Modifier.height(12.dp))

            // Tab 切换
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = sourceTab == SourceTab.PLAYLIST,
                    onClick = { viewModel.setSourceTab(SourceTab.PLAYLIST) },
                    label = { Text("频道源 (${sources.size})") }
                )
                FilterChip(
                    selected = sourceTab == SourceTab.EPG,
                    onClick = { viewModel.setSourceTab(SourceTab.EPG) },
                    label = { Text("EPG 源 (${epgSources.size})") }
                )
            }

            // 加载消息
            if (sourceMessage.isNotEmpty()) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = sourceMessage,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 添加订阅源输入框
            when (sourceTab) {
                SourceTab.PLAYLIST -> {
                    AddSourceRow(
                        placeholder = "输入 M3U 订阅源 URL",
                        onAdd = { url, name -> viewModel.addSource(url, name) },
                        urlFocusRequester = urlFocusRequester
                    )
                }
                SourceTab.EPG -> {
                    AddSourceRow(
                        placeholder = "输入 EPG 订阅源 URL（XMLTV）",
                        onAdd = { url, name -> viewModel.addEpgSource(url, name) },
                        urlFocusRequester = urlFocusRequester
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 列表（使用 Column 而非 LazyColumn，因为外层已用 verticalScroll）
            when (sourceTab) {
                SourceTab.PLAYLIST -> {
                    if (sources.isEmpty()) {
                        EmptyHint("暂无频道订阅源，点击上方输入框添加")
                    } else {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            sources.forEachIndexed { idx, source ->
                                SourceItem(
                                    source = source,
                                    index = idx,
                                    onToggle = { enabled -> viewModel.toggleSourceEnabled(idx, enabled) },
                                    onDelete = { viewModel.deleteSource(idx) },
                                    onEdit = { url, name -> viewModel.updateSource(idx, url, name) }
                                )
                            }
                        }
                    }
                }
                SourceTab.EPG -> {
                    if (epgSources.isEmpty()) {
                        EmptyHint("暂无 EPG 订阅源，点击上方输入框添加")
                    } else {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            epgSources.forEachIndexed { idx, source ->
                                EpgSourceItem(
                                    source = source,
                                    index = idx,
                                    onDelete = { viewModel.deleteEpgSource(idx) },
                                    onEdit = { url, name -> viewModel.updateEpgSource(idx, url, name) }
                                )
                            }
                        }
                    }
                }
            }

        }
    }
}

/**
 * 添加订阅源输入行
 */
@Composable
private fun AddSourceRow(
    placeholder: String,
    onAdd: (url: String, name: String) -> Unit,
    urlFocusRequester: FocusRequester? = null
) {
    var url by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            placeholder = { Text(placeholder, color = MaterialTheme.colorScheme.onSurfaceVariant) },
            modifier = Modifier.fillMaxWidth().tvTextField().then(
                if (urlFocusRequester != null) Modifier.focusRequester(urlFocusRequester) else Modifier
            ),
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            shape = RoundedCornerShape(8.dp)
        )
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            placeholder = { Text("名称（可选）", color = MaterialTheme.colorScheme.onSurfaceVariant) },
            modifier = Modifier.fillMaxWidth().tvTextField(),
            singleLine = true,
            shape = RoundedCornerShape(8.dp)
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End
        ) {
            OutlinedButton(
                onClick = {
                    if (url.isNotBlank()) {
                        onAdd(url.trim(), name.trim())
                        url = ""
                        name = ""
                    }
                },
                modifier = Modifier.tvFocusBorder()
            ) {
                Icon(Icons.Default.Add, contentDescription = "添加", tint = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.width(4.dp))
                Text("添加", color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

/**
 * 频道订阅源列表项
 */
@Composable
private fun SourceItem(
    source: IptvSource,
    index: Int,
    onToggle: (Boolean) -> Unit,
    onDelete: () -> Unit,
    onEdit: (url: String, name: String) -> Unit
) {
    var editing by remember { mutableStateOf(false) }
    var editUrl by remember { mutableStateOf(source.url) }
    var editName by remember { mutableStateOf(source.name) }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = source.name.ifEmpty { "订阅源 ${index + 1}" },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = source.url,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (source.lastUpdate != null && source.lastUpdate!!.isNotEmpty()) {
                        Text(
                            text = "更新: ${source.lastUpdate}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                Switch(checked = source.enabled, onCheckedChange = onToggle, modifier = Modifier.tvFocusBorder())
                Spacer(modifier = Modifier.width(4.dp))
                IconButton(onClick = { editing = !editing; editUrl = source.url; editName = source.name }, modifier = Modifier.tvFocusBorder()) {
                    Icon(Icons.Default.Edit, contentDescription = "编辑", tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(onClick = onDelete, modifier = Modifier.tvFocusBorder()) {
                    Icon(Icons.Default.Delete, contentDescription = "删除", tint = tvPalette.dangerSoft)
                }
            }
            if (editing) {
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = editUrl, onValueChange = { editUrl = it },
                    label = { Text("URL") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().tvTextField()
                )
                Spacer(modifier = Modifier.height(4.dp))
                OutlinedTextField(
                    value = editName, onValueChange = { editName = it },
                    label = { Text("名称") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().tvTextField()
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onEdit(editUrl.trim(), editName.trim()); editing = false }) { Text("保存") }
                    TextButton(onClick = { editing = false }) { Text("取消") }
                }
            }
        }
    }
}

/**
 * EPG 订阅源列表项
 */
@Composable
private fun EpgSourceItem(
    source: IptvEpgSource,
    index: Int,
    onDelete: () -> Unit,
    onEdit: (url: String, name: String) -> Unit
) {
    var editing by remember { mutableStateOf(false) }
    var editUrl by remember { mutableStateOf(source.url) }
    var editName by remember { mutableStateOf(source.name) }
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = source.name.ifEmpty { "EPG 源 ${index + 1}" },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = source.url,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (source.lastUpdate != null && source.lastUpdate!!.isNotEmpty()) {
                        Text(
                            text = "更新: ${source.lastUpdate}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                IconButton(onClick = { editing = !editing; editUrl = source.url; editName = source.name }, modifier = Modifier.tvFocusBorder()) {
                    Icon(Icons.Default.Edit, contentDescription = "编辑", tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(onClick = onDelete, modifier = Modifier.tvFocusBorder()) {
                    Icon(Icons.Default.Delete, contentDescription = "删除", tint = tvPalette.dangerSoft)
                }
            }
            if (editing) {
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = editUrl, onValueChange = { editUrl = it },
                    label = { Text("URL") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().tvTextField()
                )
                Spacer(modifier = Modifier.height(4.dp))
                OutlinedTextField(
                    value = editName, onValueChange = { editName = it },
                    label = { Text("名称") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().tvTextField()
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { onEdit(editUrl.trim(), editName.trim()); editing = false }) { Text("保存") }
                    TextButton(onClick = { editing = false }) { Text("取消") }
                }
            }
        }
    }
}

@Composable
private fun EmptyHint(text: String) {
    Box(
        modifier = Modifier.fillMaxWidth().padding(32.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/**
 * 局域网管理自动关闭开关
 * 开启后 5 分钟自动停止服务器，关闭后持续运行直到手动停止
 */
@Composable
private fun AdminAutoStopToggle(viewModel: AppViewModel) {
    val adminRunning by viewModel.adminServerRunning.collectAsState()
    var autoStop by remember { mutableStateOf(viewModel.getAdminAutoStop()) }
    LaunchedEffect(adminRunning) {
        autoStop = viewModel.getAdminAutoStop()
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = Icons.Default.Timer,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(18.dp)
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = "5 分钟自动关闭",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f)
        )
        Switch(
            checked = autoStop,
            onCheckedChange = {
                autoStop = it
                viewModel.setAdminAutoStop(it)
            },
            modifier = Modifier.tvFocusBorder()
        )
    }
}

/**
 * 局域网管理信息栏（含二维码展开和自动停止倒计时）
 */
@Composable
private fun LanAdminInfoBar(
    url: String,
    token: String,
    showQrCode: Boolean,
    onToggleQr: (Boolean) -> Unit,
    countdown: Int = 0
) {
    Column {
        // 半透明白替代 surfaceVariant 实底：叠加在暗玻璃弹窗上不突兀
        Surface(
            color = tvPalette.borderSubtle,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.Phonelink, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Spacer(modifier = Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "局域网管理已启动",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = "$url/admin/" + (if (token.isNotEmpty()) "?token=****" else ""),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                // 倒计时显示（mm:ss 格式）
                if (countdown > 0) {
                    val mm = countdown / 60
                    val ss = countdown % 60
                    Text(
                        text = "%d:%02d".format(mm, ss),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.tertiary,
                        modifier = Modifier.padding(end = 4.dp)
                    )
                }
                IconButton(onClick = { onToggleQr(!showQrCode) }, modifier = Modifier.tvFocusBorder()) {
                    Icon(
                        Icons.Default.QrCode,
                        contentDescription = "二维码",
                        tint = if (showQrCode) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                    )
                }
            }
        }

        if (showQrCode) {
            Spacer(modifier = Modifier.height(12.dp))
            Surface(
                color = MaterialTheme.colorScheme.onSurface,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "扫码管理",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    // 生成二维码（包含 token，扫码后前端 JS 提取 token 用于 API 认证）
                    val qrUrl = "$url/admin/" + (if (token.isNotEmpty()) "?token=$token" else "")
                    val qrBitmap = remember(url, token) { QrCodeUtil.generate(qrUrl, 512) }
                    if (qrBitmap != null) {
                        Image(
                            bitmap = qrBitmap.asImageBitmap(),
                            contentDescription = "局域网管理二维码",
                            modifier = Modifier.size(240.dp)
                        )
                    } else {
                        Text(
                            text = "二维码生成失败",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "手机浏览器扫码或输入上方地址",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    // 显示访问令牌（PC 浏览器用户需手动输入）
                    if (token.isNotEmpty()) {
                        Spacer(modifier = Modifier.height(12.dp))
                        var tokenVisible by remember { mutableStateOf(false) }
                        Surface(
                            color = MaterialTheme.colorScheme.surfaceVariant,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth()
                                .clickable { tokenVisible = !tokenVisible }
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp),
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = "访问令牌",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = if (tokenVisible) token else "••••",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurface,
                                    fontWeight = FontWeight.Bold
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = if (tokenVisible) "点击隐藏令牌" else "点击显示令牌",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * 自定义访问令牌输入（仅在服务器未运行时显示）
 * 用户可设置一个好记的令牌，留空则启动时自动生成随机令牌
 */
@Composable
private fun LanAdminTokenInput(viewModel: AppViewModel) {
    val adminToken by viewModel.adminServerToken.collectAsState()
    var tokenInput by remember { mutableStateOf("") }
    var showInput by remember { mutableStateOf(false) }

    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "访问令牌",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f)
            )
            if (adminToken.isNotEmpty()) {
                Text(
                    text = if (showInput) "" else "••••",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Medium
                )
                Spacer(modifier = Modifier.width(8.dp))
            }
            OutlinedButton(
                onClick = { showInput = !showInput; if (!showInput) tokenInput = "" },
                modifier = Modifier.tvFocusBorder()
            ) {
                Text(if (showInput) "取消" else "自定义", fontSize = 12.sp)
            }
        }

        if (showInput) {
            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = tokenInput,
                    onValueChange = { tokenInput = it },
                    placeholder = { Text("留空自动生成", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) },
                    modifier = Modifier.weight(1f).tvTextField(),
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
                    shape = RoundedCornerShape(8.dp)
                )
                OutlinedButton(
                    onClick = {
                        viewModel.setAdminToken(tokenInput.trim())
                        showInput = false
                        tokenInput = ""
                    },
                    modifier = Modifier.tvFocusBorder()
                ) {
                    Text("保存", fontSize = 12.sp)
                }
            }
            Text(
                text = "留空则自动生成 4 位数字令牌，也可自定义",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp)
            )
        }
    }
}

/**
 * 备份与恢复操作栏
 *
 * 解决 debug→release 签名切换 / 卸载重装 导致的数据丢失问题：
 * - 导出：打包订阅源 + EPG 源 + 收藏/历史/队列 + 播放器设置，写入 Downloads/IPTV_backup_*.json
 * - 恢复：通过 SAF（Storage Access Framework）选择备份文件，恢复所有配置并触发 reload
 *
 * TV 端友好：用 OutlinedButton（可聚焦、方向键选中、OK 键触发）
 */
@Composable
private fun BackupRestoreBar(viewModel: AppViewModel) {
    // SAF 文件选择器：让用户选择 JSON 备份文件恢复
    val pickFileLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        // uri 可能为 null（用户取消选择）
        if (uri != null) {
            viewModel.importConfig(uri)
        }
    }

    // 半透明衬底替代 surfaceVariant 实底：跟随主题（深色白 8%，浅色黑 8%）
    Surface(
        color = tvPalette.borderSubtle,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // 标题行：图标 + 标题 + 说明
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Save, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                Spacer(modifier = Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "备份与恢复",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        text = "导出配置到下载目录，重装/换机后可恢复",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // 操作按钮行：导出 / 恢复
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = { viewModel.exportConfig() },
                    modifier = Modifier.weight(1f).tvFocusBorder()
                ) {
                    Icon(Icons.Default.Save, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("导出配置")
                }
                OutlinedButton(
                    onClick = { pickFileLauncher.launch(arrayOf("application/json")) },
                    modifier = Modifier.weight(1f).tvFocusBorder()
                ) {
                    Icon(
                        Icons.Default.SettingsBackupRestore,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("恢复配置")
                }
            }
        }
    }
}
/**
 * APTV（iOS 风格）订阅源管理面板：单列布局，圆角分组卡片 + iOS 选择行 + 开关行。
 * 仅在竖屏 APTV 模式下使用，横屏/TV 仍走 [SourceManagerPanel] 原有布局。
 */
@Composable
private fun SourceManagerPanelAptv(viewModel: AppViewModel) {
    val sourceTab by viewModel.sourceTab.collectAsState()
    val sources by viewModel.sources.collectAsState()
    val epgSources by viewModel.epgSources.collectAsState()
    val sourceLoading by viewModel.sourceLoading.collectAsState()
    val sourceMessage by viewModel.sourceMessage.collectAsState()
    val adminUrl by viewModel.adminServerUrl.collectAsState()
    val adminToken by viewModel.adminServerToken.collectAsState()
    val adminRunning by viewModel.adminServerRunning.collectAsState()
    val adminCountdown by viewModel.adminCountdown.collectAsState()
    var showQrCode by remember { mutableStateOf(false) }
    var autoStop by remember { mutableStateOf(viewModel.getAdminAutoStop()) }

    // server 启动时自动展开二维码；同时同步自动关闭开关状态
    LaunchedEffect(adminRunning) {
        if (adminRunning) showQrCode = true
        autoStop = viewModel.getAdminAutoStop()
    }

    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
        modifier = Modifier.fillMaxSize()
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .verticalScroll(rememberScrollState())
        ) {
            AptvPanelHeader(
                title = "订阅源管理",
                subtitle = "频道源 / EPG 源 / 局域网管理",
                onClose = { viewModel.toggleSourceManager() },
                actions = {
                    // 局域网管理按钮（启动后用 AptvAccent 高亮）
                    Icon(
                        Icons.Default.Phonelink,
                        contentDescription = "局域网管理",
                        tint = if (adminRunning) AptvAccent else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(24.dp).clickable { viewModel.toggleAdminServer() }
                    )
                    Spacer(modifier = Modifier.width(16.dp))
                    // 重载按钮（加载中显示进度圈）
                    if (sourceLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = AptvAccent,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "重载",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(24.dp).clickable {
                                if (sourceTab == SourceTab.PLAYLIST) viewModel.reloadSources()
                                else viewModel.reloadEpgSources()
                            }
                        )
                    }
                    Spacer(modifier = Modifier.width(16.dp))
                }
            )

            // 订阅源刷新失败但已使用缓存频道：提示用户数据未丢失
            val iptvStatusWarnAptv by viewModel.iptvStatus.collectAsState()
            if (!sourceLoading && iptvStatusWarnAptv?.sourceWarning.orEmpty().isNotBlank()) {
                Surface(
                    color = tvPalette.warning.copy(alpha = 0.16f),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            Icons.Default.Warning,
                            contentDescription = null,
                            tint = tvPalette.warning,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = iptvStatusWarnAptv?.sourceWarning.orEmpty(),
                            // 固定 #FFDCA8 在浅色底上不可读，改主题正文色
                            color = MaterialTheme.colorScheme.onSurface,
                            fontSize = 13.sp
                        )
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
            }

            // 源类型切换（FilterChip → SelectionGroup）
            SettingsGroup("源类型") {
                SelectionGroup(
                    title = "源类型",
                    options = listOf(
                        "PLAYLIST" to "频道源 (${sources.size})",
                        "EPG" to "EPG 源 (${epgSources.size})"
                    ),
                    selectedKey = sourceTab.name,
                    onSelect = { key ->
                        if (key == "PLAYLIST") viewModel.setSourceTab(SourceTab.PLAYLIST)
                        else viewModel.setSourceTab(SourceTab.EPG)
                    }
                )
            }

            // 加载消息（小灰字）
            if (sourceMessage.isNotEmpty()) {
                Text(
                    text = sourceMessage,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp)
                )
            }

            // 局域网管理
            SettingsGroup("局域网管理") {
                if (adminRunning && adminUrl.isNotEmpty()) {
                    LanAdminInfoBar(
                        url = adminUrl,
                        token = adminToken,
                        showQrCode = showQrCode,
                        onToggleQr = { showQrCode = it },
                        countdown = adminCountdown
                    )
                    AptvRowDivider()
                    SwitchRow(
                        title = "5 分钟自动关闭",
                        checked = autoStop,
                        onCheckedChange = {
                            autoStop = it
                            viewModel.setAdminAutoStop(it)
                        }
                    )
                } else if (!adminRunning) {
                    Text(
                        text = "TV 端用遥控器输入不便，点击启动后用手机浏览器扫码管理",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(vertical = 6.dp)
                    )
                    AptvRowDivider()
                    LanAdminTokenInput(viewModel = viewModel)
                    AptvRowDivider()
                    SwitchRow(
                        title = "5 分钟自动关闭",
                        checked = autoStop,
                        onCheckedChange = {
                            autoStop = it
                            viewModel.setAdminAutoStop(it)
                        }
                    )
                }
            }

            // 备份与恢复
            SettingsGroup("备份与恢复") {
                BackupRestoreBar(viewModel)
            }

            // 添加订阅源
            SettingsGroup(if (sourceTab == SourceTab.PLAYLIST) "添加频道订阅源" else "添加 EPG 订阅源") {
                when (sourceTab) {
                    SourceTab.PLAYLIST -> AddSourceRow(
                        placeholder = "输入 M3U 订阅源 URL",
                        onAdd = { url, name -> viewModel.addSource(url, name) }
                    )
                    SourceTab.EPG -> AddSourceRow(
                        placeholder = "输入 EPG 订阅源 URL（XMLTV）",
                        onAdd = { url, name -> viewModel.addEpgSource(url, name) }
                    )
                }
            }

            // 订阅源列表
            SettingsGroup(if (sourceTab == SourceTab.PLAYLIST) "频道订阅源" else "EPG 订阅源") {
                when (sourceTab) {
                    SourceTab.PLAYLIST -> {
                        if (sources.isEmpty()) {
                            EmptyHint("暂无频道订阅源，点击上方输入框添加")
                        } else {
                            sources.forEachIndexed { idx, source ->
                                SourceItem(
                                    source = source,
                                    index = idx,
                                    onToggle = { enabled -> viewModel.toggleSourceEnabled(idx, enabled) },
                                    onDelete = { viewModel.deleteSource(idx) },
                                    onEdit = { url, name -> viewModel.updateSource(idx, url, name) }
                                )
                                if (idx < sources.size - 1) AptvRowDivider()
                            }
                        }
                    }
                    SourceTab.EPG -> {
                        if (epgSources.isEmpty()) {
                            EmptyHint("暂无 EPG 订阅源，点击上方输入框添加")
                        } else {
                            epgSources.forEachIndexed { idx, source ->
                                EpgSourceItem(
                                    source = source,
                                    index = idx,
                                    onDelete = { viewModel.deleteEpgSource(idx) },
                                    onEdit = { url, name -> viewModel.updateEpgSource(idx, url, name) }
                                )
                                if (idx < epgSources.size - 1) AptvRowDivider()
                            }
                        }
                    }
                }
            }
        }
    }
}
