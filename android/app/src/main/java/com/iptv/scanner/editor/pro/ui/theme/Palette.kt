package com.iptv.scanner.editor.pro.ui.theme

import android.content.Context
import android.util.Log
import androidx.compose.ui.graphics.Color
import org.json.JSONObject

/**
 * 跨端配色 token（单一真源：仓库根 `themes/palette.json`）。
 *
 * 设计约束与 PC 端 `ui/palette.py` 保持一致：
 * 1. 色值只写在 `themes/palette.json`，PC（QSS/绘制）与 Android（Compose）共用语义 token。
 * 2. 文件缺失、JSON 非法、单个 token 缺失或取值非法时，回退到本文件的 [DEFAULT_DARK]/[DEFAULT_LIGHT]
 *    （数值与 palette.json 同步），避免把界面渲染成全黑。
 * 3. 打包时由 gradle `assets.srcDirs` 把仓库根 `themes/` 挂进 assets，运行时读取 `assets/palette.json`，
 *    不复制、不另存一份，杜绝两份配色各自演化。
 *
 * 非 Composable 代码（默认参数、draw 回调、工具函数）可直接用 [TvColors.p] 读取当前生效配色。
 */
data class PaletteTokens(
    val window: Color,
    val base: Color,
    val baseAlt: Color,
    val raised: Color,
    val high: Color,
    val player: Color,
    val playerPlaceholder: Color,
    val overlay: Color,
    val tooltip: Color,

    val textPrimary: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val textDisabled: Color,
    val textInverse: Color,
    val textLink: Color,
    val textPlaceholder: Color,
    val textTooltip: Color,

    val borderDefault: Color,
    val borderStrong: Color,
    val borderThin: Color,
    val borderSubtle: Color,
    val borderHighlightLight: Color,
    val borderHighlightDark: Color,
    val borderFrosted: Color,
    val borderFrostedMid: Color,
    val borderFrostedStrong: Color,

    val panelBackground: Color,
    val panelTextPrimary: Color,
    val panelTextSecondary: Color,
    val panelTextDisabled: Color,
    val panelTextHint: Color,
    val panelControlBackground: Color,
    val panelControlBackgroundAlt: Color,
    val panelDivider: Color,

    val accentBase: Color,
    val accentHover: Color,
    val accentPressed: Color,
    val accentOn: Color,
    val focusIndicator: Color,
    val focusRing: Color,

    val selectionBackground: Color,
    val selectionBackgroundStrong: Color,
    val selectionText: Color,
    val selectionTextStrong: Color,

    val success: Color,
    val warning: Color,
    val danger: Color,
    val dangerSoft: Color,
    val dangerBackground: Color,
    val info: Color,
    val favorite: Color,
    val favoriteBackground: Color,
    val favoriteBorder: Color,

    val sliderTrack: Color,
    val sliderVolumeTrack: Color,
    val sliderFill: Color,
    val sliderHandle: Color,
    val sliderCache: Color,

    val osdText: Color,
    val osdBorder: Color,
    val osdShadow: Color,

    val shadowLight: Color,
    val shadowDark: Color,
    val shadowSubtle: Color
)

/** 内置回退值（与 themes/palette.json 的 dark 模式一致）。 */
internal val DEFAULT_DARK = PaletteTokens(
    window = Color(0xFF000000),
    base = Color(0xFF1A1A1A),
    baseAlt = Color(0xFF2A2A2A),
    raised = Color(0xFF3A3A3A),
    high = Color(0xFF444444),
    player = Color(0xFF1A1A1A),
    playerPlaceholder = Color(0xFF1A1A1A),
    overlay = Color(0x8C000000),
    tooltip = Color(0xFF2A2A2A),

    textPrimary = Color(0xFFFFFFFF),
    textSecondary = Color(0xFFAAAAAA),
    textTertiary = Color(0xFFC8C8C8),
    textDisabled = Color(0xFF8A8A8A),
    textInverse = Color(0xFF000000),
    textLink = Color(0xFF6A9EFF),
    textPlaceholder = Color(0xFFAAAAAA),
    textTooltip = Color(0xFFF0F0F0),

    borderDefault = Color(0xFF555555),
    borderStrong = Color(0xFF666666),
    borderThin = Color(0x14FFFFFF),
    borderSubtle = Color(0x1AFFFFFF),
    borderHighlightLight = Color(0x26FFFFFF),
    borderHighlightDark = Color(0x80000000),
    borderFrosted = Color(0x1AFFFFFF),
    borderFrostedMid = Color(0x26FFFFFF),
    borderFrostedStrong = Color(0x33FFFFFF),

    panelBackground = Color(0xFF2A2A2A),
    panelTextPrimary = Color(0xFFFFFFFF),
    panelTextSecondary = Color(0xFFAAAAAA),
    panelTextDisabled = Color(0xFF8A8A8A),
    panelTextHint = Color(0xFFC8C8C8),
    panelControlBackground = Color(0xE63C3C3C),
    panelControlBackgroundAlt = Color(0xCC2D2D2D),
    panelDivider = Color(0xFF555555),

    accentBase = Color(0xFF4A7EFF),
    accentHover = Color(0xFF3A6EFF),
    accentPressed = Color(0xFF2A5EFF),
    accentOn = Color(0xFFFFFFFF),
    focusIndicator = Color(0xFF6A9EFF),
    focusRing = Color(0x4DFFFFFF),

    selectionBackground = Color(0xFF2A3A5A),
    selectionBackgroundStrong = Color(0xFF4A7EFF),
    selectionText = Color(0xFF6A9EFF),
    selectionTextStrong = Color(0xFFFFFFFF),

    success = Color(0xFF4CAF50),
    warning = Color(0xFFFF9800),
    danger = Color(0xFFF44336),
    dangerSoft = Color(0xFFFF6464),
    dangerBackground = Color(0xFF3A1A1A),
    info = Color(0xFF2196F3),
    favorite = Color(0xFFFFD700),
    favoriteBackground = Color(0x1FFFD700),
    favoriteBorder = Color(0x80FFD700),

    sliderTrack = Color(0xFF555555),
    sliderVolumeTrack = Color(0xFF444444),
    sliderFill = Color(0xFF6A9EFF),
    sliderHandle = Color(0xFFFFFFFF),
    sliderCache = Color(0x666A9EFF),

    osdText = Color(0xFFFFFFFF),
    osdBorder = Color(0xFF000000),
    osdShadow = Color(0xFF000000),

    shadowLight = Color(0x0DFFFFFF),
    shadowDark = Color(0x66000000),
    shadowSubtle = Color(0x4D000000)
)

/** 内置回退值（与 themes/palette.json 的 light 模式一致）。 */
internal val DEFAULT_LIGHT = PaletteTokens(
    window = Color(0xFFF0F0F0),
    base = Color(0xFFFFFFFF),
    baseAlt = Color(0xFFE8E8E8),
    raised = Color(0xFFD0D0D0),
    high = Color(0xFFE0E0E0),
    player = Color(0xFFE0E0E0),
    playerPlaceholder = Color(0xFFE0E0E0),
    overlay = Color(0x59000000),
    tooltip = Color(0xFFFFFFFF),

    textPrimary = Color(0xFF333333),
    textSecondary = Color(0xFF555555),
    textTertiary = Color(0xFF666666),
    textDisabled = Color(0xFF767676),
    textInverse = Color(0xFFFFFFFF),
    textLink = Color(0xFF2A6EFF),
    textPlaceholder = Color(0xFF767676),
    textTooltip = Color(0xFF333333),

    borderDefault = Color(0xFFC0C0C0),
    borderStrong = Color(0xFFA0A0A0),
    borderThin = Color(0x0F000000),
    borderSubtle = Color(0x14000000),
    borderHighlightLight = Color(0xCCFFFFFF),
    borderHighlightDark = Color(0x26000000),
    borderFrosted = Color(0x0F000000),
    borderFrostedMid = Color(0x1A000000),
    borderFrostedStrong = Color(0x1F000000),

    panelBackground = Color(0xFFFAFAFA),
    panelTextPrimary = Color(0xFF333333),
    panelTextSecondary = Color(0xFF555555),
    panelTextDisabled = Color(0xFF767676),
    panelTextHint = Color(0xFF666666),
    panelControlBackground = Color(0xE6C8C8C8),
    panelControlBackgroundAlt = Color(0xCCDCDCDC),
    panelDivider = Color(0xFFC0C0C0),

    accentBase = Color(0xFF2A6EFF),
    accentHover = Color(0xFF1A5EFF),
    accentPressed = Color(0xFF0A4EFF),
    accentOn = Color(0xFFFFFFFF),
    focusIndicator = Color(0xFF2A6EFF),
    focusRing = Color(0x33000000),

    selectionBackground = Color(0xFFCCE0FF),
    selectionBackgroundStrong = Color(0xFF2A6EFF),
    selectionText = Color(0xFF2A6EFF),
    selectionTextStrong = Color(0xFFFFFFFF),

    success = Color(0xFF4CAF50),
    warning = Color(0xFFFF9800),
    danger = Color(0xFFF44336),
    dangerSoft = Color(0xFFFF6464),
    dangerBackground = Color(0xFFFFDDDD),
    info = Color(0xFF2196F3),
    favorite = Color(0xFFFFD700),
    favoriteBackground = Color(0x1FFFD700),
    favoriteBorder = Color(0x80FFD700),

    sliderTrack = Color(0xFFC0C0C0),
    sliderVolumeTrack = Color(0xFFD0D0D0),
    sliderFill = Color(0xFF2A6EFF),
    sliderHandle = Color(0xFF333333),
    sliderCache = Color(0x592A6EFF),

    osdText = Color(0xFF1A1A1A),
    osdBorder = Color(0xFFFFFFFF),
    osdShadow = Color(0xFF808080),

    shadowLight = Color(0xCCFFFFFF),
    shadowDark = Color(0x1F000000),
    shadowSubtle = Color(0x14000000)
)

/**
 * 当前生效配色（Compose 之外的代码也可读）。
 *
 * [IptvTheme] 在每次重组时刷新 [dark]/[light]/[isDark]；主题切换会触发整棵
 * Compose 子树重组，因此读取方总能拿到新值。
 */
object TvColors {
    @Volatile
    var isDark: Boolean = true

    @Volatile
    var dark: PaletteTokens = DEFAULT_DARK

    @Volatile
    var light: PaletteTokens = DEFAULT_LIGHT

    val p: PaletteTokens
        get() = if (isDark) dark else light
}

/** 从 assets/palette.json 加载配色（只读一次，失败回退内置默认值）。 */
object PaletteLoader {
    private const val TAG = "Palette"
    private const val ASSET_NAME = "palette.json"

    @Volatile
    private var loaded = false

    @Volatile
    private var darkTokens: PaletteTokens = DEFAULT_DARK

    @Volatile
    private var lightTokens: PaletteTokens = DEFAULT_LIGHT

    fun ensureLoaded(context: Context) {
        if (loaded) return
        synchronized(this) {
            if (loaded) return
            try {
                val text = context.assets.open(ASSET_NAME).bufferedReader().use { it.readText() }
                val root = JSONObject(text)
                val modes = root.optJSONObject("modes")
                if (modes != null) {
                    modes.optJSONObject("dark")?.let { darkTokens = parseMode(it, DEFAULT_DARK) }
                    modes.optJSONObject("light")?.let { lightTokens = parseMode(it, DEFAULT_LIGHT) }
                } else {
                    Log.w(TAG, "palette.json 缺少 modes 对象，使用内置默认配色")
                }
            } catch (e: Exception) {
                // 未打包主题文件（例如单独构建 android 目录）时走内置默认值
                Log.w(TAG, "读取 assets/$ASSET_NAME 失败，使用内置默认配色: ${e.message}")
            }
            loaded = true
        }
    }

    fun dark(): PaletteTokens = darkTokens

    fun light(): PaletteTokens = lightTokens

    private fun parseMode(node: JSONObject, d: PaletteTokens): PaletteTokens {
        fun c(path: String, fallback: Color): Color {
            var cur: JSONObject = node
            val parts = path.split('.')
            for (i in 0 until parts.size - 1) {
                cur = cur.optJSONObject(parts[i]) ?: return fallback
            }
            val raw = cur.optString(parts.last(), "")
            return parseColor(raw, fallback)
        }
        return PaletteTokens(
            window = c("background.window", d.window),
            base = c("background.base", d.base),
            baseAlt = c("background.base_alt", d.baseAlt),
            raised = c("background.raised", d.raised),
            high = c("background.high", d.high),
            player = c("background.player", d.player),
            playerPlaceholder = c("background.player_placeholder", d.playerPlaceholder),
            overlay = c("background.overlay", d.overlay),
            tooltip = c("background.tooltip", d.tooltip),

            textPrimary = c("text.primary", d.textPrimary),
            textSecondary = c("text.secondary", d.textSecondary),
            textTertiary = c("text.tertiary", d.textTertiary),
            textDisabled = c("text.disabled", d.textDisabled),
            textInverse = c("text.inverse", d.textInverse),
            textLink = c("text.link", d.textLink),
            textPlaceholder = c("text.placeholder", d.textPlaceholder),
            textTooltip = c("text.tooltip", d.textTooltip),

            borderDefault = c("border.default", d.borderDefault),
            borderStrong = c("border.strong", d.borderStrong),
            borderThin = c("border.thin", d.borderThin),
            borderSubtle = c("border.subtle", d.borderSubtle),
            borderHighlightLight = c("border.highlight_light", d.borderHighlightLight),
            borderHighlightDark = c("border.highlight_dark", d.borderHighlightDark),
            borderFrosted = c("border.frosted", d.borderFrosted),
            borderFrostedMid = c("border.frosted_mid", d.borderFrostedMid),
            borderFrostedStrong = c("border.frosted_strong", d.borderFrostedStrong),

            panelBackground = c("panel.background", d.panelBackground),
            panelTextPrimary = c("panel.text_primary", d.panelTextPrimary),
            panelTextSecondary = c("panel.text_secondary", d.panelTextSecondary),
            panelTextDisabled = c("panel.text_disabled", d.panelTextDisabled),
            panelTextHint = c("panel.text_hint", d.panelTextHint),
            panelControlBackground = c("panel.control_background", d.panelControlBackground),
            panelControlBackgroundAlt = c("panel.control_background_alt", d.panelControlBackgroundAlt),
            panelDivider = c("panel.divider", d.panelDivider),

            accentBase = c("accent.base", d.accentBase),
            accentHover = c("accent.hover", d.accentHover),
            accentPressed = c("accent.pressed", d.accentPressed),
            accentOn = c("accent.on", d.accentOn),
            focusIndicator = c("focus.indicator", d.focusIndicator),
            focusRing = c("focus.ring", d.focusRing),

            selectionBackground = c("selection.background", d.selectionBackground),
            selectionBackgroundStrong = c("selection.background_strong", d.selectionBackgroundStrong),
            selectionText = c("selection.text", d.selectionText),
            selectionTextStrong = c("selection.text_strong", d.selectionTextStrong),

            success = c("state.success", d.success),
            warning = c("state.warning", d.warning),
            danger = c("state.danger", d.danger),
            dangerSoft = c("state.danger_soft", d.dangerSoft),
            dangerBackground = c("state.danger_background", d.dangerBackground),
            info = c("state.info", d.info),
            favorite = c("state.favorite", d.favorite),
            favoriteBackground = c("state.favorite_background", d.favoriteBackground),
            favoriteBorder = c("state.favorite_border", d.favoriteBorder),

            sliderTrack = c("slider.track", d.sliderTrack),
            sliderVolumeTrack = c("slider.volume_track", d.sliderVolumeTrack),
            sliderFill = c("slider.fill", d.sliderFill),
            sliderHandle = c("slider.handle", d.sliderHandle),
            sliderCache = c("slider.cache", d.sliderCache),

            osdText = c("osd.text", d.osdText),
            osdBorder = c("osd.border", d.osdBorder),
            osdShadow = c("osd.shadow", d.osdShadow),

            shadowLight = c("shadow.light", d.shadowLight),
            shadowDark = c("shadow.dark", d.shadowDark),
            shadowSubtle = c("shadow.subtle", d.shadowSubtle)
        )
    }

    /** 支持 #RGB / #RGBA / #RRGGBB / #AARRGGBB / rgb() / rgba()，非法值回退。 */
    private fun parseColor(raw: String?, fallback: Color): Color {
        val t = raw?.trim().orEmpty()
        if (t.isEmpty()) return fallback
        return try {
            when {
                t.startsWith("#") -> {
                    val hex = t.substring(1)
                    when (hex.length) {
                        3 -> Color(0xFF000000 or expand3(hex))
                        4 -> {
                            val a = hex.substring(3, 4).toInt(16)
                            Color(((a * 17).toLong() shl 24) or expand3(hex.substring(0, 3)))
                        }
                        6 -> Color(("FF$hex").toLong(16))
                        8 -> Color(hex.toLong(16))
                        else -> fallback
                    }
                }
                t.startsWith("rgb", ignoreCase = true) -> {
                    val body = t.substringAfter('(').substringBefore(')')
                    val parts = body.split(',')
                    if (parts.size < 3) return fallback
                    val r = parts[0].trim().toInt()
                    val g = parts[1].trim().toInt()
                    val b = parts[2].trim().toInt()
                    val a = if (parts.size >= 4) (parts[3].trim().toFloat() * 255f).toInt() else 255
                    Color(
                        red = r.coerceIn(0, 255),
                        green = g.coerceIn(0, 255),
                        blue = b.coerceIn(0, 255),
                        alpha = a.coerceIn(0, 255)
                    )
                }
                else -> fallback
            }
        } catch (e: Exception) {
            fallback
        }
    }

    private fun expand3(hex: String): Long {
        val r = hex[0].digitToInt(16) * 17
        val g = hex[1].digitToInt(16) * 17
        val b = hex[2].digitToInt(16) * 17
        return (r.toLong() shl 16) or (g.toLong() shl 8) or b.toLong()
    }
}
