package com.iptv.scanner.editor.pro.ui.theme

import android.graphics.Bitmap
import android.os.Build
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import com.iptv.scanner.editor.pro.ui.tvPalette
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.hazeEffect
import dev.chrisbanes.haze.hazeSource
import kotlin.math.ceil

/**
 * iOS 26「液态玻璃」风格材质（对标 iOS 控制中心 / Telegram iOS 玻璃栏）。
 *
 * 设计要点（第一版「黑玻璃」失败教训）：
 * - iOS 玻璃是「亮」的——白色磨砂底，内容色彩从玻璃后透出，绝不是深灰实底
 * - 玻璃感来自「背后有内容可透」：真场景用 Haze backdrop blur 模糊背景；
 *   背景是纯色（如设置页）时，用「环境彩色光斑」模拟玻璃下透出的模糊世界
 * - 噪点颗粒是 iOS 玻璃质感的关键组成，缺失会显得像塑料
 *
 * 材质分层（自下而上）：
 * 1. backdrop blur（Haze）或亮色磨砂底 —— 白色系 tint
 * 2. 环境彩色光斑：蓝/紫/青三色 radial 低透明度，模拟透出的模糊色彩
 * 3. 噪点颗粒纹理
 * 4. 顶部高光光泽渐变
 * 5. lensing 双描边：顶部亮线 + 底部环境反光线 + 内侧细高光
 *
 * 平台限制：
 * - Dialog 是独立窗口（RenderNode 隔离），强制静态玻璃（staticGlass = true）
 * - SurfaceView 视频无法被采样，视频上方呈磨砂+光斑效果
 */

/** 背景层 HazeState：由播放器/主页根布局 provide，玻璃面板读取后对背景取景模糊 */
val LocalHazeState = compositionLocalOf<HazeState?> { null }

/**
 * 「画布模式」：玻璃卡直接浮在带环境光斑的页面画布上（竖屏 4 个 tab 内容区）。
 * true 时玻璃自身磨砂底减淡、光斑增强 —— 玻璃只透下面画布，不再各自带底色（iOS 观感）。
 * Dialog/独立窗口保持 false（底下无画布，需要自持底色保证可读性）。
 */
val LocalGlassOnCanvas = compositionLocalOf { false }

/** 判断当前设备是否支持实时 backdrop blur（API 31+ RenderEffect） */
internal fun isLiquidBlurSupported(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S

/** 播放器/主页根布局使用：把整个子树标记为玻璃模糊的采样源 */
internal fun Modifier.liquidGlassSource(hazeState: HazeState): Modifier =
    this.then(Modifier.hazeSource(hazeState))

/**
 * iOS 风格液态玻璃容器。
 *
 * @param enabled 液态玻璃总开关；false 时渲染为实底面板（原样式）
 * @param staticGlass 强制静态玻璃（不实时模糊）。Dialog 独立窗口必须传 true
 * @param fallbackColor 关闭时的实底色（保持各调用点原有观感）
 * @param cornerRadius 圆角半径
 */
@Composable
fun LiquidGlassSurface(
    enabled: Boolean,
    modifier: Modifier = Modifier,
    cornerRadius: Dp = 10.dp,
    staticGlass: Boolean = false,
    overlayDark: Boolean = false,
    fallbackColor: Color = Color(0xF0222222),
    content: @Composable BoxScope.() -> Unit
) {
    val shape = RoundedCornerShape(cornerRadius)
    val hazeState = LocalHazeState.current
    val useBlur = enabled && !staticGlass && isLiquidBlurSupported() && hazeState != null
    val radiusPx = with(LocalDensity.current) { cornerRadius.toPx() }
    val noise = if (enabled) rememberNoiseBitmap() else null
    // 主题自适应：深色模式玻璃为灰白磨砂（iOS 控制中心深色壁纸下的观感）；
    // 浅色模式白上白不可辨 —— 提高玻璃不透明度 + 投影浮起 + 深色描边
    val darkTheme = MaterialTheme.colorScheme.surface.luminance() < 0.5f
    // 浅色主题下覆盖层也必须用亮玻璃：否则「全屏/分屏」的侧栏、底栏、信息面板
    // 永远呈深色，用户切了浅色也看不到变化。暗玻璃只在深色主题生效。
    val glassBase = when {
        overlayDark && darkTheme -> OverlayGlass
        darkTheme -> DarkGlass
        else -> LightGlass
    }
    // 画布模式：去掉卡片内的光斑图案（光斑属于页面画布，不随卡片走），其余层保持原样
    val onCanvas = LocalGlassOnCanvas.current
    val glowScale = if (onCanvas) 0f else 1f

    Box(
        modifier = if (enabled && !darkTheme) {
            modifier
                .shadow(elevation = 6.dp, shape = shape, ambientColor = Color(0x33000000), spotColor = Color(0x44000000))
                .clip(shape)
        } else {
            modifier.clip(shape)
        }
    ) {
        if (enabled) {
            // 层 1：底色 —— blur 可用时对背景取景模糊 + 白色磨砂提亮；否则亮色磨砂底
            if (useBlur) {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .hazeEffect(state = hazeState!!) {
                            blurRadius = 24.dp
                            noiseFactor = 0f
                            // 白色磨砂：iOS 玻璃在深色内容上依然呈灰白
                            tints = listOf(HazeTint(glassBase.blurTint))
                            // SurfaceView 等无法采样的区域以中性灰兜底
                            backgroundColor = glassBase.fallbackSolid
                            fallbackTint = HazeTint(glassBase.fallbackSolid)
                        }
                )
            } else {
                Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(glassBase.frostBrush)
                )
            }
            // 层 2：环境彩色光斑 —— 模拟玻璃下透出的模糊世界（iOS 控制中心的灵魂）
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .drawBehind { drawAmbientGlow(size, glassBase, glowScale) }
            )
            // 层 3：噪点颗粒（iOS 玻璃质感关键）—— 平铺绘制，保持锐利
            noise?.let {
                androidx.compose.foundation.Canvas(
                    modifier = Modifier.matchParentSize()
                ) {
                    val step = it.width
                    var y = 0
                    while (y < size.height.toInt()) {
                        var x = 0
                        while (x < size.width.toInt()) {
                            drawImage(
                                image = it,
                                dstOffset = androidx.compose.ui.unit.IntOffset(x, y),
                                dstSize = androidx.compose.ui.unit.IntSize(step, step),
                                alpha = 0.55f,
                                filterQuality = androidx.compose.ui.graphics.FilterQuality.None
                            )
                            x += step
                        }
                        y += step
                    }
                }
            }
            // 层 4：顶部高光光泽
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .background(glassBase.glossBrush)
            )
            // 层 5：lensing 双描边
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .drawBehind { drawLensingBorder(size, radiusPx, glassBase, glassBase.borderTint ?: tvPalette.glassBorder) }
            )
        } else {
            Box(modifier = Modifier.matchParentSize().background(fallbackColor, shape))
        }
        content()
    }
}

/** 玻璃材质参数（按明暗主题区分） */
private class GlassBase(
    val blurTint: Color,
    val fallbackSolid: Color,
    val frostBrush: Brush,
    val glossBrush: Brush,
    val glowAlpha: Float,
    val borderTop: Float,
    val borderMid: Float,
    val borderBottom: Float,
    val innerHighlight: Float,
    // 描边基色：null 表示按主题取 palette 的 effect.glass_border
    // （深色白描边、浅色深灰蓝描边），避免在这里写死 #525B6B
    val borderTint: Color? = null
)

/**
 * 深色主题：iOS 控制中心式灰白磨砂玻璃，彩色光斑透出感强。
 *
 * 白色叠加强度曾用 0x66/0x4D/0x40（白 40%/30%/25%），叠在深色页底上把行底抬到
 * #7D8086 —— 上面 13~15sp 的白字只有 3.8~4.0:1。设置页分组卡片（AptvGroupCard）
 * 走的就是这条路径，属于可读性硬伤。这里降到 0x33/0x26/0x1F（白 20%/15%/12%），
 * 行底压到 #3E4A4E 量级，白字回到 6:1 以上，同时保留「比页底更亮」的玻璃层次。
 */
private val DarkGlass = GlassBase(
    blurTint = Color(0x33FFFFFF),          // 白 20%
    fallbackSolid = Color(0xFF3A3E46),
    frostBrush = Brush.verticalGradient(
        listOf(Color(0x33FFFFFF), Color(0x26FFFFFF), Color(0x1FFFFFFF))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.14f),
        0.35f to Color.White.copy(alpha = 0.04f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.06f)
    ),
    glowAlpha = 1f,
    borderTop = 0.55f, borderMid = 0.10f, borderBottom = 0.22f,
    innerHighlight = 0.16f
)

/** 播放器覆盖层专用：暗色玻璃（覆盖条上多为白色文字，亮玻璃会让白字不可读） */
private val OverlayGlass = GlassBase(
    blurTint = Color(0x66000000),          // 黑 40%
    fallbackSolid = Color(0xCC1A1C22),
    // 视频是 SurfaceView（硬件合成层）无法被采样做背景模糊 —— 霜层必须足够厚
    // （65%→50% 带蓝调）才能同时给出玻璃质感与白字可读性；太薄会退化成"只有透明度"
    frostBrush = Brush.verticalGradient(
        listOf(Color(0xA60D1016), Color(0x8F111922), Color(0x80131A20))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.20f),
        0.35f to Color.White.copy(alpha = 0.06f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.12f)
    ),
    glowAlpha = 0.5f,
    borderTop = 0.40f, borderMid = 0.10f, borderBottom = 0.20f,
    innerHighlight = 0.12f
)

/** 浅色主题：更实的白玻璃 + 阴影浮起（由外部 shadow 提供）+ 深色描边可辨 */
private val LightGlass = GlassBase(
    blurTint = Color(0x8CFFFFFF),          // 白 55%
    fallbackSolid = Color(0xFFE8EAF0),
    // 静态玻璃霜层：整体提亮（白 82%→72%→66%），减少画布灰底透出导致的「发灰」观感
    frostBrush = Brush.verticalGradient(
        listOf(Color(0xD1FFFFFF), Color(0xB8FFFFFF), Color(0xA8FFFFFF))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.30f),
        0.35f to Color.White.copy(alpha = 0.08f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.04f)
    ),
    glowAlpha = 0.85f,
    // 深色描边：白底上白描边不可见，改用深灰蓝提供轮廓（顶部仍保留弱高光感）
    borderTop = 0.30f, borderMid = 0.12f, borderBottom = 0.18f,
    innerHighlight = 0.10f
)

/** 环境彩色光斑基色 */
private val GlowBlue = Color(0x2E5B8CFF)
private val GlowPurple = Color(0x24C084FC)
private val GlowTeal = Color(0x1F34D399)

/** 环境彩色光斑：三色 radial 模拟玻璃下透出的模糊内容色彩；glowScale 画布模式下增强 */
private fun DrawScope.drawAmbientGlow(size: Size, base: GlassBase, glowScale: Float = 1f) {
    val r = size.minDimension
    // 左上：蓝
    drawCircle(
        brush = Brush.radialGradient(
            listOf(GlowBlue.copy(alpha = GlowBlue.alpha * base.glowAlpha * glowScale), Color.Transparent)
        ),
        radius = r * 0.9f,
        center = Offset(size.width * 0.12f, size.height * 0.05f)
    )
    // 右中：紫粉
    drawCircle(
        brush = Brush.radialGradient(
            listOf(GlowPurple.copy(alpha = GlowPurple.alpha * base.glowAlpha * glowScale), Color.Transparent)
        ),
        radius = r * 0.8f,
        center = Offset(size.width * 0.92f, size.height * 0.55f)
    )
    // 左下：青绿
    drawCircle(
        brush = Brush.radialGradient(
            listOf(GlowTeal.copy(alpha = GlowTeal.alpha * base.glowAlpha * glowScale), Color.Transparent)
        ),
        radius = r * 0.75f,
        center = Offset(size.width * 0.2f, size.height * 1.0f)
    )
}

/** lensing 双描边：外圈顶部亮线+底部反光线；内圈细高光 */
private fun DrawScope.drawLensingBorder(size: Size, radiusPx: Float, base: GlassBase, borderTint: Color) {
    val w = 1.2.dp.toPx()
    drawRoundRect(
        brush = Brush.verticalGradient(
            0f to borderTint.copy(alpha = base.borderTop),
            0.5f to borderTint.copy(alpha = base.borderMid),
            1f to borderTint.copy(alpha = base.borderBottom)
        ),
        cornerRadius = CornerRadius(radiusPx, radiusPx),
        style = Stroke(width = w)
    )
    val inset = w + 0.8.dp.toPx()
    drawRoundRect(
        brush = Brush.verticalGradient(
            0f to Color.White.copy(alpha = base.innerHighlight),
            1f to Color.Transparent
        ),
        topLeft = Offset(inset, inset),
        size = Size(size.width - inset * 2, size.height - inset * 2),
        cornerRadius = CornerRadius(
            (radiusPx - inset).coerceAtLeast(0f),
            (radiusPx - inset).coerceAtLeast(0f)
        ),
        style = Stroke(width = 0.8.dp.toPx())
    )
}

/** 记忆化噪点纹理：白灰随机颗粒，平铺绘制 */
@Composable
private fun rememberNoiseBitmap(): androidx.compose.ui.graphics.ImageBitmap? {
    if (!isLiquidBlurSupported()) return null
    return remember {
        runCatching {
            val s = 72
            val bmp = Bitmap.createBitmap(s, s, Bitmap.Config.ARGB_8888)
            val pixels = IntArray(s * s)
            val rng = java.util.Random(7)
            for (i in pixels.indices) {
                val a = (rng.nextInt(20) + 6) * (if (rng.nextBoolean()) 1 else 0)
                pixels[i] = (a shl 24) or 0x00FFFFFF
            }
            bmp.setPixels(pixels, 0, s, 0, 0, s, s)
            bmp.asImageBitmap()
        }.getOrNull()
    }
}

/** 记忆化 HazeState（根布局用） */
@Composable
fun rememberLiquidHazeState(): HazeState = remember { HazeState() }
