from PySide6.QtWidgets import (QDialog, QDockWidget, QWidget,
                               QHBoxLayout, QLabel, QPushButton)
from PySide6 import QtWidgets
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QCursor, QIcon, QBitmap,
                           QPixmap)
from PySide6.QtCore import Qt, QRectF, QSize
import PySide6.QtCore as QtCore
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton
from utils.platform_utils import is_windows, is_macos, is_android, is_linux, is_wayland, wayland_move
from utils.delay_constants import DelayMs
from utils.thread_safety import safe_single_shot


def _notify_main_window_activity(widget):
    """浮动面板/对话框是独立顶层窗口，鼠标活动不经过主窗口事件，需主动转发。

    全屏下主窗口依赖该通知恢复面板并重置自动隐藏计时器。
    """
    try:
        win = widget.parent()
        if win is None or win is widget:
            return
        callback = getattr(win, '_on_mouse_activity', None)
        if callable(callback):
            callback()
    except RuntimeError:
        pass


def _hide_from_taskbar(window):
    if is_windows():
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            hwnd = int(window.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass


def _parse_hex_color(hex_str, default=(0, 0, 0)):
    try:
        from ui.styles import color_to_qcolor
        c = color_to_qcolor(hex_str)
        if c.isValid():
            return c.red(), c.green(), c.blue()
    except Exception:
        pass
    return default


def _blur_pixmap(pixmap: QPixmap, radius: int = 24) -> QPixmap:
    """对背景快照做高斯模糊，作为无系统模糊平台上的玻璃兜底。"""
    try:
        from PySide6.QtWidgets import (QGraphicsScene, QGraphicsPixmapItem,
                                       QGraphicsBlurEffect)
        effect = QGraphicsBlurEffect()
        effect.setBlurRadius(radius)
        effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        item = QGraphicsPixmapItem(pixmap)
        item.setGraphicsEffect(effect)
        scene = QGraphicsScene()
        scene.addItem(item)
        out = QPixmap(pixmap.size())
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        scene.render(painter, QRectF(out.rect()), QRectF(pixmap.rect()))
        painter.end()
        return out
    except Exception:
        return pixmap


class _GlassSurfaceMixin:
    """玻璃卡片的统一实现：透明度解析、平台模糊、背景快照兜底、圆角 mask。

    dock 与 dialog 共用同一套语义：
    - 玻璃风格（frosted/win11/mac/ios）必须有真模糊；
    - 其余风格使用 alpha 255 的实色卡片，不再停在"半透明无模糊"的中间态。
    """

    _bg_color_key = 'window'
    _border_color_key = 'mid'

    def _init_glass_surface(self):
        self._dwm_blur_enabled = getattr(self, '_dwm_blur_enabled', False)
        self._backdrop = None
        self._backdrop_offset = QtCore.QPoint(0, 0)
        self._capturing_backdrop = False
        self._mask_key = None
        self._dwm_blur_checked = False
        self._glass_timer = QtCore.QTimer(self)
        self._glass_timer.setSingleShot(True)
        self._glass_timer.setInterval(180)
        self._glass_timer.timeout.connect(self._refresh_backdrop_if_needed)

    def _glass_active(self) -> bool:
        from ui.styles import AppStyles
        return AppStyles.is_glass_style() and not is_android()

    def _card_alpha(self) -> int:
        from ui.styles import AppStyles
        if not AppStyles.is_glass_style():
            return 255
        if AppStyles._visual_style == 'frosted':
            try:
                colors = AppStyles._get_colors()
                return int(max(0.35, min(0.72, float(colors.get('frosted_opacity', 0.66)))) * 255)
            except Exception:
                return 168
        return 168

    def _update_glass_mask(self):
        """统一卡面圆角裁切：dock 与 dialog、玻璃与非玻璃风格使用同一套 mask。

        非玻璃风格过去直接 clearMask()，矩形内部控件（列表/页签）会溢出卡面的
        圆角，看起来就成了"直角实心块"；现在所有风格都按同一圆角裁切。
        """
        from ui.styles import AppStyles
        try:
            size = self.size()
            if size.width() <= 0 or size.height() <= 0:
                return
            corner_r = AppStyles._get_style_border_radius()
            mask_key = (size.width(), size.height(), corner_r)
            if mask_key == getattr(self, '_mask_key', None):
                return
            self._mask_key = mask_key
            bitmap = QBitmap(size)
            bitmap.fill(QtCore.Qt.GlobalColor.color0)
            p = QPainter(bitmap)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QtCore.Qt.GlobalColor.color1)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), corner_r, corner_r)
            p.drawPath(path)
            p.end()
            self.setMask(bitmap)
            # 实测：窗口尺寸变化后 setMask 会重建窗口区域，但不会触发重绘，
            # 逐像素半透明的顶层窗口此时没有新的 layer 内容，会露出后面的视频，
            # 表现为"卡面整块消失、只剩原始画面"。这里主动标脏整窗补一次绘制。
            self.update()
        except Exception:
            pass

    def _try_enable_macos_blur(self):
        try:
            from ui.styles import AppStyles
            from utils.mac_blur_helper import MacBlurHelper
            self._dwm_blur_checked = True
            if not self._glass_active():
                self._dwm_blur_enabled = False
                MacBlurHelper.remove(self)
                return
            if self._dwm_blur_enabled:
                return
            self._dwm_blur_enabled = bool(MacBlurHelper.apply(self, material="menu"))
        except Exception:
            self._dwm_blur_enabled = False

    def _try_enable_dwm_blur(self):
        if is_android():
            return
        if is_macos():
            self._try_enable_macos_blur()
            return
        if not is_windows():
            return
        try:
            import ctypes
            from ui.styles import AppStyles
            if not self._glass_active():
                # 非玻璃风格同样要"确保关闭"，否则外部设过的 Mica 会一直留着。
                self._disable_dwm_blur()
                self._dwm_blur_enabled = False
                self._dwm_blur_checked = True
                self._update_glass_mask()
                return
            if self._dwm_blur_checked and not self._dwm_blur_enabled:
                return
            # Windows 上不再使用 DWMWA_SYSTEMBACKDROP_TYPE（Mica）。
            # 实测：Mica 启用后窗口背景变成基于壁纸的系统材质，是实心不透明的，
            # 窗后面的视频永远不会参与合成（红/蓝棋盘两点采样完全相同）；
            # 逐像素 alpha 本身是正常的（同一探针去掉 Mica 后两点分别透出红/蓝）。
            # 因此这里保持逐像素半透明，由 paintEvent 的卡片色叠到真实背景上。
            #
            # 注意：这里必须真正下发 DWMSBT_NONE，而不是只把 _dwm_blur_checked
            # 置 True 就早退——Mica 可能已被外部（ThemeManager）设到同一个 hwnd 上，
            # 只置标志位会让已有的 Mica 永久保留，面板就永远透不出视频。
            self._disable_dwm_blur()
            self._dwm_blur_enabled = False
            self._dwm_blur_checked = True
            self._update_glass_mask()
        except Exception:
            pass

    def _disable_dwm_blur(self):
        if is_android():
            return
        if is_macos():
            self._dwm_blur_enabled = False
            return
        if not is_windows():
            return
        try:
            import ctypes
            from core.log_manager import global_logger as logger
            hwnd = int(self.winId())
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMSBT_NONE = 1
            value = ctypes.c_int(DWMSBT_NONE)
            hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(value), ctypes.sizeof(value)
            )
            logger.debug(
                f"_disable_dwm_blur: backdrop=NONE hwnd={hwnd} hr=0x{hr & 0xffffffff:08X}"
            )
        except Exception as e:
            try:
                from core.log_manager import global_logger as logger
                logger.debug(f"_disable_dwm_blur: {e}")
            except Exception:
                pass

    def _capture_backdrop(self):
        """抓取窗口背后区域的快照并模糊；只在没有系统模糊时使用。

        Windows 上直接跳过：实测 QWidget.grab() 抓不到 mpv 的 QOpenGLWidget
        画面（抓到的是黑/近黑），拿它当玻璃底会把视频盖成一块暗板。
        因此 Windows 走纯逐像素半透明，底就是真实视频。
        """
        from ui.styles import AppStyles
        if is_windows():
            self._backdrop = None
            return
        if self._dwm_blur_enabled or not AppStyles.is_glass_style():
            self._backdrop = None
            return
        if getattr(self, '_capturing_backdrop', False):
            return
        self._capturing_backdrop = True
        try:
            win = self.parentWidget() or self.parent()
            while win is not None and win.parentWidget() is not None:
                win = win.parentWidget()
            if win is None or win is self or not win.isVisible():
                self._backdrop = None
                return
            origin = self.mapToGlobal(self.rect().topLeft())
            top_left = win.mapFromGlobal(origin)
            rect = QtCore.QRect(top_left, self.size()).intersected(win.rect())
            if rect.width() < 2 or rect.height() < 2:
                self._backdrop = None
                return
            pm = win.grab(rect)
            self._backdrop = _blur_pixmap(pm, 24)
            self._backdrop_offset = top_left - rect.topLeft()
        except Exception:
            self._backdrop = None
        finally:
            self._capturing_backdrop = False

    def _refresh_backdrop_if_needed(self):
        from ui.styles import AppStyles
        # Windows 走纯逐像素 alpha，没有可用的快照底（见 _capture_backdrop），
        # 不再每 180ms 触发一次无意义重绘。
        if is_windows():
            return
        if self.isVisible() and AppStyles.is_glass_style() and not self._dwm_blur_enabled:
            self._capture_backdrop()
            self.update()

    def refresh_glass_surface(self):
        """主题切换后重新解析卡片语义（模糊 / 实色 / mask / 快照）。"""
        self._cached_frosted_colors = None
        self._cached_frosted_theme = None
        self._backdrop = None
        self._dwm_blur_enabled = False
        self._mask_key = None
        self._dwm_blur_checked = False
        self._try_enable_dwm_blur()
        self._update_glass_mask()
        self._glass_timer.start()
        self.update()

    def _paint_card(self, painter: QPainter, colors: dict):
        from ui.styles import AppStyles
        corner_r = AppStyles._get_style_border_radius()
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), corner_r, corner_r)

        glass = AppStyles.is_glass_style()
        if glass and not self._dwm_blur_enabled and self._backdrop is not None:
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(self._backdrop_offset, self._backdrop)
            painter.restore()

        r, g, b = _parse_hex_color(colors.get(self._bg_color_key, '#333333'))
        painter.fillPath(path, QColor(r, g, b, self._card_alpha()))

        # 面板背后是任意亮度的视频画面，固定 51% 的深色卡面叠在亮画面（天空、白墙）
        # 上时对比度会掉到 1~3:1，文字看起来"发虚"。Windows 上拿不到真实背景亮度，
        # 所以统一补一层 25% 黑 scrim，把最坏情况的底色压暗，文字回到可读区间。
        # 浅色主题不加，避免把浅色卡片压灰。
        if glass and AppStyles._get_effective_color_mode() == 'dark':
            painter.fillPath(path, QColor(0, 0, 0, 64))

        lr, lg, lb = _parse_hex_color(colors.get(self._border_color_key, '#646464'))
        if AppStyles.is_neumorphic():
            painter.setPen(QColor(lr, lg, lb, 60))
            painter.drawPath(path)
        elif glass:
            mode = AppStyles._get_effective_color_mode()
            painter.setPen(QColor(255, 255, 255, 52) if mode == 'dark' else QColor(0, 0, 0, 34))
            painter.drawPath(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_glass_mask()
        if hasattr(self, '_glass_timer'):
            self._glass_timer.start()


class FloatingDockWidget(_GlassSurfaceMixin, QDockWidget):
    """浮动停靠窗口 - QDockWidget 子控件模式（用于诊断对比）"""

    _RESIZE_MARGIN = 8
    _bg_color_key = 'player_panel'
    _border_color_key = 'mid'

    def __init__(self, title, parent=None, opacity=130):
        super().__init__(title, parent)
        self._opacity = opacity
        self._base_title = title
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.topLevelChanged.connect(self._on_floating_changed)
        empty_bar = QWidget()
        empty_bar.setFixedHeight(0)
        self.setTitleBarWidget(empty_bar)
        self._dwm_blur_enabled = False
        self._cached_frosted_colors = None
        self._cached_frosted_theme = None
        self._resizing = False
        self._resize_edge = None
        self._resize_start_geo = None
        self._resize_start_pos = None
        self._init_glass_surface()

    def _card_alpha(self) -> int:
        """三块悬浮面板的卡面透明度按重构前的基准恢复。

        重构前 FloatingDockWidget 以构造参数 opacity=130（约 51%）逐像素填充，
        面板能明显透出底下的视频；重构后被抬到 168/199 并叠加 Mica，
        观感变成实心。这里按 130 恢复，非玻璃风格仍保持不透明。
        """
        from ui.styles import AppStyles
        if not AppStyles.is_glass_style():
            return 255
        return 130

    def _set_transient_parent(self):
        try:
            parent_window = self.parent()
            if parent_window is None:
                return
            parent_handle = parent_window.windowHandle()
            if parent_handle is None:
                parent_window.createWinId()
                parent_handle = parent_window.windowHandle()
            if parent_handle:
                self_handle = self.windowHandle()
                if self_handle is None:
                    self.createWinId()
                    self_handle = self.windowHandle()
                if self_handle:
                    self_handle.setTransientParent(parent_handle)
        except Exception:
            pass

    def _on_floating_changed(self, floating):
        if floating:
            flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            if self.parent() and (self.parent().windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
                flags |= Qt.WindowType.WindowStaysOnTopHint
            # dock 与 dialog 统一：始终透明底，卡面圆角由 _paint_card + mask 负责，
            # 不再按玻璃/非玻璃分叉透明策略。
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # 重建原生窗口会丢弃 mask，重置缓存以便 show() 重新裁切圆角
            self._mask_key = None
            self._dwm_blur_checked = False
            if is_linux():
                self._set_transient_parent()
            self.show()

    def show(self):
        super().show()
        _hide_from_taskbar(self)
        self._mask_key = None
        self._dwm_blur_checked = False
        self._try_enable_dwm_blur()
        self._update_glass_mask()
        if hasattr(self, '_glass_timer'):
            self._glass_timer.start()

    def _hit_resize_edge(self, pos):
        m = self._RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m
        if on_top and on_left:
            return 'top_left'
        if on_top and on_right:
            return 'top_right'
        if on_bottom and on_left:
            return 'bottom_left'
        if on_bottom and on_right:
            return 'bottom_right'
        if on_left:
            return 'left'
        if on_right:
            return 'right'
        if on_top:
            return 'top'
        if on_bottom:
            return 'bottom'
        return None

    def _edge_cursor(self, edge):
        cursors = {
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'top_left': Qt.CursorShape.SizeFDiagCursor,
            'bottom_right': Qt.CursorShape.SizeFDiagCursor,
            'top_right': Qt.CursorShape.SizeBDiagCursor,
            'bottom_left': Qt.CursorShape.SizeBDiagCursor,
        }
        return cursors.get(edge, Qt.CursorShape.ArrowCursor)

    def enterEvent(self, event):
        _notify_main_window_activity(self)
        super().enterEvent(event)

    def mousePressEvent(self, event):
        _notify_main_window_activity(self)
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._hit_resize_edge(event.position().toPoint())
            if edge:
                if is_wayland():
                    wh = self.windowHandle()
                    if wh:
                        edges_map = {
                            'top': Qt.Edge.TopEdge,
                            'bottom': Qt.Edge.BottomEdge,
                            'left': Qt.Edge.LeftEdge,
                            'right': Qt.Edge.RightEdge,
                            'top_left': Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                            'top_right': Qt.Edge.TopEdge | Qt.Edge.RightEdge,
                            'bottom_left': Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
                            'bottom_right': Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
                        }
                        qt_edge = edges_map.get(edge)
                        if qt_edge:
                            wh.startSystemResize(qt_edge)
                            return
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        _notify_main_window_activity(self)
        if self._resizing and self._resize_edge and self._resize_start_geo and self._resize_start_pos:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = self._resize_start_geo.__class__(self._resize_start_geo)
            edge = self._resize_edge
            min_w = self.minimumWidth() if self.minimumWidth() > 0 else 200
            min_h = self.minimumHeight() if self.minimumHeight() > 0 else 150
            if 'right' in edge:
                new_w = max(min_w, self._resize_start_geo.width() + delta.x())
                geo.setWidth(new_w)
            if 'left' in edge:
                new_w = max(min_w, self._resize_start_geo.width() - delta.x())
                geo.setX(self._resize_start_geo.x() + self._resize_start_geo.width() - new_w)
                geo.setWidth(new_w)
            if 'bottom' in edge:
                new_h = max(min_h, self._resize_start_geo.height() + delta.y())
                geo.setHeight(new_h)
            if 'top' in edge:
                new_h = max(min_h, self._resize_start_geo.height() - delta.y())
                geo.setY(self._resize_start_geo.y() + self._resize_start_geo.height() - new_h)
                geo.setHeight(new_h)
            self.setGeometry(geo)
            return
        edge = self._hit_resize_edge(event.position().toPoint())
        if edge:
            self.setCursor(QCursor(self._edge_cursor(edge)))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._resizing:
            self._resizing = False
            self._resize_edge = None
            self._resize_start_geo = None
            self._resize_start_pos = None
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        from ui.styles import AppStyles, rgba_to_blended_hex

        if not self._dwm_blur_enabled and AppStyles.is_glass_style():
            self._try_enable_dwm_blur()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = AppStyles._get_colors()

        if AppStyles._visual_style == 'frosted':
            current_theme = AppStyles._current_theme
            if self._cached_frosted_theme != current_theme:
                effective_mode = AppStyles._get_effective_color_mode()
                bg = (0, 0, 0) if effective_mode == 'dark' else (255, 255, 255)
                self._cached_frosted_colors = {}
                for k, v in colors.items():
                    self._cached_frosted_colors[k] = (
                        rgba_to_blended_hex(v, bg)
                        if isinstance(v, str) and v.startswith('rgba') else v
                    )
                self._cached_frosted_theme = current_theme
            dock_colors = self._cached_frosted_colors
        else:
            dock_colors = colors

        self._paint_card(painter, dock_colors)
        super().paintEvent(event)


class FloatingDialog(_GlassSurfaceMixin, QDialog):
    _bg_color_key = 'window'
    _border_color_key = 'mid'

    @staticmethod
    def create_dialog_title_bar(title_text, close_target, min_width=46, height=32):
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        title_text_color = colors.get('window_text', '#ffffff')
        close_hover = AppStyles.COLOR_CLOSE_HOVER if hasattr(AppStyles, 'COLOR_CLOSE_HOVER') else '#e81123'

        bar = QWidget()
        bar.setFixedHeight(height)
        bar.setObjectName("dialogTitleBar")
        bar.setStyleSheet(AppStyles.dialog_title_bar_style())

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(0)

        label = QLabel(title_text)
        label.setStyleSheet(AppStyles.title_label_style())
        layout.addWidget(label, 1)

        icon_color = title_text_color
        icon_size = QSize(14, 14)

        close_btn = QPushButton()
        close_icon_path = AppStyles.get_icon('close', icon_color, 14)
        if close_icon_path:
            close_btn.setIcon(QIcon(close_icon_path))
        close_btn.setIconSize(icon_size)
        close_btn.setFixedSize(min_width, height - 4)
        close_btn.setObjectName("closeButton")
        try:
            from core.language_manager import LanguageManager
            close_btn.setToolTip(LanguageManager().tr('close', '关闭'))
        except Exception:
            close_btn.setToolTip('关闭')
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {close_hover}; color: white;
            }}
        """)
        close_btn.clicked.connect(close_target.close)
        layout.addWidget(close_btn)

        return bar

    def __init__(self, parent=None, frameless=True, tool_window=False, stay_on_top=True):
        super().__init__(parent)
        self.dragging = False
        self.offset = None
        from ui.styles import AppStyles
        colors = AppStyles._get_colors()
        if AppStyles._visual_style == 'frosted':
            self.opacity = int(colors.get('frosted_opacity', 0.8) * 255)
        else:
            self.opacity = colors.get('window_opacity', 220)

        flags = Qt.WindowType.Window
        if stay_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if tool_window:
            flags |= Qt.WindowType.Tool
        if frameless:
            flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._dwm_blur_enabled = False
        self._cached_frosted_colors = None
        self._cached_frosted_theme = None
        self._centered = False
        self._init_glass_surface()

    # ------------------------------------------------------------------
    # 主题样式钩子（DRY）：子类只需覆写 _extra_theme_css() 返回差异 CSS
    # ------------------------------------------------------------------
    def _extra_theme_css(self) -> str:
        """子类覆写此方法返回差异 CSS；默认返回空字符串。"""
        return ""

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        from ui.styles import AppStyles
        self.setStyleSheet(AppStyles.popup_dialog_style() + self._extra_theme_css())
        self.refresh_glass_surface()

    # ------------------------------------------------------------------
    # 标准按钮区范式
    #   表单确认类: [取消] [确定]                     右对齐
    #   设置调节类: [恢复默认] ... [应用] [完成]       默认值居左、主操作居右
    # ------------------------------------------------------------------
    @staticmethod
    def _tr(text_key, default_text):
        try:
            from core.language_manager import LanguageManager
            return LanguageManager().tr(text_key, default_text)
        except Exception:
            return default_text

    @classmethod
    def _make_dialog_button(cls, text, role='normal'):
        btn = QPushButton(text)
        if role in ('primary', 'apply'):
            btn.style_type = 'apply'
        elif role == 'cancel':
            btn.style_type = 'cancel'
        btn.setMinimumWidth(88)
        return btn

    def build_confirm_buttons(self, on_ok, ok_text=None, cancel_text=None):
        """标准表单确认式按钮区：[取消] [确定]，右对齐。返回 (widget, ok_btn, cancel_btn)"""
        ok_text = ok_text or self._tr('ok', '确定')
        cancel_text = cancel_text or self._tr('cancel', '取消')
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(8)
        cancel_btn = self._make_dialog_button(cancel_text, 'cancel')
        ok_btn = self._make_dialog_button(ok_text, 'primary')
        ok_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(on_ok)
        layout.addStretch(1)
        layout.addWidget(cancel_btn)
        layout.addWidget(ok_btn)
        return bar, ok_btn, cancel_btn

    def build_settings_buttons(self, on_reset, on_apply, on_done,
                               reset_text=None, apply_text=None, done_text=None):
        """标准设置调节式按钮区：[恢复默认] | 弹性 | [应用] [完成]。返回 (widget, reset_btn, apply_btn, done_btn)"""
        reset_text = reset_text or self._tr('reset_defaults', '恢复默认')
        apply_text = apply_text or self._tr('apply', '应用')
        done_text = done_text or self._tr('done', '完成')
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(8)
        reset_btn = self._make_dialog_button(reset_text, 'normal')
        apply_btn = self._make_dialog_button(apply_text, 'apply')
        done_btn = self._make_dialog_button(done_text, 'primary')
        done_btn.setDefault(True)
        if on_reset:
            reset_btn.clicked.connect(on_reset)
        else:
            reset_btn.hide()
        if on_apply:
            apply_btn.clicked.connect(on_apply)
        else:
            apply_btn.hide()
        done_btn.clicked.connect(on_done)
        layout.addWidget(reset_btn)
        layout.addStretch(1)
        layout.addWidget(apply_btn)
        layout.addWidget(done_btn)
        return bar, reset_btn, apply_btn, done_btn

    def showEvent(self, event):
        super().showEvent(event)
        self._try_enable_dwm_blur()
        self._glass_timer.start()
        if not self._centered:
            self._centered = True
            try:
                # 优先用父窗口/自身所在屏幕，避免多显示器下弹到主屏
                screen = self.screen() or (
                    self.parent().screen() if self.parent() else None
                )
                if screen is None:
                    app = QApplication.instance()
                    screen = app.primaryScreen() if app else None
                if screen:
                    sg = screen.availableGeometry()
                    self.adjustSize()
                    ds = self.size()
                    x = (sg.width() - ds.width()) // 2 + sg.x()
                    y = (sg.height() - ds.height()) // 2 + sg.y()
                    wayland_move(self, x, y)
            except Exception:
                pass
        # 修复首次显示时文字重叠的问题（无边框透明窗口常见问题）
        # 延迟强制重新计算所有子布局并重绘
        safe_single_shot(DelayMs.NEXT_TICK, self, self._fix_first_paint)
        if is_windows():
            # Windows 分层窗口额外保险：再延迟一帧触发一次尺寸抖动，
            # 确保 QFormLayout + 嵌套 QWidget 容器的 sizeHint 完全生效
            safe_single_shot(DelayMs.UI_REFRESH, self, self._fix_first_paint)
        if is_linux() and self.parent():
            try:
                parent_handle = self.parent().windowHandle()
                if parent_handle is None:
                    self.parent().createWinId()
                    parent_handle = self.parent().windowHandle()
                if parent_handle:
                    self_handle = self.windowHandle()
                    if self_handle is None:
                        self.createWinId()
                        self_handle = self.windowHandle()
                    if self_handle and self_handle.transientParent() is None:
                        self_handle.setTransientParent(parent_handle)
            except Exception:
                pass
        if is_android():
            return
        if is_macos():
            from ui.styles import AppStyles
            if AppStyles.is_glass_style() and not self._dwm_blur_enabled:
                self._try_enable_macos_blur()
            return
        if not is_windows():
            return
        # Windows: 隐藏任务栏图标（与 FloatingDockWidget.show 行为一致）
        # 通过设置 WS_EX_TOOLWINDOW 让窗口不出现在任务栏
        # 这对所有 FloatingDialog 子类生效，无论 parent 是否为 None、无论 exec 还是 show
        try:
            _hide_from_taskbar(self)
        except Exception:
            pass

    def _fix_first_paint(self):
        """强制重新计算所有子布局并重绘，修复首次显示时文字重叠的问题。

        分层窗口（WA_TranslucentBackground + 自定义 paintEvent）在 Windows 上
        首次显示时，Qt 的布局系统可能没有正确触发子控件的布局计算，
        特别是 QFormLayout + 嵌套 QWidget 容器 + QGroupBox QSS padding 的复杂结构。
        典型表现：打开订阅设置窗口时"回放协议设置"内容全部重叠，移动窗口后恢复正常。

        修复策略：
        1. ensurePolished() 确保 QSS（如 QGroupBox padding-top:18px）已应用到控件，
           使 sizeHint 计算考虑 QSS 的 padding/margin
        2. invalidate() + activate() 强制所有布局（含子控件）重新计算
        3. 触发一次尺寸抖动（+1/-1），强制 Qt 重新派发 resizeEvent 和重绘
        """
        try:
            # 1. 确保样式表已应用（QSS padding 会影响 sizeHint 计算）
            self.ensurePolished()
            children = self.findChildren(QWidget)
            for child in children:
                child.ensurePolished()

            # 2. invalidate 并 activate 所有布局（包括子控件的嵌套布局）
            top_layout = self.layout()
            if top_layout is not None:
                top_layout.invalidate()
                top_layout.activate()
            for child in children:
                lay = child.layout()
                if lay is not None:
                    lay.invalidate()
                    lay.activate()

            # 3. 触发一次尺寸抖动，强制 Qt 重新派发 resizeEvent 并重绘
            # 这是解决分层窗口首次绘制布局问题的可靠方法
            sz = self.size()
            self.resize(sz.width() + 1, sz.height())
            self.resize(sz.width(), sz.height())

            # 4. 触发重绘
            self.update()
        except Exception:
            pass

    # 说明：macOS 模糊统一走 _GlassSurfaceMixin._try_enable_macos_blur。
    # 这里曾有一份只认 frosted 的覆写，导致 dock 与 dialog 对 win11/mac/ios
    # 三种玻璃风格解析不一致，已删除。

    def enterEvent(self, event):
        _notify_main_window_activity(self)
        super().enterEvent(event)

    def mousePressEvent(self, event):
        _notify_main_window_activity(self)
        if event.button() == Qt.MouseButton.LeftButton:
            widget = QtWidgets.QApplication.widgetAt(event.globalPosition().toPoint())
            if widget:
                interactive_types = (
                    QtWidgets.QAbstractButton,
                    QtWidgets.QLineEdit,
                    QtWidgets.QComboBox,
                    QtWidgets.QCheckBox,
                    QtWidgets.QScrollBar,
                    QtWidgets.QTableView,
                    QtWidgets.QTreeView,
                    QtWidgets.QListView,
                    QtWidgets.QAbstractSlider,
                    QtWidgets.QAbstractSpinBox,
                    QtWidgets.QTextEdit,
                    QtWidgets.QPlainTextEdit,
                )
                w = widget
                while w:
                    if isinstance(w, interactive_types):
                        super().mousePressEvent(event)
                        return
                    w = w.parent()
            if is_wayland():
                wh = self.windowHandle()
                if wh:
                    wh.startSystemMove()
                    event.accept()
                    return
            self.dragging = True
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        _notify_main_window_activity(self)
        if self.dragging and self.offset is not None:
            new_position = event.globalPosition().toPoint() - self.offset
            self.move(new_position.x(), new_position.y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def paintEvent(self, event):

        from ui.styles import AppStyles, rgba_to_blended_hex

        if not self._dwm_blur_enabled and AppStyles.is_glass_style():
            self._try_enable_dwm_blur()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = AppStyles._get_colors()
        is_frosted = AppStyles._visual_style == 'frosted'

        if is_frosted:
            current_theme = AppStyles._current_theme
            if self._cached_frosted_theme != current_theme:
                effective_mode = AppStyles._get_effective_color_mode()
                bg = (0, 0, 0) if effective_mode == 'dark' else (255, 255, 255)
                self._cached_frosted_colors = {}
                for k, v in colors.items():
                    self._cached_frosted_colors[k] = (
                        rgba_to_blended_hex(v, bg)
                        if isinstance(v, str) and v.startswith('rgba') else v
                    )
                self._cached_frosted_theme = current_theme
            dlg_colors = self._cached_frosted_colors
        else:
            dlg_colors = colors

        self._paint_card(painter, dlg_colors)

        super().paintEvent(event)
