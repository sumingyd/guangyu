from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QToolButton

from core.log_manager import global_logger as logger
from ui.styles import AppStyles
from utils.platform_utils import wayland_move, wayland_set_geometry, get_ui_scale
from utils.thread_safety import safe_single_shot


class WindowMixin:
    """从 IPTVPlayer 提取的窗口事件/定位/全屏/覆盖层职责"""

    def eventFilter(self, obj, event):
        return self.event_handler.eventFilter(obj, event)

    def update_floating_position(self):
        if not hasattr(self, 'video_frame') or self.video_frame is None:
            return

        if hasattr(self, 'video_widget') and self.video_widget:
            self.video_widget.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())

        if hasattr(self, 'video_placeholder') and self.video_placeholder:
            self.video_placeholder.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())

        self._update_video_overlay_position()

    def _raise_overlay_above_video(self):
        if not hasattr(self, '_video_overlay_label') or not self._video_overlay_label:
            return
        self._video_overlay_label.raise_()
        from utils.platform_utils import is_windows
        if is_windows():
            try:
                hwnd = int(self._video_overlay_label.winId())
                import ctypes
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                ctypes.windll.user32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
                ctypes.windll.user32.SetWindowPos(
                    hwnd, -2, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
            except Exception:
                pass

    def _update_video_overlay_position(self):
        if not hasattr(self, '_video_overlay_label') or not self._video_overlay_label:
            return
        if not hasattr(self, 'video_frame') or not self.video_frame:
            return
        self._video_overlay_label.adjustSize()
        w = self._video_overlay_label.width()
        h = self._video_overlay_label.height()
        fw = self.video_frame.width()
        fh = self.video_frame.height()
        self._video_overlay_label.setGeometry(12, fh - h - 12, w, h)
        if self._video_overlay_label.isVisible():
            self._raise_overlay_above_video()

        self._position_floating_docks()

    def _position_floating_docks(self):
        if getattr(self, '_dock_layout_unlocked', False):
            return
        import time
        now = time.time()
        if hasattr(self, '_last_position_time') and now - self._last_position_time < 0.05:
            # 节流期间不能直接丢弃请求，否则最后一次尺寸变化不会生效；
            # 安排一个尾帧，保证最终位置与主窗口一致。
            if not getattr(self, '_position_pending', False):
                self._position_pending = True
                safe_single_shot(50, self, self._flush_floating_position)
            return
        self._last_position_time = now
        if hasattr(self, '_main_container') and self._main_container.layout():
            self._main_container.layout().activate()

        mw = self.geometry()
        if mw.isEmpty():
            return

        mw_x, mw_y, mw_w, mw_h = mw.x(), mw.y(), mw.width(), mw.height()
        is_fullscreen = getattr(self, 'is_fullscreen', False)

        gap = 8
        # 全屏时标题栏已隐藏，不能再按 32px 预留，否则底栏整体上移出现空隙
        title_bar_h = 0 if is_fullscreen else 32
        menu_bar_h = 28 if (hasattr(self, '_custom_menu_bar') and self._custom_menu_bar and self._custom_menu_bar.isVisible()) else 0
        fallback_panel_h = int(round(170 * get_ui_scale()))
        floating_dock = self.floating_dock
        if floating_dock:
            if floating_dock.isVisible():
                control_panel_h = floating_dock.height()
                self._last_control_panel_h = control_panel_h
            else:
                control_panel_h = getattr(self, '_last_control_panel_h', floating_dock.height() or fallback_panel_h)
        else:
            control_panel_h = fallback_panel_h
        sb = self.statusBar() if hasattr(self, 'statusBar') else None
        # 全屏隐藏状态栏时按 0 计算，避免底栏被多顶起 25px
        status_bar_h = sb.height() if sb and sb.isVisible() else (0 if is_fullscreen else 25)

        side_top = mw_y + title_bar_h + menu_bar_h + gap
        side_h = mw_h - title_bar_h - menu_bar_h - control_panel_h - status_bar_h - gap * 2

        if hasattr(self, 'epg_dock') and self.epg_dock:
            if not self.epg_dock.isFloating():
                self.epg_dock.setFloating(True)
            wayland_move(self.epg_dock, mw_x + gap, side_top)
            self.epg_dock.setMinimumHeight(max(0, side_h))

            # 宽度以当前值为基准固定：用户拖宽/拖窄后不被重置回首次捕获值
            epg_w = self.epg_dock.width()
            if epg_w > 0:
                self._epg_dock_w = epg_w
                self.epg_dock.setFixedWidth(epg_w)

        if hasattr(self, 'playlist_dock') and self.playlist_dock:
            if not self.playlist_dock.isFloating():
                self.playlist_dock.setFloating(True)
            pl_w = self.playlist_dock.width()
            if pl_w <= 0:
                pl_w = getattr(self, '_playlist_dock_w', 0) or pl_w
            if pl_w > 0:
                self._playlist_dock_w = pl_w
                wayland_move(self.playlist_dock, mw_x + mw_w - pl_w - gap, side_top)
                self.playlist_dock.setMinimumHeight(max(0, side_h))
                self.playlist_dock.setFixedWidth(pl_w)

        if hasattr(self, 'floating_dock') and self.floating_dock:
            if not self.floating_dock.isFloating():
                self.floating_dock.setFloating(True)
            avail_w = max(0, mw_w - gap * 2)
            # 底栏宽度按窗口比例与屏宽因子推导，不再写死固定像素
            scale = get_ui_scale()
            if is_fullscreen:
                fl_w = int(round(560 * scale))
            else:
                fl_w = max(int(round(720 * scale)), int(mw_w * 0.7))
            fl_w = min(avail_w, fl_w)
            if fl_w > 0:
                self.floating_dock.setMinimumWidth(fl_w)
            fl_x = mw_x + (mw_w - self.floating_dock.width()) // 2
            fl_y = mw_y + mw_h - control_panel_h - status_bar_h - gap
            wayland_move(self.floating_dock, fl_x, fl_y)

    def _sync_floating_dock_width(self):
        """全屏/常规切换后底栏控件集合变化，强制按目标宽度收缩或恢复。"""
        dock = getattr(self, 'floating_dock', None)
        if not dock:
            return
        avail_w = max(0, self.width() - 16)
        scale = get_ui_scale()
        if getattr(self, 'is_fullscreen', False):
            target_w = int(round(560 * scale))
        else:
            target_w = max(int(round(720 * scale)), int(self.width() * 0.7))
        target_w = min(avail_w, target_w)
        if target_w > 0 and dock.width() != target_w:
            dock.resize(target_w, dock.height())

    def _flush_floating_position(self):
        """节流窗口结束后的尾帧补算。"""
        self._position_pending = False
        self._last_position_time = 0
        self._position_floating_docks()

    def toggle_dock_layout_lock(self):
        self._dock_layout_unlocked = not getattr(self, '_dock_layout_unlocked', False)
        if not self._dock_layout_unlocked:
            self._position_floating_docks()

    def _show_fullscreen_menu_button(self):
        if hasattr(self, '_fs_menu_btn') and self._fs_menu_btn:
            self._position_fullscreen_menu_button()
            self._fs_menu_btn.show()
            return
        self._fs_menu_btn = QToolButton(self)
        self._fs_menu_btn.setText('≡')
        self._fs_menu_btn.setFixedSize(28, 28)
        self._fs_menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 独立顶层窗口是为了盖在原生视频 HWND 之上
        self._fs_menu_btn.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self._apply_fullscreen_menu_button_style()
        try:
            from ui.theme_manager import get_theme_manager
            get_theme_manager().theme_changed.connect(lambda *_: self._apply_fullscreen_menu_button_style())
        except Exception as e:
            logger.debug(f"全屏菜单按钮主题订阅失败: {e}")
        self._position_fullscreen_menu_button()
        self._fs_menu_btn.show()
        self._fs_menu_btn.clicked.connect(self._toggle_fs_menu_bar)

    def _apply_fullscreen_menu_button_style(self):
        if not (hasattr(self, '_fs_menu_btn') and self._fs_menu_btn):
            return
        try:
            colors = AppStyles._get_colors()
            bg = colors.get('window', '#1e1e1e')
            fg = colors.get('window_text', '#ffffff')
            hover = colors.get('alternate_base', colors.get('mid', '#3c3c3c'))
            self._fs_menu_btn.setStyleSheet(
                "QToolButton {"
                f" background: {bg}; color: {fg};"
                " border: none; border-radius: 4px; font-size: 16px;"
                " }"
                f" QToolButton:hover {{ background: {hover}; }}"
            )
        except Exception as e:
            logger.debug(f"_apply_fullscreen_menu_button_style: {e}")

    def _position_fullscreen_menu_button(self):
        """按主窗口左上角定位，避免多显示器/非 (0,0) 起点时按钮跑到主屏角落。"""
        if not (hasattr(self, '_fs_menu_btn') and self._fs_menu_btn):
            return
        geo = self.geometry()
        self._fs_menu_btn.move(geo.x() + 4, geo.y() + 4)

    def _hide_fullscreen_menu_button(self):
        if hasattr(self, '_fs_menu_btn') and self._fs_menu_btn:
            try:
                self._fs_menu_btn.deleteLater()
            except Exception:
                pass
            self._fs_menu_btn = None
        if hasattr(self, '_custom_menu_bar') and self._custom_menu_bar:
            self._custom_menu_bar.hide()

    def _toggle_fs_menu_bar(self):
        if hasattr(self, '_custom_menu_bar') and self._custom_menu_bar:
            if self._custom_menu_bar.isVisible():
                self._custom_menu_bar.hide()
            else:
                self._custom_menu_bar.show()
                self._custom_menu_bar.raise_()

    def toggle_fullscreen(self, checked=None):
        if checked is not None and self.fullscreen_button.isCheckable():
            want_fullscreen = bool(checked)
        else:
            want_fullscreen = not self.is_fullscreen

        if want_fullscreen == self.is_fullscreen:
            logger.debug(f"toggle_fullscreen跳过: checked={checked}, is_fullscreen={self.is_fullscreen}, btn_checkable={self.fullscreen_button.isCheckable()}")
            return

        self.is_fullscreen = want_fullscreen

        if self.is_fullscreen:
            self._before_fullscreen_geo = self.geometry()
            logger.debug(f"进入全屏: 保存geometry={self._before_fullscreen_geo.getRect()}, screen={self.screen().geometry().getRect() if self.screen() else None}")
            self.panel_vis.set_auto_hide_visible()
            self.panel_vis.save_context('fullscreen')
            if hasattr(self, '_title_bar') and self._title_bar:
                self._title_bar.hide()
            if hasattr(self, '_custom_menu_bar') and self._custom_menu_bar:
                self._custom_menu_bar.hide()
            self._show_fullscreen_menu_button()
            if self.status_bar:
                self.status_bar.hide()
            self.showFullScreen()
            screen = self.screen()
            if screen:
                geo = screen.geometry()
                wayland_set_geometry(self, geo.x(), geo.y(), geo.width(), geo.height())
            self._position_fullscreen_menu_button()
            logger.debug(f"进入全屏后: geometry={self.geometry().getRect()}, isFullScreen={self.isFullScreen()}")
            self.unsetCursor()
            is_local = self._is_local_file() if hasattr(self, '_is_local_file') else False
            self.panel_vis.set_all_visible(is_local_file=is_local)
            # 全屏精简底栏：只留暂停/停止/全屏，信息区保持完整
            self._apply_control_panel_compact_mode(True)
            self._sync_floating_dock_width()
            self._sync_panel_actions()
            self._restart_auto_hide_timer()
            # 全屏切换后布局异步重算，事件循环处理完再同步视频子控件几何，
            # 否则原生 HWND（WA_NativeWindow）停留在旧尺寸导致画面区域错位
            safe_single_shot(0, self, self.update_floating_position)
            safe_single_shot(150, self, self.update_floating_position)
        else:
            self._stop_auto_hide_timer()
            self.unsetCursor()
            self._hide_fullscreen_menu_button()
            saved = self.panel_vis.restore_context('fullscreen')
            logger.debug(f"退出全屏: showNormal前geometry={self.geometry().getRect()}, isFullScreen={self.isFullScreen()}, saved_geo={getattr(self, '_before_fullscreen_geo', None)}")
            self.showNormal()
            saved_geo = getattr(self, '_before_fullscreen_geo', None)
            if saved_geo:
                wayland_set_geometry(self, saved_geo.x(), saved_geo.y(), saved_geo.width(), saved_geo.height())
            logger.debug(f"退出全屏后: geometry={self.geometry().getRect()}, isFullScreen={self.isFullScreen()}")
            if saved:
                if saved.get('title_bar', True) and hasattr(self, '_title_bar') and self._title_bar:
                    self._title_bar.show()
                if saved.get('menu_bar', True) and hasattr(self, '_custom_menu_bar') and self._custom_menu_bar:
                    self._custom_menu_bar.show()
                if saved.get('status_bar', True) and self.status_bar:
                    self.status_bar.show()
            self.panel_vis.set_auto_hide_visible()
            # 退出全屏恢复完整控件集合
            self._apply_control_panel_compact_mode(False)
            self._sync_floating_dock_width()
            self._sync_panel_actions()
            self.update_floating_position()
            # showNormal/geometry 恢复后布局仍在异步重算，延迟补同步一次
            safe_single_shot(0, self, self.update_floating_position)
            safe_single_shot(150, self, self.update_floating_position)

    def refresh_ui(self):
        self.populate_channel_list(source='auto')
        self.populate_epg_list()

    def reset_layout(self):
        self.panel_vis.reset()
        self._sync_panel_actions()
        self.resize(1280, 806)

    def open_scan_ui(self):
        try:
            from ui.dialogs.scan_channel_dialog import ScanChannelDialog

            dialog = ScanChannelDialog(self)
            self._scan_dialog = dialog

            dialog.show()

            logger.info("成功打开扫描界面")
        except Exception as ex:
            logger.error(f"打开扫描界面失败: {str(ex)}")

    def _raise_floating_panels(self):
        self.raise_()
        self.update_floating_position()
        for panel_attr in ['epg_panel', 'playlist_panel', 'floating_panel']:
            panel = getattr(self, panel_attr, None)
            if panel and panel.isVisible():
                panel.show()
                panel.raise_()
        self._raise_child_dialogs()

    def _raise_child_dialogs(self):
        for dialog in self.findChildren(QDialog):
            if getattr(dialog, '_no_auto_raise', False):
                continue
            if dialog.isVisible() and not dialog.isModal():
                dialog.raise_()

    def open_channel_mapping(self):
        try:
            from ui.dialogs.mapping_manager_dialog import MappingManagerDialog

            dialog = MappingManagerDialog(self)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.exec()

            logger.info("成功打开频道映射管理器")
        except Exception as ex:
            logger.error(f"打开频道映射管理器失败: {str(ex)}")

    def _center_dialog_on_screen(self, dialog):
        # 优先用主窗口所在屏幕，避免多显示器下弹到主屏
        screen = self.screen() if hasattr(self, 'screen') else None
        if screen is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app else None
        if screen:
            screen_geometry = screen.availableGeometry()
            dialog.adjustSize()
            dialog_size = dialog.size()
            x = (screen_geometry.width() - dialog_size.width()) // 2 + screen_geometry.x()
            y = (screen_geometry.height() - dialog_size.height()) // 2 + screen_geometry.y()
            wayland_move(dialog, x, y)

    def showEvent(self, event):
        if hasattr(self, 'event_handler') and self.event_handler:
            self.event_handler.showEvent(event)
        else:
            super().showEvent(event)
        self._fix_win32_drag_drop()

    def changeEvent(self, event):
        if hasattr(self, 'event_handler') and self.event_handler:
            self.event_handler.changeEvent(event)
        else:
            super().changeEvent(event)

    def moveEvent(self, event):
        if hasattr(self, 'event_handler') and self.event_handler:
            self.event_handler.moveEvent(event)
        else:
            super().moveEvent(event)

    def resizeEvent(self, event):
        if hasattr(self, 'event_handler') and self.event_handler:
            self.event_handler.resizeEvent(event)
        else:
            super().resizeEvent(event)

    def closeEvent(self, event):
        if getattr(self, '_is_hidden_to_tray', False):
            if hasattr(self, 'event_handler') and self.event_handler:
                self.event_handler.closeEvent(event)
            else:
                super().closeEvent(event)
            return

        if getattr(self, '_force_quit', False):
            self._force_quit = False
            try:
                from server.app import stop_server
                stop_server()
            except Exception as e:
                logger.warning(f"停止服务器失败: {e}")
            if hasattr(self, 'event_handler') and self.event_handler:
                self.event_handler.closeEvent(event)
            else:
                super().closeEvent(event)
            return

        config = self.config or self.config_manager
        if config:
            close_action = config.load_close_behavior()
            if close_action == 'minimize_tray':
                event.ignore()
                self._do_close_minimize_tray()
                return
            elif close_action == 'exit':
                try:
                    from server.app import stop_server
                    stop_server()
                except Exception as e:
                    logger.warning(f"停止服务器失败: {e}")
                if hasattr(self, 'event_handler') and self.event_handler:
                    self.event_handler.closeEvent(event)
                else:
                    super().closeEvent(event)
                return

        tr = self.language_manager.tr
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(tr('close_confirm_title', '关闭确认'))
        msg_box.setText(tr('close_confirm_text', '关闭后将无法接收节目提醒，是否最小化到系统托盘继续运行提醒功能？'))
        msg_box.setIcon(QMessageBox.Icon.Question)
        min_btn = msg_box.addButton(tr('close_minimize_tray', '最小化到托盘'), QMessageBox.ButtonRole.YesRole)
        close_btn = msg_box.addButton(tr('close_exit', '直接退出'), QMessageBox.ButtonRole.NoRole)
        cancel_btn = msg_box.addButton(tr('cancel', '取消'), QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(min_btn)

        remember_cb = QCheckBox(tr('close_remember_choice', '记住选择，不再询问'))
        msg_box.setCheckBox(remember_cb)

        msg_box.setStyleSheet(AppStyles.close_confirm_dialog_style())
        msg_box.exec()
        clicked = msg_box.clickedButton()
        if clicked == cancel_btn or clicked is None:
            event.ignore()
            return

        remember = remember_cb.isChecked()
        if clicked == min_btn:
            if remember and config:
                config.save_close_behavior('minimize_tray')
            event.ignore()
            self._do_close_minimize_tray()
            return
        if remember and config:
            config.save_close_behavior('exit')
        try:
            from server.app import stop_server
            stop_server()
        except Exception as e:
            logger.warning(f"停止服务器失败: {e}")
        if hasattr(self, 'event_handler') and self.event_handler:
            self.event_handler.closeEvent(event)
        else:
            super().closeEvent(event)