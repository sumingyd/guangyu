"""字幕样式对话框 - 完整的字幕样式、延迟、缩放、位置、可见性调整"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QSlider,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QColorDialog,
    QGroupBox,
    QListWidgetItem,
    QLineEdit,
    QListWidget,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import QThread

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


def _color_to_mpv(color: QColor) -> str:
    """转 #AARRGGBB 格式（mpv sub-color 等属性需要）"""
    return f"#{color.alpha():02X}{color.red():02X}{color.green():02X}{color.blue():02X}".upper()


def _mpv_to_color(s: str) -> QColor:
    """从 #AARRGGBB / #RRGGBB 解析为 QColor"""
    if not s:
        return QColor(255, 255, 255, 255)
    s = s.strip()
    if s.startswith('#'):
        s = s[1:]
    if len(s) == 8:
        a = int(s[0:2], 16)
        r = int(s[2:4], 16)
        g = int(s[4:6], 16)
        b = int(s[6:8], 16)
        return QColor(r, g, b, a)
    if len(s) == 6:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return QColor(r, g, b, 255)
    return QColor(255, 255, 255, 255)


class ColorButton(QPushButton):
    """颜色选择按钮 - 点击弹出 QColorDialog"""

    color_changed = Signal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(80)
        self._update_swatches()
        self.clicked.connect(self._on_clicked)

    def _update_swatches(self):
        c = self._color
        self.setText(f"#{c.alpha():02X}{c.red():02X}{c.green():02X}{c.blue():02X}".upper())
        self.setStyleSheet(
            f"background-color: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()}); "
            f"color: {'#000' if c.value() > 128 else '#fff'}; "
            f"padding: 4px; border-radius: 4px; border: 1px solid {AppStyles.get_color('mid')};"
        )

    def _on_clicked(self):
        try:
            from core.language_manager import LanguageManager
            title = LanguageManager().tr('select_color', '选择颜色')
        except Exception:
            title = '选择颜色'
        c = QColorDialog.getColor(self._color, self, title,
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._color = c
            self._update_swatches()
            self.color_changed.emit(c)

    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor):
        self._color = color
        self._update_swatches()


class SubtitleStyleDialog(FloatingDialog):
    """字幕样式调整对话框
    修改时实时应用到 mpv；保存按钮持久化到 config
    """

    style_saved = Signal(dict)

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('subtitle_style_title', '字幕样式'))
        self.setMinimumSize(560, 620)
        self._loading = False
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                margin-top: 12px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
            QSlider::groove:horizontal {{
                height: 4px; background: {c.get('mid')}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {c.get('accent')}; border-radius: 7px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 字幕样式组 =====
        style_group = QGroupBox(tr('sub_style_group', '字幕样式'))
        form = QFormLayout(style_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 颜色
        color_row = QHBoxLayout()
        self.color_btn = ColorButton(QColor(255, 255, 255, 255))
        self.color_btn.color_changed.connect(lambda c: self._on_style_changed('color', _color_to_mpv(c)))
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        form.addRow(tr('sub_color', '字幕颜色'), color_row)

        # 边框颜色
        bcolor_row = QHBoxLayout()
        self.border_color_btn = ColorButton(QColor(0, 0, 0, 255))
        self.border_color_btn.color_changed.connect(lambda c: self._on_style_changed('border_color', _color_to_mpv(c)))
        bcolor_row.addWidget(self.border_color_btn)
        bcolor_row.addStretch()
        form.addRow(tr('sub_border_color', '边框颜色'), bcolor_row)

        # 阴影颜色
        scolor_row = QHBoxLayout()
        self.shadow_color_btn = ColorButton(QColor(0, 0, 0, 255))
        self.shadow_color_btn.color_changed.connect(lambda c: self._on_style_changed('shadow_color', _color_to_mpv(c)))
        scolor_row.addWidget(self.shadow_color_btn)
        scolor_row.addStretch()
        form.addRow(tr('sub_shadow_color', '阴影颜色'), scolor_row)

        # 字体
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        form.addRow(tr('sub_font', '字体'), self.font_combo)

        # 字体大小
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(55)
        self.font_size_spin.valueChanged.connect(lambda v: self._on_style_changed('font_size', v))
        form.addRow(tr('sub_font_size', '字体大小'), self.font_size_spin)

        # 边框粗细
        self.border_size_spin = QSpinBox()
        self.border_size_spin.setRange(0, 20)
        self.border_size_spin.setValue(3)
        self.border_size_spin.valueChanged.connect(lambda v: self._on_style_changed('border_size', v))
        form.addRow(tr('sub_border_size', '边框粗细'), self.border_size_spin)

        # 阴影偏移
        self.shadow_offset_spin = QSpinBox()
        self.shadow_offset_spin.setRange(0, 20)
        self.shadow_offset_spin.setValue(1)
        self.shadow_offset_spin.valueChanged.connect(lambda v: self._on_style_changed('shadow_offset', v))
        form.addRow(tr('sub_shadow_offset', '阴影偏移'), self.shadow_offset_spin)

        # 加粗/斜体
        bold_row = QHBoxLayout()
        self.bold_check = QCheckBox(tr('sub_bold', '加粗'))
        self.bold_check.toggled.connect(lambda c: self._on_style_changed('bold', c))
        self.italic_check = QCheckBox(tr('sub_italic', '斜体'))
        self.italic_check.toggled.connect(lambda c: self._on_style_changed('italic', c))
        bold_row.addWidget(self.bold_check)
        bold_row.addWidget(self.italic_check)
        bold_row.addStretch()
        form.addRow(tr('sub_font_style', '字形'), bold_row)

        # 边距
        margin_row = QHBoxLayout()
        self.margin_x_spin = QSpinBox()
        self.margin_x_spin.setRange(0, 200)
        self.margin_x_spin.setValue(25)
        self.margin_x_spin.valueChanged.connect(lambda v: self._on_style_changed('margin_x', v))
        self.margin_y_spin = QSpinBox()
        self.margin_y_spin.setRange(0, 200)
        self.margin_y_spin.setValue(22)
        self.margin_y_spin.valueChanged.connect(lambda v: self._on_style_changed('margin_y', v))
        margin_row.addWidget(QLabel('X:'))
        margin_row.addWidget(self.margin_x_spin)
        margin_row.addWidget(QLabel('Y:'))
        margin_row.addWidget(self.margin_y_spin)
        margin_row.addStretch()
        form.addRow(tr('sub_margin', '边距'), margin_row)

        # 对齐
        align_row = QHBoxLayout()
        self.align_x_combo = QComboBox()
        self.align_x_combo.addItems(['left', 'center', 'right'])
        self.align_x_combo.currentTextChanged.connect(lambda v: self._on_style_changed('align_x', v))
        self.align_y_combo = QComboBox()
        self.align_y_combo.addItems(['top', 'center', 'bottom'])
        self.align_y_combo.currentTextChanged.connect(lambda v: self._on_style_changed('align_y', v))
        align_row.addWidget(QLabel('X:'))
        align_row.addWidget(self.align_x_combo)
        align_row.addWidget(QLabel('Y:'))
        align_row.addWidget(self.align_y_combo)
        align_row.addStretch()
        form.addRow(tr('sub_align', '对齐'), align_row)

        layout.addWidget(style_group)

        # ===== 字幕控制组 =====
        ctrl_group = QGroupBox(tr('sub_ctrl_group', '字幕控制'))
        ctrl_form = QFormLayout(ctrl_group)
        ctrl_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 字幕延迟
        delay_row = QHBoxLayout()
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(-300.0, 300.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setDecimals(3)
        self.delay_spin.setSuffix(' s')
        self.delay_spin.setValue(0.0)
        self.delay_spin.valueChanged.connect(self._on_delay_changed)
        delay_row.addWidget(self.delay_spin)
        delay_dec = QPushButton('-0.5s')
        delay_dec.setFixedWidth(56)
        delay_dec.clicked.connect(lambda: self._adjust_delay(-0.5))
        delay_inc = QPushButton('+0.5s')
        delay_inc.setFixedWidth(56)
        delay_inc.clicked.connect(lambda: self._adjust_delay(0.5))
        delay_row.addWidget(delay_dec)
        delay_row.addWidget(delay_inc)
        delay_row.addStretch()
        ctrl_form.addRow(tr('sub_delay', '字幕延迟'), delay_row)

        # 字幕缩放
        scale_row = QHBoxLayout()
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 10.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(1.0)
        self.scale_spin.valueChanged.connect(self._on_scale_changed)
        scale_row.addWidget(self.scale_spin)
        scale_dec = QPushButton('-0.1')
        scale_dec.setFixedWidth(56)
        scale_dec.clicked.connect(lambda: self._adjust_scale(-0.1))
        scale_inc = QPushButton('+0.1')
        scale_inc.setFixedWidth(56)
        scale_inc.clicked.connect(lambda: self._adjust_scale(0.1))
        scale_row.addWidget(scale_dec)
        scale_row.addWidget(scale_inc)
        scale_row.addStretch()
        ctrl_form.addRow(tr('sub_scale', '字幕缩放'), scale_row)

        # 字幕位置
        pos_row = QHBoxLayout()
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(0, 100)
        self.pos_slider.setValue(100)
        self.pos_label = QLabel('100')
        self.pos_label.setMinimumWidth(40)
        self.pos_slider.valueChanged.connect(lambda v: (self.pos_label.setText(str(v)), self._on_pos_changed(v)))
        pos_row.addWidget(self.pos_slider, 1)
        pos_row.addWidget(self.pos_label)
        ctrl_form.addRow(tr('sub_pos', '字幕位置'), pos_row)

        # 字幕可见性
        self.visibility_check = QCheckBox(tr('sub_visibility', '显示字幕'))
        self.visibility_check.setChecked(True)
        self.visibility_check.toggled.connect(self._on_visibility_toggled)
        ctrl_form.addRow('', self.visibility_check)

        layout.addWidget(ctrl_group)

        # ===== 预设组 =====
        preset_group = QGroupBox(tr('sub_preset_group', '快速预设'))
        preset_layout = QHBoxLayout(preset_group)
        for label, style in [
            (tr('sub_preset_default', '默认'), {
                'color': '#FFFFFFFF', 'border_color': '#FF000000', 'shadow_color': '#FF000000',
                'border_size': 3, 'shadow_offset': 1, 'bold': False, 'italic': False,
            }),
            (tr('sub_preset_yellow', '黄色描边'), {
                'color': '#FFFFFF00', 'border_color': '#FF000000', 'shadow_color': '#FF000000',
                'border_size': 2, 'shadow_offset': 1, 'bold': True, 'italic': False,
            }),
            (tr('sub_preset_outline', '粗描边'), {
                'color': '#FFFFFFFF', 'border_color': '#FF000000', 'shadow_color': '#FF000000',
                'border_size': 5, 'shadow_offset': 2, 'bold': True, 'italic': False,
            }),
            (tr('sub_preset_clean', '无阴影'), {
                'color': '#FFFFFFFF', 'border_color': '#FF000000', 'shadow_color': '#FF000000',
                'border_size': 3, 'shadow_offset': 0, 'bold': False, 'italic': False,
            }),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, s=style: self._apply_preset(s))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        layout.addWidget(preset_group)

        # ===== 操作按钮组（标准设置式：重置默认 | 应用 + 完成） =====
        def _on_done():
            self._apply_now()
            self._save()
            self.close()

        btn_bar, reset_btn, apply_now, close_btn = self.build_settings_buttons(
            self._reset, self._apply_now, _on_done,
            reset_text=tr('sub_reset', '重置默认'),
            apply_text=tr('sub_apply_now', '应用'),
            done_text=tr('sub_close', '完成'),
        )
        layout.addWidget(btn_bar)

        # 加载当前样式
        self._load_from_config()

    # ---------- 数据加载与回填 ----------
    def _load_from_config(self):
        """从 config 加载样式并回填到 UI 控件"""
        self._loading = True
        try:
            style = self.window.config.load_subtitle_style()
            self._set_ui_from_style(style)
        except Exception as e:
            logger.warning(f"加载字幕样式失败: {e}")
        finally:
            self._loading = False

    def _set_ui_from_style(self, style: dict):
        if not style:
            return
        try:
            self.color_btn.set_color(_mpv_to_color(style.get('color', '#FFFFFFFF')))
            self.border_color_btn.set_color(_mpv_to_color(style.get('border_color', '#FF000000')))
            self.shadow_color_btn.set_color(_mpv_to_color(style.get('shadow_color', '#FF000000')))
            font_name = style.get('font', 'sans-serif')
            f = QFont(font_name)
            self.font_combo.setCurrentFont(f)
            self.font_size_spin.setValue(int(style.get('font_size', 55)))
            self.border_size_spin.setValue(int(style.get('border_size', 3)))
            self.shadow_offset_spin.setValue(int(style.get('shadow_offset', 1)))
            self.bold_check.setChecked(bool(style.get('bold', False)))
            self.italic_check.setChecked(bool(style.get('italic', False)))
            self.margin_x_spin.setValue(int(style.get('margin_x', 25)))
            self.margin_y_spin.setValue(int(style.get('margin_y', 22)))
            # align_x/align_y 可能返回 'left'/'center'/'right' 或 'top'/'center'/'bottom'
            ax = style.get('align_x', 'center')
            ay = style.get('align_y', 'bottom')
            idx_x = self.align_x_combo.findText(ax)
            if idx_x >= 0:
                self.align_x_combo.setCurrentIndex(idx_x)
            idx_y = self.align_y_combo.findText(ay)
            if idx_y >= 0:
                self.align_y_combo.setCurrentIndex(idx_y)
            self.delay_spin.setValue(float(style.get('sub_delay', 0.0)))
            self.scale_spin.setValue(float(style.get('sub_scale', 1.0)))
            self.pos_slider.setValue(int(style.get('sub_pos', 100)))
            self.pos_label.setText(str(int(style.get('sub_pos', 100))))
            self.visibility_check.setChecked(bool(style.get('sub_visibility', True)))
        except Exception as e:
            logger.warning(f"回填字幕样式 UI 失败: {e}")

    def _collect_style(self) -> dict:
        """从 UI 控件收集样式字典"""
        return {
            'color': _color_to_mpv(self.color_btn.color()),
            'border_color': _color_to_mpv(self.border_color_btn.color()),
            'shadow_color': _color_to_mpv(self.shadow_color_btn.color()),
            'font': self.font_combo.currentFont().family(),
            'font_size': int(self.font_size_spin.value()),
            'border_size': int(self.border_size_spin.value()),
            'shadow_offset': int(self.shadow_offset_spin.value()),
            'bold': bool(self.bold_check.isChecked()),
            'italic': bool(self.italic_check.isChecked()),
            'margin_x': int(self.margin_x_spin.value()),
            'margin_y': int(self.margin_y_spin.value()),
            'align_x': self.align_x_combo.currentText(),
            'align_y': self.align_y_combo.currentText(),
            'sub_delay': float(self.delay_spin.value()),
            'sub_scale': float(self.scale_spin.value()),
            'sub_pos': int(self.pos_slider.value()),
            'sub_visibility': bool(self.visibility_check.isChecked()),
        }

    # ---------- 事件处理 ----------
    def _on_style_changed(self, key, value):
        if self._loading:
            return
        # 实时应用（仅 mpv，不持久化）
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.apply_sub_style({key: value})

    def _on_font_changed(self, font: QFont):
        if self._loading:
            return
        self._on_style_changed('font', font.family())

    def _on_delay_changed(self, v: float):
        if self._loading:
            return
        pc = self.window.player_controller
        if pc:
            pc.set_sub_delay(v)

    def _on_scale_changed(self, v: float):
        if self._loading:
            return
        pc = self.window.player_controller
        if pc:
            pc.set_sub_scale(v)

    def _on_pos_changed(self, v: int):
        if self._loading:
            return
        pc = self.window.player_controller
        if pc:
            pc.set_sub_pos(v)

    def _on_visibility_toggled(self, visible: bool):
        if self._loading:
            return
        pc = self.window.player_controller
        if pc:
            pc.set_sub_visibility(visible)

    def _adjust_delay(self, delta: float):
        new_v = round(self.delay_spin.value() + delta, 3)
        new_v = max(-300.0, min(300.0, new_v))
        self.delay_spin.setValue(new_v)

    def _adjust_scale(self, delta: float):
        new_v = round(self.scale_spin.value() + delta, 2)
        new_v = max(0.1, min(10.0, new_v))
        self.scale_spin.setValue(new_v)

    def _apply_preset(self, preset: dict):
        """应用预设（合并到当前样式）"""
        self._loading = True
        try:
            if 'color' in preset:
                self.color_btn.set_color(_mpv_to_color(preset['color']))
            if 'border_color' in preset:
                self.border_color_btn.set_color(_mpv_to_color(preset['border_color']))
            if 'shadow_color' in preset:
                self.shadow_color_btn.set_color(_mpv_to_color(preset['shadow_color']))
            if 'border_size' in preset:
                self.border_size_spin.setValue(int(preset['border_size']))
            if 'shadow_offset' in preset:
                self.shadow_offset_spin.setValue(int(preset['shadow_offset']))
            if 'bold' in preset:
                self.bold_check.setChecked(bool(preset['bold']))
            if 'italic' in preset:
                self.italic_check.setChecked(bool(preset['italic']))
        finally:
            self._loading = False
        # 应用到 mpv
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.apply_sub_style(preset)

    def _apply_now(self):
        """立即应用所有样式到当前播放"""
        style = self._collect_style()
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.apply_sub_style(style)
            pc.set_sub_delay(style['sub_delay'])
            pc.set_sub_scale(style['sub_scale'])
            pc.set_sub_pos(style['sub_pos'])
            pc.set_sub_visibility(style['sub_visibility'])
        if hasattr(self.window, '_show_osd_feedback'):
            tr = self.window.language_manager.tr
            self.window._show_osd_feedback(tr('sub_osd_applied', '字幕样式已应用'))

    def _save(self):
        """保存到配置文件"""
        try:
            style = self._collect_style()
            self.window.config.save_subtitle_style(style)
            self.style_saved.emit(style)
            if hasattr(self.window, '_show_osd_feedback'):
                tr = self.window.language_manager.tr
                self.window._show_osd_feedback(tr('sub_osd_saved', '字幕样式已保存'))
        except Exception as e:
            logger.error(f"保存字幕样式失败: {e}")

    def _reset(self):
        """重置为默认"""
        defaults = self.window.config.SUBTITLE_STYLE_DEFAULTS.copy()
        self._loading = True
        try:
            self._set_ui_from_style(defaults)
        finally:
            self._loading = False
        pc = self.window.player_controller
        if pc and pc.is_playing:
            pc.apply_sub_style(defaults)
            pc.set_sub_delay(defaults['sub_delay'])
            pc.set_sub_scale(defaults['sub_scale'])
            pc.set_sub_pos(defaults['sub_pos'])
            pc.set_sub_visibility(defaults['sub_visibility'])

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)


class SubtitleDownloadDialog(FloatingDialog):
    """字幕下载对话框 - 通过 OpenSubtitles 搜索并下载字幕"""

    subtitle_loaded = Signal(str)  # 下载完成的字幕路径

    def __init__(self, main_window, video_file_path: str = "", parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        self._video_path = video_file_path
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('subtitle_download_title', '在线下载字幕'))
        self.setMinimumSize(620, 460)
        from services.subtitle_download_service import SubtitleDownloadService
        self._service = SubtitleDownloadService()
        self._results = []
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        list_r = AppStyles._get_scaled_radius('list_item')
        text_color = c.get('window_text')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QListWidget {{
                background-color: transparent;
                color: {text_color};
                border: none; outline: none;
            }}
            QListWidget::item {{
                padding: 4px 6px; min-height: 28px;
                border: 1px solid transparent; border-radius: {list_r}px;
            }}
            QListWidget::item:selected {{
                background-color: {c.get('accent')}; color: {c.get('highlighted_text')};
            }}
        """)

    def _setup_ui(self):

        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 搜索条件
        search_row = QHBoxLayout()
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText(tr('sub_search_placeholder', '片名 / 文件名（留空按文件哈希搜索）'))
        if self._video_path:
            import os
            self.query_edit.setText(os.path.splitext(os.path.basename(self._video_path))[0])
        search_row.addWidget(self.query_edit, 1)
        self.lang_combo = QComboBox()
        # 语言代码 - 显示名（默认"全部"，避免过滤掉中文字幕）
        self.lang_combo.addItem(tr('sub_lang_all', '全部') + ' (all)', 'all')
        self.lang_combo.addItem(tr('sub_lang_cjk', '中日韩') + ' (eng,chi,jpn)', 'eng,chi,jpn')
        self.lang_combo.addItem(tr('sub_lang_chi', '中文') + ' (chi)', 'chi')
        self.lang_combo.addItem(tr('sub_lang_eng', '英语') + ' (eng)', 'eng')
        search_row.addWidget(self.lang_combo, 0)
        self.search_btn = QPushButton(tr('sub_search', '搜索'))
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)
        layout.addLayout(search_row)

        # 结果列表
        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.result_list, 1)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # 状态
        self.status_label = QLabel('')
        layout.addWidget(self.status_label)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.download_btn = QPushButton(tr('sub_download', '下载并加载'))
        self.download_btn.clicked.connect(self._download_selected)
        close_btn = QPushButton(tr('sub_close', '关闭'))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(self.download_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ---------- 搜索 ----------
    def _do_search(self):
        query = self.query_edit.text().strip()
        lang = self.lang_combo.currentData() or 'eng'
        self.result_list.clear()
        self._results = []
        self.progress.setVisible(True)
        self.search_btn.setEnabled(False)
        self.status_label.setText(self.window.language_manager.tr('sub_searching', '正在搜索...'))

        class _Worker(QThread):
            done = Signal(list)

            def __init__(self, service, query, lang, file_path):
                super().__init__()
                self._service = service
                self._query = query
                self._lang = lang
                self._file = file_path

            def run(self):
                try:
                    items = self._service.search(self._query, language=self._lang,
                                                file_path=self._file)
                except Exception:
                    items = []
                self.done.emit(items)

        self._worker = _Worker(self._service, query, lang, self._video_path)
        self._worker.done.connect(self._on_search_done)
        self._worker.start()

    def _on_search_done(self, items: list):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        tr = self.window.language_manager.tr
        self._results = items
        if not items:
            # 区分"真没找到"和"出错"，让用户知道是网络问题还是真的没字幕
            err = getattr(self._service, 'last_error', '') or ''
            if err:
                self.status_label.setText(tr('sub_search_error', '搜索失败') + f': {err}')
            else:
                self.status_label.setText(tr('sub_no_results', '没有找到字幕'))
            return
        self.status_label.setText(tr('sub_results_count', '找到 {} 条结果').format(len(items)))
        for it in items:
            # 来源标识 + 语言 + 文件名 + 影片名 + 下载数 + 下载方式
            source = it.get('source', '?')
            lang = it.get('language', '') or '?'
            fname = it.get('file_name', '') or ''
            movie = it.get('movie_name', '') or ''
            dl_count = it.get('download_count', 0)
            auto_dl = it.get('auto_download', True)
            # 下载方式提示：自动下载 / 浏览器跳转
            dl_mode = tr('sub_auto_dl', '自动下载') if auto_dl else tr('sub_browser_dl', '浏览器下载')
            label = f"[{source}] [{lang}] {fname}"
            if movie and movie != fname:
                label += f"  · {movie}"
            label += f"  · {tr('sub_downloads', '下载')}={dl_count}  · [{dl_mode}]"
            if it.get('bad'):
                label += f"  [{tr('sub_bad', '劣质')}]"
            qi = QListWidgetItem(label)
            self.result_list.addItem(qi)

    # ---------- 下载 ----------
    def _on_item_double_clicked(self, item):
        self._download_selected()

    def _download_selected(self):
        row = self.result_list.currentRow()
        if row < 0 or row >= len(self._results):
            return
        it = self._results[row]
        if not it.get('download_link'):
            return
        tr = self.window.language_manager.tr

        # SubHD 等不支持自动下载的源：跳转浏览器
        if not it.get('auto_download', True):
            detail_url = it.get('detail_url') or it.get('download_link', '')
            if detail_url and self._service.open_in_browser(detail_url):
                self.status_label.setText(
                    tr('sub_open_browser_hint', '已在浏览器打开详情页，请手动下载字幕'))
            else:
                self.status_label.setText(tr('sub_dl_failed', '下载失败'))
            return

        # OpenSubtitles / SubtitleCat：自动下载
        self.progress.setVisible(True)
        self.download_btn.setEnabled(False)
        self.status_label.setText(tr('sub_downloading', '正在下载...'))

        # 获取当前语言选择（SubtitleCat 下载需要）
        language = self.lang_combo.currentData() or 'all'


        class _DLWorker(QThread):
            done = Signal(str)

            def __init__(self, service, link, dest_dir, fname, lang):
                super().__init__()
                self._service = service
                self._link = link
                self._dest = dest_dir
                self._fname = fname
                self._lang = lang

            def run(self):
                try:
                    path = self._service.download(self._link, self._dest, self._fname,
                                                  language=self._lang)
                except Exception:
                    path = ''
                self.done.emit(path)

        # 目标目录：和视频文件同目录
        import os
        if self._video_path:
            dest_dir = os.path.dirname(self._video_path)
        else:
            dest_dir = os.path.join(os.getcwd(), 'subtitles')
        fname = it.get('file_name') or 'subtitle.srt'
        self._dl_worker = _DLWorker(self._service, it['download_link'], dest_dir, fname, language)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.start()

    def _on_download_done(self, path: str):
        self.progress.setVisible(False)
        self.download_btn.setEnabled(True)
        tr = self.window.language_manager.tr
        if not path:
            self.status_label.setText(tr('sub_dl_failed', '下载失败'))
            return
        self.status_label.setText(tr('sub_dl_ok', '下载完成：{}').format(path))
        # 加载到播放器
        pc = self.window.player_controller
        if pc and pc.is_playing:
            if pc.add_subtitle_file(path):
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('sub_loaded', '字幕已加载'))
        self.subtitle_loaded.emit(path)

    def closeEvent(self, event):
        for worker_attr in ('_worker', '_dl_worker'):
            worker = getattr(self, worker_attr, None)
            if worker and worker.isRunning():
                try:
                    worker.requestInterruption()
                    worker.quit()
                    worker.wait(2000)
                except Exception as e:
                    logger.debug(f"closeEvent: {e}")
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
