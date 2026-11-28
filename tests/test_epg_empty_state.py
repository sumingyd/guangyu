"""EPG 空态判定与退出时子进程清理的回归测试。"""
import types

import pytest

from controllers import epg_controller as epg_mod
from controllers.epg_controller import EPGController
from services import deep_probe_service
from services.ffprobe_validator_service import FfprobeStreamValidator


class _FakeLabel:
    def __init__(self):
        self.text = ''
        self.tooltip = ''
        self.cursor = None
        self.visible = False

    def setText(self, text):
        self.text = text

    def setToolTip(self, text):
        self.tooltip = text

    def setCursor(self, cursor):
        self.cursor = cursor

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def relayout(self):
        pass


def _make_controller(has_sources=True, loading=False):
    window = types.SimpleNamespace(
        current_channel=None,
        epg_empty_label=_FakeLabel(),
        epg_match_label=_FakeLabel(),
        epg_empty_action='stale',
        _local_channels=[],
        subscription_ctrl=types.SimpleNamespace(
            _workers=[types.SimpleNamespace(isRunning=lambda: loading)]
        ),
    )
    controller = EPGController(window)
    controller._has_playlist_sources = lambda: has_sources
    controller._channels_loading = lambda: loading
    return controller, window


def test_idle_with_channels_is_no_selection():
    controller, _ = _make_controller(has_sources=True)
    controller._channel_total = lambda: 306
    assert controller._idle_empty_kind() == 'no_selection'


def test_idle_channel_source_still_loading():
    controller, _ = _make_controller(has_sources=True, loading=True)
    controller._channel_total = lambda: 0
    assert controller._idle_empty_kind() == 'loading'


def test_idle_source_without_channels():
    controller, _ = _make_controller(has_sources=True, loading=False)
    controller._channel_total = lambda: 0
    assert controller._idle_empty_kind() == 'no_channel'


def test_idle_without_any_source():
    controller, _ = _make_controller(has_sources=False, loading=False)
    controller._channel_total = lambda: 0
    assert controller._idle_empty_kind() == 'no_source'


def test_channel_total_uses_aggregated_table(monkeypatch):
    """聚合表已包含本地块，不能再把 _local_channels 加一遍。"""
    controller, window = _make_controller()
    window._local_channels = [{'name': 'a'}, {'name': 'b'}]
    monkeypatch.setattr(
        'core.application_state.app_state',
        types.SimpleNamespace(channel_count=3),
    )
    assert controller._channel_total() == 3


def test_no_selection_empty_state_text(monkeypatch):
    monkeypatch.setattr(epg_mod, 'QCursor', lambda *args: 'cursor')
    controller, window = _make_controller()

    controller._show_epg_empty('no_selection')

    assert window.epg_empty_label.text == '选择频道查看节目单'
    assert window.epg_empty_action is None
    assert window.epg_empty_label.visible is True


def test_loading_empty_state_text(monkeypatch):
    monkeypatch.setattr(epg_mod, 'QCursor', lambda *args: 'cursor')
    controller, window = _make_controller()

    controller._show_epg_empty('loading')

    assert window.epg_empty_label.text == '正在加载频道…'
    assert window.epg_empty_action is None


class _FakeProc:
    def __init__(self, exit_on_kill=True):
        self.pid = 4321
        self.killed = False
        self._exit_on_kill = exit_on_kill

    def poll(self):
        if self.killed and self._exit_on_kill:
            return -9
        return None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        if not self._exit_on_kill:
            raise RuntimeError('still running')
        return 0


def test_terminate_all_deep_probes_kills_children():
    proc = _FakeProc()
    deep_probe_service._active_procs.add(proc)
    try:
        leftover = deep_probe_service.terminate_all_deep_probes()
    finally:
        deep_probe_service._active_procs.discard(proc)

    assert leftover == []
    assert proc.killed is True


def test_terminate_all_ffprobe_reports_stubborn_process(monkeypatch):
    proc = _FakeProc(exit_on_kill=False)
    monkeypatch.setattr(
        FfprobeStreamValidator, '_active_processes', {proc.pid: proc}
    )

    leftover = FfprobeStreamValidator.terminate_all()

    assert proc.killed is True
    assert leftover == [proc.pid]


def test_terminate_external_processes_is_idempotent(monkeypatch):
    from controllers import event_handler as eh
    from services import mpv_validator_service

    calls = []

    class _Validator:
        @classmethod
        def set_terminating(cls):
            calls.append('ffprobe:set')

        @classmethod
        def terminate_all(cls):
            calls.append('ffprobe:kill')
            return []

    class _Clip:
        def shutdown(self):
            calls.append('clip:shutdown')

    monkeypatch.setattr(
        'services.ffprobe_validator_service.FfprobeStreamValidator', _Validator
    )
    monkeypatch.setattr(
        mpv_validator_service.MpvStreamValidator, 'terminate_all',
        classmethod(lambda cls: calls.append('mpv:kill')),
    )
    monkeypatch.setattr(
        'services.deep_probe_service.terminate_all_deep_probes',
        lambda: calls.append('deep:kill') or [],
    )
    monkeypatch.setattr(eh, '_cleanup_done', False)

    window = types.SimpleNamespace(clip_export_service=_Clip())
    eh.terminate_external_processes(window)
    eh.terminate_external_processes(window)

    assert calls == [
        'ffprobe:set', 'ffprobe:kill', 'mpv:kill', 'deep:kill', 'clip:shutdown',
    ]
