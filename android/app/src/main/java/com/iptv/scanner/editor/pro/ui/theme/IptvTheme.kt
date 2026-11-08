package com.iptv.scanner.editor.pro.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.draw.clip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.unit.dp
import com.iptv.scanner.editor.pro.ui.AptvAccent
import com.iptv.scanner.editor.pro.ui.LocalAptvStyle

/**
 * IPTV 应用主题。支持深色/浅色/跟随系统三种模式。
 *
 * 所有色值都来自跨端单一真源 `themes/palette.json`（见 [PaletteTokens]），
 * 本文件只负责把语义 token 映射到 MaterialTheme 的槽位，不再保存色值。
 *
 * - primary → accent.base
 * - background/surface/surfaceVariant → background.window/base/base_alt
 * - onSurface/onSurfaceVariant → text.primary/secondary
 * - error/tertiary/secondary → state.danger/warning/info
 */

private fun darkScheme(p: PaletteTokens) = darkColorScheme(
    primary = p.accentBase,
    onPrimary = p.accentOn,
    primaryContainer = p.accentPressed,
    onPrimaryContainer = p.accentOn,
    secondary = p.info,
    onSecondary = p.accentOn,
    secondaryContainer = p.baseAlt,
    onSecondaryContainer = p.textPrimary,
    tertiary = p.warning,
    onTertiary = p.accentOn,
    background = p.window,
    onBackground = p.textPrimary,
    surface = p.base,
    onSurface = p.textPrimary,
    surfaceVariant = p.baseAlt,
    onSurfaceVariant = p.textSecondary,
    error = p.danger,
    onError = p.accentOn,
    outline = p.borderDefault,
    outlineVariant = p.borderStrong,
)

private fun lightScheme(p: PaletteTokens) = lightColorScheme(
    primary = p.accentBase,
    onPrimary = p.accentOn,
    primaryContainer = p.accentPressed,
    onPrimaryContainer = p.accentOn,
    secondary = p.info,
    onSecondary = p.accentOn,
    secondaryContainer = p.baseAlt,
    onSecondaryContainer = p.textPrimary,
    tertiary = p.warning,
    onTertiary = p.accentOn,
    background = p.window,
    onBackground = p.textPrimary,
    surface = p.base,
    onSurface = p.textPrimary,
    surfaceVariant = p.baseAlt,
    onSurfaceVariant = p.textSecondary,
    error = p.danger,
    onError = p.accentOn,
    outline = p.borderDefault,
    outlineVariant = p.borderStrong,
)

/**
 * 应用主题入口。
 * @param themeMode "dark"=深色, "light"=浅色, "system"=跟随系统
 */
@Composable
fun IptvTheme(
    themeMode: String = "dark",
    content: @Composable () -> Unit
) {
    val useDark = when (themeMode) {
        "light" -> false
        "system" -> isSystemInDarkTheme()
        else -> true  // "dark" 或默认
    }
    // 读取 assets/palette.json（仅首次），并同步给非 Composable 代码使用的 TvColors
    val context = androidx.compose.ui.platform.LocalContext.current
    androidx.compose.runtime.remember(context) {
        PaletteLoader.ensureLoaded(context.applicationContext)
    }
    TvColors.dark = PaletteLoader.dark()
    TvColors.light = PaletteLoader.light()
    TvColors.isDark = useDark
    MaterialTheme(
        colorScheme = if (useDark) darkScheme(TvColors.dark) else lightScheme(TvColors.light),
        content = content
    )
}

/**
 * 判断当前是否为深色主题。
 * 通过 surface 颜色的亮度判断（luminance < 0.5 = 深色）。
 */
@Composable
@ReadOnlyComposable
fun isDarkTheme(): Boolean {
    return MaterialTheme.colorScheme.surface.luminance() < 0.5f
}

/**
 * 横屏视频覆盖层面板（暗玻璃 overlayDark）专用主题。
 *
 * 这些面板悬浮在视频上，永远呈暗色玻璃 + 白字；但内部文字若用
 * MaterialTheme.colorScheme.onSurface 系，会在浅色主题下变黑/深灰，
 * 落在暗玻璃上几乎不可读。此 helper 强制文字色为白系，明暗主题通用。
 *
 * 同时提供 LocalDarkOverlay 标记：rememberPlayerOverlayColors 读取后
 * 直接返回白系配色（其浅色分支是硬编码黑字，colorScheme 覆盖管不到）。
 */
val LocalDarkOverlay = androidx.compose.runtime.staticCompositionLocalOf { false }

@Composable
fun DarkOverlayTheme(content: @Composable () -> Unit) {
    val scheme = MaterialTheme.colorScheme.copy(
        onSurface = Color(0xFFE9EDF4),
        onSurfaceVariant = Color(0xFF9AA4B2)
    )
    androidx.compose.runtime.CompositionLocalProvider(LocalDarkOverlay provides true) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

/**
 * 播放器控制层覆盖颜色 — 随主题自适应。
 *
 * 视频控制层叠在视频上方，需要遮罩保证对比度：
 * - 深色主题：深色半透明遮罩 + 白色图标/文字
 * - 浅色主题：浅色半透明遮罩 + 深色图标/文字
 * 强调色（进度条、激活态）在两种主题下统一使用蓝色。
 */
data class PlayerOverlayColors(
    val scrim: Color,           // 控制层半透明背景
    val topBarBg: Color,        // 顶部信息条背景
    val infoBarBg: Color,       // 竖屏信息栏背景
    val iconTint: Color,        // 图标默认颜色
    val iconTintActive: Color,  // 激活态图标颜色（如静音/锁定）
    val textPrimary: Color,     // 主文字色
    val textSecondary: Color,   // 次要文字色
    val accent: Color,          // 强调色（进度条/激活按钮）
    val trackInactive: Color,   // 进度条未激活轨道色
    val badgeBg: Color,         // 徽章背景色
    val badgeText: Color,       // 徽章文字色
    val divider: Color,         // 分隔线/边框色
)

/**
 * 获取当前主题下的播放器控制层颜色。
 */
@Composable
@ReadOnlyComposable
fun rememberPlayerOverlayColors(): PlayerOverlayColors {
    val p = if (isDarkTheme()) TvColors.dark else TvColors.light
    val aptv = LocalAptvStyle.current
    val accent = if (aptv) AptvAccent else p.accentBase
    // 暗玻璃覆盖层（底栏/侧栏/信息弹窗）：永远白字白图标。
    // 浅色主题的 panel.text_primary 是深色，落在暗玻璃上不可读，故强制用暗色模式的文字色。
    if (LocalDarkOverlay.current) {
        val dp = TvColors.dark
        return PlayerOverlayColors(
            scrim = dp.overlay,
            topBarBg = dp.panelControlBackground,
            infoBarBg = dp.panelControlBackgroundAlt,
            iconTint = dp.panelTextPrimary,
            iconTintActive = accent,
            textPrimary = dp.panelTextPrimary,
            textSecondary = dp.panelTextSecondary,
            accent = accent,
            trackInactive = dp.sliderTrack,
            badgeBg = accent.copy(alpha = 0.15f),
            badgeText = dp.panelTextPrimary,
            divider = dp.panelDivider,
        )
    }
    if (aptv) {
        return PlayerOverlayColors(
            scrim = p.overlay,
            topBarBg = MaterialTheme.colorScheme.surface,
            infoBarBg = MaterialTheme.colorScheme.surfaceVariant,
            iconTint = MaterialTheme.colorScheme.onSurface,
            iconTintActive = AptvAccent,
            textPrimary = MaterialTheme.colorScheme.onSurface,
            textSecondary = MaterialTheme.colorScheme.onSurfaceVariant,
            accent = AptvAccent,
            trackInactive = MaterialTheme.colorScheme.surfaceVariant,
            badgeBg = AptvAccent.copy(alpha = 0.12f),
            badgeText = AptvAccent,
            divider = MaterialTheme.colorScheme.outline,
        )
    }
    return PlayerOverlayColors(
        scrim = p.overlay,
        topBarBg = p.panelControlBackground,
        infoBarBg = p.panelControlBackgroundAlt,
        iconTint = p.panelTextPrimary,
        iconTintActive = accent,
        textPrimary = p.panelTextPrimary,
        textSecondary = p.panelTextSecondary,
        accent = accent,
        trackInactive = p.sliderTrack,
        badgeBg = accent.copy(alpha = 0.15f),
        badgeText = p.panelTextPrimary,
        divider = p.panelDivider,
    )
}

// -----------------------------------------------------------------
// 共享 UI 组件：玻璃态卡片、圆点进度条滑块、选中边框
// -----------------------------------------------------------------

/**
 * 玻璃态卡片：液态玻璃材质（Haze backdrop blur + 光泽 + 高光描边）
 * 跟随「液态玻璃」开关（LocalLiquidGlass）；关闭或降级时为实底卡片。
 * 用于替换所有硬编码的颜色块（如设置项背景、关于面板等）
 */
@Composable
fun GlassCard(
    modifier: Modifier = Modifier,
    cornerRadius: androidx.compose.ui.unit.Dp = 12.dp,
    content: @Composable () -> Unit
) {
    val oc = rememberPlayerOverlayColors()
    val liquidGlass = com.iptv.scanner.editor.pro.ui.LocalLiquidGlass.current
    val enabled = liquidGlass && isLiquidBlurSupported()
    Box(modifier = modifier) {
        LiquidGlassSurface(
            enabled = enabled,
            cornerRadius = cornerRadius,
            // 卡片/面板多出现在 Dialog 或自采样子树中，真模糊会输出黑块，统一用静态玻璃
            staticGlass = true,
            // 关闭/降级：保持原非模糊观感（topBarBg 85% 实底）
            fallbackColor = oc.topBarBg.copy(alpha = 0.85f)
        ) {
            content()
        }
    }
}

@Composable
fun GlassPanel(
    liquidGlass: Boolean,
    modifier: Modifier = Modifier,
    cornerRadius: androidx.compose.ui.unit.Dp = 10.dp,
    overlayDark: Boolean = false,
    content: @Composable () -> Unit
) {
    LiquidGlassSurface(
        enabled = liquidGlass && isLiquidBlurSupported(),
        cornerRadius = cornerRadius,
        staticGlass = true,
        overlayDark = overlayDark,
        fallbackColor = TvColors.p.panelBackground.copy(alpha = 0.96f),
        modifier = modifier
    ) {
        if (overlayDark) {
            // 暗玻璃面板文字强制白系：面板悬浮在视频上永远呈暗底，
            // 内部若用主题 onSurface 会在浅色主题下变黑字导致不可读
            DarkOverlayTheme { content() }
        } else {
            content()
        }
    }
}

/**
 * 选中状态边框：给已选择项加玻璃态边框效果
 */
@Composable
fun Modifier.selectedBorder(isSelected: Boolean): Modifier {
    if (!isSelected) return this
    val oc = rememberPlayerOverlayColors()
    return this.then(
        Modifier.border(
            width = 1.dp,
            color = oc.accent.copy(alpha = 0.50f),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
        )
    )
}

/**
 * 圆点进度条样式的 Slider
 */
@Composable
fun GlassSlider(
    value: Float,
    onValueChange: (Float) -> Unit,
    modifier: Modifier = Modifier,
    valueRange: ClosedFloatingPointRange<Float> = 0f..1f,
    enabled: Boolean = true
) {
    val oc = rememberPlayerOverlayColors()
    androidx.compose.material3.Slider(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier,
        valueRange = valueRange,
        enabled = enabled,
        colors = androidx.compose.material3.SliderDefaults.colors(
            thumbColor = oc.accent,
            activeTrackColor = oc.accent,
            inactiveTrackColor = oc.trackInactive,
            disabledThumbColor = oc.accent.copy(alpha = 0.5f),
            disabledActiveTrackColor = oc.accent.copy(alpha = 0.5f),
            disabledInactiveTrackColor = oc.trackInactive
        )
    )
}
