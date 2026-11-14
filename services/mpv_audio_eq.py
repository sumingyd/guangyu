"""MpvAudioEq — 从 MpvPlayerController 提取的子控制器。"""

from core.log_manager import global_logger as logger

import re

# 变调范围与默认值。1.0 表示不加滤镜；mpv 的 audio-pitch-correction 只是
# “变速时是否保持音调”的开关（yes/no），无法表达连续音调，因此这里用
# lavfi 的 rubberband 滤镜实现真正的变调不变速。
PITCH_MIN = 0.5
PITCH_MAX = 2.0
PITCH_NEUTRAL = 1.0


class MpvAudioEq:
    """MpvAudioEq — 通过 facade 访问 mpv 实例和播放器。"""

    def __init__(self, facade):
        self._facade = facade

    def _apply_audio_eq_filter(self, gains: list) -> bool:
        """内部：应用均衡器 af 滤镜"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        # 先移除已有的 eq 滤镜
        try:
            self._facade.send_command(['af', 'remove', '@iptv_eq'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        # 全为 0 时不再添加
        if all(abs(g) < 0.01 for g in gains):
            return True
        cmd = "@iptv_eq:equalizer=" + ":".join(f"{g:.1f}" for g in gains)
        return self._facade.send_command(['af', 'add', cmd]) == 0

    def adjust_audio_delay(self, delta: float) -> float:
        cur = self._facade.get_audio_delay()
        new_v = round(max(-10.0, min(10.0, cur + delta)), 3)
        self._facade.set_audio_delay(new_v)
        return new_v

    def adjust_audio_pitch(self, delta: float) -> float:
        cur = self.get_audio_pitch()
        new_v = round(max(PITCH_MIN, min(PITCH_MAX, cur + delta)), 3)
        self.set_audio_pitch(new_v)
        return new_v

    def apply_audio_eq(self, settings: dict) -> bool:
        """批量应用音频参数
        dict 可含：audio_delay, audio_channels, audio_pitch, audio_device, eq(列表)
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        try:
            if 'audio_delay' in settings and settings['audio_delay'] is not None:
                self._facade.set_audio_delay(float(settings['audio_delay']))
            if 'audio_pitch' in settings and settings['audio_pitch'] is not None:
                self._facade.set_audio_pitch(float(settings['audio_pitch']))
            if 'audio_channels' in settings and settings['audio_channels']:
                self._facade.set_audio_channels(str(settings['audio_channels']))
            if 'audio_device' in settings and settings['audio_device']:
                self._facade.set_audio_device(str(settings['audio_device']))
            if 'eq' in settings and settings['eq'] is not None:
                self._facade.set_audio_eq(list(settings['eq']))
            return True
        except Exception as e:
            self._facade.logger.error(f"应用音频参数失败: {e}")
            return False

    def get_audio_channel_info(self) -> dict:
        """获取当前音频声道信息
        返回: {'layout': '5.1', 'channels': ['FL','FR','FC','LFE','BL','BR'], 'count': 6}
        """
        layout = self._facade._get_mpv_property_string('audio-params/channel-layout') or ''
        count = self._facade._get_mpv_property_double('audio-params/channel-count') or 0
        # 规范化布局字符串
        layout_lower = layout.lower().strip()
        channels = self._facade.CHANNEL_LAYOUT_MAP.get(layout_lower, [])
        if not channels and count > 0:
            # 未知布局但有声道数，尝试按数量推断
            if count == 1:
                channels = ['FC']
                layout_lower = 'mono'
            elif count == 2:
                channels = ['FL', 'FR']
                layout_lower = 'stereo'
            elif count >= 6:
                channels = ['FL', 'FR', 'FC', 'LFE', 'BL', 'BR']
                layout_lower = '5.1'
            elif count >= 3:
                channels = ['FL', 'FR', 'FC']
                layout_lower = '3.0'
        return {
            'layout': layout_lower or 'stereo',
            'channels': channels,
            'count': len(channels) if channels else int(count),
        }

    def get_audio_channels(self) -> str:
        return self._facade._get_mpv_property_string('audio-channels') or 'auto'

    def get_audio_delay(self) -> float:
        v = self._facade._get_mpv_property_double('audio-delay')
        return float(v) if v is not None else 0.0

    def get_audio_device(self) -> str:
        return self._facade._get_mpv_property_string('audio-device') or ''

    def get_audio_device_list(self) -> list:
        """返回音频设备列表，每项为 dict(name, description)"""
        try:
            raw = self._facade._get_mpv_property_string('audio-device-list')
            if not raw:
                return []
            import json
            data = json.loads(raw) if isinstance(raw, str) else raw
            result = []
            for item in data:
                name = item.get('name', '')
                desc = item.get('description', '')
                if name:
                    result.append({'name': name, 'description': desc or name})
            return result
        except Exception:
            return []

    def get_audio_eq(self) -> list:
        """读取当前均衡器增益列表（长度 10）。无法读取时返回全 0"""
        try:
            af = self._facade._get_mpv_property_string('af')
            if not af:
                return [0.0] * 10
            import json
            data = json.loads(af) if isinstance(af, str) else af
            for item in data.get('af', []):
                params = item.get('params', {})
                if params.get('name') == 'equalizer':
                    raw = params.get('params', '') or ''
                    # 格式可能是 "g1:g2:...:g10" 或 dict
                    if isinstance(raw, str) and raw:
                        parts = raw.split(':')
                        if len(parts) == 10:
                            return [max(-12.0, min(12.0, float(p))) for p in parts]
                    break
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return [0.0] * 10

    def get_audio_eq_all(self) -> dict:
        """读取所有音频参数"""
        return {
            'audio_delay': self._facade.get_audio_delay(),
            'audio_channels': self._facade.get_audio_channels(),
            'audio_pitch': self._facade.get_audio_pitch(),
            'audio_device': self._facade.get_audio_device(),
            'eq': self._facade.get_audio_eq(),
        }

    def get_audio_pitch(self) -> float:
        """读取当前变调倍率（默认 1.0）。

        从 mpv 的 af 链里解析 @iptv_pitch 的 rubberband pitch 参数；
        没有该滤镜时返回 1.0。
        """
        try:
            raw = self._facade._get_mpv_property_string('af') or ''
            m = re.search(r'iptv_pitch.*?pitch=([0-9]*\.?[0-9]+)', str(raw))
            if m:
                return max(PITCH_MIN, min(PITCH_MAX, float(m.group(1))))
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return PITCH_NEUTRAL

    def get_channel_levels(self) -> dict:
        """获取各声道 RMS 电平
        返回: {声道序号(1-based): 电平dB}
        电平为 -inf 或极低值表示该声道无声。
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return {}
        try:
            # 尝试直接读取带标签的 metadata
            data = _mpv_get_property_node(
                self._facade.mpv_handle, 'af-metadata/@iptv_stats'
            )
            # 如果带 @ 的路径失败，尝试不带 @
            if not data or not isinstance(data, dict):
                data = _mpv_get_property_node(
                    self._facade.mpv_handle, 'af-metadata/iptv_stats'
                )
            # 如果仍然失败，读取全部 af-metadata 再查找
            if not data or not isinstance(data, dict):
                all_meta = _mpv_get_property_node(
                    self._facade.mpv_handle, 'af-metadata'
                )
                if all_meta and isinstance(all_meta, dict):
                    data = all_meta.get('iptv_stats') or all_meta.get('@iptv_stats') or {}
                if not data and all_meta is not None:
                    logger.debug(
                        f"af-metadata full: {all_meta}"
                    )
            if not data or not isinstance(data, dict):
                return {}
            result = {}
            for key, val in data.items():
                # 格式: lavfi.astats.1.RMS_level
                if key.startswith('lavfi.astats.') and key.endswith('.RMS_level'):
                    parts = key.split('.')
                    if len(parts) == 4 and parts[2].isdigit():
                        ch_idx = int(parts[2])
                        try:
                            level = float(val)
                            result[ch_idx] = level
                        except (ValueError, TypeError):
                            pass
            if not result:
                logger.debug(
                    f"af-metadata keys: {list(data.keys()) if data else 'empty'}"
                )
            return result
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
            return {}

    def reset_audio_eq(self):
        """重置音频参数为默认"""
        self._facade.set_audio_delay(0.0)
        self._facade.set_audio_pitch(1.0)
        self._facade.set_audio_channels('auto')
        # 清除均衡器滤镜
        try:
            self._facade.send_command(['af', 'remove', '@iptv_eq'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

    def set_audio_channels(self, ch: str) -> bool:
        """设置音频声道布局（auto/mono/1.0/2.0/2.1/3.0/4.0/5.0/5.1/6.0/6.1/7.0/7.1）"""
        if not ch:
            return False
        return self._facade._set_mpv_string('audio-channels', ch) >= 0

    def set_audio_delay(self, v: float) -> bool:
        v = max(-10.0, min(10.0, float(v)))
        return self._facade._set_mpv_string('audio-delay', f"{v:.3f}") >= 0

    def set_audio_device(self, name: str) -> bool:
        if not name:
            return False
        return self._facade._set_mpv_string('audio-device', name) >= 0

    def set_audio_eq(self, gains: list) -> bool:
        """设置完整均衡器（gains 长度 10，每项 -12~+12 dB）"""
        if not gains or len(gains) != 10:
            return False
        eq = [max(-12.0, min(12.0, float(g))) for g in gains]
        return self._facade._apply_audio_eq_filter(eq)

    def set_audio_eq_band(self, band_index: int, gain_db: float) -> bool:
        """设置均衡器指定频段的增益（band_index 0-9，gain -12~+12 dB）"""
        if not (0 <= band_index < 10):
            return False
        eq = self._facade.get_audio_eq()
        eq[band_index] = max(-12.0, min(12.0, float(gain_db)))
        return self._facade._apply_audio_eq_filter(eq)

    def set_audio_pitch(self, v: float) -> bool:
        """设置变调不变速（0.5–2.0，1.0 为原调）。

        实现方式：af 链上的 rubberband 滤镜（lavfi 包装），而不是
        audio-pitch-correction —— 后者是 yes/no 开关，传浮点会被 mpv 拒绝。

        影响面：滤镜会把音频转成 PCM 处理，音频直通（audio-spdif）时听不到
        变调效果；另外需要当前 mpv 构建编译了 librubberband，否则滤镜添加
        失败并返回 False（界面保持原调）。
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = PITCH_NEUTRAL
        # 旧配置里的 0 表示“关闭音调补偿”，对变调而言等价于原调
        if v <= 0.0:
            v = PITCH_NEUTRAL
        v = max(PITCH_MIN, min(PITCH_MAX, v))
        try:
            self._facade.send_command(['af', 'remove', '@iptv_pitch'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        if abs(v - PITCH_NEUTRAL) < 0.005:
            return True
        ret = self._facade.send_command(
            ['af', 'add', f'@iptv_pitch:lavfi=[rubberband=pitch={v:.3f}]']
        )
        if ret != 0:
            self._facade.logger.warning(
                f"变调滤镜添加失败(ret={ret})，当前 mpv 构建可能不含 rubberband 滤镜"
            )
        return ret == 0

    def start_channel_monitor(self) -> bool:
        """启动声道活动监控（添加 astats 滤镜）
        astats 滤镜将各声道 RMS 电平写入 metadata，通过 af-metadata 读取。
        reset=1 使每帧重置统计，输出瞬时 RMS 电平（VU 表所需）。
        """
        if not self._facade.mpv_handle or self._facade._terminated:
            return False
        # 先移除旧的 astats 滤镜
        try:
            self._facade.send_command(['af', 'remove', '@iptv_stats'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")
        return self._facade.send_command(
            ['af', 'add', '@iptv_stats:lavfi=[astats=metadata=1:reset=1]']
        ) == 0

    def stop_channel_monitor(self):
        """停止声道活动监控（移除 astats 滤镜）"""
        if not self._facade.mpv_handle or self._facade._terminated:
            return
        try:
            self._facade.send_command(['af', 'remove', '@iptv_stats'])
        except Exception as _e:
            logger.debug(f"unexpected error: {_e}")

