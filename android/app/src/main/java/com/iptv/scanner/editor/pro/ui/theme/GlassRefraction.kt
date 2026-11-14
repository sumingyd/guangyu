package com.iptv.scanner.editor.pro.ui.theme

import android.graphics.RuntimeShader
import android.os.Build
import android.util.Log
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asComposeRenderEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionOnScreen
import androidx.compose.ui.unit.IntSize
import dev.chrisbanes.haze.HazeState
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * 液态玻璃的「边缘折射」开关。
 *
 * 全局状态而不是 CompositionLocal：玻璃组件分散在大量面板里，其中播放器/首页根布局
 * 由另一条改动线维护，避免为了传值去改根布局的层级。默认开启。
 */
object GlassRefractionSettings {
    var enabled by mutableStateOf(true)
}

/** Canvas 兜底最低 API：需要 GraphicsLayer 录制（API33+ 则在其上再套 AGSL） */
internal fun isGlassLayerFallbackSupported(): Boolean =
    Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q

private const val GLASS_TAG = "GlassRefraction"

/**
 * 玻璃折射底色：把 Haze 采样到的背景录制进一个 GraphicsLayer，
 * 通过 RenderEffect(RuntimeShader) 做「圆角距离场边缘弯折 + RGB 色散 + 饱和/亮度 + 染色」。
 *
 * 折射公式与 Glasswork 一致：
 * - rim = min(40dp, min(w,h)/3.5)
 * - 位移 = rim × 1.1 × clamp(1 - depth/rim, 0, 1)^2.6
 * - 三通道位移倍率 1.15 / 1.0 / 0.85（±15% 色散）
 *
 * 不支持 AGSL 时退化为 Canvas 回流：边缘环带内放大 6% 绘制背景，中间保持原样，
 * 保留「边缘有厚度」的观感，只是没有逐像素色散。
 */
@Composable
internal fun GlassRefractionBackdrop(
    hazeState: HazeState,
    cornerRadiusPx: Float,
    tint: androidx.compose.ui.graphics.Color,
    tintAlpha: Float,
    saturation: Float,
    brightness: Float,
    fallbackSolid: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier
) {
    val layer = rememberGraphicsLayer()
    val shader = rememberGlassShader()
    var origin by remember { mutableStateOf(Offset.Zero) }
    val density = androidx.compose.ui.platform.LocalDensity.current.density
    // 用数组做一次性日志标记，避免在绘制阶段写 Compose 状态触发重组
    val reported = remember { BooleanArray(1) }

    Box(
        modifier = modifier
            .onGloballyPositioned { origin = it.positionOnScreen() }
            .drawBehind {
                if (!reported[0]) {
                    reported[0] = true
                    val withLayer = hazeState.areas.count { it.contentLayer != null }
                    Log.d(
                        GLASS_TAG,
                        "折射绘制：areas=${hazeState.areas.size} 有内容层=$withLayer 着色器=${shader != null}"
                    )
                }
                val w = size.width.roundToInt().coerceAtLeast(1)
                val h = size.height.roundToInt().coerceAtLeast(1)
                layer.record(this, layoutDirection, IntSize(w, h)) {
                    // 采样不到的画面（SurfaceView / 空源）用深色兜底，避免出现黑洞
                    drawRect(fallbackSolid)
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

                if (shader != null) {
                    val rim = computeRimPx(size.width, size.height, cornerRadiusPx, density)
                    shader.setFloatUniform("uSize", size.width, size.height)
                    shader.setFloatUniform("uRadius", cornerRadiusPx)
                    shader.setFloatUniform("uRim", rim)
                    shader.setFloatUniform("uBlur", max(1f, 2f * density))
                    shader.setFloatUniform("uSaturation", saturation)
                    shader.setFloatUniform("uBrightness", brightness)
                    shader.setFloatUniform("uTint", tint.red, tint.green, tint.blue)
                    shader.setFloatUniform("uTintAlpha", tintAlpha)
                    layer.renderEffect = android.graphics.RenderEffect
                        .createRuntimeShaderEffect(shader, "uContent")
                        .asComposeRenderEffect()
                    drawLayer(layer)
                } else {
                    // Canvas 回流兜底（API 29~32）：环带内放大，中心保持原样
                    layer.renderEffect = null
                    val rim = computeRimPx(size.width, size.height, cornerRadiusPx, density)
                    clipPath(roundedPath(size.width, size.height, cornerRadiusPx)) {
                        scale(1.06f, pivot = center) { drawLayer(layer) }
                        clipPath(innerPath(size.width, size.height, cornerRadiusPx, rim)) {
                            drawLayer(layer)
                        }
                    }
                    // 兜底路径自己补染色与压暗
                    drawRect(
                        color = tint.copy(alpha = tintAlpha * 0.85f),
                        size = size
                    )
                }
            }
    )
}

private fun computeRimPx(w: Float, h: Float, radiusPx: Float, density: Float): Float {
    val maxRim = 40f * density
    val limited = min(w, h) / 3.5f
    return max(1f, min(maxRim, limited)).coerceAtMost(max(1f, min(w, h) / 2f))
}

private fun roundedPath(w: Float, h: Float, radiusPx: Float): Path {
    val p = Path()
    p.addRoundRect(
        androidx.compose.ui.geometry.RoundRect(
            left = 0f,
            top = 0f,
            right = w,
            bottom = h,
            radiusX = radiusPx,
            radiusY = radiusPx
        )
    )
    return p
}

private fun innerPath(w: Float, h: Float, radiusPx: Float, rim: Float): Path {
    val inset = rim.coerceAtMost(min(w, h) / 3f)
    val p = Path()
    p.addRoundRect(
        androidx.compose.ui.geometry.RoundRect(
            left = inset,
            top = inset,
            right = w - inset,
            bottom = h - inset,
            radiusX = (radiusPx - inset).coerceAtLeast(0f),
            radiusY = (radiusPx - inset).coerceAtLeast(0f)
        )
    )
    return p
}

/** 记忆化 AGSL RuntimeShader；编译失败返回 null 走 Canvas 兜底 */
@Composable
private fun rememberGlassShader(): RuntimeShader? {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return null
    return remember {
        runCatching { RuntimeShader(GLASS_AGSL) }
            .onSuccess { Log.d(GLASS_TAG, "AGSL 折射着色器编译成功") }
            .onFailure { Log.w(GLASS_TAG, "AGSL 折射着色器编译失败，回落 Canvas 回流", it) }
            .getOrNull()
    }
}

/**
 * Glasswork 折射板的 AGSL 移植。
 * 采样来自 `uniform shader uContent`（即本 layer 录制进去的背景）。
 */
private const val GLASS_AGSL = """
uniform shader uContent;
uniform float2 uSize;
uniform float uRadius;
uniform float uRim;
uniform float uBlur;
uniform float uSaturation;
uniform float uBrightness;
uniform float3 uTint;
uniform float uTintAlpha;

half4 sampleGlass(float2 p) {
    float sigma = max(uBlur, 0.5);
    half4 sum = uContent.eval(p);
    float total = 1.0;
    for (int i = 0; i < 8; i++) {
        float d = sigma * 2.2 * sqrt((float(i) + 0.5) / 8.0);
        float a = float(i) * 2.39996;
        float w = exp(-(d * d) / (2.0 * sigma * sigma));
        sum += uContent.eval(p + float2(cos(a), sin(a)) * d) * w;
        total += w;
    }
    return half4(float4(sum) / total);
}

half4 main(float2 coord) {
    float2 hs = uSize * 0.5;
    float2 local = coord - hs;
    float2 q = abs(local) - hs + uRadius;
    float dist = length(max(q, float2(0.0))) + min(max(q.x, q.y), 0.0) - uRadius;
    float depth = max(-dist, 0.0);
    float2 axis = abs(q.x) > abs(q.y) ? float2(1.0, 0.0) : float2(0.0, 1.0);
    float2 nrm = (q.x > 0.0 || q.y > 0.0) ? normalize(max(q, float2(0.0001))) : axis;
    float bend = uRim * 1.1 * pow(clamp(1.0 - depth / uRim, 0.0, 1.0), 2.6);
    float2 offset = -sign(local) * nrm * bend;

    half r = sampleGlass(coord + offset * 1.15).r;
    half g = sampleGlass(coord + offset).g;
    half b = sampleGlass(coord + offset * 0.85).b;

    float3 c = float3(r, g, b);
    float l = dot(c, float3(0.213, 0.715, 0.072));
    c = clamp((l + (c - l) * uSaturation) * uBrightness, 0.0, 1.0);
    c = mix(c, uTint, uTintAlpha);
    return half4(half3(c), 1.0);
}
"""
