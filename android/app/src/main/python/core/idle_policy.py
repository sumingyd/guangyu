"""空闲停绘（idle render）纯逻辑策略。

把"当前是否进入空闲"的判定抽成不依赖 Qt 的状态机，便于单测与复用
（Android 端可参考同一套判定）。

判定口径（任一成立即视为空闲）：

1. 主窗口不可见 / 已最小化 —— 立刻空闲（UI 定时器不需要画）；
2. 主窗口被完全遮挡持续 ``occluded_confirm_seconds`` —— 空闲；
3. 窗口可见但"没有正在播放"（暂停/停止/未起播）、无任何面板打开，
   且距最后一次用户输入超过 ``idle_after_seconds`` —— 空闲。

注意：``playing`` 传"真正在推进播放"的状态；暂停时调用方应传 False。
这样暂停后经过一段时间才会停绘，不会一暂停就画面停更。
"""

from dataclasses import dataclass

__all__ = ['IdleSnapshot', 'IdleDecision', 'IdlePolicy']

_REASON_HIDDEN = 'hidden'
_REASON_OCCLUDED = 'occluded'
_REASON_INACTIVE = 'inactive'
_REASON_ACTIVE = 'active'


@dataclass(frozen=True)
class IdleSnapshot:
    """一次采样得到的窗口/播放/输入状态。"""

    window_visible: bool
    window_exposed: bool
    playing: bool
    panels_open: bool
    seconds_since_input: float

    def __post_init__(self):
        if self.seconds_since_input < 0:
            object.__setattr__(self, 'seconds_since_input', 0.0)


@dataclass(frozen=True)
class IdleDecision:
    idle: bool
    reason: str

    def __bool__(self):
        return self.idle


class IdlePolicy:
    """带遮挡确认时间的空闲判定器。"""

    def __init__(self, idle_after_seconds: float = 60.0,
                 occluded_confirm_seconds: float = 5.0):
        self.idle_after_seconds = max(0.0, float(idle_after_seconds))
        self.occluded_confirm_seconds = max(0.0, float(occluded_confirm_seconds))
        self._occluded_since = None

    def reset(self):
        self._occluded_since = None

    def evaluate(self, snapshot: IdleSnapshot, now: float) -> IdleDecision:
        if not snapshot.window_visible:
            self._occluded_since = None
            return IdleDecision(True, _REASON_HIDDEN)

        if not snapshot.window_exposed:
            # 完全遮挡属于"看不到"，但仍要求持续一段时间，避免窗口切换/
            # 全屏过渡瞬间被误判为空闲。
            if self._occluded_since is None:
                self._occluded_since = now
            if (now - self._occluded_since) >= self.occluded_confirm_seconds:
                return IdleDecision(True, _REASON_OCCLUDED)
            return IdleDecision(False, _REASON_ACTIVE)
        self._occluded_since = None

        if snapshot.playing:
            return IdleDecision(False, _REASON_ACTIVE)
        if snapshot.panels_open:
            return IdleDecision(False, _REASON_ACTIVE)
        if snapshot.seconds_since_input < self.idle_after_seconds:
            return IdleDecision(False, _REASON_ACTIVE)
        return IdleDecision(True, _REASON_INACTIVE)
