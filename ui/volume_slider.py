from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QLabel, QSlider

from ui.styles import AppStyles


class VolumeSlider(QSlider):
    """音量滑块：悬停或拖动时在滑块上方显示当前百分比。

    百分比用父面板内的浮层标签绘制，而不是 QToolTip：
    控制面板是独立的 Qt.Tool 窗口，系统 tooltip 在该窗口未激活时可能不显示。
    """

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setToolTip('')
        self._bubble = None
        self._bubble_parent = None
        # 菜单弹出等场景可能收不到 leaveEvent，定时兜底隐藏，避免残留百分比
        self._hide_timer = QTimer(self)
        self._hide_timer.setInterval(300)
        self._hide_timer.timeout.connect(self._check_hover)

    def set_bubble_parent(self, widget):
        self._bubble_parent = widget

    def _ensure_bubble(self) -> bool:
        parent = self._bubble_parent or self.window()
        if parent is None:
            return False
        # 父面板可能在控件创建后才就绪，父变了要重建，避免叠出多个残留标签
        if self._bubble is not None and self._bubble.parentWidget() is parent:
            return True
        if self._bubble is not None:
            self._bubble.deleteLater()
            self._bubble = None
        self._bubble_parent = parent
        bubble = QLabel(parent)
        bubble.setObjectName('volumePercentBubble')
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        colors = AppStyles._get_colors()
        bubble.setStyleSheet(
            "QLabel#volumePercentBubble {"
            f"background: {colors.get('panel_bg', '#20242c')};"
            f"color: {colors.get('player_panel_text', '#e8e8e8')};"
            "border: 1px solid rgba(255,255,255,60);"
            "border-radius: 4px; padding: 1px 6px; font-size: 11px;"
            "}"
        )
        bubble.hide()
        self._bubble = bubble
        return True

    def _handle_ratio(self) -> float:
        vmin, vmax = self.minimum(), self.maximum()
        if vmax <= vmin:
            return 0.0
        return max(0.0, min(1.0, (self.value() - vmin) / (vmax - vmin)))

    def _show_bubble(self):
        if not self._ensure_bubble():
            return
        parent = self._bubble.parentWidget()
        self._bubble.setText(f"{self.value()}%")
        self._bubble.adjustSize()
        # 手柄位置：默认样式的滑槽左右各留约 8px
        origin = self.mapTo(parent, QPoint(0, 0))
        handle_x = origin.x() + 8 + int((self.width() - 16) * self._handle_ratio())
        x = handle_x - self._bubble.width() // 2
        x = max(0, min(x, parent.width() - self._bubble.width()))
        y = origin.y() - self._bubble.height() - 2
        if y < 0:
            y = origin.y() + self.height() + 2
        self._bubble.move(x, y)
        self._bubble.show()
        self._bubble.raise_()
        if not self._hide_timer.isActive():
            self._hide_timer.start()

    def _check_hover(self):
        if self._bubble is None or not self._bubble.isVisible():
            self._hide_timer.stop()
            return
        # 独立工具窗口里 underMouse() 可能因收不到 Leave 而一直为真，用全局坐标判断
        inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if not self.isSliderDown() and not inside:
            self._bubble.hide()
            self._hide_timer.stop()

    def _hide_bubble(self):
        if self._bubble is not None and not self.isSliderDown():
            self._bubble.hide()
            self._hide_timer.stop()

    def enterEvent(self, event):
        self._show_bubble()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_bubble()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_bubble()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.isSliderDown() or self.rect().contains(event.position().toPoint()):
            self._show_bubble()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.rect().contains(event.position().toPoint()):
            self._show_bubble()
        else:
            self._hide_bubble()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._bubble is not None and self._bubble.isVisible():
            self._show_bubble()
