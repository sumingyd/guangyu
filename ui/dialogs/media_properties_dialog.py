"""媒体属性对话框。

对齐安卓分屏播放页右侧「信息」那一屏：播放信息 / 媒体信息 / 网络与性能三块。
数据全部来自 mpv，PC 端取不到的项如实显示「不可用」，不做推断、不写死假值。

数据源：
- MpvPlayerController.get_live_media_info()（每秒刷新一次的扁平字典）
- 少量 mpv 属性直接读取（display-fps / total-avsync-change / metadata 等）
"""
import math

from PySide6.QtCore import Qt, QTimer
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

    def __init__(self, text: str = '--'):
        super().__init__()
        self._full_text = ''
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
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


class MediaPropertiesDialog(FloatingDialog):
    """媒体属性（实时刷新，每秒一次）"""

    REFRESH_MS = 1000

    # 分组：(分组标题 key, 默认标题, [(字段 key, 标签 key, 默认标签), ...])
    PLAYBACK_ROWS = [
        ('resolution', 'stream_quality_resolution', '分辨率'),
        ('duration', 'properties_duration', '时长'),
        ('position', 'properties_position', '当前位置'),
        ('progress', 'properties_progress', '进度'),
    ]
    MEDIA_ROWS = [
        ('video_codec', 'properties_video_codec', '视频编码'),
        ('audio_codec', 'properties_audio_codec', '音频编码'),
        ('fps', 'stream_quality_fps', '帧率'),
        ('display_fps', 'properties_display_fps', '屏幕刷新'),
        ('video_bitrate', 'stream_quality_video_bitrate', '视频码率'),
        ('audio_bitrate', 'stream_quality_audio_bitrate', '音频码率'),
        ('cache_duration', 'stream_quality_cache_duration', '缓存时长'),
        ('av_sync', 'properties_av_sync', '音画偏移'),
        ('container', 'stream_quality_container', '封装格式'),
        ('decode_mode', 'properties_decode_mode', '解码方式'),
        ('vo', 'stream_quality_vo', '视频输出'),
        ('pixel_format', 'stream_quality_pixel_format', '像素格式'),
        ('color_space', 'properties_color_space', '色彩空间'),
        ('color_primaries', 'stream_quality_primaries', '色彩原色'),
        ('gamma', 'stream_quality_gamma', '传输特性'),
        ('color_range', 'properties_color_range', '色彩范围'),
        ('sample_rate', 'stream_quality_sample_rate', '采样率'),
        ('channels', 'stream_quality_audio_channels', '声道数'),
        ('service_name', 'properties_service_name', '电视台'),
        ('service_provider', 'properties_service_provider', '运营商'),
        ('track_count', 'properties_track_count', '轨道数'),
    ]
    NETWORK_ROWS = [
        ('dropped_frames', 'stream_quality_decoder_drop', '解码器丢帧'),
        ('render_fps', 'properties_actual_fps', '实际帧率'),
        ('cache_speed', 'stream_quality_cache_speed', '缓存速度'),
        ('media_title', 'properties_media_title', '流标题'),
    ]

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('properties_title', '属性'))
        self._labels = {}
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

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        label_color = c.get('mid')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                margin-top: 8px; padding: 4px 6px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
                color: {c.get('accent')};
                font-weight: 600;
            }}
            QScrollArea {{ background: transparent; border: none; }}
        """)
        for key, lbl in self._labels.items():
            if key.endswith('__label'):
                lbl.setStyleSheet(f"color: {label_color};")
            else:
                lbl.setStyleSheet(f"color: {text_color}; font-weight: 500;")

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll = scroll

        content = QWidget()
        self._content = content

        # 用带对话框样式的探针标签取真实字体度量：QSS 里 QLabel 固定 12px，
        # 直接读 self.fontMetrics() 会跟随系统字号把列宽算大。
        probe = QLabel('--', self)
        probe.ensurePolished()
        self._fm = probe.fontMetrics()
        probe.deleteLater()

        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)

        # 左列：播放信息 + 网络与性能（各 4 行），右列：媒体信息（21 项分两列排布）
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_col.addWidget(self._build_group(
            tr('properties_group_playback', '播放信息'),
            [(key, tr(label_key, label_default)) for key, label_key, label_default in self.PLAYBACK_ROWS],
            columns=1,
        ))
        left_col.addWidget(self._build_group(
            tr('properties_group_network', '网络与性能'),
            [(key, tr(label_key, label_default)) for key, label_key, label_default in self.NETWORK_ROWS],
            columns=1,
        ))
        left_col.addStretch(1)

        grid.addLayout(left_col, 0, 0)
        grid.addWidget(self._build_group(
            tr('properties_group_media', '媒体信息'),
            [(key, tr(label_key, label_default)) for key, label_key, label_default in self.MEDIA_ROWS],
            columns=2,
        ), 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)

        content.adjustSize()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        self._btn_row = btn_row
        btn_row.addStretch()
        close_btn = QPushButton(tr('close', '关闭'))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_group(self, title, rows, columns=1):
        """按固定行高/列宽构建分组，columns>1 时按列优先填充。"""
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(8, 4, 8, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        fm = self._fm
        label_w = max(fm.horizontalAdvance(text) for _, text in rows) + 10
        row_h = fm.height() + 4
        # 数值列宽按最长的常见值预留（如「硬解(mediacodec-copy)」），封顶避免极端字体把窗口撑宽；
        # 真正超长的自由文本（流标题/电视台/运营商）在单元格内省略并保留完整 tooltip。
        value_min = min(150, max(96, fm.horizontalAdvance('硬解(mediacodec-copy)') + 8))
        per_col = math.ceil(len(rows) / max(1, columns))

        for idx, (key, label_text) in enumerate(rows):
            row, col = idx % per_col, idx // per_col
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setFixedSize(label_w, row_h)
            value = _ElidedValueLabel('--')
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
            btn_h = self._btn_row.sizeHint().height() if self._btn_row else 0
            width = content_w + margins.left() + margins.right() + 4
            height = content_h + margins.top() + margins.bottom() + btn_h + spacing + 4
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                width = min(width, max(480, avail.width() - 24))
                height = min(height, max(320, avail.height() - 64))
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
        na = tr('properties_unavailable', '不可用')

        # ---- 播放信息 ----
        w = info.get('width', 0) or 0
        h = info.get('height', 0) or 0
        self._set('resolution', f"{w}x{h}" if w > 0 and h > 0 else na)

        duration_ms = self._total_time(pc)
        position_ms = self._current_time(pc)
        self._set('duration', self._fmt_duration(duration_ms) or na)
        self._set('position', self._fmt_duration(position_ms) or na)
        if duration_ms > 0 and position_ms >= 0:
            self._set('progress', f"{position_ms / duration_ms * 100:.0f}%")
        else:
            self._set('progress', na)

        # ---- 媒体信息 ----
        vcodec = info.get('video_codec', '') or info.get('video_format', '') or ''
        self._set('video_codec', UIController.shorten_codec_name(vcodec) if vcodec else na)
        acodec = info.get('audio_codec', '') or info.get('audio_format', '') or ''
        self._set('audio_codec', UIController.shorten_codec_name(acodec) if acodec else na)

        fps = info.get('fps', 0) or 0
        self._set('fps', f"{fps:.2f}" if fps > 0 else na)

        display_fps = self._read_double(pc, 'display-fps')
        self._set('display_fps', f"{display_fps:.1f}" if display_fps > 0 else na)

        v_br = info.get('video_bitrate', 0) or 0
        self._set('video_bitrate', UIController.format_bitrate(v_br) if v_br > 0 else na)
        a_br = info.get('audio_bitrate', 0) or 0
        self._set('audio_bitrate', UIController.format_bitrate(a_br) if a_br > 0 else na)

        cache_dur = self._read_double(pc, 'demuxer-cache-duration')
        if cache_dur <= 0:
            cache_dur = self._read_double(pc, 'demuxer-cache-time')
        self._set('cache_duration', f"{cache_dur:.2f} s" if cache_dur > 0 else na)

        av_sync = self._read_double(pc, 'total-avsync-change')
        self._set('av_sync', f"{av_sync * 1000:.0f} ms" if av_sync else na)

        container = info.get('container', '') or ''
        self._set('container', UIController.canonical_stream_token(container) if container else na)

        hwdec = info.get('hwdec', '') or ''
        if not hwdec:
            self._set('decode_mode', na)
        elif hwdec == 'no':
            self._set('decode_mode', tr('properties_hwdec_sw', '软解'))
        else:
            self._set('decode_mode',
                      tr('properties_hwdec_hw', '硬解({decoder})').format(decoder=hwdec))

        vo = info.get('egl_type', '') or self._read_string(pc, 'current-vo')
        self._set('vo', vo or na)

        pixel_format = info.get('pixel_format', '') or ''
        self._set('pixel_format', pixel_format or na)

        color_space = self._read_string(pc, 'video-params/colorspace')
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

        sample_rate = info.get('sample_rate', 0) or 0
        self._set('sample_rate', f"{sample_rate / 1000:.1f} kHz" if sample_rate > 0 else na)

        self._set('channels', self._format_channels(info, tr, na))

        service_name = self._read_string(pc, 'metadata/by-key/service_name')
        self._set('service_name', service_name or na)
        service_provider = self._read_string(pc, 'metadata/by-key/service_provider')
        self._set('service_provider', service_provider or na)

        track_count = self._read_int(pc, 'track-list/count')
        self._set('track_count', str(track_count) if track_count > 0 else na)

        # ---- 网络与性能 ----
        dropped = info.get('decoder_frame_drop_count', 0) or 0
        self._set('dropped_frames', f"{dropped}")

        render_fps = info.get('video_fps', 0) or 0
        self._set('render_fps', f"{render_fps:.1f}" if render_fps > 0 else na)

        cache_speed = info.get('cache_speed', 0) or 0
        self._set('cache_speed',
                  UIController.format_bytes_per_second(cache_speed) if cache_speed > 0 else na)

        media_title = self._read_string(pc, 'media-title')
        self._set('media_title', media_title or na)

    # ---------- 辅助 ----------
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

    def _set(self, key: str, value: str):
        lbl = self._labels.get(key)
        if lbl:
            try:
                if isinstance(lbl, _ElidedValueLabel):
                    lbl.set_full_text(value)
                else:
                    lbl.setText(value)
            except RuntimeError:
                pass

    def _set_all_unavailable(self):
        tr = self.window.language_manager.tr
        na = tr('properties_unavailable', '不可用')
        for key, lbl in self._labels.items():
            if key.endswith('__label'):
                continue
            try:
                if isinstance(lbl, _ElidedValueLabel):
                    lbl.set_full_text(na)
                else:
                    lbl.setText(na)
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
        try:
            if hasattr(pc, '_get_mpv_property_double'):
                v = pc._get_mpv_property_double(prop)
                return float(v) if v is not None else 0.0
        except Exception as e:
            logger.debug(f"读取 mpv 属性 {prop} 失败: {e}")
        return 0.0

    def _read_int(self, pc, prop: str) -> int:
        try:
            if hasattr(pc, '_get_mpv_property_int'):
                v = pc._get_mpv_property_int(prop)
                return int(v) if v is not None else 0
        except Exception as e:
            logger.debug(f"读取 mpv 属性 {prop} 失败: {e}")
        return 0
