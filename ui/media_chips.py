"""底栏媒体信息徽章行。

把「硬解: d3d11va | 视频: H.265 | 分辨率: 3840x2160」这类信息拆成
每项一枚独立的低对比小胶囊（chip），并按可用宽度整体换行：
最多两行，再放不下就整枚收起，末尾用「…」提示，避免出现被裁掉一半的徽章。

徽章的外观（半透明底、弱描边、次要文字色）由本模块统一绘制，
不再依赖外部 QSS 覆盖，深浅主题与各视觉风格都从 AppStyles 取当前色。
"""
from PySide6.QtCore import Qt, QSize, QEvent, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from ui.elided_label import ElidedLabel


class MediaChip(ElidedLabel):
    """单枚媒体徽章：宽度按完整文本，只有单枚超出行宽时才内部省略。"""

    PAD_X = 6          # 单侧内边距（像素）

    def __init__(self, owner=None):
        super().__init__('', parent=owner, full_text_hint=True)
        self._owner = owner
        # 是否属于当前要展示的候选（外部 show/hide 与文本组决定）；
        # 与「因为放不下被临时收起」区分，后者不改这个标记。
        self._eligible = True
        self._item_h = 22
        self._bg = QColor(255, 255, 255, 16)
        self._border = QColor(255, 255, 255, 28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._item_h)
        self.refresh_theme()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        width = fm.horizontalAdvance(self.fullText()) + self.PAD_X * 2 + 2
        return QSize(max(18, width), self._item_h)

    def set_item_height(self, height: int):
        self._item_h = max(12, int(height))
        self.setFixedHeight(self._item_h)
        self.updateGeometry()

    def refresh_theme(self):
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        # 所有徽章统一用次要文字色：HDR 也只靠文字表达状态，不做高亮
        text_color = colors.get('player_panel_secondary', '#aaaaaa')
        try:
            dark = AppStyles._get_effective_color_mode() == 'dark'
        except Exception:
            dark = True
        # 半透明、低对比：不铺实底色，只在面板上叠一层很淡的提亮/压暗
        self._bg = QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 12)
        self._border = QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 22)
        # 只保留文字色/字号，底色与描边由 paintEvent 负责
        self.setStyleSheet(
            f"QLabel {{ color: {text_color}; font-size: {AppStyles.fs('caption')}px;"
            f" background: transparent; border: none; padding: 0px; }}"
        )
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = rect.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QPen(self._border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()
        super().paintEvent(event)

    def event(self, event):
        # 显隐由外部控制（HDR / 缓冲 / 文本组增减），变化后要让整行重新排布。
        # 排布过程中为了「放不下」而临时收起时不改候选标记。
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            owner = self._owner
            managing = bool(getattr(owner, '_managing_visibility', False))
            if not managing:
                self._eligible = event.type() == QEvent.Type.Show
            if owner is not None:
                owner.schedule_relayout()
        return super().event(event)


class _ChipGroupProxy:
    """让 video_info / audio_info / network_info 这些旧控件名继续可用。

    外部仍在调用 setText()/text()/hide() 等，这里把它们转成整行里的
    一组徽章，避免改动所有调用方。
    """

    def __init__(self, row: 'MediaChips', group: str):
        self._row = row
        self._group = group

    def setText(self, text):
        self._row.set_group_text(self._group, text)

    def text(self):
        return self._row.get_group_text(self._group)

    def setToolTip(self, text):
        # 每枚徽章自带完整文本 tooltip，组级提示无需额外处理
        pass

    def setMaximumWidth(self, width):
        # 宽度由整行统一分配，组级上限不再生效
        pass

    def setFixedHeight(self, height):
        self._row.set_item_height(height)

    def setStyleSheet(self, style):
        # 徽章外观由 AppStyles 统一管理，忽略外部 QSS
        pass

    def setAlignment(self, alignment):
        pass

    def show(self):
        pass

    def hide(self):
        pass

    def isVisible(self):
        return self._row.isVisible()


class MediaChips(QWidget):
    """媒体徽章行：一个控件里按行排布所有小胶囊。"""

    heightChanged = Signal(int)

    MAX_LINES = 2
    GAP_X = 5
    GAP_Y = 3
    GAP_GROUP = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._item_h = 22
        self._groups = {}
        self._group_texts = {}
        self._in_relayout = False
        self._managing_visibility = False
        self._relayout_pending = False
        self._last_width = -1

        self._hdr = self._new_chip()
        self._hdr.hide()
        self._buffer = self._new_chip()
        self._buffer.hide()
        self._overflow = self._new_chip()
        self._overflow.hide()

    def _new_chip(self) -> MediaChip:
        chip = MediaChip(self)
        chip.set_item_height(self._item_h)
        return chip

    # ---------- 对外 API ----------
    def group(self, name: str) -> _ChipGroupProxy:
        return _ChipGroupProxy(self, name)

    @property
    def hdr_chip(self) -> MediaChip:
        return self._hdr

    @property
    def buffer_chip(self) -> MediaChip:
        return self._buffer

    def set_item_height(self, height: int):
        height = max(12, int(height))
        if height == self._item_h:
            return
        self._item_h = height
        for chip in self.chip_widgets():
            chip.set_item_height(height)
        self.relayout()

    def refresh_theme(self):
        for chip in self.chip_widgets():
            chip.refresh_theme()

    def chip_widgets(self):
        chips = [self._hdr, self._buffer, self._overflow]
        for group in self._groups.values():
            chips.extend(group)
        return chips

    @staticmethod
    def _item_value(text: str) -> str:
        """徽章只显示值：去掉「字段名: 」前缀，字段含义交给分组间距 + tooltip。"""
        for sep in (': ', '：'):
            if sep in text:
                return text.split(sep, 1)[1].strip()
        return text

    # ---------- 文本 ----------
    def set_group_text(self, name: str, text: str):
        items = [part.strip() for part in (text or '').split('|') if part.strip()]
        self._group_texts[name] = items
        chips = self._groups.setdefault(name, [])
        while len(chips) < len(items):
            chips.append(self._new_chip())
        for index, chip in enumerate(chips):
            if index < len(items):
                full = items[index]
                value = self._item_value(full)
                if chip.fullText() != value:
                    chip.setText(value)
                # 完整写法（字段名 + 值）保留在 tooltip，信息不丢
                chip.setToolTip(full)
                chip.setVisible(True)
            else:
                chip.setVisible(False)
        self.relayout()

    def get_group_text(self, name: str) -> str:
        return ' | '.join(self._group_texts.get(name, []))

    # ---------- 排布 ----------
    def schedule_relayout(self):
        if self._relayout_pending or self._in_relayout:
            return
        self._relayout_pending = True
        from utils.thread_safety import safe_single_shot
        safe_single_shot(0, self, self._flush_relayout)

    def _flush_relayout(self):
        self._relayout_pending = False
        self.relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.width() != self._last_width:
            self.relayout()

    def _ordered(self):
        ordered = []
        for name in ('video', 'audio', 'network'):
            ordered.extend(self._groups.get(name, []))
            if name == 'video':
                ordered.append(self._hdr)
        ordered.append(self._buffer)
        return ordered

    def _group_of(self, widget):
        if widget is self._hdr:
            return 'video'
        for name, chips in self._groups.items():
            if any(widget is chip for chip in chips):
                return name
        return None

    @staticmethod
    def _is_candidate(widget) -> bool:
        return widget._eligible

    def sizeHint(self) -> QSize:
        return QSize(240, self.height() or self._item_h)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._item_h)

    def relayout(self):
        width = self.width()
        if width <= 0 or self._in_relayout:
            return
        self._in_relayout = True
        try:
            self._last_width = width
            base = [widget for widget in self._ordered()
                    if widget is not None and self._is_candidate(widget)]
            hidden = []
            used_h = self._item_h
            for _ in range(5):
                visible = [widget for widget in base if widget not in hidden]
                if hidden:
                    self._overflow.setText('…')
                    self._overflow.setVisible(True)
                else:
                    self._overflow.setVisible(False)
                items = visible + ([self._overflow] if hidden else [])
                dropped, used_h = self._place(items, width)
                new_hidden = [widget for widget in base
                              if widget in hidden or widget in dropped]
                if self._overflow in dropped and not new_hidden and len(visible) > 1:
                    # 极端情况：连「…」都放不下，再收起最后一项给它让位
                    new_hidden = [visible[-1]]
                if new_hidden == hidden:
                    break
                hidden = new_hidden
            # 放不下的徽章整枚收起，不能留在旧位置画出半截
            self._managing_visibility = True
            try:
                for chip in base:
                    chip.setVisible(chip not in hidden)
            finally:
                self._managing_visibility = False
            self._overflow.setToolTip(' | '.join(
                chip.toolTip() for chip in hidden if isinstance(chip, MediaChip)
            ))
            if used_h != self.height():
                self.setFixedHeight(used_h)
            # 每次都通知：底栏是独立窗口，错过一次高度变化就会把第二行裁掉
            self.heightChanged.emit(self.height())
        finally:
            self._in_relayout = False

    def _place(self, items, width):
        gap_x, gap_y = self.GAP_X, self.GAP_Y
        item_h = self._item_h
        max_h = item_h * self.MAX_LINES + gap_y * (self.MAX_LINES - 1)

        x = 0
        y = 0
        dropped = []
        bottom = item_h
        prev_group = None
        for widget in items:
            hint = widget.sizeHint()
            chip_w = max(1, min(hint.width(), width))
            group = self._group_of(widget)
            extra = 0
            if x > 0 and prev_group and group and group != prev_group:
                # 组间留更大间距，不用分隔线也能看出分组
                extra = self.GAP_GROUP - gap_x
            if x > 0 and x + extra + chip_w > width:
                x = 0
                y += item_h + gap_y
                extra = 0
                prev_group = None
            if y + item_h > max_h:
                dropped.append(widget)
                continue
            x += extra
            widget.setGeometry(x, y, chip_w, item_h)
            x += chip_w + gap_x
            bottom = max(bottom, y + item_h)
            prev_group = group
        return dropped, bottom
