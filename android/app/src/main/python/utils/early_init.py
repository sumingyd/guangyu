import subprocess
import sys
import os
import time

# 无头/离屏平台由调用方显式指定（CI、测试），不要被下面的 Wayland 逻辑覆盖
_HEADLESS_QPA_PLATFORMS = ('offscreen', 'minimal')


def _patch_py314_traceback_bug():
    """Python 3.14 traceback.FrameSummary.line 在 self._lines 为 None 时崩溃。

    AttributeError: 'NoneType' object has no attribute 'partition'
      File "traceback.py", line 379, in line
        return self._lines.partition("\\n")[0].strip()

    当帧来自已卸载模块或 C 扩展时 _lines 可能为 None。
    此 monkey-patch 让 line 属性安全返回 None。"""
    try:
        import traceback as _tb
        _FrameSummary = _tb.FrameSummary
        _orig_line = _FrameSummary.line.fget

        def _safe_line(self):
            if getattr(self, '_lines', None) is None:
                return None
            try:
                return _orig_line(self)
            except AttributeError:
                return None

        _FrameSummary.line = property(_safe_line)
    except Exception:
        pass


def _patch_py314_asyncio_exception_handler():
    """Python 3.14 asyncio Handle.__init__ 在某些场景下抛出
    TypeError: __init__() should return None, not 'NoneType'

    这会导致 asyncio 默认异常处理器崩溃，进而触发 traceback 格式化崩溃。
    安装自定义异常处理器，避免 traceback 格式化时访问坏帧。"""
    try:
        import asyncio

        def _safe_exception_handler(loop, context):
            msg = context.get('message', 'Unhandled exception in asyncio')
            exception = context.get('exception')
            if exception is not None:
                import logging
                logging.getLogger('asyncio').error(
                    "%s: %s", msg, exception, exc_info=False
                )
            else:
                import logging
                logging.getLogger('asyncio').error(msg)

        _orig_set_handler = asyncio.AbstractEventLoop.set_exception_handler

        def _patched_set_handler(self, handler):
            _orig_set_handler(self, handler or _safe_exception_handler)

        asyncio.AbstractEventLoop.set_exception_handler = _patched_set_handler
    except Exception:
        pass


def _patch_py314_gc_threshold():
    """Python 3.14 GC 在多线程 native 操作（datetime/shiboken）期间触发 access violation。

    增大 GC 阈值减少自动触发频率，由 QTimer 定期手动 collect 替代。"""
    try:
        import gc
        gc.set_threshold(10000, 50, 50)
    except Exception:
        pass


def _linux_is_wayland_session():
    """按会话变量判断是否运行在 Wayland 下（此时 Qt 尚未初始化，不能用 QPA 平台名）。"""
    session_type = os.environ.get('XDG_SESSION_TYPE', '').strip().lower()
    if session_type == 'wayland':
        return True
    if session_type == 'x11':
        return False
    return bool(os.environ.get('WAYLAND_DISPLAY'))


def _log_display_error(message):
    """把启动期显示环境错误写到 stderr 和日志文件，保证 --windowed 打包后也能追溯。"""
    try:
        stream = sys.stderr if sys.stderr is not None else sys.__stderr__
        if stream is not None:
            stream.write(message + '\n')
            stream.flush()
    except Exception:
        pass
    try:
        from utils.app_paths import get_log_dir
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'startup_error.log'), 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def _show_display_error_dialog(message):
    """尽力用原生对话框告知启动失败原因；没有 zenity/kdialog 时只依赖日志。"""
    for cmd in (
        ['zenity', '--error', '--title', 'GuangYu', '--no-wrap', '--text', message],
        ['kdialog', '--title', 'GuangYu', '--error', message],
    ):
        try:
            result = subprocess.run(cmd, timeout=120)
            if result.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            continue


def _configure_linux_display():
    """Linux 显示环境预检：Wayland 会话统一切到 XWayland(xcb)。

    mpv 的 wid 嵌入只接受 X11 窗口 ID，Wayland 原生会话下 winId() 不是 XID，
    继续运行只会黑屏或在播放时静默失败。因此在导入 PySide6 之前就把 QPA
    平台固定为 xcb，并在没有 XWayland 时给出可读错误而不是让 Qt 直接崩溃。
    """
    if not sys.platform.startswith('linux') or 'ANDROID_ARGUMENT' in os.environ:
        return
    requested = (os.environ.get('QT_QPA_PLATFORM') or '').strip().lower()
    if requested in _HEADLESS_QPA_PLATFORMS:
        return
    if not _linux_is_wayland_session():
        return
    if not os.environ.get('DISPLAY'):
        message = (
            'GuangYu 启动失败：当前是 Wayland 会话，但没有可用的 X11 显示（XWayland）。\n'
            '视频画面依赖 X11 窗口嵌入，缺少 XWayland 时无法显示。\n'
            '请安装并启用 XWayland（多数发行版的 xorg-xwayland 包），'
            '或改用 X11 会话后重新启动。'
        )
        _log_display_error(message)
        _show_display_error_dialog(message)
        raise SystemExit(1)
    if requested and not requested.startswith('xcb'):
        _log_display_error(
            f'检测到 Wayland 会话，已将 QT_QPA_PLATFORM={requested} 覆盖为 xcb'
            '（mpv 窗口嵌入依赖 X11，Wayland 原生平台无法显示视频）。'
        )
    os.environ['QT_QPA_PLATFORM'] = 'xcb'


def setup_environment():
    _patch_py314_traceback_bug()
    _patch_py314_asyncio_exception_handler()
    _patch_py314_gc_threshold()
    if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
        try:
            import certifi
            os.environ['SSL_CERT_FILE'] = certifi.where()
            os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        except ImportError:
            _cert_path = os.path.join(os.path.dirname(sys.executable), 'resources', 'cert.pem')
            if os.path.exists(_cert_path):
                os.environ['SSL_CERT_FILE'] = _cert_path
                os.environ['REQUESTS_CA_BUNDLE'] = _cert_path

    _configure_linux_display()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))