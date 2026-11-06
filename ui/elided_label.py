"""单行省略文本控件：超长内容右侧省略，完整内容保留在 tooltip。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """按当前可用宽度省略的单行 QLabel。

    直接 setText 即可，控件会在 resize 时重新计算省略文本；
    完整文本始终作为 tooltip，避免信息丢失。
    """

    def __init__(self, text: str = '', parent=None):
        super().__init__(parent)
        self._full_text = ''
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str):
        self._full_text = text or ''
        super().setToolTip(self._full_text)
        self._update_elided()

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
