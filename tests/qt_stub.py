"""按需注入的 PySide6 轻量替身。

用途：mixins / 控制器里的纯逻辑测试并不依赖真实 Qt。为了让这些测试在
未安装 PySide6 的环境（如精简 CI）下也能运行，由**具体测试文件**显式调用
``ensure_qt_available()`` 注入替身。

约束：
  * 不在 conftest.py 中全局注入，避免污染其他依赖真实 Qt 的测试
    （例如 test_facade_smoke.py 要求"缺依赖时跳过而不是伪装通过"）；
  * 仅在检测不到真实 PySide6 时启用，设置了 GUANGYU_FORCE_QT_STUB=1
    时强制启用，便于本地验证替身路径；
  * 替身只暴露"可继承、可实例化、属性访问返回 MagicMock"的最小行为。
"""

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

_STUB_MARK = "__guangyu_qt_stub__"


class _StubMeta(type):
    """让替身类支持 ``QListWidget.ViewMode.IconMode`` 这类类属性链。"""

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        # 真实 Qt 在没有 QApplication 时返回 None；替身若返回 MagicMock 会
        # 让 "app is not None" 分支被误判为真，改变被测逻辑走向。
        if cls.__name__ == "QApplication" and name == "instance":
            value = staticmethod(lambda *a, **k: None)
            setattr(cls, name, value)
            return value
        value = MagicMock(name=f"{cls.__name__}.{name}")
        setattr(cls, name, value)
        return value


def _make_class(qualified_name):
    short_name = qualified_name.rsplit(".", 1)[-1]

    def _init(self, *args, **kwargs):
        return None

    def _getattr(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name=f"{qualified_name}.{name}")

    def _call(self, *args, **kwargs):
        # 支持 @Slot() / @Slot(int) 这类装饰器用法：直接返回被装饰函数
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]
        return MagicMock(name=f"{qualified_name}()")

    return _StubMeta(short_name, (object,), {
        "__init__": _init,
        "__getattr__": _getattr,
        "__call__": _call,
        "__doc__": f"PySide6 stub for {qualified_name}",
    })


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = _make_class(f"{self.__name__}.{name}")
        setattr(self, name, value)
        return value


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        setattr(module, _STUB_MARK, True)
        return module

    def exec_module(self, module):
        return None


class _StubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            return importlib.machinery.ModuleSpec(fullname, _StubLoader(), is_package=True)
        return None


def qt_is_stub():
    """当前进程是否使用 PySide6 替身。"""
    module = sys.modules.get("PySide6")
    return bool(module is not None and getattr(module, _STUB_MARK, False))


def ensure_qt_available():
    """确保 PySide6 可用；未安装时注入本文件提供的替身。"""
    if "PySide6" in sys.modules:
        return
    force_stub = os.environ.get("GUANGYU_FORCE_QT_STUB") == "1"
    if not force_stub and importlib.util.find_spec("PySide6") is not None:
        return
    if not any(isinstance(finder, _StubFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _StubFinder())
    importlib.import_module("PySide6")
