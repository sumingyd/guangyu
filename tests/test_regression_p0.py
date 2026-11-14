"""P0 回归测试 - 验证关键修复未被破坏"""
import sys
import os
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from tests.conftest import MockMainWindow


class TestP0_3_PipPixmapCache:
    """P0-3: PiP 按钮 pixmap 缓存 - paint 事件不应重复加载 QPixmap"""

    def test_pixmap_cached_at_init(self):
        """PipButton 初始化时加载 pixmap 并缓存到 _pixmap_cache"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap), \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            assert btn._widget._pixmap_cache is not None

    def test_paint_event_uses_cache(self):
        """paint_event 使用缓存 pixmap，不调用 QPixmap(path)"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.width.return_value = 22
        mock_pixmap.height.return_value = 22
        mock_pixmap.scaled.return_value = mock_pixmap

        mock_widget = MagicMock()
        mock_widget._pixmap_cache = mock_pixmap
        mock_widget._hovered = False
        mock_widget._size = 40

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            btn._widget._pixmap_cache = mock_pixmap
            btn._widget._hovered = False
            btn._widget._size = 40

            with patch('controllers.pip_controller.QPainter') as mock_painter:
                painter_inst = mock_painter.return_value
                btn._widget.paintEvent(MagicMock())

            # QPixmap should not be called during paint (only at init)
            init_calls = [c for c in mock_qpixmap.call_args_list
                          if c != call('/fake/icon.png')]
            # The key assertion: no new QPixmap(path) calls during paint
            # (init already consumed the first call)
            paint_phase_qpixmap_calls = mock_qpixmap.call_count - 1
            assert paint_phase_qpixmap_calls == 0, \
                f"paintEvent should not call QPixmap, got {paint_phase_qpixmap_calls} extra calls"

    def test_set_icon_same_name_no_reload(self):
        """set_icon 同名不重新加载 pixmap"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            calls_before = mock_qpixmap.call_count

            btn.set_icon('close')
            assert mock_qpixmap.call_count == calls_before, \
                "set_icon with same name should not reload pixmap"

    def test_set_icon_different_name_reloads(self):
        """set_icon 不同名重新加载 pixmap"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            calls_before = mock_qpixmap.call_count

            btn.set_icon('restore')
            assert mock_qpixmap.call_count > calls_before, \
                "set_icon with different name should reload pixmap"


class TestP0_1_VolumeShortcut:
    """P0-1: 音量快捷键委托给 media_ctrl（非 update_ctrl）"""

    def test_adjust_volume_delegates_to_media_ctrl(self):
        """_adjust_volume 调用 media_ctrl._set_volume"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 50

        handler._adjust_volume(10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(60)

    def test_adjust_volume_clamps_to_0_100(self):
        """_adjust_volume 限制音量在 0-100 范围"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 95

        handler._adjust_volume(10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(100)

    def test_adjust_volume_clamps_to_zero(self):
        """_adjust_volume 限制音量下限为 0"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 5

        handler._adjust_volume(-10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(0)

    def test_adjust_volume_no_media_ctrl_no_crash(self):
        """无 media_ctrl 时不崩溃"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = None
        handler._adjust_volume(10)


class TestP0_2_DeadButtonCleanup:
    """P0-2: 控制面板不创建已删除的死按钮"""

    def test_no_audio_track_button(self):
        """不创建 audio_track_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'audio_track_button'), \
            "audio_track_button should not be created (dead button removed in T1.2)"

    def test_no_sub_track_button(self):
        """不创建 sub_track_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'sub_track_button'), \
            "sub_track_button should not be created (dead button removed in T1.2)"

    def test_no_pip_button(self):
        """不创建 pip_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'pip_button'), \
            "pip_button should not be created (dead button removed in T1.2)"


class TestBatch2PlaybackChain:
    """批次二 PC 播放链修复的回归断言。"""

    def test_set_track_no_uses_string_property(self):
        """关闭字幕走字符串属性，不能因 int('no') 抛异常而被吞掉"""
        from services.mpv_playback import MpvPlayback
        facade = MagicMock()
        facade._terminated = False
        facade.mpv_handle = object()
        facade.get_current_track.return_value = None
        facade._set_mpv_string.return_value = 0

        playback = MpvPlayback(facade)
        assert playback.set_track('sub', 'no') is True
        facade._set_mpv_string.assert_called_once_with('sid', 'no')

    def test_get_current_track_uses_valid_mpv_properties(self):
        """mpv 没有 audio-track/sub-track 属性，读取必须走 aid/sid/vid"""
        from services.mpv_playback import MpvPlayback
        facade = MagicMock()
        facade._terminated = False
        facade.mpv_handle = object()
        facade._get_mpv_property_int.return_value = 2

        playback = MpvPlayback(facade)
        assert playback.get_current_track('audio') == 2
        assert playback.get_current_track('sub') == 2
        assert playback.get_current_track('video') == 2
        assert [c.args[0] for c in facade._get_mpv_property_int.call_args_list] == ['aid', 'sid', 'vid']

    def test_set_track_numeric_uses_valid_property(self):
        """数字轨号也写 aid/sid，而不是不存在的 audio-track/sub-track"""
        from services import mpv_playback
        facade = MagicMock()
        facade._terminated = False
        facade.mpv_handle = object()
        facade.get_current_track.return_value = 1

        playback = mpv_playback.MpvPlayback(facade)
        original = mpv_playback._mpv_set_property_int64
        calls = []
        mpv_playback._mpv_set_property_int64 = lambda handle, prop, value: calls.append((prop, value)) or 0
        try:
            assert playback.set_track('audio', 2) is True
            assert playback.set_track('sub', 2) is True
        finally:
            mpv_playback._mpv_set_property_int64 = original
        assert calls == [('aid', 2), ('sid', 2)]

    def test_source_timeout_uses_network_timeout(self):
        """看门狗超时取真实网络超时配置"""
        from controllers.playback_controller import PlaybackController
        window = MockMainWindow()
        window.player_controller._playback_settings = {'network_timeout_sec': 30}

        ctrl = object.__new__(PlaybackController)
        ctrl.window = window
        assert ctrl._source_timeout_ms() == 30000

    def test_source_timeout_falls_back_to_default(self):
        """缺少网络超时配置时回退默认值"""
        from controllers.playback_controller import PlaybackController
        window = MockMainWindow()
        window.player_controller._playback_settings = {}

        ctrl = object.__new__(PlaybackController)
        ctrl.window = window
        assert ctrl._source_timeout_ms() == PlaybackController.SOURCE_TIMEOUT_MS

    def test_subtitle_redownload_overwrites_existing_file(self, tmp_path):
        """重复下载同一字幕时必须覆盖旧文件，且不残留临时文件"""
        from services import subtitle_download_service as module

        payload = b'1\n00:00:01,000 --> 00:00:02,000\nhello\n'
        final_path = tmp_path / 'movie.srt'
        final_path.write_bytes(b'old subtitle')

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return payload

        with patch.object(module, '_urlopen', return_value=_Response()):
            service = module.SubtitleDownloadService()
            result = service._download_opensubtitles(
                'http://example.com/sub.gz', str(tmp_path), 'movie.srt')

        assert result == str(final_path)
        assert final_path.read_bytes() == payload
        assert not (tmp_path / 'movie.srt.gz').exists()
class TestEpgReminderBoundary:
    """EPG 提醒边界：已开播节目不应假装设置成功，临近开播应正常触发。"""

    def _svc(self):
        from services.epg_reminder_service import EpgReminderService
        return EpgReminderService(None)

    def test_reject_already_started_program(self):
        from datetime import datetime, timedelta
        svc = self._svc()
        now = datetime.now()
        added = svc.add_reminder(
            'CCTV1', '新闻联播',
            (now - timedelta(minutes=1)).isoformat(),
            (now + timedelta(minutes=29)).isoformat())
        assert added is False
        assert svc.get_reminders() == []

    def test_accept_upcoming_program(self):
        from datetime import datetime, timedelta
        svc = self._svc()
        now = datetime.now()
        added = svc.add_reminder(
            'CCTV1', '新闻联播',
            (now + timedelta(minutes=5)).isoformat(),
            (now + timedelta(minutes=35)).isoformat())
        assert added is True
        assert len(svc.get_reminders()) == 1

    def test_notify_within_early_window(self):
        from datetime import datetime, timedelta
        svc = self._svc()
        now = datetime.now()
        svc.add_reminder(
            'CCTV1', '新闻联播',
            (now + timedelta(seconds=30)).isoformat(),
            (now + timedelta(minutes=30)).isoformat())
        fired = []
        svc.set_callback(lambda r: fired.append(r))
        svc._check_reminders()
        assert len(fired) == 1
        assert fired[0]['program_title'] == '新闻联播'

class TestChannelSettingsPersistence:
    """按频道（URL）保存的播放设置：换台前必须落盘，删除频道后要清掉。"""

    class _Sig:
        def connect(self, _fn):
            pass

    class _PC:
        def __init__(self):
            self.file_loaded = TestChannelSettingsPersistence._Sig()
            self.local_file_position_to_save = TestChannelSettingsPersistence._Sig()
            self.about_to_stop = TestChannelSettingsPersistence._Sig()
            self.current_url = 'http://live.example/1.m3u8'
            self.is_playing = True

        def get_volume(self): return 40
        def get_mute(self): return False
        def get_aspect_ratio(self): return '16:9'
        def get_video_rotate(self): return 0
        def get_video_flip(self): return ''
        def get_sub_delay(self): return 0.0
        def get_audio_delay(self): return 0.0
        def get_current_track(self, kind):
            return {'sub': 1, 'audio': 2}.get(kind)

    def _window(self, tmp_path):
        from types import SimpleNamespace
        return SimpleNamespace(
            player_controller=self._PC(),
            config=SimpleNamespace(config_dir=str(tmp_path)),
            current_channel={'name': 'CCTV1', 'url': 'http://live.example/1.m3u8'},
        )

    def test_save_on_channel_switch(self, tmp_path):
        from controllers.playback_settings_controller import PlaybackSettingsController
        from core.playback_settings_store import PlaybackSettingsStore
        w = self._window(tmp_path)
        ctrl = PlaybackSettingsController(w)
        ctrl.save_current_settings()
        saved = PlaybackSettingsStore(str(tmp_path)).load_settings('http://live.example/1.m3u8')
        assert saved['volume'] == 40
        assert saved['aspect_ratio'] == '16:9'
        assert saved['audio_track'] == 2
        assert saved['sub_track'] == 1

    def test_apply_settings_restores_tracks_and_aspect(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from controllers.playback_settings_controller import PlaybackSettingsController
        from core.playback_settings_store import PlaybackSettingsStore
        url = 'http://live.example/1.m3u8'
        PlaybackSettingsStore(str(tmp_path)).save_settings(
            url, {'sub_track': 1, 'audio_track': 2, 'aspect_ratio': '4:3'})

        w = self._window(tmp_path)
        pc = w.player_controller
        for name in ('set_volume', 'set_mute', 'set_aspect_ratio', 'set_video_rotate',
                     'set_video_flip', 'set_sub_delay', 'set_audio_delay', 'set_track'):
            setattr(pc, name, MagicMock())
        ctrl = PlaybackSettingsController(w)
        ctrl._applied_url = url
        with patch('controllers.playback_settings_controller.QTimer.singleShot',
                   side_effect=lambda _ms, fn: fn()):
            ctrl._apply_settings()
        pc.set_aspect_ratio.assert_called_once_with('4:3')
        pc.set_track.assert_any_call('sub', 1)
        pc.set_track.assert_any_call('audio', 2)

    def test_switch_calls_save_before_play(self):
        from unittest.mock import MagicMock
        from controllers.playback_controller import PlaybackController
        w = MagicMock()
        w.play_state.is_catchup_or_timeshift = False
        ctrl = PlaybackController(w)
        ctrl._do_play_channel({'name': 'CCTV1', 'url': 'http://live.example/1.m3u8'})
        w.playback_settings_ctrl.save_current_settings.assert_called_once_with()

    def test_clear_on_channel_delete(self, tmp_path):
        from controllers.playback_settings_controller import PlaybackSettingsController
        from core.playback_settings_store import PlaybackSettingsStore
        store = PlaybackSettingsStore(str(tmp_path))
        store.save_settings('http://live.example/1.m3u8', {'volume': 30})
        w = self._window(tmp_path)
        ctrl = PlaybackSettingsController(w)
        ctrl.clear_settings_for_url('http://live.example/1.m3u8')
        assert PlaybackSettingsStore(str(tmp_path)).load_settings('http://live.example/1.m3u8') == {}

class TestSubscriptionDialogIsolation:
    """设置对话框内的订阅源增删改只改列表，点保存才落盘。"""

    @staticmethod
    def _ensure_app():
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def _make(self):
        from PySide6.QtWidgets import QLineEdit, QListWidget, QPushButton
        from controllers.subscription_ui_controller import SubscriptionUIController
        self._ensure_app()
        w = MagicMock()
        w.playlist_list_widget = QListWidget()
        w.playlist_new_url_edit = QLineEdit()
        w.playlist_new_name_edit = QLineEdit()
        w._playlist_add_btn = QPushButton()
        w._editing_playlist_index = -1
        w.language_manager = None
        return w, SubscriptionUIController(w)

    def test_add_source_does_not_write_config(self):
        from PySide6 import QtCore
        w, ctrl = self._make()
        w.playlist_new_url_edit.setText('http://127.0.0.1/a.m3u')
        with patch('core.subscription_manager.global_subscription_manager') as mgr:
            ctrl.add_or_update_playlist_source()
            mgr.add_playlist_source.assert_not_called()
            mgr._config.save_playlist_sources.assert_not_called()
        assert w.playlist_list_widget.count() == 1
        item = w.playlist_list_widget.item(0)
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        assert data['url'] == 'http://127.0.0.1/a.m3u'
        assert data['enabled'] is True
        assert '✓' in item.text()

    def test_remove_source_does_not_write_config(self):
        from PySide6 import QtCore
        from PySide6.QtWidgets import QListWidgetItem
        w, ctrl = self._make()
        for i in range(2):
            item = QListWidgetItem(f'S{i}')
            item.setData(QtCore.Qt.ItemDataRole.UserRole,
                         {'url': f'http://127.0.0.1/{i}.m3u', 'name': f'S{i}',
                          'enabled': i == 0})
            w.playlist_list_widget.addItem(item)
        w.playlist_list_widget.setCurrentRow(0)
        with patch('core.subscription_manager.global_subscription_manager') as mgr:
            ctrl.remove_selected_playlist_source()
            mgr.remove_playlist_source.assert_not_called()
        assert w.playlist_list_widget.count() == 1
        first = w.playlist_list_widget.item(0).data(QtCore.Qt.ItemDataRole.UserRole)
        assert first['enabled'] is True

    def test_save_reloads_when_url_changed_in_dialog(self):
        from PySide6 import QtCore
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        from controllers.settings_file_ops import SettingsFileOperations
        self._ensure_app()
        w = MagicMock()
        w.language_manager.tr = lambda k, d=None: d or k
        w.playlist_list_widget = QListWidget()
        item = QListWidgetItem('UiTest')
        item.setData(QtCore.Qt.ItemDataRole.UserRole,
                     {'url': 'http://new/a.m3u', 'name': 'UiTest', 'enabled': True})
        w.playlist_list_widget.addItem(item)
        w.epg_list_widget = QListWidget()

        dialog = MagicMock()
        dialog._old_playlist_sources = [
            {'url': 'http://old/a.m3u', 'name': 'UiTest', 'enabled': True}]
        dialog._old_epg_sources = []
        dialog._old_active_playlist_index = 0

        ops = SettingsFileOperations(w)
        with patch.object(ops, '_reload_playlist_async') as reload_mock, \
             patch.object(ops, '_save_intervals'), \
             patch.object(ops, '_save_close_behavior'), \
             patch.object(ops, '_save_screensaver_settings'), \
             patch.object(ops, '_apply_playback_settings'), \
             patch('controllers.settings_file_ops.global_subscription_manager'):
            ops._save_and_close_settings(dialog)
        reload_mock.assert_called_once()


class TestServerSettingsInNetworkTab:
    """HTTP 服务设置并入网络页签后，保存语义与独立对话框保持一致。"""

    @staticmethod
    def _ensure_app():
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_save_persists_auto_start_enabled_port_host(self):
        from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QWidget
        from controllers.settings_file_ops import SettingsFileOperations

        self._ensure_app()
        w = MagicMock()
        w.language_manager = None
        dialog = QWidget()
        check = QCheckBox(dialog)
        check.setObjectName('server_auto_start_check')
        check.setChecked(True)
        spin = QSpinBox(dialog)
        spin.setObjectName('server_port_spin')
        spin.setRange(1024, 65535)
        spin.setValue(9091)
        combo = QComboBox(dialog)
        combo.setObjectName('server_host_combo')
        combo.addItem('0.0.0.0', '0.0.0.0')
        combo.addItem('127.0.0.1', '127.0.0.1')
        combo.setCurrentIndex(0)

        SettingsFileOperations(w)._save_server_settings(dialog)

        # enabled 与 auto_start 同值：与原独立对话框的保存逻辑一致
        w.config.save_server_settings.assert_called_once_with(
            enabled=True, port=9091, host='0.0.0.0', auto_start=True)


class TestReconnectTerminalStatusBar:
    """断流重连耗尽后，状态栏不能显示成用户主动“已暂停”。"""

    def _status_after_stop(self, exhausted):
        from controllers.playback_controller import PlaybackController
        w = MagicMock()
        w.language_manager.tr = lambda k, d=None: d if d is not None else k
        w.current_channel = {'name': 'live.ts', 'url': 'http://127.0.0.1:18091/live.ts'}
        w.play_state.is_idle = False
        w.play_state.is_catchup_or_timeshift = False
        pc = w.player_controller
        pc._reconnect_exhausted = exhausted
        pc.is_paused = False
        ctrl = PlaybackController(w)
        with patch('controllers.playback_controller.QIcon'), \
             patch('controllers.playback_controller.AppStyles.get_icon', return_value=None), \
             patch('controllers.playback_controller.AppStyles.play_icon_name', return_value='play'):
            ctrl.handle_play_state_change(False)
        return w.status_bar_show_message.call_args[0][0]

    def test_exhausted_shows_failed_not_paused(self):
        msg = self._status_after_stop(True)
        assert '播放失败' in msg
        assert '已暂停' not in msg

    def test_normal_stop_still_shows_paused(self):
        msg = self._status_after_stop(False)
        assert 'Paused' in msg


class TestServerPortFallback:
    """端口被占用时向后自动顺延，而不是启动失败或误报。"""

    def test_busy_port_shifts_to_next_available(self):
        import socket
        from server.app import IPTVServer
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        server = IPTVServer(host='127.0.0.1', port=port)
        try:
            server.start()
            assert server.wait_started(3.0) is True
            assert server.requested_port == port
            assert server.port > port
        finally:
            server.stop()
            sock.close()

    def test_three_instances_shift_and_reuse_released_port(self):
        from server.app import IPTVServer
        base = self._free_base_port()
        servers = []
        try:
            for _ in range(3):
                s = IPTVServer(host='127.0.0.1', port=base)
                s.start()
                assert s.wait_started(3.0) is True
                servers.append(s)

            ports = [s.port for s in servers]
            assert len(set(ports)) == 3
            assert ports == sorted(ports)

            # 关掉中间一个，新实例应复用它释放出来的端口
            middle = servers.pop(1)
            middle_port = middle.port
            middle.stop()

            reused = IPTVServer(host='127.0.0.1', port=base)
            reused.start()
            assert reused.wait_started(3.0) is True
            servers.append(reused)
            assert reused.port == middle_port
        finally:
            for s in servers:
                s.stop()

    @staticmethod
    def _free_base_port():
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()
        return port


class TestPanelDividerStyling:
    """底栏分隔线样式刷新不能覆盖节目简介等 QLabel 的透明样式。"""

    def test_label_with_max_height_keeps_its_style(self):
        from PySide6.QtWidgets import QApplication, QFrame, QLabel, QWidget
        if QApplication.instance() is None:
            QApplication([])
        host = QWidget()
        label = QLabel('desc text', host)
        label.setObjectName('program_desc')
        label.setStyleSheet(
            'QLabel { background-color: transparent; max-height: 48px; }')
        line = QFrame(host)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('QFrame { background-color: #555555; max-height: 1px; }')

        from controllers.ui_controller import reapply_divider_styles
        reapply_divider_styles(host)

        assert 'transparent' in label.styleSheet()
        assert 'max-height' in line.styleSheet()

    def test_controller_reapply_does_not_raise_attribute_error(self):
        """主题刷新必须调用模块级函数；写成 self.reapply_divider_styles 会整段刷新失败。"""
        from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFrame
        if QApplication.instance() is None:
            QApplication([])
        from ui.styles import AppStyles
        from controllers.ui_controller import UIController

        AppStyles.set_color_mode('dark')
        host = QWidget()
        fp = QWidget(host)
        host.floating_panel = fp
        label = QLabel('简介', fp)
        label.setObjectName('program_desc')
        label.setStyleSheet('QLabel { color: #ffffff; background: transparent; max-height: 48px; }')
        line = QFrame(fp)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('QFrame { background-color: #ff0000; max-height: 1px; }')

        UIController(host)._reapply_floating_panel_styles()

        assert line.styleSheet() == AppStyles.player_line_style()
        assert 'transparent' in label.styleSheet()


class TestChannelListVirtualization:
    """大列表填充不能逐项构建行控件，否则耗时随条数平方增长（5000 条约 127 秒）。"""

    @staticmethod
    def _make_host():
        from PySide6.QtWidgets import QApplication, QListWidget, QWidget
        if QApplication.instance() is None:
            QApplication([])
        host_widget = QWidget()
        lw = QListWidget(host_widget)

        class _LM:
            def tr(self, key, default=''):
                return default

        class _Win:
            def __init__(self):
                # 持有 QListWidget 的父对象，避免测试函数返回后被 Python GC 连带销毁
                self.host_widget = host_widget
                self.language_manager = _LM()
                self.sub_empty_label = None
                self.local_empty_label = None
                self._icon_load_timer = None
                self._icon_load_set = set()
                self._icon_load_queue = []
                self.status_messages = []
                self.sub_channel_list = lw
                self.local_channel_list = None

            def status_bar_show_message(self, message, timeout=0):
                self.status_messages.append(message)

            def _on_channel_list_scrolled(self, value):
                pass

        return _Win(), lw

    @staticmethod
    def _channels(count):
        return [{'name': f'频道{i}', 'url': f'http://example/{i}', 'group': 'g'} for i in range(count)]

    def test_populate_5000_only_decorates_visible_window(self):
        import time
        from controllers.channel_controller import ChannelController
        host, lw = self._make_host()
        ctrl = ChannelController(host)

        started = time.perf_counter()
        ctrl.populate_channel_list_for(lw, self._channels(5000), 'All Channels')
        elapsed = time.perf_counter() - started

        assert lw.count() == 5000
        assert elapsed < 10.0, f'5000 条填充耗时 {elapsed:.1f}s，仍接近平方级'
        decorated = sum(1 for i in range(lw.count()) if lw.itemWidget(lw.item(i)) is not None)
        assert decorated < 300, f'为 {decorated} 行创建了控件，未按视口裁剪'
        assert lw.itemWidget(lw.item(0)) is not None, '首行应立即可见'
        # 行控件透明，装饰后条目文本必须清空，否则文字会重叠
        assert lw.item(0).text() == ''
        assert lw.item(0).data(ChannelController.ROW_DISPLAY_ROLE)
        assert any('5000' in m for m in host.status_messages), '大列表应有加载完成反馈'

    def test_scroll_to_bottom_decorates_tail_rows(self):
        from PySide6.QtWidgets import QApplication
        from controllers.channel_controller import ChannelController
        host, lw = self._make_host()
        ctrl = ChannelController(host)
        ctrl.populate_channel_list_for(lw, self._channels(2000), 'All Channels')

        lw.scrollToBottom()
        QApplication.processEvents()
        ctrl.decorate_visible_rows(lw)

        last = lw.count() - 1
        assert lw.itemWidget(lw.item(last)) is not None, '滚动到底部后末行应补上控件'

    def test_scroll_keeps_visible_rows_decorated(self):
        # 真实列表带行间距与边框，indexAt(0,0) 取点会落在间距外恒无效；
        # 这里按同样的行间距复现，滚动后视口内的行必须补上控件
        from PySide6.QtWidgets import QApplication
        from controllers.channel_controller import ChannelController
        host, lw = self._make_host()
        lw.setSpacing(2)
        lw.resize(260, 320)
        lw.show()
        QApplication.processEvents()
        ctrl = ChannelController(host)
        ctrl.populate_channel_list_for(lw, self._channels(600), 'All Channels')
        QApplication.processEvents()

        lw.verticalScrollBar().setValue(300)
        QApplication.processEvents()
        ctrl.decorate_visible_rows(lw)

        for row in range(300, 306):
            assert lw.itemWidget(lw.item(row)) is not None, f'滚动后第 {row} 行未装饰'

    def test_quality_update_survives_widget_recycle(self):
        from PySide6.QtWidgets import QApplication
        from controllers.channel_controller import ChannelController
        from ui.quality_bar import QUALITY_SCORE_ROLE, QualityBarWidget
        host, lw = self._make_host()
        ctrl = ChannelController(host)
        ctrl.populate_channel_list_for(lw, self._channels(50), 'All Channels')

        ctrl.update_quality_bar_for_url('http://example/10', 73.5, 'B')
        item = lw.item(10)
        assert item.data(QUALITY_SCORE_ROLE) == 73.5

        # 模拟滚动回收后重新装饰：评分应从条目数据恢复
        lw.removeItemWidget(item)
        QApplication.processEvents()
        ctrl.decorate_visible_rows(lw)
        widget = lw.itemWidget(item)
        assert widget is not None
        bar = widget.findChild(QualityBarWidget, 'quality_bar')
        assert bar is not None and bar._score == 73.5
