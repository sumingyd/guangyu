"""全局未捕获异常兜底。

PyInstaller --windowed 打包后没有控制台，未捕获异常只会让进程静默退出，
现场完全不可观测。这里统一把主线程、子线程以及解释器级异常写入
用户目录下的 crash.log（带时间戳、线程名与完整栈），并用 faulthandler
覆盖原生崩溃（段错误等）场景。
"""

import faulthandler
import os
import sys
import threading
import time
import traceback

_installed = False
_crash_file = None
_crash_log_path = ''


def _write_entry(thread_name: str, exc_type, exc_value, exc_tb) -> None:
    header = [
        '=' * 60,
        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"进程: {os.getpid()}  线程: {thread_name}",
        f"Python: {sys.version.splitlines()[0]}",
        '-' * 60,
    ]
    try:
        tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    except Exception:
        tb_text = f"{exc_type!r}: {exc_value!r}\n"
    text = '\n'.join(header) + '\n' + tb_text
    if not text.endswith('\n'):
        text += '\n'
    try:
        with open(_crash_log_path, 'a', encoding='utf-8') as f:
            f.write(text)
    except OSError:
        pass


def _handle_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        return
    _write_entry(threading.current_thread().name, exc_type, exc_value, exc_tb)
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _handle_thread(args) -> None:
    # threading.excepthook 参数：exc_type/exc_value/exc_traceback/thread
    try:
        name = getattr(args.thread, 'name', 'unknown')
    except Exception:
        name = 'unknown'
    _write_entry(name, args.exc_type, args.exc_value, args.exc_traceback)


def _handle_unraisable(args) -> None:
    _write_entry('unraisable', args.exc_type, args.exc_value, args.exc_traceback)


def install_crash_handler(log_dir: str = None) -> str:
    """安装全局异常兜底，返回 crash.log 的绝对路径。"""
    global _installed, _crash_file, _crash_log_path
    if _installed:
        return _crash_log_path

    if log_dir is None:
        from utils.app_paths import get_log_dir
        log_dir = get_log_dir()
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = os.path.dirname(os.path.abspath(log_dir)) or os.path.abspath('.')
    _crash_log_path = os.path.join(log_dir, 'crash.log')

    sys.excepthook = _handle_uncaught
    threading.excepthook = _handle_thread
    sys.unraisablehook = _handle_unraisable

    try:
        # 原生崩溃（SIGSEGV 等）无法走 Python 异常钩子，交给 faulthandler 落盘。
        _crash_file = open(_crash_log_path, 'a', encoding='utf-8')
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        _crash_file = None

    _installed = True
    return _crash_log_path
