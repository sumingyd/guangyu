"""Player 播放器相关样式方法。"""
from ui.styles_base import StylesBase


class StylesPlayer(StylesBase):
    """Player 播放器控件样式方法。"""

    """Player/播放器相关样式方法。"""

    @staticmethod
    def player_button_style() -> str:
        colors = AppStyles._get_qss_colors()
        r = min(AppStyles._get_style_border_radius(), 6)
        style = AppStyles._visual_style
        btn_dec = AppStyles._style_btn_decoration(colors)
        btn_dec_hover = AppStyles._style_btn_decoration(colors, hover=True)
        btn_dec_pressed = AppStyles._style_btn_decoration(colors, pressed=True)
        return f"""
            QToolButton {{
                color: {colors['player_panel_text']};
                font-size: {AppStyles.fs('caption')}px;
                {btn_dec}
                padding: 1px 4px;
                margin: 0px;
            }}
            QToolButton:hover {{
                color: {colors['player_panel_text']};
                {btn_dec_hover}
            }}
            QToolButton:pressed {{
                color: {colors['player_button']};
                {btn_dec_pressed}
            }}
            QToolButton:checked {{
                background-color: {colors['highlight']};
                color: {colors['highlighted_text']};
            }}
            QToolButton:focus {{
                border: 2px solid {colors['accent']};
            }}
            QToolButton:disabled {{
                color: {colors['player_panel_disabled']};
            }}
        """

    @staticmethod
    def player_slider_style() -> str:
        colors = AppStyles._get_qss_colors()
        groove, sub_page, handle = AppStyles._style_slider_decoration(colors)
        return f"""
            QSlider {{
                background-color: transparent;
            }}
            QSlider::groove:horizontal {{
                {groove}
            }}
            QSlider::sub-page:horizontal {{
                {sub_page}
            }}
            QSlider::handle:horizontal {{
                {handle}
            }}
        """

    @staticmethod
    def player_volume_slider_style() -> str:
        colors = AppStyles._get_qss_colors()
        groove, sub_page, handle = AppStyles._style_slider_decoration(colors)
        return f"""
            QSlider::groove:horizontal {{
                {groove}
            }}
            QSlider::sub-page:horizontal {{
                {sub_page}
            }}
            QSlider::handle:horizontal {{
                {handle}
            }}
        """

    @staticmethod
    def exit_catchup_button_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        btn_dec = AppStyles._style_btn_decoration(colors)
        btn_hover = AppStyles._style_btn_decoration(colors, hover=True, accent_color=colors['error'])
        return f"""
            QToolButton {{
                color: {colors['window_text']};
                font-size: {AppStyles.fs('body')}px;
                {btn_dec}
                padding: 0px;
                margin: 0px;
            }}
            QToolButton:hover {{
                {btn_hover}
            }}
        """

    @staticmethod
    def player_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('body')}px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_media_badge_style() -> str:
        colors = AppStyles._get_colors()
        badge_r = AppStyles._get_scaled_radius('badge')
        return f"""
            QLabel {{
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('caption')}px;
                background-color: transparent;
                padding: 1px 5px;
                border: 1px solid {colors['player_line']};
                border-radius: {badge_r}px;
            }}
        """

    @staticmethod
    def player_time_badge_style() -> str:
        colors = AppStyles._get_colors()
        badge_r = AppStyles._get_scaled_radius('badge')
        return f"""
            QLabel {{
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('caption')}px;
                background-color: transparent;
                padding: 1px 5px;
                border: 1px solid {colors['player_line']};
                border-radius: {badge_r}px;
            }}
        """

    @staticmethod
    def player_hdr_badge_style() -> str:
        colors = AppStyles._get_colors()
        badge_r = AppStyles._get_scaled_radius('badge')
        return f"""
            QLabel {{
                color: #FFD700;
                font-size: {AppStyles.fs('caption')}px;
                font-weight: bold;
                background-color: rgba(255, 215, 0, 0.12);
                padding: 1px 6px;
                border: 1px solid rgba(255, 215, 0, 0.5);
                border-radius: {badge_r}px;
            }}
        """

    @staticmethod
    def player_status_badge_style() -> str:
        colors = AppStyles._get_colors()
        badge_r = AppStyles._get_scaled_radius('badge')
        return f"""
            QLabel {{
                color: {colors['player_success']};
                font-size: {AppStyles.fs('caption')}px;
                background-color: transparent;
                padding: 1px 5px;
                border: 1px solid {colors['player_success']};
                border-radius: {badge_r}px;
            }}
        """

    @staticmethod
    def player_channel_name_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_text']};
                font-size: {AppStyles.fs('title')}px;
                font-weight: bold;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
                border: none;
            }}
        """

    @staticmethod
    def player_channel_list_name_style() -> str:
        colors = AppStyles._get_colors()
        return f"font-size: {AppStyles.fs('body')}px; font-weight: bold; color: {colors['player_panel_text']}; background: transparent; border: none;"

    @staticmethod
    def player_program_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_success']};
                font-size: {AppStyles.fs('title')}px;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
                border: none;
            }}
        """

    @staticmethod
    def player_catchup_indicator_style() -> str:
        colors = AppStyles._get_colors()
        badge_r = AppStyles._get_scaled_radius('badge')
        return f"""
            QLabel {{
                color: {colors['player_accent']};
                font-size: {AppStyles.fs('caption')}px;
                background-color: transparent;
                padding: 1px 4px;
                border: 1px solid {colors['player_accent']};
                border-radius: {badge_r}px;
            }}
        """

    @staticmethod
    def player_program_desc_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('body')}px;
                background-color: transparent;
                padding: 0px;
                margin: 0px;
                border: none;
                outline: none;
                max-height: 48px;
            }}
        """

    @staticmethod
    def player_date_button_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('title')}px;
                padding: 0px;
                margin: 0px;
                border: none;
            }}
        """

    @staticmethod
    def player_date_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_text']};
                font-size: {AppStyles.fs('body')}px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_epg_title_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_text']};
                font-size: {AppStyles.fs('title')}px;
                font-weight: bold;
                padding: 8px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_group_combo_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        pad = AppStyles._style_padding('input')
        return f"""
            QComboBox {{
                background-color: {colors['player_combo']};
                color: {colors['player_panel_text']};
                padding: {pad};
                {inp_dec}
                font-size: {AppStyles.fs('body')}px;
                min-width: 80px;
            }}
            QComboBox:hover {{
                border: 1px solid {colors['player_accent']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 16px;
                border-left: none;
                border-top-right-radius: {r}px;
                border-bottom-right-radius: {r}px;
            }}
            QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(colors['player_panel_secondary'])});
                width: 10px;
                height: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['player_panel']};
                color: {colors['player_panel_text']};
                selection-background-color: {colors['player_accent']};
                selection-color: #ffffff;
                border: 1px solid {colors['player_line']};
                border-radius: {AppStyles._get_scaled_radius('list_item')}px;
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 10px;
                min-height: 24px;
            }}
        """

    @staticmethod
    def player_tab_style() -> str:
        colors = AppStyles._get_colors()
        tab_r = AppStyles._get_scaled_radius('tab')
        return f"""
            QTabWidget::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: {colors['player_combo']};
                color: {colors['player_panel_text']};
                padding: 5px 10px;
                border: 1px solid {colors['player_line']};
                border-bottom: none;
                border-top-left-radius: {tab_r}px;
                border-top-right-radius: {tab_r}px;
                font-size: {AppStyles.fs('caption')}px;
                min-width: 90px;
            }}
            QTabBar::tab:selected {{
                background-color: {colors['player_accent']};
                color: {AppStyles.COLOR_WHITE};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {colors['player_panel']};
            }}
        """

    @staticmethod
    def player_playlist_title_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_text']};
                font-size: {AppStyles.fs('title')}px;
                font-weight: bold;
                padding: 8px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_search_input_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        inp_dec = AppStyles._style_input_decoration(colors)
        inp_focus = AppStyles._style_input_decoration(colors, focus=True)
        pad = AppStyles._style_padding('input')
        return f"""
            QLineEdit {{
                background-color: {colors['player_combo']};
                color: {colors['player_panel_text']};
                {inp_dec}
                padding: {pad};
                font-size: {AppStyles.fs('body')}px;
            }}
            QLineEdit:focus {{
                border: 1px solid {colors['player_accent']};
            }}
            QLineEdit::clear-button {{
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 16px;
                image: url({AppStyles.get_icon('close', colors['player_panel_disabled'], 10)});
            }}
        """

    @staticmethod
    def player_line_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QFrame {{
                background-color: {colors['player_line']};
                max-height: 1px;
            }}
        """

    @staticmethod
    def player_video_placeholder_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{

                color: {colors['player_panel_hint']};
                background-color: {colors['player_video_placeholder']};
            }}
        """

    @staticmethod
    def player_empty_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_hint']};
                font-size: {AppStyles.fs('body')}px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_list_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QListWidget {{
                background-color: transparent;
                color: {colors['player_panel_text']};
                border: 2px solid transparent;
                border-radius: {AppStyles._get_scaled_radius('tab')}px;
                padding: 2px;
                outline: none;
            }}
            QListWidget:focus {{
                border-color: {colors['accent']};
            }}
            QListWidget::item {{
                padding: 2px 4px;
                min-height: 26px;
                border: none;
            }}
            QListWidget::item:hover {{
                background-color: {colors['highlight']};
            }}
            QListWidget::item:selected {{
                background-color: {colors['accent']};
                color: #ffffff;
            }}
            QListWidget::item:selected:!active {{
                background-color: {colors['highlight']};
                color: {colors['highlighted_text']};
            }}
        """

    @staticmethod
    def player_progress_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                color: {colors['player_panel_secondary']};
                font-size: {AppStyles.fs('caption')}px;
                background-color: transparent;
            }}
        """

    @staticmethod
    def player_channel_logo_style() -> str:
        colors = AppStyles._get_colors()
        return f"""
            QLabel {{
                font-size: 24px;
                background-color: transparent;
                color: {colors['player_panel_secondary']};
                qproperty-alignment: AlignVCenter | AlignHCenter;
            }}
        """

    @staticmethod
    def player_background_style() -> str:
        colors = AppStyles._get_colors()
        return f"background-color: {colors['player_background']};"

    @staticmethod
    def player_panel_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"background-color: transparent; border: none; border-radius: {r}px;"

    @staticmethod
    def title_bar_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        title_bg = colors.get('window', AppStyles._safe_fallback('window'))
        title_text = colors.get('window_text', AppStyles._safe_fallback('window_text'))
        accent_color = colors.get('accent', AppStyles._safe_fallback('accent'))
        if style == 'neumorphic':
            btn_dec = f"background-color: transparent; border: none; font-size: {AppStyles.fs('title')}px; padding: 4px 12px; margin: 2px; border-radius: {r}px;"
        elif style == 'skeuomorphic':
            btn_dec = f"background-color: transparent; border: 1px outset {colors.get('border_3d_light', colors['mid'])}; font-size: {AppStyles.fs('title')}px; padding: 4px 12px; margin: 2px; border-radius: {r}px;"
        elif style == 'frosted':
            btn_dec = f"background-color: {colors.get('frosted_border', 'transparent')}; border: 1px solid {colors.get('frosted_border', colors.get('border_thin', colors['mid']))}; font-size: {AppStyles.fs('title')}px; padding: 4px 12px; margin: 2px; border-radius: {r}px;"
        elif style == 'win11':
            btn_dec = f"background-color: transparent; border: none; font-size: {AppStyles.fs('title')}px; padding: 4px 12px; margin: 2px; border-radius: {r}px;"
        elif style in ('mac', 'ios'):
            btn_dec = f"background-color: transparent; border: none; font-size: {AppStyles.fs('title')}px; padding: 4px 14px; margin: 1px; border-radius: {r}px;"
        else:
            btn_dec = f"background-color: transparent; border: none; font-size: {AppStyles.fs('title')}px; padding: 4px 12px; margin: 2px; border-radius: {r}px;"
        return f"""
            QWidget#titleBar {{
                background-color: {title_bg};
                border-top-left-radius: {r}px;
                border-top-right-radius: {r}px;
            }}
            QWidget#titleBar > QPushButton {{
                color: {title_text};
                {btn_dec}
            }}
            QWidget#titleBar > QPushButton:hover {{
                background-color: {accent_color};
                color: white;
            }}
            QWidget#titleBar > QPushButton#closeButton:hover {{
                background-color: {AppStyles.COLOR_CLOSE_HOVER};
                color: white;
            }}
        """

    @staticmethod
    def title_label_style() -> str:
        colors = AppStyles._get_colors()
        title_text = colors.get('window_text', AppStyles._safe_fallback('window_text'))
        return f"color: {title_text}; font-size: {AppStyles.fs('body')}px; font-weight: bold; background: transparent; padding-left: 6px;"

    @staticmethod
    def dialog_title_bar_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        title_bg = colors.get('window', AppStyles._safe_fallback('window'))
        title_text = colors.get('window_text', AppStyles._safe_fallback('window_text'))
        accent = colors.get('accent', AppStyles._safe_fallback('accent'))
        close_hover = AppStyles.COLOR_CLOSE_HOVER
        if style == 'neumorphic':
            btn_dec = f"background-color: transparent; border: none; border-radius: {r}px;"
        elif style == 'skeuomorphic':
            btn_dec = f"background-color: transparent; border: 1px outset {colors.get('border_3d_light', colors['mid'])}; border-radius: {r}px;"
        elif style == 'frosted':
            btn_dec = f"background-color: {colors.get('frosted_border', 'transparent')}; border: 1px solid {colors.get('frosted_border', colors.get('border_thin', colors['mid']))}; border-radius: {r}px;"
        elif style == 'win11':
            btn_dec = f"background-color: transparent; border: none; border-radius: {r}px;"
        elif style in ('mac', 'ios'):
            btn_dec = f"background-color: transparent; border: none; border-radius: {r}px;"
        else:
            btn_dec = f"background-color: transparent; border: none; border-radius: {r}px;"
        return f"""
            QWidget#dialogTitleBar {{
                background-color: {title_bg};
                border-top-left-radius: {r}px;
                border-top-right-radius: {r}px;
            }}
            QWidget#dialogTitleBar > QPushButton {{
                color: {title_text};
                {btn_dec}
            }}
            QWidget#dialogTitleBar > QPushButton:hover {{
                background-color: {accent};
                color: white;
            }}
            QWidget#dialogTitleBar > QPushButton#closeButton:hover {{
                background-color: {close_hover};
                color: white;
            }}
        """

