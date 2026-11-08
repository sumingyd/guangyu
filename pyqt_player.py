import sys
import os

from utils.early_init import setup_environment
setup_environment()

from datetime import date, datetime  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402


from core.play_state import PlayStateManager  # noqa: E402
from core.panel_visibility import PanelVisibilityManager  # noqa: E402
from controllers.main_window_protocol import CatchupProgram  # noqa: E402
from controllers.progress_controller import ProgressController  # noqa: E402
from models.channel_model import ChannelListModel  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStatusBar,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal, QRectF  # noqa: E402
from PySide6 import QtCore  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QIcon, QFont, QFontMetrics, QColor, QPainter, QBrush, QPen,
    QLinearGradient, QPainterPath, QBitmap,
)

from PySide6.QtGui import QShortcut  # noqa: E402
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QApplication as _QApp, QLabel, QSplashScreen

from core.log_manager import global_logger as logger  # noqa: E402
from core.language_manager import LanguageManager  # noqa: E402
from ui.styles import AppStyles  # noqa: E402
from utils.delay_constants import DelayMs  # noqa: E402


from controllers import (  # noqa: E402
    WindowController,
    PlaybackController,
    EPGController,
    ChannelController,
    SettingsFileOperations,
    EventHandler,
    UIController,
    SubscriptionController,
    SubscriptionUIController,
    CatchupController,
    PipController,
    MediaController,
    UpdateController,
    FavoritesController,
    EpgReminderController
)

from utils.general_utils import calculate_adaptive_delay  # noqa: E402
from mixins.server_mixin import ServerMixin  # noqa: E402
from mixins.tray_mixin import TrayMixin  # noqa: E402
from mixins.update_mixin import UpdateMixin  # noqa: E402
from mixins.thumbnail_mixin import ThumbnailMixin  # noqa: E402
from mixins.file_ops_mixin import FileOpsMixin  # noqa: E402
from mixins.panel_mixin import PanelMixin  # noqa: E402
from mixins.progress_mixin import ProgressMixin  # noqa: E402
from mixins.playback_mixin import PlaybackMixin  # noqa: E402
from mixins.epg_mixin import EpgMixin  # noqa: E402
from mixins.channel_mixin import ChannelMixin  # noqa: E402
from mixins.settings_mixin import SettingsMixin  # noqa: E402
from mixins.window_mixin import WindowMixin  # noqa: E402
from mixins.control_panel_mixin import ControlPanelMixin  # noqa: E402
from mixins.playlist_panel_mixin import PlaylistPanelMixin  # noqa: E402
from mixins.event_mixin import EventMixin  # noqa: E402


class _RoundedContainer(QWidget):
    """主窗口容器：真正裁切卡面圆角。

    QSS 的 border-radius 只圆化容器自身背景，容器内的子控件仍会以直角盖住圆角；
    旧实现的 clip 在 super().paintEvent() 之前就结束了，对子控件绘制无效。
    这里沿用浮窗/dock 已验证的 mask 方案裁切子控件。
    Windows 不启用：SetWindowRgn 会连带裁掉 wid 嵌入的视频区圆角，改变现有观感。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mask_key = None

    def _update_rounded_mask(self):
        from utils.platform_utils import is_windows
        if is_windows():
            return
        try:
            win = self.window()
            if win is not None and (win.isMaximized() or win.isFullScreen()):
                if self._mask_key is not None:
                    self.clearMask()
                    self._mask_key = None
                return
            size = self.size()
            if size.width() <= 0 or size.height() <= 0:
                return
            r = AppStyles._get_style_border_radius()
            key = (size.width(), size.height(), r)
            if key == self._mask_key:
                return
            self._mask_key = key
            bitmap = QBitmap(size)
            bitmap.fill(Qt.GlobalColor.color0)
            p = QPainter(bitmap)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(Qt.GlobalColor.color1)
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), r, r)
            p.drawPath(path)
            p.end()
            self.setMask(bitmap)
            self.update()
        except Exception as e:
            logger.debug(f"主窗口圆角遮罩更新失败: {e}")

    def paintEvent(self, event):
        self._update_rounded_mask()
        super().paintEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._mask_key = None
        self._update_rounded_mask()


class VideoOverlayBadge(QWidget):
    """视频区域叠加标识 Widget，用 QPainter 绘制精美的回看/时移标签"""

    MODE_CATCHUP = 'catchup'
    MODE_TIMESHIFT = 'timeshift'

    @staticmethod
    def _get_mode_configs():

        c = AppStyles._get_colors()
        return {
            'catchup': (c['accent'], c['accent_pressed'], 'catchup', c['window']),
            'timeshift': (c['warning'], c['accent_pressed'], 'timeshift', c['window']),
        }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = self.MODE_CATCHUP
        self._label_text = ''
        self._icon_pixmap = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._font = QFont()
        self._font.setPixelSize(13)
        self._font.setBold(True)
        self._update_icon()
        self._update_size()

    def set_mode(self, mode: str, label_text: str):
        self._mode = mode
        self._label_text = label_text
        self._update_icon()
        self._update_size()
        self.update()

    def _update_icon(self):

        c = AppStyles._get_colors()
        icon_name = 'play' if self._mode == self.MODE_CATCHUP else 'backward'
        icon_color = c['window']
        icon_path = AppStyles.get_icon(icon_name, icon_color, 14)
        if icon_path:
            px = QPixmap(icon_path)
            if not px.isNull():
                self._icon_pixmap = px.scaled(
                    14, 14,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                return
        self._icon_pixmap = None

    def _update_size(self):
        self._font.setPixelSize(13)
        fm2 = QFontMetrics(self._font)
        text_w = fm2.horizontalAdvance(self._label_text)
        icon_w = 18 if self._icon_pixmap else 0
        spacing = 4 if self._icon_pixmap else 0
        w = icon_w + spacing + text_w + 20
        h = max(fm2.height(), 14) + 12
        self.setFixedSize(w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cfg = self._get_mode_configs().get(self._mode, self._get_mode_configs()[self.MODE_CATCHUP])
        color1, color2, _icon_key, text_color = cfg

        r = self.rect()
        radius = r.height() / 2

        path = QPainterPath()
        path.addRoundedRect(0, 0, r.width(), r.height(), radius, radius)

        grad = QLinearGradient(0, 0, r.width(), 0)
        from ui.styles import color_to_qcolor
        grad.setColorAt(0, color_to_qcolor(color1))
        grad.setColorAt(1, color_to_qcolor(color2))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setFont(self._font)
        painter.setPen(color_to_qcolor(text_color))

        icon_w = 14 if self._icon_pixmap else 0
        spacing = 4 if self._icon_pixmap else 0
        total_text_w = QFontMetrics(self._font).horizontalAdvance(self._label_text)
        total_content_w = icon_w + spacing + total_text_w
        start_x = (r.width() - total_content_w) / 2

        if self._icon_pixmap:
            icon_y = (r.height() - 14) / 2
            painter.drawPixmap(int(start_x), int(icon_y), self._icon_pixmap)

        text_x = start_x + icon_w + spacing
        text_rect = QRectF(text_x, 0, r.width() - text_x, r.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label_text)

        painter.end()


# 导入播放器服务
from services.mpv_player_service import MpvPlayerController  # noqa: E402


class IPTVPlayer(
    ServerMixin, TrayMixin, UpdateMixin, ThumbnailMixin, FileOpsMixin,
    PanelMixin, ProgressMixin, PlaybackMixin, EpgMixin, ChannelMixin,
    SettingsMixin, WindowMixin, ControlPanelMixin, PlaylistPanelMixin,
    EventMixin, QMainWindow
):
    epg_status_signal = Signal(str)
    channel_list_updated = Signal()
    epg_list_updated = Signal()
    status_message = Signal(str)

    AUTO_HIDE_INTERVAL_MS = 5000
    RECONNECT_DELAY_MS = 2000
    SLIDER_DEBOUNCE_MS = 100
    CHANNEL_CLICK_DELAY_MS = 300
    PROGRAM_DESC_HEIGHT = 48
    CHANNEL_LOGO_WIDTH = 100
    CHANNEL_LOGO_HEIGHT = 36
    CTRL_BUTTON_WIDTH = 30
    CTRL_BUTTON_HEIGHT = 26

    player_controller = None
    config = None
    config_manager = None
    language_manager = None
    channel_model = None
    channels: Optional[List[Dict[str, Any]]] = None
    current_channel: Optional[Dict[str, Any]] = None
    original_channel: Optional[Dict[str, Any]] = None
    epg_parser = None

    @property
    def epg_visible(self):
        return self.panel_vis.get_visible('epg')

    @epg_visible.setter
    def epg_visible(self, value):
        self.panel_vis.set_visible('epg', value)

    @property
    def playlist_visible(self):
        return self.panel_vis.get_visible('playlist')

    @playlist_visible.setter
    def playlist_visible(self, value):
        self.panel_vis.set_visible('playlist', value)

    @property
    def floating_panel_visible(self):
        return self.panel_vis.get_visible('floating')

    @floating_panel_visible.setter
    def floating_panel_visible(self, value):
        self.panel_vis.set_visible('floating', value)

    window_ctrl = None
    playback_ctrl = None
    epg_ctrl = None
    channel_ctrl = None
    settings_ops = None
    event_handler = None
    ui_ctrl = None
    subscription_ctrl = None
    subscription_ui_ctrl = None
    catchup_ctrl = None
    pip_ctrl = None
    media_ctrl = None
    update_ctrl = None
    multi_screen_ctrl = None
    favorites_ctrl = None
    epg_reminder_ctrl = None
    progress_ctrl = None
    play_state = None
    panel_vis = None

    video_frame = None
    video_widget = None
    video_placeholder = None
    central_widget = None

    status_bar = None
    epg_panel = None
    playlist_panel = None
    floating_panel = None
    top_layout = None
    main_layout = None
    content_layout = None

    # UI 控件 - 信息区
    channel_name = None
    channel_logo = None
    channel_list = None
    group_combo = None
    video_info = None
    audio_info = None
    network_info = None
    buffer_info = None
    current_program = None
    program_desc = None
    time_label = None
    remain_label = None
    catchup_indicator = None

    # UI 控件 - 进度条区
    program_progress = None
    progress_start = None
    progress_end = None

    # UI 控件 - 控制按钮
    play_button = None
    volume_slider = None
    volume_button = None
    speed_button = None
    exit_catchup_button = None
    audio_track_button = None
    sub_track_button = None
    aspect_button = None
    pip_button = None
    fullscreen_button = None
    stop_button = None
    prev_ch_button = None
    next_ch_button = None

    # UI 控件 - EPG 面板
    epg_content = None
    epg_empty_label = None
    epg_date_label = None
    epg_title = None
    epg_prev_day = None
    epg_next_day = None

    # UI 控件 - 播放列表面板
    playlist_title = None
    sub_group_combo = None
    local_group_combo = None
    sub_channel_list = None
    local_channel_list = None
    fav_channel_list = None
    fav_empty_label = None
    history_channel_list = None
    history_empty_label = None

    # UI 控件 - 视频覆盖层
    _video_overlay_label = None

    # UI 控件 - 菜单/快捷键/动作
    recent_menu = None
    _global_search_shortcut = None
    _hide_floating_action = None
    _server_action = None
    _osd_menu_action = None
    _pip_menu_action = None
    _epg_menu_action = None
    _playlist_menu_action = None
    _floating_menu_action = None
    _fullscreen_menu_action = None

    # 标题栏
    _title_bar = None
    _title_label = None
    _title_icon_label = None
    _stay_on_top_btn = None
    _minimize_btn = None
    _maximize_btn = None
    _close_btn = None
    _custom_menu_bar = None
    _main_container = None

    # 定时器与 Dock
    update_timer = None

    epg_dock = None
    playlist_dock = None
    floating_dock = None
    playlist_tab = None
    playlist_list_widget = None
    epg_list_widget = None
    playlist_new_url_edit = None
    playlist_new_name_edit = None
    epg_new_url_edit = None
    epg_new_name_edit = None
    _playlist_add_btn = None
    _epg_add_btn = None

    # 频道数据
    _local_channels: Optional[List[Dict[str, Any]]] = None
    _sub_channels: Optional[List[Dict[str, Any]]] = None
    _local_channels_dirty = False

    # 进度/时移状态
    _progress_total_seconds: float = 3600
    _progress_time_mode: str = 'hour'
    _progress_program_start: Optional[datetime] = None
    _progress_program_end: Optional[datetime] = None
    _initial_position_fixed: bool = False
    _floating_hidden: bool = False
    _osd_visible: bool = False
    _network_base_info: str = ''
    last_catchup_state: bool = False
    _last_epg_refresh: float = 0
    _pending_catchup_progress: float = 0
    _target_catchup_progress: float = 0
    _catchup_start_time: float = 0
    _catchup_start_progress: float = 0
    _timeshift_start_time = None
    _epg_hidden_by_local_file: bool = False

    # 图标加载队列
    _icon_load_set = None
    _icon_load_queue = None
    _icon_load_timer = None

    # 媒体信息缓存
    _last_media_info: Optional[Dict[str, Any]] = None
    _last_info_key: Optional[str] = None

    # 服务/对话框引用
    _thumbnail_service = None
    _scan_dialog = None
    scan_window = None

    PLAYLIST_EXTENSIONS = ('.m3u', '.m3u8', '.txt')
    VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm')
    AUDIO_EXTENSIONS = (
        '.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus',
        '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta',
        '.dts', '.ac3', '.mid', '.midi',
    )
    ALL_DROP_EXTENSIONS = PLAYLIST_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS

    is_fullscreen = False
    _live_timeshift_seconds = 0
    catchup_program: Optional[CatchupProgram] = None
    _suppress_volume_osd = False
    _initialization_complete = False
    _panels_initialized = False
    _ui_initialized = False
    _dragging = False
    _drag_offset = None
    _last_mouse_pos = None
    _editing_playlist_index = -1
    _editing_epg_index = -1
    current_epg_date: Optional[date] = None
    _window_title = ''
    _theme_manager = None

    def __init__(self, parent: Optional[QWidget] = None, flags: Qt.WindowType = Qt.WindowType.Window):
        from utils.general_utils import suppress_urllib3_warnings
        suppress_urllib3_warnings()
        logger.debug("开始初始化 IPTVPlayer")
        super().__init__(parent=parent, flags=flags)

        self._init_config()
        self._init_state()
        self._init_signals()
        self._init_controllers()
        self._init_basic_ui()

        self.setStyleSheet(AppStyles.main_window_style())

        from ui.menu_proxy_style import MenuRoundedProxyStyle
        self._menu_proxy_style = MenuRoundedProxyStyle(self.style())
        self.setStyle(self._menu_proxy_style)

        self._initialize_in_order()

    def _init_config(self):
        """初始化配置、主题、语言、窗口布局"""
        from core.config_manager import ConfigManager
        self.config = ConfigManager()

        from ui.theme_manager import get_theme_manager
        self._theme_manager = get_theme_manager()

        self.language_manager = LanguageManager()
        self.language_manager.load_available_languages()
        saved_language = self.config.load_language_settings()
        self.language_manager.set_language(saved_language)

        from core.version import CURRENT_VERSION
        current_version = CURRENT_VERSION
        self._window_title = f"{self.language_manager.tr('app_title', 'ISEP')} v{current_version}"
        self.setWindowTitle(self._window_title)

        from utils.general_utils import get_icon_path
        ico_path = get_icon_path()
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        x, y, width, height, _ = self.config.load_window_layout(
            default_x=100, default_y=100, default_width=1280, default_height=780
        )
        x, y = self._clamp_window_position(x, y, width, height)
        self.setGeometry(x, y, width, height)
        self.setMinimumSize(800, 600)

    def _init_state(self):
        self._dragging = False
        self._drag_offset = None
        self._last_mouse_pos = None

        self.play_state = PlayStateManager()
        self.panel_vis = PanelVisibilityManager(self)
        self.progress_ctrl = ProgressController(self)
        self.channel_model = ChannelListModel()
        self.current_channel = None
        self.original_channel: Optional[Dict[str, Any]] = None

        self._floating_hidden = False
        self._suppress_volume_osd = False
        self._osd_visible = False
        self.is_fullscreen = False

        from core.subscription_manager import global_subscription_manager
        self.epg_parser = global_subscription_manager

        self.update_timer = None

        self._initialization_complete = False
        self._panels_initialized = False
        self._ui_initialized = False
        self.epg_panel = None
        self.playlist_panel = None
        self.floating_panel = None
        self.video_frame = None
        self.video_widget = None
        self.video_placeholder = None
        self.top_layout = None

        self.status_bar = None


        self.current_epg_date = datetime.now().date()
        self._last_media_info = {}
        self._last_info_key = None

    def _init_signals(self):
        """连接所有信号到槽函数"""
        self.epg_status_signal.connect(self.update_status_bar)
        self.channel_list_updated.connect(self._update_channel_list_ui)
        self.epg_list_updated.connect(self._populate_epg_list)
        self.status_message.connect(self.status_bar_show_message)

    def _init_controllers(self):
        """初始化所有业务控制器"""
        logger.debug("初始化业务控制器...")
        _init_errors = []

        def _safe_init(attr_name, cls, *args):
            try:
                setattr(self, attr_name, cls(self))
            except Exception as e:
                logger.error(f"初始化 {attr_name} 失败: {e}")
                setattr(self, attr_name, None)
                _init_errors.append(attr_name)

        _safe_init('window_ctrl', WindowController)
        _safe_init('playback_ctrl', PlaybackController)
        _safe_init('epg_ctrl', EPGController)
        _safe_init('channel_ctrl', ChannelController)
        _safe_init('settings_ops', SettingsFileOperations)
        _safe_init('event_handler', EventHandler)
        _safe_init('ui_ctrl', UIController)
        _safe_init('subscription_ctrl', SubscriptionController)
        _safe_init('subscription_ui_ctrl', SubscriptionUIController)
        _safe_init('catchup_ctrl', CatchupController)
        _safe_init('pip_ctrl', PipController)
        _safe_init('media_ctrl', MediaController)
        _safe_init('update_ctrl', UpdateController)
        try:
            from controllers.multi_screen_controller import MultiScreenController
            self.multi_screen_ctrl = MultiScreenController(self)
        except Exception as e:
            logger.error(f"初始化多画面控制器失败: {e}")
            self.multi_screen_ctrl = None
            _init_errors.append("多画面")
        _safe_init('favorites_ctrl', FavoritesController)
        _safe_init('epg_reminder_ctrl', EpgReminderController)

        if _init_errors:
            failed_names = "、".join(_init_errors)
            logger.warning(f"部分控制器初始化失败: {failed_names}")
        logger.debug("业务控制器初始化完成")

    def _init_basic_ui(self):
        """创建最基础的UI框架：无边框窗口、容器、标题栏、内容区域"""
        logger.debug("创建最最基本的UI")
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window)
        # Linux 无合成器时逐像素透明会渲染成黑底，先按环境决定初始值，
        # 主题应用时（theme_manager._apply_window_backdrop）会再次校准。
        from utils.platform_utils import has_x11_compositor
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, has_x11_compositor())
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._main_container = _RoundedContainer()
        self._main_container.setObjectName("mainContainer")
        self.setCentralWidget(self._main_container)

        self.main_layout = QVBoxLayout(self._main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._create_custom_title_bar()

        self.central_widget = QWidget()
        self.central_widget.setStyleSheet(AppStyles.player_background_style())
        self.central_widget.setObjectName("contentArea")
        self.main_layout.addWidget(self.central_widget)

        self.content_layout = QVBoxLayout(self.central_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        logger.debug("IPTVPlayer 最小化初始化完成")

    @property
    def pip_mode(self):
        return self.pip_ctrl.is_active

    def _create_custom_title_bar(self):
        """创建自定义标题栏（委托给WindowController）"""
        title_bar = self.window_ctrl.create_custom_title_bar(self._window_title)

        # 保存引用（兼容原有代码）
        self._title_bar = title_bar
        self._title_icon_label = self.window_ctrl._title_icon_label
        self._title_label = self.window_ctrl._title_label
        self._stay_on_top_btn = self.window_ctrl._stay_on_top_btn
        self._minimize_btn = self.window_ctrl._minimize_btn
        self._maximize_btn = self.window_ctrl._maximize_btn
        self._close_btn = self.window_ctrl._close_btn

        # 将标题栏添加到主布局顶部
        self.main_layout.addWidget(self._title_bar)

    def _update_splash(self, message):
        try:
            app = QApplication.instance()
            for widget in app.topLevelWidgets():
                if isinstance(widget, QSplashScreen):
                    widget.showMessage(
                        message,
                        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                        QColor(200, 200, 200))
                    app.processEvents()
                    break
        except Exception:
            pass

    def _initialize_in_order(self):
        """按照顺序执行初始化流程"""

        # 1. 菜单栏、工具栏
        self._update_splash("Loading UI...")
        self._init_video_components()
        # 2. 视频区域
        self._create_video_area()
        # 3. 状态栏
        self._create_status_bar()
        # 4. 播放器
        self._update_splash("Initializing player...")
        _QApp.instance().processEvents()
        self._init_player()
        # 5. 定时器
        self._create_timer()
        # 6-8. 面板延迟创建（窗口show后由 _deferred_create_panels 创建）
        # 9. 最近文件菜单
        self._update_recent_files_menu()
        # 10. 事件过滤器（幂等，只注册一次）
        self._install_event_filters()

        # ---- 所有同步 UI 构建完成，现在显示窗口 ----
        self._update_splash("Loading panels...")
        _QApp.instance().processEvents()
        self.show()

        # 6-8. 延迟创建面板（窗口已显示，避免阻塞首帧）
        self._create_epg_panel(show=False)
        _QApp.instance().processEvents()
        self._create_playlist_panel(show=False)
        _QApp.instance().processEvents()
        self._create_bottom_panel(show=False)
        _QApp.instance().processEvents()

        # 11. 注册清理 / 主题 / 快捷键（轻量，不阻塞）
        from utils.resource_cleaner import register_cleanup
        from services.ffprobe_validator_service import FfprobeStreamValidator
        from services.mpv_validator_service import MpvStreamValidator
        register_cleanup(FfprobeStreamValidator.terminate_all, "ffprobe_validator_terminate_all")
        register_cleanup(MpvStreamValidator.terminate_all, "mpv_validator_terminate_all")

        self._theme_manager.register_window(self)


        # 标记UI初始化完成
        self._ui_initialized = True

        # 12. 窗口首次绘制后：定位悬浮窗并显示面板（一次延迟即可）
        QTimer.singleShot(DelayMs.DEFERRED_INIT, self._deferred_initial_position)

        # 13. 延迟加载数据，确保不阻塞首帧渲染
        def load_data_with_delay():
            self.start_subscription_timers()
            self._populate_channel_list(source='subscription')
            # 默认页签以数据为准：订阅为空而本地有频道时不要停在空订阅页
            if hasattr(self, '_ensure_playlist_tab_has_content'):
                self._ensure_playlist_tab_has_content()

            self._check_for_updates_async()
            self._auto_start_server()

        adaptive_delay = calculate_adaptive_delay(300, 150, 600)
        logger.debug(f"使用自适应延迟: {adaptive_delay}ms")
        QTimer.singleShot(adaptive_delay, load_data_with_delay)


    def _update_channel_list_ui(self):
        try:
            self.populate_channel_list(source='auto')
        except Exception as ex:
            logger.error(f"更新频道列表UI失败: {ex}")

    def status_bar_show_message(self, message, timeout=0):
        """在状态栏显示消息"""
        try:
            if self.status_bar:
                self.status_bar.showMessage(message, timeout)
        except Exception as ex:
            logger.error(f"在状态栏显示消息失败: {ex}")

    def _init_video_components(self):
        """初始化视频相关组件"""

        # 第一步：创建菜单栏
        self._create_menu_bar()


    def _create_menu_bar(self):
        """创建菜单栏"""

        # 菜单栏
        self.setup_menu_bar(skip_recent_files=True)


    def _create_video_area(self):
        """创建视频区域"""

        # 上半部分布局
        self.top_layout = QHBoxLayout()

        # 只创建视频播放区域（不创建悬浮窗）
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet(AppStyles.player_background_style())
        self.video_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.video_frame.customContextMenuRequested.connect(self.media_ctrl.show_video_context_menu)

        # 创建默认背景（空闲态银河壁纸 + 软件图标）
        from utils.general_utils import get_icon_path
        from ui.wallpaper_widget import WallpaperWidget
        ico_path = get_icon_path()
        self.video_placeholder = WallpaperWidget(self.video_frame)
        self.video_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_placeholder.setStyleSheet(AppStyles.player_video_placeholder_style())
        if os.path.exists(ico_path):
            icon = QIcon(ico_path)
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            size = int(256 * dpr)
            pixmap = icon.pixmap(size, size, QIcon.Mode.Normal, QIcon.State.On)
            if not pixmap.isNull():
                pixmap.setDevicePixelRatio(dpr)
                self.video_placeholder.setPixmap(pixmap)
            else:
                self.video_placeholder.setText("")
        else:
            self.video_placeholder.setText("")

        # 创建视频播放窗口（初始隐藏，播放时才显示）
        if sys.platform == 'darwin':
            # macOS上mpv v0.41+不支持wid嵌入，使用vo=libmpv + render API渲染
            from services.mpv_gl_widget import MpvGLWidget
            self.video_widget = MpvGLWidget(self.video_frame)
            self.video_widget.setStyleSheet(AppStyles.player_background_style())
        else:
            self.video_widget = QWidget(self.video_frame)
            self.video_widget.setStyleSheet(AppStyles.player_background_style())
            from utils.platform_utils import is_linux
            needs_native_window = is_linux()
            if needs_native_window:
                self.video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
                self.video_widget.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.video_widget.hide()

        self._video_overlay_label = VideoOverlayBadge(self.video_frame)
        self._video_overlay_label.hide()

        from services.audio_visual_service import AudioVisualWidget
        self._audio_visual_widget = AudioVisualWidget(self.video_frame, player_controller=None)
        self._audio_visual_widget.hide()

        # 添加视频区域到布局
        self.top_layout.addWidget(self.video_frame, 1)
        self.content_layout.addLayout(self.top_layout, 1)


    def _create_status_bar(self):
        """创建状态栏"""

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet(AppStyles.statusbar_style())

        # 永久信息块
        self._status_channel_label = QLabel("")
        self._status_time_label = QLabel("")
        self._status_channel_label.setStyleSheet(AppStyles.status_channel_label_style())
        self._status_time_label.setStyleSheet(AppStyles.status_channel_label_style())
        self.status_bar.addPermanentWidget(self._status_channel_label)
        self.status_bar.addPermanentWidget(self._status_time_label)

        self.status_bar_show_message(self.language_manager.tr("ready", "Ready"))


    def _init_player(self):

        self.player_controller = MpvPlayerController(self.video_widget)
        if hasattr(self, '_audio_visual_widget') and self._audio_visual_widget:
            self.player_controller.audio_visual._widget = self._audio_visual_widget

            self._audio_visual_widget._pc = self.player_controller
        self.player_controller.play_state_changed.connect(self.playback_ctrl.handle_play_state_change)
        self.player_controller.live_media_info_updated.connect(self.on_live_media_info_updated)
        self.player_controller.play_error.connect(self.on_play_error)
        self.player_controller.reconnect_requested.connect(self._on_reconnect_requested)
        self.player_controller.timeshift_continue_requested.connect(self._on_timeshift_continue)
        self.player_controller.thumbnail_captured.connect(self._on_player_thumbnail_captured)
        self.player_controller.file_loaded.connect(self.media_ctrl.apply_video_eq_on_load)
        self.player_controller.file_loaded.connect(self.media_ctrl.apply_audio_eq_on_load)
        # 文件真正加载成功后立即取消源超时看门狗（END_FILE/stop 在各自路径取消）
        self.player_controller.file_loaded.connect(self._cancel_source_timeout)

        # 初始化文件队列控制器（在 player_controller 创建后）
        _init_errors = []
        try:
            from controllers.file_queue_controller import FileQueueController
            self.file_queue_ctrl = FileQueueController(self)
            self.file_queue_ctrl.load_from_config()
        except Exception as e:
            logger.error(f"初始化文件队列控制器失败: {e}")
            self.file_queue_ctrl = None
            _init_errors.append("文件队列")

        # 初始化断点续播控制器（在 player_controller 创建后）
        try:
            from controllers.resume_playback_controller import ResumePlaybackController
            self.resume_ctrl = ResumePlaybackController(self)
        except Exception as e:
            logger.error(f"初始化断点续播控制器失败: {e}")
            self.resume_ctrl = None
            _init_errors.append("断点续播")

        # 初始化播放设置持久化控制器（按 URL 保存音量/字幕轨/音轨/比例/翻转/旋转等）
        try:
            from controllers.playback_settings_controller import PlaybackSettingsController
            self.playback_settings_ctrl = PlaybackSettingsController(self)
        except Exception as e:
            logger.error(f"初始化播放设置持久化控制器失败: {e}")
            self.playback_settings_ctrl = None
            _init_errors.append("播放设置")

        # 初始化跳过片头片尾控制器（仅本地视频文件生效）
        try:
            from controllers.skip_intro_outro_controller import SkipIntroOutroController
            self.skip_intro_outro_ctrl = SkipIntroOutroController(self)
        except Exception as e:
            logger.error(f"初始化跳过片头片尾控制器失败: {e}")
            self.skip_intro_outro_ctrl = None
            _init_errors.append("跳过片头片尾")

        # 初始化动态裁剪黑边服务
        try:
            from services.autocrop_service import AutoCropService
            self.autocrop_service = AutoCropService(self)
        except Exception as e:
            logger.error(f"初始化动态裁剪黑边服务失败: {e}")
            self.autocrop_service = None
            _init_errors.append("裁剪黑边")

        # 初始化撤销/重做栈
        try:
            from services.undo_stack import UndoStack
            self.undo_stack = UndoStack(self)
        except Exception as e:
            logger.error(f"初始化撤销/重做栈失败: {e}")
            self.undo_stack = None
            _init_errors.append("撤销/重做")

        # 初始化切片导出 + GIF 制作服务
        try:
            from services.clip_export_service import ClipExportService
            self.clip_export_service = ClipExportService(self)
        except Exception as e:
            logger.error(f"初始化切片导出服务失败: {e}")
            self.clip_export_service = None
            _init_errors.append("切片导出")

        # 初始化书签与章节控制器（在 player_controller 创建后）
        try:
            from controllers.bookmark_controller import BookmarkController
            self.bookmark_ctrl = BookmarkController(self)
        except Exception as e:
            logger.error(f"初始化书签与章节控制器失败: {e}")
            self.bookmark_ctrl = None
            _init_errors.append("书签")

        # 如果有控制器初始化失败，在状态栏提示用户
        if _init_errors:
            failed_names = "、".join(_init_errors)
            self.status_bar_show_message(f"部分功能初始化失败: {failed_names}（详见日志）")

        from services.logo_cache_service import LogoCacheService
        self._logo_cache_service = LogoCacheService(self)
        self._logo_cache_service.logo_loaded.connect(self._on_logo_cache_loaded)

        from services.thumbnail_service import ThumbnailService
        self._thumbnail_service = ThumbnailService(self)
        self._thumbnail_service.thumbnail_ready.connect(self._on_thumbnail_ready)

        self._source_timeout_timer = None
        self._current_source_index = {}
        self._timeshift_start_time = None

        self._load_last_channel()
        self.media_ctrl.restore_aspect_ratio()

        self.favorites_ctrl.init_service(self.config)
        self.epg_reminder_ctrl.init_service(self.config)
        self._setup_system_tray()


    def _create_timer(self):
        """创建定时器"""


        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_floating_panel_info)
        self.player_controller.playback_position_updated.connect(self._on_playback_position_updated)


    def _install_event_filters(self):
        """安装事件过滤器（幂等：多次调用只生效一次）"""
        if getattr(self, '_event_filters_installed', False):
            logger.debug("_install_event_filters: 已安装，跳过")
            return
        self._event_filters_installed = True

        # 安装事件过滤器
        if self.video_frame:
            self.video_frame.installEventFilter(self)
        if self.video_widget:
            self.video_widget.setMouseTracking(True)
            self.video_widget.installEventFilter(self)
        if self.video_placeholder:
            self.video_placeholder.installEventFilter(self)


        app = QApplication.instance()
        if app:
            app.installEventFilter(self)


    def _populate_channel_list(self, source='subscription'):
        """填充频道列表（带EPG刷新）"""
        self.populate_channel_list(source=source)
        self._populate_epg_list()

    def _populate_epg_list(self):
        """填充EPG列表"""

        # 延迟填充EPG列表，等待EPG数据下载完成
        self.populate_epg_list()


    def _deferred_initial_position(self):
        """窗口首次渲染后的延迟定位：
        1. 先定位三个悬浮 dock（无论可见性）
        2. 再按初始可见性标志 show() 各面板
        3. 同步 video_placeholder / video_widget 到 video_frame 的实际尺寸
        """
        if getattr(self, '_initial_position_fixed', False):
            return
        self._initial_position_fixed = True

        # 1. 定位（_position_floating_docks 已改为不依赖 isVisible）
        self.update_floating_position()

        # 2. 按初始状态决定是否 show
        if getattr(self, 'epg_visible', True) and getattr(self, 'epg_panel', None):
            self.epg_panel.show()
        if getattr(self, 'playlist_visible', True) and getattr(self, 'playlist_panel', None):
            self.playlist_panel.show()
        if getattr(self, 'floating_panel_visible', True) and getattr(self, 'floating_panel', None):
            self.floating_panel.show()

        # 3. 同步视频区域子控件尺寸
        if hasattr(self, 'video_frame') and self.video_frame:
            w, h = self.video_frame.width(), self.video_frame.height()
            if w > 0 and h > 0:
                if hasattr(self, 'video_widget') and self.video_widget:
                    self.video_widget.setGeometry(0, 0, w, h)
                if hasattr(self, 'video_placeholder') and self.video_placeholder:
                    self.video_placeholder.setGeometry(0, 0, w, h)
                if hasattr(self, '_audio_visual_widget') and self._audio_visual_widget \
                        and self._audio_visual_widget.isVisible():
                    self._audio_visual_widget.setGeometry(0, 0, w, h)
                if hasattr(self, '_lyrics_widget') and self._lyrics_widget and self._lyrics_widget.isVisible():
                    self._lyrics_widget.setGeometry(0, 0, w, h)

    def _update_recent_files_menu(self):
        """初始化最近打开文件菜单"""

        # 初始化最近打开文件菜单
        self.update_recent_files_menu()

        self._panels_initialized = True
        self._initialization_complete = True
        self._restart_auto_hide_timer()


    def update_status_bar(self, message):
        """更新状态栏消息"""
        if self.status_bar:
            self.status_bar.showMessage(message)

    def update_status_bar_permanent(self, channel=None, time_info=None):
        """更新状态栏永久信息块"""
        if hasattr(self, '_status_channel_label') and channel is not None:
            self._status_channel_label.setText(channel)
        if hasattr(self, '_status_time_label') and time_info is not None:
            self._status_time_label.setText(time_info)

    def setup_menu_bar(self, skip_recent_files=False):
        self.ui_ctrl.setup_menu_bar(skip_recent_files)



