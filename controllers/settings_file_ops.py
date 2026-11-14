"""
设置和文件操作处理器 - 负责配置管理、文件打开/保存等
从 pyqt_player.py 提取的独立模块
"""

import os
import re
from urllib.parse import urlparse


from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (

    QFileDialog,
    QMessageBox,
    QComboBox,
    QApplication,
    QCheckBox,
    QSlider,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QPlainTextEdit,
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
from services.mpv_common import DEFAULT_NETWORK_TIMEOUT_SEC, AUDIO_SPDIF_MAP
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

    def player_settings(self, focus: str | None = None):
        dialog = self._create_settings_dialog()
        tr = self._tr

        playback_settings = self.window.config.load_playback_settings() if self.window.config else {}

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # 使用 Tab 分页，避免单页内容过长
        tab_widget = QTabWidget()
        tab_widget.setObjectName("settings_tab_widget")

        # ===== Tab 1：常规（关闭行为 + 屏保，应用级设置）=====
        general_tab = QWidget()
        general_tab_layout = QVBoxLayout(general_tab)
        general_tab_layout.setContentsMargins(0, 0, 0, 0)

        general_content = QWidget()
        general_content_layout = QVBoxLayout(general_content)
        general_content_layout.setContentsMargins(0, 0, 0, 0)
        screensaver_section = self._build_screensaver_section(tr)
        general_content_layout.addWidget(self._build_general_app_section(tr))
        general_content_layout.addWidget(self._build_close_behavior_section(tr))
        general_content_layout.addWidget(screensaver_section)
        general_content_layout.addStretch()

        general_scroll = QScrollArea()
        general_scroll.setWidgetResizable(True)
        general_scroll.setFrameShape(QFrame.Shape.NoFrame)
        general_scroll.setWidget(general_content)
        general_tab_layout.addWidget(general_scroll)

        tab_widget.addTab(general_tab, tr("general_settings_tab", "常规"))

        # ===== Tab 2：播放设置（只保留播放/解码相关项，可滚动）=====
        playback_tab = QWidget()
        playback_tab_layout = QVBoxLayout(playback_tab)
        playback_tab_layout.setContentsMargins(0, 0, 0, 0)

        playback_content = QWidget()
        playback_content_layout = QVBoxLayout(playback_content)
        playback_content_layout.setContentsMargins(0, 0, 0, 0)
        playback_content_layout.addWidget(self._build_protocol_section(tr, playback_settings))
        playback_content_layout.addWidget(self._build_playback_extras_section(tr, playback_settings))
        playback_content_layout.addStretch()

        playback_scroll = QScrollArea()
        playback_scroll.setWidgetResizable(True)
        playback_scroll.setFrameShape(QFrame.Shape.NoFrame)
        playback_scroll.setWidget(playback_content)
        playback_tab_layout.addWidget(playback_scroll)

        tab_widget.addTab(playback_tab, tr("playback_settings_tab", "播放设置"))

        # ===== Tab 3：网络（连接相关 + GitHub 加速代理）=====
        network_tab = QWidget()
        network_tab_layout = QVBoxLayout(network_tab)
        network_tab_layout.setContentsMargins(0, 0, 0, 0)

        network_content = QWidget()
        network_content_layout = QVBoxLayout(network_content)
        network_content_layout.setContentsMargins(0, 0, 0, 0)
        network_content_layout.addWidget(self._build_connection_section(tr, playback_settings))
        stream_section = self._build_network_stream_section(tr, playback_settings)
        network_content_layout.addWidget(stream_section)
        network_content_layout.addWidget(self._build_github_proxy_section(tr))
        server_section = self._build_server_section(tr)
        network_content_layout.addWidget(server_section)
        network_content_layout.addStretch()

        network_scroll = QScrollArea()
        network_scroll.setWidgetResizable(True)
        network_scroll.setFrameShape(QFrame.Shape.NoFrame)
        network_scroll.setWidget(network_content)
        network_tab_layout.addWidget(network_scroll)

        tab_widget.addTab(network_tab, tr("network_settings_tab", "网络"))

        # ===== Tab 4：订阅源管理（播放列表 + EPG）=====
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

        # ===== Tab 5：外观（字号档位 + 界面缩放）=====
        # 单独成页：常规页承载关闭行为/屏保，播放设置页承载解码参数，外观不属于两者，
        # 且用户反馈「字小」时第一眼就能在 Tab 上看到「外观」。
        appearance_tab = QWidget()
        appearance_tab_layout = QVBoxLayout(appearance_tab)
        appearance_tab_layout.setContentsMargins(0, 0, 0, 0)

        appearance_content = QWidget()
        appearance_content_layout = QVBoxLayout(appearance_content)
        appearance_content_layout.setContentsMargins(0, 0, 0, 0)
        self._build_appearance_section(tr, appearance_content_layout)

        appearance_scroll = QScrollArea()
        appearance_scroll.setWidgetResizable(True)
        appearance_scroll.setFrameShape(QFrame.Shape.NoFrame)
        appearance_scroll.setWidget(appearance_content)
        appearance_tab_layout.addWidget(appearance_scroll)

        tab_widget.addTab(appearance_tab, tr("appearance_settings_tab", "外观"))

        main_layout.addWidget(tab_widget, 1)

        # 记录打开对话框时的订阅配置，作为「保存」时判断是否需要重新下载的基线
        dialog._old_playlist_sources = [
            dict(s) for s in global_subscription_manager.get_playlist_sources()]
        dialog._old_epg_sources = [
            dict(s) for s in global_subscription_manager.get_epg_sources()]
        dialog._old_active_playlist_index = (
            global_subscription_manager.get_active_playlist_source_index())

        self._connect_subscription_signals(playlist_section, epg_section)

        button_layout = QHBoxLayout()
        reset_button = QPushButton(tr("reset_defaults", "恢复默认"))
        reset_button.setObjectName("settings_reset_button")
        reset_button.clicked.connect(lambda: self._reset_settings_defaults(dialog))
        save_button = QPushButton(tr("save_button", "Save"))
        cancel_button = QPushButton(tr("cancel_button", "Cancel"))
        save_button.clicked.connect(lambda: self._save_and_close_settings(dialog))
        # 外观是即时预览：取消时回到打开对话框前的档位，避免"改完未保存却已生效"
        from ui import typography
        initial_display = typography.current_display()
        cancel_button.clicked.connect(lambda: self._cancel_settings(dialog, initial_display))
        button_layout.addStretch()
        button_layout.addWidget(reset_button)
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
        # 大字号下 sizeHint 可能超过基准宽度：取两者较大值并限制在屏幕内，
        # 避免订阅源表格/外观说明被横向裁切。
        hint = dialog.sizeHint()
        width = max(typography.scale_px(720), hint.width())
        height = max(typography.scale_px(500), hint.height())
        screen = dialog.screen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, int(available.width() * 0.92))
            height = min(height, int(available.height() * 0.92))
        dialog.resize(width, height)

        if focus == 'screensaver':
            # 屏保已迁到「常规」页签（索引 0），打开后滚动到屏保分组
            tab_widget.setCurrentIndex(0)

            def _reveal_screensaver():
                # 等对话框真正显示、滚动区几何确定后再定位，避免打开后停在顶部
                if dialog.isVisible():
                    general_scroll.ensureWidgetVisible(screensaver_section, 0, 0)

            QTimer.singleShot(0, _reveal_screensaver)

        elif focus in ('network', 'network_stream'):
            # HTTP 服务 / 流媒体请求设置已并入「网络」页签（索引 2）
            tab_widget.setCurrentIndex(2)
            target = stream_section if focus == 'network_stream' else server_section

            def _reveal_target():
                if dialog.isVisible():
                    network_scroll.ensureWidgetVisible(target, 0, 0)

            QTimer.singleShot(0, _reveal_target)

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
        from ui import typography
        min_w, min_h = typography.scale_size(680, 440)
        screen = dialog.screen()
        if screen is not None:
            available = screen.availableGeometry()
            # 小屏幕 + 150% 时不能把对话框撑出屏幕
            min_w = min(min_w, int(available.width() * 0.9))
            min_h = min(min_h, int(available.height() * 0.9))
        dialog.setMinimumSize(min_w, min_h)
        dialog.resize(*typography.scale_size(720, 500))
        dialog.setStyleSheet(AppStyles.dialog_style())
        return dialog

    def _build_appearance_section(self, tr, parent_layout):
        """构建「外观」分组：字号档位 + 界面缩放。

        两者共用 ui/typography.py 这一份真源：
        * 界面缩放整体等比（文字/图标/间距/行高）；
        * 字号档位只在缩放基础上再偏文字。
        改动即时生效并写入配置，取消时由 _cancel_settings 回滚。
        """
        from ui import typography

        group = QGroupBox(tr("appearance_settings", "外观"))
        layout = QFormLayout(group)

        tier_combo = QComboBox()
        tier_combo.setObjectName("font_size_tier_combo")
        for key in ('small', 'standard', 'large', 'xlarge'):
            tier_info = typography.FONT_TIERS[key]
            text = tr(f"font_size_{key}", f"{tier_info['zh']}（{tier_info['pt']:g}pt）")
            tier_combo.addItem(text, key)

        scale_combo = QComboBox()
        scale_combo.setObjectName("ui_scale_combo")
        for percent in typography.UI_SCALE_OPTIONS:
            scale_combo.addItem(f"{percent}%", percent)

        tier, percent = typography.current_display()
        tier_combo.setCurrentIndex(max(0, tier_combo.findData(tier)))
        scale_combo.setCurrentIndex(max(0, scale_combo.findData(percent)))

        layout.addRow(QLabel(tr("font_size_label", "字体大小:")), tier_combo)
        layout.addRow(QLabel(tr("ui_scale_label", "界面缩放:")), scale_combo)

        theme_manager = get_theme_manager()
        color_combo = QComboBox()
        color_combo.setObjectName("color_mode_combo")
        for mode in theme_manager.get_available_color_modes():
            color_combo.addItem(tr(f"color_mode_{mode}", mode), mode)
        color_combo.setCurrentIndex(max(0, color_combo.findData(theme_manager.get_color_mode())))
        layout.addRow(QLabel(tr("color_mode_label", "颜色模式:")), color_combo)

        style_combo = QComboBox()
        style_combo.setObjectName("visual_style_combo")
        for style in theme_manager.get_available_visual_styles():
            style_combo.addItem(tr(f"visual_style_{style}", style), style)
        style_combo.setCurrentIndex(max(0, style_combo.findData(theme_manager.get_visual_style())))
        layout.addRow(QLabel(tr("visual_style_label", "视觉风格:")), style_combo)

        hint = QLabel(tr(
            "appearance_hint",
            "界面缩放会等比放大文字、图标与间距；字体大小只调整文字，"
            "适合只想看清文字、不想减少可视内容的情况。修改后立即生效；"
            "颜色模式与视觉风格点「保存」后生效。"
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(hint)

        def _apply(*_args):
            self._apply_display_settings(tier_combo.currentData(), scale_combo.currentData())

        tier_combo.currentIndexChanged.connect(_apply)
        scale_combo.currentIndexChanged.connect(_apply)

        parent_layout.addWidget(group)
        parent_layout.addStretch()
        return tier_combo, scale_combo

    def _apply_display_settings(self, tier, percent):
        """把档位写入单一真源并触发全局重刷（QSS + 固定尺寸）。"""
        try:
            get_theme_manager().set_display_settings(tier, percent)
        except Exception as e:
            logger.error(f"应用字号/缩放设置失败: {e}")

    def _cancel_settings(self, dialog, initial_display):
        """取消外观预览：恢复到打开对话框前的档位并关闭。"""
        try:
            get_theme_manager().set_display_settings(*initial_display)
        except Exception as e:
            logger.debug(f"回滚字号/缩放设置失败: {e}")
        dialog.close()

    def _build_general_app_section(self, tr):
        """常规页的应用级设置：界面语言与日志等级。"""
        group = QGroupBox(tr("general_app_settings", "应用"))
        layout = QFormLayout()

        lang_combo = QComboBox()
        lang_combo.setObjectName("language_combo")
        lm = getattr(self.window, 'language_manager', None)
        languages = getattr(lm, 'available_languages', {}) if lm is not None else {}
        for code in ('zh', 'en'):
            if code in languages:
                lang_combo.addItem(languages[code].get('display_name', code), code)
        for code, info in (languages or {}).items():
            if code in ('zh', 'en'):
                continue
            lang_combo.addItem(info.get('display_name', code), code)
        current_lang = getattr(lm, 'current_language', 'zh') if lm is not None else 'zh'
        idx = lang_combo.findData(current_lang)
        if idx >= 0:
            lang_combo.setCurrentIndex(idx)
        layout.addRow(tr("language_label", "界面语言:"), lang_combo)

        log_combo = QComboBox()
        log_combo.setObjectName("log_level_combo")
        log_levels = [
            ('DEBUG', tr("log_level_debug", "调试")),
            ('INFO', tr("log_level_info", "信息")),
            ('WARNING', tr("log_level_warning", "警告")),
            ('ERROR', tr("log_level_error", "错误")),
        ]
        for name, label in log_levels:
            log_combo.addItem(label, name)
        raw_level = ''
        if self.window.config:
            raw_level = str(self.window.config.get_value('UI', 'log_level', 'INFO') or 'INFO')
        current_level = raw_level.upper()
        idx = log_combo.findData(current_level)
        if idx < 0:
            idx = log_combo.findData('INFO')
        log_combo.setCurrentIndex(max(0, idx))
        layout.addRow(tr("log_level_label", "日志等级:"), log_combo)

        hint = QLabel(tr(
            "general_app_hint",
            "日志等级只影响日志文件与终端输出，普通使用保持「信息」即可。"
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(hint)

        group.setLayout(layout)
        return group

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

    def _build_screensaver_section(self, tr):
        """屏保分组：开关 + 等待时间（关闭开关时等待时间置灰）。"""
        from controllers.screensaver_controller import parse_enabled, parse_minutes

        group = QGroupBox(tr("screensaver_settings", "屏保"))
        layout = QFormLayout()

        enabled_check = QCheckBox(tr("screensaver_enabled", "启用屏保"))
        enabled_check.setObjectName("screensaver_enabled_check")

        idle_combo = QComboBox()
        idle_combo.setObjectName("screensaver_idle_combo")
        for minutes in (1, 5, 10, 30, 60):
            idle_combo.addItem(tr(f"screensaver_wait_{minutes}", f"{minutes} 分钟"), minutes)

        enabled, minutes = True, 5
        config = self.window.config
        if config:
            enabled = parse_enabled(config.get_value('ScreenSaver', 'enabled', 'true'), True)
            minutes = parse_minutes(config.get_value('ScreenSaver', 'idle_minutes', '5'), 5)

        enabled_check.setChecked(enabled)
        for i in range(idle_combo.count()):
            if idle_combo.itemData(i) == minutes:
                idle_combo.setCurrentIndex(i)
                break
        idle_combo.setEnabled(enabled)
        enabled_check.toggled.connect(idle_combo.setEnabled)

        layout.addRow(enabled_check)
        layout.addRow(tr("screensaver_wait_label", "等待时间:"), idle_combo)
        group.setLayout(layout)
        return group

    def _build_github_proxy_section(self, tr):
        """GitHub 加速代理：启用开关 + 代理地址列表。

        只影响 GitHub 域名的请求；用户自己的订阅源/EPG 源等非 GitHub 地址不受影响。
        """
        from utils import github_proxy

        group = QGroupBox(tr("github_proxy_settings", "GitHub 加速代理"))
        layout = QFormLayout()

        enabled_check = QCheckBox(tr("github_proxy_enabled", "启用 GitHub 加速代理"))
        enabled_check.setObjectName("github_proxy_enabled_check")

        proxy_combo = QComboBox()
        proxy_combo.setObjectName("github_proxy_combo")
        for proxy in github_proxy.PROXY_LIST:
            proxy_combo.addItem(proxy, proxy)

        settings = github_proxy.load_settings()
        enabled_check.setChecked(settings['enabled'])
        index = proxy_combo.findData(settings['proxy'])
        proxy_combo.setCurrentIndex(max(0, index))
        proxy_combo.setEnabled(settings['enabled'])
        enabled_check.toggled.connect(proxy_combo.setEnabled)

        layout.addRow(enabled_check)
        layout.addRow(QLabel(tr("github_proxy_label", "代理地址:")), proxy_combo)

        hint = QLabel(tr(
            "github_proxy_hint",
            "仅加速检查更新、在线更新、远程映射、订阅源与 EPG 的 GitHub 请求；"
            "其他地址不受影响。修改后立即生效。"
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(hint)

        group.setLayout(layout)
        return group

    def _build_connection_section(self, tr, playback_settings):
        """连接相关设置：TLS 校验与网络超时。

        配置键与原来保持一致（Playback.tls_verify / Playback.network_timeout_sec），
        仅界面位置从「播放设置」迁到「网络」，老配置无需迁移。
        """
        group = QGroupBox(tr("connection_settings", "连接"))
        layout = QFormLayout()

        tls_check = QCheckBox(tr("tls_verify_label", "TLS Verify"))
        tls_check.setObjectName("tls_check")
        tls_check.setChecked(playback_settings.get('tls_verify', False))
        layout.addRow(tls_check)

        timeout_combo = QComboBox()
        timeout_combo.setObjectName("network_timeout_combo")
        timeout_items = [
            (0, tr("auto_timeout", "Auto (10s)")),
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

        scope_hint = QLabel(tr(
            "connection_scope_hint",
            "TLS 校验只作用于播放器；网络超时同时用于播放器与订阅源/EPG 下载。"
        ))
        scope_hint.setWordWrap(True)
        scope_hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(scope_hint)

        group.setLayout(layout)
        return group

    def _build_network_stream_section(self, tr, playback_settings):
        """流媒体请求参数：HTTP 代理 / Referer / 自定义请求头。

        原「网络增强」对话框的三项已完整并入本分组，配置键沿用
        Playback.http_proxy / http_referer / http_headers。
        """
        group = QGroupBox(tr("network_stream_settings", "流媒体请求"))
        layout = QFormLayout()

        proxy_edit = QLineEdit()
        proxy_edit.setObjectName("http_proxy_edit")
        proxy_edit.setPlaceholderText("http://127.0.0.1:8080")
        proxy_edit.setText(playback_settings.get('http_proxy', '') or '')
        layout.addRow(tr("network_enhance_proxy", "代理 URL"), proxy_edit)

        ua_edit = QLineEdit()
        ua_edit.setObjectName("user_agent_edit")
        ua_edit.setPlaceholderText("Mozilla/5.0 ...")
        ua_edit.setText(playback_settings.get('user_agent', '') or '')
        layout.addRow(tr("network_user_agent_label", "User-Agent"), ua_edit)

        referer_edit = QLineEdit()
        referer_edit.setObjectName("http_referer_edit")
        referer_edit.setPlaceholderText("https://example.com/")
        referer_edit.setText(playback_settings.get('http_referer', '') or '')
        layout.addRow(tr("network_enhance_referer", "Referer"), referer_edit)

        headers_edit = QPlainTextEdit()
        headers_edit.setObjectName("http_headers_edit")
        headers_edit.setPlaceholderText("Key: Value\nKey2: Value2")
        headers_edit.setFixedHeight(96)
        headers_edit.setPlainText(playback_settings.get('http_headers', '') or '')
        layout.addRow(tr("network_enhance_group_headers", "HTTP 请求头"), headers_edit)

        hint = QLabel(tr(
            "network_stream_hint",
            "代理只支持 http:// 或 https://；socks5:// 会被 mpv 忽略，保存时也会被拦下。"
            "Referer 与自定义请求头同时用于播放器和订阅源/EPG 下载；User-Agent 用于播放器，"
            "下载 UA 请在「扫描整理 → 网络参数」中设置。"
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(hint)

        timing_hint = QLabel(tr(
            "network_stream_timing_hint",
            "以上修改对当前正在播放的流不生效：切换到该频道或重新打开频道后才会用新的请求参数。"
        ))
        timing_hint.setWordWrap(True)
        timing_hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(timing_hint)

        group.setLayout(layout)
        return group

    def _build_server_section(self, tr):
        """HTTP 服务：运行状态、认证码、启动/停止、自启动、端口与监听地址。

        原先放在独立对话框里，现并入「网络」页签；配置键沿用
        Server.enabled/port/host/auto_start，老配置无需迁移。
        """
        from server.app import get_server, start_server, stop_server, set_main_window
        from server.routes import get_auth_token

        settings = self.window.config.load_server_settings()

        group = QGroupBox(tr("server_settings", "服务设置"))
        layout = QVBoxLayout(group)

        status_label = QLabel()
        status_label.setObjectName("server_status_label")
        status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(status_label)

        auto_start_check = QCheckBox(tr("server_auto_start", "启动时自动运行服务"))
        auto_start_check.setObjectName("server_auto_start_check")
        auto_start_check.setChecked(settings.get("auto_start", False))
        layout.addWidget(auto_start_check)

        port_row = QHBoxLayout()
        port_label = QLabel(tr("server_port", "端口:"))
        port_label.setFixedWidth(70)
        port_row.addWidget(port_label)
        port_spin = QSpinBox()
        port_spin.setObjectName("server_port_spin")
        port_spin.setRange(1024, 65535)
        # 端口框保留配置值（起始端口），实际端口见上方状态；避免把顺延后的端口写回配置
        port_spin.setValue(settings.get("port", 8080))
        port_row.addWidget(port_spin, 1)
        layout.addLayout(port_row)

        host_row = QHBoxLayout()
        host_label = QLabel(tr("server_host", "监听地址:"))
        host_label.setFixedWidth(70)
        host_row.addWidget(host_label)
        host_combo = QComboBox()
        host_combo.setObjectName("server_host_combo")
        host_combo.addItem(f"0.0.0.0 ({tr('all_interfaces', '所有接口')})", "0.0.0.0")
        host_combo.addItem(f"127.0.0.1 ({tr('localhost_only', '仅本机')})", "127.0.0.1")
        host_idx = host_combo.findData(settings.get("host", "127.0.0.1"))
        if host_idx >= 0:
            host_combo.setCurrentIndex(host_idx)
        host_row.addWidget(host_combo, 1)
        layout.addLayout(host_row)

        host_hint = QLabel(tr(
            "server_host_hint",
            "仅本机：只有这台电脑能访问；所有接口：同一局域网的其他设备也能访问。"
        ))
        host_hint.setWordWrap(True)
        host_hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addWidget(host_hint)

        button_row = QHBoxLayout()
        button_row.addStretch()
        toggle_button = QPushButton()
        toggle_button.setObjectName("server_toggle_button")
        toggle_button.setStyleSheet(AppStyles.common_button_style())
        button_row.addWidget(toggle_button)
        layout.addLayout(button_row)

        def _sync_menu_action(is_running):
            action = getattr(self.window, "_server_action", None)
            if action is not None:
                action.setText(tr("server_stop", "停止服务") if is_running
                               else tr("server_start", "启动服务"))

        def _refresh_status():
            server = get_server()
            is_running = server.is_running()
            configured_port = port_spin.value()
            # 运行中显示实际绑定端口：配置端口被占用时会自动顺延
            port = server.port if is_running else configured_port
            token = get_auth_token()
            if is_running:
                text = (
                    f"● {tr('server_running', '服务运行中')}\n"
                    f"  {tr('server_address', '地址')}: http://localhost:{port}\n"
                    f"  {tr('server_auth_token', '认证码')}: {token}"
                )
                if configured_port != port:
                    text += "\n  " + tr(
                        "server_port_shifted", "端口 {requested} 已被占用，已改用 {port}").format(
                        requested=configured_port, port=port)
                status_label.setStyleSheet(AppStyles.status_label_style(True))
            else:
                # 未启动时也显示地址与认证码，方便先配置客户端再启动服务
                text = (
                    f"○ {tr('server_not_running', '服务未运行')}\n"
                    f"  {tr('server_address', '地址')}: http://localhost:{port}\n"
                    f"  {tr('server_auth_token', '认证码')}: {token}"
                )
                status_label.setStyleSheet(AppStyles.status_label_style(False))
            status_label.setText(text)
            toggle_button.setText(tr("server_stop", "停止服务") if is_running
                                  else tr("server_start", "启动服务"))
            _sync_menu_action(is_running)

        def _on_toggle():
            try:
                set_main_window(self.window)
                server = get_server()
                if server.is_running():
                    stop_server()
                    self.window.status_bar_show_message(tr("server_stopped", "服务已停止"), 3000)
                    _refresh_status()
                    return
                requested_port = port_spin.value()
                server = start_server(host=host_combo.currentData(), port=requested_port)
                if not (server is not None and server.wait_started(2.0)):
                    err = getattr(server, "start_error", "") if server is not None else ""
                    self.window.status_bar_show_message(
                        tr("server_start_failed", "服务启动失败") + (f": {err}" if err else ""), 8000)
                    logger.error(f"启动服务失败: {err or '端口未绑定成功'}")
                    _refresh_status()
                    return
                actual_port = server.port
                msg = (tr("server_started", "服务已启动") + f" http://localhost:{actual_port}  " +
                       tr("server_auth_token", "认证码") + f": {get_auth_token()}")
                if requested_port != actual_port:
                    msg += "  " + tr(
                        "server_port_shifted", "端口 {requested} 已被占用，已改用 {port}").format(
                        requested=requested_port, port=actual_port)
                self.window.status_bar_show_message(msg, 10000)
                logger.info(f"HTTP 服务器已启动: http://localhost:{actual_port}")
                _refresh_status()
            except Exception as e:
                logger.error(f"切换服务失败: {e}")
                _refresh_status()

        toggle_button.clicked.connect(_on_toggle)
        _refresh_status()

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

        passthrough_combo = QComboBox()
        passthrough_combo.setObjectName("audio_passthrough_combo")
        passthrough_items = [
            ('never', tr("passthrough_never", "Never (Decode)")),
            ('spdif_only', tr("passthrough_spdif", "SPDIF (AC3/EAC3/DTS)")),
            ('hd_codecs', tr("passthrough_hd", "HD + Core (AC3/EAC3/DTS/DTS-HD/TrueHD)")),
            ('lossless', tr("passthrough_lossless", "Lossless (TrueHD/DTS-HD)")),
            ('all', tr("passthrough_all", "All supported (incl. DSD)")),
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
        ]
        # 只列出当前平台真正可用的 vo：Linux 的 wid 嵌入不支持 libmpv/direct3d，
        # 列出这些选项会让用户选到必然黑屏的配置。
        from utils.platform_utils import is_windows, is_linux
        if not is_linux():
            vo_items.append(('libmpv', tr("vo_libmpv", "libmpv (Render API, macOS default)")))
        if is_windows():
            vo_items.append(('direct3d', tr("vo_direct3d", "direct3d (Windows legacy VO)")))
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
               "gpu-next is required for HDR passthrough/scRGB on Windows. "
               "Changes take effect only after restarting the app.")
        )

        vsync_combo = QComboBox()
        vsync_combo.setObjectName("video_sync_combo")
        vsync_items = [
            ('audio', tr("vsync_audio", "audio (Default, sync to audio clock)")),
            ('display-resample', tr("vsync_display_resample", "display-resample (Resample audio to display)")),
            ('display-tempo', tr("vsync_display_tempo", "display-tempo (Tempo-scale audio)")),
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
            ('decoder+vo', tr("framedrop_decoder_vo", "decoder+vo (Drop at both stages)")),
            ('no', tr("framedrop_no", "no (Never drop, testing only)")),
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
            ('auto', tr("deinterlace_auto", "Auto (detect interlaced frames)")),
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
               "Deinterlacing for interlaced video. 'Auto' lets mpv/FFmpeg detect interlaced "
               "frames and only then insert the deinterlace filter, so progressive sources pay "
               "no filtering cost. With native hardware decoding the filter may not be insertable; "
               "switch hardware decoding to copy-back (or software) if combing remains.")
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

    def _build_playback_extras_section(self, tr, playback_settings):
        """播放设置页的其余分组：循环模式、片头片尾跳过、视频/音频/字幕调整。

        图像/音频/字幕参数与各自的独立对话框共用同一份配置，保存时先读取
        现有字典再合并本次字段，避免互相覆盖。
        """
        group = QGroupBox(tr("playback_extras_settings", "播放行为"))
        layout = QFormLayout()

        queue_combo = QComboBox()
        queue_combo.setObjectName("queue_mode_combo")
        queue_items = [
            ('none', tr("playback_queue_mode_none", "不循环")),
            ('single', tr("playback_queue_mode_single", "单文件循环")),
            ('all', tr("playback_queue_mode_all", "列表循环")),
            ('shuffle', tr("playback_queue_mode_shuffle", "随机播放")),
        ]
        for value, label in queue_items:
            queue_combo.addItem(label, value)
        queue_combo.setCurrentIndex(
            max(0, queue_combo.findData(playback_settings.get('queue_mode', 'none'))))
        layout.addRow(tr("queue_mode_label", "循环模式:"), queue_combo)

        def _skip_row(enable_name, seconds_name, key_enable, key_seconds):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            check = QCheckBox(tr("skip_enabled", "自动跳过"))
            check.setObjectName(enable_name)
            check.setChecked(bool(playback_settings.get(key_enable, False)))
            spin = QSpinBox()
            spin.setObjectName(seconds_name)
            spin.setRange(0, 600)
            spin.setSuffix(tr("seconds_suffix", " 秒"))
            spin.setMinimumHeight(28)
            try:
                spin.setValue(int(round(float(playback_settings.get(key_seconds, 0.0) or 0.0))))
            except (TypeError, ValueError):
                spin.setValue(0)
            spin.setEnabled(check.isChecked())
            check.toggled.connect(spin.setEnabled)
            row_layout.addWidget(check)
            row_layout.addWidget(spin, 1)
            return row

        layout.addRow(tr("skip_intro_label", "跳过片头:"),
                      _skip_row("auto_skip_intro_check", "skip_intro_seconds_spin",
                                "auto_skip_intro", "skip_intro_seconds"))
        layout.addRow(tr("skip_outro_label", "跳过片尾:"),
                      _skip_row("auto_skip_outro_check", "skip_outro_seconds_spin",
                                "auto_skip_outro", "skip_outro_seconds"))

        # ---- 视频图像调整（核心参数） ----
        eq_cfg = self.window.config.load_video_eq() if self.window.config else {}
        video_box = QGroupBox(tr("video_eq_group_image", "图像参数"))
        video_layout = QFormLayout(video_box)
        for key in ('brightness', 'contrast', 'saturation', 'hue', 'gamma'):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setObjectName(f"video_eq_{key}_slider")
            slider.setRange(-100, 100)
            try:
                value = int(eq_cfg.get(key, 0) or 0)
            except (TypeError, ValueError):
                value = 0
            slider.setValue(max(-100, min(100, value)))
            value_label = QLabel(str(slider.value()))
            value_label.setMinimumWidth(36)
            slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(str(v)))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(value_label)
            video_layout.addRow(tr(f"video_eq_{key}", key.capitalize()), row)

        sharp_slider = QSlider(Qt.Orientation.Horizontal)
        sharp_slider.setObjectName("video_eq_sharpness_slider")
        sharp_slider.setRange(-100, 100)
        try:
            sharp_value = int(round(float(eq_cfg.get('sharpness', 0.0) or 0.0) * 100))
        except (TypeError, ValueError):
            sharp_value = 0
        sharp_slider.setValue(max(-100, min(100, sharp_value)))
        sharp_label = QLabel(f"{sharp_slider.value() / 100.0:.2f}")
        sharp_label.setMinimumWidth(42)
        sharp_slider.valueChanged.connect(
            lambda v, lbl=sharp_label: lbl.setText(f"{v / 100.0:.2f}"))
        sharp_row = QWidget()
        sharp_layout = QHBoxLayout(sharp_row)
        sharp_layout.setContentsMargins(0, 0, 0, 0)
        sharp_layout.addWidget(sharp_slider, 1)
        sharp_layout.addWidget(sharp_label)
        video_layout.addRow(tr("video_eq_sharpness", "锐度"), sharp_row)

        rotate_combo = QComboBox()
        rotate_combo.setObjectName("video_eq_rotate_combo")
        for label, value in [('0°', 0), ('90°', 90), ('180°', 180), ('270°', 270)]:
            rotate_combo.addItem(label, value)
        try:
            rotate_value = int(eq_cfg.get('video_rotate', 0) or 0)
        except (TypeError, ValueError):
            rotate_value = 0
        rotate_combo.setCurrentIndex(max(0, rotate_combo.findData(rotate_value)))
        video_layout.addRow(tr("video_eq_rotate", "旋转"), rotate_combo)

        flip_combo = QComboBox()
        flip_combo.setObjectName("video_eq_flip_combo")
        for label, value in [
            (tr("video_eq_flip_none", "无"), ''),
            (tr("video_eq_flip_horizontal", "水平翻转"), 'horizontal'),
            (tr("video_eq_flip_vertical", "垂直翻转"), 'vertical'),
            (tr("video_eq_flip_both", "双向翻转"), 'both'),
        ]:
            flip_combo.addItem(label, value)
        flip_combo.setCurrentIndex(
            max(0, flip_combo.findData(eq_cfg.get('video_flip', '') or '')))
        video_layout.addRow(tr("video_eq_flip", "镜像翻转"), flip_combo)

        reset_check = QCheckBox(tr("video_eq_reset_on_new_file", "切换文件时自动重置"))
        reset_check.setObjectName("video_eq_reset_check")
        reset_check.setChecked(bool(eq_cfg.get('reset_on_new_file', False)))
        video_layout.addRow('', reset_check)
        layout.addRow(video_box)

        # ---- 音频调整（核心参数） ----
        audio_cfg = self.window.config.load_audio_eq() if self.window.config else {}
        audio_box = QGroupBox(tr("audio_eq_group_delay", "音频调整"))
        audio_layout = QFormLayout(audio_box)

        delay_slider = QSlider(Qt.Orientation.Horizontal)
        delay_slider.setObjectName("audio_eq_delay_slider")
        delay_slider.setRange(-1000, 1000)
        try:
            delay_value = int(round(float(audio_cfg.get('audio_delay', 0.0) or 0.0) * 100))
        except (TypeError, ValueError):
            delay_value = 0
        delay_slider.setValue(max(-1000, min(1000, delay_value)))
        delay_label = QLabel(f"{delay_slider.value() / 100.0:+.3f}s")
        delay_label.setMinimumWidth(62)
        delay_slider.valueChanged.connect(
            lambda v, lbl=delay_label: lbl.setText(f"{v / 100.0:+.3f}s"))
        delay_row = QWidget()
        delay_layout = QHBoxLayout(delay_row)
        delay_layout.setContentsMargins(0, 0, 0, 0)
        delay_layout.addWidget(delay_slider, 1)
        delay_layout.addWidget(delay_label)
        audio_layout.addRow(tr("audio_eq_delay", "音频延迟"), delay_row)

        pitch_slider = QSlider(Qt.Orientation.Horizontal)
        pitch_slider.setObjectName("audio_eq_pitch_slider")
        pitch_slider.setRange(50, 200)
        try:
            pitch_value = int(round(float(audio_cfg.get('audio_pitch', 1.0) or 1.0) * 100))
        except (TypeError, ValueError):
            pitch_value = 100
        if pitch_value <= 0:
            pitch_value = 100
        pitch_slider.setValue(max(50, min(200, pitch_value)))
        pitch_label = QLabel(f"{pitch_slider.value() / 100.0:.2f}")
        pitch_label.setMinimumWidth(40)
        pitch_slider.valueChanged.connect(
            lambda v, lbl=pitch_label: lbl.setText(f"{v / 100.0:.2f}"))
        pitch_row = QWidget()
        pitch_layout = QHBoxLayout(pitch_row)
        pitch_layout.setContentsMargins(0, 0, 0, 0)
        pitch_layout.addWidget(pitch_slider, 1)
        pitch_layout.addWidget(pitch_label)
        audio_layout.addRow(tr("audio_eq_pitch", "音调（变调不变速）"), pitch_row)

        channels_combo = QComboBox()
        channels_combo.setObjectName("audio_eq_channels_combo")
        for value, label in [
            ('auto', 'Auto'), ('mono', 'Mono'), ('1.0', '1.0'), ('2.0', '2.0'),
            ('2.1', '2.1'), ('3.0', '3.0'), ('4.0', '4.0'), ('5.0', '5.0'),
            ('5.1', '5.1'), ('6.0', '6.0'), ('6.1', '6.1'), ('7.0', '7.0'),
            ('7.1', '7.1'),
        ]:
            channels_combo.addItem(label, value)
        channels_combo.setCurrentIndex(
            max(0, channels_combo.findData(audio_cfg.get('audio_channels', 'auto') or 'auto')))
        audio_layout.addRow(tr("audio_eq_channels", "声道"), channels_combo)

        eq_bands = audio_cfg.get('eq', [0.0] * 10)
        if not isinstance(eq_bands, list) or len(eq_bands) != 10:
            eq_bands = [0.0] * 10
        band_row = QWidget()
        band_layout = QHBoxLayout(band_row)
        band_layout.setContentsMargins(0, 0, 0, 0)
        band_layout.setSpacing(4)
        for i in range(10):
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setObjectName(f"audio_eq_band_{i}_slider")
            slider.setRange(-12, 12)
            slider.setFixedHeight(72)
            try:
                band_value = int(round(float(eq_bands[i])))
            except (TypeError, ValueError):
                band_value = 0
            slider.setValue(max(-12, min(12, band_value)))
            slider.setToolTip(tr("audio_eq_band_tip", "第 {n} 段").format(n=i + 1))
            band_layout.addWidget(slider, 1)
        audio_layout.addRow(tr("audio_eq_group_equalizer", "均衡器"), band_row)
        layout.addRow(audio_box)

        # ---- 字幕样式（核心参数） ----
        sub_cfg = self.window.config.load_subtitle_style() if self.window.config else {}
        sub_box = QGroupBox(tr("sub_style_group", "字幕样式"))
        sub_layout = QFormLayout(sub_box)

        sub_font_size = QSpinBox()
        sub_font_size.setObjectName("sub_font_size_spin")
        sub_font_size.setRange(8, 200)
        sub_font_size.setValue(int(sub_cfg.get('font_size', 55) or 55))
        sub_layout.addRow(tr("sub_font_size", "字体大小"), sub_font_size)

        sub_border_size = QSpinBox()
        sub_border_size.setObjectName("sub_border_size_spin")
        sub_border_size.setRange(0, 20)
        sub_border_size.setValue(int(sub_cfg.get('border_size', 3) or 0))
        sub_layout.addRow(tr("sub_border_size", "边框粗细"), sub_border_size)

        sub_shadow_offset = QSpinBox()
        sub_shadow_offset.setObjectName("sub_shadow_offset_spin")
        sub_shadow_offset.setRange(0, 20)
        sub_shadow_offset.setValue(int(sub_cfg.get('shadow_offset', 1) or 0))
        sub_layout.addRow(tr("sub_shadow_offset", "阴影偏移"), sub_shadow_offset)

        sub_font_style = QWidget()
        sub_font_style_layout = QHBoxLayout(sub_font_style)
        sub_font_style_layout.setContentsMargins(0, 0, 0, 0)
        bold_check = QCheckBox(tr("sub_bold", "加粗"))
        bold_check.setObjectName("sub_bold_check")
        bold_check.setChecked(bool(sub_cfg.get('bold', False)))
        italic_check = QCheckBox(tr("sub_italic", "斜体"))
        italic_check.setObjectName("sub_italic_check")
        italic_check.setChecked(bool(sub_cfg.get('italic', False)))
        sub_font_style_layout.addWidget(bold_check)
        sub_font_style_layout.addWidget(italic_check)
        sub_font_style_layout.addStretch()
        sub_layout.addRow(tr("sub_font_style", "字形"), sub_font_style)

        sub_delay = QSpinBox()
        sub_delay.setObjectName("sub_delay_spin")
        sub_delay.setRange(-300000, 300000)
        sub_delay.setSingleStep(100)
        sub_delay.setSuffix(' ms')
        sub_delay.setMinimumHeight(28)
        try:
            delay_ms = int(round(float(sub_cfg.get('sub_delay', 0.0) or 0.0) * 1000))
        except (TypeError, ValueError):
            delay_ms = 0
        sub_delay.setValue(max(-300000, min(300000, delay_ms)))
        sub_layout.addRow(tr("sub_delay", "字幕延迟"), sub_delay)

        sub_scale = QSpinBox()
        sub_scale.setObjectName("sub_scale_spin")
        sub_scale.setRange(10, 1000)
        sub_scale.setSingleStep(10)
        sub_scale.setSuffix(' %')
        sub_scale.setMinimumHeight(28)
        try:
            scale_percent = int(round(float(sub_cfg.get('sub_scale', 1.0) or 1.0) * 100))
        except (TypeError, ValueError):
            scale_percent = 100
        sub_scale.setValue(max(10, min(1000, scale_percent)))
        sub_layout.addRow(tr("sub_scale", "字幕缩放"), sub_scale)

        sub_pos = QSlider(Qt.Orientation.Horizontal)
        sub_pos.setObjectName("sub_pos_slider")
        sub_pos.setRange(0, 100)
        sub_pos.setValue(int(sub_cfg.get('sub_pos', 100) or 0))
        sub_pos_label = QLabel(str(sub_pos.value()))
        sub_pos_label.setMinimumWidth(36)
        sub_pos.valueChanged.connect(
            lambda v, lbl=sub_pos_label: lbl.setText(str(v)))
        sub_pos_row = QWidget()
        sub_pos_layout = QHBoxLayout(sub_pos_row)
        sub_pos_layout.setContentsMargins(0, 0, 0, 0)
        sub_pos_layout.addWidget(sub_pos, 1)
        sub_pos_layout.addWidget(sub_pos_label)
        sub_layout.addRow(tr("sub_pos", "字幕位置"), sub_pos_row)

        sub_visibility = QCheckBox(tr("sub_visibility", "显示字幕"))
        sub_visibility.setObjectName("sub_visibility_check")
        sub_visibility.setChecked(bool(sub_cfg.get('sub_visibility', True)))
        sub_layout.addRow('', sub_visibility)
        layout.addRow(sub_box)

        hint = QLabel(tr(
            "playback_extras_hint",
            "图像、音频与字幕的完整参数（运动补偿、着色器、VU 电平、颜色与预设等）"
            "仍在播放页右键的同名对话框中调整，两处共用同一份配置。"
        ))
        hint.setWordWrap(True)
        hint.setStyleSheet(AppStyles.hint_label_style())
        layout.addRow(hint)

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

    def _reset_settings_defaults(self, dialog):
        """把当前设置页的控件恢复为默认值（仍需要点「保存」才落盘）。"""
        from services.mpv_common import DEFAULT_NETWORK_TIMEOUT_SEC

        def pick(name, value):
            combo = dialog.findChild(QComboBox, name)
            if combo is not None:
                idx = combo.findData(value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        pick('font_size_tier_combo', 'standard')
        pick('ui_scale_combo', 100)
        pick('rtsp_transport_combo', 'tcp')
        pick('hwdec_combo', 'auto-copy')
        pick('network_timeout_combo', DEFAULT_NETWORK_TIMEOUT_SEC)
        pick('audio_passthrough_combo', 'never')
        pick('hdr_output_mode_combo', 'disable')
        pick('vo_combo', 'auto')
        pick('video_sync_combo', 'audio')
        pick('close_behavior_combo', 'ask')
        pick('screensaver_idle_combo', 5)
        pick('github_proxy_combo', 'gh-proxy.com')
        pick('server_host_combo', '127.0.0.1')

        spin = dialog.findChild(QSpinBox, "server_port_spin")
        if spin is not None:
            spin.setValue(8080)

        check = dialog.findChild(QCheckBox, "tls_check")
        if check is not None:
            check.setChecked(False)
        check = dialog.findChild(QCheckBox, "server_auto_start_check")
        if check is not None:
            check.setChecked(False)
        check = dialog.findChild(QCheckBox, "screensaver_enabled_check")
        if check is not None:
            check.setChecked(True)
        check = dialog.findChild(QCheckBox, "github_proxy_enabled_check")
        if check is not None:
            check.setChecked(True)

        # 常规：语言与日志等级
        pick('language_combo', 'zh')
        pick('log_level_combo', 'INFO')
        # 外观：颜色模式与视觉风格
        pick('color_mode_combo', 'dark')
        pick('visual_style_combo', 'flat')
        # 网络：流媒体请求
        for edit_name in ('http_proxy_edit', 'http_referer_edit'):
            edit = dialog.findChild(QLineEdit, edit_name)
            if edit is not None:
                edit.clear()
        edit = dialog.findChild(QPlainTextEdit, "http_headers_edit")
        if edit is not None:
            edit.clear()
        # 播放行为
        pick('queue_mode_combo', 'none')
        for check_name in ('auto_skip_intro_check', 'auto_skip_outro_check',
                           'video_eq_reset_check', 'sub_bold_check', 'sub_italic_check'):
            check = dialog.findChild(QCheckBox, check_name)
            if check is not None:
                check.setChecked(False)
        for spin_name in ('skip_intro_seconds_spin', 'skip_outro_seconds_spin'):
            spin = dialog.findChild(QSpinBox, spin_name)
            if spin is not None:
                spin.setValue(0)
        check = dialog.findChild(QCheckBox, "sub_visibility_check")
        if check is not None:
            check.setChecked(True)

        # 播放页：视频/音频/字幕参数
        for key in ('brightness', 'contrast', 'saturation', 'hue', 'gamma'):
            slider = dialog.findChild(QSlider, f"video_eq_{key}_slider")
            if slider is not None:
                slider.setValue(0)
        slider = dialog.findChild(QSlider, "video_eq_sharpness_slider")
        if slider is not None:
            slider.setValue(0)
        pick('video_eq_rotate_combo', 0)
        pick('video_eq_flip_combo', '')
        slider = dialog.findChild(QSlider, "audio_eq_delay_slider")
        if slider is not None:
            slider.setValue(0)
        slider = dialog.findChild(QSlider, "audio_eq_pitch_slider")
        if slider is not None:
            slider.setValue(100)
        pick('audio_eq_channels_combo', 'auto')
        for i in range(10):
            slider = dialog.findChild(QSlider, f"audio_eq_band_{i}_slider")
            if slider is not None:
                slider.setValue(0)

        from core.stores.video_eq_store import VideoEqStore

        sub_defaults = VideoEqStore.SUBTITLE_STYLE_DEFAULTS
        spin = dialog.findChild(QSpinBox, "sub_font_size_spin")
        if spin is not None:
            spin.setValue(int(sub_defaults.get('font_size', 55)))
        spin = dialog.findChild(QSpinBox, "sub_border_size_spin")
        if spin is not None:
            spin.setValue(int(sub_defaults.get('border_size', 3)))
        spin = dialog.findChild(QSpinBox, "sub_shadow_offset_spin")
        if spin is not None:
            spin.setValue(int(sub_defaults.get('shadow_offset', 1)))
        spin = dialog.findChild(QSpinBox, "sub_delay_spin")
        if spin is not None:
            spin.setValue(int(round(float(sub_defaults.get('sub_delay', 0.0)) * 1000)))
        spin = dialog.findChild(QSpinBox, "sub_scale_spin")
        if spin is not None:
            spin.setValue(int(round(float(sub_defaults.get('sub_scale', 1.0)) * 100)))
        slider = dialog.findChild(QSlider, "sub_pos_slider")
        if slider is not None:
            slider.setValue(int(sub_defaults.get('sub_pos', 100)))

    def _save_and_close_settings(self, dialog):
        try:
            # 代理协议校验：Socks5 等 mpv 不支持的协议不允许保存成功，
            # 否则用户会以为已生效（实际 mpv 会忽略）。
            proxy_edit = dialog.findChild(QLineEdit, "http_proxy_edit")
            if isinstance(proxy_edit, QLineEdit):
                bad_proxy = self._invalid_proxy_text(proxy_edit.text())
                if bad_proxy:
                    QMessageBox.warning(
                        dialog,
                        self._tr("warning", "警告"),
                        self._tr(
                            "invalid_proxy_url",
                            "代理地址只支持 http:// 或 https://（当前为：{url}）。\n"
                            "socks5:// 不被 mpv 支持，请先在本机转成本地 HTTP 代理端口。"
                        ).format(url=bad_proxy)
                    )
                    proxy_edit.setFocus()
                    return

            # 订阅源在对话框内只改列表，因此用「打开对话框时」的配置做对比基线；
            # 保存时再读配置会拿到已改动后的值，导致改 URL 后不触发重新下载。
            old_playlist = getattr(dialog, '_old_playlist_sources', None)
            old_epg = getattr(dialog, '_old_epg_sources', None)
            old_active_index = getattr(dialog, '_old_active_playlist_index', None)
            if old_playlist is None:
                old_playlist = global_subscription_manager.get_playlist_sources()
            if old_epg is None:
                old_epg = global_subscription_manager.get_epg_sources()
            if old_active_index is None:
                old_active_index = global_subscription_manager.get_active_playlist_source_index()

            new_playlist = self._extract_sources_from_ui('playlist')
            new_epg = self._extract_sources_from_ui('epg')
            new_playback = self._extract_playback_settings(dialog)

            # 无条件写入：删光订阅源也要能保存为空
            global_subscription_manager._config.save_playlist_sources(new_playlist)
            global_subscription_manager._config.save_epg_sources(new_epg)

            self._save_intervals(dialog)
            self._save_close_behavior(dialog)
            self._save_screensaver_settings(dialog)
            self._save_github_proxy_settings(dialog)
            self._save_server_settings(dialog)
            self._save_detailed_media_settings(dialog)
            self._apply_playback_settings(new_playback)
            self._save_theme_choices(dialog)

            playlist_changed, new_active_index = self._check_playlist_changed(old_playlist, new_playlist, old_active_index)
            if playlist_changed:
                self._reload_playlist_async(new_playlist, new_active_index)

            if self._check_epg_changed(old_epg, new_epg):
                epg_thread = _EpgLoadThread(self.window)
                epg_thread.finished.connect(epg_thread.deleteLater)
                epg_thread.start()

            # 语言切换会重建菜单与界面文案，放到其余配置落盘之后
            self._save_general_app_settings(dialog)

            dialog.close()
            try:
                self.window.status_bar_show_message(self._tr("settings_saved", "设置已保存"), 3000)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"保存订阅设置失败: {e}")
            dialog.close()

    @staticmethod
    def _invalid_proxy_text(text: str) -> str:
        """返回不合法的代理地址原文；合法或留空时返回空串。"""
        if not isinstance(text, str):
            return ''
        text = text.strip()
        if not text:
            return ''
        parsed = urlparse(text)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
            return text
        return ''

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

        # 网络页「流媒体请求」
        edit = dialog.findChild(QLineEdit, "http_proxy_edit")
        if edit is not None:
            settings['http_proxy'] = edit.text().strip()
        edit = dialog.findChild(QLineEdit, "http_referer_edit")
        if edit is not None:
            settings['http_referer'] = edit.text().strip()
        edit = dialog.findChild(QPlainTextEdit, "http_headers_edit")
        if edit is not None:
            settings['http_headers'] = edit.toPlainText().strip()
        edit = dialog.findChild(QLineEdit, "user_agent_edit")
        if edit is not None:
            settings['user_agent'] = edit.text().strip()

        # 播放页「播放行为」
        combo = dialog.findChild(QComboBox, "queue_mode_combo")
        if combo is not None:
            settings['queue_mode'] = combo.currentData() or 'none'
        check = dialog.findChild(QCheckBox, "auto_skip_intro_check")
        if check is not None:
            settings['auto_skip_intro'] = check.isChecked()
        spin = dialog.findChild(QSpinBox, "skip_intro_seconds_spin")
        if spin is not None:
            settings['skip_intro_seconds'] = float(spin.value())
        check = dialog.findChild(QCheckBox, "auto_skip_outro_check")
        if check is not None:
            settings['auto_skip_outro'] = check.isChecked()
        spin = dialog.findChild(QSpinBox, "skip_outro_seconds_spin")
        if spin is not None:
            settings['skip_outro_seconds'] = float(spin.value())

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

    def _save_screensaver_settings(self, dialog):
        """写入屏保开关与等待时间，并触发热更新。"""
        config = self.window.config
        if not config:
            return
        check = dialog.findChild(QCheckBox, "screensaver_enabled_check")
        combo = dialog.findChild(QComboBox, "screensaver_idle_combo")
        enabled = check.isChecked() if check else True
        minutes = combo.currentData() if combo and combo.currentData() is not None else 5
        config.set_value('ScreenSaver', 'enabled', 'true' if enabled else 'false')
        config.set_value('ScreenSaver', 'idle_minutes', str(int(minutes)))
        config.save_config()
        ctrl = getattr(self.window, 'screensaver_controller', None)
        if ctrl is not None:
            try:
                ctrl.reload_config()
            except Exception as e:
                logger.debug(f"屏保配置热更新失败: {e}")

    def _save_github_proxy_settings(self, dialog):
        """写入 GitHub 加速代理开关与代理地址，立即生效（下次请求即按新配置改写）。"""
        check = dialog.findChild(QCheckBox, "github_proxy_enabled_check")
        combo = dialog.findChild(QComboBox, "github_proxy_combo")
        if check is None and combo is None:
            return
        from utils import github_proxy
        current = github_proxy.load_settings()
        enabled = check.isChecked() if check is not None else current['enabled']
        proxy = combo.currentData() if combo is not None and combo.currentData() else current['proxy']
        github_proxy.save_settings(enabled, proxy)

    def _save_server_settings(self, dialog):
        """写入 HTTP 服务设置（原独立对话框的保存逻辑，行为不变）。"""
        check = dialog.findChild(QCheckBox, "server_auto_start_check")
        spin = dialog.findChild(QSpinBox, "server_port_spin")
        combo = dialog.findChild(QComboBox, "server_host_combo")
        if check is None or spin is None or combo is None:
            return
        auto_start = check.isChecked()
        self.window.config.save_server_settings(
            enabled=auto_start,
            port=spin.value(),
            host=combo.currentData() or '127.0.0.1',
            auto_start=auto_start
        )

    def _save_general_app_settings(self, dialog):
        """写入常规页的语言与日志等级。"""
        import logging

        combo = dialog.findChild(QComboBox, "language_combo")
        lm = getattr(self.window, 'language_manager', None)
        if combo is not None and lm is not None:
            lang = combo.currentData()
            if lang and lang != getattr(lm, 'current_language', None):
                self.set_language(lang)

        combo = dialog.findChild(QComboBox, "log_level_combo")
        if combo is not None and self.window.config:
            name = combo.currentData() or 'INFO'
            levels = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
            }
            level = levels.get(name, logging.INFO)
            logger.set_level(level)
            self.window.config.set_value('UI', 'log_level', name)
            self.window.config.save_config()

    def _save_theme_choices(self, dialog):
        """写入外观页的颜色模式与视觉风格。"""
        theme_manager = get_theme_manager()
        combo = dialog.findChild(QComboBox, "color_mode_combo")
        if combo is not None and combo.currentData():
            mode = combo.currentData()
            if mode != theme_manager.get_color_mode():
                self.set_color_mode(mode)
        combo = dialog.findChild(QComboBox, "visual_style_combo")
        if combo is not None and combo.currentData():
            style = combo.currentData()
            if style != theme_manager.get_visual_style():
                self.set_visual_style(style)

    def _save_detailed_media_settings(self, dialog):
        """保存播放页的视频/音频/字幕参数。

        独立对话框可能持有旧 UI，保存后清掉缓存实例，下次打开会重新读取配置。
        """
        config = self.window.config
        if not config:
            return
        pc = self.window.player_controller

        def _slider(name):
            widget = dialog.findChild(QSlider, name)
            return widget.value() if widget is not None else None

        def _combo(name, cast=None):
            widget = dialog.findChild(QComboBox, name)
            if widget is None:
                return None
            value = widget.currentData()
            return cast(value) if cast is not None and value is not None else value

        def _spin_int(name):
            widget = dialog.findChild(QSpinBox, name)
            return widget.value() if widget is not None else None

        values = {
            key: _slider(f"video_eq_{key}_slider")
            for key in ('brightness', 'contrast', 'saturation', 'hue', 'gamma')
        }
        sharp_value = _slider("video_eq_sharpness_slider")
        rotate_value = _combo("video_eq_rotate_combo")
        flip_value = _combo("video_eq_flip_combo")
        reset_value = dialog.findChild(QCheckBox, "video_eq_reset_check")
        if any(v is not None for v in values.values()) or sharp_value is not None:
            video_cfg = config.load_video_eq()
            for key, value in values.items():
                if value is not None:
                    video_cfg[key] = int(value)
            if sharp_value is not None:
                video_cfg['sharpness'] = round(sharp_value / 100.0, 3)
            if rotate_value is not None:
                video_cfg['video_rotate'] = int(rotate_value)
            if flip_value is not None:
                video_cfg['video_flip'] = flip_value or ''
            if reset_value is not None:
                video_cfg['reset_on_new_file'] = reset_value.isChecked()
            config.save_video_eq(video_cfg)
            if pc is not None:
                try:
                    if hasattr(pc, 'apply_video_eq'):
                        pc.apply_video_eq(video_cfg)
                    if hasattr(pc, 'set_video_rotate'):
                        pc.set_video_rotate(int(video_cfg.get('video_rotate', 0) or 0))
                    if hasattr(pc, 'set_video_flip'):
                        pc.set_video_flip(video_cfg.get('video_flip', '') or '')
                except Exception as e:
                    logger.debug(f"应用视频调整失败: {e}")
            self.window._video_eq_dialog = None

        delay_value = _slider("audio_eq_delay_slider")
        pitch_value = _slider("audio_eq_pitch_slider")
        channels_value = _combo("audio_eq_channels_combo")
        band_values = [_slider(f"audio_eq_band_{i}_slider") for i in range(10)]
        if delay_value is not None or pitch_value is not None or channels_value is not None:
            audio_cfg = config.load_audio_eq()
            if delay_value is not None:
                audio_cfg['audio_delay'] = round(delay_value / 100.0, 3)
            if pitch_value is not None:
                audio_cfg['audio_pitch'] = round(pitch_value / 100.0, 3)
            if channels_value is not None:
                audio_cfg['audio_channels'] = channels_value or 'auto'
            if all(v is not None for v in band_values):
                audio_cfg['eq'] = [float(v) for v in band_values]
            config.save_audio_eq(audio_cfg)
            if pc is not None:
                try:
                    if hasattr(pc, 'apply_audio_eq'):
                        pc.apply_audio_eq(audio_cfg)
                except Exception as e:
                    logger.debug(f"应用音频调整失败: {e}")
            self.window._audio_eq_dialog = None

        font_size = _spin_int("sub_font_size_spin")
        border_size = _spin_int("sub_border_size_spin")
        shadow_offset = _spin_int("sub_shadow_offset_spin")
        sub_delay_ms = _spin_int("sub_delay_spin")
        sub_scale_percent = _spin_int("sub_scale_spin")
        sub_pos = _slider("sub_pos_slider")
        if any(v is not None for v in (font_size, border_size, shadow_offset,
                                       sub_delay_ms, sub_scale_percent, sub_pos)):
            sub_cfg = config.load_subtitle_style()
            if font_size is not None:
                sub_cfg['font_size'] = int(font_size)
            if border_size is not None:
                sub_cfg['border_size'] = int(border_size)
            if shadow_offset is not None:
                sub_cfg['shadow_offset'] = int(shadow_offset)
            bold = dialog.findChild(QCheckBox, "sub_bold_check")
            if bold is not None:
                sub_cfg['bold'] = bold.isChecked()
            italic = dialog.findChild(QCheckBox, "sub_italic_check")
            if italic is not None:
                sub_cfg['italic'] = italic.isChecked()
            if sub_delay_ms is not None:
                sub_cfg['sub_delay'] = round(sub_delay_ms / 1000.0, 3)
            if sub_scale_percent is not None:
                sub_cfg['sub_scale'] = round(sub_scale_percent / 100.0, 3)
            if sub_pos is not None:
                sub_cfg['sub_pos'] = int(sub_pos)
            visible = dialog.findChild(QCheckBox, "sub_visibility_check")
            if visible is not None:
                sub_cfg['sub_visibility'] = visible.isChecked()
            config.save_subtitle_style(sub_cfg)
            if pc is not None:
                try:
                    if hasattr(pc, 'apply_sub_style'):
                        pc.apply_sub_style(sub_cfg)
                    for setter, key in (
                        ('set_sub_delay', 'sub_delay'),
                        ('set_sub_scale', 'sub_scale'),
                        ('set_sub_pos', 'sub_pos'),
                        ('set_sub_visibility', 'sub_visibility'),
                    ):
                        if hasattr(pc, setter):
                            getattr(pc, setter)(sub_cfg.get(key))
                except Exception as e:
                    logger.debug(f"应用字幕样式失败: {e}")
            self.window._subtitle_style_dialog = None

    def _apply_playback_settings(self, new_playback):
        if not new_playback or not self.window.config:
            return
        old_playback = self.window.config.load_playback_settings()
        # 只覆盖本次界面涉及的键，保留用户通过独立对话框改过的未暴露键
        merged = dict(old_playback)
        merged.update(new_playback)
        self.window.config.save_playback_settings(merged)

        if 'queue_mode' in new_playback:
            qc = getattr(self.window, 'file_queue_ctrl', None)
            if qc is not None and new_playback['queue_mode'] != qc.queue_mode:
                try:
                    qc.set_queue_mode(new_playback['queue_mode'])
                except Exception as e:
                    logger.debug(f"同步循环模式失败: {e}")

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
                        # HDR 重建完成后继续应用同一次保存中的其余运行时参数，
                        # 不能提前返回导致后者被静默跳过

                    # 即时应用可运行时修改的参数（无需重启 mpv）
                    self._apply_runtime_playback_params(pc, old_playback, new_playback)
            except Exception as e:
                global_logger.debug(f"更新播放设置失败: {e}")

    @staticmethod
    def _apply_runtime_playback_params(pc, old_playback, new_playback):
        """即时应用可运行时修改的播放参数到 mpv。

        参数分类（基于 mpv 文档与项目代码）：
        - 运行时可改 property（framedrop/video-sync/hwdec/tls-verify/
          network-timeout/audio-passthrough）：直接 set_property_string 即时生效
        - 下次切台即生效（rtsp-transport/cache-secs/demuxer-*）：
          在 _setup_protocol_options 中每次播放时重新应用，无需此处处理
        - 必须重启 mpv 的 option（vo）：运行时改不生效，记录日志提示用户
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
                elif cfg_key == 'framedrop':
                    # 旧配置可能残留 insert/none/never（mpv 不认），即时应用时一并纠正
                    fd = str(new_val).lower()
                    if fd == 'yes':
                        fd = 'decoder+vo'
                    new_val = fd if fd in ('no', 'vo', 'decoder', 'decoder+vo') else 'vo'
                elif cfg_key == 'video_sync':
                    vs = str(new_val).lower()
                    if vs not in ('audio', 'display-resample', 'display-resample-vdrop',
                                  'display-resample-desync', 'display-tempo',
                                  'display-vdrop', 'display-adrop', 'display-desync', 'desync'):
                        vs = 'audio'
                    new_val = vs
                pc.set_property_string(mpv_prop, str(new_val))
            except Exception as e:
                global_logger.debug(f"即时应用 {mpv_prop}={new_val} 失败: {e}")

        # TLS 校验：mpv 支持运行时写入 tls-verify（已实测），不必重启
        old_tls = old_playback.get('tls_verify')
        new_tls = new_playback.get('tls_verify')
        if old_tls != new_tls and new_tls is not None:
            try:
                pc.set_property_string('tls-verify', 'yes' if new_tls else 'no')
            except Exception as e:
                global_logger.debug(f"即时应用 tls-verify={new_tls} 失败: {e}")

        # 网络超时：与看门狗同口径，Auto(0) 时也写入默认值（mpv 自身默认 60s）
        old_net = old_playback.get('network_timeout_sec')
        new_net = new_playback.get('network_timeout_sec')
        if old_net != new_net and new_net is not None:
            try:
                net_to = new_net if new_net and new_net > 0 else DEFAULT_NETWORK_TIMEOUT_SEC
                pc.set_property_string('network-timeout', str(net_to))
            except Exception as e:
                global_logger.debug(f"即时应用 network-timeout={new_net} 失败: {e}")

        # 反交错：auto 用 mpv 的 deinterlace=auto（FFmpeg 检测到隔行帧才插滤镜），
        # yes（旧配置）仍用 yadif bob 滤镜。
        old_di = old_playback.get('deinterlace', 'no')
        new_di = new_playback.get('deinterlace', 'no')
        if old_di != new_di:
            try:
                di_val = str(new_di).lower()
                if di_val == 'auto':
                    pc._disable_deinterlace_filter()
                    pc.set_property_string('deinterlace', 'auto')
                elif di_val == 'yes':
                    pc.set_property_string('deinterlace', 'no')
                    pc._enable_deinterlace_filter()
                else:
                    pc.set_property_string('deinterlace', 'no')
                    pc._disable_deinterlace_filter()
            except Exception as e:
                global_logger.debug(f"即时应用 deinterlace={new_di} 失败: {e}")

        # audio_passthrough 需要特殊处理（映射到 audio-spdif）
        old_pt = old_playback.get('audio_passthrough', 'never')
        new_pt = new_playback.get('audio_passthrough', 'never')
        if old_pt != new_pt:
            try:
                pt_val = AUDIO_SPDIF_MAP.get(new_pt, '') if new_pt else ''
                pc.set_property_string('audio-spdif', pt_val)
            except Exception as e:
                global_logger.debug(f"即时应用 audio-passthrough={new_pt} 失败: {e}")

        # 必须重启 mpv 的 option 变化记录日志（tls-verify/network-timeout 已改为运行时生效）
        restart_required_keys = ('vo',)
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

    def open_log_directory(self):
        """用系统文件管理器打开日志目录（app.log / crash.log 所在位置）。"""
        import subprocess
        import sys
        from utils.app_paths import get_log_dir
        from core.log_manager import global_logger as _logger

        log_dir = get_log_dir()
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            _logger.warning(f"创建日志目录失败: {log_dir}: {e}")
            QMessageBox.warning(
                self.window,
                self._tr("log_directory_title", "日志目录"),
                self._tr("log_directory_create_failed",
                         "无法创建日志目录：\n{path}").format(path=log_dir))
            return

        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', os.path.normpath(log_dir)])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', log_dir])
            else:
                subprocess.Popen(['xdg-open', log_dir])
        except OSError as e:
            _logger.warning(f"打开日志目录失败: {log_dir}: {e}")
            QMessageBox.information(
                self.window,
                self._tr("log_directory_title", "日志目录"),
                self._tr("log_directory_open_failed",
                         "无法自动打开文件管理器，请手动访问：\n{path}").format(path=log_dir))

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
                    if hasattr(w, 'status_bar_show_message'):
                        w.status_bar_show_message(
                            tr("temp_stream_added", "已作为临时串流添加到本地列表"), 4000)
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
        if hasattr(w, 'status_bar_show_message'):
            w.status_bar_show_message(
                tr("temp_stream_added", "已作为临时串流添加到本地列表"), 4000)