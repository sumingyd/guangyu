from typing import Dict, Any, List
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QLabel)
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer
from PySide6 import QtWidgets
from ui.styles import AppStyles
from ui.floating_dialog import FloatingDialog
from core.log_manager import global_logger as logger


class _EpgSearchWorker(QThread):
    results_ready = Signal(list)
    MAX_RESULTS = 200

    def __init__(self, epg_parser, keyword):
        super().__init__()
        self._epg_parser = epg_parser
        self._keyword = keyword

    def run(self):
        results = []
        try:
            epg_data = self._epg_parser.get_epg_data_copy() if hasattr(self._epg_parser, 'get_epg_data_copy') else getattr(self._epg_parser, '_epg_data', None)
            if epg_data and isinstance(epg_data, dict):
                for epg_id, programs in epg_data.items():
                    if self.isInterruptionRequested():
                        return
                    if not isinstance(programs, list):
                        continue
                    for prog in programs:
                        if self.isInterruptionRequested():
                            return
                        title = (prog.get('title', '') or '').lower()
                        if self._keyword in title:
                            results.append({
                                'name': prog.get('title', ''),
                                'epg_id': epg_id,
                                '_program': prog,
                            })
                            break
                    if len(results) >= self.MAX_RESULTS:
                        break
        except Exception as e:
            logger.debug(f"EPG搜索异常: {e}")
        self.results_ready.emit(results)


class GlobalSearchDialog(FloatingDialog):
    channel_selected = Signal(dict)

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        self.setWindowTitle(main_window.language_manager.tr('global_search', '全局搜索'))
        self.setMinimumSize(500, 400)
        self._results: List[Dict[str, Any]] = []
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def closeEvent(self, event):
        if getattr(self, '_epg_worker', None):
            self._epg_worker.requestInterruption()
            self._epg_worker.wait(3000)
            self._epg_worker.deleteLater()
            self._epg_worker = None
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
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr('global_search_placeholder', '搜索频道名/分组/节目...'))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self.search_input)
        layout.addLayout(search_row)

        self.result_list = QListWidget()
        self.result_list.setSpacing(2)
        self.result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.result_list, 1)

        self.count_label = QLabel(tr('search_type_to_search', '输入关键词开始搜索'))
        layout.addWidget(self.count_label)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._on_search)
        self._pending_text = ''
        self._epg_worker = None

    def _on_search_text_changed(self, text: str):
        self._search_timer.stop()
        text = text.strip().lower()
        if not text:
            self.result_list.clear()
            self._results.clear()
            if self._epg_worker and self._epg_worker.isRunning():
                self._epg_worker.results_ready.disconnect(self._on_epg_results)
                self._epg_worker.requestInterruption()
                self._epg_worker.wait(1000)
            tr = self.window.language_manager.tr
            self.count_label.setText(tr('search_type_to_search', '输入关键词开始搜索'))
            return
        self._pending_text = text
        tr = self.window.language_manager.tr
        self.count_label.setText(tr('searching', '搜索中...'))
        self._search_timer.start()

    def _on_search(self):
        text = self._pending_text
        self.result_list.clear()
        self._results.clear()
        if not text:
            return

        w = self.window
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

        epg_parser = getattr(w, 'epg_parser', None)
        if epg_parser:
            if self._epg_worker and self._epg_worker.isRunning():
                self._epg_worker.results_ready.disconnect(self._on_epg_results)
                self._epg_worker.requestInterruption()
                self._epg_worker.wait(1000)
            self._epg_worker = _EpgSearchWorker(epg_parser, text)
            self._epg_worker.results_ready.connect(self._on_epg_results)
            self._epg_worker.start()
        else:
            self._render_results()

    def _on_epg_results(self, epg_results):
        tr = self.window.language_manager.tr
        for item in epg_results:
            entry = {
                'name': f"{tr('epg_program', '节目')}: {item['name']} ({item['epg_id']})",
                'url': '',
                'group': tr('epg_search_result', 'EPG搜索结果'),
                '_is_epg': True,
                '_channel_name': item['epg_id'],
                '_program': item['_program'],
            }
            self._results.append(entry)
        self._render_results()

    def _render_results(self):
        c = AppStyles._get_colors()
        name_style = f"color: {c.get('window_text')}; background-color: transparent;"

        for idx, ch in enumerate(self._results):
            try:
                channel_name = ch.get('name', '')
                group = ch.get('group', '')
                display = f"{channel_name}  [{group}]" if group else channel_name

                item_widget = QtWidgets.QWidget()
                item_layout = QtWidgets.QHBoxLayout(item_widget)
                item_layout.setContentsMargins(5, 2, 5, 2)
                item_layout.setSpacing(8)

                name_label = QtWidgets.QLabel(display)
                name_label.setStyleSheet(name_style)
                name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                name_label.setWordWrap(False)
                item_layout.addWidget(name_label, 1)

                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 36))
                item.setData(Qt.ItemDataRole.UserRole, idx)
                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, item_widget)
            except Exception as e:
                logger.debug(f"构建搜索结果失败 idx={idx}: {e}")

        count = len(self._results)
        tr = self.window.language_manager.tr
        self.count_label.setText(tr('search_results_count', '找到 {count} 个结果').format(count=count))

    def _on_item_double_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self._results):
            ch = self._results[idx]
            if ch.get('_is_epg'):
                ch_name = ch.get('_channel_name', '')
                w = self.window
                for src_ch in list(getattr(w, '_sub_channels', [])) + list(getattr(w, '_local_channels', [])):
                    if src_ch.get('name', '') == ch_name or src_ch.get('tvg_id', '') == ch_name:
                        self.channel_selected.emit(src_ch)
                        break
            else:
                self.channel_selected.emit(ch)
            self.accept()

    def show_and_focus(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
