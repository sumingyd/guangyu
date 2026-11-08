"""空闲停绘控制器（Qt 侧）。

作用：在窗口最小化/被遮挡，或"未播放 + 无面板 + 长时间无输入"时，统一把
高频 UI 定时器降频（``slow``）或直接停止（``stop``）；恢复时按原间隔重启，
并立即触发一次重绘/刷新，避免残留半帧或明显跳变。

约束：
  * 只动 UI 定时器，绝不触碰 mpv 渲染、音频与播放状态机；
  * 判定逻辑在 :mod:`core.idle_policy`，本模块只负责采样与执行；
  * 每个定时器可单独指定策略，默认 ``stop``；状态栏/时间类用 ``slow`` 保活。

可观测性：进入/退出空闲各打一条 INFO 日志，并维护
``enter_count`` / ``exit_count`` / ``paused_timers`` 供 UI 或测试读取。
"""

import os
import time

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from core.idle_policy import IdlePolicy, IdleSnapshot
from core.log_manager import global_logger as logger

__all__ = ['IdleRenderController', 'POLICY_STOP', 'POLICY_SLOW']

POLICY_STOP = 'stop'
POLICY_SLOW = 'slow'

_INPUT_EVENTS = {
    QEvent.Type.KeyPress,
    QEvent.Type.KeyRelease,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.MouseMove,
    QEvent.Type.Wheel,
    QEvent.Type.ContextMenu,
}
if hasattr(QEvent.Type, 'TouchBegin'):
    _INPUT_EVENTS.add(QEvent.Type.TouchBegin)

_WINDOW_STATE_EVENTS = {
    QEvent.Type.Show,
    QEvent.Type.Hide,
    QEvent.Type.WindowStateChange,
}


class _TimerEntry:
    __slots__ = ('name', 'timer', 'resolver', 'policy', 'idle_interval_ms',
                 'saved_interval_ms', 'was_active', 'on_idle', 'on_active')

    def __init__(self, name, timer=None, resolver=None, policy=POLICY_STOP,
                 idle_interval_ms=None, on_idle=None, on_active=None):
        self.name = name
        self.timer = timer
        self.resolver = resolver
        self.policy = policy if policy in (POLICY_STOP, POLICY_SLOW) else POLICY_STOP
        self.idle_interval_ms = idle_interval_ms
        self.saved_interval_ms = None
        self.was_active = False
        self.on_idle = on_idle
        self.on_active = on_active

    def resolve(self):
        if self.timer is not None:
            return self.timer
        if self.resolver is not None:
            try:
                self.timer = self.resolver()
            except Exception as e:
                logger.debug(f"[idle] 解析定时器 {self.name} 失败: {e}")
                return None
        return self.timer


class IdleRenderController(QObject):
    """采样窗口/播放/输入状态，统一下调 UI 刷新频率。"""

    def __init__(self, window, idle_after_seconds=None, poll_interval_ms=1000,
                 occluded_confirm_seconds=5.0, parent=None):
        super().__init__(parent or window)
        if idle_after_seconds is None:
            idle_after_seconds = self._env_idle_after()
        self._window = window
        self._policy = IdlePolicy(idle_after_seconds, occluded_confirm_seconds)
        self._entries = {}
        self._last_input_ts = time.monotonic()
        self._idle = False
        self._reason = 'active'
        self._started = False
        # 显式 hold：屏保等"自己就是动画源"的模块激活时，禁止本控制器
        # 把全局 UI 定时器判定为空闲并降频/停止。
        self._hold_reasons = {}
        # 可观测计数器：测试/日志可直接读取
        self.enter_count = 0
        self.exit_count = 0
        self.paused_timers = 0

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(200, int(poll_interval_ms)))
        self._poll_timer.timeout.connect(self._evaluate)

        self._last_snapshot = None

    # ---- 公共 API ----
    @property
    def is_idle(self) -> bool:
        return self._idle

    @property
    def is_held(self) -> bool:
        """是否有模块显式 hold（hold 期间不会进入空闲停绘）。"""
        return bool(self._hold_reasons)

    @property
    def idle_after_seconds(self) -> float:
        return self._policy.idle_after_seconds

    def get_status(self) -> dict:
        return {
            'idle': self._idle,
            'reason': self._reason,
            'held': sorted(self._hold_reasons),
            'enter_count': self.enter_count,
            'exit_count': self.exit_count,
            'paused_timers': self.paused_timers,
            'registered': sorted(self._entries),
        }

    def hold(self, reason='external'):
        """显式阻止空闲停绘（如屏保激活时自己需要持续刷新）。

        引用计数，可被多个模块同时 hold；hold 期间若已处于空闲会立刻恢复，
        并让后续 ``_evaluate`` 直接返回。
        """
        self._hold_reasons[reason] = self._hold_reasons.get(reason, 0) + 1
        if len(self._hold_reasons) == 1:
            if self._idle:
                self._apply_active(f'hold:{reason}')
            else:
                self._reason = f'hold:{reason}'
            logger.info(f"[idle] 暂停空闲判定 hold={reason}")

    def release(self, reason='external'):
        """解除 hold；全部解除后重新开始空闲计时，避免立刻又进入空闲。"""
        count = self._hold_reasons.get(reason, 0)
        if count <= 0:
            return
        if count == 1:
            self._hold_reasons.pop(reason, None)
        else:
            self._hold_reasons[reason] = count - 1
        if not self._hold_reasons:
            self._last_input_ts = time.monotonic()
            self._policy.reset()
            self._reason = 'active'
            logger.info(f"[idle] 恢复空闲判定 hold={reason}")

    def register_timer(self, name, timer, policy=POLICY_STOP, idle_interval_ms=None):
        """注册一个已存在的定时器。重复注册同名会覆盖旧配置。"""
        self._entries[name] = _TimerEntry(
            name, timer=timer, policy=policy, idle_interval_ms=idle_interval_ms)
        if self._idle:
            # 空闲期间新增的定时器同样要立刻降频/停止
            self._quiesce(self._entries[name])
        return timer

    def register_lazy(self, name, resolver, policy=POLICY_STOP, idle_interval_ms=None):
        """注册延迟创建的定时器（如按需创建的歌词组件）。"""
        self._entries[name] = _TimerEntry(
            name, resolver=resolver, policy=policy, idle_interval_ms=idle_interval_ms)
        return self._entries[name]

    def register_callbacks(self, name, on_idle=None, on_active=None):
        entry = self._entries.get(name)
        if entry is None:
            entry = _TimerEntry(name)
            self._entries[name] = entry
        entry.on_idle = on_idle
        entry.on_active = on_active

    def note_activity(self):
        """标记一次用户输入；空闲中会立即恢复刷新。"""
        self._last_input_ts = time.monotonic()
        if self._idle:
            self._apply_active('input')

    def start(self):
        if self._started:
            return
        self._started = True
        app = QApplication.instance()
        if app is not None:
            try:
                app.installEventFilter(self)
            except Exception:
                pass
        self._poll_timer.start()
        logger.info(f"[idle] 空闲停绘已启用（阈值 {self._policy.idle_after_seconds:.0f}s，"
                    f"轮询 {self._poll_timer.interval()}ms）")

    def shutdown(self, restore=True):
        """停止控制器。

        ``restore=False`` 用于应用退出：只还原定时器间隔，不重启任何定时器，
        避免在 mpv 已终止后又被唤醒去访问播放句柄。
        """
        if not self._started:
            return
        self._started = False
        self._poll_timer.stop()
        self._hold_reasons.clear()
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        if restore:
            self._apply_active('shutdown')
        else:
            for entry in self._entries.values():
                timer = entry.resolve()
                if timer is None or entry.saved_interval_ms is None:
                    continue
                try:
                    timer.setInterval(entry.saved_interval_ms)
                except RuntimeError:
                    pass
                entry.saved_interval_ms = None
                entry.was_active = False
            self._idle = False
            self.paused_timers = 0
        logger.info(f"[idle] 空闲停绘已关闭（进入 {self.enter_count} 次 / 退出 {self.exit_count} 次）")

    # ---- 内部：采样与切换 ----
    @staticmethod
    def _env_idle_after():
        raw = os.environ.get('GUANGYU_IDLE_AFTER', '').strip()
        try:
            value = float(raw)
            if value >= 0:
                return value
        except (TypeError, ValueError):
            pass
        return 60.0

    def _sample(self):
        window = self._window
        try:
            visible = bool(window.isVisible()) and not bool(window.isMinimized())
        except RuntimeError:
            return IdleSnapshot(False, False, False, False, 0.0)
        exposed = True
        if visible:
            try:
                handle = window.windowHandle()
                if handle is not None:
                    exposed = bool(handle.isExposed())
            except RuntimeError:
                exposed = True
        playing = False
        try:
            pc = getattr(window, 'player_controller', None)
            if pc is not None:
                playing = bool(getattr(pc, 'is_playing', False)) and not bool(
                    getattr(pc, 'is_paused', False))
        except Exception:
            playing = False
        now = time.monotonic()
        return IdleSnapshot(
            window_visible=visible,
            window_exposed=exposed,
            playing=playing,
            panels_open=self._panels_open(),
            seconds_since_input=now - self._last_input_ts,
        )

    def _panels_open(self):
        for attr in ('epg_panel', 'playlist_panel', 'floating_panel'):
            widget = getattr(self._window, attr, None)
            try:
                if widget is not None and widget.isVisible():
                    return True
            except RuntimeError:
                continue
        return False

    def _evaluate(self):
        if not self._started:
            return
        if self._hold_reasons:
            # 屏保等动画源在运行：不做空闲判定，也不降频任何定时器
            return
        snapshot = self._sample()
        self._last_snapshot = snapshot
        decision = self._policy.evaluate(snapshot, time.monotonic())
        if decision.idle and not self._idle:
            self._apply_idle(decision.reason)
        elif not decision.idle and self._idle:
            self._apply_active(decision.reason)
        elif self._idle:
            # 空闲期间按需创建的定时器（如歌词组件）也要立即降频/停止，
            # 否则用户暂停后打开新面板会漏掉一个 60fps 定时器。
            self._quiesce_lazy_entries()

    def _quiesce_lazy_entries(self):
        for entry in list(self._entries.values()):
            if entry.timer is not None or entry.resolver is None:
                continue
            if entry.resolver() is None:
                continue
            self._quiesce(entry)

    def _apply_idle(self, reason):
        self._idle = True
        self._reason = reason
        self.enter_count += 1
        paused = []
        for entry in self._entries.values():
            if self._quiesce(entry):
                paused.append(entry.name)
        self.paused_timers = len(paused)
        snapshot = self._last_snapshot
        logger.info(
            f"[idle] 进入空闲停绘 reason={reason} 窗口可见={getattr(snapshot, 'window_visible', None)} "
            f"暴露={getattr(snapshot, 'window_exposed', None)} 播放={getattr(snapshot, 'playing', None)} "
            f"面板={getattr(snapshot, 'panels_open', None)} "
            f"无输入={getattr(snapshot, 'seconds_since_input', 0.0):.0f}s 降频/停止={paused}"
        )

    def _apply_active(self, reason):
        was_idle = self._idle
        self._idle = False
        self._reason = reason
        if was_idle:
            self.exit_count += 1
        for entry in self._entries.values():
            self._wake(entry)
        self.paused_timers = 0
        if was_idle:
            logger.info(f"[idle] 退出空闲停绘 reason={reason}，恢复正常刷新")

    def _quiesce(self, entry) -> bool:
        timer = entry.resolve()
        if timer is None:
            return False
        try:
            entry.saved_interval_ms = timer.interval()
            entry.was_active = timer.isActive()
            if entry.policy == POLICY_STOP:
                if entry.was_active:
                    timer.stop()
                    self._safe_callback(entry.on_idle)
                    return True
                return False
            idle_interval = entry.idle_interval_ms or max(1000, int(entry.saved_interval_ms * 10))
            if entry.was_active:
                timer.setInterval(idle_interval)
                self._safe_callback(entry.on_idle)
                return True
            return False
        except RuntimeError:
            self._entries.pop(entry.name, None)
            return False
        except Exception as e:
            logger.debug(f"[idle] 降频定时器 {entry.name} 失败: {e}")
            return False

    def _wake(self, entry):
        timer = entry.resolve()
        if timer is None:
            return
        try:
            if entry.saved_interval_ms is not None:
                timer.setInterval(entry.saved_interval_ms)
                entry.saved_interval_ms = None
            if entry.policy == POLICY_STOP and entry.was_active and not timer.isActive():
                timer.start()
            if entry.was_active:
                self._safe_callback(entry.on_active)
            entry.was_active = False
        except RuntimeError:
            self._entries.pop(entry.name, None)
        except Exception as e:
            logger.debug(f"[idle] 恢复定时器 {entry.name} 失败: {e}")

    @staticmethod
    def _safe_callback(callback):
        if callback is None:
            return
        try:
            callback()
        except Exception as e:
            logger.debug(f"[idle] 回调执行失败: {e}")

    # ---- 事件过滤：用户输入 / 窗口显隐 ----
    def eventFilter(self, obj, event):
        try:
            etype = event.type()
        except Exception:
            return False
        if etype in _INPUT_EVENTS:
            self._last_input_ts = time.monotonic()
            if self._idle:
                self._apply_active('input')
        elif etype in _WINDOW_STATE_EVENTS and obj is self._window:
            # 最小化/恢复/显示/隐藏后立刻重算，不等下一轮轮询
            QTimer.singleShot(0, self._evaluate)
        return False
