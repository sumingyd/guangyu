"""numpy 可选依赖与 GPU 降级路径测试（全部使用 mock，不依赖真机显卡）。

覆盖：
  * numpy 缺失时音频可视化与环回频谱的降级行为；
  * numpy 导入失败的诊断能落盘到 crash.log；
  * D3D11 上下文初始化失败只触发一次 GPU 降级并持久化 gpu_api=opengl。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

import services.audio_visual_service as avs  # noqa: E402
import services.loopback_spectrum_service as svc  # noqa: E402
import services.mpv_playback as mpb  # noqa: E402
import utils.numpy_compat as nc  # noqa: E402
from utils.gpu_caps import d3d11_available  # noqa: E402


def test_zeros_helper_degrades(monkeypatch):
    """numpy 缺失时 _zeros 返回空元组，不引用 ndarray。"""
    monkeypatch.setattr(avs, 'np', None)
    assert avs._zeros(8) == ()


def test_compute_spectrum_without_numpy(monkeypatch):
    """numpy 缺失时频谱返回全零柱，而不是抛异常。"""
    monkeypatch.setattr(avs, 'np', None)
    assert avs.compute_spectrum([0.0] * 2048) == [0.0] * avs.NUM_BARS


def test_loopback_levels_without_numpy(monkeypatch):
    """numpy 缺失时环回频谱按零柱降级。"""
    monkeypatch.setattr(svc, 'np', None)
    bars = svc.compute_spectrum_levels(b'\x00' * 4096, 2, 48000)
    assert bars == [0.0] * svc.BAR_COUNT


def test_loopback_collector_reports_missing_dependency(monkeypatch):
    """numpy 缺失时采集器按 missing_dependency 失败，不启动线程。"""
    monkeypatch.setattr(svc, 'platform_supported', lambda: True)
    monkeypatch.setattr(svc, 'np', None)
    reasons = []
    collector = svc.LoopbackSpectrumCollector()
    collector.failed.connect(reasons.append)
    collector.start()
    assert reasons == [svc.REASON_MISSING_DEPENDENCY]
    assert collector._thread is None


def test_record_import_failure_writes_crash_log(tmp_path, monkeypatch):
    """导入失败诊断写入 crash.log，包含 CPU、指令集与 _MEIPASS 摘要。"""
    monkeypatch.setattr(nc, '_log_dir', lambda: str(tmp_path))
    try:
        raise ImportError('Importing the numpy C-extensions failed')
    except ImportError as exc:
        nc.record_import_failure(exc)

    log_path = tmp_path / 'crash.log'
    assert log_path.exists()
    content = log_path.read_text(encoding='utf-8')
    assert 'numpy 导入失败' in content
    assert 'CPU:' in content
    assert 'MEIPASS' in content


def test_gpu_caps_probe_returns_bool():
    """显卡探测必须返回布尔值且不抛异常。"""
    assert isinstance(d3d11_available(), bool)


class _FakeConfigManager:
    saved = []

    def save_video_eq(self, settings):
        _FakeConfigManager.saved.append(dict(settings))


class _FakeFacade:
    def __init__(self):
        self.logger = _FakeLogger()
        self._playback_settings = {'gpu_api': 'auto', 'hdr_output_mode': 'disable'}
        self._gpu_fallback_done = False


class _FakeLogger:
    def __init__(self):
        self.warnings = []
        self.debugs = []

    def warning(self, msg):
        self.warnings.append(msg)

    def debug(self, msg):
        self.debugs.append(msg)

    def error(self, msg):
        self.debugs.append(msg)


def test_gpu_fallback_triggers_once_and_persists(monkeypatch):
    """D3D11 初始化失败日志触发一次降级，写入配置并延迟重建。"""
    import core.config_manager as cm

    monkeypatch.setattr(mpb, 'is_windows', lambda: True)
    monkeypatch.setattr(cm, 'ConfigManager', _FakeConfigManager)
    scheduled = []
    from PySide6.QtCore import QTimer
    monkeypatch.setattr(QTimer, 'singleShot', staticmethod(lambda ms, cb: scheduled.append(cb)))
    _FakeConfigManager.saved = []

    facade = _FakeFacade()
    playback = mpb.MpvPlayback(facade)
    playback._maybe_trigger_gpu_fallback('Failed initializing any suitable GPU context!')
    playback._maybe_trigger_gpu_fallback('Failed initializing any suitable GPU context!')

    assert facade._gpu_fallback_done is True
    assert facade._playback_settings['gpu_api'] == 'opengl'
    assert _FakeConfigManager.saved == [{'gpu_api': 'opengl'}]
    assert len(scheduled) == 1
    assert facade.logger.warnings


def test_gpu_fallback_ignores_explicit_setting(monkeypatch):
    """用户显式选择 d3d11 时不做自动降级。"""
    monkeypatch.setattr(mpb, 'is_windows', lambda: True)
    facade = _FakeFacade()
    facade._playback_settings['gpu_api'] = 'd3d11'
    playback = mpb.MpvPlayback(facade)
    playback._maybe_trigger_gpu_fallback('Could not create D3D11 device.')
    assert facade._gpu_fallback_done is False
