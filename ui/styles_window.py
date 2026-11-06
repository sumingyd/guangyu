"""主窗口/菜单栏/状态栏样式方法。"""
from ui.styles_base import StylesBase, color_to_hex


class StylesWindow(StylesBase):
    """主窗口/菜单栏/状态栏样式方法。"""

    @staticmethod
    def main_window_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        if style == 'frosted':
            mw_colors = {}
            for k, v in colors.items():
                mw_colors[k] = color_to_hex(v) if isinstance(v, str) and v.startswith('rgba') else v
        else:
            mw_colors = colors
        container_bg = mw_colors['window']
        content_bg = mw_colors.get('player_background', mw_colors['window'])
        input_bg = mw_colors.get('input_bg', mw_colors['alternate_base'])
        dock_bg = mw_colors.get('dock_bg', mw_colors['base'])
        tooltip_bg = mw_colors.get('tooltip_base', mw_colors['base'])
        grp_dec = AppStyles._style_group_decoration(mw_colors)
        inp_dec = AppStyles._style_input_decoration(mw_colors)
        btn_dec = AppStyles._style_btn_decoration(mw_colors)
        btn_dec_hover = AppStyles._style_btn_decoration(mw_colors, hover=True)
        btn_dec_pressed = AppStyles._style_btn_decoration(mw_colors, pressed=True)
        container_border = "none" if style in ('neumorphic', 'mac', 'ios') else f"1px solid {mw_colors['mid']}"
        spinbox_border = AppStyles._style_input_decoration(mw_colors)
        spinbox_focus = AppStyles._style_input_decoration(mw_colors, focus=True)
        slider_groove, slider_sub_page, slider_handle = AppStyles._style_slider_decoration(mw_colors)
        progress_bg, progress_chunk = AppStyles._style_progress_decoration(mw_colors)
        sb_track_v, sb_handle_v, sb_handle_v_hover = AppStyles._style_scrollbar_decoration(mw_colors)
        sb_track_h = sb_track_v.replace('width: 10px', 'height: 10px').replace('border: none;', 'border: none;')
        sb_handle_h = sb_handle_v.replace('min-height: 40px', 'min-width: 40px').replace('margin: 2px;', 'margin: 2px;')
        sb_handle_h_hover = sb_handle_v_hover.replace('min-height: 40px', 'min-width: 40px').replace('margin: 2px;', 'margin: 2px;')
        sb_handle_h_pressed = sb_handle_h_hover
        chk_indicator = AppStyles._style_checkbox_indicator_decoration(mw_colors)
        chk_indicator_checked = AppStyles._style_checkbox_indicator_decoration(mw_colors, checked=True)
        dock_title_dec = AppStyles._style_dock_title_decoration(mw_colors)
        tooltip_dec = AppStyles._style_tooltip_decoration(mw_colors)
        return f"""
            QMainWindow {{
                background-color: transparent;
                color: {mw_colors['window_text']};
                font-family: {ff};
                font-size: {AppStyles.fs('body')}px;
            }}
            QWidget#mainContainer {{
                background-color: {container_bg};
                border-radius: {r}px;
                border: {container_border};
            }}
            QWidget#contentArea {{
                background-color: {content_bg};
                border-bottom-left-radius: {r}px;
                border-bottom-right-radius: {r}px;
            }}
            QLabel {{
                color: {mw_colors['window_text']};
                background-color: transparent;
                font-family: {ff};
            }}
            QPushButton {{
                color: {mw_colors['window_text']};
                padding: 6px 12px;
                font-weight: 500;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                {btn_dec}
            }}
            QPushButton:hover {{
                color: {mw_colors['window_text']};
                {btn_dec_hover}
            }}
            QPushButton:pressed {{
                color: {mw_colors['window_text']};
                {btn_dec_pressed}
            }}
            QPushButton:disabled {{
                background-color: {mw_colors['light']};
                color: {mw_colors['placeholder']};
            }}
            QLineEdit {{
                color: {mw_colors['window_text']};
                padding: 6px;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                {inp_dec}
            }}
            QLineEdit:focus {{
                border-color: {mw_colors['accent']};
                outline: none;
            }}
            QComboBox {{
                color: {mw_colors['window_text']};
                padding: 6px;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                {inp_dec}
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(mw_colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {mw_colors['base']};
                color: {mw_colors['window_text']};
                selection-background-color: {mw_colors['accent']};
                selection-color: {AppStyles.COLOR_WHITE};
                border: 1px solid {mw_colors['mid']};
                outline: none;
            }}
            QTableView {{
                background-color: {mw_colors['alternate_base']};
                alternate-background-color: {mw_colors['table_alternate']};
                selection-background-color: {mw_colors['table_selection']};
                selection-color: {mw_colors['table_selection_text']};
                gridline-color: {mw_colors['table_grid']};
                color: {mw_colors['window_text']};
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
            }}
            QTableView::item {{
                padding: 6px 10px;

            }}
            QTableView::item:hover {{
                background-color: {mw_colors['table_hover']};
            }}
            QTableView::item:selected {{
                background-color: {mw_colors['table_selection']};
                color: {mw_colors['table_selection_text']};
            }}
            QHeaderView {{
                background-color: {mw_colors['table_header']};
            }}
            QHeaderView::section {{
                background-color: {mw_colors['table_header']};
                color: {mw_colors['window_text']};
                padding: 8px 12px;
                font-weight: 600;
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                border: none;
                border-right: 1px solid {mw_colors['mid']};
            }}
            QListWidget {{
                background-color: {mw_colors['alternate_base']};
                color: {mw_colors['window_text']};
                font-family: {ff};
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                color: {mw_colors['window_text']};
            }}
            QListWidget::item:hover {{
                background-color: {mw_colors['highlight']};
            }}
            QListWidget::item:selected {{
                background-color: {mw_colors['accent']};
                color: {AppStyles.COLOR_WHITE};
            }}
            QTextEdit {{
                background-color: {input_bg};
                color: {mw_colors['window_text']};
                font-family: {ff};
            }}
            QToolButton {{
                color: {mw_colors['window_text']};
                font-family: {ff};
            }}
            QSlider::groove:horizontal {{
                {slider_groove}
            }}
            QSlider::sub-page:horizontal {{
                {slider_sub_page}
            }}
            QSlider::handle:horizontal {{
                {slider_handle}
            }}
            QDockWidget {{
                color: {mw_colors['window_text']};
                font-family: {ff};
            }}
            QDockWidget::title {{
                {dock_title_dec}
                color: {mw_colors['window_text']};
            }}
            QGroupBox {{
                margin-top: 12px;
                padding-top: 16px;
                font-weight: 600;
                font-size: {AppStyles.fs('title')}px;
                color: {mw_colors['window_text']};
                font-family: {ff};
                {grp_dec}
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {mw_colors['window_text']};
                font-weight: 600;
            }}
            QSplitter::handle {{
                background-color: {mw_colors['mid']};
            }}
            QSplitter::handle:hover {{
                background-color: {mw_colors['highlight']};
            }}
            QCheckBox {{
                color: {mw_colors['window_text']};
                font-size: {AppStyles.fs('body')}px;
                font-family: {ff};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                {chk_indicator}
            }}
            QCheckBox::indicator:checked {{
                {chk_indicator_checked}
                image: url({AppStyles._get_check_image(AppStyles.COLOR_WHITE)});
            }}
            QCheckBox::indicator:hover {{
                border: 2px solid {mw_colors['accent']};
            }}
            QRadioButton {{
                color: {mw_colors['window_text']};
                font-family: {ff};
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 14px; height: 14px;
                {chk_indicator}
            }}
            QRadioButton::indicator:checked {{
                {chk_indicator_checked}
            }}
            QProgressBar {{
                {progress_bg}
                color: {mw_colors['window_text']};
                text-align: center;
                font-family: {ff};
                min-height: 8px;
            }}
            QProgressBar::chunk {{
                {progress_chunk}
            }}
            QSpinBox {{
                padding: 6px 10px;
                padding-right: 32px;
                font-size: {AppStyles.fs('body')}px;
                color: {mw_colors['window_text']};
                {spinbox_border}
            }}
            QSpinBox:focus {{
                {spinbox_focus}
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 28px;
                border: none;
                border-left: 1px solid {mw_colors['mid']};
                background-color: {mw_colors['button']};
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
                background-color: {mw_colors['accent']};
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background-color: {mw_colors['accent_pressed']};
            }}
            QSpinBox::up-arrow {{
                image: url({AppStyles._get_spin_up_image(mw_colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QSpinBox::down-arrow {{
                image: url({AppStyles._get_spin_down_image(mw_colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QSpinBox::up-button:hover::up-arrow {{
                image: url({AppStyles._get_spin_up_image(mw_colors['accent'])});
            }}
            QSpinBox::down-button:hover::down-arrow {{
                image: url({AppStyles._get_spin_down_image(mw_colors['accent'])});
            }}
            QScrollBar:vertical {{
                {sb_track_v}
                margin: 2px 0;
            }}
            QScrollBar::handle:vertical {{
                {sb_handle_v}
            }}
            QScrollBar::handle:vertical:hover {{
                {sb_handle_v_hover}
            }}
            QScrollBar::handle:vertical:pressed {{
                {sb_handle_v_hover}
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background-color: transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background-color: transparent;
            }}
            QScrollBar:horizontal {{
                {sb_track_h}
                margin: 0 2px;
            }}
            QScrollBar::handle:horizontal {{
                {sb_handle_h}
            }}
            QScrollBar::handle:horizontal:hover {{
                {sb_handle_h_hover}
            }}
            QScrollBar::handle:horizontal:pressed {{
                {sb_handle_h_pressed}
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                border: none;
                background-color: transparent;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background-color: transparent;
            }}
        """

    @staticmethod
    def status_channel_label_style() -> str:
        colors = AppStyles._get_colors()
        return f"color: {colors['window_text']}; padding: 0 8px;"

    @staticmethod
    def statusbar_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        ff = AppStyles._get_style_font_family()
        sb_bg = colors['player_panel']
        if style == 'frosted':
            sb_bg = color_to_hex(colors['player_panel'])
        if style == 'neumorphic':
            sb_dec = f"background-color: {sb_bg}; {AppStyles._get_style_raised()}"
            combo_dec = f"background-color: {colors['player_combo']}; {AppStyles._get_style_inset()} border-radius: {r}px;"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; {AppStyles._get_style_raised()} border-radius: {r}px;"
        elif style == 'skeuomorphic':
            sb_dec = f"background-color: {sb_bg}; border: 1px outset {colors.get('border_3d_light', colors['mid'])};"
            combo_dec = f"border: 1px inset {colors.get('border_3d_dark', colors['mid'])}; background-color: {colors['player_combo']}; border-radius: {r}px;"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; border: 1px outset {colors.get('border_3d_light', colors['mid'])}; border-radius: {r}px;"
        elif style == 'frosted':
            sb_dec = f"background-color: {sb_bg}; border: 1px solid {colors.get('frosted_border', colors['mid'])};"
            combo_dec = f"border: 1px solid {colors.get('frosted_border', colors['mid'])}; background-color: {colors['player_combo']}; border-radius: {r}px;"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; border: 1px solid {colors.get('frosted_border', colors['mid'])}; border-radius: {r}px;"
        elif style == 'win11':
            sb_dec = f"background-color: {sb_bg}; border-top: 1px solid {colors.get('border_thin', colors['mid'])};"
            combo_dec = f"border: 1px solid {colors.get('border_thin', colors['mid'])}; background-color: {colors['player_combo']}; border-radius: {r}px; border-bottom: 2px solid {colors['accent']};"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; border: 1px solid {colors.get('border_thin', colors['mid'])}; border-radius: {r}px;"
        elif style in ('mac', 'ios'):
            sb_dec = f"background-color: {sb_bg}; border: none;"
            combo_dec = f"border: none; background-color: {colors['player_combo']}; border-radius: {r}px;"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; border: none; border-radius: {r}px;"
        else:
            sb_dec = f"background-color: {sb_bg}; border: 1px solid {colors['mid']};"
            combo_dec = f"border: 1px solid {colors['mid']}; background-color: {colors['player_combo']}; border-radius: {r}px;"
            list_dec = "border: none; background-color: transparent;"
            btn_dec = f"background-color: {colors['player_button']}; border: 1px solid {colors.get('player_line', colors['mid'])}; border-radius: {r}px;"
        return f"""
            QStatusBar {{
                {sb_dec}
                color: {colors['player_panel_text']};
                padding: 2px 4px;
                border-bottom-left-radius: {r}px;
                border-bottom-right-radius: {r}px;
            }}

            * {{
                font-family: {ff};
            }}

            QLabel {{
                color: {colors['player_panel_text']};
                background-color: transparent;
            }}
            QListWidget {{
                {list_dec}
                color: {colors['player_panel_text']};
                outline: none;
            }}
            QComboBox {{
                {combo_dec}
                color: {colors['player_panel_text']};
                padding: 2px 6px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 16px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(colors['player_panel_secondary'])});
                width: 10px;
                height: 6px;
            }}
            QToolButton {{
                {btn_dec}
                padding: 0px;
                margin: 0px;
            }}
            QPushButton {{
                {btn_dec}
                padding: 0px;
                margin: 0px;
            }}
        """

    @staticmethod
    def player_menu_bar_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        menu_bg = colors['base']
        menu_text = colors['window_text']
        menu_hover_bg = colors['neumorphic_light'] if style == 'neumorphic' else colors['highlight']
        menu_hover_text = colors['accent'] if style == 'neumorphic' else colors['highlighted_text']
        menu_dec = AppStyles._style_menu_decoration(colors)
        item_r = max(r - 2, 4)
        if style in ('neumorphic', 'skeuomorphic'):
            item_pad = "6px 24px"
        elif style == 'ios':
            item_pad = "8px 28px"
        else:
            item_pad = "4px 20px"
        if style == 'neumorphic':
            menubar_border_bottom = f"border-bottom: 2px solid {colors['shadow_dark']};"
            menubar_item_dec = AppStyles._style_btn_decoration(colors)
        elif style == 'skeuomorphic':
            menubar_border_bottom = f"border-bottom: 1px solid {colors.get('border_3d_dark', colors['mid'])};"
            menubar_item_dec = ""
        elif style == 'win11':
            menubar_border_bottom = f"border-bottom: 1px solid {colors.get('border_thin', colors['mid'])};"
            menubar_item_dec = ""
        else:
            menubar_border_bottom = ""
            menubar_item_dec = ""
        if style == 'neumorphic':
            item_selected_dec = f"background-color: {menu_hover_bg}; {AppStyles._get_style_inset()} border-radius: {item_r}px;"
        elif style == 'skeuomorphic':
            item_selected_dec = f"background-color: {menu_hover_bg}; border: 1px inset {colors.get('border_3d_dark', colors['mid'])}; border-radius: {item_r}px;"
        elif style == 'frosted':
            item_selected_dec = f"background-color: {menu_hover_bg}; border: 1px solid {colors.get('frosted_border_mid', colors['mid'])}; border-radius: {item_r}px;"
        elif style == 'win11':
            item_selected_dec = f"background-color: {menu_hover_bg}; border-bottom: 2px solid {colors['accent']}; border-radius: {item_r}px;"
        elif style in ('mac', 'ios'):
            item_selected_dec = f"background-color: {menu_hover_bg}; border-radius: {item_r}px;"
        else:
            item_selected_dec = f"background-color: {menu_hover_bg}; border: 1px solid {colors['accent']}; border-radius: {item_r}px;"
        return f"""
            QMenuBar {{
                background-color: {menu_bg};
                color: {menu_text};
                padding: 2px;
                {menubar_border_bottom}
            }}
            QMenuBar::item {{
                padding: 4px 10px;
                margin: 2px;
                border-radius: {item_r}px;
                {menubar_item_dec}
            }}
            QMenuBar::item:selected {{
                {item_selected_dec}
                color: {menu_hover_text};
            }}
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
                {item_selected_dec}
                color: {menu_hover_text};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {colors.get('shadow_dark', colors['mid'])};
                margin: 4px 8px;
            }}
        """

    @staticmethod
    def statusbar_error_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        sb_bg = colors['player_panel']
        if style == 'frosted':
            sb_bg = color_to_hex(colors['player_panel'])
        if style == 'neumorphic':
            sb_dec = f"background-color: {sb_bg}; {AppStyles._get_style_raised()}"
        elif style == 'skeuomorphic':
            sb_dec = f"background-color: {sb_bg}; border: 1px outset {colors.get('border_3d_light', colors['mid'])};"
        elif style == 'frosted':
            sb_dec = f"background-color: {sb_bg}; border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            sb_dec = f"background-color: {sb_bg}; border-top: 1px solid {colors.get('border_thin', colors['mid'])};"
        elif style in ('mac', 'ios'):
            sb_dec = f"background-color: {sb_bg}; border: none;"
        else:
            sb_dec = f"background-color: {sb_bg}; border: none;"
        return f"""
            QStatusBar {{
                {sb_dec}
                color: {colors['error']};
                font-weight: bold;
                padding: 4px;
                border-bottom-left-radius: {r}px;
                border-bottom-right-radius: {r}px;
            }}
        """



