"""连拍截图对话框 - 定时连续截图"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QProgressBar,
    QGroupBox,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


class BurstScreenshotDialog(FloatingDialog):
    """连拍截图对话框
    - 配置间隔（秒）和总数（张）
    - 开始后定时调用 media_ctrl.take_screenshot()
    - 显示进度（已拍摄/总数）
    - 关闭对话框时自动停止连拍
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('burst_screenshot_title', 'Burst Screenshot'))
        self.setMinimumSize(420, 280)
        self._burst_timer = QTimer(self)
        self._burst_timer.timeout.connect(self._on_burst_timeout)
        self._burst_count = 0
        self._burst_total = 5
        self._burst_interval = 2.0
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        self._update_ui_state()

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
            QProgressBar {{
                background: {c.get('base')};
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {c.get('accent')};
                border-radius: {r}px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 参数组 =====
        param_group = QGroupBox(tr('burst_screenshot_group_params', 'Parameters'))
        pform = QFormLayout(param_group)
        pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 间隔（秒）
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 60.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(2.0)
        self.interval_spin.setSuffix('s')
        pform.addRow(tr('burst_screenshot_interval', 'Interval'), self.interval_spin)

        # 总数
        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 999)
        self.total_spin.setSingleStep(1)
        self.total_spin.setValue(5)
        pform.addRow(tr('burst_screenshot_total', 'Count'), self.total_spin)

        layout.addWidget(param_group)

        # ===== 进度组 =====
        prog_group = QGroupBox(tr('burst_screenshot_group_progress', 'Progress'))
        prog_layout = QVBoxLayout(prog_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)
        self.status_label = QLabel(tr('burst_screenshot_status_idle', 'Idle'))
        prog_layout.addWidget(self.status_label)
        layout.addWidget(prog_group)

        # ===== 操作按钮 =====
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton(tr('burst_screenshot_start', 'Start'))
        self.start_btn.clicked.connect(self._start_burst)
        self.start_btn.setToolTip(tr('burst_start_tooltip', '开始连拍'))
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton(tr('burst_screenshot_stop', 'Stop'))
        self.stop_btn.clicked.connect(self._stop_burst)
        self.stop_btn.setToolTip(tr('burst_stop_tooltip', '停止连拍'))
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()

        self.close_btn = QPushButton(tr('playback_queue_close', 'Close'))
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setToolTip(tr('close_tooltip', '关闭'))
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

    # ---------- 连拍逻辑 ----------
    def _start_burst(self):
        """开始连拍"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('burst_screenshot_not_playing', 'No media playing'))
                return
            self._burst_interval = float(self.interval_spin.value())
            self._burst_total = int(self.total_spin.value())
            self._burst_count = 0
            interval_ms = int(self._burst_interval * 1000)
            self._burst_timer.start(interval_ms)
            # 立即拍第一张
            self._on_burst_timeout()
            self._update_ui_state()
        except Exception as e:
            logger.error(f"开始连拍失败: {e}")

    def _stop_burst(self):
        """停止连拍"""
        self._burst_timer.stop()
        self._update_ui_state()

    def _on_burst_timeout(self):
        """连拍定时器回调"""
        if self._burst_count >= self._burst_total:
            self._burst_timer.stop()
            self._update_ui_state()
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    tr('burst_screenshot_done', 'Burst complete: {n} screenshots').format(n=self._burst_count))
            return
        try:
            media_ctrl = getattr(self.window, 'media_ctrl', None)
            if media_ctrl and hasattr(media_ctrl, 'take_screenshot'):
                media_ctrl.take_screenshot()
            self._burst_count += 1
            self._update_ui_state()
        except Exception as e:
            logger.debug(f"连拍截图失败: {e}")

    def _update_ui_state(self):
        """更新 UI 状态"""
        tr = self.window.language_manager.tr
        is_running = self._burst_timer.isActive()
        self.start_btn.setEnabled(not is_running)
        self.stop_btn.setEnabled(is_running)
        self.interval_spin.setEnabled(not is_running)
        self.total_spin.setEnabled(not is_running)
        if self._burst_total > 0:
            self.progress_bar.setValue(int(self._burst_count * 100 / self._burst_total))
        if is_running:
            self.status_label.setText(
                tr('burst_screenshot_status_running', 'Running: {n}/{total}').format(
                    n=self._burst_count, total=self._burst_total))
        elif self._burst_count > 0:
            self.status_label.setText(
                tr('burst_screenshot_status_done', 'Done: {n}/{total}').format(
                    n=self._burst_count, total=self._burst_total))
        else:
            self.status_label.setText(tr('burst_screenshot_status_idle', 'Idle'))

    def closeEvent(self, event):
        # 关闭时停止连拍
        if self._burst_timer.isActive():
            self._burst_timer.stop()
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
