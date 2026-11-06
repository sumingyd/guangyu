from typing import Dict, Any, List
from datetime import datetime, date
import time
from PySide6.QtWidgets import (
    QPushButton,
    QDateEdit,
    QLabel,
    QWidget,
    QCalendarWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QToolButton,
)
from PySide6.QtCore import Qt, QDate, Signal, QThread, QTimer
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QIcon
from ui.styles import AppStyles
from ui.floating_dialog import FloatingDialog
from ui.epg_timeline_widget import EpgTimelineWidget, EpgChannelHeaderWidget, EpgTimeHeaderWidget
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs
from utils.thread_safety import safe_single_shot


class _ThemedCalendarWidget(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._prev_icon = None
        self._next_icon = None

    def set_nav_icons(self, prev_icon: QIcon, next_icon: QIcon):
        self._prev_icon = prev_icon
        self._next_icon = next_icon
        self._apply_nav_icons()

    def _apply_nav_icons(self):
        tool_buttons = self.findChildren(QToolButton)
        if len(tool_buttons) >= 4:
            if self._prev_icon:
                tool_buttons[0].setIcon(self._prev_icon)
                tool_buttons[0].setArrowType(Qt.ArrowType.NoArrow)
            if self._next_icon:
                tool_buttons[1].setIcon(self._next_icon)
                tool_buttons[1].setArrowType(Qt.ArrowType.NoArrow)

    def showEvent(self, event):
        super().showEvent(event)
        safe_single_shot(DelayMs.UI_REFRESH, self, self._apply_nav_icons)

    def paintEvent(self, event):
        super().paintEvent(event)


class _TimelineLoadWorker(QThread):
    data_ready = Signal(list, object)

    def __init__(self, epg_parser, channels, selected_date):
        super().__init__()
        self._epg_parser = epg_parser
        self._channels = channels
        self._selected_date = selected_date
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        channels_data = []
        for ch in self._channels:
            if self._abort:
                return
            ch_name = ch.get('name', '')
            tvg_id = ch.get('tvg_id', '')
            all_tags = ch.get('_all_tags', {})
            tvg_name = all_tags.get('tvg-name', '')
            comma_name = ''
            raw_extinf = ch.get('_raw_extinf', '')
            if raw_extinf and ',' in raw_extinf:
                comma_name = raw_extinf.split(',', 1)[-1].strip()
                if comma_name.startswith('"') and comma_name.endswith('"'):
                    comma_name = comma_name[1:-1]

            programs = []
            try:
                all_programs = self._epg_parser.get_channel_epg(
                    ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name
                ) or []
                if all_programs and self._selected_date:
                    for p in all_programs:
                        try:
                            p_start = datetime.fromisoformat(p.get('start', ''))
                            p_end = datetime.fromisoformat(p.get('end', ''))
                            if p_start.date() <= self._selected_date <= p_end.date():
                                programs.append(p)
                        except Exception as e:
                            logger.debug(f"run: {e}")
                else:
                    programs = all_programs
            except Exception as e:
                logger.debug(f"EPG时间轴获取节目失败: {ch_name} - {e}")

            channels_data.append({
                'name': ch_name,
                # 保留原始频道对象，双击时按对象精确播台（同名频道不会串台）
                'channel': ch,
                'logo': ch.get('logo') or ch.get('logo_url') or all_tags.get('tvg-logo', ''),
                'programs': programs,
            })
        self.data_ready.emit(channels_data, self._selected_date)


class EpgTimelineDialog(FloatingDialog):
    channel_selected = Signal(dict)

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=True, stay_on_top=False, tool_window=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self._title_text = tr('epg_timeline', 'EPG时间轴')
        self.setWindowTitle(self._title_text)
        self.setMinimumSize(1000, 600)
        self._channels_data: List[Dict[str, Any]] = []
        self._load_worker = None
        self._retired_workers = []
        self._selected_date_ref = None
        self._epg_dates_cache = set()
        self._epg_dates_cache_ts = 0.0
        self._setup_ui()
        self._apply_theme()
        self._load_data()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def reapply_styles(self):
        self._apply_theme()
        self._update_corner_widget()
        self._update_date_edit_icon()
        self._update_calendar_nav_icons()
        self._mark_calendar_dates()
        self.timeline_widget.update()
        self.channel_header.update()
        self.time_header.update()

    def _update_date_edit_icon(self):
        try:
            icon_color = AppStyles.get_color('window_text')
            icon_path = AppStyles.get_icon('chevron_down', icon_color, 12)
            if icon_path:
                safe_icon = icon_path.replace('\\', '/')
                # 每次整体覆盖而非累加，避免主题切换多次后 QSS 无限膨胀
                self.date_edit.setStyleSheet(
                    "QDateEdit::drop-down {"
                    " border: none;"
                    " width: 20px;"
                    " subcontrol-origin: padding;"
                    " subcontrol-position: center right;"
                    f" image: url({safe_icon});"
                    " }"
                )
        except Exception as e:
            logger.debug(f"_update_date_edit_icon: {e}")


    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        style = AppStyles._visual_style
        if style == 'frosted':
            from ui.styles import rgba_to_blended_hex
            effective_mode = AppStyles._get_effective_color_mode()
            bg = (0, 0, 0) if effective_mode == 'dark' else (255, 255, 255)
            tc = {}
            for k, v in c.items():
                tc[k] = rgba_to_blended_hex(v, bg) if isinstance(v, str) and v.startswith('rgba') else v
        else:
            tc = c
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QDateEdit {{
                background-color: {tc.get('player_combo')};
                color: {tc.get('window_text')};
                border: 1px solid {tc.get('player_line')};
                border-radius: {r}px;
                padding: 2px 4px 2px 8px;
                min-height: 24px;
            }}
            QDateEdit::up-button {{
                width: 0px;
                border: none;
            }}
            QDateEdit::down-button {{
                width: 0px;
                border: none;
            }}
            QDateEdit::drop-down {{
                border: none;
                width: 20px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            QCalendarWidget {{
                background-color: {tc.get('base')};
                color: {tc.get('window_text')};
            }}
            QCalendarWidget QWidget {{
                alternate-background-color: {tc.get('alternate_base')};
            }}
            QCalendarWidget QToolButton {{
                color: {tc.get('window_text')};
                background-color: {tc.get('player_button')};
                border: 1px solid {tc.get('player_line')};
                border-radius: {r}px;
                padding: 4px;
                min-width: 80px;
            }}
            QCalendarWidget QToolButton:hover {{
                background-color: {tc.get('alternate_base')};
                border-color: {tc.get('accent')};
            }}
            QCalendarWidget QToolButton:pressed {{
                background-color: {tc.get('accent')};
                color: {tc.get('highlighted_text')};
            }}
            QCalendarWidget QMenu {{
                background-color: {tc.get('base')};
                color: {tc.get('window_text')};
            }}
            QCalendarWidget QAbstractItemView {{
                background-color: {tc.get('base')};
                color: {tc.get('window_text')};
                selection-background-color: {tc.get('accent')};
                selection-color: {tc.get('highlighted_text')};
                alternate-background-color: {tc.get('alternate_base')};
            }}
            QCalendarWidget QSpinBox {{
                color: {tc.get('window_text')};
                background-color: {tc.get('player_combo')};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 0, 8, 8)
        outer_layout.setSpacing(0)

        title_bar = FloatingDialog.create_dialog_title_bar(self._title_text, self)
        outer_layout.addWidget(title_bar)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(8, 8, 8, 0)
        content_layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        date_label = QLabel(tr('epg_date', '日期'))
        toolbar.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self._calendar = _ThemedCalendarWidget()
        self.date_edit.setCalendarWidget(self._calendar)
        self.date_edit.setDisplayFormat('yyyy-MM-dd')
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        self.date_edit.setFixedSize(140, 30)
        toolbar.addWidget(self.date_edit)

        safe_single_shot(DelayMs.NEXT_TICK, self, self._update_date_edit_icon)

        toolbar.addStretch(1)

        self._status_label = QLabel('')
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        toolbar.addWidget(self._status_label)

        self.refresh_btn = QPushButton(tr('refresh', '刷新'))
        self.refresh_btn.clicked.connect(self._load_data)
        toolbar.addWidget(self.refresh_btn)

        content_layout.addLayout(toolbar)

        self._grid_widget = QWidget()
        self._grid_layout = QVBoxLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)

        self._corner_widget = QWidget()
        self._corner_widget.setFixedSize(EpgTimelineWidget.LEFT_MARGIN, EpgTimelineWidget.HEADER_HEIGHT)
        top_row.addWidget(self._corner_widget)

        self.time_header_scroll = QScrollArea()
        self.time_header_scroll.setWidgetResizable(True)
        self.time_header_scroll.setFixedHeight(EpgTimelineWidget.HEADER_HEIGHT)
        self.time_header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.time_header_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.time_header = EpgTimeHeaderWidget()
        self.time_header.setFixedHeight(EpgTimelineWidget.HEADER_HEIGHT)
        self.time_header_scroll.setWidget(self.time_header)
        top_row.addWidget(self.time_header_scroll, 1)

        self._grid_layout.addLayout(top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(0)

        self.channel_scroll = QScrollArea()
        self.channel_scroll.setWidgetResizable(True)
        self.channel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.channel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.channel_scroll.setFixedWidth(EpgTimelineWidget.LEFT_MARGIN)
        self.channel_header = EpgChannelHeaderWidget()
        self.channel_scroll.setWidget(self.channel_header)
        bottom_row.addWidget(self.channel_scroll)

        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.timeline_widget = EpgTimelineWidget()
        self.timeline_widget.channel_double_clicked.connect(self._on_channel_double_clicked)
        self.main_scroll.setWidget(self.timeline_widget)
        bottom_row.addWidget(self.main_scroll, 1)

        self._grid_layout.addLayout(bottom_row, 1)

        content_layout.addWidget(self._grid_widget, 1)
        outer_layout.addLayout(content_layout)

        self.main_scroll.verticalScrollBar().valueChanged.connect(self._sync_v_scroll)
        self.main_scroll.horizontalScrollBar().valueChanged.connect(self._sync_h_scroll)
        self._v_scroll_timer = QTimer(self)
        self._v_scroll_timer.setSingleShot(True)
        self._v_scroll_timer.setInterval(16)
        self._v_scroll_timer.timeout.connect(self._apply_v_scroll)
        self._pending_v_value = 0
        self._h_scroll_timer = QTimer(self)
        self._h_scroll_timer.setSingleShot(True)
        self._h_scroll_timer.setInterval(16)
        self._h_scroll_timer.timeout.connect(self._apply_h_scroll)
        self._pending_h_value = 0

        self._now_timer = QTimer(self)
        self._now_timer.setInterval(60000)
        self._now_timer.timeout.connect(self._on_now_timer)
        self._now_timer.start()

    def _sync_v_scroll(self, value):
        self._pending_v_value = value
        if not self._v_scroll_timer.isActive():
            self._v_scroll_timer.start()

    def _apply_v_scroll(self):
        self.channel_scroll.verticalScrollBar().setValue(self._pending_v_value)

    def _sync_h_scroll(self, value):
        self._pending_h_value = value
        if not self._h_scroll_timer.isActive():
            self._h_scroll_timer.start()

    def _apply_h_scroll(self):
        self.time_header_scroll.horizontalScrollBar().setValue(self._pending_h_value)

    def _on_now_timer(self):
        now = datetime.now()
        if self._selected_date_ref and now.date() != self._selected_date_ref:
            self.timeline_widget._cache_valid = False
        self.timeline_widget.update()

    def _update_calendar_nav_icons(self):
        try:
            icon_color = AppStyles.get_color('window_text')
            prev_path = AppStyles.get_icon('chevron_left', icon_color, 12)
            next_path = AppStyles.get_icon('chevron_right', icon_color, 12)
            if prev_path and next_path:
                self._calendar.set_nav_icons(QIcon(prev_path), QIcon(next_path))
        except Exception as e:
            logger.debug(f"_update_calendar_nav_icons: {e}")

    def _on_date_changed(self, qdate):
        self._load_data()

    def _get_epg_dates(self):
        # 30 秒缓存：主题切换/重复打开时不必再次遍历全部 EPG 节目
        if self._epg_dates_cache_ts and (time.time() - self._epg_dates_cache_ts) < 30:
            return self._epg_dates_cache
        epg_parser = getattr(self.window, 'epg_parser', None)
        if not epg_parser:
            return self._epg_dates_cache
        dates = set()
        try:
            if hasattr(epg_parser, 'get_epg_data_copy'):
                epg_data = epg_parser.get_epg_data_copy()
            else:
                lock = getattr(epg_parser, '_epg_lock', None)
                if lock:
                    # 非阻塞尝试，避免 UI 线程最多卡 2 秒
                    if not lock.acquire(blocking=False):
                        return self._epg_dates_cache
                try:
                    epg_data = dict(getattr(epg_parser, '_epg_data', {}))
                finally:
                    if lock:
                        lock.release()
            for channel_id, programs in epg_data.items():
                for prog in programs:
                    try:
                        start_str = prog.get('start', '')
                        if start_str:
                            d = datetime.fromisoformat(start_str).date()
                            dates.add(d)
                    except Exception as e:
                        logger.debug(f"_get_epg_dates: {e}")
        except Exception as e:
            logger.debug(f"_get_epg_dates: {e}")
        self._epg_dates_cache = dates
        self._epg_dates_cache_ts = time.time()
        return dates

    def _retire_worker(self, worker):
        """不阻塞 UI 线程地停止 worker：断开信号后等线程自己结束后再销毁。"""
        if worker is None:
            return
        try:
            worker.data_ready.disconnect(self._on_data_loaded)
        except (RuntimeError, TypeError):
            pass
        worker.abort()
        if worker.isRunning():
            self._retired_workers.append(worker)
        else:
            worker.deleteLater()

    def _on_load_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._load_worker:
            self._load_worker = None
        try:
            self._retired_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def reload(self):
        """外部复用对话框时重新加载当前日期数据。"""
        self._load_data()

    def _load_data(self):
        w = self.window
        epg_parser = getattr(w, 'epg_parser', None)
        if not epg_parser:
            logger.debug("EPG时间轴: epg_parser不可用")
            tr = self.window.language_manager.tr
            self._status_label.setText(tr('epg_no_data', '无EPG数据'))
            return

        qd = self.date_edit.date()
        selected_date = date(qd.year(), qd.month(), qd.day())
        channels = list(getattr(w, '_sub_channels', [])) + list(getattr(w, '_local_channels', []))

        # 旧任务只做协作式中止，不在这里 wait()，否则恢复 UI 线程卡顿
        if self._load_worker is not None:
            self._retire_worker(self._load_worker)
            self._load_worker = None

        tr = self.window.language_manager.tr
        self._status_label.setText(tr('loading', '加载中...'))
        worker = _TimelineLoadWorker(epg_parser, channels, selected_date)
        worker.data_ready.connect(self._on_data_loaded)
        worker.finished.connect(self._on_load_worker_finished)
        self._load_worker = worker
        worker.start()

    def _on_data_loaded(self, channels_data, selected_date):
        self._channels_data = channels_data
        self._selected_date_ref = selected_date
        tr = self.window.language_manager.tr
        total_programs = sum(len(ch.get('programs', [])) for ch in channels_data)
        has_data = any(ch.get('programs') for ch in channels_data)
        if not has_data:
            self._status_label.setText(tr('epg_no_programs', '该日期无节目数据'))
        else:
            self._status_label.setText(tr('epg_channels_loaded', '{count}个频道 / {prog}个节目').format(count=len(channels_data), prog=total_programs))
        logger.debug(f"EPG时间轴: 加载{len(channels_data)}个频道数据")

        self.timeline_widget.set_data(channels_data, selected_date)
        self.channel_header.set_data(channels_data)
        self.channel_header.set_logo_service(getattr(self.window, '_logo_cache_service', None))
        self.time_header.set_start_hour(self.timeline_widget._start_hour)

        current_ch = getattr(self.window, 'current_channel', None)
        if current_ch:
            self.channel_header.set_current_channel(current_ch)

        self._update_corner_widget()

        self._mark_calendar_dates()
        safe_single_shot(DelayMs.STYLE_REAPPLY, self, self._update_calendar_nav_icons)

        safe_single_shot(DelayMs.LAYOUT_SETTLE, self, self._scroll_to_current_time)

    def _update_corner_widget(self):
        c = AppStyles._get_colors()
        from ui.styles import color_to_hex
        header_bg = c.get('alternate_base', c.get('window'))
        if isinstance(header_bg, str) and header_bg.startswith('rgba('):
            header_bg = color_to_hex(header_bg)
        self._corner_widget.setStyleSheet(f"background-color: {header_bg};")
        self._corner_widget.setAutoFillBackground(True)

    def _mark_calendar_dates(self):
        epg_dates = self._get_epg_dates()
        calendar = self.date_edit.calendarWidget()
        if not calendar:
            return
        try:
            calendar.setMinimumSize(320, 240)
            accent = AppStyles.get_color('accent')
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(accent))
            fmt.setFontWeight(QFont.Weight.Bold)
            for d in epg_dates:
                qd = QDate(d.year, d.month, d.day)
                calendar.setDateTextFormat(qd, fmt)
        except Exception as e:
            logger.debug(f"_mark_calendar_dates: {e}")

    def _scroll_to_current_time(self):
        try:
            selected = self._selected_date_ref
            # 仅“今天”才需要定位到当前时间；历史/未来日期从 00:00 开始，避免被钳到最右端
            if selected is not None and selected != date.today():
                self.main_scroll.horizontalScrollBar().setValue(0)
                return
            now_x = self.timeline_widget.get_current_time_x()
            viewport_width = self.main_scroll.viewport().width()
            target_x = int(now_x - viewport_width / 2)
            if target_x < 0:
                target_x = 0
            self.main_scroll.horizontalScrollBar().setValue(target_x)
        except Exception as e:
            logger.debug(f"_scroll_to_current_time: {e}")

    def _on_channel_double_clicked(self, channel):
        w = self.window
        if not isinstance(channel, dict):
            return
        # 正常情况下收到的是原始频道对象，可直接播放；否则退化为按名称查找
        target = channel if channel.get('url') else None
        if target is None:
            name = channel.get('name', '')
            channels = getattr(w, '_sub_channels', []) + getattr(w, '_local_channels', [])
            for ch in channels:
                if ch.get('name', '') == name:
                    target = ch
                    break
        if target is None:
            return
        self.channel_selected.emit(target)
        w.current_channel = target
        if hasattr(w, 'update_channel_info_on_selection'):
            w.update_channel_info_on_selection()
        if hasattr(w, 'play_channel'):
            w.play_channel(target)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_now_timer') and not self._now_timer.isActive():
            self._now_timer.start()
        if self._channels_data:
            # 复用时数据可能已加载，窗口可见后再定位一次（隐藏时 viewport 宽度为 0）
            safe_single_shot(DelayMs.LAYOUT_SETTLE, self, self._scroll_to_current_time)

    def closeEvent(self, event):
        if self._load_worker is not None:
            self._retire_worker(self._load_worker)
            self._load_worker = None
        if hasattr(self, '_now_timer'):
            self._now_timer.stop()
        # 对话框实例会被复用，保持注册在 ThemeManager 中（销毁时自动注销）
        super().closeEvent(event)
