"""媒体属性对话框。

对齐安卓分屏播放页右侧「信息」那一屏，PC 端能拿到的同类项都放进来。
数据全部来自 mpv，取不到的项显示「—」并在底部说明；不做推断、不写死假值。

数据源：
- MpvPlayerController.get_live_media_info()（每秒刷新一次的扁平字典）
- 少量 mpv 属性直接读取（display-fps / total-avsync-change / metadata / track-list 等）
"""
import json
import math
import re

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QSizePolicy, QWidget, QFrame,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from controllers.ui_controller import UIController
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class _ElidedValueLabel(QLabel):
    """定宽单行数值标签。

    单元格宽度由对话框尺寸固定，文本超出时右侧省略并保留完整 tooltip，
    这样每秒刷新时数值长短变化不会改变控件尺寸，也就不会带动整行抖动或换行。
    """

    def __init__(self, text: str = '—', width: int = 0, role: str = 'value'):
        super().__init__()
        self._full_text = ''
        self.setObjectName('propsValue')
        self.setProperty('role', role)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if width > 0:
            self.setFixedWidth(width)
        self.set_full_text(text)

    def set_full_text(self, text: str):
        self._full_text = text or ''
        self.setToolTip(self._full_text)
        self._update_elided()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        fm = self.fontMetrics()
        width = max(0, self.width() - 2)
        if width <= 0:
            text = self._full_text
        else:
            text = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        if text != QLabel.text(self):
            QLabel.setText(self, text)


class _ProgressLine(QWidget):
    """3px 播放进度条：自绘，避免 QProgressBar 的样式高度不稳定。"""

    def __init__(self):
        super().__init__()
        self._percent = 0
        self.setFixedHeight(3)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_percent(self, percent: int):
        value = max(0, min(100, int(percent)))
        if value != self._percent:
            self._percent = value
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        accent = QColor(AppStyles._get_colors().get('accent') or '#4a9eff')
        track = QColor(accent)
        track.setAlpha(64)
        radius = self.height() / 2
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), radius, radius)
        if self._percent > 0:
            width = self.width() * self._percent / 100
            painter.setBrush(accent)
            painter.drawRoundedRect(QRectF(0, 0, width, self.height()), radius, radius)
        painter.end()


class MediaPropertiesDialog(FloatingDialog):
    """媒体属性（实时刷新，每秒一次）"""

    REFRESH_MS = 1000
    # 独立工作窗口：任务栏/Alt+Tab 可见、跟随主窗口置顶、切回程序时回到前台
    _allow_taskbar = True
    _restore_on_app_activate = True

    # 分组：标题 key，标题默认值，[(字段 key, 标签 key, 默认标签), ...]
    PLAYBACK_ROWS = [
        ('resolution', 'stream_quality_resolution', '分辨率'),
        ('aspect', 'properties_aspect', '画面比例'),
        ('scan_mode', 'properties_scan_mode', '扫描方式'),
        ('rotation', 'properties_rotation', '旋转'),
        ('duration', 'properties_duration', '时长'),
        ('position', 'properties_position', '当前位置'),
        ('progress', 'properties_progress', '进度'),
    ]
    VIDEO_ROWS = [
        ('video_codec', 'properties_video_codec', '视频编码'),
        ('fps', 'stream_quality_fps', '帧率'),
        ('display_fps', 'properties_display_fps', '屏幕刷新'),
        ('video_bitrate', 'stream_quality_video_bitrate', '视频码率'),
        ('pixel_format', 'stream_quality_pixel_format', '像素格式'),
        ('bit_depth', 'properties_bit_depth', '位深'),
        ('color_space', 'properties_color_space', '色彩空间'),
        ('color_primaries', 'stream_quality_primaries', '色彩原色'),
        ('gamma', 'stream_quality_gamma', '传输特性'),
        ('color_range', 'properties_color_range', '色彩范围'),
        ('vo', 'stream_quality_vo', '视频输出'),
        ('gpu_api', 'properties_gpu_api', '渲染后端'),
        ('decode_mode', 'properties_decode_mode', '解码方式'),
    ]
    AUDIO_ROWS = [
        ('audio_codec', 'properties_audio_codec', '音频编码'),
        ('audio_bitrate', 'stream_quality_audio_bitrate', '音频码率'),
        ('sample_rate', 'stream_quality_sample_rate', '采样率'),
        ('channels', 'stream_quality_audio_channels', '声道数'),
        ('audio_format', 'properties_audio_format', '采样格式'),
    ]
    NETWORK_ROWS = [
        ('protocol', 'properties_protocol', '协议'),
        ('container', 'stream_quality_container', '封装格式'),
        ('cache_duration', 'stream_quality_cache_duration', '缓存时长'),
        ('cache_size', 'properties_cache_size', '缓存大小'),
        ('cache_speed', 'stream_quality_cache_speed', '缓存速度'),
        ('buffering', 'properties_buffering', '缓冲状态'),
        ('first_frame', 'properties_first_frame', '首帧耗时'),
        ('av_sync', 'properties_av_sync', '音画偏移'),
        ('dropped_frames', 'stream_quality_decoder_drop', '解码器丢帧'),
        ('render_drops', 'properties_render_drops', '渲染丢帧'),
        ('render_fps', 'properties_actual_fps', '实际帧率'),
        ('track_count', 'properties_track_count', '轨道数'),
        ('service_name', 'properties_service_name', '电视台'),
        ('service_provider', 'properties_service_provider', '运营商'),
        ('media_title', 'properties_media_title', '流标题'),
    ]

    def __init__(self, main_window, parent=None):
        # 无边框：卡面自绘并铺满整个窗口。带原生边框时，WA_TranslucentBackground
        # 会让标题栏与 7px 左右/底部缩放边框变成不可见的透明带，点上去没有反应。
        super().__init__(parent, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('properties_title', '属性'))
        self._labels = {}
        self._chips = {}
        self._size_applied = False
        self._apply_theme()
        self._setup_ui()

        from ui.theme_manager import safe_register_window
        safe_register_window(self)

        self._timer = QTimer(self)
        self._timer.setInterval(self.REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        QTimer.singleShot(DelayMs.UI_REFRESH, self._refresh)

    # ---------- UI ----------
    def reapply_styles(self):
        self._apply_theme()

    @staticmethod
    def _luminance(hex_color: str) -> float:
        raw = (hex_color or '').lstrip('#')
        if len(raw) != 6:
            return 0.0
        try:
            r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        except ValueError:
            return 0.0
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0

    def _apply_theme(self):
        tr = self.window.language_manager.tr
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        label_color = c.get('mid')
        accent = c.get('accent')
        dark = self._luminance(text_color) > 0.5
        zebra = 'rgba(255,255,255,0.035)' if dark else 'rgba(0,0,0,0.03)'
        card_bg = 'rgba(255,255,255,0.03)' if dark else 'rgba(0,0,0,0.022)'
        chip_bg = self._rgba(accent, 0.16)
        chip_border = self._rgba(accent, 0.42)

        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel[role="title"] {{ color: {text_color}; font-size: 15px; font-weight: 600; }}
            QLabel[role="hint"] {{ color: {label_color}; font-size: 11px; }}
            QLabel[role="label"] {{ color: {label_color}; font-size: 11px; }}
            QLabel[role="label"][zebra="true"] {{ background: {zebra}; border-radius: 3px; }}
            QLabel[role="value"] {{ color: {text_color}; font-size: 11px;
                font-family: Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace; }}
            QLabel[role="value"][absent="true"] {{ color: {label_color}; }}
            QLabel[role="value"][zebra="true"] {{ background: {zebra}; border-radius: 3px; }}
            QLabel[role="chip"] {{ color: {accent}; background: {chip_bg};
                border: 1px solid {chip_border}; border-radius: 9px;
                padding: 2px 8px; font-size: 11px; font-weight: 600; }}
            QGroupBox {{
                color: {text_color}; background: {card_bg};
                border: 1px solid {self._rgba(label_color, 0.35)};
                border-radius: {max(6, r)}px;
                margin-top: 10px; padding: 6px 8px 6px 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
                color: {accent}; font-weight: 600; font-size: 11px;
            }}
            QScrollArea {{ background: transparent; border: none; }}
        """)
        self._repolish_children()

    @staticmethod
    def _rgba(hex_color: str, alpha: float) -> str:
        raw = (hex_color or '').lstrip('#')
        if len(raw) != 6:
            return f'rgba(128,128,128,{alpha})'
        try:
            r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        except ValueError:
            return f'rgba(128,128,128,{alpha})'
        return f'rgba({r},{g},{b},{alpha})'

    def _repolish_children(self):
        style = self.style()
        widgets = list(self._labels.values()) + list(self._chips.values())
        content = getattr(self, '_content', None)
        if content is not None:
            widgets.append(content)
        for widget in widgets:
            try:
                style.unpolish(widget)
                style.polish(widget)
            except RuntimeError:
                pass

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 6)
        outer.setSpacing(5)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll = scroll

        content = QWidget()
        self._content = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        # 探针标签取真实字体度量（QSS 固定 11px，直接读 self.fontMetrics() 会跟随系统字号）
        probe = QLabel('—', self)
        probe.setProperty('role', 'value')
        probe.ensurePolished()
        self._fm = probe.fontMetrics()
        probe.deleteLater()

        content_layout.addLayout(self._build_header(tr))
        content_layout.addWidget(self._progress)

        body = QHBoxLayout()
        body.setSpacing(6)
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_col.addWidget(self._build_group(
            tr('properties_group_playback', '播放信息'), self.PLAYBACK_ROWS, columns=1))
        left_col.addWidget(self._build_group(
            tr('properties_group_audio', '音频'), self.AUDIO_ROWS, columns=1))
        left_col.addStretch(1)
        body.addLayout(left_col, 1)
        body.addWidget(self._build_group(
            tr('properties_group_video', '视频'), self.VIDEO_ROWS, columns=1), 1)
        body.addWidget(self._build_group(
            tr('properties_group_network', '网络与性能'), self.NETWORK_ROWS, columns=1), 1)
        content_layout.addLayout(body, 1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        footer = QHBoxLayout()
        self._footer = footer
        hint = QLabel(tr('properties_na_hint', '「—」表示当前源未提供该项，数值每秒刷新'))
        hint.setProperty('role', 'hint')
        self._hint = hint
        footer.addWidget(hint)
        footer.addStretch()
        close_btn = QPushButton(tr('close', '关闭'))
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

    def _build_header(self, tr) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel(tr('properties_title', '属性'))
        title.setProperty('role', 'title')
        header.addWidget(title)

        chip_widths = {'mode': 56, 'resolution': 108, 'fps': 72, 'hwdec': 60, 'hdr': 66}
        for key, default in (('mode', '直播'), ('resolution', '—'), ('fps', '—'),
                             ('hwdec', '—'), ('hdr', 'SDR')):
            chip = _ElidedValueLabel(default, width=chip_widths[key], role='chip')
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedHeight(self._fm.height() + 10)
            self._chips[key] = chip
            header.addWidget(chip)
        header.addStretch()

        self._progress = _ProgressLine()
        return header

    def _build_group(self, title, rows, columns=1):
        """按固定行高/列宽构建分组，columns>1 时按列优先填充。"""
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(6, 4, 6, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(1)

        tr = self.window.language_manager.tr
        fm = self._fm
        label_texts = [tr(key, default) for _, key, default in rows]
        label_w = max(fm.horizontalAdvance(text) for text in label_texts) + 6
        row_h = fm.height() + 4
        # 数值列宽按最长的常见值预留（如「硬解(mediacodec-copy)」），封顶避免极端字体把窗口撑宽；
        # 真正超长的自由文本（流标题/电视台/运营商）在单元格内省略并保留完整 tooltip。
        value_min = min(128, max(84, fm.horizontalAdvance('硬解(mediacodec-copy)') + 6))
        per_col = math.ceil(len(rows) / max(1, columns))

        for idx, ((key, label_key, label_default), label_text) in enumerate(zip(rows, label_texts)):
            row, col = idx % per_col, idx // per_col
            zebra = (row % 2 == 1)
            label = QLabel(label_text)
            label.setProperty('role', 'label')
            label.setProperty('zebra', zebra)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setFixedSize(label_w, row_h)
            value = _ElidedValueLabel('—')
            value.setProperty('zebra', zebra)
            value.setMinimumWidth(value_min)
            value.setFixedHeight(row_h)
            grid.addWidget(label, row, col * 2)
            grid.addWidget(value, row, col * 2 + 1)
            self._labels[key + '__label'] = label
            self._labels[key] = value

        for col in range(columns):
            grid.setColumnStretch(col * 2 + 1, 1)
        return group

    def _apply_compact_size(self):
        """窗口按内容自然尺寸一次定好，全部字段一屏显示；屏幕确实不够时滚动兜底。"""
        try:
            self.layout().activate()
            self._content.ensurePolished()
            self._content.adjustSize()
            hint = self._content.sizeHint()
            min_hint = self._content.minimumSizeHint()
            content_w = max(hint.width(), min_hint.width())
            content_h = max(hint.height(), min_hint.height())
            margins = self.layout().contentsMargins()
            spacing = self.layout().spacing()
            footer_h = self._footer.sizeHint().height() if self._footer else 0
            width = content_w + margins.left() + margins.right() + 4
            height = content_h + margins.top() + margins.bottom() + footer_h + spacing + 4
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                width = min(width, max(560, avail.width() - 24))
                height = min(height, max(360, avail.height() - 64))
            self.resize(width, height)
        except Exception as e:
            logger.debug(f"计算属性对话框尺寸失败: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        # 首次显示时布局才完成 polish，这里再按真实 sizeHint 定一次尺寸并重新居中
        if not getattr(self, '_size_applied', False):
            self._size_applied = True
            self._apply_compact_size()
            try:
                screen = self.screen() or QApplication.primaryScreen()
                if screen:
                    sg = screen.availableGeometry()
                    self.move(
                        sg.x() + max(0, (sg.width() - self.width()) // 2),
                        sg.y() + max(0, (sg.height() - self.height()) // 2),
                    )
            except Exception as e:
                logger.debug(f"属性对话框居中失败: {e}")

    # ---------- 实时刷新 ----------
    def _refresh(self):
        if not self.isVisible():
            return
        try:
            pc = self.window.player_controller
            if not pc or not hasattr(pc, 'get_live_media_info'):
                self._set_all_unavailable()
                return
            try:
                info = pc.get_live_media_info()
            except Exception as e:
                logger.debug(f"get_live_media_info 失败: {e}")
                info = None
            if not info:
                self._set_all_unavailable()
                return
            self._update_rows(pc, info)
        except RuntimeError:
            # 窗口已关闭
            pass
        except Exception as e:
            logger.debug(f"属性面板刷新失败: {e}")

    def _update_rows(self, pc, info):
        tr = self.window.language_manager.tr
        na = tr('properties_value_absent', '—')
        self._absent_mark = na
        self._set_hint(tr('properties_na_hint', '「—」表示当前源未提供该项，数值每秒刷新'))

        duration_ms = self._total_time(pc)
        position_ms = self._current_time(pc)

        # ---- 播放信息 ----
        w = info.get('width', 0) or 0
        h = info.get('height', 0) or 0
        resolution = f"{w}x{h}" if w > 0 and h > 0 else na
        self._set('resolution', resolution)

        aspect = self._fmt_ratio(info.get('aspect_ratio', ''))
        self._set('aspect', aspect or na)

        interlaced = (self._read_string(pc, 'video-frame-info/interlaced') or '').lower()
        if interlaced == 'yes':
            self._set('scan_mode', tr('properties_scan_interlaced', '隔行'))
        elif interlaced == 'no':
            self._set('scan_mode', tr('properties_scan_progressive', '逐行'))
        else:
            self._set('scan_mode', na)

        rotate = info.get('video_rotate', 0) or 0
        self._set('rotation', f"{int(rotate)}°")

        if duration_ms > 0:
            self._set('duration', self._fmt_duration(duration_ms) or na)
        else:
            self._set('duration', tr('properties_live', '直播'))
        self._set('position', self._fmt_duration(position_ms) or na)
        if duration_ms > 0 and position_ms >= 0:
            percent = max(0, min(100, round(position_ms / duration_ms * 100)))
            self._set('progress', f"{percent}%")
            self._set_progress(percent)
        else:
            self._set('progress', tr('properties_live', '直播'))
            self._set_progress(0)

        # ---- 视频 ----
        vcodec = info.get('video_codec', '') or info.get('video_format', '') or ''
        self._set('video_codec', UIController.shorten_codec_name(vcodec) if vcodec else na)

        fps = info.get('fps', 0) or 0
        self._set('fps', f"{fps:.2f}" if fps > 0 else na)

        display_fps = self._display_fps(pc)
        self._set('display_fps', f"{display_fps:.0f} Hz" if display_fps > 0 else na)

        v_br = info.get('video_bitrate', 0) or 0
        self._set('video_bitrate', UIController.format_bitrate(v_br) if v_br > 0 else na)

        pixel_format = info.get('pixel_format', '') or ''
        self._set('pixel_format', pixel_format or na)
        self._set('bit_depth', self._bit_depth(pixel_format) or na)

        # mpv 没有 video-params/colorspace（读它恒失败），实际字段是 colormatrix
        color_space = (info.get('colormatrix', '') or '').lower()
        self._set('color_space', color_space.upper() if color_space else na)

        primaries = info.get('color_primaries', '') or ''
        self._set('color_primaries', primaries.upper() if primaries else na)

        gamma = (info.get('gamma', '') or '').lower()
        if not gamma:
            self._set('gamma', na)
        elif gamma == 'pq':
            self._set('gamma', 'PQ(HDR10)')
        elif gamma == 'hlg':
            self._set('gamma', 'HLG')
        else:
            self._set('gamma', gamma.upper())

        color_range = (info.get('colorlevels', '') or '').lower()
        if color_range == 'limited':
            self._set('color_range', 'Limited')
        elif color_range == 'full':
            self._set('color_range', 'Full')
        else:
            self._set('color_range', color_range.upper() if color_range else na)

        vo = info.get('egl_type', '') or self._read_string(pc, 'current-vo')
        self._set('vo', vo or na)

        gpu_api = info.get('current_gpu_api', '') or ''
        gpu_context = info.get('gpu_context', '') or ''
        self._set('gpu_api', gpu_api or na, tip=gpu_context or None)

        hwdec = info.get('hwdec', '') or ''
        if not hwdec:
            self._set('decode_mode', na)
        elif hwdec == 'no':
            self._set('decode_mode', tr('properties_hwdec_sw', '软解'))
        else:
            self._set('decode_mode',
                      tr('properties_hwdec_hw', '硬解({decoder})').format(decoder=hwdec))

        # ---- 音频 ----
        acodec = info.get('audio_codec', '') or info.get('audio_format', '') or ''
        self._set('audio_codec', UIController.shorten_codec_name(acodec) if acodec else na)
        a_br = info.get('audio_bitrate', 0) or 0
        self._set('audio_bitrate', UIController.format_bitrate(a_br) if a_br > 0 else na)

        sample_rate = info.get('sample_rate', 0) or 0
        self._set('sample_rate', f"{sample_rate / 1000:.1f} kHz" if sample_rate > 0 else na)

        self._set('channels', self._format_channels(info, tr, na))
        self._set('audio_format', self._audio_format(self._read_string(pc, 'audio-params/format')) or na)

        # ---- 网络与性能 ----
        self._set('protocol', self._protocol(pc, tr) or na)
        container = info.get('container', '') or ''
        self._set('container', UIController.canonical_stream_token(container) if container else na)

        cache_dur = self._read_double(pc, 'demuxer-cache-duration')
        if cache_dur <= 0:
            cache_dur = self._read_double(pc, 'demuxer-cache-time')
        self._set('cache_duration', f"{cache_dur:.2f} s" if cache_dur > 0 else na)

        cache_size = self._cache_size_bytes(pc)
        self._set('cache_size', UIController.format_bytes(cache_size) if cache_size > 0 else na)

        cache_speed = info.get('cache_speed', 0) or 0
        self._set('cache_speed',
                  UIController.format_bytes_per_second(cache_speed) if cache_speed > 0 else na)

        buffering = self._read_int(pc, 'cache-buffering-state')
        self._set('buffering', f"{buffering}%" if buffering > 0 else na)

        first_frame = info.get('first_frame_ms', 0) or 0
        self._set('first_frame', f"{int(first_frame)} ms" if first_frame > 0 else na)

        av_sync = self._read_double_opt(pc, 'total-avsync-change')
        self._set('av_sync', f"{av_sync * 1000:.0f} ms" if av_sync is not None else na)

        dropped = info.get('decoder_frame_drop_count', 0) or 0
        self._set('dropped_frames', f"{dropped}")
        render_drops = info.get('frame_drop_count', 0) or 0
        self._set('render_drops', f"{render_drops}")

        render_fps = info.get('video_fps', 0) or 0
        if render_fps <= 0:
            render_fps = fps
        self._set('render_fps', f"{render_fps:.1f}" if render_fps > 0 else na)

        track_count = self._read_int(pc, 'track-list/count')
        self._set('track_count', str(track_count) if track_count > 0 else na)

        service_name = (self._read_string(pc, 'metadata/by-key/service_name')
                        or self._read_string(pc, 'metadata/by-key/ServiceName'))
        self._set('service_name', service_name or na)
        service_provider = (self._read_string(pc, 'metadata/by-key/service_provider')
                            or self._read_string(pc, 'metadata/by-key/ServiceProvider'))
        self._set('service_provider', service_provider or na)

        media_title = self._read_string(pc, 'media-title')
        self._set('media_title', media_title or na)

        self._update_chips(tr, duration_ms, resolution, fps, hwdec, gamma)

    # ---------- 顶部状态徽章 ----------
    def _update_chips(self, tr, duration_ms, resolution, fps, hwdec, gamma):
        self._set_chip('mode', tr('properties_live', '直播') if duration_ms <= 0
                       else tr('properties_vod', '点播'))
        self._set_chip('resolution', resolution)
        self._set_chip('fps', f"{fps:.2f} fps" if fps > 0 else '—')
        if not hwdec:
            self._set_chip('hwdec', '—')
        elif hwdec == 'no':
            self._set_chip('hwdec', tr('properties_hwdec_sw', '软解'))
        else:
            self._set_chip('hwdec', tr('properties_hwdec_sw', '硬解'))
        if gamma == 'pq':
            self._set_chip('hdr', 'HDR10')
        elif gamma == 'hlg':
            self._set_chip('hdr', 'HLG')
        elif gamma:
            self._set_chip('hdr', 'SDR')
        else:
            self._set_chip('hdr', '—')

    def _set_chip(self, key, text):
        chip = self._chips.get(key)
        if chip is not None:
            try:
                chip.set_full_text(text)
            except RuntimeError:
                pass

    def _set_progress(self, percent: int):
        try:
            self._progress.set_percent(percent)
        except RuntimeError:
            pass

    # ---------- 取值辅助 ----------
    @staticmethod
    def _fmt_ratio(text) -> str:
        try:
            value = float(text)
        except (TypeError, ValueError):
            return ''
        if value <= 0:
            return ''
        for target, label in ((16 / 9, '16:9'), (4 / 3, '4:3'), (3 / 2, '3:2'),
                              (2.35, '2.35:1'), (1.85, '1.85:1')):
            if abs(value - target) < 0.03:
                return label
        return f"{value:.2f}:1"

    @staticmethod
    def _bit_depth(pixel_format: str) -> str:
        p = (pixel_format or '').lower()
        if not p:
            return ''
        if any(k in p for k in ('p016', '16le', '16be')):
            return '16-bit'
        if any(k in p for k in ('p012', '12le', '12be')):
            return '12-bit'
        if any(k in p for k in ('p010', 'p10', '10le', '10be')):
            return '10-bit'
        if p.startswith(('d3d11', 'cuda', 'videotoolbox', 'vaapi', 'mediacodec', 'vdpau')):
            return ''
        return '8-bit'

    @staticmethod
    def _audio_format(sample_format: str) -> str:
        fmt = (sample_format or '').lower()
        names = {
            'floatp': '32-bit float', 'fltp': '32-bit float', 'flt': '32-bit float',
            'float': '32-bit float', 'dblp': '64-bit float', 'dbl': '64-bit float',
            's16': '16-bit', 's16p': '16-bit', 's32': '32-bit', 's32p': '32-bit',
            'u8': '8-bit', 'u8p': '8-bit',
        }
        return names.get(fmt, fmt.upper() if fmt else '')

    def _display_fps(self, pc) -> float:
        for prop in ('display-fps', 'current-display-fps'):
            value = self._read_double_opt(pc, prop)
            if value and value > 0:
                return value
        try:
            screen = self.screen() or QApplication.primaryScreen()
            return float(screen.refreshRate()) if screen else 0.0
        except Exception:
            return 0.0

    def _protocol(self, pc, tr) -> str:
        source = self._read_string(pc, 'stream-open-filename')
        if not source:
            return ''
        if '://' in source:
            return source.split('://', 1)[0].upper()
        if re.match(r'^[A-Za-z]:[\\/]', source) or source.startswith(('/', '\\\\')):
            return tr('properties_protocol_local', '本地文件')
        return ''

    def _cache_size_bytes(self, pc) -> float:
        raw = self._read_string(pc, 'demuxer-cache-state')
        if not raw:
            return 0.0
        try:
            value = (json.loads(raw) or {}).get('total-bytes') or 0
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _format_channels(self, info, tr, na) -> str:
        layout = (info.get('audio_layout', '') or '').lower()
        if layout == 'stereo':
            return tr('properties_channel_stereo', '立体声')
        if layout == 'mono':
            return tr('properties_channel_mono', '单声道')
        if layout:
            return layout
        channels = info.get('audio_channels', 0) or 0
        return f"{channels} ch" if channels > 0 else na

    def _set(self, key: str, value: str, tip: str = None):
        lbl = self._labels.get(key)
        if not lbl:
            return
        try:
            # 缺失项用弱化颜色，「—」不会在满屏数值里跳出来
            is_absent = (value == getattr(self, '_absent_mark', '—'))
            if getattr(lbl, '_absent_state', None) != is_absent:
                lbl._absent_state = is_absent
                lbl.setProperty('absent', is_absent)
                style = self.style()
                style.unpolish(lbl)
                style.polish(lbl)
            if isinstance(lbl, _ElidedValueLabel):
                lbl.set_full_text(value)
            else:
                lbl.setText(value)
            if tip:
                lbl.setToolTip(f"{value}\n{tip}")
        except RuntimeError:
            pass

    def _set_all_unavailable(self):
        tr = self.window.language_manager.tr
        absent = tr('properties_value_absent', '—')
        self._absent_mark = absent
        self._set_hint(tr('properties_no_media', '当前没有播放中的媒体'))
        for key in list(self._labels):
            if not key.endswith('__label'):
                self._set(key, absent)
        for chip in self._chips.values():
            try:
                chip.set_full_text(absent)
            except RuntimeError:
                pass
        self._set_progress(0)

    def _set_hint(self, text: str):
        try:
            self._hint.setText(text)
        except RuntimeError:
            pass

    @staticmethod
    def _current_time(pc) -> int:
        try:
            return int(pc.get_current_time() or 0)
        except Exception:
            return 0

    @staticmethod
    def _total_time(pc) -> int:
        try:
            return int(pc.get_total_time() or 0)
        except Exception:
            return 0

    @staticmethod
    def _fmt_duration(ms: int) -> str:
        if not ms or ms <= 0:
            return ''
        total = int(ms / 1000)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _read_string(self, pc, prop: str) -> str:
        try:
            if hasattr(pc, '_get_mpv_property_string'):
                return pc._get_mpv_property_string(prop) or ''
        except Exception as e:
            logger.debug(f"读取 mpv 属性 {prop} 失败: {e}")
        return ''

    def _read_double(self, pc, prop: str) -> float:
        value = self._read_double_opt(pc, prop)
        return float(value) if value is not None else 0.0

    def _read_double_opt(self, pc, prop: str):
        try:
            if hasattr(pc, '_get_mpv_property_double'):
                value = pc._get_mpv_property_double(prop)
                return float(value) if value is not None else None
        except Exception as e:
            logger.debug(f"读取 mpv 属性 {prop} 失败: {e}")
        return None

    def _read_int(self, pc, prop: str) -> int:
        try:
            if hasattr(pc, '_get_mpv_property_int'):
                value = pc._get_mpv_property_int(prop)
                if value is not None:
                    return int(value)
            raw = self._read_string(pc, prop)
            if raw:
                return int(float(raw))
        except Exception as e:
            logger.debug(f"读取 mpv 属性 {prop} 失败: {e}")
        return 0
