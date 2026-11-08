from PySide6.QtCore import QTimer
from core.log_manager import global_logger as logger
import re
from datetime import datetime, timedelta, timezone
from core.play_state import PlayMode
from controllers.main_window_protocol import MainWindowProtocol, CatchupProgram


class CatchupController:

    CATCHUP_TYPES = {
        'default', 'append', 'shift', 'flussonic', 'fs',
        'xc', 'xtream', 'vod', 'timemachine', 'pltv'
    }

    URL_REBUILD_COOLDOWN = 3.0
    # 节目结束时间距"现在"不超过该阈值即视为已追到直播边缘
    LIVE_EDGE_TOLERANCE_SECONDS = 30

    def __init__(self, main_window: MainWindowProtocol):
        self.window: MainWindowProtocol = main_window
        self._original_channel: dict | None = None
        self._catchup_program: CatchupProgram | None = None
        self._last_url_rebuild_time: float = 0.0
        self._url_rebuild_pending: bool = False
        self._pending_seek_after_cooldown: float | None = None
        self._cooldown_timer = None

    def _fcc_leave(self):
        """进入回看/时移前，向 FCC 代理补发直播源的 LEAVE。"""
        playback_ctrl = getattr(self.window, 'playback_ctrl', None)
        fcc = getattr(playback_ctrl, 'fcc', None)
        if fcc:
            try:
                fcc.on_stop()
            except Exception as e:
                logger.debug(f"回看切换前发送FCC LEAVE失败: {e}")

    def _fcc_switch(self, url: str):
        """直接调用 player_controller.play 的直播路径也要同步 FCC 状态。"""
        if not url:
            return
        playback_ctrl = getattr(self.window, 'playback_ctrl', None)
        fcc = getattr(playback_ctrl, 'fcc', None)
        if fcc:
            try:
                fcc.on_channel_change(url)
            except Exception as e:
                logger.debug(f"直播切换时同步FCC状态失败: {e}")

    @property
    def original_channel(self) -> dict | None:
        return self._original_channel

    @original_channel.setter
    def original_channel(self, value: dict | None):
        self._original_channel = value
        self.window.original_channel = value

    @property
    def catchup_program(self) -> CatchupProgram | None:
        return self._catchup_program

    @catchup_program.setter
    def catchup_program(self, value: CatchupProgram | None):
        self._catchup_program = value
        self.window.catchup_program = value

    def _enter_catchup_state(self, channel: dict, program: CatchupProgram, mode: PlayMode = PlayMode.CATCHUP):
        self.original_channel = channel.copy()
        self.catchup_program = program
        self.window.play_state.mode = mode
        self.window._live_timeshift_seconds = 0
        # 立即切到 epg 模式并记录节目起点，避免首个进度 tick 之前
        # 悬浮预览仍按直播的 'hour' 模式换算出错误时间
        w = self.window
        start_time = program.get('start')
        if start_time:
            w._progress_time_mode = 'epg'
            w._progress_program_start = start_time
            w._progress_program_end = program.get('end')

    def _clear_catchup_state(self, set_state='idle'):
        self._original_channel = None
        self._catchup_program = None
        if set_state == 'live':
            self.window.play_state.set_live()
        elif set_state == 'idle':
            self.window.play_state.set_idle()
        self.window._live_timeshift_seconds = 0
        self.window.catchup_program = None

    def replace_catchup_variables(self, catchup_source: str, start_time: datetime, end_time: datetime) -> str:
        if not catchup_source:
            return catchup_source

        url = catchup_source

        def apply_timezone_offset(dt, offset_str):
            if not offset_str:
                return dt
            offset_str = offset_str.strip()
            if offset_str.lower() == 'utc':
                if dt.tzinfo is None:
                    local_tz = datetime.now().astimezone().tzinfo
                    dt = dt.replace(tzinfo=local_tz)
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            if offset_str.lower() == 'local':
                return dt
            m = re.match(r'^([+-])(\d{1,2}):?(\d{2})$', offset_str)
            if m:
                sign = 1 if m.group(1) == '+' else -1
                hours = int(m.group(2))
                minutes = int(m.group(3))
                offset = timedelta(hours=hours, minutes=minutes) * sign
                target_tz = timezone(offset)
                if dt.tzinfo is None:
                    local_tz = datetime.now().astimezone().tzinfo
                    dt = dt.replace(tzinfo=local_tz)
                return dt.astimezone(target_tz).replace(tzinfo=None)
            return dt

        def format_time(dt, fmt):
            timezone_spec = None
            base_fmt = fmt

            parts = re.split(r'[|]', fmt, maxsplit=1)
            if len(parts) > 1:
                base_fmt = parts[0]
                timezone_spec = parts[1]
            elif ':utc' in fmt.lower():
                timezone_spec = 'utc'
                base_fmt = re.split(r'[:]', fmt, maxsplit=1)[0]
            elif ':local' in fmt.lower():
                timezone_spec = 'local'
                base_fmt = re.split(r'[:]', fmt, maxsplit=1)[0]

            target_dt = dt
            if timezone_spec:
                target_dt = apply_timezone_offset(dt, timezone_spec)

            fmt_map = {
                'yyyyMMddHHmmss': target_dt.strftime('%Y%m%d%H%M%S'),
                'yyyyMMddHHmm': target_dt.strftime('%Y%m%d%H%M'),
                'yyyyMMdd': target_dt.strftime('%Y%m%d'),
                'HHmmss': target_dt.strftime('%H%M%S'),
                'HHmm': target_dt.strftime('%H%M'),
                'yyyy-MM-dd': target_dt.strftime('%Y-%m-%d'),
                'yyyy-MM-ddTHH:mm:ss': target_dt.strftime('%Y-%m-%dT%H:%M:%S'),
                'yyyy-MM-dd HH:mm:ss': target_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'yyyy': target_dt.strftime('%Y'),
                'yy': target_dt.strftime('%y'),
                'MM': target_dt.strftime('%m'),
                'dd': target_dt.strftime('%d'),
                'HH': target_dt.strftime('%H'),
                'mm': target_dt.strftime('%M'),
                'ss': target_dt.strftime('%S'),
                'unix': str(int(target_dt.timestamp())),
                'unix_ms': str(int(target_dt.timestamp() * 1000)),
                '10': str(int(target_dt.timestamp())),
                '13': str(int(target_dt.timestamp() * 1000)),
            }
            if base_fmt in fmt_map:
                result = fmt_map[base_fmt]
            else:
                try:
                    py_fmt = base_fmt
                    py_fmt = py_fmt.replace('yyyy', '%Y')
                    py_fmt = py_fmt.replace('yy', '%y')
                    py_fmt = py_fmt.replace('MM', '%m')
                    py_fmt = py_fmt.replace('dd', '%d')
                    py_fmt = py_fmt.replace('HH', '%H')
                    py_fmt = py_fmt.replace('mm', '%M')
                    py_fmt = py_fmt.replace('ss', '%S')
                    result = target_dt.strftime(py_fmt)
                except Exception:
                    logger.debug("build_catchup_url: 自定义格式解析失败，使用默认格式")
                    result = target_dt.strftime('%Y%m%d%H%M%S')
            return result

        def replace_braced_vars(url, dt, prefix):
            for m in re.finditer(r'\$\{\(' + re.escape(prefix) + r'\)([^}]+)\}', url):
                fmt = m.group(1)
                replacement = format_time(dt, fmt)
                url = url.replace(m.group(0), replacement)
            return url

        url = replace_braced_vars(url, start_time, 'b')
        url = replace_braced_vars(url, end_time, 'e')
        url = replace_braced_vars(url, start_time, 'start')
        url = replace_braced_vars(url, end_time, 'end')

        start_ts = str(int(start_time.timestamp()))
        end_ts = str(int(end_time.timestamp()))
        start_ts_ms = str(int(start_time.timestamp() * 1000))
        end_ts_ms = str(int(end_time.timestamp() * 1000))
        duration_sec = int((end_time - start_time).total_seconds())

        replacements = {
            '${start}': start_ts, '${end}': end_ts,
            '${timestamp}': start_ts, '${start_utc}': start_ts, '${end_utc}': end_ts,
            '${start_ms}': start_ts_ms, '${end_ms}': end_ts_ms,
            '${offset}': start_ts,
            '${duration}': str(duration_sec),
            '${duration_ms}': str(duration_sec * 1000),
            '{start}': start_ts, '{end}': end_ts,
            '{timestamp}': start_ts, '{offset}': start_ts,
        }
        for placeholder, value in replacements.items():
            url = url.replace(placeholder, value)

        date_fields = [
            ('${start_year}', '%Y'), ('${start_month}', '%m'), ('${start_day}', '%d'),
            ('${start_hour}', '%H'), ('${start_minute}', '%M'), ('${start_second}', '%S'),
            ('${end_year}', '%Y'), ('${end_month}', '%m'), ('${end_day}', '%d'),
            ('${end_hour}', '%H'), ('${end_minute}', '%M'), ('${end_second}', '%S'),
        ]
        for placeholder, fmt in date_fields:
            url = url.replace(placeholder, (start_time if 'start' in placeholder else end_time).strftime(fmt))

        return url

    def build_catchup_url(self, channel: dict, start_time: datetime, end_time: datetime) -> str:

        catchup_type = (channel.get('catchup', '') or '').lower().strip()
        catchup_source = channel.get('catchup_source', '')
        catchup_correction = channel.get('catchup_correction', '')
        live_url = channel.get('url', '')

        # Fallback：catchup 字段为空时，即时从 URL 检测可回看模式（PLTV/TVOD、SNM/TVOD）
        # 避免依赖 M3U 重新解析；用户手动添加的单播频道也能自动支持回看
        if not catchup_type and not catchup_source and live_url:
            try:
                from services.m3u_parser import detect_catchup_pattern
                detected = detect_catchup_pattern(live_url)
                if detected:
                    catchup_type, catchup_source = detected
                    logger.debug(f"build_catchup_url: 自动检测回看模式 type={catchup_type}, url={live_url}")
            except Exception as e:
                logger.debug(f"build_catchup_url: 自动检测回看模式失败: {e}")

        logger.debug(f"build_catchup_url: type={catchup_type}, correction={catchup_correction}, "
                     f"start={start_time}, end={end_time}, "
                     f"start_ts={int(start_time.timestamp())}, end_ts={int(end_time.timestamp())}")

        if catchup_correction:
            try:
                offset = float(catchup_correction)
                tz_offset = timezone(timedelta(hours=offset))
                local_tz = start_time.astimezone().tzinfo if start_time.tzinfo else datetime.now().astimezone().tzinfo
                start_time = start_time.replace(tzinfo=local_tz).astimezone(tz_offset).replace(tzinfo=None)
                end_time = end_time.replace(tzinfo=local_tz).astimezone(tz_offset).replace(tzinfo=None)
            except (ValueError, TypeError):
                pass

        if catchup_source:
            catchup_url = self.replace_catchup_variables(catchup_source, start_time, end_time)
        else:
            catchup_url = ''

        if catchup_type == 'append':
            if catchup_url:
                if catchup_url.startswith('?') or catchup_url.startswith('&'):
                    return live_url + catchup_url
                sep = '&' if '?' in live_url else '?'
                return live_url + sep + catchup_url
            return live_url

        elif catchup_type in ('flussonic', 'fs'):
            if catchup_url:
                return catchup_url
            ts_start = int(start_time.timestamp())
            ts_end = int(end_time.timestamp())
            return f"{live_url}/{ts_start}-{ts_end}.m3u8"

        elif catchup_type in ('xc', 'xtream'):
            if catchup_url:
                return catchup_url
            ts_start = int(start_time.timestamp())
            ts_end = int(end_time.timestamp())
            duration = int((end_time - start_time).total_seconds())
            sep = '&' if '?' in live_url else '?'
            return f"{live_url}{sep}start={ts_start}&end={ts_end}&duration={duration}"

        elif catchup_type == 'shift':
            if catchup_url:
                return catchup_url
            offset = int((datetime.now() - start_time).total_seconds())
            sep = '&' if '?' in live_url else '?'
            return f"{live_url}{sep}timeshift={offset}"

        elif catchup_type == 'pltv':
            if catchup_url:
                return catchup_url
            pltv_url = re.sub(r'/PLTV/', '/TVOD/', live_url, count=1, flags=re.IGNORECASE)
            start_str = start_time.strftime('%Y%m%d%H%M%S')
            end_str = end_time.strftime('%Y%m%d%H%M%S')
            sep = '&' if '?' in pltv_url else '?'
            return f"{pltv_url}{sep}playseek={start_str}-{end_str}"

        elif catchup_type in ('default', 'vod', 'timemachine', ''):
            return catchup_url if catchup_url else live_url

        return catchup_url if catchup_url else live_url

    def start_catchup(self, program):

        if not self.window.current_channel:
            return

        channel_name = self.window.current_channel.get("name", "")
        tr = getattr(self.window.language_manager, 'tr', lambda x, y: x)

        start_str = program.get('start', '')
        end_str = program.get('end', '')
        if not start_str or not end_str:
            logger.warning(f"回看节目缺少时间信息: start={start_str!r}, end={end_str!r}")
            return
        try:
            start_time = datetime.fromisoformat(start_str)
            end_time = datetime.fromisoformat(end_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"回看节目时间格式无效: {e}")
            return
        title = program.get('title', tr("unknown_program", "Unknown Program"))

        catchup_url = self.build_catchup_url(self.window.current_channel, start_time, end_time)
        logger.debug(f"构建回看URL: {catchup_url}")

        if not catchup_url or not catchup_url.strip():
            logger.warning(f"回看URL构建失败: channel={channel_name}, catchup_source={self.window.current_channel.get('catchup_source', '')!r}")
            no_support_msg = tr('catchup_not_supported', '该频道不支持回看')
            self.window.status_bar_show_message(no_support_msg)
            return

        catchup_template = tr('catchup_playing', '正在回看: {name}')
        self.window.status_bar_show_message(f"{catchup_template.format(name=channel_name)} - {title}")

        if self.window.player_controller:
            self._enter_catchup_state(self.window.current_channel, {
                'start': start_time, 'end': end_time,
                'title': title, 'desc': program.get('desc', '')
            }, mode=PlayMode.CATCHUP)

            if hasattr(self.window, '_cancel_source_timeout'):
                self.window._cancel_source_timeout()

            if hasattr(self.window, 'video_placeholder') and self.window.video_placeholder:
                self.window.video_placeholder.hide()
            if hasattr(self.window, 'video_widget') and self.window.video_widget and self.window.video_frame:
                self.window.video_widget.setGeometry(0, 0, self.window.video_frame.width(), self.window.video_frame.height())
            if hasattr(self.window, 'floating_panel') and self.window.floating_panel:
                self.window.floating_panel.raise_()

            for attr in ['_catchup_start_time', '_catchup_start_progress',
                         '_target_catchup_progress', '_disable_progress_auto_update']:
                if hasattr(self.window, attr):
                    setattr(self.window, attr, None if 'time' in attr or 'progress' in attr else False)
            # 新回看URL从节目起点开播，time-pos换算偏移归零
            self.window._catchup_time_pos_offset = 0.0

            if hasattr(self.window, 'program_progress'):
                self._set_progress_value(0)

            if getattr(self.window, 'speed_button', None) is not None and self.window.player_controller:
                current_speed = self.window.player_controller.get_speed()
                if abs(current_speed - 1.0) > 0.01:
                    self.window.player_controller.set_speed(1.0)
                    self.window.speed_button.setText("1.0x")

            self._fcc_leave()
            self.window.player_controller.play(catchup_url, f"{channel_name} - {title} ({self.window.language_manager.tr('catchup_osd', '回看')})")
            self.add_exit_catchup_button()
            if hasattr(self.window, 'media_ctrl'):
                self.window.media_ctrl.update_catchup_indicator()
            if hasattr(self.window, '_populate_epg_list'):
                self.window._populate_epg_list()

    def add_exit_catchup_button(self):

        try:
            tr = getattr(self.window.language_manager, 'tr', lambda x, y: x)
            # 退出项已收入“更多”菜单，通过统一入口同步可见性与文案
            self.window._set_exit_catchup_visible(True, tr("exit_catchup", "退出回看"))
            logger.debug("退出回看菜单项已显示")
        except Exception as e:
            logger.error(f"显示退出回看按钮失败: {e}")

    def exit_catchup(self):


        saved_original_channel = self.original_channel or self.window.current_channel

        if hasattr(self.window, 'playback_ctrl'):
            self.window.playback_ctrl._exit_catchup_mode()

        self.window.current_epg_date = datetime.now().date()
        if hasattr(self.window, 'epg_ctrl'):
            self.window.epg_ctrl.update_epg_date_display()

        if hasattr(self.window, '_populate_epg_list'):
            self.window._populate_epg_list()

        if saved_original_channel:
            tr = self.window.language_manager.tr
            channel_name = saved_original_channel.get("name", tr("unknown_channel", "Unknown Channel"))
            self.window.status_bar_show_message(f"{tr('back_to_live', 'Back to live')}: {channel_name}")
            self.window.current_channel = saved_original_channel
            self.window.play_channel(saved_original_channel)
            if hasattr(self.window, 'update_channel_info_on_selection'):
                self.window.update_channel_info_on_selection()

        # 退出回看后已切回直播，不能清成空闲态，否则播放中按暂停会禁用整排控制按钮
        self._clear_catchup_state(set_state='live')

    def show_exit_timeshift_button(self):

        try:
            tr = getattr(self.window.language_manager, 'tr', lambda x, y: x)
            # 退出项已收入“更多”菜单，通过统一入口同步可见性与文案
            self.window._set_exit_catchup_visible(True, tr("exit_timeshift", "退出时移"))
            logger.debug("退出时移菜单项已显示")
        except Exception as e:
            logger.error(f"显示退出时移按钮失败: {e}")

    def exit_timeshift(self):

        saved_original = self.original_channel or self.window.current_channel

        if hasattr(self.window, 'playback_ctrl'):
            self.window.playback_ctrl._exit_catchup_mode()

        if hasattr(self.window, 'program_progress') and self.window.program_progress:
            self._set_progress_range(3600)
            self._set_progress_value(0)

        channel_name = self.window.current_channel.get("name", "") if self.window.current_channel else ""
        tr = getattr(self.window.language_manager, 'tr', lambda x, y: x)
        self.window.status_bar_show_message(f"{tr('back_to_live', 'Back to live')}: {channel_name}")

        if saved_original and hasattr(self.window, 'play_channel'):
            self.window.current_channel = saved_original
            self.window.play_channel(saved_original)
            if hasattr(self.window, 'update_channel_info_on_selection'):
                self.window.update_channel_info_on_selection()
        elif self.window.player_controller and self.window.current_channel:
            url = self.window.current_channel.get('url', '')
            if url:
                self._fcc_switch(url)
                self.window.player_controller.play(url, channel_name)

        # 退出时移后已切回直播，保持直播态而非空闲态
        self._clear_catchup_state(set_state='live')

    def _set_progress_value(self, seconds):
        if hasattr(self.window, '_set_progress_value'):
            self.window._set_progress_value(seconds)

    def _set_progress_range(self, total):
        if hasattr(self.window, '_set_progress_range'):
            self.window._set_progress_range(total)

    def seek_catchup(self, position: float):
        w = self.window

        import time as _time

        if self.catchup_program is None or self.original_channel is None:
            logger.error("回看模式但缺少必要信息")
            w.status_bar.showMessage(w.language_manager.tr("catchup_error", "Catchup error: Missing information"))
            return

        try:

            if self._try_mpv_seek(position):
                return

            now_time = _time.time()
            if self._url_rebuild_pending:
                elapsed_since_rebuild = now_time - self._last_url_rebuild_time
                if elapsed_since_rebuild < self.URL_REBUILD_COOLDOWN:
                    self._pending_seek_after_cooldown = position
                    logger.info(f"时移seek延迟: URL重建后冷却中({elapsed_since_rebuild:.1f}s/{self.URL_REBUILD_COOLDOWN}s)")
                    self._ensure_cooldown_timer()
                    return
                else:
                    self._url_rebuild_pending = False

            channel_name = self.original_channel.get("name", w.language_manager.tr("unknown_channel", "Unknown Channel"))
            title = self.catchup_program.get('title', w.language_manager.tr('unknown_program', 'Unknown Program'))

            catchup_source = self.original_channel.get('catchup_source', '')
            catchup_type = (self.original_channel.get('catchup', '') or '').lower().strip()

            # Fallback：catchup 字段为空时，即时从 URL 检测可回看模式
            if not catchup_source and not catchup_type:
                try:
                    from services.m3u_parser import detect_catchup_pattern
                    detected = detect_catchup_pattern(self.original_channel.get('url', ''))
                    if detected:
                        catchup_type, catchup_source = detected
                except Exception as e:
                    logger.debug(f"catchup 类型检测失败: {e}")

            if not catchup_source and not catchup_type:
                w.status_bar_show_message(w.language_manager.tr("catchup_not_supported", "This channel does not support catchup"))
                return

            start_time = self.catchup_program['start']
            end_time = self.catchup_program['end']

            new_start_time = start_time + timedelta(seconds=position)
            now = datetime.now()

            is_timeshift = w.play_state.is_timeshift

            if is_timeshift:
                # 时移 URL 的 end 必须跟随直播边缘（now）。如果沿用进入时移时
                # 冻结的 end，向后拖动生成的 URL 窗口会提前结束，流立刻 EOF，
                # 进度条也会停在冻结点不再前进。
                end_time = max(self.catchup_program['end'], now)

            if new_start_time >= end_time:
                ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
                current_program = w.epg_parser.get_current_program(ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
                if current_program:
                    new_program_start = datetime.fromisoformat(current_program.get('start', ''))
                    new_program_end = datetime.fromisoformat(current_program.get('end', ''))
                    if new_start_time >= new_program_start and new_start_time < new_program_end:
                        start_time = new_program_start
                        end_time = new_program_end
                        self.catchup_program = {
                            'start': start_time, 'end': end_time,
                            'title': current_program.get('title', title),
                            'desc': current_program.get('desc', ''),
                        }
                        w._progress_program_start = start_time
                        w._progress_program_end = end_time
                        total_duration = int((end_time - start_time).total_seconds())
                        if total_duration > 0:
                            self._set_progress_range(total_duration)
                        position = (new_start_time - start_time).total_seconds()
                        new_start_time = start_time + timedelta(seconds=position)
                        logger.info(f"时移跨节目 -> 新节目 {start_time}~{end_time}, position={position:.0f}s")

            new_end_time = end_time
            if new_start_time >= new_end_time:
                new_start_time = min(new_start_time, now - timedelta(seconds=5))
                new_end_time = max(new_end_time, now)
                logger.info(f"时移超范围 -> 限制到 {new_start_time}~{new_end_time}")

            if new_end_time - new_start_time < timedelta(seconds=30):
                new_end_time = new_start_time + timedelta(minutes=30)
                logger.info(f"时移窗口过短 -> 扩展endTime到 {new_end_time}")

            catchup_url = self.build_catchup_url(self.original_channel, new_start_time, new_end_time)

            logger.info(f"时移重新构建URL -> new_start={new_start_time}, end={new_end_time}, url={catchup_url}")

            catchup_msg = w.language_manager.tr('catchup_playing', '正在回看: {name}')
            w.status_bar.showMessage(f"{catchup_msg.format(name=channel_name)} - {title}")

            w._pending_catchup_progress = position

            self._last_url_rebuild_time = _time.time()
            self._url_rebuild_pending = True

            if self._cooldown_timer is not None:
                try:
                    self._cooldown_timer.stop()
                except Exception as e:
                    logger.debug(f"停止冷却计时器失败: {e}")
                self._cooldown_timer = None
            w._catchup_start_time = _time.time()
            w._catchup_start_progress = position
            # 新URL从节目内 position 处开播，mpv time-pos 从 0 重新计数，
            # 偏移 = 节目起点 - URL起点 = -position，使 raw = time-pos + position
            # 才是节目内真实位置，否则进度条会跳回节目开头
            w._catchup_time_pos_offset = -float(position)

            if hasattr(w, 'player_controller') and w.player_controller:
                self._fcc_leave()
                w.player_controller.play(catchup_url, f"{channel_name} - {title} ({w.language_manager.tr('catchup_osd', '回看')})")
        except Exception as e:

            logger.error(f"重新构建回看 URL 失败：{e}")
            w.status_bar.showMessage(w.language_manager.tr("catchup_seek_error", "Catchup seek failed"))

    def _try_mpv_seek(self, position):
        w = self.window

        if not hasattr(w, 'player_controller') or not w.player_controller:
            return False
        # 暂停时 mpv 依然支持在缓冲区里 seek；此前只判断 is_playing，
        # 暂停状态拖动进度条会误走 URL 重建（重新拉流、丢失精确位置）
        if not (w.player_controller.is_playing
                or getattr(w.player_controller, 'is_paused', False)):
            return False

        catchup_start_progress = getattr(w, '_catchup_start_progress', None)
        if catchup_start_progress is None:
            return False

        # 流内绝对位置 = 节目内位置 + 偏移（offset = 节目起点 - URL起点）。
        # 不能用 _catchup_start_progress 计算：它已被进度tick持续同步为
        # "当前"节目位置，用它算出的是相对距离，当绝对位置用会跳错位置
        target_mpv_pos = position + getattr(w, '_catchup_time_pos_offset', 0.0)
        if target_mpv_pos < 0:
            return False

        seek_range = w.player_controller.get_available_seek_range()
        buffer_start = seek_range.get('buffer_start', 0)
        buffer_end = seek_range.get('buffer_end', 0)
        time_pos = seek_range.get('time_pos', 0)
        cache_duration = seek_range.get('cache_duration', 0)

        if cache_duration >= 2 or buffer_end > buffer_start + 1:
            if self._url_rebuild_pending:
                self._url_rebuild_pending = False
                logger.debug(f"缓冲区就绪，清除URL重建pending标记 (cache={cache_duration:.1f}s, buffer={buffer_start:.1f}s~{buffer_end:.1f}s)")

        if cache_duration < 2 and buffer_end <= buffer_start:
            return False

        if target_mpv_pos < buffer_start:
            logger.info(f"回看seek超出缓冲区前部: target_mpv={target_mpv_pos:.1f}s < buffer_start={buffer_start:.1f}s, 需重建URL")
            return False

        if target_mpv_pos > buffer_end + 5:
            logger.info(f"回看seek超出缓冲区后部: target_mpv={target_mpv_pos:.1f}s > buffer_end={buffer_end:.1f}s, 需重建URL")
            return False

        target_mpv_pos = max(buffer_start, min(target_mpv_pos, buffer_end))

        if abs(target_mpv_pos - time_pos) < 0.5:
            logger.debug(f"回看seek跳过: target_mpv={target_mpv_pos:.1f}s 与当前位置{time_pos:.1f}s差<0.5s")
            return True

        logger.info(f"回看MPV seek: position={position:.1f}s -> target_mpv={target_mpv_pos:.1f}s "
                    f"(start_progress={catchup_start_progress:.1f}s, time_pos={time_pos:.1f}s)")

        w.player_controller.seek_absolute(target_mpv_pos)

        import time as _time
        w._catchup_start_time = _time.time()
        w._catchup_start_progress = position

        return True

    def _ensure_cooldown_timer(self):
        if self._cooldown_timer is not None:
            return
        import time as _time
        remaining_ms = max(200, int((self.URL_REBUILD_COOLDOWN - (_time.time() - self._last_url_rebuild_time)) * 1000))
        self._cooldown_timer = QTimer(self.window)
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._execute_pending_seek)
        self._cooldown_timer.start(remaining_ms)

    def _execute_pending_seek(self):
        self._cooldown_timer = None
        position = self._pending_seek_after_cooldown
        self._pending_seek_after_cooldown = None
        if position is not None:
            import time as _time
            elapsed = _time.time() - self._last_url_rebuild_time
            if elapsed < self.URL_REBUILD_COOLDOWN:
                self._ensure_cooldown_timer()
                return
            logger.info(f"冷却期结束，执行延迟的时移seek: position={position:.1f}s")
            self.seek_catchup(position)

    def rollover_catchup_program(self, raw_seconds: float) -> bool:
        """回看墙钟进度越过当前节目末尾时，把记账状态滚动到下一节目。

        回看URL按节目起点开播后服务器通常连续发流，越过节目边界无需重载流，
        只需把 catchup_program/进度条/EPG"正在回看"标记滚动到下一节目，
        避免进度条顶满、EPG 仍高亮上一节目。倍速保持不变。
        返回 True 表示已滚动到下一节目。
        """
        w = self.window
        if not self.catchup_program or not self.original_channel:
            return False
        program_start = self.catchup_program.get('start')
        program_end = self.catchup_program.get('end')
        if not isinstance(program_start, datetime) or not isinstance(program_end, datetime):
            return False

        now = datetime.now()
        if program_end > now:
            return False  # 节目尚未播完（贴近直播边缘），不滚动

        next_program = None
        try:
            ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
            epg_list = w.epg_parser.get_channel_epg(ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
            for prog in epg_list or []:
                try:
                    if datetime.fromisoformat(prog.get('start', '')) >= program_end:
                        next_program = prog
                        break
                except (ValueError, KeyError):
                    continue
        except Exception as ex:
            logger.debug(f"回看滚动查找下一节目失败: {ex}")
        if not next_program:
            return False
        try:
            next_start = datetime.fromisoformat(next_program['start'])
            next_end = datetime.fromisoformat(next_program['end'])
        except (ValueError, KeyError):
            return False
        if next_start >= now:
            return False  # 下一节目尚未开播，墙钟位置不可能超前直播

        # 流墙钟位置 = program_start + raw_seconds，换算为下一节目内的偏移
        pos_in_next = (program_start + timedelta(seconds=raw_seconds) - next_start).total_seconds()
        pos_in_next = max(0.0, min(pos_in_next,
                                   (next_end - next_start).total_seconds(),
                                   (now - next_start).total_seconds()))

        import time as _time
        self.catchup_program = {
            'start': next_start, 'end': next_end,
            'title': next_program.get('title', ''),
            'desc': next_program.get('desc', ''),
        }
        w._catchup_start_time = _time.time()
        w._catchup_start_progress = pos_in_next
        # time-pos 从URL起点连续计数（滚动不重载流），累计节目起点偏移
        # 使进度换算保持为当前节目内的位置
        w._catchup_time_pos_offset = getattr(w, '_catchup_time_pos_offset', 0.0) \
            + (next_start - program_start).total_seconds()
        w._progress_time_mode = 'epg'
        w._progress_program_start = next_start
        w._progress_program_end = next_end
        total_duration = int((next_end - next_start).total_seconds())
        if total_duration > 0:
            self._set_progress_range(total_duration)
        self._set_progress_value(pos_in_next)

        catchup_template = w.language_manager.tr('catchup_playing', '正在回看: {name}')
        w.status_bar_show_message(
            f"{catchup_template.format(name=self.original_channel.get('name', ''))} - {self.catchup_program.get('title', '')}"
        )

        try:
            # EPG键未变时走 _refresh_badges_only，仅刷新"正在回看"标记
            if hasattr(w, '_populate_epg_list'):
                w._populate_epg_list()
            elif hasattr(w, 'populate_epg_list'):
                w.populate_epg_list()
        except Exception as ex:
            logger.debug(f"回看滚动刷新EPG标记失败: {ex}")

        logger.info(
            f"回看滚动到下一节目 {next_start.strftime('%H:%M')}~{next_end.strftime('%H:%M')} "
            f"title={self.catchup_program.get('title', '')}，节目内进度 {pos_in_next:.0f}s，倍速保持"
        )
        return True

    def continue_timeshift(self):
        """时移流播放到终点后自动续播：优先切换到下一个节目，无下一节目则从当前位置续播"""
        w = self.window


        if not self.catchup_program or not self.original_channel:
            logger.warning("时移续播失败: 缺少节目信息")
            return

        program_start = self.catchup_program['start']
        program_end = self.catchup_program['end']
        now = datetime.now()
        channel_name = self.original_channel.get('name', '')

        # 时移进度会持续把节目结束时间推进到"现在"。EOF 时若已贴近直播边缘，
        # 再拼回看 URL 只会得到起止时间都在未来的窗口，直接回直播。
        if program_end >= now - timedelta(seconds=self.LIVE_EDGE_TOLERANCE_SECONDS):
            logger.info(f"时移/回看已追到直播边缘，切回直播: {channel_name}")
            live_channel = self.original_channel
            self._clear_catchup_state(set_state='live')
            w._pending_catchup_progress = None
            w.current_channel = live_channel
            if hasattr(w, 'play_channel'):
                w.play_channel(live_channel)
            elif w.player_controller and live_channel.get('url'):
                self._fcc_switch(live_channel.get('url', ''))
                w.player_controller.play(live_channel.get('url', ''), channel_name)
            return

        next_program = None
        try:
            ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
            epg_list = w.epg_parser.get_channel_epg(ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
            for prog in epg_list:
                try:
                    prog_start = datetime.fromisoformat(prog.get('start', ''))
                    if prog_start >= program_end:
                        next_program = prog
                        break
                except (ValueError, KeyError):
                    continue
        except Exception as ex:
            logger.warning(f"获取下一节目失败: {ex}")

        # 尚未开播的节目不能作为回看窗口（起止时间会落在未来），退回当前节目续播
        if next_program:
            try:
                if datetime.fromisoformat(next_program['start']) >= now:
                    logger.info("下一节目尚未开播，改用当前节目位置续播")
                    next_program = None
            except (ValueError, KeyError):
                next_program = None

        if next_program:
            next_start = datetime.fromisoformat(next_program['start'])
            next_end = datetime.fromisoformat(next_program['end'])
            # 无论下一节目是否已播完，都从其开头续播（连播体验）；
            # 原先"已播完则从结尾前5秒续播"会跳过下一节目内容
            play_start = next_start
            start_offset = 0.0
            end_time = next_end if next_end > now else now + timedelta(minutes=30)
            catchup_url = self.build_catchup_url(self.original_channel, play_start, end_time)
            self.catchup_program = {
                'start': next_start, 'end': next_end,
                'title': next_program.get('title', ''),
                'desc': next_program.get('desc', ''),
            }
            w._progress_program_start = next_start
            w._progress_program_end = next_end
            total_duration = int((next_end - next_start).total_seconds())
            if total_duration > 0:
                self._set_progress_range(total_duration)
            w._progress_time_mode = 'epg'
            logger.info(f"时移续播 -> 下一节目 {next_start}~{next_end}, title={next_program.get('title', '')}")
        else:
            elapsed_since_start = getattr(w, '_catchup_start_progress', None)
            if elapsed_since_start is not None and hasattr(w, '_catchup_start_time'):
                import time as _time
                elapsed_real = _time.time() - w._catchup_start_time
                new_start_time = program_start + timedelta(seconds=elapsed_since_start + elapsed_real)
            else:
                new_start_time = now - timedelta(seconds=5)

            if new_start_time >= now:
                new_start_time = now - timedelta(seconds=5)
            if new_start_time < program_start:
                new_start_time = program_start

            end_time = program_end if program_end > now else now + timedelta(minutes=30)
            catchup_url = self.build_catchup_url(self.original_channel, new_start_time, end_time)
            logger.info(f"时移续播(同节目) -> new_start={new_start_time}, end={end_time}")
            # 新URL从节目内 new_start_time 处开播，记账偏移 = new_start_time - 节目起点
            start_offset = max(0.0, (new_start_time - program_start).total_seconds())

        w._pending_catchup_progress = start_offset
        import time as _time
        self._last_url_rebuild_time = _time.time()
        self._url_rebuild_pending = True
        w._catchup_start_time = _time.time()
        w._catchup_start_progress = start_offset
        # 新URL从节目内 start_offset 处开播，mpv time-pos 从 0 重新计数
        w._catchup_time_pos_offset = -float(start_offset)

        if hasattr(w, 'player_controller') and w.player_controller:
            self._fcc_leave()
            w.player_controller.play(catchup_url, f"{channel_name} ({w.language_manager.tr('timeshift_resume', '时移续播')})")

    def start_live_timeshift_from_progress(self, slider_seconds, catchup_source, has_epg=True):
        w = self.window


        now = datetime.now()

        if has_epg and w._progress_program_start:
            program_start = w._progress_program_start
            program_end = w._progress_program_end
            target_wallclock = program_start + timedelta(seconds=slider_seconds)
        else:
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            target_wallclock = hour_start + timedelta(seconds=slider_seconds)
            program_start = hour_start
            program_end = None

        if target_wallclock >= now:
            target_wallclock = now - timedelta(seconds=5)

        if target_wallclock < program_start:
            target_wallclock = program_start

        end_time = now

        if not w.current_channel:
            return

        timeshift_url = self.build_catchup_url(w.current_channel, target_wallclock, end_time)

        channel_name = w.current_channel.get('name', '')
        program_title = ''
        try:
            ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
            prog = w.epg_parser.get_current_program(ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
            if prog:
                program_title = prog.get('title', '')
        except Exception as e:
            logger.debug(f"EPG获取节目标题失败: {e}")

        offset_from_start = int((target_wallclock - program_start).total_seconds())
        m, s = divmod(offset_from_start, 60)
        h, m = divmod(m, 60)
        offset_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        logger.info(f"直播时移(进度条) -> 从 {target_wallclock} 开始播放，offset={offset_str}, url={timeshift_url}")

        tr = w.language_manager.tr
        w.status_bar_show_message(
            f"{tr('timeshift_playing', '正在时移')}: {channel_name}"
            + (f" - {program_title}" if program_title else "")
            + f"  [{offset_str}]"
        )

        if hasattr(w, '_cancel_source_timeout'):
            w._cancel_source_timeout()

        if hasattr(w, 'video_placeholder') and w.video_placeholder:
            w.video_placeholder.hide()
        if hasattr(w, 'video_widget') and w.video_widget and w.video_frame:
            w.video_widget.setGeometry(0, 0, w.video_frame.width(), w.video_frame.height())
        if hasattr(w, 'floating_panel') and w.floating_panel:
            if not w.floating_panel.isVisible():
                w.floating_panel.show()

        for attr in ['_target_catchup_progress', '_disable_progress_auto_update']:
            if hasattr(w, attr):
                setattr(w, attr, False)

        offset_seconds = int((target_wallclock - program_start).total_seconds())
        import time as _time
        self._last_url_rebuild_time = _time.time()
        self._url_rebuild_pending = True
        self._pending_seek_after_cooldown = None
        if self._cooldown_timer is not None:
            try:
                self._cooldown_timer.stop()
            except Exception:
                logger.debug("自动检测回看模式失败，将使用默认方式")
            self._cooldown_timer = None
        w._catchup_start_time = _time.time()
        w._catchup_start_progress = offset_seconds
        # 时移 URL 从 target_wallclock 开始拉流，mpv 的 time-pos 从 0 重新计数。
        # 节目内真实位置 = time-pos + offset_seconds，而进度代码计算的是
        # raw = time-pos - _catchup_time_pos_offset，因此偏移必须是 -offset_seconds。
        # 之前写死为 0 会让进度条立刻跳回节目开头，seek 也会算错目标位置。
        w._catchup_time_pos_offset = -float(offset_seconds)

        w._timeshift_start_time = target_wallclock
        w.play_state.set_timeshift()
        w._live_timeshift_seconds = max(0, (datetime.now() - target_wallclock).total_seconds())
        self.original_channel = w.current_channel.copy()
        self.catchup_program = {
            'start': program_start,
            'end': end_time,
            'title': program_title or tr('timeshift_label', '时移'),
            'desc': '',
        }

        total_duration = int((end_time - program_start).total_seconds())
        if total_duration > 0:
            self._set_progress_range(total_duration)
            w._pending_catchup_progress = offset_seconds
            self._set_progress_value(offset_seconds)
            w._progress_time_mode = 'epg'
            w._progress_program_start = program_start
            w._progress_program_end = end_time

        if w.player_controller:
            self._fcc_leave()
            w.player_controller.play(timeshift_url, f"{channel_name} ({w.language_manager.tr('timeshift_label', '时移')} {offset_str})")
        w._show_exit_timeshift_button()
        w.media_ctrl.update_catchup_indicator()
        w._populate_epg_list()
