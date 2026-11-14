from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from PySide6.QtCore import QObject

from controllers import playback_controller as pc_module
from controllers.playback_controller import PlaybackController


class _Host(QObject):
    def __init__(self, channels, buffering=False):
        super().__init__()
        self.channel_model = SimpleNamespace(channels=channels)
        self.language_manager = SimpleNamespace(tr=lambda _k, d='': d)
        self.current_channel = None
        self.play_state = SimpleNamespace(is_live=True, is_idle=False,
                                          is_catchup_or_timeshift=False)
        self.player_controller = SimpleNamespace(
            is_playing=True,
            get_buffer_state=lambda: {'buffering': buffering},
        )
        self.messages = []

    def status_bar_show_message(self, message, timeout=0):
        self.messages.append(message)


def _channel(name, url, resolution=''):
    return {'name': name, 'url': url, 'resolution': resolution}


def _make(channels, buffering=False):
    host = _Host(channels, buffering)
    ctrl = PlaybackController(host)
    ctrl._buffer_watch_timer.stop()
    return ctrl, host


def test_resolution_height_from_field_and_name():
    assert PlaybackController._resolution_height({'resolution': '1920x1080'}) == 1080
    assert PlaybackController._resolution_height({'name': 'CCTV1 576P'}) == 576
    assert PlaybackController._resolution_height({'name': 'CCTV1'}) == 0


def test_find_backup_prefers_lower_resolution_only():
    current = _channel('CCTV1', 'http://a', '1920x1080')
    lower = _channel('CCTV1', 'http://b', '720x576')
    higher = _channel('CCTV1', 'http://c', '3840x2160')
    other = _channel('CCTV2', 'http://d', '720x576')
    ctrl, _ = _make([current, lower, higher, other])

    assert ctrl._find_backup_channel(current)['url'] == 'http://b'
    degraded = ctrl._find_backup_channel(current, prefer_lower=True)
    assert degraded['url'] == 'http://b'


def test_find_backup_skips_already_tried():
    current = _channel('CCTV1', 'http://a', '1920x1080')
    backup = _channel('CCTV1', 'http://b', '720x576')
    ctrl, _ = _make([current, backup])
    ctrl._tried_urls.add('http://b')
    assert ctrl._find_backup_channel(current) is None


def test_degrade_switches_once_and_notifies():
    current = _channel('CCTV1', 'http://a', '1920x1080')
    backup = _channel('CCTV1', 'http://b', '720x576')
    ctrl, host = _make([current, backup])
    ctrl.play_channel = MagicMock()

    ctrl._degrade_on_buffering(current)
    ctrl._degrade_on_buffering(current)

    ctrl.play_channel.assert_called_once_with(backup)
    assert ctrl._auto_degraded_urls == {'http://a'}
    assert any('更低码率' in m for m in host.messages)


def test_sustained_buffering_triggers_degrade(monkeypatch):
    current = _channel('CCTV1', 'http://a', '1920x1080')
    backup = _channel('CCTV1', 'http://b', '720x576')
    ctrl, host = _make([current, backup], buffering=True)
    ctrl.play_channel = MagicMock()
    host.current_channel = current
    ctrl.current_channel = current
    ctrl._buf_watch_started_at = 0.0

    clock = {'now': 100.0}
    monkeypatch.setattr(pc_module, 'monotonic', lambda: clock['now'])

    # 起播窗口内不参与
    ctrl._tick_buffer_watch()
    assert ctrl.play_channel.call_count == 0

    # 连续缓冲 9 秒后触发一次降级
    clock['now'] = 110.0
    ctrl._tick_buffer_watch()
    assert ctrl.play_channel.call_count == 0
    clock['now'] = 120.0
    ctrl._tick_buffer_watch()
    assert ctrl.play_channel.call_count == 1
    ctrl.play_channel.assert_called_once_with(backup)
