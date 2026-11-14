package com.iptv.scanner.editor.pro.ui.theme

import android.os.Build
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionOnScreen
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.iptv.scanner.editor.pro.ui.tvPalette
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.HazeTint
import dev.chrisbanes.haze.hazeEffect
import dev.chrisbanes.haze.hazeSource
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 液态玻璃材质（对标 Glasswork / MarcoMovie）。
 *
 * 材质分层（自下而上）：
 * 1. backdrop：折射层（AGSL，API33+ / Canvas 回流兜底）或 Haze 实时模糊，或静态霜层
 * 2. 染色：深色压暗 #1E1E22（不是白色提亮），浅色薄白
 * 3. 顶部光泽：很淡的白，避免把玻璃洗成奶白
 * 4. 边缘：外圈 1dp 镜面渐变 + 内圈缩进高光（液态玻璃的轮廓来源）
 *
 * 关键取舍：
 * - 模糊半径必须小（2~4dp）。大半径会把背景糊成均匀灰，玻璃后「没有任何内容」。
 * - 深色主题是压暗而非提亮；白色叠层会把暗底抬成灰塑料。
 * - 不做自绘噪点与环境彩色光斑：前者像塑料，后者与真实背景无关。
 *
 * 平台限制：
 * - Dialog 是独立窗口（RenderNode 隔离），强制静态玻璃（staticGlass = true）
 * - SurfaceView 视频无法被采样，视频上方走静态暗玻璃
 */

/** 背景层 HazeState：由播放器/主页根布局 provide，玻璃面板读取后对背景取景模糊 */
val LocalHazeState = compositionLocalOf<HazeState?> { null }

/**
 * 「画布模式」：玻璃卡直接浮在带环境光斑的页面画布上（竖屏 4 个 tab 内容区）。
 * true 时玻璃染色略轻，让画布光斑透出更多。
 */
val LocalGlassOnCanvas = compositionLocalOf { false }

/** 判断当前设备是否支持实时 backdrop blur（API 31+ RenderEffect） */
internal fun isLiquidBlurSupported(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S

/**
 * 是否可渲染玻璃材质：API29+ 有 GraphicsLayer，可做静态玻璃与 Canvas 折射兜底。
 * 实时模糊仍受 [isLiquidBlurSupported] 限制。
 */
internal fun isLiquidGlassSupported(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q

/** 播放器/主页根布局使用：把整个子树标记为玻璃模糊的采样源 */
internal fun Modifier.liquidGlassSource(hazeState: HazeState): Modifier =
    this.then(Modifier.hazeSource(hazeState))

/**
 * 玻璃容器。
 *
 * @param enabled 液态玻璃总开关；false 时渲染为实底面板（原样式）
 * @param staticGlass 强制静态玻璃（不采样背景）。Dialog 独立窗口必须传 true
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
    val radiusPx = with(LocalDensity.current) { cornerRadius.toPx() }
    // 主题自适应：深色主题玻璃为暗色压暗玻璃；浅色主题为薄白玻璃
    val darkTheme = MaterialTheme.colorScheme.surface.luminance() < 0.5f
    val glassBase = when {
        overlayDark && darkTheme -> OverlayGlass
        darkTheme -> DarkGlass
        else -> LightGlass
    }
    val onCanvas = LocalGlassOnCanvas.current
    // 折射分两条：API33+ 走 AGSL 逐像素折射（车机验证过，保持不动）；
    // API29~30 走原来的 Canvas 回流兜底。
    val agslAvailable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
    val useRefraction = enabled && !staticGlass && hazeState != null &&
        GlassRefractionSettings.enabled && isGlassLayerFallbackSupported() &&
        (agslAvailable || Build.VERSION.SDK_INT <= Build.VERSION_CODES.R)
    // 没有 AGSL 但支持 RenderEffect 的设备（电视 API31、手机 API31/32）：
    // 把背景栅格化到低分辨率再高斯模糊，作为非视频页玻璃的底色。
    val useSampled = enabled && !staticGlass && hazeState != null &&
        GlassRefractionSettings.enabled && Build.VERSION.SDK_INT in
        (Build.VERSION_CODES.S..(Build.VERSION_CODES.TIRAMISU - 1))
    // 模糊：不满足折射/采样条件时退回 Haze 实时模糊
    val useBlur = enabled && !staticGlass && isLiquidBlurSupported() &&
        hazeState != null && !useRefraction && !useSampled
    val tintAlpha = if (onCanvas) glassBase.canvasTintAlpha else glassBase.tintAlpha

    Box(
        modifier = if (enabled) {
            modifier
                .shadow(
                    elevation = glassBase.shadowElevation,
                    shape = shape,
                    ambientColor = glassBase.shadowAmbient,
                    spotColor = glassBase.shadowSpot
                )
                .clip(shape)
        } else {
            modifier.clip(shape)
        }
    ) {
        if (enabled) {
            // 层 1：底色
            when {
                useRefraction -> GlassRefractionBackdrop(
                    hazeState = hazeState!!,
                    cornerRadiusPx = radiusPx,
                    tint = glassBase.tintColor,
                    tintAlpha = tintAlpha,
                    saturation = glassBase.saturation,
                    brightness = glassBase.brightness,
                    fallbackSolid = glassBase.fallbackSolid,
                    modifier = Modifier.matchParentSize()
                )

                // 无 AGSL 设备：低分辨率栅格化 + 高斯模糊（MarcoMovie 同款思路）
                useSampled -> GlassSampledBackdrop(
                    hazeState = hazeState!!,
                    cornerRadiusPx = radiusPx,
                    tint = glassBase.tintColor,
                    tintAlpha = tintAlpha,
                    saturation = glassBase.saturation,
                    brightness = glassBase.brightness,
                    fallbackSolid = glassBase.fallbackSolid,
                    modifier = Modifier.matchParentSize()
                )

                useBlur -> Box(
                    modifier = Modifier
                        .matchParentSize()
                        .hazeEffect(state = hazeState!!) {
                            // 小半径：保住背景结构，玻璃后要能看出「有东西」
                            blurRadius = glassBase.blurRadius
                            noiseFactor = 0.02f
                            tints = listOf(HazeTint(glassBase.tintColor.copy(alpha = tintAlpha)))
                            // SurfaceView 等无法采样的区域以深色兜底
                            backgroundColor = glassBase.fallbackSolid
                            fallbackTint = HazeTint(glassBase.fallbackSolid)
                        }
                )

                else -> Box(
                    modifier = Modifier
                        .matchParentSize()
                        .background(glassBase.frostBrush)
                )
            }
            // 层 2：顶部光泽（很淡，防止洗白）
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .background(glassBase.glossBrush)
            )
            // 层 3：厚度阴影 + 镜面双描边（内阴影/边缘高光都画在同一层，保证在内容之下）
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .drawBehind {
                        drawGlassDepth(size = size, radiusPx = radiusPx, base = glassBase)
                        drawGlassEdges(
                            size = size,
                            radiusPx = radiusPx,
                            base = glassBase,
                            borderTint = glassBase.borderTint ?: tvPalette.glassBorder
                        )
                    }
            )
        } else {
            Box(modifier = Modifier.matchParentSize().background(fallbackColor, shape))
        }
        content()
    }
}

/** 玻璃材质参数（按明暗主题区分） */
private class GlassBase(
    /** 折射着色器/模糊染色基色 */
    val tintColor: Color,
    /** 静态/对话框场景的染色不透明度 */
    val tintAlpha: Float,
    /** 画布模式下的染色不透明度（略轻，透出画布光斑） */
    val canvasTintAlpha: Float,
    val saturation: Float,
    val brightness: Float,
    val fallbackSolid: Color,
    val blurRadius: Dp,
    val frostBrush: Brush,
    val glossBrush: Brush,
    val shadowElevation: Dp,
    val shadowAmbient: Color,
    val shadowSpot: Color,
    val borderTop: Float,
    val borderMid: Float,
    val borderBottom: Float,
    val innerHighlight: Float,
    /** 顶部内阴影强度：面板上沿向下的暗带，模拟玻璃被边框遮挡的厚度 */
    val innerTopShadow: Float,
    /** 底部内阴影强度：下沿向上的暗带，把面板"压"在视频上 */
    val innerBottomShadow: Float,
    /** 顶部内侧细高光线强度：玻璃厚度的第二道反光 */
    val innerTopSheen: Float,
    /** 主描边线宽：大屏上 1dp 描边的侧边会被抗锯齿摊薄，overlay 用略粗的线保证轮廓可辨 */
    val edgeWidth: Dp = 1.dp,
    /** 描边基色：null 表示按主题取 palette 的 effect.glass_border */
    val borderTint: Color? = null
)

/**
 * 深色主题：Glasswork 式暗色压暗玻璃。
 *
 * 旧实现用白 20% tint + 白霜层 20/15/12% + 白 gloss 14%，叠在深色页底上把行底抬到
 * #7D8086 量级，白字只有 3.8~4.0:1，观感发灰发奶。这里改为 #1E1E22 压暗：
 * 背景色彩保留、亮度降 0.82、饱和度提 1.6，文字对比反而更稳。
 */
private val DarkGlass = GlassBase(
    tintColor = Color(0xFF1E1E22),
    tintAlpha = 0.30f,
    canvasTintAlpha = 0.26f,
    saturation = 1.6f,
    brightness = 0.82f,
    fallbackSolid = Color(0xFF1E1E22),
    blurRadius = 3.dp,
    frostBrush = Brush.verticalGradient(
        listOf(Color(0x662B303A), Color(0x571E1E22), Color(0x5C14161C))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.07f),
        0.35f to Color.White.copy(alpha = 0.025f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.05f)
    ),
    shadowElevation = 10.dp,
    shadowAmbient = Color(0x33000000),
    shadowSpot = Color(0x4D000000),
    borderTop = 0.46f, borderMid = 0.08f, borderBottom = 0.18f,
    innerHighlight = 0.20f,
    innerTopShadow = 0.12f, innerBottomShadow = 0.14f, innerTopSheen = 0.10f
)

/** 播放器覆盖层专用：暗色玻璃（覆盖条上多为白色文字，亮玻璃会让白字不可读） */
private val OverlayGlass = GlassBase(
    tintColor = Color(0xFF0D1016),
    tintAlpha = 0.62f,
    canvasTintAlpha = 0.62f,
    saturation = 1.35f,
    brightness = 0.78f,
    fallbackSolid = Color(0xFF0D1016),
    blurRadius = 3.dp,
    // 视频是 SurfaceView（硬件合成层）无法被采样做背景模糊 —— 霜层必须足够厚。
    // 压在视频上的玻璃按需求保持半透观感（不做背景采集），材质感交给边缘 bevel /
    // 内顶高光 / 内阴影 / 投影，不靠把面板做"实"。
    frostBrush = Brush.verticalGradient(
        listOf(Color(0xA60D1016), Color(0x8F111922), Color(0x80131A20))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.12f),
        0.35f to Color.White.copy(alpha = 0.04f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.10f)
    ),
    shadowElevation = 14.dp,
    shadowAmbient = Color(0x40000000),
    shadowSpot = Color(0x59000000),
    borderTop = 0.52f, borderMid = 0.14f, borderBottom = 0.24f,
    innerHighlight = 0.24f,
    innerTopShadow = 0.16f, innerBottomShadow = 0.22f, innerTopSheen = 0.14f,
    edgeWidth = 1.3.dp
)

/** 浅色主题：薄白玻璃 + 阴影浮起 + 深色描边可辨 */
private val LightGlass = GlassBase(
    tintColor = Color.White,
    tintAlpha = 0.16f,
    canvasTintAlpha = 0.12f,
    saturation = 1.8f,
    brightness = 1.04f,
    fallbackSolid = Color(0xFFE8EAF0),
    blurRadius = 3.dp,
    frostBrush = Brush.verticalGradient(
        listOf(Color(0xBAFFFFFF), Color(0xA3FFFFFF), Color(0x99FFFFFF))
    ),
    glossBrush = Brush.verticalGradient(
        0f to Color.White.copy(alpha = 0.22f),
        0.35f to Color.White.copy(alpha = 0.06f),
        0.7f to Color.Transparent,
        1f to Color.Black.copy(alpha = 0.03f)
    ),
    shadowElevation = 8.dp,
    shadowAmbient = Color(0x1F000000),
    shadowSpot = Color(0x33000000),
    // 白底上白描边不可见，改用深灰蓝提供轮廓
    borderTop = 0.26f, borderMid = 0.10f, borderBottom = 0.16f,
    innerHighlight = 0.30f,
    innerTopShadow = 0.06f, innerBottomShadow = 0.08f, innerTopSheen = 0.18f
)

/**
 * 玻璃厚度层：顶部/底部内阴影 + 内侧细高光线。
 *
 * 电视端视频走 SurfaceView，玻璃拿不到背景采样，材质感只能靠这三层静态明暗
 * 关系堆出来：上沿被边框遮住 → 暗带；下沿贴着视频 → 更暗的收边；再补一条
 * 缩进的高光线表示玻璃厚度。全部画在内容之下，不影响文字对比度。
 */
private fun DrawScope.drawGlassDepth(
    size: Size,
    radiusPx: Float,
    base: GlassBase
) {
    // 顶部内阴影：从面板上沿向下快速衰减的暗带
    val topBand = (size.height * 0.35f).coerceAtMost(18.dp.toPx())
    if (base.innerTopShadow > 0f && topBand > 1f) {
        drawRect(
            brush = Brush.verticalGradient(
                0f to Color.Black.copy(alpha = base.innerTopShadow),
                0.30f to Color.Black.copy(alpha = base.innerTopShadow * 0.35f),
                1f to Color.Transparent,
                startY = 0f,
                endY = topBand
            ),
            topLeft = Offset.Zero,
            size = Size(size.width, topBand)
        )
    }
    // 底部内阴影：把面板"压"在视频上，避免下沿发飘
    val bottomBand = (size.height * 0.30f).coerceAtMost(14.dp.toPx())
    if (base.innerBottomShadow > 0f && bottomBand > 1f) {
        drawRect(
            brush = Brush.verticalGradient(
                0f to Color.Transparent,
                0.70f to Color.Black.copy(alpha = base.innerBottomShadow * 0.35f),
                1f to Color.Black.copy(alpha = base.innerBottomShadow),
                startY = size.height - bottomBand,
                endY = size.height
            ),
            topLeft = Offset(0f, size.height - bottomBand),
            size = Size(size.width, bottomBand)
        )
    }
    // 内侧细高光线：缩进 2.5dp，只在顶部约 1/3 高度内可见
    val inset = 2.5.dp.toPx()
    if (base.innerTopSheen > 0f && size.width > inset * 2 && size.height > inset * 2) {
        drawRoundRect(
            brush = Brush.verticalGradient(
                0f to Color.White.copy(alpha = base.innerTopSheen),
                0.34f to Color.Transparent,
                1f to Color.Transparent
            ),
            topLeft = Offset(inset, inset),
            size = Size(size.width - inset * 2, size.height - inset * 2),
            cornerRadius = CornerRadius((radiusPx - inset).coerceAtLeast(0f)),
            style = Stroke(width = 1.dp.toPx())
        )
    }
}

/**
 * 镜面双描边：外圈纵向由亮到暗再回亮（玻璃边缘受光），
 * 内圈缩进 1.5dp，只保留顶部高光，模拟玻璃厚度。
 */
private fun DrawScope.drawGlassEdges(
    size: Size,
    radiusPx: Float,
    base: GlassBase,
    borderTint: Color
) {
    // palette 里的描边色自带 alpha（如 0x4DFFFFFF），这里先归一化再按位置施加 alpha。
    // 否则两次 alpha 相乘后电视上的 1dp 描边只剩约 0.14，几乎完全看不见。
    val tint = borderTint.copy(alpha = 1f)
    val radius = CornerRadius(radiusPx, radiusPx)
    // 外圈柔光：3dp 宽的低 alpha 描边，给边缘一层受光的高光晕
    drawRoundRect(
        brush = Brush.verticalGradient(
            0f to tint.copy(alpha = base.borderTop * 0.18f),
            0.5f to Color.Transparent,
            1f to tint.copy(alpha = base.borderBottom * 0.12f)
        ),
        cornerRadius = radius,
        style = Stroke(width = 3.dp.toPx())
    )
    // 主描边：纵向渐变，顶边最亮、两侧中段最暗、底边略回亮（受光 bevel）
    drawRoundRect(
        brush = Brush.verticalGradient(
            0f to tint.copy(alpha = base.borderTop),
            0.42f to tint.copy(alpha = base.borderMid),
            0.82f to tint.copy(alpha = base.borderMid * 1.2f),
            1f to tint.copy(alpha = base.borderBottom)
        ),
        cornerRadius = radius,
        style = Stroke(width = 1.dp.toPx())
    )
    val inset = 1.5.dp.toPx()
    if (size.width <= inset * 2 || size.height <= inset * 2) return
    drawRoundRect(
        brush = Brush.verticalGradient(
            0f to Color.White.copy(alpha = base.innerHighlight),
            0.4f to Color.Transparent,
            1f to Color.White.copy(alpha = base.innerHighlight * 0.25f)
        ),
        topLeft = Offset(inset, inset),
        size = Size(size.width - inset * 2, size.height - inset * 2),
        cornerRadius = CornerRadius(
            (radiusPx - inset).coerceAtLeast(0f),
            (radiusPx - inset).coerceAtLeast(0f)
        ),
        style = Stroke(width = 1.dp.toPx())
    )
}

/** 低分辨率采样最长边：与 MarcoMovie 的 384px 烘焙档一致 */
private const val SAMPLED_MAX_EDGE = 384f

/**
 * 无 AGSL 设备（电视 API31 / 手机 API31~32）的玻璃底色：
 * 把背景内容层栅格化到低分辨率，套 RenderEffect 高斯模糊，再放大回原尺寸。
 *
 * 两个关键修正（对照 MarcoMovie 的缺陷）：
 * 1. 每次绘制都重新录制，内容/页面/分组一变，下一帧就是新图，不会残留上一次的填充；
 * 2. 滚动或切页时（连续重绘）采样比例降到 0.28 并限制最长边 384px，控制开销；
 *    连续 240ms 没有新的绘制后判定为静止，自动补一张全分辨率清晰版。
 */
@Composable
internal fun GlassSampledBackdrop(
    hazeState: HazeState,
    cornerRadiusPx: Float,
    tint: Color,
    tintAlpha: Float,
    saturation: Float,
    brightness: Float,
    fallbackSolid: Color,
    modifier: Modifier = Modifier
) {
    val layer = rememberGraphicsLayer()
    var origin by remember { mutableStateOf(Offset.Zero) }
    val density = LocalDensity.current.density
    // 每次绘制 +1，用于判断内容是否仍在变化（滚动/切页）；不参与快照，避免绘制期写状态
    val drawCount = remember { intArrayOf(0) }
    var settled by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        var last = -1
        var stableTicks = 0
        while (true) {
            kotlinx.coroutines.delay(120)
            val c = drawCount[0]
            if (c == last) stableTicks++ else { stableTicks = 0; last = c }
            val want = stableTicks >= 2
            if (want != settled) settled = want
        }
    }

    Box(
        modifier = modifier
            .onGloballyPositioned { origin = it.positionOnScreen() }
            .drawBehind {
                drawCount[0]++
                val longest = max(size.width, size.height).coerceAtLeast(1f)
                val sampleScale = if (settled) 1f else {
                    min(0.28f, SAMPLED_MAX_EDGE / longest)
                }
                val w = (size.width * sampleScale).roundToInt().coerceAtLeast(1)
                val h = (size.height * sampleScale).roundToInt().coerceAtLeast(1)
                layer.record(this, layoutDirection, IntSize(w, h)) {
                    drawRect(fallbackSolid)
                    scale(scale = sampleScale, pivot = Offset.Zero) {
                        translate(-origin.x, -origin.y) {
                            hazeState.areas.forEach { area ->
                                val content = area.contentLayer ?: return@forEach
                                if (content.isReleased) return@forEach
                                if (content.size.width <= 0 || content.size.height <= 0) return@forEach
                                translate(area.positionOnScreen.x, area.positionOnScreen.y) {
                                    drawLayer(content)
                                }
                            }
                        }
                    }
                }
                // 模糊在高斯近似下略大于采样像素，静止时用更大半径把低清纹理抹平
                val blurPx = (if (settled) 16f else 10f) * density * sampleScale
                layer.renderEffect = android.graphics.RenderEffect
                    .createBlurEffect(blurPx, blurPx, android.graphics.Shader.TileMode.CLAMP)
                    .asComposeRenderEffect()
                val inv = 1f / sampleScale
                scale(scale = inv, pivot = Offset.Zero) { drawLayer(layer) }
                // 采样路径不逐像素调饱和/亮度：用染色 + 上下渐变近似同一材质
                drawRect(tint.copy(alpha = (tintAlpha * 1.1f).coerceAtMost(1f)))
                drawRect(
                    brush = Brush.verticalGradient(
                        0f to Color.White.copy(alpha = 0.06f),
                        0.45f to Color.Transparent,
                        1f to Color.Black.copy(alpha = 0.10f)
                    )
                )
            }
    )
}

/** 记忆化 HazeState（根布局用） */
@Composable
fun rememberLiquidHazeState(): HazeState = androidx.compose.runtime.remember { HazeState() }
