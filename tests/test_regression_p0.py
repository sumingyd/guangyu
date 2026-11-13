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


class TestServerStartFailure:
    """端口被占用时必须能识别启动失败，而不是显示“服务已启动”。"""

    def test_wait_started_false_when_port_busy(self):
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
            assert server.wait_started(3.0) is False
            assert server.start_error
        finally:
            server.stop()
            sock.close()
