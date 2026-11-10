package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 启动加载屏：调用 initContext → 轮询 getStatus，加载完成后 Activity 切换到主播放屏。
 *
 * 显示内容：
 * - 旋转加载指示器
 * - 应用标题
 * - 当前状态消息（初始化中 / 正在加载订阅源 / 失败原因）
 * - 失败时显示重试按钮
 *
 * 注意：这里绝不能自带 IptvTheme。主题（含全局 TvColors）由 MainActivityCompose 唯一提供，
 * 早期版本在此处再包一层 `IptvTheme { }`，会用默认 themeMode="dark" 写污染全局
 * TvColors.isDark，且启动屏退出后无人复位 —— 浅色模式下整页画布/分割线仍按深色取值绘制，
 * 表现为「整页底色是黑的」「MINI 条深色文字压在黑色画布上看不清」。
 */
@Composable
fun SplashScreen(viewModel: AppViewModel) {
    val initState by viewModel.initState.collectAsState()
    val iptvStatus by viewModel.iptvStatus.collectAsState()

    // 初始化已在 AppViewModel.init 块中自动启动，这里只负责显示状态。
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.systemBarsPadding().padding(24.dp)
        ) {
            // 加载指示器（失败时不显示）
            if (initState !is InitState.Failed) {
                CircularProgressIndicator(
                    color = MaterialTheme.colorScheme.primary,
                    strokeWidth = 3.dp,
                    modifier = Modifier.width(56.dp).height(56.dp)
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = viewModel.getCurrentVersion(),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 14.sp
                )
                Spacer(modifier = Modifier.height(24.dp))
            }

            Text(
                text = "光屿 GuangYu",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onBackground
            )
            Spacer(modifier = Modifier.height(12.dp))

            // 状态消息
            val statusMessage = when (val state = initState) {
                is InitState.Idle -> "准备初始化..."
                is InitState.Initializing -> {
                    // 显示更详细的状态
                    val s = iptvStatus
                    when {
                        s == null -> "正在初始化 Python 环境..."
                        !s.inited -> "正在初始化 ServerContext..."
                        s.sourceLoading -> "正在加载订阅源...（${s.channelsTotal} 频道）"
                        else -> "加载完成，频道数：${s.channelsTotal}"
                    }
                }
                is InitState.Ready -> "加载完成"
                is InitState.Failed -> "初始化失败：${state.message}"
            }
            Text(
                text = statusMessage,
                style = MaterialTheme.typography.bodyMedium,
                color = if (initState is InitState.Failed)
                    MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center
            )

            // 失败时显示重试按钮
            if (initState is InitState.Failed) {
                Spacer(modifier = Modifier.height(20.dp))
                Button(onClick = { viewModel.startInitialization() }) {
                    Text("重试")
                }
            }
        }
    }
}
