"""ui/typography.py 单元测试：字号档位与界面缩放的换算契约。"""

import pytest

from ui import typography


@pytest.fixture(autouse=True)
def _reset_display():
    typography.set_display('standard', 100)
    yield
    typography.set_display('standard', 100)


def test_default_display_is_identity():
    assert typography.get_font_tier() == 'standard'
    assert typography.get_ui_scale_percent() == 100
    qss = 'QWidget{font-size:12px;padding:6px;min-height:28px;border:1px solid #fff;}'
    assert typography.scale_qss(qss) == qss


def test_text_and_layout_factors_are_independent():
    # 字号档位只偏文字，不动布局
    typography.set_display('large', 100)
    assert typography.scale_px(12, text=True) == 14
    assert typography.scale_px(6, text=False) == 6
    # 界面缩放同时作用于两者
    typography.set_display('standard', 150)
    assert typography.scale_px(12, text=True) == 18
    assert typography.scale_px(6, text=False) == 9


def test_max_tier_qss_scaling():
    typography.set_display('xlarge', 150)
    qss = (
        'QWidget{font-size:12px;padding:6px 12px;min-height:28px;'
        'border:1px solid #ffffff;background:rgba(1, 2, 3, 0.5);height:0px;}'
    )
    scaled = typography.scale_qss(qss)
    assert 'font-size:24px' in scaled          # 12 × (16/12) × 1.5
    assert 'padding:9px 18px' in scaled        # 只跟缩放
    assert 'min-height:42px' in scaled
    assert 'border:1px solid #ffffff' in scaled  # 边框宽度不放大
    assert 'rgba(1, 2, 3, 0.5)' in scaled        # 颜色数值不放大
    assert 'height:0px' in scaled                # 0 保持 0


def test_scale_qss_is_safe_for_non_strings():
    assert typography.scale_qss(None) is None
    assert typography.scale_qss('') == ''


def test_normalize_falls_back_on_invalid_values():
    assert typography.normalize_tier('xlarge') == 'xlarge'
    assert typography.normalize_tier('huge') == 'standard'
    assert typography.normalize_percent('125') == 125
    assert typography.normalize_percent('133') == 100
    assert typography.normalize_percent(None) == 100


def test_config_roundtrip():
    class FakeConfig:
        def __init__(self):
            self.saved = None

        def load_display_settings(self):
            return 'large', '125'

        def save_display_settings(self, tier, percent):
            self.saved = (tier, percent)
            return True

    fake = FakeConfig()
    typography.load_from_config(fake)
    assert typography.current_display() == ('large', 125)

    typography.set_display('xlarge', 150)
    tier, percent = typography.current_display()
    fake.save_display_settings(tier, percent)
    assert fake.saved == ('xlarge', 150)


def test_scaled_icon_and_row_height_follow_layout_only():
    typography.set_display('xlarge', 150)
    assert typography.scaled_icon(16) == 24
    assert typography.scaled_row_height(44) == 66
    typography.set_display('small', 100)
    assert typography.scaled_icon(16) == 16
