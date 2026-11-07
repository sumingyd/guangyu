"""macOS NSVisualEffectView 毛玻璃辅助工具。

在 macOS 上通过 PyObjC 调用 NSVisualEffectView 实现原生毛玻璃模糊效果。
非 macOS 平台或 PyObjC 不可用时，apply() 返回 False，调用方回退到 WA_TranslucentBackground。
"""
import logging
import sys

logger = logging.getLogger(__name__)


def _is_macos():
    return sys.platform == 'darwin'


def wrap_ns_object(ptr):
    """把原生指针包装成 PyObjC 对象。

    macOS 上 QWidget.winId() 返回的就是 NSView*。PyObjC 未安装或包装失败时
    返回 None，调用方应回退到不依赖原生的实现。
    """
    if not ptr:
        return None
    try:
        import objc
    except ImportError:
        return None
    try:
        return objc.objc_object(c_void_p=int(ptr))
    except TypeError:
        try:
            return objc.objc_object(int(ptr))
        except Exception:
            return None
    except Exception:
        return None


class MacBlurHelper:
    """macOS 原生毛玻璃模糊辅助类。

    使用方法::

        if MacBlurHelper.apply(window):
            # 成功附着 NSVisualEffectView
        else:
            # 回退到 WA_TranslucentBackground
    """

    _initialized = False
    _objc_available = False

    @classmethod
    def _ensure_init(cls):
        if cls._initialized:
            return
        cls._initialized = True
        if not _is_macos():
            return
        try:
            import objc  # noqa: F401
            import AppKit  # noqa: F401
            cls._objc_available = True
        except ImportError:
            cls._objc_available = False
            logger.debug("PyObjC 不可用，macOS 原生毛玻璃将回退到半透明背景")

    @classmethod
    def apply(cls, window, material="menu"):
        """将 NSVisualEffectView 附着到 Qt 窗口的 NSView 句柄。

        Args:
            window: QWidget 或 QMainWindow 实例
            material: 毛玻璃材质，可选 "menu"、"sidebar"、"popover"、"titlebar"、"fullscreen"

        Returns:
            bool: True 表示成功附着，False 表示不可用或失败
        """
        cls._ensure_init()
        if not cls._objc_available:
            return False
        try:
            from AppKit import (
                NSVisualEffectView,
                NSVisualEffectMaterialMenu,
                NSVisualEffectMaterialSidebar,
                NSVisualEffectMaterialPopover,
                NSVisualEffectMaterialTitlebar,
                NSVisualEffectMaterialFullScreenUI,
                NSVisualEffectBlendingModeBehindWindow,
                NSViewWidthSizable,
                NSViewHeightSizable,
                NSWindowBelow,
            )

            material_map = {
                "menu": NSVisualEffectMaterialMenu,
                "sidebar": NSVisualEffectMaterialSidebar,
                "popover": NSVisualEffectMaterialPopover,
                "titlebar": NSVisualEffectMaterialTitlebar,
                "fullscreen": NSVisualEffectMaterialFullScreenUI,
            }

            # PySide6 6.7 的 QWindow 没有 nativeInterface()（旧代码在这里抛
            # AttributeError 并被吞掉，导致原生毛玻璃从未生效）。
            # macOS 上 QWidget.winId() 返回的就是 NSView*。
            ns_view = wrap_ns_object(window.winId())
            if ns_view is None:
                window.createWinId()
                ns_view = wrap_ns_object(window.winId())
            if ns_view is None:
                return False

            ns_window = ns_view.window() if hasattr(ns_view, 'window') else None
            if ns_window is None:
                return False
            content_view = ns_window.contentView()
            if content_view is None:
                return False
            frame_view = content_view.superview()
            if frame_view is None:
                return False

            # 重复 apply（主题切换、面板重建）时先摘掉旧视图，避免层层累积
            cls.remove(window)

            effect_view = NSVisualEffectView.alloc().initWithFrame_(content_view.frame())
            effect_view.setMaterial_(material_map.get(material, NSVisualEffectMaterialMenu))
            effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
            effect_view.setState_(1)
            effect_view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            # 插到 contentView 之下：Qt 的控件与 QOpenGLWidget 视频仍绘制在上层，
            # 毛玻璃只透出窗口背后的桌面/下层面板，不会把画面盖成一层灰。
            frame_view.addSubview_positioned_relativeTo_(
                effect_view, NSWindowBelow, content_view
            )

            window._mac_blur_views = [effect_view]
            return True
        except Exception as e:
            logger.debug(f"macOS 毛玻璃附着失败: {e}")
            return False

    @classmethod
    def remove(cls, window):
        """移除 NSVisualEffectView 附着。

        Args:
            window: QWidget 或 QMainWindow 实例
        """
        if not _is_macos():
            return
        try:
            views = getattr(window, '_mac_blur_views', [])
            for view in views:
                try:
                    view.removeFromSuperview()
                except Exception:
                    pass
            window._mac_blur_views = []
        except Exception:
            pass

    @classmethod
    def is_available(cls):
        """检查 macOS 毛玻璃是否可用。"""
        cls._ensure_init()
        return cls._objc_available