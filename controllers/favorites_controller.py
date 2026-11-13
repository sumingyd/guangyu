from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from PySide6 import QtWidgets
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QInputDialog, QListWidget, QListWidgetItem, QMessageBox
from core.log_manager import global_logger as logger
from controllers.main_window_protocol import ChannelProtocol


class FavoritesController:
    def __init__(self, main_window: ChannelProtocol):
        self.window: ChannelProtocol = main_window
        self._service = None

    def init_service(self, config_manager):
        from services.favorites_service import FavoritesService
        self._service = FavoritesService(config_manager)

    @property
    def service(self):
        return self._service

    def on_channel_played(self, channel: Dict[str, Any]):
        if self._service and channel and channel.get('url'):
            self._service.record_play(channel)
            playlist_tab = getattr(self.window, 'playlist_tab', None)
            if playlist_tab and playlist_tab.currentIndex() == 3:
                self.populate_history_tab()
            else:
                self._refresh_tab_counts()

    def toggle_favorite(self, channel: Optional[Dict[str, Any]] = None):
        ch = channel or getattr(self.window, 'current_channel', None)
        if not ch or not self._service:
            return
        is_fav = self._service.toggle_favorite(ch)
        tr = self.window.language_manager.tr
        if is_fav:
            self.window.status_bar_show_message(tr('added_to_favorites', '已添加到收藏夹'))
        else:
            self.window.status_bar_show_message(tr('removed_from_favorites', '已从收藏夹移除'))
        self.populate_favorites_tab()
        return is_fav

    def is_favorite(self, channel: Optional[Dict[str, Any]] = None) -> bool:
        ch = channel or getattr(self.window, 'current_channel', None)
        if not ch or not self._service:
            return False
        return self._service.is_favorite(ch)

    def get_favorites(self) -> List[Dict[str, Any]]:
        if self._service:
            return self._service.get_favorites()
        return []

    def get_play_history(self) -> List[Dict[str, Any]]:
        if self._service:
            return self._service.get_play_history()
        return []

    def _refresh_tab_counts(self):
        updater = getattr(self.window, '_update_playlist_tab_counts', None)
        if updater is not None:
            try:
                updater()
            except Exception as e:
                logger.debug(f"刷新页签条目数失败: {e}")

    def populate_favorites_tab(self):
        list_widget = getattr(self.window, 'fav_channel_list', None)
        if list_widget is None:
            return
        list_widget.clear()
        if not self._service:
            return
        from ui.styles import AppStyles
        w = self.window
        tr = w.language_manager.tr
        name_style = AppStyles.player_channel_list_name_style()
        channels = self._service.get_favorites()

        for idx, channel in enumerate(channels):
            try:
                channel_name = channel.get('name', tr('unnamed', 'Unnamed'))
                try:
                    item_widget = QtWidgets.QWidget()
                    item_layout = QtWidgets.QHBoxLayout(item_widget)
                    item_layout.setContentsMargins(5, 2, 5, 2)
                    item_layout.setSpacing(8)
                    logo_label = QtWidgets.QLabel()
                    logo_label.setFixedSize(44, 32)
                    logo_label.setStyleSheet(AppStyles.transparent_style())
                    logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    logo_label.setObjectName("channel_logo_label")
                    name_label = QtWidgets.QLabel(channel_name)
                    name_label.setStyleSheet(name_style)
                    name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    name_label.setWordWrap(False)
                    item_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
                    item_layout.addWidget(name_label, 1, Qt.AlignmentFlag.AlignVCenter)
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(0, 40))
                    item.setData(Qt.ItemDataRole.UserRole, idx)
                    list_widget.addItem(item)
                    list_widget.setItemWidget(item, item_widget)
                except Exception as widget_ex:
                    simple_item = QListWidgetItem(channel_name)
                    simple_item.setData(Qt.ItemDataRole.UserRole, idx)
                    list_widget.addItem(simple_item)
                    if logger:
                        logger.warning(f"收藏项自定义widget创建失败(idx={idx})，使用简单文本: {widget_ex}")
                logo_url = channel.get('logo', '')
                if logo_url:
                    logo_cache = getattr(w, '_logo_cache_service', None)
                    if logo_cache:
                        cached = logo_cache.get(logo_url)
                        if cached:
                            scaled = logo_cache.scale_logo_pixmap_to_fit(cached, 44, 32)
                            logo_label.setPixmap(scaled)
                        else:
                            logo_cache.fetch_async(logo_url)
            except Exception as e:
                if logger:
                    logger.warning(f"填充收藏项失败(idx={idx}): {e}")
        empty_label = getattr(self.window, 'fav_empty_label', None)
        if empty_label:
            if len(channels) == 0:
                empty_label.show()
            else:
                empty_label.hide()
        self._refresh_tab_counts()

    def populate_history_tab(self):
        list_widget = getattr(self.window, 'history_channel_list', None)
        if list_widget is None:
            return
        list_widget.clear()
        if not self._service:
            return
        from ui.styles import AppStyles
        w = self.window
        tr = w.language_manager.tr
        name_style = AppStyles.player_channel_list_name_style()
        channels = self._service.get_play_history()

        for idx, channel in enumerate(channels):
            try:
                channel_name = channel.get('name', tr('unnamed', 'Unnamed'))
                play_time = channel.get('play_time', '')
                time_str = ''
                if play_time:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(play_time)
                        time_str = dt.strftime('%m/%d %H:%M')
                    except Exception as e:
                        logger.debug(f"解析收藏播放时间失败: {e}")
                display_name = f"{channel_name}  {time_str}" if time_str else channel_name
                try:
                    item_widget = QtWidgets.QWidget()
                    item_layout = QtWidgets.QHBoxLayout(item_widget)
                    item_layout.setContentsMargins(5, 2, 5, 2)
                    item_layout.setSpacing(8)
                    logo_label = QtWidgets.QLabel()
                    logo_label.setFixedSize(44, 32)
                    logo_label.setStyleSheet(AppStyles.transparent_style())
                    logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    logo_label.setObjectName("channel_logo_label")
                    name_label = QtWidgets.QLabel(display_name)
                    name_label.setStyleSheet(name_style)
                    name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    name_label.setWordWrap(False)
                    item_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
                    item_layout.addWidget(name_label, 1, Qt.AlignmentFlag.AlignVCenter)
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(0, 40))
                    item.setData(Qt.ItemDataRole.UserRole, idx)
                    list_widget.addItem(item)
                    list_widget.setItemWidget(item, item_widget)
                except Exception as widget_ex:
                    simple_item = QListWidgetItem(display_name)
                    simple_item.setData(Qt.ItemDataRole.UserRole, idx)
                    list_widget.addItem(simple_item)
                    if logger:
                        logger.warning(f"历史项自定义widget创建失败(idx={idx})，使用简单文本: {widget_ex}")
                logo_url = channel.get('logo', '')
                if logo_url:
                    logo_cache = getattr(w, '_logo_cache_service', None)
                    if logo_cache:
                        cached = logo_cache.get(logo_url)
                        if cached:
                            scaled = logo_cache.scale_logo_pixmap_to_fit(cached, 44, 32)
                            logo_label.setPixmap(scaled)
                        else:
                            logo_cache.fetch_async(logo_url)
            except Exception as e:
                if logger:
                    logger.warning(f"填充历史项失败(idx={idx}): {e}")
        empty_label = getattr(self.window, 'history_empty_label', None)
        if empty_label:
            if len(channels) == 0:
                empty_label.show()
            else:
                empty_label.hide()
        self._refresh_tab_counts()

    def on_favorite_item_clicked(self, item):
        if not self._service:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        favorites = self._service.get_favorites()
        if isinstance(idx, int) and 0 <= idx < len(favorites):
            channel = favorites[idx]
            self._play_from_entry(channel)

    def on_history_item_clicked(self, item):
        if not self._service:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        history = self._service.get_play_history()
        if isinstance(idx, int) and 0 <= idx < len(history):
            channel = history[idx]
            self._play_from_entry(channel)

    def _play_from_entry(self, channel: Dict[str, Any]):
        w = self.window
        url = channel.get('url', '')
        name = channel.get('name', '')
        if not url:
            return
        existing_ch = None
        for ch_list in (getattr(w, '_sub_channels', None) or [], getattr(w, '_local_channels', None) or []):
            for ch in ch_list:
                if ch.get('url', '') == url:
                    existing_ch = ch
                    break
            if existing_ch:
                break
        if existing_ch:
            w.current_channel = existing_ch
            w.update_channel_info_on_selection()
            w.play_channel(existing_ch)
        else:
            w.current_channel = channel
            if hasattr(w, 'channel_name'):
                w.channel_name.setText(name)
            w.play_channel(channel)

    def show_channel_list_context_menu(self, pos, list_widget, source):
        w = self.window
        tr = w.language_manager.tr
        item = list_widget.itemAt(pos)
        if not item:
            menu = QMenu(list_widget)
            menu.setStyleSheet(self._get_menu_style())
            menu.addAction(tr('ctx_add_channel', '添加频道'), lambda: self._add_channel_from_url(source))
            menu.addAction(tr('ctx_refresh_list', '刷新列表'), lambda: self._refresh_channel_list(source))
            menu.exec(list_widget.mapToGlobal(pos))
            return

        idx = item.data(Qt.ItemDataRole.UserRole)
        if source == 'subscription':
            channels = getattr(w, '_sub_channels', None) or []
        else:
            channels = getattr(w, '_local_channels', None) or []

        if not isinstance(idx, int) or idx < 0 or idx >= len(channels):
            return

        channel = channels[idx]
        menu = QMenu(list_widget)
        menu.setStyleSheet(self._get_menu_style())

        # 播放
        play_action = menu.addAction(tr('ctx_play_now', '播放'))
        play_action.triggered.connect(lambda: self._play_channel_from_list(channel))

        menu.addSeparator()

        # 收藏
        is_fav = self.is_favorite(channel)
        if is_fav:
            fav_action = menu.addAction(tr('remove_from_favorites', '删除收藏'))
            fav_action.triggered.connect(lambda: self._do_remove_favorite(channel))
        else:
            fav_action = menu.addAction(tr('add_to_favorites', '加入收藏'))
            fav_action.triggered.connect(lambda: self._do_add_favorite(channel))

        # 订阅频道可以复制到本地
        if source == 'subscription':
            add_local_action = menu.addAction(tr('add_to_local', '添加到本地列表'))
            add_local_action.triggered.connect(lambda: self._do_add_to_local(channel))

        menu.addSeparator()

        # 复制
        copy_name_action = menu.addAction(tr('copy_channel_name', '复制频道名称'))
        copy_name_action.triggered.connect(lambda: self._copy_text(channel.get('name', '')))
        copy_url_action = menu.addAction(tr('copy_channel_url', '复制频道地址'))
        copy_url_action.triggered.connect(lambda: self._copy_text(channel.get('url', '')))

        menu.addSeparator()

        # 编辑频道信息
        edit_action = menu.addAction(tr('edit_channel_info', '编辑频道信息'))
        edit_action.triggered.connect(lambda: self._edit_channel_info(channel, idx, source, list_widget))

        # 移动到分组
        if source == 'local':
            move_action = menu.addAction(tr('move_to_group', '移动到分组'))
            move_action.triggered.connect(lambda: self._move_channel_to_group(channel, idx, list_widget))

        if source == 'local':
            menu.addSeparator()
            del_action = menu.addAction(tr('delete_channel', '删除频道'))
            del_action.triggered.connect(lambda: self._do_delete_local_channel(idx))

        menu.exec(list_widget.mapToGlobal(pos))

    def _edit_channel_info(self, channel, idx, source, list_widget):
        w = self.window
        tr = w.language_manager.tr
        new_name, ok = QInputDialog.getText(
            w, tr('edit_channel_info', '编辑频道信息'),
            tr('channel_name', '频道名称:'), text=channel.get('name', ''))
        if not ok:
            return
        new_url, ok = QInputDialog.getText(
            w, tr('edit_channel_info', '编辑频道信息'),
            tr('channel_url', '频道地址:'), text=channel.get('url', ''))
        if not ok:
            return
        channel['name'] = new_name
        channel['url'] = new_url
        if source == 'subscription':
            channels = getattr(w, '_sub_channels', None) or []
        else:
            channels = getattr(w, '_local_channels', None) or []
        if 0 <= idx < len(channels):
            channels[idx] = channel
        if hasattr(w, 'channel_model'):
            w.channel_model.channels = channels
            w.channel_model.refresh()
        logger.info(f"编辑频道: {new_name}")

    def _move_channel_to_group(self, channel, idx, list_widget):
        w = self.window
        tr = w.language_manager.tr
        channels = getattr(w, '_local_channels', None) or []
        groups = sorted(set(ch.get('group', '') for ch in channels if ch.get('group')))
        if not groups:
            return
        items = [tr('uncategorized', '未分类')] + groups
        choice, ok = QInputDialog.getItem(
            w, tr('move_to_group', '移动到分组'),
            tr('select_group', '选择分组:'), items, 0, False)
        if not ok:
            return
        if choice == items[0]:
            choice = ''
        channel['group'] = choice
        channel['_groups'] = [choice] if choice else []
        if 0 <= idx < len(channels):
            channels[idx] = channel
        if hasattr(w, 'channel_model'):
            w.channel_model.channels = channels
            w.channel_model.refresh()
        logger.info(f"移动频道到分组: {choice}")

    def show_favorites_context_menu(self, pos):
        w = self.window
        tr = w.language_manager.tr
        list_widget = getattr(w, 'fav_channel_list', None)
        if list_widget is None:
            return

        menu = QMenu(list_widget)
        menu.setStyleSheet(self._get_menu_style())

        item = list_widget.itemAt(pos)
        has_item = False
        if item:
            idx = item.data(Qt.ItemDataRole.UserRole)
            favorites = self._service.get_favorites() if self._service else []
            if isinstance(idx, int) and 0 <= idx < len(favorites):
                channel = favorites[idx]
                has_item = True

                # 播放
                play_action = menu.addAction(tr('ctx_play_now', '播放'))
                play_action.triggered.connect(lambda: self._play_channel_from_list(channel))

                menu.addSeparator()

                # 删除收藏
                del_action = menu.addAction(tr('remove_from_favorites', '删除收藏'))
                del_action.triggered.connect(lambda: self._do_remove_favorite(channel))

                menu.addSeparator()

                # 添加到本地列表
                add_local_action = menu.addAction(tr('add_to_local', '添加到本地列表'))
                add_local_action.triggered.connect(lambda: self._add_to_local_from_channel(channel))

                menu.addSeparator()

                # 复制
                copy_name_action = menu.addAction(tr('copy_channel_name', '复制频道名称'))
                copy_name_action.triggered.connect(lambda: self._copy_text(channel.get('name', '')))
                copy_url_action = menu.addAction(tr('copy_channel_url', '复制频道地址'))
                copy_url_action.triggered.connect(lambda: self._copy_text(channel.get('url', '')))

        if self._service and self._service.get_favorites():
            if has_item:
                menu.addSeparator()
            clear_action = menu.addAction(tr('clear_favorites', '清空收藏'))
            clear_action.triggered.connect(self._do_clear_favorites)

        if menu.actions():
            menu.exec(list_widget.mapToGlobal(pos))

    def show_history_context_menu(self, pos):
        w = self.window
        tr = w.language_manager.tr
        list_widget = getattr(w, 'history_channel_list', None)
        if list_widget is None:
            return

        menu = QMenu(list_widget)
        menu.setStyleSheet(self._get_menu_style())

        item = list_widget.itemAt(pos)
        has_item = False
        if item:
            idx = item.data(Qt.ItemDataRole.UserRole)
            history = self._service.get_play_history() if self._service else []
            if isinstance(idx, int) and 0 <= idx < len(history):
                channel = history[idx]
                has_item = True

                # 播放
                play_action = menu.addAction(tr('ctx_play_now', '播放'))
                play_action.triggered.connect(lambda: self._play_channel_from_list(channel))

                menu.addSeparator()

                # 删除单条历史
                del_action = menu.addAction(tr('remove_from_history', '删除此历史记录'))
                del_action.triggered.connect(lambda: self._do_remove_history(channel.get('url', '')))

                menu.addSeparator()

                # 加入收藏
                fav_action = menu.addAction(tr('add_to_favorites', '加入收藏'))
                fav_action.triggered.connect(lambda: self._add_to_favorites_from_channel(channel))
                # 添加到本地列表
                add_local_action = menu.addAction(tr('add_to_local', '添加到本地列表'))
                add_local_action.triggered.connect(lambda: self._add_to_local_from_channel(channel))

                menu.addSeparator()

                # 复制
                copy_name_action = menu.addAction(tr('copy_channel_name', '复制频道名称'))
                copy_name_action.triggered.connect(lambda: self._copy_text(channel.get('name', '')))
                copy_url_action = menu.addAction(tr('copy_channel_url', '复制频道地址'))
                copy_url_action.triggered.connect(lambda: self._copy_text(channel.get('url', '')))

        if self._service and self._service.get_play_history():
            if has_item:
                menu.addSeparator()
            clear_action = menu.addAction(tr('clear_history', '清空历史'))
            clear_action.triggered.connect(self._do_clear_history)

        if menu.actions():
            menu.exec(list_widget.mapToGlobal(pos))

    def _do_add_favorite(self, channel):
        if not self._service or not channel:
            return
        self._service.add_to_favorites(channel)
        tr = self.window.language_manager.tr
        self.window.status_bar_show_message(tr('added_to_favorites', '已添加到收藏夹'))
        self.populate_favorites_tab()

    def _do_remove_favorite(self, channel):
        if not self._service or not channel:
            return
        self._service.remove_from_favorites(channel)
        tr = self.window.language_manager.tr
        self.window.status_bar_show_message(tr('removed_from_favorites', '已从收藏夹移除'))
        self.populate_favorites_tab()

    def _do_add_to_local(self, channel):
        w = self.window
        import copy
        w._add_to_local_list(copy.deepcopy(channel))
        tr = w.language_manager.tr
        w.status_bar_show_message(tr('added_to_local', '已添加到本地列表'))

    def _do_remove_history(self, url):
        if not self._service or not url:
            return
        self._service.remove_from_history(url)
        self.populate_history_tab()
        tr = self.window.language_manager.tr
        self.window.status_bar_show_message(tr('history_removed', '历史记录已删除'))

    def _play_channel_from_list(self, channel):
        w = self.window
        if not channel:
            return
        w.current_channel = channel
        w.update_channel_info_on_selection()
        w.play_channel(channel)

    def _copy_text(self, text):
        if not text:
            return
        QApplication.clipboard().setText(text)
        tr = self.window.language_manager.tr
        self.window.status_bar_show_message(tr('copied_to_clipboard', '已复制到剪贴板'))

    def _do_delete_local_channel(self, idx):
        w = self.window
        channels = getattr(w, '_local_channels', None) or []
        if not isinstance(idx, int) or idx < 0 or idx >= len(channels):
            return
        tr = w.language_manager.tr
        name = channels[idx].get('name', '')
        if QMessageBox.question(w, tr('confirm_delete', '确认删除'),
                tr('confirm_delete_channel', '确定删除频道') + f' "{name}"?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        removed = channels.pop(idx)
        w._local_channels_dirty = True
        w._update_groups_for('local')
        w._populate_channel_list_for(
            w.local_channel_list, w._local_channels,
            w.local_group_combo.currentText()
        )
        w.status_bar_show_message(tr('channel_deleted', '频道已删除') + f': {name}')

    def _do_clear_history(self):
        if not self._service:
            return
        tr = self.window.language_manager.tr
        if QMessageBox.question(self.window, tr('confirm_clear', '确认清空'),
                tr('confirm_clear_history', '确定清空所有播放历史？此操作不可撤销。'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._service.clear_play_history()
        self.populate_history_tab()
        self.window.status_bar_show_message(tr('history_cleared', '历史已清空'))

    def _do_clear_favorites(self):
        if not self._service:
            return
        tr = self.window.language_manager.tr
        if QMessageBox.question(self.window, tr('confirm_clear', '确认清空'),
                tr('confirm_clear_favorites', '确定清空所有收藏？此操作不可撤销。'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._service.clear_favorites()
        self.populate_favorites_tab()
        self.window.status_bar_show_message(tr('favorites_cleared', '收藏已清空'))

    def _add_channel_from_url(self, source):
        """从URL添加频道到本地列表"""
        tr = self.window.language_manager.tr
        url, ok = QInputDialog.getText(self.window, tr('add_channel', '添加频道'),
            tr('enter_channel_url', '请输入频道URL:'))
        if ok and url.strip():
            ch = {'name': url.strip().split('/')[-1] or url.strip(), 'url': url.strip(),
                  'group': tr('uncategorized', '未分类'), 'valid': None, 'source': ''}
            self.window._local_channels.append(ch)
            self.window._local_channels_dirty = True
            self.window._update_groups_for('local')
            self.window._populate_channel_list_for(
                self.window.local_channel_list, self.window._local_channels,
                self.window.local_group_combo.currentText())
            self.window.status_bar_show_message(tr('channel_added', '频道已添加'))

    def _refresh_channel_list(self, source):
        """刷新频道列表"""
        if source == 'subscription':
            self.window._populate_channel_list_for(
                self.window.sub_channel_list, self.window._sub_channels,
                self.window.sub_group_combo.currentText())
        else:
            self.window._populate_channel_list_for(
                self.window.local_channel_list, self.window._local_channels,
                self.window.local_group_combo.currentText())

    def _add_to_favorites_from_channel(self, channel):
        """从频道信息加入收藏"""
        if self._service:
            self._service.add_to_favorites(channel)
            self.populate_favorites_tab()
            tr = self.window.language_manager.tr
            self.window.status_bar_show_message(tr('added_to_favorites', '已加入收藏'))

    def _add_to_local_from_channel(self, channel):
        """从频道信息添加到本地列表"""
        ch = {**channel, 'source': ''}
        self.window._local_channels.append(ch)
        self.window._local_channels_dirty = True
        self.window._update_groups_for('local')
        self.window._populate_channel_list_for(
            self.window.local_channel_list, self.window._local_channels,
            self.window.local_group_combo.currentText())
        tr = self.window.language_manager.tr
        self.window.status_bar_show_message(tr('added_to_local', '已添加到本地列表'))

    def _get_menu_style(self):
        from ui.styles import AppStyles
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"""
            QMenu {{
                background-color: {c.get('base', '#1e1e1e')};
                color: {c.get('window_text', '#ffffff')};
                border: 1px solid {c.get('border', '#444444')};
                border-radius: {r}px;
                padding: 4px 0px;
            }}
            QMenu::item {{
                padding: 6px 24px;
                border-radius: {r}px;
                margin: 1px 4px;
            }}
            QMenu::item:selected {{
                background-color: {c.get('accent', '#4a9eff')};
                color: {c.get('highlighted_text', '#ffffff')};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {c.get('mid', '#333333')};
                margin: 4px 8px;
            }}
        """
