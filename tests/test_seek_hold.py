from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from controllers import event_handler as event_handler_module
from controllers.event_handler import EventHandler


class _FakeSlider:
    def __init__(self, maximum):
        self._maximum = maximum
        self.value = 0

    def maximum(self):
        return self._maximum

    def setValue(self, value):
        self.value = value


class _FakeWindow:
    def __init__(self, pc, slider):
        self.player_controller = pc
        self.program_progress = slider
        self.language_manager = SimpleNamespace(tr=lambda _k, d='': d)
        self.is_fullscreen = True

    def isActiveWindow(self):
        return True


def _make_handler():
    pc = MagicMock()
    pc.is_playing = True
    pc.is_paused = False
    pc.get_current_time.return_value = 60_000  # 当前 60s
    pc.get_total_time.return_value = 600_000   # 总长 600s
    slider = _FakeSlider(600)
    handler = EventHandler(_FakeWindow(pc, slider))
    handler._seek_hold_timer = MagicMock()
    return handler, pc, slider


def test_single_click_seeks_15s_once(monkeypatch):
    handler, pc, _ = _make_handler()
    clock = {'now': 100.0}
    monkeypatch.setattr(event_handler_module.time, 'monotonic', lambda: clock['now'])

    handler._begin_seek_hold(1)
    assert handler._seek_hold_timer.start.called
    # 按下 200ms 就松手：只提交一次 +15s
    clock['now'] = 100.2
    handler._finish_seek_hold()

    pc.seek_relative_seconds.assert_called_once_with(15.0)
    assert handler._seek_hold_dir == 0
    assert handler.window._seek_preview_active is False


def test_hold_previews_then_commits_on_release(monkeypatch):
    handler, pc, slider = _make_handler()
    clock = {'now': 200.0}
    monkeypatch.setattr(event_handler_module.time, 'monotonic', lambda: clock['now'])

    handler._begin_seek_hold(1)
    pc.seek_relative_seconds.assert_not_called()

    # 越过 500ms 阈值后开始预览：进度条前移，但播放器一次都没有被 seek
    clock['now'] = 200.6
    handler._tick_seek_hold()
    clock['now'] = 201.0
    handler._tick_seek_hold()

    pc.seek_relative_seconds.assert_not_called()
    assert handler._seek_hold_offset >= 15.0
    assert slider.value > 60

    # 按住 3 秒后松手：一次性提交累计跳转量
    clock['now'] = 203.0
    handler._tick_seek_hold()
    expected = handler._seek_hold_offset
    handler._finish_seek_hold()

    pc.seek_relative_seconds.assert_called_once()
    assert pc.seek_relative_seconds.call_args[0][0] == pytest.approx(expected)


def test_hold_is_clamped_to_duration(monkeypatch):
    handler, pc, _ = _make_handler()
    clock = {'now': 300.0}
    monkeypatch.setattr(event_handler_module.time, 'monotonic', lambda: clock['now'])

    handler._begin_seek_hold(1)
    # 长按很久也不会超过视频总长
    clock['now'] = 400.0
    handler._tick_seek_hold()
    assert handler._seek_hold_base + handler._seek_hold_offset <= 600
