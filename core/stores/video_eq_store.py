"""视频 EQ 域存储 — 视频图像调整/字幕样式。"""


class VideoEqStore:
    """视频 EQ 配置域存储，通过 facade 访问共享 ConfigParser。"""

    VIDEO_EQ_DEFAULTS = {
        'brightness': 0,
        'contrast': 0,
        'saturation': 0,
        'hue': 0,
        'gamma': 0,
        'sharpness': 0.0,
        'video_rotate': 0,
        'video_flip': '',
        'reset_on_new_file': False,
        'motion_comp': 'off',
        'motion_comp_fps': 60,
        'superres_scale': 'off',
        'superres_detail': 0,
        'shader_preset': 'off',
        'scene_detect_enabled': False,
        'gpu_api': 'auto',
    }

    SUBTITLE_STYLE_DEFAULTS = {
        'color': '#FFFFFFFF',
        'border_color': '#FF000000',
        'shadow_color': '#FF000000',
        'font': 'sans-serif',
        'font_size': 55,
        'border_size': 3,
        'shadow_offset': 1,
        'bold': False,
        'italic': False,
        'margin_x': 25,
        'margin_y': 22,
        'align_x': 'center',
        'align_y': 'bottom',
        'sub_delay': 0.0,
        'sub_scale': 1.0,
        'sub_pos': 100,
        'sub_visibility': True,
    }

    def __init__(self, facade):
        self._facade = facade

    def save_video_eq(self, settings: dict):
        """保存视频图像参数到 VideoEQ 节"""
        f = self._facade
        for key, value in settings.items():
            if key == 'gpu_api':
                # Playback 为唯一权威键；VideoEQ 保留一份供旧配置回退
                val = str(value or '').strip() or 'auto'
                f.set_value('VideoEQ', key, val)
                f.set_value('Playback', key, val)
            elif isinstance(value, bool):
                f.set_value('VideoEQ', key, 'yes' if value else 'no')
            elif isinstance(value, float):
                f.set_value('VideoEQ', key, f"{value:.3f}")
            elif isinstance(value, int):
                f.set_value('VideoEQ', key, str(value))
            else:
                f.set_value('VideoEQ', key, str(value))
        return f.save_config()

    def load_video_eq(self) -> dict:
        """加载视频图像参数，缺失项写回默认值"""
        f = self._facade
        result = {}
        need_save = False
        missing_keys = {}
        for key, default in self.VIDEO_EQ_DEFAULTS.items():
            raw = f.get_value('VideoEQ', key)
            if raw is None:
                result[key] = default
                need_save = True
                missing_keys[key] = str(default)
            elif isinstance(default, bool):
                result[key] = f._parse_bool(raw)
            elif isinstance(default, float):
                try:
                    result[key] = float(raw)
                except (ValueError, TypeError):
                    result[key] = default
            elif isinstance(default, int):
                try:
                    result[key] = int(raw)
                except (ValueError, TypeError):
                    result[key] = default
            else:
                result[key] = raw
        if missing_keys:
            with f._lock:
                if not f.config.has_section('VideoEQ'):
                    f.config.add_section('VideoEQ')
                for key, value in missing_keys.items():
                    f.config.set('VideoEQ', key, value)
        if need_save:
            f.save_config()
        canonical_gpu_api = (f.get_value('Playback', 'gpu_api', '') or '').strip()
        if canonical_gpu_api:
            result['gpu_api'] = canonical_gpu_api
        return result

    def save_subtitle_style(self, settings: dict):
        """保存字幕样式到 SubtitleStyle 节"""
        f = self._facade
        for key, value in settings.items():
            if isinstance(value, bool):
                f.set_value('SubtitleStyle', key, 'yes' if value else 'no')
            elif isinstance(value, float):
                f.set_value('SubtitleStyle', key, f"{value:.3f}")
            elif isinstance(value, int):
                f.set_value('SubtitleStyle', key, str(value))
            else:
                f.set_value('SubtitleStyle', key, str(value))
        return f.save_config()

    def load_subtitle_style(self) -> dict:
        """加载字幕样式，缺失项写回默认值"""
        f = self._facade
        result = {}
        need_save = False
        missing_keys = {}
        for key, default in self.SUBTITLE_STYLE_DEFAULTS.items():
            raw = f.get_value('SubtitleStyle', key)
            if raw is None:
                result[key] = default
                need_save = True
                missing_keys[key] = str(default)
            elif isinstance(default, bool):
                result[key] = f._parse_bool(raw)
            elif isinstance(default, float):
                try:
                    result[key] = float(raw)
                except (ValueError, TypeError):
                    result[key] = default
            elif isinstance(default, int):
                try:
                    result[key] = int(raw)
                except (ValueError, TypeError):
                    result[key] = default
            else:
                result[key] = raw
        if missing_keys:
            with f._lock:
                if not f.config.has_section('SubtitleStyle'):
                    f.config.add_section('SubtitleStyle')
                for key, value in missing_keys.items():
                    f.config.set('SubtitleStyle', key, value)
        if need_save:
            f.save_config()
        return result