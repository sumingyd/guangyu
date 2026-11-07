"""ContextMenuController — 从 MediaController 提取的子控制器。"""

import os
import re

from core.log_manager import global_logger as logger
from utils.thread_safety import safe_single_shot
from utils.delay_constants import DelayMs
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu


class ContextMenuController:
    """ContextMenuController — 通过 facade 访问主窗口和播放器。"""

    def __init__(self, facade):
        self._facade = facade

    def show_video_context_menu(self, pos):
        from ui.styles import AppStyles
        tr = self._facade.window.language_manager.tr
        menu = QMenu(self._facade.window)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())

        pc = self._facade.window.player_controller
        is_playing = pc and (pc.is_playing or getattr(pc, 'is_paused', False))

        # ---- 核心播放控制 ----
        if is_playing:
            play_pause_text = tr("ctx_pause", "Pause") if not getattr(pc, 'is_paused', False) else tr("ctx_play", "Play")
            menu.addAction(play_pause_text, lambda *a: self._facade.window.playback_ctrl.toggle_play())
            menu.addAction(tr("ctx_stop", "Stop"), lambda *a: self._facade.window.playback_ctrl.stop_playback())

            menu.addSeparator()

            menu.addAction(tr("ctx_prev_channel", "Previous Channel"), lambda *a: self._facade.window.event_handler._switch_channel(-1))
            menu.addAction(tr("ctx_next_channel", "Next Channel"), lambda *a: self._facade.window.event_handler._switch_channel(1))

            menu.addSeparator()

        # ---- 倍速/音量/比例 子菜单 ----
        speed_menu = menu.addMenu(tr("ctx_speed", "Speed"))
        speed_menu.setStyleSheet(AppStyles.player_menu_bar_style())
        try:
            current_speed = pc.get_speed() if pc and pc.is_playing else 1.0
        except Exception:
            current_speed = 1.0
        for s in self._facade.SPEED_STEPS:
            label = f"{s}x" + (" ✓" if abs(current_speed - s) < 0.01 else "")
            speed_menu.addAction(label, lambda *a, speed=s: self._facade._set_speed(speed))

        volume_menu = menu.addMenu(tr("ctx_volume", "Volume"))
        volume_menu.setStyleSheet(AppStyles.player_menu_bar_style())
        try:
            current_vol = pc.get_volume() if pc and pc.is_playing else 80
            is_muted = pc.get_mute() if pc and pc.is_playing else False
        except Exception:
            current_vol = 80
            is_muted = False
        mute_text = tr("ctx_unmute", "Unmute") if is_muted else tr("ctx_mute", "Mute")
        volume_menu.addAction(mute_text, lambda *a: self._facade.window.toggle_mute())
        volume_menu.addSeparator()
        for v in (0, 25, 50, 75, 100, 125, 150):
            label = f"{v}%" + (" ✓" if not is_muted and abs(current_vol - v) < 2 else "")
            volume_menu.addAction(label, lambda *a, vol=v: self._facade._set_volume(vol))

        aspect_menu = menu.addMenu(tr("ctx_aspect_ratio", "Aspect Ratio"))
        aspect_menu.setStyleSheet(AppStyles.player_menu_bar_style())
        aspect_labels = {
            'default': tr("ctx_aspect_default", "Default"),
            '16:9': '16:9',
            '4:3': '4:3',
            'stretch': tr("ctx_aspect_stretch", "Stretch"),
            'fill': tr("ctx_aspect_fill", "Fill"),
        }
        current_ratio = self._facade.ASPECT_CYCLE[self._facade._current_aspect_idx]
        for ratio in self._facade.ASPECT_CYCLE:
            label = aspect_labels.get(ratio, ratio) + (" ✓" if ratio == current_ratio else "")
            aspect_menu.addAction(label, lambda *a, r=ratio: self._facade._set_aspect(r))

        # ---- 播放中：音频与字幕 / 工具 子菜单 ----
        if is_playing:
            menu.addSeparator()

            # 音频与字幕
            audio_sub_menu = menu.addMenu(tr("ctx_audio_subtitle", "Audio & Subtitle"))
            audio_sub_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            audio_track_menu = audio_sub_menu.addMenu(tr("ctx_audio_track", "Audio Track"))
            audio_track_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            self._facade._populate_audio_menu(audio_track_menu)
            sub_track_menu = audio_sub_menu.addMenu(tr("ctx_subtitle", "Subtitle"))
            sub_track_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            self._facade._populate_subtitle_menu(sub_track_menu)
            audio_sub_menu.addSeparator()
            audio_sub_menu.addAction(tr("ctx_audio_eq", "Audio Equalizer..."), lambda *a: self._facade._show_audio_eq_dialog())
            audio_sub_menu.addAction(tr("ctx_video_eq", "Video Equalizer..."), lambda *a: self._facade._show_video_eq_dialog())

            # 工具
            tools_menu = menu.addMenu(tr("ctx_tools", "Tools"))
            tools_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            tools_menu.addAction(tr("ctx_screenshot", "Screenshot\tS"), lambda *a: self._facade._take_screenshot())
            tools_menu.addAction(tr("ctx_burst_screenshot", "Burst Screenshot..."), lambda *a: self._facade._show_burst_screenshot_dialog())
            tools_menu.addSeparator()
            tools_menu.addAction(tr("ctx_bookmarks", "Bookmarks & Chapters..."), lambda *a: self._facade._show_bookmark_dialog())
            tools_menu.addAction(tr("ctx_av_sync", "A/V Sync Monitor..."), lambda *a: self._facade._show_av_sync_dialog())
            tools_menu.addAction(tr("ctx_stream_quality", "Stream Quality..."), lambda *a: self._facade._show_stream_quality_dialog())
            tools_menu.addAction(tr("ctx_3d_video", "3D / 360° Video..."), lambda *a: self._facade._show_3d_dialog())
            tools_menu.addSeparator()
            tools_menu.addAction(tr("ctx_playback_queue", "Playback Queue..."), lambda *a: self._facade._show_playback_queue_dialog())
            tools_menu.addAction(tr("ctx_resume_list", "Resume Positions..."), lambda *a: self._facade._show_resume_list_dialog())
            tools_menu.addAction(tr("ctx_network_enhance", "Network Enhance..."), lambda *a: self._facade._show_network_enhance_dialog())

            # HDR 模式子菜单
            self._facade._populate_hdr_submenu(menu)

        if is_playing and self._facade._is_audio_only():
            vis_menu = menu.addMenu(tr("ctx_audio_visual", "音频可视化"))
            vis_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            self._facade._populate_visual_menu(vis_menu)

            lyrics_menu = menu.addMenu(tr("ctx_lyrics", "歌词"))
            lyrics_menu.setStyleSheet(AppStyles.player_menu_bar_style())
            self._facade._populate_lyrics_menu(lyrics_menu)

        menu.addSeparator()

        menu.addAction(tr("ctx_fullscreen", "Fullscreen\tF11"), lambda *a: self._facade.window.toggle_fullscreen())
        pip_action = menu.addAction(tr("ctx_pip", "Picture-in-Picture\tP"), lambda *a: self._facade.window.pip_ctrl.toggle())
        pip_action.setEnabled(is_playing)

        menu.addSeparator()

        view_menu = menu.addMenu(tr("ctx_view", "View"))
        view_menu.setStyleSheet(AppStyles.player_menu_bar_style())
        epg_action = view_menu.addAction(tr("ctx_epg", "EPG List\tE"))
        epg_action.setCheckable(True)
        epg_action.setChecked(self._facade.window.epg_visible)
        epg_action.triggered.connect(lambda checked=False: self._facade.window.toggle_epg())
        playlist_action = view_menu.addAction(tr("ctx_playlist", "Channel List\tL"))
        playlist_action.setCheckable(True)
        playlist_action.setChecked(self._facade.window.playlist_visible)
        playlist_action.triggered.connect(lambda checked=False: self._facade.window.toggle_playlist())
        panel_action = view_menu.addAction(tr("ctx_control_panel", "Control Panel\tM"))
        panel_action.setCheckable(True)
        panel_action.setChecked(self._facade.window.floating_panel_visible)
        panel_action.triggered.connect(lambda checked=False: self._facade.window.toggle_floating_panel())
        view_menu.addSeparator()
        view_menu.addAction(tr("ctx_hide_panels", "Hide Floating Panels\tY"), lambda *a: self._facade.window.toggle_hide_floating())
        view_menu.addAction(tr("ctx_reset_layout", "Reset Layout"), lambda *a: self._facade.window.reset_layout())

        menu.addSeparator()

        menu.addAction(tr("ctx_open_stream", "Open Stream\tCtrl+U"), lambda *a: self._facade.window._open_stream())
        menu.addAction(tr("ctx_open_video", "Open Video\tCtrl+Shift+O"), lambda *a: self._facade.window._open_video_file())
        menu.addSeparator()
        menu.addAction(tr("ctx_scan", "Scan & Organize"), lambda *a: self._facade.window.open_scan_ui())


        menu.exec(self._facade.window.video_frame.mapToGlobal(pos))

    def take_screenshot(self):
        self._facade._take_screenshot()

    def _take_screenshot(self):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        # 纯音频频道没有视频帧，截图会失败
        if hasattr(pc, '_has_video_track') and not pc._has_video_track():
            self._facade.window.status_bar_show_message(
                self._facade.window.language_manager.tr('screenshot_no_video',
                                                '当前频道无视频画面，无法截图'))
            return
        try:
            from datetime import datetime

            from utils.app_paths import get_cache_dir
            screenshot_dir = os.path.join(get_cache_dir(), 'screenshots')
            os.makedirs(screenshot_dir, exist_ok=True)

            channel_name = ''
            current = self._facade.window.current_channel
            if current:
                channel_name = current.get('name', '')
                channel_name = re.sub(r'[\\/:*?"<>|]', '_', channel_name)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{channel_name}_{timestamp}.png" if channel_name else f"screenshot_{timestamp}.png"
            filepath = os.path.join(screenshot_dir, filename)

            pc.send_command(['screenshot-to-file', filepath, 'video'])

            def _copy_to_clipboard():
                try:
                    clipboard = QApplication.clipboard()
                    pixmap = QPixmap(filepath)
                    if not pixmap.isNull():
                        clipboard.setPixmap(pixmap)
                except Exception as e:
                    logger.debug(f"截图复制到剪贴板失败: {e}")

            QTimer.singleShot(DelayMs.OSD_FADE, _copy_to_clipboard)

            self._facade.window.status_bar_show_message(
                f"{self._facade.window.language_manager.tr('screenshot_saved', 'Screenshot saved')}: {filename}")
        except Exception as e:
            logger.error(f"截图失败: {e}")

    def _populate_audio_menu(self, menu):
        menu.clear()
        pc = self._facade.window.player_controller
        tr = self._facade.window.language_manager.tr
        if not pc or not pc.is_playing:
            act = menu.addAction(tr('ctx_no_audio_track', 'No Audio Tracks'))
            act.setEnabled(False)
            return
        tracks = pc.get_track_list('audio')
        current_id = pc.get_current_track('audio')
        if not tracks:
            act = menu.addAction(tr('ctx_no_audio_track', 'No Audio Tracks'))
            act.setEnabled(False)
        else:
            actions = []
            for t in tracks:
                label = t.get('title') or t.get('lang') or tr('ctx_audio_track_n', 'Track {}').format(t['id'])
                if t.get('lang') and t.get('title') and t['lang'] != t['title']:
                    label = f"{t['title']} ({t['lang']})"
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(t['id'] == current_id)
                actions.append((act, t['id'], label))
            for act, tid, label in actions:
                act.triggered.connect(
                    lambda checked, tid=tid, label=label, actions=actions: self._facade._on_audio_track_selected(tid, label, actions)
                )

    def _on_audio_track_selected(self, track_id, label, actions):
        pc = self._facade.window.player_controller
        if not pc:
            return
        success = pc.set_track('audio', track_id)
        if success:
            for act, tid, _ in actions:
                act.setChecked(tid == track_id)
            tr = self._facade.window.language_manager.tr
            osd_text = tr('osd_audio_track', 'Audio: {}').format(label)
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(osd_text)
        else:
            tr = self._facade.window.language_manager.tr
            fallback_id = self._facade._try_fallback_track(pc, 'audio', track_id)
            if fallback_id is not None:
                fallback_label = ''
                for act, tid, lbl in actions:
                    if tid == fallback_id:
                        fallback_label = lbl
                        act.setChecked(True)
                    else:
                        act.setChecked(False)
                osd_text = tr('osd_audio_track_fallback', 'Audio track unavailable, switched to: {}').format(fallback_label)
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(osd_text)
            else:
                osd_text = tr('osd_audio_track_failed', 'Audio track switch failed')
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(osd_text)

    def _populate_subtitle_menu(self, menu):
        menu.clear()
        pc = self._facade.window.player_controller
        tr = self._facade.window.language_manager.tr
        if not pc or not pc.is_playing:
            act = menu.addAction(tr('ctx_no_subtitle', 'No Subtitle'))
            act.setEnabled(False)
            return
        current_id = pc.get_current_track('sub')
        tracks = pc.get_track_list('sub')
        sub_actions = []
        no_sub = menu.addAction(tr("ctx_no_subtitle", "No Subtitle"))
        no_sub.setCheckable(True)
        no_sub.setChecked(current_id is None or current_id == 0)
        sub_actions.append((no_sub, 0, tr("ctx_no_subtitle", "No Subtitle")))
        if tracks:
            menu.addSeparator()
            for t in tracks:
                label = t.get('title') or t.get('lang') or tr('ctx_subtitle_track_n', 'Sub {}').format(t['id'])
                if t.get('lang') and t.get('title') and t['lang'] != t['title']:
                    label = f"{t['title']} ({t['lang']})"
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(t['id'] == current_id)
                sub_actions.append((act, t['id'], label))
        for act, tid, label in sub_actions:
            act.triggered.connect(
                lambda checked, tid=tid, label=label, actions=sub_actions: self._facade._on_sub_track_selected(tid, label, actions)
            )
        menu.addSeparator()
        menu.addAction(tr("ctx_load_subtitle", "Load Subtitle..."), lambda *a: self._facade._load_external_subtitle())
        menu.addAction(tr("ctx_download_subtitle", "Download Subtitle..."), lambda *a: self._facade._download_subtitle())
        menu.addAction(tr("ctx_subtitle_style", "Subtitle Style..."), lambda *a: self._facade._show_subtitle_style_dialog())
        menu.addSeparator()
        # 字幕可见性切换
        sub_visible = pc.get_sub_visibility() if hasattr(pc, 'get_sub_visibility') else True
        vis_act = menu.addAction(tr("ctx_sub_visibility", "Show Subtitle"))
        vis_act.setCheckable(True)
        vis_act.setChecked(sub_visible)
        vis_act.triggered.connect(lambda checked=False: self._facade._toggle_sub_visibility())
        # 字幕延迟/缩放/位置快捷调整
        delay_menu = menu.addMenu(tr("ctx_sub_delay", "Subtitle Delay"))
        delay_menu.addAction('-0.5s', lambda *a: self._facade._adjust_sub_delay(-0.5))
        delay_menu.addAction('-0.1s', lambda *a: self._facade._adjust_sub_delay(-0.1))
        delay_menu.addAction('+0.1s', lambda *a: self._facade._adjust_sub_delay(0.1))
        delay_menu.addAction('+0.5s', lambda *a: self._facade._adjust_sub_delay(0.5))
        scale_menu = menu.addMenu(tr("ctx_sub_scale", "Subtitle Scale"))
        scale_menu.addAction('-0.1', lambda *a: self._facade._adjust_sub_scale(-0.1))
        scale_menu.addAction('+0.1', lambda *a: self._facade._adjust_sub_scale(0.1))
        scale_menu.addAction('1.0', lambda *a: self._facade._set_sub_scale(1.0))
        pos_menu = menu.addMenu(tr("ctx_sub_pos", "Subtitle Position"))
        pos_menu.addAction(tr("ctx_sub_pos_up", "Up"), lambda *a: self._facade._adjust_sub_pos(5))
        pos_menu.addAction(tr("ctx_sub_pos_down", "Down"), lambda *a: self._facade._adjust_sub_pos(-5))
        pos_menu.addAction(tr("ctx_sub_pos_reset", "Reset"), lambda *a: self._facade._set_sub_pos(100))

    def _on_sub_track_selected(self, track_id, label, actions):
        pc = self._facade.window.player_controller
        if not pc:
            return
        if track_id == 0:
            pc.set_track('sub', 'no')
            for act, tid, _ in actions:
                act.setChecked(tid == 0)
            tr = self._facade.window.language_manager.tr
            osd_text = tr('osd_subtitle_track', 'Subtitle: {}').format(label)
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(osd_text)
            return
        success = pc.set_track('sub', track_id)
        if success:
            for act, tid, _ in actions:
                act.setChecked(tid == track_id)
            tr = self._facade.window.language_manager.tr
            osd_text = tr('osd_subtitle_track', 'Subtitle: {}').format(label)
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(osd_text)
        else:
            tr = self._facade.window.language_manager.tr
            fallback_id = self._facade._try_fallback_track(pc, 'sub', track_id)
            if fallback_id is not None:
                fallback_label = ''
                for act, tid, lbl in actions:
                    if tid == fallback_id:
                        fallback_label = lbl
                        act.setChecked(True)
                    else:
                        act.setChecked(False)
                osd_text = tr('osd_sub_track_fallback', 'Subtitle track unavailable, switched to: {}').format(fallback_label)
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(osd_text)
            else:
                osd_text = tr('osd_subtitle_track_failed', 'Subtitle track switch failed')
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(osd_text)

    def _try_fallback_track(self, pc, track_type, failed_id):
        try:
            tracks = pc.get_track_list(track_type)
            if not tracks:
                return None
            current = pc.get_current_track(track_type)
            for t in tracks:
                if t['id'] != failed_id and t['id'] != current:
                    if pc.set_track(track_type, t['id']):
                        logger.info(f"轨道降级切换: {track_type} 从 {failed_id} 降级到 {t['id']}")
                        return t['id']
            if current and current != failed_id:
                return current
        except Exception as e:
            logger.debug(f"轨道降级切换失败: {e}")
        return None

    def _menu_anchor(self, attr: str):
        """菜单锚点：次级按钮已收入“更多”菜单，统一锚定到 more_button"""
        more = getattr(self._facade.window, 'more_button', None)
        if more is not None:
            return more
        return getattr(self._facade.window, attr, None)

    def _exec_menu_upward(self, menu, btn):
        """在按钮上方弹出菜单（控制栏位于底部，向下弹出会被屏幕裁剪）"""
        menu.adjustSize()
        top_left = btn.mapToGlobal(btn.rect().topLeft())
        y = top_left.y() - menu.sizeHint().height() - 4
        if y < 0:
            y = btn.mapToGlobal(btn.rect().bottomLeft()).y()
        menu.exec(QPoint(top_left.x(), y))

    def show_audio_track_menu(self):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        from ui.styles import AppStyles
        menu = QMenu(self._facade.window)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())
        self._facade._populate_audio_menu(menu)
        btn = self._facade._menu_anchor('audio_track_button')
        if btn:
            self._facade._exec_menu_upward(menu, btn)

    def show_sub_track_menu(self):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        from ui.styles import AppStyles
        menu = QMenu(self._facade.window)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())
        self._facade._populate_subtitle_menu(menu)
        btn = self._facade._menu_anchor('sub_track_button')
        if btn:
            self._facade._exec_menu_upward(menu, btn)

    def show_speed_menu(self):
        from ui.styles import AppStyles
        tr = self._facade.window.language_manager.tr
        menu = QMenu(self._facade.window)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())
        pc = self._facade.window.player_controller
        try:
            current_speed = pc.get_speed() if pc and pc.is_playing else 1.0
        except Exception:
            current_speed = 1.0
        for s in self._facade.SPEED_STEPS:
            label = f"{s}x" + (" ✓" if abs(current_speed - s) < 0.01 else "")
            menu.addAction(label, lambda *a, speed=s: self._facade._set_speed(speed))
        btn = self._facade._menu_anchor('speed_button')
        if btn:
            self._facade._exec_menu_upward(menu, btn)

    def show_aspect_menu(self):
        from ui.styles import AppStyles
        tr = self._facade.window.language_manager.tr
        menu = QMenu(self._facade.window)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())
        aspect_labels = {
            'default': tr("ctx_aspect_default", "Default"),
            '16:9': '16:9',
            '4:3': '4:3',
            'stretch': tr("ctx_aspect_stretch", "Stretch"),
            'fill': tr("ctx_aspect_fill", "Fill"),
        }
        current_ratio = self._facade.ASPECT_CYCLE[self._facade._current_aspect_idx]
        for ratio in self._facade.ASPECT_CYCLE:
            label = aspect_labels.get(ratio, ratio) + (" ✓" if ratio == current_ratio else "")
            menu.addAction(label, lambda *a, r=ratio: self._facade._set_aspect(r))
        btn = self._facade._menu_anchor('aspect_button')
        if btn:
            self._facade._exec_menu_upward(menu, btn)

    def _load_external_subtitle(self):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        tr = self._facade.window.language_manager.tr
        file_path, _ = QFileDialog.getOpenFileName(
            self._facade.window, tr("ctx_load_subtitle", "Load Subtitle..."), '',
            tr("ctx_subtitle_files", "Subtitle Files") + " (*.srt *.ass *.ssa *.sub *.idx *.vtt *.lrc);;" + tr("ctx_all_files", "All Files") + " (*)"
        )
        if file_path:
            if pc.add_subtitle_file(file_path):
                self._facade.window._show_osd_feedback(f"{tr('ctx_subtitle', 'Subtitle')}: {file_path.split('/')[-1].split(chr(92))[-1]}")

    def _show_subtitle_style_dialog(self):
        """打开字幕样式对话框"""
        try:
            from ui.dialogs.subtitle_style_dialog import SubtitleStyleDialog
            if not hasattr(self._facade.window, '_subtitle_style_dialog') or not self._facade.window._subtitle_style_dialog:
                self._facade.window._subtitle_style_dialog = SubtitleStyleDialog(self._facade.window)
            self._facade.window._subtitle_style_dialog.show()
            self._facade.window._subtitle_style_dialog.raise_()
            self._facade.window._subtitle_style_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开字幕样式对话框失败: {e}")

    def _download_subtitle(self):
        """打开字幕下载对话框"""
        try:
            from ui.dialogs.subtitle_style_dialog import SubtitleDownloadDialog
            # 当前播放的视频文件路径
            video_path = ''
            pc = self._facade.window.player_controller
            if pc and pc.is_playing:
                cur = getattr(pc, 'current_url', '') or getattr(pc, '_current_url', '')
                if cur and not cur.startswith(('http', 'rtp', 'udp', 'rtmp', 'rtsp')):
                    video_path = cur
            dialog = SubtitleDownloadDialog(self._facade.window, video_file_path=video_path)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开字幕下载对话框失败: {e}")

    def _toggle_sub_visibility(self):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'toggle_sub_visibility'):
            return
        new_state = pc.toggle_sub_visibility()
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            osd_text = tr('osd_sub_visible', 'Subtitle: On') if new_state else tr('osd_sub_hidden', 'Subtitle: Off')
            self._facade.window._show_osd_feedback(osd_text)

    def _adjust_sub_delay(self, delta: float):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'adjust_sub_delay'):
            return
        new_delay = pc.adjust_sub_delay(delta)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_sub_delay', 'Subtitle Delay')}: {new_delay:+.3f}s")

    def _adjust_sub_scale(self, delta: float):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'adjust_sub_scale'):
            return
        new_scale = pc.adjust_sub_scale(delta)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_sub_scale', 'Subtitle Scale')}: {new_scale:.2f}x")

    def _set_sub_scale(self, scale: float):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'set_sub_scale'):
            return
        pc.set_sub_scale(scale)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_sub_scale', 'Subtitle Scale')}: {scale:.2f}x")

    def _adjust_sub_pos(self, delta: int):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'get_sub_pos') or not hasattr(pc, 'set_sub_pos'):
            return
        new_pos = max(0, min(100, pc.get_sub_pos() + delta))
        pc.set_sub_pos(new_pos)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_sub_pos', 'Subtitle Position')}: {new_pos}")

    def _set_sub_pos(self, pos: int):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'set_sub_pos'):
            return
        pc.set_sub_pos(pos)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_sub_pos', 'Subtitle Position')}: {pos}")

    def toggle_subtitle_visibility(self):
        """供快捷键调用"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        self._facade._toggle_sub_visibility()

    def adjust_subtitle_delay(self, delta: float):
        """供快捷键调用"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        self._facade._adjust_sub_delay(delta)

    def adjust_subtitle_scale(self, delta: float):
        """供快捷键调用"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        self._facade._adjust_sub_scale(delta)

    def _show_video_eq_dialog(self):
        """打开视频图像调整对话框"""
        try:
            from ui.dialogs.video_eq_dialog import VideoEqualizerDialog
            if not hasattr(self._facade.window, '_video_eq_dialog') or not self._facade.window._video_eq_dialog:
                self._facade.window._video_eq_dialog = VideoEqualizerDialog(self._facade.window)
            self._facade.window._video_eq_dialog.show()
            self._facade.window._video_eq_dialog.raise_()
            self._facade.window._video_eq_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开视频 EQ 对话框失败: {e}")

    def adjust_video_eq(self, key: str, delta: float):
        """相对调整图像参数（供快捷键调用）
        key: brightness/contrast/saturation/hue/gamma（int 步进）
              sharpness（float 步进）
        """
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'adjust_video_eq'):
            return
        new_v = pc.adjust_video_eq(key, delta)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            label_key = f'osd_video_{key}'
            if key == 'sharpness':
                self._facade.window._show_osd_feedback(f"{tr(label_key, 'Sharpness')}: {new_v:+.2f}")
            else:
                self._facade.window._show_osd_feedback(f"{tr(label_key, key.capitalize())}: {int(new_v):+d}")

    def cycle_video_rotate(self, step: int = 90):
        """循环切换画面旋转角度（0→90→180→270→0）"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'get_video_rotate'):
            return
        cur = pc.get_video_rotate()
        new_degree = (cur + step) % 360
        pc.set_video_rotate(new_degree)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_video_rotate', 'Rotate')}: {new_degree}°")

    def toggle_video_flip(self):
        """循环切换画面翻转模式（无→水平→垂直→双向→无）"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'get_video_flip'):
            return
        cur = pc.get_video_flip() or ''
        order = ['', 'horizontal', 'vertical', 'both']
        try:
            idx = order.index(cur)
        except ValueError:
            idx = -1
        new_mode = order[(idx + 1) % len(order)]
        pc.set_video_flip(new_mode)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            label_map = {
                '': tr('video_eq_flip_none', 'None'),
                'horizontal': tr('video_eq_flip_horizontal', 'Horizontal'),
                'vertical': tr('video_eq_flip_vertical', 'Vertical'),
                'both': tr('video_eq_flip_both', 'Both'),
            }
            self._facade.window._show_osd_feedback(f"{tr('osd_video_flip', 'Flip')}: {label_map.get(new_mode, new_mode)}")

    def apply_video_eq_on_load(self):
        """在文件加载时应用已保存的视频 EQ 配置
        由播放器在加载新文件后调用；若启用 reset_on_new_file 则重置
        """
        try:
            cfg = self._facade.window.config.load_video_eq()
        except Exception:
            return
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'apply_video_eq'):
            return
        if cfg.get('reset_on_new_file', False):
            pc.reset_video_eq()
            pc.set_video_rotate(0)
            pc.set_video_flip('')
            pc.clear_video_crop()
            # 重置运动补偿和分辨率提升
            if hasattr(pc, 'clear_motion_compensation'):
                pc.clear_motion_compensation()
            if hasattr(pc, 'clear_super_resolution'):
                pc.clear_super_resolution()
            return
        # 应用保存的图像参数
        eq = {k: cfg.get(k, 0) for k in ('brightness', 'contrast', 'saturation', 'hue', 'gamma', 'sharpness')}
        eq['video_rotate'] = cfg.get('video_rotate', 0)
        eq['video_flip'] = cfg.get('video_flip', '')
        pc.apply_video_eq(eq)
        # 应用运动补偿
        mc_strength = cfg.get('motion_comp', 'off')
        mc_fps = int(cfg.get('motion_comp_fps', 60))
        if mc_strength and mc_strength != 'off' and hasattr(pc, 'set_motion_compensation'):
            pc.set_motion_compensation(mc_strength, mc_fps)
        # 应用分辨率提升
        sr_scale = cfg.get('superres_scale', 'off')
        sr_detail = int(cfg.get('superres_detail', 0))
        if (sr_scale and sr_scale != 'off') or sr_detail > 0:
            if hasattr(pc, 'set_super_resolution'):
                pc.set_super_resolution(sr_scale if sr_scale else 'off', sr_detail)
        # 应用用户着色器
        shader_preset = cfg.get('shader_preset', 'off')
        if shader_preset and shader_preset != 'off' and hasattr(pc, 'set_user_shader'):
            pc.set_user_shader(shader_preset)

    def set_motion_compensation(self, strength: str, target_fps: int = 60):
        """设置运动补偿"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'set_motion_compensation'):
            return
        pc.set_motion_compensation(strength, target_fps)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            strength_labels = {
                'off': tr('mc_off', '关闭'),
                'low': tr('mc_low', '轻度'),
                'medium': tr('mc_medium', '中度'),
                'high': tr('mc_high', '强力'),
            }
            label = strength_labels.get(strength, strength)
            if strength == 'off':
                self._facade.window._show_osd_feedback(f"{tr('osd_motion_comp', '运动补偿')}: {label}")
            else:
                self._facade.window._show_osd_feedback(f"{tr('osd_motion_comp', '运动补偿')}: {label} {target_fps}fps")

    def set_super_resolution(self, scale_algo: str, detail_enhance: int = 0):
        """设置分辨率提升"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'set_super_resolution'):
            return
        pc.set_super_resolution(scale_algo, detail_enhance)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            scale_labels = {
                'off': tr('sr_off', '关闭'),
                'bilinear': tr('sr_bilinear', '双线性'),
                'bicubic': tr('sr_bicubic', '双三次'),
                'lanczos': tr('sr_lanczos', 'Lanczos'),
                'spline': tr('sr_spline', '样条'),
                'ewa_lanczos': tr('sr_ewa_lanczos', 'EWA Lanczos'),
                'ewa_lanczossharp': tr('sr_ewa_lanczossharp', 'EWA Lanczos Sharp'),
            }
            parts = []
            if scale_algo and scale_algo != 'off':
                parts.append(scale_labels.get(scale_algo, scale_algo))
            if detail_enhance > 0:
                parts.append(f"{tr('sr_detail', '细节')} {detail_enhance}")
            if parts:
                self._facade.window._show_osd_feedback(f"{tr('osd_super_res', '分辨率提升')}: {', '.join(parts)}")
            else:
                self._facade.window._show_osd_feedback(f"{tr('osd_super_res', '分辨率提升')}: {tr('sr_off', '关闭')}")

    def set_user_shader(self, preset: str):
        """设置用户着色器

        :param preset: 'off' / 'ravu' / 'fsrcnnx' / 'anime4k' / 'krig' / 'ssim' / 'esrgan' / 'adaptive_sharpen' / 自定义路径
        """
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'set_user_shader'):
            return
        success = pc.set_user_shader(preset)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            if preset == 'off':
                self._facade.window._show_osd_feedback(
                    f"{tr('osd_shader', '着色器')}: {tr('shader_off', '关闭')}"
                )
            elif not success:
                # 着色器文件未找到，区分于主动关闭
                self._facade.window._show_osd_feedback(
                    f"{tr('osd_shader', '着色器')}: {tr('shader_not_found', '文件未找到，请放入 shaders/ 目录')}"
                )
            else:
                shader_labels = {
                    'ravu': 'RAVU', 'fsrcnnx': 'FSRCNNX',
                    'anime4k': 'Anime4K', 'krig': 'KrigBilateral',
                    'ssim': 'SSim', 'esrgan': 'ESRGAN',
                    'adaptive_sharpen': 'Adaptive Sharpen',
                }
                label = shader_labels.get(preset, preset)
                self._facade.window._show_osd_feedback(
                    f"{tr('osd_shader', '着色器')}: {label}"
                )

    def toggle_scene_detect(self, enabled: bool) -> bool:
        """开关智能场景检测"""
        try:
            from services.scene_detect_service import get_scene_detect_service
            svc = get_scene_detect_service()
            if enabled:
                pc = self._facade.window.player_controller
                if not pc or not pc.is_playing:
                    return False
                svc.start(pc, callback=self._facade._on_scene_changed)
                tr = self._facade.window.language_manager.tr
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(
                        tr('scene_detect_on', '智能场景检测已启用')
                    )
                return True
            else:
                svc.stop()
                tr = self._facade.window.language_manager.tr
                if hasattr(self._facade.window, '_show_osd_feedback'):
                    self._facade.window._show_osd_feedback(
                        tr('scene_detect_off', '智能场景检测已关闭')
                    )
                return True
        except Exception as e:
            logger.error(f"切换场景检测失败: {e}")
            return False

    def _on_scene_changed(self, params: dict, scene_type: str):
        """场景检测回调：在主线程应用参数"""
        try:
            safe_single_shot(0, self._facade.window, lambda: self._facade._apply_scene_params(params, scene_type))
        except Exception as e:
            logger.debug(f"场景检测回调调度失败: {e}")

    def _apply_scene_params(self, params: dict, scene_type: str):
        """应用场景检测推荐的参数"""
        try:
            mc_strength = params.get('motion_comp', 'off')
            mc_fps = int(params.get('motion_comp_fps', 60))
            sr_scale = params.get('superres_scale', 'off')
            sr_detail = int(params.get('superres_detail', 0))
            shader = params.get('shader_preset', 'off')
            scene_label = params.get('scene_label', scene_type)
            self._facade.set_motion_compensation(mc_strength, mc_fps)
            self._facade.set_super_resolution(sr_scale, sr_detail)
            self._facade.set_user_shader(shader)
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(
                    f"{tr('scene_detect_label', '场景检测')}: {scene_label}"
                )
        except Exception as e:
            logger.error(f"应用场景参数失败: {e}")

    def get_scene_detect_status(self) -> dict:
        """获取场景检测状态"""
        try:
            from services.scene_detect_service import get_scene_detect_service
            svc = get_scene_detect_service()
            return {
                'enabled': svc.enabled,
                'scene_type': svc.last_scene_type,
                'params': svc.last_params,
            }
        except Exception:
            return {'enabled': False, 'scene_type': 'unknown', 'params': {}}

    def _show_audio_eq_dialog(self):
        """打开音频调整对话框"""
        try:
            from ui.dialogs.audio_eq_dialog import AudioEqualizerDialog
            if not hasattr(self._facade.window, '_audio_eq_dialog') or not self._facade.window._audio_eq_dialog:
                self._facade.window._audio_eq_dialog = AudioEqualizerDialog(self._facade.window)
            self._facade.window._audio_eq_dialog.show()
            self._facade.window._audio_eq_dialog.raise_()
            self._facade.window._audio_eq_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开音频 EQ 对话框失败: {e}")

    def adjust_audio_delay(self, delta: float):
        """相对调整音频延迟（供快捷键调用）"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'adjust_audio_delay'):
            return
        new_v = pc.adjust_audio_delay(delta)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_audio_delay', 'Audio Delay')}: {new_v:+.3f}s")

    def adjust_audio_pitch(self, delta: float):
        """相对调整音调补偿（供快捷键调用）"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'adjust_audio_pitch'):
            return
        new_v = pc.adjust_audio_pitch(delta)
        tr = self._facade.window.language_manager.tr
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_audio_pitch', 'Pitch')}: {new_v:.2f}")

    def set_channel_volumes(self, volumes: dict):
        """设置逐声道音量"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'set_channel_volumes'):
            return
        pc.set_channel_volumes(volumes)

    def get_audio_channel_info(self) -> dict:
        """获取当前音频声道信息"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'get_audio_channel_info'):
            return {}
        return pc.get_audio_channel_info()

    def start_channel_monitor(self):
        """启动声道活动状态监控"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'start_channel_monitor'):
            return
        pc.start_channel_monitor()

    def stop_channel_monitor(self):
        """停止声道活动状态监控"""
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'stop_channel_monitor'):
            return
        pc.stop_channel_monitor()

    def get_channel_levels(self) -> dict:
        """获取各声道 RMS 电平"""
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing or not hasattr(pc, 'get_channel_levels'):
            return {}
        return pc.get_channel_levels()

    def apply_audio_eq_on_load(self):
        """在文件加载时应用已保存的音频 EQ 配置"""
        try:
            cfg = self._facade.window.config.load_audio_eq()
        except Exception:
            return
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'apply_audio_eq'):
            return
        if cfg.get('reset_on_new_file', False):
            pc.reset_audio_eq()
            return
        pc.apply_audio_eq(cfg)

    def _show_playback_queue_dialog(self):
        """打开播放队列与控制对话框"""
        try:
            from ui.dialogs.playback_queue_dialog import PlaybackQueueDialog
            if not hasattr(self._facade.window, '_playback_queue_dialog') or not self._facade.window._playback_queue_dialog:
                self._facade.window._playback_queue_dialog = PlaybackQueueDialog(self._facade.window)
            self._facade.window._playback_queue_dialog.show()
            self._facade.window._playback_queue_dialog.raise_()
            self._facade.window._playback_queue_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开播放队列对话框失败: {e}")

    def _show_resume_list_dialog(self):
        """打开断点续播列表对话框"""
        try:
            rc = getattr(self._facade.window, 'resume_ctrl', None)
            if rc and hasattr(rc, 'show_resume_list_dialog'):
                rc.show_resume_list_dialog()
        except Exception as e:
            logger.error(f"打开断点续播列表对话框失败: {e}")

    def _show_network_enhance_dialog(self):
        """打开网络流媒体增强对话框"""
        try:
            from ui.dialogs.network_enhance_dialog import NetworkEnhanceDialog
            if not hasattr(self._facade.window, '_network_enhance_dialog') or not self._facade.window._network_enhance_dialog:
                self._facade.window._network_enhance_dialog = NetworkEnhanceDialog(self._facade.window)
            self._facade.window._network_enhance_dialog.show()
            self._facade.window._network_enhance_dialog.raise_()
            self._facade.window._network_enhance_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开网络流媒体增强对话框失败: {e}")

    def _show_burst_screenshot_dialog(self):
        """打开连拍截图对话框"""
        try:
            from ui.dialogs.burst_screenshot_dialog import BurstScreenshotDialog
            if not hasattr(self._facade.window, '_burst_screenshot_dialog') or not self._facade.window._burst_screenshot_dialog:
                self._facade.window._burst_screenshot_dialog = BurstScreenshotDialog(self._facade.window)
            self._facade.window._burst_screenshot_dialog.show()
            self._facade.window._burst_screenshot_dialog.raise_()
            self._facade.window._burst_screenshot_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开连拍截图对话框失败: {e}")

    def _show_bookmark_dialog(self):
        """打开书签/章节对话框"""
        try:
            bc = getattr(self._facade.window, 'bookmark_ctrl', None)
            if bc and hasattr(bc, 'show_bookmark_dialog'):
                bc.show_bookmark_dialog()
        except Exception as e:
            logger.error(f"打开书签对话框失败: {e}")

    def _show_av_sync_dialog(self):
        """打开音视频同步监控对话框"""
        try:
            from ui.dialogs.av_sync_dialog import AVSyncDialog
            if not hasattr(self._facade.window, '_av_sync_dialog') or not self._facade.window._av_sync_dialog:
                self._facade.window._av_sync_dialog = AVSyncDialog(self._facade.window)
            self._facade.window._av_sync_dialog.show()
            self._facade.window._av_sync_dialog.raise_()
            self._facade.window._av_sync_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开 A/V 同步监控对话框失败: {e}")

    def _show_stream_quality_dialog(self):
        """打开流质量检测对话框"""
        try:
            from ui.dialogs.stream_quality_dialog import StreamQualityDialog
            if not hasattr(self._facade.window, '_stream_quality_dialog') or not self._facade.window._stream_quality_dialog:
                self._facade.window._stream_quality_dialog = StreamQualityDialog(self._facade.window)
            self._facade.window._stream_quality_dialog.show()
            self._facade.window._stream_quality_dialog.raise_()
            self._facade.window._stream_quality_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开流质量检测对话框失败: {e}")

    def _show_3d_dialog(self):
        """打开 3D / 360° 视频对话框"""
        try:
            from ui.dialogs.video_3d_dialog import Video3DDialog
            if not hasattr(self._facade.window, '_video_3d_dialog') or not self._facade.window._video_3d_dialog:
                self._facade.window._video_3d_dialog = Video3DDialog(self._facade.window)
            self._facade.window._video_3d_dialog.show()
            self._facade.window._video_3d_dialog.raise_()
            self._facade.window._video_3d_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开 3D/360 对话框失败: {e}")

    def _populate_hdr_submenu(self, parent_menu):
        """构造 HDR 模式子菜单"""
        from ui.styles import AppStyles
        tr = self._facade.window.language_manager.tr
        pc = self._facade.window.player_controller
        hdr_menu = parent_menu.addMenu(tr("ctx_hdr_mode", "HDR Mode"))
        hdr_menu.setStyleSheet(AppStyles.player_menu_bar_style())

        # 顶部：显示当前视频 HDR 类型
        current_hdr_type = ''
        if pc and pc.is_playing:
            try:
                info = pc.get_live_media_info() if hasattr(pc, 'get_live_media_info') else None
                if info:
                    from services.mpv_player_service import MpvPlayerController
                    current_hdr_type = MpvPlayerController.detect_hdr_type(
                        info.get('colormatrix', ''),
                        info.get('gamma', ''),
                        info.get('sig_peak', 0),
                        info.get('video_format', ''),
                        info.get('color_primaries', '')
                    )
            except Exception:
                current_hdr_type = ''
        if current_hdr_type:
            label_action = hdr_menu.addAction(
                f"{tr('hdr_current_video', 'Current')}: {current_hdr_type}")
            label_action.setEnabled(False)
            # DV 基础层警告：libmpv 无法解码 DV RPU 增强层，只能播放 HDR10 基础层
            if current_hdr_type == 'DV':
                dv_warn = hdr_menu.addAction(
                    f"  ⚠ {tr('dv_base_layer_warning', 'Dolby Vision: playing HDR10 base layer only')}")
                dv_warn.setEnabled(False)
            hdr_menu.addSeparator()

        # 当前模式
        current_mode = 'disable'
        if pc and hasattr(pc, '_playback_settings'):
            current_mode = pc._playback_settings.get('hdr_output_mode', 'disable')

        # 5 个模式选项
        for mode, key in self._facade._HDR_MODES:
            label = tr(key, mode)
            act = hdr_menu.addAction(label, lambda checked=False, m=mode: self._facade._set_hdr_mode(m))
            act.setCheckable(True)
            act.setChecked(mode == current_mode)

    def _set_hdr_mode(self, mode: str):
        """切换 HDR 输出模式（需要重新初始化 mpv）"""
        try:
            pc = self._facade.window.player_controller
            if not pc or not hasattr(pc, 'reinit_for_hdr_change'):
                return
            # 持久化到配置文件
            try:
                if self._facade.window.config:
                    settings = self._facade.window.config.load_playback_settings()
                    settings['hdr_output_mode'] = mode
                    self._facade.window.config.save_playback_settings(settings)
            except Exception as e:
                logger.warning(f"保存 HDR 模式失败: {e}")
            # 调用 player_controller 切换（会硬重启 mpv）
            pc.reinit_for_hdr_change(mode)
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(
                    f"{tr('osd_hdr_mode', 'HDR Mode')}: {tr(f'hdr_{mode}', mode)}")
        except Exception as e:
            logger.error(f"切换 HDR 模式失败: {e}")

    def add_bookmark_now(self):
        """快捷键调用：在当前位置添加书签"""
        try:
            bc = getattr(self._facade.window, 'bookmark_ctrl', None)
            if bc and hasattr(bc, 'add_bookmark'):
                bc.add_bookmark('')
        except Exception as e:
            logger.debug(f"添加书签失败: {e}")

    def chapter_next(self):
        """快捷键调用：跳转到下一章"""
        try:
            bc = getattr(self._facade.window, 'bookmark_ctrl', None)
            if bc and hasattr(bc, 'next_chapter'):
                bc.next_chapter()
        except Exception as e:
            logger.debug(f"下一章失败: {e}")

    def chapter_prev(self):
        """快捷键调用：跳转到上一章"""
        try:
            bc = getattr(self._facade.window, 'bookmark_ctrl', None)
            if bc and hasattr(bc, 'prev_chapter'):
                bc.prev_chapter()
        except Exception as e:
            logger.debug(f"上一章失败: {e}")

    def get_queue_controller(self):
        return getattr(self._facade.window, 'file_queue_ctrl', None)

    def cycle_queue_mode(self):
        """循环切换队列模式"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            new_mode = qc.cycle_queue_mode()
            tr = self._facade.window.language_manager.tr
            labels = {
                'none': tr('playback_queue_mode_none', 'No Loop'),
                'single': tr('playback_queue_mode_single', 'Loop Single File'),
                'all': tr('playback_queue_mode_all', 'Loop List'),
                'shuffle': tr('playback_queue_mode_shuffle', 'Shuffle'),
            }
            osd_text = f"{tr('osd_queue_mode', 'Queue Mode')}: {labels.get(new_mode, new_mode)}"
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(osd_text)
        except Exception as e:
            logger.debug(f"循环切换队列模式失败: {e}")

    def toggle_shuffle(self):
        """切换随机播放开关"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            is_on = qc.toggle_shuffle()
            tr = self._facade.window.language_manager.tr
            key = 'osd_shuffle_on' if is_on else 'osd_shuffle_off'
            osd_text = tr(key, 'Shuffle: On' if is_on else 'Shuffle: Off')
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(osd_text)
        except Exception as e:
            logger.debug(f"切换随机播放失败: {e}")

    def play_next_file(self):
        """播放下一个文件"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            qc.play_next()
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(tr('osd_play_next', 'Next File'))
        except Exception as e:
            logger.debug(f"播放下一文件失败: {e}")

    def play_previous_file(self):
        """播放上一个文件"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            qc.play_previous()
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(tr('osd_play_prev', 'Previous File'))
        except Exception as e:
            logger.debug(f"播放上一文件失败: {e}")

    def ab_loop_set_a(self):
        """设置 A-B 循环 A 点"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            pos = qc.ab_loop_set_a()
            if pos is None:
                return
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(f"{tr('osd_ab_loop_a', 'A Point')}: {pos:.2f}s")
        except Exception as e:
            logger.debug(f"设置 A 点失败: {e}")

    def ab_loop_set_b(self):
        """设置 A-B 循环 B 点"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            pos = qc.ab_loop_set_b()
            if pos is None:
                return
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(f"{tr('osd_ab_loop_b', 'B Point')}: {pos:.2f}s")
        except Exception as e:
            logger.debug(f"设置 B 点失败: {e}")

    def ab_loop_clear(self):
        """清除 A-B 循环"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            qc.ab_loop_clear()
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(tr('osd_ab_loop_cleared', 'A-B Loop cleared'))
        except Exception as e:
            logger.debug(f"清除 A-B 循环失败: {e}")

    def frame_step(self):
        """前进一帧"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            qc.frame_step()
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(f"{tr('osd_frame_step', 'Frame')} >>")
        except Exception as e:
            logger.debug(f"前进一帧失败: {e}")

    def frame_back_step(self):
        """后退一帧"""
        qc = self._facade.get_queue_controller()
        if not qc:
            return
        try:
            qc.frame_back_step()
            tr = self._facade.window.language_manager.tr
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(f"<< {tr('osd_frame_step', 'Frame')}")
        except Exception as e:
            logger.debug(f"后退一帧失败: {e}")

    def adjust_speed(self, delta):
        pc = self._facade.window.player_controller
        if not pc:
            return
        current = pc.get_speed()
        new_speed = round(max(0.1, min(10.0, current + delta)), 1)
        pc.set_speed(new_speed)
        speed_btn = self._facade.window.speed_button
        if speed_btn:
            speed_btn.setText(f"{new_speed}x")
        if not self._facade.is_osd_visible:
            self._facade.window._show_osd_feedback(f"{self._facade.window.language_manager.tr('osd_speed', 'Speed')}: {new_speed}x")

    def cycle_speed(self):
        pc = self._facade.window.player_controller
        if not pc:
            return
        current = pc.get_speed()
        idx = 0
        for i, s in enumerate(self._facade.SPEED_STEPS):
            if abs(current - s) < 0.01:
                idx = i
                break
        next_idx = (idx + 1) % len(self._facade.SPEED_STEPS)
        new_speed = self._facade.SPEED_STEPS[next_idx]
        pc.set_speed(new_speed)
        speed_btn = self._facade.window.speed_button
        if speed_btn:
            speed_btn.setText(f"{new_speed}x")
        if not self._facade.is_osd_visible:
            self._facade.window._show_osd_feedback(f"{self._facade.window.language_manager.tr('osd_speed', 'Speed')}: {new_speed}x")

    def cycle_aspect_ratio(self):
        pc = self._facade.window.player_controller
        if not pc:
            return
        self._facade._current_aspect_idx = (self._facade._current_aspect_idx + 1) % len(self._facade.ASPECT_CYCLE)
        ratio = self._facade.ASPECT_CYCLE[self._facade._current_aspect_idx]
        pc.set_aspect_ratio(ratio)
        tr = self._facade.window.language_manager.tr
        labels = {
            'default': tr('ctx_aspect_default', 'Default'),
            '16:9': '16:9',
            '4:3': '4:3',
            'stretch': tr('ctx_aspect_stretch', 'Stretch'),
            'fill': tr('ctx_aspect_fill', 'Fill')
        }
        aspect_btn = getattr(self._facade.window, 'aspect_button', None)
        if aspect_btn:
            aspect_btn.setText(labels.get(ratio, tr('ctx_aspect_default', 'Default')))
        if hasattr(self._facade.window, '_show_osd_feedback'):
            osd_text = f"{tr('osd_aspect_ratio', 'Aspect')}: {labels.get(ratio, tr('ctx_aspect_default', 'Default'))}"
            self._facade.window._show_osd_feedback(osd_text)
        self._facade._save_aspect_ratio(ratio)

    def _save_aspect_ratio(self, ratio):
        try:
            self._facade.window.config.set_value('Player', 'aspect_ratio', ratio)
            self._facade.window.config.save_config()
        except Exception as e:
            logger.debug(f"保存画面比例设置失败: {e}")

    def restore_aspect_ratio(self):
        try:
            ratio = self._facade.window.config.get_value('Player', 'aspect_ratio', 'default') or 'default'
            if ratio in self._facade.ASPECT_CYCLE:
                self._facade._current_aspect_idx = self._facade.ASPECT_CYCLE.index(ratio)
            else:
                self._facade._current_aspect_idx = 0
                ratio = 'default'
            pc = self._facade.window.player_controller
            if pc:
                pc.set_aspect_ratio(ratio)
            tr = self._facade.window.language_manager.tr
            labels = {
                'default': tr('ctx_aspect_default', 'Default'),
                '16:9': '16:9',
                '4:3': '4:3',
                'stretch': tr('ctx_aspect_stretch', 'Stretch'),
                'fill': tr('ctx_aspect_fill', 'Fill')
            }
            aspect_btn = getattr(self._facade.window, 'aspect_button', None)
            if aspect_btn:
                aspect_btn.setText(labels.get(ratio, tr('ctx_aspect_default', 'Default')))
        except Exception as e:
            logger.debug(f"恢复画面比例失败: {e}")

    def _set_speed(self, speed):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return
        try:
            pc.set_speed(speed)
        except Exception:
            return
        speed_btn = self._facade.window.speed_button
        if speed_btn:
            speed_btn.setText(f"{speed}x")
        if not self._facade.is_osd_visible:
            self._facade.window._show_osd_feedback(f"{self._facade.window.language_manager.tr('osd_speed', 'Speed')}: {speed}x")

    def _set_volume(self, volume):
        pc = self._facade.window.player_controller
        if not pc:
            return
        try:
            pc.set_volume(volume)
        except Exception:
            return
        volume_slider = self._facade.window.volume_slider
        if volume_slider:
            volume_slider.setValue(volume)
        playback_ctrl = getattr(self._facade.window, 'playback_ctrl', None)
        if playback_ctrl:
            playback_ctrl._update_volume_icon(volume)
        if not self._facade.is_osd_visible:
            self._facade.window._show_osd_feedback(f"{self._facade.window.language_manager.tr('osd_volume', 'Volume')}: {volume}%")

    def _set_aspect(self, ratio):
        pc = self._facade.window.player_controller
        if not pc:
            return
        try:
            pc.set_aspect_ratio(ratio)
        except Exception:
            return
        if ratio in self._facade.ASPECT_CYCLE:
            self._facade._current_aspect_idx = self._facade.ASPECT_CYCLE.index(ratio)
        tr = self._facade.window.language_manager.tr
        labels = {
            'default': tr('ctx_aspect_default', 'Default'),
            '16:9': '16:9',
            '4:3': '4:3',
            'stretch': tr('ctx_aspect_stretch', 'Stretch'),
            'fill': tr('ctx_aspect_fill', 'Fill')
        }
        aspect_btn = getattr(self._facade.window, 'aspect_button', None)
        if aspect_btn:
            aspect_btn.setText(labels.get(ratio, tr('ctx_aspect_default', 'Default')))
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_aspect_ratio', 'Aspect')}: {labels.get(ratio, tr('ctx_aspect_default', 'Default'))}")
        self._facade._save_aspect_ratio(ratio)

    def update_catchup_indicator(self):
        try:
            indicator = getattr(self._facade.window, 'catchup_indicator', None)
            if not indicator:
                return

            is_timeshift = self._facade.window.play_state.is_timeshift
            is_catchup = self._facade.window.play_state.is_catchup

            if is_timeshift:
                indicator.setText(self._facade.window.language_manager.tr('timeshift_watching', '正在时移观看'))
                indicator.show()
            elif is_catchup and not is_timeshift:
                indicator.setText(self._facade.window.language_manager.tr('catchup_playing_label', '正在回看'))
                indicator.show()
            elif self._facade.window.current_channel and (
                self._facade.window.current_channel.get('catchup_source', '')
                or self._facade.window.current_channel.get('catchup', '')
            ):
                indicator.setText(self._facade.window.language_manager.tr('catchup_available', '可回放'))
                indicator.show()
            elif self._facade.window.current_channel:
                # Fallback：catchup 字段为空时，即时从 URL 检测可回看模式（PLTV/TVOD、SNM/TVOD）
                ch_url = self._facade.window.current_channel.get('url', '')
                if ch_url:
                    from services.m3u_parser import safe_detect_catchup_source
                    if safe_detect_catchup_source(ch_url):
                        indicator.setText(self._facade.window.language_manager.tr('catchup_available', '可回放'))
                        indicator.show()
                        return
                indicator.hide()
            else:
                indicator.hide()
        except Exception as e:
            logger.debug(f"更新回看指示器失败: {e}")

    def _is_audio_only(self):
        pc = self._facade.window.player_controller
        if not pc or not pc.is_playing:
            return False
        if hasattr(pc, 'audio_visual') and pc.audio_visual:
            return pc.audio_visual.is_audio_only
        return False

    def _populate_visual_menu(self, menu):
        from services.audio_visual_service import AUDIO_VISUAL_STYLES, STYLE_KEYS
        pc = self._facade.window.player_controller
        tr = self._facade.window.language_manager.tr
        current_style = 'none'
        if pc and hasattr(pc, 'audio_visual') and pc.audio_visual:
            current_style = pc.audio_visual.current_style

        for key in STYLE_KEYS:
            style = AUDIO_VISUAL_STYLES[key]
            label = tr(style['name_key'], style['name_default'])
            if key == current_style:
                label += " ✓"
            menu.addAction(label, lambda *a, k=key: self._facade._set_visual_style(k))

        menu.addSeparator()

        random_label = tr("audio_vis_random", "随机效果")
        if current_style == 'random':
            random_label += " ✓"
        menu.addAction(random_label, lambda *a: self._facade._set_visual_style('random'))

        menu.addSeparator()

        off_style = AUDIO_VISUAL_STYLES['none']
        off_label = tr(off_style['name_key'], off_style['name_default'])
        if current_style == 'none':
            off_label += " ✓"
        menu.addAction(off_label, lambda *a: self._facade._set_visual_style('none'))

        self._populate_cover_menu(menu)

    def _populate_cover_menu(self, menu):
        """封面显示子菜单：位置 / 大小 / 形式（任务B）。"""
        tr = self._facade.window.language_manager.tr
        widget = None
        pc = self._facade.window.player_controller
        if pc and hasattr(pc, 'audio_visual') and pc.audio_visual:
            widget = pc.audio_visual.get_visual_widget()

        menu.addSeparator()
        cover_menu = menu.addMenu(tr("cover_display_menu", "封面显示"))
        if widget:
            cur_pos = widget.get_cover_pos()
            cur_size = widget.get_cover_size()
            cur_shape = widget.get_cover_shape()
        else:
            # 可视化控件尚未创建时，选项要回显已保存的配置而不是固定默认值
            try:
                from core.config_manager import ConfigManager
                config = ConfigManager()
                cur_pos = config.get_value('Player', 'cover_position', 'center')
                cur_size = config.get_value('Player', 'cover_size', 'medium')
                cur_shape = config.get_value('Player', 'cover_shape', 'card')
            except Exception:
                cur_pos, cur_size, cur_shape = 'center', 'medium', 'card'
            if cur_pos not in ('center', 'left', 'right'):
                cur_pos = 'center'
            if cur_size not in ('small', 'medium', 'large'):
                cur_size = 'medium'
            if cur_shape not in ('card', 'circle', 'hidden'):
                cur_shape = 'card'

        def _apply_cover(key, value):
            if widget:
                setter = {
                    'pos': widget.set_cover_pos,
                    'size': widget.set_cover_size,
                    'shape': widget.set_cover_shape,
                }.get(key)
                if setter:
                    setter(value)
                return
            from services.audio_visual_service import AudioVisualWidget
            AudioVisualWidget._save_cover_setting(key, value)
            # 无控件时也要给出可感知的反馈，否则用户以为菜单点击无效
            if hasattr(self._facade.window, '_show_osd_feedback'):
                self._facade.window._show_osd_feedback(
                    tr('cover_setting_saved', '封面设置已保存')
                )

        pos_menu = cover_menu.addMenu(tr("cover_pos_menu", "位置"))
        for key, label_key, label_def in (
            ('center', "cover_pos_center", "居中"),
            ('left', "cover_pos_left", "左侧"),
            ('right', "cover_pos_right", "右侧"),
        ):
            label = tr(label_key, label_def)
            if cur_pos == key:
                label += " ✓"
            pos_menu.addAction(label, lambda *a, k=key: _apply_cover('pos', k))

        size_menu = cover_menu.addMenu(tr("cover_size_menu", "大小"))
        for key, label_key, label_def in (
            ('small', "cover_size_small", "小"),
            ('medium', "cover_size_medium", "中"),
            ('large', "cover_size_large", "大"),
        ):
            label = tr(label_key, label_def)
            if cur_size == key:
                label += " ✓"
            size_menu.addAction(label, lambda *a, k=key: _apply_cover('size', k))

        shape_menu = cover_menu.addMenu(tr("cover_shape_menu", "形式"))
        for key, label_key, label_def in (
            ('card', "cover_shape_card", "圆角卡片"),
            ('circle', "cover_shape_circle", "圆形"),
            ('hidden', "cover_shape_hidden", "隐藏封面"),
        ):
            label = tr(label_key, label_def)
            if cur_shape == key:
                label += " ✓"
            shape_menu.addAction(label, lambda *a, k=key: _apply_cover('shape', k))

    def _set_visual_style(self, style_key):
        pc = self._facade.window.player_controller
        if not pc or not hasattr(pc, 'audio_visual') or not pc.audio_visual:
            return
        tr = self._facade.window.language_manager.tr
        if style_key == 'random':
            pc.audio_visual.apply_random_style()
        else:
            pc.audio_visual.apply_visual_style(style_key)
        pc.audio_visual.save_current_style()
        display = pc.audio_visual.get_style_display_name(pc.audio_visual.current_style, self._facade.window.language_manager)
        if hasattr(self._facade.window, '_show_osd_feedback'):
            self._facade.window._show_osd_feedback(f"{tr('osd_audio_visual', '音频可视化')}: {display}")

