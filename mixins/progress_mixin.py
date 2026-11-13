from PySide6.QtCore import QTimer
from datetime import datetime, timedelta

from core.log_manager import global_logger as logger


class ProgressMixin:
    """从 IPTVPlayer 提取的进度条/Seek 职责"""

    def _map_slider_to_stream_position(self, slider_seconds, seek_range):
        buffer_start = seek_range.get('buffer_start', 0)
        buffer_end = seek_range.get('buffer_end', 0)

        if getattr(self, '_progress_time_mode', None) == 'epg' and self._progress_program_start:
            try:
                target_wallclock = self._progress_program_start + timedelta(seconds=slider_seconds)
                now = datetime.now()
                offset_from_live = (now - target_wallclock).total_seconds()
                target_pos = buffer_end - offset_from_live
                return target_pos
            except (ValueError, TypeError, AttributeError):
                pass

        try:
            now = datetime.now()
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            target_wallclock = hour_start + timedelta(seconds=slider_seconds)
            offset_from_live = (now - target_wallclock).total_seconds()
            target_pos = buffer_end - offset_from_live
            return target_pos
        except (ValueError, TypeError, AttributeError):
            pass

        total_seconds = self._progress_total_seconds
        if total_seconds <= 0:
            total_seconds = 3600
        ratio = slider_seconds / total_seconds
        return buffer_start + (buffer_end - buffer_start) * ratio

    def _set_progress_range(self, total_seconds):
        self._progress_total_seconds = total_seconds
        self.program_progress.setRange(0, int(total_seconds))

    def _set_progress_value(self, seconds):
        if self.program_progress.isSliderDown():
            return
        v = max(0, min(int(seconds), self.program_progress.maximum()))
        self.program_progress.setValue(v)


    def _get_progress_seconds(self):
        return self.program_progress.value()

    def _get_current_program_duration(self):
        try:
            if self.current_channel:
                channel_name, tvg_id, tvg_name, comma_name = self._get_epg_match_params()
                current_program = self.epg_parser.get_current_program(channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
                if current_program:
                    start_time = datetime.fromisoformat(current_program.get('start', ''))
                    end_time = datetime.fromisoformat(current_program.get('end', ''))
                    duration = int((end_time - start_time).total_seconds())
                    if duration > 0:
                        return duration
        except (ValueError, KeyError, TypeError):
            pass
        return 0

    def _check_program_change(self):
        is_catchup = self.play_state.is_catchup_or_timeshift
        if is_catchup:
            return

        if self._is_local_file():
            return

        try:
            if not self.current_channel or not self.player_controller:
                return

            channel_name, tvg_id, tvg_name, comma_name = self._get_epg_match_params()
            current_program = self.epg_parser.get_current_program(channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)

            if current_program:
                program_id = current_program.get('start', '') + current_program.get('end', '')
                last_id = getattr(self, '_last_program_id', None)

                if last_id != program_id:
                    logger.info(f"检测到节目切换，更新UI信息 (last={last_id}, new={program_id})")
                    self._live_timeshift_seconds = 0
                    desc = current_program.get('desc', '') or self.language_manager.tr('no_program_desc', 'No program description')
                    if hasattr(self, 'program_desc') and self.program_desc:
                        self.program_desc.setText(desc)
                    if hasattr(self, 'program_progress'):
                        new_duration = self._get_current_program_duration()
                        if new_duration > 0:
                            self._set_progress_range(new_duration)
                            self._set_progress_value(0)

                self._last_program_id = program_id
            else:
                self._last_program_id = None
        except Exception as e:
            logger.debug("节目切换检测异常: {}".format(e))

    def _on_progress_slider_pressed(self):
        self._stop_auto_hide_timer()
        self._live_seek_unavailable = False
        if self._is_live_seek_unavailable():
            # 直播链路没有可回退缓冲：不要冻结进度更新/吞掉拖动，直接给出说明
            self._live_seek_unavailable = True
            self.status_bar_show_message(
                self.language_manager.tr(
                    "live_seek_unavailable",
                    "直播流暂不支持拖动，可在节目单中选择「可回看」节目回看"
                )
            )
            return
        self._disable_progress_auto_update = True

    def _is_live_seek_unavailable(self):
        """直播态且当前缓冲不可回退时，进度条不应进入拖动逻辑。"""
        try:
            if self.play_state.is_catchup_or_timeshift:
                return False
            if getattr(self, '_progress_time_mode', None) == 'vod':
                return False
            pc = getattr(self, 'player_controller', None)
            if not pc:
                return False
            seek_range = pc.get_available_seek_range() or {}
            return (seek_range.get('max_back', 0) == 0
                    and seek_range.get('cache_duration', 0) < 5)
        except Exception:
            return False

    def _format_preview_text(self, seconds):
        mode = getattr(self, '_progress_time_mode', None)
        if mode == 'vod':
            return self._format_seconds_to_time(seconds)
        elif mode == 'epg':
            program_start = getattr(self, '_progress_program_start', None)
            if program_start:
                preview_time = program_start + timedelta(seconds=seconds)
                return preview_time.strftime("%H:%M:%S")
            return self._format_seconds_to_time(seconds)
        elif mode == 'hour':
            now = datetime.now()
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            preview_time = hour_start + timedelta(seconds=seconds)
            return preview_time.strftime("%H:%M:%S")
        else:
            is_catchup = self.play_state.is_catchup_or_timeshift
            if is_catchup:
                catchup_program = getattr(self, 'catchup_program', None)
                if catchup_program:
                    start_time = catchup_program.get('start')
                    if start_time:
                        preview_time = start_time + timedelta(seconds=seconds)
                        return preview_time.strftime("%H:%M:%S")
            return self._format_seconds_to_time(seconds)

    def _on_progress_preview(self, seconds):
        self.program_progress.set_preview_text(self._format_preview_text(seconds))

    def _format_seconds_to_time(self, seconds):
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def on_progress_slider_released(self):
        if hasattr(self, '_slider_debounce_timer') and self._slider_debounce_timer is not None:
            self._slider_debounce_timer.stop()
        else:
            self._slider_debounce_timer = QTimer(self)
            self._slider_debounce_timer.setSingleShot(True)
            self._slider_debounce_timer.timeout.connect(self._do_progress_slider_released)
        self._slider_debounce_timer.start(self.SLIDER_DEBOUNCE_MS)

    def _do_progress_slider_released(self):
        self._disable_progress_auto_update = False
        if getattr(self, '_live_seek_unavailable', False):
            # 拖动被判定为不可用：恢复自动更新，下一拍进度刷新会把滑块拉回直播位置
            self._live_seek_unavailable = False
            return
        is_catchup = self.play_state.is_catchup_or_timeshift
        if getattr(self, '_progress_time_mode', None) == 'vod' and not is_catchup:
            self._seek_vod(self._get_progress_seconds())
        elif is_catchup:
            self._seek_catchup(self._get_progress_seconds())
        else:
            self._seek_live(self._get_progress_seconds())

        if getattr(self, 'is_fullscreen', False):
            self._restart_auto_hide_timer()

    def _seek_vod(self, position):
        if self.player_controller:
            self.player_controller.seek_absolute(float(position))

    def _seek_live(self, position):
        if not self.current_channel or not self.player_controller:
            return

        seek_range = self.player_controller.get_available_seek_range()
        max_back = seek_range.get('max_back', 0)
        cache_duration = seek_range.get('cache_duration', 0)
        buffer_start = seek_range.get('buffer_start', 0)
        buffer_end = seek_range.get('buffer_end', 0)
        time_pos = seek_range.get('time_pos', 0)

        logger.info(f"直播拖动进度条 -> slider={position}s, "
                    f"time_pos={time_pos:.1f}s, buffer={buffer_start:.1f}s~{buffer_end:.1f}s, "
                    f"max_back={max_back}s, mode={getattr(self, '_progress_time_mode', '?')}")

        if max_back == 0 and cache_duration < 5:
            logger.warning(f"直播拖动进度条 -> 无法回退（缓冲区为空，cache={cache_duration:.1f}s）")
            self.status_bar_show_message(self.language_manager.tr("cannot_seek_live", "无法回退：直播流缓冲区不足"))
            return

        target_pos = self._map_slider_to_stream_position(position, seek_range)

        logger.info(f"直播拖动进度条 -> 映射后 target_pos={target_pos:.1f}s, "
                    f"clamp后={max(buffer_start, min(target_pos, buffer_end)):.1f}s")

        if target_pos < buffer_start:
            catchup_source = self.current_channel.get('catchup_source', '') if self.current_channel else ''
            # Fallback：catchup_source 为空时，即时从 URL 检测可回看模式（PLTV/TVOD、SNM/TVOD）
            if not catchup_source and self.current_channel:
                from services.m3u_parser import safe_detect_catchup_source
                catchup_source = safe_detect_catchup_source(self.current_channel.get('url', ''))
            if catchup_source:
                has_epg = getattr(self, '_progress_time_mode', None) == 'epg' and self._progress_program_start
                self._start_live_timeshift_from_progress(position, catchup_source, has_epg=has_epg)
                return
            else:
                self.status_bar_show_message(
                    self.language_manager.tr(
                        "timeshift_beyond_cache",
                        "超出缓冲范围，无法跳转到更早时间"
                    )
                )
            return

        target_pos = max(buffer_start, min(target_pos, buffer_end))

        timeshift = getattr(self, '_live_timeshift_seconds', 0)
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

        self.player_controller.seek_absolute(target_pos)

        if target_pos < buffer_end - 1:
            self._live_timeshift_seconds = buffer_end - target_pos
        else:
            self._live_timeshift_seconds = 0

    def _seek_catchup(self, position):
        self.catchup_ctrl.seek_catchup(position)

    def _start_live_timeshift_from_progress(self, slider_seconds, catchup_source, has_epg=True):
        self.catchup_ctrl.start_live_timeshift_from_progress(slider_seconds, catchup_source, has_epg=has_epg)