import json
import os
import threading
import time
from typing import Dict
from core.log_manager import global_logger
from utils.general_utils import build_mpv_http_header_fields
from services.mpv_common import (
    MPV_EVENT_FILE_LOADED,
    MPV_EVENT_END_FILE,
    MPV_EVENT_VIDEO_RECONFIG,
    MPV_EVENT_SHUTDOWN,
    MPV_END_FILE_REASON_EOF,
    MPV_END_FILE_REASON_STOP,
    MPV_END_FILE_REASON_ERROR,
    mpv_event_end_file,
    create_mpv_handle,
    initialize_mpv,
    destroy_mpv,
    terminate_destroy_mpv,
    set_property_string as _mpv_set_property_string,
    set_option_string as _mpv_set_option_string,
    send_command as _mpv_send_command,
    DEFAULT_NETWORK_TIMEOUT_SEC,
    wait_for_specific_event,
    wait_for_event,
    get_property_string as _mpv_get_property_string,
    get_property_int as _mpv_get_property_int,
    _is_mpv_available,
)


def get_optimal_thread_count():
    cpu = os.cpu_count() or 4
    return min(max(cpu, 4), 32)


def _create_lightweight_mpv():
    if not _is_mpv_available():
        return None
    try:
        handle = create_mpv_handle()
        if not handle:
            return None
        _mpv_set_option_string(handle, 'vo', 'null')
        _mpv_set_option_string(handle, 'ao', 'null')
        _mpv_set_option_string(handle, 'hwdec', 'no')
        _mpv_set_option_string(handle, 'osc', 'no')
        _mpv_set_option_string(handle, 'osd-bar', 'no')
        _mpv_set_option_string(handle, 'idle', 'yes')
        _mpv_set_option_string(handle, 'ytdl', 'no')
        _mpv_set_option_string(handle, 'keep-open', 'yes')
        _mpv_set_option_string(handle, 'log-level', 'fatal')
        _mpv_set_option_string(handle, 'config', 'no')
        _mpv_set_option_string(handle, 'demuxer-lavf-probesize', '1048576')
        _mpv_set_option_string(handle, 'demuxer-lavf-analyzeduration', '5')
        _mpv_set_option_string(handle, 'cache', 'yes')
        _mpv_set_option_string(handle, 'cache-secs', '10')
        _mpv_set_option_string(handle, 'demuxer-max-bytes', '16MiB')
        _mpv_set_option_string(handle, 'demuxer-max-back-bytes', '8MiB')
        _mpv_set_option_string(handle, 'tls-verify', 'no')

        try:
            from core.config_manager import ConfigManager
            playback = ConfigManager().load_playback_settings()
        except Exception:
            playback = {}

        net_timeout = playback.get('network_timeout_sec', 0)
        if not net_timeout or net_timeout <= 0:
            net_timeout = DEFAULT_NETWORK_TIMEOUT_SEC
        _mpv_set_option_string(handle, 'network-timeout', str(net_timeout))

        user_agent = MpvStreamValidator.get_user_agent()
        if not user_agent:
            user_agent = playback.get('user_agent', '')
        if user_agent:
            _mpv_set_option_string(handle, 'user-agent', user_agent)

        http_headers = playback.get('http_headers', '')
        referer = MpvStreamValidator.get_referer()
        header_val = build_mpv_http_header_fields(http_headers, referer)
        if header_val:
            _mpv_set_option_string(handle, 'http-header-fields', header_val)

        if not initialize_mpv(handle):
            destroy_mpv(handle)
            return None
        return handle
    except Exception:
        return None


def _try_get_resolution_and_codec(handle, retries=3, interval=0.3):
    resolution = None
    codec = None
    for _ in range(retries):
        w = _mpv_get_property_int(handle, 'width')
        h = _mpv_get_property_int(handle, 'height')
        if w and h and w > 0 and h > 0:
            resolution = f"{w}x{h}"
            break
        time.sleep(interval)
    codec = _mpv_get_property_string(handle, 'video-codec') or None
    return resolution, codec


def _try_get_hdr_type(handle, retries=3, interval=0.3):
    """从 mpv 属性提取 HDR 类型（与 detect_hdr_type 统一逻辑）。

    mpv 运行时无法检测 HDR10+（ST.2094-40 不暴露为属性），
    统一返回 HDR10。HDR10+ 仅在 ffprobe 扫描阶段通过 side_data 检测。
    """
    for _ in range(retries):
        gamma = _mpv_get_property_string(handle, 'video-params/gamma') or ''
        if gamma:
            break
        time.sleep(interval)
    cm = _mpv_get_property_string(handle, 'video-params/colormatrix') or ''
    prim = _mpv_get_property_string(handle, 'video-params/primaries') or ''
    vf = _mpv_get_property_string(handle, 'video-format') or ''
    try:
        sig_peak = float(_mpv_get_property_string(handle, 'video-params/sig-peak') or '0')
    except (ValueError, TypeError):
        sig_peak = 0.0
    # 复用统一的 detect_hdr_type 逻辑
    from services.mpv_player_service import MpvPlayerController
    return MpvPlayerController.detect_hdr_type(cm, gamma, sig_peak, vf, prim)


class MpvStreamValidator:
    _semaphore: threading.Semaphore = threading.Semaphore(get_optimal_thread_count())
    _user_agent: str | None = None
    _referer: str | None = None
    _headers_lock = threading.Lock()
    _active_handles: list = []
    _handles_lock = threading.Lock()
    _terminating = False

    @classmethod
    def _get_semaphore(cls) -> threading.Semaphore:

        return cls._semaphore

    def __init__(self, main_window=None):
        self.logger = global_logger
        self.main_window = main_window

    def validate_stream(self, url: str, raw_channel_name: str | None = None, timeout: int = 3) -> Dict:
        result = {
            'url': url,
            'valid': False,
            'latency': None,
            'error': None,
            'error_type': None,
            'service_name': None,
            'resolution': None,
            'codec': None,
            'bitrate': None,
            'hdr_type': None,
        }

        if not _is_mpv_available():
            result['error'] = 'mpv不可用'
            result['error_type'] = 'mpv_unavailable'
            return result

        if self._terminating:
            result['error'] = '验证器正在关闭'
            result['error_type'] = 'terminating'
            return result

        sem = self._get_semaphore()
        acquired = False
        for _ in range(60):
            if self._terminating:
                result['error'] = '验证器正在关闭'
                result['error_type'] = 'terminating'
                return result
            acquired = sem.acquire(timeout=0.5)
            if acquired:
                break

        if not acquired:
            result['error'] = '并发数超限'
            result['error_type'] = 'concurrency_limit'
            return result

        handle = None
        try:
            handle = _create_lightweight_mpv()
            if not handle:
                result['error'] = '创建mpv实例失败'
                result['error_type'] = 'mpv_create_failed'
                return result

            u = url.lower()
            looks_ts = '/rtp/' in u or u.endswith('.ts') or 'proto=http' in u or u.startswith('udp://')
            if u.startswith('rtsp://'):
                rtsp_transport = 'tcp'
                try:
                    from core.config_manager import ConfigManager
                    cfg = ConfigManager()
                    playback = cfg.load_playback_settings()
                    rtsp_transport = playback.get('rtsp_transport', 'tcp')
                except Exception as e:
                    logger.debug(f"validate_stream: {e}")
                _mpv_set_property_string(handle, 'rtsp-transport', rtsp_transport)
                _mpv_set_property_string(handle, 'demuxer', 'lavf')
                _mpv_set_property_string(handle, 'force-seekable', 'yes')
            elif looks_ts:
                _mpv_set_property_string(handle, 'demuxer', 'lavf')
                _mpv_set_property_string(handle, 'demuxer-lavf-format', 'mpegts')
                _mpv_set_property_string(handle, 'force-seekable', 'yes')
            elif u.startswith('http://') or u.startswith('https://'):
                _mpv_set_property_string(handle, 'force-seekable', 'yes')

            start_time = time.time()

            _mpv_send_command(handle, ['loadfile', url])

            with self._handles_lock:
                self._active_handles.append(handle)

            found_tracks = False
            found_tracks_time = 0.0
            event_id = 0
            event_data = None
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._terminating:
                    result['error'] = '验证器正在关闭'
                    result['error_type'] = 'terminating'
                    break
                evt = wait_for_event(handle, 0.05)
                if evt:
                    eid = evt.event_id
                    if eid in (MPV_EVENT_FILE_LOADED, MPV_EVENT_END_FILE):
                        event_id = eid
                        event_data = evt.data
                        break
                    if eid == MPV_EVENT_SHUTDOWN:
                        event_id = MPV_EVENT_SHUTDOWN
                        break
                if not found_tracks:
                    try:
                        tl = _mpv_get_property_string(handle, 'track-list')
                        if tl and '"id"' in tl:
                            tracks = json.loads(tl)
                            if len(tracks) > 0:
                                found_tracks = True
                                found_tracks_time = time.time()
                    except Exception as e:
                        logger.debug(f"validate_stream: {e}")
                else:
                    if found_tracks_time > 0 and (time.time() - found_tracks_time) > 1.5:
                        break

            latency = int((time.time() - start_time) * 1000)

            if found_tracks:
                result['valid'] = True
                result['latency'] = latency
                wait_for_specific_event(
                    handle, 2.0,
                    {MPV_EVENT_VIDEO_RECONFIG, MPV_EVENT_END_FILE}
                )
                res, codec = _try_get_resolution_and_codec(handle)
                if res:
                    result['resolution'] = res
                if codec:
                    result['codec'] = codec
                result['hdr_type'] = _try_get_hdr_type(handle)
                try:
                    from models.channel_mappings import extract_channel_name_from_url
                    result['service_name'] = extract_channel_name_from_url(url)
                except Exception:
                    result['service_name'] = ''

            elif event_id == MPV_EVENT_FILE_LOADED:
                result['valid'] = True
                result['latency'] = latency

                wait_for_specific_event(
                    handle, min(timeout, 3),
                    {MPV_EVENT_VIDEO_RECONFIG, MPV_EVENT_END_FILE}
                )

                res, codec = _try_get_resolution_and_codec(handle)
                if res:
                    result['resolution'] = res
                if codec:
                    result['codec'] = codec
                result['hdr_type'] = _try_get_hdr_type(handle)

                try:
                    from models.channel_mappings import extract_channel_name_from_url
                    result['service_name'] = extract_channel_name_from_url(url)
                except Exception:
                    result['service_name'] = ''

            elif event_id == MPV_EVENT_END_FILE:
                result['latency'] = latency
                end_reason = None
                end_error = 0
                if event_data:
                    try:
                        import ctypes as _ctypes
                        end_file = _ctypes.cast(event_data, _ctypes.POINTER(mpv_event_end_file)).contents
                        end_reason = end_file.reason
                        end_error = end_file.error
                    except Exception as e:
                        logger.debug(f"validate_stream: {e}")

                if end_reason in (MPV_END_FILE_REASON_EOF, MPV_END_FILE_REASON_STOP):
                    result['valid'] = True
                    res, codec = _try_get_resolution_and_codec(handle, retries=2, interval=0.2)
                    if res:
                        result['resolution'] = res
                    if codec:
                        result['codec'] = codec
                elif end_reason == MPV_END_FILE_REASON_ERROR:
                    if found_tracks:
                        result['valid'] = True
                        result['error'] = f'播放警告(vo=null,END_FILE错误码:{end_error})'
                        result['error_type'] = 'playback_warning'
                        res, codec = _try_get_resolution_and_codec(handle, retries=2, interval=0.2)
                        if res:
                            result['resolution'] = res
                        if codec:
                            result['codec'] = codec
                    else:
                        try:
                            tl = _mpv_get_property_string(handle, 'track-list')
                            if tl and '"id"' in tl:
                                tracks = json.loads(tl)
                                if len(tracks) > 0:
                                    found_tracks = True
                        except Exception as e:
                            logger.debug(f"validate_stream: {e}")
                        if found_tracks:
                            result['valid'] = True
                            result['error'] = f'播放警告(vo=null,END_FILE错误码:{end_error})'
                            result['error_type'] = 'playback_warning'
                            res, codec = _try_get_resolution_and_codec(handle, retries=2, interval=0.2)
                            if res:
                                result['resolution'] = res
                            if codec:
                                result['codec'] = codec
                        else:
                            result['valid'] = False
                            result['error'] = f'播放失败(错误码:{end_error})'
                            result['error_type'] = 'playback_failed'
                else:
                    result['valid'] = False
                    if end_reason is not None:
                        result['error'] = f'流结束(reason:{end_reason})'
                        result['error_type'] = 'stream_ended'
                    else:
                        result['error'] = '流结束'
                        result['error_type'] = 'stream_ended'

            else:
                result['valid'] = False
                result['latency'] = latency
                result['error'] = f'超时({timeout}秒)'
                result['error_type'] = 'timeout'

        except Exception as e:
            global_logger.debug(f"mpv 验证未知异常: {e}")
            result['error'] = '内部错误'
            result['error_type'] = 'unknown_error'
        finally:
            if handle:
                with self._handles_lock:
                    was_active = handle in self._active_handles
                    if was_active:
                        self._active_handles.remove(handle)
                if was_active:
                    try:
                        terminate_destroy_mpv(handle)
                    except Exception as e:
                        logger.debug(f"validate_stream: {e}")
            sem.release()

        if not result.get('valid', False):
            global_logger.debug(
                f"验证无效: {url} | "
                f"latency={result.get('latency', 0)}ms | "
                f"error_type={result.get('error_type', 'unknown')} | "
                f"error={result.get('error', '')}"
            )

        return result

    @classmethod
    def set_max_concurrent(cls, max_count):
        cls._semaphore = threading.Semaphore(max(1, max_count))

    @classmethod
    def set_user_agent(cls, user_agent: str):
        with cls._headers_lock:
            cls._user_agent = user_agent if user_agent else None

    @classmethod
    def set_referer(cls, referer: str):
        with cls._headers_lock:
            cls._referer = referer if referer else None

    @classmethod
    def get_headers(cls) -> dict:
        with cls._headers_lock:
            headers = {}
            if cls._user_agent:
                headers['user-agent'] = cls._user_agent
            if cls._referer:
                headers['referer'] = cls._referer
            return headers

    @classmethod
    def get_user_agent(cls) -> str | None:
        with cls._headers_lock:
            return cls._user_agent

    @classmethod
    def get_referer(cls) -> str | None:
        with cls._headers_lock:
            return cls._referer

    @classmethod
    def terminate_all(cls):
        cls._terminating = True
        with cls._handles_lock:
            handles_to_destroy = list(cls._active_handles)
            cls._active_handles.clear()
        for handle in handles_to_destroy:
            try:
                terminate_destroy_mpv(handle)
            except Exception as e:
                logger.debug(f"terminate_all: {e}")

    @classmethod
    def set_terminating(cls):
        """仅设置终止标志，不销毁句柄（用于安全停止）"""
        cls._terminating = True

    @classmethod
    def destroy_all_handles(cls):
        """销毁所有活跃mpv句柄（应在工作线程退出后调用）"""
        with cls._handles_lock:
            handles_to_destroy = list(cls._active_handles)
            cls._active_handles.clear()
        for handle in handles_to_destroy:
            try:
                terminate_destroy_mpv(handle)
            except Exception as e:
                logger.debug(f"destroy_all_handles: {e}")

    @classmethod
    def reset_terminating(cls):
        cls._terminating = False
