"""
频道列表控制器 - 负责频道信息显示、分组切换等
从 pyqt_player.py 提取的独立模块
"""

from typing import Dict, Any
from datetime import datetime
from collections import deque
from time import perf_counter

from PySide6.QtWidgets import QListWidgetItem, QListWidget, QWidget
from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6 import QtWidgets

from core.application_state import app_state
from core.log_manager import global_logger as logger
from utils.general_utils import get_display_channel_name
from controllers.main_window_protocol import ChannelProtocol
from services.stream_quality_scorer import StreamQualityScorer
from ui.quality_bar import QualityBarWidget
from utils.thread_safety import safe_single_shot


class ChannelController:
    """频道列表控制器 - 管理频道信息显示和分组切换"""

    def __init__(self, main_window: ChannelProtocol):
        self.window: ChannelProtocol = main_window

    def on_group_changed(self, group_name: str):
        """处理分组切换事件"""
        self.window._populate_channel_list(source='auto')

    def _get_current_channels(self):
        """获取当前活跃的频道列表"""
        playlist_tab = getattr(self.window, 'playlist_tab', None)
        if playlist_tab:
            # Tab 1 = 本地频道，Tab 0 = 订阅频道
            if playlist_tab.currentIndex() == 1:
                channels = getattr(self.window, '_local_channels', None)
                if channels:
                    return channels
            else:
                channels = getattr(self.window, '_sub_channels', None)
                if channels:
                    return channels
        # fallback：任一列表有数据则返回
        sub = getattr(self.window, '_sub_channels', None)
        local = getattr(self.window, '_local_channels', None)
        if sub:
            return sub
        if local:
            return local
        return app_state.channels

    def _get_display_channel_name(self, channel: Dict[str, Any]) -> str:
        """获取频道的显示名称（委托给通用工具函数）"""
        language_manager = getattr(self.window, 'language_manager', None)
        return get_display_channel_name(channel, language_manager)

    @staticmethod
    def _resolution_label(resolution: str) -> str:
        """分辨率标签：1920x1080 → 1080P，3840x2160 → 4K，720x576 → 576P"""
        r = (resolution or '').strip().lower()
        if not r:
            return ''
        height = 0
        if 'x' in r:
            digits = ''.join(c for c in r.rsplit('x', 1)[-1] if c.isdigit())
            if digits:
                height = int(digits)
        if height >= 2160:
            return '4K'
        if height >= 1080:
            return '1080P'
        if height >= 720:
            return '720P'
        if height >= 576:
            return '576P'
        if height >= 480:
            return '480P'
        return f'{height}P' if height else r.upper()

    @classmethod
    def _channel_list_display_name(cls, channel: Dict[str, Any], name: str,
                                   name_counts: Dict[str, int]) -> str:
        """列表显示名：同名多路流（同一频道的不同码流）追加分辨率后缀以区分。

        只影响列表显示文本，不修改频道数据本身（名称/频道号/URL 保持原样）。
        """
        if name_counts.get((name or '').strip(), 0) <= 1:
            return name
        suffix = cls._resolution_label(channel.get('resolution', ''))
        if not suffix:
            chno = str(channel.get('tvg_chno', '') or '').strip()
            suffix = f'CH{chno}' if chno else ''
        return f'{name} · {suffix}' if suffix else name

    def _update_channel_info(self, channel: Dict[str, Any]):
        """更新频道信息显示区域"""
        if not self.window.channel_name:
            return

        display_name = self._get_display_channel_name(channel)
        self.window.channel_name.setText(display_name)

        if self.window.channel_logo:
            logo_url = channel.get('logo') or channel.get('logo_url')
            if not logo_url:
                self.window.channel_logo.setText("")
                self.window.channel_logo.setPixmap(None)

    @staticmethod
    def _set_list_bulk_mode(list_widget, enabled):
        try:
            list_widget.setUpdatesEnabled(enabled)
            if enabled:
                # QAbstractItemView 在 PySide6 中存在 update(QModelIndex) 重载，
                # 会遮蔽 QWidget.update() 的零参形式，直接调用会抛 TypeError。
                QWidget.update(list_widget)
        except RuntimeError:
            pass

    # 行内控件（台标 + 名称 + 评分条）按视口按需创建。
    # 逐项 addItem 与 setItemWidget 交错执行会让 QListWidget 反复重排已有的
    # item widget，耗时随条数平方增长（5000 条约 127 秒）；先建轻量条目，
    # 再只为视口附近的行装饰控件、回收远处的行，耗时与内存都只和视口相关。
    ROW_DECORATE_MARGIN = 40
    ROW_WIDGET_CACHE = 400
    # 条目自身文本在装饰行控件时必须清空，否则会从透明的行控件底下透出来
    ROW_DISPLAY_ROLE = Qt.ItemDataRole.UserRole + 1

    def populate_channel_list_for(self, list_widget, channels, selected_group=''):
        w = self.window
        tr = w.language_manager.tr

        list_widget.clear()
        list_widget._channel_render = None

        # 批量重建期间关闭刷新，避免每 addItem 都触发一次重绘；分片完成时恢复
        self._set_list_bulk_mode(list_widget, False)

        if hasattr(w, '_icon_load_timer') and w._icon_load_timer:
            w._icon_load_timer.stop()
        if w._icon_load_set:
            w._icon_load_set.clear()
        if w._icon_load_queue:
            w._icon_load_queue.clear()

        all_channels_text = tr("all_channels", "All Channels")
        is_all_channels = (
            not selected_group or
            selected_group.lower() == all_channels_text.lower()
        )

        from utils.platform_utils import get_effective_ui_scale
        from ui.typography import text_factor
        ui_scale = get_effective_ui_scale()
        # 行高必须跟文字一起放大：只按界面缩放放大时「特大」字号会挤爆两行内容
        row_h = int(round(46 * ui_scale * max(1.0, text_factor())))

        # 同名多路流（同一频道的不同分辨率/码流）在列表名称后追加分辨率后缀，
        # 让用户能区分两条同名频道；不影响频道数据本身
        name_counts = {}
        for ch in channels:
            key = (ch.get('name') or '').strip()
            name_counts[key] = name_counts.get(key, 0) + 1

        visible_indices = []
        for idx, channel in enumerate(channels):
            if is_all_channels:
                visible_indices.append(idx)
                continue
            channel_groups = channel.get('_groups', [channel.get('group', '')])
            if selected_group in channel_groups:
                visible_indices.append(idx)

        added_count = 0
        error_count = 0
        skipped_count = len(channels) - len(visible_indices)
        is_grid = list_widget.viewMode() == QListWidget.ViewMode.IconMode

        if len(visible_indices) >= 500 and hasattr(w, 'status_bar_show_message'):
            w.status_bar_show_message(tr('loading_channels', '正在加载频道...'))

        # 大列表分片填充：先同步建首批保证立即可用，其余按 8ms/帧预算追加。
        # token 用于取消上一轮未完成的分片，避免快速切分组时重复添加。
        state = {'pos': 0, 'token': object()}
        list_widget._channel_populate_token = state['token']
        # 首批别太大：600 条轻量 item 的构建通常在 10ms 量级
        initial_limit = 600 if len(visible_indices) > 600 else len(visible_indices)

        def _add_range(limit):
            nonlocal added_count, error_count
            start_ts = perf_counter()
            while state['pos'] < limit:
                idx = visible_indices[state['pos']]
                state['pos'] += 1
                try:
                    channel = channels[idx]
                    channel_name = channel.get("name", tr("unnamed", "Unnamed"))
                    display_name = self._channel_list_display_name(channel, channel_name, name_counts)
                    item = QListWidgetItem()
                    item.setText(display_name)
                    item.setData(self.ROW_DISPLAY_ROLE, display_name)
                    item.setToolTip(display_name)
                    item.setData(Qt.ItemDataRole.UserRole, idx)
                    if is_grid:
                        item.setSizeHint(QSize(int(round(220 * ui_scale)), int(round(150 * ui_scale))))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    else:
                        # 轻量条目：行内控件由 decorate_visible_rows 按视口补上
                        item.setSizeHint(QSize(0, row_h))
                    list_widget.addItem(item)
                    added_count += 1
                except Exception as e:
                    error_count += 1
                    if error_count <= 3:
                        logger.error(f"populate_channel_list: 添加第{idx}个频道失败: {e}")
                if (perf_counter() - start_ts) * 1000 >= 8:
                    break

        def _finalize():
            if getattr(list_widget, '_channel_populate_token', None) is not state['token']:
                return
            if not is_grid:
                list_widget._channel_render = {
                    'channels': channels,
                    'name_counts': name_counts,
                    'row_h': row_h,
                    'ui_scale': ui_scale,
                }
                self.decorate_visible_rows(list_widget)

            empty_label = None
            if list_widget is getattr(w, 'sub_channel_list', None):
                empty_label = getattr(w, 'sub_empty_label', None)
            elif list_widget is getattr(w, 'local_channel_list', None):
                empty_label = getattr(w, 'local_empty_label', None)

            if empty_label:
                if added_count == 0:
                    empty_label.show()
                else:
                    empty_label.hide()

            if error_count > 0:
                logger.warning(f"populate_channel_list: 共 {error_count} 个频道添加失败")
            if skipped_count > 0:
                logger.warning(f"populate_channel_list: 共 {skipped_count} 个频道被分组过滤跳过")

            logger.info(f"populate_channel_list: 填充完成，共 {list_widget.count()} 个频道项（实际添加: {added_count}, 跳过: {skipped_count}, 总数据: {len(channels)}）")
            self._set_list_bulk_mode(list_widget, True)
            if len(visible_indices) >= 500 and hasattr(w, 'status_bar_show_message'):
                w.status_bar_show_message(
                    tr('channel_list_loaded', '频道列表已加载（{count} 个频道）').format(count=added_count), 3000)
            try:
                list_widget.verticalScrollBar().valueChanged.connect(w._on_channel_list_scrolled, Qt.ConnectionType.UniqueConnection)
            except TypeError:
                pass
            self._connect_render_refresh(list_widget)
            safe_single_shot(50, self.window, lambda: self.load_visible_icons(list_widget, channels))

        try:
            _add_range(initial_limit)
            if state['pos'] < len(visible_indices):
                def _next_chunk():
                    if getattr(list_widget, '_channel_populate_token', None) is not state['token']:
                        return
                    _add_range(len(visible_indices))
                    if state['pos'] < len(visible_indices):
                        QTimer.singleShot(0, list_widget, _next_chunk)
                    else:
                        _finalize()

                QTimer.singleShot(0, list_widget, _next_chunk)
            else:
                _finalize()
        except Exception as e:
            logger.error(f"populate_channel_list: 分片填充异常，恢复列表刷新: {e}")
            self._set_list_bulk_mode(list_widget, True)

    def _connect_render_refresh(self, list_widget):
        """面板拉伸/字号变化导致可见行数变化时，补装饰新出现的可见行。"""
        sb = list_widget.verticalScrollBar()
        old = getattr(list_widget, '_channel_range_handler', None)
        if old is not None:
            try:
                sb.rangeChanged.disconnect(old)
            except (RuntimeError, TypeError):
                pass
        handler = lambda *_: self._refresh_visible_rows(list_widget)
        list_widget._channel_range_handler = handler
        try:
            sb.rangeChanged.connect(handler)
        except (RuntimeError, TypeError):
            pass

    def _refresh_visible_rows(self, list_widget):
        """视口范围变化后补装饰新出现的行，并补加载这些行的台标。"""
        self.decorate_visible_rows(list_widget)
        state = getattr(list_widget, '_channel_render', None) or {}
        channels = state.get('channels')
        if channels:
            self.load_visible_icons(list_widget, channels)

    @staticmethod
    def _visible_row_bounds(list_widget, row_h):
        """返回视口内首末行号。

        indexAt 取 (0,0)/(0,height-1) 时，x=0 与 y=0 落在列表边框、行间距之外，
        Qt 一直返回无效索引，导致"顶部永远是第 0 行"，只装饰前几十行。
        这里从视口内部取点探测，探测失败再按滚动条/行高兜底。
        """
        vp = list_widget.viewport().rect()
        width = max(1, vp.width())
        height = max(1, vp.height())

        def _row_at(y):
            idx = list_widget.indexAt(QPoint(width // 2, max(0, min(height - 1, y))))
            return idx.row() if idx.isValid() else -1

        first = -1
        for y in (3, 6, 12, 24):
            if y >= height:
                break
            first = _row_at(y)
            if first >= 0:
                break
        if first < 0:
            # 默认按行滚动时，滚动条数值即顶部行号
            first = max(0, list_widget.verticalScrollBar().value())

        last = -1
        for y in (height - 3, height - 12, height - 24):
            if y < 0:
                continue
            last = _row_at(y)
            if last >= 0:
                break
        if last < 0:
            last = first + height // max(1, int(row_h or 46)) + 1
        last = min(list_widget.count() - 1, max(first, last))
        return first, last

    def decorate_visible_rows(self, list_widget):
        """只装饰视口附近的行，并回收远离视口的行内控件。"""
        state = getattr(list_widget, '_channel_render', None)
        if not state:
            return
        try:
            if list_widget.viewMode() == QListWidget.ViewMode.IconMode:
                return
            count = list_widget.count()
            if count <= 0:
                return
            row_h = max(1, int(state.get('row_h') or 46))
            first, last = self._visible_row_bounds(list_widget, row_h)
            lo = max(0, first - self.ROW_DECORATE_MARGIN)
            hi = min(count - 1, last + self.ROW_DECORATE_MARGIN)
            if hi < lo:
                return

            channels = state['channels']
            for row in range(lo, hi + 1):
                item = list_widget.item(row)
                if item is None or list_widget.itemWidget(item) is not None:
                    continue
                idx = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(idx, int) or idx >= len(channels):
                    continue
                try:
                    widget = self._build_channel_row_widget(item, channels[idx])
                    list_widget.setItemWidget(item, widget)
                    # 行控件是透明的，条目文本必须清空，避免与控件内文字重叠
                    item.setText('')
                except Exception as e:
                    logger.debug(f"装饰频道行失败 row={row}: {e}")

            keep_lo = max(0, lo - self.ROW_WIDGET_CACHE)
            keep_hi = min(count - 1, hi + self.ROW_WIDGET_CACHE)
            # 回收要扫描全表（5000 条约 10ms），滚动过程中每 8 次做一次即可
            tick = (getattr(list_widget, '_channel_trim_tick', 0) + 1) % 8
            list_widget._channel_trim_tick = tick
            if tick == 0:
                self._trim_row_widgets(list_widget, keep_lo, keep_hi)
        except RuntimeError:
            pass

    @staticmethod
    def _trim_row_widgets(list_widget, keep_lo, keep_hi):
        """回收超出缓存窗口的行内控件，避免大列表把内存全占住。"""
        for row in range(list_widget.count()):
            if keep_lo <= row <= keep_hi:
                continue
            item = list_widget.item(row)
            if item is None or list_widget.itemWidget(item) is None:
                continue
            list_widget.removeItemWidget(item)
            # 恢复条目文本，回收后的行仍能正常显示名称
            display_name = item.data(ChannelController.ROW_DISPLAY_ROLE)
            if display_name:
                item.setText(display_name)

    def _build_channel_row_widget(self, item, channel):
        """构建单行频道控件：台标 + 名称 + 评分条。"""
        from ui.styles import AppStyles
        from ui.elided_label import ElidedLabel
        from ui.quality_bar import QUALITY_SCORE_ROLE, QUALITY_GRADE_ROLE
        state = getattr(item.listWidget(), '_channel_render', None) or {}
        ui_scale = state.get('ui_scale', 1.0)

        item_widget = QtWidgets.QWidget()
        item_widget.style_type = 'channel_item'
        item_widget.setStyleSheet(AppStyles.transparent_style())
        outer_layout = QtWidgets.QVBoxLayout(item_widget)
        outer_layout.setContentsMargins(5, 2, 5, 2)
        outer_layout.setSpacing(0)

        row_layout = QtWidgets.QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        logo_label = QtWidgets.QLabel()
        logo_label.setFixedSize(int(round(44 * ui_scale)), int(round(32 * ui_scale)))
        logo_label.setStyleSheet(AppStyles.transparent_style())
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setObjectName("channel_logo_label")
        # 台标兜底文字只允许单行：字号档位放大后 44×32 放不下两行中文
        logo_label.setWordWrap(False)
        _logo_font = logo_label.font()
        _logo_font.setPointSizeF(max(6.0, min(_logo_font.pointSizeF(), 8.0 * ui_scale)))
        logo_label.setFont(_logo_font)

        name_label = ElidedLabel(item.text())
        name_label.setStyleSheet(AppStyles.player_channel_list_name_style())
        name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        row_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(name_label, 1, Qt.AlignmentFlag.AlignVCenter)

        # 三档有效性徽章：确证有效不额外标注，疑似/不可用给出可见提示
        from services.validity_tiers import INVALID, SUSPECTED, channel_tier
        tier = channel_tier(channel)
        if tier in (SUSPECTED, INVALID):
            from ui.palette import get_token
            mode = AppStyles._get_effective_color_mode()
            if tier == SUSPECTED:
                badge_text = '疑似'
                badge_color = (get_token('state.warning_text', mode)
                               or AppStyles._get_colors().get('warning', '#FF9800'))
                badge_tip = '疑似：能连上但未解析出媒体流，建议在扫描整理里检测有效性'
            else:
                badge_text = '不可用'
                badge_color = (get_token('state.danger_text', mode)
                               or AppStyles._get_colors().get('error', '#ff6666'))
                badge_tip = '不可用：服务器拒绝、404 或无法拉流'
            badge = QtWidgets.QLabel(badge_text)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setToolTip(badge_tip)
            badge.setStyleSheet(
                f"QLabel {{ color: {badge_color}; background: transparent; "
                f"border: 1px solid {badge_color}; border-radius: 7px; "
                f"padding: 0px 6px; font-size: {max(10, int(round(11 * ui_scale)))}px; }}"
            )
            row_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        outer_layout.addLayout(row_layout, 1)

        # 评分条：名称下方红→黄→绿渐变指示
        # 优先读持久化 quality_score 字段（订阅源/本地 M3U 自带评分的场景）
        # 否才按 valid 判断（未检测 valid is None 不显示）
        quality_bar = QualityBarWidget(item_widget)
        persisted_score = channel.get('quality_score')
        persisted_grade = channel.get('quality_grade') or ''
        if persisted_score is not None and persisted_score != '':
            try:
                quality_bar.set_score(float(persisted_score), persisted_grade)
            except (TypeError, ValueError):
                quality_bar.set_score(None)
        else:
            score_info = StreamQualityScorer.score_from_channel_safe(channel)
            if score_info is not None:
                quality_bar.set_score(score_info.get('total'), score_info.get('grade', ''))
            else:
                quality_bar.set_score(None)
        # 播放中实时评分优先于持久化值（行控件被回收后重建也能恢复最新评分）
        live_score = item.data(QUALITY_SCORE_ROLE)
        if live_score is not None:
            quality_bar.set_score(float(live_score), item.data(QUALITY_GRADE_ROLE) or '')
        outer_layout.addWidget(quality_bar, 0)
        return item_widget

    def refresh_item_metrics(self, list_widget):
        """字号/缩放变更后更新已建频道项的行高与 logo 尺寸。

        频道项是创建时写死 sizeHint 的，QSS 缩放管不到行高；这里按当前
        单一真源重算，避免大字号下名称被裁或行间留白过大。
        """
        if list_widget is None:
            return
        from utils.platform_utils import get_effective_ui_scale
        from ui.typography import text_factor
        scale = get_effective_ui_scale()
        is_grid = list_widget.viewMode() == QListWidget.ViewMode.IconMode
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item is None:
                continue
            if is_grid:
                item.setSizeHint(QSize(int(round(220 * scale)), int(round(150 * scale))))
                continue
            item.setSizeHint(QSize(0, int(round(46 * scale * max(1.0, text_factor())))))
            item_widget = list_widget.itemWidget(item)
            if item_widget is None:
                continue
            for logo in item_widget.findChildren(QtWidgets.QLabel, "channel_logo_label"):
                logo.setFixedSize(int(round(44 * scale)), int(round(32 * scale)))
        # 之后按视口新建的行控件要用新尺寸
        state = getattr(list_widget, '_channel_render', None)
        if state and not is_grid:
            state['ui_scale'] = scale
            state['row_h'] = int(round(46 * scale * max(1.0, text_factor())))

    def load_visible_icons(self, list_widget, channels):
        w = self.window

        if not w._icon_load_queue:
            w._icon_load_queue = deque()
            w._icon_load_set = set()
            w._icon_load_timer = QTimer(w)
            w._icon_load_timer.setInterval(16)
            w._icon_load_timer.timeout.connect(w._process_icon_load_batch)

        icon_load_set = w._icon_load_set
        icon_load_queue = w._icon_load_queue
        icon_load_timer = w._icon_load_timer
        assert icon_load_set is not None and icon_load_queue is not None

        if not hasattr(w, '_logo_cache_service') or not w._logo_cache_service:
            logger.warning("_load_visible_icons: _logo_cache_service未初始化，跳过台标加载")
            return

        row_h = int((getattr(list_widget, '_channel_render', None) or {}).get('row_h') or 46)
        first_visible, last_visible = self._visible_row_bounds(list_widget, row_h)
        first_visible = max(0, first_visible - 3)
        last_visible = min(list_widget.count() - 1, last_visible + 3)

        is_grid = list_widget.viewMode() == QListWidget.ViewMode.IconMode

        logger.debug(f"_load_visible_icons: 项数={list_widget.count()}, channels={len(channels)}")
        need_capture = []
        queue_items = []

        for i in range(first_visible, last_visible + 1):
            item = list_widget.item(i)
            if not item:
                continue
            channel_idx = item.data(Qt.ItemDataRole.UserRole)
            if channel_idx is None or channel_idx >= len(channels):
                continue
            channel = channels[channel_idx]
            logo_url = channel.get('logo', '').strip('`' + '"' + '\'')

            if is_grid:
                if not item.icon().isNull():
                    continue
                ch_url = channel.get('url', '')
                if w.player_controller and ch_url:
                    thumb_path = w.player_controller.get_thumbnail_path(ch_url)
                    if thumb_path:
                        dedupe_key = ('grid_thumb', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('grid_thumb', item, thumb_path, None))
                            icon_load_set.add(dedupe_key)
                        continue
                if logo_url:
                    cached = w._logo_cache_service.get_scaled(logo_url, 160, 90)
                    if cached:
                        dedupe_key = ('grid_logo', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('grid_logo', item, None, cached))
                            icon_load_set.add(dedupe_key)
                    else:
                        w._logo_cache_service.fetch_async(logo_url)
                if ch_url:
                    need_capture.append(channel)
            else:
                item_widget = list_widget.itemWidget(item)
                if not item_widget:
                    continue
                logo_label = item_widget.findChild(QtWidgets.QLabel, "channel_logo_label")
                if not logo_label:
                    continue
                if logo_label.pixmap() and not logo_label.pixmap().isNull():
                    continue
                if logo_url:
                    cached = w._logo_cache_service.get_scaled(
                        logo_url,
                        logo_label.width() if logo_label.width() > 0 else 48,
                        logo_label.height() if logo_label.height() > 0 else 34)
                    if cached:
                        dedupe_key = ('list_logo', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('list_logo', item, logo_label, cached))
                            icon_load_set.add(dedupe_key)
                    else:
                        w._logo_cache_service.fetch_async(logo_url)
                else:
                    ch_url = channel.get('url', '')
                    if ch_url:
                        from services.audio_visual_service import AUDIO_EXTENSIONS, extract_cover_art
                        if ch_url.lower().endswith(AUDIO_EXTENSIONS):
                            cover = extract_cover_art(ch_url)
                            if cover and not cover.isNull():
                                dedupe_key = ('list_logo', i)
                                if dedupe_key not in icon_load_set:
                                    queue_items.append(('list_logo', item, logo_label, cover))
                                    icon_load_set.add(dedupe_key)

        icon_load_queue.extend(queue_items)
        if icon_load_queue and icon_load_timer and not icon_load_timer.isActive():
            icon_load_timer.start()

        if need_capture and hasattr(w, '_thumbnail_service'):
            w._thumbnail_service.capture_channels(need_capture, force=True)

    def update_channel_info_on_selection(self):
        w = self.window
        if not w.current_channel:
            return

        w.media_ctrl.update_catchup_indicator()

        display_name = self._get_display_channel_name(w.current_channel)
        w.channel_name.setText(display_name)
        w.current_program.setText("")
        logo = w.current_channel.get("logo", "")

        if logo:
            logo = logo.strip('`"\'')

            svc = w._logo_cache_service
            target_w = max(48, w.channel_logo.width())
            target_h = max(34, w.channel_logo.height())
            # 先用列表尺寸的低清图立刻出画，再在事件循环空闲时换成高清
            small = svc.get_scaled(logo, 48, 34)
            if small and not small.isNull():
                w.channel_logo.setPixmap(small)
                w.channel_logo.setText("")
                if (target_w, target_h) != (48, 34):
                    def _upgrade_logo(_logo=logo, _w=target_w, _h=target_h):
                        high = svc.get_scaled(_logo, _w, _h)
                        if high and not high.isNull():
                            w.channel_logo.setPixmap(high)
                    safe_single_shot(0, w, _upgrade_logo)
            else:
                cached = svc.get(logo)
                if cached:
                    scaled_pixmap = svc.scale_logo_pixmap_to_fit(cached, target_w, target_h)
                    w.channel_logo.setPixmap(scaled_pixmap)
                    w.channel_logo.setText("")
                else:
                    svc.fetch_async(logo)
                    from utils.general_utils import set_default_channel_logo
                    set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())
        else:
            ch_url = w.current_channel.get('url', '') if w.current_channel else ''
            from services.audio_visual_service import AUDIO_EXTENSIONS
            if ch_url and ch_url.lower().endswith(AUDIO_EXTENSIONS):
                from services.audio_visual_service import extract_cover_art
                cover = extract_cover_art(ch_url)
                if cover and not cover.isNull():
                    from utils.general_utils import set_default_channel_logo
                    scaled = cover.scaled(w.channel_logo.width(), w.channel_logo.height(),
                                          Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
                    w.channel_logo.setPixmap(scaled)
                    w.channel_logo.setText("")
                    if hasattr(w, 'player_controller') and w.player_controller:
                        if hasattr(w.player_controller, 'audio_visual') and w.player_controller.audio_visual:
                            if w.player_controller.audio_visual._widget:
                                w.player_controller.audio_visual._widget.set_cover(cover)
                else:
                    from utils.general_utils import set_default_channel_logo
                    set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())
            else:
                from utils.general_utils import set_default_channel_logo
                set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())

        try:
            if w._is_local_file():
                w.current_program.setText("")
                ch_url = w.current_channel.get('url', '') if w.current_channel else ''
                from services.audio_visual_service import AUDIO_EXTENSIONS
                if ch_url and ch_url.lower().endswith(AUDIO_EXTENSIONS):
                    w.program_desc.setText(w.language_manager.tr("local_audio_file", "本地音频文件"))
                else:
                    w.program_desc.setText(w.language_manager.tr("local_video_file", "本地视频文件"))
                w.time_label.setText("--:-- / --:--")
                w.remain_label.setText(w.language_manager.tr("loading", "加载中..."))
            else:
                channel_name = w.current_channel.get("name", "")
                current_program_data = None
                if channel_name and hasattr(w, 'epg_parser') and w.epg_parser:
                    ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
                    current_program_data = w.epg_parser.get_current_program(
                        ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name
                    )
                if current_program_data:
                    program_name = current_program_data.get("title", "")
                    w.current_program.setText(f"· {program_name}" if program_name else "")
                    w.program_desc.setText(current_program_data.get("desc", w.language_manager.tr("no_program_desc", "No program description")))
                    start_str = current_program_data.get("start", "")
                    start_display = datetime.fromisoformat(start_str).strftime("%H:%M") if start_str else "--:--"
                    w.progress_start.setText(start_display)
                    w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
                    w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))
                else:
                    w.current_program.setText("")
                    w.program_desc.setText(w.language_manager.tr("open_playlist_success", "Channel list opened, click a channel to play"))
                    w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
                    w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))
        except Exception:
            w.current_program.setText("")
            w.program_desc.setText(w.language_manager.tr("open_playlist_success", "Channel list opened, click a channel to play"))
            current_time = datetime.now().strftime("%H:%M")
            w.time_label.setText(f"{current_time}")
            w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))

        w._set_progress_value(0)
        w.progress_end.setText("--:--")

        w.video_info.setText(f'{w.language_manager.tr("waiting_to_play", "Waiting to play...")}')
        w.audio_info.setText("--")
        w.network_info.setText(f'{w.language_manager.tr("waiting_connect", "Waiting to connect...")}')
        if hasattr(w, 'buffer_info'):
            w.buffer_info.hide()
        if hasattr(w, 'hdr_badge'):
            w.hdr_badge.hide()

    @property
    def channel_count(self) -> int:
        """当前频道数量"""
        return len(app_state.channels)

    @property
    def current_group(self) -> str:
        """当前选中的分组名称"""
        if self.window.group_combo:
            return self.window.group_combo.currentText()
        return ""

    def update_quality_bar_for_url(self, url: str, score: float, grade: str = ''):
        """播放过程中获取到媒体信息后，更新播放列表中对应频道的评分条。

        遍历 sub_channel_list 和 local_channel_list，找到 URL 匹配的条目，
        通过 findChild 找到 QualityBarWidget 并调用 set_score。

        Args:
            url: 频道 URL
            score: 质量评分 (0~100)
            grade: 质量等级 (A/B/C/D/F)
        """
        if not url:
            return
        from ui.quality_bar import QUALITY_SCORE_ROLE, QUALITY_GRADE_ROLE
        for list_attr in ('sub_channel_list', 'local_channel_list'):
            cl = getattr(self.window, list_attr, None)
            if not cl:
                continue
            state = getattr(cl, '_channel_render', None) or {}
            channels = state.get('channels')
            if not channels:
                channels = getattr(self.window, '_sub_channels', None) if list_attr == 'sub_channel_list' \
                    else getattr(self.window, '_local_channels', None)
            for i in range(cl.count()):
                item = cl.item(i)
                if not item:
                    continue
                idx = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(idx, int) or not channels or idx >= len(channels):
                    continue
                if channels[idx].get('url', '') != url:
                    continue
                # 评分写回条目数据：行控件可能因滚动被回收，重建时据此恢复最新评分
                item.setData(QUALITY_SCORE_ROLE, float(score))
                item.setData(QUALITY_GRADE_ROLE, grade or '')
                item_widget = cl.itemWidget(item)
                if item_widget:
                    bar = item_widget.findChild(QualityBarWidget, "quality_bar")
                    if bar:
                        bar.set_score(score, grade)
                break
