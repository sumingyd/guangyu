"""音视频同步监控对话框 - 实时显示 A/V 同步状态与历史趋势波形"""
from collections import deque

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QFont, QPolygonF
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QSlider, QWidget, QCheckBox, QDoubleSpinBox,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class AVSyncWaveWidget(QWidget):
    """A/V 同步历史趋势波形图
    - 中线表示 avdiff=0（完美同步）
    - 上方为正（音频落后），下方为负（音频领先）
    - 颜色随偏差大小变化（绿/黄/红）
    """
    MAX_POINTS = 200  # 保留最多 200 个采样点

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples: deque = deque(maxlen=self.MAX_POINTS)
        self.setMinimumHeight(140)
        self.setAutoFillBackground(True)

    def add_sample(self, value: float):
        """添加一个采样点"""
        self._samples.append(float(value))
        self.update()

    def clear_samples(self):
        self._samples.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.rect()
            if rect.width() <= 0 or rect.height() <= 0:
                return

            c = AppStyles._get_colors()
            bg = QColor(c.get('base'))
            mid_color = QColor(c.get('mid'))
            text_color = QColor(c.get('window_text'))
            accent = QColor(c.get('accent'))

            # 背景
            painter.fillRect(rect, bg)

            # 中线（avdiff=0）
            cy = rect.height() / 2
            pen = QPen(mid_color, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(0, int(cy), rect.width(), int(cy))

            # 中线标签
            painter.setPen(QPen(text_color))
            font = QFont()
            from ui.typography import scaled_pt
            font.setPointSizeF(scaled_pt(8))
            painter.setFont(font)
            painter.drawText(4, int(cy) - 2, '0')

            # 计算自适应范围
            max_abs = 0.1  # 默认 ±0.1s 范围
            for v in self._samples:
                a = abs(v)
                if a > max_abs:
                    max_abs = a
            # 限制范围避免极端值导致图形不可读
            max_abs = min(max_abs, 5.0)
            # 上下各留 10% 边距
            half_h = (rect.height() * 0.4) / max_abs if max_abs > 0 else 1.0

            # 上下边界标签
            painter.drawText(4, 12, f'+{max_abs:.2f}s')
            painter.drawText(4, rect.height() - 4, f'-{max_abs:.2f}s')

            # 绘制波形（填充 + 描边）
            n = len(self._samples)
            if n < 2:
                painter.setPen(QPen(text_color))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, '...')
                return

        # 构建 polygon 点
            points = []
            for i, v in enumerate(self._samples):
                x = rect.width() * i / max(1, self.MAX_POINTS - 1)
                y = cy - max(-max_abs, min(max_abs, v)) * half_h
                points.append((x, y))

            # 渐变填充
            grad = QLinearGradient(0, 0, 0, rect.height())
            grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 100))
            grad.setColorAt(0.5, QColor(accent.red(), accent.green(), accent.blue(), 40))
            grad.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 100))

            poly = QPolygonF()
            poly.append(QPointF(points[0][0], cy))
            for x, y in points:
                poly.append(QPointF(x, y))
            poly.append(QPointF(points[-1][0], cy))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(poly)

            # 描边（根据最新值变色）
            latest = self._samples[-1]
            if abs(latest) < 0.04:
                line_color = accent
            elif abs(latest) < 0.2:
                line_color = QColor('#f0ad4e')  # 黄
            else:
                line_color = QColor('#d9534f')  # 红

            pen = QPen(line_color, 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            prev = points[0]
            for cur in points[1:]:
                painter.drawLine(QPointF(prev[0], prev[1]), QPointF(cur[0], cur[1]))
                prev = cur
        finally:
            painter.end()


class AVSyncDialog(FloatingDialog):
    """音视频同步监控对话框
    - 实时显示 avdiff / audio-pts / video-pts / audio-delay
    - avdiff 历史趋势波形图
    - 音频延迟微调滑块（-10s ~ +10s）
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('av_sync_title', 'A/V Sync Monitor'))
        self.setMinimumSize(520, 420)
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 采样定时器（每 100ms 采样一次 avdiff）
        self._sample_timer = QTimer(self)
        self._sample_timer.setInterval(100)
        self._sample_timer.timeout.connect(self._sample_avdiff)
        self._sample_timer.start()
        # UI 刷新定时器（每 200ms 刷新数值）
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._refresh_values)
        self._ui_timer.start()
        QTimer.singleShot(DelayMs.UI_REFRESH, self._refresh_values)
        # 字幕自动同步定时器（每 500ms 检查一次）
        self._sub_sync_enabled = False
        self._sub_sync_timer = QTimer(self)
        self._sub_sync_timer.setInterval(500)
        self._sub_sync_timer.timeout.connect(self._sub_sync_tick)
        # 字幕同步最近 N 次采样窗口（用于平滑 avdiff）
        self._sub_sync_history = deque(maxlen=6)
        self._sub_sync_last_adjust_ts = 0.0

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
                background: {c.get('base')};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {c.get('accent')};
                width: 14px; height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 实时数值组 =====
        info_group = QGroupBox(tr('av_sync_group_status', 'Real-time Status'))
        info_grid = QVBoxLayout(info_group)
        info_grid.setSpacing(6)

        # A/V 差值（带颜色指示）
        avdiff_row = QHBoxLayout()
        avdiff_row.addWidget(QLabel(tr('av_sync_avdiff', 'A/V Diff:')))
        self._avdiff_label = QLabel('+0.000s')
        f = self._avdiff_label.font()
        f.setBold(True)
        from ui.typography import scaled_pt
        f.setPointSizeF(scaled_pt(11))
        self._avdiff_label.setFont(f)
        avdiff_row.addWidget(self._avdiff_label)
        avdiff_row.addStretch()
        self._status_label = QLabel(tr('av_sync_status_ok', 'OK'))
        info_grid.addLayout(avdiff_row)

        # 音频 PTS
        audio_pts_row = QHBoxLayout()
        audio_pts_row.addWidget(QLabel(tr('av_sync_audio_pts', 'Audio PTS:')))
        self._audio_pts_label = QLabel('0.000s')
        audio_pts_row.addWidget(self._audio_pts_label)
        audio_pts_row.addStretch()
        info_grid.addLayout(audio_pts_row)

        # 视频 PTS
        video_pts_row = QHBoxLayout()
        video_pts_row.addWidget(QLabel(tr('av_sync_video_pts', 'Video PTS:')))
        self._video_pts_label = QLabel('0.000s')
        video_pts_row.addWidget(self._video_pts_label)
        video_pts_row.addStretch()
        info_grid.addLayout(video_pts_row)

        # 当前音频延迟
        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel(tr('av_sync_current_delay', 'Current Audio Delay:')))
        self._delay_value_label = QLabel('+0.000s')
        delay_row.addWidget(self._delay_value_label)
        delay_row.addStretch()
        info_grid.addLayout(delay_row)

        layout.addWidget(info_group)

        # ===== 波形图组 =====
        wave_group = QGroupBox(tr('av_sync_group_wave', 'A/V Diff Trend'))
        wave_layout = QVBoxLayout(wave_group)
        self._wave_widget = AVSyncWaveWidget()
        wave_layout.addWidget(self._wave_widget)
        layout.addWidget(wave_group, 1)

        # ===== 音频延迟调整组 =====
        adj_group = QGroupBox(tr('av_sync_group_adjust', 'Audio Delay Adjustment'))
        adj_layout = QVBoxLayout(adj_group)
        # 滑块
        slider_row = QHBoxLayout()
        self._delay_slider = QSlider(Qt.Orientation.Horizontal)
        self._delay_slider.setRange(-1000, 1000)  # -10.00s ~ +10.00s（精度 0.01s）
        self._delay_slider.setSingleStep(1)
        self._delay_slider.setPageStep(10)
        self._delay_slider.setValue(0)
        self._delay_slider.valueChanged.connect(self._on_delay_slider_changed)
        slider_row.addWidget(self._delay_slider, 1)
        self._slider_value_label = QLabel('+0.000s')
        slider_row.addWidget(self._slider_value_label)
        adj_layout.addLayout(slider_row)

        # 按钮行
        btn_row = QHBoxLayout()
        minus_btn = QPushButton('-0.1s')
        minus_btn.clicked.connect(lambda: self._adjust_delay(-0.1))
        minus_btn.setToolTip(tr('av_minus_tooltip', '减小音视频同步偏移'))
        btn_row.addWidget(minus_btn)
        plus_btn = QPushButton('+0.1s')
        plus_btn.clicked.connect(lambda: self._adjust_delay(0.1))
        plus_btn.setToolTip(tr('av_plus_tooltip', '增大音视频同步偏移'))
        btn_row.addWidget(plus_btn)
        reset_btn = QPushButton(tr('av_sync_reset_delay', 'Reset'))
        reset_btn.clicked.connect(self._reset_delay)
        reset_btn.setToolTip(tr('av_reset_tooltip', '重置同步偏移'))
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        adj_layout.addLayout(btn_row)

        layout.addWidget(adj_group)

        # ===== 字幕自动同步组 =====
        sub_group = QGroupBox(tr('av_sync_group_sub_sync', 'Subtitle Auto-Sync'))
        sub_layout = QVBoxLayout(sub_group)
        # 启用开关
        enable_row = QHBoxLayout()
        self._sub_sync_checkbox = QCheckBox(tr('av_sync_sub_sync_enable', 'Enable auto-sync (align subtitle to audio by avdiff)'))
        self._sub_sync_checkbox.toggled.connect(self._on_sub_sync_toggled)
        enable_row.addWidget(self._sub_sync_checkbox)
        enable_row.addStretch()
        sub_layout.addLayout(enable_row)
        # 阈值与步长配置
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel(tr('av_sync_sub_sync_threshold', 'Threshold (s):')))
        self._sub_sync_threshold = QDoubleSpinBox()
        self._sub_sync_threshold.setRange(0.01, 1.0)
        self._sub_sync_threshold.setSingleStep(0.01)
        self._sub_sync_threshold.setValue(0.05)
        param_row.addWidget(self._sub_sync_threshold)
        param_row.addSpacing(12)
        param_row.addWidget(QLabel(tr('av_sync_sub_sync_factor', 'Gain:')))
        self._sub_sync_factor = QDoubleSpinBox()
        self._sub_sync_factor.setRange(0.05, 1.0)
        self._sub_sync_factor.setSingleStep(0.05)
        self._sub_sync_factor.setValue(0.30)
        param_row.addWidget(self._sub_sync_factor)
        param_row.addStretch()
        sub_layout.addLayout(param_row)
        # 状态显示
        self._sub_sync_status = QLabel('--')
        sub_layout.addWidget(self._sub_sync_status)
        layout.addWidget(sub_group)

        # 关闭按钮
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton(tr('playback_queue_close', 'Close'))
        close_btn.clicked.connect(self.close)
        close_btn.setToolTip(tr('close_tooltip', '关闭'))
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # ---------- 实时采样与刷新 ----------
    def _sample_avdiff(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'get_avdiff'):
                return
            v = pc.get_avdiff()
            self._wave_widget.add_sample(v)
        except Exception as e:
            logger.debug(f"采样 avdiff 失败: {e}")

    def _refresh_values(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            tr = self.window.language_manager.tr

            # avdiff
            avdiff = pc.get_avdiff() if hasattr(pc, 'get_avdiff') else 0.0
            self._avdiff_label.setText(f"{avdiff:+.3f}s")

            # 状态指示
            abs_av = abs(avdiff)
            c = AppStyles._get_colors()
            if abs_av < 0.04:
                color = QColor(c.get('accent'))
                status_text = tr('av_sync_status_ok', 'OK')
            elif abs_av < 0.2:
                color = QColor(c.get('warning'))
                status_text = tr('av_sync_status_minor', 'Minor Desync')
            else:
                color = QColor(c.get('error'))
                status_text = tr('av_sync_status_bad', 'Out of Sync')
            self._avdiff_label.setStyleSheet(f"color: {color.name()};")
            self._status_label.setText(status_text)
            self._status_label.setStyleSheet(f"color: {color.name()}; font-weight: bold;")

            # PTS
            audio_pts = pc.get_audio_pts() if hasattr(pc, 'get_audio_pts') else 0.0
            video_pts = pc.get_video_pts() if hasattr(pc, 'get_video_pts') else 0.0
            self._audio_pts_label.setText(f"{audio_pts:.3f}s")
            self._video_pts_label.setText(f"{video_pts:.3f}s")

            # 当前音频延迟
            delay = pc.get_audio_delay() if hasattr(pc, 'get_audio_delay') else 0.0
            self._delay_value_label.setText(f"{delay:+.3f}s")
            # 同步滑块位置（不触发 valueChanged）
            self._delay_slider.blockSignals(True)
            self._delay_slider.setValue(int(delay * 100))
            self._delay_slider.blockSignals(False)
            self._slider_value_label.setText(f"{delay:+.3f}s")
        except Exception as e:
            logger.debug(f"刷新 A/V 同步数值失败: {e}")

    # ---------- 音频延迟调整 ----------
    def _on_delay_slider_changed(self, value: int):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'set_audio_delay'):
                return
            delay = value / 100.0
            pc.set_audio_delay(delay)
            self._slider_value_label.setText(f"{delay:+.3f}s")
            self._delay_value_label.setText(f"{delay:+.3f}s")
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    f"{tr('osd_audio_delay', 'Audio Delay')}: {delay:+.3f}s")
        except Exception as e:
            logger.debug(f"调整音频延迟失败: {e}")

    def _adjust_delay(self, delta: float):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'adjust_audio_delay'):
                return
            new_v = pc.adjust_audio_delay(delta)
            self._slider_value_label.setText(f"{new_v:+.3f}s")
            self._delay_value_label.setText(f"{new_v:+.3f}s")
        except Exception as e:
            logger.debug(f"微调音频延迟失败: {e}")

    def _reset_delay(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'set_audio_delay'):
                return
            pc.set_audio_delay(0.0)
            self._slider_value_label.setText('+0.000s')
            self._delay_value_label.setText('+0.000s')
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    f"{tr('osd_audio_delay', 'Audio Delay')}: +0.000s")
        except Exception as e:
            logger.debug(f"重置音频延迟失败: {e}")

    # ---------- 字幕自动同步 ----------
    def _on_sub_sync_toggled(self, checked: bool):
        """启用/禁用字幕自动同步"""
        self._sub_sync_enabled = checked
        if checked:
            self._sub_sync_history.clear()
            self._sub_sync_timer.start()
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('osd_sub_sync_on', 'Subtitle auto-sync on'))
        else:
            self._sub_sync_timer.stop()
            self._sub_sync_status.setText('--')
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('osd_sub_sync_off', 'Subtitle auto-sync off'))

    def _sub_sync_tick(self):
        """字幕自动同步主循环：
        - 采样 avdiff，存入历史窗口
        - 取最近 N 次平均，若超过阈值则用比例增益调整 sub_delay
        - 调整方向：avdiff = audio_pts - video_pts；avdiff > 0 表示音频领先，
          字幕应延后跟随音频 → sub_delay += avg * gain
        - 避免在极端 avdiff（>1s）下调整（可能是 seek/暂停）
        """
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'get_avdiff'):
                return
            if not hasattr(pc, 'adjust_sub_delay'):
                return
            avdiff = pc.get_avdiff()
            # 跳过 NaN/None
            if avdiff is None or (isinstance(avdiff, float) and (avdiff != avdiff)):
                return
            self._sub_sync_history.append(float(avdiff))
            if len(self._sub_sync_history) < 3:
                return
            avg = sum(self._sub_sync_history) / len(self._sub_sync_history)
            threshold = float(self._sub_sync_threshold.value())
            gain = float(self._sub_sync_factor.value())
            # 极端值跳过（seek/暂停后短暂异常）
            if abs(avg) > 1.0:
                self._sub_sync_status.setText(f'avdiff={avg:+.3f}s (skipped, too large)')
                return
            if abs(avg) < threshold:
                self._sub_sync_status.setText(f'avdiff={avg:+.3f}s (in sync)')
                return
            # 调整量：将字幕朝向音频对齐方向移动（比例控制）
            delta = avg * gain
            new_delay = pc.adjust_sub_delay(delta)
            if new_delay is not None:
                self._sub_sync_status.setText(
                    f'avdiff={avg:+.3f}s → sub_delay={new_delay:+.3f}s (delta={delta:+.3f})')
            else:
                self._sub_sync_status.setText(f'avdiff={avg:+.3f}s (adjust failed)')
        except Exception as e:
            logger.debug(f"字幕自动同步失败: {e}")

    # ---------- 生命周期 ----------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._sample_timer.isActive():
            self._sample_timer.start()
        if not self._ui_timer.isActive():
            self._ui_timer.start()
        self._wave_widget.clear_samples()

    def closeEvent(self, event):
        self._sample_timer.stop()
        self._ui_timer.stop()
        self._sub_sync_timer.stop()
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
