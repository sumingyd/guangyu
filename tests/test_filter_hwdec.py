"""运动补偿/细节增强与硬解模式的联动回归测试。

背景：hwdec=auto（原生硬解）下解码帧留在 GPU，lavfi 滤镜拿不到帧数据，
mpv 会静默禁用 iptv_mc / iptv_sr。开启这些增强项时必须自动改用
copy-back，关闭后再还原，避免用户手动改播放设置。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.mpv_shader as mpv_shader  # noqa: E402
from services.mpv_common import effective_hwdec, normalize_hwdec  # noqa: E402


class FakeFacade:
    """模拟 MpvPlayerController 中 MpvShader 用到的接口。"""

    def __init__(self, hwdec='auto', is_4k=False):
        self._playback_settings = {'hwdec': hwdec}
        self.mpv_handle = object()
        self._terminated = False
        self.logger = MagicMock()
        self.hwdec_runtime = 'auto-copy' if hwdec is True else (
            hwdec if isinstance(hwdec, str) else 'no')
        self.set_hwdec_fail = False
        self.filter_add_ret = 0
        self.filter_add_results = None
        self.ops = []
        self._MC_PRESETS = {
            'off': None,
            'low': 'mi_mode=blend',
            'medium': 'mi_mode=mci:mc_mode=obmc:me=dsr',
            'high': 'mi_mode=mci:mc_mode=aobmc:me=hexbs',
        }
        self._SCALE_OPTIONS = (
            'bilinear', 'bicubic', 'lanczos', 'spline', 'ewa_lanczos', 'ewa_lanczossharp')
        self._SHADER_PRESET_FILES = {}
        self._is_4k = is_4k

    def send_command(self, cmd):
        self.ops.append(tuple(cmd))
        if list(cmd[:2]) == ['vf', 'add']:
            if self.filter_add_results:
                return self.filter_add_results.pop(0)
            return self.filter_add_ret
        return 0

    def _set_mpv_string(self, name, value):
        if name == 'hwdec':
            self.ops.append(('set-hwdec', value))
            if self.set_hwdec_fail:
                return -1
            self.hwdec_runtime = value
        return 0

    def _get_mpv_property_string(self, name):
        if name == 'hwdec':
            return self.hwdec_runtime
        return ''

    def _is_4k_or_above(self):
        return self._is_4k


def _added_filters(facade):
    return [op[2] for op in facade.ops if op[:2] == ('vf', 'add')]


def test_effective_hwdec_at_startup():
    # 两项都关：保持用户的原生硬解，不做无谓降级
    assert effective_hwdec('auto', {'motion_comp': 'off', 'superres_detail': 0}) == 'auto'
    # 运动补偿或细节增强开启：自动升为 copy-back
    assert effective_hwdec('auto', {'motion_comp': 'low'}) == 'auto-copy'
    assert effective_hwdec('auto', {'motion_comp': 'off', 'superres_detail': 30}) == 'auto-copy'
    # 用户已选 copy-back / 软解时维持原值
    assert effective_hwdec('auto-copy', {'motion_comp': 'high'}) == 'auto-copy'
    assert effective_hwdec('no', {'motion_comp': 'high'}) == 'no'
    # 每次起播自动重置增强项时，滤镜不会挂上，保持原生硬解
    assert effective_hwdec('auto', {'motion_comp': 'high', 'reset_on_new_file': True}) == 'auto'
    # 旧配置兼容
    assert normalize_hwdec(True) == 'auto-copy'
    assert normalize_hwdec(False) == 'no'
    assert normalize_hwdec('True') == 'auto-copy'
    assert effective_hwdec(False, {'motion_comp': 'low'}) == 'no'


def test_motion_comp_switches_auto_to_copyback_before_filter():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('low', 60) is True

    assert facade.hwdec_runtime == 'auto-copy'
    filters = _added_filters(facade)
    assert len(filters) == 1 and 'minterpolate' in filters[0]
    # 必须先切解码方式，再挂滤镜
    assert facade.ops.index(('set-hwdec', 'auto-copy')) < facade.ops.index(
        ('vf', 'add', filters[0]))


def test_detail_enhance_switches_auto_to_copyback():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_super_resolution('off', 30) is True

    assert facade.hwdec_runtime == 'auto-copy'
    filters = _added_filters(facade)
    assert len(filters) == 1 and 'unsharp' in filters[0]


def test_copyback_and_software_configs_are_not_touched():
    for configured in ('auto-copy', 'no'):
        facade = FakeFacade(configured)
        shader = mpv_shader.MpvShader(facade)
        assert shader.set_motion_compensation('low', 60) is True
        assert facade.hwdec_runtime == configured
        assert ('set-hwdec', 'auto-copy') not in facade.ops


def test_enhancements_off_keeps_native_hwdec():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('off', 60) is True
    assert shader.set_super_resolution('off', 0) is True

    assert facade.hwdec_runtime == 'auto'
    assert _added_filters(facade) == []
    assert ('set-hwdec', 'auto-copy') not in facade.ops


def test_hwdec_restored_after_motion_comp_off():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('low', 60) is True
    assert facade.hwdec_runtime == 'auto-copy'

    assert shader.set_motion_compensation('off', 60) is True
    assert facade.hwdec_runtime == 'auto'


def test_hwdec_restored_after_clear_super_resolution():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_super_resolution('off', 40) is True
    assert facade.hwdec_runtime == 'auto-copy'

    assert shader.clear_super_resolution() is True
    assert facade.hwdec_runtime == 'auto'


def test_hwdec_kept_until_both_enhancements_off():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('low', 60) is True
    assert shader.set_super_resolution('off', 30) is True

    # 关闭运动补偿，但细节增强仍在用滤镜 -> 仍需 copy-back
    assert shader.set_motion_compensation('off', 60) is True
    assert facade.hwdec_runtime == 'auto-copy'

    # 细节增强也关闭后才还原
    assert shader.set_super_resolution('off', 0) is True
    assert facade.hwdec_runtime == 'auto'


def test_filter_add_retries_after_video_reload():
    facade = FakeFacade('auto')
    facade.filter_add_results = [1, 0]
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('low', 60) is True
    # 首次添加失败后应重载视频再重试，而不是直接放弃
    assert ('video-reload',) in facade.ops
    assert len(_added_filters(facade)) == 2
    assert facade.hwdec_runtime == 'auto-copy'


def test_filter_skipped_and_reported_when_hwdec_switch_fails():
    facade = FakeFacade('auto')
    facade.set_hwdec_fail = True
    shader = mpv_shader.MpvShader(facade)

    assert shader.set_motion_compensation('low', 60) is False
    # 明知接不上就不要再挂滤镜，避免 mpv 反复刷格式转换失败日志
    assert _added_filters(facade) == []
    assert facade.hwdec_runtime == 'auto'
    assert facade.logger.warning.called


def test_resolve_hwdec_setting_respects_active_enhancements():
    facade = FakeFacade('auto')
    shader = mpv_shader.MpvShader(facade)

    # 未开启增强：用户在播放设置里选 auto 就保持 auto
    assert shader.resolve_hwdec('auto') == 'auto'

    assert shader.set_motion_compensation('low', 60) is True
    # 增强开启中：即使设置里选 auto，也要落在 copy-back
    assert shader.resolve_hwdec('auto') == 'auto-copy'
    assert shader.resolve_hwdec('no') == 'no'

    assert shader.set_motion_compensation('off', 60) is True
    assert shader.resolve_hwdec('auto') == 'auto'
