"""方向键/空格分发的焦点门回归测试。

背景：``EventHandler._is_player_focus()`` 曾被收紧为"焦点必须是主窗口本体或
视频控件"，而视频控件是 NoFocus、永远不会成为 focusWidget，导致正常启动态
（焦点落在标题栏按钮上）上下键切台、左右键 seek、空格播放/暂停全部失效。
本文件锁定窗口级语义：主窗口内任意子控件都算播放器焦点，独立顶层悬浮面板不算。

测试使用 offscreen 平台，不依赖显示器。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget

from controllers.event_handler import EventHandler


@pytest.fixture(scope="module")
def qapp():
    """复用（或创建）offscreen QApplication。"""
    app = QApplication.instance() or QApplication([])
    yield app


def _make_main_window(qapp):
    """构造一个最小主窗口：窗口内包含一个可聚焦按钮（模拟标题栏按钮）。"""
    window = QMainWindow()
    central = QWidget()
    window.setCentralWidget(central)
    button = QPushButton("ok", central)
    button.setGeometry(0, 0, 80, 24)
    window.show()
    window.activateWindow()
    qapp.processEvents()
    return window, button


def test_player_focus_true_when_main_window_child_focused(qapp):
    """回归核心断言：焦点在主窗口内某个按钮时，方向键/空格应被播放器接管。

    若把 _is_player_focus() 改回"只认 video_widget/video_frame"的严格判定，
    本用例必然失败（按钮既不是主窗口本体，也不是视频控件）。
    """
    window, button = _make_main_window(qapp)
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    assert QApplication.focusWidget() is button, "offscreen 下未能把焦点交给窗口内按钮"
    assert EventHandler(window)._is_player_focus() is True


def test_player_focus_true_when_no_focus_and_window_active(qapp):
    """焦点为空且主窗口处于激活态时，视为播放器焦点。"""
    window, button = _make_main_window(qapp)
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    QApplication.focusWidget().clearFocus()
    qapp.processEvents()

    assert QApplication.focusWidget() is None
    assert window.isActiveWindow() is True
    assert EventHandler(window)._is_player_focus() is True


def test_player_focus_false_for_independent_tool_window(qapp):
    """焦点在独立的 Qt::Tool 悬浮面板里时，方向键应归面板自己处理。"""
    window, _ = _make_main_window(qapp)
    panel_button = QPushButton("panel")
    panel_button.setWindowFlags(Qt.WindowType.Tool)
    panel_button.show()
    qapp.processEvents()
    panel_button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    assert QApplication.focusWidget() is panel_button
    assert QApplication.focusWidget().window() is not window
    assert EventHandler(window)._is_player_focus() is False


def test_handled_shortcut_claims_key_m(qapp):
    """M（悬浮面板显隐）已进入分发逻辑，ShortcutOverride 也必须认领该键。"""
    window, button = _make_main_window(qapp)
    button.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    handler = EventHandler(window)
    assert handler._is_handled_shortcut(
        Qt.Key.Key_M, Qt.KeyboardModifier.NoModifier) is True
