"""
订阅UI控制器 - 管理订阅设置对话框中的所有UI逻辑
从 pyqt_player.py 提取的独立模块
"""

from PySide6.QtWidgets import QListWidgetItem
from PySide6 import QtCore
from controllers.main_window_protocol import MainWindowProtocol


class SubscriptionUIController:
    """订阅UI控制器 - 管理订阅源设置对话框的所有逻辑"""

    def __init__(self, main_window: MainWindowProtocol):
        self.window: MainWindowProtocol = main_window

    def _tr(self, key, default):
        w = self.window
        if w and w.language_manager:
            return w.language_manager.tr(key, default)
        return default or key

    def load_subscription_sources_to_ui(self, pl_widget=None, epg_widget=None):
        from core.log_manager import global_logger as logger
        from core.subscription_manager import global_subscription_manager

        widget = pl_widget or self.window.playlist_list_widget
        epg_w = epg_widget or self.window.epg_list_widget

        if widget is None or epg_w is None:
            logger.warning("load_subscription_sources_to_ui: widget为空")
            return

        widget.clear()
        playlist_sources = self._safe_get_sources(global_subscription_manager.get_playlist_sources, logger, '直播源')
        for source in playlist_sources:
            item = QListWidgetItem(f"{'✓ ' if source.get('enabled') else '  '}{source.get('name', 'Unnamed')}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, source)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if source.get('enabled') else QtCore.Qt.CheckState.Unchecked)
            item.setToolTip(source.get('url', ''))
            widget.addItem(item)

        epg_w.clear()
        epg_sources = self._safe_get_sources(global_subscription_manager.get_epg_sources, logger, 'EPG源')
        for source in epg_sources:
            item = QListWidgetItem(source.get('name', 'Unnamed'))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, source)
            item.setToolTip(source.get('url', ''))
            epg_w.addItem(item)

    @staticmethod
    def _safe_get_sources(getter, logger, label):
        try:
            result = getter()
            logger.debug(f"加载{label}列表: {len(result)} 个源")
            return result
        except Exception as e:
            logger.error(f"获取{label}列表失败: {e}")
            return []

    # ---- 通用源管理辅助方法 ----

    def _get_source_config(self, source_type):
        """获取指定类型源的配置元数据"""
        if source_type == 'playlist':
            return {
                'list_widget': self.window.playlist_list_widget,
                'url_edit': self.window.playlist_new_url_edit,
                'name_edit': self.window.playlist_new_name_edit,
                'add_btn': self.window._playlist_add_btn,
                'editing_index_attr': '_editing_playlist_index',
                'manager_getter': '_get_playlist_sources',
                'manager_adder': '_add_playlist_source',
                'manager_updater': '_update_playlist_source',
                'manager_remover': '_remove_playlist_source',
            }
        elif source_type == 'epg':
            return {
                'list_widget': self.window.epg_list_widget,
                'url_edit': self.window.epg_new_url_edit,
                'name_edit': self.window.epg_new_name_edit,
                'add_btn': self.window._epg_add_btn,
                'editing_index_attr': '_editing_epg_index',
                'manager_getter': '_get_epg_sources',
                'manager_adder': '_add_epg_source',
                'manager_updater': '_update_epg_source',
                'manager_remover': '_remove_epg_source',
            }
        return {}

    def _get_editing_index(self, source_type):
        attr = self._get_source_config(source_type).get('editing_index_attr', '')
        return getattr(self.window, attr, -1)

    def _set_editing_index(self, source_type, value):
        attr = self._get_source_config(source_type).get('editing_index_attr', '')
        setattr(self.window, attr, value)

    @staticmethod
    def _get_playlist_sources(mgr):
        return mgr.get_playlist_sources()

    @staticmethod
    def _add_playlist_source(mgr, url, name):
        return mgr.add_playlist_source(url, name)

    @staticmethod
    def _update_playlist_source(mgr, index, url, name):
        return mgr.update_playlist_source(index, url, name)

    @staticmethod
    def _remove_playlist_source(mgr, index):
        return mgr.remove_playlist_source(index)

    @staticmethod
    def _get_epg_sources(mgr):
        return mgr.get_epg_sources()

    @staticmethod
    def _add_epg_source(mgr, url, name):
        return mgr.add_epg_source(url, name)

    @staticmethod
    def _update_epg_source(mgr, index, url, name):
        return mgr.update_epg_source(index, url, name)

    @staticmethod
    def _remove_epg_source(mgr, index):
        return mgr.remove_epg_source(index)

    # ---- 直播源 CRUD ----

    def add_or_update_playlist_source(self):
        self._add_or_update_source('playlist')

    def edit_playlist_source(self, item):
        self._edit_source('playlist', item)

    def remove_selected_playlist_source(self):
        self._remove_selected_source('playlist')

    def activate_playlist_source(self, item):
        """激活指定的直播源（点击切换，仅更新UI，保存时才生效）"""
        index = self.window.playlist_list_widget.row(item)
        if index >= 0:
            for i in range(self.window.playlist_list_widget.count()):
                list_item = self.window.playlist_list_widget.item(i)
                source = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
                if source:
                    source['enabled'] = (i == index)
                    check_state = QtCore.Qt.CheckState.Checked if i == index else QtCore.Qt.CheckState.Unchecked
                    list_item.setCheckState(check_state)
                    prefix = '✓ ' if i == index else '  '
                    list_item.setText(f"{prefix}{source.get('name', 'Unnamed')}")

    # ---- EPG 源 CRUD ----

    def add_or_update_epg_source(self):
        self._add_or_update_source('epg')

    def edit_epg_source(self, item):
        self._edit_source('epg', item)

    def remove_selected_epg_source(self):
        self._remove_selected_source('epg')

    # ---- 通用实现 ----

    def _refresh_source_item_text(self, item, source, source_type):
        if source_type == 'playlist':
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            checked = bool(source.get('enabled'))
            item.setCheckState(
                QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
            item.setText(f"{'✓ ' if checked else '  '}{source.get('name', 'Unnamed')}")
        else:
            item.setText(source.get('name', 'Unnamed'))
        item.setToolTip(source.get('url', ''))

    def _add_or_update_source(self, source_type):
        """只改对话框内的列表，写盘与下载统一在点「保存」时进行。

        以前每次增删改都立即写配置：点「取消」也会生效，且保存时对比不出
        URL 变化，改完订阅地址不会重新下载。
        """
        cfg = self._get_source_config(source_type)

        url = cfg['url_edit'].text().strip()
        name = cfg['name_edit'].text().strip() or None
        if not url:
            return

        editing_index = self._get_editing_index(source_type)
        list_widget = cfg['list_widget']

        if 0 <= editing_index < list_widget.count():
            item = list_widget.item(editing_index)
            source = dict(item.data(QtCore.Qt.ItemDataRole.UserRole) or {})
            source['url'] = url
            if name:
                source['name'] = name
            item.setData(QtCore.Qt.ItemDataRole.UserRole, source)
            self._refresh_source_item_text(item, source, source_type)
            self._set_editing_index(source_type, -1)
            cfg['add_btn'].setText(self._tr("add_source", "+ Add Source"))
        else:
            source = {
                'url': url,
                'name': name or f"Source {list_widget.count() + 1}",
                'enabled': list_widget.count() == 0,
            }
            item = QListWidgetItem(source['name'])
            item.setData(QtCore.Qt.ItemDataRole.UserRole, source)
            list_widget.addItem(item)
            self._refresh_source_item_text(item, source, source_type)

        cfg['url_edit'].clear()
        cfg['name_edit'].clear()

    def _edit_source(self, source_type, item):
        if not item:
            return
        cfg = self._get_source_config(source_type)
        list_widget = cfg['list_widget']
        current_row = list_widget.row(item)
        if current_row < 0:
            return
        source = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not source:
            return
        cfg['url_edit'].setText(source.get('url', ''))
        cfg['name_edit'].setText(source.get('name', ''))
        self._set_editing_index(source_type, current_row)
        cfg['add_btn'].setText(self._tr("update_source", "✎ Update"))

    def _remove_selected_source(self, source_type):
        """只从对话框列表移除，点「保存」时才写配置。"""
        cfg = self._get_source_config(source_type)
        list_widget = cfg['list_widget']

        current_row = list_widget.currentRow()
        if current_row < 0:
            return

        removed = list_widget.takeItem(current_row)
        removed_source = removed.data(QtCore.Qt.ItemDataRole.UserRole) if removed else None

        # 删掉的正好是启用中的直播源：把第一项改为启用，避免保存后没有任何启用的源
        if source_type == 'playlist' and removed_source and removed_source.get('enabled'):
            if list_widget.count() > 0:
                first = list_widget.item(0)
                first_source = dict(first.data(QtCore.Qt.ItemDataRole.UserRole) or {})
                first_source['enabled'] = True
                first.setData(QtCore.Qt.ItemDataRole.UserRole, first_source)
                self._refresh_source_item_text(first, first_source, source_type)

        editing_index = self._get_editing_index(source_type)
        if editing_index == current_row:
            self._set_editing_index(source_type, -1)
            cfg['add_btn'].setText(self._tr("add_source", "+ Add Source"))
            cfg['url_edit'].clear()
            cfg['name_edit'].clear()
        elif editing_index > current_row:
            self._set_editing_index(source_type, editing_index - 1)