package com.iptv.scanner.editor.pro.ui

import com.iptv.scanner.editor.pro.ui.theme.PaletteTokens
import com.iptv.scanner.editor.pro.ui.theme.TvColors

/**
 * 当前生效的跨端配色 token 快捷入口。
 *
 * UI 层（`com.iptv.scanner.editor.pro.ui` 包内）直接用 [tvPalette] 取色，
 * 避免每个文件都写一遍 `TvColors.p`；色值本身仍来自唯一的 `themes/palette.json`。
 */
internal val tvPalette: PaletteTokens
    get() = TvColors.p
