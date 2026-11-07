from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolButton, QComboBox, QDockWidget, QButtonGroup,
    QListWidget, QPushButton, QTabWidget, QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtGui import QPixmap
try:
    from shiboken6 import isValid as _shiboken_isvalid
except ImportError:
    _shiboken_isvalid = None

from core.log_manager import global_logger as logger
from ui.styles import AppStyles
from ui.empty_state import EmptyStateLabel
from utils.delay_constants import DelayMs



class PlaylistPanelMixin:
    """从 IPTVPlayer 提取的播放列表面板和EPG面板UI构建职责"""

    def _create_epg_panel(self, show=True):
        """创建EPG面板（QDockWidget 停靠左侧）"""
        logger.debug("_create_epg_panel: 开始")
        tr = self.language_manager.tr

        epg_container = QWidget()
        epg_container.setObjectName("panelContainer")
        epg_container.setStyleSheet("background-color: transparent; border: none;")
        epg_container.setMinimumWidth(200)
        self.epg_layout = QVBoxLayout(epg_container)
        self.epg_layout.setContentsMargins(0, 0, 0, 0)
        self.epg_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        epg_title_row = QHBoxLayout()
        epg_title_row.setSpacing(6)
        epg_title_row.setContentsMargins(8, 4, 8, 0)
        epg_icon_color = AppStyles.get_color('player_panel_text')
        self.epg_title_icon = QLabel()
        self.epg_title_icon.setFixedSize(16, 16)
        self.epg_title_icon.setStyleSheet("background: transparent; border: none;")
        epg_icon_path = AppStyles.get_icon('calendar', epg_icon_color)
        if epg_icon_path:
            self.epg_title_icon.setPixmap(QPixmap(epg_icon_path))
        epg_title_row.addWidget(self.epg_title_icon)
        self.epg_title = QLabel(tr('epg_title', 'Program Guide'))
        self.epg_title.setStyleSheet(AppStyles.player_epg_title_style())
        epg_title_row.addWidget(self.epg_title, 1)
        epg_title_row.addStretch()
        self.epg_layout.addLayout(epg_title_row)

        date_layout = QHBoxLayout()
        date_layout.setContentsMargins(8, 4, 8, 4)
        date_layout.setSpacing(8)

        date_icon_color = AppStyles.get_color('player_panel_text')
        self.epg_prev_day = QPushButton()
        self.epg_prev_day.setIcon(QIcon(AppStyles.get_icon('chevron_left', date_icon_color, 12)))  # type: ignore[arg-type]
        self.epg_prev_day.setIconSize(QSize(12, 12))
        self.epg_prev_day.setFixedSize(24, 24)
        self.epg_prev_day.setCursor(Qt.CursorShape.PointingHandCursor)
        self.epg_prev_day.setStyleSheet(AppStyles.player_date_button_style())
        self.epg_prev_day.clicked.connect(self.epg_ctrl.on_prev_day)
        self.epg_prev_day.setToolTip(tr("tooltip_prev_day", "前一天"))
        date_layout.addWidget(self.epg_prev_day)

        self.epg_date_label = QLabel(tr("today", "Today"))
        self.epg_date_label.setStyleSheet(AppStyles.player_date_label_style())
        self.epg_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_layout.addWidget(self.epg_date_label, 1)

        self.epg_next_day = QPushButton()
        self.epg_next_day.setIcon(QIcon(AppStyles.get_icon('chevron_right', date_icon_color, 12)))  # type: ignore[arg-type]
        self.epg_next_day.setIconSize(QSize(12, 12))
        self.epg_next_day.setFixedSize(24, 24)
        self.epg_next_day.setCursor(Qt.CursorShape.PointingHandCursor)
        self.epg_next_day.setStyleSheet(AppStyles.player_date_button_style())
        self.epg_next_day.clicked.connect(self.epg_ctrl.on_next_day)
        self.epg_next_day.setToolTip(tr("tooltip_next_day", "后一天"))
        date_layout.addWidget(self.epg_next_day)

        self.epg_layout.addLayout(date_layout)

        self.epg_content = QListWidget()
        self.epg_content.setToolTip(tr('epg_content_tooltip', '节目单列表，双击可播放对应频道'))
        self.epg_content.setStyleSheet(AppStyles.player_list_style())
        self.epg_content.setSpacing(2)
        self.epg_content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.epg_content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        from controllers.epg_controller import EPGItemDelegate
        self.epg_content.setItemDelegate(EPGItemDelegate(self.epg_content))
        self.epg_content.addItem(self.language_manager.tr("loading", "Loading..."))
        self.epg_content.itemClicked.connect(self.on_epg_item_clicked)
        self.epg_content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.epg_content.customContextMenuRequested.connect(self._on_epg_context_menu)
        self.epg_layout.addWidget(self.epg_content, 1)

        self.epg_empty_label = EmptyStateLabel(
            self.epg_content, tr("no_epg_data", "No program information")
        )
        # 空态 CTA：动作由 EPG 控制器按空态原因设置（无订阅源/无频道/无节目）
        self.epg_empty_action = 'open_playlist'
        self.epg_empty_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.epg_empty_label.setToolTip(tr("tooltip_open_playlist_cta", "点击打开订阅文件"))

        def _on_epg_empty_clicked(event):
            if event.button() == Qt.MouseButton.LeftButton:
                event.accept()
                action = getattr(self, 'epg_empty_action', 'open_playlist')
                if action == 'manage_sources':
                    settings_ops = getattr(self, 'settings_ops', None)
                    if settings_ops is not None:
                        settings_ops.player_settings()
                    else:
                        self.open_playlist()
                elif action == 'open_playlist':
                    self.open_playlist()

        self.epg_empty_label.mousePressEvent = _on_epg_empty_clicked

        from ui.floating_dialog import FloatingDockWidget
        self.epg_dock = FloatingDockWidget(tr("epg_title", "Program Guide"), self)
        self.epg_dock.setWidget(epg_container)
        self.epg_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.epg_dock.setObjectName("epg_dock")
        if hasattr(self, 'epg_panel'):
            self.epg_panel = None
        self.epg_panel = self.epg_dock

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.epg_dock)
        self.epg_dock.setFloating(True)
        if not show:
            self.epg_dock.hide()

        logger.debug("_create_epg_panel: 完成")

    def _create_playlist_panel(self, show=True):
        """创建播放列表面板（双标签：订阅 + 本地）"""
        logger.debug("_create_playlist_panel: 开始")
        tr = self.language_manager.tr

        playlist_container = QWidget()
        playlist_container.setObjectName("panelContainer")
        playlist_container.setStyleSheet("background-color: transparent; border: none;")
        playlist_container.setMinimumWidth(200)
        self.playlist_layout = QVBoxLayout(playlist_container)
        self.playlist_layout.setContentsMargins(8, 8, 8, 8)

        self.playlist_title = QLabel(tr('playlist_title', 'Channel List'))
        self.playlist_title.setStyleSheet(AppStyles.player_playlist_title_style())
        self.playlist_layout.addWidget(self.playlist_title)

        self._create_playlist_tab_buttons(tr)
        self.playlist_tab = QTabWidget()
        self.playlist_tab.setStyleSheet(AppStyles.player_tab_style())
        self.playlist_tab.tabBar().hide()

        sub_tab = self._create_sub_tab(tr)
        local_tab = self._create_local_tab(tr)
        fav_tab = self._create_fav_tab(tr)
        history_tab = self._create_history_tab(tr)

        self.playlist_tab.addTab(sub_tab, tr("subscription_tab", "Subscription"))
        self.playlist_tab.addTab(local_tab, tr("local_tab", "Local"))
        self.playlist_tab.addTab(fav_tab, tr("favorites_tab", "Favorites"))
        self.playlist_tab.addTab(history_tab, tr("history_tab", "History"))

        self.playlist_tab.currentChanged.connect(self._on_playlist_tab_changed)
        self.playlist_layout.addWidget(self.playlist_tab)

        self.channel_list = self.sub_channel_list
        self.group_combo = self.sub_group_combo
        self.channel_empty_label = self.sub_empty_label
        # 当前页签对应的频道列表（含收藏/历史），供上下键切台使用
        self.active_channel_list = self.sub_channel_list

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._deferred_single_click)
        self._pending_click_item = None
        self._pending_click_source = None

        self._sub_channels = []
        self._local_channels = []
        self._local_channels_dirty = False
        self._sub_groups = [tr("all_channels", "All Channels")]
        self._local_groups = [tr("all_channels", "All Channels")]

        from ui.floating_dialog import FloatingDockWidget
        self.playlist_dock = FloatingDockWidget(tr("channel_list", "Channel List"), self)
        self.playlist_dock.setWidget(playlist_container)
        self.playlist_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.playlist_dock.setObjectName("playlist_dock")
        if hasattr(self, 'playlist_panel'):
            self.playlist_panel = None
        self.playlist_panel = self.playlist_dock

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.playlist_dock)
        self.playlist_dock.setFloating(True)
        self.playlist_dock.setMaximumWidth(600)
        if not show:
            self.playlist_dock.hide()

        logger.debug("_create_playlist_panel: 完成")

    def _create_playlist_tab_buttons(self, tr):
        tab_switch_row = QHBoxLayout()
        tab_switch_row.setContentsMargins(0, 0, 0, 0)
        tab_switch_row.setSpacing(2)
        tab_icon_color = AppStyles.get_color('player_panel_text')
        btn_icon_size = QSize(14, 14)

        self._playlist_tab_btns = []
        tab_configs = [
            ('signal', tr("subscription_tab", "Subscription"), 0),
            ('folder', tr("local_tab", "Local"), 1),
            ('favorite', tr("favorites_tab", "Favorites"), 2),
            ('history', tr("history_tab", "History"), 3),
        ]
        for icon_name, tooltip, tab_idx in tab_configs:
            btn = QToolButton()
            btn.style_type = 'tab_switch'
            icon_path = AppStyles.get_icon(icon_name, tab_icon_color, 14)
            if icon_path:
                btn.setIcon(QIcon(icon_path))
            btn.setIconSize(btn_icon_size)
            btn.setText(tooltip)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setFixedHeight(20)
            btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(AppStyles.tab_button_style(tab_icon_color, AppStyles.get_color('accent')))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setChecked(tab_idx == 0)
            btn.clicked.connect(lambda checked, idx=tab_idx: self._switch_playlist_tab(idx))
            tab_switch_row.addWidget(btn)
            self._playlist_tab_btns.append(btn)
        self.playlist_layout.addLayout(tab_switch_row)

    def _create_channel_list_widget(self, style_type='player', on_click=None, on_double_click=None, on_context_menu=None):
        from ui.multi_screen_widget import DraggableChannelListWidget
        widget = DraggableChannelListWidget()
        widget.style_type = style_type
        widget.setStyleSheet(AppStyles.player_list_style())
        widget.setSpacing(2)
        widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if on_click:
            widget.itemClicked.connect(on_click)
        if on_double_click:
            widget.itemDoubleClicked.connect(on_double_click)
        if on_context_menu:
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(on_context_menu)
        return widget

    def _create_channel_search_row(self, tr, view_icon_color, search_handler, view_scope):
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(4)

        search_input = QLineEdit()
        search_input.setPlaceholderText(tr("search_channel", "搜索频道..."))
        search_input.setClearButtonEnabled(True)
        search_input.setStyleSheet(AppStyles.player_search_input_style())
        search_input.setToolTip(tr("search_channel", "搜索频道"))
        search_input.textChanged.connect(search_handler)
        search_row.addWidget(search_input, 1)

        list_btn = QToolButton()
        list_btn.setIcon(QIcon(AppStyles.get_icon('list_view', view_icon_color)))
        list_btn.setIconSize(QSize(14, 14))
        list_btn.setFixedSize(24, 20)
        list_btn.setStyleSheet(AppStyles.player_button_style())
        list_btn.setCheckable(True)
        list_btn.setChecked(True)
        list_btn.setToolTip(tr("list_view", "列表视图"))
        list_btn.clicked.connect(lambda: self._set_channel_view_mode('list', view_scope))
        search_row.addWidget(list_btn)

        grid_btn = QToolButton()
        grid_btn.setIcon(QIcon(AppStyles.get_icon('grid_view', view_icon_color)))
        grid_btn.setIconSize(QSize(14, 14))
        grid_btn.setFixedSize(24, 20)
        grid_btn.setStyleSheet(AppStyles.player_button_style())
        grid_btn.setCheckable(True)
        grid_btn.setToolTip(tr("grid_view", "网格视图"))
        grid_btn.clicked.connect(lambda: self._set_channel_view_mode('grid', view_scope))
        search_row.addWidget(grid_btn)

        view_group = QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(list_btn, 0)
        view_group.addButton(grid_btn, 1)

        return search_row, search_input, list_btn, grid_btn, view_group

    def _create_sub_tab(self, tr):
        sub_tab = QWidget()
        sub_layout = QVBoxLayout(sub_tab)
        sub_layout.setContentsMargins(4, 4, 4, 4)
        sub_layout.setSpacing(4)

        self.sub_group_combo = QComboBox()
        # 不直接复制 app_state._channel_groups：其值在模块导入时（语言未加载）已固化为英文，
        # 播放列表为空时不会触发 _update_groups_for 重建，需按当前语言取翻译
        self.sub_group_combo.addItems([tr("all_channels", "全部频道")])
        self.sub_group_combo.setStyleSheet(AppStyles.player_group_combo_style())
        self.sub_group_combo.setToolTip(tr("channel_group", "频道分组"))
        self.sub_group_combo.currentTextChanged.connect(self.on_sub_group_changed)
        sub_layout.addWidget(self.sub_group_combo)

        view_icon_color = AppStyles.get_color('player_panel_text')
        search_row, self.sub_search_input, self.sub_view_list_btn, self.sub_view_grid_btn, self._sub_view_group = \
            self._create_channel_search_row(tr, view_icon_color, self._on_sub_search_changed, 'sub')
        sub_layout.addLayout(search_row)

        self.sub_channel_list = self._create_channel_list_widget(
            on_click=self._on_channel_single_click,
            on_double_click=self._on_channel_double_clicked,
            on_context_menu=self._on_sub_channel_context_menu,
        )
        self.sub_channel_list.setToolTip(tr('sub_channel_list_tooltip', '订阅频道列表，双击播放，右键打开菜单'))
        sub_layout.addWidget(self.sub_channel_list, 1)

        self.sub_empty_label = EmptyStateLabel(
            self.sub_channel_list, tr("no_channels", "No channels")
        )

        return sub_tab

    def _create_local_tab(self, tr):
        local_tab = QWidget()
        local_layout = QVBoxLayout(local_tab)
        local_layout.setContentsMargins(4, 4, 4, 4)
        local_layout.setSpacing(4)

        self.local_group_combo = QComboBox()
        self.local_group_combo.addItems([tr("all_channels", "All Channels")])
        self.local_group_combo.setStyleSheet(AppStyles.player_group_combo_style())
        self.local_group_combo.setToolTip(tr("channel_group", "频道分组"))
        self.local_group_combo.currentTextChanged.connect(self.on_local_group_changed)
        local_layout.addWidget(self.local_group_combo)

        view_icon_color = AppStyles.get_color('player_panel_text')
        search_row, self.local_search_input, self.local_view_list_btn, self.local_view_grid_btn, self._local_view_group = \
            self._create_channel_search_row(tr, view_icon_color, self._on_local_search_changed, 'local')
        local_layout.addLayout(search_row)

        self.local_channel_list = self._create_channel_list_widget(
            on_click=self._on_channel_single_click,
            on_double_click=self._on_channel_double_clicked,
            on_context_menu=self._on_local_channel_context_menu,
        )
        self.local_channel_list.setToolTip(tr('local_channel_list_tooltip', '本地频道列表，双击播放，右键打开菜单'))
        local_layout.addWidget(self.local_channel_list, 1)

        self.local_empty_label = EmptyStateLabel(
            self.local_channel_list, tr("no_channels", "No channels")
        )

        return local_tab

    def _create_fav_tab(self, tr):
        fav_tab = QWidget()
        fav_layout = QVBoxLayout(fav_tab)
        fav_layout.setContentsMargins(4, 4, 4, 4)
        fav_layout.setSpacing(4)

        self.fav_channel_list = self._create_channel_list_widget(
            on_click=self.favorites_ctrl.on_favorite_item_clicked,
            on_context_menu=self.favorites_ctrl.show_favorites_context_menu,
        )
        self.fav_channel_list.setToolTip(tr('fav_channel_list_tooltip', '收藏频道列表，双击播放，右键管理收藏'))
        fav_layout.addWidget(self.fav_channel_list, 1)

        self.fav_empty_label = EmptyStateLabel(
            self.fav_channel_list, tr("no_favorites", "No favorites")
        )

        return fav_tab

    def _create_history_tab(self, tr):
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.setSpacing(4)

        self.history_channel_list = self._create_channel_list_widget(
            on_click=self.favorites_ctrl.on_history_item_clicked,
            on_context_menu=self.favorites_ctrl.show_history_context_menu,
        )
        self.history_channel_list.setToolTip(tr('history_channel_list_tooltip', '播放历史列表，双击播放，右键管理历史'))
        history_layout.addWidget(self.history_channel_list, 1)

        self.history_empty_label = EmptyStateLabel(
            self.history_channel_list, tr("no_history", "No play history")
        )

        return history_tab

    def _switch_playlist_tab(self, idx):
        self.playlist_tab.setCurrentIndex(idx)
        for i, btn in enumerate(self._playlist_tab_btns):
            btn.blockSignals(True)
            btn.setChecked(i == idx)
            btn.blockSignals(False)

    def _ensure_playlist_tab_has_content(self):
        """当前页签为空而另一个页签有数据时切换过去。

        只处理订阅/本地两页：不抢用户正在看的非空页签，也不在没有数据的
        情况下反复切页。收藏/历史页签交给各自控制器维护。
        """
        tab = getattr(self, 'playlist_tab', None)
        if tab is None:
            return
        index = tab.currentIndex()
        if index not in (0, 1):
            return
        sub_count = len(getattr(self, '_sub_channels', []) or [])
        local_count = len(getattr(self, '_local_channels', []) or [])
        if index == 0 and sub_count == 0 and local_count > 0:
            self._switch_playlist_tab(1)
        elif index == 1 and local_count == 0 and sub_count > 0:
            self._switch_playlist_tab(0)

    def _on_playlist_tab_changed(self, index):
        """播放列表标签页切换"""

        for i, btn in enumerate(self._playlist_tab_btns):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)
        if index == 0:
            self.channel_list = self.sub_channel_list
            self.group_combo = self.sub_group_combo
            self.channel_empty_label = self.sub_empty_label
            self.active_channel_list = self.sub_channel_list
        elif index == 1:
            self.channel_list = self.local_channel_list
            self.group_combo = self.local_group_combo
            self.channel_empty_label = self.local_empty_label
            self.active_channel_list = self.local_channel_list
        elif index == 2:
            fav_list = getattr(self, 'fav_channel_list', None)
            if fav_list is not None:
                self.active_channel_list = fav_list
            self.favorites_ctrl.populate_favorites_tab()
            return
        elif index == 3:
            history_list = getattr(self, 'history_channel_list', None)
            if history_list is not None:
                self.active_channel_list = history_list
            self.favorites_ctrl.populate_history_tab()
            return

        if self.channel_list.viewMode() == QListWidget.ViewMode.IconMode:
            tab = 'sub' if index == 0 else 'local'
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, lambda: None if (_shiboken_isvalid and not _shiboken_isvalid(self)) else self._capture_visible_thumbnails(tab))

    def on_sub_group_changed(self, group_name):
        """订阅标签分组切换"""
        self._populate_channel_list_for(self.sub_channel_list, self._sub_channels, group_name)
        if self.sub_channel_list.viewMode() == QListWidget.ViewMode.IconMode:
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, lambda: None if (_shiboken_isvalid and not _shiboken_isvalid(self)) else self._capture_visible_thumbnails('sub'))

    def on_local_group_changed(self, group_name):
        """本地标签分组切换"""
        self._populate_channel_list_for(self.local_channel_list, self._local_channels, group_name)
        if self.local_channel_list.viewMode() == QListWidget.ViewMode.IconMode:
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, lambda: None if (_shiboken_isvalid and not _shiboken_isvalid(self)) else self._capture_visible_thumbnails('local'))