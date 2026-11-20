"""未播放时的待机画面（PC）。

原先的实现是「图标 + 一圈椭圆轨道粒子旋转」，用户反馈偏乱；现在收敛为
安静的静态排版：主题化画布渐变 + 图标背后的柔和光晕 + 应用名。

两种形态，由 ``variant`` 选择：

* ``breathe``（默认）：图标光晕与图标透明度做约 6s 的极慢呼吸，8fps，且只
  重绘图标周边区域；定时器以旧名 ``_timer`` 暴露，``pyqt_player._setup_idle_render``
  会把它注册到空闲停绘（降频到 2fps），长时间无人操作时几乎不耗电。
* ``quiet``：完全静态。没有定时器、没有持续重绘，只在显示、尺寸变化与换主题
  时各绘制一次。把构造参数改成 ``WallpaperWidget(parent, variant='quiet')`` 即可换回。

配色全部取自 ``themes/palette.json`` 的语义 token（找不到时回退到
``AppStyles`` 旧键），不写死色值；字号、间距按视频区短边等比缩放，
高 DPI 下由 Qt 统一做逻辑像素换算，图标按 ``devicePixelRatio`` 取高分辨率源图。

对调用方保持 QLabel 兼容 API（setPixmap / setText / setAlignment /
setStyleSheet），``video_placeholder`` 的既有生命周期代码无需改动。
"""

import math
import re

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ui.palette import get_token
from ui.styles import AppStyles

__all__ = ['WallpaperWidget']

# 呼吸形态的刷新频率：8fps 对 6s 周期的极慢变化足够平滑，开销只有 60fps 的 1/7。
_BREATH_INTERVAL_MS = 125
_BREATH_PERIOD_S = 6.0

_RGBA_RE = re.compile(
    r'rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)')


def _qcolor(value, fallback=''):
    """把 token 的 #RRGGBB / #AARRGGBB / rgb[a]() 解析为 QColor。"""
    if isinstance(value, str):
        text = value.strip()
        match = _RGBA_RE.match(text)
        if match:
            r, g, b = (int(match.group(i)) for i in (1, 2, 3))
            alpha = float(match.group(4)) if match.group(4) else 1.0
            return QColor(r, g, b, int(max(0.0, min(1.0, alpha)) * 255))
        color = QColor(text)
        if color.isValid():
            return color
    color = QColor(fallback) if fallback else QColor()
    return color if color.isValid() else QColor()


def _clamp(value, low, high):
    return low if value < low else (high if value > high else value)


class WallpaperWidget(QWidget):
    """播放器未播放时的居中待机画面（默认极慢呼吸，可切回完全静态）。"""

    def __init__(self, parent=None, variant: str = 'breathe'):
        super().__init__(parent)
        self._variant = 'quiet' if variant == 'quiet' else 'breathe'
        self._icon_pixmap = None
        self._title_text = ''
        self._phase = 0.0
        self._colors = {}
        # 静态形态不建定时器：既省 CPU，也让空闲停绘的注册自动跳过。
        self._timer = None
        if self._variant == 'breathe':
            self._timer = QTimer(self)
            self._timer.setInterval(_BREATH_INTERVAL_MS)
            self._timer.timeout.connect(self._on_tick)
        # 自绘全部内容，不让 Qt 再擦一遍背景
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._load_colors()
        self._load_title()
        self._connect_language_signal()

    # ---- QLabel 兼容 API（调用点无需改动） ----
    def setPixmap(self, pixmap: QPixmap):
        self._icon_pixmap = pixmap
        self.update()

    def setText(self, _text: str):
        """兼容 QLabel API：待机画面不显示任意文本，标题固定取应用名。"""
        pass

    def setAlignment(self, _alignment):
        """兼容 QLabel API：内容始终居中排布。"""
        pass

    def setStyleSheet(self, _style: str):
        """兼容 QLabel API：颜色来自主题 token，这里只把换主题变成一次重绘。"""
        self._load_colors()
        self.update()

    def reapply_styles(self):
        self._load_colors()
        self.update()

    # ---- 主题 / 文案 ----
    def _load_colors(self):
        try:
            mode = AppStyles._get_effective_color_mode()
        except Exception:
            mode = 'dark'

        def token(path, legacy_key):
            fallback = AppStyles.get_color(legacy_key)
            parsed = _qcolor(get_token(path, mode, fallback), fallback)
            return parsed if parsed.isValid() else _qcolor(fallback)

        self._colors = {
            'canvas_start': token('background.canvas_start', 'player_video_placeholder'),
            'canvas_end': token('background.canvas_end', 'player_video_placeholder'),
            'halo': token('accent.base', 'accent'),
            'title': token('text.secondary', 'player_panel_secondary'),
            'mode': mode,
        }

    def _load_title(self):
        text = ''
        try:
            from core.language_manager import LanguageManager
            window = self.window()
            manager = getattr(window, 'language_manager', None) if window is not None else None
            if manager is None:
                manager = LanguageManager()
            text = manager.tr('app_title', '光屿') or ''
        except Exception:
            text = '光屿'
        self._title_text = text
        self.update()

    def _connect_language_signal(self):
        try:
            from core.language_manager import LanguageManager
            manager = LanguageManager()
            manager.language_changed.connect(self._load_title)
        except Exception:
            pass

    # ---- 动画驱动（仅 breathe 形态） ----
    def _on_tick(self):
        self._phase = (self._phase + (_BREATH_INTERVAL_MS / 1000.0)
                       * math.tau / _BREATH_PERIOD_S) % math.tau
        self.update(self._halo_rect().toAlignedRect())

    def showEvent(self, event):
        super().showEvent(event)
        self._load_colors()
        self._phase = 0.0
        if self._timer is not None:
            self._timer.start()
        self.update()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._timer is not None:
            self._timer.stop()

    # ---- 布局计算 ----
    def _breath_value(self):
        if self._variant != 'breathe':
            return 1.0
        return 0.5 + 0.5 * math.sin(self._phase)

    def _icon_size(self):
        return _clamp(min(self.width(), self.height()) * 0.15, 56.0, 128.0)

    def _title_px(self):
        return _clamp(min(self.width(), self.height()) * 0.030, 14.0, 24.0)

    def _icon_rect(self) -> QRectF:
        size = self._icon_size()
        return QRectF(self.width() / 2 - size / 2, self._block_top(), size, size)

    def _title_rect(self) -> QRectF:
        size = self._icon_size()
        gap = size * 0.34
        metrics = QFontMetrics(self._title_font())
        return QRectF(0, self._block_top() + size + gap,
                      self.width(), float(metrics.height()))

    def _block_top(self):
        size = self._icon_size()
        gap = size * 0.34
        text_h = float(QFontMetrics(self._title_font()).height())
        total = size + gap + text_h
        # 视觉重心略高于几何中心，观感更稳
        return (self.height() - total) / 2 - self.height() * 0.015

    def _halo_rect(self) -> QRectF:
        icon = self._icon_rect()
        radius = icon.width() * 1.55
        center = icon.center()
        return QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

    def _title_font(self) -> QFont:
        font = QFont(self.font())
        px = self._title_px()
        font.setPixelSize(max(8, int(round(px))))
        font.setWeight(QFont.Weight.Medium)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(1.0, px * 0.16))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font

    # ---- 绘制 ----
    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            w, h = self.width(), self.height()
            if w <= 0 or h <= 0:
                return
            self._paint_canvas(painter)
            self._paint_icon(painter)
            self._paint_title(painter, w)
        finally:
            painter.end()

    def _paint_canvas(self, painter):
        start = self._colors.get('canvas_start', QColor('#16162a'))
        end = self._colors.get('canvas_end', QColor('#0b0f1a'))
        if not start.isValid():
            start = QColor('#16162a')
        if not end.isValid():
            end = QColor('#0b0f1a')
        # 上亮下暗的极轻纵深；两色都来自画布 token，深浅主题各自成立
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, end)
        gradient.setColorAt(1.0, start)
        painter.fillRect(self.rect(), gradient)

    def _paint_icon(self, painter):
        icon = self._icon_rect()
        if not self._icon_pixmap or self._icon_pixmap.isNull():
            return
        halo = self._colors.get('halo', QColor('#4a7eff'))
        breath = self._breath_value()
        center = icon.center()
        radius = icon.width() * 1.55
        # 光晕跟着呼吸轻微起伏；静态形态取中间值，不做任何过渡
        mood = 0.78 + 0.22 * breath
        peak_alpha = 34 if self._colors.get('mode') == 'light' else 52
        glow = QRadialGradient(center, radius)
        glow.setColorAt(0.0, QColor(halo.red(), halo.green(), halo.blue(),
                                    int(peak_alpha * mood)))
        glow.setColorAt(0.55, QColor(halo.red(), halo.green(), halo.blue(),
                                     int(peak_alpha * 0.34 * mood)))
        glow.setColorAt(1.0, QColor(halo.red(), halo.green(), halo.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius,
                                   radius * 2, radius * 2))

        painter.setOpacity(0.90 + 0.10 * breath)
        painter.drawPixmap(icon, self._icon_pixmap,
                           QRectF(0, 0, self._icon_pixmap.width(),
                                  self._icon_pixmap.height()))
        painter.setOpacity(1.0)

    def _paint_title(self, painter, w):
        if not self._title_text:
            return
        font = self._title_font()
        painter.setFont(font)
        color = self._colors.get('title', QColor('#aaaaaa'))
        painter.setPen(color)
        metrics = QFontMetrics(font)
        rect = self._title_rect()
        text = metrics.elidedText(self._title_text, Qt.TextElideMode.ElideRight,
                                  max(10, int(w * 0.7)))
        # letter-spacing 会加在最后一个字形后面，左移半格让文字视觉居中
        offset = font.letterSpacing() / 2 if font.letterSpacing() > 0 else 0
        painter.drawText(rect.translated(-offset, 0),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                         text)
