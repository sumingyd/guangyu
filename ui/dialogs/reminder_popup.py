from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QProgressBar, QApplication)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from utils.platform_utils import wayland_move


class ReminderPopup(FloatingDialog):
    _AUTO_CLOSE_MS = 300000
    _PROGRESS_UPDATE_MS = 1000

    def __init__(self, main_window, channel_name: str, program_title: str,
                 start_time_str: str = '', auto_switch: bool = False,
                 on_switch_callback=None, parent=None):
        super().__init__(parent, frameless=True, stay_on_top=True, tool_window=True)
        self.window = main_window
        self._channel_name = channel_name
        self._program_title = program_title
        self._start_time_str = start_time_str
        self._auto_switch = auto_switch
        self._on_switch_callback = on_switch_callback
        self._elapsed_ms = 0
        self._dragging = False
        self._drag_offset = None
        self._setup_ui()
        self._setup_timers()
        self._apply_theme()
        self._register_theme()
        self._position_bottom_right()

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        ff = AppStyles._get_style_font_family()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        title_label = QLabel(tr('reminder_popup_title', '节目提醒'))
        title_label.setObjectName('popupTitle')
        from ui.typography import scaled_pt
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSizeF(scaled_pt(11))
        title_font.setFamily(ff)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        channel_label = QLabel(tr('reminder_popup_channel', '频道: {channel}').format(channel=self._channel_name))
        channel_label.setObjectName('popupChannel')
        layout.addWidget(channel_label)

        program_label = QLabel(tr('reminder_popup_program', '节目: {title}').format(title=self._program_title))
        program_label.setObjectName('popupProgram')
        program_font = QFont()
        program_font.setBold(True)
        program_font.setPointSizeF(scaled_pt(10))
        program_font.setFamily(ff)
        program_label.setFont(program_font)
        layout.addWidget(program_label)

        if self._start_time_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(self._start_time_str)
                time_str = dt.strftime('%H:%M:%S')
            except Exception:
                time_str = self._start_time_str
            time_label = QLabel(tr('reminder_popup_time', '开始时间: {time}').format(time=time_str))
            time_label.setObjectName('popupTime')
            layout.addWidget(time_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, self._AUTO_CLOSE_MS // self._PROGRESS_UPDATE_MS)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        layout.addWidget(self._progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        if self._on_switch_callback:
            self._switch_btn = QPushButton(tr('reminder_popup_switch', '切换频道'))
            self._switch_btn.clicked.connect(self._on_switch_clicked)
            self._switch_btn.setToolTip(tr('switch_channel_tooltip', '切换到该频道'))
            btn_layout.addWidget(self._switch_btn)

        self._close_btn = QPushButton(tr('reminder_popup_close', '关闭'))
        self._close_btn.clicked.connect(self.close)
        self._close_btn.setToolTip(tr('close_tooltip', '关闭'))
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)
        self.setFixedSize(320, self.sizeHint().height() + 60)

    def _setup_timers(self):
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.close)
        self._auto_close_timer.start(self._AUTO_CLOSE_MS)

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._update_progress)
        self._progress_timer.start(self._PROGRESS_UPDATE_MS)

    def _update_progress(self):
        self._elapsed_ms += self._PROGRESS_UPDATE_MS
        step = self._elapsed_ms // self._PROGRESS_UPDATE_MS
        self._progress_bar.setValue(step)

    def _on_switch_clicked(self):
        if self._on_switch_callback:
            self._on_switch_callback()
        self.close()

    def _position_bottom_right(self):
        screen = None
        if self.window and hasattr(self.window, 'screen'):
            try:
                screen = self.window.screen()
            except Exception:
                pass
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        margin = 16
        gap = 8
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        if self.window and hasattr(self.window, 'epg_reminder_ctrl'):
            ctrl = self.window.epg_reminder_ctrl
            get_popups = getattr(ctrl, 'get_active_popups', None)
            existing_popups = [p for p in (get_popups() if get_popups else getattr(ctrl, '_active_popups', [])) if p is not self and p.isVisible()]
            for p in existing_popups:
                y = min(y, p.y() - self.height() - gap)
        if y < geo.top() + margin:
            y = geo.top() + margin
        wayland_move(self, x, y)

    def _apply_theme(self):
        self.setStyleSheet(AppStyles.popup_dialog_style())
        if hasattr(self, '_progress_bar'):
            self._progress_bar.setStyleSheet(AppStyles.progress_style())
        for btn in self.findChildren(QPushButton):
            if btn is getattr(self, '_switch_btn', None):
                btn.setStyleSheet(AppStyles.apply_button_style())
            else:
                btn.setStyleSheet(AppStyles.button_style())

    def _register_theme(self):
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def reapply_styles(self):
        self._apply_theme()

    def closeEvent(self, event):
        if hasattr(self, '_auto_close_timer') and self._auto_close_timer:
            self._auto_close_timer.stop()
        if hasattr(self, '_progress_timer') and self._progress_timer:
            self._progress_timer.stop()
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)

    def show(self):
        super().show()
        self._position_bottom_right()
