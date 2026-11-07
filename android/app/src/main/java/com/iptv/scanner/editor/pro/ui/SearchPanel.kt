package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import com.iptv.scanner.editor.pro.ui.theme.tvTextField
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 全局搜索面板：与 PC 端 UnifiedSearchDialog + Web 端 search 面板对齐。
 *
 * 搜索范围：
 * - 频道：name / group / url（与 PC 端一致）
 * - 节目：title / desc（遍历 epgCache，上限 200 条）
 *
 * 结果点击：
 * - 频道：切台并播放
 * - 节目：切台，过去节目触发 catchup（与 PC 端 _on_epg_search_program_selected 对齐）
 *
 * 防抖 250ms（与 PC 端一致）。
 */
@Composable
fun SearchPanel(viewModel: AppViewModel) {
    if (LocalAptvStyle.current) {
        SearchPanelAptv(viewModel)
        return
    }
    val results by viewModel.searchResults.collectAsState()
    val loading by viewModel.searchLoading.collectAsState()
    val scope by viewModel.searchScope.collectAsState()

    var query by remember { mutableStateOf("") }

    // TV 焦点管理：面板打开时请求焦点到关闭按钮，确保 DPAD 可操作。
    // 不请求到搜索框，因为 OutlinedTextField 获得焦点会弹出软键盘，阻碍 DPAD 导航。
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(50)
        kotlin.runCatching { closeFocusRequester.requestFocus() }
    }

    // 输入防抖：query 变化时触发 ViewModel.performSearch（内部已有 250ms 防抖）
    LaunchedEffect(query) {
        viewModel.performSearch(query)
    }

    Surface(color = Color.Transparent, modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
            // -----------------------------------------------------------------
            // 标题栏
            // -----------------------------------------------------------------
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "全局搜索",
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.onSurface
                )
                IconButton(
                    onClick = { viewModel.toggleSearchPanel() },
                    modifier = Modifier
                        .tvFocusBorder()
                        .focusRequester(closeFocusRequester)
                ) {
                    Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // -----------------------------------------------------------------
            // 搜索框
            // -----------------------------------------------------------------
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = {
                    Text(
                        "搜索频道名 / 分组 / URL / 节目标题...",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                },
                leadingIcon = {
                    Icon(Icons.Default.Search, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = "" }, modifier = Modifier.tvFocusBorder()) {
                            Icon(Icons.Default.Close, contentDescription = "清空", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().tvTextField(),
                shape = RoundedCornerShape(8.dp),
                singleLine = true
            )

            Spacer(modifier = Modifier.height(8.dp))

            // -----------------------------------------------------------------
            // 范围筛选 + 状态
            // -----------------------------------------------------------------
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = scope == SearchScope.ALL,
                        onClick = { viewModel.setSearchScope(SearchScope.ALL) },
                        label = { Text("全部", fontSize = 11.sp) },
                        modifier = Modifier.tvFocusBorder()
                    )
                    FilterChip(
                        selected = scope == SearchScope.CHANNELS,
                        onClick = { viewModel.setSearchScope(SearchScope.CHANNELS) },
                        label = { Text("频道", fontSize = 11.sp) },
                        modifier = Modifier.tvFocusBorder()
                    )
                    FilterChip(
                        selected = scope == SearchScope.PROGRAMS,
                        onClick = { viewModel.setSearchScope(SearchScope.PROGRAMS) },
                        label = { Text("节目", fontSize = 11.sp) },
                        modifier = Modifier.tvFocusBorder()
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (loading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(14.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                    Text(
                        text = "${results.size} 条结果",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // -----------------------------------------------------------------
            // 结果列表
            // -----------------------------------------------------------------
            when {
                query.isBlank() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "输入关键词搜索频道和节目",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp
                        )
                    }
                }
                !loading && results.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "无搜索结果",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp
                        )
                    }
                }
                else -> {
                    LazyColumn(modifier = Modifier.fillMaxSize()) {
                        items(items = results, key = { resultKey(it) }) { result ->
                            SearchResultRow(result) { viewModel.onSearchResultClick(result) }
                        }
                    }
                }
            }
        }
    }
}

/**
 * APTV（iOS 风格）全局搜索面板：单列布局，圆角分组卡片 + iOS 选择行。
 * 仅在竖屏 APTV 模式下使用，横屏/TV 仍走 [SearchPanel] 原有布局。
 */
@Composable
private fun SearchPanelAptv(viewModel: AppViewModel) {
    val results by viewModel.searchResults.collectAsState()
    val loading by viewModel.searchLoading.collectAsState()
    val scope by viewModel.searchScope.collectAsState()

    var query by remember { mutableStateOf("") }

    // 输入防抖：query 变化时触发 ViewModel.performSearch（内部已有 250ms 防抖）
    LaunchedEffect(query) {
        viewModel.performSearch(query)
    }

    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
        modifier = Modifier.fillMaxSize()
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
        ) {
            AptvPanelHeader(
                title = "全局搜索",
                subtitle = "频道 / 节目",
                onClose = { viewModel.toggleSearchPanel() }
            )

            // 搜索框
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                placeholder = {
                    Text(
                        "搜索频道名 / 分组 / URL / 节目标题...",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                },
                leadingIcon = {
                    Icon(Icons.Default.Search, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = "" }) {
                            Icon(Icons.Default.Close, contentDescription = "清空", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp)
                    .tvTextField(),
                shape = RoundedCornerShape(10.dp),
                singleLine = true
            )

            // 搜索范围（iOS 选择行）
            SettingsGroup("搜索范围") {
                SelectionGroup(
                    title = "范围",
                    options = listOf(
                        SearchScope.ALL.name to "全部",
                        SearchScope.CHANNELS.name to "频道",
                        SearchScope.PROGRAMS.name to "节目"
                    ),
                    selectedKey = scope.name,
                    onSelect = { key -> viewModel.setSearchScope(SearchScope.valueOf(key)) }
                )
            }

            // 状态行
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "结果",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (loading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(14.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                    }
                    Text(
                        text = "${results.size} 条",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 13.sp
                    )
                }
            }

            AptvRowDivider()

            // 结果列表
            when {
                query.isBlank() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "输入关键词搜索频道和节目",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp
                        )
                    }
                }
                !loading && results.isEmpty() -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = "无搜索结果",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 13.sp
                        )
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            horizontal = 16.dp,
                            vertical = 8.dp
                        )
                    ) {
                        items(items = results, key = { resultKey(it) }) { result ->
                            SearchResultRow(result) { viewModel.onSearchResultClick(result) }
                        }
                    }
                }
            }
        }
    }
}

/** 生成结果项的唯一 key */
private fun resultKey(result: SearchResult): String = when (result) {
    is SearchResult.ChannelResult -> "ch_${result.idx}"
    is SearchResult.ProgramResult ->
        "pg_${result.channelIdx}_${result.program.start}_${result.program.title}"
}

/**
 * 搜索结果行：
 * - 频道：[TV图标] 频道名  [分组]
 * - 节目：[HH:MM] 节目标题  (频道名)
 */
@Composable
private fun SearchResultRow(
    result: SearchResult,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .tvFocusBorder()
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        when (result) {
            is SearchResult.ChannelResult -> {
                // 频道图标
                Icon(
                    imageVector = Icons.Default.Tv,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(10.dp))
                // 频道名
                Text(
                    text = result.channel.name,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 14.sp,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                // 分组
                if (result.channel.group.isNotEmpty()) {
                    Spacer(modifier = Modifier.width(8.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f),
                        shape = RoundedCornerShape(4.dp),
                        modifier = Modifier.clip(RoundedCornerShape(4.dp))
                    ) {
                        Text(
                            text = result.channel.group,
                            color = MaterialTheme.colorScheme.secondary,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            maxLines = 1
                        )
                    }
                }
            }
            is SearchResult.ProgramResult -> {
                // 时间
                val timeText = remember(result.program.start) {
                    formatProgramTime(result.program.start)
                }
                Text(
                    text = timeText,
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 12.sp,
                    modifier = Modifier.width(50.dp)
                )
                Spacer(modifier = Modifier.width(10.dp))
                // 节目标题
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = result.program.title,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 13.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = result.channelName,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

/** 格式化节目时间（HH:MM） */
private fun formatProgramTime(iso: String): String {
    if (iso.isEmpty()) return "--:--"
    val patterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss'Z'",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd HH:mm"
    )
    for (pattern in patterns) {
        try {
            val date = SimpleDateFormat(pattern, Locale.US).parse(iso) ?: continue
            val cal = java.util.Calendar.getInstance().apply { time = date }
            return String.format(Locale.US, "%02d:%02d", cal.get(java.util.Calendar.HOUR_OF_DAY), cal.get(java.util.Calendar.MINUTE))
        } catch (_: Exception) {
        }
    }
    return iso.take(5)
}
