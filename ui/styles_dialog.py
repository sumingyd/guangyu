"""对话框/列表/表格样式方法。"""
from ui.styles_base import StylesBase, rgba_to_blended_hex


class StylesDialog(StylesBase):
    """对话框/列表/表格样式方法。"""

    @staticmethod
    def list_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        if style == 'neumorphic':
            tv_border = f"border: none; {AppStyles._get_style_inset()}"
        elif style == 'skeuomorphic':
            tv_border = f"border: 2px outset {colors.get('border_3d_light', colors['mid'])};"
        elif style == 'frosted':
            tv_border = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            tv_border = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
        elif style in ('mac', 'ios'):
            tv_border = "border: none;"
        else:
            tv_border = f"border: 2px solid {colors['table_border']};"
        hdr_sep = colors['shadow_dark'] if style in ('neumorphic', 'skeuomorphic') else colors['table_border']
        list_r = AppStyles._get_scaled_radius('list_item')
        return f"""
            QTableView {{
                {tv_border}
                border-radius: {r}px;
                alternate-background-color: {colors['table_alternate']};
                selection-background-color: {colors['table_selection']};
                selection-color: {colors['table_selection_text']};
                gridline-color: {colors['table_grid']};
                font-size: 12px;
                font-family: {ff};
                background-color: {colors['alternate_base']};
            }}
            QTableView::item {{
                padding: 6px 10px;
                border-bottom: 1px solid {colors['table_grid']};

            }}
            QTableView::item:hover {{
                background-color: {colors['table_hover']};
                border: 1px solid {colors['accent']};
                border-radius: {list_r}px;
            }}
            QTableView::item:selected {{
                background-color: {colors['table_selection']};
                color: {colors['table_selection_text']};
                font-weight: 500;
                border: 1px solid {colors['accent_pressed']};
                border-radius: {list_r}px;
            }}
            QTableView::item:selected:hover {{
                background-color: {colors['accent_hover']};
                border-color: {colors['accent_pressed']};
            }}
            QHeaderView {{
                background-color: {colors['table_header']};
                border: none;
            }}
            QHeaderView::section {{
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['table_header_gradient_start']},
                    stop:0.5 {colors['table_header_gradient_middle']},
                    stop:1 {colors['table_header_gradient_end']});
                padding: 8px 12px;
                border: none;
                border-right: 1px solid {hdr_sep};
                color: {colors['window_text']};
                font-weight: 600;
                font-size: 12px;
                font-family: {ff};
            }}
            QHeaderView::section:hover {{
                background-color: {colors['table_hover']};
            }}
            QHeaderView::up-arrow {{
                image: url({AppStyles._get_sort_up_image(colors['window_text'])});
                width: 10px;
                height: 8px;
            }}
            QHeaderView::down-arrow {{
                image: url({AppStyles._get_sort_down_image(colors['window_text'])});
                width: 10px;
                height: 8px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QHeaderView::section:first {{ min-width: 60px; }}
            QHeaderView::section:nth-child(2) {{ min-width: 180px; }}
            QHeaderView::section:nth-child(3) {{ min-width: 100px; }}
            QHeaderView::section:nth-child(4) {{ min-width: 250px; }}
            QTableView::item:drag {{
                background-color: {colors['table_selection']};
                color: {colors['table_selection_text']};
                border: 2px dashed {colors['accent_pressed']};
                border-radius: {list_r}px;
                opacity: 0.7;
            }}
            QTableView::item:drop {{
                background-color: {colors['table_hover']};
                border: 2px solid {colors['accent']};
                border-radius: {list_r}px;
            }}
        """

    @staticmethod
    def popup_dialog_style() -> str:
        colors = AppStyles._get_colors()
        style = AppStyles._visual_style
        if style == 'frosted':
            effective_mode = AppStyles._get_effective_color_mode()
            bg = (0, 0, 0) if effective_mode == 'dark' else (255, 255, 255)
            dlg_colors = {}
            for k, v in colors.items():
                dlg_colors[k] = rgba_to_blended_hex(v, bg) if isinstance(v, str) and v.startswith('rgba') else v
        else:
            dlg_colors = colors
        window_bg = dlg_colors['player_panel']
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        btn_dec = AppStyles._style_btn_decoration(dlg_colors)
        btn_hover = AppStyles._style_btn_decoration(dlg_colors, hover=True)
        btn_pressed = AppStyles._style_btn_decoration(dlg_colors, pressed=True)
        inp_dec = AppStyles._style_input_decoration(dlg_colors)
        inp_focus = AppStyles._style_input_decoration(dlg_colors, focus=True)
        grp_dec = AppStyles._style_group_decoration(dlg_colors)
        chk_bg = dlg_colors['neumorphic_light'] if style == 'neumorphic' else dlg_colors['alternate_base']
        chk_inset = AppStyles._get_style_inset() if style == 'neumorphic' else ""
        chk_border = f"2px solid {dlg_colors['mid']}" if style != 'neumorphic' else ""
        input_bg = dlg_colors['neumorphic_light'] if style == 'neumorphic' else dlg_colors['alternate_base']
        dialog_r = r + 4 if r > 4 else 12
        indicator_r = AppStyles._get_scaled_radius('indicator')
        list_item_r = AppStyles._get_scaled_radius('list_item')
        return f"""
            QDialog {{
                background-color: transparent;
                color: {dlg_colors['window_text']};
                border: 1px solid {dlg_colors['mid']};
                border-radius: {dialog_r}px;
                font-family: {ff};
            }}
            QDialog > QWidget {{
                background-color: transparent;
                border-radius: {dialog_r}px;
            }}
            QDialog QLabel {{
                color: {dlg_colors['window_text']};
                font-size: 12px;
            }}
            QDialog QPushButton {{
                min-width: 70px;
                padding: {AppStyles._style_padding('button')};
                font-size: 12px;
                font-weight: 500;
                color: {dlg_colors['window_text']};
                {btn_dec}
            }}
            QDialog QPushButton:hover {{
                {btn_hover}
            }}
            QDialog QPushButton:pressed {{
                {btn_pressed}
            }}
            QDialog QGroupBox {{
                margin-top: 12px;
                padding-top: 18px;
                {grp_dec}
            }}
            QDialog QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {dlg_colors['window_text']};
                font-weight: 600;
                font-size: 12px;
            }}
            QDialog QLineEdit, QDialog QComboBox {{
                padding: {AppStyles._style_padding('input')};
                font-size: 12px;
                color: {dlg_colors['window_text']};
                {inp_dec}
            }}
            QDialog QLineEdit:focus, QDialog QComboBox:focus {{
                {inp_focus}
            }}
            QDialog QComboBox QAbstractItemView {{
                background-color: {dlg_colors['window']};
                color: {dlg_colors['window_text']};
                border: 1px solid {dlg_colors['mid']};
                border-radius: {list_item_r}px;
            }}
            QDialog QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 20px;
                border: none;
            }}
            QDialog QComboBox::down-arrow {{
                image: url({AppStyles._get_arrow_image(dlg_colors['window_text'])});
                width: 10px;
                height: 6px;
            }}
            QDialog QCheckBox {{
                color: {dlg_colors['window_text']};
                font-size: 12px;
                font-family: {ff};
                spacing: 8px;
            }}
            QDialog QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: {indicator_r}px;
                background-color: {chk_bg};
                {chk_inset}
                border: {chk_border};
            }}
            QDialog QCheckBox::indicator:checked {{
                background-color: {dlg_colors['accent']};
                border: 2px solid {dlg_colors['accent']};
                border-radius: {indicator_r}px;
                image: url({AppStyles._get_check_image(AppStyles.COLOR_WHITE)});
            }}
            QDialog QCheckBox::indicator:hover {{
                border: 2px solid {dlg_colors['accent']};
                border-radius: {indicator_r}px;
            }}
            QDialog QCheckBox::indicator:pressed {{
                background-color: {dlg_colors['accent_pressed']};
                border: 2px solid {dlg_colors['accent_pressed']};
                border-radius: {indicator_r}px;
            }}
            QDialog QTextEdit {{
                padding: 10px;
                font-size: 12px;
                color: {dlg_colors['window_text']};
                {inp_dec}
            }}
            QDialog QTextEdit:focus {{
                {inp_focus}
            }}
            QDialog QListWidget {{
                background-color: {input_bg};
                color: {dlg_colors['window_text']};
                border: 1px solid {dlg_colors['mid']};
                border-radius: {r}px;
            }}
            QDialog QListWidget::item {{
                padding: 4px 8px;
                border-radius: {list_item_r}px;
            }}
            QDialog QListWidget::item:selected {{
                background-color: {dlg_colors['accent']};
                color: {dlg_colors['bright_text']};
            }}
            QDialog QListWidget::item:hover {{
                background-color: {dlg_colors['button']};
            }}
            QDialog QListWidget::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {dlg_colors['mid']};
                border-radius: {indicator_r}px;
                background-color: {input_bg};
            }}
            QDialog QListWidget::indicator:checked {{
                background-color: {dlg_colors['accent']};
                border-color: {dlg_colors['accent']};
                image: url({AppStyles._get_check_image(dlg_colors['bright_text'])});
            }}
            QDialog QListWidget::indicator:hover {{
                border-color: {dlg_colors['accent']};
            }}
            QDialog QTabWidget::pane {{
                border: 1px solid {dlg_colors['mid']};
                border-radius: {r}px;
                background-color: {dlg_colors['window']};
                margin-top: -1px;
            }}
            QDialog QTabBar {{
                background-color: transparent;
            }}
            QDialog QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QDialog QScrollArea > QWidget > QWidget {{
                background-color: transparent;
            }}
        """

    @staticmethod
    def dialog_style() -> str:
        return AppStyles.popup_dialog_style()

    @staticmethod
    def progress_style() -> str:
        colors = AppStyles._get_qss_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        if style == 'neumorphic':
            progress_border = AppStyles._get_style_inset()
        elif style == 'skeuomorphic':
            progress_border = f"border: 2px inset {colors.get('border_3d_dark', colors['mid'])};"
        elif style in ('mac', 'ios'):
            progress_border = "border: none;"
        elif style == 'frosted':
            progress_border = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
        elif style == 'win11':
            progress_border = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
        else:
            progress_border = f"border: 1px solid {colors['mid']};"
        return f"""
            QProgressBar {{
                {progress_border}
                border-radius: {r}px;
                text-align: center;
                height: 24px;
                background-color: {colors['alternate_base']};
                font-size: 11px;
                font-weight: 500;
                font-family: {ff};
                color: {colors['window_text']};
            }}
            QProgressBar::chunk {{
                background-color: {colors['accent']};
                border-radius: {max(r-1, 3)}px;
                margin: 1px;
            }}
        """

    @staticmethod
    def drag_list_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        if style == 'neumorphic':
            list_border = f"border: none; {AppStyles._get_style_inset()}"
            item_bg = colors['neumorphic_light']
            item_dec = AppStyles._get_style_raised()
        elif style == 'skeuomorphic':
            list_border = f"border: 2px outset {colors.get('border_3d_light', colors['mid'])};"
            item_bg = f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {colors.get('gradient_start', colors['light'])}, stop:1 {colors['button']})"
            item_dec = ""
        elif style == 'frosted':
            list_border = f"border: 1px solid {colors.get('frosted_border', colors['mid'])};"
            item_bg = colors['light']
            item_dec = ""
        elif style == 'win11':
            list_border = f"border: 1px solid {colors.get('border_thin', colors['mid'])};"
            item_bg = colors['light']
            item_dec = ""
        elif style in ('mac', 'ios'):
            list_border = "border: none;"
            item_bg = colors['light']
            item_dec = ""
        else:
            list_border = f"border: 1px solid {colors['mid']};"
            item_bg = colors['light']
            item_dec = ""
        item_r = max(r - 2, 4)
        return f"""
            QListWidget {{
                {list_border}
                border-radius: {r}px;
                padding: 4px;
                background-color: {colors['alternate_base']};
                font-size: 13px;
            }}
            QListWidget::item {{
                border: 1px solid transparent;
                border-radius: {item_r}px;
                padding: 8px 12px;
                margin: 2px;
                background-color: {item_bg};
                color: {colors['window_text']};
                {item_dec}
            }}
            QListWidget::item:hover {{
                background-color: {colors['highlight']};
                border: 1px solid {colors['mid']};
            }}
            QListWidget::item:selected {{
                background-color: {colors['accent']};
                color: {AppStyles.COLOR_WHITE};
                border: 1px solid {colors['accent_pressed']};
            }}
            QListWidget::item:selected:hover {{
                background-color: {colors['accent_hover']};
            }}
        """

    @staticmethod
    def drag_hint_label_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        btn_dec = AppStyles._style_btn_decoration(colors)
        return f"""
            QLabel {{
                color: {colors['accent']};
                font-size: 12px;
                padding: 8px 12px;
                font-weight: 500;
                {btn_dec}
            }}
        """

    @staticmethod
    def group_hint_label_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        btn_dec = AppStyles._style_btn_decoration(colors)
        return f"""
            QLabel {{
                color: {colors['window_text']};
                font-size: 12px;
                padding: 8px 12px;
                font-weight: 500;
                {btn_dec}
                opacity: 0.8;
            }}
        """

    @staticmethod
    def tab_widget_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        ff = AppStyles._get_style_font_family()
        style = AppStyles._visual_style
        grp_dec = AppStyles._style_group_decoration(colors)
        if style in ('neumorphic', 'mac', 'ios', 'frosted'):
            tab_border = "none"
            pane_border = "none"
            tabbar_bottom = "none"
        else:
            tab_border = f"1px solid {colors['mid']}"
            pane_border = f"1px solid {colors['mid']}"
            tabbar_bottom = f"1px solid {colors['mid']}"
        tab_r = max(r - 2, 4)
        if style == 'neumorphic':
            tab_selected_dec = AppStyles._get_style_raised()
            tab_selected_bg = colors['neumorphic_light']
        elif style == 'skeuomorphic':
            tab_selected_dec = f"border: 2px outset {colors.get('border_3d_light', colors['mid'])};"
            tab_selected_bg = colors.get('gradient_start', colors['window'])
        elif style in ('mac', 'ios'):
            tab_selected_dec = ""
            tab_selected_bg = colors['window']
        else:
            tab_selected_dec = ""
            tab_selected_bg = colors['window']
        return f"""
            QTabWidget {{
                background-color: {colors['window']};
                border: {tab_border};
                border-radius: {r}px;
                font-family: {ff};
            }}
            QTabWidget::pane {{
                border: {pane_border};
                border-radius: 0 0 {r}px {r}px;
                background-color: {colors['window']};
                margin-top: -1px;
            }}
            QTabBar {{
                background-color: {colors['alternate_base']};
                border-bottom: {tabbar_bottom};
                border-radius: {r}px {r}px 0 0;
            }}
            QTabBar::tab {{
                background-color: {colors['alternate_base']};
                border: {tab_border};
                border-bottom: none;
                border-radius: {tab_r}px {tab_r}px 0 0;
                padding: 6px 16px;
                margin-right: 4px;
                margin-top: 4px;
                font-size: 12px;
                font-weight: 500;
                color: {colors['window_text']};
            }}
            QTabBar::tab:selected {{
                background-color: {tab_selected_bg};
                border-color: {colors['mid']};
                border-bottom-color: {colors['window']};
                color: {colors['accent']};
                font-weight: 600;
                {tab_selected_dec}
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {colors['light']};
                color: {colors['accent']};
            }}
            QTabBar::tab:focus {{
                color: {colors['accent']};
                border-color: {colors['accent']};
            }}
            QTabBar::tab:first {{
                margin-left: 4px;
            }}
            QTabBar::tab:last {{
                margin-right: 0;
            }}
        """

    @staticmethod
    def table_style() -> str:
        return AppStyles.list_style()

    @staticmethod
    def close_confirm_dialog_style() -> str:
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        c = colors
        return f"""
            QMessageBox {{
                background-color: {c.get('panel', c['base'])};
                color: {c.get('window_text', AppStyles._safe_fallback('window_text'))};
            }}
            QLabel {{
                color: {c.get('window_text', AppStyles._safe_fallback('window_text'))};
                background-color: transparent;
            }}
            QPushButton {{
                background-color: {c.get('player_button', c['button'])};
                color: {c.get('window_text', AppStyles._safe_fallback('window_text'))};
                border: 1px solid {c.get('player_line', c['mid'])};
                border-radius: {r}px;
                padding: 4px 16px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {c.get('accent', AppStyles._safe_fallback('accent'))};
            }}
            QCheckBox {{
                color: {c.get('window_text', AppStyles._safe_fallback('window_text'))};
                background-color: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {c.get('player_line', c['mid'])};
                border-radius: 3px;
                background-color: {c.get('player_button', c['button'])};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c.get('accent', AppStyles._safe_fallback('accent'))};
                border-color: {c.get('accent', AppStyles._safe_fallback('accent'))};
            }}
        """


