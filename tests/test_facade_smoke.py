"""Facade 冒烟测试：真实构造拆分后的门面类，拦截"子控制器丢失实例化"回归。

背景：批次二架构重构曾在 MpvPlayerController / MediaController 中引用
self._playback / self._context_menu 等子控制器却从未实例化，且被上层
except 吞掉，表现为启动崩溃或点台无声。本测试不 mock Qt，要求真实
构造路径可用（缺失依赖时跳过而非伪装通过）。
"""

import pytest

from tests.qt_stub import qt_is_stub

if qt_is_stub():
    pytest.skip("当前使用 PySide6 替身，跳过依赖真实 Qt 的冒烟测试", allow_module_level=True)

pytest.importorskip("PySide6.QtWidgets")


def test_mpv_player_controller_subcontrollers_instantiated():
    from services.mpv_player_service import MpvPlayerController

    pc = MpvPlayerController(None)
    for attr in ("_playback", "_hdr", "_video_eq", "_audio_eq",
                 "_filter", "_subtitle", "_shader", "audio_visual"):
        sub = getattr(pc, attr, None)
        assert sub is not None, (
            f"MpvPlayerController.{attr} 未实例化——门面拆分丢失子控制器"
        )


def test_media_controller_subcontrollers_instantiated():
    from controllers.media_controller import MediaController

    class _StubWindow:
        pass

    mc = MediaController(_StubWindow())
    for attr in ("_context_menu", "_preset", "_lyrics"):
        sub = getattr(mc, attr, None)
        assert sub is not None, (
            f"MediaController.{attr} 未实例化——门面拆分丢失子控制器"
        )


def test_appstyles_composition_resolves():
    """AppStyles 聚合门面的 mixin 方法体内引用 AppStyles 全局名，
    依赖 ui/styles.py 的命名空间回注，缺失时任何样式调用即 NameError。"""
    from ui.styles import AppStyles
    from ui import styles_player, styles_window, styles_common, styles_dialog

    for mod in (styles_player, styles_window, styles_common, styles_dialog):
        assert getattr(mod, "AppStyles", None) is AppStyles, (
            f"{mod.__name__} 缺少聚合类回注，样式方法调用将 NameError"
        )
    # 实际调用一个样式方法确认无 NameError
    assert isinstance(AppStyles.title_bar_style(), str)
    assert isinstance(AppStyles.statusbar_style(), str)
