"""PC 屏保控制器：进入/退出状态机 + 文本上下文刷新。

与 Android 端对齐的进入条件：
  * 开关开启（``ScreenSaver.enabled``）；
  * 主窗口可见（且未被最小化/完全遮挡）；
  * 没有正在出画面的播放（暂停/停止可进入）；
  * 没有任何面板 / 对话框打开；
  * 距最后一次用户输入超过设定时长（``ScreenSaver.idle_minutes``）。

退出：任意键、鼠标移动/点击、触摸。退出时这一下输入会被本过滤器吞掉，
不会再交给主窗口的快捷键分发（避免顺带切台或 seek）。

与空闲停绘（:mod:`core.idle_render`）的协调：屏保激活期间调用
``IdleRenderController.hold('screensaver')``，让空闲判定暂停；退出时
``release`` 并重置输入时间，避免刚退出就又被判为空闲。
"""

import time
from datetime import datetime

from PySide6.QtCore import QEvent, QLocale, QObject, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from core.idle_policy import IdlePolicy, IdleSnapshot
from core.log_manager import global_logger as logger
from services.loopback_spectrum_service import (
    LoopbackSpectrumCollector,
    REASON_UNSUPPORTED,
    platform_supported,
)

__all__ = ['ScreenSaverController', 'parse_enabled', 'parse_minutes',
           'VALID_MINUTES', 'DEFAULT_MINUTES']

CONFIG_SECTION = 'ScreenSaver'
KEY_ENABLED = 'enabled'
KEY_IDLE_MINUTES = 'idle_minutes'
VALID_MINUTES = (1, 5, 10, 30, 60)
DEFAULT_MINUTES = 5
DEFAULT_ENABLED = True

_INPUT_EVENTS = {
    QEvent.Type.KeyPress,
    QEvent.Type.KeyRelease,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.MouseMove,
    QEvent.Type.Wheel,
    QEvent.Type.ContextMenu,
}
for _name in ('TouchBegin', 'TouchEnd', 'TouchUpdate'):
    if hasattr(QEvent.Type, _name):
        _INPUT_EVENTS.add(getattr(QEvent.Type, _name))

_SWALLOW_WINDOW_SECONDS = 2.0


def parse_enabled(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off'):
        return False
    return default


def parse_minutes(value, default=DEFAULT_MINUTES):
    try:
        minutes = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return minutes if minutes in VALID_MINUTES else default


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


class ScreenSaverController(QObject):
    def __init__(self, window, widget=None, parent=None,
                 require_exposed=True, poll_interval_ms=1000,
                 collector_factory=None):
        super().__init__(parent or window)
        self._window = window
        self._widget = widget
        # 离屏测试环境没有真实曝光状态，可显式关闭该要求
        self._require_exposed = bool(require_exposed)
        # 测试注入点：返回带 start/stop 与 bars_ready/failed 信号的对象
        self._collector_factory = collector_factory
        self._spectrum = None
        self._spectrum_source = 'none'
        self._spectrum_degraded_reason = ''
        self._spectrum_warned = set()

        self._enabled = DEFAULT_ENABLED
        self._minutes = DEFAULT_MINUTES
        self._policy = IdlePolicy(DEFAULT_MINUTES * 60, occluded_confirm_seconds=5.0)

        self._started = False
        self._active = False
        self._reason = 'inactive'
        self._last_input_ts = time.monotonic()
        self._cursor_origin = QCursor.pos()
        self._swallow_key_release = False
        self._swallow_mouse_release = False
        self._swallow_next_press = False
        self._suppress_shortcut_until = 0.0
        self._swallow_at = 0.0
        self._status_texts = {}

        # 可观测计数器
        self.enter_count = 0
        self.exit_count = 0

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(200, int(poll_interval_ms)))
        self._poll_timer.timeout.connect(self._evaluate)

    # ---- 公共 API ----
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def minutes(self) -> int:
        return self._minutes

    def get_status(self) -> dict:
        return {
            'active': self._active,
            'enabled': self._enabled,
            'minutes': self._minutes,
            'reason': self._reason,
            'enter_count': self.enter_count,
            'exit_count': self.exit_count,
            'texts': dict(self._status_texts),
            # 采集中断原因仅用于日志/调试，不弹窗、不写状态栏
            'spectrum_source': self._spectrum_source,
            'spectrum_degraded_reason': self._spectrum_degraded_reason,
        }

    def start(self):
        if self._started:
            return
        self._started = True
        self.reload_config()
        app = QApplication.instance()
        if app is not None:
            try:
                # 后安装者先收到事件：确保屏保激活时能抢在主窗口之前吞掉输入
                app.installEventFilter(self)
            except Exception:
                pass
        self._last_input_ts = time.monotonic()
        self._poll_timer.start()
        logger.info(f"[screensaver] 已启用（开关={self._enabled} 等待={self._minutes} 分钟）")

    def shutdown(self):
        if not self._started:
            return
        self._started = False
        self._poll_timer.stop()
        if self._active:
            self._deactivate('shutdown')
        else:
            # 兜底：即使状态机已不是激活态，也确保没有遗留的采集线程/设备
            self._stop_spectrum()
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        logger.info(f"[screensaver] 已关闭（进入 {self.enter_count} 次 / 退出 {self.exit_count} 次）")

    def reload_config(self):
        config = getattr(self._window, 'config', None)
        if config is None:
            return
        try:
            raw_enabled = config.get_value(CONFIG_SECTION, KEY_ENABLED, 'true')
            raw_minutes = config.get_value(CONFIG_SECTION, KEY_IDLE_MINUTES, str(DEFAULT_MINUTES))
        except Exception as e:
            logger.debug(f"[screensaver] 读取配置失败: {e}")
            return
        self._enabled = parse_enabled(raw_enabled, DEFAULT_ENABLED)
        self._minutes = parse_minutes(raw_minutes, DEFAULT_MINUTES)
        self._policy.idle_after_seconds = float(self._minutes * 60)
        if not self._enabled and self._active:
            self._deactivate('disabled')

    def note_activity(self):
        self._last_input_ts = time.monotonic()
        if self._active:
            self._deactivate('input')

    # ---- 事件过滤：输入即退出，并吞掉这一下输入 ----
    def eventFilter(self, obj, event):
        try:
            etype = event.type()
        except Exception:
            return False

        # Qt 在 KeyPress 之前会先发 ShortcutOverride：主窗口会在这里认领
        # E/L/M/Y/方向键等快捷键。屏保激活时必须先吞掉它，否则按键会先被
        # 快捷键系统消费（可能直接切台/seek），屏保反而收不到 KeyPress。
        if etype in (QEvent.Type.ShortcutOverride, QEvent.Type.Shortcut):
            now = time.monotonic()
            if not self._active:
                # 退出瞬间可能仍有同一物理按键派生出的 Shortcut（如 Ctrl+M），
                # 在很短的保护窗口内一并吞掉，避免顺带最小化/关闭窗口。
                if etype == QEvent.Type.Shortcut and now < self._suppress_shortcut_until:
                    return True
                return False
            self._last_input_ts = now
            if etype == QEvent.Type.ShortcutOverride:
                try:
                    event.accept()
                except Exception:
                    pass
            # 无论后续是否还有 KeyPress，都吞掉并标记配对释放
            self._swallow_next_press = True
            self._swallow_key_release = True
            self._suppress_shortcut_until = now + 0.5
            self._swallow_at = now
            self._deactivate('input')
            return True

        if etype not in _INPUT_EVENTS:
            if etype == QEvent.Type.WindowStateChange and obj is self._window:
                QTimer.singleShot(0, self._evaluate)
            return False

        now = time.monotonic()
        self._last_input_ts = now

        if etype == QEvent.Type.KeyPress and self._swallow_next_press:
            if now - self._swallow_at <= _SWALLOW_WINDOW_SECONDS:
                self._swallow_next_press = False
                return True
            self._swallow_next_press = False

        # 退出时被吞掉的按下事件，其配对的释放事件也要吞掉，
        # 否则释放会落到下面的控件上（例如按钮/快捷键）。
        if etype == QEvent.Type.KeyRelease and self._swallow_key_release:
            if now - self._swallow_at <= _SWALLOW_WINDOW_SECONDS:
                self._swallow_key_release = False
                if self._active:
                    self._deactivate('input')
                return True
            self._swallow_key_release = False
        if etype == QEvent.Type.MouseButtonRelease and self._swallow_mouse_release:
            if now - self._swallow_at <= _SWALLOW_WINDOW_SECONDS:
                self._swallow_mouse_release = False
                if self._active:
                    self._deactivate('input')
                return True
            self._swallow_mouse_release = False

        if not self._active:
            return False

        if etype == QEvent.Type.MouseMove and not self._cursor_moved():
            # 覆盖层刚出现时的位置抖动不算用户操作，但仍吞掉避免穿透
            return True

        self._deactivate('input')
        if etype == QEvent.Type.KeyPress:
            self._swallow_key_release = True
            self._swallow_at = now
        elif etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            self._swallow_mouse_release = True
            self._swallow_at = now
        return True

    # ---- 内部：判定 ----
    def _window_state(self):
        window = self._window
        try:
            if not window.isVisible() or window.isMinimized():
                return False, False
        except RuntimeError:
            return False, False
        exposed = True
        try:
            handle = window.windowHandle()
            if handle is not None:
                exposed = bool(handle.isExposed())
        except RuntimeError:
            exposed = True
        return True, exposed

    def _playing(self):
        try:
            pc = getattr(self._window, 'player_controller', None)
            if pc is None:
                return False
            return bool(getattr(pc, 'is_playing', False)) and not bool(getattr(pc, 'is_paused', False))
        except Exception:
            return False

    def _panels_open(self):
        for attr in ('epg_panel', 'playlist_panel', 'floating_panel'):
            widget = getattr(self._window, attr, None)
            try:
                if widget is not None and widget.isVisible():
                    return True
            except RuntimeError:
                continue
        return False

    def _dialog_open(self):
        app = QApplication.instance()
        if app is None:
            return False
        try:
            if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
                return True
        except Exception:
            pass
        for widget in app.topLevelWidgets():
            if widget is self._window:
                continue
            try:
                if widget.isVisible() and isinstance(widget, (QDialog, QMenu)):
                    return True
            except RuntimeError:
                continue
        return False

    def _cursor_moved(self):
        try:
            return (QCursor.pos() - self._cursor_origin).manhattanLength() > 2
        except Exception:
            return False

    def _evaluate(self):
        if not self._started:
            return
        if not self._enabled:
            if self._active:
                self._deactivate('disabled')
            return

        visible, exposed = self._window_state()
        if not visible:
            if self._active:
                self._deactivate('hidden')
            return

        if self._active:
            self._evaluate_active(exposed)
            return

        if self._require_exposed and not exposed:
            return
        if self._dialog_open() or self._panels_open() or self._playing():
            return

        now = time.monotonic()
        snapshot = IdleSnapshot(
            window_visible=True,
            window_exposed=True,
            playing=False,
            panels_open=False,
            seconds_since_input=now - self._last_input_ts,
        )
        decision = self._policy.evaluate(snapshot, now)
        if decision.idle:
            self._activate(decision.reason)

    def _evaluate_active(self, exposed):
        if self._require_exposed and not exposed:
            self._deactivate('occluded')
            return
        if self._dialog_open():
            self._deactivate('dialog')
            return
        if self._panels_open():
            self._deactivate('panel')
            return
        if self._playing():
            self._deactivate('playing')
            return
        if self._cursor_moved():
            self._deactivate('input')
            return
        self._refresh_context()

    # ---- 内部：进入/退出 ----
    def _activate(self, reason):
        self._active = True
        self._reason = reason
        self.enter_count += 1
        self._cursor_origin = QCursor.pos()
        self._swallow_key_release = False
        self._swallow_mouse_release = False
        self._swallow_next_press = False
        self._suppress_shortcut_until = 0.0
        # 主窗口的 app 级 eventFilter 可能晚于本控制器安装（安装越晚越先收到
        # 事件）。激活时重新安装一次，把自己移到过滤器链最前端，确保输入先
        # 被屏保吞掉，不会触发切台/seek。
        app = QApplication.instance()
        if app is not None:
            try:
                app.installEventFilter(self)
            except Exception:
                pass
        widget = self._widget
        if widget is not None:
            try:
                widget.set_static_bars(self._borrow_bars())
                widget.set_context(**self._build_context())
                widget.start()
            except Exception as e:
                logger.error(f"[screensaver] 显示屏保失败: {e}")
                self._active = False
                return
        idle_render = getattr(self._window, '_idle_render', None)
        if idle_render is not None:
            try:
                # 屏保自己是动画源：显式阻止空闲停绘把刷新掐掉
                idle_render.hold('screensaver')
            except Exception as e:
                logger.debug(f"[screensaver] hold 空闲停绘失败: {e}")
        # 屏保已显示后再启动采集：采集失败/初始化慢都不会拖住进入过程
        self._start_spectrum()
        logger.info(f"[screensaver] 进入 reason={reason} 等待={self._minutes}分钟")

    def _deactivate(self, reason):
        if not self._active:
            return
        self._active = False
        self._reason = reason
        self.exit_count += 1
        # 先停采集并释放设备，再隐藏覆盖层：退出后不再有任何后台音频读取
        self._stop_spectrum()
        self._spectrum_source = 'none'
        widget = self._widget
        if widget is not None:
            try:
                widget.stop()
            except Exception as e:
                logger.debug(f"[screensaver] 隐藏失败: {e}")
        idle_render = getattr(self._window, '_idle_render', None)
        if idle_render is not None:
            try:
                idle_render.release('screensaver')
                idle_render.note_activity()
            except Exception as e:
                logger.debug(f"[screensaver] 恢复空闲停绘失败: {e}")
        self._last_input_ts = time.monotonic()
        self._policy.reset()
        logger.info(f"[screensaver] 退出 reason={reason}")

    # ---- 内部：文本上下文 ----
    def _refresh_context(self, now=None):
        widget = self._widget
        if widget is None:
            return
        try:
            widget.set_context(**self._build_context(now))
        except Exception as e:
            logger.debug(f"[screensaver] 刷新文本失败: {e}")

    def _build_context(self, now=None):
        now = now or datetime.now()
        channel_name, program_title, time_range = self._current_program(now)
        texts = {
            'clock_text': now.strftime('%H:%M'),
            'date_text': f"{now:%Y-%m-%d} {self._weekday_name(now)}",
            'channel_text': channel_name or self._tr('screensaver_no_channel', '未选择频道'),
            'program_text': program_title or self._tr('screensaver_no_program', '暂无节目信息'),
            'range_text': time_range,
        }
        self._status_texts = texts
        return texts

    @staticmethod
    def _weekday_name(now):
        try:
            return QLocale().dayName(now.isoweekday(), QLocale.FormatType.LongFormat)
        except Exception:
            return ''

    def _current_program(self, now):
        """返回 (频道名, 当前节目名, 时段)。

        严格按 ``start <= now < stop`` 匹配；结束时刻的那一秒不再属于该节目，
        与 ``get_current_program`` 的闭区间语义区分开。
        """
        window = self._window
        channel = getattr(window, 'current_channel', None)
        channel_name = ''
        if isinstance(channel, dict):
            channel_name = str(channel.get('name') or '').strip()
        parser = getattr(window, 'epg_parser', None)
        if parser is None or not hasattr(parser, 'get_channel_epg'):
            return channel_name, '', ''
        try:
            params = window._get_epg_match_params() if hasattr(window, '_get_epg_match_params') else ()
            params = list(params) + ['', '', '', '']
            programs = parser.get_channel_epg(
                params[0], params[1], tvg_name=params[2], comma_name=params[3])
        except Exception as e:
            logger.debug(f"[screensaver] 读取 EPG 失败: {e}")
            return channel_name, '', ''
        for program in programs or []:
            start = _parse_datetime(program.get('start'))
            end = _parse_datetime(program.get('end'))
            if start is None or end is None:
                continue
            if start <= now < end:
                title = str(program.get('title') or '').strip()
                return channel_name, title, f"{start:%H:%M} - {end:%H:%M}"
        return channel_name, '', ''

    def _borrow_bars(self):
        """借用现有音频可视化的频谱快照；无有效数据时返回 None（走慢波动降级）。"""
        widget = getattr(self._window, '_audio_visual_widget', None)
        if widget is None:
            try:
                widget = self._window.player_controller.audio_visual.get_visual_widget()
            except Exception:
                widget = None
        bars = getattr(widget, '_smooth_bars', None) if widget is not None else None
        if bars is None:
            return None
        try:
            values = [float(v) for v in list(bars)]
        except (TypeError, ValueError):
            return None
        if not values or max(values) < 0.02:
            return None
        return values

    # ---- 内部：实时频谱采集（严格限制在屏保激活期间） ----
    def _start_spectrum(self):
        """激活后启动一次采集；失败一律降级，不阻塞屏保显示。"""
        self._spectrum_source = 'none'
        self._spectrum_degraded_reason = ''
        self._spectrum_warned = set()
        self._stop_spectrum()

        if self._collector_factory is not None:
            try:
                collector = self._collector_factory()
            except Exception as e:
                logger.debug(f"[screensaver] 创建采集器失败: {e}")
                self._degrade_spectrum('init_failed')
                return
        elif not platform_supported():
            # 非 Windows：导入期判定，不创建线程、不探测设备
            self._degrade_spectrum(REASON_UNSUPPORTED)
            return
        else:
            try:
                collector = LoopbackSpectrumCollector(parent=self)
            except Exception as e:
                logger.debug(f"[screensaver] 创建采集器失败: {e}")
                self._degrade_spectrum('init_failed')
                return

        self._spectrum = collector
        try:
            collector.bars_ready.connect(self._on_spectrum_bars)
            collector.failed.connect(self._on_spectrum_failed)
            collector.start()
        except Exception as e:
            logger.debug(f"[screensaver] 启动采集失败: {e}")
            self._stop_spectrum()
            self._degrade_spectrum('init_failed')

    def _stop_spectrum(self):
        """停止并释放采集器；任何释放异常都不会抛到调用方。"""
        collector = self._spectrum
        self._spectrum = None
        if collector is None:
            return
        try:
            collector.stop(join_timeout=0.8)
        except TypeError:
            try:
                collector.stop()
            except Exception as e:
                logger.debug(f"[screensaver] 停止采集失败: {e}")
        except Exception as e:
            logger.debug(f"[screensaver] 停止采集失败: {e}")
        # 采集线程仍活着（例如驱动调用卡住）时不要销毁对象，避免悬空信号
        if not getattr(collector, 'is_running', False):
            try:
                collector.deleteLater()
            except Exception:
                pass

    def _on_spectrum_bars(self, bars):
        """采集线程 -> UI 线程：校验屏保仍激活且控件存活后才写柱高。"""
        if not self._active or self._spectrum is None:
            return
        widget = self._widget
        if widget is None:
            return
        try:
            if not widget.is_active():
                return
            widget.set_live_bars(bars)
        except RuntimeError:
            return
        except Exception as e:
            logger.debug(f"[screensaver] 更新实时频谱失败: {e}")
            return
        if self._spectrum_source != 'loopback':
            self._spectrum_source = 'loopback'
            self._spectrum_degraded_reason = ''
            logger.debug('[screensaver] 实时频谱已连接 loopback')

    def _on_spectrum_failed(self, reason):
        if not self._active:
            return
        self._degrade_spectrum(reason)

    def _degrade_spectrum(self, reason):
        """失败矩阵的统一出口：一次会话内同一原因码只记一条 WARNING。"""
        reason = str(reason or 'unknown')
        self._spectrum_source = 'none'
        self._spectrum_degraded_reason = reason
        if reason in self._spectrum_warned:
            logger.debug(f"[screensaver] 实时频谱仍不可用 reason={reason}（本会话已记录）")
            return
        self._spectrum_warned.add(reason)
        logger.warning(f"[screensaver] 实时频谱不可用，降级为静态频谱 reason={reason}")

        widget = self._widget
        if widget is None or not self._active:
            return
        try:
            # 先更新降级底图，再触发约 300ms 的交叉淡入
            widget.set_static_bars(self._borrow_bars())
            widget.set_live_bars(None)
        except Exception as e:
            logger.debug(f"[screensaver] 频谱降级过渡失败: {e}")

    def _tr(self, key, default):
        try:
            manager = getattr(self._window, 'language_manager', None)
            if manager is not None:
                return manager.tr(key, default)
        except Exception:
            pass
        return default
