from datetime import datetime, timedelta
from core.log_manager import global_logger as logger


class ProgressController:

    def __init__(self, window):
        self.window = window

    def update_progress(self, current_time_ms, total_time_ms, position):
        w = self.window
        play_state = w.play_state

        if play_state.is_catchup and not play_state.is_timeshift:
            self._update_catchup_progress(current_time_ms, total_time_ms, position)
        elif play_state.is_timeshift:
            self._update_timeshift_progress(current_time_ms, total_time_ms, position)
        else:
            has_epg, current_program = self._get_current_epg()
            if has_epg and current_program:
                self._update_epg_progress(current_program, current_time_ms, total_time_ms, position)
            else:
                self._update_default_progress(current_time_ms, total_time_ms, position)

    def _update_catchup_progress(self, current_time_ms, total_time_ms, position):
        w = self.window
        catchup_program = getattr(w, 'catchup_program', None)
        if catchup_program is None:
            return

        try:
            start_time = catchup_program.get('start')
            end_time = catchup_program.get('end')
            if not start_time or not end_time:
                return

            total_duration = (end_time - start_time).total_seconds()
            start_str = start_time.strftime("%H:%M")
            end_str = end_time.strftime("%H:%M")
            w.progress_start.setText(start_str)
            w.progress_end.setText(end_str)
            w.progress_start.repaint()
            w.progress_end.repaint()

            # 回看进度条 = 节目开播起的秒数，必须同步设置 epg 模式和节目起点，
            # 否则残留直播的 'hour' 模式，悬浮预览会按当前小时换算出错误时间
            w._progress_time_mode = 'epg'
            w._progress_program_start = start_time
            w._progress_program_end = end_time

            current_position = current_time_ms / 1000 if current_time_ms else 0

            if total_duration > 0:
                if abs(w._progress_total_seconds - int(total_duration)) > 1:
                    w._set_progress_range(int(total_duration))

                if hasattr(w, '_catchup_start_time') and hasattr(w, '_catchup_start_progress') \
                        and w._catchup_start_time is not None and w._catchup_start_progress is not None:
                    import time
                    current_time = time.time()
                    # get_speed 在流结束/加载中可能返回 None，参与运算会 TypeError
                    speed = (w.player_controller.get_speed() if w.player_controller else 1.0) or 1.0

                    if current_time_ms:
                        # 以mpv实际内容位置为准：倍速下墙钟外推会在网络缓冲停顿时
                        # 超前于真实位置，导致提前跨边界滚动、连锁滚动到失真位置、
                        # 甚至误触发"追上直播"降速。time-pos从URL起点连续计数
                        # （滚动到下一节目不重载流），减去累计节目起点偏移得到节目内位置
                        raw_seconds = max(0.0, current_time_ms / 1000 - getattr(w, '_catchup_time_pos_offset', 0.0))
                        # 同步校准墙钟基准，time-pos 短暂不可用时兜底
                        w._catchup_start_progress = raw_seconds
                        w._catchup_start_time = current_time
                    else:
                        raw_seconds = w._catchup_start_progress + (current_time - w._catchup_start_time) * speed

                    # 进度越过节目末尾：回看流连续发流，内容已进入下一节目，
                    # 滚动记账到下一节目（保留倍速、重置进度条、刷新EPG标记）
                    if raw_seconds >= total_duration:
                        try:
                            if w.catchup_ctrl.rollover_catchup_program(raw_seconds):
                                return
                        except Exception as e:
                            logger.debug(f"回看滚动到下一节目失败: {e}")

                    progress_seconds = min(int(raw_seconds), int(total_duration))

                    if progress_seconds >= int(total_duration) * 0.98 and hasattr(w, 'speed_button') and w.player_controller:
                        # 只有真正追到直播边缘才恢复 1.0x：老节目回看到 98% 但
                        # 墙钟位置仍落后于直播时，用户可能主动倍速观看，不应被强制降速
                        try:
                            playback_wallclock = start_time + timedelta(seconds=progress_seconds)
                            caught_up = (datetime.now() - playback_wallclock).total_seconds() <= 3
                        except (TypeError, ValueError):
                            caught_up = False
                        current_speed = w.player_controller.get_speed()
                        if caught_up and current_speed is not None and abs(current_speed - 1.0) > 0.01:
                            w.player_controller.set_speed(1.0)
                            w.speed_button.setText("1.0x")
                            logger.info("回看已追上直播，自动恢复倍速到1.0x")

                    w._set_progress_value(progress_seconds)
                else:
                    if getattr(w, '_disable_progress_auto_update', False):
                        target_progress = getattr(w, '_target_catchup_progress', 0)
                        if current_position >= target_progress * 0.9:
                            setattr(w, '_disable_progress_auto_update', False)
                    else:
                        progress_seconds = min(int(current_position), int(total_duration)) if current_position > 0 else 0
                        w._set_progress_value(progress_seconds)
            else:
                if not getattr(w, '_disable_progress_auto_update', False):
                    w._set_progress_value(0)
        except Exception as e:
            logger.error(f"处理回看时间显示失败: {e}")
            self._fallback_progress(current_time_ms, total_time_ms, position)

    def _update_timeshift_progress(self, current_time_ms, total_time_ms, position):
        w = self.window
        catchup_program = getattr(w, 'catchup_program', None)
        has_epg, current_program = self._get_current_epg()
        if catchup_program or (has_epg and current_program):
            self._update_timeshift_epg_progress(current_program, current_time_ms, total_time_ms, position)
        else:
            self._update_timeshift_live_progress()

    def _update_timeshift_epg_progress(self, current_program, current_time_ms, total_time_ms, position):
        w = self.window
        try:
            now = datetime.now()
            catchup_program = getattr(w, 'catchup_program', None)
            if catchup_program:
                start_time = catchup_program.get('start')
                end_time = catchup_program.get('end')
                # 时移窗口的终点应随直播推进。若冻结在"进入时移"的时刻，
                # 进度条会很快顶在 100% 不再前进，拖动映射的窗口范围也不再
                # 覆盖新到内容。这里把 end 平滑推进到当前直播边缘。
                if (w.play_state.is_timeshift and isinstance(end_time, datetime)
                        and end_time < now):
                    end_time = now
                    catchup_program['end'] = end_time
            else:
                start_time = datetime.fromisoformat(current_program.get('start', ''))
                end_time = datetime.fromisoformat(current_program.get('end', ''))

            if not start_time or not end_time:
                return

            total_duration = (end_time - start_time).total_seconds()
            if total_duration <= 0:
                return

            if abs(w._progress_total_seconds - int(total_duration)) > 1:
                w._set_progress_range(int(total_duration))
            w._progress_time_mode = 'epg'
            w._progress_program_start = start_time
            w._progress_program_end = end_time

            if hasattr(w, '_catchup_start_time') and hasattr(w, '_catchup_start_progress') \
                    and w._catchup_start_time is not None and w._catchup_start_progress is not None:
                import time
                elapsed = time.time() - w._catchup_start_time
                speed = (w.player_controller.get_speed() if w.player_controller else 1.0) or 1.0
                current_position = w._catchup_start_progress + elapsed * speed
                current_position = max(0, min(current_position, total_duration))
            else:
                timeshift = getattr(w, '_live_timeshift_seconds', 0)
                if timeshift > 0:
                    current_position = (now - timedelta(seconds=timeshift) - start_time).total_seconds()
                    current_position = max(0, min(current_position, total_duration))
                else:
                    current_position = (now - start_time).total_seconds()

            w._set_progress_value(current_position)

            start_str = start_time.strftime("%H:%M")
            end_str = end_time.strftime("%H:%M")
            w.progress_start.setText(start_str)
            w.progress_end.setText(end_str)
            w.progress_start.repaint()
            w.progress_end.repaint()
        except Exception:
            self._fallback_progress(current_time_ms, total_time_ms, position)

    def _update_timeshift_live_progress(self):
        w = self.window
        if w._progress_total_seconds != 3600:
            w._set_progress_range(3600)
            w._progress_time_mode = 'hour'
            w._progress_program_start = None
            w._progress_program_end = None

        timeshift = getattr(w, '_live_timeshift_seconds', 0)
        if timeshift > 0:
            effective_time = datetime.now() - timedelta(seconds=timeshift)
        else:
            effective_time = datetime.now()

        start_hour = effective_time.replace(minute=0, second=0, microsecond=0).strftime("%H:00")
        end_hour = (effective_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).strftime("%H:00")
        w.progress_start.setText(start_hour)
        w.progress_end.setText(end_hour)
        w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
        seconds_from_hour = effective_time.minute * 60 + effective_time.second
        w._set_progress_value(seconds_from_hour)

        if hasattr(w, 'remain_label') and w.remain_label.isVisible():
            playing_label = w.language_manager.tr("playing_label", "Playing...")
            if w.remain_label.text() != playing_label:
                w.remain_label.setText(playing_label)

    def _update_epg_progress(self, current_program, current_time_ms, total_time_ms, position):
        w = self.window
        try:
            start_time = datetime.fromisoformat(current_program.get('start', ''))
            end_time = datetime.fromisoformat(current_program.get('end', ''))
            now = datetime.now()

            total_duration = (end_time - start_time).total_seconds()

            if total_duration > 0:
                if abs(w._progress_total_seconds - int(total_duration)) > 1:
                    w._set_progress_range(int(total_duration))
                w._progress_time_mode = 'epg'
                w._progress_program_start = start_time
                w._progress_program_end = end_time

                timeshift = getattr(w, '_live_timeshift_seconds', 0)
                if timeshift > 0:
                    current_position = (now - timedelta(seconds=timeshift) - start_time).total_seconds()
                    live_position = (now - start_time).total_seconds()
                    if current_position >= live_position - 1:
                        w._live_timeshift_seconds = 0
                        current_position = live_position
                    else:
                        current_position = max(0, current_position)
                else:
                    current_position = (now - start_time).total_seconds()

                w._set_progress_value(current_position)

                start_str = start_time.strftime("%H:%M")
                end_str = end_time.strftime("%H:%M")
                w.progress_start.setText(start_str)
                w.progress_end.setText(end_str)
            else:
                if not w.play_state.is_catchup_or_timeshift:
                    w._set_progress_value(0)
        except Exception:
            self._fallback_progress(current_time_ms, total_time_ms, position)

    def _update_default_progress(self, current_time_ms, total_time_ms, position):
        w = self.window
        is_local_file = w._is_local_file() if hasattr(w, '_is_local_file') else False

        if is_local_file and total_time_ms > 0:
            self._update_vod_progress(int(current_time_ms) // 1000 if current_time_ms else 0,
                                      int(total_time_ms) // 1000)
        elif is_local_file:
            self._update_vod_fallback()
        else:
            self._update_live_progress()

    def _update_vod_progress(self, current_seconds, total_seconds):
        w = self.window
        if total_seconds <= 0:
            return

        if abs(w._progress_total_seconds - total_seconds) > 1:
            w._set_progress_range(total_seconds)
        w._progress_time_mode = 'vod'
        w._progress_program_start = None
        w._progress_program_end = None

        w._set_progress_value(current_seconds)
        self._format_vod_time(current_seconds, total_seconds)

    def _update_vod_fallback(self):
        w = self.window
        w._progress_time_mode = 'vod'
        w._progress_program_start = None
        w._progress_program_end = None

        total_time_ms = getattr(w, '_cached_total_time_ms', 0)
        current_time_ms = getattr(w, '_cached_current_time_ms', 0)

        if total_time_ms <= 0 and w.player_controller and w.player_controller.is_playing:
            try:
                fallback_total = w.player_controller.get_total_time()
                fallback_current = w.player_controller.get_current_time()
                if fallback_total > 0:
                    w._cached_total_time_ms = fallback_total
                    w._cached_current_time_ms = fallback_current
                    total_seconds = int(fallback_total) // 1000
                    current_seconds = int(fallback_current) // 1000 if fallback_current else 0
                    if abs(w._progress_total_seconds - total_seconds) > 1:
                        w._set_progress_range(total_seconds)
                    w._set_progress_value(current_seconds)
                    self._format_vod_time(current_seconds, total_seconds)
                    return
            except Exception as e:
                logger.debug(f"VOD进度回退失败: {e}")

        w.progress_start.setText("--:--")
        w.progress_end.setText("--:--")
        w.time_label.setText("--:-- / --:--")
        w._set_progress_value(0)
        if hasattr(w, 'remain_label'):
            w.remain_label.setText(w.language_manager.tr("loading", "加载中..."))

    def _update_live_progress(self):
        w = self.window
        if w._progress_total_seconds != 3600:
            w._set_progress_range(3600)
            w._progress_time_mode = 'hour'
            w._progress_program_start = None
            w._progress_program_end = None

        timeshift = getattr(w, '_live_timeshift_seconds', 0)
        if timeshift > 0:
            effective_time = datetime.now() - timedelta(seconds=timeshift)
        else:
            effective_time = datetime.now()

        start_hour = effective_time.strftime("%H:00")
        end_hour = (effective_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).strftime("%H:00")
        w.progress_start.setText(start_hour)
        w.progress_end.setText(end_hour)
        w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
        seconds_from_hour = effective_time.minute * 60 + effective_time.second
        w._set_progress_value(seconds_from_hour)

        if hasattr(w, 'remain_label') and w.remain_label.isVisible():
            current_text = w.remain_label.text()
            playing_label = w.language_manager.tr("playing_label", "Playing...")
            if current_text != playing_label:
                w.remain_label.setText(playing_label)

    def _format_vod_time(self, current_seconds, total_seconds):
        w = self.window
        m_s, s_s = divmod(current_seconds, 60)
        m_e, s_e = divmod(total_seconds, 60)
        if m_s >= 60 or m_e >= 60:
            h_s, m_s = divmod(m_s, 60)
            h_e, m_e = divmod(m_e, 60)
            w.progress_start.setText(f"{h_s}:{m_s:02d}:{s_s:02d}")
            w.progress_end.setText(f"{h_e}:{m_e:02d}:{s_e:02d}")
            w.time_label.setText(f"{h_s}:{m_s:02d}:{s_s:02d} / {h_e}:{m_e:02d}:{s_e:02d}")
        else:
            w.progress_start.setText(f"{m_s}:{s_s:02d}")
            w.progress_end.setText(f"{m_e}:{s_e:02d}")
            w.time_label.setText(f"{m_s}:{s_s:02d} / {m_e}:{s_e:02d}")

        remain = total_seconds - current_seconds
        m_r, s_r = divmod(remain, 60)
        if m_r >= 60:
            h_r, m_r = divmod(m_r, 60)
            w.remain_label.setText(f"-{h_r}:{m_r:02d}:{s_r:02d}")
        else:
            w.remain_label.setText(f"-{m_r}:{s_r:02d}")

    def _fallback_progress(self, current_time_ms, total_time_ms, position):
        w = self.window
        if total_time_ms > 0:
            w._set_progress_value(position * total_time_ms / 1000)
            current_str = self._format_ms(current_time_ms)
            total_str = self._format_ms(total_time_ms)
            w.progress_start.setText(current_str)
            w.progress_end.setText(total_str)
        else:
            if not w.play_state.is_catchup_or_timeshift:
                w._set_progress_value(0)

    def _get_current_epg(self):
        w = self.window
        if w._is_local_file() if hasattr(w, '_is_local_file') else False:
            return False, None
        if w.play_state.is_catchup and not w.play_state.is_timeshift:
            return False, None
        try:
            channel_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
            if channel_name:
                current_program = w.epg_parser.get_current_program(channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
                if current_program:
                    return True, current_program
        except Exception as e:
            logger.debug(f"获取EPG当前节目失败: {e}")
        return False, None

    @staticmethod
    def _format_ms(ms):
        if not ms or ms <= 0:
            return "00:00:00"
        seconds = int(ms) // 1000
        minutes = seconds // 60
        hours = minutes // 60
        return f"{hours:02d}:{minutes % 60:02d}:{seconds % 60:02d}"
