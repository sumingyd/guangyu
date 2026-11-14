"""流质量检测对话框 - 实时显示 mpv 流信息

与安卓端 StreamQualityPanel.kt + Web 端 stream_quality 面板对齐。
数据源：MpvPlayerController.get_live_media_info()（每秒刷新）。

显示分组：
- 视频：codec / 分辨率 / 显示分辨率 / 帧率 / 码率 / 像素格式 / 颜色空间 / HDR / 位深 / 宽高比
- 音频：codec / 声道 / 声道布局 / 采样率 / 码率 / 位深
- 网络与缓存：容器 / 协议 / 解复用器 / 缓存时长 / 缓存大小 / 缓存速度 / 缓冲状态 / 解复用码率
- 丢帧统计：VO 丢帧 / 解码器丢帧 / 误时帧 / VO 延迟帧
- 硬件与渲染：硬解 / 视频输出 / GPU API / GPU 上下文
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QGroupBox, QSizePolicy,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from controllers.ui_controller import UIController
from services.mpv_player_service import MpvPlayerController
from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class StreamQualityDialog(FloatingDialog):
    """流质量检测对话框（实时刷新，每秒一次）"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('stream_quality_title', '流质量检测'))
        self.setMinimumSize(640, 660)
        self._labels = {}
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 每秒刷新（与安卓端 StreamQualityPanel / Web 端 setInterval 1000ms 一致）
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
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
        value_color = c.get('window_text')
        label_color = c.get('mid')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                margin-top: 12px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
                color: {c.get('accent')};
                font-weight: 600;
            }}
        """)
        # 主题切换后重新设置标签颜色
        for key, lbl in self._labels.items():
            if key.endswith('__label'):
                lbl.setStyleSheet(f"color: {label_color};")
            else:
                lbl.setStyleSheet(f"color: {value_color}; font-weight: 500;")

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 视频信息 =====
        video_group = QGroupBox(tr('stream_quality_group_video', '视频'))
        vform = QFormLayout(video_group)
        self._add_rows(vform, [
            ('video_codec',        tr('stream_quality_video_codec',        '编解码器')),
            ('resolution',          tr('stream_quality_resolution',         '分辨率')),
            ('display_resolution',  tr('stream_quality_display_resolution', '显示分辨率')),
            ('fps',                 tr('stream_quality_fps',                '帧率')),
            ('video_bitrate',       tr('stream_quality_video_bitrate',      '视频码率')),
            ('pixel_format',        tr('stream_quality_pixel_format',       '像素格式')),
            ('colormatrix',         tr('stream_quality_colormatrix',        '色彩矩阵')),
            ('color_primaries',     tr('stream_quality_primaries',          '色彩原色')),
            ('gamma',               tr('stream_quality_gamma',              '传输特性')),
            ('hdr_type',            tr('stream_quality_hdr_type',           'HDR 类型')),
            ('video_depth',         tr('stream_quality_video_depth',        '视频位深')),
            ('aspect_ratio',        tr('stream_quality_aspect_ratio',       '宽高比')),
        ])
        layout.addWidget(video_group)

        # ===== 音频信息 =====
        audio_group = QGroupBox(tr('stream_quality_group_audio', '音频'))
        aform = QFormLayout(audio_group)
        self._add_rows(aform, [
            ('audio_codec',    tr('stream_quality_audio_codec',   '编解码器')),
            ('audio_channels', tr('stream_quality_audio_channels','声道数')),
            ('audio_layout',   tr('stream_quality_audio_layout',  '声道布局')),
            ('sample_rate',    tr('stream_quality_sample_rate',   '采样率')),
            ('audio_bitrate',  tr('stream_quality_audio_bitrate', '音频码率')),
            ('audio_depth',    tr('stream_quality_audio_depth',   '音频位深')),
        ])
        layout.addWidget(audio_group)

        # ===== 网络与缓存 =====
        net_group = QGroupBox(tr('stream_quality_group_network', '网络与缓存'))
        nform = QFormLayout(net_group)
        self._add_rows(nform, [
            ('container',        tr('stream_quality_container',       '容器格式')),
            ('protocol',         tr('stream_quality_protocol',        '协议')),
            ('demuxer',          tr('stream_quality_demuxer',         '解复用器')),
            ('cache_duration',   tr('stream_quality_cache_duration',  '缓存时长')),
            ('cache_size',       tr('stream_quality_cache_size',      '缓存大小')),
            ('cache_speed',      tr('stream_quality_cache_speed',     '缓存速度')),
            ('buffering',        tr('stream_quality_buffering',       '缓冲状态')),
            ('first_frame',      tr('stream_quality_first_frame',     '首帧耗时')),
            ('demuxer_bitrate',  tr('stream_quality_demuxer_bitrate', '解复用码率')),
        ])
        layout.addWidget(net_group)

        # ===== 丢帧统计 =====
        drop_group = QGroupBox(tr('stream_quality_group_drops', '丢帧统计'))
        dform = QFormLayout(drop_group)
        self._add_rows(dform, [
            ('vo_drop',           tr('stream_quality_vo_drop',           'VO 丢帧')),
            ('decoder_drop',      tr('stream_quality_decoder_drop',      '解码器丢帧')),
            ('mistimed_frame',    tr('stream_quality_mistimed_frame',    '误时帧')),
            ('vo_delay',          tr('stream_quality_vo_delay',          'VO 延迟帧')),
        ])
        layout.addWidget(drop_group)

        # ===== 硬件与渲染 =====
        hw_group = QGroupBox(tr('stream_quality_group_hw', '硬件与渲染'))
        hform = QFormLayout(hw_group)
        self._add_rows(hform, [
            ('hwdec',          tr('stream_quality_hwdec',          '硬解')),
            ('vo',             tr('stream_quality_vo',             '视频输出')),
            ('gpu_api',        tr('stream_quality_gpu_api',        'GPU API')),
            ('gpu_context',    tr('stream_quality_gpu_context',    'GPU 上下文')),
        ])
        layout.addWidget(hw_group)

        # ===== 关闭按钮 =====
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(tr('playback_queue_close', '关闭'))
        close_btn.clicked.connect(self.close)
        close_btn.setToolTip(tr('close_tooltip', '关闭'))
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _add_rows(self, form: QFormLayout, rows):
        """批量添加 label: value 行，value 标签存入 self._labels

        优化显示：
        - label 设置最小宽度，防止被压缩截断
        - value 启用 wordWrap，长文本自动换行
        - value 设置最小宽度，防止短文本列过窄
        - FormLayout 使用 ExpandingFieldsGrow，value 列随窗口扩展
        """
        # value 列随窗口扩展（默认 FieldsStayAtSizeHint 会限制 value 列宽度）
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)  # label 与 value 之间的水平间距
        form.setVerticalSpacing(6)     # 行间距
        form.setContentsMargins(8, 4, 8, 4)

        c = AppStyles._get_colors()
        label_color = c.get('mid')
        value_color = c.get('window_text')
        # label 列最小宽度：取所有 label 文本估算宽度的最大值
        # 中文每字约 12px，英文每字符约 7px，4 字 label 约 48px + padding
        label_min_width = 72
        for key, label_text in rows:
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {label_color};")
            label.setMinimumWidth(label_min_width)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value = QLabel('--')
            value.setStyleSheet(f"color: {value_color}; font-weight: 500;")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)  # 长文本自动换行，防止被截断
            value.setMinimumWidth(180)
            value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            form.addRow(label, value)
            self._labels[key + '__label'] = label
            self._labels[key] = value

    # ---------- 实时刷新 ----------
    def _refresh(self):
        try:
            pc = self.window.player_controller
            if not pc or not hasattr(pc, 'get_live_media_info'):
                self._set_all_placeholder()
                return
            try:
                info = pc.get_live_media_info()
            except Exception as e:
                logger.debug(f"get_live_media_info 失败: {e}")
                info = None
            if not info:
                self._set_all_placeholder()
                return

            # 视频
            vcodec = info.get('video_codec', '') or info.get('video_format', '')
            self._set('video_codec', UIController.shorten_codec_name(vcodec) if vcodec else 'N/A')
            w = info.get('width', 0) or 0
            h = info.get('height', 0) or 0
            self._set('resolution', f"{w}x{h}" if w > 0 and h > 0 else 'N/A')
            dw = info.get('dwidth', 0) or 0
            dh = info.get('dheight', 0) or 0
            self._set('display_resolution', f"{dw}x{dh}" if dw > 0 and dh > 0 else 'N/A')
            fps = info.get('fps', 0) or 0
            self._set('fps', f"{fps:.2f} fps" if fps > 0 else 'N/A')
            v_br = info.get('video_bitrate', 0) or 0
            self._set('video_bitrate', UIController.format_bitrate(v_br) if v_br > 0 else 'N/A')
            self._set('pixel_format', info.get('pixel_format', '') or 'N/A')
            self._set('colormatrix', info.get('colormatrix', '') or 'N/A')
            self._set('color_primaries', info.get('color_primaries', '') or 'N/A')
            gamma = info.get('gamma', '') or ''
            self._set('gamma', gamma or 'N/A')
            hdr_type = MpvPlayerController.detect_hdr_type(
                info.get('colormatrix', ''),
                gamma,
                info.get('sig_peak', 0) or 0,
                info.get('video_format', '') or '',
                info.get('color_primaries', '') or ''
            )
            self._set('hdr_type', hdr_type or 'SDR')
            v_depth = info.get('video_depth', 0) or 0
            self._set('video_depth', f"{v_depth} bit" if v_depth > 0 else 'N/A')
            self._set('aspect_ratio', info.get('aspect_ratio', '') or 'N/A')

            # 音频
            acodec = info.get('audio_codec', '') or info.get('audio_format', '')
            self._set('audio_codec', UIController.shorten_codec_name(acodec) if acodec else 'N/A')
            ch = info.get('audio_channels', 0) or 0
            self._set('audio_channels', f"{ch} ch" if ch > 0 else 'N/A')
            self._set('audio_layout', info.get('audio_layout', '') or 'N/A')
            sr = info.get('sample_rate', 0) or 0
            self._set('sample_rate', f"{sr} Hz" if sr > 0 else 'N/A')
            a_br = info.get('audio_bitrate', 0) or 0
            self._set('audio_bitrate', UIController.format_bitrate(a_br) if a_br > 0 else 'N/A')
            a_depth = info.get('audio_depth', 0) or 0
            self._set('audio_depth', f"{a_depth} bit" if a_depth > 0 else 'N/A')

            # 网络与缓存
            self._set('container', info.get('container', '') or 'N/A')
            self._set('protocol', info.get('protocol', '') or 'N/A')
            self._set('demuxer', info.get('demuxer', '') or 'N/A')
            # 缓存时长：优先 demuxer-cache-duration，回退 demuxer-cache-time
            cache_dur = self._read_mpv_double(pc, 'demuxer-cache-duration')
            if cache_dur <= 0:
                cache_dur = self._read_mpv_double(pc, 'demuxer-cache-time')
            self._set('cache_duration', f"{cache_dur:.2f} s" if cache_dur > 0 else 'N/A')
            cache_size = info.get('cache_size', 0) or 0
            if cache_size <= 0:
                cache_size = self._read_mpv_double(pc, 'demuxer-cache-state/total-bytes')
            self._set('cache_size', UIController.format_bytes(cache_size) if cache_size > 0 else 'N/A')
            cache_speed = info.get('cache_speed', 0) or 0
            self._set('cache_speed',
                      UIController.format_bytes_per_second(cache_speed) if cache_speed > 0 else 'N/A')
            buf = info.get('buffering', 0) or 0
            tr = self.window.language_manager.tr
            self._set('buffering',
                      f"{buf}%" if buf > 0 else tr('stream_quality_no_buffer', '无缓冲'))
            demux_br = info.get('demuxer_bitrate', 0) or 0
            self._set('demuxer_bitrate', UIController.format_bitrate(demux_br) if demux_br > 0 else 'N/A')
            first_frame = info.get('first_frame_ms', 0) or 0
            self._set('first_frame', f"{first_frame}ms" if first_frame > 0 else 'N/A')

            # 丢帧统计
            self._set('vo_drop', str(info.get('frame_drop_count', 0) or 0))
            self._set('decoder_drop', str(info.get('decoder_frame_drop_count', 0) or 0))
            self._set('mistimed_frame', str(info.get('mistimed_frame_count', 0) or 0))
            vo_delay = info.get('vo_delay', 0) or 0
            self._set('vo_delay', f"{vo_delay:.0f}" if vo_delay > 0 else '0')

            # 硬件与渲染
            self._set('hwdec', info.get('hwdec', '') or 'off')
            self._set('vo', info.get('egl_type', '') or self._read_mpv_string(pc, 'vo') or 'N/A')
            self._set('gpu_api', info.get('current_gpu_api', '') or 'N/A')
            self._set('gpu_context', info.get('gpu_context', '') or 'N/A')
        except RuntimeError:
            # 窗口已关闭
            pass
        except Exception as e:
            logger.debug(f"流质量检测刷新失败: {e}")

    # ---------- 辅助 ----------
    def _set(self, key: str, value: str):
        lbl = self._labels.get(key)
        if lbl:
            try:
                lbl.setText(value)
            except RuntimeError:
                pass

    def _set_all_placeholder(self):
        for key, lbl in self._labels.items():
            if key.endswith('__label'):
                continue
            try:
                lbl.setText('--')
            except RuntimeError:
                pass

    def _read_mpv_string(self, pc, prop: str) -> str:
        """安全读取 mpv 字符串属性（pc 即 MpvPlayerController）"""
        try:
            if hasattr(pc, '_get_mpv_property_string'):
                return pc._get_mpv_property_string(prop) or ''
        except Exception as e:
            logger.debug(f"_read_mpv_string: {e}")
        return ''

    def _read_mpv_double(self, pc, prop: str) -> float:
        """安全读取 mpv 数值属性（pc 即 MpvPlayerController）"""
        try:
            if hasattr(pc, '_get_mpv_property_double'):
                v = pc._get_mpv_property_double(prop)
                return float(v) if v is not None else 0.0
        except Exception as e:
            logger.debug(f"_read_mpv_double: {e}")
        return 0.0

    # ---------- 生命周期 ----------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()
        self._refresh()

    def closeEvent(self, event):
        self._timer.stop()
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
