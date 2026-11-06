"""P0 回归测试 - 验证关键修复未被破坏"""
import sys
import os
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

from tests.conftest import MockMainWindow


class TestP0_3_PipPixmapCache:
    """P0-3: PiP 按钮 pixmap 缓存 - paint 事件不应重复加载 QPixmap"""

    def test_pixmap_cached_at_init(self):
        """PipButton 初始化时加载 pixmap 并缓存到 _pixmap_cache"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap), \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            assert btn._widget._pixmap_cache is not None

    def test_paint_event_uses_cache(self):
        """paint_event 使用缓存 pixmap，不调用 QPixmap(path)"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.width.return_value = 22
        mock_pixmap.height.return_value = 22
        mock_pixmap.scaled.return_value = mock_pixmap

        mock_widget = MagicMock()
        mock_widget._pixmap_cache = mock_pixmap
        mock_widget._hovered = False
        mock_widget._size = 40

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            btn._widget._pixmap_cache = mock_pixmap
            btn._widget._hovered = False
            btn._widget._size = 40

            with patch('controllers.pip_controller.QPainter') as mock_painter:
                painter_inst = mock_painter.return_value
                btn._widget.paintEvent(MagicMock())

            # QPixmap should not be called during paint (only at init)
            init_calls = [c for c in mock_qpixmap.call_args_list
                          if c != call('/fake/icon.png')]
            # The key assertion: no new QPixmap(path) calls during paint
            # (init already consumed the first call)
            paint_phase_qpixmap_calls = mock_qpixmap.call_count - 1
            assert paint_phase_qpixmap_calls == 0, \
                f"paintEvent should not call QPixmap, got {paint_phase_qpixmap_calls} extra calls"

    def test_set_icon_same_name_no_reload(self):
        """set_icon 同名不重新加载 pixmap"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            calls_before = mock_qpixmap.call_count

            btn.set_icon('close')
            assert mock_qpixmap.call_count == calls_before, \
                "set_icon with same name should not reload pixmap"

    def test_set_icon_different_name_reloads(self):
        """set_icon 不同名重新加载 pixmap"""
        from controllers.pip_controller import PipButton
        mock_pixmap = MagicMock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.scaled.return_value = mock_pixmap

        with patch('controllers.pip_controller.QWidget'), \
             patch('controllers.pip_controller.QPixmap', return_value=mock_pixmap) as mock_qpixmap, \
             patch('controllers.pip_controller.QRegion'), \
             patch('controllers.pip_controller.QRect'), \
             patch('ui.styles.AppStyles.get_icon', return_value='/fake/icon.png'):
            btn = PipButton('close', 40, None, lambda: None)
            calls_before = mock_qpixmap.call_count

            btn.set_icon('restore')
            assert mock_qpixmap.call_count > calls_before, \
                "set_icon with different name should reload pixmap"


class TestP0_1_VolumeShortcut:
    """P0-1: 音量快捷键委托给 media_ctrl（非 update_ctrl）"""

    def test_adjust_volume_delegates_to_media_ctrl(self):
        """_adjust_volume 调用 media_ctrl._set_volume"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 50

        handler._adjust_volume(10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(60)

    def test_adjust_volume_clamps_to_0_100(self):
        """_adjust_volume 限制音量在 0-100 范围"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 95

        handler._adjust_volume(10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(100)

    def test_adjust_volume_clamps_to_zero(self):
        """_adjust_volume 限制音量下限为 0"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = MagicMock()
        handler.window.media_ctrl._set_volume = MagicMock()
        handler.window.volume_slider = MagicMock()
        handler.window.volume_slider.value.return_value = 5

        handler._adjust_volume(-10)
        handler.window.media_ctrl._set_volume.assert_called_once_with(0)

    def test_adjust_volume_no_media_ctrl_no_crash(self):
        """无 media_ctrl 时不崩溃"""
        from controllers.event_handler import EventHandler
        handler = EventHandler(MagicMock())
        handler.window.media_ctrl = None
        handler._adjust_volume(10)


class TestP0_2_DeadButtonCleanup:
    """P0-2: 控制面板不创建已删除的死按钮"""

    def test_no_audio_track_button(self):
        """不创建 audio_track_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'audio_track_button'), \
            "audio_track_button should not be created (dead button removed in T1.2)"

    def test_no_sub_track_button(self):
        """不创建 sub_track_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'sub_track_button'), \
            "sub_track_button should not be created (dead button removed in T1.2)"

    def test_no_pip_button(self):
        """不创建 pip_button"""
        from mixins.control_panel_mixin import ControlPanelMixin
        host = type('H', (MockMainWindow, ControlPanelMixin), {})()
        host.language_manager = MagicMock()
        host.language_manager.tr = lambda k, d='': d
        host.floating_layout = MagicMock()
        host.CHANNEL_LOGO_WIDTH = 100
        host.CHANNEL_LOGO_HEIGHT = 36
        host.PROGRAM_DESC_HEIGHT = 54
        host.CTRL_BUTTON_WIDTH = 36
        host.CTRL_BUTTON_HEIGHT = 32
        host._create_panel = MagicMock()

        host._create_bottom_panel()
        assert not hasattr(host, 'pip_button'), \
            "pip_button should not be created (dead button removed in T1.2)"