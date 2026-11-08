"""配色 token 加载器 —— 把 ``themes/palette.json`` 转成运行时颜色字典。

设计目标（"配色即数据"）：

1. 单一真源：色值只写在 ``themes/palette.json``，PC 端 QSS/绘制与 Android 端
   共用同一份语义 token（``panel.background``、``state.danger`` 等）。
2. 安全回退：文件缺失、JSON 非法、某个 token 缺失或取值非法时，一律回退到
   调用方（``AppStyles.COLOR_PALETTES``）的内置默认值，避免旧配置或残缺文件
   把界面渲染成全黑。
3. 纯 Python：本模块不 import Qt，便于单测与跨端复用。

对外主要接口：

- ``get_legacy_colors(mode)``：返回 ``AppStyles`` 旧键名 -> 颜色值，用于覆盖
  内置调色板（只返回校验通过的 token，未提供的键不出现在结果里）。
- ``get_token(path, mode)``：按语义路径取单个 token，如
  ``get_token('focus.indicator', 'dark')``。
- ``reload()``：丢弃缓存（测试或运行时热更新用）。
"""

import json
import os
import re
import sys
import threading

__all__ = [
    'PALETTE_FILE_NAME', 'PALETTE_ENV_VAR', 'REQUIRED_TOKENS',
    'get_palette_path', 'load_palette', 'get_mode_tokens',
    'get_legacy_colors', 'get_token', 'reload',
]

PALETTE_FILE_NAME = 'palette.json'
PALETTE_ENV_VAR = 'GUANGYU_PALETTE'

# 语义 token 路径 -> AppStyles 旧键名。旧键名保留是为了不动现有的
# QSS 生成代码与第三方调用点；语义路径才是跨端共享的契约。
LEGACY_TOKEN_MAP = {
    'background.window': 'window',
    'background.base': 'base',
    'background.base_alt': 'alternate_base',
    'background.raised': 'button',
    'background.high': 'light',
    'background.player': 'player_background',
    'background.player_placeholder': 'player_video_placeholder',
    'background.tooltip': 'tooltip_base',
    'text.primary': 'window_text',
    'text.bright': 'bright_text',
    'text.placeholder': 'placeholder',
    'text.link': 'link',
    'text.link_visited': 'link_visited',
    'text.tooltip': 'tooltip_text',
    'border.default': 'mid',
    'border.strong': 'dark',
    # 以下装饰性 token 只供语义查询与 Android 复用，不注入旧键名：
    # border_thin / border_3d_* / frosted_border* / card_color 由视觉风格
    # 修饰器按需写入，强行覆盖会改变 flat/neumorphic 等旧风格的外观。
    'panel.background': 'player_panel',
    'panel.text_primary': 'player_panel_text',
    'panel.text_secondary': 'player_panel_secondary',
    'panel.text_disabled': 'player_panel_disabled',
    'panel.text_hint': 'player_panel_hint',
    'panel.control_background': 'player_button',
    'panel.control_background_alt': 'player_combo',
    'panel.divider': 'player_line',
    'accent.base': 'accent',
    'accent.hover': 'accent_hover',
    'accent.pressed': 'accent_pressed',
    'accent.on': 'on_accent',
    'focus.indicator': 'player_accent',
    'selection.background': 'highlight',
    'selection.background_strong': 'table_selection',
    'selection.text': 'highlighted_text',
    'selection.text_strong': 'table_selection_text',
    'state.success': ('success', 'player_success'),
    'state.warning': 'warning',
    'state.danger': 'error',
    'state.danger_soft': 'player_warning',
    'state.danger_background': 'error_background',
    'state.info': 'info',
    'state.favorite': 'favorite',
    'state.favorite_background': 'favorite_background',
    'state.favorite_border': 'favorite_border',
    'slider.track': 'player_slider_track',
    'slider.volume_track': 'player_volume_track',
    'slider.fill': 'player_slider_fill',
    'slider.handle': 'player_slider_handle',
    'slider.cache': 'player_cache_bar',
    'table.header': 'table_header',
    'table.header_gradient_start': 'table_header_gradient_start',
    'table.header_gradient_middle': 'table_header_gradient_middle',
    'table.header_gradient_end': 'table_header_gradient_end',
    'table.header_text': 'table_header_text',
    'table.header_hover': 'table_header_hover',
    'table.border': 'table_border',
    'table.grid': 'table_grid',
    'table.alternate': 'table_alternate',
    'table.hover': 'table_hover',
    'table.selection': 'table_selection',
    'table.selection_text': 'table_selection_text',
    'osd.text': 'osd_text',
    'osd.border': 'osd_border',
    'osd.shadow': 'osd_shadow',
    'shadow.light': 'shadow_light',
    'shadow.dark': 'shadow_dark',
    'effect.neumorphic_light': 'neumorphic_light',
    'effect.neumorphic_dark': 'neumorphic_dark',
    'metrics.window_opacity': 'window_opacity',
}

# 跨端契约：Android 端可直接依赖这些语义 token 的存在性。
REQUIRED_TOKENS = (
    'background.window',
    'background.base',
    'background.player',
    'text.primary',
    'text.secondary',
    'border.default',
    'panel.background',
    'panel.text_primary',
    'accent.base',
    'accent.on',
    'focus.indicator',
    'selection.background',
    'state.success',
    'state.warning',
    'state.danger',
    'state.info',
    'osd.text',
    'shadow.dark',
)

_HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')
_RGBA_RE = re.compile(r'^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*(?:\d+(?:\.\d+)?|\.\d+)\s*)?\)$')

_lock = threading.RLock()
_cache_key = None
_cache_data = {}
_cache_missing_reported = False


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidate_paths():
    env_path = os.environ.get(PALETTE_ENV_VAR, '').strip()
    if env_path:
        yield env_path
    # 开发环境：仓库根目录/themes/palette.json
    yield os.path.join(_project_root(), 'themes', PALETTE_FILE_NAME)
    # PyInstaller onefile：解包目录
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        yield os.path.join(meipass, 'themes', PALETTE_FILE_NAME)
    # 打包后：exe 同级目录（便于用户直接替换换肤）
    if getattr(sys, 'frozen', False):
        yield os.path.join(os.path.dirname(sys.executable), 'themes', PALETTE_FILE_NAME)
    # 兜底：当前工作目录
    yield os.path.join(os.getcwd(), 'themes', PALETTE_FILE_NAME)


def get_palette_path():
    """返回实际生效的 palette.json 路径；都找不到时返回 None。"""
    for path in _candidate_paths():
        try:
            if path and os.path.isfile(path):
                return os.path.abspath(path)
        except OSError:
            continue
    return None


def _is_color(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(_HEX_RE.match(text) or _RGBA_RE.match(text))


def _is_metric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_value(key: str, value) -> bool:
    if key.startswith('metrics.'):
        return _is_metric(value)
    return _is_color(value)


def _load_raw():
    """读取并缓存 palette.json（按路径 + mtime + size 失效）。"""
    global _cache_key, _cache_data, _cache_missing_reported
    path = get_palette_path()
    if not path:
        with _lock:
            if not _cache_missing_reported:
                _cache_missing_reported = True
                try:
                    from core.log_manager import global_logger as logger
                    logger.warning("未找到 themes/palette.json，配色回退到内置默认值")
                except Exception:
                    pass
            _cache_key = None
            _cache_data = {}
        return {}

    try:
        stat = os.stat(path)
        key = (path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (path, None, None)

    with _lock:
        if _cache_key == key:
            return _cache_data

    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            raw = json.load(fp)
        if isinstance(raw, dict) and isinstance(raw.get('modes'), dict):
            data = raw
        else:
            raise ValueError('palette.json 顶层缺少 modes 对象')
    except Exception as exc:
        try:
            from core.log_manager import global_logger as logger
            logger.error(f"解析配色文件失败，回退内置默认值: {path}: {exc}")
        except Exception:
            pass
        data = {}

    with _lock:
        _cache_key = key
        _cache_data = data
    return data


def load_palette():
    """返回完整 palette 字典（只读语义，调用方不要就地修改）。"""
    return _load_raw()


def _resolve_mode(mode: str) -> str:
    return mode if mode in ('dark', 'light') else 'dark'


def get_mode_tokens(mode: str) -> dict:
    """返回指定模式的嵌套 token 字典（忽略非法值）。"""
    resolved = _resolve_mode(mode)
    modes = _load_raw().get('modes', {})
    tokens = modes.get(resolved)
    if not isinstance(tokens, dict):
        return {}
    return tokens


def _flatten(tokens: dict):
    """把嵌套 token 压平成 (dotted_path, value)，只保留合法值。"""
    flat = {}
    stack = [('', tokens)]
    while stack:
        prefix, node = stack.pop()
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if not isinstance(key, str):
                continue
            path = f'{prefix}.{key}' if prefix else key
            if isinstance(value, dict):
                stack.append((path, value))
            elif _validate_value(path, value):
                flat[path] = value
    return flat


def get_legacy_colors(mode: str) -> dict:
    """把 JSON token 映射成 AppStyles 旧键名。

    只返回校验通过的 token；缺失字段不会出现在结果中，因此调用方用
    ``{**内置默认值, **返回值}`` 合并即可获得"JSON 优先、旧值兜底"的效果。
    """
    flat = _flatten(get_mode_tokens(mode))
    if not flat:
        return {}
    colors = {}
    for path, legacy_names in LEGACY_TOKEN_MAP.items():
        if path not in flat:
            continue
        value = flat[path]
        names = legacy_names if isinstance(legacy_names, tuple) else (legacy_names,)
        for name in names:
            colors[name] = value
    return colors


def get_token(path: str, mode: str = 'dark', default=None):
    """按语义路径读取单个 token（自动回退到默认值）。"""
    flat = _flatten(get_mode_tokens(mode))
    return flat.get(path, default)


def reload():
    """清空缓存，下次访问时重新读盘（测试/热更新用）。"""
    global _cache_key, _cache_data, _cache_missing_reported
    with _lock:
        _cache_key = None
        _cache_data = {}
        _cache_missing_reported = False
    return get_palette_path()
