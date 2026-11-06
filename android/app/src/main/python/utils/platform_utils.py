try:
    from PySide6.QtCore import QPoint, QStandardPaths
    from PySide6.QtGui import QGuiApplication
    _HAS_QT = True
except ImportError:
    # Android（p4a 共享包）/ 无 GUI 环境没有 PySide6；
    # 本模块被 server 初始化路径导入，必须保持可导入
    _HAS_QT = False
import os
import sys
import logging

_logger = logging.getLogger(__name__)


def is_windows():
    return sys.platform == 'win32'


def is_macos():
    return sys.platform == 'darwin'


def is_linux():
    return sys.platform.startswith('linux') and not is_android()


def is_wayland():
    if not is_linux():
        return False
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    if session_type == 'wayland':
        return True
    qt_qpa = os.environ.get('QT_QPA_PLATFORM', '').lower()
    if qt_qpa == 'wayland':
        return True
    if session_type == 'x11':
        return False
    wayland_display = os.environ.get('WAYLAND_DISPLAY', '')
    if wayland_display:
        return True
    return False


def wayland_move(widget, x, y):
    if not is_wayland():
        widget.move(x, y)
        return
    try:
        window_handle = widget.windowHandle()
        if window_handle is None:
            widget.createWinId()
            window_handle = widget.windowHandle()
        if window_handle:
            window_handle.setPosition(QPoint(x, y))
            widget.move(x, y)
        else:
            _logger.warning("wayland_move: windowHandle is None after createWinId, falling back to widget.move")
            widget.move(x, y)
    except Exception as e:
        _logger.warning(f"wayland_move: setPosition failed ({e}), falling back to widget.move")
        widget.move(x, y)


def wayland_set_geometry(widget, x, y, w, h):
    if not is_wayland():
        widget.setGeometry(x, y, w, h)
        return
    try:
        window_handle = widget.windowHandle()
        if window_handle is None:
            widget.createWinId()
            window_handle = widget.windowHandle()
        if window_handle:
            window_handle.setPosition(QPoint(x, y))
        else:
            _logger.warning("wayland_set_geometry: windowHandle is None after createWinId, falling back to setGeometry")
        widget.resize(w, h)
        widget.move(x, y)
    except Exception as e:
        _logger.warning(f"wayland_set_geometry: setPosition failed ({e}), falling back to setGeometry")
        widget.setGeometry(x, y, w, h)


def is_android():
    return getattr(sys, 'platform', '') == 'android' or 'ANDROID_ARGUMENT' in os.environ



def is_touch_device():
    if is_android():
        return True
    return False


def get_platform_name():
    if is_android():
        return 'android'
    if is_windows():
        return 'windows'
    if is_macos():
        return 'macos'
    if is_linux():
        return 'linux'
    return 'unknown'


def get_android_data_dir():
    """获取 Android 端数据存储目录路径（已包含 ISEP）。

    android_bridge._setup_android_paths() 会将 IPTV_DATA_DIR 设置为完整的 ISEP 目录
    （如 /sdcard/ISEP 或 getExternalFilesDir()/ISEP）。
    其他设置途径（如 server_main.py 的 setdefault）可能指向父目录，此时补齐 ISEP。

    Returns:
        str: 数据目录绝对路径。环境变量未设置时返回空字符串。
    """
    android_data = os.environ.get('IPTV_DATA_DIR', '')
    if not android_data:
        return ''
    if os.path.basename(android_data) == 'ISEP':
        return android_data
    return os.path.join(android_data, 'ISEP')


def get_app_base_path():
    if is_android():
        # 优先使用 IPTV_DATA_DIR（由 android_bridge._setup_android_paths 设置为 ISEP 目录）
        data_dir = get_android_data_dir()
        if data_dir:
            return data_dir
        try:
            app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
            if app_data:
                return app_data
        except Exception:
            pass
        return os.path.join(os.path.expanduser('~'), 'ISEP')
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    from models.channel_mappings import get_app_data_dir
    return get_app_data_dir()


def get_libmpv_filename():
    if is_windows():
        return 'libmpv-2.dll'
    if is_macos():
        return 'libmpv.2.dylib'
    if is_android():
        return 'libmpv.so'
    return 'libmpv.so.2'


def find_libmpv_paths():
    """返回所有候选 libmpv 路径列表（按优先级排序，含不存在的路径）。

    调用方应逐一尝试加载，某个路径加载失败（文件存在但损坏/依赖缺失）时
    继续尝试下一个路径，而不是仅凭 os.path.exists 判断。
    """
    base_path = get_app_base_path()
    mpv_dir = os.path.join(base_path, 'mpv')
    filename = get_libmpv_filename()

    if is_windows():
        # 按优先级查找 libmpv-2.dll
        search_paths = [
            os.path.join(mpv_dir, filename),  # PyInstaller _MEIPASS/mpv/ 或开发模式 data_dir/mpv/
        ]
        # frozen 模式下增加备用路径：
        # onefile 模式的 _MEIPASS 临时目录可能因 UPX 解压失败、杀毒软件删除、
        # 临时目录被清理等原因丢失 dll，此时从 exe 同级目录查找（便携版分发模式）
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            search_paths.extend([
                os.path.join(exe_dir, 'mpv', filename),  # 便携版 exe 同级 mpv/
                os.path.join(exe_dir, filename),          # 直接放在 exe 旁边
            ])
        # 从系统 PATH 搜索（如果用户安装了 mpv 播放器）
        for d in os.environ.get('PATH', '').split(os.pathsep):
            if d:
                p = os.path.join(d, filename)
                if p not in search_paths:
                    search_paths.append(p)
        # 从常见 mpv 安装路径搜索
        for d in [r'C:\Program Files\mpv', r'C:\Program Files (x86)\mpv']:
            search_paths.append(os.path.join(d, filename))
        return search_paths

    if is_macos():
        return [
            os.path.join(mpv_dir, 'libmpv.2.dylib'),
            '/usr/local/lib/libmpv.2.dylib',
            '/opt/homebrew/lib/libmpv.2.dylib',
            '/usr/lib/libmpv.2.dylib',
        ]

    if is_android():
        possible_names = ['libmpv.so', 'libmpv.so.2', 'libmpv.so.1']
        paths = []
        # 优先从 Kotlin 端传递的 nativeLibraryDir 搜索
        native_lib_dir = os.environ.get('IPTV_NATIVE_LIB_DIR', '')
        if native_lib_dir:
            for name in possible_names:
                paths.append(os.path.join(native_lib_dir, name))
        for name in possible_names:
            paths.append(os.path.join(mpv_dir, name))
        lib_dir = os.path.join(base_path, 'lib')
        for name in possible_names:
            paths.append(os.path.join(lib_dir, name))
        return paths

    # Linux
    possible_names = ['libmpv.so.2', 'libmpv.so.1', 'libmpv.so']
    paths = []
    for name in possible_names:
        paths.append(os.path.join(mpv_dir, name))

    try:
        import ctypes.util
        found = ctypes.util.find_library('mpv')
        if found and os.path.exists(found):
            paths.append(found)
    except Exception:
        pass

    system_dirs = [
        '/usr/lib/aarch64-linux-gnu/',
        '/usr/lib/x86_64-linux-gnu/',
        '/usr/lib64/',
        '/usr/local/lib/',
        '/usr/lib/',
    ]
    for d in system_dirs:
        for name in possible_names:
            paths.append(os.path.join(d, name))

    try:
        import subprocess
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            for name in possible_names:
                if name in line:
                    parts = line.strip().split('=>')
                    if len(parts) == 2:
                        p = parts[1].strip()
                        if os.path.exists(p):
                            paths.append(p)
    except Exception:
        pass

    return paths


def find_libmpv_path():
    """返回第一个存在的 libmpv 路径（向后兼容）。

    注意：此函数仅判断文件是否存在，不验证可加载性。
    加载逻辑应使用 find_libmpv_paths() 逐一尝试，以应对文件存在但损坏的情况。
    """
    for p in find_libmpv_paths():
        if os.path.exists(p):
            return p
    # 都找不到时返回默认路径（保持原行为，让加载逻辑报错）
    return find_libmpv_paths()[0] if find_libmpv_paths() else ''


def get_ffprobe_filename():
    if is_windows():
        return 'ffprobe.exe'
    return 'ffprobe'


def get_ffprobe_path():
    base_path = get_app_base_path()
    ffprobe_dir = os.path.join(base_path, 'ffmpeg')
    filename = get_ffprobe_filename()
    ffprobe_exe = os.path.join(ffprobe_dir, filename)
    if os.path.exists(ffprobe_exe):
        return ffprobe_exe
    ffprobe_dir_alt = os.path.join(base_path, 'ffmpeg')
    ffprobe_exe_alt = os.path.join(ffprobe_dir_alt, filename)
    if os.path.exists(ffprobe_exe_alt):
        return ffprobe_exe_alt
    # frozen 模式下从 exe 同级目录查找备用（_MEIPASS 解压失败时的兜底）
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        for p in [
            os.path.join(exe_dir, 'ffmpeg', filename),
            os.path.join(exe_dir, filename),
        ]:
            if os.path.exists(p):
                return p
    # 退回到系统 PATH
    import shutil as _sh
    sys_ffprobe = _sh.which('ffprobe')
    if sys_ffprobe:
        return sys_ffprobe
    return None


def get_ffmpeg_filename():
    if is_windows():
        return 'ffmpeg.exe'
    return 'ffmpeg'


def get_ffmpeg_path():
    """获取 ffmpeg 可执行文件路径

    优先级：
    1. 打包目录下的 ffmpeg/ffmpeg(.exe)
    2. exe 同级目录的 ffmpeg/ffmpeg(.exe)（frozen 模式备用）
    3. 系统 PATH 中的 ffmpeg
    """
    base_path = get_app_base_path()
    ffmpeg_dir = os.path.join(base_path, 'ffmpeg')
    filename = get_ffmpeg_filename()
    ffmpeg_exe = os.path.join(ffmpeg_dir, filename)
    if os.path.exists(ffmpeg_exe):
        return ffmpeg_exe
    # frozen 模式下从 exe 同级目录查找备用（_MEIPASS 解压失败时的兜底）
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        for p in [
            os.path.join(exe_dir, 'ffmpeg', filename),
            os.path.join(exe_dir, filename),
        ]:
            if os.path.exists(p):
                return p
    # 退回到系统 PATH
    import shutil as _sh
    sys_ffmpeg = _sh.which('ffmpeg')
    if sys_ffmpeg:
        return sys_ffmpeg
    return None


def get_subprocess_creation_flags():
    if is_windows():
        import subprocess
        return subprocess.CREATE_NO_WINDOW
    return 0


def get_screen_dpi_scale():
    try:
        if _HAS_QT and QGuiApplication.instance():
            screen = QGuiApplication.primaryScreen()
            if screen:
                return screen.devicePixelRatio()
    except Exception:
        pass
    return 1.0


def get_touch_target_size():
    if is_android():
        return 48
    return 32


def get_logical_screen_width() -> int:
    """主屏逻辑宽度（已按 DPR 折算，不含缩放）；无 Qt 环境时回落 1920。"""
    try:
        if _HAS_QT:
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app else None
            if screen:
                return max(0, screen.availableGeometry().width())
    except Exception:
        pass
    return 1920


def get_ui_scale() -> float:
    """按逻辑屏宽分级的界面尺寸因子，统一驱动按钮/行高/字号等。

    < 1280 小屏 0.85；< 1920 常规 1.0；< 2560 大屏 1.15；其余超宽 1.3。
    """
    w = get_logical_screen_width()
    if w < 1280:
        return 0.85
    if w < 1920:
        return 1.0
    if w < 2560:
        return 1.15
    return 1.3
