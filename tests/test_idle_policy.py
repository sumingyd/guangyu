"""空闲停绘判定策略的单测（纯逻辑，不依赖 Qt）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.idle_policy import IdlePolicy, IdleSnapshot


def _snapshot(**kwargs):
    base = dict(window_visible=True, window_exposed=True, playing=False,
                panels_open=False, seconds_since_input=999.0)
    base.update(kwargs)
    return IdleSnapshot(**base)


def test_hidden_window_is_idle_immediately():
    policy = IdlePolicy(idle_after_seconds=60)
    decision = policy.evaluate(_snapshot(window_visible=False), now=100.0)
    assert decision.idle and decision.reason == 'hidden'


def test_playing_window_never_idles():
    policy = IdlePolicy(idle_after_seconds=0)
    decision = policy.evaluate(_snapshot(playing=True), now=100.0)
    assert not decision.idle


def test_open_panel_keeps_active():
    policy = IdlePolicy(idle_after_seconds=0)
    decision = policy.evaluate(_snapshot(panels_open=True), now=100.0)
    assert not decision.idle


def test_recent_input_keeps_active_then_idles():
    policy = IdlePolicy(idle_after_seconds=60)
    assert not policy.evaluate(_snapshot(seconds_since_input=5.0), now=100.0).idle
    decision = policy.evaluate(_snapshot(seconds_since_input=61.0), now=160.0)
    assert decision.idle and decision.reason == 'inactive'


def test_occlusion_requires_confirmation_window():
    policy = IdlePolicy(idle_after_seconds=60, occluded_confirm_seconds=5.0)
    snap = _snapshot(window_exposed=False)
    assert not policy.evaluate(snap, now=10.0).idle
    assert not policy.evaluate(snap, now=13.0).idle
    decision = policy.evaluate(snap, now=16.0)
    assert decision.idle and decision.reason == 'occluded'


def test_occlusion_timer_resets_when_window_exposed_again():
    policy = IdlePolicy(idle_after_seconds=60, occluded_confirm_seconds=5.0)
    occluded = _snapshot(window_exposed=False)
    policy.evaluate(occluded, now=10.0)
    assert not policy.evaluate(_snapshot(seconds_since_input=0.0), now=12.0).idle
    # 重新遮挡需要重新计时，不能沿用旧时间戳
    assert not policy.evaluate(occluded, now=13.0).idle
    assert policy.evaluate(occluded, now=18.5).idle


def test_negative_seconds_since_input_is_clamped():
    snap = _snapshot(seconds_since_input=-3.0)
    assert snap.seconds_since_input == 0.0
