from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QSlider, QToolTip


class VolumeSlider(QSlider):
    """音量滑块：悬停或拖动时显示当前百分比。"""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._refresh_tooltip()
        self.valueChanged.connect(self._refresh_tooltip)

    def _refresh_tooltip(self, *_):
        self.setToolTip(f"{self.value()}%")

    @staticmethod
    def _tip_pos(event) -> QPoint:
        pos = event.globalPosition().toPoint()
        return QPoint(pos.x(), pos.y() - 28)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            QToolTip.showText(self._tip_pos(event), f"{self.value()}%", self)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.isSliderDown() or self.rect().contains(event.position().toPoint()):
            QToolTip.showText(self._tip_pos(event), f"{self.value()}%", self)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.rect().contains(event.position().toPoint()):
            QToolTip.showText(self._tip_pos(event), f"{self.value()}%", self)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)
