"""切片导出 + GIF 制作对话框

通过 ffmpeg 子进程导出指定时间段的视频片段或 GIF。
- 自动读取当前播放位置作为起始时间
- 支持自定义时长、输出路径
- 异步执行，进度反馈
"""
import os

from PySide6.QtCore import Qt, QTimer
from utils.delay_constants import DelayMs
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QProgressBar,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


class ClipExportDialog(FloatingDialog):
    """切片导出 + GIF 制作对话框"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('clip_export_title', '切片导出 / GIF 制作'))
        self.setMinimumSize(480, 380)
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 初始化默认值
        QTimer.singleShot(DelayMs.UI_REFRESH, self._populate_current_position)

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
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 时间范围组 =====
        time_group = QGroupBox(tr('clip_export_group_time', '时间范围'))
        tform = QFormLayout(time_group)
        tform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 起始时间（秒）
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(0, 86400)
        self._start_spin.setSingleStep(1.0)
        self._start_spin.setDecimals(2)
        self._start_spin.setSuffix(' s')
        tform.addRow(tr('clip_export_start_time', '起始时间'), self._start_spin)

        # 时长
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setRange(0.1, 3600)
        self._duration_spin.setSingleStep(1.0)
        self._duration_spin.setDecimals(2)
        self._duration_spin.setSuffix(' s')
        self._duration_spin.setValue(10.0)
        tform.addRow(tr('clip_export_duration', '时长'), self._duration_spin)

        # 自动填充当前播放位置
        auto_fill_btn = QPushButton(tr('clip_export_use_current', '使用当前播放位置'))
        auto_fill_btn.clicked.connect(self._populate_current_position)
        tform.addRow('', auto_fill_btn)

        layout.addWidget(time_group)

        # ===== 输出设置组 =====
        out_group = QGroupBox(tr('clip_export_group_output', '输出设置'))
        oform = QFormLayout(out_group)
        oform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 输出格式
        self._format_combo = QComboBox()
        self._format_combo.addItem(tr('clip_export_format_mp4', 'MP4 (视频)'), 'mp4')
        self._format_combo.addItem(tr('clip_export_format_mkv', 'MKV (视频)'), 'mkv')
        self._format_combo.addItem(tr('clip_export_format_webm', 'WebM (视频)'), 'webm')
        self._format_combo.addItem(tr('clip_export_format_gif', 'GIF (动画)'), 'gif')
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        oform.addRow(tr('clip_export_format', '输出格式'), self._format_combo)

        # 编码模式（仅视频格式有效）
        self._copy_check = QPushButton(tr('clip_export_stream_copy', '流复制（快，不重新编码）'))
        self._copy_check.setCheckable(True)
        self._copy_check.setChecked(True)
        oform.addRow('', self._copy_check)

        # GIF 参数（仅 GIF 有效）
        self._gif_width_spin = QSpinBox()
        self._gif_width_spin.setRange(120, 1920)
        self._gif_width_spin.setSingleStep(60)
        self._gif_width_spin.setValue(480)
        self._gif_width_spin.setSuffix(' px')
        oform.addRow(tr('clip_export_gif_width', 'GIF 宽度'), self._gif_width_spin)

        self._gif_fps_spin = QSpinBox()
        self._gif_fps_spin.setRange(5, 30)
        self._gif_fps_spin.setSingleStep(1)
        self._gif_fps_spin.setValue(15)
        self._gif_fps_spin.setSuffix(' fps')
        oform.addRow(tr('clip_export_gif_fps', 'GIF 帧率'), self._gif_fps_spin)

        # 输出路径
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        browse_btn = QPushButton(tr('clip_export_browse', '浏览...'))
        browse_btn.clicked.connect(self._browse_output)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        oform.addRow(tr('clip_export_output', '输出路径'), path_row)

        layout.addWidget(out_group)

        # ===== 进度条 =====
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # 不确定模式
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ===== 操作按钮 =====
        btn_row = QHBoxLayout()
        self._export_btn = QPushButton(tr('clip_export_start_btn', '开始导出'))
        self._export_btn.clicked.connect(self._on_export_clicked)
        self._cancel_btn = QPushButton(tr('clip_export_cancel', '取消'))
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setEnabled(False)
        self._close_btn = QPushButton(tr('playback_queue_close', '关闭'))
        self._close_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(self._export_btn)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        # 初始默认路径
        self._on_format_changed(0)

    def _on_format_changed(self, idx: int):
        """切换格式时调整 UI 和默认路径"""
        fmt = self._format_combo.currentData() or 'mp4'
        is_gif = (fmt == 'gif')
        # GIF 参数启用状态
        self._gif_width_spin.setEnabled(is_gif)
        self._gif_fps_spin.setEnabled(is_gif)
        # 流复制对 GIF 无效
        self._copy_check.setEnabled(not is_gif)
        # 默认路径
        try:
            default_dir = os.path.expanduser('~')
        except Exception:
            default_dir = os.getcwd()
        ts_label = 'clip'
        base_name = f"{ts_label}_{int(__import__('time').time())}"
        ext = 'gif' if is_gif else fmt
        default_path = os.path.join(default_dir, f"{base_name}.{ext}")
        self._path_edit.setText(default_path)

    def _populate_current_position(self):
        """填充当前播放位置作为起始时间"""
        try:
            pc = self.window.player_controller
            if pc and pc.is_playing and hasattr(pc, 'get_current_time'):
                ms = pc.get_current_time()
                if ms and ms > 0:
                    self._start_spin.setValue(ms / 1000.0)
        except Exception as e:
            logger.debug(f"获取当前播放位置失败: {e}")

    def _browse_output(self):
        """选择输出路径"""
        tr = self.window.language_manager.tr
        fmt = self._format_combo.currentData() or 'mp4'
        ext = 'gif' if fmt == 'gif' else fmt
        filter_str = f"{ext.upper()} (*.{ext});;All Files (*.*)"
        cur_path = self._path_edit.text().strip()
        cur_dir = os.path.dirname(cur_path) if cur_path else os.path.expanduser('~')
        path, _ = QFileDialog.getSaveFileName(self, tr('clip_export_select_output', '选择输出路径'), cur_dir, filter_str)
        if path:
            if not path.lower().endswith(f'.{ext}'):
                path = path + f'.{ext}'
            self._path_edit.setText(path)

    def _on_export_clicked(self):
        """开始导出"""
        tr = self.window.language_manager.tr
        # 获取源文件
        pc = self.window.player_controller
        if not pc or not pc.is_playing:
            QMessageBox.warning(self, tr('clip_export_tip', '提示'), tr('clip_export_no_playback', '当前无播放内容，无法导出'))
            return
        source = pc.current_url or ''
        # 处理 file:// 协议
        if source.startswith('file://'):
            from urllib.parse import urlparse, unquote
            parsed = urlparse(source)
            source = unquote(parsed.path)
            import sys
            if sys.platform == 'win32' and source.startswith('/') and len(source) > 2 and source[2] == ':':
                source = source[1:]
        if not source or not os.path.exists(source):
            QMessageBox.warning(self, tr('clip_export_tip', '提示'), tr('clip_export_source_not_found', '源文件不存在: {path}').format(path=source))
            return
        output_path = self._path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, tr('clip_export_tip', '提示'), tr('clip_export_no_output_path', '请选择输出路径'))
            return
        start_sec = float(self._start_spin.value())
        duration = float(self._duration_spin.value())
        end_sec = start_sec + duration
        fmt = self._format_combo.currentData() or 'mp4'

        # 获取服务
        svc = getattr(self.window, 'clip_export_service', None)
        if not svc:
            QMessageBox.warning(self, tr('clip_export_tip', '提示'), tr('clip_export_service_unavailable', '导出服务未初始化'))
            return
        # 切换 UI 状态
        self._set_busy(True)
        self._progress.setFormat(tr('clip_export_exporting', '导出中...') if hasattr(self._progress, 'setFormat') else '')

        def _on_done(success, message):
            def _ui_update():
                self._set_busy(False)
                if success:
                    QMessageBox.information(self, tr('clip_export_done', '完成'), message)
                else:
                    QMessageBox.warning(self, tr('clip_export_failed', '失败'), message)
            from utils.thread_safety import invoke_on_thread
            invoke_on_thread(self, _ui_update)

        try:
            if fmt == 'gif':
                svc.export_gif(source, start_sec, end_sec, output_path,
                               width=int(self._gif_width_spin.value()),
                               fps=int(self._gif_fps_spin.value()),
                               done_callback=_on_done)
            else:
                svc.export_clip(source, start_sec, end_sec, output_path,
                                stream_copy=self._copy_check.isChecked(),
                                done_callback=_on_done)
        except Exception as e:
            self._set_busy(False)
            QMessageBox.warning(self, tr('clip_export_error', '异常'), tr('clip_export_export_failed', '导出失败: {err}').format(err=e))

    def _on_cancel_clicked(self):
        """取消当前导出"""
        svc = getattr(self.window, 'clip_export_service', None)
        if svc:
            svc.cancel()
            self._set_busy(False)

    def _set_busy(self, busy: bool):
        """切换 UI 忙碌状态"""
        self._export_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._progress.setVisible(busy)

    def closeEvent(self, event):
        svc = getattr(self.window, 'clip_export_service', None)
        if svc and hasattr(svc, 'cancel'):
            svc.cancel()
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
