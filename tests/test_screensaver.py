"""屏保控制器与覆盖层测试（离屏）。

覆盖：
  * 配置默认值/非法值回退；
  * 进入条件（开关、播放、面板、对话框、输入超时）；
  * 退出条件（按键/鼠标移动/播放/隐藏）与"退出这一下输入被吞掉"；
  * 与空闲停绘的 hold/release 协调；
  * EPG 严格 ``[start, stop)`` 匹配；
  * 覆盖层真实绘制冒烟。
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal  # noqa: E402
from PySide6.QtGui import QCursor, QKeyEvent, QKeySequence, QShortcutEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from controllers.screensaver_controller import (  # noqa: E402
    ScreenSaverController, parse_enabled, parse_minutes,
)
from ui.screensaver_widget import ScreenSaverWidget  # noqa: E402


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


class _PlayerStub:
    is_playing = False
    is_paused = False


class _ConfigStub:
    def __init__(self, values=None):
        self.values = values or {}

    def get_value(self, section, key, default=None):
        return self.values.get((section, key), default)


class _EpgStub:
    def __init__(self, programs):
        self.programs = programs

    def get_channel_epg(self, *_args, **_kwargs):
        return list(self.programs)


class _IdleStub:
    def __init__(self):
        self.hold_calls = 0
        self.release_calls = 0
        self.activity_calls = 0

    def hold(self, reason):
        self.hold_calls += 1

    def release(self, reason):
        self.release_calls += 1

    def note_activity(self):
        self.activity_calls += 1


class _WindowStub(QWidget):
    def __init__(self, programs=None):
        super().__init__()
        self.player_controller = _PlayerStub()
        self.epg_panel = None
        self.playlist_panel = None
        self.floating_panel = None
        self.config = _ConfigStub()
        self.language_manager = None
        self.current_channel = {'name': 'CCTV-1'}
        self.epg_parser = _EpgStub(programs or [])
        self._idle_render = _IdleStub()
        self._audio_visual_widget = None

    def _get_epg_match_params(self):
        return 'CCTV-1', '', '', ''


class _NullCollector(QObject):
    """测试用空采集器：不发数据、不碰真实音频设备。"""

    bars_ready = Signal(list)
    failed = Signal(str)

    def start(self):
        pass

    def stop(self, *args, **kwargs):
        pass


def _make(window, widget, collector_factory=_NullCollector):
    ctrl = ScreenSaverController(window, widget, require_exposed=False,
                                 poll_interval_ms=60000,
                                 collector_factory=collector_factory)
    ctrl.start()
    return ctrl


def _expire_input(ctrl, seconds=600):
    ctrl._last_input_ts = time.monotonic() - seconds


@pytest.fixture
def env(app):
    window = _WindowStub()
    window.resize(640, 360)
    window.show()
    widget = ScreenSaverWidget(window)
    widget.hide()
    ctrl = _make(window, widget)
    try:
        yield window, widget, ctrl
    finally:
        ctrl.shutdown()
        widget.hide()
        window.hide()


def test_parse_config_values():
    assert parse_enabled('true') is True
    assert parse_enabled('false') is False
    assert parse_enabled(None, True) is True
    assert parse_enabled('garbage', True) is True
    assert parse_minutes('30') == 30
    assert parse_minutes('7') == 5
    assert parse_minutes('abc') == 5
    assert parse_minutes(None) == 5


def test_defaults_enabled_five_minutes(env):
    _window, _widget, ctrl = env
    assert ctrl.enabled is True
    assert ctrl.minutes == 5
    assert ctrl.is_active is False


def test_enter_after_timeout_and_hold_idle_render(env):
    window, widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active
    assert widget.is_active()
    assert window._idle_render.hold_calls == 1
    assert ctrl.get_status()['texts']['channel_text'] == 'CCTV-1'


def test_recent_input_blocks_entry(env):
    _window, _widget, ctrl = env
    ctrl._evaluate()
    assert ctrl.is_active is False


def test_playing_blocks_entry(env):
    window, _widget, ctrl = env
    window.player_controller.is_playing = True
    window.player_controller.is_paused = False
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active is False

    window.player_controller.is_playing = False
    window.player_controller.is_paused = True
    ctrl._evaluate()
    assert ctrl.is_active is True, '暂停状态应允许进入屏保'


def test_panel_and_dialog_block_entry(env):
    window, _widget, ctrl = env
    panel = QWidget(window)
    panel.show()
    window.epg_panel = panel
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active is False
    panel.hide()

    dialog = QDialog(window)
    dialog.show()
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active is False
    dialog.hide()


def test_key_press_exits_and_is_swallowed(env):
    window, _widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active

    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    assert ctrl.eventFilter(window, press) is True, '退出这一下按键必须被吞掉'
    assert ctrl.is_active is False
    assert ctrl.exit_count == 1
    assert window._idle_render.release_calls == 1

    release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    assert ctrl.eventFilter(window, release) is True, '配对的 KeyRelease 也要吞掉'

    # 退出后的新按键必须正常下发给快捷键
    again = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    assert ctrl.eventFilter(window, again) is False


def test_shortcut_override_exits_and_swallows_following_press(env):
    """真实键盘路径：ShortcutOverride 先于 KeyPress，两者都必须被吞掉。"""
    window, _widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active

    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_E,
                         Qt.KeyboardModifier.NoModifier)
    override.ignore()
    assert ctrl.eventFilter(window, override) is True
    assert override.isAccepted(), '必须显式 accept，避免被快捷键系统消费'
    assert ctrl.is_active is False

    press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
    assert ctrl.eventFilter(window, press) is True, 'ShortcutOverride 后的 KeyPress 必须吞掉'
    release = QKeyEvent(QEvent.Type.KeyRelease, Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier)
    assert ctrl.eventFilter(window, release) is True


def test_shortcut_event_right_after_exit_is_suppressed(env):
    """退出瞬间由同一按键派生的 Shortcut（如 Ctrl+M）不能被放行。"""
    window, _widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active

    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_M,
                         Qt.KeyboardModifier.ControlModifier)
    assert ctrl.eventFilter(window, override) is True
    assert ctrl.is_active is False

    shortcut = QShortcutEvent(QKeySequence('Ctrl+M'), 1)
    assert ctrl.eventFilter(window, shortcut) is True, '保护窗口内必须吞掉快捷键事件'

    ctrl._suppress_shortcut_until = time.monotonic() - 1
    later = QShortcutEvent(QKeySequence('Ctrl+Y'), 2)
    assert ctrl.eventFilter(window, later) is False, '保护窗口过后恢复正常分发'


def test_controller_filter_jumps_ahead_of_later_filters(env):
    """主窗口的 app 过滤器若晚于控制器安装，激活后必须仍被控制器抢先。"""
    app = QApplication.instance()
    window, _widget, ctrl = env

    class _LateFilter(QObject):
        def __init__(self):
            super().__init__()
            self.keys = 0

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.KeyPress:
                self.keys += 1
            return False

    late = _LateFilter()
    app.installEventFilter(late)
    try:
        _expire_input(ctrl)
        ctrl._evaluate()  # 激活时会重新安装，移到过滤器链最前
        assert ctrl.is_active

        press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right,
                          Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, press)
        assert ctrl.is_active is False
        assert late.keys == 0, '退出按键不能落到后安装的主窗口过滤器'

        normal = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left,
                           Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, normal)
        assert late.keys == 1, '屏保未激活时事件应正常下发'
    finally:
        app.removeEventFilter(late)


def test_mouse_move_exits_when_cursor_moves(env):
    window, _widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active
    ctrl._cursor_origin = QCursor.pos() + QPoint(120, 120)
    ctrl._evaluate()
    assert ctrl.is_active is False
    assert ctrl.get_status()['reason'] == 'input'


def test_playback_and_hidden_window_exit(env):
    window, _widget, ctrl = env
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active
    window.player_controller.is_playing = True
    ctrl._evaluate()
    assert ctrl.is_active is False
    assert ctrl.get_status()['reason'] == 'playing'

    window.player_controller.is_playing = False
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active
    window.hide()
    ctrl._evaluate()
    assert ctrl.is_active is False
    assert ctrl.get_status()['reason'] == 'hidden'


def test_disabled_config_stops_entry_and_active(env):
    window, _widget, ctrl = env
    window.config.values[('ScreenSaver', 'enabled')] = 'false'
    window.config.values[('ScreenSaver', 'idle_minutes')] = '10'
    ctrl.reload_config()
    assert ctrl.enabled is False and ctrl.minutes == 10
    _expire_input(ctrl)
    ctrl._evaluate()
    assert ctrl.is_active is False

    window.config.values[('ScreenSaver', 'enabled')] = 'true'
    ctrl.reload_config()
    ctrl._evaluate()
    assert ctrl.is_active
    window.config.values[('ScreenSaver', 'enabled')] = 'false'
    ctrl.reload_config()
    assert ctrl.is_active is False


def test_epg_strict_interval(env):
    now = datetime.now().replace(microsecond=0)
    programs = [
        # 已结束（end == now 必须被排除）
        {'title': '刚刚结束', 'start': (now - timedelta(minutes=30)).isoformat(),
         'end': now.isoformat()},
        # 当前节目
        {'title': '正在播出', 'start': (now - timedelta(minutes=10)).isoformat(),
         'end': (now + timedelta(minutes=20)).isoformat()},
    ]
    window = _WindowStub(programs=programs)
    widget = ScreenSaverWidget(window)
    ctrl = _make(window, widget)
    try:
        channel, title, time_range = ctrl._current_program(now)
        assert channel == 'CCTV-1'
        assert title == '正在播出'
        assert ' - ' in time_range
    finally:
        ctrl.shutdown()
        widget.hide()
        window.hide()


def test_borrow_real_spectrum_snapshot(env):
    window, _widget, ctrl = env
    assert ctrl._borrow_bars() is None

    class _Visual:
        _smooth_bars = [0.0] * 64

    visual = _Visual()
    window._audio_visual_widget = visual
    assert ctrl._borrow_bars() is None, '全零快照不得作为频谱'

    visual._smooth_bars = [0.5] * 64
    borrowed = ctrl._borrow_bars()
    assert borrowed is not None and len(borrowed) == 64


def test_widget_paints_offscreen(env):
    _window, widget, _ctrl = env
    widget.set_context(clock_text='12:34', date_text='2026-11-09 星期一',
                       channel_text='CCTV-1', program_text='新闻联播',
                       range_text='19:00 - 19:30')
    widget.resize(640, 360)
    widget.set_static_bars([0.4] * 48)
    widget.show()
    try:
        image = widget.grab()
        assert not image.isNull()
        assert image.width() == 640 and image.height() == 360
    finally:
        widget.hide()
