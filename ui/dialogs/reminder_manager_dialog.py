from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QLabel, QPushButton)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor
from PySide6 import QtWidgets
from ui.styles import AppStyles
from ui.floating_dialog import FloatingDialog


class ReminderManagerDialog(FloatingDialog):
    reminder_removed = Signal(str)

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self._title_text = tr('reminder_manager', '提醒管理')
        self.setWindowTitle(self._title_text)
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._apply_theme()
        self._load_reminders()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.get('window')};
                color: {c.get('window_text')};
            }}
            QLabel {{
                color: {c.get('window_text')};
                background-color: transparent;
            }}
            QListWidget {{
                background-color: transparent;
                color: {c.get('window_text')};
                border: none; outline: none;
            }}
            QListWidget::item {{
                padding: 4px 6px; min-height: 30px;
                border: 1px solid transparent; border-radius: {r}px;
            }}
            QListWidget::item:selected {{
                border: 1px solid {c.get('accent')};
                background-color: {c.get('highlight')};
            }}
            QPushButton {{
                background-color: {c.get('player_button')};
                color: {c.get('window_text')};
                border: 1px solid {c.get('player_line')};
                border-radius: {r}px;
                padding: 4px 12px; min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {c.get('accent')};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.setSpacing(0)

        title_bar = FloatingDialog.create_dialog_title_bar(self._title_text, self)
        layout.addWidget(title_bar)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(8)

        self.info_label = QLabel(tr('reminder_info', '提醒基于具体频道+节目+开始时间，节目开始前60秒触发通知'))
        self.info_label.setWordWrap(True)
        content_layout.addWidget(self.info_label)

        self.reminder_list = QListWidget()
        self.reminder_list.setSpacing(2)
        content_layout.addWidget(self.reminder_list, 1)

        btn_row = QHBoxLayout()
        self.remove_btn = QPushButton(tr('remove_selected', '删除选中'))
        self.remove_btn.clicked.connect(self._on_remove_selected)
        self.remove_btn.setToolTip(tr('remove_tooltip', '删除选中提醒'))
        btn_row.addWidget(self.remove_btn)

        self.clear_btn = QPushButton(tr('clear_all', '清空全部'))
        self.clear_btn.clicked.connect(self._on_clear_all)
        self.clear_btn.setToolTip(tr('clear_all_tooltip', '清空全部提醒'))
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch(1)
        content_layout.addLayout(btn_row)
        layout.addLayout(content_layout)

    def _load_reminders(self):
        self.reminder_list.clear()
        ctrl = getattr(self.window, 'epg_reminder_ctrl', None)
        if not ctrl or not ctrl.service:
            return

        c = AppStyles._get_colors()
        name_style = f"color: {c.get('window_text')}; background-color: transparent;"
        time_style = (
            f"color: {c.get('player_panel_secondary', c.get('window_text'))};"
            f" background-color: transparent;"
        )

        reminders = ctrl.get_reminders()
        for idx, reminder in enumerate(reminders):
            try:
                ch_name = reminder.get('channel_name', '')
                title = reminder.get('program_title', '')
                start = reminder.get('start_time', '')
                time_str = ''
                if start:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(start)
                        time_str = dt.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        time_str = start

                item_widget = QtWidgets.QWidget()
                item_layout = QtWidgets.QHBoxLayout(item_widget)
                item_layout.setContentsMargins(5, 2, 5, 2)
                item_layout.setSpacing(8)

                name_label = QtWidgets.QLabel(f"{ch_name} - {title}")
                name_label.setStyleSheet(name_style)
                name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

                time_label = QtWidgets.QLabel(time_str)
                time_label.setStyleSheet(time_style)
                time_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

                item_layout.addWidget(name_label, 1)
                item_layout.addWidget(time_label)

                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 40))
                item.setData(Qt.ItemDataRole.UserRole, reminder.get('id', ''))
                self.reminder_list.addItem(item)
                self.reminder_list.setItemWidget(item, item_widget)
            except Exception:
                pass

        tr = self.window.language_manager.tr
        if not reminders:
            empty_item = QListWidgetItem(tr('reminder_empty', '暂无提醒，在节目详情中可添加提醒'))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            c_empty = AppStyles._get_colors()
            empty_item.setForeground(QColor(c_empty.get('placeholder')))
            self.reminder_list.addItem(empty_item)

        self.info_label.setText(
            tr('reminder_count_info', '共 {count} 个提醒 | 提醒基于具体频道+节目+开始时间，节目开始前60秒触发通知')
            .format(count=len(reminders))
        )

    def _on_remove_selected(self):
        item = self.reminder_list.currentItem()
        if not item:
            return
        reminder_id = item.data(Qt.ItemDataRole.UserRole)
        ctrl = getattr(self.window, 'epg_reminder_ctrl', None)
        if not ctrl or not ctrl.service:
            return
        if reminder_id:
            ctrl.remove_reminder(reminder_id)
            self.reminder_removed.emit(reminder_id)
            self._load_reminders()

    def _on_clear_all(self):
        ctrl = getattr(self.window, 'epg_reminder_ctrl', None)
        if not ctrl or not ctrl.service:
            return
        reminders = ctrl.get_reminders()
        for r in reminders:
            ctrl.remove_reminder(r.get('id', ''))
        self._load_reminders()
