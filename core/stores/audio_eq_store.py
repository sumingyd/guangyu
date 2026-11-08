"""音频 EQ 域存储 — 音频系统增强参数。"""


class AudioEqStore:
    """音频 EQ 配置域存储，通过 facade 访问共享 ConfigParser。"""

    AUDIO_EQ_DEFAULTS = {
        'audio_delay': 0.0,
        'audio_channels': 'auto',
        'audio_pitch': 1.0,
        'audio_device': '',
        'eq': [0.0] * 10,
        'reset_on_new_file': False,
    }

    def __init__(self, facade):
        self._facade = facade

    def save_audio_eq(self, settings: dict):
        """保存音频参数到 AudioEQ 节
        eq 字段为长度 10 的列表，存储为逗号分隔字符串
        """
        f = self._facade
        for key, value in settings.items():
            if key == 'eq':
                if isinstance(value, list):
                    s = ','.join(f"{float(v):.1f}" for v in value)
                    f.set_value('AudioEQ', key, s)
                else:
                    f.set_value('AudioEQ', key, str(value))
            elif isinstance(value, bool):
                f.set_value('AudioEQ', key, 'yes' if value else 'no')
            elif isinstance(value, float):
                f.set_value('AudioEQ', key, f"{value:.3f}")
            elif isinstance(value, int):
                f.set_value('AudioEQ', key, str(value))
            else:
                f.set_value('AudioEQ', key, str(value))
        return f.save_config()

    def load_audio_eq(self) -> dict:
        """加载音频参数，缺失项写回默认值"""
        f = self._facade
        result = {}
        need_save = False
        missing_keys = {}
        for key, default in self.AUDIO_EQ_DEFAULTS.items():
            raw = f.get_value('AudioEQ', key)
            if raw is None:
                result[key] = default
                need_save = True
                if key == 'eq':
                    missing_keys[key] = ','.join(f"{float(v):.1f}" for v in default)
                else:
                    missing_keys[key] = str(default)
            elif key == 'eq':
                try:
                    if isinstance(raw, str) and raw:
                        parts = [float(x) for x in raw.split(',') if x.strip()]
                        if len(parts) == 10:
                            result[key] = [max(-12.0, min(12.0, p)) for p in parts]
                        else:
                            result[key] = list(default)
                            need_save = True
                    else:
                        result[key] = list(default)
                        need_save = True
                except (ValueError, TypeError):
                    result[key] = list(default)
                    need_save = True
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
                if not f.config.has_section('AudioEQ'):
                    f.config.add_section('AudioEQ')
                for key, value in missing_keys.items():
                    f.config.set('AudioEQ', key, value)
        if need_save:
            f.save_config()
        return result