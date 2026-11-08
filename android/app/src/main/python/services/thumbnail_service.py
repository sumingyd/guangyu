import hashlib
import os
import sys
import threading
import time
from collections import deque
from typing import Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
from utils.general_utils import build_mpv_http_header_fields
from services.mpv_common import (
    MPV_EVENT_FILE_LOADED,
    MPV_EVENT_END_FILE,
    create_mpv_handle,
    initialize_mpv,
    destroy_mpv,
    set_option_string as _mpv_set_option_string,
    send_command as _mpv_send_command,
    wait_for_specific_event,
    _is_mpv_available,
)

# Android Chaquopy 环境：优先使用 IPTV_DATA_DIR（已指向 ISEP 目录）下的 cache 目录
from utils.app_paths import get_cache_dir
from core.log_manager import global_logger as logger
CACHE_DIR = os.path.join(get_cache_dir(), 'thumbnails')


def _url_to_thumb_path(url: str) -> str:
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f"{url_hash}.png")


def has_thumbnail(url: str) -> bool:
    if not url:
        return False
    return os.path.exists(_url_to_thumb_path(url))


def is_thumbnail_stale(url: str, max_age_minutes: int = 1440) -> bool:
    if not url:
        return False
    path = _url_to_thumb_path(url)
    if not os.path.exists(path):
        return True
    try:
        mtime = os.path.getmtime(path)
        age_minutes = (time.time() - mtime) / 60
        return age_minutes > max_age_minutes
    except Exception:
        return False


def get_thumbnail_path(url: str) -> Optional[str]:
    if not url:
        return None
    path = _url_to_thumb_path(url)
    if os.path.exists(path):
        return path
    return None


def _capture_single(url: str, timeout: int = 8, wid: int = 0, force: bool = False) -> Optional[str]:
    if not _is_mpv_available():
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    thumb_path = _url_to_thumb_path(url)
    if os.path.exists(thumb_path) and not force:
        return thumb_path

    handle = None
    try:
        handle = create_mpv_handle()
        if not handle:
            return None

        if wid:
            _mpv_set_option_string(handle, 'wid', str(wid))
        _mpv_set_option_string(handle, 'vo', 'gpu')
        _mpv_set_option_string(handle, 'ao', 'null')
        if sys.platform == 'win32':
            _mpv_set_option_string(handle, 'gpu-api', 'd3d11')
            _mpv_set_option_string(handle, 'hwdec', 'd3d11va')
        elif sys.platform.startswith('linux'):
            # 程序在 Linux 上强制使用 xcb(XWayland)，缩略图 VO 也必须走 X11 context，
            # 否则 gpu VO 会因找不到可用的 GPU context 直接失败、取不到帧。
            _mpv_set_option_string(handle, 'gpu-context', 'x11')
            _mpv_set_option_string(handle, 'hwdec', 'auto')
        else:
            _mpv_set_option_string(handle, 'hwdec', 'auto')
        _mpv_set_option_string(handle, 'osc', 'no')
        _mpv_set_option_string(handle, 'osd-bar', 'no')
        _mpv_set_option_string(handle, 'idle', 'yes')
        _mpv_set_option_string(handle, 'ytdl', 'no')
        _mpv_set_option_string(handle, 'keep-open', 'yes')
        _mpv_set_option_string(handle, 'log-level', 'error')
        _mpv_set_option_string(handle, 'config', 'no')
        _mpv_set_option_string(handle, 'force-window', 'no')

        u = url.lower()
        if u.startswith('rtsp://'):
            try:
                from core.config_manager import ConfigManager
                cfg = ConfigManager()
                playback = cfg.load_playback_settings()
                rtsp_transport = playback.get('rtsp_transport', 'tcp')
            except Exception:
                rtsp_transport = 'tcp'
            _mpv_set_option_string(handle, 'rtsp-transport', rtsp_transport)
        elif '/rtp/' in u or u.endswith('.ts') or u.startswith('udp://'):
            _mpv_set_option_string(handle, 'demuxer-lavf-format', 'mpegts')

        try:
            from services.ffprobe_validator_service import FfprobeStreamValidator
            headers = FfprobeStreamValidator.get_headers()
            if headers:
                header_val = build_mpv_http_header_fields(
                    '\n'.join(f'{k}: {v}' for k, v in headers.items())
                )
                if header_val:
                    _mpv_set_option_string(handle, 'http-header-fields', header_val)
        except Exception as e:
            logger.debug(f"设置 HTTP headers 失败: {e}")

        if not initialize_mpv(handle):
            destroy_mpv(handle)
            return None

        _mpv_send_command(handle, ['loadfile', url])

        event_id, _, _ = wait_for_specific_event(handle, timeout, {MPV_EVENT_FILE_LOADED, MPV_EVENT_END_FILE})

        if event_id == MPV_EVENT_FILE_LOADED:
            wait_for_specific_event(handle, 2, {MPV_EVENT_END_FILE})

            _mpv_send_command(handle, ['screenshot-to-file', thumb_path, 'video'])

            for _ in range(50):
                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                    return thumb_path
                time.sleep(0.05)

            return None

        return None
    except Exception:
        return None
    finally:
        if handle:
            destroy_mpv(handle)


class ThumbnailService(QObject):
    thumbnail_ready = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hidden_widget = QWidget()
        self._hidden_widget.resize(320, 180)
        self._hidden_winid = int(self._hidden_widget.winId())
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._running = False

    def capture_channels(self, channels: list, force: bool = False):
        added = False
        need_start = False
        with self._lock:
            existing_urls = {url for _, url, _ in self._queue}
            for ch in channels:
                url = ch.get('url', '')
                name = ch.get('name', '')
                if not url or url in existing_urls:
                    continue
                if force:
                    if is_thumbnail_stale(url) or not has_thumbnail(url):
                        self._queue.append((name, url, True))
                        existing_urls.add(url)
                        added = True
                else:
                    if not has_thumbnail(url):
                        self._queue.append((name, url, False))
                        existing_urls.add(url)
                        added = True
            if added and not self._running:
                self._stop_event.clear()
                self._running = True
                need_start = True
        if need_start:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        with self._lock:
            self._queue.clear()

    def _worker(self):
        while not self._stop_event.is_set():
            with self._lock:
                if not self._queue:
                    self._running = False
                    break
                name, url, force = self._queue.popleft()
            try:
                result = _capture_single(url, timeout=8, wid=self._hidden_winid, force=force)
                if result and not self._stop_event.is_set():
                    try:
                        self.thumbnail_ready.emit(name, url)
                    except RuntimeError:
                        pass
            except Exception as e:
                logger.debug(f"缩略图生成失败: {e}")

