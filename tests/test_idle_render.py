"""空闲停绘控制器的 Qt 冒烟测试（离屏，无需真实显示）。

验证：
  * 窗口不可见时进入空闲，``stop`` 策略的定时器被停、``slow`` 策略被降频；
  * 用户输入触发恢复，定时器间隔/运行状态还原；
  * 计数器与 shutdown(restore=False) 不唤醒定时器。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from core.idle_render import IdleRenderController, POLICY_SLOW, POLICY_STOP  # noqa: E402


@pytest.fixture(scope='module')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


class _PlayerStub:
    is_playing = False
    is_paused = False


class _WindowStub(QWidget):
    def __init__(self):
        super().__init__()
        self.player_controller = _PlayerStub()
        self.epg_panel = None
        self.playlist_panel = None
        self.floating_panel = None


def _make_controller(window, **kwargs):
    kwargs.setdefault('idle_after_seconds', 0)
    kwargs.setdefault('occluded_confirm_seconds', 0)
    kwargs.setdefault('poll_interval_ms', 60000)  # 手动驱动，避免测试等待
    return IdleRenderController(window, **kwargs)


def test_idle_stops_and_slows_timers_then_input_restores(app):
    window = _WindowStub()  # 不 show -> window_visible=False -> 立即空闲
    stop_timer = QTimer(window)
    stop_timer.setInterval(1000)
    stop_timer.start()
    slow_timer = QTimer(window)
    slow_timer.setInterval(40)
    slow_timer.start()
    calls = {'pause': 0, 'resume': 0}

    ctrl = _make_controller(window)
    ctrl.register_timer('stop_me', stop_timer, policy=POLICY_STOP)
    ctrl.register_timer('slow_me', slow_timer, policy=POLICY_SLOW, idle_interval_ms=500)
    ctrl.register_callbacks('slow_me', on_idle=lambda: calls.__setitem__('pause', calls['pause'] + 1),
                            on_active=lambda: calls.__setitem__('resume', calls['resume'] + 1))
    ctrl.start()
    try:
        ctrl._evaluate()
        assert ctrl.is_idle
        assert not stop_timer.isActive()
        assert slow_timer.interval() == 500
        assert calls == {'pause': 1, 'resume': 0}
        assert ctrl.enter_count == 1

        ctrl.note_activity()
        assert not ctrl.is_idle
        assert stop_timer.isActive()
        assert slow_timer.interval() == 40
        assert calls == {'pause': 1, 'resume': 1}
        assert ctrl.exit_count == 1
    finally:
        ctrl.shutdown()


def test_playing_window_stays_active(app):
    window = _WindowStub()
    window.show()
    window.player_controller.is_playing = True
    window.player_controller.is_paused = False
    timer = QTimer(window)
    timer.setInterval(100)
    timer.start()

    ctrl = _make_controller(window, occluded_confirm_seconds=999)
    ctrl.register_timer('t', timer, policy=POLICY_STOP)
    ctrl.start()
    try:
        ctrl._evaluate()
        assert not ctrl.is_idle
        assert timer.isActive()
    finally:
        ctrl.shutdown()
        window.hide()


def test_open_panel_keeps_active(app):
    window = _WindowStub()
    window.show()
    panel = QWidget(window)
    panel.show()
    window.epg_panel = panel

    ctrl = _make_controller(window, occluded_confirm_seconds=999)
    ctrl.start()
    try:
        ctrl._evaluate()
        assert not ctrl.is_idle
    finally:
        ctrl.shutdown()
        panel.hide()
        window.hide()


def test_shutdown_without_restore_does_not_restart_timers(app):
    window = _WindowStub()
    timer = QTimer(window)
    timer.setInterval(1000)
    timer.start()

    ctrl = _make_controller(window)
    ctrl.register_timer('t', timer, policy=POLICY_STOP)
    ctrl.start()
    ctrl._evaluate()
    assert ctrl.is_idle and not timer.isActive()

    ctrl.shutdown(restore=False)
    assert not timer.isActive(), '退出流程不应唤醒指向播放句柄的定时器'
    assert timer.interval() == 1000, '间隔仍需还原，便于下次启动'


def test_lazy_timer_is_registered_after_creation(app):
    window = _WindowStub()
    holder = {}

    def resolver():
        return holder.get('timer')

    ctrl = _make_controller(window)
    ctrl.register_lazy('lazy', resolver, policy=POLICY_STOP)
    ctrl.start()
    try:
        ctrl._evaluate()
        assert ctrl.is_idle
        timer = QTimer(window)
        timer.setInterval(200)
        timer.start()
        holder['timer'] = timer
        # 空闲期间新建的定时器要下一轮才被处理（模拟按需创建歌词）
        ctrl._evaluate()
        assert not timer.isActive()
    finally:
        ctrl.shutdown()


def test_status_snapshot_is_observable(app):
    window = _WindowStub()
    ctrl = _make_controller(window)
    ctrl.register_timer('a', QTimer(window), policy=POLICY_STOP)
    status = ctrl.get_status()
    assert status['idle'] is False
    assert status['registered'] == ['a']
    assert {'enter_count', 'exit_count', 'paused_timers', 'reason'} <= set(status)
