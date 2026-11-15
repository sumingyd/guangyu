from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QToolButton, QSizePolicy, QDockWidget,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu

from core.log_manager import global_logger as logger
from ui.elided_label import ElidedLabel
from ui.media_chips import MediaChips
from ui.styles import AppStyles
from ui.volume_slider import VolumeSlider
from utils.platform_utils import is_android



class ControlPanelMixin:
    """从 IPTVPlayer 提取的底部控制面板UI构建职责"""

    def _create_bottom_panel(self, show=True):
        """创建底部悬浮控制面板"""

        self._create_panel(show=show)


    def _create_panel(self, show=True):
        """创建底部控制面板（QDockWidget 停靠底部）"""
        tr = self.language_manager.tr

        floating_container = QWidget()
        floating_container.setObjectName("panelContainer")
        floating_container.setStyleSheet("background-color: transparent; border: none;")
        floating_container.setMinimumHeight(120)
        floating_container.setMinimumWidth(360)
        floating_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.floating_layout = QVBoxLayout(floating_container)
        self.floating_layout.setContentsMargins(8, 8, 8, 8)
        self.floating_layout.setSpacing(3)

        self._create_media_row()

        from ui.floating_dialog import FloatingDockWidget
        self.floating_dock = FloatingDockWidget(tr("control_panel", "Control Panel"), self)
        self.floating_dock.setWidget(floating_container)
        self.floating_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.floating_dock.setObjectName("floating_dock")
        if hasattr(self, 'floating_panel'):
            self.floating_panel = None
        self.floating_panel = self.floating_dock

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.floating_dock)
        self.floating_dock.setFloating(True)
        # 构造期徽章行可能已按两行定高，但底栏这时才存在：补一次高度同步
        self._on_media_chips_height_changed(self.media_chips.height())
        if not show:
            self.floating_dock.hide()


    def _control_panel_ui_metrics(self):
        """控制栏尺寸基线：逻辑屏宽因子 × 用户界面缩放档位。

        QSS 内的字号/内边距由 ui/typography 的统一拦截器换算；这里负责
        setFixedSize / setIconSize 这类样式表管不到的固定尺寸，两处不能重复乘。
        """
        from utils.platform_utils import get_effective_ui_scale
        from ui.typography import text_factor
        scale = get_effective_ui_scale()
        # 只有字号档位偏大时才用字体实际高度兜底；标准档保持既有观感不变，
        # 避免「字号设置」本身把默认界面改高。
        try:
            text_h = self.fontMetrics().height()
        except Exception:
            text_h = 18
        min_text_h = (text_h + 12) if text_factor() > 1.0 else 0
        return {
            'scale': scale,
            'button_w': max(25, int(round(self.CTRL_BUTTON_WIDTH * scale))),
            'button_h': max(22, int(round(self.CTRL_BUTTON_HEIGHT * scale)), min_text_h),
            'icon': max(14, int(round(16 * scale))),
            'info_h': max(16, int(round(22 * scale)), min_text_h),
            'logo_w': max(40, int(round(self.CHANNEL_LOGO_WIDTH * scale))),
            'logo_h': max(20, int(round(self.CHANNEL_LOGO_HEIGHT * scale))),
            'volume_w': max(64, int(round(90 * scale))),
            'spacing': max(4, int(round(6 * scale))),
        }

    def refresh_control_panel_metrics(self):
        """字号/缩放在运行期变更后重算控制栏与信息行的固定尺寸。"""
        metrics = self._control_panel_ui_metrics()
        icon_size = QSize(metrics['icon'], metrics['icon'])
        for name in (
            'prev_ch_button', 'play_button', 'next_ch_button', 'stop_button',
            'volume_button', 'more_button', 'fullscreen_button',
        ):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setIconSize(icon_size)
            btn.setFixedSize(metrics['button_w'], metrics['button_h'])
        slider = getattr(self, 'volume_slider', None)
        if slider is not None:
            slider.setFixedWidth(metrics['volume_w'])
        for name in ('video_info', 'audio_info', 'network_info', 'buffer_info'):
            label = getattr(self, name, None)
            if label is not None:
                # 各段宽度由徽章行统一分配，这里只同步行高，
                # 避免「特大」字号 + 高 DPI 时文字被面板右边界硬裁。
                label.setFixedHeight(metrics['info_h'])
        chips = getattr(self, 'media_chips', None)
        if chips is not None:
            chips.set_item_height(metrics['info_h'])
        desc = getattr(self, 'program_desc', None)
        if desc is not None:
            desc.setFixedHeight(self._scaled_program_desc_height())
        if chips is not None:
            chips.relayout()
        logo = getattr(self, 'channel_logo', None)
        if logo is not None:
            logo.setFixedSize(metrics['logo_w'], metrics['logo_h'])
        row = getattr(self, 'control_row', None)
        if row is not None and not is_android():
            row.setSpacing(metrics['spacing'])

    def _on_media_chips_height_changed(self, height):
        """徽章行从一行变两行（或反过来）时，浮动底栏要跟着长/缩。

        底栏是独立浮动窗口，内容尺寸变化不会自动改变窗口高度；
        不跟就会把第二行徽章裁掉。这里延后一帧，等布局把新高度算进去。
        """
        if getattr(self, '_chips_dock_sync_pending', False):
            return
        self._chips_dock_sync_pending = True
        from utils.thread_safety import safe_single_shot
        safe_single_shot(0, self, self._sync_media_chips_dock_height)

    def _sync_media_chips_dock_height(self, attempt=0):
        self._chips_dock_sync_pending = False
        dock = getattr(self, 'floating_dock', None)
        if dock is None:
            return
        container = dock.widget()
        if container is None:
            return
        try:
            layout = container.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            # 底栏窗口的 sizeHint 会晚一帧才反映子控件新高度，
            # 直接按容器内容高度 + 原有边框补，避免第二行刚出现时被裁一下
            content_h = container.sizeHint().height()
            frame = max(0, dock.height() - container.height())
            target = max(content_h + frame, dock.sizeHint().height())
            if target > 0 and dock.height() != target:
                dock.resize(dock.width(), target)
            # 首帧布局可能还没算完，再看一次；只重试一次，避免反复触发
            if attempt < 1:
                from utils.thread_safety import safe_single_shot
                safe_single_shot(
                    60, self,
                    lambda: self._sync_media_chips_dock_height(attempt + 1),
                )
        except Exception as e:
            logger.debug(f"调整底栏高度失败: {e}")

    def _create_media_row(self):
        """创建媒体信息行（每项一枚低对比小胶囊）"""
        tr = self.language_manager.tr
        info_h = self._control_panel_ui_metrics()['info_h']

        self.media_row = QHBoxLayout()
        self.media_row.setSpacing(6)

        self.media_chips = MediaChips()
        self.media_chips.set_item_height(info_h)
        self.media_chips.heightChanged.connect(self._on_media_chips_height_changed)

        # 沿用旧控件名：setText 会被拆成一组独立徽章
        self.video_info = self.media_chips.group('video')
        self.video_info.setToolTip(tr('tooltip_video_info', '视频信息'))
        self.video_info.setText(tr('not_playing', 'Not playing'))

        self.hdr_badge = self.media_chips.hdr_chip
        self.hdr_badge.setToolTip(tr('tooltip_hdr', 'HDR状态'))
        self.hdr_badge.hide()

        self.audio_info = self.media_chips.group('audio')
        self.audio_info.setToolTip(tr('tooltip_audio_info', '音频信息'))
        self.audio_info.setText("--")

        self.network_info = self.media_chips.group('network')
        self.network_info.setToolTip(tr('tooltip_network_info', '网络信息'))
        self.network_info.setText("--")

        self.buffer_info = self.media_chips.buffer_chip
        self.buffer_info.setToolTip(tr('tooltip_buffer_info', '缓冲信息'))
        self.buffer_info.hide()

        self.media_row.addWidget(self.media_chips, 1)
        self.floating_layout.addLayout(self.media_row)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(AppStyles.player_line_style())
        self.floating_layout.addWidget(line1)

        self._create_info_row()


    def _scaled_program_desc_height(self):
        """简介行高度按两行实际行高计算，随字号档位放大，避免第二行被裁。"""
        try:
            line_h = self.fontMetrics().lineSpacing()
            return max(self.PROGRAM_DESC_HEIGHT, line_h * 2 + 4)
        except Exception:
            return self.PROGRAM_DESC_HEIGHT

    def _create_info_row(self):
        """创建节目信息行"""
        tr = self.language_manager.tr

        info_layout = QHBoxLayout()
        info_layout.setSpacing(12)

        self.channel_logo = QLabel()
        self.channel_logo.setStyleSheet(AppStyles.player_channel_logo_style())
        self.channel_logo.setFixedSize(
            self._control_panel_ui_metrics()['logo_w'],
            self._control_panel_ui_metrics()['logo_h'],
        )
        self.channel_logo.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter)
        from utils.general_utils import set_default_channel_logo
        logo_metrics = self._control_panel_ui_metrics()
        set_default_channel_logo(
            self.channel_logo,
            max(60, int(round(100 * logo_metrics['scale']))),
            max(24, int(round(36 * logo_metrics['scale']))),
        )
        info_layout.addWidget(self.channel_logo, 0, Qt.AlignmentFlag.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.channel_name = ElidedLabel(tr("no_channel_selected", "No channel selected"), full_text_hint=True)
        self.channel_name.setObjectName("channel_name")
        self.channel_name.setStyleSheet(AppStyles.player_channel_name_style())
        # 不再写死最大宽度：按完整文本参与布局，只有整行真的放不下时才省略（保留 tooltip）
        row1.addWidget(self.channel_name, 0)
        self.current_program = ElidedLabel("")
        self.current_program.setObjectName("current_program")
        self.current_program.setStyleSheet(AppStyles.player_program_style())
        self.current_program.setAutoFillBackground(False)
        self.current_program.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.current_program.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(self.current_program, 1)
        self.time_label = QLabel("--:-- - --:--")
        self.time_label.setStyleSheet(AppStyles.player_time_badge_style())
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self.time_label, 0)
        self.catchup_indicator = QLabel("")
        self.catchup_indicator.setStyleSheet(AppStyles.player_catchup_indicator_style())
        self.catchup_indicator.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.catchup_indicator.hide()
        row1.addWidget(self.catchup_indicator, 0)
        self.remain_label = QLabel(tr("waiting_to_play", "Waiting to play..."))
        self.remain_label.setStyleSheet(AppStyles.player_status_badge_style())
        self.remain_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.remain_label.setMinimumWidth(70)
        # 字号放大后「播放中...」的宽度会超过旧的 70px 下限，行内空间不足时
        # QLabel 默认会被压到 minimumWidth。改为 Minimum 横向策略，让省略发生在
        # channel_name / current_program 上，状态徽标始终按 sizeHint 显示完整文字。
        self.remain_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        row1.addWidget(self.remain_label, 0)
        text_layout.addLayout(row1)

        self.program_desc = QLabel(tr("open_playlist_or_import", "Open a channel list file or import channels to start watching"))
        self.program_desc.setObjectName("program_desc")
        self.program_desc.setStyleSheet(AppStyles.player_program_desc_style())
        self.program_desc.setWordWrap(True)
        self.program_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.program_desc.setFixedHeight(self._scaled_program_desc_height())
        self.program_desc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        # 空态引导 CTA：文案为引导语时可点击打开订阅；业务描述更新无需感知
        self.program_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.program_desc.setToolTip(tr("tooltip_open_playlist_cta", "点击打开订阅文件"))
        self.program_desc.mousePressEvent = self._on_program_desc_clicked
        self.program_desc.enterEvent = self._on_program_desc_enter
        text_layout.addWidget(self.program_desc, 0, Qt.AlignmentFlag.AlignTop)

        info_layout.addLayout(text_layout)

        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        info_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.floating_layout.addWidget(info_widget)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(AppStyles.player_line_style())
        self.floating_layout.addWidget(line2)

        self._create_control_row()


    def _create_control_row(self):
        """创建控制行"""
        tr = self.language_manager.tr

        self.control_row = QHBoxLayout()
        # 间距随按钮一起收紧（Windows 桌面）；Android/TV 保持原间距
        self.control_row.setSpacing(6 if not is_android() else 8)

        btn_color = AppStyles.get_color('player_panel_text')
        # 按「逻辑屏宽 × 用户界面缩放」分级：按钮、图标与全屏精简模式统一套用
        metrics = self._control_panel_ui_metrics()
        btn_w = metrics['button_w']
        btn_h = metrics['button_h']
        btn_icon_size = QSize(metrics['icon'], metrics['icon'])
        if is_android():
            btn_icon_size = QSize(28, 28)
            btn_w = max(btn_w, 48)
            btn_h = max(btn_h, 48)
        self.prev_ch_button = QToolButton()
        self.prev_ch_button.setIcon(QIcon(AppStyles.get_icon('prev', btn_color)))  # type: ignore[arg-type]
        self.prev_ch_button.setIconSize(btn_icon_size)
        self.prev_ch_button.setFixedSize(btn_w, btn_h)
        self.prev_ch_button.setStyleSheet(AppStyles.player_button_style())
        self.prev_ch_button.clicked.connect(lambda: self._switch_channel_safe(-1))
        self.prev_ch_button.setToolTip(tr("panel_prev_ch", "上一频道"))
        self.control_row.addWidget(self.prev_ch_button)

        self.play_button = QToolButton()
        self.play_button.setIcon(QIcon(AppStyles.get_icon(AppStyles.play_icon_name(False, False), btn_color)))  # type: ignore[arg-type]
        self.play_button.setIconSize(btn_icon_size)
        self.play_button.setFixedSize(btn_w, btn_h)
        self.play_button.setStyleSheet(AppStyles.player_button_style())
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setToolTip(tr("panel_play", "播放/暂停"))
        self.control_row.addWidget(self.play_button)

        self.next_ch_button = QToolButton()
        self.next_ch_button.setIcon(QIcon(AppStyles.get_icon('next', btn_color)))  # type: ignore[arg-type]
        self.next_ch_button.setIconSize(btn_icon_size)
        self.next_ch_button.setFixedSize(btn_w, btn_h)
        self.next_ch_button.setStyleSheet(AppStyles.player_button_style())
        self.next_ch_button.clicked.connect(lambda: self._switch_channel_safe(1))
        self.next_ch_button.setToolTip(tr("panel_next_ch", "下一频道"))
        self.control_row.addWidget(self.next_ch_button)

        self.stop_button = QToolButton()
        self.stop_button.setIcon(QIcon(AppStyles.get_icon('stop', btn_color)))  # type: ignore[arg-type]
        self.stop_button.setIconSize(btn_icon_size)
        self.stop_button.setFixedSize(btn_w, btn_h)
        self.stop_button.setStyleSheet(AppStyles.player_button_style())
        self.stop_button.clicked.connect(self.stop_playback)
        self.stop_button.setToolTip(tr("panel_stop", "停止"))
        self.control_row.addWidget(self.stop_button)

        self.progress_group = QHBoxLayout()
        self.progress_group.setSpacing(4)

        self.progress_start = QLabel("--:--")
        self.progress_start.setStyleSheet(AppStyles.player_progress_label_style())
        self.progress_group.addWidget(self.progress_start)

        from ui.cache_progress_slider import CacheProgressSlider
        self.program_progress = CacheProgressSlider(Qt.Orientation.Horizontal)
        self.program_progress.setRange(0, 3600)
        self.program_progress.setValue(0)
        self.program_progress.setSingleStep(1)
        self.program_progress.setPageStep(30)
        self.program_progress.setStyleSheet(AppStyles.player_slider_style())
        self.program_progress.set_cache_color(AppStyles._get_colors().get('player_cache_bar', 'rgba(106,158,255,0.4)'))
        self.program_progress.set_tooltip_formatter(self._format_preview_text)
        self.program_progress.sliderReleased.connect(self.on_progress_slider_released)
        self.program_progress.sliderPressed.connect(self._on_progress_slider_pressed)
        self.program_progress.seek_blocked.connect(self._on_progress_seek_blocked)
        self.program_progress.preview_position_changed.connect(self._on_progress_preview)
        self._progress_total_seconds = 3600
        self.progress_group.addWidget(self.program_progress, 1)

        self.progress_end = QLabel("--:--")
        self.progress_end.setStyleSheet(AppStyles.player_progress_label_style())
        self.progress_group.addWidget(self.progress_end)

        self.control_row.addLayout(self.progress_group, 1)

        self.volume_button = QToolButton()
        self.volume_button.setIcon(QIcon(AppStyles.get_icon('volume', btn_color)))  # type: ignore[arg-type]
        self.volume_button.setIconSize(btn_icon_size)
        self.volume_button.setFixedSize(btn_w, btn_h)
        self.volume_button.setStyleSheet(AppStyles.player_button_style())
        self.volume_button.clicked.connect(self.toggle_mute)
        self.volume_button.setToolTip(tr("panel_volume", "音量"))
        self.control_row.addWidget(self.volume_button)

        self.volume_slider = VolumeSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(metrics['volume_w'])
        self.volume_slider.setStyleSheet(AppStyles.player_volume_slider_style())
        self.volume_slider.setToolTip(tr("panel_volume_slider", "音量调节"))
        self.volume_slider.set_bubble_parent(getattr(self, 'floating_panel', None))
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.control_row.addWidget(self.volume_slider)

        # speed/aspect/exit_catchup 已全部收入“更多”菜单，不再实例化隐藏控件；
        # 类属性保留为 None，旧引用按可选控件处理。

        self._create_more_menu()

        self.more_button = QToolButton()
        self.more_button.setIcon(QIcon(AppStyles.get_icon('more', btn_color)))  # type: ignore[arg-type]
        self.more_button.setIconSize(btn_icon_size)
        self.more_button.setFixedSize(btn_w, btn_h)
        self.more_button.setStyleSheet(AppStyles.player_button_style())
        self.more_button.clicked.connect(self._show_more_menu)
        self.more_button.setToolTip(tr("panel_more", "更多"))
        self.control_row.addWidget(self.more_button)

        self.fullscreen_button = QToolButton()
        self.fullscreen_button.setIcon(QIcon(AppStyles.get_icon('fullscreen', btn_color)))  # type: ignore[arg-type]
        self.fullscreen_button.setIconSize(btn_icon_size)
        self.fullscreen_button.setFixedSize(btn_w, btn_h)
        self.fullscreen_button.setStyleSheet(AppStyles.player_button_style())
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_button.setToolTip(tr("panel_fullscreen", "全屏"))
        self.control_row.addWidget(self.fullscreen_button)

        self.floating_layout.addLayout(self.control_row)

    def _update_fullscreen_button_hint(self):
        """全屏按钮的提示语跟随状态（全屏时提示退出全屏）。

        只改提示文案，不再像旧的全屏精简模式那样隐藏进度条与部分按钮：
        窗口模式与全屏模式的底栏控件集合必须保持一致。
        """
        btn = getattr(self, 'fullscreen_button', None)
        if btn is None:
            return
        tr = self.language_manager.tr
        if getattr(self, 'is_fullscreen', False):
            btn.setToolTip(tr("panel_exit_fullscreen", "退出全屏"))
        else:
            btn.setToolTip(tr("panel_fullscreen", "全屏"))


    def _switch_channel_safe(self, direction: int):
        eh = getattr(self, 'event_handler', None)
        if eh:
            eh._switch_channel(direction)

    def _create_more_menu(self):
        """创建“更多”菜单：收纳次级控制按钮（倍速/比例/音轨/字幕/画中画/退出回看）"""

        self._more_menu = QMenu(self)
        self._more_menu.setStyleSheet(AppStyles.player_menu_bar_style())
        mc = self.media_ctrl
        for key, fallback, slot in (
            ("panel_speed", "播放速度", mc.show_speed_menu),
            ("panel_aspect", "画面比例", mc.show_aspect_menu),
            ("panel_audio_track", "音轨", mc.show_audio_track_menu),
            ("panel_subtitle", "字幕", mc.show_sub_track_menu),
            ("panel_pip", "画中画", self.pip_ctrl.toggle),
        ):
            act = self._more_menu.addAction(self.language_manager.tr(key, fallback), slot)
            # 记录 (key, fallback) 供语言切换时刷新文案
            act.setData((key, fallback))
        self._more_menu.addSeparator()
        self._more_catchup_action = self._more_menu.addAction(
            self.language_manager.tr("panel_exit_catchup", "退出回看"), self.exit_catchup
        )
        self._more_catchup_action.setData(("panel_exit_catchup", "退出回看"))
        self._more_catchup_action.setVisible(False)

    def _show_more_menu(self):
        """弹出“更多”菜单（向上弹出，避免被屏幕底部裁剪）"""

        menu = self._more_menu
        btn = self.more_button
        menu.adjustSize()
        top_left = btn.mapToGlobal(btn.rect().topLeft())
        y = top_left.y() - menu.height() - 4
        if y < 0:
            y = btn.mapToGlobal(btn.rect().bottomLeft()).y()
        menu.exec(QPoint(top_left.x(), y))

    def _set_exit_catchup_visible(self, visible: bool, text: str = None):
        """回看/时移模式切换时同步“更多”菜单中的退出项。

        退出回看已完全收入“更多”菜单（不再有独立按钮），
        菜单项的可见性与文案是唯一事实来源。
        """
        action = getattr(self, '_more_catchup_action', None)
        if action is not None:
            action.setVisible(visible)
            if text is not None:
                action.setText(text)

    def _is_program_desc_cta(self) -> bool:
        """节目描述当前是否为空态引导文案（与语言切换无关，直接比较 tr 结果）"""
        if not hasattr(self, 'program_desc'):
            return False
        cta_text = self.language_manager.tr(
            "open_playlist_or_import", "Open a channel list file or import channels to start watching"
        )
        return self.program_desc.text() == cta_text

    def _on_program_desc_clicked(self, event):
        """空态引导文案可点击：打开订阅选择；业务描述文本走 QLabel 默认行为"""
        if event.button() == Qt.MouseButton.LeftButton and self._is_program_desc_cta():
            event.accept()
            self.open_playlist()
            return
        QLabel.mousePressEvent(self.program_desc, event)

    def _on_program_desc_enter(self, event):
        """悬停时按文案判断手型光标与提示，避免业务描述残留 CTA 交互暗示"""
        if self._is_program_desc_cta():
            self.program_desc.setCursor(Qt.CursorShape.PointingHandCursor)
            self.program_desc.setToolTip(self.language_manager.tr("tooltip_open_playlist_cta", "点击打开订阅文件"))
        else:
            self.program_desc.setCursor(Qt.CursorShape.ArrowCursor)
            self.program_desc.setToolTip("")
        QLabel.enterEvent(self.program_desc, event)