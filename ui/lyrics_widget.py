import re
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QBrush


# 歌词显示配置常量（任务B）：位置 / 形式 / 字号
LYRICS_POS_ANCHOR = {'top': 0.18, 'center': 0.5, 'bottom': 0.82}
LYRICS_FONT_SCALE = {'small': 0.8, 'medium': 1.0, 'large': 1.3}
_LYRICS_CFG_SECTION = 'Player'
_LYRICS_CFG_KEYS = {
    'pos': 'lyrics_position',
    'mode': 'lyrics_display_mode',
    'font': 'lyrics_font_scale',
}


def parse_lrc(lrc_text):
    lines = []
    time_pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]')
    tag_pattern = re.compile(r'\[.*?\]')
    for line in lrc_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        matches = time_pattern.findall(line)
        text = tag_pattern.sub('', line).strip()
        if not text:
            continue
        for m in matches:
            try:
                minutes = int(m[0])
                seconds = int(m[1])
                ms = 0
                if m[2]:
                    raw = m[2]
                    if len(raw) == 1:
                        ms = int(raw) * 100
                    elif len(raw) == 2:
                        ms = int(raw) * 10
                    else:
                        ms = int(raw[:3].ljust(3, '0'))
                time_sec = minutes * 60 + seconds + ms / 1000.0
                lines.append((time_sec, text))
            except (ValueError, IndexError):
                continue
    lines.sort(key=lambda x: x[0])
    return lines if lines else None


def parse_plain_lyrics(text):
    lines = []
    for i, line in enumerate(text.split('\n')):
        line = line.strip()
        if line:
            lines.append((i * 5, line))
    return lines if lines else None


class LyricsWidget(QWidget):
    # 滚动动画刷新间隔（25fps）；必须显式设置，QTimer 默认 interval 为 0 会导致满帧重绘
    REPAINT_INTERVAL_MS = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []
        self._current_idx = -1
        self._scroll_y = 0.0
        self._target_y = 0.0
        # 歌词来源：'embedded'（音频内嵌）/ 'external'（用户加载的 .lrc）/ ''（空）
        self._lyrics_source = ''
        self._line_height = 52
        # 歌词显示配置（任务B）：位置 / 形式 / 字号，持久化到 ConfigManager
        self._position_mode = 'center'   # top / center / bottom
        self._display_mode = 'multi'     # single / multi
        self._font_scale_mode = 'medium'  # small / medium / large
        from ui.styles import AppStyles
        _family = AppStyles._get_style_font_family().split(",")[0].strip("' ")
        _family = _family if _family else "sans-serif"
        self._font = QFont(_family, 16)
        self._font_current = QFont(_family, 22, QFont.Weight.Bold)
        self._load_settings()
        self._apply_font_scale()

        self._timer = QTimer(self)
        self._timer.setInterval(self.REPAINT_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ---- 歌词显示配置（任务B）：持久化 + setter/getter ----

    def _load_settings(self):
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            pos = config.get_value(_LYRICS_CFG_SECTION, _LYRICS_CFG_KEYS['pos'], 'center')
            mode = config.get_value(_LYRICS_CFG_SECTION, _LYRICS_CFG_KEYS['mode'], 'multi')
            font = config.get_value(_LYRICS_CFG_SECTION, _LYRICS_CFG_KEYS['font'], 'medium')
            if pos in LYRICS_POS_ANCHOR:
                self._position_mode = pos
            if mode in ('single', 'multi'):
                self._display_mode = mode
            if font in LYRICS_FONT_SCALE:
                self._font_scale_mode = font
        except Exception:
            pass

    @staticmethod
    def _save_setting(key, value):
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            config.set_value(_LYRICS_CFG_SECTION, _LYRICS_CFG_KEYS[key], value)
            config.save_config()
        except Exception:
            pass

    def _apply_font_scale(self):
        """按档位缩放系数重建缓存字体与行高。"""
        scale = LYRICS_FONT_SCALE.get(self._font_scale_mode, 1.0)
        self._font_s = QFont(self._font)
        self._font_s.setPointSizeF(self._font.pointSizeF() * scale)
        self._font_c = QFont(self._font_current)
        self._font_c.setPointSizeF(self._font_current.pointSizeF() * scale)
        # 单行大字：当前行字体再放大 1.35 倍
        self._font_single = QFont(self._font_current)
        self._font_single.setPointSizeF(self._font_current.pointSizeF() * 1.35 * scale)
        self._line_height = int(52 * scale)
        if self._current_idx >= 0:
            self._target_y = self._current_idx * self._line_height

    def set_position_mode(self, mode):
        if mode not in LYRICS_POS_ANCHOR:
            return
        self._position_mode = mode
        self._save_setting('pos', mode)
        self.update()

    def get_position_mode(self):
        return self._position_mode

    def set_display_mode(self, mode):
        if mode not in ('single', 'multi'):
            return
        self._display_mode = mode
        self._save_setting('mode', mode)
        self.update()

    def get_display_mode(self):
        return self._display_mode

    def set_font_scale(self, mode):
        """mode: 'small' / 'medium' / 'large'（缩放系数 0.8 / 1.0 / 1.3）。"""
        if mode not in LYRICS_FONT_SCALE:
            return
        self._font_scale_mode = mode
        self._apply_font_scale()
        self._save_setting('font', mode)
        self.update()

    def get_font_scale_mode(self):
        return self._font_scale_mode

    def reapply_styles(self):
        """主题切换时刷新绘制"""
        self.update()
        self._timer.setInterval(self.REPAINT_INTERVAL_MS)

    def set_lyrics(self, lrc_text, is_lrc=True, source='embedded'):
        if is_lrc:
            parsed = parse_lrc(lrc_text)
            if not parsed:
                parsed = parse_plain_lyrics(lrc_text)
        else:
            parsed = parse_plain_lyrics(lrc_text)
        self._lines = parsed or []
        self._lyrics_source = source if self._lines else ''
        self._current_idx = -1
        self._scroll_y = 0.0
        self._target_y = 0.0
        self.update()

    def has_lyrics(self):
        return bool(self._lines)

    def get_lyrics_source(self):
        return self._lyrics_source

    def update_time(self, time_sec):
        if not self._lines:
            return
        new_idx = -1
        for i, (t, _) in enumerate(self._lines):
            if t <= time_sec:
                new_idx = i
            else:
                break
        if new_idx != self._current_idx:
            self._current_idx = new_idx
            self._target_y = new_idx * self._line_height
            # 仅在当前行变化时请求重绘，滚动过程由 _tick 定时器驱动
            self.update()

    def start(self):
        self._timer.start(self.REPAINT_INTERVAL_MS)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        needs_repaint = False
        parent = self.parent()
        if parent:
            pw, ph = parent.width(), parent.height()
            if pw > 0 and ph > 0 and (self.width() != pw or self.height() != ph):
                self.setGeometry(0, 0, pw, ph)
                needs_repaint = True
        diff = self._target_y - self._scroll_y
        if self._display_mode == 'multi':
            if abs(diff) > 0.5:
                self._scroll_y += diff * 0.15
                needs_repaint = True
            elif self._scroll_y != self._target_y:
                self._scroll_y = self._target_y
                needs_repaint = True
        # 滚动已稳定时不再逐帧重绘，避免闲置时持续 25fps 重绘
        if needs_repaint:
            self.update()

    def paintEvent(self, event):
        if not self._lines:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        # 歌词锚点：顶部 / 居中 / 底部（相对 video_frame 区域即自身高度）
        cy = h * LYRICS_POS_ANCHOR.get(self._position_mode, 0.5)
        if self._display_mode == 'single':
            self._paint_single_line(painter, w, h, cy)
        else:
            self._paint_multi_line(painter, w, h, cy)
        painter.end()

    def _paint_single_line(self, painter, w, h, cy):
        """单行大字：只绘制当前行，锚点处水平垂直居中。"""
        idx = self._current_idx
        if idx < 0 or idx >= len(self._lines):
            return
        _, text = self._lines[idx]
        painter.setFont(self._font_single)
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        text_height = fm.height()
        x = (w - text_width) / 2.0
        baseline_y = cy + text_height / 3.0
        alpha = 255
        grad = QLinearGradient(x, baseline_y, x + text_width, baseline_y)
        grad.setColorAt(0, QColor(80, 180, 255, alpha))
        grad.setColorAt(0.5, QColor(255, 255, 255, alpha))
        grad.setColorAt(1, QColor(80, 180, 255, alpha))
        painter.setPen(QPen(QBrush(grad), 1))
        painter.drawText(int(x), int(baseline_y), text)

    def _paint_multi_line(self, painter, w, h, cy):
        """多行滚动：当前行 + 上下文（含平滑滚动与淡出层次）。"""
        n = len(self._lines)
        line_h = self._line_height
        visible_count = int(h / line_h) + 4
        half = visible_count // 2

        for offset in range(-half, half + 1):
            idx = self._current_idx + offset
            if idx < 0 or idx >= n:
                continue
            _, text = self._lines[idx]

            scroll_frac = (self._scroll_y - self._target_y) / line_h if line_h > 0 else 0
            y = cy + (offset - scroll_frac) * line_h

            if y < -line_h * 2 or y > h + line_h * 2:
                continue

            distance = abs(offset)
            if distance == 0:
                alpha = 255
                painter.setFont(self._font_c)
                painter.setPen(QColor(255, 255, 255, alpha))
            elif distance == 1:
                alpha = 180
                painter.setFont(self._font_s)
                painter.setPen(QColor(200, 210, 230, alpha))
            elif distance == 2:
                alpha = 120
                painter.setFont(self._font_s)
                painter.setPen(QColor(160, 170, 190, alpha))
            else:
                alpha = max(20, 80 - distance * 12)
                painter.setFont(self._font_s)
                painter.setPen(QColor(120, 130, 150, alpha))

            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            text_height = fm.height()
            x = (w - text_width) / 2.0
            baseline_y = y + text_height / 2.0

            if distance == 0:

                grad = QLinearGradient(x, baseline_y, x + text_width, baseline_y)
                grad.setColorAt(0, QColor(80, 180, 255, alpha))
                grad.setColorAt(0.5, QColor(255, 255, 255, alpha))
                grad.setColorAt(1, QColor(80, 180, 255, alpha))
                painter.setPen(QPen(QBrush(grad), 1))

            painter.drawText(int(x), int(baseline_y), text)
