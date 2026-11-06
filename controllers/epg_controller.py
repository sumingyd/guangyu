"""
EPG节目单控制器 - 负责EPG数据管理、显示、交互
从 pyqt_player.py 提取的独立模块
"""

from datetime import datetime, timedelta, date
from PySide6.QtWidgets import QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtGui import QPainter, QFontMetrics, QFont, QCursor
from PySide6.QtCore import Qt, QTimer, QRect

from core.log_manager import global_logger as logger
from controllers.main_window_protocol import EpgProtocol
from utils.thread_safety import safe_single_shot


class EPGItemDelegate(QStyledItemDelegate):
    @staticmethod
    def _get_status_colors():
        from ui.styles import AppStyles, color_to_qcolor
        colors = AppStyles._get_colors()
        past_bg = color_to_qcolor(colors.get('mid', '#999999'))
        past_bg.setAlpha(160)
        past_text = color_to_qcolor(colors.get('window_text', '#cccccc'))
        past_text.setAlpha(200)
        return {
            'live': (color_to_qcolor(colors.get('error', '#f44336')), color_to_qcolor(colors.get('bright_text', '#ffffff'))),
            'past': (past_bg, past_text),
            'catchup': (color_to_qcolor(colors.get('accent', '#4a7eff')), color_to_qcolor(colors.get('bright_text', '#ffffff'))),
        }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if not data:
            super().paint(painter, option, index)
            return

        left_badges = []
        if data.get('is_live'):
            left_badges.append(('LIVE', 'live'))
        elif data.get('is_past'):
            left_badges.append(('\u2022', 'past'))

        right_badge = None
        if data.get('is_catchup'):
            right_badge = (data.get('catchup_label', '\u21a9'), 'catchup')

        if not left_badges and not right_badge:
            super().paint(painter, option, index)
            return

        font = QFont(option.font)
        if font.pointSize() <= 0:
            if font.pixelSize() > 0:
                pass
            else:
                font.setPixelSize(12)
        fm = QFontMetrics(font)
        text_height = fm.height() + 4
        y = option.rect.top() + (option.rect.height() - text_height) // 2

        painter.save()

        status_colors = self._get_status_colors()
        default_colors = status_colors['past']

        left_offset = option.rect.left() + 4
        for text, status_type in left_badges:
            text_width = fm.horizontalAdvance(text) + 8
            bg_color, text_color = status_colors.get(status_type, default_colors)
            bg_rect = QRect(left_offset, y, text_width, text_height)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(bg_rect, 3, 3)

            painter.setPen(text_color)
            painter.setFont(font)
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

            left_offset += text_width + 4

        right_limit = option.rect.right() - 4
        if right_badge:
            text, status_type = right_badge
            text_width = fm.horizontalAdvance(text) + 8
            bg_color, text_color = status_colors.get(status_type, default_colors)
            bg_rect = QRect(right_limit - text_width, y, text_width, text_height)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(bg_rect, 3, 3)

            painter.setPen(text_color)
            painter.setFont(font)
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

            right_limit -= text_width + 4

        painter.restore()

        text_rect = QRect(
            left_offset, option.rect.top(),
            right_limit - left_offset, option.rect.height()
        )
        option_copy = QStyleOptionViewItem(option)
        option_copy.rect = text_rect
        super().paint(painter, option_copy, index)


class EPGController:
    """EPG节目单控制器 - 管理电子节目单的所有逻辑"""

    def __init__(self, main_window: EpgProtocol):
        self.window: EpgProtocol = main_window
        self._current_date = None
        self._last_epg_key = None

    # 无 catchup_source 也能自行生成 catchup URL 的类型
    _CATCHUP_TYPES_WITHOUT_SOURCE = frozenset(
        {'flussonic', 'fs', 'xc', 'xtream', 'shift', 'pltv'}
    )

    def _channel_supports_catchup(self, channel: dict) -> bool:
        """判断频道是否真正支持回看（比仅检查 catchup 字段非空更严格）。

        仅凭 catchup="default" 但无 catchup_source 的频道不算支持回看，
        因为 build_catchup_url 对 default 类型无 source 时返回空字符串。

        判定规则：
          1. catchup_source 非空 → 有模板 URL，支持回看
          2. catchup_source 为空但 catchup 类型可自行生成 URL → 支持
          3. URL 匹配 PLTV/SNM 模式 → 支持
          4. 其他情况（default/vod/timemachine/append/空 无 source）→ 不支持
        """
        if not channel:
            return False
        catchup_source = channel.get('catchup_source', '') or ''
        catchup_type = (channel.get('catchup', '') or '').lower().strip()
        live_url = channel.get('url', '') or ''

        # 1. 有 catchup_source 模板
        if catchup_source:
            return True
        # 2. 无 source 但类型可自行生成 URL
        if catchup_type in self._CATCHUP_TYPES_WITHOUT_SOURCE:
            return True
        # 3. URL 匹配 PLTV/SNM 模式
        if live_url:
            from services.m3u_parser import safe_detect_catchup_source
            if safe_detect_catchup_source(live_url):
                return True
        # 4. 其他情况不支持
        return False

    @property
    def tr(self):
        if hasattr(self.window, 'language_manager'):
            return self.window.language_manager.tr
        return lambda key, fallback: fallback

    def _get_active_catchup_label(self, program, is_live, is_past, channel_supports_catchup, tr):
        """确定回看/时移标签，考虑当前活跃的回看/时移状态"""
        if not channel_supports_catchup:
            return ''

        is_timeshift_mode = self.window.play_state.is_timeshift
        is_catchup_mode = self.window.play_state.is_catchup
        catchup_program = getattr(self.window, 'catchup_program', None)

        if is_timeshift_mode and is_live:
            return tr('timeshift_playing', '正在时移')

        if is_catchup_mode and catchup_program:
            prog_start = program.get('start', '')
            prog_end = program.get('end', '')
            cp_start = catchup_program.get('start', None)
            cp_end = catchup_program.get('end', None)
            if isinstance(cp_start, datetime):
                cp_start = cp_start.isoformat()
            if isinstance(cp_end, datetime):
                cp_end = cp_end.isoformat()
            if prog_start and cp_start and prog_end and cp_end:
                if prog_start == cp_start and prog_end == cp_end:
                    return tr('catchup_playing_label', '正在回看')

        if is_live:
            return tr('timeshift_available', '可时移')
        elif is_past:
            return tr('catchup_available', '可回放')

        return ''

    def _compute_epg_key(self, filtered_list, channel_name, target_date):
        if not filtered_list:
            return None
        import hashlib
        h = hashlib.sha256()
        h.update(f"{channel_name}|{target_date}".encode('utf-8'))
        for p in filtered_list:
            h.update(f"|{p.get('start','')}|{p.get('title','')}".encode('utf-8'))
        return h.hexdigest()

    def _refresh_badges_only(self, filtered_list, now, channel_supports_catchup, tr):
        epg_content = self.window.epg_content
        count = epg_content.count()
        if count != len(filtered_list):
            return False
        for i, program in enumerate(filtered_list):
            item = epg_content.item(i)
            if not item:
                return False
            start_time = program.get('start', '')
            end_time = program.get('end', '')
            start_dt = None
            end_dt = None
            try:
                if start_time:
                    start_dt = datetime.fromisoformat(start_time)
                if end_time:
                    end_dt = datetime.fromisoformat(end_time)
            except (ValueError, TypeError):
                pass

            is_past_program = False
            is_live = False
            if start_dt and end_dt:
                if now > end_dt:
                    is_past_program = True
                elif start_dt <= now <= end_dt:
                    is_live = True

            is_catchup = (is_past_program or is_live) and channel_supports_catchup
            catchup_label = self._get_active_catchup_label(
                program, is_live, is_past_program, channel_supports_catchup, tr
            )
            item.setData(Qt.ItemDataRole.UserRole, {
                'channel': (item.data(Qt.ItemDataRole.UserRole) or {}).get('channel', ''),
                'program': program,
                'status': tr("epg_status_live", "LIVE") if is_live else (tr("epg_status_finished", "") if is_past_program else ""),
                'start_dt': start_dt,
                'end_dt': end_dt,
                'is_catchup': is_catchup,
                'catchup_label': catchup_label,
                'is_live': is_live,
                'is_past': is_past_program,
            })
        epg_content.viewport().update()
        return True

    @staticmethod
    def _has_playlist_sources() -> bool:
        try:
            from core.subscription_manager import SubscriptionManager
            return bool(SubscriptionManager().get_playlist_sources())
        except Exception:
            return False

    def _show_epg_empty(self, kind: str):
        """统一 EPG 空态：按原因分文案与 CTA，且每次显式设置，避免残留上一次状态。

        kind: 'no_source' | 'no_channel' | 'no_program'
        """
        if not hasattr(self.window, 'epg_empty_label'):
            return
        label = self.window.epg_empty_label
        tr = self.tr
        if kind == 'no_source':
            label.setText(tr("epg_empty_no_source", "暂无订阅源，点击打开或导入订阅"))
            label.setToolTip(tr("tooltip_open_playlist_cta", "点击打开订阅文件"))
            label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.window.epg_empty_action = 'open_playlist'
        elif kind == 'no_channel':
            label.setText(tr("epg_empty_no_channel", "订阅源中没有频道，点击管理订阅源"))
            label.setToolTip(tr("tooltip_manage_sources_cta", "点击管理订阅源"))
            label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.window.epg_empty_action = 'manage_sources'
        else:
            label.setText(tr("epg_empty_no_program", "该频道暂无节目单"))
            label.setToolTip('')
            label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.window.epg_empty_action = None
        label.show()
        label.adjustSize()
        cw = self.window.epg_content.width()
        ch = self.window.epg_content.height()
        lw = label.width()
        lh = label.height()
        label.setGeometry((cw - lw) // 2, (ch - lh) // 2, lw, lh)
        label.raise_()

    def populate_epg_list(self):
        """填充EPG列表"""
        if not hasattr(self.window, 'epg_content'):
            logger.debug("EPG列表组件不存在，跳过填充")
            return

        self.window.epg_content.clear()

        # 重新应用样式（确保样式正确）
        try:
            from ui.styles import AppStyles
            self.window.epg_content.setStyleSheet(AppStyles.player_list_style())
        except ImportError as e:
            logger.debug(f"EPG样式导入失败: {e}")

        # 检查是否有当前频道
        if not hasattr(self.window, 'current_channel') or not self.window.current_channel:
            self._show_epg_empty(
                'no_source' if not self._has_playlist_sources() else 'no_channel'
            )
            logger.debug("无当前频道，显示空EPG提示")
            return

        # 获取当前频道信息
        channel_name = self.window.current_channel.get("name", "")
        tvg_id = self.window.current_channel.get("tvg_id", "")
        all_tags = self.window.current_channel.get("_all_tags", {})
        tvg_name = all_tags.get("tvg-name", "")

        comma_name = ''
        raw_extinf = self.window.current_channel.get('_raw_extinf', '')
        if raw_extinf and ',' in raw_extinf:
            comma_name = raw_extinf.split(',', 1)[-1].strip()
            if comma_name.startswith('"') and comma_name.endswith('"'):
                comma_name = comma_name[1:-1]

        logger.debug(f"EPG填充: 频道名称={channel_name}, tvg_id={tvg_id}, tvg_name={tvg_name}, comma_name={comma_name}")

        epg_list = []

        if hasattr(self.window, 'epg_parser') and self.window.epg_parser:
            try:
                epg_list = self.window.epg_parser.get_channel_epg(
                    channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name
                )
                if epg_list:
                    def _epg_sort_key(x):
                        try:
                            return datetime.fromisoformat(x.get('start', ''))
                        except (ValueError, TypeError):
                            return datetime.min
                    epg_list.sort(key=_epg_sort_key)
                    logger.debug(f"EPG填充: 从epg_parser获取到 {len(epg_list)} 个节目")
                else:
                    logger.debug(f"EPG填充: epg_parser未找到频道 {channel_name} 的数据")
            except Exception as e:
                logger.error(f"从epg_parser获取EPG失败: {e}")

        # 填充EPG列表
        if epg_list:
            # 按日期过滤：只显示当前选中日期的节目（默认今天）
            target_date = getattr(self.window, 'current_epg_date', None) or date.today()

            filtered_list = []
            for program in epg_list:
                start_str = program.get('start', '')
                if start_str:
                    try:
                        prog_date = datetime.fromisoformat(start_str).date()
                        if prog_date == target_date:
                            filtered_list.append(program)
                    except (ValueError, TypeError):
                        filtered_list.append(program)

            today = date.today()
            is_browsing_other_date = (target_date != today)

            if not filtered_list:
                if is_browsing_other_date:
                    logger.info(f"EPG: {target_date} 无节目数据")
                else:
                    logger.info("EPG: 今天无节目数据")
            else:
                logger.debug(f"EPG: 按日期 {target_date} 过滤，{len(epg_list)} -> {len(filtered_list)} 个节目")

            if hasattr(self.window, 'epg_empty_label') and hasattr(self.window, 'epg_content'):
                if filtered_list:
                    self.window.epg_empty_label.hide()
                else:
                    self.window.epg_content.clear()
                    self.window.epg_content.show()
                    self.window.epg_empty_label.show()
                    self.window.epg_empty_label.adjustSize()
                    cw = self.window.epg_content.width()
                    ch = self.window.epg_content.height()
                    lw = self.window.epg_empty_label.width()
                    lh = self.window.epg_empty_label.height()
                    self.window.epg_empty_label.setGeometry((cw - lw) // 2, (ch - lh) // 2, lw, lh)
                    self.window.epg_empty_label.raise_()

            tr = self.tr

            # 显示层去重：防止漏网的重复节目
            seen = set()
            deduped_list = []
            for program in filtered_list:
                key = (program.get('start', ''), program.get('title', ''))
                if key not in seen:
                    seen.add(key)
                    deduped_list.append(program)
            if len(deduped_list) < len(filtered_list):
                logger.debug(f"EPG显示层去重: {len(filtered_list)} -> {len(deduped_list)} 个节目")
            filtered_list = deduped_list

            # 获取当前时间用于判断节目状态
            now = datetime.now()

            channel_supports_catchup = self._channel_supports_catchup(
                self.window.current_channel
            ) if hasattr(self.window, 'current_channel') and self.window.current_channel else False

            new_key = self._compute_epg_key(filtered_list, channel_name, target_date)
            if new_key and new_key == self._last_epg_key:
                if self._refresh_badges_only(filtered_list, now, channel_supports_catchup, tr):
                    return
            self._last_epg_key = new_key

            for program in filtered_list:
                item = QListWidgetItem()

                start_time = program.get('start', '')
                end_time = program.get('end', '')
                title = program.get('title', '')

                # 格式化时间显示
                start_display = ''
                end_display = ''
                start_dt = None
                end_dt = None

                if start_time:
                    try:
                        start_dt = datetime.fromisoformat(start_time)
                        start_display = start_dt.strftime('%H:%M')
                    except (ValueError, TypeError):
                        start_display = start_time[:5] if len(start_time) >= 5 else start_time

                if end_time:
                    try:
                        end_dt = datetime.fromisoformat(end_time)
                        end_display = end_dt.strftime('%H:%M')
                    except (ValueError, TypeError):
                        end_display = end_time[:5] if len(end_time) >= 5 else end_time

                # 判断节目播放状态并添加状态标识
                status_text = ""
                is_past_program = False
                is_live = False
                if start_dt and end_dt:
                    if now < start_dt:
                        status_text = tr("epg_status_upcoming", "")
                    elif now > end_dt:
                        status_text = tr("epg_status_finished", "")
                        is_past_program = True
                    else:
                        status_text = tr("epg_status_live", "LIVE")
                        is_live = True

                display_text = f"{start_display}  {title}"
                item.setText(display_text)

                desc = program.get('desc', '')
                duration_min = ''
                if start_dt and end_dt:
                    dur = (end_dt - start_dt).total_seconds() / 60
                    if dur > 0:
                        duration_min = f"{int(dur)}min" if dur == int(dur) else f"{dur:.0f}min"
                tip_parts = [title]
                if duration_min:
                    tip_parts.append(f"({duration_min})")
                if desc:
                    if len(desc) > 120:
                        desc = desc[:117] + '...'
                    tip_parts.append(desc)
                item.setToolTip('\n'.join(tip_parts))

                is_catchup = (is_past_program or is_live) and channel_supports_catchup
                catchup_label = self._get_active_catchup_label(
                    program, is_live, is_past_program, channel_supports_catchup, tr
                )

                item.setData(Qt.ItemDataRole.UserRole, {
                    'channel': channel_name,
                    'program': program,
                    'status': status_text,
                    'start_dt': start_dt,
                    'end_dt': end_dt,
                    'is_catchup': is_catchup,
                    'catchup_label': catchup_label,
                    'is_live': is_live,
                    'is_past': is_past_program,
                })

                self.window.epg_content.addItem(item)

            logger.debug(f"EPG列表填充完成，共 {len(filtered_list)} 个节目")

            # 自动定位到当前正在播放的节目（使用过滤后的列表，确保索引匹配）
            self._scroll_to_current_program(filtered_list, now)
        else:
            if hasattr(self.window, 'epg_content'):
                self.window.epg_content.clear()
                self.window.epg_content.show()
            # 有频道但没有节目单：不提供跳转 CTA，避免误导去打开订阅文件
            self._show_epg_empty('no_program')
            logger.debug(f"频道 {channel_name} 无EPG数据")

    def on_epg_item_clicked(self, item: QListWidgetItem):
        """处理EPG列表项点击事件"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        program = data.get('program')
        if not program:
            return


        # 判断节目状态
        start_str = program.get('start', '')
        end_str = program.get('end', '')
        now = datetime.now()

        is_past_program = False
        if start_str and end_str:
            try:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(end_str)
                # 已结束或正在播放的节目都可以回看
                if end_dt < now or (start_dt <= now <= end_dt):
                    is_past_program = True
            except (ValueError, TypeError):
                pass

        # 检查当前频道是否支持回看功能
        channel_catchup = ''
        if hasattr(self.window, 'current_channel') and self.window.current_channel:
            channel_catchup = self.window.current_channel.get('catchup_source', '')
            if not channel_catchup:
                channel_catchup = self.window.current_channel.get('catchup', '')

        # 如果是已播放/已结束的节目且频道支持回看，启动回看
        if is_past_program and channel_catchup and hasattr(self.window, 'start_catchup'):
            logger.info(f"用户点击EPG节目 '{program.get('title')}'，启动回看")
            self.window.start_catchup(program)
        elif not channel_catchup:
            logger.debug("频道不支持回看功能（无 catchup_source 或 catchup 类型）")
            if hasattr(self.window, 'status_bar_show_message'):
                tr = self.tr
                self.window.status_bar_show_message(tr('epg_no_catchup', '该频道不支持回看'))
        elif not is_past_program:
            logger.debug("点击的是未来节目，暂不支持预约播放")
            if hasattr(self.window, 'status_bar_show_message'):
                tr = self.tr
                start_display = ''
                try:
                    start_display = datetime.fromisoformat(start_str).strftime('%H:%M')
                except Exception as e:
                    logger.debug(f"解析 EPG 开始时间失败: {e}")
                self.window.status_bar_show_message(tr('epg_upcoming', '节目尚未开始') + (f' ({start_display})' if start_display else ''))

    def update_epg_date_display(self):
        """更新EPG日期显示"""
        if not hasattr(self.window, 'current_epg_date'):
            return

        today = date.today()

        if self.window.current_epg_date:
            # 更新日期标签显示
            if hasattr(self.window, 'epg_date_label'):
                tr = self.tr
                if self.window.current_epg_date == today:
                    self.window.epg_date_label.setText(tr("today", "Today"))
                elif self.window.current_epg_date == today - timedelta(days=1):
                    self.window.epg_date_label.setText(tr("yesterday", "Yesterday"))
                elif self.window.current_epg_date == today + timedelta(days=1):
                    self.window.epg_date_label.setText(tr("tomorrow", "Tomorrow"))
                else:
                    self.window.epg_date_label.setText(self.window.current_epg_date.strftime("%Y-%m-%d"))

    def on_prev_day(self):
        """切换到前一天（最多回退7天）"""
        if not hasattr(self.window, 'current_epg_date') or not self.window.current_epg_date:
            return
        min_date = date.today() - timedelta(days=7)
        if self.window.current_epg_date <= min_date:
            if hasattr(self.window, 'status_bar_show_message'):
                tr = self.tr
                self.window.status_bar_show_message(tr('epg_date_limit', '已到最早日期'))
            return
        self.window.current_epg_date -= timedelta(days=1)
        self.update_epg_date_display()
        if hasattr(self.window, 'populate_epg_list'):
            self.window.populate_epg_list()

    def on_next_day(self):
        """切换到后一天（最多前进7天）"""
        if not hasattr(self.window, 'current_epg_date') or not self.window.current_epg_date:
            return
        max_date = date.today() + timedelta(days=7)
        if self.window.current_epg_date >= max_date:
            if hasattr(self.window, 'status_bar_show_message'):
                tr = self.tr
                self.window.status_bar_show_message(tr('epg_date_limit', '已到最远日期'))
            return
        self.window.current_epg_date += timedelta(days=1)
        self.update_epg_date_display()
        # 重新加载该日期的EPG数据
        if hasattr(self.window, 'populate_epg_list'):
            self.window.populate_epg_list()

    def _scroll_to_current_program(self, epg_list: list, now):
        """自动滚动到当前正在播放的节目（回看/时移模式下居中到回看节目）"""
        if not epg_list or not hasattr(self.window, 'epg_content'):
            return


        w = self.window

        # 回看/时移模式：优先居中到回看节目
        catchup_program = getattr(w, 'catchup_program', None)
        play_state = getattr(w, 'play_state', None)
        if catchup_program and play_state and play_state.is_catchup_or_timeshift:
            cp_start = catchup_program.get('start')
            cp_end = catchup_program.get('end')
            if cp_start and cp_end:
                for i, program in enumerate(epg_list):
                    try:
                        p_start = datetime.fromisoformat(program.get('start', ''))
                        p_end = datetime.fromisoformat(program.get('end', ''))
                        if p_start == cp_start and p_end == cp_end:
                            self._do_scroll_to_index(i, logger, "回看节目")
                            return
                    except (ValueError, TypeError):
                        continue

        # 正常直播模式：查找当前正在播放的节目
        current_index = -1
        for i, program in enumerate(epg_list):
            start_str = program.get('start', '')
            end_str = program.get('end', '')

            try:
                start_dt = datetime.fromisoformat(start_str) if start_str else None
                end_dt = datetime.fromisoformat(end_str) if end_str else None

                if start_dt and end_dt:
                    if start_dt <= now <= end_dt:
                        current_index = i
                        break
                    elif start_dt > now and current_index == -1:
                        current_index = i
                        break
            except (ValueError, TypeError):
                continue

        if current_index < 0:
            current_index = 0

        self._do_scroll_to_index(current_index, logger, "直播节目")

    def _do_scroll_to_index(self, index, logger, label=""):
        if index < 0:
            return

        def do_scroll():
            if hasattr(self.window, 'epg_content') and self.window.epg_content.count() > index:
                item = self.window.epg_content.item(index)
                if item:
                    self.window.epg_content.scrollToItem(
                        item,
                        self.window.epg_content.ScrollHint.PositionAtCenter
                    )
                    logger.debug(f"EPG已定位到第 {index + 1} 个节目（{label}，居中显示）")
        safe_single_shot(100, self.window, do_scroll)

    def toggle_epg(self, checked: bool):
        """切换EPG面板显示/隐藏"""
        if hasattr(self.window, 'epg_panel'):
            self.window.epg_visible = checked
            self.window._sync_panel_actions()

    @property
    def has_epg_data(self) -> bool:
        """是否有EPG数据"""
        epg_parser = getattr(self.window, 'epg_parser', None)
        if epg_parser is None:
            return False
        return epg_parser.has_epg_data()

    @property
    def current_program_count(self) -> int:
        """当前显示的节目数量"""
        epg_parser = getattr(self.window, 'epg_parser', None)
        if epg_parser is None:
            return 0
        return epg_parser.get_epg_program_count()
