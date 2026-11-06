import time

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QListWidget

from core.log_manager import global_logger as logger
from core.application_state import app_state
from utils.thread_safety import safe_single_shot


class ChannelMixin:
    """从 IPTVPlayer 提取的频道列表/选择/搜索/分组职责"""

    def update_channel_groups(self):
        self.subscription_ctrl.update_channel_groups()

    def populate_channel_list(self, source='subscription'):
        if source == 'auto':
            if not hasattr(self, 'playlist_tab'):
                source = 'subscription'
            else:
                source = 'subscription' if self.playlist_tab.currentIndex() == 0 else 'local'

        current_time = time.time()
        if not hasattr(self, '_last_populate_times'):
            self._last_populate_times = {}
        last_time = self._last_populate_times.get(source, 0)

        if source == 'subscription':
            new_channels = app_state.channels
            skip_debounce = len(new_channels) != len(getattr(self, '_sub_channels', []))
        else:
            new_channels = None
            skip_debounce = False

        if not skip_debounce and current_time - last_time < 0.5:
            logger.debug(f"populate_channel_list: 跳过重复调用（source={source}，距上次{current_time - last_time:.2f}秒）")
            return
        self._last_populate_times[source] = current_time

        if source == 'subscription':
            self._sub_channels = new_channels
            self._update_groups_for('subscription')
            self._populate_channel_list_for(self.sub_channel_list, self._sub_channels,
                                            self.sub_group_combo.currentText())
        else:
            self._update_groups_for('local')
            self._populate_channel_list_for(self.local_channel_list, self._local_channels,
                                            self.local_group_combo.currentText())

        pending = getattr(self, '_pending_last_channel', None)
        if pending:
            channels_to_search = self._sub_channels if source == 'subscription' else self._local_channels
            target_list = self.sub_channel_list if source == 'subscription' else self.local_channel_list
            if len(channels_to_search or []) > 0:
                self._pending_last_channel = None
                last_url = pending.get('url', '')
                last_name = pending.get('name', '')
                last_idx = pending.get('index', -1)
                target_idx = -1
                # 同名多源时频道名无法唯一确定频道，优先按 URL 定位
                if last_url:
                    for i, ch in enumerate(channels_to_search or []):
                        if ch.get('url', '') == last_url:
                            target_idx = i
                            break
                # URL 命中不了（旧配置或列表已变动）退回下标
                if target_idx < 0 and last_idx >= 0 and last_idx < len(channels_to_search or []):
                    target_idx = last_idx
                # 最后才用名字兜底
                if target_idx < 0 and last_name:
                    for i, ch in enumerate(channels_to_search or []):
                        if ch.get('name', '') == last_name:
                            target_idx = i
                            break
                if target_idx >= 0:
                    safe_single_shot(100, self, lambda idx=target_idx, sl=target_list: self.select_channel_by_index(idx, source_list=sl))

    def _update_groups_for(self, source):
        channels = self._sub_channels if source == 'subscription' else self._local_channels
        combo = self.sub_group_combo if source == 'subscription' else self.local_group_combo
        groups_attr = '_sub_groups' if source == 'subscription' else '_local_groups'

        tr = self.language_manager.tr
        all_channels_text = tr("all_channels", "All Channels")

        groups = []
        seen = set()
        for channel in channels or []:
            for g in channel.get('_groups', [channel.get('group', '') or tr('uncategorized', '未分类')]):
                if g and g not in seen:
                    groups.append(g)
                    seen.add(g)

        new_groups = [all_channels_text] + groups
        old_groups = getattr(self, groups_attr, [])

        if new_groups == old_groups:
            return

        setattr(self, groups_attr, new_groups)

        current_text = combo.currentText() if combo.currentText() else all_channels_text
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(new_groups)
        if current_text in new_groups:
            combo.setCurrentText(current_text)
        elif new_groups:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _on_sub_search_changed(self, text):
        self._apply_channel_search(self.sub_channel_list, self._sub_channels, text)

    def _on_local_search_changed(self, text):
        self._apply_channel_search(self.local_channel_list, self._local_channels, text)

    def _apply_channel_search(self, list_widget, channels, search_text):
        search_text = search_text.strip().lower()
        if not search_text:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item:
                    item.setHidden(False)
            return
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not item:
                continue
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx is None or idx >= len(channels):
                item.setHidden(True)
                continue
            channel = channels[idx]
            name = channel.get('name', '').lower()
            url = channel.get('url', '').lower()
            group = channel.get('group', '').lower()
            match = search_text in name or search_text in url or search_text in group
            item.setHidden(not match)

    def _populate_channel_list_for(self, list_widget, channels, selected_group=''):
        self.channel_ctrl.populate_channel_list_for(list_widget, channels, selected_group)

    def _load_visible_icons(self, list_widget, channels):
        self.channel_ctrl.load_visible_icons(list_widget, channels)

    def _process_icon_load_batch(self):
        if not hasattr(self, '_icon_load_queue') or not self._icon_load_queue:
            if hasattr(self, '_icon_load_timer'):
                self._icon_load_timer.stop()
            return

        batch_size = 3
        for _ in range(batch_size):
            if not self._icon_load_queue:
                if hasattr(self, '_icon_load_set'):
                    self._icon_load_set.clear()
                break
            task = self._icon_load_queue.popleft()
            try:
                kind = task[0]
                if kind == 'grid_thumb':
                    _, item, thumb_path, _ = task
                    px = QPixmap(thumb_path)
                    if not px.isNull():
                        scaled = px.scaled(210, 118, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        item.setIcon(QIcon(scaled))
                elif kind == 'grid_logo':
                    _, item, _, cached = task
                    if cached and not cached.isNull():
                        scaled = cached.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        item.setIcon(QIcon(scaled))
                elif kind == 'list_logo':
                    _, item, logo_label, cached = task
                    if cached and not cached.isNull() and logo_label:
                        scaled = self._logo_cache_service.scale_logo_pixmap_to_fit(
                            cached,
                            logo_label.width() if logo_label.width() > 0 else 48,
                            logo_label.height() if logo_label.height() > 0 else 34
                        )
                        logo_label.setPixmap(scaled)
            except RuntimeError:
                pass

        if not self._icon_load_queue:
            self._icon_load_timer.stop()

    def _on_channel_list_scrolled(self, value):
        sender = self.sender()
        if sender is self.local_channel_list:
            list_widget = self.local_channel_list
            channels = self._local_channels
        else:
            list_widget = self.sub_channel_list
            channels = self._sub_channels
        self._load_visible_icons(list_widget, channels)

    def _capture_visible_thumbnails(self, tab='sub'):
        list_widget = self.sub_channel_list if tab == 'sub' else self.local_channel_list
        channels = self._sub_channels if tab == 'sub' else self._local_channels
        if list_widget.viewMode() != QListWidget.ViewMode.IconMode:
            return
        if not hasattr(self, '_thumbnail_service'):
            return

        viewport_rect = list_widget.viewport().rect()
        top_index = list_widget.indexAt(viewport_rect.topLeft())
        bottom_index = list_widget.indexAt(viewport_rect.bottomLeft())

        first_visible = top_index.row() if top_index.isValid() else 0
        last_visible = bottom_index.row() if bottom_index.isValid() else list_widget.count() - 1

        need_capture = []
        for i in range(first_visible, last_visible + 1):
            item = list_widget.item(i)
            if not item:
                continue
            channel_idx = item.data(Qt.ItemDataRole.UserRole)
            if channel_idx is None or channel_idx >= len(channels or []):
                continue
            channel = channels[channel_idx]
            ch_url = channel.get('url', '')
            if ch_url:
                need_capture.append(channel)

        if need_capture:
            self._thumbnail_service.capture_channels(need_capture, force=True)

    def on_group_changed(self, group_name):
        self.channel_ctrl.on_group_changed(group_name)

    def select_channel(self, item, source_list=None):
        try:
            idx = item.data(Qt.ItemDataRole.UserRole)

            if source_list is not None:
                channel_list = source_list
            else:
                sender = self.sender()
                channel_list = sender if sender else self.sub_channel_list

            if channel_list is self.local_channel_list:
                channels = self._local_channels
            else:
                channels = self._sub_channels

            old_channel = self.current_channel

            if isinstance(idx, int) and 0 <= idx < len(channels or []):
                self.current_channel = channels[idx]
            else:
                index = self.channel_list.row(item)
                if 0 <= index < len(channels or []):
                    self.current_channel = channels[index]
                else:
                    logger.warning(f"select_channel: 无效的索引 idx={idx}, row={index}, channels长度={len(channels or [])}")
                    return

            logger.info(f"select_channel: 选中频道 {self.current_channel.get('name', '?')}")

            if old_channel and old_channel is not self.current_channel:
                self._previous_channel = dict(old_channel)

            try:
                ch_name = self.current_channel.get('name', '')
                ch_url = self.current_channel.get('url', '') or ''
                ch_idx = idx if isinstance(idx, int) and 0 <= idx < len(channels or []) else self.channel_list.row(item)
                is_local = channel_list is self.local_channel_list
                ch_file = getattr(self, '_local_playlist_path', '') if is_local else getattr(self, '_subscription_url', '')
                # 与 event_handler 关闭时保存保持一致：url 作为恢复时的首要匹配键
                self.config.set_value('Player', 'last_channel_url', ch_url)
                self.config.save_last_channel(ch_file, ch_name, ch_idx)
            except Exception:
                pass

            if self.play_state.is_catchup_or_timeshift:
                self.playback_ctrl._exit_catchup_mode()

            self.update_channel_info_on_selection()
            if not self._is_local_file():
                self.populate_epg_list()
            self.play_channel(self.current_channel)
        except Exception as e:
            logger.error(f"select_channel: 选择频道失败: {e}", exc_info=True)

    def _on_channel_single_click(self, item):
        self._pending_click_item = item
        self._pending_click_source = self.sender()
        self._click_timer.start(self.CHANNEL_CLICK_DELAY_MS)

    def _on_sub_channel_context_menu(self, pos):
        self.favorites_ctrl.show_channel_list_context_menu(pos, self.sub_channel_list, 'subscription')

    def _on_local_channel_context_menu(self, pos):
        self.favorites_ctrl.show_channel_list_context_menu(pos, self.local_channel_list, 'local')

    def _deferred_single_click(self):
        if self._pending_click_item:
            self.select_channel(self._pending_click_item, source_list=self._pending_click_source)

    def _on_channel_double_clicked(self, item):
        self._click_timer.stop()
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        sender = self.sender()
        if sender is self.local_channel_list:
            channels = self._local_channels
        else:
            channels = self._sub_channels
        if isinstance(idx, int) and 0 <= idx < len(channels or []):
            channel = channels[idx]
        else:
            return
        if hasattr(self, 'multi_screen_ctrl') and self.multi_screen_ctrl.is_active:
            self.multi_screen_ctrl.play_in_empty_cell(channel)
        else:
            self.select_channel(item, source_list=sender)

    def _get_display_channel_name(self, channel):
        from utils.general_utils import get_display_channel_name
        return get_display_channel_name(channel, self.language_manager)

    def update_channel_info_on_selection(self):
        self.channel_ctrl.update_channel_info_on_selection()

    def _load_last_channel(self):
        try:
            last = self.config.load_last_channel()
            # url 是恢复时的首要匹配键；旧配置没有该字段时保持原有名字/下标恢复
            last_url = self.config.get_value('Player', 'last_channel_url', '')
            if not isinstance(last_url, str):
                last_url = ''
            if last_url:
                last['url'] = last_url
            if last.get('url') or (last.get('name') and last.get('index', -1) >= 0):
                self._pending_last_channel = last
        except Exception as e:
            logger.debug(f"加载最后频道失败: {e}")

    def select_channel_by_index(self, idx, source_list=None):
        target_list = source_list if source_list is not None else getattr(self, 'channel_list', None)
        if not target_list or idx < 0:
            return
        for i in range(target_list.count()):
            item = target_list.item(i)
            if item is None:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == idx:
                target_list.setCurrentItem(item)
                self.select_channel(item, source_list=target_list)
                return

    def switch_to_previous_channel(self):
        if not hasattr(self, '_previous_channel') or not self._previous_channel:
            return
        prev = self._previous_channel
        self._previous_channel = None
        if hasattr(self, 'channel_list'):
            sender = self.sender()
            if sender is getattr(self, 'local_channel_list', None):
                channels = self._local_channels
            else:
                channels = self._sub_channels
            for i in range(self.channel_list.count()):
                item = self.channel_list.item(i)
                if item is None:
                    continue
                idx = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(idx, int) and 0 <= idx < len(channels or []):
                    ch = channels[idx]
                    if ch.get('url') == prev.get('url'):
                        self.channel_list.setCurrentItem(item)
                        self.select_channel(item, source_list=self.channel_list)
                        return

    def _set_channel_view_mode(self, mode, tab='sub'):
        list_widget = self.sub_channel_list if tab == 'sub' else self.local_channel_list
        list_btn = getattr(self, f'{tab}_view_list_btn', None)
        grid_btn = getattr(self, f'{tab}_view_grid_btn', None)

        if mode == 'list':
            if list_btn:
                list_btn.setChecked(True)
            if grid_btn:
                grid_btn.setChecked(False)
            list_widget.setViewMode(QListWidget.ViewMode.ListMode)
            list_widget.setGridSize(QSize())
            list_widget.setIconSize(QSize())
            list_widget.setSpacing(2)
            list_widget.setWrapping(False)
            if hasattr(self, '_thumbnail_service'):
                self._thumbnail_service.stop()
        elif mode == 'grid':
            if list_btn:
                list_btn.setChecked(False)
            if grid_btn:
                grid_btn.setChecked(True)
            list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            list_widget.setGridSize(QSize(230, 160))
            list_widget.setIconSize(QSize(210, 110))
            list_widget.setSpacing(4)
            list_widget.setWrapping(True)
            list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            list_widget.setWordWrap(True)
            list_widget.verticalScrollBar().setSingleStep(30)

        source = 'subscription' if tab == 'sub' else 'local'
        self.populate_channel_list(source)

        if mode == 'grid':
            safe_single_shot(200, self, lambda: self._capture_visible_thumbnails(tab))