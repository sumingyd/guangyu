"""
画中画控制器 - 负责 PiP（画中画）模式的所有逻辑
从 pyqt_player.py 提取的独立模块
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QRegion, QPixmap
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QWidget

from core.log_manager import global_logger as logger
from controllers.main_window_protocol import PlaybackProtocol
from utils.platform_utils import is_wayland, wayland_move, wayland_set_geometry
from utils.delay_constants import DelayMs


class PipButton:
    """画中画圆形按钮（自定义绘制，SVG 图标，无背景填充）"""

    def __init__(self, icon_name, size, parent, click_callback):
        widget = QWidget(parent)
        widget._icon_name = icon_name
        widget._size = size
        widget._hovered = False
        widget._click_callback = click_callback
        widget.setFixedSize(size, size)
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAutoFillBackground(False)
        widget.setMouseTracking(True)
        circle = QRegion(QRect(0, 0, size, size), QRegion.RegionType.Ellipse)
        widget.setMask(circle)

        def _load_pixmap(icon_name):
            from ui.styles import AppStyles
            icon_color = "#FFFFFF"
            icon_size = int(size * 0.55)
            path = AppStyles.get_icon(icon_name, icon_color, icon_size)
            if path:
                pm = QPixmap(path)
                if not pm.isNull():
                    return pm.scaled(icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return QPixmap()

        widget._pixmap_cache = _load_pixmap(icon_name)

        def paint_event(self_widget, event):
            painter = QPainter(self_widget)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self_widget._hovered:
                painter.setBrush(QColor(50, 50, 50, 200))
                pen = QPen(QColor(255, 255, 255, 220), 2)
            else:
                painter.setBrush(QColor(20, 20, 20, 160))
                pen = QPen(QColor(255, 255, 255, 150), 2)
            painter.setPen(pen)
            painter.drawEllipse(1, 1, self_widget._size - 2, self_widget._size - 2)
            pm = self_widget._pixmap_cache
            if not pm.isNull():
                px = (self_widget._size - pm.width()) // 2
                py = (self_widget._size - pm.height()) // 2
                painter.drawPixmap(px, py, pm)
            painter.end()

        def enter_event(self_widget, event):
            self_widget._hovered = True
            self_widget.update()

        def leave_event(self_widget, event):
            self_widget._hovered = False
            self_widget.update()

        def mouse_press_event(self_widget, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self_widget._click_callback()

        def set_icon(self_widget, icon_name):
            if self_widget._icon_name != icon_name:
                self_widget._icon_name = icon_name
                self_widget._pixmap_cache = _load_pixmap(icon_name)
            self_widget.update()

        widget.paintEvent = lambda event: paint_event(widget, event)
        widget.enterEvent = lambda event: enter_event(widget, event)
        widget.leaveEvent = lambda event: leave_event(widget, event)
        widget.mousePressEvent = lambda event: mouse_press_event(widget, event)
        widget.set_icon = lambda icon_name: set_icon(widget, icon_name)

        self._widget = widget

    def set_icon(self, icon_name):
        self._widget.set_icon(icon_name)

    def show(self):
        self._widget.show()

    def hide(self):
        self._widget.hide()

    def move(self, x, y):
        self._widget.move(x, y)

    def setParent(self, parent):
        self._widget.setParent(parent)

    def isHidden(self):
        return self._widget.isHidden()

    def geometry(self):
        return self._widget.geometry()


class PipController:
    """画中画控制器 - 管理 PiP 模式的所有状态和行为"""

    def __init__(self, main_window: PlaybackProtocol):
        self.window: PlaybackProtocol = main_window

        self._is_active = False
        self._pip_dragging = False
        self._pip_drag_pos = None
        self._pip_resizing = False
        self._pip_resize_edge = None
        self._pip_resize_start_geo = None
        self._pip_resize_start_pos = None
        self._pip_saved_geometry = None
        self._pip_saved_maximized = False
        self._pip_saved_fullscreen = False
        self._pip_exit_status_msg = ''

        self._pip_overlay_widget = None
        self._pip_buttons = []
        self._pip_prev_btn = None
        self._pip_play_btn = None
        self._pip_next_btn = None
        self._pip_close_btn = None

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value):
        self._is_active = value

    def toggle(self, checked=None):
        should_enter = not self._is_active
        if should_enter:
            pc = self.window.player_controller
            has_content = (pc and (pc.is_playing or getattr(pc, 'is_paused', False))) or getattr(self.window, 'current_channel', None)
            if not has_content:
                pip_menu = getattr(self.window, '_pip_menu_action', None)
                if pip_menu:
                    pip_menu.setChecked(False)
                return
            self._enter()
        else:
            self._exit()

    def _enter(self):
        if self._is_active:
            return

        multi_ctrl = getattr(self.window, 'multi_screen_ctrl', None)
        if multi_ctrl and multi_ctrl.is_active:
            multi_ctrl.exit_multi_screen()
            from core.log_manager import global_logger as _logger
            _logger.info("PiP与多画面互斥：自动退出多画面模式")

        try:
            self._pip_saved_geometry = self.window.geometry()
            self._pip_saved_maximized = self.window.isMaximized()
            self._pip_saved_fullscreen = getattr(self.window, 'is_fullscreen', False)

            self.window.panel_vis.save_context('pip')

            if self._pip_saved_fullscreen:
                self.window.toggle_fullscreen()

            if self.window.isMaximized():
                self.window.showNormal()

            self.window._stop_auto_hide_timer()

            self._is_active = True
            self.window.panel_vis.hide_all()

            title_bar = self.window._title_bar
            if title_bar:
                title_bar.hide()
            menu_bar = self.window._custom_menu_bar
            if menu_bar:
                menu_bar.hide()
            if self.window.status_bar:
                self.window.status_bar.hide()
            epg_panel = self.window.epg_panel
            if epg_panel:
                epg_panel.hide()
            playlist_panel = self.window.playlist_panel
            if playlist_panel:
                playlist_panel.hide()
            floating_panel = self.window.floating_panel
            if floating_panel:
                floating_panel.hide()

            pip_w, pip_h = 480, 270
            scr = self.window.screen()
            primary = QApplication.primaryScreen()
            if scr:
                screen = scr.availableGeometry()
            elif primary:
                screen = primary.availableGeometry()
            else:
                logger.error("_enter_pip: 无法获取屏幕信息")
                self._is_active = False
                self._restore_hidden_elements()
                return

            x = screen.right() - pip_w - 20
            y = screen.bottom() - pip_h - 20

            self.window.setMinimumSize(240, 135)
            self.window.setMaximumSize(16777215, 16777215)
            self.window.resize(pip_w, pip_h)
            wayland_move(self.window, x, y)

            self.window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.window.show()
            self.window.raise_()

            self._pip_dragging = False
            self._pip_drag_pos = None
            self._pip_resizing = False
            self._pip_resize_edge = None
            self._pip_resize_start_geo = None
            self._pip_resize_start_pos = None
            self.window.setMouseTracking(True)

            if not self._pip_buttons:
                self._create_overlay()

            QTimer.singleShot(DelayMs.UI_REFRESH, self._show_overlay)
            QTimer.singleShot(DelayMs.UI_REFRESH, self._update_video_geometry)

            pip_menu = getattr(self.window, '_pip_menu_action', None)
            if pip_menu:
                pip_menu.setChecked(True)
            self.window.status_bar_show_message(
                self.window.language_manager.tr('pip_mode', 'PiP Mode') + " - P " +
                self.window.language_manager.tr('to_exit', 'to exit'))
            logger.info("已进入画中画模式")
        except Exception as e:
            logger.error(f"进入画中画模式失败: {e}")
            self._is_active = False
            pip_menu = getattr(self.window, '_pip_menu_action', None)
            if pip_menu:
                pip_menu.setChecked(False)
            self._restore_hidden_elements()

    def _exit(self):
        if not self._is_active:
            return

        try:
            self._is_active = False
            self._hide_overlay()

            self.window.setMinimumSize(800, 600)
            self.window.setMaximumSize(16777215, 16777215)

            self.window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
            self.window.show()
            self.window.raise_()

            if self._pip_saved_maximized:
                self.window.showMaximized()
            elif self._pip_saved_geometry is not None:
                wayland_set_geometry(self.window, self._pip_saved_geometry.x(), self._pip_saved_geometry.y(), self._pip_saved_geometry.width(), self._pip_saved_geometry.height())

            # 进入 PiP 时若原本是全屏，会先退出全屏；退出 PiP 必须恢复，
            # 否则主窗口会停在普通窗口状态（此前遗漏了这一步）
            if self._pip_saved_fullscreen:
                try:
                    if not getattr(self.window, 'is_fullscreen', False):
                        self.window.toggle_fullscreen()
                except Exception as _e:
                    logger.debug(f"退出画中画恢复全屏失败: {_e}")
                self._pip_saved_fullscreen = False

            self._pip_dragging = False
            self._pip_resizing = False
            self.window.unsetCursor()
            pip_menu = getattr(self.window, '_pip_menu_action', None)
            if pip_menu:
                pip_menu.setChecked(False)

            self._pip_exit_status_msg = (
                self.window.language_manager.tr('pip_mode', 'PiP Mode') + " " +
                self.window.language_manager.tr('pip_exited', 'exited'))

            def _safe_call(fn):
                def _wrapper():
                    try:
                        fn()
                    except RuntimeError:
                        pass
                return _wrapper

            QTimer.singleShot(DelayMs.LAYOUT_SETTLE, _safe_call(self._restore_hidden_elements))
            QTimer.singleShot(DelayMs.STYLE_REAPPLY, _safe_call(self.window.update_floating_position))
            QTimer.singleShot(DelayMs.VOLUME_HOLD, _safe_call(self.window._restart_auto_hide_timer))
            logger.info("已退出画中画模式")
        except Exception as e:
            logger.error(f"退出画中画模式失败: {e}")
            self._is_active = False
            pip_menu = getattr(self.window, '_pip_menu_action', None)
            if pip_menu:
                pip_menu.setChecked(False)

    def _restore_hidden_elements(self):
        saved = self.window.panel_vis.restore_context('pip')
        if not saved:
            return

        if saved.get('title_bar', True):
            title_bar = self.window._title_bar
            if title_bar:
                title_bar.show()
        if saved.get('menu_bar', True):
            menu_bar = self.window._custom_menu_bar
            if menu_bar:
                menu_bar.show()
        if saved.get('status_bar', True) and self.window.status_bar:
            self.window.status_bar.show()
        self.window._sync_panel_actions()

        if self._pip_exit_status_msg:
            self.window.status_bar_show_message(self._pip_exit_status_msg)
            self._pip_exit_status_msg = ''

    def _create_overlay(self):

        if is_wayland():
            overlay_flags = Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        else:
            overlay_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        self._pip_overlay_widget = QWidget(
            self.window,
            overlay_flags
        )
        self._pip_overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pip_overlay_widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._pip_overlay_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        btn_size = 44
        self._pip_prev_btn = self._create_button("prev", btn_size, self._on_prev_channel)
        self._pip_play_btn = self._create_button("pause", btn_size, self._on_toggle_play)
        self._pip_next_btn = self._create_button("next", btn_size, self._on_next_channel)
        self._pip_close_btn = self._create_button("close", btn_size, self._exit)

        self._pip_buttons = [self._pip_prev_btn, self._pip_play_btn, self._pip_next_btn, self._pip_close_btn]
        for btn in self._pip_buttons:
            btn.setParent(self._pip_overlay_widget)
            btn.hide()

        self._pip_overlay_widget.hide()

    def _create_button(self, icon_name, btn_size, click_callback):
        return PipButton(icon_name, btn_size, None, click_callback)

    def _on_prev_channel(self):
        logger.debug("画中画: 点击上一个频道按钮")
        event_handler = getattr(self.window, 'event_handler', None)
        if event_handler:
            event_handler._switch_channel(-1)

    def _on_toggle_play(self):
        logger.debug("画中画: 点击播放/暂停按钮")
        playback_ctrl = getattr(self.window, 'playback_ctrl', None)
        if playback_ctrl:
            playback_ctrl.toggle_play()
            self._update_play_btn()

    def _on_next_channel(self):
        logger.debug("画中画: 点击下一个频道按钮")
        event_handler = getattr(self.window, 'event_handler', None)
        if event_handler:
            event_handler._switch_channel(1)

    def _update_play_btn(self):
        if not self._pip_play_btn:
            return
        pc = self.window.player_controller
        if pc and pc.is_playing:
            self._pip_play_btn.set_icon("pause")
        else:
            self._pip_play_btn.set_icon("play")

    def handle_mouse_press(self, event):
        if not self._is_active:
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            overlay = self._pip_overlay_widget
            if overlay and overlay.isVisible():
                gpos = event.globalPosition().toPoint()
                overlay_geo = overlay.geometry()
                if overlay_geo.contains(gpos):
                    return False
            edge = self._get_resize_edge(event.position().toPoint())
            if edge:
                self._pip_resizing = True
                self._pip_resize_edge = edge
                self._pip_resize_start_geo = self.window.geometry()
                self._pip_resize_start_pos = event.globalPosition().toPoint()
                return True
            else:
                self._pip_dragging = True
                if is_wayland():
                    self._pip_drag_pos = event.globalPosition().toPoint() - self.window.pos()
                else:
                    self._pip_drag_pos = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
                return True
        return False

    def handle_mouse_move(self, event):
        if not self._is_active:
            return False

        if self._pip_dragging and self._pip_drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._pip_drag_pos
            wayland_move(self.window, new_pos.x(), new_pos.y())
            return True

        if self._pip_resizing and self._pip_resize_edge:
            delta = event.globalPosition().toPoint() - self._pip_resize_start_pos
            geo = self._pip_resize_start_geo
            min_w, min_h = 240, 135

            dx_left = 0
            dx_right = 0
            dy_top = 0
            dy_bottom = 0

            if 'left' in self._pip_resize_edge:
                dx_left = min(delta.x(), geo.width() - min_w)
            if 'right' in self._pip_resize_edge:
                dx_right = max(delta.x(), min_w - geo.width())
            if 'top' in self._pip_resize_edge:
                dy_top = min(delta.y(), geo.height() - min_h)
            if 'bottom' in self._pip_resize_edge:
                dy_bottom = max(delta.y(), min_h - geo.height())

            new_x = geo.x() + dx_left
            new_y = geo.y() + dy_top
            new_w = geo.width() - dx_left + dx_right
            new_h = geo.height() - dy_top + dy_bottom

            wayland_set_geometry(self.window, new_x, new_y, max(min_w, new_w), max(min_h, new_h))
            self._update_overlay_geometry()
            self._update_video_geometry()
            return True

        edge = self._get_resize_edge(event.position().toPoint())
        self._update_cursor(edge)
        return False

    def handle_mouse_release(self, event):
        if not self._is_active:
            return False
        if event.button() == Qt.MouseButton.LeftButton:
            self._pip_dragging = False
            self._pip_drag_pos = None
            self._pip_resizing = False
            self._pip_resize_edge = None
            self._pip_resize_start_geo = None
            self._pip_resize_start_pos = None
            return True
        return False

    def _get_resize_edge(self, pos):
        if not self._is_active:
            return None
        margin = 8
        w = self.window.width()
        h = self.window.height()
        x, y = pos.x(), pos.y()

        edges = []
        if x < margin:
            edges.append('left')
        if x > w - margin:
            edges.append('right')
        if y < margin:
            edges.append('top')
        if y > h - margin:
            edges.append('bottom')

        if not edges:
            return None
        return '-'.join(edges)

    def _update_cursor(self, edge):
        if edge is None:
            self.window.unsetCursor()
        elif edge in ('left', 'right'):
            self.window.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in ('top', 'bottom'):
            self.window.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge in ('top-left', 'bottom-right'):
            self.window.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ('top-right', 'bottom-left'):
            self.window.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.window.unsetCursor()

    def _update_video_geometry(self):
        if not self._is_active:
            return
        video_widget = self.window.video_widget
        video_frame = self.window.video_frame
        if video_widget and video_frame:
            video_widget.setGeometry(0, 0, video_frame.width(), video_frame.height())

    def _update_overlay_geometry(self):
        if not self._is_active:
            return
        if not self._pip_buttons:
            return
        video_widget = self.window.video_widget
        if not video_widget:
            return
        overlay = self._pip_overlay_widget
        if not overlay:
            return

        vw = video_widget
        top_left = vw.mapToGlobal(vw.rect().topLeft())
        wayland_set_geometry(overlay, top_left.x(), top_left.y(), vw.width(), vw.height())

        btn_size = 44
        spacing = 16
        total_w = btn_size * 3 + spacing * 2
        cx = vw.width() // 2
        cy = vw.height() // 2
        start_x = cx - total_w // 2
        control_btns = [self._pip_prev_btn, self._pip_play_btn, self._pip_next_btn]
        positions = [
            (start_x, cy - btn_size // 2),
            (start_x + btn_size + spacing, cy - btn_size // 2),
            (start_x + (btn_size + spacing) * 2, cy - btn_size // 2),
        ]
        for btn, (x, y) in zip(control_btns, positions):
            btn.move(x, y)

        close_margin = 6
        if self._pip_close_btn:
            self._pip_close_btn.move(vw.width() - btn_size - close_margin, close_margin)


        mask = QRegion()
        for btn in self._pip_buttons:
            if not btn.isHidden():
                mask = mask.united(QRegion(btn.geometry()))
        if mask.isEmpty():
            mask = QRegion(QRect(0, 0, 1, 1))
        overlay.setMask(mask)

    def show_overlay(self):
        self._show_overlay()

    def hide_overlay(self):
        self._hide_overlay()

    def _show_overlay(self):
        if not self._is_active:
            return
        if not self._pip_buttons:
            return
        self._update_play_btn()
        for btn in self._pip_buttons:
            btn.show()
        self._update_overlay_geometry()
        if self._pip_overlay_widget:
            self._pip_overlay_widget.show()

    def _hide_overlay(self):
        if self._pip_overlay_widget:
            self._pip_overlay_widget.hide()
        if not self._pip_buttons:
            return
        for btn in self._pip_buttons:
            btn.hide()

    def delayed_hide_overlay(self):
        if not self._is_active:
            return
        cursor_pos = self.window.cursor().pos()
        if self.window.rect().contains(self.window.mapFromGlobal(cursor_pos)):
            return
        overlay = self._pip_overlay_widget
        if overlay and overlay.isVisible():
            overlay_rect = overlay.geometry()
            if overlay_rect.contains(cursor_pos):
                return
        self._hide_overlay()