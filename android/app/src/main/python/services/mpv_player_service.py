import os
import json
import ctypes
import threading
from PySide6.QtCore import QObject, Signal, QTimer
from core.log_manager import global_logger
from utils.platform_utils import is_windows, is_macos, is_linux, is_android, get_android_data_dir
from services.mpv_common import (
    mpv_event,
    mpv_event_end_file,
    mpv_event_property,
    mpv_event_log_message,
    MPV_EVENT_NONE,
    MPV_EVENT_END_FILE,
    MPV_EVENT_FILE_LOADED,
    MPV_EVENT_PROPERTY_CHANGE,
    MPV_EVENT_LOG_MESSAGE,
    MPV_FORMAT_STRING,
    MPV_FORMAT_FLAG,
    MPV_END_FILE_REASON_EOF,
    MPV_END_FILE_REASON_ERROR,
    MPV_END_FILE_REASON_STOP,
    MPV_END_FILE_REASON_QUIT,
    get_property_string as _mpv_get_property_string,
    get_property_int as _mpv_get_property_int,
    get_property_double as _mpv_get_property_double,
    create_mpv_handle,
    initialize_mpv,
    destroy_mpv,
    terminate_destroy_mpv,
    set_property_string as _mpv_set_property_string,
    set_property_int64 as _mpv_set_property_int64,
    set_option_string as _mpv_set_option_string,
    send_command as _mpv_send_command,
    observe_property as _mpv_observe_property,
    get_property_node as _mpv_get_property_node,
)

from services.mpv_common import _ensure_env_initialized, DEFAULT_USER_AGENT
from services.mpv_playback import MpvPlayback
from services.mpv_hdr import MpvHdr
from services.mpv_video_eq import MpvVideoEq
from services.mpv_audio_eq import MpvAudioEq
from services.mpv_filter import MpvFilter
from services.mpv_subtitle import MpvSubtitle
from services.mpv_shader import MpvShader

try:
    _ensure_env_initialized()
    import mpv
except ImportError as _e:
    import logging as _logging
    _logging.getLogger('services.mpv_player_service').warning(
        f"python-mpv 模块导入失败（非致命，libmpv 直接调用仍可用）: {_e}"
    )
    mpv = None
except Exception as _e:
    import logging as _logging
    _logging.getLogger('services.mpv_player_service').warning(
        f"python-mpv 模块导入异常: {_e}"
    )
    mpv = None

VIDEO_CODEC_MAP = {
    'h264': 'H.264', 'avc1': 'H.264', 'h265': 'H.265', 'hevc': 'H.265',
    'vp9': 'VP9', 'vp8': 'VP8', 'av01': 'AV1', 'mpeg': 'MPEG-2',
    'mp2v': 'MPEG-2', 'mp4v': 'MPEG-4', 'divx': 'DivX', 'xvid': 'XviD',
    'wmv3': 'WMV3', 'wmv2': 'WMV2', 'wmv1': 'WMV1', 'theo': 'Theora',
    'flv1': 'FLV', 'rv40': 'RealVideo 4', 'rv30': 'RealVideo 3',
    '462h': 'H.264', '462H': 'H.264', 'avc3': 'H.264',
    'hvc1': 'H.265', 'hev1': 'H.265', 'vp09': 'VP9', 'av00': 'AV1',
}

AUDIO_CODEC_MAP = {
    'aac': 'AAC', 'mp3': 'MP3', 'mp2': 'MP2', 'mp1': 'MP1',
    'ac3': 'AC-3', 'eac3': 'E-AC-3', 'dts': 'DTS', 'dtsh': 'DTS-HD',
    'opus': 'Opus', 'vorb': 'Vorbis', 'flac': 'FLAC', 'alac': 'ALAC',
    'wma': 'WMA', 'pcm': 'PCM', 'twos': 'PCM', 'sowt': 'PCM', 'lpcm': 'PCM',
    'agpm': 'AAC', 'aacp': 'AAC+', 'aach': 'AAC-HE', 'mp4a': 'AAC',
    'ac-3': 'AC-3', 'dtsc': 'DTS', 'dtse': 'DTS-HD Master Audio',
    'truehd': 'TrueHD',
}

def _load_playback_settings():
    settings = {
        'hwdec': 'auto-copy',
        'cache_secs': 1.0,
        'demuxer_max_bytes_mib': 16,
        'demuxer_max_back_bytes_mib': 4,
        'fcc_prefetch_count': 2,
        'enable_protocol_adaptive': True,
        'hls_start_at_live_edge': False,
        'hls_readahead_secs': 0,
        'user_agent': DEFAULT_USER_AGENT,
        'tls_verify': False,
        'http_headers': '',
        'rtsp_transport': 'tcp',
        'rtsp_user_agent': 'VLC/3.0.18Libmpv',
        'network_timeout_sec': 30,
        'audio_passthrough': 'never',
        'http_referer': '',
        'http_proxy': '',
        # 高级播放器参数（与安卓端 PlayerSettingsPanel 对齐）
        'vo': 'auto',
        'gpu_api': 'auto',
        'video_sync': 'audio',
        'framedrop': 'vo',
        'cache_secs_override': 0,
        'demuxer_readahead_secs_override': 0,
        'demuxer_max_bytes_mib_override': 0,
        'deinterlace': 'no',
        'probesize_override': 0,
        'analyzeduration_override': 0,
    }
    try:
        from core.config_manager import ConfigManager
        config = ConfigManager()
        s = config.load_playback_settings()
        settings.update(s)
    except Exception as e:
        import logging as _logging
        _logging.getLogger('services.mpv_player_service').warning(
            f"加载播放设置失败，使用默认值: {e}"
        )
    return settings


class MpvPlayerController(QObject):

    play_state_changed = Signal(bool)
    play_error = Signal(str)
    reconnect_requested = Signal(str)
    timeshift_continue_requested = Signal()
    live_media_info_updated = Signal(dict)
    playback_position_updated = Signal(int, int, float)
    logo_cache_loaded = Signal(str, object)
    thumbnail_captured = Signal(str)
    file_loaded = Signal()
    local_file_ended = Signal(str)
    # 本地文件结束时需保存播放位置：参数 (url, position_sec, duration_sec)
    local_file_position_to_save = Signal(str, float, float)

    _MC_PRESETS = {
        'off': None,
        'low': 'mi_mode=blend',
        'medium': 'mi_mode=mci:mc_mode=obmc:me=dsr',
        'high': 'mi_mode=mci:mc_mode=aobmc:me=hexbs',
    }

    _SCALE_OPTIONS = ('bilinear', 'bicubic', 'lanczos', 'spline', 'ewa_lanczos', 'ewa_lanczossharp')

    _STEREO_MODES = ('mono', 'sbs', 'sbs2', 'ab', 'ab2')

    _SHADER_PRESET_FILES = {
        'ravu': ['ravu_r3.hook'],
        'fsrcnnx': ['FSRCNNX_x2_8-0-4-1.glsl'],
        'anime4k': [
            'Anime4K_Clamp_Highlights.glsl',
            'Anime4K_Restore_CNN_S.glsl',
            'Anime4K_Upscale_CNN_x2_S.glsl',
        ],
        'krig': ['KrigBilateral.hook'],
        'ssim': ['SSimDownscaler.glsl'],
        'esrgan': [
            'ravu_r4.hook',
            'FSRCNNX_x2_8-0-4-1.glsl',
            'adaptive_sharpen.glsl',
        ],
        'adaptive_sharpen': ['adaptive_sharpen.glsl'],
    }

    _STATIC_INFO_REFRESH_TICKS = 10

    def __init__(self, video_widget, channel_model=None):
        super().__init__()
        self.logger = global_logger
        self._lock = threading.RLock()
        self.video_widget = video_widget
        self.channel_model = channel_model
        self.mpv_handle = None
        self.is_playing = False
        self.is_paused = False
        self.current_url = None
        self.media_info = {}
        self.event_timer = None
        self._playback_settings = _load_playback_settings()
        self._current_speed = 1.0
        # 当前画面比例（'default'/'16:9'/'4:3'/'stretch'/'fill'/'crop'）
        # set_aspect_ratio 写入，get_aspect_ratio 读出
        self._current_aspect_ratio = 'default'
        self._live_info_timer = None
        self._last_volume = 80
        self._reconnect_count = 0
        self._max_reconnect = 3
        self._user_stopped = False
        self._switching_channel = False
        self._mpv_initialized = False
        self._use_render_api = False
        self._terminated = False
        from services.audio_visual_service import AudioVisualService
        self.audio_visual = AudioVisualService(self)
        self._playback = MpvPlayback(self)
        self._hdr = MpvHdr(self)
        self._video_eq = MpvVideoEq(self)
        self._audio_eq = MpvAudioEq(self)
        self._filter = MpvFilter(self)
        self._subtitle = MpvSubtitle(self)
        self._shader = MpvShader(self)

    def _ensure_mpv_initialized(self):
        return self._playback._ensure_mpv_initialized()

    def _safe_emit(self, signal, *args):
        if self._terminated:
            return
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def _get_sdr_target_trc(self):
        return self._hdr._get_sdr_target_trc()

    def _apply_tonemap_config(self, is_hlg=False):
        return self._hdr._apply_tonemap_config(is_hlg)

    def _apply_passthrough_config(self, is_pq=True):
        return self._hdr._apply_passthrough_config(is_pq)

    def _apply_scrgb_config(self, is_pq=True):
        return self._hdr._apply_scrgb_config(is_pq)

    def _apply_wcg_config(self):
        return self._hdr._apply_wcg_config()

    def _reset_hdr_params(self):
        return self._hdr._reset_hdr_params()

    def _set_mpv_string(self, name, value):
        if self._terminated or not self.mpv_handle:
            return -1
        return _mpv_set_property_string(self.mpv_handle, name, str(value))

    def _set_cache_param(self, name, value):
        """设置缓存相关参数（cache-secs / demuxer-max-bytes / demuxer-readahead-secs）。

        与 _set_mpv_string 的区别：用户在订阅设置中配置了 override(>0) 时，
        用 override 替换动态计算值。_reset_demuxer_options 中的清空操作
        不经过此方法，因此 override 不会破坏重置逻辑。
        """
        if self._terminated or not self.mpv_handle:
            return -1
        s = self._playback_settings
        try:
            if name == 'cache-secs':
                ov = float(s.get('cache_secs_override', 0) or 0)
                if ov > 0:
                    value = str(int(ov))
            elif name == 'demuxer-max-bytes':
                ov = float(s.get('demuxer_max_bytes_mib_override', 0) or 0)
                if ov > 0:
                    value = f'{int(ov)}MiB'
            elif name == 'demuxer-readahead-secs':
                ov = float(s.get('demuxer_readahead_secs_override', 0) or 0)
                if ov > 0:
                    value = str(int(ov))
        except (TypeError, ValueError):
            pass
        return _mpv_set_property_string(self.mpv_handle, name, str(value))

    def _is_network_url(self, url):
        return self._playback._is_network_url(url)

    def _is_network_drive(self, path):
        return self._playback._is_network_drive(path)

    def _fix_unc_path(self, path):
        return self._playback._fix_unc_path(path)

    @staticmethod
    def _detect_bdmv_path(path):
        return MpvPlayback._detect_bdmv_path(path)

    def _normalize_url(self, url):
        return self._playback._normalize_url(url)

    def _apply_hdr_on_file_loaded(self):
        return self._hdr._apply_hdr_on_file_loaded()

    def _reset_demuxer_options(self):
        return self._playback._reset_demuxer_options()

    def _adjust_buffer_for_content(self):
        return self._playback._adjust_buffer_for_content()

    def _setup_bluray_options(self):
        return self._playback._setup_bluray_options()

    def _setup_network_drive_options(self):
        return self._playback._setup_network_drive_options()

    def _setup_protocol_options(self, url, program_duration=0):
        return self._playback._setup_protocol_options(url, program_duration)

    def _process_events(self):
        return self._playback._process_events()

    def play(self, url, channel_name=None, program_duration=0, **kwargs):
        return self._playback.play(url, channel_name, program_duration, **kwargs)

    def play_with_prefetch(self, url, next_urls=None, program_duration=0):
        return self._playback.play_with_prefetch(url, next_urls, program_duration)

    def _prefetch_next_channels(self, next_urls):
        return self._playback._prefetch_next_channels(next_urls)

    def stop(self):
        return self._playback.stop()

    def terminate(self):
        return self._playback.terminate()

    def reinit_for_hdr_change(self, new_hdr_mode):
        return self._playback.reinit_for_hdr_change(new_hdr_mode)

    def pause(self):
        return self._playback.pause()

    def set_volume(self, volume):
        return self._playback.set_volume(volume)

    def get_volume(self):
        return self._playback.get_volume()

    def set_speed(self, speed):
        return self._playback.set_speed(speed)

    def get_speed(self):
        return self._playback.get_speed()

    def set_aspect_ratio(self, ratio):
        return self._playback.set_aspect_ratio(ratio)

    def get_aspect_ratio(self) -> str:
        return self._playback.get_aspect_ratio()

    def set_mute(self, muted):
        return self._playback.set_mute(muted)

    def get_mute(self):
        return self._playback.get_mute()

    def get_current_time(self):
        return self._playback.get_current_time()

    def get_total_time(self):
        return self._playback.get_total_time()

    def get_position(self):
        return self._playback.get_position()

    def get_timeshift_range(self):
        return self._playback.get_timeshift_range()

    def seek_absolute(self, target_seconds):
        return self._playback.seek_absolute(target_seconds)

    def seek(self, position):
        return self._playback.seek(position)

    def seek_relative_seconds(self, seconds):
        return self._playback.seek_relative_seconds(seconds)

    def get_live_media_info(self):
        return self._playback.get_live_media_info()

    def _start_live_info_timer(self):
        return self._playback._start_live_info_timer()

    def _stop_live_info_timer(self):
        return self._playback._stop_live_info_timer()

    def _update_live_info(self):
        return self._playback._update_live_info()

    def _schedule_media_info_start(self):
        return self._playback._schedule_media_info_start()

    def _has_video_track(self):
        return self._playback._has_video_track()

    def _capture_thumbnail(self):
        return self._playback._capture_thumbnail()

    def _check_thumbnail_saved(self, filepath):
        return self._playback._check_thumbnail_saved(filepath)

    def get_thumbnail_path(self, url):
        return self._playback.get_thumbnail_path(url)

    def _guess_protocol(self, url):
        return self._playback._guess_protocol(url)

    def _get_mpv_property_string(self, property_name):
        if self._terminated:
            return None
        with self._lock:
            if not self.mpv_handle:
                return None
            return _mpv_get_property_string(self.mpv_handle, property_name)

    def _get_mpv_error_string(self, error_code):
        try:
            from services.mpv_common import libmpv as _libmpv
            if hasattr(_libmpv, 'mpv_error_string'):
                error_str = _libmpv.mpv_error_string(error_code)
                if error_str:
                    return error_str.decode('utf-8')
        except Exception as _e:
            global_logger.debug(f"unexpected error: {_e}")
        return f"错误码: {error_code}"

    def _get_mpv_property_int(self, property_name):
        if self._terminated:
            return None
        with self._lock:
            if not self.mpv_handle:
                return None
            return _mpv_get_property_int(self.mpv_handle, property_name)

    def _get_mpv_property_double(self, property_name):
        if self._terminated:
            return None
        with self._lock:
            if not self.mpv_handle:
                return None
            return _mpv_get_property_double(self.mpv_handle, property_name)

    def get_video_resolution(self):
        return self._playback.get_video_resolution()

    def ensure_ready_for_load(self):
        return self._playback.ensure_ready_for_load()

    def is_eof_reached(self):
        return self._playback.is_eof_reached()

    def get_buffer_state(self):
        return self._playback.get_buffer_state()

    def get_track_list(self, track_type='audio'):
        return self._playback.get_track_list(track_type)

    def set_track(self, track_type, track_id):
        return self._playback.set_track(track_type, track_id)

    def get_current_track(self, track_type='audio'):
        return self._playback.get_current_track(track_type)

    def add_subtitle_file(self, file_path):
        return self._playback.add_subtitle_file(file_path)

    def get_chapter_list(self):
        return self._playback.get_chapter_list()

    def get_chapter_count(self) -> int:
        return self._playback.get_chapter_count()

    def get_current_chapter(self):
        return self._playback.get_current_chapter()

    def set_chapter(self, idx: int) -> bool:
        return self._playback.set_chapter(idx)

    def chapter_next(self) -> bool:
        return self._playback.chapter_next()

    def chapter_prev(self) -> bool:
        return self._playback.chapter_prev()

    def get_avdiff(self) -> float:
        return self._playback.get_avdiff()

    def get_audio_pts(self) -> float:
        return self._playback.get_audio_pts()

    def get_video_pts(self) -> float:
        return self._playback.get_video_pts()

    def set_sub_delay(self, delay: float) -> bool:
        return self._subtitle.set_sub_delay(delay)

    def get_sub_delay(self) -> float:
        return self._subtitle.get_sub_delay()

    def adjust_sub_delay(self, delta: float) -> float:
        return self._subtitle.adjust_sub_delay(delta)

    def set_sub_scale(self, scale: float) -> bool:
        return self._subtitle.set_sub_scale(scale)

    def get_sub_scale(self) -> float:
        return self._subtitle.get_sub_scale()

    def adjust_sub_scale(self, delta: float) -> float:
        return self._subtitle.adjust_sub_scale(delta)

    def set_sub_pos(self, pos: int) -> bool:
        return self._subtitle.set_sub_pos(pos)

    def get_sub_pos(self) -> int:
        return self._subtitle.get_sub_pos()

    def set_sub_visibility(self, visible: bool) -> bool:
        return self._subtitle.set_sub_visibility(visible)

    def get_sub_visibility(self) -> bool:
        return self._subtitle.get_sub_visibility()

    def toggle_sub_visibility(self) -> bool:
        return self._subtitle.toggle_sub_visibility()

    def apply_sub_style(self, style: dict) -> bool:
        return self._subtitle.apply_sub_style(style)

    def get_sub_style(self) -> dict:
        return self._subtitle.get_sub_style()

    def set_brightness(self, v: int) -> bool:
        return self._video_eq.set_brightness(v)

    def get_brightness(self) -> int:
        return self._video_eq.get_brightness()

    def set_contrast(self, v: int) -> bool:
        return self._video_eq.set_contrast(v)

    def get_contrast(self) -> int:
        return self._video_eq.get_contrast()

    def set_saturation(self, v: int) -> bool:
        return self._video_eq.set_saturation(v)

    def get_saturation(self) -> int:
        return self._video_eq.get_saturation()

    def set_hue(self, v: int) -> bool:
        return self._video_eq.set_hue(v)

    def get_hue(self) -> int:
        return self._video_eq.get_hue()

    def set_gamma(self, v: int) -> bool:
        return self._video_eq.set_gamma(v)

    def get_gamma(self) -> int:
        return self._video_eq.get_gamma()

    def set_sharpness(self, v: float) -> bool:
        return self._video_eq.set_sharpness(v)

    def get_sharpness(self) -> float:
        return self._video_eq.get_sharpness()

    def adjust_video_eq(self, key: str, delta) -> float:
        return self._video_eq.adjust_video_eq(key, delta)

    def apply_video_eq(self, eq: dict) -> bool:
        return self._video_eq.apply_video_eq(eq)

    def get_video_eq(self) -> dict:
        return self._video_eq.get_video_eq()

    def reset_video_eq(self):
        return self._video_eq.reset_video_eq()

    def _enable_deinterlace_filter(self):
        return self._video_eq._enable_deinterlace_filter()

    def _disable_deinterlace_filter(self):
        return self._video_eq._disable_deinterlace_filter()

    def set_video_rotate(self, degree: int) -> bool:
        return self._video_eq.set_video_rotate(degree)

    def get_video_rotate(self) -> int:
        return self._video_eq.get_video_rotate()

    def set_video_flip(self, mode: str) -> bool:
        return self._video_eq.set_video_flip(mode)

    def get_video_flip(self) -> str:
        return self._video_eq.get_video_flip()

    def set_video_crop(self, x: int, y: int, w: int, h: int) -> bool:
        return self._video_eq.set_video_crop(x, y, w, h)

    def clear_video_crop(self) -> bool:
        return self._video_eq.clear_video_crop()

    def clear_all_video_filters(self) -> bool:
        return self._video_eq.clear_all_video_filters()

    def _get_video_resolution(self):
        return self._playback._get_video_resolution()

    def _is_4k_or_above(self) -> bool:
        return self._playback._is_4k_or_above()

    def set_motion_compensation(self, strength: str, target_fps: int = 60) -> bool:
        return self._shader.set_motion_compensation(strength, target_fps)

    def get_motion_compensation(self) -> dict:
        return self._shader.get_motion_compensation()

    def clear_motion_compensation(self) -> bool:
        return self._shader.clear_motion_compensation()

    def set_super_resolution(self, scale_algo: str = 'off', detail_enhance: int = 0) -> bool:
        return self._shader.set_super_resolution(scale_algo, detail_enhance)

    def get_super_resolution(self) -> dict:
        return self._shader.get_super_resolution()

    def clear_super_resolution(self) -> bool:
        return self._shader.clear_super_resolution()

    def _get_shaders_dir(self) -> str:
        return self._shader._get_shaders_dir()

    def _find_shader_files(self, preset: str) -> list:
        return self._shader._find_shader_files(preset)

    def list_available_shaders(self) -> list:
        return self._shader.list_available_shaders()

    def set_user_shader(self, preset: str) -> bool:
        return self._shader.set_user_shader(preset)

    def get_user_shader(self) -> str:
        return self._shader.get_user_shader()

    def clear_user_shader(self) -> bool:
        return self._shader.clear_user_shader()

    def set_video_stereo_mode(self, mode: str) -> bool:
        return self._filter.set_video_stereo_mode(mode)

    def get_video_stereo_mode(self) -> str:
        return self._filter.get_video_stereo_mode()

    def set_360_view(self, yaw: float, pitch: float, roll: float,
                     projection: str = 'equirect') -> bool:
        return self._filter.set_360_view(yaw, pitch, roll, projection)

    def clear_360_filter(self) -> bool:
        return self._filter.clear_360_filter()

    def get_360_view(self) -> dict:
        return self._filter.get_360_view()

    def set_audio_delay(self, v: float) -> bool:
        return self._audio_eq.set_audio_delay(v)

    def get_audio_delay(self) -> float:
        return self._audio_eq.get_audio_delay()

    def adjust_audio_delay(self, delta: float) -> float:
        return self._audio_eq.adjust_audio_delay(delta)

    def set_audio_device(self, name: str) -> bool:
        return self._audio_eq.set_audio_device(name)

    def get_audio_device(self) -> str:
        return self._audio_eq.get_audio_device()

    def get_audio_device_list(self) -> list:
        return self._audio_eq.get_audio_device_list()

    def set_audio_channels(self, ch: str) -> bool:
        return self._audio_eq.set_audio_channels(ch)

    def get_audio_channels(self) -> str:
        return self._audio_eq.get_audio_channels()

    def get_audio_channel_info(self) -> dict:
        return self._audio_eq.get_audio_channel_info()

    def start_channel_monitor(self) -> bool:
        return self._audio_eq.start_channel_monitor()

    def stop_channel_monitor(self):
        return self._audio_eq.stop_channel_monitor()

    def get_channel_levels(self) -> dict:
        return self._audio_eq.get_channel_levels()

    def set_audio_pitch(self, v: float) -> bool:
        return self._audio_eq.set_audio_pitch(v)

    def get_audio_pitch(self) -> float:
        return self._audio_eq.get_audio_pitch()

    def adjust_audio_pitch(self, delta: float) -> float:
        return self._audio_eq.adjust_audio_pitch(delta)

    def set_audio_eq_band(self, band_index: int, gain_db: float) -> bool:
        return self._audio_eq.set_audio_eq_band(band_index, gain_db)

    def set_audio_eq(self, gains: list) -> bool:
        return self._audio_eq.set_audio_eq(gains)

    def get_audio_eq(self) -> list:
        return self._audio_eq.get_audio_eq()

    def _apply_audio_eq_filter(self, gains: list) -> bool:
        return self._audio_eq._apply_audio_eq_filter(gains)

    def apply_audio_eq(self, settings: dict) -> bool:
        return self._audio_eq.apply_audio_eq(settings)

    def get_audio_eq_all(self) -> dict:
        return self._audio_eq.get_audio_eq_all()

    def reset_audio_eq(self):
        return self._audio_eq.reset_audio_eq()

    def set_loop_file(self, mode: str) -> bool:
        return self._filter.set_loop_file(mode)

    def get_loop_file(self) -> str:
        return self._filter.get_loop_file()

    def set_loop_playlist(self, mode: str) -> bool:
        return self._filter.set_loop_playlist(mode)

    def get_loop_playlist(self) -> str:
        return self._filter.get_loop_playlist()

    def ab_loop_set_a(self) -> float:
        return self._filter.ab_loop_set_a()

    def ab_loop_set_b(self) -> float:
        return self._filter.ab_loop_set_b()

    def ab_loop_clear(self) -> bool:
        return self._filter.ab_loop_clear()

    def ab_loop_get_status(self) -> dict:
        return self._filter.ab_loop_get_status()

    def frame_step(self) -> bool:
        return self._filter.frame_step()

    def frame_back_step(self) -> bool:
        return self._filter.frame_back_step()

    def set_http_referer(self, referer: str) -> bool:
        return self._playback.set_http_referer(referer)

    def get_http_referer(self) -> str:
        return self._playback.get_http_referer()

    def set_http_proxy(self, proxy: str) -> bool:
        return self._playback.set_http_proxy(proxy)

    def get_http_proxy(self) -> str:
        return self._playback.get_http_proxy()

    def set_http_headers(self, headers: str):
        return self._playback.set_http_headers(headers)

    def set_property_string(self, name, value):
        return self._playback.set_property_string(name, value)

    def send_command(self, cmd_args):
        return self._playback.send_command(cmd_args)

    def show_osd(self, text: str, duration: int = 3000):
        return self._playback.show_osd(text, duration)

    def _apply_osd_colors(self):
        return self._playback._apply_osd_colors()

    def update_osd_theme(self):
        return self._playback.update_osd_theme()

    @staticmethod
    def detect_hdr_type(colormatrix: str, gamma: str, sig_peak: float,
                        video_format: str = '', primaries: str = '') -> str:
        return MpvHdr.detect_hdr_type(colormatrix, gamma, sig_peak, video_format, primaries)

    def get_available_seek_range(self) -> dict:
        return self._playback.get_available_seek_range()

