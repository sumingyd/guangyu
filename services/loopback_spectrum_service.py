"""Windows WASAPI loopback 实时频谱采集（仅屏保激活期间使用）。

职责边界：
  * 只在屏保激活时由 :class:`~controllers.screensaver_controller.ScreenSaverController`
    创建；退出屏保立即停止线程并释放设备，绝非常驻。
  * 只读取系统默认输出设备的 loopback 流，不改变播放链路的任何音频输出。
  * FFT 与平滑全部在采集线程内完成；UI 线程只收到已经算好的柱高列表，
    采集线程不会直接触碰任何 widget。

失败矩阵（每一行都对应一个原因码，统一降级为静态柱/慢波）：
  ========================  ==================================================
  ``unsupported``           非 Windows：导入期判定，不创建线程、不初始化设备
  ``missing_dependency``    未安装 PyAudioWPatch / 扩展模块导入失败
  ``no_device``             没有默认输出设备或没有 loopback 设备
  ``device_exclusive_or_format``  设备被独占，或采样格式/采样率被拒绝
  ``init_timeout``          初始化超时
  ``init_failed``           初始化阶段其他异常
  ``runtime_error``         采集过程中读流抛异常
  ``invalid_data``          连续多帧读不到有效数据
  ========================  ==================================================

同一个采集器实例最多发出一次失败信号；重试边界由控制器负责（只允许新的一次
屏保会话重试，激活期间不重启）。
"""

import importlib
import math
import sys
import threading
import time
from functools import lru_cache

from utils.numpy_compat import np, NUMPY_AVAILABLE
from PySide6.QtCore import QObject, QTimer, Signal

from core.log_manager import global_logger as logger

__all__ = [
    'LoopbackSpectrumCollector',
    'compute_spectrum_levels',
    'platform_supported',
    'REASON_CODES',
    'BAR_COUNT',
]

BAR_COUNT = 48
PREFERRED_RATE = 16000
FFT_SIZE = 1024
# 每块时长：20fps 上限（不按固定帧数，回落到 48kHz 时同样保持 50ms 一块）
BLOCK_SECONDS = 0.05
# 低于该 RMS 视为静音：直接输出全零柱，避免底噪把柱子抬起来
SILENCE_RMS = 0.0012
# 连续无有效数据的判定阈值（帧数或时长，先到先算）
INVALID_FRAME_LIMIT = 10
# 某些输出设备在空闲时不会向 loopback 送静音包（如 SPDIF 空闲），
# 连续该时长读不到任何数据块即判定无有效数据并降级；帧数阈值同时兜底。
DATA_TIMEOUT_SECONDS = 0.5
# 频带下限；上限取 Nyquist 的 95% 与 10kHz 中较小者
LOW_FREQ = 40.0
HIGH_FREQ = 10000.0
DB_FLOOR = -55.0

REASON_UNSUPPORTED = 'unsupported'
REASON_MISSING_DEPENDENCY = 'missing_dependency'
REASON_NO_DEVICE = 'no_device'
REASON_DEVICE_EXCLUSIVE_OR_FORMAT = 'device_exclusive_or_format'
REASON_INIT_TIMEOUT = 'init_timeout'
REASON_INIT_FAILED = 'init_failed'
REASON_RUNTIME_ERROR = 'runtime_error'
REASON_INVALID_DATA = 'invalid_data'

REASON_CODES = frozenset({
    REASON_UNSUPPORTED,
    REASON_MISSING_DEPENDENCY,
    REASON_NO_DEVICE,
    REASON_DEVICE_EXCLUSIVE_OR_FORMAT,
    REASON_INIT_TIMEOUT,
    REASON_INIT_FAILED,
    REASON_RUNTIME_ERROR,
    REASON_INVALID_DATA,
})


class _BackendError(Exception):
    """初始化阶段的可归类失败。``reason`` 必须是 :data:`REASON_CODES` 之一。"""

    def __init__(self, reason, detail=''):
        super().__init__(detail or reason)
        self.reason = reason if reason in REASON_CODES else REASON_INIT_FAILED
        self.detail = detail or ''


def platform_supported():
    """导入期判定：只有 Windows 才有 WASAPI loopback。此处不做任何设备探测。"""
    return sys.platform == 'win32'


# ---- 纯函数：FFT -> 柱高 -------------------------------------------------

@lru_cache(maxsize=8)
def _spectrum_plan(rate, bar_count, fft_size):
    """预计算 Hann 窗与几何间距频带切片，避免每帧重复分配。"""
    window = np.hanning(fft_size).astype(np.float32)
    bins = fft_size // 2 + 1
    nyquist = rate / 2.0
    low = LOW_FREQ
    high = min(nyquist * 0.95, HIGH_FREQ)
    if high <= low:
        low = max(1.0, nyquist * 0.02)
        high = max(low * 2.0, nyquist * 0.9)
    edges = np.geomspace(low, high, bar_count + 1)
    starts = np.clip(np.round(edges[:-1] / nyquist * (bins - 1)).astype(np.int64),
                     0, bins - 1)
    ends = np.clip(np.round(edges[1:] / nyquist * (bins - 1)).astype(np.int64) + 1,
                   1, bins)
    for index in range(bar_count):
        if ends[index] <= starts[index]:
            ends[index] = min(bins, starts[index] + 1)
    return window, tuple(int(v) for v in starts), tuple(int(v) for v in ends)


def compute_spectrum_levels(pcm_bytes, channels, rate, bar_count=BAR_COUNT,
                            fft_size=FFT_SIZE):
    """把一块 int16 PCM 转成 ``bar_count`` 个 ``[0, 1]`` 柱高。

    多声道按帧均值混成单声道；RMS 低于静音阈值时直接返回全零（静音输出就是
    零柱，不用底噪抬柱）。长度不足一个 FFT 窗时左补零，超过时取最后一段。
    """
    zeros = [0.0] * bar_count
    if np is None or not pcm_bytes or channels <= 0 or rate <= 0:
        return zeros
    try:
        data = np.frombuffer(pcm_bytes, dtype=np.int16)
    except (TypeError, ValueError):
        return zeros
    if data.size == 0:
        return zeros
    usable = data.size - (data.size % channels)
    if usable <= 0:
        return zeros
    mono = data[:usable].reshape(-1, channels).mean(axis=1).astype(np.float32)
    mono /= 32768.0
    if mono.size == 0:
        return zeros
    rms = float(np.sqrt(np.mean(mono * mono)))
    if not math.isfinite(rms) or rms < SILENCE_RMS:
        return zeros

    window, starts, ends = _spectrum_plan(float(rate), int(bar_count), int(fft_size))
    if mono.size < fft_size:
        mono = np.concatenate(
            [np.zeros(fft_size - mono.size, dtype=np.float32), mono])
    else:
        mono = mono[-fft_size:]
    magnitudes = np.abs(np.fft.rfft(mono * window))
    scale = fft_size / 4.0
    span = -DB_FLOOR
    levels = []
    for start, end in zip(starts, ends):
        peak = float(np.max(magnitudes[start:end])) if end > start else 0.0
        if peak > 0.0:
            db = 20.0 * math.log10(peak / scale)
        else:
            db = DB_FLOOR - 10.0
        level = (db - DB_FLOOR) / span
        levels.append(0.0 if level < 0.0 else (1.0 if level > 1.0 else level))
    return levels


# ---- 设备/流：只在采集线程内调用 ----------------------------------------

def _import_backend():
    try:
        return importlib.import_module('pyaudiowpatch')
    except Exception as e:
        raise _BackendError(REASON_MISSING_DEPENDENCY, str(e))


def _candidate_rates(preferred_rate, device_rate):
    rates = []
    for rate in (preferred_rate, device_rate):
        try:
            value = int(rate)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in rates:
            rates.append(value)
    return rates


def _safe_close(py_audio, stream):
    """释放顺序固定且每步独立包裹：任何一步异常都不能影响后续释放。"""
    if stream is not None:
        try:
            stream.stop_stream()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
    if py_audio is not None:
        try:
            py_audio.terminate()
        except Exception:
            pass


def _open_loopback(module, preferred_rate, block_seconds):
    """打开默认输出设备的 loopback 流。

    返回 ``(py_audio, stream, channels, rate, frames)``；失败抛
    :class:`_BackendError`，并保证已创建的资源被释放。
    """
    py_audio = None
    stream = None
    try:
        try:
            py_audio = module.PyAudio()
        except Exception as e:
            raise _BackendError(REASON_INIT_FAILED, f'PyAudio 初始化失败: {e}')

        try:
            device = py_audio.get_default_wasapi_loopback()
        except Exception as e:
            raise _BackendError(REASON_NO_DEVICE, f'获取默认 loopback 设备失败: {e}')
        if not device:
            raise _BackendError(REASON_NO_DEVICE, '没有可用的 WASAPI loopback 设备')

        try:
            channels = int(device.get('maxInputChannels') or 0)
            device_rate = int(device.get('defaultSampleRate') or 0)
        except (TypeError, ValueError, AttributeError) as e:
            raise _BackendError(REASON_NO_DEVICE, f'loopback 设备参数无效: {e}')
        if channels <= 0 or device_rate <= 0:
            raise _BackendError(REASON_NO_DEVICE, 'loopback 设备参数无效')
        index = device.get('index')

        errors = []
        for rate in _candidate_rates(preferred_rate, device_rate):
            frames = max(256, int(rate * block_seconds))
            try:
                stream = py_audio.open(
                    format=module.paInt16,
                    channels=channels,
                    rate=rate,
                    input=True,
                    input_device_index=index,
                    frames_per_buffer=frames,
                )
                return py_audio, stream, channels, rate, frames
            except Exception as e:
                errors.append(f'{rate}Hz: {e}')
                stream = None
        raise _BackendError(REASON_DEVICE_EXCLUSIVE_OR_FORMAT, '; '.join(errors))
    except BaseException:
        _safe_close(py_audio, stream)
        raise


class LoopbackSpectrumCollector(QObject):
    """一次屏保会话对应一个采集器；``start`` 后失败只会发一次 ``failed``。"""

    bars_ready = Signal(list)
    failed = Signal(str)
    _opened = Signal()

    def __init__(self, parent=None, init_timeout_ms=3000,
                 preferred_rate=PREFERRED_RATE, block_seconds=BLOCK_SECONDS,
                 bar_count=BAR_COUNT, fft_size=FFT_SIZE,
                 data_timeout_seconds=DATA_TIMEOUT_SECONDS,
                 module_loader=None, opener=None):
        super().__init__(parent)
        self._init_timeout_ms = max(1, int(init_timeout_ms))
        self._preferred_rate = int(preferred_rate)
        self._block_seconds = float(block_seconds)
        self._no_data_seconds = max(0.05, float(data_timeout_seconds))
        self._bar_count = int(bar_count)
        self._fft_size = int(fft_size)
        self._module_loader = module_loader or _import_backend
        self._opener = opener or _open_loopback

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._py_audio = None
        self._stream = None
        self._ready = False
        self._released = False
        self._failed = False
        self._fail_reason = ''
        self._last_error = ''
        self._smooth = [0.0] * self._bar_count

        self._init_timer = QTimer(self)
        self._init_timer.setSingleShot(True)
        self._init_timer.timeout.connect(self._on_init_timeout)
        # 由采集线程发出、在 UI 线程执行：只用来停初始化看门狗
        self._opened.connect(self._on_stream_opened)

    # ---- 公共 API ----
    @property
    def is_running(self):
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def fail_reason(self):
        return self._fail_reason

    @property
    def last_error(self):
        return self._last_error

    def start(self):
        if self._thread is not None:
            return
        if not platform_supported():
            self._fail(REASON_UNSUPPORTED, '非 Windows 平台')
            return
        if np is None:
            # numpy 缺失时 FFT 无法进行，按既有失败矩阵降级为静态柱
            self._fail(REASON_MISSING_DEPENDENCY, 'numpy 不可用')
            return
        self._stop_event.clear()
        self._init_timer.start(self._init_timeout_ms)
        self._thread = threading.Thread(
            target=self._run, name='loopback-spectrum', daemon=True)
        self._thread.start()

    def request_stop(self):
        """非阻塞地请求停止；可在 UI 线程或失败回调里安全调用。"""
        self._stop_event.set()
        try:
            self._init_timer.stop()
        except Exception:
            pass

    def stop(self, join_timeout=0.5):
        """停止并释放。释放本身异常也被包住，绝不会抛到调用方。"""
        self.request_stop()
        thread = self._thread
        self._thread = None
        if thread is not None:
            try:
                thread.join(timeout=max(0.0, float(join_timeout)))
            except Exception as e:
                logger.debug(f"[spectrum] 等待采集线程结束失败: {e}")
            if thread.is_alive():
                # 极端情况下读流仍卡住：强制释放设备以解除阻塞，再等一次
                self._release()
                try:
                    thread.join(timeout=0.2)
                except Exception:
                    pass
        self._release()

    def _release(self):
        """只释放一次；由停止方与采集线程共用，重复调用无副作用。"""
        with self._lock:
            if self._released:
                return
            self._released = True
            py_audio, stream = self._py_audio, self._stream
            self._py_audio = None
            self._stream = None
            self._ready = False
        _safe_close(py_audio, stream)

    # ---- 采集线程 ----
    def _run(self):
        try:
            module = self._module_loader()
            if self._stop_event.is_set():
                return
            py_audio, stream, channels, rate, frames = self._opener(
                module, self._preferred_rate, self._block_seconds)
            with self._lock:
                released = self._released
                if not released:
                    self._py_audio = py_audio
                    self._stream = stream
                    self._ready = True
            if released:
                # 初始化期间已被停止：这里补一次释放，避免设备句柄泄漏
                _safe_close(py_audio, stream)
                return
            if self._stop_event.is_set():
                # 初始化超时后返回：不再进入采集循环
                return
            self._opened.emit()

            no_data_reads = 0
            no_data_since = 0.0
            last_emit = 0.0
            while not self._stop_event.is_set():
                # 先查是否有数据再读：设备空闲时 read() 会一直阻塞，
                # 用轮询把停止权留在自己手里，退出屏保才能立即释放。
                try:
                    available = int(stream.get_read_available())
                except Exception as e:
                    self._fail(REASON_RUNTIME_ERROR, f'查询可读帧失败: {e}')
                    return
                if available <= 0:
                    now = time.monotonic()
                    no_data_reads += 1
                    if no_data_since <= 0.0:
                        no_data_since = now
                    if (no_data_reads >= INVALID_FRAME_LIMIT
                            or (now - no_data_since) >= self._no_data_seconds):
                        self._fail(REASON_INVALID_DATA,
                                   f'{self._no_data_seconds:.1f}s 内没有可读音频块')
                        return
                    self._stop_event.wait(self._block_seconds)
                    continue
                # 显式限速到约 20fps：多出来的数据直接丢弃，不做 FFT
                now = time.monotonic()
                if last_emit and (now - last_emit) < self._block_seconds:
                    self._stop_event.wait(self._block_seconds - (now - last_emit))
                    continue
                read_frames = min(frames, available)
                try:
                    data = stream.read(read_frames, exception_on_overflow=False)
                except Exception as e:
                    self._fail(REASON_RUNTIME_ERROR, f'读取音频流失败: {e}')
                    return
                if not data:
                    now = time.monotonic()
                    no_data_reads += 1
                    if no_data_since <= 0.0:
                        no_data_since = now
                    if (no_data_reads >= INVALID_FRAME_LIMIT
                            or (now - no_data_since) >= self._no_data_seconds):
                        self._fail(REASON_INVALID_DATA, '连续读到空音频块')
                        return
                    continue
                no_data_reads = 0
                no_data_since = 0.0
                last_emit = time.monotonic()
                levels = compute_spectrum_levels(
                    data, channels, rate, self._bar_count, self._fft_size)
                self._apply_smoothing(levels)
                self.bars_ready.emit(list(self._smooth))
        except ImportError as e:
            self._fail(REASON_MISSING_DEPENDENCY, str(e))
        except _BackendError as e:
            self._fail(e.reason, e.detail)
        except Exception as e:
            self._fail(REASON_RUNTIME_ERROR, str(e))
        finally:
            self._release()
            self._stop_event.set()

    def _apply_smoothing(self, levels):
        """上升立即跟随，下降做指数平滑，避免柱子抖动。"""
        smooth = self._smooth
        for index, raw in enumerate(levels):
            if raw != raw:  # NaN
                raw = 0.0
            raw = 0.0 if raw < 0.0 else (1.0 if raw > 1.0 else float(raw))
            previous = smooth[index]
            if raw >= previous:
                smooth[index] = raw
            else:
                smooth[index] = previous * 0.72 + raw * 0.28

    # ---- 失败与超时 ----
    def _fail(self, reason, detail=''):
        if self._failed:
            return
        self._failed = True
        self._fail_reason = reason if reason in REASON_CODES else REASON_RUNTIME_ERROR
        self._last_error = f'{reason}:{detail}' if detail else reason
        self._stop_event.set()
        if detail:
            logger.debug(f"[spectrum] 采集失败 reason={self._fail_reason} detail={detail}")
        self.failed.emit(self._fail_reason)

    def _on_init_timeout(self):
        with self._lock:
            ready = self._ready
        if ready or self._failed:
            return
        self._fail(REASON_INIT_TIMEOUT, f'初始化超过 {self._init_timeout_ms}ms')

    def _on_stream_opened(self):
        try:
            self._init_timer.stop()
        except Exception:
            pass
