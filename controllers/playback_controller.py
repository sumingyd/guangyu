import os
from typing import Dict, Any, Optional
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from core.log_manager import global_logger as logger
from controllers.main_window_protocol import MainWindowProtocol
from ui.styles import AppStyles
from services.fcc_service import FCCService
from services.mpv_common import DEFAULT_NETWORK_TIMEOUT_SEC
from utils.delay_constants import DelayMs


class PlaybackController:

    # loadfile 之后等待 FILE_LOADED 的兜底超时；优先取播放设置中的真实网络超时
    SOURCE_TIMEOUT_MS = DEFAULT_NETWORK_TIMEOUT_SEC * 1000

    def __init__(self, main_window: MainWindowProtocol):
        self.window: MainWindowProtocol = main_window
        self._is_muted = False
        self._pre_mute_volume = 0
        self.current_channel: Optional[Dict[str, Any]] = None
        self._is_switching = False
        # 切换窗口内到达的最新一次请求，窗口结束后补播（最后一次请求生效）
        self._pending_channel: Optional[Dict[str, Any]] = None
        # 切换代次：用于丢弃过期的切换窗口结束回调
        self._switch_token = 0
        self._last_program_id = None
        self._aspect_ratio_restored = False
        self.fcc = FCCService()

    def toggle_play(self):
        pc = getattr(self.window, 'player_controller', None)
        if not pc:
            return
        if pc.is_paused or pc.is_playing:
            pc.pause()
        elif self.current_channel or getattr(self.window, 'current_channel', None):
            ch = self.current_channel or self.window.current_channel
            if ch:
                self.play_channel(ch)

    def stop_playback(self):
        self.fcc.on_stop()
        if hasattr(self.window, '_cancel_source_timeout'):
            self.window._cancel_source_timeout()
        # 停止后不再补播切换窗口内积压的请求，并立即解除切换锁
        self._pending_channel = None
        self._is_switching = False
        self._switch_token += 1

        if hasattr(self.window, 'player_controller') and self.window.player_controller:
            self.window.player_controller.stop()

        if hasattr(self.window, 'video_widget') and self.window.video_widget:
            self.window.video_widget.hide()
        if hasattr(self.window, 'video_placeholder') and self.window.video_placeholder:
            self.window.video_placeholder.show()

            from utils.general_utils import get_icon_path
            ico_path = get_icon_path()
            if os.path.exists(ico_path):
                icon = QIcon(ico_path)
                screen = QApplication.primaryScreen()
                dpr = screen.devicePixelRatio() if screen else 1.0
                size = int(256 * dpr)
                pixmap = icon.pixmap(size, size, QIcon.Mode.Normal, QIcon.State.On)
                if not pixmap.isNull():
                    pixmap.setDevicePixelRatio(dpr)
                    self.window.video_placeholder.setPixmap(pixmap)
                else:
                    self.window.video_placeholder.setText("")
            else:
                self.window.video_placeholder.setText("")

        self.current_channel = None

        # 清理时移/回看状态：否则之后播放直播时进度条会一直按旧的时移偏移计算
        catchup_ctrl = getattr(self.window, 'catchup_ctrl', None)
        if catchup_ctrl and hasattr(catchup_ctrl, '_clear_catchup_state'):
            try:
                catchup_ctrl._clear_catchup_state(set_state='idle')
            except Exception as e:
                logger.debug(f"停止播放时清理回看状态失败: {e}")
        # 兜底：即使没有 catchup_ctrl，也保证窗口级时移状态归零
        try:
            self.window._live_timeshift_seconds = 0
            self.window.catchup_program = None
        except Exception as e:
            logger.debug(f"重置窗口时移状态失败: {e}")

        self.window.play_state.set_idle()

        self._reset_ui_to_initial_state()

        if hasattr(self.window, 'language_manager'):
            tr = self.window.language_manager.tr
            self.window.status_bar_show_message(tr('playback_stopped', 'Playback stopped'))

    def _reset_ui_to_initial_state(self):
        ui_elements = {
            'play_button': (AppStyles.play_icon_name(False, False), "setIcon_name"),
            'channel_name': ("no_channel_selected,No Channel Selected", "setText_tr"),
            'current_program': ("select_channel_to_play,Select a channel to play", "setText_tr"),
            'channel_logo': (None, "clear_pixmap"),
            'video_info': ("not_playing,Not Playing", "setText_tr"),
            'audio_info': ("--", "setText"),
            'network_info': ("--", "setText"),
            'program_desc': ("open_playlist_or_import,Open playlist or import file", "setText_tr"),
            'time_label': ("--:-- - --:--", "setText"),
            'remain_label': ("waiting_to_play,Waiting to play", "setText_tr"),
            'progress_start': ("--:--", "setText"),
            'progress_end': ("--:--", "setText"),
        }

        btn_color = AppStyles.get_color('player_panel_text')

        for attr_name, (value, action) in ui_elements.items():
            if not hasattr(self.window, attr_name):
                continue

            element = getattr(self.window, attr_name)

            if action == "setText":
                element.setText(value)
            elif action == "setIcon_name":
                icon_path = AppStyles.get_icon(value, btn_color)
                if icon_path:
                    element.setIcon(QIcon(icon_path))
            elif action == "setText_tr" and hasattr(self.window, 'language_manager'):
                tr = self.window.language_manager.tr
                parts = value.split(',', 1)
                key = parts[0]
                fallback = parts[1] if len(parts) > 1 else key
                element.setText(tr(key, fallback) or fallback)
            elif action == "clear_pixmap":
                from utils.general_utils import set_default_channel_logo
                set_default_channel_logo(element, element.width() or 100, element.height() or 36)

        if hasattr(self.window, 'program_progress') and hasattr(self.window, '_set_progress_value'):
            self.window._set_progress_value(0)
        if hasattr(self.window, 'program_progress'):
            self.window.program_progress.setRange(0, 3600)
        if hasattr(self.window, '_progress_total_seconds'):
            self.window._progress_total_seconds = 3600
        if hasattr(self.window, '_progress_time_mode'):
            self.window._progress_time_mode = 'hour'
        if hasattr(self.window, '_progress_program_start'):
            self.window._progress_program_start = None
        if hasattr(self.window, '_progress_program_end'):
            self.window._progress_program_end = None
        if hasattr(self.window, 'current_channel'):
            self.window.current_channel = None

    def set_volume(self, value: int):
        if hasattr(self.window, 'player_controller') and self.window.player_controller:
            self.window.player_controller.set_volume(value)
            if not self._is_muted:
                self._update_volume_icon(value)

    def toggle_mute(self):
        if not self.window.player_controller:
            return

        if self._is_muted:
            self._is_muted = False
            self.window.player_controller.set_volume(self._pre_mute_volume)
            if self.window.volume_slider:
                self.window.volume_slider.blockSignals(True)
                self.window.volume_slider.setValue(self._pre_mute_volume)
                self.window.volume_slider.blockSignals(False)
            self._update_volume_icon(self._pre_mute_volume)
        else:
            self._is_muted = True
            self._pre_mute_volume = self.window.player_controller.get_volume()
            self.window.player_controller.set_volume(0)
            if self.window.volume_slider:
                self.window.volume_slider.blockSignals(True)
                self.window.volume_slider.setValue(0)
                self.window.volume_slider.blockSignals(False)
            self._update_volume_icon(0)

    def _update_volume_icon(self, volume: int):
        if not self.window.volume_button:
            return

        color = AppStyles.get_color('player_panel_text')
        if volume == 0:
            icon_name = 'volume_mute'
        elif volume < 50:
            icon_name = 'volume_low'
        else:
            icon_name = 'volume'
        icon_path = AppStyles.get_icon(icon_name, color)
        if icon_path:
            self.window.volume_button.setIcon(QIcon(icon_path))

    def play_channel(self, channel: Dict[str, Any]):

        if not channel:
            return

        if self._is_switching:
            # 300ms 切换窗口内不再静默丢弃：记录最新请求，窗口结束后补播
            self._pending_channel = channel
            logger.debug(f"play_channel: 切换窗口内收到新请求，排队最后一次 {channel.get('name', '?')}")
            return

        self._is_switching = True
        self._switch_token += 1
        token = self._switch_token

        try:
            logger.debug(f"play_channel: 开始切换频道 {channel.get('name', '?')} url={channel.get('url', '?')}")
            self._do_play_channel(channel)
        finally:
            self._schedule_switch_window_end(token)

    def _schedule_switch_window_end(self, token: int):
        """在切换窗口结束后解除锁，并补播窗口内积压的最后一次请求。"""
        def _on_window_end():
            # 过期回调（期间已停止播放或开始了新的切换窗口）直接丢弃
            if token != self._switch_token:
                return
            self._is_switching = False
            pending = self._pending_channel
            self._pending_channel = None
            if not pending:
                return
            current = self.current_channel or getattr(self.window, 'current_channel', None)
            if current and pending.get('url') == current.get('url'):
                logger.debug("play_channel: 积压请求与当前频道一致，跳过补播")
                return
            logger.debug(f"play_channel: 切换窗口结束，补播最后一次请求 {pending.get('name', '?')}")
            self.play_channel(pending)

        try:
            from utils.thread_safety import invoke_on_thread, safe_single_shot

            def _schedule_reset():
                safe_single_shot(DelayMs.CHANNEL_CLICK, self.window, _on_window_end)

            invoke_on_thread(self.window, _schedule_reset)
        except Exception as e:
            logger.debug(f"invoke_on_thread 失败，使用 QTimer.singleShot 兜底: {e}")
            try:
                QTimer.singleShot(DelayMs.CHANNEL_CLICK, _on_window_end)
            except Exception:
                # 最后兜底：直接重置，避免标志永久锁定
                self._is_switching = False

    def _do_play_channel(self, channel: Dict[str, Any]):
        if not (hasattr(self.window, 'player_controller') and self.window.player_controller and channel):
            return

        # 时移偏移由 UI（window）读取，必须重置窗口上的同名属性
        self.window._live_timeshift_seconds = 0
        self._last_program_id = None

        if self.window.play_state.is_catchup_or_timeshift:
            self._exit_catchup_mode()

        if hasattr(self.window, 'player_controller') and self.window.player_controller:
            try:
                current_speed = self.window.player_controller.get_speed()
                if abs(current_speed - 1.0) > 0.01:
                    self.window.player_controller.set_speed(1.0)
                    if getattr(self.window, 'speed_button', None) is not None:
                        self.window.speed_button.setText("1.0x")
                    if hasattr(self.window, '_show_osd_feedback'):
                        tr = self.window.language_manager.tr
                        self.window._show_osd_feedback(f"{tr('osd_speed', 'Speed')}: 1.0x")
            except Exception as e:
                logger.debug(f"恢复播放速度失败: {e}")

        url = channel.get('url', '')
        name = channel.get('name', '')

        # 同一频道重连/重试：强制重发 JOIN，避免被“同地址早退”挡掉
        same_as_current = bool(
            self.current_channel and self.current_channel.get('url') == url)
        self.fcc.on_channel_change(url, force=same_as_current)
        # 把 FCC 通知器挂到播放器 facade 上，供 HDR 重建等绕过控制器的路径复用
        try:
            self.window.player_controller._fcc_notifier = self.fcc
        except Exception as e:
            logger.debug(f"挂载FCC通知器失败: {e}")
        self.window.player_controller.play(url)

        if not self._aspect_ratio_restored:
            self._aspect_ratio_restored = True
            try:
                media_ctrl = getattr(self.window, 'media_ctrl', None)
                if media_ctrl:
                    media_ctrl.restore_aspect_ratio()
            except Exception as e:
                logger.debug(f"恢复画面比例失败: {e}")

        self.current_channel = channel
        self.window.play_state.set_live()
        # loadfile 后启动看门狗：超过网络超时仍未 FILE_LOADED 即判定拉流失败
        self._start_source_timeout(channel)

        # 重置媒体信息缓存，确保新频道的媒体信息和质量评分被重新计算
        # 不重置会导致：切到相同分辨率的频道时 static_key 不变，评分条不更新
        self.window._last_info_key = None
        self.window._last_media_info = {}

    def _source_timeout_ms(self) -> int:
        """看门狗超时与真实网络超时保持一致，未配置时回退默认值。"""
        try:
            settings = getattr(
                getattr(self.window, 'player_controller', None),
                '_playback_settings', None) or {}
            net_to = float(settings.get('network_timeout_sec', 0) or 0)
            if net_to > 0:
                return int(net_to * 1000)
        except (TypeError, ValueError):
            pass
        return self.SOURCE_TIMEOUT_MS

    def _start_source_timeout(self, channel: Dict[str, Any]):
        """loadfile 后启动源超时看门狗（FILE_LOADED / END_FILE / stop 时取消）。"""
        w = self.window
        if not hasattr(w, 'player_controller') or not w.player_controller:
            return
        if not (hasattr(w, '_cancel_source_timeout') and hasattr(w, '_on_source_timeout')):
            return
        w._cancel_source_timeout()
        timer = getattr(w, '_source_timeout_timer', None)
        if timer is None:
            timer = QTimer(w)
            timer.setSingleShot(True)
            w._source_timeout_timer = timer
        else:
            try:
                timer.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
        timer.timeout.connect(lambda ch=channel: w._on_source_timeout(ch))
        timer.start(self._source_timeout_ms())

    def _exit_catchup_mode(self):
        catchup_ctrl = getattr(self.window, 'catchup_ctrl', None)
        if catchup_ctrl:
            catchup_ctrl._clear_catchup_state(set_state='live')

        if hasattr(self.window, 'exit_catchup_button'):
            # 退出项已收入“更多”菜单，通过统一入口隐藏
            self.window._set_exit_catchup_visible(False)

        for attr in ['_catchup_start_time', '_catchup_start_progress',
                     '_target_catchup_progress',
                     '_pending_catchup_progress',
                     '_timeshift_enter_time_ms', '_timeshift_start_time']:
            if hasattr(self.window, attr):
                setattr(self.window, attr, None)
            if hasattr(self, attr):
                setattr(self, attr, None)

        for attr in ['_disable_progress_auto_update']:
            if hasattr(self.window, attr):
                setattr(self.window, attr, False)
            if hasattr(self, attr):
                setattr(self, attr, False)

        if hasattr(self.window, 'program_progress'):
            self.window.program_progress.setValue(0)
            self.window.program_progress.setRange(0, 3600)

        if hasattr(self.window, '_progress_total_seconds'):
            self.window._progress_total_seconds = 3600
        if hasattr(self.window, '_progress_time_mode'):
            self.window._progress_time_mode = 'hour'
        if hasattr(self.window, '_progress_program_start'):
            self.window._progress_program_start = None
        if hasattr(self.window, '_progress_program_end'):
            self.window._progress_program_end = None

        if hasattr(self.window, 'progress_start'):
            self.window.progress_start.setText("--:--")
        if hasattr(self.window, 'progress_end'):
            self.window.progress_end.setText("--:--")

        if hasattr(self.window, 'current_program'):
            self.window.current_program.setText("")
        if hasattr(self.window, 'remain_label') and hasattr(self.window, 'language_manager'):
            self.window.remain_label.setText(
                self.window.language_manager.tr("waiting_to_play", "Waiting to play..."))
        if hasattr(self.window, 'time_label'):
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M")
            self.window.time_label.setText(current_time)

    @property
    def is_playing(self) -> bool:
        if self.window.play_state.is_idle:
            return False
        window_ch = getattr(self.window, 'current_channel', None)
        return (self.current_channel is not None) or (window_ch is not None)

    @property
    def is_muted_state(self) -> bool:
        return self._is_muted

    def handle_play_state_change(self, is_playing):

        w = self.window
        tr = w.language_manager.tr
        btn_color = AppStyles.get_color('player_panel_text')
        pc = getattr(w, 'player_controller', None)
        # 图标与状态同源：只有在真正播放且未暂停时才显示暂停图标
        play_icon = AppStyles.play_icon_name(is_playing, getattr(pc, 'is_paused', False))
        play_icon_path = AppStyles.get_icon(play_icon, btn_color)
        if play_icon_path:
            w.play_button.setIcon(QIcon(play_icon_path))
        if is_playing:
            w.pip_ctrl._update_play_btn()
            w._cancel_source_timeout()
            for btn in ('stop_button', 'speed_button', 'aspect_button',
                        'audio_track_button', 'sub_track_button', 'volume_slider'):
                obj = getattr(w, btn, None)
                if obj is not None:
                    obj.setEnabled(True)
            if hasattr(w, 'video_placeholder') and w.video_placeholder:
                w.video_placeholder.hide()
            if hasattr(w, 'video_widget') and w.video_widget and w.video_frame:
                w.video_widget.setGeometry(0, 0, w.video_frame.width(), w.video_frame.height())
                w.video_widget.show()
            if hasattr(w, '_audio_visual_widget') and w._audio_visual_widget and w._audio_visual_widget.isVisible():
                w._audio_visual_widget.setGeometry(0, 0, w.video_frame.width(), w.video_frame.height())
                w._audio_visual_widget.raise_()
            w._last_info_key = None
            w.update_timer.start(1000)
            if w._is_local_file():
                if hasattr(w, 'epg_panel') and w.epg_panel:
                    if not hasattr(w, '_epg_hidden_by_local_file'):
                        w._epg_hidden_by_local_file = w.epg_visible
                    w.epg_visible = False
            elif hasattr(w, 'epg_panel') and w.epg_panel:
                if hasattr(w, '_epg_hidden_by_local_file'):
                    was_visible = w._epg_hidden_by_local_file
                    w._epg_hidden_by_local_file = False
                    if was_visible:
                        w.epg_visible = True
                elif getattr(w, 'epg_visible', True) and not w.epg_panel.isVisible():
                    w.epg_visible = True
            if w.current_channel:
                channel_name = w.current_channel.get('name', tr('unknown_channel', 'Unknown Channel'))
                if w.play_state.is_catchup_or_timeshift:
                    catchup_playing_text = tr('catchup_playing', '正在回看: {name}')
                    w.status_bar_show_message(catchup_playing_text.format(name=channel_name))
                    if getattr(w, '_pending_catchup_progress', None) is not None:
                        try:
                            progress_value = w._pending_catchup_progress
                            w._pending_catchup_progress = None
                            w._set_progress_value(progress_value)
                            w._target_catchup_progress = progress_value
                            import time
                            w._catchup_start_time = time.time()
                            w._catchup_start_progress = progress_value
                            logger.debug(f"记录回看开始时间：{w._catchup_start_time}，开始进度：{progress_value}%")
                            logger.debug(f"已设置回看进度条，保存目标值：{progress_value}%，保留禁用标志")
                        except Exception as e:
                            logger.error(f"设置回看进度条失败：{e}")
                else:
                    w.status_bar_show_message(f"{tr('playing', 'Playing')}: {channel_name}")
        else:
            # END_FILE / stop / 暂停都会走到这里；源超时看门狗只在加载阶段有意义
            if hasattr(w, '_cancel_source_timeout'):
                w._cancel_source_timeout()
            w.pip_ctrl._update_play_btn()
            if w.update_timer:
                w.update_timer.stop()
            if w.play_state.is_idle:
                for btn in ('stop_button', 'speed_button', 'aspect_button',
                            'audio_track_button', 'sub_track_button'):
                    obj = getattr(w, btn, None)
                    if obj is not None:
                        obj.setEnabled(False)
                return
            if w.current_channel:
                channel_name = w.current_channel.get('name', tr('unknown_channel', 'Unknown Channel'))
                if w.play_state.is_catchup_or_timeshift:
                    catchup_paused_text = tr('catchup_paused', '回看暂停: {name}')
                    w.status_bar_show_message(catchup_paused_text.format(name=channel_name))
                else:
                    w.status_bar_show_message(f"{tr('paused', 'Paused')}: {channel_name}")

    def seek_live(self, position):

        w = self.window
        if not w.current_channel or not w.player_controller:
            return

        seek_range = w.player_controller.get_available_seek_range()
        max_back = seek_range.get('max_back', 0)
        cache_duration = seek_range.get('cache_duration', 0)
        buffer_start = seek_range.get('buffer_start', 0)
        buffer_end = seek_range.get('buffer_end', 0)
        time_pos = seek_range.get('time_pos', 0)

        logger.info(f"直播拖动进度条 -> slider={position}s, "
                    f"time_pos={time_pos:.1f}s, buffer={buffer_start:.1f}s~{buffer_end:.1f}s, "
                    f"max_back={max_back}s, mode={getattr(w, '_progress_time_mode', '?')}")

        if max_back == 0 and cache_duration < 5:
            logger.warning(f"直播拖动进度条 -> 无法回退（缓冲区为空，cache={cache_duration:.1f}s）")
            w.status_bar_show_message(w.language_manager.tr("cannot_seek_live", "无法回退：直播流缓冲区不足"))
            return

        target_pos = w._map_slider_to_stream_position(position, seek_range)

        logger.info(f"直播拖动进度条 -> 映射后 target_pos={target_pos:.1f}s, "
                    f"clamp后={max(buffer_start, min(target_pos, buffer_end)):.1f}s")

        if target_pos < buffer_start:
            catchup_source = w.current_channel.get('catchup_source', '') if w.current_channel else ''
            # Fallback：catchup_source 为空时，即时从 URL 检测可回看模式（PLTV/TVOD、SNM/TVOD）
            if not catchup_source and w.current_channel:
                from services.m3u_parser import safe_detect_catchup_source
                catchup_source = safe_detect_catchup_source(w.current_channel.get('url', ''))
            if catchup_source:
                has_epg = getattr(w, '_progress_time_mode', None) == 'epg' and w._progress_program_start
                w._start_live_timeshift_from_progress(position, catchup_source, has_epg=has_epg)
                return
            else:
                w.status_bar_show_message(
                    w.language_manager.tr(
                        "timeshift_beyond_cache",
                        "超出缓冲范围，无法跳转到更早时间"
                    )
                )
            return

        target_pos = max(buffer_start, min(target_pos, buffer_end))

        timeshift = getattr(w, '_live_timeshift_seconds', 0)
        if timeshift > 0 and time_pos < 1:
            effective_pos = buffer_end - timeshift
        elif time_pos > 1:
            effective_pos = time_pos
        else:
            effective_pos = buffer_end

        if abs(target_pos - effective_pos) < 1:
            logger.info(f"直播拖动进度条 -> 跳过（目标{target_pos:.1f}s与当前位置{effective_pos:.1f}s差<1s, timeshift={timeshift}s）")
            return

        logger.info(f"直播拖动进度条 -> seek到 {target_pos:.1f}s")

        w.player_controller.seek_absolute(target_pos)

        if target_pos < buffer_end - 1:
            w._live_timeshift_seconds = buffer_end - target_pos
        else:
            w._live_timeshift_seconds = 0
