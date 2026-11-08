package com.iptv.scanner.editor.pro.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 屏保页（D）。
 *
 * 内容层次：时钟 → 当前频道 / 当前节目（EPG）→ 频谱层（有真实音频才动，否则静态柱）。
 *
 * 性能约束：
 * - 只随音频帧更新（Visualizer 上限 20Hz），天然低于 30fps 上限；时钟单独 1s 刷新。
 * - 频谱固定 48 根柱子、纯色矩形、无模糊/无渐变/无阴影，单次 Canvas 绘制。
 * - 屏保未显示时本 Composable 直接返回，不采样、不占帧。
 *
 * 退出：任意按键由 MainActivity.dispatchKeyEvent 在最前面吞掉并调用 dismissScreenSaver；
 * 触摸由下方 pointerInput 兜底。屏保只在「无面板、未播放、前台」时出现，因此退出时没有
 * 其它层可被顺带关闭。
 */
@Composable
fun ScreenSaverOverlay(viewModel: AppViewModel) {
    val visible by viewModel.screenSaverVisible.collectAsState()
    if (!visible) return

    val palette = tvPalette
    val spectrum by viewModel.audioSpectrum.collectAsState()
    val spectrumError by viewModel.audioSpectrumError.collectAsState()
    val playback by viewModel.playbackState.collectAsState()
    val currentEpg by viewModel.currentEpg.collectAsState()

    // 屏保显示期间才启动音频采样，退出立即释放（与其它面板共用引用计数）
    DisposableEffect(Unit) {
        viewModel.startSpectrumSampling()
        onDispose { viewModel.stopSpectrumSampling() }
    }

    var nowMs by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            nowMs = System.currentTimeMillis()
            delay(1_000L)
        }
    }

    val channelName = playback.originalChannel?.name.orEmpty()
    val program = currentEpg.firstOrNull {
        it.startTs > 0 && nowMs >= it.startTs && nowMs < it.stopTs
    }
    val programTitle = program?.title.orEmpty()
    val programTime = if (program != null) {
        val fmt = SimpleDateFormat("HH:mm", Locale.getDefault())
        "${fmt.format(Date(program.startTs))} - ${fmt.format(Date(program.stopTs))}"
    } else ""

    val timeFmt = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }
    val dateFmt = remember { SimpleDateFormat("M月d日 EEEE", Locale.CHINA) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.window)
            .pointerInput(Unit) {
                detectTapGestures { viewModel.dismissScreenSaver("touch") }
            }
    ) {
        // 静态氛围光（不参与动画，避免屏保期间持续重绘）
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawRect(
                brush = Brush.radialGradient(
                    colors = listOf(palette.accentBase.copy(alpha = 0.10f), Color.Transparent),
                    center = Offset(size.width * 0.5f, size.height * 0.38f),
                    radius = size.minDimension * 0.62f
                )
            )
        }

        Column(
            modifier = Modifier
                .align(Alignment.Center)
                .padding(horizontal = 48.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(
                text = timeFmt.format(Date(nowMs)),
                color = palette.textPrimary,
                fontSize = 104.sp,
                fontWeight = FontWeight.Light
            )
            Text(
                text = dateFmt.format(Date(nowMs)),
                color = palette.textSecondary,
                fontSize = 22.sp
            )
            if (channelName.isNotEmpty()) {
                Text(
                    text = channelName,
                    color = palette.textTertiary,
                    fontSize = 26.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 18.dp)
                )
            }
            if (programTitle.isNotEmpty()) {
                Text(
                    text = programTitle,
                    color = palette.textSecondary,
                    fontSize = 19.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                if (programTime.isNotEmpty()) {
                    Text(text = programTime, color = palette.textDisabled, fontSize = 15.sp)
                }
            }
        }

        // 频谱层：有真实音频时随音频帧更新；不可用时退化为静态柱形装饰（不再动画）
        val source = if (spectrumError.isEmpty() && spectrum.any { it > 0.01f }) {
            spectrum
        } else {
            STATIC_BARS
        }
        Canvas(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(horizontal = 96.dp, vertical = 40.dp)
                .height(96.dp)
        ) {
            val bars = source.size.coerceAtMost(STATIC_BARS.size)
            if (bars <= 0) return@Canvas
            val gap = size.width / bars * 0.35f
            val barW = (size.width - gap * (bars - 1)) / bars
            for (i in 0 until bars) {
                val v = source[i].coerceIn(0f, 1f)
                val h = (size.height * (0.06f + v * 0.94f)).coerceAtLeast(3f)
                drawRect(
                    color = palette.accentBase.copy(alpha = if (source === STATIC_BARS) 0.28f else 0.85f),
                    topLeft = Offset(i * (barW + gap), size.height - h),
                    size = Size(barW, h)
                )
            }
        }
    }
}

/** 无音频时的静态柱形（不随时间变化，避免屏保期间空转） */
private val STATIC_BARS = FloatArray(48) { i ->
    val x = i / 47f
    (0.10f + 0.26f * kotlin.math.abs(kotlin.math.sin(x * 7.0f))) * (1f - 0.3f * x)
}
