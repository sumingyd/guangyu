"""播放设置持久化控制器
按 URL 保存/恢复每个文件的播放设置（音量/字幕轨/音轨/比例/翻转/旋转/字幕延迟/音频延迟）。

设计：
- file_loaded 信号触发时，延迟读取持久化设置并应用
- 文件切换前（stop 或新 play）保存当前文件的设置
- 保存与断点续播（resume_position）独立，互不干扰
"""
from PySide6.QtCore import QObject, QTimer

from core.log_manager import global_logger as logger
from core.playback_settings_store import PlaybackSettingsStore
from utils.delay_constants import DelayMs


class PlaybackSettingsController(QObject):
    """按 URL 持久化播放设置"""

    # 应用设置前的延迟（等待 mpv 完成轨道初始化）
    _APPLY_DELAY_MS = 600

    def __init__(self, main_window):
        super().__init__()
        self.window = main_window
        self._store = PlaybackSettingsStore(main_window.config.config_dir)
        # 当前已应用设置的 URL（避免重复应用）
        self._applied_url = None
        # 上一个 URL（用于切换时保存旧设置）
        self._last_url = None
        # 是否正在应用设置（避免应用过程中触发保存）
        self._applying = False

        pc = main_window.player_controller
        if pc:
            if hasattr(pc, 'file_loaded'):
                pc.file_loaded.connect(self._on_file_loaded)
            if hasattr(pc, 'local_file_position_to_save'):
                pc.local_file_position_to_save.connect(self._on_position_save)
            if hasattr(pc, 'about_to_stop'):
                pc.about_to_stop.connect(self._on_about_to_stop)
            else:
                # 没有专用信号，hook stop 方法
                if not getattr(pc, '_is_stop_wrapped', False):
                    self._orig_stop = pc.stop
                    pc.stop = self._wrapped_stop
                    pc._is_stop_wrapped = True

    # ---------- 文件加载时应用 ----------
    def _on_file_loaded(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            url = pc.current_url or ''
            if not url or url == self._applied_url:
                return
            self._applied_url = url
            # 延迟应用，等轨道初始化完成
            QTimer.singleShot(self._APPLY_DELAY_MS, self._apply_settings)
        except Exception as e:
            logger.debug(f"播放设置 file_loaded 失败: {e}")

    def _apply_settings(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            url = pc.current_url or ''
            if not url or url != self._applied_url:
                return
            settings = self._store.load_settings(url)
            if not settings:
                return
            self._applying = True
            try:
                # 音量/静音
                if 'volume' in settings:
                    pc.set_volume(int(settings['volume']))
                if 'mute' in settings:
                    pc.set_mute(bool(settings['mute']))
                # 宽高比
                if 'aspect_ratio' in settings and settings['aspect_ratio']:
                    pc.set_aspect_ratio(settings['aspect_ratio'])
                # 旋转
                if 'video_rotate' in settings:
                    pc.set_video_rotate(int(settings['video_rotate']))
                # 翻转
                if 'video_flip' in settings and settings['video_flip']:
                    pc.set_video_flip(settings['video_flip'])
                # 字幕延迟
                if 'sub_delay' in settings:
                    pc.set_sub_delay(float(settings['sub_delay']))
                # 音频延迟
                if 'audio_delay' in settings:
                    pc.set_audio_delay(float(settings['audio_delay']))
                # 字幕轨
                if 'sub_track' in settings and settings['sub_track']:
                    QTimer.singleShot(DelayMs.STYLE_REAPPLY, lambda: self._set_track('sub', settings['sub_track']))
                # 音轨
                if 'audio_track' in settings and settings['audio_track']:
                    QTimer.singleShot(DelayMs.STYLE_REAPPLY, lambda: self._set_track('audio', settings['audio_track']))
                logger.debug(f"已应用播放设置: {url[:60]}")
            finally:
                self._applying = False
        except Exception as e:
            logger.warning(f"应用播放设置失败: {e}")
            self._applying = False

    def _set_track(self, track_type: str, track_id):
        try:
            pc = self.window.player_controller
            if pc and pc.is_playing:
                pc.set_track(track_type, int(track_id))
        except Exception as e:
            logger.debug(f"设置{track_type}轨失败: {e}")

    # ---------- 保存当前设置 ----------
    def save_current_settings(self):
        """对外入口：换台/停止前保存当前 URL 的播放设置。

        play() 直接 loadfile，不经过 stop()，网络频道也不会触发断点信号，
        因此换台前必须显式调用，否则旧频道的音轨/字幕/比例等偏好永远存不下来。
        """
        self._save_current()

    def clear_settings_for_url(self, url: str):
        """删除频道时清掉该 URL 的播放设置，避免重新添加同名/同地址频道时继承旧偏好。"""
        if not url:
            return
        try:
            self._store.clear_settings(url)
            logger.debug(f"已清除播放设置: {url[:60]}")
        except Exception as e:
            logger.debug(f"清除播放设置失败: {e}")

    def _capture_current_settings(self) -> dict:
        """读取当前 mpv 的播放设置"""
        settings = {}
        try:
            pc = self.window.player_controller
            if not pc:
                return settings
            vol = pc.get_volume()
            if vol is not None:
                settings['volume'] = int(vol)
            mute = pc.get_mute()
            if mute is not None:
                settings['mute'] = bool(mute)
            aspect = pc.get_aspect_ratio()
            if aspect:
                settings['aspect_ratio'] = aspect
            rotate = pc.get_video_rotate()
            if rotate:
                settings['video_rotate'] = int(rotate)
            flip = pc.get_video_flip()
            if flip:
                settings['video_flip'] = flip
            sub_delay = pc.get_sub_delay()
            if sub_delay and abs(sub_delay) > 0.001:
                settings['sub_delay'] = float(sub_delay)
            audio_delay = pc.get_audio_delay()
            if audio_delay and abs(audio_delay) > 0.001:
                settings['audio_delay'] = float(audio_delay)
            sub_track = pc.get_current_track('sub')
            if sub_track:
                settings['sub_track'] = sub_track
            audio_track = pc.get_current_track('audio')
            if audio_track:
                settings['audio_track'] = audio_track
        except Exception as e:
            logger.debug(f"捕获播放设置失败: {e}")
        return settings

    def _save_current(self):
        """保存当前 URL 的播放设置"""
        if self._applying:
            return
        try:
            pc = self.window.player_controller
            if not pc:
                return
            url = pc.current_url or self._last_url
            if not url:
                return
            settings = self._capture_current_settings()
            if not settings:
                return
            name = self._get_name_for_url(url)
            self._store.save_settings(url, settings, name)
            logger.debug(f"已保存播放设置: {url[:60]}")
        except Exception as e:
            logger.debug(f"保存播放设置失败: {e}")

    def _get_name_for_url(self, url: str) -> str:
        try:
            cur = getattr(self.window, 'current_channel', None)
            if cur and isinstance(cur, dict) and cur.get('url') == url:
                return cur.get('name', '') or ''
        except Exception as e:
            logger.debug(f"获取当前频道名失败: {e}")
        return ''

    def _on_position_save(self, url: str, position: float, duration: float):
        """断点续播保存时，顺便保存播放设置"""
        if url:
            self._last_url = url
            self._save_current()

    def _on_about_to_stop(self):
        self._save_current()

    def _wrapped_stop(self, *args, **kwargs):
        self._save_current()
        return self._orig_stop(*args, **kwargs)
