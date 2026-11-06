from typing import Dict, Any, List
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QLabel,
                               QCheckBox, QWidget)
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer
from PySide6 import QtWidgets
from ui.styles import AppStyles
from ui.floating_dialog import FloatingDialog
from core.log_manager import global_logger as logger


class _EpgSearchWorker(QThread):
    results_ready = Signal(list, list)
    MAX_RESULTS = 200

    def __init__(self, epg_parser, channels, keyword):
        super().__init__()
        self._epg_parser = epg_parser
        self._channels = channels
        self._keyword = keyword

    def run(self):
        keyword = self._keyword
        results = []
        result_channels = []
        seen = set()

        ch_map = {}
        for ch in self._channels:
            if self.isInterruptionRequested():
                return
            name = ch.get('name', '')
            if name and name not in ch_map:
                ch_map[name] = ch
            tvg_id = ch.get('tvg_id', '')
            if tvg_id and tvg_id not in ch_map:
                ch_map[tvg_id] = ch

        epg_data = (
            self._epg_parser.get_epg_data_copy()
            if hasattr(self._epg_parser, 'get_epg_data_copy')
            else getattr(self._epg_parser, '_epg_data', None)
        )
        if not epg_data or not isinstance(epg_data, dict):
            self.results_ready.emit(results, result_channels)
            return

        for epg_id, programs in epg_data.items():
            if self.isInterruptionRequested():
                return
            if not isinstance(programs, list):
                continue
            ch = ch_map.get(epg_id)
            for prog in programs:
                if self.isInterruptionRequested():
                    return
                title = (prog.get('title', '') or '').lower()
                if keyword in title:
                    key = f"{epg_id}_{prog.get('title', '')}_{prog.get('start', '')}"
                    if key not in seen:
                        seen.add(key)
                        results.append(prog)
                        result_channels.append(ch if ch else {'name': epg_id})
                        if len(results) >= self.MAX_RESULTS:
                            break
            if len(results) >= self.MAX_RESULTS:
                break

        results.sort(key=lambda r: r.get('start', ''))
        self.results_ready.emit(results, result_channels)


class UnifiedSearchDialog(FloatingDialog):
    channel_selected = Signal(dict)
    epg_program_selected = Signal(dict, dict)

    def __init__(self, main_window, parent=None, search_epg=True, search_channel=True):
        super().__init__(parent, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self._title_text = tr('search', '搜索')
        self.setWindowTitle(self._title_text)
        self.setMinimumSize(500, 400)
        self._results: List[Dict[str, Any]] = []
        self._result_channels: List[Dict[str, Any]] = []
        self._epg_results: List[Dict[str, Any]] = []
        self._initial_search_epg = search_epg
        self._initial_search_channel = search_channel
        self._worker = None
        self._retired_workers = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._do_search)
        self._pending_text = ''
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def _retire_worker(self, worker):
        """非阻塞停止搜索线程：中断请求发出后由 finished 信号负责销毁。"""
        if worker is None:
            return
        try:
            worker.results_ready.disconnect(self._on_epg_search_results)
        except (RuntimeError, TypeError):
            pass
        worker.requestInterruption()
        if worker.isRunning():
            self._retired_workers.append(worker)
        else:
            worker.deleteLater()

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._worker:
            self._worker = None
        try:
            self._retired_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def closeEvent(self, event):
        if self._worker is not None:
            self._retire_worker(self._worker)
            self._worker = None
        if hasattr(self, '_search_timer'):
            self._search_timer.stop()
        # 对话框实例会被复用，保持注册在 ThemeManager 中（销毁时自动注销）
        super().closeEvent(event)

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c.get('panel', c['base'])};
                color: {c.get('window_text')};
            }}
            QLabel {{
                color: {c.get('window_text')};
                background-color: transparent;
            }}
            QLineEdit {{
                background-color: {c.get('player_combo')};
                color: {c.get('window_text')};
                border: 1px solid {c.get('player_line')};
                border-radius: {r}px;
                padding: 4px 8px;
                min-height: 28px;
            }}
            QCheckBox {{
                color: {c.get('window_text')};
                background-color: transparent;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {c.get('player_line')};
                border-radius: 3px;
                background-color: {c.get('player_combo')};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c.get('accent')};
                border-color: {c.get('accent')};
            }}
            QListWidget {{
                background-color: transparent;
                color: {c.get('window_text')};
                border: none; outline: none;
            }}
            QListWidget::item {{
                padding: 2px 4px; min-height: 26px;
                border: 1px solid transparent; border-radius: {r}px;
            }}
            QListWidget::item:selected {{
                border: 1px solid {c.get('accent')};
                background-color: {c.get('highlight')};
                color: {c.get('highlighted_text')};
            }}
            QListWidget::item:hover {{
                border: 1px solid {c.get('player_line')};
                background-color: {c.get('highlight')};
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

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr('search_placeholder', '输入关键词搜索...'))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self.search_input, 1)
        content_layout.addLayout(search_row)

        scope_row = QHBoxLayout()
        scope_row.setSpacing(16)
        self.channel_cb = QCheckBox(tr('search_scope_channel', '频道'))
        self.channel_cb.setChecked(self._initial_search_channel)
        self.channel_cb.stateChanged.connect(self._on_scope_changed)
        scope_row.addWidget(self.channel_cb)

        self.epg_cb = QCheckBox(tr('search_scope_epg', 'EPG节目'))
        self.epg_cb.setChecked(self._initial_search_epg)
        self.epg_cb.stateChanged.connect(self._on_scope_changed)
        scope_row.addWidget(self.epg_cb)

        scope_row.addStretch(1)
        content_layout.addLayout(scope_row)

        self.result_list = QListWidget()
        self.result_list.setSpacing(2)
        self.result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        content_layout.addWidget(self.result_list, 1)

        self.count_label = QLabel(tr('search_type_to_search', '输入关键词开始搜索'))
        content_layout.addWidget(self.count_label)

        layout.addLayout(content_layout)

    def _on_scope_changed(self):
        if self._pending_text:
            self._search_timer.stop()
            self._search_timer.start()

    def _on_search_text_changed(self, text: str):
        self._search_timer.stop()
        text = text.strip().lower()
        if not text:
            self.result_list.clear()
            self._results.clear()
            self._result_channels.clear()
            self._epg_results.clear()
            if self._worker is not None:
                self._retire_worker(self._worker)
                self._worker = None
            tr = self.window.language_manager.tr
            self.count_label.setText(tr('search_type_to_search', '输入关键词开始搜索'))
            return
        self._pending_text = text
        tr = self.window.language_manager.tr
        self.count_label.setText(tr('searching', '搜索中...'))
        self._search_timer.start()

    def _do_search(self):
        text = self._pending_text
        if not text:
            return

        self.result_list.clear()
        self._results.clear()
        self._result_channels.clear()
        self._epg_results.clear()

        w = self.window
        tr = w.language_manager.tr
        search_channel = self.channel_cb.isChecked()
        search_epg = self.epg_cb.isChecked()

        if not search_channel and not search_epg:
            self.count_label.setText(tr('search_no_scope', '请至少选择一个搜索范围'))
            return

        if search_channel:
            all_channels = list(getattr(w, '_sub_channels', [])) + list(getattr(w, '_local_channels', []))
            seen_urls = set()
            for ch in all_channels:
                url = ch.get('url', '')
                if url in seen_urls:
                    continue
                name = ch.get('name', '').lower()
                group = ch.get('group', '').lower()
                if text in name or text in group or text in url:
                    self._results.append(ch)
                    seen_urls.add(url)

        if search_epg:
            epg_parser = getattr(w, 'epg_parser', None)
            if epg_parser:
                if self._worker is not None:
                    self._retire_worker(self._worker)
                    self._worker = None
                channels = list(getattr(w, '_sub_channels', []))
                worker = _EpgSearchWorker(epg_parser, channels, text)
                worker.results_ready.connect(self._on_epg_search_results)
                worker.finished.connect(self._on_worker_finished)
                self._worker = worker
                worker.start()
            else:
                self._render_results()
        else:
            self._render_results()

    def _on_epg_search_results(self, results, result_channels):
        self._epg_results = results
        self._result_channels = result_channels
        self._render_results()

    def _render_results(self):
        c = AppStyles._get_colors()
        name_style = (
            f"color: {c.get('window_text')};"
            f" background-color: transparent;"
        )
        secondary_style = (
            f"color: {c.get('player_panel_secondary', c.get('window_text'))};"
            f" background-color: transparent; font-size: 11px;"
        )
        tr = self.window.language_manager.tr

        channel_results = self._results
        epg_results = self._epg_results
        epg_channels = self._result_channels

        self.result_list.clear()

        for idx, ch in enumerate(channel_results):
            try:
                channel_name = ch.get('name', '')
                group = ch.get('group', '')

                item_widget = QWidget()
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(5, 2, 5, 2)
                item_layout.setSpacing(8)

                name_label = QtWidgets.QLabel(channel_name)
                name_label.setStyleSheet(name_style)
                name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                name_label.setWordWrap(False)
                item_layout.addWidget(name_label, 1)

                if group:
                    group_label = QtWidgets.QLabel(f'[{group}]')
                    group_label.setStyleSheet(secondary_style)
                    group_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    item_layout.addWidget(group_label)

                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 36))
                item.setData(Qt.ItemDataRole.UserRole, ('channel', idx))
                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, item_widget)
            except Exception as e:
                logger.debug(f"构建频道搜索结果失败 idx={idx}: {e}")

        for idx, prog in enumerate(epg_results):
            try:
                ch = epg_channels[idx] if idx < len(epg_channels) else {}
                ch_name = ch.get('name', '')
                title = prog.get('title', '')
                start = prog.get('start', '')
                time_str = ''
                if start:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(start)
                        time_str = dt.strftime('%H:%M')
                    except Exception as e:
                        logger.debug(f"_render_results: {e}")

                item_widget = QWidget()
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(5, 2, 5, 2)
                item_layout.setSpacing(8)

                display_parts = []
                if time_str:
                    display_parts.append(time_str)
                display_parts.append(title)
                display_text = ' '.join(display_parts)

                name_label = QtWidgets.QLabel(display_text)
                name_label.setStyleSheet(name_style)
                name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                name_label.setWordWrap(False)
                item_layout.addWidget(name_label, 1)

                if ch_name:
                    ch_label = QtWidgets.QLabel(f'({ch_name})')
                    ch_label.setStyleSheet(secondary_style)
                    ch_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    item_layout.addWidget(ch_label)

                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 36))
                item.setData(Qt.ItemDataRole.UserRole, ('epg', idx))
                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, item_widget)
            except Exception as e:
                logger.debug(f"构建 EPG 搜索结果失败 idx={idx}: {e}")

        total = len(channel_results) + len(epg_results)
        is_truncated = len(epg_results) >= _EpgSearchWorker.MAX_RESULTS
        if is_truncated:
            self.count_label.setText(tr('search_results_truncated', '找到 {count}+ 个结果（已截断）').format(count=total))
        elif total > 0:
            self.count_label.setText(tr('search_results_count', '找到 {count} 个结果').format(count=total))
        else:
            self.count_label.setText(tr('search_no_results', '无结果'))

    def _on_item_double_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data or not isinstance(data, tuple):
            return
        kind, idx = data
        if kind == 'channel' and 0 <= idx < len(self._results):
            ch = self._results[idx]
            self.channel_selected.emit(ch)
            self.accept()
        elif kind == 'epg' and 0 <= idx < len(self._epg_results):
            ch = self._result_channels[idx] if idx < len(self._result_channels) else {}
            prog = self._epg_results[idx]
            self.epg_program_selected.emit(ch, prog)
            self.accept()

    def show_and_focus(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
