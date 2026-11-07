"""单行省略文本控件：超长内容右侧省略，完整内容保留在 tooltip。"""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """按当前可用宽度省略的单行 QLabel。

    直接 setText 即可，控件会在 resize 时重新计算省略文本；
    完整文本始终作为 tooltip，避免信息丢失。
    """

    def __init__(self, text: str = '', parent=None, full_text_hint: bool = False):
        super().__init__(parent)
        self._full_text = ''
        # 默认按"当前已省略文本"给出尺寸提示（列表项等场景够用）；
        # 置 True 时按完整文本给尺寸提示，布局能按真实需求分配宽度，
        # 避免一旦被压缩就再也长不回来（只在实际放不下时才省略）。
        self._full_text_hint = full_text_hint
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def sizeHint(self):
        if not self._full_text_hint or not self._full_text:
            return super().sizeHint()
        metrics = QFontMetrics(self.font())
        m = self.contentsMargins()
        # 预留 4px：省略判断用的是 contentsRect，与 sizeHint 取整可能差 1~2px
        width = metrics.horizontalAdvance(self._full_text) + m.left() + m.right() + 4
        return QSize(width, super().sizeHint().height())

    def minimumSizeHint(self):
        if not self._full_text_hint:
            return super().minimumSizeHint()
        return QSize(40, super().minimumSizeHint().height())

    def setText(self, text: str):
        self._full_text = text or ''
        super().setToolTip(self._full_text)
        self._update_elided()
        if self._full_text_hint:
            # 完整文本变化后 sizeHint 也随之变化，通知布局重新分配宽度
            self.updateGeometry()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        if not self._full_text:
            super().setText('')
            return
        avail = max(0, self.contentsRect().width())
        if avail <= 0:
            super().setText(self._full_text)
            return
        metrics = QFontMetrics(self.font())
        super().setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, avail)
        )
