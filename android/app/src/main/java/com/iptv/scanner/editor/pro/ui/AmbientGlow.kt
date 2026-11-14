package com.iptv.scanner.editor.pro.ui

import android.graphics.Bitmap
import android.graphics.Color as AndroidColor
import android.graphics.drawable.BitmapDrawable
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import coil.imageLoader
import coil.request.ImageRequest
import coil.request.SuccessResult

/**
 * 环境色柔光：从当前台标提取两个主色，压暗后作为首页背景光斑。
 *
 * 只解码 24x14 的缩略图采样，颜色按 URL 缓存；取不到台标时调用方回落到主题色。
 */
data class AmbientColors(val primary: Color, val secondary: Color)

private object AmbientColorCache {
    private const val MAX = 48
    private val cache = object : LinkedHashMap<String, AmbientColors>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, AmbientColors>?): Boolean =
            size > MAX
    }

    @Synchronized
    fun get(key: String): AmbientColors? = cache[key]

    @Synchronized
    fun put(key: String, value: AmbientColors) {
        cache[key] = value
    }
}

@Composable
fun rememberAmbientColors(logoUrl: String?): AmbientColors? {
    val context = LocalContext.current
    var colors by remember(logoUrl) { mutableStateOf<AmbientColors?>(null) }

    LaunchedEffect(logoUrl) {
        if (logoUrl.isNullOrBlank()) {
            colors = null
            return@LaunchedEffect
        }
        AmbientColorCache.get(logoUrl)?.let {
            colors = it
            return@LaunchedEffect
        }
        val request = ImageRequest.Builder(context)
            .data(logoUrl)
            .size(24, 14)
            .allowHardware(false)
            .build()
        val result = runCatching { context.imageLoader.execute(request) }.getOrNull()
        val bitmap = ((result as? SuccessResult)?.drawable as? BitmapDrawable)?.bitmap
        if (bitmap != null) {
            val sampled = sampleAmbientColors(bitmap)
            AmbientColorCache.put(logoUrl, sampled)
            colors = sampled
        }
    }
    return colors
}

/** 按饱和度平方加权取两个主色，再压到低饱和、固定明度，避免抢画面。 */
fun sampleAmbientColors(bitmap: Bitmap): AmbientColors {
    val bins = arrayOfNulls<DoubleArray>(12)
    val weights = DoubleArray(12)
    val hsv = FloatArray(3)
    val stepX = (bitmap.width / 24).coerceAtLeast(1)
    val stepY = (bitmap.height / 14).coerceAtLeast(1)
    var y = 0
    while (y < bitmap.height) {
        var x = 0
        while (x < bitmap.width) {
            val pixel = bitmap.getPixel(x, y)
            if (AndroidColor.alpha(pixel) > 32) {
                AndroidColor.colorToHSV(pixel, hsv)
                if (hsv[1] > 0.12f && hsv[2] > 0.12f) {
                    val bin = ((hsv[0] / 30f).toInt()).coerceIn(0, 11)
                    val weight = (hsv[1] * hsv[1] * hsv[2]).toDouble()
                    val acc = bins[bin] ?: DoubleArray(3).also { bins[bin] = it }
                    acc[0] += AndroidColor.red(pixel) * weight
                    acc[1] += AndroidColor.green(pixel) * weight
                    acc[2] += AndroidColor.blue(pixel) * weight
                    weights[bin] += weight
                }
            }
            x += stepX
        }
        y += stepY
    }

    val order = (0 until 12)
        .filter { weights[it] > 0.0 }
        .sortedByDescending { weights[it] }
    if (order.isEmpty()) {
        val fallback = Color(0xFF3A4A6B)
        return AmbientColors(fallback, fallback)
    }

    fun colorAt(bin: Int): Color {
        val w = weights[bin].coerceAtLeast(1e-6)
        val r = (bins[bin]!![0] / w).toInt().coerceIn(0, 255)
        val g = (bins[bin]!![1] / w).toInt().coerceIn(0, 255)
        val b = (bins[bin]!![2] / w).toInt().coerceIn(0, 255)
        return soften(AndroidColor.rgb(r, g, b))
    }

    val first = colorAt(order[0])
    val second = if (order.size > 1) colorAt(order[1]) else first
    return AmbientColors(first, second)
}

private fun soften(rgb: Int): Color {
    val hsv = FloatArray(3)
    AndroidColor.colorToHSV(rgb, hsv)
    hsv[1] = hsv[1].coerceAtMost(0.48f)
    hsv[2] = 0.25f
    val softened = AndroidColor.HSVToColor(hsv)
    // 保留一份原始色相给 Compose，明度由调用方按主题透明度再抬
    return Color(softened).copy(alpha = 1f)
}
