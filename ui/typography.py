"""PC 端字号 / 界面尺寸单一真源。

背景
----
PC 端各处样式里的 ``font-size``、``min-height``、``padding`` 长期以字面量散落
在 QSS 与 ``setFixedSize`` 调用中。只调用 ``QApplication.setFont`` 时，带
``font-size`` 的控件不跟随、不带的行高又跟着变，导致按钮文字溢出、表格行高
不动、EPG 时间线错位。

为此把「字号档位」和「界面缩放」收敛到本模块：

* ``FONT_TIERS``：字号档位表（小 / 标准 / 大 / 特大），以 pt 与正文 px 标定。
* ``UI_SCALE_OPTIONS``：界面缩放档位（100 / 110 / 125 / 150）。
* ``DERIVED_RATIOS``：图标、行高、间距等派生尺寸相对缩放档位的比例。

两者关系：**缩放是整体等比，字号档位只在缩放基础上再偏文字**。

* 布局尺寸（padding / min-height / 图标 / 行高 / 时间刻度）= 基准 × 缩放；
* 文字尺寸（font-size）= 基准 × 字号系数 × 缩放。

因此 100% 缩放 + 特大字号只会让文字变大而界面不松开，150% 缩放 + 小字号则
整体放大但文字相对更紧凑，两者不会互相重复放大。

本模块是 PC 专属的：``themes/palette.json`` 是 PC 与 Android 共用的配色真源，
字号键不写进该文件，避免污染 Android 侧。

模块本身不 import Qt（应用字体时才延迟导入），便于单测与跨端复用。
"""

import re
import threading

__all__ = [
    'FONT_TIERS', 'DEFAULT_FONT_TIER', 'UI_SCALE_OPTIONS', 'DEFAULT_UI_SCALE',
    'DERIVED_RATIOS', 'normalize_tier', 'normalize_percent',
    'get_font_tier', 'get_ui_scale_percent', 'text_factor', 'layout_factor',
    'scale_px', 'scale_size', 'scaled_icon', 'scaled_row_height', 'scaled_pt',
    'scale_qss', 'apply_application_font', 'load_from_config',
    'set_display', 'current_display',
    'install_qss_scaler', 'rescale_all_widgets', 'is_scaler_installed',
    'relax_fixed_metrics',
]

# 字号档位表（唯一真源）。pt 为应用级基准字号，body_px 为 QSS 正文基准，
# factor 为相对「标准」的文字系数，用于换算所有 font-size。
FONT_TIERS = {
    'small': {
        'pt': 8.0, 'body_px': 11, 'factor': 11 / 12,
        'zh': '小', 'en': 'Small',
    },
    'standard': {
        'pt': 9.0, 'body_px': 12, 'factor': 1.0,
        'zh': '标准', 'en': 'Standard',
    },
    'large': {
        'pt': 10.5, 'body_px': 14, 'factor': 14 / 12,
        'zh': '大', 'en': 'Large',
    },
    'xlarge': {
        'pt': 12.0, 'body_px': 16, 'factor': 16 / 12,
        'zh': '特大', 'en': 'Extra Large',
    },
}

DEFAULT_FONT_TIER = 'standard'

# 界面缩放档位（百分比）。同时作用于文字与布局。
UI_SCALE_OPTIONS = (100, 110, 125, 150)
DEFAULT_UI_SCALE = 100

# 派生尺寸比例：全部相对「界面缩放」而非字号档位。
# 保留这张表是为了让后续新增的尺寸类型有统一入口，而不是又写一个魔数。
DERIVED_RATIOS = {
    'icon': 1.0,            # 按钮/工具图标
    'row_height': 1.0,      # 列表行高
    'spacing': 1.0,         # 控件间距
    'padding': 1.0,         # 内边距
    'control_height': 1.0,  # 控制栏按钮高度
    'epg_hour_width': 1.0,  # EPG 每小时列宽
    'epg_row_height': 1.0,  # EPG 行高
}

_lock = threading.RLock()
_font_tier = DEFAULT_FONT_TIER
_ui_scale_percent = DEFAULT_UI_SCALE

# 需要按缩放换算的 QSS 属性（文字属性单独用 font-size）。
_TEXT_PROPERTIES = frozenset({'font-size'})
_LAYOUT_PROPERTIES = frozenset({
    'padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom',
    'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom',
    'min-width', 'min-height', 'max-width', 'max-height',
    'width', 'height', 'border-radius', 'spacing',
})

_PROP_RE = re.compile(
    r'(?P<head>(?P<prop>[A-Za-z-]+)\s*:\s*)(?P<value>[^;{}]*)'
)
_PX_RE = re.compile(r'(?<![\w.#])(-?\d+(?:\.\d+)?)px\b')


def normalize_tier(tier) -> str:
    """把任意输入规范成合法档位名，非法时回退标准档。"""
    if isinstance(tier, str):
        key = tier.strip().lower()
        if key in FONT_TIERS:
            return key
    return DEFAULT_FONT_TIER


def normalize_percent(percent) -> int:
    """把任意输入规范成合法缩放档位，非法时回退 100。"""
    try:
        value = int(str(percent).strip().rstrip('%'))
    except (TypeError, ValueError):
        return DEFAULT_UI_SCALE
    if value not in UI_SCALE_OPTIONS:
        return DEFAULT_UI_SCALE
    return value


def get_font_tier() -> str:
    with _lock:
        return _font_tier


def get_ui_scale_percent() -> int:
    with _lock:
        return _ui_scale_percent


def text_factor() -> float:
    """文字相对系数（字号档位），不包含界面缩放。"""
    with _lock:
        tier = _font_tier
    return float(FONT_TIERS[tier]['factor'])


def layout_factor() -> float:
    """界面整体缩放系数（1.0 / 1.1 / 1.25 / 1.5）。"""
    with _lock:
        percent = _ui_scale_percent
    return percent / 100.0


def scale_px(px: float, text: bool = False) -> int:
    """把基准像素换算成当前生效像素。

    ``text=True`` 时叠加字号档位系数，用于文字；否则只跟随界面缩放。
    0 保持 0（0px 用于关闭边框/指示器，不能被放大）。
    """
    if not px:
        return 0
    factor = layout_factor() * (text_factor() if text else 1.0)
    value = px * factor
    if value > 0:
        return max(1, int(round(value)))
    return min(-1, int(round(value)))


def scale_size(width: float, height: float):
    """按界面缩放换算一对尺寸（对话框初始大小等）。"""
    return scale_px(width), scale_px(height)


def scaled_icon(base: int) -> int:
    """图标尺寸：只跟随界面缩放。"""
    return scale_px(base * DERIVED_RATIOS['icon'])


def scaled_pt(base_pt: float) -> float:
    """代码里直接 setPointSize 的场景：按字号档位与界面缩放换算。

    基准为「标准档 9pt」，与 QSS 的 12px 正文对齐；不经过 QSS 拦截器，
    因此不会被二次放大。
    """
    return max(
        6.0,
        float(base_pt) * (float(FONT_TIERS[get_font_tier()]['pt']) / 9.0) * layout_factor(),
    )


def scaled_row_height(base: int) -> int:
    """列表/时间线行高：只跟随界面缩放。"""
    return scale_px(base * DERIVED_RATIOS['row_height'])


def _format_px(value: float) -> str:
    rounded = int(round(value))
    if value > 0:
        rounded = max(1, rounded)
    elif value < 0:
        rounded = min(-1, rounded)
    return f'{rounded}px'


def _scale_value(value: str, factor: float) -> str:
    if not value or 'px' not in value:
        return value

    def _repl(match):
        number = float(match.group(1))
        if number == 0:
            return '0px'
        return _format_px(number * factor)

    return _PX_RE.sub(_repl, value)


def scale_qss(qss: str) -> str:
    """按单一真源换算一段 QSS。

    只处理白名单属性：
    * ``font-size`` → 字号系数 × 缩放；
    * 间距/行高/圆角/宽高等 → 缩放。

    颜色、边框宽度、``url(...)``、``0px`` 一律不动。默认档位（标准 + 100%）
    直接原样返回，保证不改变现有观感，也避免无意义的字符串重写。
    """
    if not qss or not isinstance(qss, str):
        return qss
    layout = layout_factor()
    text = layout * text_factor()
    if abs(layout - 1.0) < 1e-9 and abs(text - 1.0) < 1e-9:
        return qss

    def _repl(match):
        prop = match.group('prop').lower()
        if prop in _TEXT_PROPERTIES:
            factor = text
        elif prop in _LAYOUT_PROPERTIES:
            factor = layout
        else:
            return match.group(0)
        value = _scale_value(match.group('value'), factor)
        return f"{match.group('head')}{value}"

    return _PROP_RE.sub(_repl, qss)


def apply_application_font(app=None) -> None:
    """把应用级字体设成当前档位（未显式设 font-size 的控件跟随）。

    pt 为绝对档位值乘以界面缩放：100% 时标准档即 9pt（Windows 默认），
    与 QSS 的 12px 正文一致，不会双重放大。
    """
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    application = app or QApplication.instance()
    if application is None:
        return
    try:
        font = application.font()
        font.setPointSizeF(max(6.0, float(FONT_TIERS[get_font_tier()]['pt']) * layout_factor()))
        application.setFont(font)
    except Exception:
        pass


def current_display():
    """返回 ``(tier, percent)``，供配置持久化使用。"""
    return get_font_tier(), get_ui_scale_percent()


def set_display(tier=None, percent=None) -> bool:
    """更新档位，返回是否发生变化（无变化时不触发界面重刷）。"""
    global _font_tier, _ui_scale_percent
    with _lock:
        new_tier = normalize_tier(tier) if tier is not None else _font_tier
        new_percent = normalize_percent(percent) if percent is not None else _ui_scale_percent
        changed = (new_tier != _font_tier) or (new_percent != _ui_scale_percent)
        _font_tier = new_tier
        _ui_scale_percent = new_percent
    return changed


def load_from_config(config) -> None:
    """从 ConfigManager 读取档位；任何异常都保持默认值。"""
    tier = DEFAULT_FONT_TIER
    percent = DEFAULT_UI_SCALE
    try:
        if config is not None:
            tier, percent = config.load_display_settings()
    except Exception:
        pass
    with _lock:
        global _font_tier, _ui_scale_percent
        _font_tier = normalize_tier(tier)
        _ui_scale_percent = normalize_percent(percent)


# ==================== QSS 统一拦截器 ====================
# 应用里几百处 setStyleSheet 各自拼接 QSS，无法逐处改写。这里在 QWidget
# 上装一个薄钩子：记录原始 QSS，写入时统一按 typography 换算；切换档位时
# 用原始 QSS 重放，即可覆盖所有对话框/弹窗/菜单，做到立即生效。

_original_set_style_sheet = None
_BASE_QSS_PROPERTY = '_gy_base_qss'


def is_scaler_installed() -> bool:
    return _original_set_style_sheet is not None


def install_qss_scaler() -> None:
    """安装全局 QSS 换算钩子（进程内只需一次）。"""
    global _original_set_style_sheet
    if _original_set_style_sheet is not None:
        return
    try:
        from PySide6.QtWidgets import QWidget
    except Exception:
        return
    original = QWidget.setStyleSheet

    def _set_style_sheet(widget, qss):
        base = qss or ''
        try:
            widget.setProperty(_BASE_QSS_PROPERTY, base)
        except Exception:
            pass
        try:
            return original(widget, scale_qss(base))
        except RuntimeError:
            # 控件已销毁（延迟信号回调），忽略即可
            return None

    QWidget.setStyleSheet = _set_style_sheet
    _original_set_style_sheet = original


def rescale_all_widgets() -> None:
    """用记录的原始 QSS 重放全部控件（改档位后立即生效）。"""
    if _original_set_style_sheet is None:
        return
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        try:
            base = widget.property(_BASE_QSS_PROPERTY)
            if base is None:
                continue
            _original_set_style_sheet(widget, scale_qss(base))
        except (RuntimeError, TypeError):
            continue


def relax_fixed_metrics(root) -> int:
    """放宽「写死高度/宽度」但已装不下当前字号的文本控件。

    setFixedHeight / setFixedWidth 不经过样式表，字号档位放大后会出现
    输入框、按钮文字被裁。这里只在「最小值 == 最大值（即确实写死）且小于
    当前字体所需」时解除约束，属于兜底而非全面布局重写：
    * 进度条、分隔线等非文本控件不受影响；
    * 一旦放宽，min != max，后续调用会跳过，具备幂等性。
    """
    if root is None:
        return 0
    if abs(layout_factor() - 1.0) < 1e-9 and abs(text_factor() - 1.0) < 1e-9:
        # 标准档 + 100% 时保持既有布局，不要让兜底逻辑改变默认观感
        return 0
    try:
        from PySide6.QtWidgets import (
            QWidget, QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox,
        )
    except Exception:
        return 0
    changed = 0
    widgets = [root]
    try:
        widgets.extend(root.findChildren(QWidget))
    except RuntimeError:
        return 0
    for widget in widgets:
        try:
            font_metrics = widget.fontMetrics()
            min_h, max_h = widget.minimumHeight(), widget.maximumHeight()
            need_h = font_metrics.height() + 10
            if min_h == max_h and 0 < min_h < need_h:
                widget.setMinimumHeight(need_h)
                widget.setMaximumHeight(16777215)
                changed += 1

            text = ''
            if isinstance(widget, QAbstractButton):
                text = widget.text()
            elif isinstance(widget, QLineEdit):
                text = widget.text()
            elif isinstance(widget, (QComboBox, QAbstractSpinBox)):
                text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            if not text:
                continue
            need_w = font_metrics.horizontalAdvance(text) + 18
            min_w, max_w = widget.minimumWidth(), widget.maximumWidth()
            if min_w == max_w and 0 < min_w < need_w:
                widget.setMinimumWidth(min(need_w, 480))
                widget.setMaximumWidth(16777215)
                changed += 1
        except RuntimeError:
            continue
    return changed
