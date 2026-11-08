"""配色 token 层测试：单一真源、跨端契约与安全回退。

这些测试只依赖纯 Python 的 ui.palette，不需要 Qt，也不需要真实渲染。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import build
from ui import palette


@pytest.fixture(autouse=True)
def _reset_palette_cache():
    palette.reload()
    yield
    palette.reload()


def test_palette_file_is_source_of_truth():
    path = palette.get_palette_path()
    assert path, "themes/palette.json 必须存在，否则无法换肤"
    assert Path(path).name == 'palette.json'

    data = palette.load_palette()
    assert data.get('version') == 1
    assert set(data['modes']) >= {'dark', 'light'}


def test_required_semantic_tokens_exist_in_both_modes():
    for mode in ('dark', 'light'):
        flat = palette.get_mode_tokens(mode)
        for token in palette.REQUIRED_TOKENS:
            node = flat
            for part in token.split('.'):
                assert isinstance(node, dict) and part in node, f'{mode} 缺少 token: {token}'
                node = node[part]


def test_all_colors_are_valid_or_dropped():
    data = palette.load_palette()
    for mode, tokens in data['modes'].items():
        for path, value in palette._flatten(tokens).items():
            if path.startswith('metrics.'):
                assert isinstance(value, (int, float))
            else:
                assert palette._is_color(value), f'{mode}.{path} 取值非法: {value!r}'


def test_legacy_mapping_covers_core_keys():
    colors = palette.get_legacy_colors('dark')
    # QSS 生成代码直接按旧键名取值，缺任何一个都会 KeyError / 变成 fallback 灰
    for legacy_key in (
        'window', 'base', 'window_text', 'mid', 'accent', 'player_panel',
        'player_panel_text', 'player_line', 'osd_text', 'shadow_dark',
        'favorite', 'on_accent',
    ):
        assert legacy_key in colors, f'缺少旧键名映射: {legacy_key}'
        assert palette._is_color(colors[legacy_key])

    # 装饰性 token 不进旧键名（避免改变 flat 风格外观），但语义查询必须可用
    for token in ('border.thin', 'border.frosted_mid', 'panel.card', 'shadow.subtle'):
        assert palette._is_color(palette.get_token(token, 'dark'))


def test_legacy_values_match_json_tokens():
    colors = palette.get_legacy_colors('light')
    assert colors['window'] == palette.get_token('background.window', 'light')
    assert colors['accent'] == palette.get_token('accent.base', 'light')
    assert colors['osd_text'] == palette.get_token('osd.text', 'light')
    assert colors['player_panel'] == palette.get_token('panel.background', 'light')


def test_missing_file_falls_back_to_empty_overrides(monkeypatch):
    monkeypatch.setenv(palette.PALETTE_ENV_VAR, str(Path('__not_exists__') / 'palette.json'))
    monkeypatch.setattr(palette, '_candidate_paths', lambda: iter(()))
    palette.reload()
    assert palette.get_palette_path() is None
    assert palette.get_legacy_colors('dark') == {}
    assert palette.get_token('accent.base', 'dark', '#123456') == '#123456'


def test_invalid_values_are_filtered(monkeypatch, tmp_path):
    bogus = tmp_path / 'palette.json'
    bogus.write_text(json.dumps({
        'version': 1,
        'modes': {
            'dark': {
                'accent': {'base': 'not-a-color', 'hover': '#3a6eff'},
                'background': {'window': '#12345'},
                'metrics': {'window_opacity': 'alpha'},
            }
        },
    }), encoding='utf-8')
    monkeypatch.setenv(palette.PALETTE_ENV_VAR, str(bogus))
    palette.reload()

    colors = palette.get_legacy_colors('dark')
    assert 'accent' not in colors            # 非法色值被丢弃 -> 调用方用内置默认
    assert colors['accent_hover'] == '#3a6eff'
    assert 'window' not in colors
    assert 'window_opacity' not in colors


def test_themes_dir_is_bundled():
    assert 'themes' in build.DATA_DIRS
