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
import androidx.compose.foundation.ExperimentalFoundationApi
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
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
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
import androidx.compose.material3.RadioButton
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.foundation.focusGroup
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
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
import kotlinx.coroutines.launch
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
// =================================================================
// 网络增强面板
// =================================================================

/**
 * 网络增强面板：HTTP Referer / Proxy / Headers 设置。
 * 与 PC 端「设置 → 网络 → 流媒体请求」对齐。
 *
 * 仅 MPV 播放器支持（通过 setPropertyString 下发到 mpv）。
 * 注意：设置在下次 loadfile 时生效，当前播放不会立即应用。
 */
@Composable
fun NetworkPanel(viewModel: AppViewModel) {
    val (initReferer, initProxy, initHeaders) = remember { viewModel.loadNetworkSettings() }
    var referer by remember { mutableStateOf(initReferer) }
    var proxy by remember { mutableStateOf(initProxy) }
    var headers by remember { mutableStateOf(initHeaders) }
    var errorText by remember { mutableStateOf("") }

    PanelScaffold(
        title = "网络增强",
        subtitle = "Referer / Proxy / Headers（仅 MPV 支持）",
        onClose = { viewModel.toggleNetworkPanel() }
    ) {
        SettingsGroup("HTTP Referer") {
            DescText("用于绕过防盗链（mpv referrer 属性）")
            OutlinedTextField(
                value = referer, onValueChange = { referer = it },
                label = { Text("如 https://example.com/") },
                modifier = Modifier.fillMaxWidth().tvTextField(),
                singleLine = true
            )
        }

        SettingsGroup("HTTP/HTTPS 代理") {
            DescText("仅支持 http:// / https://（mpv http-proxy）；SOCKS5 不被 mpv 的 HTTP 协议栈支持，socks5:// 不会生效。只有 SOCKS5 时请在本机用 gost/Privoxy 转成本地 HTTP 端口后再填。")
            OutlinedTextField(
                value = proxy, onValueChange = { proxy = it },
                label = { Text("如 http://127.0.0.1:8080") },
                modifier = Modifier.fillMaxWidth().tvTextField(),
                singleLine = true
            )
        }

        SettingsGroup("HTTP Headers") {
            DescText("每行一个，格式 Key: Value；保存时整体一次写入（多行都会保留）")
            OutlinedTextField(
                value = headers, onValueChange = { headers = it },
                label = { Text("User-Agent: Mozilla/5.0\nAuthorization: Bearer xxx") },
                modifier = Modifier.fillMaxWidth().heightIn(min = 80.dp).tvTextField(),
                maxLines = 5
            )
        }

        if (errorText.isNotBlank()) {
            Text(
                text = errorText,
                color = MaterialTheme.colorScheme.error,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 4.dp)
            )
        }

        Spacer(modifier = Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedButton(
                onClick = {
                    referer = ""; proxy = ""; headers = ""; errorText = ""
                    viewModel.clearNetworkSettings()
                },
                modifier = Modifier.weight(1f).tvFocusBorder()
            ) { Text("清除", color = MaterialTheme.colorScheme.onSurface) }

            OutlinedButton(
                onClick = {
                    val ok = viewModel.applyNetworkSettings(referer, proxy, headers)
                    errorText = if (ok) "" else "代理地址需以 http:// 或 https:// 开头"
                },
                modifier = Modifier.weight(1f).tvFocusBorder()
            ) { Text("应用", color = MaterialTheme.colorScheme.onSurface) }

            OutlinedButton(
                onClick = {
                    val ok = viewModel.saveNetworkSettings(referer, proxy, headers)
                    errorText = if (ok) "" else "代理地址需以 http:// 或 https:// 开头"
                },
                modifier = Modifier.weight(1f).tvFocusBorder()
            ) { Text("保存", color = MaterialTheme.colorScheme.primary) }
        }

        Spacer(modifier = Modifier.height(8.dp))
        DescText("代理只支持 http:// 或 https://，socks5:// 会被拒绝；设置在下一次加载流时生效，当前播放不会立即应用。清除会同时移除 Referer、代理与自定义请求头。")
    }
}

// -----------------------------------------------------------------
// GitHub 加速代理（设置 -> 网络）
// -----------------------------------------------------------------

@OptIn(ExperimentalFoundationApi::class)
@Composable
internal fun GithubProxyPanel(viewModel: AppViewModel) {
    val enabled by viewModel.githubProxyEnabled.collectAsState()
    val selected by viewModel.githubProxySelected.collectAsState()
    val options by viewModel.githubProxyOptions.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadGithubProxySettings() }

    PanelScaffold(
        title = "GitHub 加速代理",
        subtitle = "用于检查更新、在线更新、远程映射、订阅源与 EPG",
        onClose = { viewModel.toggleGithubProxyPanel() }
    ) {
        SettingsGroup("加速开关") {
            AptvSwitchRow(
                Icons.Default.Link,
                "启用 GitHub 加速代理",
                checked = enabled,
                onCheckedChange = { viewModel.setGithubProxyEnabled(it) }
            )
            DescText("只改写 GitHub 域名请求；订阅源、EPG 等非 GitHub 地址不受影响。")
        }

        SettingsGroup("代理地址") {
            val scope = rememberCoroutineScope()
            options.forEach { proxy ->
                // 遥控器上下移动时把当前项滚进可视区，避免 25 个代理里后段永远够不到
                val bring = remember(proxy) { BringIntoViewRequester() }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 2.dp)
                        .bringIntoViewRequester(bring)
                        .onFocusChanged {
                            if (it.isFocused) scope.launch { bring.bringIntoView() }
                        }
                        .tvFocusBorder()
                        .clip(RoundedCornerShape(8.dp))
                        .clickable(enabled = enabled) { viewModel.setGithubProxySelected(proxy) }
                        .padding(horizontal = 8.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(
                        selected = proxy == selected,
                        onClick = null,
                        enabled = enabled
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = proxy,
                        color = if (proxy == selected) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurface,
                        fontSize = 14.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
            DescText("修改后立即生效，无需重启。")
        }
    }
}
