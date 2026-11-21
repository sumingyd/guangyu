from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QToolButton

from core.log_manager import global_logger as logger
from ui.styles import AppStyles
from utils.platform_utils import is_macos, wayland_move, wayland_set_geometry, get_ui_scale
from utils.thread_safety import safe_single_shot


class WindowMixin:
    """从 IPTVPlayer 提取的窗口事件/定位/全屏/覆盖层职责"""

    def eventFilter(self, obj, event):
        # 底栏实际高度会随字号/内容异步变化（布局在首帧后才定型）；
        # 只在启动时算一次会让左右浮层压住底栏，这里按 resize 触发重排。
        try:
            if event.type() == QEvent.Type.Resize and obj is getattr(self, 'floating_dock', None):
                self._schedule_dock_reposition()
            elif event.type() in (QEvent.Type.Move, QEvent.Type.Resize) and obj is getattr(self, 'video_frame', None):
                # 独立窗口模式的标识不会随父控件移动，视频区一动就同步一次
                self._sync_video_overlay_window()
        except Exception:
            pass
        return self.event_handler.eventFilter(obj, event)

    def _schedule_dock_reposition(self):
        if getattr(self, '_dock_reposition_pending', False):
            return
        self._dock_reposition_pending = True
        safe_single_shot(60, self, self._deferred_dock_reposition)

    def _deferred_dock_reposition(self):
        self._dock_reposition_pending = False
        try:
            self._position_floating_docks()
        except Exception as e:
            logger.debug(f"底栏尺寸变化后重排浮层失败: {e}")

    def update_floating_position(self):
        if not hasattr(self, 'video_frame') or self.video_frame is None:
            return

        if hasattr(self, 'video_widget') and self.video_widget:
            self.video_widget.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())

        if hasattr(self, 'video_placeholder') and self.video_placeholder:
            self.video_placeholder.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())

        # 屏保覆盖层与视频区同尺寸，窗口缩放时同步（只在其可见时调整）
        screensaver = getattr(self, '_screensaver_widget', None)
        try:
            if screensaver is not None and screensaver.isVisible():
                screensaver.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())
        except RuntimeError:
            pass

        self._update_video_overlay_position()
        self._position_floating_docks()

    def _raise_overlay_above_video(self):
        """把回看/时移标识提到视频之上。

        Windows 下标识是独立的透明工具窗口，属主关系保证它在主窗口之上；
        其余平台是视频区里的原生子控件，raise_() 即可。
        """
        if not hasattr(self, '_video_overlay_label') or not self._video_overlay_label:
            return
        overlay = self._video_overlay_label
        if overlay.isWindow():
            # 顶层窗口 raise 会压住设置等对话框；前台不是主窗口时不动 z-order
            from PySide6.QtWidgets import QApplication
            active = QApplication.activeWindow()
            if active is not None and active is not self:
                return
        overlay.raise_()

    def _sync_video_overlay_window(self):
        """独立窗口模式：把标识对齐到视频区左下角（子控件模式由父级自动跟随）。"""
        overlay = getattr(self, '_video_overlay_label', None)
        frame = getattr(self, 'video_frame', None)
        if overlay is None or frame is None:
            return
        if not overlay.isWindow():
            return
        origin = frame.mapToGlobal(frame.rect().topLeft())
        overlay.sync_position(
            origin.x() + 12,
            origin.y() + frame.height() - overlay.height() - 12,
        )

    def _update_video_overlay_position(self):
        if not hasattr(self, '_video_overlay_label') or not self._video_overlay_label:
            return
        if not hasattr(self, 'video_frame') or not self.video_frame:
            return
        overlay = self._video_overlay_label
        overlay.adjustSize()
        if overlay.isWindow():
            self._sync_video_overlay_window()
        else:
            h = overlay.height()
            overlay.setGeometry(12, self.video_frame.height() - h - 12, overlay.width(), h)
        if overlay.isVisible():
            self._raise_overlay_above_video()

    def _position_floating_docks(self):
        if getattr(self, '_dock_layout_unlocked', False):
            return
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
        side_h = max(0, side_h)

        def _sync_side_height(dock):
            """最小高度只增不减，退出全屏时必须显式 resize 才会缩回窗口高度。"""
            dock.setMinimumHeight(side_h)
            if dock.height() > side_h:
                dock.resize(dock.width(), side_h)

        if hasattr(self, 'epg_dock') and self.epg_dock:
            if not self.epg_dock.isFloating():
                self.epg_dock.setFloating(True)
            wayland_move(self.epg_dock, mw_x + gap, side_top)
            _sync_side_height(self.epg_dock)

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
                _sync_side_height(self.playlist_dock)
                self.playlist_dock.setFixedWidth(pl_w)

        if hasattr(self, 'floating_dock') and self.floating_dock:
            if not self.floating_dock.isFloating():
                self.floating_dock.setFloating(True)
            avail_w = max(0, mw_w - gap * 2)
            # 底栏宽度按窗口比例与屏宽因子推导，不再写死固定像素；
            # 全屏与窗口模式同一套控件，宽度也按同一公式，否则全屏下控件会被挤掉
            scale = get_ui_scale()
            fl_w = max(int(round(720 * scale)), int(mw_w * 0.7))
            fl_w = min(avail_w, fl_w)
            if fl_w > 0 and self.floating_dock.minimumWidth() != fl_w:
                self.floating_dock.setMinimumWidth(fl_w)
            # 用户之前拖宽过 / 全屏留下的宽度可能超过窗口，必须先收回来，
            # 否则底栏会伸出窗口右侧，文字看起来被硬裁。
            if self.floating_dock.width() > avail_w and avail_w > 0:
                self.floating_dock.resize(avail_w, self.floating_dock.height())
            fl_x = mw_x + (mw_w - self.floating_dock.width()) // 2
            fl_y = mw_y + mw_h - control_panel_h - status_bar_h - gap
            wayland_move(self.floating_dock, fl_x, fl_y)
        self._remember_main_window_anchor()

    def _sync_floating_dock_width(self):
        """按当前窗口宽度把底栏收/放到目标宽度（全屏与窗口模式同一公式）。

        只允许在窗口几何已经生效后调用：退出全屏时 showNormal/setGeometry 是
        异步生效的，过早调用会读到全屏时的旧宽度，把底栏留在全屏宽度上。
        """
        dock = getattr(self, 'floating_dock', None)
        if not dock:
            return
        avail_w = max(0, self.width() - 16)
        scale = get_ui_scale()
        target_w = max(int(round(720 * scale)), int(self.width() * 0.7))
        target_w = min(avail_w, target_w)
        if target_w <= 0:
            return
        # 先同步最小宽度，否则在「最小宽度仍是全屏值」时 resize 会被约束回全屏宽度
        if dock.minimumWidth() != target_w:
            dock.setMinimumWidth(target_w)
        if dock.width() != target_w:
            dock.resize(target_w, dock.height())

    def _remember_main_window_anchor(self):
        """记录本次全量定位时的窗口基准，供拖动时的位移路径使用。"""
        self._last_main_pos = self.pos()
        self._last_main_dpr = self.devicePixelRatioF()
        self._last_main_screen = self.screen()

    def _on_main_window_moved(self):
        """主窗口拖动：只按位移平移浮层，不重排、不改尺寸。

        20Hz 节流与逐帧全量重算会让面板明显落后于窗口；这里改为逐次
        moveEvent 直接位移。跨屏或缩放比变化时基准不再有效，强制走一次
        全量重算，避免按旧像素比平移造成错位。
        """
        if getattr(self, '_dock_layout_unlocked', False):
            return
        last = getattr(self, '_last_main_pos', None)
        dpr = self.devicePixelRatioF()
        screen = self.screen()
        dpr_changed = dpr != getattr(self, '_last_main_dpr', dpr)
        screen_changed = screen is not getattr(self, '_last_main_screen', screen)
        if last is None or dpr_changed or screen_changed:
            self._position_floating_docks()
            return
        pos = self.pos()
        dx = pos.x() - last.x()
        dy = pos.y() - last.y()
        if dx == 0 and dy == 0:
            return
        self._last_main_pos = pos
        self._shift_floating_docks(dx, dy)

    def _shift_floating_docks(self, dx, dy):
        """把所有可见浮层与独立窗口形态的角标按 dx/dy 平移。"""
        for name in ('epg_dock', 'playlist_dock', 'floating_dock'):
            dock = getattr(self, name, None)
            if dock is None or not dock.isVisible() or not dock.isFloating():
                continue
            dock.move(dock.x() + dx, dock.y() + dy)
        overlay = getattr(self, '_video_overlay_label', None)
        if overlay is not None and overlay.isVisible() and overlay.isWindow():
            overlay.sync_position(overlay.x() + dx, overlay.y() + dy)

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
            # macOS 的全屏由 NSWindow 进入独立 Space 管理，进入后 Qt 会自动把
            # 窗口铺满目标屏幕；这里再 setGeometry 会打断原生全屏动画，甚至
            # 把窗口留在错误的 Space 里，因此 macOS 跳过。
            if not is_macos():
                screen = self.screen()
                if screen:
                    geo = screen.geometry()
                    wayland_set_geometry(self, geo.x(), geo.y(), geo.width(), geo.height())
            self._position_fullscreen_menu_button()
            logger.debug(f"进入全屏后: geometry={self.geometry().getRect()}, isFullScreen={self.isFullScreen()}")
            self.unsetCursor()
            is_local = self._is_local_file() if hasattr(self, '_is_local_file') else False
            self.panel_vis.set_all_visible(is_local_file=is_local)
            # 全屏与窗口模式保持同一套底栏控件（不再精简进度条/按钮集合）
            self._update_fullscreen_button_hint()
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
            # 退出原生全屏时 macOS 会自行恢复进入前的窗口几何，
            # 再调 setGeometry 会与系统恢复流程打架（多屏/DPI 下位置漂移）。
            if saved_geo and not is_macos():
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
            # 退出全屏后提示语恢复为「全屏」（控件集合两种模式本就一致）
            self._update_fullscreen_button_hint()
            # 此时窗口几何还没真正恢复，立刻按当前宽度算会拿到全屏的旧宽度；
            # 交给 update_floating_position（含 0/150ms 延迟补算）按恢复后的宽度收敛
            self._sync_panel_actions()
            self.update_floating_position()
            # showNormal/geometry 恢复后布局仍在异步重算，延迟补同步一次；
            # 底栏宽度必须等恢复后的窗口宽度生效再算，否则会残留全屏时的宽度
            safe_single_shot(0, self, self.update_floating_position)
            safe_single_shot(150, self, self.update_floating_position)
            safe_single_shot(0, self, self._sync_floating_dock_width)
            safe_single_shot(150, self, self._sync_floating_dock_width)

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

    def _clamp_window_position(self, x, y, width, height):
        """校正保存的窗口位置：显示器被拔掉或分辨率变化后窗口可能完全落在屏幕外。

        要求窗口尽量完整落在某块屏幕的可用区内（含标题栏与关闭按钮），
        多屏时优先选重叠面积最大的一块，再钳制 x/y；窗口比屏幕还大时贴左上。
        """
        try:
            from PySide6.QtCore import QRect
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return x, y
            screens = app.screens()
            if not screens:
                return x, y
            rect = QRect(x, y, width, height)
            best = None
            best_area = -1
            for screen in screens:
                avail = screen.availableGeometry()
                inter = avail.intersected(rect)
                area = inter.width() * inter.height() if inter.isValid() else 0
                if area > best_area:
                    best_area = area
                    best = screen
            if best is None:
                return x, y
            avail = best.availableGeometry()
            if avail.contains(rect):
                return x, y

            max_x = max(avail.x(), avail.x() + avail.width() - width)
            max_y = max(avail.y(), avail.y() + avail.height() - height)
            new_x = min(max(x, avail.x()), max_x)
            new_y = min(max(y, avail.y()), max_y)
            if (new_x, new_y) != (x, y):
                logger.warning(
                    f"保存的窗口位置({x},{y},{width}x{height})超出屏幕可用区，"
                    f"已钳制为({new_x},{new_y})，屏幕={avail.getRect()}")
            return new_x, new_y
        except Exception as e:
            logger.debug(f"校正窗口位置失败: {e}")
            return x, y

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
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            # 独立窗口模式的标识是顶层工具窗口，不会跟着主窗口最小化自动隐藏
            self._hide_video_overlay_window()

    def hideEvent(self, event):
        # 最小化到托盘/隐藏主窗口时，标识也不能留在桌面上
        self._hide_video_overlay_window()
        super().hideEvent(event)

    def _hide_video_overlay_window(self):
        """隐藏回看/时移角标：独立工具窗口和子控件两种形态都要收起。"""
        overlay = getattr(self, '_video_overlay_label', None)
        if overlay is not None and overlay.isVisible():
            overlay.hide()

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
        msg_box.setText(tr('close_confirm_text', '关闭后将无法接收节目提醒。你可以选择最小化到系统托盘，让程序继续在后台运行。'))
        msg_box.setIcon(QMessageBox.Icon.Question)
        min_btn = msg_box.addButton(tr('close_minimize_tray', '最小化到托盘'), QMessageBox.ButtonRole.YesRole)
        close_btn = msg_box.addButton(tr('close_exit', '直接退出'), QMessageBox.ButtonRole.NoRole)
        cancel_btn = msg_box.addButton(tr('cancel', '取消'), QMessageBox.ButtonRole.RejectRole)
        # 默认落在「取消」：回车不会误触最小化或退出
        msg_box.setDefaultButton(cancel_btn)
        msg_box.setEscapeButton(cancel_btn)

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