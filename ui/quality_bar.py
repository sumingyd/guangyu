"""频道质量评分条组件

提供两种渲染形式：
1. QualityBarWidget：用于主窗口 QListWidget 的 item widget
2. QualityBarDelegate：用于扫描对话框 QTableView 的名称列

视觉规范：
- 满分 100，按分数比例填充长度
- 颜色：HSV 色相从 0°（红，0分）→ 60°（黄，50分）→ 120°（绿，100分）平滑插值
- 背景：半透明灰色轨道，已填充部分为渐变色
- 评分条高度 4px，圆角 2px
- valid is None（未检测）时不绘制评分条
"""
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPalette
from PySide6.QtWidgets import QWidget, QStyledItemDelegate, QStyle
from PySide6.QtWidgets import QApplication, QSizePolicy, QStyleOptionViewItem, QToolTip

# 自定义数据角色：用于 delegate 从 QModelIndex 取评分
QUALITY_SCORE_ROLE = Qt.ItemDataRole.UserRole + 100
QUALITY_GRADE_ROLE = Qt.ItemDataRole.UserRole + 101

# 评分条几何参数
BAR_HEIGHT = 4
BAR_RADIUS = 2
BAR_BOTTOM_MARGIN = 2
TEXT_BOTTOM_MARGIN = 1  # 名称文字与评分条之间的间距


def _score_to_color(score: float) -> QColor:
    """分数（0~100）映射到颜色：红(0) → 黄(50) → 绿(100)。

    使用 HSV 色相线性插值，饱和度/明度保持鲜艳。
    """
    if score is None:
        return QColor(150, 150, 150)
    s = max(0.0, min(100.0, float(score)))
    # 色相从 0°（红）到 120°（绿），分数线性映射
    hue = (s / 100.0) * 120.0
    c = QColor.fromHsvF(hue / 360.0, 0.85, 0.95)
    return c


def _track_color() -> QColor:
    """评分条轨道颜色（未填充部分），跟随主题取色。"""
    try:
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        base = colors.get('table_grid') or colors.get('placeholder') or '#444444'
        c = QColor(base)
        c.setAlpha(80)
        return c
    except Exception:
        return QColor(120, 120, 120, 80)


def _score_to_tooltip(score, grade) -> str:
    if score is None:
        return ""
    try:
        from core.language_manager import LanguageManager
        template = LanguageManager().tr(
            "quality_score_tooltip", "质量评分: {score} / 100  (等级: {grade})"
        )
        return template.format(score=f"{score:.1f}", grade=grade)
    except Exception:
        return f"质量评分: {score:.1f} / 100  (等级: {grade})"


class QualityBarWidget(QWidget):
    """用于 QListWidget 的 item widget 形式的评分条。

    用法：插入到 item_widget 的布局中，名称下方。
    调用 set_score 设置评分（None 或负数表示不显示）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score: Optional[float] = None
        self._grade: str = ''
        # 透明背景，避免遮挡 item 选中样式
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 设置 objectName 以便通过 findChild 查找并动态更新评分
        self.setObjectName("quality_bar")

    def reapply_styles(self):
        """主题切换时刷新绘制"""
        self.update()

    def set_score(self, score, grade: str = ''):
        """设置评分。score 为 None 表示未检测，不显示评分条。"""
        new_score = None if score is None else float(score)
        if new_score is not None and new_score < 0:
            new_score = None
        if self._score == new_score and self._grade == grade:
            return
        self._score = new_score
        self._grade = grade or ''
        self.setToolTip(_score_to_tooltip(new_score, grade))
        self.setVisible(new_score is not None)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.width() or 100, BAR_HEIGHT)

    def paintEvent(self, event):
        if self._score is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = max(0, self.width())
        h = self.height()
        bar_rect = QRectF(0, (h - BAR_HEIGHT) / 2.0, w, BAR_HEIGHT)

        # 轨道（未填充背景）
        track_color = _track_color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(bar_rect, BAR_RADIUS, BAR_RADIUS)

        # 已填充部分
        fill_width = bar_rect.width() * (max(0.0, min(100.0, self._score)) / 100.0)
        if fill_width >= 1.0:
            fill_rect = QRectF(bar_rect.left(), bar_rect.top(), fill_width, bar_rect.height())
            # 渐变填充（左端稍暗到右端明亮，增加质感）
            grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            base = _score_to_color(self._score)
            light = QColor(base)
            light.setHsvF(base.hueF(), max(0.5, base.saturationF() - 0.2), 1.0)
            grad.setColorAt(0.0, base)
            grad.setColorAt(1.0, light)
            painter.setBrush(grad)
            painter.drawRoundedRect(fill_rect, BAR_RADIUS, BAR_RADIUS)

        painter.end()


class QualityBarDelegate(QStyledItemDelegate):
    """用于 QTableView 名称列的 delegate。

    在原文本（频道名称）下方绘制评分条。
    评分数据通过 index.data(QUALITY_SCORE_ROLE) 和 index.data(QUALITY_GRADE_ROLE) 获取。
    若评分数据为 None，则按默认行为只绘制名称。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar_height = BAR_HEIGHT
        self._text_bottom_margin = TEXT_BOTTOM_MARGIN

    def paint(self, painter: QPainter, option, index):
        # 先让基类绘制默认内容（包含选中背景、文字等）
        # 但我们只需要基类的选中背景，文字自己画可以更好控制位置
        # 折中：先画选中背景，再画文字 + 评分条

        score = index.data(QUALITY_SCORE_ROLE)
        grade = index.data(QUALITY_GRADE_ROLE) or ''

        if score is None:
            # 未检测：按基类默认绘制
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. 绘制选中/悬停背景（复用 QStyle）
        style = option.widget.style() if option.widget else QApplication.style()
        # 绘制 control 背景（包含选中态）
        opt = self._copy_option(option)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)

        # 2. 绘制频道名称（在文本矩形顶部，超长省略）
        text = index.data(Qt.ItemDataRole.DisplayRole) or ''
        text_rect = self._text_rect(option)
        painter.setPen(self._text_color(option))
        # 使用 option.font 确保字体一致
        painter.setFont(option.font)
        elided = painter.fontMetrics().elidedText(
            str(text), Qt.TextElideMode.ElideRight, max(0, int(text_rect.width()))
        )
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         elided)

        # 3. 在名称下方绘制评分条
        self._draw_bar(painter, option, float(score), grade)

        painter.restore()

    def _draw_bar(self, painter: QPainter, option, score: float, grade: str):
        w = option.rect.width()
        if w <= 0:
            return
        # 评分条位置：底部对齐
        bar_y = option.rect.bottom() - BAR_HEIGHT - BAR_BOTTOM_MARGIN
        bar_x = option.rect.left() + 4  # 左侧留 4px
        bar_w = w - 8  # 左右各留 4px
        if bar_w < 4:
            return
        bar_rect = QRectF(bar_x, bar_y, bar_w, BAR_HEIGHT)

        # 轨道
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_track_color())
        painter.drawRoundedRect(bar_rect, BAR_RADIUS, BAR_RADIUS)

        # 已填充
        fill_w = bar_rect.width() * (max(0.0, min(100.0, score)) / 100.0)
        if fill_w >= 1.0:
            fill_rect = QRectF(bar_rect.left(), bar_rect.top(), fill_w, bar_rect.height())
            grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            base = _score_to_color(score)
            light = QColor(base)
            light.setHsvF(base.hueF(), max(0.5, base.saturationF() - 0.2), 1.0)
            grad.setColorAt(0.0, base)
            grad.setColorAt(1.0, light)
            painter.setBrush(grad)
            painter.drawRoundedRect(fill_rect, BAR_RADIUS, BAR_RADIUS)

    def _text_rect(self, option):
        # 文字区域：去掉下方评分条占用的空间
        rect = option.rect.adjusted(4, 0, -4,
                                    -(self._bar_height + BAR_BOTTOM_MARGIN + self._text_bottom_margin))
        return rect

    def _text_color(self, option) -> QColor:
        # 选中时使用表格选中文字色，否则用主题窗口文字色
        # 注意：应用主题完全由QSS驱动、不写入QPalette，delegate手工绘制
        # 文字时必须直接取主题色，否则深色主题下会用系统palette的黑色
        try:
            from ui.styles import AppStyles
            colors = AppStyles._get_colors()
            if option.state & QStyle.StateFlag.State_Selected:
                return QColor(colors['table_selection_text'])
            return QColor(colors['window_text'])
        except Exception:
            if option.state & QStyle.StateFlag.State_Selected:
                return option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText)
            return option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.Text)

    def _copy_option(self, option):
        # 拷贝一份 option，避免修改原始对象
        opt = QStyleOptionViewItem(option)
        # 清空 text，让基类不重复绘制（我们手动画）
        opt.text = ''
        return opt

    def sizeHint(self, option, index) -> QSize:
        base = super().sizeHint(option, index)
        # 增加评分条占用的额外高度
        score = index.data(QUALITY_SCORE_ROLE)
        if score is None:
            return base
        extra = self._bar_height + BAR_BOTTOM_MARGIN + self._text_bottom_margin
        return QSize(base.width(), base.height() + extra)

    def helpEvent(self, event, view, option, index) -> bool:
        # 显示评分 tooltip
        if event.type() == event.Type.ToolTip:
            score = index.data(QUALITY_SCORE_ROLE)
            grade = index.data(QUALITY_GRADE_ROLE) or ''
            tip = _score_to_tooltip(score, grade)
            if tip:
                QToolTip.showText(event.globalPos(), tip, view)
                return True
        return super().helpEvent(event, view, option, index)
