"""全局未捕获异常兜底。

PyInstaller --windowed 打包后没有控制台，未捕获异常只会让进程静默退出，
现场完全不可观测。这里统一把主线程、子线程以及解释器级异常写入
用户目录下的 crash.log（带时间戳、线程名与完整栈），并覆盖原生崩溃
（段错误等）场景。

Windows 上不使用 faulthandler.enable()：它在 Windows 通过向量化异常处理器
捕获**所有**它认不出的 SEH 码，包括库内部被正常捕获的 first-chance 异常。
libmpv 静态链接的 LuaJIT 每次 Lua 报错都会抛 0xE24C4A02（LuaJIT 私有码），
faulthandler 会把它写成 "Windows fatal exception: code 0xe24c4a02"，
而进程其实继续运行，导致 crash.log 全是假崩溃、真崩溃反而被淹没。
这里改为挂 SetUnhandledExceptionFilter：只有异常真的无人处理、进程即将
退出时才落盘。
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
_native_filter = None  # 必须保持引用，否则 ctypes 回调会被回收导致崩溃


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


def _write_native_header(code: int) -> None:
    """原生崩溃落盘前写一段可读头，避免和 Python 异常的条目混淆。"""
    if _crash_file is None:
        return
    header = [
        '=' * 60,
        f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"进程: {os.getpid()}  线程: 原生崩溃",
        f"原生异常码: 0x{code:08X}",
        '-' * 60,
    ]
    _crash_file.write('\n'.join(header) + '\n')
    _crash_file.flush()


def _install_windows_unhandled_filter() -> bool:
    """Windows：只在异常真正无人处理（进程即将退出）时落盘。

    faulthandler 的向量化异常处理器会把库内部被正常捕获的 first-chance
    异常也算作致命异常，crash.log 因此充满假警报。SetUnhandledExceptionFilter
    只在没有 SEH 帧接手时被调用，判断口径更准确。
    """
    global _native_filter
    try:
        import ctypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)

        @callback_type
        def _unhandled_filter(exc_info):
            try:
                code = 0
                if exc_info:
                    record = ctypes.cast(exc_info, ctypes.POINTER(ctypes.c_void_p))[0]
                    if record:
                        code = ctypes.cast(record, ctypes.POINTER(ctypes.c_ulong))[0]
                _write_native_header(code)
                if _crash_file is not None:
                    faulthandler.dump_traceback(file=_crash_file, all_threads=True)
                    _crash_file.flush()
            except Exception:
                pass
            # 继续交给系统默认处理（WER / 进程终止），保持原有崩溃行为
            return 0  # EXCEPTION_CONTINUE_SEARCH

        kernel32.SetUnhandledExceptionFilter.argtypes = [callback_type]
        kernel32.SetUnhandledExceptionFilter.restype = ctypes.c_void_p
        kernel32.SetUnhandledExceptionFilter(_unhandled_filter)
        _native_filter = _unhandled_filter
        return True
    except Exception:
        return False


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
        # 原生崩溃（SEGV 等）无法走 Python 异常钩子，需要单独落盘。
        _crash_file = open(_crash_log_path, 'a', encoding='utf-8')
        if sys.platform == 'win32':
            # Windows 用未处理异常过滤器，避免把库内部 first-chance 异常
            # 误记为致命崩溃；安装失败时退回 faulthandler 保证仍有记录。
            if not _install_windows_unhandled_filter():
                faulthandler.enable(file=_crash_file, all_threads=True)
        else:
            faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        _crash_file = None

    _installed = True
    return _crash_log_path
