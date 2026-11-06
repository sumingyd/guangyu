"""通用控件/对话框样式方法。"""
from ui.styles_base import StylesBase


class StylesCommon(StylesBase):
    """通用控件样式方法。"""

    """通用控件/对话框/列表样式方法。"""

    @staticmethod
    def common_menu_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        menu_bg = colors['base']
        menu_text = colors['window_text']
        menu_hover_bg = colors['neumorphic_light'] if style == 'neumorphic' else colors['highlight']
        menu_hover_text = colors['accent'] if style == 'neumorphic' else colors['highlighted_text']
        menu_dec = AppStyles._style_menu_decoration(colors)
        item_r = max(r - 2, 4)
        if style in ('neumorphic', 'skeuomorphic'):
            item_pad = "6px 24px"
        else:
            item_pad = "4px 20px"
        return f"""
            QMenu {{
                color: {menu_text};
                {menu_dec}
            }}
            QMenu::item {{
                padding: {item_pad};
                margin: 2px;
                border-radius: {item_r}px;
            }}
            QMenu::item:selected {{
                background-color: {menu_hover_bg};
                color: {menu_hover_text};
                border-radius: {item_r}px;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {colors.get('shadow_dark', colors['mid'])};
                margin: 4px 8px;
            }}
        """

    @staticmethod
    def toolbar_button_style() -> str:
        colors = AppStyles._get_qss_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        btn_dec = AppStyles._style_btn_decoration(colors)
        btn_hover = AppStyles._style_btn_decoration(colors, hover=True)
        btn_pressed = AppStyles._style_btn_decoration(colors, pressed=True)
        return f"""
            QToolButton {{
                padding: 4px 8px;
                margin: 1px;
                min-width: 60px;
                min-height: 28px;
                color: {colors['window_text']};
                font-size: 12px;
                font-weight: 500;
                font-family: {ff};
                {btn_dec}
            }}
            QToolButton:hover {{
                color: {colors['accent']};
                {btn_hover}
            }}
            QToolButton:pressed {{
                color: {colors['accent_pressed']};
                {btn_pressed}
            }}
            QToolButton::menu-indicator {{
                width: 0px;
            }}
        """

    @staticmethod
    def apply_button_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        btn_dec = AppStyles._style_btn_decoration(colors, accent_color=colors['success'])
        btn_hover = AppStyles._style_btn_decoration(colors, hover=True, accent_color=colors['success'])
        btn_pressed = AppStyles._style_btn_decoration(colors, pressed=True, accent_color=colors['success'])
        pad = AppStyles._style_padding('button')
        return f"""
            QPushButton {{
                color: {colors['window_text']};
                {btn_dec}
                padding: {pad};
                font-weight: 500;
                font-size: 12px;
                font-family: {ff};
            }}
            QPushButton:hover {{
                {btn_hover}
            }}
            QPushButton:pressed {{
                {btn_pressed}
            }}
        """

    @staticmethod
    def cancel_button_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        btn_dec = AppStyles._style_btn_decoration(colors, accent_color=colors['error'])
        btn_hover = AppStyles._style_btn_decoration(colors, hover=True, accent_color=colors['error'])
        btn_pressed = AppStyles._style_btn_decoration(colors, pressed=True, accent_color=colors['error'])
        pad = AppStyles._style_padding('button')
        return f"""
            QPushButton {{
                color: {colors['window_text']};
                {btn_dec}
                padding: {pad};
                font-weight: 500;
                font-size: 12px;
                font-family: {ff};
            }}
            QPushButton:hover {{
                {btn_hover}
            }}
            QPushButton:pressed {{
                {btn_pressed}
            }}
        """

    @staticmethod
    def secondary_label_style() -> str:
        colors = AppStyles._get_colors()
        ff = AppStyles._get_style_font_family()
        return f"""
            QLabel {{
                color: {colors['window_text']};
                padding: 0 5px;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
            }}
        """

    @staticmethod
    def common_button_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        btn_dec = AppStyles._style_btn_decoration(colors)
        btn_hover = AppStyles._style_btn_decoration(colors, hover=True)
        btn_pressed = AppStyles._style_btn_decoration(colors, pressed=True)
        btn_disabled = AppStyles._style_btn_decoration(colors, disabled=True)
        pad = AppStyles._style_padding('button')
        from utils.platform_utils import get_touch_target_size, is_touch_device
        touch_h = get_touch_target_size() if is_touch_device() else 0
        return f"""
            QPushButton {{
                color: {colors['window_text']};
                {btn_dec}
                padding: {pad};
                min-width: 0px;
                min-height: {touch_h}px;
                font-weight: 500;
                font-size: 12px;
                font-family: {ff};
            }}
            QPushButton:hover {{
                {btn_hover}
            }}
            QPushButton:pressed {{
                {btn_pressed}
            }}
            QPushButton:disabled {{
                {btn_disabled}
            }}
        """

    @staticmethod
    def common_label_style() -> str:
        colors = AppStyles._get_colors()
        ff = AppStyles._get_style_font_family()
        return f"""
            QLabel {{
                color: {colors['window_text']};
                font-size: 12px;
                font-family: {ff};
            }}
        """

    @staticmethod
    def common_line_edit_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        inp_disabled = AppStyles._style_input_decoration(colors, disabled=True)
        pad = AppStyles._style_padding('input')
        return f"""
            QLineEdit {{
                color: {colors['window_text']};
                {inp_dec}
                padding: {pad};
                font-size: 12px;
                font-family: {ff};
                min-height: 20px;
            }}
            QLineEdit:focus {{
                {inp_focus}
            }}
            QLineEdit:disabled {{
                {inp_disabled}
            }}
            QLineEdit::clear-button {{

                width: 14px;
            }}
        """

    @staticmethod
    def common_combo_box_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        inp_disabled = AppStyles._style_input_decoration(colors, disabled=True)
        pad = AppStyles._style_padding('input')
        list_item_r = AppStyles._get_scaled_radius('list_item')
        return f"""
            QComboBox {{
                color: {colors['window_text']};
                {inp_dec}
                padding: {pad};
                font-size: 12px;
                font-family: {ff};
                min-width: 120px;
            }}
            QComboBox:focus {{
                {inp_focus}
            }}
            QComboBox:disabled {{
                {inp_disabled}
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['alternate_base']};
                color: {colors['window_text']};
                border: 1px solid {colors['mid']};
                border-radius: {list_item_r}px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 10px;
                min-height: 24px;
                margin: 2px 0;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {colors['accent']};
                color: {AppStyles.COLOR_WHITE};
            }}
        """

    @staticmethod
    def common_spin_box_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        inp_disabled = AppStyles._style_input_decoration(colors, disabled=True)
        pad = AppStyles._style_padding('input')
        return f"""
            QSpinBox {{
                color: {colors['window_text']};
                {inp_dec}
                padding: {pad};
                padding-right: 32px;
                font-size: 12px;
                font-family: {ff};
                min-height: 20px;
            }}
            QSpinBox:focus {{
                {inp_focus}
            }}
            QSpinBox:disabled {{
                {inp_disabled}
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 20px;
                border: none;
                border-left: 1px solid {colors['mid']};
                background-color: {colors['button']};
                min-width: 0;
                min-height: 0;
                padding: 0;
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: right top;
                border-top-right-radius: {r}px;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: right bottom;
                border-bottom-right-radius: {r}px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {colors['accent']};
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background-color: {colors['accent_pressed']};
            }}
            QSpinBox::up-arrow {{
                image: url({AppStyles._get_spin_up_image(colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QSpinBox::down-arrow {{
                image: url({AppStyles._get_spin_down_image(colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QSpinBox::up-button:hover::up-arrow {{
                image: url({AppStyles._get_spin_up_image(colors['accent'])});
            }}
            QSpinBox::down-button:hover::down-arrow {{
                image: url({AppStyles._get_spin_down_image(colors['accent'])});
            }}
        """

    @staticmethod
    def url_combo_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        return f"""
            QComboBox {{
                color: {colors['window_text']};
                {inp_dec}
                padding: 2px 20px 2px 6px;
                font-size: 12px;
                font-family: {ff};
            }}
            QComboBox:focus {{
                {inp_focus}
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 18px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['alternate_base']};
                color: {colors['window_text']};
                border: 1px solid {colors['mid']};
                selection-background-color: {colors['accent']};
                selection-color: {AppStyles.COLOR_WHITE};
                padding: 2px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 3px 6px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {colors['accent']};
                color: {AppStyles.COLOR_WHITE};
            }}
            QComboBox QLineEdit {{
                background-color: transparent;
                border: none;
                padding: 0;
                font-size: 12px;
            }}
        """

    @staticmethod
    def url_range_input_style() -> str:
        """URL 范围输入框样式（QPlainTextEdit 版本，支持长 URL 多行显示）"""
        colors = AppStyles._get_colors()
        ff = AppStyles._get_style_font_family()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        return f"""
            QPlainTextEdit {{
                color: {colors['window_text']};
                {inp_dec}
                padding: 4px 6px;
                font-size: 12px;
                font-family: {ff};
            }}
            QPlainTextEdit:focus {{
                {inp_focus}
            }}
        """

    @staticmethod
    def common_check_box_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        indicator_r = AppStyles._get_scaled_radius('indicator')
        chk_bg = colors['neumorphic_light'] if style == 'neumorphic' else colors['alternate_base']
        if style == 'neumorphic':
            chk_border_dec = AppStyles._get_style_inset()
        elif style == 'skeuomorphic':
            chk_border_dec = f"border: 2px inset {colors.get('border_3d_dark', colors['mid'])};"
        elif style in ('mac', 'ios'):
            chk_border_dec = "border: none;"
        elif style == 'frosted':
            chk_border_dec = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            chk_border_dec = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
        else:
            chk_border_dec = f"border: 2px solid {colors['mid']};"
        return f"""
            QCheckBox {{
                color: {colors['window_text']};
                font-size: 12px;
                font-family: {ff};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: {indicator_r}px;
                background-color: {chk_bg};
                {chk_border_dec}
            }}
            QCheckBox::indicator:checked {{
                background-color: {colors['accent']};
                border: 2px solid {colors['accent']};
                border-radius: {indicator_r}px;
                image: url({AppStyles._get_check_image(AppStyles.COLOR_WHITE)});
            }}
            QCheckBox::indicator:hover {{
                border: 2px solid {colors['accent']};
                border-radius: {indicator_r}px;
            }}
        """

    @staticmethod
    def common_radio_button_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        indicator_r = AppStyles._get_scaled_radius('indicator')
        chk_bg = colors['neumorphic_light'] if style == 'neumorphic' else colors['alternate_base']
        if style == 'neumorphic':
            chk_border_dec = AppStyles._get_style_inset()
        elif style == 'skeuomorphic':
            chk_border_dec = f"border: 2px inset {colors.get('border_3d_dark', colors['mid'])};"
        elif style in ('mac', 'ios'):
            chk_border_dec = "border: none;"
        elif style == 'frosted':
            chk_border_dec = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            chk_border_dec = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
        else:
            chk_border_dec = f"border: 2px solid {colors['mid']};"
        return f"""
            QRadioButton {{
                color: {colors['window_text']};
                font-size: 12px;
                font-family: {ff};
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 16px;
                height: 16px;
                border-radius: {indicator_r}px;
                background-color: {chk_bg};
                {chk_border_dec}
            }}
            QRadioButton::indicator:checked {{
                background-color: {colors['accent']};
                border: 3px solid {colors['accent']};
                border-radius: {indicator_r}px;
                image: url({AppStyles._get_radio_dot_image(AppStyles.COLOR_WHITE)});
            }}
            QRadioButton::indicator:hover {{
                border: 2px solid {colors['accent']};
                border-radius: {indicator_r}px;
            }}
        """

    @staticmethod
    def common_group_box_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        grp_dec = AppStyles._style_group_decoration(colors)
        return f"""
            QGroupBox {{
                color: {colors['window_text']};
                margin-top: 12px;
                padding-top: 16px;
                font-weight: 600;
                font-size: {AppStyles.fs('title')}px;
                font-family: {ff};
                {grp_dec}
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {colors['window_text']};
                font-weight: 600;
                font-size: {AppStyles.fs('title')}px;
                font-family: {ff};
            }}
        """

    @staticmethod
    def scroll_area_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QScrollArea {{
                background-color: {colors['player_panel']};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {colors['player_panel']};
            }}
        """

    @staticmethod
    def label_style() -> str:
        colors = AppStyles._get_colors()
        return f"color: {colors['window_text']}; background-color: transparent;"

    @staticmethod
    def text_edit_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"color: {colors['window_text']}; background-color: {colors['base']}; border: 1px solid {colors['mid']}; border-radius: {r}px;"

    @staticmethod
    def frame_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"background-color: transparent; border: none; border-radius: {r}px;"

    @staticmethod
    def common_title_style() -> str:
        colors = AppStyles._get_colors()
        ff = AppStyles._get_style_font_family()
        return f"""
            QLabel {{
                color: {colors['window_text']};
                font-size: {AppStyles.fs('title')}px;
                font-weight: bold;
                font-family: {ff};
                background-color: transparent;
            }}
        """

    @staticmethod
    def common_link_style() -> str:
        colors = AppStyles._get_colors()
        ff = AppStyles._get_style_font_family()
        return f"""
            QLabel {{
                color: {colors['link']};
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                background-color: transparent;
                text-decoration: underline;
            }}
            QLabel:hover {{
                color: {colors['accent_hover']};
            }}
        """

    @staticmethod
    def common_area_style() -> str:
        colors = AppStyles._get_colors()
        grp_dec = AppStyles._style_group_decoration(colors)
        return f"""
            QWidget {{
                padding: 12px;
                {grp_dec}
            }}
        """

    @staticmethod
    def side_panel_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        if style == 'neumorphic':
            panel_dec = f"border: none; {AppStyles._get_style_raised()}"
        elif style == 'skeuomorphic':
            panel_dec = f"border: 2px outset {colors.get('border_3d_light', colors['mid'])};"
        elif style == 'frosted':
            panel_dec = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            panel_dec = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
        elif style in ('mac', 'ios'):
            panel_dec = "border: none;"
        else:
            panel_dec = ""
        return f"""
            QWidget {{
                background-color: {colors['alternate_base']};
                border-radius: {r}px;
                {panel_dec}
            }}
        """

    @staticmethod
    def section_title_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                font-size: {AppStyles.fs('title')}px;
                font-weight: bold;
                color: {colors['window_text']};
                background-color: transparent;
            }}
        """

    @staticmethod
    def small_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                font-size: {AppStyles.fs('caption')}px;
                color: {colors['window_text']};
                background-color: transparent;
            }}
        """

    @staticmethod
    def hint_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                font-size: {AppStyles.fs('caption')}px;
                color: {colors['mid']};
                background-color: transparent;
            }}
        """

    @staticmethod
    def button_style(active=False):
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        if active:
            btn_dec = AppStyles._style_primary_btn_decoration(colors)
            btn_hover = AppStyles._style_primary_btn_decoration(colors, hover=True)
            btn_pressed = AppStyles._style_primary_btn_decoration(colors, pressed=True)
        else:
            btn_dec = AppStyles._style_btn_decoration(colors)
            btn_hover = AppStyles._style_btn_decoration(colors, hover=True)
            btn_pressed = AppStyles._style_btn_decoration(colors, pressed=True)
            btn_disabled = AppStyles._style_btn_decoration(colors, disabled=True)
        pad = AppStyles._style_padding('button')
        if active:
            return f"""
                QPushButton {{
                    color: {colors['window_text']};
                    {btn_dec}
                    padding: {pad};
                    font-weight: 500;
                    font-size: {AppStyles.fs('body')}px;
                    font-family: {ff};
                }}
                QPushButton:hover {{
                    {btn_hover}
                }}
                QPushButton:pressed {{
                    {btn_pressed}
                }}
                QPushButton:focus {{
                    border: 2px solid {colors['accent']};
                }}
            """
        return f"""
            QPushButton {{
                color: {colors['window_text']};
                {btn_dec}
                padding: {pad};
                font-weight: 500;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
            }}
            QPushButton:hover {{
                {btn_hover}
            }}
            QPushButton:pressed {{
                {btn_pressed}
            }}
            QPushButton:focus {{
                border: 2px solid {colors['accent']};
            }}
            QPushButton:disabled {{
                {btn_disabled}
            }}
        """
    @staticmethod
    def transparent_style():
        return "background: transparent; border: none;"

    @staticmethod
    def transparent_background_style():
        return "background: transparent;"

    @staticmethod
    def tab_button_style(color: str, accent: str):
        return f"""
            QToolButton {{
                color: {color};
                background: transparent;
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 1px 3px;
                font-size: {AppStyles.fs('caption')}px;
            }}
            QToolButton:checked {{
                color: {accent};
                background-color: rgba(127, 127, 127, 0.16);
                font-weight: bold;
            }}
            QToolButton:hover {{
                color: {accent};
                background-color: rgba(127, 127, 127, 0.10);
            }}
            QToolButton:focus {{
                border-color: {accent};
            }}
        """

    @staticmethod
    def description_text_style():
        colors = AppStyles._get_colors()
        return f"color: {colors.get('mid', 'gray')}; font-size: {AppStyles.fs('caption')}px;"

    @staticmethod
    def separator_line_style():
        colors = AppStyles._get_colors()
        return f"background-color: {colors['mid']}; border: none;"

    @staticmethod
    def text_edit_info_style():
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"""
            QTextEdit {{
                background-color: {colors['alternate_base']};
                color: {colors['window_text']};
                border: 1px solid {colors['mid']};
                border-radius: {r}px;
                padding: 10px;
                font-size: {AppStyles.fs('body')}px;
            }}
        """

    @staticmethod
    def shortcut_overlay_style():
        c = AppStyles._get_colors()
        return f"""
            QWidget#shortcutOverlay {{
                background-color: {c.get('tooltip_base')};
                border: 1px solid {c.get('mid')};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; color: {c.get('tooltip_text')}; font-size: 14px; }}
            QLabel[role="key"] {{ color: {c.get('accent')}; font-weight: 600; }}
            QLabel[role="title"] {{ color: {c.get('window_text')}; font-size: 16px; font-weight: 700; }}
        """

    @staticmethod
    def status_label_style(success: bool):
        colors = AppStyles._get_colors()
        if success:
            color = colors.get('success', '#4CAF50')
        else:
            color = colors.get('warning', '#FF9800')
        return f"color: {color}; font-weight: bold; font-size: {AppStyles.fs('body')}px;"

    @classmethod
    def tooltip_style(cls):
        """QToolTip 是独立顶层窗口，必须在 QApplication 级样式表中生效。"""
        c = cls._get_colors()
        return f"""
            QToolTip {{
                {cls._style_tooltip_decoration(c)}
                color: {c.get('tooltip_text', c.get('window_text', '#ffffff'))};
                font-family: {cls._get_style_font_family()};
            }}
        """

