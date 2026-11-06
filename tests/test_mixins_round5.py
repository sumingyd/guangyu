import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from mixins.control_panel_mixin import ControlPanelMixin
from mixins.playlist_panel_mixin import PlaylistPanelMixin
from mixins.event_mixin import EventMixin
from mixins.progress_mixin import ProgressMixin
from tests.conftest import MockMainWindow


class _ControlPanelTestHost(MockMainWindow, ControlPanelMixin, ProgressMixin):
    pass


class _PlaylistPanelTestHost(MockMainWindow, PlaylistPanelMixin):
    pass


class _EventTestHost(EventMixin, MockMainWindow):
    pass


class TestControlPanelMixin:
    def setup_method(self):
        self.host = _ControlPanelTestHost()
        self.host.language_manager = MagicMock()
        self.host.language_manager.tr = lambda k, d='': d
        self.host.floating_layout = MagicMock()
        self.host.CHANNEL_LOGO_WIDTH = 100
        self.host.CHANNEL_LOGO_HEIGHT = 36
        self.host.PROGRAM_DESC_HEIGHT = 54
        self.host.CTRL_BUTTON_WIDTH = 36
        self.host.CTRL_BUTTON_HEIGHT = 32

    def test_create_bottom_panel(self):
        self.host._create_panel = MagicMock()
        self.host._create_bottom_panel(show=False)
        self.host._create_panel.assert_called_once_with(show=False)

    def test_create_bottom_panel_default_show(self):
        self.host._create_panel = MagicMock()
        self.host._create_bottom_panel()
        self.host._create_panel.assert_called_once_with(show=True)

    def test_set_info_label_icon_no_path(self):
        icon_label = MagicMock()
        with patch('mixins.control_panel_mixin.AppStyles.get_icon', return_value=None):
            self.host._set_info_label_icon(icon_label, 'tv')
        icon_label.setPixmap.assert_not_called()

    def test_set_info_label_icon_with_pixmap(self):
        icon_label = MagicMock()
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        with patch('mixins.control_panel_mixin.AppStyles.get_icon', return_value='/fake/path.png'), \
             patch('mixins.control_panel_mixin.QPixmap', return_value=mock_pixmap):
            self.host._set_info_label_icon(icon_label, 'tv')
        icon_label.setPixmap.assert_called_once()

    def test_set_info_label_icon_null_pixmap(self):
        icon_label = MagicMock()
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = True
        with patch('mixins.control_panel_mixin.AppStyles.get_icon', return_value='/fake/path.png'), \
             patch('mixins.control_panel_mixin.QPixmap', return_value=mock_pixmap):
            self.host._set_info_label_icon(icon_label, 'tv')
        icon_label.setPixmap.assert_not_called()

    def test_create_media_row_calls_info_row(self):
        self.host._set_info_label_icon = MagicMock()
        self.host._create_info_row = MagicMock()
        with patch('mixins.control_panel_mixin.QHBoxLayout', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QLabel', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QFrame') as mock_frame:
            mock_frame.return_value = MagicMock()
            with patch('mixins.control_panel_mixin.AppStyles.player_media_badge_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_hdr_badge_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_line_style', return_value=''):
                self.host._create_media_row()
        self.host._create_info_row.assert_called_once()

    def test_create_info_row_calls_control_row(self):
        self.host._create_control_row = MagicMock()
        with patch('mixins.control_panel_mixin.QHBoxLayout', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QVBoxLayout', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QLabel', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.ElidedLabel', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QWidget', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QFrame') as mock_frame:
            mock_frame.return_value = MagicMock()
            with patch('mixins.control_panel_mixin.AppStyles.player_channel_logo_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_channel_name_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_program_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_time_badge_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_catchup_indicator_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_status_badge_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_program_desc_style', return_value=''), \
                 patch('mixins.control_panel_mixin.AppStyles.player_line_style', return_value=''), \
                 patch('utils.general_utils.set_default_channel_logo'):
                self.host._create_info_row()
        self.host._create_control_row.assert_called_once()

    def test_create_control_row_creates_buttons(self):
        self.host.toggle_play = MagicMock()
        self.host.stop_playback = MagicMock()
        self.host.event_handler = MagicMock()
        self.host.on_progress_slider_released = MagicMock()
        self.host._on_progress_slider_pressed = MagicMock()
        self.host._on_progress_preview = MagicMock()
        self.host.toggle_mute = MagicMock()
        self.host.set_volume = MagicMock()
        self.host.exit_catchup = MagicMock()
        self.host.media_ctrl = MagicMock()
        self.host.pip_ctrl = MagicMock()
        self.host.toggle_fullscreen = MagicMock()
        with patch('mixins.control_panel_mixin.QHBoxLayout', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QToolButton') as mock_btn, \
             patch('mixins.control_panel_mixin.QLabel', return_value=MagicMock()), \
             patch('mixins.control_panel_mixin.QSlider') as mock_slider, \
             patch('mixins.control_panel_mixin.QSize'), \
             patch('mixins.control_panel_mixin.QIcon'), \
             patch('ui.cache_progress_slider.CacheProgressSlider') as mock_cps, \
             patch('mixins.control_panel_mixin.AppStyles._get_colors', return_value={'player_panel_text': '#fff', 'player_cache_bar': 'rgba(0,0,0,0)'}), \
             patch('mixins.control_panel_mixin.AppStyles._safe_fallback', return_value='#fff'), \
             patch('mixins.control_panel_mixin.AppStyles.get_icon', return_value='/fake/icon.png'), \
             patch('mixins.control_panel_mixin.AppStyles.player_button_style', return_value=''), \
             patch('mixins.control_panel_mixin.AppStyles.player_progress_label_style', return_value=''), \
             patch('mixins.control_panel_mixin.AppStyles.player_slider_style', return_value=''), \
             patch('mixins.control_panel_mixin.AppStyles.player_volume_slider_style', return_value=''), \
             patch('mixins.control_panel_mixin.AppStyles.player_menu_bar_style', return_value=''), \
             patch('mixins.control_panel_mixin.QMenu'):
            mock_btn.return_value = MagicMock()
            mock_slider.return_value = MagicMock()
            mock_cps.return_value = MagicMock()
            self.host._create_control_row()
        assert mock_btn.call_count > 0


class TestPlaylistPanelMixin:
    def setup_method(self):
        self.host = _PlaylistPanelTestHost()
        self.host.language_manager = MagicMock()
        self.host.language_manager.tr = lambda k, d='': d
        self.host.favorites_ctrl = MagicMock()
        self.host._on_channel_single_click = MagicMock()
        self.host._on_channel_double_clicked = MagicMock()
        self.host._on_sub_channel_context_menu = MagicMock()
        self.host._on_local_channel_context_menu = MagicMock()
        self.host._on_sub_search_changed = MagicMock()
        self.host._on_local_search_changed = MagicMock()
        self.host._set_channel_view_mode = MagicMock()
        self.host._capture_visible_thumbnails = MagicMock()
        self.host._populate_channel_list_for = MagicMock()
        self.host._deferred_single_click = MagicMock()

    def test_create_channel_list_widget(self):
        with patch('mixins.playlist_panel_mixin.AppStyles.player_list_style', return_value=''), \
             patch('ui.multi_screen_widget.DraggableChannelListWidget') as mock_widget:
            mock_widget.return_value = MagicMock()
            widget = self.host._create_channel_list_widget()
        assert widget is not None

    def test_create_channel_list_widget_with_callbacks(self):
        on_click = MagicMock()
        on_dbl = MagicMock()
        on_ctx = MagicMock()
        with patch('mixins.playlist_panel_mixin.AppStyles.player_list_style', return_value=''), \
             patch('ui.multi_screen_widget.DraggableChannelListWidget') as mock_widget:
            mock_widget.return_value = MagicMock()
            widget = self.host._create_channel_list_widget(
                on_click=on_click, on_double_click=on_dbl, on_context_menu=on_ctx
            )
        assert widget is not None

    def test_create_channel_search_row(self):
        with patch('mixins.playlist_panel_mixin.QHBoxLayout', return_value=MagicMock()), \
             patch('mixins.playlist_panel_mixin.QLineEdit', return_value=MagicMock()), \
             patch('mixins.playlist_panel_mixin.QToolButton', return_value=MagicMock()), \
             patch('mixins.playlist_panel_mixin.QButtonGroup', return_value=MagicMock()), \
             patch('mixins.playlist_panel_mixin.AppStyles.player_search_input_style', return_value=''), \
             patch('mixins.playlist_panel_mixin.AppStyles.player_button_style', return_value=''), \
             patch('mixins.playlist_panel_mixin.AppStyles.get_icon', return_value='/fake/icon.png'):
            result = self.host._create_channel_search_row(
                self.host.language_manager.tr, '#fff', MagicMock(), 'sub'
            )
        assert len(result) == 5

    def test_switch_playlist_tab(self):
        self.host.playlist_tab = MagicMock()
        btn1 = MagicMock()
        btn2 = MagicMock()
        self.host._playlist_tab_btns = [btn1, btn2]
        self.host._switch_playlist_tab(1)
        self.host.playlist_tab.setCurrentIndex.assert_called_once_with(1)
        btn2.setChecked.assert_called_once_with(True)

    def test_on_playlist_tab_changed_sub(self):
        btn1 = MagicMock()
        self.host._playlist_tab_btns = [btn1]
        self.host.sub_channel_list = MagicMock()
        self.host.sub_channel_list.viewMode.return_value = 0
        self.host.sub_group_combo = MagicMock()
        self.host.sub_empty_label = MagicMock()
        self.host._on_playlist_tab_changed(0)
        assert self.host.channel_list is self.host.sub_channel_list

    def test_on_playlist_tab_changed_local(self):
        btn1 = MagicMock()
        self.host._playlist_tab_btns = [btn1]
        self.host.local_channel_list = MagicMock()
        self.host.local_channel_list.viewMode.return_value = 0
        self.host.local_group_combo = MagicMock()
        self.host.local_empty_label = MagicMock()
        self.host._on_playlist_tab_changed(1)
        assert self.host.channel_list is self.host.local_channel_list

    def test_on_playlist_tab_changed_fav(self):
        btn1 = MagicMock()
        self.host._playlist_tab_btns = [btn1]
        self.host._on_playlist_tab_changed(2)
        self.host.favorites_ctrl.populate_favorites_tab.assert_called_once()

    def test_on_playlist_tab_changed_history(self):
        btn1 = MagicMock()
        self.host._playlist_tab_btns = [btn1]
        self.host._on_playlist_tab_changed(3)
        self.host.favorites_ctrl.populate_history_tab.assert_called_once()

    def test_on_sub_group_changed(self):
        self.host.sub_channel_list = MagicMock()
        self.host.sub_channel_list.viewMode.return_value = 0
        self.host._sub_channels = []
        self.host.on_sub_group_changed('All')
        self.host._populate_channel_list_for.assert_called_once()

    def test_on_local_group_changed(self):
        self.host.local_channel_list = MagicMock()
        self.host.local_channel_list.viewMode.return_value = 0
        self.host._local_channels = []
        self.host.on_local_group_changed('All')
        self.host._populate_channel_list_for.assert_called_once()


class TestEventMixin:
    def setup_method(self):
        self.host = _EventTestHost()
        self.host.is_fullscreen = False
        self.host.pip_mode = False
        self.host.pip_ctrl = MagicMock()
        self.host.window_ctrl = MagicMock()
        self.host.event_handler = MagicMock()
        self.host.settings_ops = MagicMock()
        self.host.ALL_DROP_EXTENSIONS = ('.m3u', '.m3u8', '.txt', '.mp4', '.mkv')
        self.host.PLAYLIST_EXTENSIONS = ('.m3u', '.m3u8', '.txt')
        self.host.VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi')
        self.host._add_local_video_and_track = MagicMock()

    def test_mouse_press_event_not_fullscreen(self):
        event = MagicMock()
        self.host.window_ctrl.handle_mouse_press_event.return_value = False
        self.host.update_floating_position = MagicMock()
        self.host.mousePressEvent(event)
        self.host.window_ctrl.handle_mouse_press_event.assert_called_once()

    def test_mouse_press_event_fullscreen(self):
        self.host.is_fullscreen = True
        self.host._on_mouse_activity = MagicMock()
        event = MagicMock()
        self.host.window_ctrl.handle_mouse_press_event.return_value = True
        self.host.mousePressEvent(event)
        self.host._on_mouse_activity.assert_called_once()

    def test_mouse_press_event_pip(self):
        self.host.pip_mode = True
        self.host.pip_ctrl.handle_mouse_press.return_value = True
        event = MagicMock()
        self.host.mousePressEvent(event)
        self.host.pip_ctrl.handle_mouse_press.assert_called_once()

    def test_drag_enter_event_accept(self):
        event = MagicMock()
        url = MagicMock()
        url.toLocalFile.return_value = 'test.m3u'
        event.mimeData.return_value.hasUrls.return_value = True
        event.mimeData.return_value.urls.return_value = [url]
        self.host.dragEnterEvent(event)
        event.acceptProposedAction.assert_called_once()

    def test_drag_enter_event_reject(self):
        event = MagicMock()
        event.mimeData.return_value.hasUrls.return_value = False
        self.host.dragEnterEvent(event)
        event.ignore.assert_called_once()

    def test_drag_move_event_accept(self):
        event = MagicMock()
        event.mimeData.return_value.hasUrls.return_value = True
        self.host.dragMoveEvent(event)
        event.acceptProposedAction.assert_called_once()

    def test_drag_move_event_reject(self):
        event = MagicMock()
        event.mimeData.return_value.hasUrls.return_value = False
        self.host.dragMoveEvent(event)
        event.ignore.assert_called_once()

    def test_drop_event_playlist(self):
        event = MagicMock()
        url = MagicMock()
        url.toLocalFile.return_value = 'test.m3u'
        event.mimeData.return_value.urls.return_value = [url]
        self.host.dropEvent(event)
        event.acceptProposedAction.assert_called_once()
        self.host.settings_ops.open_specific_file.assert_called_once_with('test.m3u')

    def test_drop_event_video(self):
        event = MagicMock()
        url = MagicMock()
        url.toLocalFile.return_value = 'test.mp4'
        event.mimeData.return_value.urls.return_value = [url]
        self.host.dropEvent(event)
        event.acceptProposedAction.assert_called_once()
        self.host._add_local_video_and_track.assert_called_once_with('test.mp4')

    def test_drop_event_ignore(self):
        event = MagicMock()
        url = MagicMock()
        url.toLocalFile.return_value = 'test.xyz'
        event.mimeData.return_value.urls.return_value = [url]
        self.host.dropEvent(event)
        event.ignore.assert_called_once()

    def test_fix_win32_drag_drop_non_win32(self):
        with patch('mixins.event_mixin.sys') as mock_sys:
            mock_sys.platform = 'linux'
            self.host._fix_win32_drag_drop()

    def test_mouse_move_event(self):
        event = MagicMock()
        self.host.window_ctrl.handle_mouse_move_event.return_value = False
        self.host.mouseMoveEvent(event)
        self.host.window_ctrl.handle_mouse_move_event.assert_called_once()

    def test_mouse_move_event_fullscreen(self):
        self.host.is_fullscreen = True
        self.host._on_mouse_activity = MagicMock()
        event = MagicMock()
        self.host.window_ctrl.handle_mouse_move_event.return_value = True
        self.host.mouseMoveEvent(event)
        self.host._on_mouse_activity.assert_called_once()

    def test_mouse_release_event(self):
        event = MagicMock()
        self.host.mouseReleaseEvent(event)
        self.host.window_ctrl.handle_mouse_release_event.assert_called_once()

    def test_mouse_double_click_event_pip(self):
        self.host.pip_mode = True
        event = MagicMock()
        self.host.mouseDoubleClickEvent(event)

    def test_wheel_event(self):
        self.host.is_fullscreen = False
        event = MagicMock()
        event.angleDelta.return_value.y.return_value = 120
        self.host.wheelEvent(event)
        self.host.event_handler._adjust_volume.assert_called_once_with(5)

    def test_wheel_event_negative(self):
        event = MagicMock()
        event.angleDelta.return_value.y.return_value = -120
        self.host.wheelEvent(event)
        self.host.event_handler._adjust_volume.assert_called_once_with(-5)

    def test_wheel_event_pip(self):
        self.host.pip_mode = True
        event = MagicMock()
        self.host.wheelEvent(event)
        self.host.event_handler._adjust_volume.assert_not_called()

    def test_enter_event_normal(self):
        event = MagicMock()
        self.host._show_floating_panels_on_enter = MagicMock()
        self.host.enterEvent(event)
        self.host._show_floating_panels_on_enter.assert_called_once()

    def test_enter_event_pip(self):
        self.host.pip_mode = True
        event = MagicMock()
        self.host.enterEvent(event)
        self.host.pip_ctrl.show_overlay.assert_called_once()

    def test_leave_event_normal(self):
        event = MagicMock()
        self.host._delayed_hide_floating_panels = MagicMock()
        with patch('mixins.event_mixin.safe_single_shot') as mock_shot:
            self.host.leaveEvent(event)
            mock_shot.assert_called_once_with(50, self.host, self.host._delayed_hide_floating_panels)

    def test_leave_event_pip(self):
        self.host.pip_mode = True
        event = MagicMock()
        with patch('mixins.event_mixin.safe_single_shot') as mock_shot:
            self.host.leaveEvent(event)
        mock_shot.assert_called_once_with(50, self.host, self.host.pip_ctrl.delayed_hide_overlay)
