"""3D / 360° 视频对话框 - 立体模式选择与 360° 视角控制"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSlider, QComboBox, QGroupBox, QWidget,
)
from PySide6.QtCore import Qt

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


class Video3DDialog(FloatingDialog):
    """3D / 360° 视频对话框
    - 3D 立体模式选择（mono / SBS-L / SBS-R / TB-F / TB-S）
    - 360° 视频视角控制（yaw / pitch / roll + 投影方式）
    """

    # 3D 立体模式（mpv video-stereo-mode 取值）
    _STEREO_ITEMS = (
        ('mono', 'video_3d_stereo_mono', '普通 2D'),
        ('sbs',  'video_3d_stereo_sbs_l', '左右并排 - 左眼优先'),
        ('sbs2', 'video_3d_stereo_sbs_r', '左右并排 - 右眼优先'),
        ('ab',   'video_3d_stereo_tb_f',  '上下并排 - 上前'),
        ('ab2',  'video_3d_stereo_tb_s',  '上下并排 - 下前'),
    )

    # 360° 投影方式
    _PROJ_ITEMS = (
        ('equirect', 'video_3d_proj_equirect', 'Equirectangular (等距柱状)'),
        ('cubemap',  'video_3d_proj_cubemap',  'Cubemap (立方体贴图)'),
        ('flat',     'video_3d_proj_flat',     'Flat (平面)'),
    )

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('video_3d_title', '3D / 360° 视频'))
        self.setMinimumSize(520, 480)
        self._loading = False
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 初始回填当前 mpv 状态
        self._reload_from_player()

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
                background: {c.get('accent')};
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 3D 立体模式组 =====
        stereo_group = QGroupBox(tr('video_3d_group_stereo', '3D 立体模式'))
        sform = QFormLayout(stereo_group)
        sform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.stereo_combo = QComboBox()
        for mode, key, fallback in self._STEREO_ITEMS:
            self.stereo_combo.addItem(tr(key, fallback), mode)
        self.stereo_combo.currentIndexChanged.connect(self._on_stereo_changed)
        sform.addRow(tr('video_3d_stereo_label', '模式:'), self.stereo_combo)

        self.stereo_hint = QLabel(tr('video_3d_stereo_hint',
            '选择与片源匹配的 3D 格式；普通 2D 视频请选择"普通 2D"'))
        self.stereo_hint.setWordWrap(True)
        self.stereo_hint.setStyleSheet("font-size: 11px; opacity: 0.75;")
        sform.addRow('', self.stereo_hint)

        layout.addWidget(stereo_group)

        # ===== 360° 视角控制组 =====
        view_group = QGroupBox(tr('video_3d_group_360', '360° 视角控制'))
        vform = QFormLayout(view_group)
        vform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 投影方式
        self.proj_combo = QComboBox()
        for proj, key, fallback in self._PROJ_ITEMS:
            self.proj_combo.addItem(tr(key, fallback), proj)
        self.proj_combo.currentIndexChanged.connect(self._on_360_changed)
        vform.addRow(tr('video_3d_proj_label', '投影:'), self.proj_combo)

        # Yaw 滑块（偏航 -180~180）
        self.yaw_slider, self.yaw_value = self._make_angle_slider(
            -180, 180, 0, 'video_3d_yaw', 'Yaw', self._on_360_changed)
        vform.addRow(tr('video_3d_yaw', '偏航 (Yaw):'), self.yaw_slider)

        # Pitch 滑块（俯仰 -90~90）
        self.pitch_slider, self.pitch_value = self._make_angle_slider(
            -90, 90, 0, 'video_3d_pitch', 'Pitch', self._on_360_changed)
        vform.addRow(tr('video_3d_pitch', '俯仰 (Pitch):'), self.pitch_slider)

        # Roll 滑块（滚转 -180~180）
        self.roll_slider, self.roll_value = self._make_angle_slider(
            -180, 180, 0, 'video_3d_roll', 'Roll', self._on_360_changed)
        vform.addRow(tr('video_3d_roll', '滚转 (Roll):'), self.roll_slider)

        self.view_hint = QLabel(tr('video_3d_360_hint',
            '360° 视角控制依赖 lavfi panorama 滤镜，部分版本可能不支持'))
        self.view_hint.setWordWrap(True)
        self.view_hint.setStyleSheet("font-size: 11px; opacity: 0.75;")
        vform.addRow('', self.view_hint)

        layout.addWidget(view_group)

        # ===== 操作按钮 =====
        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton(tr('video_3d_reset', '重置全部'))
        self.reset_btn.clicked.connect(self._reset_all)
        self.reset_btn.setToolTip(tr('reset_3d_tooltip', '重置3D设置'))
        self.apply_btn = QPushButton(tr('video_3d_apply', '应用'))
        self.apply_btn.clicked.connect(self._apply_now)
        self.apply_btn.setToolTip(tr('apply_3d_tooltip', '应用3D设置'))
        self.close_btn = QPushButton(tr('video_3d_close', '关闭'))
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setToolTip(tr('close_tooltip', '关闭'))
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    def _make_angle_slider(self, lo, hi, default, key, fallback, callback):
        """构造角度滑块（整数度数），返回 (container, value_label)"""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setSingleStep(1)
        slider.setPageStep(10)
        slider.setValue(default)
        value_label = QLabel(f"{default}°")
        value_label.setMinimumWidth(48)
        slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(f"{v}°"))
        slider.valueChanged.connect(callback)
        row = QHBoxLayout()
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        container = QWidget()
        container.setLayout(row)
        # 通过属性附加滑块引用
        container.slider = slider
        container.value_label = value_label
        return container, value_label

    # ---------- 数据加载 ----------
    def _reload_from_player(self):
        """从 mpv 读取当前状态并回填 UI"""
        pc = getattr(self.window, 'player_controller', None)
        if not pc or not pc.is_playing:
            return
        self._loading = True
        try:
            # 3D 模式
            mode = pc.get_video_stereo_mode() if hasattr(pc, 'get_video_stereo_mode') else 'mono'
            idx = self.stereo_combo.findData(mode)
            if idx >= 0:
                self.stereo_combo.setCurrentIndex(idx)
            # 360° 视角
            view = pc.get_360_view() if hasattr(pc, 'get_360_view') else None
            if view:
                idx = self.proj_combo.findData(view.get('projection', 'equirect'))
                if idx >= 0:
                    self.proj_combo.setCurrentIndex(idx)
                self.yaw_slider.slider.setValue(int(round(view.get('yaw', 0.0))))
                self.pitch_slider.slider.setValue(int(round(view.get('pitch', 0.0))))
                self.roll_slider.slider.setValue(int(round(view.get('roll', 0.0))))
        except Exception as e:
            logger.debug(f"加载 3D/360 状态失败: {e}")
        finally:
            self._loading = False

    # ---------- 事件处理 ----------
    def _on_stereo_changed(self, idx: int):
        if self._loading:
            return
        pc = getattr(self.window, 'player_controller', None)
        if not pc or not pc.is_playing or not hasattr(pc, 'set_video_stereo_mode'):
            return
        mode = self.stereo_combo.currentData() or 'mono'
        if pc.set_video_stereo_mode(mode):
            tr = self.window.language_manager.tr
            label = self.stereo_combo.currentText()
            self._show_osd(f"{tr('osd_video_3d_mode', '3D Mode')}: {label}")

    def _on_360_changed(self):
        if self._loading:
            return
        pc = getattr(self.window, 'player_controller', None)
        if not pc or not pc.is_playing or not hasattr(pc, 'set_360_view'):
            return
        yaw = self.yaw_slider.slider.value()
        pitch = self.pitch_slider.slider.value()
        roll = self.roll_slider.slider.value()
        proj = self.proj_combo.currentData() or 'equirect'
        if pc.set_360_view(yaw, pitch, roll, proj):
            tr = self.window.language_manager.tr
            self._show_osd(f"{tr('osd_video_360_view', '360° View')}: "
                          f"Y={yaw}° P={pitch}° R={roll}°")

    def _apply_now(self):
        """显式应用当前设置"""
        self._on_stereo_changed(self.stereo_combo.currentIndex())
        self._on_360_changed()

    def _reset_all(self):
        """重置全部为默认"""
        self._loading = True
        try:
            self.stereo_combo.setCurrentIndex(0)
            self.proj_combo.setCurrentIndex(0)
            self.yaw_slider.slider.setValue(0)
            self.pitch_slider.slider.setValue(0)
            self.roll_slider.slider.setValue(0)
        finally:
            self._loading = False
        # 应用到 mpv
        pc = getattr(self.window, 'player_controller', None)
        if pc and pc.is_playing:
            if hasattr(pc, 'set_video_stereo_mode'):
                pc.set_video_stereo_mode('mono')
            if hasattr(pc, 'clear_360_filter'):
                pc.clear_360_filter()
        tr = self.window.language_manager.tr
        self._show_osd(tr('osd_video_3d_reset', '3D/360 已重置'))

    # ---------- 辅助 ----------
    def _show_osd(self, text: str):
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(text)

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
