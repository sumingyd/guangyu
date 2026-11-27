"""书签与章节对话框 - 显示视频内置章节和用户书签"""
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QWidget,
    QAbstractItemView,
    QInputDialog,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class BookmarkDialog(FloatingDialog):
    """书签与章节对话框
    - 章节标签页：显示视频内置章节列表（只读，双击跳转）
    - 书签标签页：显示当前视频/所有视频的用户书签，支持添加/删除/跳转
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('bookmark_title', 'Bookmarks & Chapters'))
        self.setMinimumSize(640, 480)
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        QTimer.singleShot(DelayMs.UI_REFRESH, self._reload_all)

    @property
    def _bookmark_ctrl(self) -> Optional[object]:
        return getattr(self.window, 'bookmark_ctrl', None)

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
                color: {c.get('bright_text')};
            }}
            QTabWidget::pane {{
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                top: -1px;
            }}
            QTabBar::tab {{
                background: {c.get('button')};
                color: {text_color};
                padding: 6px 14px;
                border: 1px solid {c.get('mid')};
                border-bottom: none;
                border-top-left-radius: {r}px;
                border-top-right-radius: {r}px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {c.get('accent')};
                color: {c.get('bright_text')};
            }}
            QLineEdit {{
                background: {c.get('base')};
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                padding: 4px 8px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 顶部说明
        info_label = QLabel(tr('bookmark_info',
            'Chapters are video built-in. Bookmarks are user-defined. Double-click to seek.'))
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 标签页
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        # ===== 章节标签页 =====
        chapter_tab = QWidget()
        clayout = QVBoxLayout(chapter_tab)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(8)
        self._chapter_list = QListWidget()
        self._chapter_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._chapter_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._chapter_list.itemDoubleClicked.connect(self._on_chapter_double_clicked)
        clayout.addWidget(self._chapter_list)

        chap_btn_row = QHBoxLayout()
        chap_prev = QPushButton(tr('bookmark_chapter_prev', 'Previous Chapter'))
        chap_prev.clicked.connect(self._on_prev_chapter)
        chap_prev.setToolTip(tr('chap_prev_tooltip', '上一个章节'))
        chap_btn_row.addWidget(chap_prev)
        chap_next = QPushButton(tr('bookmark_chapter_next', 'Next Chapter'))
        chap_next.clicked.connect(self._on_next_chapter)
        chap_next.setToolTip(tr('chap_next_tooltip', '下一个章节'))
        chap_btn_row.addWidget(chap_next)
        chap_btn_row.addStretch()
        chap_refresh = QPushButton(tr('ctx_refresh', 'Refresh'))
        chap_refresh.clicked.connect(self._reload_chapters)
        chap_refresh.setToolTip(tr('chap_refresh_tooltip', '刷新章节列表'))
        chap_btn_row.addWidget(chap_refresh)
        clayout.addLayout(chap_btn_row)

        self._tabs.addTab(chapter_tab, tr('bookmark_tab_chapters', 'Chapters'))

        # ===== 书签标签页 =====
        bookmark_tab = QWidget()
        blayout = QVBoxLayout(bookmark_tab)
        blayout.setContentsMargins(0, 0, 0, 0)
        blayout.setSpacing(8)

        # 视图切换：当前视频 / 全部
        view_row = QHBoxLayout()
        view_row.addWidget(QLabel(tr('bookmark_view_label', 'View:')))
        self._view_combo = self._build_view_combo()
        view_row.addWidget(self._view_combo, 1)
        view_row.addStretch()
        blayout.addLayout(view_row)

        self._bookmark_list = QListWidget()
        self._bookmark_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._bookmark_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._bookmark_list.itemDoubleClicked.connect(self._on_bookmark_double_clicked)
        blayout.addWidget(self._bookmark_list)

        bm_btn_row = QHBoxLayout()
        add_btn = QPushButton(tr('bookmark_add', 'Add Bookmark'))
        add_btn.clicked.connect(self._on_add_bookmark)
        add_btn.setToolTip(tr('bookmark_add_tooltip', '添加书签'))
        bm_btn_row.addWidget(add_btn)
        delete_btn = QPushButton(tr('bookmark_delete', 'Delete Selected'))
        delete_btn.clicked.connect(self._on_delete_bookmark)
        delete_btn.setToolTip(tr('bookmark_delete_tooltip', '删除书签'))
        bm_btn_row.addWidget(delete_btn)
        clear_url_btn = QPushButton(tr('bookmark_clear_url', 'Clear Current File'))
        clear_url_btn.clicked.connect(self._on_clear_current_url)
        clear_url_btn.setToolTip(tr('clear_url_tooltip', '清除书签URL'))
        bm_btn_row.addWidget(clear_url_btn)
        clear_all_btn = QPushButton(tr('bookmark_clear_all', 'Clear All'))
        clear_all_btn.clicked.connect(self._on_clear_all)
        clear_all_btn.setToolTip(tr('clear_all_bookmarks_tooltip', '清空全部书签'))
        bm_btn_row.addWidget(clear_all_btn)
        bm_btn_row.addStretch()
        refresh_btn = QPushButton(tr('ctx_refresh', 'Refresh'))
        refresh_btn.clicked.connect(self._reload_bookmarks)
        refresh_btn.setToolTip(tr('refresh_bookmarks_tooltip', '刷新书签列表'))
        bm_btn_row.addWidget(refresh_btn)
        blayout.addLayout(bm_btn_row)

        self._tabs.addTab(bookmark_tab, tr('bookmark_tab_bookmarks', 'Bookmarks'))

        # 底部关闭
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton(tr('playback_queue_close', 'Close'))
        close_btn.clicked.connect(self.close)
        close_btn.setToolTip(tr('close_tooltip', '关闭'))
        close_btn.setAutoDefault(True)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        QTimer.singleShot(DelayMs.INPUT_DEBOUNCE, self._bookmark_list.setFocus)

    def _build_view_combo(self):
        tr = self.window.language_manager.tr
        combo = QComboBox()
        combo.addItem(tr('bookmark_view_current', 'Current File'), 'current')
        combo.addItem(tr('bookmark_view_all', 'All Files'), 'all')
        combo.setCurrentIndex(0)
        combo.currentIndexChanged.connect(lambda _idx: self._reload_bookmarks())
        return combo

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(DelayMs.UI_REFRESH, self._reload_all)

    # ---------- 数据加载 ----------
    def _reload_all(self):
        self._reload_chapters()
        self._reload_bookmarks()

    def _reload_chapters(self):
        tr = self.window.language_manager.tr
        self._chapter_list.clear()
        try:
            ctrl = self._bookmark_ctrl
            chapters = ctrl.get_chapters() if ctrl and hasattr(ctrl, 'get_chapters') else []
        except Exception as e:
            logger.debug(f"加载章节失败: {e}")
            chapters = []
        if not chapters:
            empty_item = QListWidgetItem(tr('bookmark_chapters_empty', 'No chapters in this video'))
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self._chapter_list.addItem(empty_item)
            return
        try:
            current_idx = ctrl.get_current_chapter() if ctrl and hasattr(ctrl, 'get_current_chapter') else -1
        except Exception:
            current_idx = -1
        current_label = tr('playback_queue_current', 'Current')
        for i, ch in enumerate(chapters):
            title = ch.get('title', '') or tr('bookmark_chapter_n', 'Chapter {}').format(i + 1)
            time_str = self._format_time(float(ch.get('time', 0) or 0))
            is_current = (i == current_idx)
            prefix = '▶ ' if is_current else '  '
            text = f"{prefix}{title}\n   {time_str}"
            if is_current:
                text += f"  [{current_label}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._chapter_list.addItem(item)
            if is_current:
                try:
                    c = AppStyles._get_colors()
                    item.setForeground(QColor(c.get('accent')))
                except Exception as e:
                    logger.debug(f"_reload_chapters: {e}")
                self._chapter_list.setCurrentItem(item)

    def _reload_bookmarks(self):
        tr = self.window.language_manager.tr
        self._bookmark_list.clear()
        try:
            ctrl = self._bookmark_ctrl
            if not ctrl:
                return
            view_mode = self._view_combo.currentData() or 'current'
            if view_mode == 'all':
                entries = ctrl.load_all_bookmarks()
            else:
                # 当前文件
                pc = self.window.player_controller
                if not pc or not pc.is_playing:
                    entries = []
                else:
                    url = pc.current_url or ''
                    marks = ctrl.load_bookmarks(url) if url else []
                    entries = []
                    for m in marks:
                        item = dict(m)
                        item['url'] = url
                        entries.append(item)
        except Exception as e:
            logger.debug(f"加载书签失败: {e}")
            entries = []

        if not entries:
            empty_item = QListWidgetItem(tr('bookmark_empty', 'No bookmarks'))
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self._bookmark_list.addItem(empty_item)
            return

        current_url = ''
        pc = self.window.player_controller
        if pc and pc.is_playing:
            current_url = pc.current_url or ''
        current_label = tr('playback_queue_current', 'Current')

        for entry in entries:
            url = entry.get('url', '')
            name = entry.get('name', '') or ''
            position = float(entry.get('position', 0) or 0)
            created = int(entry.get('created_at', 0) or 0)
            is_current = (url and url == current_url)

            if not name:
                name = self._basename(url)

            pos_str = self._format_time(position)
            time_str = self._format_relative_time(created)
            prefix = '▶ ' if is_current else '  '
            text = f"{prefix}{name}"
            sub = f"   {pos_str}   ·   {time_str}"
            if is_current:
                text += f"  [{current_label}]"
            # 在 all 视图中显示文件名前缀
            if self._view_combo.currentData() == 'all' and not is_current:
                pass  # name 已包含文件名
            item = QListWidgetItem(f"{text}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, {'url': url, 'position': position})
            self._bookmark_list.addItem(item)
            if is_current:
                try:
                    c = AppStyles._get_colors()
                    item.setForeground(QColor(c.get('accent')))
                except Exception as e:
                    logger.debug(f"_reload_bookmarks: {e}")
                self._bookmark_list.setCurrentItem(item)

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
            from core.language_manager import LanguageManager
            tr = LanguageManager().tr
            now = int(time.time())
            diff = now - ts
            if diff < 60:
                return tr('just_now', '刚刚')
            if diff < 3600:
                return tr('minutes_ago', '{}分钟前').format(diff // 60)
            if diff < 86400:
                return tr('hours_ago', '{}小时前').format(diff // 3600)
            if diff < 86400 * 30:
                return tr('days_ago', '{}天前').format(diff // 86400)
            return time.strftime('%Y-%m-%d', time.localtime(ts))
        except Exception:
            return ''

    # ---------- 章节操作 ----------
    def _on_chapter_double_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'seek_to_chapter'):
            ctrl.seek_to_chapter(int(idx))

    def _on_prev_chapter(self):
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'prev_chapter'):
            ctrl.prev_chapter()
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, self._reload_chapters)

    def _on_next_chapter(self):
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'next_chapter'):
            ctrl.next_chapter()
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, self._reload_chapters)

    # ---------- 书签操作 ----------
    def _on_add_bookmark(self):
        ctrl = self._bookmark_ctrl
        if not ctrl or not hasattr(ctrl, 'add_bookmark'):
            return
        tr = self.window.language_manager.tr
        # 弹出输入对话框获取书签名称（可选）
        name, ok = QInputDialog.getText(
            self,
            tr('bookmark_add_title', 'Add Bookmark'),
            tr('bookmark_add_prompt', 'Bookmark name (optional):'),
            text='',
        )
        if not ok:
            return
        ctrl.add_bookmark(name or '')

    def _on_delete_bookmark(self):
        item = self._bookmark_list.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        url = data.get('url', '')
        position = float(data.get('position', 0) or 0)
        if not url:
            return
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'delete_bookmark'):
            ctrl.delete_bookmark(url, position)

    def _on_clear_current_url(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            url = pc.current_url or ''
            if not url:
                return
            ctrl = self._bookmark_ctrl
            if ctrl and hasattr(ctrl, 'clear_bookmarks'):
                ctrl.clear_bookmarks(url)
        except Exception as e:
            logger.debug(f"清除当前文件书签失败: {e}")

    def _on_clear_all(self):
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'clear_all_bookmarks'):
            ctrl.clear_all_bookmarks()

    def _on_bookmark_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        url = data.get('url', '')
        position = float(data.get('position', 0) or 0)
        if not url:
            return
        ctrl = self._bookmark_ctrl
        if ctrl and hasattr(ctrl, 'seek_to_bookmark'):
            ctrl.seek_to_bookmark(url, position)

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
