"""样式修饰器和装饰基础方法。"""
from ui.styles_base import StylesBase


class StylesDecorations(StylesBase):
    """样式修饰器和装饰基础方法。"""

    @classmethod
    def _style_modifier_flat(cls, colors, color_mode):
        return colors.copy()

    @classmethod
    def _style_modifier_neumorphic(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['shadow_light'] = 'rgba(100,100,160,0.5)'
            c['shadow_dark'] = 'rgba(0,0,0,0.7)'
            c['neumorphic_light'] = '#303055'
            c['neumorphic_dark'] = '#181830'
            c['window'] = '#1a1a2e'
            c['window_text'] = '#eaeaea'
            c['base'] = '#222240'
            c['alternate_base'] = '#28284a'
            c['button'] = '#28284a'
            c['light'] = '#303055'
            c['mid'] = '#3a3a60'
            c['dark'] = '#454570'
            c['highlight'] = '#2a2a50'
            c['highlighted_text'] = '#7c8aff'
            c['bright_text'] = '#eaeaea'
            c['link'] = '#7c8aff'
            c['link_visited'] = '#9580ff'
            c['tooltip_base'] = '#28284a'
            c['tooltip_text'] = '#eaeaea'
            c['placeholder'] = '#808090'
            c['accent'] = '#6b7bff'
            c['accent_hover'] = '#5b6bef'
            c['accent_pressed'] = '#4b5bdf'
            c['success'] = '#5fcf73'
            c['warning'] = '#ffaa70'
            c['error'] = '#ff6060'
            c['error_background'] = '#2a1a20'
            c['info'] = '#5090ff'
            c['table_header'] = '#28284a'
            c['table_header_gradient_start'] = '#303055'
            c['table_header_gradient_middle'] = '#28284a'
            c['table_header_gradient_end'] = '#202038'
            c['table_header_text'] = '#d0d0e0'
            c['table_header_hover'] = '#6b7bff'
            c['table_border'] = '#3a3a60'
            c['table_grid'] = '#303055'
            c['table_alternate'] = '#202038'
            c['table_hover'] = '#2a2a50'
            c['table_selection'] = '#5b6bef'
            c['player_background'] = '#16162a'
            c['player_panel'] = '#222240'
            c['player_panel_text'] = '#eaeaea'
            c['player_panel_secondary'] = '#888898'
            c['player_panel_disabled'] = '#585878'
            c['player_panel_hint'] = '#6a6a8a'
            c['player_button'] = 'rgba(40, 40, 74, 0.95)'
            c['player_combo'] = 'rgba(34, 34, 64, 0.9)'
            c['player_line'] = '#3a3a60'
            c['player_accent'] = '#7c8aff'
            c['player_slider_track'] = '#3a3a60'
            c['player_slider_fill'] = '#6b7bff'
            c['player_slider_handle'] = '#eaeaea'
            c['player_cache_bar'] = 'rgba(107, 123, 255, 0.35)'
            c['player_volume_track'] = '#303055'
            c['player_video_placeholder'] = '#16162a'
        else:
            c['shadow_light'] = 'rgba(255,255,255,0.95)'
            c['shadow_dark'] = 'rgba(163,177,198,0.7)'
            c['neumorphic_light'] = '#ecf1f9'
            c['neumorphic_dark'] = '#bec6d2'
            c['window'] = '#e0e5ec'
            c['window_text'] = '#44476a'
            c['base'] = '#e0e5ec'
            c['alternate_base'] = '#d1d9e6'
            c['button'] = '#d1d9e6'
            c['light'] = '#e0e5ec'
            c['mid'] = '#b8bec7'
            c['dark'] = '#a0a6b0'
            c['highlight'] = '#d6e4ff'
            c['highlighted_text'] = '#4a6eff'
            c['bright_text'] = '#44476a'
            c['link'] = '#4a6eff'
            c['link_visited'] = '#6a5eef'
            c['tooltip_base'] = '#e0e5ec'
            c['tooltip_text'] = '#44476a'
            c['placeholder'] = '#9ba4b5'
            c['accent'] = '#4a6eff'
            c['accent_hover'] = '#3a5eef'
            c['accent_pressed'] = '#2a4edf'
            c['success'] = '#4caf50'
            c['warning'] = '#ff9800'
            c['error'] = '#f44336'
            c['error_background'] = '#f5d0d0'
            c['info'] = '#2196f3'
            c['table_header'] = '#d1d9e6'
            c['table_header_gradient_start'] = '#e0e5ec'
            c['table_header_gradient_middle'] = '#d1d9e6'
            c['table_header_gradient_end'] = '#c8d0da'
            c['table_header_text'] = '#44476a'
            c['table_header_hover'] = '#4a6eff'
            c['table_border'] = '#b8bec7'
            c['table_grid'] = '#c8d0da'
            c['table_alternate'] = '#e8ecf2'
            c['table_hover'] = '#d6e4ff'
            c['table_selection'] = '#4a6eff'
            c['player_background'] = '#d1d9e6'
            c['player_panel'] = '#e0e5ec'
            c['player_panel_text'] = '#44476a'
            c['player_panel_secondary'] = '#5a5f7a'
            c['player_panel_disabled'] = '#8086a0'
            c['player_panel_hint'] = '#7a7f9a'
            c['player_button'] = 'rgba(209, 217, 230, 0.95)'
            c['player_combo'] = 'rgba(224, 229, 236, 0.9)'
            c['player_line'] = '#b8bec7'
            c['player_accent'] = '#4a6eff'
            c['player_slider_track'] = '#b8bec7'
            c['player_slider_fill'] = '#4a6eff'
            c['player_slider_handle'] = '#44476a'
            c['player_cache_bar'] = 'rgba(74, 110, 255, 0.3)'
            c['player_volume_track'] = '#c8d0da'
            c['player_video_placeholder'] = '#d1d9e6'
        return c

    @classmethod
    def _style_modifier_skeuomorphic(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['shadow_dark'] = 'rgba(0,0,0,0.6)'
            c['shadow_light'] = 'rgba(255,255,255,0.08)'
            c['neumorphic_light'] = '#383838'
            c['neumorphic_dark'] = '#080808'
            c['gradient_start'] = '#403830'
            c['gradient_end'] = '#2a2218'
            c['border_3d_light'] = 'rgba(255,200,150,0.12)'
            c['border_3d_dark'] = 'rgba(0,0,0,0.5)'
            c['accent'] = '#e8a040'
            c['accent_hover'] = '#d89030'
            c['accent_pressed'] = '#c88020'
        else:
            c['shadow_dark'] = 'rgba(0,0,0,0.25)'
            c['shadow_light'] = 'rgba(255,255,255,0.9)'
            c['neumorphic_light'] = '#f0f0f0'
            c['neumorphic_dark'] = '#c8c8c8'
            c['gradient_start'] = '#f0e8e0'
            c['gradient_end'] = '#d8d0c8'
            c['border_3d_light'] = 'rgba(255,255,255,0.8)'
            c['border_3d_dark'] = 'rgba(0,0,0,0.15)'
            c['accent'] = '#c87820'
            c['accent_hover'] = '#b06818'
            c['accent_pressed'] = '#985810'
        return c

    @classmethod
    def _style_modifier_frosted(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['window'] = 'rgba(16, 20, 28, 0.82)'
            c['base'] = 'rgba(24, 28, 38, 0.78)'
            c['alternate_base'] = 'rgba(32, 36, 48, 0.75)'
            c['button'] = 'rgba(44, 48, 62, 0.72)'
            c['player_panel'] = 'rgba(28, 32, 42, 0.78)'
            c['player_button'] = 'rgba(48, 52, 66, 0.7)'
            c['player_combo'] = 'rgba(36, 40, 52, 0.65)'
            c['player_background'] = 'rgba(12, 16, 24, 0.85)'
            c['player_slider_track'] = 'rgba(70, 80, 100, 0.6)'
            c['player_volume_track'] = 'rgba(56, 64, 80, 0.6)'
            c['player_line'] = 'rgba(70, 80, 100, 0.5)'
            c['table_alternate'] = 'rgba(16, 20, 28, 0.7)'
            c['table_header'] = 'rgba(48, 52, 66, 0.7)'
            c['tooltip_base'] = 'rgba(32, 36, 48, 0.85)'
            c['backdrop_tint'] = 'rgba(0, 20, 40, 0.3)'
            c['frosted_opacity'] = 0.78
            c['frosted_border'] = 'rgba(255,255,255,0.1)'
            c['frosted_border_mid'] = 'rgba(255,255,255,0.15)'
            c['frosted_border_strong'] = 'rgba(255,255,255,0.2)'
            c['frosted_border_focus'] = 'rgba(255,255,255,0.3)'
            c['accent'] = '#40a0e0'
            c['accent_hover'] = '#3090d0'
            c['accent_pressed'] = '#2080c0'
            c['osd_text'] = '#e0f0ff'
            c['osd_border'] = '#0a1020'
            c['osd_shadow'] = '#0a1020'
        else:
            c['window'] = 'rgba(238, 242, 248, 0.82)'
            c['base'] = 'rgba(248, 250, 255, 0.78)'
            c['alternate_base'] = 'rgba(228, 232, 240, 0.75)'
            c['button'] = 'rgba(210, 214, 224, 0.72)'
            c['player_panel'] = 'rgba(242, 244, 250, 0.78)'
            c['player_button'] = 'rgba(200, 204, 216, 0.7)'
            c['player_combo'] = 'rgba(218, 222, 232, 0.65)'
            c['player_background'] = 'rgba(242, 244, 250, 0.85)'
            c['player_slider_track'] = 'rgba(150, 160, 180, 0.5)'
            c['player_volume_track'] = 'rgba(170, 178, 196, 0.5)'
            c['player_line'] = 'rgba(170, 178, 196, 0.4)'
            c['table_alternate'] = 'rgba(238, 242, 248, 0.7)'
            c['table_header'] = 'rgba(228, 232, 240, 0.7)'
            c['tooltip_base'] = 'rgba(250, 252, 255, 0.85)'
            c['backdrop_tint'] = 'rgba(200, 220, 255, 0.2)'
            c['frosted_opacity'] = 0.82
            c['frosted_border'] = 'rgba(0,0,0,0.06)'
            c['frosted_border_mid'] = 'rgba(0,0,0,0.1)'
            c['frosted_border_strong'] = 'rgba(0,0,0,0.12)'
            c['frosted_border_focus'] = 'rgba(0,0,0,0.2)'
            c['accent'] = '#2080c0'
            c['accent_hover'] = '#1870b0'
            c['accent_pressed'] = '#1060a0'
            c['osd_text'] = '#1a2a3a'
            c['osd_border'] = '#ffffff'
            c['osd_shadow'] = '#c0c0c0'
        return c

    @classmethod
    def _style_modifier_win11(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['window'] = '#202020'
            c['base'] = '#2d2d2d'
            c['button'] = '#383838'
            c['accent'] = '#60cdff'
            c['accent_hover'] = '#4cc2ff'
            c['accent_pressed'] = '#38b8ff'
            c['mica_color'] = '#1c1c1c'
            c['card_color'] = '#2d2d2d'
        else:
            c['window'] = '#f3f3f3'
            c['base'] = '#ffffff'
            c['button'] = '#e5e5e5'
            c['accent'] = '#0078d4'
            c['accent_hover'] = '#006cbe'
            c['accent_pressed'] = '#005fa8'
            c['mica_color'] = '#f9f9f9'
            c['card_color'] = '#ffffff'
        c['font_family'] = "'Segoe UI Variable', 'Segoe UI', 'Microsoft YaHei', sans-serif"
        c['border_thin'] = 'rgba(255,255,255,0.08)' if color_mode == 'dark' else 'rgba(0,0,0,0.06)'
        c['shadow_subtle'] = '0 2px 4px rgba(0,0,0,0.16)' if color_mode == 'dark' else '0 2px 4px rgba(0,0,0,0.08)'
        c['border_subtle'] = 'rgba(255,255,255,0.10)' if color_mode == 'dark' else 'rgba(0,0,0,0.08)'
        return c

    @classmethod
    def _style_modifier_mac(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['window'] = '#2d2d2d'
            c['base'] = '#333333'
            c['button'] = '#3e3e3e'
            c['accent'] = '#0a84ff'
            c['accent_hover'] = '#0070e0'
            c['accent_pressed'] = '#0058b0'
            c['window_text'] = '#f5f5f7'
            c['shadow_dark'] = 'rgba(0,0,0,0.3)'
            c['shadow_light'] = 'rgba(255,255,255,0.06)'
            c['shadow_subtle'] = '0 2px 8px rgba(0,0,0,0.24)'
            c['border_subtle'] = 'rgba(255,255,255,0.12)'
        else:
            c['window'] = '#f5f5f7'
            c['base'] = '#ffffff'
            c['button'] = '#e8e8ed'
            c['accent'] = '#0a84ff'
            c['accent_hover'] = '#0070e0'
            c['accent_pressed'] = '#0058b0'
            c['window_text'] = '#1d1d1f'
            c['shadow_dark'] = 'rgba(0,0,0,0.1)'
            c['shadow_light'] = 'rgba(255,255,255,0.9)'
            c['shadow_subtle'] = '0 2px 8px rgba(0,0,0,0.12)'
            c['border_subtle'] = 'rgba(0,0,0,0.08)'
        c['font_family'] = "'SF Pro Display', 'SF Pro', 'Segoe UI', 'Microsoft YaHei', sans-serif"
        return c

    @classmethod
    def _style_modifier_ios(cls, colors, color_mode):
        c = colors.copy()
        if color_mode == 'dark':
            c['window'] = '#1c1c1e'
            c['base'] = '#2c2c2e'
            c['button'] = '#3a3a3c'
            c['accent'] = '#0a84ff'
            c['accent_hover'] = '#409cff'
            c['accent_pressed'] = '#0070e0'
            c['window_text'] = '#f5f5f7'
            c['shadow_dark'] = 'rgba(0,0,0,0.2)'
            c['shadow_light'] = 'rgba(255,255,255,0.04)'
            c['shadow_subtle'] = '0 1px 4px rgba(0,0,0,0.16)'
            c['border_subtle'] = 'rgba(255,255,255,0.12)'
        else:
            c['window'] = '#f2f2f7'
            c['base'] = '#ffffff'
            c['button'] = '#e5e5ea'
            c['accent'] = '#007aff'
            c['accent_hover'] = '#0062cc'
            c['accent_pressed'] = '#004d99'
            c['window_text'] = '#1c1c1e'
            c['shadow_dark'] = 'rgba(0,0,0,0.06)'
            c['shadow_light'] = 'rgba(255,255,255,0.95)'
            c['shadow_subtle'] = '0 1px 4px rgba(0,0,0,0.08)'
            c['border_subtle'] = 'rgba(0,0,0,0.08)'
        c['font_family'] = "'SF Pro Display', 'SF Pro', 'Segoe UI', 'Microsoft YaHei', sans-serif"
        return c

    STYLE_MODIFIERS = {
        'flat': _style_modifier_flat,
        'neumorphic': _style_modifier_neumorphic,
        'skeuomorphic': _style_modifier_skeuomorphic,
        'frosted': _style_modifier_frosted,
        'win11': _style_modifier_win11,
        'mac': _style_modifier_mac,
        'ios': _style_modifier_ios,
    }


    @staticmethod
    def _accent_fill(accent: str, alpha: int) -> str:
        """把强调色转成半透明填充，供玻璃风格主按钮使用。"""
        from PySide6.QtGui import QColor
        c = QColor(accent)
        if not c.isValid():
            return accent
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha / 255:.2f})"

    @classmethod
    def _style_primary_btn_decoration(cls, colors, hover=False, pressed=False):
        """主按钮（强调色按钮）装饰。

        四套玻璃风格用“强调色淡填充 + 强调色描边”与普通按钮拉开层级；
        其余风格保持原有表现，不引入额外视觉噪音。
        """
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        ac = c.get('accent', '#4a9eff')
        if style in cls.GLASS_STYLES:
            alpha = 102 if pressed else (66 if hover else 40)
            border = ac
            return (
                f"background-color: {cls._accent_fill(ac, alpha)}; "
                f"border: 1px solid {border}; border-radius: {r}px;"
            )
        return cls._style_btn_decoration(
            c, hover=hover, pressed=pressed, accent_color=ac
        )

    @classmethod
    def _style_btn_decoration(cls, colors, hover=False, pressed=False, disabled=False, accent_color=None):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        ac = accent_color or c['accent']
        if disabled:
            if style in ('neumorphic',):
                return f"background-color: {c['light']}; border: 1px solid {c['mid']}; border-radius: {r}px; color: {c['placeholder']};"
            return f"background-color: {c['light']}; border-color: {c['mid']}; color: {c['placeholder']};"
        if pressed:
            if style == 'neumorphic':
                return f"background-color: {c['neumorphic_dark']}; {cls._get_style_inset()} border-radius: {r}px;"
            elif style == 'skeuomorphic':
                return f"background-color: {c.get('gradient_end', c['dark'])}; border: 2px inset {c.get('border_3d_dark', c['mid'])}; border-radius: {r}px;"
            elif style == 'frosted':
                return f"background-color: {c['dark']}; border: 1px solid {c.get('frosted_border_mid', c['mid'])}; border-radius: {r}px;"
            elif style == 'win11':
                return f"background-color: {c['dark']}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px;"
            elif style == 'mac':
                return f"background-color: {c['dark']}; border: 1px solid; border-top-color: {c.get('border_subtle', c['shadow_dark'])}; border-left-color: {c.get('border_subtle', c['shadow_dark'])}; border-bottom-color: {c['mid']}; border-right-color: {c['mid']}; border-radius: {r}px;"
            elif style == 'ios':
                return f"background-color: {c['dark']}; border: none; border-radius: {r - 1}px;"
            return f"background-color: {c['dark']}; border-color: {c.get('accent_pressed', ac)};"
        if hover:
            if style == 'neumorphic':
                return f"background-color: {c['neumorphic_dark']}; border: 2px solid {ac}; border-radius: {r}px;"
            elif style == 'skeuomorphic':
                return f"background-color: {c.get('gradient_start', c['light'])}; border: 2px outset {ac}; border-radius: {r}px;"
            elif style == 'frosted':
                return f"background-color: {c['light']}; border: 1px solid {c.get('frosted_border_strong', c['mid'])}; border-radius: {r}px;"
            elif style == 'win11':
                return f"background-color: {c['light']}; border: 1px solid {ac}; border-radius: {r}px;"
            elif style == 'mac':
                return f"background-color: {c['light']}; border: 1px solid {c.get('border_subtle', c['mid'])}; border-radius: {r}px;"
            elif style == 'ios':
                return f"background-color: {c['light']}; border: none; border-radius: {r}px;"
            return f"background-color: {c['light']}; border-color: {ac};"
        if style == 'neumorphic':
            return f"background-color: {c['neumorphic_light']}; {cls._get_style_raised()} border-radius: {r}px;"
        elif style == 'skeuomorphic':
            return f"background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c.get('gradient_start', c['light'])}, stop:1 {c['button']}); border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {r}px;"
        elif style == 'frosted':
            return f"background-color: {c['button']}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px;"
        elif style == 'win11':
            return f"background-color: {c['button']}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px;"
        elif style == 'mac':
            return f"background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['light']}, stop:0.95 {c['button']}, stop:1 {c['dark']}); border: none; border-radius: {r}px;"
        elif style == 'ios':
            return f"background-color: {c['button']}; border: none; border-radius: {r}px;"
        return f"background-color: {c['button']}; border: 1px solid {c['mid']}; border-radius: {r}px;"

    @classmethod
    def _style_input_decoration(cls, colors, focus=False, disabled=False):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if disabled:
            return f"background-color: {c['light']}; border: 1px solid {c['mid']}; border-radius: {r}px; color: {c['placeholder']};"
        if focus:
            if style == 'neumorphic':
                return f"border: 2px solid {c['accent']}; border-radius: {r}px; outline: none;"
            elif style == 'skeuomorphic':
                return f"border: 2px solid {c['accent']}; border-radius: {r}px; outline: none;"
            elif style == 'frosted':
                return f"border: 1px solid {c.get('frosted_border_focus', c['mid'])}; border-radius: {r}px; outline: none;"
            elif style == 'win11':
                return f"border: 1px solid {c.get('border_thin', c['mid'])}; border-bottom: 2px solid {c['accent']}; border-radius: {r}px; outline: none;"
            elif style == 'mac':
                return f"border: 2px solid {c['accent']}; border-radius: {r}px; outline: none;"
            elif style == 'ios':
                return f"border: 2px solid {c['accent']}; border-radius: {r}px; outline: none;"
            return f"border-color: {c['accent']}; outline: none;"
        if style == 'neumorphic':
            return f"background-color: {c['neumorphic_light']}; {cls._get_style_inset()} border-radius: {r}px;"
        elif style == 'skeuomorphic':
            return f"background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c.get('gradient_start', c['light'])}, stop:1 {c['alternate_base']}); border: 2px inset {c.get('border_3d_dark', c['mid'])}; border-radius: {r}px;"
        elif style == 'frosted':
            return f"background-color: {c['alternate_base']}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px;"
        elif style == 'win11':
            return f"background-color: {c['alternate_base']}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px; border-bottom: 2px solid {c['accent']};"
        elif style == 'mac':
            return f"background-color: {c['alternate_base']}; border: 1px solid; border-top-color: {c.get('border_subtle', c['shadow_dark'])}; border-left-color: {c.get('border_subtle', c['shadow_dark'])}; border-bottom-color: {c['mid']}; border-right-color: {c['mid']}; border-radius: {r}px;"
        elif style == 'ios':
            return f"background-color: {c['alternate_base']}; border: 1px solid {c.get('border_subtle', c['shadow_dark'])}; border-radius: {r}px;"
        return f"background-color: {c['alternate_base']}; border: 1px solid {c['mid']}; border-radius: {r}px;"

    @classmethod
    def _style_group_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if style == 'neumorphic':
            return f"background-color: {c['alternate_base']}; border: none; border-radius: {r}px; {cls._get_style_raised()}"
        elif style == 'skeuomorphic':
            return f"background-color: {c['alternate_base']}; border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {r}px;"
        elif style == 'frosted':
            return f"background-color: {c['alternate_base']}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px;"
        elif style == 'win11':
            return f"background-color: {c.get('card_color', c['alternate_base'])}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px;"
        elif style == 'mac':
            return f"background-color: {c['alternate_base']}; border-top: 1px solid {c.get('border_subtle', c['shadow_dark'])}; border-radius: {r}px;"
        elif style == 'ios':
            return f"background-color: {c['alternate_base']}; border: 1px solid {c.get('border_subtle', c['shadow_dark'])}; border-radius: {r}px;"
        return f"background-color: {c['alternate_base']}; border: 1px solid {c['mid']}; border-radius: {r}px;"

    @classmethod
    def _style_menu_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        menu_r = max(r - 2, 4)
        menu_pad = max(menu_r // 2, 4)
        if style == 'neumorphic':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 2px solid; border-top-color: {c['shadow_light']}; border-left-color: {c['shadow_light']}; border-bottom-color: {c['shadow_dark']}; border-right-color: {c['shadow_dark']}; border-radius: {menu_r}px;"
        elif style == 'skeuomorphic':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {menu_r}px;"
        elif style == 'frosted':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {menu_r}px;"
        elif style == 'win11':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {menu_r}px;"
        elif style == 'mac':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 1px solid {c.get('border_subtle', c['mid'])}; border-radius: {menu_r}px;"
        elif style == 'ios':
            return f"background-color: {c['base']}; padding: {menu_pad}px; border: 1px solid {c.get('border_subtle', c['shadow_dark'])}; border-radius: {menu_r}px;"
        return f"background-color: {c['base']}; padding: 2px; border: 1px solid {c['mid']}; border-radius: {menu_r}px;"

    @classmethod
    def _style_padding(cls, widget_type='button'):
        style = cls._visual_style
        if widget_type == 'button':
            pads = {'win11': '8px 16px', 'ios': '10px 20px', 'mac': '8px 16px'}
            return pads.get(style, '6px 12px')
        elif widget_type == 'input':
            pads = {'win11': '8px 12px', 'ios': '10px 14px', 'mac': '8px 12px'}
            return pads.get(style, '6px')
        return '6px 12px'

    @classmethod
    def _style_slider_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        groove_h = 6 if style in ('neumorphic', 'skeuomorphic') else 4
        handle_size = 14 if style in ('neumorphic', 'skeuomorphic', 'ios') else 10
        handle_margin = -((handle_size - groove_h) // 2)
        if style == 'neumorphic':
            groove = f"background: {c['neumorphic_light']}; height: {groove_h}px; {cls._get_style_inset()} border-radius: {r}px;"
            handle = f"background: {c['neumorphic_light']}; width: {handle_size}px; height: {handle_size}px; {cls._get_style_raised()} border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        elif style == 'skeuomorphic':
            groove = f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c.get('gradient_start', c['light'])}, stop:1 {c.get('gradient_end', c['dark'])}); height: {groove_h}px; border: 1px inset {c.get('border_3d_dark', c['mid'])}; border-radius: {r}px;"
            handle = f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c.get('gradient_start', c['light'])}, stop:1 {c['button']}); width: {handle_size}px; height: {handle_size}px; border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        elif style == 'frosted':
            groove = f"background: {c['player_slider_track']}; height: {groove_h}px; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px;"
            handle = f"background: {c['player_slider_handle']}; width: {handle_size}px; height: {handle_size}px; border: 1px solid {c.get('frosted_border_strong', c['mid'])}; border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        elif style == 'win11':
            groove = f"background: {c['player_slider_track']}; height: {groove_h}px; border: none; border-radius: {r}px;"
            handle = f"background: {c['accent']}; width: {handle_size}px; height: {handle_size}px; border: none; border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        elif style == 'mac':
            groove = f"background: {c['player_slider_track']}; height: {groove_h}px; border: none; border-radius: {r}px;"
            handle = f"background: {c['player_slider_handle']}; width: {handle_size}px; height: {handle_size}px; border: none; border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        elif style == 'ios':
            groove = f"background: {c['player_slider_track']}; height: {groove_h}px; border: none; border-radius: {r}px;"
            handle = f"background: {c.get('slider_handle_light', c['light'])}; width: {handle_size}px; height: {handle_size}px; border: 1px solid rgba(0,0,0,0.15); border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        else:
            groove = f"background: {c['player_slider_track']}; height: {groove_h}px; border-radius: {cls._get_scaled_radius('scrollbar')}px;"
            handle = f"background: {c['player_slider_handle']}; width: {handle_size}px; height: {handle_size}px; border-radius: {handle_size // 2}px; margin: {handle_margin}px 0;"
        sub_page = f"background: {c['player_slider_fill']}; height: {groove_h}px; border-radius: {cls._get_scaled_radius('scrollbar')}px;"
        return groove, sub_page, handle

    @classmethod
    def _style_progress_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if style == 'neumorphic':
            return (
                f"background-color: {c['neumorphic_light']}; {cls._get_style_inset()} border-radius: {r}px;",
                f"background-color: {c['accent']}; border-radius: {r}px;"
            )
        elif style == 'skeuomorphic':
            return (
                f"background-color: {c.get('gradient_start', c['light'])}; border: 1px inset {c.get('border_3d_dark', c['mid'])}; border-radius: {r}px;",
                f"background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {c['accent']}, stop:1 {c.get('accent_pressed', c['dark'])}); border-radius: {r}px;"
            )
        elif style == 'frosted':
            return (
                f"background-color: {c['alternate_base']}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px;",
                f"background-color: {c['accent']}; border-radius: {r}px;"
            )
        elif style == 'win11':
            return (
                f"background-color: {c.get('card_color', c['alternate_base'])}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px;",
                f"background-color: {c['accent']}; border-radius: {r}px;"
            )
        elif style in ('mac', 'ios'):
            return (
                f"background-color: {c['alternate_base']}; border: none; border-radius: {r}px;",
                f"background-color: {c['accent']}; border-radius: {r}px;"
            )
        return (
            f"background-color: {c['alternate_base']}; border-radius: {r}px;",
            f"background-color: {c['accent']}; border-radius: {r}px;"
        )

    @classmethod
    def _style_scrollbar_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if style == 'neumorphic':
            return (
                f"background-color: {c['neumorphic_light']}; width: 10px; border: none;",
                f"background-color: {c['neumorphic_light']}; {cls._get_style_raised()} border-radius: {r}px; min-height: 40px; margin: 2px;",
                f"background-color: {c['neumorphic_dark']}; {cls._get_style_inset()} border-radius: {r}px; min-height: 40px; margin: 2px;"
            )
        elif style == 'skeuomorphic':
            return (
                f"background-color: {c['alternate_base']}; width: 10px; border: 1px solid {c.get('border_3d_dark', c['mid'])};",
                f"background-color: {c['button']}; border: 1px outset {c.get('border_3d_light', c['mid'])}; border-radius: {r}px; min-height: 40px; margin: 2px;",
                f"background-color: {c['dark']}; border: 1px inset {c.get('border_3d_dark', c['mid'])}; border-radius: {r}px; min-height: 40px; margin: 2px;"
            )
        elif style == 'frosted':
            return (
                "background-color: transparent; width: 10px; border: none;",
                f"background-color: {c.get('frosted_border_mid', c['mid'])}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px; min-height: 40px; margin: 2px;",
                f"background-color: {c.get('frosted_border_strong', c['mid'])}; border: 1px solid {c.get('frosted_border_mid', c['mid'])}; border-radius: {r}px; min-height: 40px; margin: 2px;"
            )
        elif style == 'win11':
            return (
                "background-color: transparent; width: 10px; border: none;",
                f"background-color: {c.get('border_thin', c['mid'])}; border: none; border-radius: {r}px; min-height: 40px; margin: 2px;",
                f"background-color: {c['mid']}; border: none; border-radius: {r}px; min-height: 40px; margin: 2px;"
            )
        elif style in ('mac', 'ios'):
            return (
                "background-color: transparent; width: 8px; border: none;",
                f"background-color: {c['mid']}; border: none; border-radius: {r}px; min-height: 30px; margin: 2px;",
                f"background-color: {c['accent']}; border: none; border-radius: {r}px; min-height: 30px; margin: 2px;"
            )
        return (
            f"background-color: {c['alternate_base']}; width: 10px; border: none;",
            f"background-color: {c['mid']}; border-radius: {r}px; min-height: 40px; margin: 2px;",
            f"background-color: {c['accent']}; border-radius: {r}px; min-height: 40px; margin: 2px;"
        )

    @classmethod
    def _style_checkbox_indicator_decoration(cls, colors, checked=False):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        indicator_r = max(r - 4, 3)
        if style == 'neumorphic':
            bg = c['accent'] if checked else c['neumorphic_light']
            border = f"border: 2px solid {c['accent']};" if checked else cls._get_style_inset()
            return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"
        elif style == 'skeuomorphic':
            bg = c['accent'] if checked else c.get('gradient_start', c['light'])
            border = f"border: 2px solid {c['accent']};" if checked else f"border: 2px inset {c.get('border_3d_dark', c['mid'])};"
            return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"
        elif style == 'frosted':
            bg = c['accent'] if checked else c['alternate_base']
            border = f"border: 1px solid {c['accent']};" if checked else f"border: 1px solid {c.get('frosted_border', c['mid'])};"
            return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"
        elif style == 'win11':
            bg = c['accent'] if checked else c['alternate_base']
            border = f"border: 1px solid {c['accent']};" if checked else f"border: 1px solid {c.get('border_thin', c['mid'])};"
            return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"
        elif style in ('mac', 'ios'):
            bg = c['accent'] if checked else c['alternate_base']
            border = "border: none;" if not checked else "border: none;"
            return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"
        bg = c['accent'] if checked else c['alternate_base']
        border = f"border: 2px solid {c['accent']};" if checked else f"border: 2px solid {c['mid']};"
        return f"background-color: {bg}; {border} border-radius: {indicator_r}px;"

    @classmethod
    def _style_dock_title_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if style == 'neumorphic':
            return f"background-color: {c['base']}; {cls._get_style_raised()} border-radius: {r}px; padding: 6px;"
        elif style == 'skeuomorphic':
            return f"background-color: {c['base']}; border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {r}px; padding: 4px;"
        elif style == 'frosted':
            return f"background-color: {c['base']}; border: 1px solid {c.get('frosted_border', c['mid'])}; border-radius: {r}px; padding: 4px;"
        elif style == 'win11':
            return f"background-color: {c.get('card_color', c['base'])}; border: none; border-bottom: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px; padding: 4px;"
        elif style in ('mac', 'ios'):
            return f"background-color: {c['base']}; border: none; border-radius: {r}px; padding: 6px;"
        return f"background-color: {c['base']}; border: none; padding: 4px;"

    @classmethod
    def _style_tooltip_decoration(cls, colors):
        c = colors
        style = cls._visual_style
        r = cls._get_style_border_radius()
        if style == 'neumorphic':
            return f"background-color: {c.get('tooltip_base', c['base'])}; {cls._get_style_raised()} border-radius: {r}px; padding: 6px;"
        elif style == 'skeuomorphic':
            return f"background-color: {c.get('tooltip_base', c['base'])}; border: 2px outset {c.get('border_3d_light', c['mid'])}; border-radius: {r}px; padding: 4px;"
        elif style == 'frosted':
            return f"background-color: {c.get('tooltip_base', c['base'])}; border: 1px solid {c.get('frosted_border_mid', c['mid'])}; border-radius: {r}px; padding: 6px;"
        elif style == 'win11':
            return f"background-color: {c.get('card_color', c['base'])}; border: 1px solid {c.get('border_thin', c['mid'])}; border-radius: {r}px; padding: 6px;"
        elif style in ('mac', 'ios'):
            return f"background-color: {c.get('tooltip_base', c['base'])}; border: none; border-radius: {r}px; padding: 6px;"
        return f"background-color: {c.get('tooltip_base', c['base'])}; border: 1px solid {c['mid']}; padding: 4px;"


