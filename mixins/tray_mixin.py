from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from core.log_manager import global_logger as logger
from utils.platform_utils import is_macos, is_android


class TrayMixin:

    def _setup_system_tray(self):
        if is_macos():
            self._setup_macos_dock_restore()
        if is_android():
            self._system_tray = None
            self._tray_available = False
            self._is_hidden_to_tray = False
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # GNOME 默认没有托盘/AppIndicator，此时隐藏主窗口会让程序"消失"且
            # 无法从托盘找回（静默失败），改为不创建托盘并降级为最小化。
            self._system_tray = None
            self._tray_available = False
            self._is_hidden_to_tray = False
            logger.warning("当前桌面环境没有可用的系统托盘，关闭窗口时将改为最小化到任务栏")
            return
        self._tray_available = True
        import os
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_candidates = []
        if is_macos():
            icon_candidates.append(os.path.join(project_dir, 'resources', 'logo.icns'))
            icon_candidates.append(os.path.join(project_dir, 'resources', 'logo.png'))
        icon_candidates.append(os.path.join(project_dir, 'resources', 'logo.ico'))
        icon_path = None
        for p in icon_candidates:
            if os.path.exists(p):
                icon_path = p
                break
        icon = QIcon(icon_path) if icon_path else QIcon()
        self._system_tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        tr = self.language_manager.tr
        show_action = tray_menu.addAction(tr('tray_show', '显示主窗口'))
        show_action.triggered.connect(self._tray_show_window)
        tray_menu.addSeparator()

        play_pause_action = tray_menu.addAction(tr('tray_play_pause', '播放/暂停'))
        play_pause_action.triggered.connect(self._tray_play_pause)
        prev_ch_action = tray_menu.addAction(tr('tray_prev', '上一频道'))
        prev_ch_action.triggered.connect(self._tray_prev_channel)
        next_ch_action = tray_menu.addAction(tr('tray_next', '下一频道'))
        next_ch_action.triggered.connect(self._tray_next_channel)
        mute_action = tray_menu.addAction(tr('tray_mute', '静音'))
        mute_action.triggered.connect(self._tray_toggle_mute)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction(tr('tray_quit', '退出程序'))
        quit_action.triggered.connect(self._tray_quit)
        self._system_tray.setContextMenu(tray_menu)
        self._system_tray.activated.connect(self._on_tray_activated)
        self._is_hidden_to_tray = False

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show_window()

    def _setup_macos_dock_restore(self):
        """macOS 上最小化到托盘后，点击 Dock 图标应恢复窗口。

        macOS 没有 Windows 那样的托盘双击习惯，用户会点 Dock 图标。
        Qt 在 Dock 重新激活应用时会给 QApplication 投递 ApplicationActivate /
        ApplicationStateChange 事件，这里据此把隐藏的主窗口找回来。
        """
        if getattr(self, '_mac_dock_restore_filter', None) is not None:
            return
        try:
            from PySide6.QtCore import QEvent, QObject, QTimer
            from PySide6.QtWidgets import QApplication
        except ImportError as e:
            logger.debug(f"安装 macOS Dock 恢复监听失败: {e}")
            return

        owner = self

        class _DockRestoreFilter(QObject):
            def eventFilter(self, obj, event):
                etype = event.type()
                if etype == QEvent.Type.ApplicationActivate:
                    QTimer.singleShot(0, owner._restore_from_dock_if_hidden)
                elif etype == QEvent.Type.ApplicationStateChange:
                    try:
                        if event.applicationState() == Qt.ApplicationState.ApplicationActive:
                            QTimer.singleShot(0, owner._restore_from_dock_if_hidden)
                    except Exception:
                        pass
                return False

        app = QApplication.instance()
        if app is None:
            return
        dock_filter = _DockRestoreFilter(app)
        app.installEventFilter(dock_filter)
        self._mac_dock_restore_filter = dock_filter

    def _restore_from_dock_if_hidden(self):
        if getattr(self, '_is_hidden_to_tray', False) and not self.isVisible():
            logger.info("检测到 Dock 重新激活，恢复隐藏到托盘的主窗口")
            self._tray_show_window()

    def _tray_show_window(self):
        self._is_hidden_to_tray = False
        self.show()
        self.activateWindow()
        self.raise_()
        for dock_name in getattr(self, '_tray_hidden_docks', []):
            dock = getattr(self, dock_name, None)
            if dock:
                dock.show()
                dock.setFloating(True)
        # 隐藏到托盘时若正在播放而暂停，恢复窗口后继续播放
        if getattr(self, '_was_playing_before_tray', False):
            pc = getattr(self, 'player_controller', None)
            if pc:
                pc.play()
            self._was_playing_before_tray = False

    def _tray_quit(self):
        self._force_quit = True
        self._is_hidden_to_tray = False
        self.close()

    def _tray_play_pause(self):
        pc = getattr(self, 'player_controller', None)
        if pc:
            if pc.is_playing and not pc.is_paused:
                pc.pause()
            else:
                pc.play()

    def _tray_prev_channel(self):
        if hasattr(self, '_switch_channel_safe'):
            self._switch_channel_safe(-1)

    def _tray_next_channel(self):
        if hasattr(self, '_switch_channel_safe'):
            self._switch_channel_safe(1)

    def _tray_toggle_mute(self):
        if hasattr(self, 'toggle_mute'):
            self.toggle_mute()

    def _do_close_minimize_tray(self):
        tray = getattr(self, '_system_tray', None)
        if tray is None or not getattr(self, '_tray_available', True):
            # 没有托盘时隐藏窗口会让程序无法找回，降级为最小化到任务栏
            self._is_hidden_to_tray = False
            self.showMinimized()
            return
        tr = self.language_manager.tr
        self._is_hidden_to_tray = True
        pc = self.player_controller
        if pc and pc.is_playing and not pc.is_paused:
            pc.pause()
            self._was_playing_before_tray = True
        else:
            self._was_playing_before_tray = False
        self._tray_hidden_docks = []
        for dock_name in ('epg_dock', 'playlist_dock', 'floating_dock'):
            dock = getattr(self, dock_name, None)
            if dock and dock.isVisible():
                self._tray_hidden_docks.append(dock_name)
                dock.blockSignals(True)
                dock.setFloating(False)
                dock.blockSignals(False)
        self.hide()
        tray = self._system_tray
        if tray:
            tray.show()
            tray.setToolTip(tr('app_title', 'GuangYu'))