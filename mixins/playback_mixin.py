from typing import Any, Dict

from PySide6.QtCore import QTimer
from core.log_manager import global_logger as logger
from utils.platform_utils import wayland_set_geometry
from utils.thread_safety import safe_single_shot


class PlaybackMixin:
    """从 IPTVPlayer 提取的播放控制职责"""

    def toggle_osd(self, checked=None):
        self.ui_ctrl.toggle_osd(checked)

    def toggle_play(self):
        self.playback_ctrl.toggle_play()

    def stop_playback(self):
        self.playback_ctrl.stop_playback()

    def set_volume(self, value):
        self.playback_ctrl.set_volume(value)
        if not self._suppress_volume_osd and not self._osd_visible:
            self._show_osd_feedback(f"{self.language_manager.tr('osd_volume', 'Volume')}: {value}%")

    def toggle_mute(self):
        self._suppress_volume_osd = True
        self.playback_ctrl.toggle_mute()
        if not self._osd_visible:
            if self.playback_ctrl.is_muted_state:
                self._show_osd_feedback(self.language_manager.tr('osd_muted', 'Muted'))
            else:
                vol = self.volume_slider.value() if hasattr(self, 'volume_slider') else 0
                self._show_osd_feedback(f"{self.language_manager.tr('osd_volume', 'Volume')}: {vol}%")
        self._suppress_volume_osd = False

    def _show_osd_feedback(self, text: str):
        if hasattr(self, 'player_controller') and self.player_controller:
            self.player_controller.show_osd(text, 2000)

    def play_channel(self, channel):
        # 快速连点换台不在这里拦截：切换窗口内的请求由控制器排队，最后一次请求生效
        self.playback_ctrl.play_channel(channel)
        if channel and channel.get('url'):
            self.favorites_ctrl.on_channel_played(channel)

    def _do_play_channel(self, channel):
        self.playback_ctrl._do_play_channel(channel)

    def on_play_error(self, error_msg):
        tr = self.language_manager.tr
        logger.error(f"播放错误：{error_msg}")
        if self.current_channel:
            channel_name = self.current_channel.get('name', tr('unknown_channel', 'Unknown Channel'))
            self.status_bar_show_message(f"{tr('play_error', 'Play Error')}: {channel_name} - {error_msg}")
        else:
            self.status_bar_show_message(f"{tr('play_error', 'Play Error')}: {error_msg}")

    def on_source_connecting(self, url):
        """loadfile 已发出但尚未出流：明确显示"正在连接"，避免假"正在播放"。"""
        tr = self.language_manager.tr
        name = ''
        if self.current_channel:
            name = self.current_channel.get('name', '')
        text = f"{tr('connecting', '正在连接')}: {name or url}"
        self.status_bar_show_message(text)
        if hasattr(self, 'remain_label') and self.remain_label:
            self.remain_label.setText(tr('connecting_label', '连接中…'))

    def _on_reconnect_requested(self, url):
        tr = self.language_manager.tr
        pc = self.player_controller
        if getattr(pc, '_reconnect_exhausted', False):
            logger.debug("重连已耗尽，忽略 reconnect_requested")
            return
        if self.current_channel:
            channel_name = self.current_channel.get('name', '')
            self.status_bar_show_message(
                f"{tr('reconnecting', 'Reconnecting')}: {channel_name} "
                f"({self.player_controller._reconnect_count}/{self.player_controller._max_reconnect})")

        def _reconnect_callback():
            try:
                self._do_reconnect(url)
            except RuntimeError:
                pass

        safe_single_shot(self.RECONNECT_DELAY_MS, self, _reconnect_callback)

    def _on_timeshift_continue(self):
        # 回看流的URL带endTime，节目播完服务器会切断流触发EOF，
        # 同样需要自动续播到下一节目（时移同理）
        if self.play_state.is_catchup_or_timeshift:
            logger.info("回看/时移流播放到终点，自动续播")
            self.catchup_ctrl.continue_timeshift()
            # 续播兜底：只有确认已停流（既未播放也未暂停，且不在缓冲/加载中）
            # 才退回直播。原先固定 8 秒判定，慢源/IPv6 回退尚未出画面就被误判失败。
            attempts = {'n': 0}

            def _check_catchup_resume():
                try:
                    pc = self.player_controller
                    if not pc:
                        return
                    if getattr(pc, 'is_playing', False) or getattr(pc, 'is_paused', False):
                        return
                    if getattr(pc, '_user_stopped', False):
                        return
                    buffering = False
                    try:
                        buffering = bool((pc.get_buffer_state() or {}).get('buffering', False))
                    except Exception:
                        pass
                    if (buffering or getattr(pc, '_switching_channel', False)) and attempts['n'] < 2:
                        attempts['n'] += 1
                        logger.info("时移/回看续播仍在缓冲，延长等待后再次检查")
                        safe_single_shot(12000, self, _check_catchup_resume)
                        return
                    if not self.current_channel:
                        return
                    tr = self.language_manager.tr
                    logger.warning("时移/回看续播多次等待后仍未播放，退回直播")
                    self.status_bar_show_message(
                        f"{tr('timeshift_failed_back_to_live', '时移播放失败，退回直播')}: "
                        f"{self.current_channel.get('name', '')}")
                    self.playback_ctrl.play_channel(self.current_channel)
                except RuntimeError:
                    pass
            safe_single_shot(10000, self, _check_catchup_resume)
        else:
            # 直播网络流 EOF（服务器主动断流）：此前该信号在直播模式下无人处理，
            # 会停在 play_state=False 的停止态。这里按断线处理并重连。
            # 注意：网络点播（有已知时长）播完不应重连，否则会从头循环播放。
            pc = getattr(self, 'player_controller', None)
            if pc and not getattr(pc, '_user_stopped', False) and self.current_channel:
                # 直播 TS 的 duration 可能被服务端关闭连接后估出非 0 值，不能据此判断点播；
                # 只认显式的点播模式（打开视频文件走 'vod'）。
                if getattr(self, '_progress_time_mode', None) == 'vod':
                    logger.info("点播文件播放结束，不自动重连")
                    return
                logger.info("直播流播放到终点，触发重连续播")
                self.playback_ctrl.on_live_disconnect(pc.current_url, reason='live_eof')

    def _do_reconnect(self, url):
        pc = self.player_controller
        if pc._user_stopped or pc._reconnect_exhausted:
            return
        # 重连延迟期间若新流已经成功加载，就不要再次重启播放（会造成闪断）
        if getattr(pc, 'is_playing', False):
            logger.debug("重连跳过：播放已恢复")
            return
        if self.current_channel:
            if self.play_state.is_catchup_or_timeshift:
                tr = self.language_manager.tr
                channel_name = self.current_channel.get('name', '')
                logger.info(f"时移/回看播放失败，自动退回直播: {channel_name}")
                self.status_bar_show_message(
                    f"{tr('timeshift_failed_back_to_live', '时移播放失败，退回直播')}: {channel_name}"
                )
            # 标记这是重连发起的 play：play() 不能重置重连计数，否则会无限循环
            pc._reconnect_in_progress = True
            try:
                self.playback_ctrl.play_channel(self.current_channel)
            finally:
                pc._reconnect_in_progress = False

    def on_live_media_info_updated(self, info: Dict[str, Any]):
        self.ui_ctrl.on_live_media_info_updated(info)

    def adjust_window_size_to_video(self):
        if not self.player_controller:
            return

        try:
            resolution = self.player_controller.get_video_resolution()
            if not resolution:
                return

            parts = resolution.split('x')
            if len(parts) != 2:
                return

            video_width = int(parts[0])
            video_height = int(parts[1])

            if video_width <= 0 or video_height <= 0:
                return

            current_height = self.height()
            current_width = self.width()

            max_video_width = 1920
            if video_width > max_video_width:
                original_video_width = video_width
                video_width = max_video_width
                video_height = int(video_height * (max_video_width / original_video_width))

            scale = current_height / video_height
            new_window_width = int(video_width * scale)
            new_window_width = max(800, min(new_window_width, 1920))

            if abs(new_window_width - current_width) < 50:
                return

            current_geometry = self.geometry()
            center_x = current_geometry.x() + current_geometry.width() // 2
            center_y = current_geometry.y() + current_geometry.height() // 2

            new_x = center_x - new_window_width // 2
            new_y = center_y - current_height // 2

            wayland_set_geometry(self, new_x, new_y, new_window_width, current_height)

        except Exception as e:
            logger.debug(f"调整窗口大小异常: {e}")

    def update_media_info(self):
        self.ui_ctrl.update_media_info()

    def _on_playback_position_updated(self, current_time_ms, total_time_ms, position):
        prev_total = getattr(self, '_cached_total_time_ms', 0) or 0
        self._cached_current_time_ms = current_time_ms
        self._cached_total_time_ms = total_time_ms
        self._cached_position = position
        if ((not prev_total or prev_total <= 0) and total_time_ms and total_time_ms > 0
                and self._is_local_file()):
            logger.warning(f"[GOT_DURATION] total={total_time_ms:.0f}ms cur={current_time_ms:.0f}ms pos={position:.4f}")
        self.update_floating_panel_info()

    def update_floating_panel_info(self):
        self.ui_ctrl.update_floating_panel_info()
