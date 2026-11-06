import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from mixins.channel_mixin import ChannelMixin  # noqa: E402
from mixins.settings_mixin import SettingsMixin  # noqa: E402
from mixins.window_mixin import WindowMixin  # noqa: E402
from tests.conftest import MockMainWindow  # noqa: E402


class _ChannelTestHost(MockMainWindow, ChannelMixin):
    pass


class _SettingsTestHost(MockMainWindow, SettingsMixin):
    pass


class _WindowTestHost(MockMainWindow, WindowMixin):
    pass


class TestChannelMixin:
    def setup_method(self):
        self.host = _ChannelTestHost()
        self.host.subscription_ctrl = MagicMock()
        self.host.channel_ctrl = MagicMock()
        self.host.favorites_ctrl = MagicMock()
        self.host.sub_channel_list = MagicMock()
        self.host.local_channel_list = MagicMock()
        self.host.sub_group_combo = MagicMock()
        self.host.local_group_combo = MagicMock()
        self.host.playlist_tab = MagicMock()
        self.host._sub_channels = []
        self.host._local_channels = []
        self.host._pending_last_channel = None
        self.host._pending_click_item = None
        self.host._pending_click_source = None
        self.host._click_timer = MagicMock()
        self.host.CHANNEL_CLICK_DELAY_MS = 300
        self.host.current_channel = None
        self.host.play_state = MagicMock()
        self.host.play_state.is_catchup_or_timeshift = False
        self.host.playback_ctrl = MagicMock()
        self.host.config = MagicMock()
        self.host.channel_list = MagicMock()
        self.host.multi_screen_ctrl = MagicMock()
        self.host.multi_screen_ctrl.is_active = False

    def test_update_channel_groups(self):
        self.host.update_channel_groups()
        self.host.subscription_ctrl.update_channel_groups.assert_called_once()

    def test_on_group_changed(self):
        self.host.on_group_changed('All')
        self.host.channel_ctrl.on_group_changed.assert_called_once_with('All')

    def test_populate_channel_list_for(self):
        self.host._populate_channel_list_for(self.host.sub_channel_list, [], '')
        self.host.channel_ctrl.populate_channel_list_for.assert_called_once()

    def test_load_visible_icons(self):
        self.host._load_visible_icons(self.host.sub_channel_list, [])
        self.host.channel_ctrl.load_visible_icons.assert_called_once()

    def test_on_sub_search_changed(self):
        mock_item = MagicMock()
        mock_item.data.return_value = 0
        self.host.sub_channel_list.count.return_value = 1
        self.host.sub_channel_list.item.return_value = mock_item
        self.host._sub_channels = [{'name': 'ch1', 'url': 'http://x.com', 'group': 'g1'}]
        self.host._on_sub_search_changed('ch1')

    def test_on_sub_channel_context_menu(self):
        self.host._on_sub_channel_context_menu(MagicMock())
        self.host.favorites_ctrl.show_channel_list_context_menu.assert_called_once()

    def test_on_local_channel_context_menu(self):
        self.host._on_local_channel_context_menu(MagicMock())
        self.host.favorites_ctrl.show_channel_list_context_menu.assert_called_once()

    def test_update_channel_info_on_selection(self):
        self.host.update_channel_info_on_selection()
        self.host.channel_ctrl.update_channel_info_on_selection.assert_called_once()

    def test_load_last_channel(self):
        self.host.config.load_last_channel.return_value = {'name': 'ch1', 'index': 0}
        self.host._load_last_channel()
        assert self.host._pending_last_channel is not None

    def test_load_last_channel_empty(self):
        self.host.config.load_last_channel.return_value = {}
        self.host._load_last_channel()
        assert self.host._pending_last_channel is None

    def test_select_channel_by_index_negative(self):
        self.host.select_channel_by_index(-1)
        # should return without error

    def test_switch_to_previous_channel_none(self):
        self.host.switch_to_previous_channel()
        # should return without error


class TestSettingsMixin:
    def setup_method(self):
        self.host = _SettingsTestHost()
        self.host.settings_ops = MagicMock()
        self.host.status_bar = MagicMock()
        self.host.player_controller = MagicMock()
        self.host.player_controller.is_playing = False
        self.host.play_state = MagicMock()
        self.host.play_state.is_catchup_or_timeshift = False

    def test_set_language(self):
        self.host.set_language('en')
        self.host.settings_ops.set_language.assert_called_once_with('en')

    def test_set_theme(self):
        self.host.set_theme('dark')
        self.host.settings_ops.set_theme.assert_called_once_with('dark')

    def test_set_color_mode(self):
        self.host.set_color_mode('dark')
        self.host.settings_ops.set_color_mode.assert_called_once_with('dark')

    def test_set_visual_style(self):
        self.host.set_visual_style('modern')
        self.host.settings_ops.set_visual_style.assert_called_once_with('modern')

    def test_show_about(self):
        self.host.show_about()
        self.host.settings_ops.show_about.assert_called_once()

    def test_player_settings(self):
        self.host.player_settings()
        self.host.settings_ops.player_settings.assert_called_once()

    def test_cancel_source_timeout(self):
        self.host._source_timeout_timer = MagicMock()
        self.host._cancel_source_timeout()
        self.host._source_timeout_timer.stop.assert_called_once()

    def test_cancel_source_timeout_no_timer(self):
        self.host._cancel_source_timeout()

    def test_on_source_timeout_not_playing(self):
        self.host._on_source_timeout({'name': 'ch1'})


class TestWindowMixin:
    def setup_method(self):
        self.host = _WindowTestHost()
        self.host.event_handler = MagicMock()
        self.host.video_frame = None
        self.host.status_bar = MagicMock()
        self.host.is_fullscreen = False
        self.host.fullscreen_button = MagicMock()
        self.host.fullscreen_button.isCheckable.return_value = False
        self.host.panel_vis = MagicMock()
        self.host.language_manager = MagicMock()
        self.host.language_manager.tr = lambda k, d='': d
        self.host.config = MagicMock()
        self.host.config_manager = MagicMock()
        self.host._is_hidden_to_tray = False
        self.host._force_quit = False
        self.host._is_local_file = MagicMock(return_value=False)

    def test_event_filter(self):
        self.host.eventFilter(MagicMock(), MagicMock())
        self.host.event_handler.eventFilter.assert_called_once()

    def test_update_floating_position_no_frame(self):
        self.host.update_floating_position()

    def test_refresh_ui(self):
        self.host.populate_channel_list = MagicMock()
        self.host.populate_epg_list = MagicMock()
        self.host.refresh_ui()
        self.host.populate_channel_list.assert_called_once()
        self.host.populate_epg_list.assert_called_once()

    def test_reset_layout(self):
        self.host.panel_vis.reset = MagicMock()
        self.host._sync_panel_actions = MagicMock()
        self.host.resize = MagicMock()
        self.host.reset_layout()
        self.host.panel_vis.reset.assert_called_once()

    def test_show_event(self):
        self.host._fix_win32_drag_drop = MagicMock()
        self.host.showEvent(MagicMock())
        self.host.event_handler.showEvent.assert_called_once()

    def test_change_event(self):
        self.host.changeEvent(MagicMock())
        self.host.event_handler.changeEvent.assert_called_once()

    def test_move_event(self):
        self.host.moveEvent(MagicMock())
        self.host.event_handler.moveEvent.assert_called_once()

    def test_resize_event(self):
        self.host.resizeEvent(MagicMock())
        self.host.event_handler.resizeEvent.assert_called_once()

    def test_close_event_hidden_to_tray(self):
        self.host._is_hidden_to_tray = True
        event = MagicMock()
        self.host.closeEvent(event)
        self.host.event_handler.closeEvent.assert_called_once()

    def test_close_event_force_quit(self):
        self.host._force_quit = True
        event = MagicMock()
        with patch('server.app.stop_server'):
            self.host.closeEvent(event)

    def test_close_event_exit_action(self):
        self.host.config.load_close_behavior.return_value = 'exit'
        event = MagicMock()
        with patch('server.app.stop_server') as mock_stop:
            self.host.closeEvent(event)
        mock_stop.assert_called_once()
        self.host.event_handler.closeEvent.assert_called_once()
