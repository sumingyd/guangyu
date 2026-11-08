package com.iptv.scanner.editor.pro.ui.theme

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import androidx.compose.ui.draw.drawWithContent

/**
 * TV 端焦点高亮边框 Modifier。
 *
 * 焦点反馈增强（放大 + 高亮）：
 * - 获取焦点：元素平滑放大（默认 1.07 倍）+ 提升绘制层级（不被相邻卡片遮挡）+
 *   2.5dp 白色圆角边框 + 半透明白色背景
 * - 失去焦点：动画还原到原始大小
 *
 * 仅添加焦点检测和条件边框，不添加 focusable（因为 `Modifier.clickable` 已内置 focusable）。
 * 适用于已有 `clickable` 的组件，链式调用 `.tvFocusBorder()` 即可。
 *
 * @param cornerRadius 边框圆角（dp），默认 8
 * @param focusedScale 焦点时放大倍数，默认 1.07
 */
fun Modifier.tvFocusBorder(cornerRadius: Int = 8, focusedScale: Float = 1.07f): Modifier = composed {
    var isFocused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isFocused) focusedScale else 1f,
        animationSpec = tween(durationMillis = 160),
        label = "tvFocusBorderScale"
    )
    this
        // 焦点元素提升绘制层级：放大后不被相邻网格卡/列表行遮挡
        .zIndex(if (isFocused) 1f else 0f)
        .onFocusChanged { isFocused = it.isFocused }
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        // 焦点视觉用 drawWithContent 画在内容之上：
        // 不会被链上更内层的不透明背景（chip 表面/选中底色）盖住，也不会被外层 clip 裁掉边框
        .drawWithContent {
            drawContent()
            if (isFocused) {
                val stroke = 2.5.dp.toPx()
                val pal = TvColors.p
                // 半透明底蒙层 + 聚焦描边，均取自 palette 的 focus token
                drawRoundRect(
                    color = pal.focusRing,
                    cornerRadius = CornerRadius(cornerRadius.dp.toPx())
                )
                drawRoundRect(
                    color = pal.focusIndicator,
                    topLeft = Offset(stroke / 2f, stroke / 2f),
                    size = Size(size.width - stroke, size.height - stroke),
                    cornerRadius = CornerRadius(cornerRadius.dp.toPx()),
                    style = Stroke(width = stroke)
                )
            }
        }
}

/**
 * 竖屏同款「白亮玻璃凸起块」选中效果（iOS 分段控件选中态）：
 * 白 20% 底 + 白 45% 描边 + 顶部高光垂直渐变。
 * 横屏 TV 面板（统一面板/主菜单/底栏）的选中态统一使用，替代旧的纯色/描边选中。
 */
fun Modifier.tvGlassSelected(cornerRadius: Int = 10): Modifier = composed {
    val shape = RoundedCornerShape(cornerRadius.dp)
    val pal = TvColors.p
    this
        .background(pal.borderFrostedStrong, shape)
        .border(1.dp, pal.focusRing, shape)
        .background(
            androidx.compose.ui.graphics.Brush.verticalGradient(
                0f to pal.borderHighlightLight,
                1f to Color.Transparent
            ),
            shape
        )
}

/**
 * TV 端可聚焦 + 焦点高亮 Modifier。
 *
 * 同时添加 `focusable()` + 焦点高亮（焦点时放大 + 2.5dp 白边，与 tvFocusBorder 一致）。
 * 适用于没有 `clickable` 但需要 D-pad 焦点导航的组件（如纯展示性 Surface）。
 *
 * @param cornerRadius 边框圆角（dp），默认 8
 * @param focusedScale 焦点时放大倍数，默认 1.07
 */
fun Modifier.tvFocusable(cornerRadius: Int = 8, focusedScale: Float = 1.07f): Modifier = composed {
    var isFocused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (isFocused) focusedScale else 1f,
        animationSpec = tween(durationMillis = 160),
        label = "tvFocusableScale"
    )
    this
        .zIndex(if (isFocused) 1f else 0f)
        .onFocusChanged { isFocused = it.isFocused }
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .focusable()
        .drawWithContent {
            drawContent()
            if (isFocused) {
                val stroke = 2.5.dp.toPx()
                val pal = TvColors.p
                drawRoundRect(
                    color = pal.focusRing,
                    cornerRadius = CornerRadius(cornerRadius.dp.toPx())
                )
                drawRoundRect(
                    color = pal.focusIndicator,
                    topLeft = Offset(stroke / 2f, stroke / 2f),
                    size = Size(size.width - stroke, size.height - stroke),
                    cornerRadius = CornerRadius(cornerRadius.dp.toPx()),
                    style = Stroke(width = stroke)
                )
            }
        }
}

/**
 * TV 端 TextField 焦点导航 Modifier。
 *
 * 解决 OutlinedTextField / BasicTextField 获得焦点后 D-pad 上下键被
 * 文本光标移动消费、导致焦点无法移出输入框的问题（"焦点陷阱"）。
 *
 * 行为：
 * - DPAD_UP：移动焦点到上一个可聚焦元素，成功则消费事件
 * - DPAD_DOWN：移动焦点到下一个可聚焦元素，成功则消费事件
 * - DPAD_LEFT/RIGHT：不拦截，保留文本光标左右移动功能
 * - 其他按键（含软键盘输入）：不拦截
 *
 * 如果 moveFocus 返回 false（方向上没有更多可聚焦元素），
 * 也消费事件以防 TextField 内部将 DPAD_UP/DOWN 误解为光标移动。
 *
 * 用法：
 * ```
 * OutlinedTextField(
 *     value = text,
 *     onValueChange = { text = it },
 *     modifier = Modifier.fillMaxWidth().tvTextField(),
 *     ...
 * )
 * ```
 */
fun Modifier.tvTextField(): Modifier = composed {
    val focusManager = LocalFocusManager.current
    this.onPreviewKeyEvent { event ->
        if (event.type == KeyEventType.KeyDown) {
            when (event.key) {
                Key.DirectionUp -> {
                    focusManager.moveFocus(FocusDirection.Up)
                    true
                }
                Key.DirectionDown -> {
                    focusManager.moveFocus(FocusDirection.Down)
                    true
                }
                else -> false
            }
        } else {
            false
        }
    }
}
