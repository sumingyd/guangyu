"""AppStyles 核心引擎 - 主题/颜色/图标/装饰基础方法。"""
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
import os

import tempfile
import atexit
import shutil
from typing import Optional


_SVG_TMPDIR: str = tempfile.mkdtemp(prefix='iptv_svg_')
atexit.register(shutil.rmtree, _SVG_TMPDIR, ignore_errors=True)


def color_to_qcolor(color_str):
    if not color_str:
        return QColor()
    if color_str.startswith('#'):
        return QColor(color_str)
    if color_str.startswith('rgba('):
        try:
            inner = color_str[5:].rstrip(')')
            parts = [p.strip() for p in inner.split(',')]
            return QColor(int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
        except Exception:
            return QColor()
    if color_str.startswith('rgb('):
        try:
            inner = color_str[4:].rstrip(')')
            parts = [p.strip() for p in inner.split(',')]
            return QColor(int(parts[0]), int(parts[1]), int(parts[2]))
        except Exception:
            return QColor()
    return QColor(color_str)


def color_to_hex(color_str) -> str:
    qc = color_to_qcolor(color_str)
    if qc.isValid():
        return qc.name()
    return color_str


def rgba_to_blended_hex(color_str, bg_color=(0, 0, 0)) -> str:
    if not color_str or not isinstance(color_str, str) or not color_str.startswith('rgba('):
        return color_to_hex(color_str) if isinstance(color_str, str) else color_str
    try:
        inner = color_str[5:].rstrip(')')
        parts = [p.strip() for p in inner.split(',')]
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = float(parts[3])
        br, bg_c, bb = bg_color
        blended_r = int(r * a + br * (1 - a))
        blended_g = int(g * a + bg_c * (1 - a))
        blended_b = int(b * a + bb * (1 - a))
        return f'#{blended_r:02x}{blended_g:02x}{blended_b:02x}'
    except Exception:
        return color_to_hex(color_str)





class StylesBase:
    """样式核心引擎 - 主题管理、颜色系统、缓存。"""
    """样式核心引擎 - 主题管理、颜色系统、图标生成、装饰基础。"""
    """应用样式管理类 - 支持颜色模式×视觉风格双维度主题"""

    _color_mode = 'dark'
    _visual_style = 'flat'
    _current_theme = 'dark'
    _arrow_cache = {}
    _check_cache = {}
    _radio_cache = {}
    _spinup_cache = {}
    _spindown_cache = {}
    _icon_cache = {}
    _cache_lock = __import__('threading').Lock()
    _sort_up_cache = {}
    _sort_down_cache = {}
    _colors_cache = None
    _colors_cache_key = None

    # 固定颜色常量（不随主题变化）
    COLOR_WHITE          = '#ffffff'
    COLOR_CLOSE_HOVER    = '#e81123'

    AVAILABLE_COLOR_MODES = ['auto', 'dark', 'light']
    AVAILABLE_VISUAL_STYLES = ['neumorphic', 'flat', 'skeuomorphic', 'frosted', 'win11', 'mac', 'ios']

    _OLD_THEME_MAPPING = {
        'dark': ('dark', 'flat'),
        'light': ('light', 'flat'),
        'dark_blue': ('dark', 'neumorphic'),
        'neumorphic_light': ('light', 'neumorphic'),
        'github_dark': ('dark', 'flat'),
        'default': ('dark', 'flat'),
    }

    @classmethod
    def _safe_fallback(cls, key: str) -> str:
        dark_fallbacks = {
            'window_text': '#ffffff',
            'accent': '#0078d4',
            'player_panel_text': '#ffffff',
            'window': '#1e1e1e',
            'mid': '#555555',
            'border_3d_light': 'rgba(255,255,255,0.15)',
            'border_3d_dark': 'rgba(0,0,0,0.5)',
            'shadow_subtle': 'rgba(0,0,0,0.3)',
            'border_thin': 'rgba(255,255,255,0.08)',
        }
        light_fallbacks = {
            'window_text': '#1e1e1e',
            'accent': '#005fb8',
            'player_panel_text': '#1e1e1e',
            'window': '#f3f3f3',
            'mid': '#b8bec7',
            'border_3d_light': 'rgba(255,255,255,0.8)',
            'border_3d_dark': 'rgba(0,0,0,0.15)',
            'shadow_subtle': 'rgba(0,0,0,0.08)',
            'border_thin': 'rgba(0,0,0,0.06)',
        }
        mode = cls._get_effective_color_mode()
        if mode == 'light':
            return light_fallbacks.get(key, '#888888')
        return dark_fallbacks.get(key, '#888888')

    @classmethod
    def get_color(cls, key: str) -> str:
        """获取主题颜色，自动使用 _safe_fallback 作为回退"""
        return cls._get_colors().get(key, cls._safe_fallback(key))

    # 统一字阶：辅助 11 / 辅助+ 12 / 正文 14 / 小标题 16 / 标题 20 / 大标题 28
    # 11 必须保留：面板列表项、徽标等 caption 语义就是 11px，
    # 旧的五档（12/14/16/20/28）会把它吸附成 12px，实测比重构前大 9%。
    FONT_SIZE_STEPS = (11, 12, 14, 16, 20, 28)

    # 三级语义字号：辅助（说明/徽标）/ 正文（按钮/输入）/ 标题（区块标题）
    FONT_LEVELS = {'caption': 11, 'body': 12, 'title': 14}

    @classmethod
    def fs(cls, level: str = 'body') -> int:
        """语义字号（px），取重构前的固定值。

        重构前各面板样式就是字面量 14/12/11px，没有乘屏宽因子；
        引入 get_ui_scale() 后在高分屏上会被放大两次（系统 DPI 已放大一次，
        token 再乘 1.15/1.3），实测观感明显大于重构前，故恢复固定值。
        """
        return cls.FONT_LEVELS.get(level, 12)

    @classmethod
    def font_size(cls, level: str) -> int:
        """语义字阶：caption(辅助)/body(正文)/subtitle(小标题)/title(标题)/display(大标题)"""
        return {'caption': 12, 'body': 14, 'subtitle': 16,
                'title': 20, 'display': 28}.get(level, 14)

    @classmethod
    def normalize_font_sizes(cls, qss: str) -> str:
        """把 QSS 文本中所有 font-size: Npx 吸附到标准字阶。

        并列时取较小档：旧实现取较大档，会把 13px 抬成 14px，
        在高分屏（scale=1.15）上 caption 被放大 27%，是面板字偏大的来源之一。
        """
        if not qss:
            return qss
        import re
        steps = cls.FONT_SIZE_STEPS

        def _snap(m):
            px = int(m.group(1))
            snapped = min(steps, key=lambda s: (abs(s - px), s))
            return f"font-size: {snapped}px"

        return re.sub(r'font-size:\s*(\d+)px', _snap, qss)

    @classmethod
    def _get_scaled_radius(cls, widget_type: str) -> int:
        r = cls._get_style_border_radius()
        scaling = {
            'default': r,
            'tab': max(r - 2, 4),
            'list_item': max(r - 4, 2),
            'indicator': max(r - 4, 3),
            'badge': max(r - 6, 2),
            'slider_handle': max(r - 2, 3),
            'menu': max(r - 2, 4),
            'scrollbar': max(r - 4, 3),
        }
        return scaling.get(widget_type, r)

    @classmethod
    def _detect_system_color_mode(cls):
        from utils.platform_utils import is_android, is_macos, is_windows, is_linux
        if is_android():
            try:
                if QGuiApplication.instance():
                    color_scheme = QGuiApplication.styleHints().colorScheme()
                    if color_scheme == Qt.ColorScheme.Dark:
                        return 'dark'
                    elif color_scheme == Qt.ColorScheme.Light:
                        return 'light'
            except Exception:
                pass
        if is_macos():
            try:
                import subprocess
                result = subprocess.run(
                    ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and 'Dark' in result.stdout:
                    return 'dark'
                return 'light'
            except Exception:
                pass
        if is_windows():
            try:
                import ctypes
                registry = ctypes.windll.advapi32
                key = ctypes.c_ulong()
                access = 0x20019
                result = registry.RegOpenKeyExW(0x80000001, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize', 0, access, ctypes.byref(key))
                if result == 0:
                    value = ctypes.c_ulong()
                    size = ctypes.c_ulong(4)
                    registry.RegQueryValueExW(key.value, 'AppsUseLightTheme', 0, None, ctypes.byref(value), ctypes.byref(size))
                    registry.RegCloseKey(key.value)
                    return 'light' if value.value == 1 else 'dark'
            except Exception:
                pass
        try:
            if QGuiApplication.instance():
                color_scheme = QGuiApplication.styleHints().colorScheme()
                if color_scheme == Qt.ColorScheme.Dark:
                    return 'dark'
                elif color_scheme == Qt.ColorScheme.Light:
                    return 'light'
        except Exception:
            pass
        if is_linux():
            try:
                import subprocess as _sp
                result = _sp.run(
                    ['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    val = result.stdout.strip()
                    if 'dark' in val:
                        return 'dark'
                    if 'light' in val:
                        return 'light'
            except Exception:
                pass
        try:
            palette = QCoreApplication.instance().palette() if QCoreApplication.instance() else None
            if palette:
                window_bg = palette.color(QPalette.ColorRole.Window)
                text_color = palette.color(QPalette.ColorRole.WindowText)
                if text_color.lightness() > window_bg.lightness():
                    return 'dark'
                return 'light'
        except Exception:
            pass
        return 'dark'

    @classmethod
    def _get_effective_color_mode(cls):
        if cls._color_mode == 'auto':
            return cls._detect_system_color_mode()
        return cls._color_mode

    @classmethod
    def _get_colors(cls):
        effective_mode = cls._get_effective_color_mode()
        cache_key = (effective_mode, cls._visual_style)
        with cls._cache_lock:
            if cls._colors_cache is not None and cls._colors_cache_key == cache_key:
                return cls._colors_cache
        base_colors = dict(cls.COLOR_PALETTES.get(effective_mode, cls.COLOR_PALETTES['dark']))
        # 主题 JSON（themes/palette.json）是配色单一真源：覆盖内置默认值。
        # 文件缺失 / JSON 非法 / 字段非法时 get_legacy_colors 只返回可用项，
        # 剩余键继续沿用上方内置默认值，保证任何异常都不会把界面渲染成黑色。
        overrides = cls._palette_overrides(effective_mode)
        if overrides:
            base_colors.update(overrides)
        style = cls._visual_style
        if style == 'neumorphic':
            result = cls._style_modifier_neumorphic(base_colors.copy(), effective_mode)
        elif style == 'skeuomorphic':
            result = cls._style_modifier_skeuomorphic(base_colors.copy(), effective_mode)
        elif style == 'frosted':
            result = cls._style_modifier_frosted(base_colors.copy(), effective_mode)
        elif style == 'win11':
            result = cls._style_modifier_win11(base_colors.copy(), effective_mode)
        elif style == 'mac':
            result = cls._style_modifier_mac(base_colors.copy(), effective_mode)
        elif style == 'ios':
            result = cls._style_modifier_ios(base_colors.copy(), effective_mode)
        else:
            result = base_colors.copy()
        with cls._cache_lock:
            cls._colors_cache = result
            cls._colors_cache_key = cache_key
        return result

    @classmethod
    def _palette_overrides(cls, effective_mode: str) -> dict:
        """读取 themes/palette.json 并转成旧键名；任何异常都回退为空字典。"""
        try:
            from ui.palette import get_legacy_colors
            return get_legacy_colors(effective_mode)
        except Exception as e:
            try:
                from core.log_manager import global_logger as logger
                logger.warning(f"加载主题 token 失败，使用内置默认配色: {e}")
            except Exception:
                pass
            return {}

    @classmethod
    def reload_theme_tokens(cls):
        """重新读取 palette.json 并清缓存（换肤不重启时调用）。"""
        try:
            from ui.palette import reload as reload_palette
            reload_palette()
        except Exception:
            pass
        cls._invalidate_caches()

    @classmethod
    def _get_qss_colors(cls):
        colors = cls._get_colors()
        if cls._visual_style == 'frosted':
            effective_mode = cls._get_effective_color_mode()
            bg = (0, 0, 0) if effective_mode == 'dark' else (255, 255, 255)
            qss_colors = {}
            for k, v in colors.items():
                if isinstance(v, str) and v.startswith('rgba'):
                    qss_colors[k] = rgba_to_blended_hex(v, bg)
                else:
                    qss_colors[k] = v
            return qss_colors
        return colors

    COLOR_KEYS = frozenset({
        'accent', 'window', 'window_text', 'base', 'alternate_base',
        'button', 'button_text', 'button_hover', 'button_pressed',
        'light', 'mid', 'dark', 'shadow_dark', 'shadow_light',
        'neumorphic_light', 'neumorphic_dark', 'midlight',
        'highlight', 'highlighted_text', 'tooltip_base', 'tooltip_text',
        'table_alternate', 'border', 'border_focus', 'text',
        'disabled_text', 'bright_text',
    })

    @classmethod
    def set_theme(cls, theme_name):
        if '+' in theme_name:
            parts = theme_name.split('+')
            if len(parts) == 2:
                cls._color_mode = parts[0]
                cls._visual_style = parts[1]
                cls._current_theme = theme_name
                return
        mapping = cls._OLD_THEME_MAPPING.get(theme_name)
        if mapping:
            cls._color_mode, cls._visual_style = mapping
        else:
            cls._color_mode = theme_name
            cls._visual_style = 'flat'
        cls._current_theme = f"{cls._color_mode}+{cls._visual_style}"

    @classmethod
    def set_color_mode(cls, mode):
        if mode in cls.AVAILABLE_COLOR_MODES:
            cls._color_mode = mode
            cls._current_theme = f"{cls._color_mode}+{cls._visual_style}"
            cls._invalidate_caches()

    @classmethod
    def set_visual_style(cls, style):
        if style in cls.AVAILABLE_VISUAL_STYLES:
            cls._visual_style = style
            cls._current_theme = f"{cls._color_mode}+{cls._visual_style}"
            cls._invalidate_caches()

    @classmethod
    def _invalidate_caches(cls):
        with cls._cache_lock:
            cls._colors_cache = None
            cls._colors_cache_key = None
            for cache in (cls._icon_cache, cls._arrow_cache, cls._check_cache,
                          cls._radio_cache, cls._spinup_cache, cls._spindown_cache,
                          cls._sort_up_cache, cls._sort_down_cache):
                cache.clear()


    @staticmethod
    def get_theme():
        return AppStyles._current_theme

    @classmethod
    def get_color_mode(cls):
        return cls._color_mode

    @classmethod
    def get_visual_style(cls):
        return cls._visual_style

    @classmethod
    def is_style(cls, style_name):
        return cls._visual_style == style_name

    @staticmethod
    def get_available_themes():
        return list(AppStyles._OLD_THEME_MAPPING.keys()) + [f"{m}+{s}" for m in ('dark', 'light') for s in AppStyles.AVAILABLE_VISUAL_STYLES]

    @staticmethod
    def is_neumorphic():
        return AppStyles._visual_style == 'neumorphic'

    # 具备“玻璃”语义的风格：必须实打实有模糊，而不是半透明纯色
    GLASS_STYLES = ('frosted', 'win11', 'mac', 'ios')

    @classmethod
    def is_glass_style(cls) -> bool:
        return cls._visual_style in cls.GLASS_STYLES

    @classmethod
    def get_card_alpha(cls) -> int:
        """玻璃卡片统一透明度：玻璃风格带通透感，其余风格必须是实色"""
        return 168 if cls.is_glass_style() else 255

    @classmethod
    def _get_style_border_radius(cls):
        radii = {
            'flat': 4,
            'neumorphic': 10,
            'skeuomorphic': 6,
            'frosted': 12,
            'win11': 8,
            'mac': 12,
            'ios': 14,
        }
        return radii.get(cls._visual_style, 4)

    @classmethod
    def _get_style_shadow(cls):
        c = cls._get_colors()
        effective = cls._get_effective_color_mode()
        shadows = {
            'flat': f"0 1px 3px {c['shadow_dark']}",
            'neumorphic': f"4px 4px 8px {c['shadow_dark']}, -4px -4px 8px {c['shadow_light']}",
            'skeuomorphic': f"2px 2px 6px {c.get('shadow_dark', 'rgba(0,0,0,0.3)')}, -1px -1px 3px {c.get('shadow_light', 'rgba(255,255,255,0.1)')}",
            'frosted': f"0 4px 16px {c.get('shadow_dark', 'rgba(0,0,0,0.2)')}",
            'win11': f"0 2px 4px {c.get('shadow_dark', 'rgba(0,0,0,0.16)')}",
            'mac': f"0 1px 4px {c.get('shadow_dark', 'rgba(0,0,0,0.1)')}, 0 0 0 0.5px {c.get('border_thin', 'rgba(0,0,0,0.04)')}",
            'ios': f"0 2px 8px {c.get('shadow_dark', 'rgba(0,0,0,0.12)')}",
        }
        return shadows.get(cls._visual_style, f"0 1px 3px {c['shadow_dark']}")

    @classmethod
    def _get_style_inset(cls):
        c = cls._get_colors()
        if cls._visual_style == 'neumorphic':
            return (
                f"border: 2px solid;"
                f"border-top-color: {c['shadow_dark']};"
                f"border-left-color: {c['shadow_dark']};"
                f"border-bottom-color: {c['shadow_light']};"
                f"border-right-color: {c['shadow_light']};"
            )
        if cls._visual_style == 'skeuomorphic':
            return (
                f"border: 2px solid;"
                f"border-top-color: {c.get('border_3d_dark', c['shadow_dark'])};"
                f"border-left-color: {c.get('border_3d_dark', c['shadow_dark'])};"
                f"border-bottom-color: {c.get('border_3d_light', c['shadow_light'])};"
                f"border-right-color: {c.get('border_3d_light', c['shadow_light'])};"
            )
        if cls._visual_style == 'frosted':
            return f"border: 1px solid {c.get('frosted_border_mid', c['mid'])};"
        if cls._visual_style == 'win11':
            return f"border: 1px solid {c.get('border_thin', c['mid'])};"
        if cls._visual_style == 'mac':
            return f"border: 1px solid; border-top-color: {c.get('shadow_subtle', c['shadow_dark'])}; border-left-color: {c.get('shadow_subtle', c['shadow_dark'])}; border-bottom-color: {c['mid']}; border-right-color: {c['mid']};"
        if cls._visual_style == 'ios':
            return f"border: 1px solid {c.get('shadow_subtle', c['shadow_dark'])};"
        return f"border: 1px solid {c.get('mid', cls._safe_fallback('mid'))};"

    @classmethod
    def _get_style_raised(cls):
        c = cls._get_colors()
        if cls._visual_style == 'neumorphic':
            return (
                f"border: 2px solid;"
                f"border-top-color: {c['shadow_light']};"
                f"border-left-color: {c['shadow_light']};"
                f"border-bottom-color: {c['shadow_dark']};"
                f"border-right-color: {c['shadow_dark']};"
            )
        if cls._visual_style == 'skeuomorphic':
            return (
                f"border: 2px solid;"
                f"border-top-color: {c.get('border_3d_light', c['shadow_light'])};"
                f"border-left-color: {c.get('border_3d_light', c['shadow_light'])};"
                f"border-bottom-color: {c.get('border_3d_dark', c['shadow_dark'])};"
                f"border-right-color: {c.get('border_3d_dark', c['shadow_dark'])};"
            )
        if cls._visual_style == 'frosted':
            return f"border: 1px solid {c.get('frosted_border_strong', c['mid'])};"
        if cls._visual_style == 'win11':
            return f"border: 1px solid {c.get('border_thin', c['mid'])};"
        if cls._visual_style == 'mac':
            return f"border: 1px solid {c.get('shadow_subtle', c['mid'])};"
        if cls._visual_style == 'ios':
            return f"border: 1px solid {c.get('shadow_subtle', c['mid'])};"
        return f"border: 1px solid {c.get('mid', cls._safe_fallback('mid'))};"

    @staticmethod
    def _neumorphic_inset():
        return AppStyles._get_style_inset()

    @staticmethod
    def _neumorphic_raised():
        return AppStyles._get_style_raised()

    @classmethod
    def _get_style_font_family(cls):
        from utils.platform_utils import is_macos, is_linux, is_android
        cjk = "'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', sans-serif"
        if is_android():
            fonts = {
                'win11': f"'Roboto', 'Noto Sans', {cjk}",
                'mac': f"'Roboto', 'Noto Sans', {cjk}",
                'ios': f"'Roboto', 'Noto Sans', {cjk}",
            }
            return fonts.get(cls._visual_style, f"'Roboto', 'Noto Sans', {cjk}")
        if is_macos():
            fonts = {
                'win11': f"'Helvetica Neue', {cjk}",
                'mac': f"'SF Pro Display', 'Helvetica Neue', {cjk}",
                'ios': f"'SF Pro Display', 'Helvetica Neue', {cjk}",
            }
            return fonts.get(cls._visual_style, f"'Helvetica Neue', {cjk}")
        if is_linux():
            fonts = {
                'win11': f"'Noto Sans', 'Ubuntu', {cjk}",
                'mac': f"'Noto Sans', 'Helvetica Neue', {cjk}",
                'ios': f"'Noto Sans', 'Helvetica Neue', {cjk}",
            }
            return fonts.get(cls._visual_style, f"'Noto Sans', 'Ubuntu', {cjk}")
        fonts = {
            'win11': f"'Segoe UI Variable', 'Segoe UI', {cjk}",
            'mac': f"'SF Pro Display', 'Helvetica Neue', 'Segoe UI', {cjk}",
            'ios': f"'SF Pro Display', 'Helvetica Neue', 'Segoe UI', {cjk}",
        }
        return fonts.get(cls._visual_style, f"'Segoe UI', {cjk}")

