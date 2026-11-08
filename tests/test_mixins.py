import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from PySide6.QtWidgets import QListWidget  # noqa: E402

from mixins.server_mixin import ServerMixin  # noqa: E402
from mixins.tray_mixin import TrayMixin  # noqa: E402
from mixins.update_mixin import UpdateMixin  # noqa: E402
from mixins.thumbnail_mixin import ThumbnailMixin  # noqa: E402
from mixins.file_ops_mixin import FileOpsMixin  # noqa: E402
from mixins.panel_mixin import PanelMixin  # noqa: E402
from mixins.progress_mixin import ProgressMixin  # noqa: E402
from mixins.playback_mixin import PlaybackMixin  # noqa: E402
from mixins.epg_mixin import EpgMixin  # noqa: E402
from tests.conftest import MockMainWindow  # noqa: E402


class _ServerTestHost(MockMainWindow, ServerMixin):
    pass


class _TrayTestHost(MockMainWindow, TrayMixin):
    pass


class _UpdateTestHost(MockMainWindow, UpdateMixin):
    pass


class _ThumbnailTestHost(MockMainWindow, ThumbnailMixin):
    pass


class _FileOpsTestHost(MockMainWindow, FileOpsMixin):
    pass


class _PanelTestHost(MockMainWindow, PanelMixin):
    pass


class _ProgressTestHost(MockMainWindow, ProgressMixin):
    pass


class _PlaybackTestHost(MockMainWindow, PlaybackMixin):
    pass


class _EpgTestHost(MockMainWindow, EpgMixin):
    pass


class TestServerMixin:
    def setup_method(self):
        self.host = _ServerTestHost()

    @patch('mixins.server_mixin.logger')
    def test_auto_start_server_disabled(self, mock_logger):
        self.host.config.load_server_settings.return_value = {'auto_start': False}
        with patch('server.app.set_main_window') as mock_set, \
             patch('server.app.start_server') as mock_start:
            self.host._auto_start_server()
            mock_set.assert_called_once_with(self.host)
            mock_start.assert_not_called()

    @patch('mixins.server_mixin.logger')
    def test_auto_start_server_default_off_when_key_missing(self, mock_logger):
        """Settings 里没有 auto_start 键（新用户）时不得启动服务，且需记日志。"""
        self.host.config.load_server_settings.return_value = {}
        with patch('server.app.set_main_window'), \
             patch('server.app.start_server') as mock_start:
            self.host._auto_start_server()
            mock_start.assert_not_called()
        mock_logger.info.assert_called()

    @patch('mixins.server_mixin.logger')
    def test_auto_start_server_syncs_menu_action(self, mock_logger):
        """按用户设置启动后，菜单项文案需与实际运行状态一致。"""
        self.host.config.load_server_settings.return_value = {
            'auto_start': True, 'port': 9090, 'host': '0.0.0.0'
        }
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        with patch('server.app.set_main_window'), \
             patch('server.app.start_server'), \
             patch('server.app.get_server', return_value=mock_server), \
             patch('server.routes.get_auth_token', return_value='tok'):
            self.host._auto_start_server()
        self.host._server_action.setText.assert_called_once()

    @patch('mixins.server_mixin.logger')
    def test_auto_start_server_enabled(self, mock_logger):
        self.host.config.load_server_settings.return_value = {
            'auto_start': True, 'port': 9090, 'host': '0.0.0.0'
        }
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        with patch('server.app.set_main_window'), \
             patch('server.app.start_server') as mock_start, \
             patch('server.app.get_server', return_value=mock_server):
            self.host._auto_start_server()
            mock_start.assert_called_once_with(host='0.0.0.0', port=9090)

    @patch('mixins.server_mixin.logger')
    def test_auto_start_server_exception(self, mock_logger):
        self.host.config.load_server_settings.side_effect = Exception("test error")
        self.host._auto_start_server()
        mock_logger.error.assert_called_once()

    @patch('mixins.server_mixin.logger')
    def test_toggle_server_running(self, mock_logger):
        mock_server = MagicMock()
        mock_server.is_running.return_value = True
        with patch('server.app.set_main_window'), \
             patch('server.app.get_server', return_value=mock_server), \
             patch('server.app.stop_server') as mock_stop:
            self.host._toggle_server()
            mock_stop.assert_called_once()
            self.host._server_action.setText.assert_called_once()

    @patch('mixins.server_mixin.logger')
    def test_toggle_server_not_running(self, mock_logger):
        mock_server = MagicMock()
        mock_server.is_running.return_value = False
        self.host.config.load_server_settings.return_value = {
            'port': 8080, 'host': '0.0.0.0'
        }
        with patch('server.app.set_main_window'), \
             patch('server.app.get_server', return_value=mock_server), \
             patch('server.app.start_server') as mock_start:
            self.host._toggle_server()
            mock_start.assert_called_once()

    @patch('mixins.server_mixin.logger')
    def test_open_server_api(self, mock_logger):
        mock_server = MagicMock()
        mock_server.port = 8080
        mock_server.is_running.return_value = True
        with patch('server.app.get_server', return_value=mock_server), \
             patch('server.routes.get_auth_token', return_value='tok123'), \
             patch('webbrowser.open') as mock_open:
            self.host._open_server_api()
            mock_open.assert_called_once_with('http://localhost:8080/?token=tok123')

    @patch('mixins.server_mixin.logger')
    def test_open_server_api_when_not_running(self, mock_logger):
        """服务默认关闭时打开 API 只提示用户开启，不得打开无效链接。"""
        mock_server = MagicMock()
        mock_server.is_running.return_value = False
        with patch('server.app.get_server', return_value=mock_server), \
             patch('webbrowser.open') as mock_open:
            self.host._open_server_api()
            mock_open.assert_not_called()
        self.host.status_bar.showMessage.assert_called_once()

    @patch('mixins.server_mixin.logger')
    def test_open_server_api_exception(self, mock_logger):
        with patch('server.app.get_server', side_effect=Exception("test")):
            self.host._open_server_api()
            mock_logger.error.assert_called_once()


class TestTrayMixin:
    def setup_method(self):
        self.host = _TrayTestHost()

    def test_tray_show_window(self):
        self.host._is_hidden_to_tray = True
        self.host._tray_hidden_docks = []
        with patch.object(self.host, 'show'), \
             patch.object(self.host, 'activateWindow'), \
             patch.object(self.host, 'raise_'):
            self.host._tray_show_window()
            assert self.host._is_hidden_to_tray is False

    def test_tray_quit(self):
        self.host._is_hidden_to_tray = True
        with patch.object(self.host, 'close'):
            self.host._tray_quit()
            assert self.host._force_quit is True
            assert self.host._is_hidden_to_tray is False

    def test_do_close_minimize_tray_not_playing(self):
        self.host.player_controller.is_playing = False
        self.host._tray_hidden_docks = []
        with patch.object(self.host, 'hide'):
            self.host._do_close_minimize_tray()
            assert self.host._is_hidden_to_tray is True
            assert self.host._was_playing_before_tray is False

    def test_do_close_minimize_tray_playing(self):
        self.host.player_controller.is_playing = True
        self.host.player_controller.is_paused = False
        self.host._tray_hidden_docks = []
        with patch.object(self.host, 'hide'):
            self.host._do_close_minimize_tray()
            assert self.host._was_playing_before_tray is True

    def test_do_close_minimize_tray_hides_docks(self):
        self.host.player_controller.is_playing = False
        mock_dock = MagicMock()
        mock_dock.isVisible.return_value = True
        self.host.epg_dock = mock_dock
        self.host.playlist_dock = MagicMock()
        self.host.playlist_dock.isVisible.return_value = False
        self.host.floating_dock = MagicMock()
        self.host.floating_dock.isVisible.return_value = False
        with patch.object(self.host, 'hide'):
            self.host._do_close_minimize_tray()
            assert 'epg_dock' in self.host._tray_hidden_docks
            assert len(self.host._tray_hidden_docks) == 1


class TestUpdateMixin:
    def setup_method(self):
        self.host = _UpdateTestHost()

    def test_do_check_for_updates_async(self):
        self.host._do_check_for_updates_async()
        self.host.update_ctrl.check_for_updates.assert_called_once()

    def test_on_update_found(self):
        self.host._on_update_found('1.2.0', '1.1.0', 'https://example.com/download')
        self.host.update_ctrl._on_update_found.assert_called_once_with(
            '1.2.0', '1.1.0', 'https://example.com/download'
        )

    def test_on_update_check_completed(self):
        self.host._on_update_check_completed(True, 'OK')
        self.host.update_ctrl._on_update_check_completed.assert_called_once_with(True, 'OK')


class TestThumbnailMixin:
    def setup_method(self):
        self.host = _ThumbnailTestHost()

    def test_on_logo_cache_loaded_delegates(self):
        self.host._on_logo_cache_loaded('http://x.com/logo.png', MagicMock())
        self.host.ui_ctrl._on_logo_cache_loaded.assert_called_once()

    def test_on_thumbnail_ready_calls_update(self):
        with patch.object(self.host, '_update_grid_thumbnail') as mock_update:
            self.host._on_thumbnail_ready('ch1', 'http://x.com/stream.m3u8')
            mock_update.assert_called_once_with('http://x.com/stream.m3u8')

    def test_on_player_thumbnail_captured_calls_update(self):
        with patch.object(self.host, '_update_grid_thumbnail') as mock_update:
            self.host._on_player_thumbnail_captured('http://x.com/stream.m3u8')
            mock_update.assert_called_once_with('http://x.com/stream.m3u8')

    @patch('services.thumbnail_service.get_thumbnail_path', return_value=None)
    def test_update_grid_thumbnail_no_path(self, mock_get_path):
        self.host._update_grid_thumbnail('http://x.com/stream.m3u8')
        mock_get_path.assert_called_once_with('http://x.com/stream.m3u8')

    @patch('mixins.thumbnail_mixin.QIcon')
    @patch('mixins.thumbnail_mixin.QPixmap')
    @patch('services.thumbnail_service.get_thumbnail_path', return_value='/tmp/thumb.jpg')
    def test_update_grid_thumbnail_with_match(self, mock_get_path, mock_pixmap_cls, mock_qicon):
        mock_item = MagicMock()
        mock_item.data.return_value = 0
        mock_list = MagicMock()
        mock_list.viewMode.return_value = QListWidget.ViewMode.IconMode
        mock_list.item.return_value = mock_item
        self.host.sub_channel_list = mock_list
        self.host._sub_channels = [{'url': 'http://x.com/stream.m3u8', 'name': 'ch1'}]
        self.host.local_channel_list = MagicMock()
        self.host.local_channel_list.viewMode.return_value = 0
        self.host._local_channels = []

        mock_px = MagicMock()
        mock_px.isNull.return_value = False
        mock_scaled = MagicMock()
        mock_px.scaled.return_value = mock_scaled
        mock_pixmap_cls.return_value = mock_px

        self.host._update_grid_thumbnail('http://x.com/stream.m3u8')
        mock_item.setIcon.assert_called_once()


class TestFileOpsMixin:
    def setup_method(self):
        self.host = _FileOpsTestHost()
        self.host.recent_menu = MagicMock()
        self.host.config.load_recent_files.return_value = []
        self.host.settings_ops = MagicMock()
        self.host.channel_model = MagicMock()
        self.host._local_channels = []
        self.host._local_channels_dirty = False
        self.host.playlist_tab = MagicMock()
        self.host.local_channel_list = MagicMock()
        self.host.local_group_combo = MagicMock()
        self.host.channel_name = MagicMock()
        self.host.status_bar = MagicMock()

    @patch('mixins.file_ops_mixin.QAction')
    def test_update_recent_files_menu_empty(self, mock_action_cls):
        self.host.config.load_recent_files.return_value = []
        self.host.update_recent_files_menu()
        self.host.recent_menu.clear.assert_called_once()

    @patch('mixins.file_ops_mixin.QAction')
    def test_update_recent_files_menu_with_files(self, mock_action_cls):
        self.host.config.load_recent_files.return_value = ['/a.m3u', '/b.m3u']
        self.host.update_recent_files_menu()
        self.host.recent_menu.clear.assert_called_once()

    def test_open_recent_file_delegates(self):
        self.host.open_recent_file('/test.m3u')
        self.host.settings_ops.open_recent_file.assert_called_once_with('/test.m3u')

    def test_open_playlist_delegates(self):
        self.host.open_playlist()
        self.host.settings_ops.open_playlist.assert_called_once()

    def test_open_stream_delegates(self):
        self.host._open_stream()
        self.host.settings_ops._open_stream.assert_called_once()

    def test_save_as_delegates(self):
        self.host.save_as()
        self.host.settings_ops.save_as.assert_called_once()

    def test_show_usage_instructions_delegates(self):
        self.host.show_usage_instructions()
        self.host.settings_ops.show_usage_instructions.assert_called_once()

    def test_save_window_layout_delegates(self):
        self.host.save_window_layout()
        self.host.settings_ops.save_window_layout.assert_called_once()

    def test_create_local_video_channel(self):
        ch = self.host._create_local_video_channel('/videos/test.mp4')
        assert ch['name'] == 'test'
        assert ch['url'] == '/videos/test.mp4'

    @patch('mixins.file_ops_mixin.copy')
    def test_add_to_local_list(self, mock_copy):
        mock_copy.deepcopy.return_value = {'name': 'ch1', 'url': 'http://x.com'}
        self.host.local_channel_list.count.return_value = 1
        mock_item = MagicMock()
        mock_item.data.return_value = 0
        self.host.local_channel_list.item.return_value = mock_item
        self.host.local_group_combo.currentText.return_value = 'All'
        self.host._update_groups_for = MagicMock()
        self.host._populate_channel_list_for = MagicMock()
        self.host.update_channel_info_on_selection = MagicMock()
        self.host.play_channel = MagicMock()
        channel = {'name': 'ch1', 'url': 'http://x.com'}
        self.host._add_to_local_list(channel)
        assert len(self.host._local_channels) == 1
        assert self.host._local_channels_dirty is True


class TestPanelMixin:
    def setup_method(self):
        self.host = _PanelTestHost()
        # MockMainWindow 不是 QObject，真实 QTimer(self) 会失败；
        # 且魔改后的面板 mock 会让指针命中判断恒为真，导致走不到 auto_hide_all。
        self.host._is_pointer_on_floating_widgets = MagicMock(return_value=False)
        self.host.panel_vis = MagicMock()
        self.host.panel_vis.is_auto_hidden = False
        self.host.panel_vis.manually_hidden = False
        self.host.playlist_panel = MagicMock()
        self.host.floating_panel = MagicMock()
        self.host.epg_panel = MagicMock()
        self.host.is_fullscreen = False
        self.host._osd_visible = False
        self.host.pip_ctrl = MagicMock()
        self.host.pip_ctrl.is_active = False
        self.host.subscription_ctrl = MagicMock()
        self.host._epg_menu_action = MagicMock()
        self.host._playlist_menu_action = MagicMock()
        self.host._floating_menu_action = MagicMock()
        self.host._osd_menu_action = MagicMock()
        self.host._fullscreen_menu_action = MagicMock()
        self.host._pip_menu_action = MagicMock()

    def test_toggle_playlist(self):
        self.host.playlist_panel.isVisible.return_value = False
        self.host.toggle_playlist()
        assert self.host.playlist_visible is True

    def test_toggle_playlist_checked(self):
        self.host.toggle_playlist(checked=True)
        assert self.host.playlist_visible is True

    def test_toggle_floating_panel(self):
        self.host.floating_panel.isVisible.return_value = False
        self.host.toggle_floating_panel()
        assert self.host.floating_panel_visible is True

    def test_toggle_hide_floating_manually_hidden_restores(self):
        self.host.panel_vis.manually_hidden = True
        self.host._is_local_file = MagicMock(return_value=False)
        self.host.toggle_hide_floating()
        self.host.panel_vis.restore_from_manual_hide.assert_called_once()

    def test_auto_hide_panels_not_fullscreen(self):
        self.host.is_fullscreen = False
        self.host._auto_hide_panels()
        self.host.panel_vis.auto_hide_all.assert_not_called()

    def test_auto_hide_panels_fullscreen(self):
        self.host.is_fullscreen = True
        self.host.panel_vis.is_auto_hide_visible = True
        self.host._auto_hide_panels()
        self.host.panel_vis.auto_hide_all.assert_called_once()

    def test_stop_auto_hide_timer(self):
        self.host._auto_hide_timer = MagicMock()
        self.host._stop_auto_hide_timer()
        self.host._auto_hide_timer.stop.assert_called_once()

    def test_stop_auto_hide_timer_no_timer(self):
        self.host._stop_auto_hide_timer()

    def test_sync_panel_actions(self):
        self.host._sync_panel_actions()
        self.host._epg_menu_action.blockSignals.assert_called()

    def test_handle_playlist_subscription_delegates(self):
        self.host._handle_playlist_subscription(True, 'http://x.com/m3u', 0)
        self.host.subscription_ctrl.handle_playlist_subscription.assert_called_once()

    def test_reload_subscription(self):
        self.host.reload_subscription()
        self.host.subscription_ctrl.reload_subscription.assert_called_once()

    def test_start_subscription_timers(self):
        self.host.start_subscription_timers()
        self.host.subscription_ctrl.start_subscription_timers.assert_called_once()

    def test_update_playlist_subscription(self):
        self.host.update_playlist_subscription(source_index=0)
        self.host.subscription_ctrl.update_playlist_subscription.assert_called_once_with(0)

    def test_reapply_side_panel_styles(self):
        self.host.ui_ctrl = MagicMock()
        self.host._reapply_side_panel_styles()
        self.host.ui_ctrl._reapply_side_panel_styles.assert_called_once()

    def test_reapply_floating_panel_styles(self):
        self.host.ui_ctrl = MagicMock()
        self.host._reapply_floating_panel_styles()
        self.host.ui_ctrl._reapply_floating_panel_styles.assert_called_once()


class TestProgressMixin:
    def setup_method(self):
        self.host = _ProgressTestHost()
        self.host.program_progress = MagicMock()
        self.host.program_progress.isSliderDown.return_value = False
        self.host.program_progress.maximum.return_value = 3600
        self.host.program_progress.value.return_value = 100
        self.host._progress_total_seconds = 3600
        self.host._progress_time_mode = 'hour'
        self.host._progress_program_start = None
        self.host._disable_progress_auto_update = False
        self.host.play_state = MagicMock()
        self.host.play_state.is_catchup_or_timeshift = False
        self.host.player_controller = MagicMock()
        self.host.current_channel = None
        self.host._live_timeshift_seconds = 0
        self.host._stop_auto_hide_timer = MagicMock()
        self.host._restart_auto_hide_timer = MagicMock()
        self.host.is_fullscreen = False
        self.host.catchup_ctrl = MagicMock()
        self.host.SLIDER_DEBOUNCE_MS = 100

    def test_set_progress_range(self):
        self.host._set_progress_range(7200)
        assert self.host._progress_total_seconds == 7200
        self.host.program_progress.setRange.assert_called_once_with(0, 7200)

    def test_set_progress_value(self):
        self.host._set_progress_value(100)
        self.host.program_progress.setValue.assert_called_once_with(100)

    def test_set_progress_value_slider_down(self):
        self.host.program_progress.isSliderDown.return_value = True
        self.host._set_progress_value(100)
        self.host.program_progress.setValue.assert_not_called()

    def test_get_progress_seconds(self):
        result = self.host._get_progress_seconds()
        assert result == 100

    def test_format_seconds_to_time(self):
        assert self.host._format_seconds_to_time(3661) == "1:01:01"
        assert self.host._format_seconds_to_time(125) == "2:05"
        assert self.host._format_seconds_to_time(0) == "0:00"

    def test_seek_vod(self):
        self.host._seek_vod(120)
        self.host.player_controller.seek_absolute.assert_called_once_with(120.0)

    def test_seek_catchup(self):
        self.host._seek_catchup(60)
        self.host.catchup_ctrl.seek_catchup.assert_called_once_with(60)

    def test_on_progress_slider_pressed(self):
        self.host._on_progress_slider_pressed()
        assert self.host._disable_progress_auto_update is True
        self.host._stop_auto_hide_timer.assert_called_once()

    def test_start_live_timeshift_from_progress(self):
        self.host._start_live_timeshift_from_progress(300, 'catchup://x')
        self.host.catchup_ctrl.start_live_timeshift_from_progress.assert_called_once()


class TestPlaybackMixin:
    def setup_method(self):
        self.host = _PlaybackTestHost()
        self.host.playback_ctrl = MagicMock()
        self.host.playback_ctrl.is_muted_state = False
        self.host.ui_ctrl = MagicMock()
        self.host.favorites_ctrl = MagicMock()
        self.host.player_controller = MagicMock()
        self.host.language_manager.tr = lambda k, d='': d
        self.host._suppress_volume_osd = False
        self.host._osd_visible = False
        self.host.volume_slider = MagicMock()
        self.host.volume_slider.value.return_value = 50
        self.host.current_channel = None
        self.host.play_state = MagicMock()
        self.host.play_state.is_catchup_or_timeshift = False
        self.host.RECONNECT_DELAY_MS = 2000
        self.host.status_bar = MagicMock()

    def test_toggle_play(self):
        self.host.toggle_play()
        self.host.playback_ctrl.toggle_play.assert_called_once()

    def test_stop_playback(self):
        self.host.stop_playback()
        self.host.playback_ctrl.stop_playback.assert_called_once()

    def test_set_volume(self):
        self.host.set_volume(80)
        self.host.playback_ctrl.set_volume.assert_called_once_with(80)

    def test_toggle_mute(self):
        self.host.toggle_mute()
        self.host.playback_ctrl.toggle_mute.assert_called_once()

    def test_show_osd_feedback(self):
        self.host._show_osd_feedback("test")
        self.host.player_controller.show_osd.assert_called_once_with("test", 2000)

    def test_play_channel(self):
        self.host.playback_ctrl._is_switching = False
        ch = {'name': 'ch1', 'url': 'http://x.com'}
        self.host.play_channel(ch)
        self.host.playback_ctrl.play_channel.assert_called_once_with(ch)

    def test_play_channel_during_switching_delegates_to_controller(self):
        # 入口不再拦截切换窗口内的请求，统一交给控制器排队（最后一次请求生效）
        self.host.playback_ctrl._is_switching = True
        ch = {'name': 'ch1', 'url': 'http://x.com'}
        self.host.play_channel(ch)
        self.host.playback_ctrl.play_channel.assert_called_once_with(ch)

    def test_on_play_error(self):
        self.host.on_play_error("test error")
        self.host.status_bar.showMessage.assert_called()

    def test_on_live_media_info_updated(self):
        self.host.on_live_media_info_updated({})
        self.host.ui_ctrl.on_live_media_info_updated.assert_called_once()

    def test_update_media_info(self):
        self.host.update_media_info()
        self.host.ui_ctrl.update_media_info.assert_called_once()

    def test_update_floating_panel_info(self):
        self.host.update_floating_panel_info()
        self.host.ui_ctrl.update_floating_panel_info.assert_called_once()

    def test_toggle_osd(self):
        self.host.toggle_osd()
        self.host.ui_ctrl.toggle_osd.assert_called_once()


class TestEpgMixin:
    def setup_method(self):
        self.host = _EpgTestHost()
        self.host.epg_ctrl = MagicMock()
        self.host.catchup_ctrl = MagicMock()
        self.host.epg_reminder_ctrl = MagicMock()
        self.host.current_channel = None
        self.host.panel_vis = MagicMock()
        self.host.panel_vis.is_auto_hidden = False
        self.host.epg_panel = MagicMock()

    def test_populate_epg_list(self):
        self.host.populate_epg_list()
        self.host.epg_ctrl.populate_epg_list.assert_called_once()

    def test_on_epg_item_clicked(self):
        item = MagicMock()
        self.host.on_epg_item_clicked(item)
        self.host.epg_ctrl.on_epg_item_clicked.assert_called_once_with(item)

    def test_start_catchup(self):
        self.host.start_catchup({})
        self.host.catchup_ctrl.start_catchup.assert_called_once()

    def test_exit_catchup(self):
        self.host.exit_catchup()
        self.host.catchup_ctrl.exit_catchup.assert_called_once()

    def test_add_exit_catchup_button(self):
        self.host.add_exit_catchup_button()
        self.host.catchup_ctrl.add_exit_catchup_button.assert_called_once()

    def test_show_exit_timeshift_button(self):
        self.host._show_exit_timeshift_button()
        self.host.catchup_ctrl.show_exit_timeshift_button.assert_called_once()

    def test_get_epg_match_params_no_channel(self):
        result = self.host._get_epg_match_params()
        assert result == ('', '', '', '')

    def test_get_epg_match_params_with_channel(self):
        self.host.current_channel = {
            'name': 'ch1', 'tvg_id': 'id1', '_all_tags': {'tvg-name': 'tn1'},
            '_raw_extinf': '#EXTINF:1,Test Channel'
        }
        result = self.host._get_epg_match_params()
        assert result[0] == 'ch1'
        assert result[1] == 'id1'
        assert result[2] == 'tn1'

    def test_is_local_file_none(self):
        assert self.host._is_local_file() is False

    def test_is_local_file_http(self):
        self.host.current_channel = {'url': 'http://x.com/stream.m3u8'}
        assert self.host._is_local_file() is False

    def test_is_local_file_local(self):
        self.host.current_channel = {'url': '/videos/test.mp4'}
        assert self.host._is_local_file() is True

    def test_is_local_file_file_protocol(self):
        self.host.current_channel = {'url': 'file:///videos/test.mp4'}
        assert self.host._is_local_file() is True

    def test_update_epg_date_display(self):
        self.host.update_epg_date_display()
        self.host.epg_ctrl.update_epg_date_display.assert_called_once()
