"""
设置和文件操作处理器 - 负责配置管理、文件打开/保存等
从 pyqt_player.py 提取的独立模块
"""

import os
import re


from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (

    QFileDialog,
    QMessageBox,
    QComboBox,
    QApplication,
    QCheckBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QListWidget,
    QWidget,
    QFormLayout,
    QTextEdit,
    QFrame,
    QTabWidget,
    QScrollArea,
)

from core.log_manager import global_logger as logger
from core.config_manager import ConfigManager
from core.subscription_manager import global_subscription_manager
from core.application_state import app_state
from ui.styles import AppStyles
from ui.floating_dialog import FloatingDialog
from ui.theme_manager import get_theme_manager
from utils.delay_constants import DelayMs
from core.version import CURRENT_VERSION
from services.m3u_parser import load_m3u_file
from controllers.main_window_protocol import MainWindowProtocol


class _EpgLoadThread(QThread):
    """EPG 数据加载线程（替代裸 daemon Thread，确保生命周期可管理）"""
    def run(self):
        try:
            global_subscription_manager.load_all_epg_data()
        except Exception as e:
            logger.error(f"EPG数据加载失败: {e}")


class _PlaylistReloadThread(QThread):
    """播放列表重新加载线程（网络下载 + M3U 解析，完成后通知主线程刷新 UI）"""
    reload_complete = Signal()
    reload_error = Signal(str)

    def __init__(self, window, url, source_index, parent=None):
        super().__init__(parent)
        self._window = window
        self._url = url
        self._source_index = source_index

    def run(self):
        try:
            self._window._handle_playlist_subscription(True, self._url, self._source_index)
            self.reload_complete.emit()
        except Exception as e:
            logger.error(f"重新加载播放列表失败: {e}")
            self.reload_error.emit(str(e))


# 使用说明默认内容 —— 定义在模块级别便于维护
DEFAULT_USAGE_CONTENT = (
    '## 基本操作\n\n'
    '### 1. 打开频道列表\n'
    '- 点击"文件"菜单 → "打开频道列表"（Ctrl+O）\n'
    '- 支持 M3U、M3U8、TXT 格式\n'
    '- 也可将文件直接拖放到主窗口打开\n\n'
    '### 2. 播放频道\n'
    '- 在频道列表中**双击**频道开始播放\n'
    '- 底部控制面板：▶ 播放 / ▮▮ 暂停 / ■ 停止\n'
    '- 音量滑块调节音量，点击图标静音/取消静音\n'
    '- 倍速按钮切换播放速度，比例按钮切换画面比例\n'
    '- 全屏按钮或 F11 进入全屏\n'
    '- **↑ ↓** 键切换频道，**← →** 键快退/快进，**滚轮** 调整音量\n\n'
    '### 3. EPG 电子节目单\n'
    '- 左侧面板显示当前频道节目安排\n'
    '- 点击 ◀ / ▶ 切换日期查看节目\n'
    '- 进度条实时显示当前节目播放进度\n'
    '- 支持配置 EPG 数据源自动订阅更新\n'
    '- M3U 文件头中的 EPG 地址会自动加载\n\n'
    '### 4. 扫描整理\n'
    '- 工具菜单 → 扫描整理\n'
    '- 输入 IP 范围或流地址\n'
    '- 设置超时时间和线程数，支持追加扫描和重试\n'
    '- **搜索过滤**：输入框实时过滤频道名/URL/分组（Ctrl+F）\n'
    '- **右键菜单**：全选/反选/选有效/选无效/批量删除\n'
    '- 扫描完成后可使用**批量操作**：自动分类、清理名称、匹配台标\n'
    '- **Ctrl+S** 保存，**Ctrl+A** 全选，**Delete** 删除选中\n'
    '- 导出时可选择仅导出选中频道\n\n'
    '### 5. 验证频道\n'
    '- 批量检测频道有效性，显示延迟、分辨率等参数\n'
    '- 支持智能重试失败的项\n\n'
    '## 高级功能\n\n'
    '### 订阅设置\n'
    '- 工具菜单 → 订阅设置\n'
    '- 配置多个订阅源和 EPG 数据源\n\n'
    '### 频道映射\n'
    '- 工具菜单 → 频道映射管理器\n\n'
    '### 界面定制\n'
    '- **主题切换**：5 种主题即时切换\n'
    '- **语言切换**：中文 / English\n'
    '- E / L / M / Y 快捷键控制面板\n'
    '- Tab 切换 OSD 信息遮罩\n'
    '- F5 刷新界面，F11 全屏，Ctrl+Q 退出\n\n'
    '### 时移/回看\n'
    '- 支持多种回看类型：default / append / shift / flussonic / xc\n'
    '- 时间变量替换支持自定义格式和时区偏移\n'
)


class SettingsFileOperations:
    """设置和文件操作 - 管理配置和文件I/O"""

    def __init__(self, main_window: MainWindowProtocol):
        self.window: MainWindowProtocol = main_window

    def _tr(self, key, default=None):
        w = self.window
        if w and w.language_manager:
            return w.language_manager.tr(key, default or key)
        return default or key

    # ==================== 文件操作 ====================

    def open_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.window,
            self._tr("open_playlist", "Open Channel List"),
            "",
            "M3U Files (*.m3u *.m3u8);;Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self._load_playlist_file(file_path)

    def open_specific_file(self, file_path: str):
        if file_path and os.path.isfile(file_path):
            self._load_playlist_file(file_path)

    def save_as(self):
        tab = self.window.playlist_tab
        if tab and tab.currentIndex() == 1:
            channels = self.window._local_channels
        else:
            channels = self.window._sub_channels
        if not channels:
            QMessageBox.warning(
                self.window,
                self._tr("warning", "Warning"),
                self._tr("no_channels_to_save", "No channels to save")
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.window,
            self._tr("save_as", "Save As"),
            "",
            "M3U Files (*.m3u);;Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self._save_playlist_file(file_path)

    # ==================== 设置对话框 ====================

    def player_settings(self):
        dialog = self._create_settings_dialog()
        tr = self._tr

        playback_settings = self.window.config.load_playback_settings() if self.window.config else {}

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 使用 Tab 分页，避免单页内容过长
        tab_widget = QTabWidget()
        tab_widget.setObjectName("settings_tab_widget")

        # ===== Tab 1：播放设置（回放协议 + 关闭行为，可滚动）=====
        playback_tab = QWidget()
        playback_tab_layout = QVBoxLayout(playback_tab)
        playback_tab_layout.setContentsMargins(0, 0, 0, 0)

        playback_content = QWidget()
        playback_content_layout = QVBoxLayout(playback_content)
        playback_content_layout.setContentsMargins(0, 0, 0, 0)
        playback_content_layout.addWidget(self._build_protocol_section(tr, playback_settings))
        playback_content_layout.addWidget(self._build_close_behavior_section(tr))
        playback_content_layout.addStretch()

        playback_scroll = QScrollArea()
        playback_scroll.setWidgetResizable(True)
        playback_scroll.setFrameShape(QFrame.Shape.NoFrame)
        playback_scroll.setWidget(playback_content)
        playback_tab_layout.addWidget(playback_scroll)

        tab_widget.addTab(playback_tab, tr("playback_settings_tab", "播放设置"))

        # ===== Tab 2：订阅源管理（播放列表 + EPG）=====
        subscription_tab = QWidget()
        subscription_tab_layout = QVBoxLayout(subscription_tab)
        subscription_tab_layout.setContentsMargins(0, 0, 0, 0)

        playlist_section = self._build_subscription_section(tr, 'playlist', playback=False)
        epg_section = self._build_subscription_section(tr, 'epg', playback=False)

        sub_layout = QHBoxLayout()
        sub_layout.setSpacing(8)
        sub_layout.addWidget(playlist_section['group'], 1)
        sub_layout.addWidget(epg_section['group'], 1)
        subscription_tab_layout.addLayout(sub_layout)

        tab_widget.addTab(subscription_tab, tr("subscription_sources_tab", "订阅源管理"))

        main_layout.addWidget(tab_widget, 1)

        self._connect_subscription_signals(playlist_section, epg_section)

        button_layout = QHBoxLayout()
        save_button = QPushButton(tr("save_button", "Save"))
        cancel_button = QPushButton(tr("cancel_button", "Cancel"))
        save_button.clicked.connect(lambda: self._save_and_close_settings(dialog))
        cancel_button.clicked.connect(dialog.close)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

        if self.window.subscription_ui_ctrl:
            self.window.subscription_ui_ctrl.load_subscription_sources_to_ui(
                pl_widget=playlist_section['list_widget'],
                epg_widget=epg_section['list_widget']
            )

        # exec 前的布局准备：加载订阅源后 QListWidget 尺寸提示变化，
        # 这里激活布局并设定窗口初始大小。
        # 分层窗口首次绘制时的文字重叠由 FloatingDialog.showEvent 中的
        # _fix_first_paint 负责（ensurePolished + invalidate/activate + resize 抖动）。
        dialog.layout().activate()
        dialog.adjustSize()
        dialog.resize(720, 500)

        if self.window._center_dialog_on_screen:
            self.window._center_dialog_on_screen(dialog)


        try:
            tm = get_theme_manager()
            tm.register_window(dialog)
        except Exception:
            tm = None
        dialog.exec()
        if tm:
            try:
                tm.unregister_window(dialog)
            except Exception as e:
                logger.debug(f"注销窗口失败: {e}")

    def _create_settings_dialog(self):
        try:
            dialog = FloatingDialog(self.window, stay_on_top=False)
        except TypeError:
            dialog = FloatingDialog(self.window)
        dialog.setWindowTitle(self._tr("subscription_settings_title", "Subscription Settings"))
        dialog.setMinimumSize(680, 440)
        dialog.resize(720, 500)
        dialog.setStyleSheet(AppStyles.dialog_style())
        return dialog

    def _build_close_behavior_section(self, tr):
        group = QGroupBox(tr("close_behavior_settings", "关闭行为"))
        layout = QFormLayout()

        close_combo = QComboBox()
        close_combo.setObjectName("close_behavior_combo")
        close_combo.addItem(tr("close_behavior_ask", "每次询问"), "ask")
        close_combo.addItem(tr("close_minimize_tray", "最小化到托盘"), "minimize_tray")
        close_combo.addItem(tr("close_exit", "直接退出"), "exit")

        config = self.window.config
        if config:
            saved = config.load_close_behavior()
            if saved == 'minimize_tray':
                close_combo.setCurrentIndex(1)
            elif saved == 'exit':
                close_combo.setCurrentIndex(2)
            else:
                close_combo.setCurrentIndex(0)

        layout.addRow(tr("close_action_label", "关闭窗口时:"), close_combo)
        group.setLayout(layout)
        return group

    def _build_protocol_section(self, tr, playback_settings):
        group = QGroupBox(tr("protocol_settings", "Protocol Settings"))
        layout = QFormLayout()

        rtsp_transport_combo = QComboBox()
        rtsp_transport_combo.setObjectName("rtsp_transport_combo")
        for display, value in [("TCP", "tcp"), ("UDP", "udp"), ("LAVF", "lavf")]:
            rtsp_transport_combo.addItem(display, value)
        rtsp_value = playback_settings.get('rtsp_transport', 'tcp')
        for i in range(rtsp_transport_combo.count()):
            if rtsp_transport_combo.itemData(i) == rtsp_value:
                rtsp_transport_combo.setCurrentIndex(i)
                break
        layout.addRow(tr("rtsp_transport_colon", "RTSP Transport:"), rtsp_transport_combo)

        hwdec_combo = QComboBox()
        hwdec_combo.setObjectName("hwdec_combo")
        # 兼容旧配置：bool True→auto-copy，False→no；新配置直接用字符串
        hwdec_raw = playback_settings.get('hwdec', 'auto-copy')
        if isinstance(hwdec_raw, bool):
            hwdec_value = 'auto-copy' if hwdec_raw else 'no'
        else:
            hwdec_value = str(hwdec_raw) if hwdec_raw in ('auto', 'auto-copy', 'no') else 'auto-copy'
        hwdec_items = [
            (tr("hwdec_auto_copy", "HW Copy-back (filters)"), 'auto-copy'),
            (tr("hwdec_auto", "HW Native (fastest)"), 'auto'),
            (tr("hwdec_no", "Software"), 'no'),
        ]
        for display, value in hwdec_items:
            hwdec_combo.addItem(display, value)
        for i in range(hwdec_combo.count()):
            if hwdec_combo.itemData(i) == hwdec_value:
                hwdec_combo.setCurrentIndex(i)
                break
        layout.addRow(tr("hwdec_label", "Hardware Decoding"), hwdec_combo)

        tls_check = QCheckBox(tr("tls_verify_label", "TLS Verify"))
        tls_check.setObjectName("tls_check")
        tls_check.setChecked(playback_settings.get('tls_verify', False))
        layout.addRow(tls_check)

        timeout_combo = QComboBox()
        timeout_combo.setObjectName("network_timeout_combo")
        timeout_items = [
            (0, tr("auto_timeout", "Auto")),
            (5, "5s"), (10, "10s"), (15, "15s"), (20, "20s"),
            (30, "30s"), (45, "45s"), (60, "60s"), (90, "90s"), (120, "120s"),
        ]
        current_timeout = playback_settings.get('network_timeout_sec', 0)
        selected_idx = 0
        for i, (val, label) in enumerate(timeout_items):
            timeout_combo.addItem(label, val)
            if val == current_timeout:
                selected_idx = i
        timeout_combo.setCurrentIndex(selected_idx)
        layout.addRow(tr("network_timeout_colon", "Network Timeout:"), timeout_combo)

        passthrough_combo = QComboBox()
        passthrough_combo.setObjectName("audio_passthrough_combo")
        passthrough_items = [
            ('never', tr("passthrough_never", "Never (Decode)")),
            ('spdif_only', tr("passthrough_spdif", "SPDIF (AC3/EAC3/DTS)")),
            ('hd_codecs', tr("passthrough_hd", "HD Codecs (DTS-HD/TrueHD)")),
            ('lossless', tr("passthrough_lossless", "Lossless Only (FLAC/ALAC/TrueHD)")),
            ('all', tr("passthrough_all", "All Codecs")),
        ]
        current_passthrough = playback_settings.get('audio_passthrough', 'never')
        selected_pt_idx = 0
        for i, (val, label) in enumerate(passthrough_items):
            passthrough_combo.addItem(label, val)
            if val == current_passthrough:
                selected_pt_idx = i
        passthrough_combo.setCurrentIndex(selected_pt_idx)
        layout.addRow(tr("audio_passthrough_colon", "Audio Pass-through:"), passthrough_combo)

        hdr_combo = QComboBox()
        hdr_combo.setObjectName("hdr_output_mode_combo")
        hdr_items = [
            ('disable', tr("hdr_disable", "Disable (Force SDR Output)")),
            ('auto', tr("hdr_auto", "Auto (scRGB for Windows HDR)")),
            ('scrgb', tr("hdr_scrgb", "scRGB (Windows HDR ON)")),
            ('passthrough', tr("hdr_passthrough", "PQ Passthrough (Windows HDR OFF)")),
            ('tonemap', tr("hdr_tonemap", "Tone Map to SDR")),
        ]
        current_hdr = playback_settings.get('hdr_output_mode', 'disable')
        selected_hdr_idx = 0
        for i, (val, label) in enumerate(hdr_items):
            hdr_combo.addItem(label, val)
            if val == current_hdr:
                selected_hdr_idx = i
        hdr_combo.setCurrentIndex(selected_hdr_idx)
        layout.addRow(tr("hdr_output_mode_colon", "HDR Output:"), hdr_combo)

        # ---- 高级参数：视频输出 / 视频同步 / 丢帧策略 / 缓存 override ----
        # 这些参数原仅由播放器内部按 HDR 模式和流类型自动推导；PC 端开放给用户
        # 自定义。'auto' 保留原自动推导行为（推荐），手动选择会覆盖自动值。
        vo_combo = QComboBox()
        vo_combo.setObjectName("vo_combo")
        vo_items = [
            ('auto', tr("vo_auto", "Auto (Recommended - derive from HDR mode)")),
            ('gpu', tr("vo_gpu", "gpu (Default cross-platform VO)")),
            ('gpu-next', tr("vo_gpu_next", "gpu-next (Next-gen, HDR passthrough/scRGB)")),
            ('libmpv', tr("vo_libmpv", "libmpv (Render API, macOS default)")),
            ('direct3d', tr("vo_direct3d", "direct3d (Windows legacy VO)")),
        ]
        current_vo = str(playback_settings.get('vo', 'auto')).lower()
        selected_vo_idx = 0
        for i, (val, label) in enumerate(vo_items):
            vo_combo.addItem(label, val)
            if val == current_vo:
                selected_vo_idx = i
        vo_combo.setCurrentIndex(selected_vo_idx)
        self._add_form_row_with_desc(
            layout,
            tr("vo_label", "Video Output (vo):"),
            vo_combo,
            tr("vo_desc",
               "Selects the video output. 'Auto' derives vo from HDR mode (gpu/gpu-next). "
               "On macOS, vo is always forced to libmpv (mpv v0.41+ no longer supports wid embedding). "
               "gpu-next is required for HDR passthrough/scRGB on Windows.")
        )

        vsync_combo = QComboBox()
        vsync_combo.setObjectName("video_sync_combo")
        vsync_items = [
            ('audio', tr("vsync_audio", "audio (Default, sync to audio clock)")),
            ('display-resample', tr("vsync_display_resample", "display-resample (Resample audio to display)")),
            ('display-tempo', tr("vsync_display_tempo", "display-tempo (Tempo-scale audio)")),
            ('resample', tr("vsync_resample", "resample (Resample audio, may cause drift)")),
            ('display-desync', tr("vsync_display_desync", "display-desync (No sync, may drop/dup)")),
            ('desync', tr("vsync_desync", "desync (Completely asynchronous)")),
        ]
        current_vsync = str(playback_settings.get('video_sync', 'audio')).lower()
        selected_vsync_idx = 0
        for i, (val, label) in enumerate(vsync_items):
            vsync_combo.addItem(label, val)
            if val == current_vsync:
                selected_vsync_idx = i
        vsync_combo.setCurrentIndex(selected_vsync_idx)
        self._add_form_row_with_desc(
            layout,
            tr("video_sync_label", "Video Sync (video-sync):"),
            vsync_combo,
            tr("video_sync_desc",
               "A/V sync timing reference. 'audio' is the safest default. "
               "'display-resample'/'display-tempo' sync to display refresh rate (smoother but may pitch-shift audio).")
        )

        framedrop_combo = QComboBox()
        framedrop_combo.setObjectName("framedrop_combo")
        fd_items = [
            ('vo', tr("framedrop_vo", "vo (Default, drop when VO is slow)")),
            ('decoder', tr("framedrop_decoder", "decoder (Drop at decoder, lower CPU)")),
            ('insert', tr("framedrop_insert", "insert (Insert 1:1 frame, may stutter)")),
            ('none', tr("framedrop_none", "none (Never drop)")),
            ('never', tr("framedrop_never", "never (Alias of none)")),
        ]
        current_fd = str(playback_settings.get('framedrop', 'vo')).lower()
        selected_fd_idx = 0
        for i, (val, label) in enumerate(fd_items):
            framedrop_combo.addItem(label, val)
            if val == current_fd:
                selected_fd_idx = i
        framedrop_combo.setCurrentIndex(selected_fd_idx)
        self._add_form_row_with_desc(
            layout,
            tr("framedrop_label", "Framedrop (framedrop):"),
            framedrop_combo,
            tr("framedrop_desc",
               "Frame dropping strategy when video output falls behind. "
               "'vo' drops only at output stage (keeps decode quality). "
               "'decoder' drops earlier (saves CPU on weak machines).")
        )

        # 反交错：隔行扫描视频（有些频道有横纹）的反交错处理
        deinterlace_combo = QComboBox()
        deinterlace_combo.setObjectName("deinterlace_combo")
        di_items = [
            ('no', tr("deinterlace_no", "Off (No deinterlacing)")),
            ('auto', tr("deinterlace_auto", "Auto (Yadif, detect interlaced frames)")),
        ]
        current_di = str(playback_settings.get('deinterlace', 'no')).lower()
        if current_di == 'yes':
            current_di = 'auto'
        selected_di_idx = 0
        for i, (val, label) in enumerate(di_items):
            deinterlace_combo.addItem(label, val)
            if val == current_di:
                selected_di_idx = i
        deinterlace_combo.setCurrentIndex(selected_di_idx)
        self._add_form_row_with_desc(
            layout,
            tr("deinterlace_label", "Deinterlace:"),
            deinterlace_combo,
            tr("deinterlace_desc",
               "Deinterlacing for interlaced video (channels with horizontal lines/comb artifacts). "
               "'Auto' uses Yadif Bob mode (mode=1), 50i->50p, maintains original framerate for smooth motion. "
               "Requires copy-back hwdec or software decoding.")
        )

        # 缓存 override：留空或 0 表示保持播放器内部动态计算值（按流类型/HDR/分辨率自适应）
        cache_secs_edit = QLineEdit()
        cache_secs_edit.setObjectName("cache_secs_override_edit")
        cache_secs_edit.setPlaceholderText(
            tr("cache_secs_override_placeholder", "0 = auto (derived from stream type)")
        )
        cache_secs_val = playback_settings.get('cache_secs_override', 0)
        try:
            cache_secs_val = int(float(cache_secs_val))
        except (TypeError, ValueError):
            cache_secs_val = 0
        if cache_secs_val > 0:
            cache_secs_edit.setText(str(cache_secs_val))
        self._add_form_row_with_desc(
            layout,
            tr("cache_secs_override_label", "Cache Seconds (cache-secs):"),
            cache_secs_edit,
            tr("cache_secs_override_desc",
               "Overrides the demuxer cache duration in seconds. Leave 0 to keep "
               "the auto value (e.g. 3600s for live, 180s for Blu-ray, dynamically adjusted by resolution).")
        )

        demuxer_max_edit = QLineEdit()
        demuxer_max_edit.setObjectName("demuxer_max_bytes_override_edit")
        demuxer_max_edit.setPlaceholderText(
            tr("demuxer_max_bytes_override_placeholder", "0 = auto (MiB, derived from cache-secs)")
        )
        demuxer_max_val = playback_settings.get('demuxer_max_bytes_mib_override', 0)
        try:
            demuxer_max_val = int(float(demuxer_max_val))
        except (TypeError, ValueError):
            demuxer_max_val = 0
        if demuxer_max_val > 0:
            demuxer_max_edit.setText(str(demuxer_max_val))
        self._add_form_row_with_desc(
            layout,
            tr("demuxer_max_bytes_override_label", "Demuxer Max Bytes (MiB):"),
            demuxer_max_edit,
            tr("demuxer_max_bytes_override_desc",
               "Overrides the demuxer forward cache size in MiB. Leave 0 to keep "
               "the auto value (scales with cache-secs, capped at 4096MiB).")
        )

        readahead_edit = QLineEdit()
        readahead_edit.setObjectName("demuxer_readahead_secs_override_edit")
        readahead_edit.setPlaceholderText(
            tr("demuxer_readahead_secs_override_placeholder", "0 = auto (per stream type: HLS=120s, TS=300s, ...)")
        )
        readahead_val = playback_settings.get('demuxer_readahead_secs_override', 0)
        try:
            readahead_val = int(float(readahead_val))
        except (TypeError, ValueError):
            readahead_val = 0
        if readahead_val > 0:
            readahead_edit.setText(str(readahead_val))
        self._add_form_row_with_desc(
            layout,
            tr("demuxer_readahead_secs_override_label", "Demuxer Readahead (s):"),
            readahead_edit,
            tr("demuxer_readahead_secs_override_desc",
               "Overrides the demuxer readahead in seconds. Leave 0 to keep "
               "the auto value (120s for HLS/HTTP, 300s for TS, 30s for network drives, etc.).")
        )

        # probesize / analyzeduration 覆盖
        probesize_edit = QLineEdit()
        probesize_edit.setObjectName("probesize_override_edit")
        probesize_edit.setPlaceholderText(
            tr("probesize_override_placeholder", "0 = auto (5MB for live, 2MB for FCC, ...)")
        )
        probesize_val = playback_settings.get('probesize_override', 0)
        try:
            probesize_val = int(float(probesize_val))
        except (TypeError, ValueError):
            probesize_val = 0
        if probesize_val > 0:
            probesize_edit.setText(str(probesize_val))
        self._add_form_row_with_desc(
            layout,
            tr("probesize_override_label", "Probesize (bytes):"),
            probesize_edit,
            tr("probesize_override_desc",
               "Overrides the demuxer probe size in bytes. Leave 0 for auto "
               "(5MB for live streams, 2MB for FCC). Increase if streams "
               "fail to load with 'unspecified pixel format' warnings.")
        )

        analyzeduration_edit = QLineEdit()
        analyzeduration_edit.setObjectName("analyzeduration_override_edit")
        analyzeduration_edit.setPlaceholderText(
            tr("analyzeduration_override_placeholder", "0 = auto (5s for live, 2s for FCC, ...)")
        )
        analyzeduration_val = playback_settings.get('analyzeduration_override', 0)
        try:
            analyzeduration_val = float(analyzeduration_val)
        except (TypeError, ValueError):
            analyzeduration_val = 0
        if analyzeduration_val > 0:
            analyzeduration_edit.setText(str(analyzeduration_val))
        self._add_form_row_with_desc(
            layout,
            tr("analyzeduration_override_label", "Analyzeduration (seconds):"),
            analyzeduration_edit,
            tr("analyzeduration_override_desc",
               "Overrides the demuxer analysis duration in seconds. Leave 0 for auto "
               "(5s for live, 2s for FCC). Increase if streams take too long "
               "to load or fail with corrupt packet warnings.")
        )

        group.setLayout(layout)
        return group

    @staticmethod
    def _add_form_row_with_desc(layout, label_text, widget, desc_text):
        """在 QFormLayout 中添加一行：label + (widget + 灰色说明文字)。

        说明文字独立一行显示在 widget 下方，便于用户理解参数含义。
        """
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        v.addWidget(widget)
        desc = QLabel(desc_text)
        desc.setWordWrap(True)
        desc.setStyleSheet(AppStyles.description_text_style())
        v.addWidget(desc)
        layout.addRow(label_text, container)


    def _build_subscription_section(self, tr, source_type, playback=True):
        if source_type == 'playlist':
            title_key = "playlist_subscription"
            title_default = "Subscription Sources"
            sources_label_key = "playlist_sources"
            sources_label_default = "Subscription sources (click to activate):"
            list_obj_name = "__settings_playlist_list__"
            interval_obj_name = "playlist_interval_combo"
            config_section = 'PlaylistSources'
            url_placeholder_key = "enter_playlist_url"
            url_placeholder_default = "Enter subscription source URL"
            widget_prefix = 'playlist_'
        else:
            title_key = "epg_subscription"
            title_default = "EPG Subscription (all sources will be merged)"
            sources_label_key = "epg_sources"
            sources_label_default = "EPG Sources:"
            list_obj_name = "__settings_epg_list__"
            interval_obj_name = "epg_interval_combo"
            config_section = 'EPGSources'
            url_placeholder_key = "enter_epg_url"
            url_placeholder_default = "Enter EPG URL"
            widget_prefix = 'epg_'

        group = QGroupBox(tr(title_key, title_default))
        layout = QVBoxLayout()

        sources_label = QLabel(tr(sources_label_key, sources_label_default))
        list_widget = QListWidget()
        list_widget.setObjectName(list_obj_name)
        list_widget.setMaximumHeight(160)

        add_btn = QPushButton(tr("add_source", "+ Add Source"))
        remove_btn = QPushButton(tr("remove_source", "- Remove Selected"))

        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)

        new_url_edit = QLineEdit()
        new_url_edit.setPlaceholderText(tr(url_placeholder_key, url_placeholder_default))
        new_name_edit = QLineEdit()
        new_name_edit.setPlaceholderText(tr("enter_source_name", "Source name (optional)"))
        new_name_edit.setMaximumWidth(180)

        input_layout.addWidget(QLabel("URL:"))
        input_layout.addWidget(new_url_edit, 1)
        input_layout.addWidget(QLabel("Name:"))
        input_layout.addWidget(new_name_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()

        interval_label = QLabel(tr("update_interval_colon", "Update interval (minutes):"))
        interval_combo = QComboBox()
        interval_combo.setObjectName(interval_obj_name)
        interval_combo.addItems(["15", "30", "60", "120", "240", "480", "720"])

        if self.window.config and not playback:
            interval_value = self.window.config.get_value(config_section, 'update_interval', '60')
            idx = interval_combo.findText(interval_value)
            if idx >= 0:
                interval_combo.setCurrentIndex(idx)

        layout.addWidget(sources_label)
        layout.addWidget(list_widget)
        layout.addWidget(input_widget)
        layout.addLayout(btn_layout)
        if not playback:
            layout.addWidget(interval_label)
            layout.addWidget(interval_combo)

        group.setLayout(layout)

        self.window.__dict__[f'{widget_prefix}list_widget'] = list_widget
        self.window.__dict__[f'{widget_prefix}new_url_edit'] = new_url_edit
        self.window.__dict__[f'{widget_prefix}new_name_edit'] = new_name_edit
        self.window.__dict__[f'_{widget_prefix}add_btn'] = add_btn
        self.window.__dict__[f'_editing_{widget_prefix}index'] = -1

        return {
            'group': group,
            'list_widget': list_widget,
            'add_btn': add_btn,
            'remove_btn': remove_btn,
            'new_url_edit': new_url_edit,
            'new_name_edit': new_name_edit,
        }

    def _connect_subscription_signals(self, playlist_section, epg_section):
        ui = self.window.subscription_ui_ctrl
        if not ui:
            return

        playlist_section['add_btn'].clicked.connect(lambda: ui.add_or_update_playlist_source())
        playlist_section['remove_btn'].clicked.connect(lambda: ui.remove_selected_playlist_source())
        playlist_section['list_widget'].itemClicked.connect(lambda item: ui.activate_playlist_source(item))
        playlist_section['list_widget'].itemDoubleClicked.connect(lambda item: ui.edit_playlist_source(item))

        epg_section['add_btn'].clicked.connect(lambda: ui.add_or_update_epg_source())
        epg_section['remove_btn'].clicked.connect(lambda: ui.remove_selected_epg_source())
        epg_section['list_widget'].itemDoubleClicked.connect(lambda item: ui.edit_epg_source(item))

    # ==================== 保存与关闭 ====================

    def _save_and_close_settings(self, dialog):
        try:
            old_playlist = global_subscription_manager.get_playlist_sources()
            old_epg = global_subscription_manager.get_epg_sources()
            old_active_index = global_subscription_manager.get_active_playlist_source_index()

            new_playlist = self._extract_sources_from_ui('playlist')
            new_epg = self._extract_sources_from_ui('epg')
            new_playback = self._extract_playback_settings(dialog)

            if new_playlist:
                global_subscription_manager._config.save_playlist_sources(new_playlist)
            if new_epg:
                global_subscription_manager._config.save_epg_sources(new_epg)

            self._save_intervals(dialog)
            self._save_close_behavior(dialog)
            self._apply_playback_settings(new_playback)

            playlist_changed, new_active_index = self._check_playlist_changed(old_playlist, new_playlist, old_active_index)
            if playlist_changed:
                self._reload_playlist_async(new_playlist, new_active_index)

            if self._check_epg_changed(old_epg, new_epg):
                epg_thread = _EpgLoadThread(self.window)
                epg_thread.finished.connect(epg_thread.deleteLater)
                epg_thread.start()

            dialog.close()
        except Exception as e:
            logger.error(f"保存订阅设置失败: {e}")
            dialog.close()

    def _extract_sources_from_ui(self, source_type):
        widget = getattr(self.window, f'{source_type}_list_widget', None)
        if not widget:
            return []
        sources = []
        for i in range(widget.count()):
            item = widget.item(i)
            source_data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if source_data:
                if source_type == 'playlist':
                    source_data['enabled'] = item.checkState() == QtCore.Qt.CheckState.Checked
                sources.append(source_data)
        return sources

    def _extract_playback_settings(self, dialog):
        settings = {}
        combo = dialog.findChild(QComboBox, "rtsp_transport_combo")
        if combo:
            settings['rtsp_transport'] = combo.currentData() or combo.currentText().lower()
        combo = dialog.findChild(QComboBox, "hwdec_combo")
        if combo:
            settings['hwdec'] = combo.currentData() if combo.currentData() else 'auto-copy'
        check = dialog.findChild(QCheckBox, "tls_check")
        if check:
            settings['tls_verify'] = check.isChecked()
        combo = dialog.findChild(QComboBox, "network_timeout_combo")
        if combo:
            settings['network_timeout_sec'] = combo.currentData() if combo.currentData() is not None else 0
        combo = dialog.findChild(QComboBox, "audio_passthrough_combo")
        if combo:
            settings['audio_passthrough'] = combo.currentData() if combo.currentData() is not None else 'never'
        combo = dialog.findChild(QComboBox, "hdr_output_mode_combo")
        if combo:
            settings['hdr_output_mode'] = combo.currentData() if combo.currentData() is not None else 'disable'

        # 高级参数（vo / video-sync / framedrop / 缓存 override）
        combo = dialog.findChild(QComboBox, "vo_combo")
        if combo:
            settings['vo'] = combo.currentData() if combo.currentData() else 'auto'
        combo = dialog.findChild(QComboBox, "video_sync_combo")
        if combo:
            settings['video_sync'] = combo.currentData() if combo.currentData() else 'audio'
        combo = dialog.findChild(QComboBox, "framedrop_combo")
        if combo:
            settings['framedrop'] = combo.currentData() if combo.currentData() else 'vo'
        combo = dialog.findChild(QComboBox, "deinterlace_combo")
        if combo:
            settings['deinterlace'] = combo.currentData() if combo.currentData() else 'no'

        def _parse_positive_int(edit_name):
            edit = dialog.findChild(QLineEdit, edit_name)
            if not edit:
                return 0
            text = edit.text().strip()
            if not text:
                return 0
            try:
                v = int(float(text))
                return v if v > 0 else 0
            except (TypeError, ValueError):
                return 0

        settings['cache_secs_override'] = _parse_positive_int("cache_secs_override_edit")
        settings['demuxer_max_bytes_mib_override'] = _parse_positive_int("demuxer_max_bytes_override_edit")
        settings['demuxer_readahead_secs_override'] = _parse_positive_int("demuxer_readahead_secs_override_edit")
        settings['probesize_override'] = _parse_positive_int("probesize_override_edit")
        analyzeduration_edit = dialog.findChild(QLineEdit, "analyzeduration_override_edit")
        if analyzeduration_edit:
            text = analyzeduration_edit.text().strip()
            try:
                settings['analyzeduration_override'] = float(text) if text else 0
            except (TypeError, ValueError):
                settings['analyzeduration_override'] = 0
        else:
            settings['analyzeduration_override'] = 0
        return settings

    def _save_intervals(self, dialog):
        for prefix, section in [('playlist', 'PlaylistSources'), ('epg', 'EPGSources')]:
            combo = dialog.findChild(QComboBox, f"{prefix}_interval_combo")
            if combo and self.window.config:
                self.window.config.set_value(section, 'update_interval', combo.currentText())

    def _save_close_behavior(self, dialog):
        combo = dialog.findChild(QComboBox, "close_behavior_combo")
        if combo and self.window.config:
            action = combo.currentData()
            if action == 'ask':
                self.window.config.clear_close_behavior()
            else:
                self.window.config.save_close_behavior(action)

    def _apply_playback_settings(self, new_playback):
        if not new_playback or not self.window.config:
            return
        old_playback = self.window.config.load_playback_settings()
        self.window.config.save_playback_settings(new_playback)

        changed = any(old_playback.get(k) != v for k, v in new_playback.items())
        if changed and self.window.player_controller:
            try:
                pc = self.window.player_controller
                if pc and hasattr(pc, '_playback_settings'):
                    old_hdr = pc._playback_settings.get('hdr_output_mode', 'disable')
                    new_hdr = new_playback.get('hdr_output_mode', 'disable')
                    pc._playback_settings.update(new_playback)

                    # HDR 变化需要重新初始化 mpv（会中断当前播放并恢复）
                    if old_hdr != new_hdr and hasattr(pc, 'reinit_for_hdr_change'):
                        pc.reinit_for_hdr_change(new_hdr)
                        return

                    # 即时应用可运行时修改的参数（无需重启 mpv）
                    self._apply_runtime_playback_params(pc, old_playback, new_playback)
            except Exception as e:
                global_logger.debug(f"更新播放设置失败: {e}")

    @staticmethod
    def _apply_runtime_playback_params(pc, old_playback, new_playback):
        """即时应用可运行时修改的播放参数到 mpv。

        参数分类（基于 mpv 文档与项目代码）：
        - 运行时可改 property（framedrop/video-sync/hwdec/audio-passthrough）：
          直接 set_property_string 即时生效
        - 下次切台即生效（rtsp-transport/cache-secs/demuxer-*）：
          在 _setup_protocol_options 中每次播放时重新应用，无需此处处理
        - 必须重启 mpv 的 option（vo/tls-verify/network-timeout）：
          运行时改不生效，记录日志提示用户
        """
        if not hasattr(pc, 'set_property_string'):
            return

        # 运行时可改属性映射：(配置键, mpv属性名)
        runtime_props = [
            ('framedrop', 'framedrop'),
            ('video_sync', 'video-sync'),
            ('hwdec', 'hwdec'),
        ]
        for cfg_key, mpv_prop in runtime_props:
            old_val = old_playback.get(cfg_key)
            new_val = new_playback.get(cfg_key)
            if old_val == new_val or new_val is None:
                continue
            try:
                # hwdec 需要 bool 兼容处理（与 _ensure_mpv_initialized 一致）
                if cfg_key == 'hwdec':
                    if isinstance(new_val, bool):
                        new_val = 'auto-copy' if new_val else 'no'
                    else:
                        hwdec_str = str(new_val).lower()
                        if hwdec_str in ('auto', 'auto-copy', 'no'):
                            pass
                        elif hwdec_str in ('true', '1', 'yes'):
                            new_val = 'auto-copy'
                        else:
                            new_val = 'no'
                pc.set_property_string(mpv_prop, str(new_val))
            except Exception as e:
                global_logger.debug(f"即时应用 {mpv_prop}={new_val} 失败: {e}")

        # 反交错：使用 vf 滤镜（yadif=mode=1 bob）代替 deinterlace 属性，保持帧率不变
        old_di = old_playback.get('deinterlace', 'no')
        new_di = new_playback.get('deinterlace', 'no')
        if old_di != new_di:
            try:
                di_val = str(new_di).lower()
                if di_val in ('yes', 'auto'):
                    pc._enable_deinterlace_filter()
                else:
                    pc._disable_deinterlace_filter()
            except Exception as e:
                global_logger.debug(f"即时应用 deinterlace={new_di} 失败: {e}")

        # audio_passthrough 需要特殊处理（映射到 audio-spdif + audio-passthrough）
        old_pt = old_playback.get('audio_passthrough', 'never')
        new_pt = new_playback.get('audio_passthrough', 'never')
        if old_pt != new_pt:
            try:
                if new_pt and new_pt != 'never':
                    passthrough_map = {
                        'all': 'yes',
                        'hd_codecs': 'ac3,eac3,dts,dts-hd,truehd',
                        'lossless': 'flac,alac,truehd,dts-hd',
                        'spdif_only': 'ac3,eac3,dts',
                    }
                    pt_val = passthrough_map.get(new_pt, '')
                    if pt_val:
                        pc.set_property_string('audio-spdif', pt_val)
                        pc.set_property_string('audio-passthrough', pt_val)
                else:
                    pc.set_property_string('audio-spdif', '')
                    pc.set_property_string('audio-passthrough', '')
            except Exception as e:
                global_logger.debug(f"即时应用 audio-passthrough={new_pt} 失败: {e}")

        # 必须重启 mpv 的 option 变化记录日志（vo/tls-verify/network-timeout）
        restart_required_keys = ('vo', 'tls_verify', 'network_timeout_sec')
        for key in restart_required_keys:
            if old_playback.get(key) != new_playback.get(key):
                global_logger.info(
                    f"播放参数 {key} 已更改，将在下次重启播放器后完全生效"
                )
                break

    @staticmethod
    def _check_playlist_changed(old, new, old_active_index):
        if len(old) != len(new):
            return True, SettingsFileOperations._find_active_index(new)
        new_active_index = SettingsFileOperations._find_active_index(new)
        if old_active_index != new_active_index:
            return True, new_active_index
        for old_s, new_s in zip(old, new):
            if old_s.get('url') != new_s.get('url') or old_s.get('enabled') != new_s.get('enabled'):
                return True, new_active_index
        return False, old_active_index

    @staticmethod
    def _find_active_index(sources):
        for i, s in enumerate(sources):
            if s.get('enabled'):
                return i
        return 0 if sources else -1

    @staticmethod
    def _check_epg_changed(old, new):
        if len(old) != len(new):
            return True
        return any(old_s.get('url') != new_s.get('url') for old_s, new_s in zip(old, new))

    def _reload_playlist_async(self, new_sources, new_active_index):
        if new_active_index < 0 or new_active_index >= len(new_sources):
            return
        active = new_sources[new_active_index]

        thread = _PlaylistReloadThread(
            self.window, active.get('url', ''), new_active_index, self.window
        )
        thread.reload_complete.connect(self.window._do_on_playlist_updated_in_main_thread)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    # ==================== 语言 / 主题 ====================

    def set_language(self, language: str):
        try:
            self.window.language_manager.set_language(language)
            ConfigManager().save_language_settings(language)

            current_version = CURRENT_VERSION
            tr = self.window.language_manager.tr
            new_title = f"{tr('app_title', 'ISEP')} v{current_version}"
            self.window.setWindowTitle(new_title)
            if self.window._title_label:
                self.window._title_label.setText(new_title)

            if hasattr(self.window, 'setup_menu_bar'):
                self.window.setup_menu_bar()

            self.window.language_manager.update_ui_texts(self.window)

            if hasattr(self.window, 'status_bar_show_message'):
                self.window.status_bar_show_message(tr("language_changed", "Language changed"))
        except Exception as e:
            logger.error(f"切换语言失败: {e}")
            if hasattr(self.window, 'status_bar_show_message'):
                fallback = getattr(self.window.language_manager, 'tr', lambda x, y: x) if self.window.language_manager else lambda x, y: x
                self.window.status_bar_show_message(fallback("language_change_failed", "Failed"))

    def set_theme(self, theme: str):
        get_theme_manager().set_theme(theme)

    def set_color_mode(self, mode: str):
        get_theme_manager().set_color_mode(mode)

    def set_visual_style(self, style: str):
        get_theme_manager().set_visual_style(style)

    def _reapply_all_styles(self):
        w = self.window
        w.setStyleSheet(AppStyles.main_window_style())

        for attr, style_func in [
            ('_title_bar', AppStyles.title_bar_style),
            ('_title_label', AppStyles.title_label_style),
            ('_custom_menu_bar', AppStyles.player_menu_bar_style),
            ('central_widget', AppStyles.player_background_style),
            ('video_frame', AppStyles.player_background_style),
            ('video_placeholder', AppStyles.player_video_placeholder_style),
            ('status_bar', AppStyles.statusbar_style),
            ('toolbar', AppStyles.player_menu_bar_style),
        ]:
            widget = getattr(w, attr, None)
            if widget:
                widget.setStyleSheet(style_func())

        for dock_attr in ['epg_dock', 'playlist_dock', 'floating_dock']:
            panel = getattr(w, dock_attr, None)
            if panel:
                container = panel.widget()
                if container and hasattr(container, 'setStyleSheet'):
                    container.setStyleSheet(AppStyles.player_panel_style())
                panel.update()

        if hasattr(w, '_reapply_floating_panel_styles'):
            w._reapply_floating_panel_styles()
        if hasattr(w, '_reapply_side_panel_styles'):
            w._reapply_side_panel_styles()

        w.update()
        QApplication.processEvents()

    # ==================== 关于 / 使用说明 ====================

    def show_about(self):
        from ui.dialogs.about_dialog import AboutDialog
        AboutDialog(self.window).exec()

    def show_usage_instructions(self):
        dialog = FloatingDialog(self.window, stay_on_top=False)
        tr = self._tr
        colors = AppStyles._get_colors()

        dialog.setWindowTitle(tr("usage_instructions_title", "Usage Instructions"))
        dialog.setMinimumSize(520, 460)
        dialog.resize(620, 560)
        dialog.setStyleSheet(AppStyles.dialog_style())

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(16, 14, 16, 12)
        main_layout.setSpacing(8)

        header_label = QLabel(tr("usage_instructions_title", "Usage Instructions"))
        header_label.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {colors['accent']}; background-color: transparent; padding: 2px 0;"
        )
        main_layout.addWidget(header_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(AppStyles.separator_line_style())
        main_layout.addWidget(sep)

        text_edit = QTextEdit()
        usage_content = tr("usage_content", "") or DEFAULT_USAGE_CONTENT
        text_edit.setHtml(self._convert_markdown_to_html(usage_content))
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        text_edit.setWordWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setStyleSheet(AppStyles.text_edit_info_style())
        main_layout.addWidget(text_edit, 1)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton(tr("close_button", "Close"))
        close_btn.setFixedSize(72, 28)
        close_btn.setStyleSheet(AppStyles.button_style())
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        main_layout.addLayout(button_layout)

        if self.window._center_dialog_on_screen:
            self.window._center_dialog_on_screen(dialog)


        try:
            tm2 = get_theme_manager()
            tm2.register_window(dialog)
        except Exception:
            tm2 = None
        dialog.exec()
        if tm2:
            try:
                tm2.unregister_window(dialog)
            except Exception as e:
                logger.debug(f"注销窗口失败: {e}")

    @staticmethod
    def _convert_markdown_to_html(markdown):
        colors = AppStyles._get_colors()
        accent = colors['accent']
        text_color = colors['window_text']
        blocks = []
        current_list_items = []

        def flush_list():
            nonlocal current_list_items
            if current_list_items:
                items_html = ''.join(
                    f'<li>{item}</li>' for item in current_list_items
                )
                blocks.append(f'<ul>{items_html}</ul>')
                current_list_items = []

        for line in markdown.split('\n'):
            stripped = line.strip()
            if not stripped:
                flush_list()
                continue
            m = re.match(r'^## (.+)', stripped)
            if m:
                flush_list()
                blocks.append(f'<h2>{m.group(1)}</h2>')
                continue
            m = re.match(r'^### (.+)', stripped)
            if m:
                flush_list()
                blocks.append(f'<h3>{m.group(1)}</h3>')
                continue
            m = re.match(r'^- (.+)', stripped)
            if m:
                content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', m.group(1))
                current_list_items.append(content)
                continue
            content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', stripped)
            blocks.append(f'<p>{content}</p>')

        flush_list()

        body_html = '\n'.join(blocks)
        return f'''<html>
        <head>
            <style>
                body {{
                    font-family: {AppStyles._get_style_font_family()};
                    font-size: 13px;
                    line-height: 1.6;
                    color: {text_color};
                    background-color: transparent;
                    margin: 0;
                    padding: 0;
                }}
                h2 {{
                    color: {accent};
                    font-size: 14px;
                    font-weight: bold;
                    margin-top: 14px;
                    margin-bottom: 6px;
                    padding-bottom: 3px;
                    border-bottom: 1px solid {accent}40;
                }}
                h3 {{
                    color: {text_color};
                    font-size: 13px;
                    font-weight: bold;
                    margin-top: 8px;
                    margin-bottom: 4px;
                }}
                p {{
                    margin: 2px 0;
                }}
                ul {{
                    margin: 2px 0 2px 8px;
                    padding-left: 16px;
                }}
                li {{
                    margin: 1px 0;
                    line-height: 1.5;
                }}
                b {{
                    color: {text_color};
                }}
            </style>
        </head>
        <body>
            {body_html}
        </body>
        </html>'''

    # ==================== 窗口布局 ====================

    def save_window_layout(self):
        config = self.window.config or self.window.config_manager
        if not config:
            logger.warning("无法保存窗口布局：未找到配置管理器")
            return

        geometry = self.window.geometry()

        floating_settings: dict[str, object] = {
            'epg_visible': self.window.epg_visible,
            'playlist_visible': self.window.playlist_visible,
            'floating_visible': self.window.floating_panel_visible,
        }

        if self.window.epg_dock:
            floating_settings['epg_width'] = self.window.epg_dock.width()
        if self.window.playlist_dock:
            floating_settings['playlist_width'] = self.window.playlist_dock.width()
        if self.window.floating_dock:
            floating_settings['floating_width'] = self.window.floating_dock.width()

        config.save_window_layout(
            x=geometry.x(), y=geometry.y(),
            width=geometry.width(), height=geometry.height(),
            dividers=[]
        )
        config.save_ui_settings(floating_settings)

    # ==================== 内部文件 I/O ====================

    def _load_playlist_file(self, file_path: str):
        tr = self._tr
        try:
            content = load_m3u_file(file_path)

            if self.window.channel_model and self.window.channel_model.load_from_file(content):
                channels = self.window.channel_model.channels
            else:
                channels = []

            self.window._local_channels = list(channels)
            self.window._local_channels_dirty = True
            app_state.replace_channels(channels)

            if self.window.channel_model:
                self.window.channel_model._source_file_path = file_path

            if self.window.channel_model:
                epg_url = getattr(self.window.channel_model, '_last_header_attrs', {}).get('epg_url', '')
                if epg_url and not global_subscription_manager.get_epg_sources():
                    logger.info(f"本地文件头发现EPG地址，自动加载: {epg_url[:80]}")
                    try:
                        global_subscription_manager.load_single_epg(epg_url)
                        if hasattr(self.window, '_populate_epg_list') and callable(self.window._populate_epg_list):
                            QTimer.singleShot(DelayMs.OSD_FADE, self.window._populate_epg_list)
                    except Exception as epg_err:
                        logger.warning(f"从本地文件头加载EPG失败: {epg_err}")

            if self.window.playlist_tab:
                self.window.playlist_tab.setCurrentIndex(1)

            if hasattr(self.window, 'populate_channel_list'):
                self.window.populate_channel_list(source='local')

            from core.config_manager import ConfigManager
            ConfigManager().add_recent_file(file_path)
            if hasattr(self.window, 'update_recent_files_menu'):
                self.window.update_recent_files_menu()

            logger.info(f"成功加载播放列表: {file_path}, 共 {len(channels)} 个频道")
        except Exception as e:
            logger.error(f"加载播放列表失败: {e}")
            QMessageBox.critical(
                self.window,
                tr("error", "Error"),
                tr("open_file_error", "Failed to load channel list. Please check the file format and try again.")
            )

    def _save_playlist_file(self, file_path: str):
        tr = self._tr
        try:
            tab = self.window.playlist_tab
            if tab and tab.currentIndex() == 1:
                channels = self.window._local_channels
            else:
                channels = self.window._sub_channels
            if not channels:
                return
            if file_path.endswith('.m3u') or file_path.endswith('.m3u8'):
                self._save_as_m3u(channels, file_path)
            elif file_path.endswith('.txt'):
                self._save_as_txt(channels, file_path)
            else:
                self._save_as_m3u(channels, file_path)
            logger.info(f"成功保存播放列表: {file_path}")
        except Exception as e:
            QMessageBox.critical(
                self.window,
                tr("error", "Error"),
                tr("save_error", "Failed to save channel list. Please check the file path and permissions.")
            )

    @staticmethod
    def _save_as_m3u(channels: list, file_path: str):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for ch in channels:
                name = ch.get('name', '')
                url = ch.get('url', '')
                group = ch.get('group', '')
                logo = ch.get('logo', ch.get('logo_url', ''))
                tags = ch.get('_all_tags', {}) or {}
                tvg_id = ch.get('tvg_id', '')
                tvg_name = tags.get('tvg-name', '')
                tvg_chno = tags.get('tvg-chno', '')
                tvg_shift = tags.get('tvg-shift', '')
                catchup = tags.get('catchup', '') or ch.get('catchup', '')
                catchup_days = tags.get('catchup-days', '') or ch.get('catchup_days', '')
                catchup_source = ch.get('catchup_source', '')
                catchup_correction = tags.get('catchup-correction', '')
                groups = ch.get('_groups', [])

                attrs = ['#EXTINF:-1']
                if tvg_id:
                    attrs.append(f'tvg-id="{tvg_id}"')
                if tvg_name:
                    attrs.append(f'tvg-name="{tvg_name}"')
                elif name:
                    attrs.append(f'tvg-name="{name}"')
                if logo:
                    attrs.append(f'tvg-logo="{logo}"')
                if tvg_chno:
                    attrs.append(f'tvg-chno="{tvg_chno}"')
                if tvg_shift:
                    attrs.append(f'tvg-shift="{tvg_shift}"')
                if group:
                    group_value = ';'.join(groups) if groups and len(groups) > 1 else group
                    attrs.append(f'group-title="{group_value}"')
                if catchup:
                    attrs.append(f'catchup="{catchup}"')
                if catchup_days:
                    attrs.append(f'catchup-days="{catchup_days}"')
                if catchup_source:
                    attrs.append(f'catchup-source="{catchup_source}"')
                if catchup_correction:
                    attrs.append(f'catchup-correction="{catchup_correction}"')

                f.write(' '.join(attrs) + f',{name}\n')
                f.write(f'{url}\n')

    @staticmethod
    def _save_as_txt(channels: list, file_path: str):
        with open(file_path, 'w', encoding='utf-8') as f:
            for ch in channels:
                f.write(f"{ch.get('name', '')},{ch.get('url', '')}\n")

    def open_recent_file(self, file_path):
        w = self.window
        tr = w.language_manager.tr

        VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm'}

        def _handle_not_found():
            w.config.remove_recent_file(file_path)
            w.update_recent_files_menu()
            w.status_bar.showMessage(tr('file_not_found', 'File not found, removed from recent list'))
            logger.warning(f"最近文件不存在，已从列表移除: {file_path}")

        def _handle_url():
            sub_ctrl = w.subscription_ctrl if hasattr(w, 'subscription_ctrl') and w.subscription_ctrl else None
            if sub_ctrl:
                content = sub_ctrl._download_subscription_content(file_path)
                if content:
                    w._apply_m3u_content(content, file_path)
                    w.config.add_recent_file(file_path)
                    w.update_recent_files_menu()
                else:
                    w.status_bar.showMessage(tr("download_failed", "下载失败"))
                    logger.warning(f"下载最近链接失败: {file_path}")
            else:
                w.status_bar.showMessage(tr("download_failed", "下载失败"))

        def _handle_local_video():
            if not os.path.isfile(file_path):
                _handle_not_found()
                return
            w._add_local_video_and_track(file_path)

        def _handle_local_playlist():
            try:
                content = load_m3u_file(file_path)
                w._apply_m3u_content(content, file_path)
                w.config.add_recent_file(file_path)
                w.update_recent_files_menu()
            except FileNotFoundError:
                _handle_not_found()
            except Exception as ex:
                logger.error(f"打开最近文件失败: {str(ex)}")
                w.status_bar.showMessage(tr('file_open_failed', 'Failed to open file'), 3000)

        if file_path.startswith('http'):
            _handle_url()
        elif os.path.splitext(file_path)[1].lower() in VIDEO_EXTS:
            _handle_local_video()
        else:
            _handle_local_playlist()

    def _open_stream(self):
        """打开串流地址"""

        w = self.window
        tr = w.language_manager.tr

        dialog = FloatingDialog(w, frameless=False, stay_on_top=False)
        dialog.setWindowTitle(tr("open_stream", "打开串流"))
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(160)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel(tr("open_stream_url", "请输入直播地址或串流URL:"))
        layout.addWidget(label)

        url_input = QLineEdit()
        url_input.setPlaceholderText("http://example.com/stream.m3u8")
        url_input.setMinimumHeight(32)
        layout.addWidget(url_input)

        name_label = QLabel(tr("stream_name_optional", "频道名称（可选）:"))
        layout.addWidget(name_label)

        name_input = QLineEdit()
        name_input.setPlaceholderText(tr("stream_name_hint", "留空则自动命名"))
        name_input.setMinimumHeight(32)
        layout.addWidget(name_input)

        # "作为 M3U 列表解析"复选框
        # 用户可主动选择是否将输入的 URL 作为 M3U 列表解析
        # 不勾选时，系统自动判断（下载内容后根据 #EXTM3U 等标记判断）
        parse_as_playlist_checkbox = QCheckBox(
            tr("parse_as_playlist", "作为 M3U 频道列表解析（不勾选则自动判断）")
        )
        layout.addWidget(parse_as_playlist_checkbox)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr("cancel", "取消"))
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        ok_btn = QPushButton(tr("ok", "确定"))
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setDefault(True)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        dialog.setStyleSheet(AppStyles.popup_dialog_style())

        tm = get_theme_manager()
        tm.register_window(dialog)

        url_input.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = url_input.text().strip()
            if url:
                self._open_stream_by_content(
                    url, name_input.text().strip(),
                    force_as_playlist=parse_as_playlist_checkbox.isChecked()
                )
                w.config.add_recent_file(url)
                w.update_recent_files_menu()
            tm.unregister_window(dialog)
        else:
            tm.unregister_window(dialog)

    def _open_stream_by_content(self, url: str, custom_name: str = '', force_as_playlist: bool = False):
        """根据URL内容自动判断是M3U列表还是单个串流

        Args:
            force_as_playlist: 强制作为 M3U 列表解析。
                True: 强制按 M3U 列表解析，下载失败则提示用户，不回退到单流。
                False: 自动判断（默认行为）。
        """

        from services.m3u_parser import parse_m3u_content, load_m3u_from_url_data
        from urllib.parse import urlparse
        w = self.window
        tr = w.language_manager.tr

        path_lower = urlparse(url).path.lower()
        maybe_m3u = path_lower.endswith(('.m3u', '.m3u8', '.txt'))

        if maybe_m3u or force_as_playlist:
            # URL 基本格式校验：必须包含协议scheme（如 http://、https://），
            # 或者是本地文件路径（以 / 或盘符开头）。
            # 避免用户误粘贴非URL内容（如命令行）后直接报底层异常。
            if '://' not in url and not (
                    url.startswith('/') or (len(url) >= 2 and url[1] == ':' and url[0].isalpha())):
                QMessageBox.warning(
                    w, tr("open_stream", "打开串流"),
                    tr("invalid_url_prompt",
                       "输入的地址格式不正确，请检查是否包含完整的URL\n"
                       "（例如 http://example.com/playlist.m3u）")
                )
                return

            content = ''
            try:
                import requests
                from utils.http_session import get as _http_get
                config = w.config
                timeout = int(config.get_value('Network', 'timeout', '30') or 30)
                from utils.general_utils import sanitize_http_header_value
                headers = {}
                user_agent = sanitize_http_header_value(
                    config.get_value('Network', 'user_agent', ''))
                referer = sanitize_http_header_value(
                    config.get_value('Network', 'referer', ''))
                if user_agent:
                    headers['User-Agent'] = user_agent
                if referer:
                    headers['Referer'] = referer

                ssl_verify = config.get_value('Network', 'ssl_verify', 'true').lower() != 'false'
                response = _http_get(url, timeout=timeout, headers=headers,
                                        allow_redirects=True, verify=ssl_verify)
                response.raise_for_status()
                content = load_m3u_from_url_data(response.content)
            except Exception as e:
                logger.error(f"下载M3U列表失败: {e}")
                if hasattr(w, 'status_bar_show_message'):
                    w.status_bar_show_message(tr("m3u_download_failed", "M3U列表下载失败"))
                # 强制作为列表解析时，下载失败则提示用户，不回退到单流
                if force_as_playlist:
                    QMessageBox.warning(
                        w, tr("open_stream", "打开串流"),
                        tr("m3u_download_failed_prompt",
                           "无法下载列表内容，请检查网络或地址是否正确。")
                    )
                    return
                # 否则回退到作为单频道串流处理（不 return）
                # 某些 m3u8 服务器会拒绝 requests 下载（UA/token 校验），
                # 但 mpv 内部使用自己的 HTTP 客户端可以正常播放，
                # 因此下载失败时不应阻止直接交给 mpv 播放。

            if content and content.lstrip().startswith('#EXTM3U'):
                # HLS Playlist 特有标记：#EXT-X-STREAM-INF（主播放列表）或 #EXT-X-TARGETDURATION（媒体播放列表）
                # 注意：#EXTINF 不能作为 HLS 判断依据，因为普通 M3U 频道列表也包含 #EXTINF
                is_hls = '#EXT-X-STREAM-INF' in content or '#EXT-X-TARGETDURATION' in content
                if is_hls:
                    # HLS 单流（主播放列表或媒体播放列表），作为单频道处理
                    if force_as_playlist:
                        # 用户强制作为列表解析，但实际是 HLS 单流，提示用户
                        logger.info("检测到HLS Playlist，用户强制作为列表解析，提示用户并作为单流添加")
                        QMessageBox.information(
                            w, tr("open_stream", "打开串流"),
                            tr("hls_not_playlist_prompt",
                               "检测到这是 HLS 单流，不是 M3U 频道列表。\n已作为单流添加到本地列表。")
                        )
                    else:
                        logger.info("检测到HLS Playlist，作为单频道串流处理")
                    name = custom_name
                    if not name:
                        name = url.split('/')[-1][:30] if '/' in url else url[:30]
                    channel = {
                        'name': name,
                        'url': url,
                        'group': tr("temp_stream", "临时串流"),
                        '_groups': [tr("temp_stream", "临时串流")],
                    }
                    w._add_to_local_list(channel)
                    return
                else:
                    try:
                        channels, _ = parse_m3u_content(content)
                    except Exception as e:
                        logger.error(f"解析M3U列表失败: {e}")
                        return

                    if not channels:
                        logger.warning("M3U列表解析结果为空")
                        return

                    import copy
                    w.playlist_tab.setCurrentIndex(1)
                    for ch in channels:
                        w._local_channels.append(copy.deepcopy(ch))
                    w._local_channels_dirty = True
                    w._update_groups_for('local')
                    # 显式切换到"全部频道"，确保新添加的频道能全部显示
                    # （_update_groups_for 在分组未变化时会跳过 combo 更新，
                    #  若当前选中的是某个特定分组，新频道会被过滤掉而不显示）
                    all_channels_text = tr("all_channels", "All Channels")
                    w.local_group_combo.blockSignals(True)
                    if w.local_group_combo.currentText() != all_channels_text:
                        w.local_group_combo.setCurrentText(all_channels_text)
                    w.local_group_combo.blockSignals(False)
                    w._populate_channel_list_for(
                        w.local_channel_list, w._local_channels,
                        all_channels_text
                    )
                    logger.info(f"已从M3U列表加载 {len(channels)} 个频道到本地列表")
                    if hasattr(w, 'status_bar_show_message'):
                        w.status_bar_show_message(
                            tr("m3u_loaded_n_channels", "已加载 {n} 个频道").format(n=len(channels))
                        )
                    if channels:
                        w.current_channel = channels[0]
                        w.update_channel_info_on_selection()
                        w.play_channel(channels[0])
                    return

        name = custom_name
        if not name:
            name = url.split('/')[-1][:30] if '/' in url else url[:30]
        channel = {
            'name': name,
            'url': url,
            'group': tr("temp_stream", "临时串流"),
            '_groups': [tr("temp_stream", "临时串流")],
        }
        w._add_to_local_list(channel)