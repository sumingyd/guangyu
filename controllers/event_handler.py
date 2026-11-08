"""
事件处理器 - 负责键盘快捷键、事件过滤、窗口事件等
从 pyqt_player.py 提取的独立模块
"""

from core.log_manager import global_logger as logger
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDockWidget, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit, QSpinBox, QTextEdit, QVBoxLayout, QWidget
from controllers.main_window_protocol import MainWindowProtocol
from utils.thread_safety import safe_single_shot


class EventHandler:
    """事件处理器 - 统一管理所有事件处理逻辑"""

    def __init__(self, main_window: MainWindowProtocol):
        self.window: MainWindowProtocol = main_window
        self._shortcuts = {}  # 快捷键映射表

    def _adjust_volume(self, delta: int):
        """调整音量（增量/减量），委托给 media_controller"""
        mc = getattr(self.window, 'media_ctrl', None)
        if mc and hasattr(mc, '_set_volume'):
            vs = getattr(self.window, 'volume_slider', None)
            current = vs.value() if vs else 100
            mc._set_volume(max(0, min(current + delta, 100)))

    def _is_app_window_active(self) -> bool:
        """当前活动窗口是否属于本应用（主窗口或其浮动面板），对话框不算"""
        active = QApplication.activeWindow()
        if active is None:
            return self.window.isActiveWindow()
        if active is self.window:
            return True
        if isinstance(active, QDialog):
            return False
        if isinstance(active, QDockWidget):
            if active.parent() is self.window:
                return True
            for attr in ('epg_dock', 'playlist_dock', 'floating_dock'):
                if active is getattr(self.window, attr, None):
                    return True
            return False
        return active.parent() is self.window

    def _has_open_dialog(self) -> bool:
        """是否存在模态对话框、活动的非模态对话框，或弹出控件（右键菜单/下拉框）"""
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self.window:
            return True
        # 右键菜单、QComboBox 下拉列表等弹出控件同样持有键盘焦点：
        # 此时 Escape 应关闭弹层，而不是停播放/退全屏
        popup = QApplication.activePopupWidget()
        if popup is not None and popup is not self.window:
            return True
        active = QApplication.activeWindow()
        if active is not None and active is not self.window and isinstance(active, QDialog):
            return True
        return False

    def _is_player_focus(self) -> bool:
        """焦点是否属于播放器窗口（主窗口及其子控件），此时可安全接管方向键/空格。

        判定按窗口级而非具体控件级：视频控件自身是 NoFocus，永远不会成为
        QApplication.focusWidget()，若只认视频控件则方向键在正常启动态恒失效。
        三块悬浮面板都是独立的 Qt::Tool 顶层窗口，其 focus_widget.window()
        不是主窗口，因此面板内的方向键仍由面板自身（列表/网格）处理。
        """
        focus_widget = QApplication.focusWidget()
        if focus_widget is None:
            return self.window.isActiveWindow()
        return focus_widget.window() is self.window

    def _is_multi_screen_active(self) -> bool:
        """多画面是否激活（激活时方向键/空格由网格单元格处理）"""
        ms = getattr(self.window, 'multi_screen_ctrl', None)
        return bool(ms is not None and getattr(ms, 'is_active', False))

    def eventFilter(self, obj, event: QEvent) -> bool:
        """事件过滤器 - 在 app 级别统一处理所有快捷键（不受焦点影响）"""
        event_type = event.type()

        if event_type == QEvent.Type.ShortcutOverride:
            key = event.key()
            modifiers = event.modifiers()
            if self._is_handled_shortcut(key, modifiers):
                event.accept()
                return True

        if event_type == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            handled = self._handle_global_shortcut(key, modifiers)
            if handled:
                return True

        if getattr(self.window, 'is_fullscreen', False) and not getattr(self.window, '_floating_hidden', False):
            if obj is getattr(self.window, 'video_widget', None):
                if event_type in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
                    if hasattr(self.window, '_on_mouse_activity'):
                        self.window._on_mouse_activity()

        if not getattr(self.window, 'pip_mode', False):
            if obj is getattr(self.window, 'video_widget', None):
                if event_type == QEvent.Type.Wheel:
                    if hasattr(self.window, 'wheelEvent'):
                        self.window.wheelEvent(event)
                        return True
                elif event_type == QEvent.Type.MouseButtonDblClick:
                    if hasattr(self.window, 'mouseDoubleClickEvent'):
                        self.window.mouseDoubleClickEvent(event)
                        return True

        manually_hidden = getattr(self.window, 'panel_vis', None) and self.window.panel_vis.manually_hidden
        if not getattr(self.window, 'pip_mode', False) and not getattr(self.window, 'is_fullscreen', False) and not manually_hidden:
            if event_type == QEvent.Type.Leave:
                if obj is self.window or obj is getattr(self.window, 'video_widget', None) or obj is getattr(self.window, 'central_widget', None):
                    if hasattr(self.window, '_delayed_hide_floating_panels'):
                        safe_single_shot(200, self.window, self.window._delayed_hide_floating_panels)
            elif event_type == QEvent.Type.Enter:
                if obj is self.window or obj is getattr(self.window, 'video_widget', None):
                    if hasattr(self.window, '_show_floating_panels_on_enter'):
                        self.window._show_floating_panels_on_enter()
                else:
                    for panel_name in ('epg_panel', 'playlist_panel', 'floating_panel'):
                        panel = getattr(self.window, panel_name, None)
                        if panel and obj is panel:
                            if hasattr(self.window, '_show_floating_panels_on_enter'):
                                self.window._show_floating_panels_on_enter()
                            break

        return False

    def _is_input_widget_focused(self) -> bool:
        """判断当前焦点是否在输入控件上（编辑框、文本框等）"""
        focus_widget = QApplication.focusWidget()
        if focus_widget:
            if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox)):
                return True
            if isinstance(focus_widget, QComboBox) and focus_widget.isEditable():
                return True
        return False

    def _is_handled_shortcut(self, key, modifiers) -> bool:
        """判断按键组合是否由 eventFilter 统一处理（用于拦截 ShortcutOverride）"""
        # 对话框打开或活动窗口不属于本应用时，不抢占任何按键
        if self._has_open_dialog() or not self._is_app_window_active():
            return False
        if self._is_input_widget_focused():
            return False
        # 快捷键速查浮层（? 键；Shift+/ 与直接 ? 两种键盘布局均支持）
        if key == Qt.Key.Key_Question:
            return True
        # _is_input_widget_focused() 已在上方检查，此处无需重复判断
        if modifiers == Qt.KeyboardModifier.NoModifier:
            # 注意：Tab 与 Space 不在此列表中，交回 Qt 处理焦点移动与控件激活
            global_keys = (Qt.Key.Key_Escape,
                           Qt.Key.Key_F, Qt.Key.Key_E,
                           Qt.Key.Key_L,
                           Qt.Key.Key_Y,
                           Qt.Key.Key_F5, Qt.Key.Key_F11,
                           Qt.Key.Key_Backspace, Qt.Key.Key_S,
                           Qt.Key.Key_Period, Qt.Key.Key_Comma,
                           Qt.Key.Key_P,
                           # 字幕快捷键
                           Qt.Key.Key_V, Qt.Key.Key_Z, Qt.Key.Key_X,
                           Qt.Key.Key_Q, Qt.Key.Key_W,
                           # 视频图像调整快捷键
                           Qt.Key.Key_3, Qt.Key.Key_4,
                           Qt.Key.Key_5, Qt.Key.Key_6,
                           Qt.Key.Key_7, Qt.Key.Key_8,
                           Qt.Key.Key_9, Qt.Key.Key_0,
                           Qt.Key.Key_R, Qt.Key.Key_T,
                           # 音频调整快捷键
                           Qt.Key.Key_Minus, Qt.Key.Key_Equal,
                           Qt.Key.Key_G, Qt.Key.Key_H,
                           # 播放队列与控制快捷键
                           Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                           Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_C,
                           Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight,
                           Qt.Key.Key_J,
                           # 悬浮面板显隐（分发逻辑中有 Key_M，此处需对齐）
                           Qt.Key.Key_M)
            main_only_keys = (Qt.Key.Key_Up, Qt.Key.Key_Down,
                              Qt.Key.Key_Left, Qt.Key.Key_Right)
            # Backspace 已被上方 _is_input_widget_focused() 检查拦截，此处无需重复判断
            if key in global_keys:
                return True
            # 方向键仅在视频区域聚焦且非多画面时接管（多画面交给单元格自己处理）
            if key in main_only_keys and self._is_player_focus() and not self._is_multi_screen_active():
                return True
            return False
        elif modifiers == Qt.KeyboardModifier.ControlModifier:
            return key in (Qt.Key.Key_O, Qt.Key.Key_S, Qt.Key.Key_Q,
                           Qt.Key.Key_U)
        elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_O:
                return True
            if key == Qt.Key.Key_B:
                return True
            if key in (Qt.Key.Key_S, Qt.Key.Key_M, Qt.Key.Key_E, Qt.Key.Key_R, Qt.Key.Key_F):
                return True
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self._is_player_focus() and not self._is_multi_screen_active():
                return True
            return False
        return False

    def _handle_global_shortcut(self, key, modifiers) -> bool:
        """统一快捷键分发（所有快捷键在此处理，保证可靠触发）"""
        try:
            # 对话框打开时把按键交回对话框；活动窗口不属于本应用时不响应
            if self._has_open_dialog() or not self._is_app_window_active():
                return False
            if self._is_input_widget_focused():
                return False
            w = self.window

            # 快捷键速查浮层：? 键切换；浮层开启时任意快捷键先将其关闭
            overlay = getattr(w, '_shortcut_overlay', None)
            if key == Qt.Key.Key_Question:
                self.toggle_shortcut_overlay()
                return True
            if overlay is not None and overlay.isVisible():
                overlay.close()
                w._shortcut_overlay = None

            if modifiers == Qt.KeyboardModifier.NoModifier:
                if key == Qt.Key.Key_Space:
                    # 多画面激活时由获得焦点的单元格处理，主播放器不响应
                    if self._is_multi_screen_active():
                        return False
                    # 焦点在按钮/列表等控件上时交回控件（Space 激活控件）
                    if not self._is_player_focus():
                        return False
                    if hasattr(w, 'playback_ctrl'):
                        w.playback_ctrl.toggle_play()
                    return True
                elif key == Qt.Key.Key_Escape:
                    # 多画面激活时先退出多画面
                    if self._is_multi_screen_active():
                        ms = getattr(w, 'multi_screen_ctrl', None)
                        if ms and hasattr(ms, 'exit_multi_screen'):
                            ms.exit_multi_screen()
                            return True
                        return False
                    if not self._is_app_window_active():
                        return False
                    if hasattr(w, 'isFullScreen') and w.isFullScreen():
                        w.toggle_fullscreen()
                    elif hasattr(w, 'playback_ctrl'):
                        w.playback_ctrl.stop_playback()
                    return True
                elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                             Qt.Key.Key_Left, Qt.Key.Key_Right):
                    if self._is_multi_screen_active():
                        ms = getattr(w, 'multi_screen_ctrl', None)
                        if ms and hasattr(ms, 'move_focus'):
                            ms.move_focus(key)
                            return True
                        return False
                    if not self._is_player_focus():
                        return False
                    if key == Qt.Key.Key_Up:
                        self._switch_channel(-1)
                    elif key == Qt.Key.Key_Down:
                        self._switch_channel(1)
                    elif key == Qt.Key.Key_Left:
                        self._seek_relative(-10)
                    elif key == Qt.Key.Key_Right:
                        self._seek_relative(10)
                    return True
                elif key == Qt.Key.Key_F:
                    if hasattr(w, 'toggle_fullscreen'):
                        w.toggle_fullscreen()
                    return True
                elif key == Qt.Key.Key_E:
                    if hasattr(w, 'toggle_epg'):
                        w.toggle_epg(None)
                    return True
                elif key == Qt.Key.Key_L:
                    if hasattr(w, 'toggle_playlist'):
                        w.toggle_playlist(None)
                    return True
                elif key == Qt.Key.Key_M:
                    if hasattr(w, 'toggle_floating_panel'):
                        w.toggle_floating_panel(None)
                    return True
                elif key == Qt.Key.Key_Y:
                    if hasattr(w, 'toggle_hide_floating'):
                        logger.debug("eventFilter: Y key pressed, calling toggle_hide_floating")
                        w.toggle_hide_floating(None)
                    return True
                elif key == Qt.Key.Key_F5:
                    if hasattr(w, 'refresh_ui'):
                        w.refresh_ui()
                    return True
                elif key == Qt.Key.Key_F11:
                    if hasattr(w, 'toggle_fullscreen'):
                        w.toggle_fullscreen()
                    return True
                elif key == Qt.Key.Key_Backspace:
                    if self._is_input_widget_focused():
                        return False
                    if hasattr(w, 'switch_to_previous_channel'):
                        w.switch_to_previous_channel()
                    return True
                elif key == Qt.Key.Key_S:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.take_screenshot()
                    return True
                elif key == Qt.Key.Key_Period:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_speed(0.1)
                    return True
                elif key == Qt.Key.Key_Comma:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_speed(-0.1)
                    return True
                elif key == Qt.Key.Key_P:
                    if hasattr(w, 'pip_ctrl'):
                        w.pip_ctrl.toggle()
                    return True
                # 字幕可见性切换（V）
                elif key == Qt.Key.Key_V:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.toggle_subtitle_visibility()
                    return True
                # 字幕延迟 -0.1/+0.1（Z/X）
                elif key == Qt.Key.Key_Z:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_subtitle_delay(-0.1)
                    return True
                elif key == Qt.Key.Key_X:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_subtitle_delay(0.1)
                    return True
                # 字幕缩放 -0.1/+0.1（Q/W）
                elif key == Qt.Key.Key_Q:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_subtitle_scale(-0.1)
                    return True
                elif key == Qt.Key.Key_W:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_subtitle_scale(0.1)
                    return True
                # 视频图像调整：亮度(3/4) 对比度(5/6) 饱和度(7/8) Gamma(9/0)
                elif key == Qt.Key.Key_3:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('brightness', -2)
                    return True
                elif key == Qt.Key.Key_4:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('brightness', 2)
                    return True
                elif key == Qt.Key.Key_5:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('contrast', -2)
                    return True
                elif key == Qt.Key.Key_6:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('contrast', 2)
                    return True
                elif key == Qt.Key.Key_7:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('saturation', -2)
                    return True
                elif key == Qt.Key.Key_8:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('saturation', 2)
                    return True
                elif key == Qt.Key.Key_9:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('gamma', -2)
                    return True
                elif key == Qt.Key.Key_0:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_video_eq('gamma', 2)
                    return True
                # 画面旋转循环（R）/ 翻转循环（T）
                elif key == Qt.Key.Key_R:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.cycle_video_rotate(90)
                    return True
                elif key == Qt.Key.Key_T:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.toggle_video_flip()
                    return True
                # 音频延迟 -0.1/+0.1（-/=）
                elif key == Qt.Key.Key_Minus:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_audio_delay(-0.1)
                    return True
                elif key == Qt.Key.Key_Equal:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_audio_delay(0.1)
                    return True
                # 音调补偿 -0.05/+0.05（G/H）
                elif key == Qt.Key.Key_G:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_audio_pitch(-0.05)
                    return True
                elif key == Qt.Key.Key_H:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.adjust_audio_pitch(0.05)
                    return True
                # ---------- 播放队列与控制 ----------
                # 上一/下一文件（PageUp/PageDown）
                elif key == Qt.Key.Key_PageUp:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.play_previous_file()
                    return True
                elif key == Qt.Key.Key_PageDown:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.play_next_file()
                    return True
                # A-B 循环：A 设 A 点 / B 设 B 点 / C 清除
                elif key == Qt.Key.Key_A:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.ab_loop_set_a()
                    return True
                elif key == Qt.Key.Key_B:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.ab_loop_set_b()
                    return True
                elif key == Qt.Key.Key_C:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.ab_loop_clear()
                    return True
                # 逐帧：[ 后退一帧 / ] 前进一帧
                elif key == Qt.Key.Key_BracketLeft:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.frame_back_step()
                    return True
                elif key == Qt.Key.Key_BracketRight:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.frame_step()
                    return True
                # 静音切换（J）：分屏激活时作用于当前单元格，避免解除主播放器静音造成串音
                elif key == Qt.Key.Key_J:
                    if self._is_multi_screen_active():
                        ms = getattr(w, 'multi_screen_ctrl', None)
                        if ms and hasattr(ms, 'toggle_focused_mute'):
                            ms.toggle_focused_mute()
                            return True
                    if hasattr(w, 'toggle_mute'):
                        w.toggle_mute()
                    return True

            elif modifiers == Qt.KeyboardModifier.ControlModifier:
                if key == Qt.Key.Key_O:
                    if hasattr(w, 'settings_ops'):
                        w.settings_ops.open_playlist()
                    return True
                elif key == Qt.Key.Key_S:
                    if hasattr(w, 'settings_ops'):
                        w.settings_ops.save_as()
                    return True
                elif key == Qt.Key.Key_Q:
                    w.close()
                    return True
                elif key == Qt.Key.Key_U:
                    if hasattr(w, '_open_stream'):
                        w._open_stream()
                    return True


            elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                    if not self._is_player_focus() or self._is_multi_screen_active():
                        return False
                    if key == Qt.Key.Key_Left:
                        self._switch_channel(-1)
                    else:
                        self._switch_channel(1)
                    return True
                elif key == Qt.Key.Key_O:
                    if hasattr(w, '_open_video_file'):
                        w._open_video_file()
                    return True
                elif key == Qt.Key.Key_B:
                    if hasattr(w, 'media_ctrl'):
                        w.media_ctrl.add_bookmark_now()
                    return True
                elif key == Qt.Key.Key_S:
                    if hasattr(w, 'open_scan_ui'):
                        w.open_scan_ui()
                    return True
                elif key == Qt.Key.Key_M:
                    if hasattr(w, 'open_channel_mapping'):
                        w.open_channel_mapping()
                    return True
                elif key == Qt.Key.Key_E:
                    if hasattr(w, 'ui_ctrl') and hasattr(w.ui_ctrl, '_show_epg_timeline'):
                        w.ui_ctrl._show_epg_timeline()
                    return True
                elif key == Qt.Key.Key_R:
                    if hasattr(w, 'ui_ctrl') and hasattr(w.ui_ctrl, '_show_reminder_manager'):
                        w.ui_ctrl._show_reminder_manager()
                    return True
                elif key == Qt.Key.Key_F:
                    if hasattr(w, 'ui_ctrl') and hasattr(w.ui_ctrl, '_show_global_search'):
                        w.ui_ctrl._show_global_search()
                    return True

        except Exception as e:
            logger.error(f"快捷键处理失败(key={key}, mod={modifiers}): {e}")

        return False

    def toggle_shortcut_overlay(self):
        """切换快捷键速查浮层（? 键触发；再次按 ? 或任意快捷键关闭）"""
        w = self.window
        overlay = getattr(w, '_shortcut_overlay', None)
        if overlay is not None and overlay.isVisible():
            overlay.close()
            w._shortcut_overlay = None
            return

        from ui.styles import AppStyles

        tr = w.language_manager.tr
        rows = [
            ("Space", tr("sc_play_pause", "播放 / 暂停")),
            ("↑ / ↓", tr("sc_channel_switch", "上一 / 下一频道")),
            ("← / →", tr("sc_seek_10s", "快退 / 快进 10 秒")),
            ("Backspace", tr("sc_prev_channel", "上一个频道")),
            ("F / F11", tr("sc_fullscreen", "全屏切换")),
            ("Esc", tr("sc_exit_or_stop", "退出全屏 / 停止播放")),
            ("E", tr("sc_epg", "节目单")),
            ("L", tr("sc_playlist", "频道列表")),
            ("M", tr("sc_control_panel", "控制面板")),
            ("Y", tr("sc_hide_panels", "隐藏悬浮面板")),
            ("J", tr("sc_mute", "静音切换")),
            ("S", tr("sc_screenshot", "截图")),
            ("P", tr("sc_pip", "画中画")),
            ("V", tr("sc_subtitle_toggle", "字幕显示 / 隐藏")),
            ("Z / X", tr("sc_subtitle_delay", "字幕延迟 ±0.1s")),
            ("Q / W", tr("sc_subtitle_scale", "字幕缩放 ±0.1")),
            (", / .", tr("sc_speed", "倍速 ±0.1x")),
            ("- / =", tr("sc_audio_delay", "音频延迟 ±0.1s")),
            ("G / H", tr("sc_audio_pitch", "音调补偿 ±0.05")),
            ("R / T", tr("sc_rotate_flip", "画面旋转 / 翻转")),
            ("[ / ]", tr("sc_frame_step", "逐帧后退 / 前进")),
            ("3-0", tr("sc_video_eq", "亮度/对比度/饱和度/Gamma")),
            ("A / B / C", tr("sc_ab_loop", "AB 循环设点 / 清除")),
            ("PgUp / PgDn", tr("sc_prev_next_file", "上一 / 下一文件")),
            ("Ctrl+O / S / Q", tr("sc_file_ops", "打开订阅 / 另存 / 退出")),
            ("Ctrl+U", tr("sc_open_stream", "打开网络流")),
            ("Ctrl+Shift+O", tr("sc_open_video", "打开本地视频")),
            ("Ctrl+Shift+B", tr("sc_bookmark", "添加书签")),
            ("Ctrl+Shift+E/R/F", tr("sc_tools", "EPG 时间轴 / 提醒 / 全局搜索")),
            ("Ctrl+Shift+S/M", tr("sc_scan_mapping", "扫描频道 / 频道映射")),
            ("?", tr("sc_help_hint", "本速查浮层")),
        ]


        overlay = QWidget(w, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        overlay.setObjectName("shortcutOverlay")
        overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        overlay.setStyleSheet(AppStyles.shortcut_overlay_style())

        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        title = QLabel(tr("shortcut_cheatsheet", "快捷键速查（按 ? 或任意键关闭）"))
        title.setProperty("role", "title")
        layout.addWidget(title)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        half = (len(rows) + 1) // 2
        for chunk in (rows[:half], rows[half:]):
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(4)
            for r, (k, desc) in enumerate(chunk):
                key_lbl = QLabel(k)
                key_lbl.setProperty("role", "key")
                key_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(key_lbl, r, 0)
                grid.addWidget(QLabel(desc), r, 1)
            columns.addLayout(grid)
        layout.addLayout(columns)

        overlay.adjustSize()
        geo = w.frameGeometry()
        x = geo.center().x() - overlay.width() // 2
        y = geo.center().y() - overlay.height() // 2
        overlay.move(max(0, x), max(0, y))
        overlay.show()
        w._shortcut_overlay = overlay

    def _switch_channel(self, direction: int):
        """切换频道（-1=上一个，1=下一个），按当前激活的播放列表页签取列表"""
        w = self.window
        active_list = getattr(w, 'active_channel_list', None)
        if active_list is None:
            active_list = getattr(w, 'channel_list', None)
        if active_list is None:
            return

        total_rows = active_list.count()
        if total_rows == 0:
            return

        current_row = active_list.currentRow()
        # currentRow 为 -1（未选中）时按方向取首/尾，避免负数取模跳到倒数第二行
        if current_row < 0:
            new_row = 0 if direction > 0 else total_rows - 1
        else:
            new_row = (current_row + direction) % total_rows
        active_list.setCurrentRow(new_row)

        item = active_list.currentItem()
        if item is None:
            return

        # 收藏/历史页签的索引指向各自的服务数据，不能交给 select_channel 解析
        favorites_ctrl = getattr(w, 'favorites_ctrl', None)
        if favorites_ctrl:
            if active_list is getattr(w, 'fav_channel_list', None):
                favorites_ctrl.on_favorite_item_clicked(item)
                return
            if active_list is getattr(w, 'history_channel_list', None):
                favorites_ctrl.on_history_item_clicked(item)
                return

        if hasattr(w, 'select_channel'):
            w.select_channel(item, source_list=active_list)

    def _is_local_file_playing(self) -> bool:
        """判断当前是否在播放本地视频文件或回看/时移（支持seek）"""
        w = self.window
        if not hasattr(w, 'player_controller') or not w.player_controller or not w.player_controller.is_playing:
            return False
        if hasattr(w, '_is_local_file') and w._is_local_file():
            return True
        if hasattr(w, 'play_state') and w.play_state.is_catchup_or_timeshift:
            return True
        return False

    def _seek_relative(self, seconds: float):
        """相对跳转（seconds为正快进，为负快退）"""
        w = self.window
        if not hasattr(w, 'player_controller') or not w.player_controller:
            return
        if not w.player_controller.is_playing:
            return
        try:
            w.player_controller.seek_relative_seconds(seconds)
        except Exception as e:
            logger.debug(f"快进快退失败: {e}")

    def _on_mouse_activity(self):
        """鼠标活动回调 - 通知主窗口"""
        if hasattr(self.window, '_on_mouse_activity'):
            self.window._on_mouse_activity()

    def showEvent(self, event):
        """窗口首次显示后，延迟定位悬浮窗"""
        if hasattr(self.window, 'showEvent'):
            QMainWindow.showEvent(self.window, event)

        has_panels = (hasattr(self.window, 'epg_dock') and self.window.epg_dock and
                      hasattr(self.window, 'playlist_dock') and self.window.playlist_dock and
                      hasattr(self.window, 'floating_dock') and self.window.floating_dock)

        if has_panels and not getattr(self.window, '_initial_position_fixed', False):
            safe_single_shot(50, self.window, self._deferred_position_docks)
            safe_single_shot(200, self.window, self._deferred_position_docks)

    def _deferred_position_docks(self):
        """延迟到事件循环下一帧执行定位（确保主窗口geometry已稳定）"""
        try:
            app = QApplication.instance()
            if app:
                app.processEvents()

            config = getattr(self.window, 'config', None)
            if config:
                defaults = {
                    'epg_visible': True,
                    'playlist_visible': True,
                    'floating_visible': True,
                    'epg_width': 280,
                    'playlist_width': 280,
                    'floating_width': 1050,
                }
                settings = config.load_ui_settings(defaults)

                # 尊重用户保存的面板可见性设置，而非强制全部显示
                self.window.epg_visible = settings.get('epg_visible', True)
                self.window.playlist_visible = settings.get('playlist_visible', True)
                self.window.floating_panel_visible = settings.get('floating_visible', True)

                epg_w = 280
                if hasattr(self.window, 'epg_dock') and self.window.epg_dock:
                    epg_w = max(200, settings.get('epg_width', 280))
                    self.window.epg_dock.setMinimumWidth(epg_w)
                    self.window.epg_dock.resize(epg_w, self.window.epg_dock.height())
                if hasattr(self.window, 'playlist_dock') and self.window.playlist_dock:
                    pl_w = max(200, settings.get('playlist_width', epg_w))
                    self.window.playlist_dock.setMinimumWidth(pl_w)
                    self.window.playlist_dock.resize(pl_w, self.window.playlist_dock.height())
                if hasattr(self.window, 'floating_dock') and self.window.floating_dock:
                    self.window.floating_dock.setMinimumWidth(max(480, settings.get('floating_width', 1050)))

            self.window.update_floating_position()
        except Exception as e:
            logger.error(f"延迟定位悬浮窗失败: {e}")

    def changeEvent(self, event):
        """窗口状态变化事件"""
        if not self.window:
            return
        if hasattr(self.window, 'changeEvent'):
            try:
                QMainWindow.changeEvent(self.window, event)
            except (AttributeError, TypeError):
                pass

        if event.type() == QEvent.Type.ActivationChange:
            if self.window and self.window.isActiveWindow():
                if not getattr(self.window, 'pip_mode', False):
                    self.window.raise_()
                    if hasattr(self.window, 'raise_floating_panels'):
                        self.window.raise_floating_panels()
                    if getattr(self.window, 'is_fullscreen', False):
                        if getattr(self.window, 'panel_vis', None) and self.window.panel_vis.is_auto_hidden:
                            if hasattr(self.window, '_show_floating_panels_on_enter'):
                                self.window._show_floating_panels_on_enter()
                    if hasattr(self.window, '_on_main_window_activated'):
                        self.window._on_main_window_activated()
            else:
                if hasattr(self.window, '_on_main_window_deactivated'):
                    self.window._on_main_window_deactivated()

    def moveEvent(self, event):
        """窗口移动事件 - 跟随定位浮动Dock（节流）"""
        if getattr(self.window, 'pip_mode', False):
            if hasattr(self.window, 'pip_ctrl'):
                self.window.pip_ctrl._update_overlay_geometry()
            return
        self._schedule_position_update()

    def resizeEvent(self, event):
        """窗口大小变化事件 - 跟随重定位浮动Dock（节流）"""
        if getattr(self.window, 'pip_mode', False):
            if hasattr(self.window, 'pip_ctrl'):
                self.window.pip_ctrl._update_overlay_geometry()
                self.window.pip_ctrl._update_video_geometry()
            return
        self._schedule_position_update()

    def _schedule_position_update(self):
        if not hasattr(self, '_position_timer'):
            self._position_timer = QTimer(self.window)
            self._position_timer.setSingleShot(True)
            self._position_timer.setInterval(16)
            self._position_timer.timeout.connect(self._do_position_update)
        if not self._position_timer.isActive():
            self._position_timer.start()

    def _do_position_update(self):
        if hasattr(self.window, 'update_floating_position'):
            self.window.update_floating_position()

    def closeEvent(self, event):
        """窗口关闭事件"""
        logger.debug("关闭事件 - 清理所有资源")

        if hasattr(self.window, '_stop_auto_hide_timer'):
            self.window._stop_auto_hide_timer()

        try:
            from ui.theme_manager import get_theme_manager
            tm = get_theme_manager()
            tm._stop_system_theme_watcher()
            tm._windows.clear()
        except Exception as e:
            logger.debug(f"清理主题管理器失败: {e}")

        # 1. 保存窗口布局
        if hasattr(self.window, 'settings_ops'):
            try:
                self.window.settings_ops.save_window_layout()
            except Exception as e:
                logger.error(f"保存窗口布局失败: {e}")

        # 1.5 保存当前频道
        if hasattr(self.window, 'current_channel') and hasattr(self.window, 'config'):
            try:
                ch = self.window.current_channel
                if ch:
                    ch_name = ch.get('name', '')
                    ch_url = ch.get('url', '')
                    is_local = (getattr(self.window, 'channel_list', None)
                                is getattr(self.window, 'local_channel_list', None))
                    # 同名多源时频道名无法唯一确定频道，优先按 URL 定位；
                    # 当前激活的列表优先，避免订阅/本地存在同 URL 时记错来源
                    ordered_attrs = (('_local_channels', '_sub_channels') if is_local
                                     else ('_sub_channels', '_local_channels'))
                    ch_idx = -1
                    if ch_url:
                        for attr in ordered_attrs:
                            for i, c in enumerate(getattr(self.window, attr, []) or []):
                                if c.get('url') == ch_url:
                                    ch_idx = i
                                    break
                            if ch_idx >= 0:
                                break
                    if ch_idx < 0 and ch_name:
                        # URL 缺失（如回看/时移期间被改写）时退回名字匹配
                        for attr in ordered_attrs:
                            for i, c in enumerate(getattr(self.window, attr, []) or []):
                                if c.get('name', '') == ch_name:
                                    ch_idx = i
                                    break
                            if ch_idx >= 0:
                                break
                    ch_file = getattr(self.window, '_local_playlist_path', '') if is_local else getattr(self.window, '_subscription_url', '')
                    # url 作为恢复时的首要匹配键，与 channel_mixin 选择频道时的写入保持一致
                    self.window.config.set_value('Player', 'last_channel_url', ch_url or '')
                    self.window.config.save_last_channel(ch_file, ch_name, ch_idx)
            except Exception as e:
                logger.debug(f"保存最后频道失败: {e}")

        # 屏保：先退出覆盖层并释放对空闲停绘的 hold，再关闭空闲控制器
        screensaver = getattr(self.window, 'screensaver_controller', None)
        if screensaver is not None:
            try:
                screensaver.shutdown()
            except Exception as e:
                logger.debug(f"关闭屏保失败: {e}")

        # 2. 先停止所有可能访问mpv_handle的定时器（必须在终止MPV之前！）
        idle_render = getattr(self.window, '_idle_render', None)
        if idle_render is not None:
            try:
                # restore=False：不唤醒被空闲停绘挂起的定时器，避免 mpv 终止后被回调访问
                idle_render.shutdown(restore=False)
            except Exception as e:
                logger.debug(f"关闭空闲停绘失败: {e}")
        timer_attrs = ['update_timer', '_source_timeout_timer', '_auto_hide_timer']
        for attr in timer_attrs:
            timer = getattr(self.window, attr, None)
            if timer:
                try:
                    timer.stop()
                except Exception as e:
                    logger.debug(f"停止定时器{attr}失败: {e}")
        sub_ctrl = getattr(self.window, 'subscription_ctrl', None)
        if sub_ctrl and hasattr(sub_ctrl, '_refresh_timer') and sub_ctrl._refresh_timer:
            try:
                sub_ctrl._refresh_timer.stop()
            except Exception as e:
                logger.debug(f"停止订阅刷新定时器失败: {e}")
        if hasattr(self, '_position_timer'):
            try:
                self._position_timer.stop()
            except Exception as e:
                logger.debug(f"停止位置定时器失败: {e}")

        # 3. 终止MPV播放器（定时器已停止，不会再访问mpv_handle）
        if hasattr(self.window, 'player_controller') and self.window.player_controller:
            try:
                logger.debug("正在终止MPV播放器...")
                if hasattr(self.window.player_controller, 'terminate'):
                    self.window.player_controller.terminate()
                else:
                    self.window.player_controller.stop()
                logger.info("MPV播放器已终止")
            except Exception as e:
                logger.error(f"终止MPV播放器失败: {e}")

        # 3.5 终止多画面控制器
        if hasattr(self.window, 'multi_screen_ctrl') and self.window.multi_screen_ctrl:
            try:
                self.window.multi_screen_ctrl.terminate()
            except Exception as e:
                logger.error(f"终止多画面控制器失败: {e}")

        # 4. 关闭扫描窗口
        scan_dialog = getattr(self.window, '_scan_dialog', None) or getattr(self.window, 'scan_window', None)
        if scan_dialog:
            try:
                scan_dialog.close()
                scan_dialog.deleteLater()
            except Exception as e:
                logger.debug(f"关闭扫描窗口失败: {e}")
            self.window._scan_dialog = None
            self.window.scan_window = None

        # 5. 关闭所有悬浮窗
        for panel_name in ['floating_panel', 'epg_panel', 'playlist_panel']:
            panel = getattr(self.window, panel_name, None)
            if panel:
                try:
                    logger.debug(f"关闭悬浮窗: {panel_name}")
                    panel.close()
                    panel.deleteLater()
                except Exception as e:
                    logger.error(f"关闭{panel_name}失败: {e}")
                setattr(self.window, panel_name, None)

        # 6. 停止缩略图服务
        if hasattr(self.window, '_thumbnail_service'):
            try:
                self.window._thumbnail_service.stop()
            except Exception as e:
                logger.debug(f"停止缩略图服务失败: {e}")

        # 6.5 停止台标缓存服务
        logo_svc = getattr(self.window, '_logo_cache_service', None)
        if logo_svc:
            try:
                warmup_timer = getattr(logo_svc, '_warmup_timer', None)
                if warmup_timer:
                    warmup_timer.stop()
            except Exception as e:
                logger.debug(f"停止台标缓存定时器失败: {e}")

        # 6.7 停止EPG提醒服务
        epg_reminder = getattr(self.window, 'epg_reminder_ctrl', None)
        if epg_reminder and hasattr(epg_reminder, '_reminder_service'):
            try:
                epg_reminder._reminder_service.stop()
            except Exception as e:
                logger.debug(f"停止EPG提醒服务失败: {e}")

        # 6.8 停止FCC服务（真实持有者是 playback_controller.fcc）
        playback_ctrl = getattr(self.window, 'playback_ctrl', None)
        fcc_service = getattr(playback_ctrl, 'fcc', None)
        if fcc_service and hasattr(fcc_service, 'on_stop'):
            try:
                fcc_service.on_stop()
            except Exception as e:
                logger.debug(f"停止FCC服务失败: {e}")

        # 6.85 清理代理样式
        proxy_style = getattr(self.window, '_menu_proxy_style', None)
        if proxy_style:
            try:
                proxy_style.deleteLater()
            except Exception as e:
                logger.debug(f"清理代理样式失败: {e}")

        # 6.9 清理系统托盘
        tray = getattr(self.window, '_system_tray', None)
        if tray:
            try:
                tray.hide()
                tray.deleteLater()
            except Exception as e:
                logger.debug(f"清理系统托盘失败: {e}")
            self.window._system_tray = None

        # 6.10 执行注册的资源清理器
        try:
            from utils.resource_cleaner import cleanup_all
            cleanup_all()
        except Exception as e:
            logger.debug(f"执行资源清理器失败: {e}")

        # 6.11 刷新配置写入（确保防抖的save_config落盘）
        try:
            if hasattr(self.window, 'config'):
                self.window.config.flush()
        except Exception as e:
            logger.debug(f"刷新配置写入失败: {e}")

        # 7. 等待后台工作线程完成
        if hasattr(self.window, 'subscription_ctrl'):
            # 复制 workers 列表避免遍历过程中被修改导致竞争
            workers = list(self.window.subscription_ctrl._workers)
            for worker in workers:
                if worker.isRunning():
                    try:
                        worker.requestInterruption()
                        if not worker.wait(3000):
                            logger.warning(f"工作线程 {worker} 未在3秒内退出，将随进程终止")
                    except Exception as e:
                        logger.debug(f"等待工作线程失败: {e}")

        # 7.5 断开控制器与主窗口的引用循环
        controller_attrs = [
            'window_ctrl', 'playback_ctrl', 'epg_ctrl', 'channel_ctrl',
            'settings_ops', 'ui_ctrl', 'subscription_ctrl', 'subscription_ui_ctrl',
            'catchup_ctrl', 'pip_ctrl', 'media_ctrl', 'update_ctrl',
            'favorites_ctrl', 'epg_reminder_ctrl', 'event_handler',
            'multi_screen_ctrl', 'progress_ctrl', 'file_queue_ctrl',
            'resume_ctrl', 'playback_settings_ctrl', 'skip_intro_outro_ctrl',
            'bookmark_ctrl', 'autocrop_service', 'undo_stack', 'clip_export_service',
        ]
        for attr in controller_attrs:
            ctrl = getattr(self.window, attr, None)
            if ctrl is not None:
                try:
                    if hasattr(ctrl, 'window'):
                        ctrl.window = None
                except Exception as e:
                    logger.debug(f"断开控制器{attr}引用失败: {e}")

        # 7.6 清理音视频/歌词 widget
        for widget_attr in ('_audio_visual_widget', '_lyrics_widget'):
            widget = getattr(self.window, widget_attr, None)
            if widget:
                try:
                    if hasattr(widget, 'stop'):
                        widget.stop()
                    widget.hide()
                    widget.deleteLater()
                except Exception as e:
                    logger.debug(f"清理{widget_attr}失败: {e}")
                setattr(self.window, widget_attr, None)

        # 7.7 清理 server 全局引用
        try:
            from server.app import set_main_window
            set_main_window(None)
        except Exception as e:
            logger.debug(f"清理 server main_window 引用失败: {e}")
        try:
            from server.context import ServerContext
            ServerContext._instance = None
        except Exception as e:
            logger.debug(f"清理 ServerContext 失败: {e}")

        # 8. 退出应用
        event.accept()

        try:
            QApplication.instance().quit()
        except Exception as e:
            logger.debug(f"应用退出失败: {e}")

    def register_shortcut(self, key_sequence: str, callback):
        """注册自定义快捷键"""
        self._shortcuts[key_sequence] = callback

    def unregister_shortcut(self, key_sequence: str):
        """注销快捷键"""
        if key_sequence in self._shortcuts:
            del self._shortcuts[key_sequence]
