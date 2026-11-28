"""音频调整对话框 - 延迟/声道/设备/音调补偿 + 声道电平表 + 10 段均衡器"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QComboBox, QGroupBox, QWidget,
    QGridLayout, QProgressBar, QScrollArea, QFrame, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtCore import QTimer as _QTimer

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class ChannelVUMeter(QWidget):
    """单个声道 VU 电平表（竖条 + 名称 + dB 值）"""

    def __init__(self, ch_name: str, display_name: str, parent=None):
        super().__init__(parent)
        self._ch_name = ch_name
        self._display_name = display_name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # 声道名称
        name_lbl = QLabel(display_name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet("font-size: 10px; border: none;")
        layout.addWidget(name_lbl)

        # 电平条
        self._bar = QProgressBar()
        self._bar.setOrientation(Qt.Orientation.Vertical)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(100)
        self._bar.setFixedWidth(24)
        colors = AppStyles._get_colors()
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {colors.get('mid')};
                border-radius: 3px;
                background: {colors.get('alternate_base')};
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background: qlineargradient(
                    y1: 1, y2: 0,
                    stop: 0.0 {colors.get('success')},
                    stop: 0.6 {colors.get('success')},
                    stop: 0.8 {colors.get('warning')},
                    stop: 1.0 {colors.get('error')}
                );
            }}
        """)
        layout.addWidget(self._bar, 1)

        # dB 值
        self._db_label = QLabel('-∞')
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._db_label.setStyleSheet("font-size: 9px; border: none;")
        self._db_label.setFixedWidth(50)
        layout.addWidget(self._db_label)

    def set_level(self, level_db: float | None):
        """设置电平
        level_db: RMS 电平 dB 值，None 表示无声
        """
        import math
        if level_db is None or math.isnan(level_db) or level_db <= -60:
            self._bar.setValue(0)
            self._db_label.setText('-∞')
        else:
            # -60dB → 0%, 0dB → 100%
            pct = max(0, min(100, int((level_db + 60) * 100 / 60)))
            self._bar.setValue(pct)
            self._db_label.setText(f'{level_db:.1f}')

    def reset(self):
        self._bar.setValue(0)
        self._db_label.setText('-∞')


# EQ 预设
EQ_PRESETS = {
    'flat':       [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    'bass':       [8, 6, 4, 2, 0, 0, 0, 0, 0, 0],
    'treble':     [0, 0, 0, 0, 0, 2, 4, 6, 8, 8],
    'vocal':      [-2, -2, 0, 2, 4, 4, 3, 1, 0, -1],
    'classical':  [3, 2, 1, 0, -1, -1, 0, 2, 3, 3],
    'pop':        [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2],
    'rock':       [5, 3, 1, 0, -1, -1, 1, 3, 4, 4],
    'electronic': [4, 3, 0, -2, -2, 1, 2, 3, 4, 5],
}

# 声道布局选项
CHANNEL_OPTIONS = [
    ('auto', 'Auto'),
    ('mono', 'Mono'),
    ('1.0', '1.0'),
    ('2.0', '2.0 (Stereo)'),
    ('2.1', '2.1'),
    ('3.0', '3.0'),
    ('4.0', '4.0'),
    ('5.0', '5.0'),
    ('5.1', '5.1'),
    ('6.0', '6.0'),
    ('6.1', '6.1'),
    ('7.0', '7.0'),
    ('7.1', '7.1'),
]


class AudioEqualizerDialog(FloatingDialog):
    """音频调整对话框
    调整时实时应用到 mpv；保存按钮持久化到 config
    """

    style_saved = Signal(dict)

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('audio_eq_title', '音频调整'))
        # 最小尺寸只防止控件被压扁；实际尺寸按内容，超出屏幕时内部滚动
        self.setMinimumSize(560, 420)
        self._loading = False
        self._eq_sliders = []
        self._eq_labels = []
        self._vu_meters = {}            # {ch_name: ChannelVUMeter}
        self._channel_info_label = None
        self._monitor_timer = None
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        self._reload_from_config()
        # 监听频道切换，自动刷新 VU 电平表
        pc = self.window.player_controller
        if pc and hasattr(pc, 'file_loaded'):
            try:
                pc.file_loaded.connect(self._on_file_loaded)
            except Exception as e:
                logger.debug(f"__init__: {e}")

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        accent = c.get('accent')
        mid = c.get('mid')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {mid};
                border-radius: {r}px;
                margin-top: 12px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
            QSlider::groove:horizontal {{
                height: 4px; background: {mid}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {accent}; border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {accent}; border: 2px solid {text_color};
            }}
            QSlider::groove:vertical {{
                width: 4px; background: {mid}; border-radius: 2px;
            }}
            QSlider::handle:vertical {{
                height: 14px; width: 14px; margin: 0 -5px;
                background: {accent}; border-radius: 7px;
            }}
            QSlider::handle:vertical:hover {{
                background: {accent}; border: 2px solid {text_color};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        content = QWidget()
        self._content_widget = content
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 内容超出屏幕时由滚动区兜底，底部操作按钮始终可见
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll, 1)

        # ===== 上半部分：左右双列 =====
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # ---- 左列：音频同步 + 音调补偿 ----
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # 音频同步
        delay_group = QGroupBox(tr('audio_eq_group_delay', '音频同步'))
        dform = QFormLayout(delay_group)
        dform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        dform.setSpacing(6)
        dform.setContentsMargins(8, 8, 8, 8)
        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setRange(-1000, 1000)
        self.delay_slider.setSingleStep(10)
        self.delay_slider.setPageStep(100)
        self.delay_slider.setValue(0)
        self.delay_label = QLabel('0.000s')
        self.delay_label.setMinimumWidth(60)
        self.delay_slider.valueChanged.connect(self._on_delay_changed)
        drow = QHBoxLayout()
        drow.addWidget(self.delay_slider, 1)
        drow.addWidget(self.delay_label)
        dcontainer = QWidget()
        dcontainer.setLayout(drow)
        dform.addRow(tr('audio_eq_delay', '音频延迟'), dcontainer)
        left_col.addWidget(delay_group)

        # 音调补偿
        pitch_group = QGroupBox(tr('audio_eq_group_pitch', '音调补偿'))
        pform = QFormLayout(pitch_group)
        pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        pform.setSpacing(6)
        pform.setContentsMargins(8, 8, 8, 8)
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(50, 200)
        self.pitch_slider.setSingleStep(5)
        self.pitch_slider.setPageStep(20)
        self.pitch_slider.setValue(100)
        self.pitch_label = QLabel('1.00')
        self.pitch_label.setMinimumWidth(48)
        self.pitch_slider.valueChanged.connect(self._on_pitch_changed)
        prows = QHBoxLayout()
        prows.addWidget(self.pitch_slider, 1)
        prows.addWidget(self.pitch_label)
        pcontainer = QWidget()
        pcontainer.setLayout(prows)
        pform.addRow(tr('audio_eq_pitch', '音调'), pcontainer)
        left_col.addWidget(pitch_group)

        # 声道布局 + 输出设备
        dev_group = QGroupBox(
            tr('audio_eq_group_channels', '声道布局') + ' / ' +
            tr('audio_eq_group_device', '输出设备')
        )
        dform2 = QFormLayout(dev_group)
        dform2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        dform2.setSpacing(6)
        dform2.setContentsMargins(8, 8, 8, 8)
        self.channels_combo = QComboBox()
        for val, label in CHANNEL_OPTIONS:
            self.channels_combo.addItem(label, val)
        self.channels_combo.currentIndexChanged.connect(self._on_channels_changed)
        dform2.addRow(tr('audio_eq_channels', '声道'), self.channels_combo)
        self.device_combo = QComboBox()
        self.device_combo.addItem(tr('audio_eq_preset_flat', '默认') + ' (auto)', '')
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        dform2.addRow(tr('audio_eq_device', '设备'), self.device_combo)
        self._devices_loaded = False
        left_col.addWidget(dev_group)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        top_row.addWidget(left_widget, 1)

        # ---- 右列：声道电平表 ----
        ch_group = QGroupBox(tr('audio_eq_group_channel_info', '声道电平'))
        ch_layout = QVBoxLayout(ch_group)
        ch_layout.setContentsMargins(8, 8, 8, 8)
        ch_layout.setSpacing(6)

        # 声道布局信息
        self._channel_info_label = QLabel(
            tr('audio_eq_channel_info', '检测中...')
        )
        self._channel_info_label.setStyleSheet(
            f"color: {AppStyles.get_color('mid')};"
            f" font-size: 10px;"
        )
        self._channel_info_label.setWordWrap(True)
        ch_layout.addWidget(self._channel_info_label)

        # VU 电平表容器（横向排列）
        self._vu_container = QWidget()
        self._vu_layout = QHBoxLayout(self._vu_container)
        self._vu_layout.setSpacing(4)
        self._vu_layout.setContentsMargins(0, 0, 0, 0)
        ch_layout.addWidget(self._vu_container)
        ch_layout.addStretch()

        # 刷新按钮
        ch_btn_row = QHBoxLayout()
        ch_btn_row.addStretch()
        self.ch_refresh_btn = QPushButton(
            tr('audio_eq_channel_refresh', '刷新')
        )
        self.ch_refresh_btn.setFixedWidth(60)
        self.ch_refresh_btn.clicked.connect(self._refresh_channels)
        ch_btn_row.addWidget(self.ch_refresh_btn)
        ch_layout.addLayout(ch_btn_row)

        top_row.addWidget(ch_group, 1)
        layout.addLayout(top_row)

        # ===== 均衡器组 =====
        eq_group = QGroupBox(tr('audio_eq_group_equalizer', '均衡器'))
        eq_layout = QVBoxLayout(eq_group)

        # 预设按钮行
        preset_row = QHBoxLayout()
        preset_label = QLabel(tr('audio_eq_preset', '快速预设') + ':')
        preset_row.addWidget(preset_label)
        preset_keys = [
            ('flat', tr('audio_eq_preset_flat', '平直')),
            ('bass', tr('audio_eq_preset_bass', '重低音')),
            ('treble', tr('audio_eq_preset_treble', '高音')),
            ('vocal', tr('audio_eq_preset_vocal', '人声')),
            ('classical', tr('audio_eq_preset_classical', '古典')),
            ('pop', tr('audio_eq_preset_pop', '流行')),
            ('rock', tr('audio_eq_preset_rock', '摇滚')),
            ('electronic', tr('audio_eq_preset_electronic', '电子')),
        ]
        for key, label in preset_keys:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, k=key: self._apply_preset(k))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        eq_layout.addLayout(preset_row)

        # 10 段均衡器滑块网格
        from services.mpv_player_service import MpvPlayerController
        band_labels = MpvPlayerController.EQ_LABELS
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, bl in enumerate(band_labels):
            lbl = QLabel(bl)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, i)

            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-12, 12)
            slider.setSingleStep(1)
            slider.setPageStep(3)
            slider.setValue(0)
            slider.setFixedHeight(120)
            slider.valueChanged.connect(
                lambda v, idx=i: self._on_eq_band_changed(idx, v)
            )
            grid.addWidget(slider, 1, i)

            val_lbl = QLabel('0')
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setMinimumWidth(36)
            grid.addWidget(val_lbl, 2, i)

            self._eq_sliders.append(slider)
            self._eq_labels.append(val_lbl)

        eq_layout.addLayout(grid)
        layout.addWidget(eq_group)

        # 切换文件时自动重置
        self.reset_on_new_check = QCheckBox(
            tr('audio_eq_reset_on_new_file', '切换文件时自动重置')
        )
        self.reset_on_new_check.toggled.connect(self._on_reset_on_new_toggled)
        layout.addWidget(self.reset_on_new_check)

        # ===== 操作按钮（标准设置式：恢复默认 | 应用 + 完成） =====
        def _on_done():
            self._apply_now()
            self._save()
            self.close()

        btn_bar, self.reset_btn, self.apply_btn, self.close_btn = self.build_settings_buttons(
            self._reset_all, self._apply_now, _on_done,
            reset_text=tr('audio_eq_reset', '恢复默认'),
            apply_text=tr('audio_eq_apply', '应用'),
            done_text=tr('audio_eq_close', '完成'),
        )
        outer.addWidget(btn_bar)

    def showEvent(self, event):
        self._apply_screen_limits()
        super().showEvent(event)
        _QTimer.singleShot(DelayMs.UI_REFRESH, self._apply_screen_limits)
        if not self._devices_loaded:
            try:
                _QTimer.singleShot(DelayMs.LAYOUT_SETTLE, self._load_audio_devices)
                _QTimer.singleShot(DelayMs.STYLE_REAPPLY, self._refresh_channels)
            except Exception:
                self._load_audio_devices()
                self._refresh_channels()

    def _apply_screen_limits(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        max_w = max(560, int(avail.width() * 0.96))
        max_h = max(400, int(avail.height() * 0.94))
        if self._content_widget.layout() is not None:
            self._content_widget.layout().activate()
        hint = self._content_widget.sizeHint()
        want_w = max(560, hint.width() + 24)
        # 按钮行约 40，加外边距
        want_h = max(420, hint.height() + 64)
        self.setMaximumSize(max_w, max_h)
        self.setMinimumSize(min(want_w, max_w), min(want_h, max_h))
        self.resize(min(want_w, max_w), min(want_h, max_h))

    def _load_audio_devices(self):
        """从 mpv 加载音频设备列表"""
        if self._devices_loaded:
            return
        self._devices_loaded = True
        pc = self.window.player_controller
        if not pc or not hasattr(pc, 'get_audio_device_list'):
            return
        try:
            devices = pc.get_audio_device_list()
        except Exception as e:
            logger.debug(f"加载音频设备列表失败: {e}")
            return
        if not devices:
            return
        current = self.device_combo.currentData() or ''
        self._loading = True
        try:
            while self.device_combo.count() > 1:
                self.device_combo.removeItem(self.device_combo.count() - 1)
            for dev in devices:
                name = dev.get('name', '')
                desc = dev.get('description', name)
                if name:
                    self.device_combo.addItem(desc, name)
            idx = self.device_combo.findData(current)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        finally:
            self._loading = False

    # ---------- 数据加载/收集 ----------
    def _reload_from_config(self):
        try:
            cfg = self.window.config.load_audio_eq()
        except Exception as e:
            logger.warning(f"加载音频 EQ 配置失败: {e}")
            cfg = {}
        self._loading = True
        try:
            self._set_ui_from_dict(cfg)
        finally:
            self._loading = False
        self._apply_now(silent=True)

    def _set_ui_from_dict(self, cfg: dict):
        delay = float(cfg.get('audio_delay', 0.0) or 0.0)
        delay = max(-10.0, min(10.0, delay))
        self.delay_slider.setValue(int(round(delay * 100)))
        self.delay_label.setText(f"{delay:.3f}s")
        pitch = float(cfg.get('audio_pitch', 1.0) or 1.0)
        # 旧配置里的 0（audio-pitch-correction 关闭）按原调处理
        pitch = 1.0 if pitch <= 0 else max(0.5, min(2.0, pitch))
        self.pitch_slider.setValue(int(round(pitch * 100)))
        self.pitch_label.setText(f"{pitch:.2f}")
        ch = cfg.get('audio_channels', 'auto') or 'auto'
        idx = self.channels_combo.findData(ch)
        if idx >= 0:
            self.channels_combo.setCurrentIndex(idx)
        dev = cfg.get('audio_device', '') or ''
        idx = self.device_combo.findData(dev)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)
        eq = cfg.get('eq', [0.0] * 10) or [0.0] * 10
        if not isinstance(eq, list) or len(eq) != 10:
            eq = [0.0] * 10
        for i, g in enumerate(eq):
            v = int(round(max(-12.0, min(12.0, float(g)))))
            self._eq_sliders[i].setValue(v)
            self._eq_labels[i].setText(str(v))
        self.reset_on_new_check.setChecked(
            bool(cfg.get('reset_on_new_file', False))
        )

    def _collect_eq(self) -> dict:
        return {
            'audio_delay': round(self.delay_slider.value() / 100.0, 3),
            'audio_pitch': round(self.pitch_slider.value() / 100.0, 3),
            'audio_channels': self.channels_combo.currentData() or 'auto',
            'audio_device': self.device_combo.currentData() or '',
            'eq': [float(s.value()) for s in self._eq_sliders],
            'reset_on_new_file': bool(self.reset_on_new_check.isChecked()),
        }

    # ---------- 事件处理 ----------
    def _on_delay_changed(self, value: int):
        v = value / 100.0
        self.delay_label.setText(f"{v:+.3f}s")
        if self._loading:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_delay'):
            pc.set_audio_delay(v)
            self._show_osd(
                f"{self.window.language_manager.tr('osd_audio_delay', 'Audio Delay')}:"
                f" {v:+.3f}s"
            )

    def _on_pitch_changed(self, value: int):
        v = value / 100.0
        self.pitch_label.setText(f"{v:.2f}")
        if self._loading:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_pitch'):
            pc.set_audio_pitch(v)
            self._show_osd(
                f"{self.window.language_manager.tr('osd_audio_pitch', 'Pitch')}:"
                f" {v:.2f}"
            )

    def _on_channels_changed(self, idx: int):
        if self._loading:
            return
        ch = self.channels_combo.currentData() or 'auto'
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_channels'):
            pc.set_audio_channels(ch)
            self._show_osd(
                f"{self.window.language_manager.tr('osd_audio_channels', 'Channels')}:"
                f" {ch}"
            )

    def _on_device_changed(self, idx: int):
        if self._loading:
            return
        dev = self.device_combo.currentData() or ''
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_device'):
            if dev:
                pc.set_audio_device(dev)
            self._show_osd(
                f"{self.window.language_manager.tr('audio_eq_device', 'Device')}:"
                f" {self.device_combo.currentText()}"
            )

    def _on_eq_band_changed(self, idx: int, value: int):
        self._eq_labels[idx].setText(str(value))
        if self._loading:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_eq_band'):
            pc.set_audio_eq_band(idx, float(value))
            self._show_osd(
                f"{self.window.language_manager.tr('osd_audio_eq_band', 'Band')}"
                f" {idx+1}: {value:+d}dB"
            )

    # ---------- 声道电平监控 ----------
    def _refresh_channels(self):
        """从 MPV 检测当前声道布局并重建 VU 电平表"""
        from services.mpv_player_service import MpvPlayerController
        tr = self.window.language_manager.tr
        pc = self.window.player_controller
        if not pc or not pc.is_playing:
            self._channel_info_label.setText(
                tr('audio_eq_channel_no_playback', '未在播放，无法检测声道')
            )
            self._clear_vu_meters()
            self._stop_monitor()
            return
        info = {}
        if hasattr(pc, 'get_audio_channel_info'):
            try:
                info = pc.get_audio_channel_info()
            except Exception as e:
                logger.debug(f"检测声道信息失败: {e}")
        channels = info.get('channels', [])
        layout = info.get('layout', '')
        count = info.get('count', 0)
        if not channels:
            self._channel_info_label.setText(
                tr('audio_eq_channel_not_detected', '无法检测声道布局')
            )
            self._clear_vu_meters()
            self._stop_monitor()
            return
        # 更新信息标签
        display_map = MpvPlayerController.CHANNEL_DISPLAY
        ch_display = ', '.join(
            f"{display_map.get(ch, ch)}" for ch in channels
        )
        self._channel_info_label.setText(
            f"{tr('audio_eq_channel_layout', '布局')}: {layout}"
            f" ({count}ch)\n{ch_display}"
        )
        # 重建 VU 电平表
        self._clear_vu_meters()
        for ch in channels:
            display = display_map.get(ch, ch)
            meter = ChannelVUMeter(ch, display)
            self._vu_layout.addWidget(meter)
            self._vu_meters[ch] = meter
        # 启动监控定时器
        self._start_monitor()

    def _clear_vu_meters(self):
        """清除所有 VU 电平表"""
        while self._vu_layout.count() > 0:
            item = self._vu_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._vu_meters.clear()

    def _start_monitor(self):
        """启动声道电平监控定时器"""
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'start_channel_monitor'):
            pc.start_channel_monitor()
        if self._monitor_timer is None:
            self._monitor_timer = QTimer(self)
            self._monitor_timer.timeout.connect(self._update_channel_levels)
        self._monitor_timer.start(150)

    def _stop_monitor(self):
        """停止声道电平监控"""
        if self._monitor_timer:
            self._monitor_timer.stop()
        pc = self.window.player_controller
        if pc and hasattr(pc, 'stop_channel_monitor'):
            try:
                pc.stop_channel_monitor()
            except Exception as e:
                logger.debug(f"_stop_monitor: {e}")

    def _update_channel_levels(self):
        """定时更新声道 VU 电平表"""
        pc = self.window.player_controller
        if not pc or not pc.is_playing:
            self._stop_monitor()
            return
        levels = {}
        if hasattr(pc, 'get_channel_levels'):
            try:
                levels = pc.get_channel_levels()
            except Exception as e:
                logger.debug(f"_update_channel_levels exception: {e}")
        if not levels:
            return
        channels = list(self._vu_meters.keys())
        for idx, ch in enumerate(channels):
            # astats 声道编号是 1-based
            level = levels.get(idx + 1, None)
            self._vu_meters[ch].set_level(level)

    def _on_reset_on_new_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            cfg = self.window.config.load_audio_eq()
            cfg['reset_on_new_file'] = bool(checked)
            self.window.config.save_audio_eq(cfg)
        except Exception as e:
            logger.warning(f"保存 reset_on_new_file 失败: {e}")

    def _apply_preset(self, key: str):
        gains = EQ_PRESETS.get(key)
        if not gains:
            return
        self._loading = True
        try:
            for i, g in enumerate(gains):
                self._eq_sliders[i].setValue(int(g))
                self._eq_labels[i].setText(str(int(g)))
        finally:
            self._loading = False
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'set_audio_eq'):
            pc.set_audio_eq([float(g) for g in gains])

    def _apply_now(self, silent: bool = False):
        eq = self._collect_eq()
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'apply_audio_eq'):
            pc.apply_audio_eq(eq)
            if not silent:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(
                        tr('audio_eq_applied', '音频参数已应用')
                    )
        elif not silent:
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    tr('audio_eq_applied', '音频参数已应用')
                )

    def _save(self):
        try:
            eq = self._collect_eq()
            self.window.config.save_audio_eq(eq)
            self.style_saved.emit(eq)
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    tr('audio_eq_saved', '音频参数已保存')
                )
        except Exception as e:
            logger.error(f"保存音频 EQ 失败: {e}")

    def _reset_all(self):
        defaults = self.window.config.AUDIO_EQ_DEFAULTS.copy()
        defaults['eq'] = [0.0] * 10
        self._loading = True
        try:
            self._set_ui_from_dict(defaults)
        finally:
            self._loading = False
        pc = self.window.player_controller
        if pc and pc.is_playing and hasattr(pc, 'reset_audio_eq'):
            pc.reset_audio_eq()
        tr = self.window.language_manager.tr
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(
                tr('audio_eq_reset_done', '音频参数已重置')
            )

    def _on_file_loaded(self):
        """频道切换完成后自动刷新声道 VU 电平表"""
        # 延迟 500ms 等待音频参数就绪
        _QTimer.singleShot(DelayMs.OSD_FADE, self._refresh_channels)

    def _show_osd(self, text: str):
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(text)

    def closeEvent(self, event):
        self._stop_monitor()
        # 断开 file_loaded 信号
        pc = self.window.player_controller
        if pc and hasattr(pc, 'file_loaded'):
            try:
                pc.file_loaded.disconnect(self._on_file_loaded)
            except Exception as e:
                logger.debug(f"closeEvent: {e}")
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
