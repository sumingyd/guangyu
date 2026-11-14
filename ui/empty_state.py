"""列表空态的统一样式与布局。

EPG 面板与频道列表过去各用一套做法：EPG 手工 ``adjustSize()+setGeometry``
在列表上叠加，频道列表则把标签塞进布局底部。前者在面板变宽/变窄后不会
重新定位，导致文案被裁到左边缘；后者则贴在右下角。两处因此永远对不齐。

这里用同一个 ``EmptyStateLabel``：作为列表子控件居中叠加，监听父控件尺寸
变化自动重排，宽度不足时换行而不是被裁掉。调用方只需要 ``setText()`` /
``show()`` / ``hide()``。
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class EmptyStateLabel(QLabel):
    """居中叠加在列表上的空态标签，随列表尺寸自动重排。"""

    _MARGIN = 12
    _ACTION_GAP = 8

    def __init__(self, parent, text=''):
        super().__init__(parent)
        self._anchor = parent
        self._action_bar = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(self._style())
        parent.installEventFilter(self)
        self.setText(text)
        self.hide()

    def set_actions(self, actions):
        """在空态文案下方挂一排主操作按钮：[('文案', 回调), ...]。"""
        if self._action_bar is not None:
            self._action_bar.deleteLater()
            self._action_bar = None
        if not actions:
            self.relayout()
            return
        bar = QWidget(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._ACTION_GAP)
        for text, callback in actions:
            button = QPushButton(text, bar)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(callback)
            layout.addWidget(button)
        bar.adjustSize()
        bar.show()
        self._action_bar = bar
        self.relayout()

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
        action_bar = self._action_bar
        action_w = 0
        action_h = 0
        if action_bar is not None and action_bar.isVisible():
            action_hint = action_bar.sizeHint()
            action_w = action_hint.width()
            action_h = action_hint.height()
            action_bar.adjustSize()
        width = min(max(hint.width(), action_w), avail_w)
        text_height = self.heightForWidth(width)
        if text_height <= 0:
            text_height = hint.height()
        gap = self._ACTION_GAP if action_h > 0 else 0
        block_height = text_height + gap + action_h
        block_height = min(block_height, avail_h)
        x = (self._anchor.width() - width) // 2
        y = (self._anchor.height() - block_height) // 2
        self.setGeometry(x, y, width, text_height)
        if action_bar is not None and action_h > 0:
            bar_w = min(action_bar.width(), avail_w)
            bar_x = (self._anchor.width() - bar_w) // 2
            bar_y = y + text_height + gap
            action_bar.setGeometry(bar_x, bar_y, bar_w, action_h)
