"""列表空态的统一样式与布局。

EPG 面板与频道列表过去各用一套做法：EPG 手工 ``adjustSize()+setGeometry``
在列表上叠加，频道列表则把标签塞进布局底部。前者在面板变宽/变窄后不会
重新定位，导致文案被裁到左边缘；后者则贴在右下角。两处因此永远对不齐。

这里用同一个 ``EmptyStateLabel``：作为列表子控件居中叠加，监听父控件尺寸
变化自动重排，宽度不足时换行而不是被裁掉。调用方只需要 ``setText()`` /
``show()`` / ``hide()``。
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QLabel


class EmptyStateLabel(QLabel):
    """居中叠加在列表上的空态标签，随列表尺寸自动重排。"""

    _MARGIN = 12

    def __init__(self, parent, text=''):
        super().__init__(parent)
        self._anchor = parent
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(self._style())
        parent.installEventFilter(self)
        self.setText(text)
        self.hide()

    @staticmethod
    def _style():
        from ui.styles import AppStyles
        return AppStyles.player_empty_label_style()

    def refresh_style(self):
        """主题切换后刷新空态字号与颜色。"""
        self.setStyleSheet(self._style())
        self.relayout()

    def eventFilter(self, obj, event):
        if obj is self._anchor and event.type() == QEvent.Type.Resize:
            self.relayout()
        return False

    def setText(self, text):  # noqa: N802 - 保持 Qt 命名
        super().setText(text)
        self.relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self.relayout()
        self.raise_()

    def relayout(self):
        if self._anchor is None:
            return
        avail_w = max(0, self._anchor.width() - self._MARGIN * 2)
        avail_h = max(0, self._anchor.height() - self._MARGIN * 2)
        if avail_w <= 0 or avail_h <= 0:
            return
        hint = self.sizeHint()
        width = min(hint.width(), avail_w)
        height = self.heightForWidth(width)
        if height <= 0:
            height = hint.height()
        height = min(height, avail_h)
        x = (self._anchor.width() - width) // 2
        y = (self._anchor.height() - height) // 2
        self.setGeometry(x, y, width, height)
