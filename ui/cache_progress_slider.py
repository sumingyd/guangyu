from PySide6.QtWidgets import QSlider, QToolTip
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QFontMetrics


class CacheProgressSlider(QSlider):
    """带缓存区间可视化与拖动时间预览（控件内自绘，避免顶层窗口闪烁）的进度条"""

    preview_position_changed = Signal(int)
    # 直播等不可拖动场景下被点击时发出，用于给出「不可拖动」的说明
    seek_blocked = Signal()

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self._cache_start_ratio = -1.0
        self._cache_end_ratio = -1.0
        self._cache_color = QColor(76, 175, 80, 100)
        self._update_cache_color_from_theme()
        self._preview_text = ''
        self._is_dragging = False
        self._seekable = True
        self._tooltip_formatter = None
        self.setMouseTracking(True)
        self._update_preview_style()
        from ui.theme_manager import get_theme_manager
        get_theme_manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme_name):
        self._update_cache_color_from_theme()
        self._update_preview_style()
        self.update()

    def _update_preview_style(self):
        try:
            from ui.styles import AppStyles
            colors = AppStyles._get_colors()
            self._preview_bg = QColor(
                colors.get('player_background') or AppStyles._safe_fallback('window'))
            self._preview_bg.setAlpha(235)
            self._preview_text_color = QColor(
                colors.get('player_slider_handle') or AppStyles._safe_fallback('window_text'))
            self._preview_border = QColor(
                colors.get('player_slider_fill') or AppStyles._safe_fallback('accent'))
            self._preview_radius = max(4, AppStyles._get_style_border_radius())
        except Exception:
            self._preview_bg = QColor(26, 26, 26, 235)
            self._preview_text_color = QColor('#ffffff')
            self._preview_border = QColor('#4CAF50')
            self._preview_radius = 4

    def _update_cache_color_from_theme(self):
        try:
            from ui.styles import AppStyles
            colors = AppStyles._get_colors()
            color_str = colors.get('player_cache_bar', 'rgba(76,175,80,0.39)')
            self.set_cache_color(color_str)
        except Exception:
            self._cache_color = QColor(76, 175, 80, 100)

    def set_cache_range(self, start_ratio: float, end_ratio: float):
        self._cache_start_ratio = max(0.0, min(1.0, start_ratio))
        self._cache_end_ratio = max(0.0, min(1.0, end_ratio))
        self.update()

    def clear_cache_range(self):
        self._cache_start_ratio = -1.0
        self._cache_end_ratio = -1.0
        self.update()

    def set_cache_color(self, color_str: str):
        try:
            if color_str.startswith('rgba('):
                parts = color_str[5:-1].split(',')
                r = int(parts[0].strip())
                g = int(parts[1].strip())
                b = int(parts[2].strip())
                a = int(float(parts[3].strip()) * 255)
                self._cache_color = QColor(r, g, b, a)
            elif color_str.startswith('#') and len(color_str) == 7:
                self._cache_color = QColor(color_str)
                self._cache_color.setAlpha(100)
            else:
                self._cache_color = QColor(color_str)
        except Exception:
            self._cache_color = QColor(76, 175, 80, 100)

    def set_preview_text(self, text: str):
        self._preview_text = text or ''
        self.update()

    def set_seekable(self, seekable: bool) -> bool:
        """设置是否允许点击/拖动进度条，返回状态是否发生变化。"""
        changed = self._seekable != seekable
        self._seekable = seekable
        if not seekable and self._is_dragging:
            self._is_dragging = False
            self.setSliderDown(False)
            self.update()
        if changed:
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if seekable else Qt.CursorShape.ArrowCursor
            )
        return changed

    @property
    def is_seekable(self) -> bool:
        return self._seekable

    def set_tooltip_formatter(self, formatter):
        self._tooltip_formatter = formatter

    def _get_handle_x(self) -> int:
        value = self.value()
        min_val = self.minimum()
        max_val = self.maximum()
        if max_val == min_val:
            return 0
        ratio = (value - min_val) / (max_val - min_val)
        groove_rect = self._get_groove_rect()
        return int(groove_rect.x() + groove_rect.width() * ratio)

    def _pos_to_value(self, pos_x):
        groove_rect = self._get_groove_rect()
        if groove_rect.width() <= 0:
            return self.value()
        ratio = max(0.0, min(1.0, (pos_x - groove_rect.x()) / groove_rect.width()))
        return int(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._seekable:
                # 直播等无缓冲场景不改变进度，仅给出说明
                self.seek_blocked.emit()
                event.accept()
                return
            self._is_dragging = True
            self.setSliderDown(True)
            new_value = self._pos_to_value(event.position().toPoint().x())
            self.setValue(new_value)
            self.sliderPressed.emit()
            self.preview_position_changed.emit(self.value())
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._seekable:
            super().mouseMoveEvent(event)
            return
        if self._is_dragging:
            new_value = self._pos_to_value(event.position().toPoint().x())
            self.setValue(new_value)
            self.preview_position_changed.emit(self.value())
            self.update()
        else:
            if self._tooltip_formatter:
                try:
                    v = self._pos_to_value(event.position().toPoint().x())
                    text = self._tooltip_formatter(v)
                    if text:
                        QToolTip.showText(event.globalPosition().toPoint(), text, self)
                except Exception:
                    pass
            super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._seekable:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setSliderDown(False)
            self.sliderReleased.emit()
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        groove_rect = self._get_groove_rect()
        # 缓存区间可视化
        if (groove_rect.width() > 0
                and self._cache_start_ratio >= 0
                and self._cache_end_ratio > self._cache_start_ratio):
            cache_x_start = groove_rect.x() + groove_rect.width() * self._cache_start_ratio
            cache_x_end = groove_rect.x() + groove_rect.width() * self._cache_end_ratio
            cache_rect = QRectF(
                cache_x_start,
                groove_rect.y(),
                cache_x_end - cache_x_start,
                groove_rect.height()
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._cache_color)
            painter.drawRoundedRect(cache_rect, groove_rect.height() / 2, groove_rect.height() / 2)

        # 拖动时间预览气泡（控件内自绘，随主题变色）
        if self._is_dragging and self._preview_text:
            font = self.font()
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
            painter.setFont(font)
            fm = QFontMetrics(font)
            text_w = fm.horizontalAdvance(self._preview_text)
            pad_x, pad_y = 8, 4
            bubble_w = text_w + pad_x * 2
            bubble_h = fm.height() + pad_y * 2
            handle_x = self._get_handle_x()
            bx = max(2, min(self.width() - bubble_w - 2, handle_x - bubble_w // 2))
            by = max(2, int(groove_rect.y()) - bubble_h - 6)
            if by <= 2:
                by = int(groove_rect.y() + groove_rect.height()) + 6
            bubble = QRectF(bx, by, bubble_w, bubble_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._preview_bg)
            painter.drawRoundedRect(bubble, self._preview_radius, self._preview_radius)
            painter.setPen(self._preview_border)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bubble, self._preview_radius, self._preview_radius)
            painter.setPen(self._preview_text_color)
            painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, self._preview_text)

        painter.end()

    def _get_groove_rect(self) -> QRectF:
        w = self.width()
        h = self.height()
        groove_height = 4
        y = (h - groove_height) / 2.0
        margin = 5
        return QRectF(margin, y, w - 2 * margin, groove_height)
