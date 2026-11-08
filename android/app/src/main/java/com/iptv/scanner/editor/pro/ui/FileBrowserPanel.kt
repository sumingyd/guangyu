package com.iptv.scanner.editor.pro.ui

import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.Settings
import android.util.Log
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iptv.scanner.editor.pro.ui.theme.tvFocusBorder
import kotlinx.coroutines.delay
import java.io.File

// 与 PC 端 file_ops_mixin.py 对齐的扩展名
private val VIDEO_EXTS = setOf("mp4", "mkv", "avi", "mov", "flv", "wmv", "ts", "m2ts", "webm")
private val AUDIO_EXTS = setOf("mp3", "flac", "wav", "aac", "ogg", "opus", "wma", "m4a",
    "ape", "alac", "wv", "tta", "dts", "ac3", "mid", "midi")
private val MEDIA_EXTS = VIDEO_EXTS + AUDIO_EXTS

/**
 * 文件浏览器面板：当系统 SAF 不可用时（Android TV 无文件选择器），
 * 提供应用内文件浏览功能。
 *
 * 两种模式（由 [AppViewModel.fileBrowserMode] 控制）：
 * - PLAYLIST：选择 M3U/M3U8 文件导入频道列表
 * - MEDIA：选择视频/音频文件直接播放
 *
 * 特性：
 * - 从外部存储根目录开始浏览
 * - 目录优先，文件按名称排序
 * - 高亮显示目标文件
 * - 支持 TV 遥控器 DPAD 焦点导航
 */
@Composable
fun FileBrowserPanel(viewModel: AppViewModel) {
    val mode by viewModel.fileBrowserMode.collectAsState()
    val context = LocalContext.current
    var hasStoragePermission by remember { mutableStateOf(android.os.Environment.isExternalStorageManager()) }
    var currentPath by remember {
        val initDir = if (hasStoragePermission) {
            try {
                Environment.getExternalStorageDirectory().absolutePath
            } catch (e: Exception) {
                "/storage"
            }
        } else {
            context.getExternalFilesDir(null)?.absolutePath ?: context.filesDir.absolutePath
        }
        mutableStateOf(initDir)
    }

    // 应用从后台返回时（如从权限设置页面返回）重新检查权限
    val lifecycleOwner = androidx.compose.ui.platform.LocalLifecycleOwner.current
    androidx.compose.runtime.DisposableEffect(lifecycleOwner) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME) {
                val granted = android.os.Environment.isExternalStorageManager()
                if (granted && !hasStoragePermission) {
                    // 权限刚授予，切换到外部存储根目录
                    hasStoragePermission = true
                    try {
                        currentPath = Environment.getExternalStorageDirectory().absolutePath
                    } catch (e: Exception) {
                        currentPath = "/storage"
                    }
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val items = remember(currentPath) {
        try {
            val dir = File(currentPath)
            val files = dir.listFiles()?.toMutableList() ?: mutableListOf()
            // 目录在前，文件在后；各自按名称排序
            files.sortWith(compareBy<File> { !it.isDirectory }.thenBy { it.name.lowercase() })
            files
        } catch (e: Exception) {
            emptyList()
        }
    }

    // 返回上一级路径（无父目录时为 null）
    val parentPath = remember(currentPath) {
        val f = File(currentPath)
        f.parentFile?.absolutePath
    }

    // 焦点处理：
    // 1. listFocusRequester：绑定到文件列表第一项（用户打开面板后期望直接浏览文件）
    // 2. upFocusRequester：绑定到"返回上一级"（当列表为空时作为 fallback）
    // 3. closeFocusRequester：绑定到关闭按钮（当无父目录且列表为空时作为最终 fallback）
    // 用 LaunchedEffect(currentPath) 确保每次切换目录后重新请求焦点到列表第一项。
    // delay(50) 等 LazyColumn 第一项完成组合，避免 FocusRequester 找不到绑定节点。
    val listFocusRequester = remember { FocusRequester() }
    val upFocusRequester = remember { FocusRequester() }
    val closeFocusRequester = remember { FocusRequester() }
    LaunchedEffect(currentPath, items.size) {
        delay(50)
        try {
            if (items.isNotEmpty()) {
                listFocusRequester.requestFocus()
            } else if (parentPath != null) {
                upFocusRequester.requestFocus()
            } else {
                closeFocusRequester.requestFocus()
            }
        } catch (e: Exception) {
            Log.w("FileBrowserPanel", "requestFocus failed: ${e.message}")
        }
    }

    val focusManager = LocalFocusManager.current

    Surface(
        color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxSize()
    ) {
Column(modifier = Modifier.fillMaxSize().systemBarsPadding()) {
// 标题栏
Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = when (mode) {
                                FileBrowserMode.PLAYLIST -> "选择播放列表文件"
                                FileBrowserMode.MEDIA -> "选择音视频文件"
                            },
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            text = currentPath,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    IconButton(
                        onClick = { viewModel.toggleFileBrowser() },
                        modifier = Modifier
                            .tvFocusBorder()
                            .focusRequester(closeFocusRequester)
                    ) {
                        Icon(Icons.Default.Close, contentDescription = "关闭", tint = MaterialTheme.colorScheme.onSurface)
                    }
                }
            }

            // 权限不足提示
            if (!hasStoragePermission) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "仅可浏览应用目录。授予权限后可浏览全部存储",
                            color = tvPalette.warning,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1f)
                        )
                        Button(
                            onClick = {
                                // Android TV 上 Composable 的 LocalContext 可能不是 Activity，
                                // 需要添加 FLAG_ACTIVITY_NEW_TASK 确保能启动系统设置 Activity。
                                // 某些 Android TV ROM 不支持 ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION，
                                // 回退到 ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION 通用设置页。
                                try {
                                    val intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                                        data = Uri.parse("package:${context.packageName}")
                                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                    }
                                    context.startActivity(intent)
                                } catch (e: Exception) {
                                    Log.w("FileBrowserPanel", "MANAGE_APP_ALL_FILES failed: ${e.message}")
                                    try {
                                        val intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION).apply {
                                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                        }
                                        context.startActivity(intent)
                                    } catch (e2: Exception) {
                                        Log.e("FileBrowserPanel", "MANAGE_ALL_FILES also failed: ${e2.message}")
                                        viewModel.showOsd("无法打开权限设置", "请手动在系统设置中授予权限")
                                    }
                                }
                            },
                            modifier = Modifier.tvFocusBorder()
                        ) {
                            Icon(
                                Icons.Default.LockOpen,
                                contentDescription = null,
                                modifier = Modifier.padding(end = 4.dp)
                            )
                            Text("授予权限", fontSize = 12.sp)
                        }
                    }
                }
            }

            // 返回上一级
            if (parentPath != null) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        // tvFocusBorder 在 clickable 之前（外层）才能收到焦点事件
                        .tvFocusBorder()
                        .clickable { currentPath = parentPath }
                        .padding(horizontal = 16.dp, vertical = 10.dp)
                        .focusRequester(upFocusRequester),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "返回上一级",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    Text("返回上一级", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
                }
            }

            // 文件列表
            if (items.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "此目录为空或无法访问",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 14.sp
                    )
                }
            } else {
                // 焦点导航修复：
                // 根因：Column(verticalScroll) 会消费方向键事件来滚动内容，导致上键无法
                // 逃逸到列表上方的"返回上一级"行和"关闭/授权"按钮。
                // 修复：用 onPreviewKeyEvent 在 KeyDown 阶段处理边缘导航：
                // - 焦点在第一项时按上键 → focusManager.moveFocus(Up) 强制移到上方元素
                // - 焦点在最后一项时按下键 → 拦截，保持焦点不动（防止逃逸到下层播放器）
                // 用 onFocusChanged 记录当前焦点项索引。
                var focusedIndex by remember { mutableStateOf(0) }
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(vertical = 4.dp)
                        .onPreviewKeyEvent { e ->
                            if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                            when (e.key) {
                                Key.DirectionUp -> {
                                    if (focusedIndex == 0) {
                                        // 焦点在第一项，强制移到上方元素（返回上一级/授权/关闭）
                                        focusManager.moveFocus(FocusDirection.Up)
                                        true  // 消费事件，防止 verticalScroll 滚动
                                    } else false
                                }
                                Key.DirectionDown -> {
                                    if (focusedIndex >= items.size - 1) {
                                        true  // 拦截，防止焦点逃逸到下层
                                    } else false
                                }
                                else -> false
                            }
                        }
                ) {
                    items.forEachIndexed { index, file ->
                        val ext = file.extension.lowercase()
                        // 根据 mode 判断目标文件
                        val isTarget = when (mode) {
                            FileBrowserMode.PLAYLIST -> ext in setOf("m3u", "m3u8")
                            FileBrowserMode.MEDIA -> ext in MEDIA_EXTS
                        }
                        val isVideo = ext in VIDEO_EXTS
                        val isAudio = ext in AUDIO_EXTS
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                // 第一项绑定 listFocusRequester，面板打开/切换目录时自动获得焦点
                                .then(if (index == 0) Modifier.focusRequester(listFocusRequester) else Modifier)
                                .onFocusChanged { if (it.isFocused) focusedIndex = index }
                                .clickable {
                                    if (file.isDirectory) {
                                        currentPath = file.absolutePath
                                    } else if (isTarget) {
                                        when (mode) {
                                            FileBrowserMode.PLAYLIST ->
                                                viewModel.importPlaylistFromFile(file.absolutePath)
                                            FileBrowserMode.MEDIA ->
                                                viewModel.playLocalVideo(file.absolutePath)
                                        }
                                    }
                                }
                                .padding(horizontal = 16.dp, vertical = 10.dp)
                                .tvFocusBorder(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            val icon = when {
                                file.isDirectory -> Icons.Default.Folder
                                isVideo -> Icons.Default.Movie
                                isAudio -> Icons.Default.MusicNote
                                else -> Icons.Default.Description
                            }
                            val iconTint = when {
                                file.isDirectory -> tvPalette.success
                                isTarget -> tvPalette.warning
                                else -> MaterialTheme.colorScheme.onSurfaceVariant
                            }
                            Icon(
                                imageVector = icon,
                                contentDescription = null,
                                tint = iconTint,
                                modifier = Modifier.padding(end = 10.dp)
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = file.name,
                                    color = if (isTarget) tvPalette.warning else MaterialTheme.colorScheme.onSurface,
                                    fontSize = 14.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                                if (!file.isDirectory) {
                                    val sizeText = remember(file.length()) {
                                        val len = file.length()
                                        when {
                                            len < 1024 -> "${len}B"
                                            len < 1024 * 1024 -> "${len / 1024}KB"
                                            else -> "${len / (1024 * 1024)}MB"
                                        }
                                    }
                                    Text(
                                        text = sizeText,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 11.sp
                                    )
                                }
                            }
                            if (isTarget) {
                                val label = when {
                                    ext in setOf("m3u", "m3u8") -> "M3U"
                                    isVideo -> "VIDEO"
                                    else -> "AUDIO"
                                }
                                Text(
                                    text = label,
                                    color = tvPalette.warning,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier
                                        .background(tvPalette.warning.copy(alpha = 0.2f), RoundedCornerShape(4.dp))
                                        .padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
