from datetime import datetime, timedelta
from typing import Dict, Any, List
from PySide6.QtWidgets import QWidget, QToolTip, QApplication
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QPainterPath
from ui.styles import AppStyles, color_to_hex


def _scaled_font(point_delta: int = 0) -> QFont:
    """基于应用字体创建 DPI 感知字体，point_delta 为相对偏移。

    字号同时套用逻辑屏宽分级因子，并保底 8pt（小屏不再出现 6pt 的不可读字号）。
    """
    base = QApplication.font() if QApplication.instance() else QFont()
    font = QFont(base)
    ps = base.pointSize() if base.pointSize() > 0 else 9
    try:
        from utils.platform_utils import get_ui_scale
        scale = get_ui_scale()
    except Exception:
        scale = 1.0
    font.setPointSizeF(max(8.0, (ps + point_delta) * scale))
    return font


def epg_metrics() -> Dict[str, int]:
    """EPG 尺寸基线：时间刻度宽 / 行高 / 表头高 / 左栏宽。

    同时跟随逻辑屏宽与用户界面缩放档位（非 QSS 尺寸，无法由样式表换算）。
    文字则由 ``_scaled_font`` 基于应用字体派生，应用字体已包含字号档位与缩
    放，因此这里只算布局，不重复放大文字。
    """
    try:
        from utils.platform_utils import get_effective_ui_scale
        scale = get_effective_ui_scale()
    except Exception:
        scale = 1.0
    try:
        from ui.typography import text_factor
        text_scale = max(1.0, text_factor())
    except Exception:
        text_scale = 1.0
    return {
        'hour_width': max(96, int(round(120 * scale))),
        'row_height': max(36, int(round(44 * scale))),
        'header_height': max(28, int(round(32 * scale))),
        # 左栏承载「序号 + 频道名」，需随字号一起放宽，否则最大档下频道名会被省略
        'left_margin': max(96, int(round(120 * scale * text_scale))),
    }


def _safe_color(color_val, fallback='#1e1e1e'):
    if not color_val:
        return QColor(fallback)
    if isinstance(color_val, str) and color_val.startswith('rgba('):
        parts = color_val.strip('rgba()').split(',')
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        a = int(float(parts[3]) * 255) if len(parts) > 3 else 255
        return QColor(r, g, b, a)
    return QColor(color_val)


class EpgTimelineWidget(QWidget):
    HOUR_WIDTH = 120
    ROW_HEIGHT = 44
    HEADER_HEIGHT = 32
    LEFT_MARGIN = 120
    # 携带原始频道对象（dict），避免同名频道按名称回查时匹配到错误频道
    channel_double_clicked = Signal(object)
    program_hovered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 实例尺寸按逻辑屏宽分级，避免小屏下字号与行高同步缩到不可读
        metrics = epg_metrics()
        self.HOUR_WIDTH = metrics['hour_width']
        self.ROW_HEIGHT = metrics['row_height']
        self.HEADER_HEIGHT = metrics['header_height']
        self.LEFT_MARGIN = metrics['left_margin']
        self._channels: List[Dict[str, Any]] = []
        self._start_hour = 0
        self._hours = 24
        self._selected_date = None
        self.setMinimumHeight(200)
        self._hover_channel = -1
        self._hover_program_idx = -1
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)
        self._cached_rects: List[List[Dict[str, Any]]] = []
        self._cache_valid = False

    def apply_metrics(self):
        """字号/缩放变更后重算刻度与行高，并用现有数据重绘。"""
        metrics = epg_metrics()
        self.HOUR_WIDTH = metrics['hour_width']
        self.ROW_HEIGHT = metrics['row_height']
        self.HEADER_HEIGHT = metrics['header_height']
        self.LEFT_MARGIN = metrics['left_margin']
        self.set_data(self._channels, self._selected_date)

    def set_data(self, channels: List[Dict[str, Any]], selected_date=None):
        self._channels = channels
        self._selected_date = selected_date
        if selected_date:
            self._start_hour = 0
        else:
            now = datetime.now()
            self._start_hour = max(0, now.hour - 2)
        n = len(self._channels)
        h = n * self.ROW_HEIGHT + 10
        self.setMinimumHeight(max(200, h))
        # 用最小宽度而非固定宽度：宽屏下由 QScrollArea 拉伸填满，避免右侧留白
        self.setMinimumWidth(self._hours * self.HOUR_WIDTH)
        self._cache_valid = False
        self._build_cache()
        self.update()

    def _get_base(self):
        if self._selected_date:
            return datetime(self._selected_date.year, self._selected_date.month, self._selected_date.day, self._start_hour, 0, 0)
        now = datetime.now()
        return now.replace(hour=self._start_hour, minute=0, second=0, microsecond=0)

    def _build_cache(self):
        self._cached_rects = []
        base = self._get_base()
        w = self._hours * self.HOUR_WIDTH
        for ch_data in self._channels:
            row_rects = []
            programs = ch_data.get('programs', [])
            for prog in programs:
                try:
                    start = datetime.fromisoformat(prog.get('start', ''))
                    end = datetime.fromisoformat(prog.get('end', ''))
                    start_sec = (start - base).total_seconds()
                    end_sec = (end - base).total_seconds()
                    x1 = (start_sec / 3600) * self.HOUR_WIDTH
                    x2 = (end_sec / 3600) * self.HOUR_WIDTH
                    if x2 < 0 or x1 > w:
                        continue
                    x1 = max(0, x1)
                    x2 = min(w, x2)
                    if x2 - x1 < 2:
                        continue
                    row_rects.append({
                        'x1': int(x1), 'x2': int(x2),
                        'title': prog.get('title', ''),
                        'start': start,
                        'end': end,
                        'desc': prog.get('desc', ''),
                    })
                except Exception:
                    pass
            self._cached_rects.append(row_rects)
        self._cache_valid = True

    def _is_current_program(self, rect_info, now=None):
        if now is None:
            now = datetime.now()
        return rect_info['start'] <= now <= rect_info['end']

    def get_current_time_x(self):
        now = datetime.now()
        base = self._get_base()
        now_sec = (now - base).total_seconds()
        now_x = (now_sec / 3600) * self.HOUR_WIDTH
        return now_x

    def paintEvent(self, event):
        if not self._cache_valid:
            self._build_cache()
        painter = QPainter(self)
        c = AppStyles._get_colors()
        bg = _safe_color(c.get('player_panel', c.get('window', '#1e1e1e')))
        text = _safe_color(c.get('player_panel_text', c.get('window_text', '#ffffff')))
        accent = _safe_color(c.get('accent', '#4a9eff'))
        border = _safe_color(c.get('player_line', c.get('mid', '#333333')))
        program_bg = _safe_color(c.get('alternate_base', '#2a2a2a'))
        # 当前节目：accent 半透明底 + accent 描边；hover：中性轻叠加。
        # 二者不能再共用同一个 highlight/table_hover 色，否则无法区分。
        current_bg = QColor(accent)
        current_bg.setAlpha(44)
        hover_bg = QColor(text)
        hover_bg.setAlpha(22)
        style = AppStyles._visual_style
        list_r = AppStyles._get_scaled_radius('list_item')

        clip = event.rect()
        painter.fillRect(clip, bg)

        if not self._channels:
            from core.language_manager import LanguageManager
            painter.setPen(text)
            painter.setFont(_scaled_font(0))
            painter.drawText(clip, Qt.AlignmentFlag.AlignCenter,
                             LanguageManager().tr('epg_empty', '暂无节目数据'))
            painter.end()
            return

        now = datetime.now()
        w = self._hours * self.HOUR_WIDTH

        first_hour = max(0, clip.left() // self.HOUR_WIDTH)
        last_hour = min(self._hours, clip.right() // self.HOUR_WIDTH + 1)
        pen_border = QPen(border, 1)
        painter.setPen(pen_border)
        for h in range(first_hour, last_hour + 1):
            x = h * self.HOUR_WIDTH
            painter.drawLine(x, 0, x, len(self._channels) * self.ROW_HEIGHT)

        first_row = max(0, clip.top() // self.ROW_HEIGHT)
        last_row = min(len(self._channels), clip.bottom() // self.ROW_HEIGHT + 1)

        small_font = _scaled_font(-2)
        fm = QFontMetrics(small_font)

        for i in range(first_row, last_row):
            y = i * self.ROW_HEIGHT
            painter.setPen(pen_border)
            painter.drawLine(0, y + self.ROW_HEIGHT, w, y + self.ROW_HEIGHT)

            if i < len(self._cached_rects):
                for prog_idx, rect_info in enumerate(self._cached_rects[i]):
                    rx1, rx2 = rect_info['x1'], rect_info['x2']
                    if rx2 < clip.left() or rx1 > clip.right():
                        continue
                    is_current = self._is_current_program(rect_info, now)
                    is_hover = (i == self._hover_channel and prog_idx == self._hover_program_idx)
                    if is_current:
                        fill = current_bg
                    elif is_hover:
                        fill = hover_bg
                    else:
                        fill = program_bg
                    rect_w = rx2 - rx1 - 2
                    rect_h = self.ROW_HEIGHT - 6
                    prog_rect = QRectF(rx1 + 1, y + 3, rect_w, rect_h)

                    if list_r > 0 and rect_w > 4 and rect_h > 4:
                        prog_path = QPainterPath()
                        prog_path.addRoundedRect(prog_rect, list_r, list_r)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(fill)
                        painter.drawPath(prog_path)
                        if style == 'neumorphic':
                            shadow_color = QColor(0, 0, 0, 40)
                            painter.setPen(QPen(shadow_color, 1))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawPath(prog_path)
                        elif style == 'skeuomorphic':
                            border_light = _safe_color(c.get('border_3d_light', '#555555'))
                            painter.setPen(QPen(border_light, 1))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawPath(prog_path)
                        elif style in ('frosted', 'win11'):
                            frosted_border = _safe_color(c.get('frosted_border', c.get('border_thin', c.get('mid', '#555555'))))
                            painter.setPen(QPen(frosted_border, 1))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawPath(prog_path)
                        if is_current:
                            painter.setPen(QPen(accent, 1))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            painter.drawPath(prog_path)
                    else:
                        painter.fillRect(rx1 + 1, y + 3, rect_w, rect_h, fill)

                    painter.setPen(text)
                    painter.setFont(small_font)
                    text_w = rect_w - 8
                    title = rect_info['title']
                    if text_w > 0 and title:
                        elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, text_w)
                        painter.drawText(rx1 + 4, y + 3, rect_w, rect_h,
                                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                       elided)

        # 复用 paintEvent 开头获取的 now，避免每帧重复调用系统时钟
        base = self._get_base()
        now_sec = (now - base).total_seconds()
        now_x = (now_sec / 3600) * self.HOUR_WIDTH
        if 0 <= now_x <= w:
            pen_now = QPen(accent, 2)
            painter.setPen(pen_now)
            painter.drawLine(int(now_x), 0, int(now_x), len(self._channels) * self.ROW_HEIGHT)
            now_label = now.strftime('%H:%M')
            label_font = _scaled_font(-3)
            painter.setFont(label_font)
            painter.drawText(int(now_x) + 4, 0, 50, self.HEADER_HEIGHT,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           now_label)

        painter.end()

    def _get_program_at(self, pos):
        x, y = pos.x(), pos.y()
        row = y // self.ROW_HEIGHT
        if row < 0 or row >= len(self._channels):
            return None, None
        ch = self._channels[row]
        base = self._get_base()
        click_sec = (x / self.HOUR_WIDTH) * 3600
        click_time = base + timedelta(seconds=click_sec)
        for prog in ch.get('programs', []):
            try:
                start = datetime.fromisoformat(prog.get('start', ''))
                end = datetime.fromisoformat(prog.get('end', ''))
                if start <= click_time <= end:
                    return ch, prog
            except Exception:
                pass
        return ch, None

    def _get_cached_program_at(self, pos):
        x, y = pos.x(), pos.y()
        row = y // self.ROW_HEIGHT
        if row < 0 or row >= len(self._cached_rects):
            return None
        for rect_info in self._cached_rects[row]:
            if rect_info['x1'] <= x <= rect_info['x2']:
                return rect_info
        return None

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        row = pos.y() // self.ROW_HEIGHT
        rect_info = self._get_cached_program_at(pos)
        if rect_info:
            title = rect_info.get('title', '')
            start_str = rect_info['start'].strftime('%H:%M')
            end_str = rect_info['end'].strftime('%H:%M')
            tip = f"{title}\n{start_str} - {end_str}"
            desc = rect_info.get('desc', '')
            if desc:
                tip += f"\n{desc}"
            QToolTip.showText(event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else self.mapToGlobal(pos), tip, self)
            new_ch = row
            new_idx = self._cached_rects[row].index(rect_info) if row < len(self._cached_rects) else -1
        else:
            QToolTip.hideText()
            new_ch = -1
            new_idx = -1
        if new_ch != self._hover_channel or new_idx != self._hover_program_idx:
            self._hover_channel = new_ch
            self._hover_program_idx = new_idx
            self.update()

    def leaveEvent(self, event):
        self._hover_channel = -1
        self._hover_program_idx = -1
        QToolTip.hideText()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ch, prog = self._get_program_at(event.position().toPoint() if hasattr(event, 'position') else event.pos())
            if ch:
                # 优先回传原始频道对象（含 url 等唯一信息），同名频道也能精确匹配
                original = ch.get('channel')
                self.channel_double_clicked.emit(original if original else {'name': ch.get('name', '')})


class EpgChannelHeaderWidget(QWidget):
    # 频道列行高必须与节目区 EpgTimelineWidget.ROW_HEIGHT 一致，否则左右并排
    # 滚动时频道名与节目块逐行错位（两部件由对话框按同一滚动值同步）。
    ROW_HEIGHT = EpgTimelineWidget.ROW_HEIGHT
    # 左侧台号宽度 / 台标盒宽度 / 内边距
    NUM_WIDTH = 26
    LOGO_WIDTH = 34
    LOGO_HEIGHT = 26
    PADDING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        # 与节目区共用同一套分级尺寸，保证左右并排滚动时逐行对齐
        metrics = epg_metrics()
        self.ROW_HEIGHT = metrics['row_height']
        self.NUM_WIDTH = max(22, int(round(26 * metrics['row_height'] / 44)))
        self.LOGO_WIDTH = max(28, int(round(34 * metrics['row_height'] / 44)))
        self.LOGO_HEIGHT = max(20, int(round(26 * metrics['row_height'] / 44)))
        self._channels: List[Dict[str, Any]] = []
        self._display_names: List[str] = []
        self._current_channel = None
        self._logo_service = None
        self._logo_pixmaps: Dict[str, Any] = {}
        self.setAutoFillBackground(False)

    def apply_metrics(self):
        """与节目区共用基线：重算行高与台号/台标尺寸并重绘。"""
        metrics = epg_metrics()
        self.ROW_HEIGHT = metrics['row_height']
        self.NUM_WIDTH = max(22, int(round(26 * metrics['row_height'] / 44)))
        self.LOGO_WIDTH = max(28, int(round(34 * metrics['row_height'] / 44)))
        self.LOGO_HEIGHT = max(20, int(round(26 * metrics['row_height'] / 44)))
        self.set_data(self._channels)

    def set_data(self, channels: List[Dict[str, Any]]):
        self._channels = channels
        self._display_names = self._build_display_names(channels)
        n = len(self._channels)
        h = n * self.ROW_HEIGHT + 10
        self.setFixedHeight(max(200, h))
        self.update()

    @staticmethod
    def _build_display_names(channels: List[Dict[str, Any]]) -> List[str]:
        """行显示名：同名多路流（同一频道的不同码流）追加分辨率后缀。

        复用频道列表的同名后缀规则（同名才加，无分辨率退回频道号），
        避免两处规则漂移；只影响显示文本，不改频道数据。
        """
        name_counts: Dict[str, int] = {}
        for ch in channels:
            name = (ch.get('name') or '').strip()
            name_counts[name] = name_counts.get(name, 0) + 1
        from controllers.channel_controller import ChannelController
        names: List[str] = []
        for ch in channels:
            # 行数据里 'channel' 是原始频道对象，分辨率/频道号要从它取
            src = ch.get('channel')
            if not isinstance(src, dict):
                src = ch
            names.append(
                ChannelController._channel_list_display_name(src, ch.get('name', ''), name_counts)
            )
        return names

    def set_current_channel(self, channel):
        """channel 可以是原始频道 dict（按对象身份匹配），也兼容传频道名。"""
        self._current_channel = channel
        self.update()

    def set_logo_service(self, service):
        if service is self._logo_service:
            return
        self._logo_service = service
        self._logo_pixmaps.clear()
        if service is not None and hasattr(service, 'logo_loaded'):
            try:
                service.logo_loaded.connect(self._on_logo_loaded)
            except (RuntimeError, TypeError):
                pass
        self.update()

    def _on_logo_loaded(self, url, pixmap):
        if not url or pixmap is None or pixmap.isNull():
            return
        self._logo_pixmaps[url] = self._scale_logo(pixmap)
        self.update()

    def _scale_logo(self, pixmap):
        return pixmap.scaled(
            self.LOGO_WIDTH, self.LOGO_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _is_current(self, ch_data):
        if self._current_channel is None:
            return False
        original = ch_data.get('channel')
        if isinstance(self._current_channel, dict):
            if original is not None:
                return original is self._current_channel or (
                    original.get('url') and original.get('url') == self._current_channel.get('url')
                )
            return ch_data.get('name', '') == self._current_channel.get('name', '')
        # 兼容旧调用：传的是频道名字符串
        return ch_data.get('name', '') == self._current_channel

    def _get_logo_pixmap(self, logo_url):
        if not logo_url or self._logo_service is None:
            return None
        cached = self._logo_pixmaps.get(logo_url)
        if cached is not None:
            return cached if cached is not False else None
        try:
            pixmap = self._logo_service.get(logo_url)
        except Exception:
            pixmap = None
        if pixmap is None or pixmap.isNull():
            # 标记为缺失，并异步拉取（不阻塞绘制）
            self._logo_pixmaps[logo_url] = False
            try:
                self._logo_service.fetch_async(logo_url)
            except Exception:
                pass
            return None
        scaled = self._scale_logo(pixmap)
        self._logo_pixmaps[logo_url] = scaled
        return scaled

    def paintEvent(self, event):
        painter = QPainter(self)
        c = AppStyles._get_colors()
        text = _safe_color(c.get('player_panel_text', c.get('window_text', '#ffffff')))
        border = _safe_color(c.get('player_line', c.get('mid', '#333333')))
        header_bg = _safe_color(c.get('alternate_base', c.get('window', '#2d2d2d')))
        accent = _safe_color(c.get('accent', '#4a9eff'))

        w = self.width()
        clip = event.rect()
        painter.fillRect(clip, header_bg)

        pen = QPen(border, 1)
        font = _scaled_font(-1)
        num_font = _scaled_font(-3)
        painter.setFont(font)
        fm = QFontMetrics(font)

        num_w = self.NUM_WIDTH
        logo_w = self.LOGO_WIDTH if self._logo_service is not None else 0
        name_x = self.PADDING + num_w + (logo_w + self.PADDING if logo_w else 0)
        name_w = max(0, w - name_x - self.PADDING)

        first_row = max(0, clip.top() // self.ROW_HEIGHT)
        last_row = min(len(self._channels), clip.bottom() // self.ROW_HEIGHT + 1)

        for i in range(first_row, last_row):
            y = i * self.ROW_HEIGHT
            ch_data = self._channels[i]
            ch_name = (self._display_names[i] if i < len(self._display_names)
                       else ch_data.get('name', ''))
            is_current = self._is_current(ch_data)
            if is_current:
                painter.fillRect(0, y, w, self.ROW_HEIGHT, QColor(accent.red(), accent.green(), accent.blue(), 40))
            painter.setPen(pen)
            painter.drawLine(0, y + self.ROW_HEIGHT, w, y + self.ROW_HEIGHT)

            # 台号
            painter.setFont(num_font)
            painter.setPen(QColor(text.red(), text.green(), text.blue(), 150))
            painter.drawText(self.PADDING, y, num_w - self.PADDING, self.ROW_HEIGHT,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             str(i + 1))

            # 台标（有缓存/可加载时显示）
            if logo_w:
                pixmap = self._get_logo_pixmap(ch_data.get('logo', ''))
                if pixmap is not None:
                    lx = self.PADDING + num_w
                    ly = y + (self.ROW_HEIGHT - self.LOGO_HEIGHT) // 2
                    painter.drawPixmap(lx, ly, pixmap)

            # 频道名（按剩余宽度省略，避免文字溢出压到节目区）
            painter.setFont(font)
            painter.setPen(accent if is_current else text)
            if name_w > 0 and ch_name:
                elided = fm.elidedText(ch_name, Qt.TextElideMode.ElideRight, name_w)
                painter.drawText(name_x, y, name_w, self.ROW_HEIGHT,
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 elided)

        painter.end()


class EpgTimeHeaderWidget(QWidget):
    HOUR_WIDTH = 120
    HEADER_HEIGHT = 32

    def __init__(self, parent=None):
        super().__init__(parent)
        metrics = epg_metrics()
        self.HOUR_WIDTH = metrics['hour_width']
        self.HEADER_HEIGHT = metrics['header_height']
        self._start_hour = 0
        self._hours = 24
        self.setAutoFillBackground(False)

    def apply_metrics(self):
        """字号/缩放变更后重算时间刻度宽与表头高。"""
        metrics = epg_metrics()
        self.HOUR_WIDTH = metrics['hour_width']
        self.HEADER_HEIGHT = metrics['header_height']
        self.set_start_hour(self._start_hour)

    def set_start_hour(self, start_hour):
        self._start_hour = start_hour
        self.setMinimumWidth(self._hours * self.HOUR_WIDTH)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        c = AppStyles._get_colors()
        text = _safe_color(c.get('player_panel_text', c.get('window_text', '#ffffff')))
        border = _safe_color(c.get('player_line', c.get('mid', '#333333')))
        header_bg = _safe_color(c.get('alternate_base', c.get('window', '#2d2d2d')))

        w = self._hours * self.HOUR_WIDTH
        clip = event.rect()
        painter.fillRect(clip, header_bg)
        pen = QPen(border, 1)
        painter.setPen(pen)
        painter.drawLine(0, self.HEADER_HEIGHT, w, self.HEADER_HEIGHT)

        font = _scaled_font(-1)
        painter.setFont(font)
        painter.setPen(text)

        first_hour = max(0, clip.left() // self.HOUR_WIDTH)
        last_hour = min(self._hours, clip.right() // self.HOUR_WIDTH + 1)

        for h in range(first_hour, last_hour + 1):
            hour = (self._start_hour + h) % 24
            x = h * self.HOUR_WIDTH
            painter.drawText(x + 4, 0, self.HOUR_WIDTH - 8, self.HEADER_HEIGHT,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           f"{hour:02d}:00")
            painter.setPen(pen)
            painter.drawLine(x, 0, x, self.HEADER_HEIGHT)
            painter.setPen(text)

        painter.end()
