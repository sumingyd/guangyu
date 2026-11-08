"""屏保覆盖层（PC）：与 Android 端同形态的全屏信息层。

内容层次（自上而下居中）：
    时钟 -> 日期 -> 当前频道名 -> 当前节目名 -> 节目时段
底部：固定柱数的频谱层。

性能约定：
  * 文本由控制器 1 秒刷新一次，本控件不额外跑文本定时器；
  * 频谱 10fps（100ms），仅在可见时运行；
  * 柱数固定、纯色矩形填充，无渐变/模糊/阴影。

配色全部来自 ``themes/palette.json`` 的语义 token，找不到时回退到
``AppStyles`` 的内置旧键，绝不写死色值。
"""

import math
import re
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from ui.palette import get_token
from ui.styles import AppStyles

__all__ = ['ScreenSaverWidget', 'BAR_COUNT']

BAR_COUNT = 48

_RGBA_RE = re.compile(r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)')


def _clamp(value, low, high):
    return low if value < low else (high if value > high else value)


def _parse_color(value, fallback=''):
    """把 palette token 解析成 QColor，支持 #RRGGBB / #AARRGGBB / rgb[a]()。"""
    if isinstance(value, str):
        text = value.strip()
        match = _RGBA_RE.match(text)
        if match:
            r, g, b = (int(match.group(i)) for i in (1, 2, 3))
            alpha = float(match.group(4)) if match.group(4) else 1.0
            return QColor(r, g, b, int(_clamp(alpha, 0.0, 1.0) * 255))
        color = QColor(text)
        if color.isValid():
            return color
    if fallback:
        color = QColor(fallback)
        if color.isValid():
            return color
    return QColor()


def _resample(values, count=BAR_COUNT):
    """把任意长度柱高线性重采样到 ``count`` 个（保持视觉密度一致）。"""
    if not values or count <= 0:
        return []
    source_count = len(values)
    if source_count == count:
        return [float(v) for v in values]
    resampled = []
    for i in range(count):
        pos = (i + 0.5) * source_count / count - 0.5
        low = int(math.floor(pos))
        frac = pos - low
        low = max(0, min(source_count - 1, low))
        high = max(0, min(source_count - 1, low + 1))
        resampled.append(values[low] * (1.0 - frac) + values[high] * frac)
    return resampled


def _effective_mode():
    try:
        return AppStyles._get_effective_color_mode()
    except Exception:
        return 'dark'


def _app_palette_color(role):
    app = QApplication.instance()
    if app is not None:
        return app.palette().color(role)
    return QColor()


def _token_color(token, legacy_key, role):
    try:
        fallback = AppStyles.get_color(legacy_key)
    except Exception:
        fallback = ''
    color = _parse_color(get_token(token, _effective_mode(), fallback), fallback)
    return color if color.isValid() else _app_palette_color(role)


class ScreenSaverWidget(QWidget):
    """全屏覆盖层：只负责绘制，进入/退出由控制器驱动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('screensaver_overlay')
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        # 无按键的状态下也能收到 MouseMove，供控制器判定"鼠标移动即退出"
        self.setMouseTracking(True)

        self._clock_text = ''
        self._date_text = ''
        self._channel_text = ''
        self._program_text = ''
        self._range_text = ''

        self._static_bars = []
        self._bars = [0.0] * BAR_COUNT
        self._phase = 0.0
        self._active = False
        self._live = False
        self._transition_from = None
        self._transition_start = 0.0
        self._colors = {}
        self._load_colors()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(100)
        self._anim_timer.timeout.connect(self._on_anim_tick)

    # ---- 对外 API ----
    def set_context(self, clock_text='', date_text='', channel_text='',
                    program_text='', range_text=''):
        self._clock_text = clock_text or ''
        self._date_text = date_text or ''
        self._channel_text = channel_text or ''
        self._program_text = program_text or ''
        self._range_text = range_text or ''
        if self._active:
            self.update()

    def set_static_bars(self, bars):
        """借用一份频谱快照作为降级底图（可选）；为空时退化为确定性慢波动。

        只更新底图，不直接改写当前柱高：实时采集切换到降级时由
        :meth:`set_live_bars` 驱动约 300ms 的交叉淡入，避免突然归零。
        """
        try:
            values = [max(0.0, float(v)) for v in (bars or [])]
        except (TypeError, ValueError):
            values = []
        resampled = _resample(values) if values else []
        self._static_bars = resampled
        if not self._live and self._transition_from is None:
            self._bars = ([max(0.06, min(1.0, v)) for v in resampled]
                          if resampled else self._fallback_bars())

    def set_live_bars(self, bars):
        """写入实时采集的柱高；``None`` 表示回落到静态/慢波（约 300ms 淡入）。"""
        if bars is None:
            if self._live:
                self._live = False
                self._transition_from = list(self._bars)
                self._transition_start = time.monotonic()
                if self._active and not self._anim_timer.isActive():
                    self._anim_timer.start()
                self.update()
            return
        try:
            values = [max(0.0, float(v)) for v in bars]
        except (TypeError, ValueError):
            return
        if not values:
            return
        resampled = _resample(values)
        self._live = True
        self._transition_from = None
        self._bars = [_clamp(v, 0.0, 1.0) for v in resampled]
        # 实时数据自带 20fps 节奏，停掉自绘动画，避免双重刷新
        self._anim_timer.stop()
        if self._active:
            self.update()

    def start(self):
        if self._active:
            return
        self._active = True
        self._phase = 0.0
        self._live = False
        self._transition_from = None
        self._load_colors()
        self._sync_parent_size()
        self.show()
        self.raise_()
        self._anim_timer.start()
        self.update()

    def stop(self):
        self._active = False
        self._live = False
        self._transition_from = None
        self._anim_timer.stop()
        self.hide()

    def is_active(self):
        return self._active

    # ---- 内部 ----
    def _load_colors(self):
        self._colors = {
            'background': _token_color('background.window', 'window',
                                       QPalette.ColorRole.Window),
            'clock': _token_color('text.primary', 'window_text',
                                  QPalette.ColorRole.WindowText),
            'date': _token_color('text.secondary', 'window_text',
                                 QPalette.ColorRole.WindowText),
            'channel': _token_color('text.primary', 'window_text',
                                    QPalette.ColorRole.WindowText),
            'program': _token_color('text.secondary', 'window_text',
                                    QPalette.ColorRole.WindowText),
            'range': _token_color('text.tertiary', 'window_text',
                                  QPalette.ColorRole.WindowText),
            'bar': _token_color('accent.base', 'accent',
                                QPalette.ColorRole.Highlight),
        }

    def _sync_parent_size(self):
        parent = self.parent()
        if parent is None:
            return
        pw, ph = parent.width(), parent.height()
        if pw > 0 and ph > 0 and (self.width() != pw or self.height() != ph):
            self.setGeometry(0, 0, pw, ph)

    def _fallback_bars(self):
        """降级柱高：有快照做轻微呼吸，无快照走确定性慢波，柱高恒大于零。"""
        if self._static_bars:
            return [
                _clamp(v * (0.9 + 0.1 * math.sin(self._phase * 0.8 + i * 0.35)), 0.06, 1.0)
                for i, v in enumerate(self._static_bars)
            ]
        return [
            _clamp(0.16 + 0.10 * math.sin(self._phase * 0.9 + i * 0.35)
                   + 0.06 * math.sin(self._phase * 0.53 + i * 0.9), 0.08, 0.6)
            for i in range(BAR_COUNT)
        ]

    def _on_anim_tick(self):
        self._phase += 0.16
        target = self._fallback_bars()
        if self._transition_from is not None:
            # 有数据 -> 降级：约 300ms 平滑交叉淡入，不闪、不突然归零
            elapsed = time.monotonic() - self._transition_start
            progress = _clamp(elapsed / 0.3, 0.0, 1.0)
            eased = progress * progress * (3.0 - 2.0 * progress)
            self._bars = [
                start + (end - start) * eased
                for start, end in zip(self._transition_from, target)
            ]
            if progress >= 1.0:
                self._transition_from = None
        else:
            self._bars = target
        self.update()

    def showEvent(self, event):
        self._load_colors()
        self._sync_parent_size()
        super().showEvent(event)

    def resizeEvent(self, event):
        self._sync_parent_size()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            palette = self.palette()
            painter.fillRect(self.rect(),
                             self._colors.get('background', palette.color(QPalette.ColorRole.Window)))
            w, h = self.width(), self.height()
            if w <= 0 or h <= 0:
                return
            self._paint_texts(painter, w, h)
            self._paint_spectrum(painter, w, h)
        finally:
            painter.end()

    def _paint_texts(self, painter, w, h):
        family = self.font().family()
        margin_x = max(12, int(w * 0.06))
        bottom_margin = max(12, int(h * 0.06))
        spectrum_h = max(32, min(int(h * 0.12), 160))
        top_margin = max(10, int(h * 0.05))

        specs = (
            (self._clock_text, _clamp(h * 0.15, 24, 220), 'clock'),
            (self._date_text, _clamp(h * 0.035, 11, 40), 'date'),
            (self._channel_text, _clamp(h * 0.05, 13, 60), 'channel'),
            (self._program_text, _clamp(h * 0.032, 11, 38), 'program'),
            (self._range_text, _clamp(h * 0.024, 10, 28), 'range'),
        )
        fonts = []
        heights = []
        for _text, size, _key in specs:
            font = QFont(family)
            font.setPixelSize(max(8, int(size)))
            fonts.append(font)
            heights.append(QFontMetrics(font).height())

        gaps = (int(h * 0.012), int(h * 0.022), int(h * 0.008), int(h * 0.006))
        total = sum(heights) + sum(gaps)
        bottom_limit = h - bottom_margin - spectrum_h - int(h * 0.02)
        y = top_margin + max(0, (bottom_limit - top_margin - total) // 2)

        for index, (text, _size, key) in enumerate(specs):
            if not text:
                y += heights[index] + (gaps[index] if index < len(gaps) else 0)
                continue
            font = fonts[index]
            painter.setFont(font)
            painter.setPen(self._colors.get(
                key, self.palette().color(QPalette.ColorRole.WindowText)))
            metrics = QFontMetrics(font)
            shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(10, w - 2 * margin_x))
            rect = QRectF(margin_x, y, w - 2 * margin_x, heights[index])
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), shown)
            y += heights[index] + (gaps[index] if index < len(gaps) else 0)

    def _paint_spectrum(self, painter, w, h):
        margin_x = max(12, int(w * 0.06))
        bottom_margin = max(12, int(h * 0.06))
        spectrum_h = max(32, min(int(h * 0.12), 160))
        baseline = h - bottom_margin
        area_w = max(1, w - 2 * margin_x)
        slot = area_w / BAR_COUNT
        bar_w = max(2.0, slot * 0.55)
        bar_color = self._colors.get('bar', self.palette().color(QPalette.ColorRole.Highlight))
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(BAR_COUNT):
            level = _clamp(self._bars[index] if index < len(self._bars) else 0.0, 0.0, 1.0)
            bar_h = max(2.0, level * spectrum_h)
            x = margin_x + index * slot + (slot - bar_w) / 2.0
            painter.fillRect(QRectF(x, baseline - bar_h, bar_w, bar_h), bar_color)
