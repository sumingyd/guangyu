"""
频道列表控制器 - 负责频道信息显示、分组切换等
从 pyqt_player.py 提取的独立模块
"""

from typing import Dict, Any
from datetime import datetime
from collections import deque

from PySide6.QtWidgets import QListWidgetItem, QListWidget, QWidget
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6 import QtWidgets

from core.application_state import app_state
from core.log_manager import global_logger as logger
from utils.general_utils import get_display_channel_name
from controllers.main_window_protocol import ChannelProtocol
from services.stream_quality_scorer import StreamQualityScorer
from ui.quality_bar import QualityBarWidget
from utils.thread_safety import safe_single_shot


class ChannelController:
    """频道列表控制器 - 管理频道信息显示和分组切换"""

    def __init__(self, main_window: ChannelProtocol):
        self.window: ChannelProtocol = main_window

    def on_group_changed(self, group_name: str):
        """处理分组切换事件"""
        self.window._populate_channel_list(source='auto')

    def _get_current_channels(self):
        """获取当前活跃的频道列表"""
        playlist_tab = getattr(self.window, 'playlist_tab', None)
        if playlist_tab:
            # Tab 1 = 本地频道，Tab 0 = 订阅频道
            if playlist_tab.currentIndex() == 1:
                channels = getattr(self.window, '_local_channels', None)
                if channels:
                    return channels
            else:
                channels = getattr(self.window, '_sub_channels', None)
                if channels:
                    return channels
        # fallback：任一列表有数据则返回
        sub = getattr(self.window, '_sub_channels', None)
        local = getattr(self.window, '_local_channels', None)
        if sub:
            return sub
        if local:
            return local
        return app_state.channels

    def _get_display_channel_name(self, channel: Dict[str, Any]) -> str:
        """获取频道的显示名称（委托给通用工具函数）"""
        language_manager = getattr(self.window, 'language_manager', None)
        return get_display_channel_name(channel, language_manager)

    def _update_channel_info(self, channel: Dict[str, Any]):
        """更新频道信息显示区域"""
        if not self.window.channel_name:
            return

        display_name = self._get_display_channel_name(channel)
        self.window.channel_name.setText(display_name)

        if self.window.channel_logo:
            logo_url = channel.get('logo') or channel.get('logo_url')
            if not logo_url:
                self.window.channel_logo.setText("")
                self.window.channel_logo.setPixmap(None)

    @staticmethod
    def _set_list_bulk_mode(list_widget, enabled):
        try:
            list_widget.setUpdatesEnabled(enabled)
            if enabled:
                # QAbstractItemView 在 PySide6 中存在 update(QModelIndex) 重载，
                # 会遮蔽 QWidget.update() 的零参形式，直接调用会抛 TypeError。
                QWidget.update(list_widget)
        except RuntimeError:
            pass

    def populate_channel_list_for(self, list_widget, channels, selected_group=''):
        w = self.window
        tr = w.language_manager.tr

        list_widget.clear()

        # 批量重建期间关闭刷新，避免每 addItem/setItemWidget 都触发一次重绘
        self._set_list_bulk_mode(list_widget, False)
        # 兜底：即使中途异常，也在当前调用栈返回后恢复刷新
        safe_single_shot(0, list_widget, lambda: self._set_list_bulk_mode(list_widget, True))

        if hasattr(w, '_icon_load_timer') and w._icon_load_timer:
            w._icon_load_timer.stop()
        if w._icon_load_set:
            w._icon_load_set.clear()
        if w._icon_load_queue:
            w._icon_load_queue.clear()

        all_channels_text = tr("all_channels", "All Channels")
        is_all_channels = (
            not selected_group or
            selected_group.lower() == all_channels_text.lower()
        )

        added_count = 0
        error_count = 0
        skipped_count = 0

        from ui.styles import AppStyles
        from ui.elided_label import ElidedLabel
        from utils.platform_utils import get_ui_scale
        name_style = AppStyles.player_channel_list_name_style()
        ui_scale = get_ui_scale()

        for idx, channel in enumerate(channels):
            try:
                if not is_all_channels:
                    channel_groups = channel.get('_groups', [channel.get('group', '')])
                    if selected_group not in channel_groups:
                        skipped_count += 1
                        continue

                channel_name = channel.get("name", tr("unnamed", "Unnamed"))
                logo_url = channel.get('logo', '')

                try:
                    is_grid = list_widget.viewMode() == QListWidget.ViewMode.IconMode

                    if is_grid:
                        item = QListWidgetItem()
                        item.setText(channel_name)
                        item.setToolTip(channel_name)
                        item.setData(Qt.ItemDataRole.UserRole, idx)
                        item.setSizeHint(QSize(int(round(220 * ui_scale)), int(round(150 * ui_scale))))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                        list_widget.addItem(item)
                    else:
                        item_widget = QtWidgets.QWidget()
                        item_widget.style_type = 'channel_item'
                        item_widget.setStyleSheet(AppStyles.transparent_style())
                        outer_layout = QtWidgets.QVBoxLayout(item_widget)
                        outer_layout.setContentsMargins(5, 2, 5, 2)
                        outer_layout.setSpacing(0)

                        row_layout = QtWidgets.QHBoxLayout()
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.setSpacing(8)

                        logo_label = QtWidgets.QLabel()
                        logo_label.setFixedSize(int(round(44 * ui_scale)), int(round(32 * ui_scale)))
                        logo_label.setStyleSheet(AppStyles.transparent_style())
                        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        logo_label.setObjectName("channel_logo_label")

                        name_label = ElidedLabel(channel_name)
                        name_label.setStyleSheet(name_style)
                        name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

                        row_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
                        row_layout.addWidget(name_label, 1, Qt.AlignmentFlag.AlignVCenter)

                        outer_layout.addLayout(row_layout, 1)

                        # 评分条：名称下方红→黄→绿渐变指示
                        # 优先读持久化 quality_score 字段（订阅源/本地 M3U 自带评分的场景）
                        # 否才按 valid 判断（未检测 valid is None 不显示）
                        quality_bar = QualityBarWidget(item_widget)
                        persisted_score = channel.get('quality_score')
                        persisted_grade = channel.get('quality_grade') or ''
                        if persisted_score is not None and persisted_score != '':
                            try:
                                quality_bar.set_score(float(persisted_score), persisted_grade)
                            except (TypeError, ValueError):
                                quality_bar.set_score(None)
                        else:
                            score_info = StreamQualityScorer.score_from_channel_safe(channel)
                            if score_info is not None:
                                quality_bar.set_score(score_info.get('total'), score_info.get('grade', ''))
                            else:
                                quality_bar.set_score(None)
                        outer_layout.addWidget(quality_bar, 0)

                        item = QListWidgetItem()
                        item.setSizeHint(QSize(0, int(round(46 * ui_scale))))
                        item.setData(Qt.ItemDataRole.UserRole, idx)

                        list_widget.addItem(item)
                        list_widget.setItemWidget(item, item_widget)

                    added_count += 1

                except Exception as widget_ex:
                    simple_item = QListWidgetItem(channel_name)
                    simple_item.setData(Qt.ItemDataRole.UserRole, idx)
                    list_widget.addItem(simple_item)
                    added_count += 1
                    error_count += 1
                    if error_count <= 3:
                        logger.warning(f"第{idx}个频道的自定义widget创建失败，使用简单文本: {widget_ex}")

            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    logger.error(f"populate_channel_list: 添加第{idx}个频道失败: {e}")

        empty_label = None
        if list_widget is getattr(w, 'sub_channel_list', None):
            empty_label = getattr(w, 'sub_empty_label', None)
        elif list_widget is getattr(w, 'local_channel_list', None):
            empty_label = getattr(w, 'local_empty_label', None)

        if empty_label:
            if added_count == 0:
                empty_label.show()
            else:
                empty_label.hide()

        if error_count > 0:
            logger.warning(f"populate_channel_list: 共 {error_count} 个频道添加失败")
        if skipped_count > 0:
            logger.warning(f"populate_channel_list: 共 {skipped_count} 个频道被分组过滤跳过")

        logger.info(f"populate_channel_list: 填充完成，共 {list_widget.count()} 个频道项（实际添加: {added_count}, 跳过: {skipped_count}, 总数据: {len(channels)}）")
        self._set_list_bulk_mode(list_widget, True)
        try:
            list_widget.verticalScrollBar().valueChanged.connect(w._on_channel_list_scrolled, Qt.ConnectionType.UniqueConnection)
        except TypeError:
            pass
        safe_single_shot(50, self.window, lambda: self.load_visible_icons(list_widget, channels))

    def load_visible_icons(self, list_widget, channels):
        w = self.window

        if not w._icon_load_queue:
            w._icon_load_queue = deque()
            w._icon_load_set = set()
            w._icon_load_timer = QTimer(w)
            w._icon_load_timer.setInterval(16)
            w._icon_load_timer.timeout.connect(w._process_icon_load_batch)

        icon_load_set = w._icon_load_set
        icon_load_queue = w._icon_load_queue
        icon_load_timer = w._icon_load_timer
        assert icon_load_set is not None and icon_load_queue is not None

        if not hasattr(w, '_logo_cache_service') or not w._logo_cache_service:
            logger.warning("_load_visible_icons: _logo_cache_service未初始化，跳过台标加载")
            return

        viewport_rect = list_widget.viewport().rect()
        top_index = list_widget.indexAt(viewport_rect.topLeft())
        bottom_index = list_widget.indexAt(viewport_rect.bottomLeft())

        first_visible = top_index.row() if top_index.isValid() else 0
        last_visible = bottom_index.row() if bottom_index.isValid() else list_widget.count() - 1
        first_visible = max(0, first_visible - 3)
        last_visible = min(list_widget.count() - 1, last_visible + 3)

        is_grid = list_widget.viewMode() == QListWidget.ViewMode.IconMode

        logger.debug(f"_load_visible_icons: 项数={list_widget.count()}, channels={len(channels)}")
        need_capture = []
        queue_items = []

        for i in range(first_visible, last_visible + 1):
            item = list_widget.item(i)
            if not item:
                continue
            channel_idx = item.data(Qt.ItemDataRole.UserRole)
            if channel_idx is None or channel_idx >= len(channels):
                continue
            channel = channels[channel_idx]
            logo_url = channel.get('logo', '').strip('`' + '"' + '\'')

            if is_grid:
                if not item.icon().isNull():
                    continue
                ch_url = channel.get('url', '')
                if w.player_controller and ch_url:
                    thumb_path = w.player_controller.get_thumbnail_path(ch_url)
                    if thumb_path:
                        dedupe_key = ('grid_thumb', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('grid_thumb', item, thumb_path, None))
                            icon_load_set.add(dedupe_key)
                        continue
                if logo_url:
                    cached = w._logo_cache_service.get(logo_url)
                    if cached:
                        dedupe_key = ('grid_logo', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('grid_logo', item, None, cached))
                            icon_load_set.add(dedupe_key)
                    else:
                        w._logo_cache_service.fetch_async(logo_url)
                if ch_url:
                    need_capture.append(channel)
            else:
                item_widget = list_widget.itemWidget(item)
                if not item_widget:
                    continue
                logo_label = item_widget.findChild(QtWidgets.QLabel, "channel_logo_label")
                if not logo_label:
                    continue
                if logo_label.pixmap() and not logo_label.pixmap().isNull():
                    continue
                if logo_url:
                    cached = w._logo_cache_service.get(logo_url)
                    if cached:
                        dedupe_key = ('list_logo', i)
                        if dedupe_key not in icon_load_set:
                            queue_items.append(('list_logo', item, logo_label, cached))
                            icon_load_set.add(dedupe_key)
                    else:
                        w._logo_cache_service.fetch_async(logo_url)
                else:
                    ch_url = channel.get('url', '')
                    if ch_url:
                        from services.audio_visual_service import AUDIO_EXTENSIONS, extract_cover_art
                        if ch_url.lower().endswith(AUDIO_EXTENSIONS):
                            cover = extract_cover_art(ch_url)
                            if cover and not cover.isNull():
                                dedupe_key = ('list_logo', i)
                                if dedupe_key not in icon_load_set:
                                    queue_items.append(('list_logo', item, logo_label, cover))
                                    icon_load_set.add(dedupe_key)

        icon_load_queue.extend(queue_items)
        if icon_load_queue and icon_load_timer and not icon_load_timer.isActive():
            icon_load_timer.start()

        if need_capture and hasattr(w, '_thumbnail_service'):
            w._thumbnail_service.capture_channels(need_capture, force=True)

    def update_channel_info_on_selection(self):
        w = self.window
        if not w.current_channel:
            return

        w.media_ctrl.update_catchup_indicator()

        display_name = self._get_display_channel_name(w.current_channel)
        w.channel_name.setText(display_name)
        w.current_program.setText("")
        logo = w.current_channel.get("logo", "")

        if logo:
            logo = logo.strip('`"\'')

            cached = w._logo_cache_service.get(logo)
            if cached:
                scaled_pixmap = w._logo_cache_service.scale_logo_pixmap_to_fit(cached, w.channel_logo.width(), w.channel_logo.height())
                w.channel_logo.setPixmap(scaled_pixmap)
                w.channel_logo.setText("")
            else:
                w._logo_cache_service.fetch_async(logo)
                from utils.general_utils import set_default_channel_logo
                set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())
        else:
            ch_url = w.current_channel.get('url', '') if w.current_channel else ''
            from services.audio_visual_service import AUDIO_EXTENSIONS
            if ch_url and ch_url.lower().endswith(AUDIO_EXTENSIONS):
                from services.audio_visual_service import extract_cover_art
                cover = extract_cover_art(ch_url)
                if cover and not cover.isNull():
                    from utils.general_utils import set_default_channel_logo
                    scaled = cover.scaled(w.channel_logo.width(), w.channel_logo.height(),
                                          Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
                    w.channel_logo.setPixmap(scaled)
                    w.channel_logo.setText("")
                    if hasattr(w, 'player_controller') and w.player_controller:
                        if hasattr(w.player_controller, 'audio_visual') and w.player_controller.audio_visual:
                            if w.player_controller.audio_visual._widget:
                                w.player_controller.audio_visual._widget.set_cover(cover)
                else:
                    from utils.general_utils import set_default_channel_logo
                    set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())
            else:
                from utils.general_utils import set_default_channel_logo
                set_default_channel_logo(w.channel_logo, w.channel_logo.width(), w.channel_logo.height())

        try:
            if w._is_local_file():
                w.current_program.setText("")
                ch_url = w.current_channel.get('url', '') if w.current_channel else ''
                from services.audio_visual_service import AUDIO_EXTENSIONS
                if ch_url and ch_url.lower().endswith(AUDIO_EXTENSIONS):
                    w.program_desc.setText(w.language_manager.tr("local_audio_file", "本地音频文件"))
                else:
                    w.program_desc.setText(w.language_manager.tr("local_video_file", "本地视频文件"))
                w.time_label.setText("--:-- / --:--")
                w.remain_label.setText(w.language_manager.tr("loading", "加载中..."))
            else:
                channel_name = w.current_channel.get("name", "")
                current_program_data = None
                if channel_name and hasattr(w, 'epg_parser') and w.epg_parser:
                    ch_name, tvg_id, tvg_name, comma_name = w._get_epg_match_params()
                    current_program_data = w.epg_parser.get_current_program(
                        ch_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name
                    )
                if current_program_data:
                    program_name = current_program_data.get("title", "")
                    w.current_program.setText(f"· {program_name}" if program_name else "")
                    w.program_desc.setText(current_program_data.get("desc", w.language_manager.tr("no_program_desc", "No program description")))
                    start_str = current_program_data.get("start", "")
                    start_display = datetime.fromisoformat(start_str).strftime("%H:%M") if start_str else "--:--"
                    w.progress_start.setText(start_display)
                    w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
                    w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))
                else:
                    w.current_program.setText("")
                    w.program_desc.setText(w.language_manager.tr("open_playlist_success", "Channel list opened, click a channel to play"))
                    w.time_label.setText(f"{datetime.now().strftime('%H:%M')}")
                    w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))
        except Exception:
            w.current_program.setText("")
            w.program_desc.setText(w.language_manager.tr("open_playlist_success", "Channel list opened, click a channel to play"))
            current_time = datetime.now().strftime("%H:%M")
            w.time_label.setText(f"{current_time}")
            w.remain_label.setText(w.language_manager.tr("waiting_to_play", "Waiting to play..."))

        w._set_progress_value(0)
        w.progress_end.setText("--:--")

        w.video_info.setText(f'{w.language_manager.tr("waiting_to_play", "Waiting to play...")}')
        w.audio_info.setText("--")
        w.network_info.setText(f'{w.language_manager.tr("waiting_connect", "Waiting to connect...")}')
        if hasattr(w, 'buffer_info'):
            w.buffer_info.hide()
        if hasattr(w, 'hdr_badge'):
            w.hdr_badge.hide()

    @property
    def channel_count(self) -> int:
        """当前频道数量"""
        return len(app_state.channels)

    @property
    def current_group(self) -> str:
        """当前选中的分组名称"""
        if self.window.group_combo:
            return self.window.group_combo.currentText()
        return ""

    def update_quality_bar_for_url(self, url: str, score: float, grade: str = ''):
        """播放过程中获取到媒体信息后，更新播放列表中对应频道的评分条。

        遍历 sub_channel_list 和 local_channel_list，找到 URL 匹配的条目，
        通过 findChild 找到 QualityBarWidget 并调用 set_score。

        Args:
            url: 频道 URL
            score: 质量评分 (0~100)
            grade: 质量等级 (A/B/C/D/F)
        """
        if not url:
            return
        for list_attr in ('sub_channel_list', 'local_channel_list'):
            cl = getattr(self.window, list_attr, None)
            if not cl:
                continue
            for i in range(cl.count()):
                item = cl.item(i)
                if not item:
                    continue
                idx = item.data(Qt.ItemDataRole.UserRole)
                channels = getattr(self.window, '_sub_channels', None) if list_attr == 'sub_channel_list' \
                    else getattr(self.window, '_local_channels', None)
                if not isinstance(idx, int) or not channels or idx >= len(channels):
                    continue
                if channels[idx].get('url', '') != url:
                    continue
                # 找到匹配的条目，更新评分条
                item_widget = cl.itemWidget(item)
                if item_widget:
                    bar = item_widget.findChild(QualityBarWidget, "quality_bar")
                    if bar:
                        bar.set_score(score, grade)
                break
