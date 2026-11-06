import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 注意：这里不再全局注入 PySide6 替身。
# 需要 Qt 的纯逻辑测试在各自文件内调用 tests.qt_stub.ensure_qt_available()，
# 依赖真实 Qt 的冒烟测试则会在缺少依赖时正常跳过，而不是被假模块伪装通过。


class MockMainWindow:
    """模拟 MainWindowProtocol 的最小实现，用于 Mixin 单元测试"""

    def __init__(self):
        self.config = MagicMock()
        self.language_manager = MagicMock()
        self.language_manager.tr = lambda key, default='': default
        self.status_bar = MagicMock()
        self._server_action = MagicMock()
        self._system_tray = MagicMock()
        self._is_hidden_to_tray = False
        self._was_playing_before_tray = False
        self._tray_hidden_docks = []
        self._force_quit = False
        self.player_controller = MagicMock()
        self.player_controller.is_playing = False
        self.player_controller.is_paused = False
        self.update_ctrl = MagicMock()
        self.ui_ctrl = MagicMock()
        self.sub_channel_list = MagicMock()
        self.local_channel_list = MagicMock()
        self._sub_channels = []
        self._local_channels = []
        self.play_state = MagicMock()
        self.play_state.is_catchup_or_timeshift = False
        self.event_handler = MagicMock()
        self.config_manager = MagicMock()
        self.epg_visible = False
        self.playlist_visible = False
        self.floating_panel_visible = False

        self.PLAYLIST_EXTENSIONS = ('.m3u', '.m3u8', '.txt')
        self.VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.webm')
        self.AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta', '.dts', '.ac3', '.mid', '.midi')
        self.ALL_DROP_EXTENSIONS = self.PLAYLIST_EXTENSIONS + self.VIDEO_EXTENSIONS + self.AUDIO_EXTENSIONS

    def status_bar_show_message(self, message, timeout=0):
        if self.status_bar:
            self.status_bar.showMessage(message, timeout)

    def show(self):
        pass

    def hide(self):
        pass

    def activateWindow(self):
        pass

    def raise_(self):
        pass

    def close(self):
        pass

    def setAttribute(self, *args, **kwargs):
        pass

    def setCursor(self, *args, **kwargs):
        pass

    def unsetCursor(self, *args, **kwargs):
        pass

    def cursor(self):
        m = MagicMock()
        m.pos.return_value = MagicMock()
        return m

    def rect(self):
        m = MagicMock()
        m.contains.return_value = True
        return m

    def mapFromGlobal(self, pos):
        return pos

    def mousePressEvent(self, event):
        pass

    def mouseMoveEvent(self, event):
        pass

    def mouseReleaseEvent(self, event):
        pass

    def mouseDoubleClickEvent(self, event):
        pass

    def enterEvent(self, event):
        pass

    def leaveEvent(self, event):
        pass


@pytest.fixture
def mock_main_window():
    return MockMainWindow()