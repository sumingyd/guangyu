"""WASAPI loopback 频谱采集与失败矩阵测试（全部使用 mock，不依赖真机设备）。

覆盖：
  * FFT 输出形状、静音全零、单声道混音；
  * 六条降级路径：非 Windows、依赖缺失、无设备、初始化异常、
    运行中读流异常、连续无有效数据（外加初始化超时）；
  * 控制器层：同一原因码每会话只记一条 WARNING；
  * 重新进入屏保会重试一次，退出无条件停止采集；
  * 实时 -> 降级约 300ms 交叉淡入。
"""

import os
import sys
import time
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import controllers.screensaver_controller as ssc  # noqa: E402
import services.loopback_spectrum_service as svc  # noqa: E402
from ui.screensaver_widget import ScreenSaverWidget  # noqa: E402


@pytest.fixture(scope='module', autouse=True)
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def supported(monkeypatch):
    """所有采集器测试都假定平台可用，避免受 CI 平台影响。"""
    monkeypatch.setattr(svc, 'platform_supported', lambda: True)


def _wait_for(predicate, timeout=2.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---- 纯函数：FFT ---------------------------------------------------------

def _pcm_tone(freq, rate=16000, seconds=0.1, channels=1, amp=0.5):
    count = int(rate * seconds)
    t = np.arange(count) / rate
    mono = (np.sin(2 * np.pi * freq * t) * amp * 32767).astype(np.int16)
    if channels > 1:
        mono = np.repeat(mono[:, None], channels, axis=1).reshape(-1)
    return mono.tobytes()


def test_compute_levels_shape_and_peak():
    levels = svc.compute_spectrum_levels(_pcm_tone(1000), 1, 16000)
    assert len(levels) == svc.BAR_COUNT
    assert max(levels) > 0.3
    peak = levels.index(max(levels))
    assert 24 <= peak <= 34, '1kHz 应落在中低频段附近'


def test_compute_levels_silence_is_zero():
    silence = np.zeros(1600, dtype=np.int16).tobytes()
    assert svc.compute_spectrum_levels(silence, 1, 16000) == [0.0] * svc.BAR_COUNT
    assert svc.compute_spectrum_levels(b'', 1, 16000) == [0.0] * svc.BAR_COUNT


def test_compute_levels_stereo_mix():
    mono = svc.compute_spectrum_levels(_pcm_tone(1000), 1, 16000)
    stereo = svc.compute_spectrum_levels(_pcm_tone(1000, channels=2), 2, 16000)
    assert np.allclose(mono, stereo, atol=1e-6), '同信号立体声应等同单声道'


# ---- 采集器：失败矩阵 ----------------------------------------------------

class _FakeStream:
    def __init__(self, reader, available=4096):
        self._reader = reader
        self._available = available
        self.stop_calls = 0
        self.close_calls = 0

    def get_read_available(self):
        return self._available

    def read(self, frames, exception_on_overflow=False):
        return self._reader()

    def stop_stream(self):
        self.stop_calls += 1

    def close(self):
        self.close_calls += 1


class _FakePyAudio:
    def __init__(self, device=None, device_exc=None, open_exc=None, stream=None,
                 init_exc=None):
        if init_exc is not None:
            raise init_exc
        self.device = device
        self.device_exc = device_exc
        self.open_exc = open_exc
        self.stream = stream
        self.terminated = False
        self.open_kwargs = None

    def get_default_wasapi_loopback(self):
        if self.device_exc is not None:
            raise self.device_exc
        return self.device

    def open(self, **kwargs):
        self.open_kwargs = kwargs
        if self.open_exc is not None:
            raise self.open_exc
        return self.stream

    def terminate(self):
        self.terminated = True


def _fake_module(audio):
    return types.SimpleNamespace(PyAudio=lambda: audio, paInt16=8)


def _device(channels=1, rate=16000):
    return {
        'index': 3,
        'name': 'Fake Loopback',
        'maxInputChannels': channels,
        'defaultSampleRate': rate,
        'isLoopbackDevice': True,
    }


def _collect(_unused, module_loader, opener=None, **kwargs):
    # 平台可用性由 ``supported`` fixture 统一注入；这里只负责装配采集器
    collector = svc.LoopbackSpectrumCollector(
        module_loader=module_loader, opener=opener, **kwargs)
    failures = []
    bars = []
    collector.failed.connect(failures.append)
    collector.bars_ready.connect(bars.append)
    collector.start()
    return collector, failures, bars


def test_collector_unsupported_platform(monkeypatch):
    monkeypatch.setattr(svc, 'platform_supported', lambda: False)
    collector = svc.LoopbackSpectrumCollector()
    failures = []
    collector.failed.connect(failures.append)
    collector.start()
    assert failures == [svc.REASON_UNSUPPORTED]
    assert collector.is_running is False


def test_collector_missing_dependency(supported):
    def loader():
        raise ImportError('no pyaudiowpatch')

    collector, failures, _bars = _collect(None, loader)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_MISSING_DEPENDENCY]
    finally:
        collector.stop()


def test_collector_no_device(supported):
    module = _fake_module(_FakePyAudio(device=None))
    collector, failures, _bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_NO_DEVICE]
    finally:
        collector.stop()


def test_collector_init_exception(supported):
    def raising_audio():
        raise RuntimeError('boom')

    module = types.SimpleNamespace(PyAudio=raising_audio, paInt16=8)
    collector, failures, _bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_INIT_FAILED]
    finally:
        collector.stop()


def test_collector_device_exclusive_or_format(supported):
    audio = _FakePyAudio(device=_device(), open_exc=OSError('device busy'))
    module = _fake_module(audio)
    collector, failures, _bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_DEVICE_EXCLUSIVE_OR_FORMAT]
        assert audio.terminated is True
    finally:
        collector.stop()


def test_collector_runtime_error_stops_capture(supported):
    def reader():
        raise OSError('stream lost')

    stream = _FakeStream(reader)
    audio = _FakePyAudio(device=_device(), stream=stream)
    module = _fake_module(audio)
    collector, failures, _bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_RUNTIME_ERROR]
        assert _wait_for(lambda: not collector.is_running, timeout=1.0)
    finally:
        collector.stop()
    assert stream.close_calls >= 1


def test_collector_invalid_data_stops_capture(supported):
    stream = _FakeStream(lambda: b'')
    audio = _FakePyAudio(device=_device(), stream=stream)
    module = _fake_module(audio)
    collector, failures, _bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: failures)
        assert failures == [svc.REASON_INVALID_DATA]
        assert _wait_for(lambda: not collector.is_running, timeout=1.0)
    finally:
        collector.stop()


def test_collector_no_available_data_degrades(supported):
    """设备空闲时没有可读帧（真实 SPDIF 场景），必须按时降级而不是卡死。"""
    stream = _FakeStream(lambda: b'', available=0)
    audio = _FakePyAudio(device=_device(), stream=stream)
    module = _fake_module(audio)
    collector, failures, _bars = _collect(
        None, lambda: module, data_timeout_seconds=0.1)
    try:
        assert _wait_for(lambda: failures, timeout=1.0)
        assert failures == [svc.REASON_INVALID_DATA]
        assert _wait_for(lambda: not collector.is_running, timeout=1.0)
    finally:
        collector.stop()


def test_collector_init_timeout(supported):
    def slow_opener(_module, _rate, _block):
        time.sleep(0.25)
        raise RuntimeError('late failure')

    module = _fake_module(_FakePyAudio(device=_device()))
    collector, failures, _bars = _collect(
        None, lambda: module, opener=slow_opener, init_timeout_ms=50)
    try:
        assert _wait_for(lambda: failures, timeout=1.5)
        assert failures == [svc.REASON_INIT_TIMEOUT]
    finally:
        collector.stop()


def test_collector_emits_bars_for_tone(supported):
    tone = _pcm_tone(1000)
    stream = _FakeStream(lambda: tone)
    audio = _FakePyAudio(device=_device(), stream=stream)
    module = _fake_module(audio)
    collector, failures, bars = _collect(None, lambda: module)
    try:
        assert _wait_for(lambda: bars, timeout=1.5)
        assert not failures
        assert len(bars[0]) == svc.BAR_COUNT
        assert max(bars[0]) > 0.2
        assert audio.open_kwargs['rate'] == 16000, '应优先尝试低采样率'
    finally:
        collector.stop()
    assert stream.close_calls >= 1


# ---- 控制器层：日志去重与重试边界 ---------------------------------------

class _RecordingLogger:
    def __init__(self):
        self.warnings = []
        self.debugs = []
        self.infos = []
        self.errors = []

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)

    def debug(self, message, *args, **kwargs):
        self.debugs.append(message)

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)


class _FakeCollector(QObject):
    bars_ready = Signal(list)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = 0
        self.stopped = 0
        self.deleted = False

    def start(self):
        self.started += 1

    def stop(self, *args, **kwargs):
        self.stopped += 1

    def deleteLater(self):
        self.deleted = True


class _WindowStub(QWidget):
    def __init__(self):
        super().__init__()
        self.player_controller = None
        self.epg_panel = None
        self.playlist_panel = None
        self.floating_panel = None
        self.config = None
        self.language_manager = None
        self.current_channel = {'name': 'CCTV-1'}
        self.epg_parser = None
        self._idle_render = None
        self._audio_visual_widget = None


def _make_env(monkeypatch, platform=False):
    logger = _RecordingLogger()
    monkeypatch.setattr(ssc, 'logger', logger)
    if platform:
        monkeypatch.setattr(ssc, 'platform_supported', lambda: True)
    else:
        monkeypatch.setattr(ssc, 'platform_supported', lambda: False)
    window = _WindowStub()
    window.resize(640, 360)
    window.show()
    widget = ScreenSaverWidget(window)
    widget.hide()
    collectors = []

    def factory():
        collector = _FakeCollector()
        collectors.append(collector)
        return collector

    kwargs = {}
    if platform:
        # 只有「平台可用」的用例注入假采集器；其余走真实失败分支
        kwargs['collector_factory'] = factory
    ctrl = ssc.ScreenSaverController(
        window, widget, require_exposed=False, poll_interval_ms=60000, **kwargs)
    ctrl.start()
    return window, widget, ctrl, logger, collectors


def _activate(ctrl):
    ctrl._last_input_ts = time.monotonic() - 600
    ctrl._evaluate()
    assert ctrl.is_active


def test_degrade_logs_once_per_reason(app, monkeypatch):
    window, _widget, ctrl, logger, _collectors = _make_env(monkeypatch, platform=True)
    try:
        _activate(ctrl)
        ctrl._on_spectrum_failed('no_device')
        ctrl._on_spectrum_failed('no_device')
        assert len(logger.warnings) == 1, '同一原因码每会话只记一条 WARNING'
        status = ctrl.get_status()
        assert status['spectrum_source'] == 'none'
        assert status['spectrum_degraded_reason'] == 'no_device'
    finally:
        ctrl.shutdown()
        window.hide()


def test_unsupported_platform_degrades_without_collector(app, monkeypatch):
    window, _widget, ctrl, logger, collectors = _make_env(monkeypatch)
    try:
        _activate(ctrl)
        assert collectors == [], '非 Windows 不得创建采集器'
        assert ctrl.get_status()['spectrum_degraded_reason'] == svc.REASON_UNSUPPORTED
        assert len(logger.warnings) == 1
    finally:
        ctrl.shutdown()
        window.hide()


def test_lifecycle_starts_on_activate_stops_on_exit(app, monkeypatch):
    window, widget, ctrl, _logger, collectors = _make_env(monkeypatch, platform=True)
    try:
        _activate(ctrl)
        assert len(collectors) == 1 and collectors[0].started == 1
        ctrl.note_activity()
        assert ctrl.is_active is False
        assert collectors[0].stopped == 1, '退出屏保必须立即停止采集'

        _activate(ctrl)
        assert len(collectors) == 2, '新的一次屏保会话允许重试一次'
        assert collectors[1].started == 1
        assert collectors[1] is not collectors[0]
    finally:
        ctrl.shutdown()
        window.hide()


def test_live_bars_and_crossfade(app, monkeypatch):
    window, widget, ctrl, _logger, collectors = _make_env(monkeypatch, platform=True)
    try:
        _activate(ctrl)
        collector = collectors[0]
        collector.bars_ready.emit([0.5] * svc.BAR_COUNT)
        assert ctrl.get_status()['spectrum_source'] == 'loopback'
        assert widget._live is True

        ctrl._on_spectrum_failed('runtime_error')
        assert widget._live is False
        assert widget._transition_from is not None, '有数据到降级要交叉淡入'

        # 把起点拨到 300ms 之前，让下一帧完成过渡
        widget._transition_start = time.monotonic() - 1.0
        widget._on_anim_tick()
        assert widget._transition_from is None
        assert min(widget._bars) > 0.0, '降级柱高必须恒大于零'
    finally:
        ctrl.shutdown()
        window.hide()


def test_bars_ignored_after_exit(app, monkeypatch):
    window, widget, ctrl, _logger, collectors = _make_env(monkeypatch, platform=True)
    try:
        _activate(ctrl)
        ctrl.note_activity()
        collectors[0].bars_ready.emit([0.5] * svc.BAR_COUNT)
        assert widget._live is False, '退出后到达的采集帧不得再写控件'
        assert ctrl.get_status()['spectrum_source'] == 'none'
    finally:
        ctrl.shutdown()
        window.hide()
