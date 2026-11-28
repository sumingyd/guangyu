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

    def populate_channel_list(self, source='subscription', force=False, restore_pending=True):
        if source == 'auto':
            if not hasattr(self, 'playlist_tab'):
                source = 'subscription'
            else:
                source = 'subscription' if self.playlist_tab.currentIndex() == 0 else 'local'

        current_time = time.time()
        if not hasattr(self, '_last_populate_times'):
            self._last_populate_times = {}
        last_time = self._last_populate_times.get(source, 0)

        # 页签各自渲染自己的来源块：订阅页只读 _sub_channels，本地页只读 _local_channels
        channels = self._sub_channels if source == 'subscription' else self._local_channels
        signature = (len(channels or []), id(channels))
        last_signature = getattr(self, '_last_populate_signatures', {}).get(source)
        if not force and signature == last_signature and current_time - last_time < 0.5:
            logger.debug(f"populate_channel_list: 跳过重复调用（source={source}，距上次{current_time - last_time:.2f}秒）")
            return
        if not hasattr(self, '_last_populate_signatures'):
            self._last_populate_signatures = {}
        self._last_populate_signatures[source] = signature
        self._last_populate_times[source] = current_time

        if source == 'subscription':
            self._update_groups_for('subscription')
            self._populate_channel_list_for(self.sub_channel_list, self._sub_channels,
                                            self.sub_group_combo.currentText())
        else:
            self._update_groups_for('local')
            self._populate_channel_list_for(self.local_channel_list, self._local_channels,
                                            self.local_group_combo.currentText())

        pending = getattr(self, '_pending_last_channel', None)
        if pending and restore_pending:
            self._restore_pending_channel(source)

        if hasattr(self, '_update_playlist_tab_counts'):
            self._update_playlist_tab_counts()

    def _rebuild_channel_aggregation(self):
        """重建聚合表：本地块在前、订阅块在后，按归一化播放地址去重。

        聚合表写入 app_state.channels，供播放、EPG 过滤、搜索、服务端与续播使用；
        页签仍按各自的来源块渲染。
        """
        from services.channel_dedup_service import merge_channel_blocks

        aggregated = merge_channel_blocks(
            list(getattr(self, '_local_channels', []) or []),
            list(getattr(self, '_sub_channels', []) or []),
        )
        app_state.replace_channels(aggregated)
        self._sync_channel_model(aggregated)
        if hasattr(self, '_update_playlist_tab_counts'):
            self._update_playlist_tab_counts()
        return aggregated

    def _sync_channel_model(self, channels):
        """让频道模型与聚合表保持一致，扫描/服务端/页签读到同一份数据。"""
        model = getattr(self, 'channel_model', None)
        if model is None:
            return
        try:
            model.beginResetModel()
            model.channels = [dict(ch) for ch in channels]
            if hasattr(model, '_name_cache'):
                model._name_cache = {c.get('name') for c in channels if c.get('name')}
            if hasattr(model, '_group_cache'):
                groups = set()
                for c in channels:
                    for g in (c.get('_groups') or [c.get('group', '')]):
                        if g:
                            groups.add(g)
                model._group_cache = groups
            model.endResetModel()
        except Exception as e:
            logger.warning(f"同步频道模型失败: {e}")

    def _apply_local_block(self, channels, file_path, header_attrs=None,
                           silent=False, record=True):
        """替换本地来源块并重建聚合表。

        silent=True 用于启动自动打开：只准备数据，不切页签、不选频道、不自动播放。
        """
        new_channels = []
        for ch in channels or []:
            item = dict(ch)
            item['source'] = ''
            new_channels.append(item)
        # 本地文件内部也按播放地址去重，避免页签出现同地址重复项
        from services.channel_dedup_service import ChannelDedupService
        new_channels = ChannelDedupService().deduplicate(new_channels)
        self._local_channels = new_channels
        self._local_channels_dirty = True
        self._local_playlist_path = file_path or ''
        model = getattr(self, 'channel_model', None)
        if model is not None and header_attrs is not None:
            model._last_header_attrs = header_attrs
        self._rebuild_channel_aggregation()
        # 启动自动打开只准备数据：不触发上次频道恢复（不自动播放、不选频道）
        self.populate_channel_list(source='local', force=True, restore_pending=not silent)
        if record:
            try:
                self.config.save_last_playlist(file_path, len(new_channels))
            except Exception as e:
                logger.debug(f"记录上次播放列表失败: {e}")
        return new_channels

    def _restore_pending_channel(self, populated_source):
        """恢复上次播放频道；频道在哪一页签就切到哪一页签。

        优先在当前刚填充的列表里查找，找不到再查另一页签，
        避免"订阅为空、频道属于本地"时永远无法恢复或停在空订阅页。
        """
        pending = getattr(self, '_pending_last_channel', None)
        if not pending:
            return

        candidates = [
            ('subscription', self.sub_channel_list, self._sub_channels),
            ('local', self.local_channel_list, self._local_channels),
        ]
        if populated_source != 'subscription':
            candidates.reverse()

        for source, target_list, channels in candidates:
            if not channels:
                continue
            target_idx = self._find_channel_index(channels, pending)
            if target_idx < 0:
                continue
            self._pending_last_channel = None
            tab_index = 0 if source == 'subscription' else 1
            tab = getattr(self, 'playlist_tab', None)
            if tab is not None and tab.currentIndex() != tab_index:
                # 走统一切页入口，保证 active_channel_list 与页签一致
                switch = getattr(self, '_switch_playlist_tab', None)
                if switch is not None:
                    switch(tab_index)
                else:
                    tab.setCurrentIndex(tab_index)
            safe_single_shot(
                100, self,
                lambda idx=target_idx, sl=target_list: self.select_channel_by_index(idx, source_list=sl)
            )
            return

        # 只有两个来源块都已加载且有数据时才判断「配置过期」；
        # 另一来源还没填充时保留 pending，等它加载完继续尝试，避免启动竞态丢失恢复。
        if getattr(self, '_sub_channels', None) and getattr(self, '_local_channels', None):
            self._pending_last_channel = None

    @staticmethod
    def _find_channel_index(channels, pending):
        """按 URL → 下标 → 名称的顺序在给定频道列表中定位待恢复频道。"""
        last_url = pending.get('url', '')
        last_name = pending.get('name', '')
        last_idx = pending.get('index', -1)
        if last_url:
            for i, ch in enumerate(channels):
                if ch.get('url', '') == last_url:
                    return i
        if isinstance(last_idx, int) and 0 <= last_idx < len(channels):
            return last_idx
        if last_name:
            for i, ch in enumerate(channels):
                if ch.get('name', '') == last_name:
                    return i
        return -1

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
            # 清空搜索回到完整列表时，滚动位置应回到顶部，而不是停在搜索结果处
            list_widget.scrollToTop()
            # 可见行集合变化（隐藏行恢复），按新视口补行控件与台标
            self.channel_ctrl.decorate_visible_rows(list_widget)
            self._load_visible_icons(list_widget, channels)
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

        # 过滤后可见行整体换了一批，按新视口补行控件与台标，否则命中行只有裸文本
        self.channel_ctrl.decorate_visible_rows(list_widget)
        self._load_visible_icons(list_widget, channels)

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
        # 滚动到的新行先补上控件，再加载可见台标
        self.channel_ctrl.decorate_visible_rows(list_widget)
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
            # 启动自动续播关闭时不恢复上次频道，避免启动即自动播放
            if not self._is_auto_resume_on_start():
                return
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

    def _is_auto_resume_on_start(self) -> bool:
        """启动自动续播开关（与安卓端同名设置一致），读取失败时按关闭处理。"""
        try:
            settings = self.config.load_playback_settings()
            if isinstance(settings, dict):
                return bool(settings.get('auto_resume_last_channel', False))
        except Exception as e:
            logger.debug(f"读取启动自动续播设置失败: {e}")
        return False

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