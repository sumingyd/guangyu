"""断点续播列表对话框 - 显示所有保存的播放断点"""
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)
from PySide6.QtGui import QColor

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from utils.delay_constants import DelayMs
from core.log_manager import global_logger as logger


class ResumeListDialog(FloatingDialog):
    """断点续播列表对话框
    - 显示所有保存的播放断点
    - 双击项恢复播放
    - 单项删除 / 全部清除
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('resume_list_title', 'Resume Positions'))
        self.setMinimumSize(640, 480)
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        QTimer.singleShot(DelayMs.UI_REFRESH, self._reload_list)

    @property
    def _resume_ctrl(self) -> Optional[object]:
        return getattr(self.window, 'resume_ctrl', None)

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
            QListWidget {{
                background: {c.get('base')};
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background: {c.get('accent')};
                color: {c.get('highlighted_text')};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 顶部说明
        info_label = QLabel(tr('resume_list_info',
            'Saved playback positions. Double-click to resume, or use the buttons below.'))
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 列表组
        list_group = QGroupBox(tr('resume_list_group', 'Resume Positions'))
        lg_layout = QVBoxLayout(list_group)
        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        lg_layout.addWidget(self._list_widget)
        layout.addWidget(list_group, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        resume_btn = QPushButton(tr('resume_list_resume', 'Resume Selected'))
        resume_btn.clicked.connect(self._resume_selected)
        resume_btn.setToolTip(tr('resume_tooltip', '继续播放选中记录'))
        btn_row.addWidget(resume_btn)

        delete_btn = QPushButton(tr('resume_list_delete', 'Delete Selected'))
        delete_btn.clicked.connect(self._delete_selected)
        delete_btn.setToolTip(tr('delete_tooltip', '删除选中记录'))
        btn_row.addWidget(delete_btn)

        clear_all_btn = QPushButton(tr('resume_list_clear_all', 'Clear All'))
        clear_all_btn.clicked.connect(self._clear_all)
        clear_all_btn.setToolTip(tr('clear_all_tooltip', '清空全部记录'))
        btn_row.addWidget(clear_all_btn)

        btn_row.addStretch()

        refresh_btn = QPushButton(tr('ctx_refresh', 'Refresh'))
        refresh_btn.clicked.connect(self._reload_list)
        refresh_btn.setToolTip(tr('refresh_tooltip', '刷新列表'))
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton(tr('playback_queue_close', 'Close'))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(DelayMs.UI_REFRESH, self._reload_list)

    # ---------- 数据加载 ----------
    def _reload_list(self):
        tr = self.window.language_manager.tr
        try:
            entries = self.window.config.load_all_resume_positions()
        except Exception as e:
            logger.debug(f"加载断点列表失败: {e}")
            entries = []

        self._list_widget.clear()
        if not entries:
            empty_item = QListWidgetItem(tr('resume_list_empty', 'No saved positions'))
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self._list_widget.addItem(empty_item)
            return

        current_url = ''
        cur = getattr(self.window, 'current_channel', None)
        if cur and isinstance(cur, dict):
            current_url = cur.get('url', '') or ''

        current_label = tr('playback_queue_current', 'Current')
        for entry in entries:
            try:
                url = entry.get('url', '')
                name = entry.get('name', '') or self._basename(url)
                position = float(entry.get('position', 0) or 0)
                duration = float(entry.get('duration', 0) or 0)
                updated = int(entry.get('updated_at', 0) or 0)
            except (ValueError, TypeError):
                continue
            is_current = (url and url == current_url)

            pos_str = self._format_time(position)
            dur_str = self._format_time(duration) if duration > 0 else '--:--'
            time_str = self._format_relative_time(updated)

            prefix = '▶ ' if is_current else '  '
            text = f"{prefix}{name}"
            sub = f"   {pos_str} / {dur_str}   ·   {time_str}"
            if is_current:
                text += f"  [{current_label}]"
            item = QListWidgetItem(f"{text}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, url)
            if is_current:
                try:
                    c = AppStyles._get_colors()
                    item.setForeground(QColor(c.get('accent')))
                except Exception as e:
                    logger.debug(f"_reload_list: {e}")
            self._list_widget.addItem(item)
            if is_current:
                self._list_widget.setCurrentItem(item)

    @staticmethod
    def _basename(url: str) -> str:
        try:
            import os
            return os.path.basename(url.replace('file://', '').split('?')[0]) or url
        except Exception:
            return url

    @staticmethod
    def _format_time(seconds: float) -> str:
        try:
            s = int(seconds)
            h = s // 3600
            m = (s % 3600) // 60
            sec = s % 60
            if h > 0:
                return f"{h:d}:{m:02d}:{sec:02d}"
            return f"{m:d}:{sec:02d}"
        except Exception:
            return "--:--"

    def _format_relative_time(self, ts: int) -> str:
        if not ts:
            return ''
        try:
            now = int(time.time())
            diff = now - ts
            tr = self.window.language_manager.tr
            if diff < 60:
                return tr('just_now', 'just now')
            if diff < 3600:
                return tr('minutes_ago', '{}m ago').format(diff // 60)
            if diff < 86400:
                return tr('hours_ago', '{}h ago').format(diff // 3600)
            if diff < 86400 * 30:
                return tr('days_ago', '{}d ago').format(diff // 86400)
            return time.strftime('%Y-%m-%d', time.localtime(ts))
        except Exception:
            return ''

    # ---------- 操作 ----------
    def _get_selected_url(self) -> Optional[str]:
        item = self._list_widget.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _resume_selected(self):
        url = self._get_selected_url()
        if not url:
            return
        rc = self._resume_ctrl
        if rc and hasattr(rc, 'resume_specific'):
            rc.resume_specific(url)
            # 关闭对话框（避免遮挡播放画面）
            self.close()

    def _delete_selected(self):
        url = self._get_selected_url()
        if not url:
            return
        try:
            self.window.config.clear_resume_position(url)
            self._reload_list()
        except Exception as e:
            logger.debug(f"删除断点失败: {e}")

    def _clear_all(self):
        try:
            rc = self._resume_ctrl
            if rc and hasattr(rc, 'clear_all_resume_positions'):
                rc.clear_all_resume_positions()
            self.window.config.clear_all_resume_positions()
            self._reload_list()
        except Exception as e:
            logger.debug(f"清除所有断点失败: {e}")

    def _on_item_double_clicked(self, item: QListWidgetItem):
        url = item.data(Qt.ItemDataRole.UserRole)
        if not url:
            return
        rc = self._resume_ctrl
        if rc and hasattr(rc, 'resume_specific'):
            rc.resume_specific(url)
            self.close()

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
