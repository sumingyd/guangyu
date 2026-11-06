from core.log_manager import global_logger as logger
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QIcon
from ui.styles import AppStyles
from utils.singleton import Singleton
from utils.platform_utils import is_windows, is_macos, is_android
import os


class ThemeManager(Singleton, QtCore.QObject):
    theme_changed = QtCore.Signal(str)
    color_mode_changed = QtCore.Signal(str)
    visual_style_changed = QtCore.Signal(str)

    def __init__(self):
        if self._initialized:
            return
        QtCore.QObject.__init__(self)
        self._windows = []
        from core.config_manager import ConfigManager
        self.config = ConfigManager()
        color_mode, visual_style = self.config.load_theme_settings()
        self._color_mode = color_mode if color_mode in AppStyles.AVAILABLE_COLOR_MODES else 'dark'
        self._visual_style = visual_style if visual_style in AppStyles.AVAILABLE_VISUAL_STYLES else 'flat'
        self._current_theme = f"{self._color_mode}+{self._visual_style}"
        AppStyles.set_color_mode(self._color_mode)
        AppStyles.set_visual_style(self._visual_style)
        self._system_theme_timer = None
        self._system_theme_style_hints = None
        if self._color_mode == 'auto':
            self._start_system_theme_watcher()
        self._initialized = True

    def _start_system_theme_watcher(self):
        if self._system_theme_timer is not None or self._system_theme_style_hints is not None:
            return
        self._last_detected_mode = AppStyles._detect_system_color_mode()
        try:
            style_hints = QGuiApplication.styleHints()
            style_hints.colorSchemeChanged.connect(self._check_system_theme_change)
            self._system_theme_style_hints = style_hints
            return
        except Exception as e:
            logger.debug(f"_start_system_theme_watcher: {e}")
        self._system_theme_timer = QtCore.QTimer(self)
        self._system_theme_timer.timeout.connect(self._check_system_theme_change)
        self._system_theme_timer.start(3000)

    def _stop_system_theme_watcher(self):
        if self._system_theme_timer is not None:
            self._system_theme_timer.stop()
            self._system_theme_timer = None
        if self._system_theme_style_hints is not None:
            try:
                self._system_theme_style_hints.colorSchemeChanged.disconnect(self._check_system_theme_change)
            except Exception as e:
                logger.debug(f"_stop_system_theme_watcher: {e}")
            self._system_theme_style_hints = None

    def _check_system_theme_change(self):
        if self._color_mode != 'auto':
            return
        detected = AppStyles._detect_system_color_mode()
        if detected != self._last_detected_mode:
            self._last_detected_mode = detected
            self._update_all_windows()
            self.theme_changed.emit(self._current_theme)

    def register_window(self, window: QtWidgets.QWidget):
        # 可见性变化（对话框复用时会反复 show/close）不应重复连接 destroyed
        if window not in self._windows:
            self._windows.append(window)
            window.destroyed.connect(lambda _=None, w=window: self.unregister_window(w))
        self._apply_theme_to_window(window)

    def unregister_window(self, window: QtWidgets.QWidget):
        if window in self._windows:
            self._windows.remove(window)

    def _update_all_windows(self):
        for window in list(self._windows):
            self._apply_theme_to_window(window)

    def _apply_theme_to_window(self, window: QtWidgets.QWidget):
        try:
            self._apply_window_backdrop(window)
            window.setUpdatesEnabled(False)
            window.setStyleSheet("")
            if isinstance(window, QtWidgets.QMainWindow):
                window.setStyleSheet(AppStyles.normalize_font_sizes(AppStyles.main_window_style()))
                self._update_child_widgets(window)
                self._reapply_main_window_components(window)
            elif isinstance(window, QtWidgets.QDialog):
                window.setStyleSheet(AppStyles.normalize_font_sizes(AppStyles.dialog_style()))
                self._update_child_widgets(window)
                if hasattr(window, 'reapply_styles'):
                    window.reapply_styles()
            window.setUpdatesEnabled(True)
            window.update()
            # 不再调用 QApplication.processEvents()：主题应用期间强制派发事件
            # 会重入正在进行的布局/绘制，导致主题切换闪烁甚至递归。
        except Exception as e:
            window.setUpdatesEnabled(True)
            logger.error(f"应用主题到窗口失败: {e}")

    def _apply_window_backdrop(self, window):
        try:
            is_frosted = AppStyles._visual_style == 'frosted'
            if isinstance(window, QtWidgets.QMainWindow):
                if is_frosted:
                    window.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
                    self._enable_dwm_blur(window)
                    for child in window.findChildren(QtWidgets.QDialog):
                        child.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
                        self._enable_dwm_blur(child)
                else:
                    window.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
                    self._disable_dwm_blur(window)
                    for child in window.findChildren(QtWidgets.QDialog):
                        child.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, False)
                        self._disable_dwm_blur(child)
                for dock_attr in ('epg_dock', 'playlist_dock', 'floating_dock'):
                    dock = getattr(window, dock_attr, None)
                    if dock:
                        dock.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
                        if is_frosted:
                            self._enable_dwm_blur(dock)
                        else:
                            self._disable_dwm_blur(dock)
        except Exception as e:
            logger.error(f"设置窗口背景模糊失败: {e}")

    def _enable_dwm_blur(self, window):
        if is_android():
            return
        if is_macos():
            if AppStyles._visual_style == 'frosted':
                from utils.mac_blur_helper import MacBlurHelper
                if not MacBlurHelper.apply(window, material="sidebar"):
                    window.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
            return
        if not is_windows():
            return
        try:
            import ctypes
            hwnd = int(window.winId())
            try:
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                dark = ctypes.c_int(1 if AppStyles._get_effective_color_mode() == 'dark' else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(dark), ctypes.sizeof(dark)
                )
            except Exception as e:
                logger.debug(f"_enable_dwm_blur: {e}")
            try:
                DWMWA_SYSTEMBACKDROP_TYPE = 38
                DWMSBT_MAINVIEW = 2
                value = ctypes.c_int(DWMSBT_MAINVIEW)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                    ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception as e:
                logger.debug(f"_enable_dwm_blur: {e}")
        except Exception as e:
            logger.debug(f"_enable_dwm_blur: {e}")

    def _disable_dwm_blur(self, window):
        if is_android():
            return
        if is_macos():
            from utils.mac_blur_helper import MacBlurHelper
            MacBlurHelper.remove(window)
            return
        if not is_windows():
            return
        try:
            import ctypes
            hwnd = int(window.winId())
            try:
                DWMWA_SYSTEMBACKDROP_TYPE = 38
                DWMSBT_NONE = 1
                value = ctypes.c_int(DWMSBT_NONE)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                    ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception as e:
                logger.debug(f"_disable_dwm_blur: {e}")
            try:
                class ACCENT_POLICY(ctypes.Structure):
                    _fields_ = [
                        ('AccentState', ctypes.c_int),
                        ('AccentFlags', ctypes.c_int),
                        ('GradientColor', ctypes.c_uint),
                        ('AnimationId', ctypes.c_int),
                    ]

                class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                    _fields_ = [
                        ('Attrib', ctypes.c_int),
                        ('pvData', ctypes.POINTER(ACCENT_POLICY)),
                        ('cbData', ctypes.c_size_t),
                    ]
                WCA_ACCENT_POLICY = 19
                accent = ACCENT_POLICY(0, 0, 0, 0)
                data = WINDOWCOMPOSITIONATTRIBDATA(WCA_ACCENT_POLICY, ctypes.pointer(accent), ctypes.sizeof(accent))
                ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
            except Exception as e:
                logger.debug(f"_disable_dwm_blur: {e}")
        except Exception as e:
            logger.debug(f"_disable_dwm_blur: {e}")


    def _reapply_main_window_components(self, window):
        """对主窗口的各区域组件逐一重刷样式，确保Dock/面板/标题栏/菜单栏都更新"""
        try:
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
                widget = getattr(window, attr, None)
                if widget:
                    widget.setStyleSheet(AppStyles.normalize_font_sizes(style_func()))

            self._reapply_title_bar_icons(window)

            for dock_attr in ['epg_dock', 'playlist_dock', 'floating_dock']:
                panel = getattr(window, dock_attr, None)
                if panel:
                    container = panel.widget()
                    if container and hasattr(container, 'setStyleSheet'):
                        container.setStyleSheet(AppStyles.normalize_font_sizes(AppStyles.player_panel_style()))
                        container.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
                        container.setAutoFillBackground(False)
                    panel.update()

            if hasattr(window, '_reapply_floating_panel_styles'):
                window._reapply_floating_panel_styles()
            if hasattr(window, '_reapply_side_panel_styles'):
                window._reapply_side_panel_styles()
            if hasattr(window, 'reapply_styles'):
                window.reapply_styles()

            pc = getattr(window, 'player_controller', None)
            if pc and hasattr(pc, 'player') and hasattr(pc.player, 'update_osd_theme'):
                pc.player.update_osd_theme()
        except Exception as e:
            logger.error(f"重刷主窗口组件样式失败: {e}")

    def _reapply_title_bar_icons(self, window):
        """主题切换时重新生成标题栏按钮图标，使图标颜色跟随主题变化"""
        try:
            window_ctrl = getattr(window, 'window_ctrl', None)
            if not window_ctrl:
                return
            btn_color = AppStyles._get_colors().get('window_text')
            icon_size = QSize(14, 14)
            btn_style = window_ctrl._title_btn_style()

            close_btn = getattr(window_ctrl, '_close_btn', None)
            if close_btn:
                icon_path = AppStyles.get_icon('close', btn_color, 14)
                if icon_path:
                    close_btn.setIcon(QIcon(icon_path))
                close_btn.setIconSize(icon_size)
                close_btn.setStyleSheet(btn_style)

            minimize_btn = getattr(window_ctrl, '_minimize_btn', None)
            if minimize_btn:
                icon_path = AppStyles.get_icon('minimize', btn_color, 14)
                if icon_path:
                    minimize_btn.setIcon(QIcon(icon_path))
                minimize_btn.setIconSize(icon_size)
                minimize_btn.setStyleSheet(btn_style)

            maximize_btn = getattr(window_ctrl, '_maximize_btn', None)
            if maximize_btn:
                is_maximized = window.isMaximized() if hasattr(window, 'isMaximized') else False
                icon_name = 'restore' if is_maximized else 'fullscreen'
                icon_path = AppStyles.get_icon(icon_name, btn_color, 14)
                if icon_path:
                    maximize_btn.setIcon(QIcon(icon_path))
                maximize_btn.setIconSize(icon_size)
                maximize_btn.setStyleSheet(btn_style)

            stay_on_top_btn = getattr(window_ctrl, '_stay_on_top_btn', None)
            if stay_on_top_btn:
                is_on_top = getattr(window_ctrl, '_stay_on_top_active', False)
                if is_on_top:
                    icon_path = AppStyles.get_icon('pin_active', btn_color, 14)
                    accent = AppStyles._get_colors().get('accent')
                    r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
                    stay_on_top_btn.setStyleSheet(
                        btn_style.replace("}", "") +
                        f" background-color: rgba({r}, {g}, {b}, 0.25); }}"
                    )
                else:
                    icon_path = AppStyles.get_icon('pin', btn_color, 14)
                    stay_on_top_btn.setStyleSheet(btn_style)
                if icon_path:
                    stay_on_top_btn.setIcon(QIcon(icon_path))
                stay_on_top_btn.setIconSize(icon_size)

            title_icon_label = getattr(window_ctrl, '_title_icon_label', None)
            if title_icon_label:
                from utils.general_utils import get_icon_path
                ico_path = get_icon_path()
                if os.path.exists(ico_path):
                    title_icon_label.setPixmap(QIcon(ico_path).pixmap(16, 16))
                else:
                    tv_icon_path = AppStyles.get_icon('tv', AppStyles._get_colors().get('accent'), 16)
                    if tv_icon_path:
                        title_icon_label.setPixmap(QIcon(tv_icon_path).pixmap(16, 16))
        except Exception as e:
            logger.error(f"重刷标题栏图标失败: {e}")

    def _is_in_dock(self, widget):
        w = widget.parent()
        while w:
            if isinstance(w, QtWidgets.QDockWidget):
                return True
            w = w.parent()
        return False

    def _is_in_managed_widget(self, widget):
        """检查控件是否在有独立样式管理的容器内（标题栏、菜单栏）。
        Dock内控件不再跳过，因为_reapply_main_window_components已确保Dock刷新。"""
        w = widget.parent()
        while w:
            if isinstance(w, QtWidgets.QMenuBar):
                return True
            if isinstance(w, QtWidgets.QWidget) and w.objectName() == "titleBar":
                return True
            w = w.parent()
        return False

    def _update_child_widgets(self, parent: QtWidgets.QWidget):
        style_map = {
            QtWidgets.QPushButton: lambda w: AppStyles.button_style() if not hasattr(w, 'style_type') else (
                AppStyles.apply_button_style() if w.style_type == 'apply' else
                AppStyles.cancel_button_style() if w.style_type == 'cancel' else
                AppStyles.button_style()
            ),
            QtWidgets.QTableView: lambda w: AppStyles.list_style(),
            QtWidgets.QTableWidget: lambda w: AppStyles.list_style(),
            QtWidgets.QListWidget: lambda w: AppStyles.player_list_style(),
            QtWidgets.QStatusBar: lambda w: AppStyles.statusbar_style(),
            QtWidgets.QTabWidget: lambda w: AppStyles.tab_widget_style(),
            QtWidgets.QToolButton: lambda w: (
                None if hasattr(w, 'style_type')
                else AppStyles.toolbar_button_style()
            ),
            QtWidgets.QLineEdit: lambda w: (
                AppStyles.common_line_edit_style()
                if (not w.styleSheet() or 'common_line_edit' not in w.styleSheet())
                else None
            ),
            QtWidgets.QComboBox: lambda w: (
                AppStyles.common_combo_box_style()
                if (not w.styleSheet() or 'common_combo' not in w.styleSheet())
                else None
            ),
            QtWidgets.QLabel: lambda w: (
                AppStyles.label_style() if hasattr(AppStyles, 'label_style') else None
            ),
            QtWidgets.QCheckBox: lambda w: AppStyles.common_check_box_style(),
            QtWidgets.QRadioButton: lambda w: (
                AppStyles.common_radio_button_style()
                if hasattr(AppStyles, 'common_radio_button_style') else None
            ),
            QtWidgets.QProgressBar: lambda w: AppStyles.progress_style(),
            QtWidgets.QGroupBox: lambda w: AppStyles.common_group_box_style(),
            QtWidgets.QScrollArea: lambda w: (
                AppStyles.scroll_area_style()
                if hasattr(AppStyles, 'scroll_area_style') else None
            ),
            QtWidgets.QSlider: lambda w: (
                AppStyles.player_slider_style()
                if hasattr(AppStyles, 'player_slider_style') else None
            ),
            QtWidgets.QTextEdit: lambda w: (
                AppStyles.text_edit_style()
                if hasattr(AppStyles, 'text_edit_style') else None
            ),
            QtWidgets.QFrame: lambda w: None if hasattr(w, 'style_type') else None,
        }
        spin_style = AppStyles.common_spin_box_style() if hasattr(AppStyles, 'common_spin_box_style') else None
        if spin_style:
            spin_style = AppStyles.normalize_font_sizes(spin_style)

        all_widgets = parent.findChildren(QtWidgets.QWidget)
        for widget in all_widgets:
            if self._is_in_managed_widget(widget):
                continue
            widget_type = type(widget)
            style_func = style_map.get(widget_type)
            if style_func:
                try:
                    style = style_func(widget)
                    if style:
                        new_style = AppStyles.normalize_font_sizes(style)
                        if widget.styleSheet() != new_style:
                            widget.setStyleSheet(new_style)
                except Exception as e:
                    logger.debug(f"_update_child_widgets: {e}")
            elif widget_type is QtWidgets.QSpinBox and spin_style:
                try:
                    if widget.styleSheet() != spin_style:
                        widget.setStyleSheet(spin_style)
                except Exception as e:
                    logger.debug(f"_update_child_widgets: {e}")


    def get_current_theme(self) -> str:
        return self._current_theme

    def get_color_mode(self) -> str:
        return self._color_mode

    def get_visual_style(self) -> str:
        return self._visual_style

    def get_available_color_modes(self) -> list:
        return AppStyles.AVAILABLE_COLOR_MODES

    def get_available_visual_styles(self) -> list:
        return AppStyles.AVAILABLE_VISUAL_STYLES

    def set_color_mode(self, mode: str):
        if mode not in AppStyles.AVAILABLE_COLOR_MODES:
            return
        self._color_mode = mode
        AppStyles.set_color_mode(mode)
        self._current_theme = f"{self._color_mode}+{self._visual_style}"
        self.config.save_theme_settings(self._color_mode, self._visual_style)
        if mode == 'auto':
            self._start_system_theme_watcher()
        else:
            self._stop_system_theme_watcher()
        self._update_all_windows()
        self.color_mode_changed.emit(mode)
        self.theme_changed.emit(self._current_theme)

    def set_visual_style(self, style: str):
        if style not in AppStyles.AVAILABLE_VISUAL_STYLES:
            return
        self._visual_style = style
        AppStyles.set_visual_style(style)
        self._current_theme = f"{self._color_mode}+{self._visual_style}"
        self.config.save_theme_settings(self._color_mode, self._visual_style)
        self._update_all_windows()
        self.visual_style_changed.emit(style)
        self.theme_changed.emit(self._current_theme)

    def set_theme(self, theme_name: str):
        if theme_name in AppStyles._OLD_THEME_MAPPING:
            self._color_mode, self._visual_style = AppStyles._OLD_THEME_MAPPING[theme_name]
        elif '+' in theme_name:
            parts = theme_name.split('+')
            if len(parts) == 2:
                self._color_mode = parts[0] if parts[0] in AppStyles.AVAILABLE_COLOR_MODES else 'dark'
                self._visual_style = parts[1] if parts[1] in AppStyles.AVAILABLE_VISUAL_STYLES else 'flat'
        else:
            self._color_mode = theme_name if theme_name in AppStyles.AVAILABLE_COLOR_MODES else 'dark'
            self._visual_style = 'flat'
        AppStyles.set_color_mode(self._color_mode)
        AppStyles.set_visual_style(self._visual_style)
        self._current_theme = f"{self._color_mode}+{self._visual_style}"
        self.config.save_theme_settings(self._color_mode, self._visual_style)
        if self._color_mode == 'auto':
            self._start_system_theme_watcher()
        else:
            self._stop_system_theme_watcher()
        self._update_all_windows()
        self.theme_changed.emit(self._current_theme)

    def get_available_themes(self) -> list:
        return AppStyles.get_available_themes()


theme_manager = None


def get_theme_manager() -> ThemeManager:
    global theme_manager
    if theme_manager is None:
        theme_manager = ThemeManager()
    return theme_manager


def safe_register_window(window):
    try:
        get_theme_manager().register_window(window)
    except Exception as e:
        logger.debug(f"safe_register_window: {e}")


def safe_unregister_window(window):
    try:
        get_theme_manager().unregister_window(window)
    except Exception as e:
        logger.debug(f"safe_unregister_window: {e}")
