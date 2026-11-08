import ctypes
import os
import sys
import locale
import threading

from core.log_manager import global_logger as logger
from utils.platform_utils import find_libmpv_path, find_libmpv_paths, get_libmpv_filename, is_windows, is_macos, is_linux, is_android

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# 网络超时“自动”口径：mpv 的 network-timeout、源超时看门狗、流校验器共用同一值，
# 避免出现 mpv 等 60s（其默认值）而 UI 10s 就判失败的口径分裂。
DEFAULT_NETWORK_TIMEOUT_SEC = 10

_mpv_loaded = False
_env_initialized = False

libmpv_path = ''
mpv_dir = ''

MPV_AVAILABLE = False
libmpv = None
_last_load_error = ""


def _ensure_env_initialized():
    global libmpv_path, mpv_dir, _env_initialized
    if _env_initialized:
        return
    _env_initialized = True

    libmpv_path = find_libmpv_path()

    if libmpv_path and os.path.exists(libmpv_path):
        os.environ['MPV_LIBRARY'] = libmpv_path
        mpv_dir = os.path.dirname(libmpv_path)
    else:
        if getattr(sys, 'frozen', False):
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            from models.channel_mappings import get_app_data_dir
            base_path = get_app_data_dir()
        mpv_dir = os.path.join(base_path, 'mpv')
        logger.warning(f"未找到libmpv库: {libmpv_path}")

    # MPV_HOME 指向 mpv 的配置目录，不应指向 libmpv 所在的库目录；
    # Linux 上 libmpv 通常在 /usr/lib 等系统目录，指向那里会让 mpv 在系统目录里找脚本/配置。
    if not is_linux():
        os.environ['MPV_HOME'] = mpv_dir
    os.environ['PATH'] = mpv_dir + os.pathsep + os.environ.get('PATH', '')

    if is_macos() and os.path.isdir(mpv_dir):
        existing = os.environ.get('DYLD_LIBRARY_PATH', '')
        if mpv_dir not in existing:
            os.environ['DYLD_LIBRARY_PATH'] = mpv_dir + (os.pathsep + existing if existing else '')

    if is_linux() and os.path.isdir(mpv_dir):
        existing = os.environ.get('LD_LIBRARY_PATH', '')
        if mpv_dir not in existing:
            os.environ['LD_LIBRARY_PATH'] = mpv_dir + (os.pathsep + existing if existing else '')


def _extract_real_winerror(exc):
    """从异常中提取真正的 winerror。

    PyInstaller 的 pyimod03_ctypes.PyInstallerImportError 继承自 OSError，
    但丢失了原始异常的 winerror（原始异常保存在 __cause__ 中）。
    这导致 ctypes.CDLL 加载失败时，无法从 winerror 判断具体原因
    （126=依赖缺失, 193=文件损坏, 5=访问拒绝, None=文件不存在）。
    """
    # 直接获取 winerror
    winerror = getattr(exc, 'winerror', None)
    if winerror is not None:
        return winerror
    # PyInstallerImportError 丢失了 winerror，从 __cause__ 获取原始异常的 winerror
    cause = getattr(exc, '__cause__', None)
    if cause is not None:
        winerror = getattr(cause, 'winerror', None)
        if winerror is not None:
            return winerror
    return None


def _log_file_diag(path, prefix=""):
    """记录文件诊断信息（大小、存在性），帮助判断 onefile 解压是否完整。"""
    try:
        if os.path.exists(path):
            size = os.path.getsize(path)
            logger.warning(f"{prefix}文件存在但加载失败: {path} (大小: {size / 1024 / 1024:.2f} MB)")
        else:
            logger.warning(f"{prefix}文件不存在: {path}")
    except Exception as e:
        logger.debug(f"_log_file_diag: {e}")


def _is_mpv_available():
    _ensure_libmpv_loaded()
    return MPV_AVAILABLE


def _extract_dll_to_exe_dir():
    """Windows onefile 模式下，将 libmpv-2.dll 从 _MEIPASS 提取到 exe 同级目录。

    _MEIPASS 临时目录中的大 DLL（112MB+）可能因杀毒软件实时扫描锁定文件、
    解压不完整等原因导致 LoadLibrary 加载失败。提取到 exe 同级目录后可稳定加载。

    Returns:
        提取后的 dll 路径；不需要提取或提取失败时返回 None
    """
    if not is_windows() or not getattr(sys, 'frozen', False):
        return None

    try:
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, '_MEIPASS', None)
        if not meipass:
            return None

        filename = get_libmpv_filename()
        src = os.path.join(meipass, 'mpv', filename)
        dst = os.path.join(exe_dir, filename)

        if not os.path.exists(src):
            return None

        src_size = os.path.getsize(src)

        # 目标已存在且大小相同，跳过复制（版本未变化）
        if os.path.exists(dst) and os.path.getsize(dst) == src_size:
            return dst

        # 复制 DLL（112MB，可能需要数秒）
        import shutil
        logger.info(f"正在提取 {filename} 到程序目录: {dst}")
        shutil.copy2(src, dst)

        # 验证复制结果
        if os.path.exists(dst) and os.path.getsize(dst) == src_size:
            logger.info(f"{filename} 提取成功 ({src_size / 1024 / 1024:.1f} MB)")
            return dst
        else:
            logger.warning(f"{filename} 提取后大小不匹配，将回退到 _MEIPASS 加载")
            return None
    except PermissionError:
        logger.warning("无权限写入程序目录，跳过 DLL 提取（将直接从 _MEIPASS 加载）")
        return None
    except Exception as e:
        logger.warning(f"提取 DLL 到程序目录失败: {e}")
        return None


def _ensure_libmpv_loaded():
    global libmpv, MPV_AVAILABLE, _mpv_loaded, libmpv_path, _last_load_error
    if _mpv_loaded:
        return MPV_AVAILABLE

    _ensure_env_initialized()

    if is_linux() or is_android():
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except Exception as e:
            logger.debug(f"_ensure_libmpv_loaded: {e}")

    # Windows onefile 模式：先将 DLL 从 _MEIPASS 提取到 exe 同级目录，
    # 避免 _MEIPASS 临时目录中大文件加载不稳定的问题
    extracted_path = _extract_dll_to_exe_dir()

    # 逐一尝试所有候选路径：文件可能存在但损坏（UPX 解压损坏、杀毒软件拦截、依赖缺失），
    # ctypes.CDLL 失败时继续尝试下一个路径（exe 同级 mpv/ 目录等 fallback）
    candidate_paths = find_libmpv_paths()

    # 提取成功时优先从 exe 同级目录加载（最稳定的路径）
    if extracted_path:
        norm_extracted = os.path.normpath(extracted_path)
        candidate_paths = [extracted_path] + [
            p for p in candidate_paths if os.path.normpath(p) != norm_extracted
        ]

    last_error = None
    for path in candidate_paths:
        if not path or not os.path.exists(path):
            continue
        try:
            # Windows 上先添加 DLL 所在目录到搜索路径，
            # 确保 libmpv-2.dll 的依赖 DLL（如 MinGW 运行时、VC++ Runtime）能被找到。
            # Python 3.8+ 不再使用 PATH 搜索 DLL，必须显式调用 os.add_dll_directory。
            if is_windows():
                dll_dir = os.path.dirname(os.path.abspath(path))
                try:
                    os.add_dll_directory(dll_dir)
                except Exception as e:
                    logger.debug(f"add_dll_directory 失败: {e}")
            libmpv = ctypes.CDLL(path)

            libmpv.mpv_create.restype = ctypes.c_void_p
            libmpv.mpv_create.argtypes = []

            libmpv.mpv_initialize.restype = ctypes.c_int
            libmpv.mpv_initialize.argtypes = [ctypes.c_void_p]

            libmpv.mpv_set_option_string.restype = ctypes.c_int
            libmpv.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]

            libmpv.mpv_set_property_string.restype = ctypes.c_int
            libmpv.mpv_set_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]

            libmpv.mpv_set_property.restype = ctypes.c_int
            libmpv.mpv_set_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]

            libmpv.mpv_command.restype = ctypes.c_int
            libmpv.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]

            libmpv.mpv_destroy.restype = None
            libmpv.mpv_destroy.argtypes = [ctypes.c_void_p]

            libmpv.mpv_terminate_destroy.restype = None
            libmpv.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]

            libmpv.mpv_observe_property.restype = ctypes.c_int
            libmpv.mpv_observe_property.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_int]

            libmpv.mpv_set_wakeup_callback.restype = None
            libmpv.mpv_set_wakeup_callback.argtypes = [ctypes.c_void_p, ctypes.CFUNCTYPE(None, ctypes.c_void_p), ctypes.c_void_p]

            libmpv.mpv_wait_event.restype = ctypes.c_void_p
            libmpv.mpv_wait_event.argtypes = [ctypes.c_void_p, ctypes.c_double]

            libmpv.mpv_get_property_string.restype = ctypes.c_void_p
            libmpv.mpv_get_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

            libmpv.mpv_free.restype = None
            libmpv.mpv_free.argtypes = [ctypes.c_void_p]

            libmpv.mpv_get_property.restype = ctypes.c_int
            libmpv.mpv_get_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]

            libmpv.mpv_request_log_messages.restype = ctypes.c_int
            libmpv.mpv_request_log_messages.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

            libmpv.mpv_free_node_contents.restype = None
            libmpv.mpv_free_node_contents.argtypes = [ctypes.c_void_p]

            # 加载成功：更新 libmpv_path 和环境变量，确保后续使用正确的路径
            libmpv_path = path
            os.environ['MPV_LIBRARY'] = path
            mpv_dir = os.path.dirname(path)
            if not is_linux():
                os.environ['MPV_HOME'] = mpv_dir
            os.environ['PATH'] = mpv_dir + os.pathsep + os.environ.get('PATH', '')
            MPV_AVAILABLE = True
            _mpv_loaded = True
            return True
        except OSError as e:
            last_error = e
            # PyInstaller 的 PyInstallerImportError 继承自 OSError 但丢失了 winerror，
            # 需要从 __cause__ 获取原始异常的 winerror 才能判断真正的失败原因
            winerror = _extract_real_winerror(e)
            _log_file_diag(path, "libmpv加载失败诊断: ")
            if winerror == 126:
                # ERROR_MOD_NOT_FOUND: 文件存在但依赖的 DLL 缺失（通常是 VC++ Runtime）
                logger.warning(f"libmpv加载失败（依赖DLL缺失，可能是VC++ Runtime未安装）: {path} -> winerror={winerror}")
            elif winerror == 193:
                # ERROR_BAD_EXE_FORMAT: 文件存在但损坏或架构不匹配（32/64位）
                # onefile 模式下大文件(112MB+)解压不完整也会触发此错误
                logger.warning(f"libmpv加载失败（文件损坏或架构不匹配，可能是解压不完整）: {path} -> winerror={winerror}")
            elif winerror == 5:
                # ERROR_ACCESS_DENIED: 杀毒软件拦截或权限不足
                logger.warning(f"libmpv加载失败（访问被拒绝，可能是杀毒软件拦截）: {path} -> winerror={winerror}")
            else:
                cause = getattr(e, '__cause__', None)
                cause_str = str(cause) if cause else str(e)
                logger.warning(f"libmpv路径加载失败，尝试下一个: {path} -> winerror={winerror}, {cause_str}")
            continue
        except Exception as e:
            last_error = e
            logger.warning(f"libmpv路径加载失败，尝试下一个: {path} -> {e}")
            continue

    # 所有路径均失败：输出诊断信息
    logger.error(f"加载libmpv失败（所有候选路径均失败）: {last_error}")
    diag_msg = "libmpv加载失败"
    if is_linux():
        # Linux 的 OSError 文本本身已包含 "cannot open shared object file" 等原因，
        # 之前只写日志不返回，界面只能看到笼统的"加载失败"，用户无从下手。
        cause = getattr(last_error, '__cause__', None) if last_error else None
        cause_str = str(cause) if cause else str(last_error)
        diag_msg = (
            f"libmpv 加载失败：{cause_str}\n"
            "请确认已安装 libmpv（Ubuntu/Debian: sudo apt install libmpv2 或 libmpv1，"
            "Fedora: sudo dnf install mpv-libs，Arch: sudo pacman -S mpv），"
            "或把 libmpv.so 放到程序目录的 mpv/ 文件夹后重启。"
        )
        logger.error(f"诊断: {diag_msg}")
    elif is_windows():
        winerror = _extract_real_winerror(last_error) if last_error else None
        if winerror == 126:
            # ERROR_MOD_NOT_FOUND: 检查 VC++ Runtime 是否存在并提供解决建议
            system_dir = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
            vcruntime_files = ['MSVCP140.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll']
            missing = [f for f in vcruntime_files if not os.path.exists(os.path.join(system_dir, f))]
            if missing:
                diag_msg = (f"libmpv加载失败：Visual C++ Runtime 缺失（缺少 {', '.join(missing)}）。"
                            f"请安装 VC++ Redistributable: https://aka.ms/vs/17/release/vc_redist.x64.exe")
                logger.error(f"诊断: {diag_msg}")
            else:
                diag_msg = ("libmpv加载失败：依赖 DLL 缺失（VC++ Runtime 已安装，"
                            "可能是其他依赖项问题）。建议重新下载程序或安装 mpv 播放器。")
                logger.error(f"诊断: {diag_msg}")
        elif winerror == 193:
            # ERROR_BAD_EXE_FORMAT: 文件存在但损坏或架构不匹配
            # onefile 模式下 112MB 的 libmpv-2.dll 解压不完整是最可能的原因
            diag_msg = ("libmpv加载失败：DLL 文件可能损坏（onefile 解压不完整）或架构不匹配。"
                        "建议重新下载程序，或从 shinchiro/mpv-winbuild-cmake releases 下载 libmpv-2.dll 放到程序同目录。")
            logger.error(f"诊断: {diag_msg}")
        elif winerror == 5:
            diag_msg = "libmpv加载失败：访问被拒绝，可能是杀毒软件拦截。请将程序加入白名单。"
            logger.error(f"诊断: {diag_msg}")
        else:
            cause = getattr(last_error, '__cause__', None) if last_error else None
            cause_str = str(cause) if cause else str(last_error)
            diag_msg = f"libmpv加载失败（winerror={winerror}）: {cause_str}"
            logger.error(f"诊断: {diag_msg}")
    _last_load_error = diag_msg
    _mpv_loaded = False
    return False


class mpv_event(ctypes.Structure):
    _fields_ = [
        ('event_id', ctypes.c_int),
        ('error', ctypes.c_int),
        ('reply_userdata', ctypes.c_uint64),
        ('data', ctypes.c_void_p)
    ]


class mpv_event_end_file(ctypes.Structure):
    _fields_ = [
        ('reason', ctypes.c_int),
        ('error', ctypes.c_int),
        ('playlist_entry_id', ctypes.c_int64),
        ('playlist_insert_id', ctypes.c_int64),
        ('playlist_insert_num_entries', ctypes.c_int),
    ]


class mpv_event_property(ctypes.Structure):
    _fields_ = [
        ('name', ctypes.c_char_p),
        ('format', ctypes.c_int),
        ('data', ctypes.c_void_p),
    ]


class mpv_event_log_message(ctypes.Structure):
    """mpv 日志消息事件结构体（MPV_EVENT_LOG_MESSAGE）

    对应 mpv client.h 中的 mpv_event_log_message：
        const char *prefix;   // 模块前缀，如 "demuxer"、"vd"
        const char *level;    // 级别字符串，如 "debug"、"warn"、"error"
        const char *text;     // 日志文本（含换行符）
        mpv_log_level log_level;  // 级别枚举值（int）
    """
    _fields_ = [
        ('prefix', ctypes.c_char_p),
        ('level', ctypes.c_char_p),
        ('text', ctypes.c_char_p),
        ('log_level', ctypes.c_int),
    ]


MPV_EVENT_NONE = 0
MPV_EVENT_SHUTDOWN = 1
MPV_EVENT_LOG_MESSAGE = 2
MPV_EVENT_GET_PROPERTY_REPLY = 3
MPV_EVENT_SET_PROPERTY_REPLY = 4
MPV_EVENT_COMMAND_REPLY = 5
MPV_EVENT_START_FILE = 6
MPV_EVENT_END_FILE = 7
MPV_EVENT_FILE_LOADED = 8
MPV_EVENT_IDLE = 11
MPV_EVENT_TICK = 14
MPV_EVENT_CLIENT_MESSAGE = 16
MPV_EVENT_VIDEO_RECONFIG = 17
MPV_EVENT_AUDIO_RECONFIG = 18
MPV_EVENT_SEEK = 20
MPV_EVENT_PLAYBACK_RESTART = 21
MPV_EVENT_PROPERTY_CHANGE = 22
MPV_EVENT_QUEUE_OVERFLOW = 24
MPV_EVENT_HOOK = 25

MPV_FORMAT_NONE = 0
MPV_FORMAT_STRING = 1
MPV_FORMAT_OSD_STRING = 2
MPV_FORMAT_FLAG = 3
MPV_FORMAT_INT64 = 4
MPV_FORMAT_DOUBLE = 5
MPV_FORMAT_NODE = 6
MPV_FORMAT_NODE_ARRAY = 7
MPV_FORMAT_NODE_MAP = 8

MPV_END_FILE_REASON_EOF = 0
MPV_END_FILE_REASON_STOP = 2
MPV_END_FILE_REASON_QUIT = 3
MPV_END_FILE_REASON_ERROR = 4
MPV_END_FILE_REASON_REDIRECT = 5


def get_property_string(handle, name):
    if not handle or not libmpv:
        return None
    try:
        raw_ptr = libmpv.mpv_get_property_string(handle, name.encode('utf-8'))
        if not raw_ptr:
            return None
        value = ctypes.cast(raw_ptr, ctypes.c_char_p).value.decode('utf-8')
        libmpv.mpv_free(raw_ptr)
        return value
    except Exception:
        return None


def get_property_int(handle, name):
    if not handle or not libmpv:
        return None
    try:
        value = ctypes.c_int64()
        result = libmpv.mpv_get_property(handle, name.encode('utf-8'), MPV_FORMAT_INT64, ctypes.byref(value))
        if result < 0:
            return None
        return value.value
    except Exception:
        return None


def get_property_double(handle, name):
    if not handle or not libmpv:
        return None
    try:
        value = ctypes.c_double()
        result = libmpv.mpv_get_property(handle, name.encode('utf-8'), MPV_FORMAT_DOUBLE, ctypes.byref(value))
        if result < 0:
            return None
        return value.value
    except Exception:
        return None


# ---------- mpv_node 结构体定义（用于读取 node 类型属性如 af-metadata） ----------

class _mpv_node_list(ctypes.Structure):
    pass


class _mpv_node_union(ctypes.Union):
    _fields_ = [
        ('flag', ctypes.c_int64),
        ('double_', ctypes.c_double),
        ('int64', ctypes.c_int64),
        ('string', ctypes.c_char_p),
        ('list', ctypes.POINTER(_mpv_node_list)),
    ]


class _mpv_node(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [
        ('u', _mpv_node_union),
        ('format', ctypes.c_int),
    ]


_mpv_node_list._fields_ = [
    ('num', ctypes.c_int),
    ('values', ctypes.POINTER(_mpv_node)),
    ('keys', ctypes.POINTER(ctypes.c_char_p)),
]


def _parse_mpv_node(node):
    """递归解析 mpv_node 为 Python 对象"""
    fmt = node.format
    if fmt == MPV_FORMAT_STRING:
        return node.string.decode('utf-8') if node.string else None
    elif fmt == MPV_FORMAT_FLAG:
        return bool(node.flag)
    elif fmt == MPV_FORMAT_INT64:
        return node.int64
    elif fmt == MPV_FORMAT_DOUBLE:
        return node.double_
    elif fmt in (MPV_FORMAT_NODE_MAP, MPV_FORMAT_NODE_ARRAY, MPV_FORMAT_NODE):
        if not node.list:
            return {}
        lst = node.list.contents
        result = {}
        for i in range(lst.num):
            val = _parse_mpv_node(lst.values[i])
            if lst.keys and lst.keys[i]:
                key = lst.keys[i].decode('utf-8')
                result[key] = val
            else:
                result[i] = val
        return result
    return None


def get_property_node(handle, name):
    """读取 node 类型属性（如 af-metadata），返回 Python dict 或 None"""
    if not handle or not libmpv:
        return None
    try:
        node = _mpv_node()
        result = libmpv.mpv_get_property(
            handle, name.encode('utf-8'),
            MPV_FORMAT_NODE, ctypes.byref(node),
        )
        if result < 0:
            logger.debug(f"get_property_node('{name}') failed: error={result}")
            return None
        value = _parse_mpv_node(node)
        try:
            libmpv.mpv_free_node_contents(ctypes.byref(node))
        except Exception as e:
            logger.debug(f"get_property_node: {e}")
        return value
    except Exception as e:
        logger.debug(f"get_property_node error: {e}")
        return None


def create_mpv_handle():
    if not MPV_AVAILABLE or not libmpv:
        return None
    try:
        handle = libmpv.mpv_create()
        return handle if handle else None
    except Exception as e:
        logger.error(f"create_mpv_handle failed: {e}")
        return None


def initialize_mpv(handle):
    if not handle or not libmpv:
        return False
    try:
        return libmpv.mpv_initialize(handle) >= 0
    except Exception as e:
        logger.error(f"initialize_mpv failed: {e}")
        return False


def destroy_mpv(handle):
    if handle and libmpv:
        try:
            libmpv.mpv_destroy(handle)
        except Exception as e:
            logger.debug(f"destroy_mpv: {e}")


def terminate_destroy_mpv(handle):
    if handle and libmpv:
        try:
            libmpv.mpv_terminate_destroy(handle)
        except Exception:
            try:
                libmpv.mpv_destroy(handle)
            except Exception as e:
                logger.debug(f"terminate_destroy_mpv: {e}")


def set_property_string(handle, name, value):
    if not handle or not libmpv:
        return -1
    try:
        return libmpv.mpv_set_property_string(handle, name.encode('utf-8'), str(value).encode('utf-8'))
    except Exception:
        return -1


def set_property_int64(handle, name, value):
    if not handle or not libmpv:
        return -1
    try:
        v = ctypes.c_int64(int(value))
        return libmpv.mpv_set_property(handle, name.encode('utf-8'), MPV_FORMAT_INT64, ctypes.byref(v))
    except Exception:
        return -1


def set_option_string(handle, name, value):
    if not handle or not libmpv:
        return -1
    try:
        return libmpv.mpv_set_option_string(handle, name.encode('utf-8'), str(value).encode('utf-8'))
    except Exception:
        return -1


def send_command(handle, cmd_parts):
    if not handle or not libmpv:
        return -1
    try:
        cmd = [part.encode('utf-8') if isinstance(part, str) else part for part in cmd_parts] + [None]
        cmd_ptr = (ctypes.c_char_p * len(cmd))(*cmd)
        return libmpv.mpv_command(handle, cmd_ptr)
    except Exception:
        return -1


def wait_for_event(handle, timeout_sec):
    if not handle or not libmpv:
        return None
    try:
        event_ptr = libmpv.mpv_wait_event(handle, timeout_sec)
        if event_ptr:
            return ctypes.cast(event_ptr, ctypes.POINTER(mpv_event)).contents
    except Exception as e:
        logger.debug(f"wait_for_event 失败: {e}")
    return None


def wait_for_specific_event(handle, timeout_sec, target_events):
    import time
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            event_ptr = libmpv.mpv_wait_event(handle, 0.02)
            if event_ptr:
                event = ctypes.cast(event_ptr, ctypes.POINTER(mpv_event)).contents
                if event.event_id in target_events:
                    return event.event_id, event.error, event.data
                if event.event_id == MPV_EVENT_SHUTDOWN:
                    return MPV_EVENT_SHUTDOWN, 0, None
                if event.event_id == MPV_EVENT_NONE:
                    continue
        except Exception as e:
            logger.debug(f"wait_for_specific_event 失败: {e}")
            break
    return 0, 0, None


def observe_property(handle, reply_userdata, name, fmt):
    if not handle or not libmpv:
        return -1
    try:
        return libmpv.mpv_observe_property(handle, reply_userdata, name.encode('utf-8'), fmt)
    except Exception:
        return -1


_callback_refs = []
_callback_refs_lock = threading.Lock()
_MAX_CALLBACK_REFS = 16


def set_wakeup_callback(handle, callback, data):
    if not handle or not libmpv:
        return
    try:
        with _callback_refs_lock:
            _callback_refs.append(callback)
            if len(_callback_refs) > _MAX_CALLBACK_REFS:
                _callback_refs[:] = _callback_refs[-_MAX_CALLBACK_REFS:]
        libmpv.mpv_set_wakeup_callback(handle, callback, data)
    except Exception as e:
        logger.debug(f"set_wakeup_callback 失败: {e}")


MPV_RENDER_API_TYPE_OPENGL = b'opengl'
MPV_RENDER_PARAM_INVALID = 0
MPV_RENDER_PARAM_API_TYPE = 1
MPV_RENDER_PARAM_OPENGL_FBO = 2
MPV_RENDER_PARAM_FLIP_Y = 3
MPV_RENDER_PARAM_DEPTH = 4
MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME = 11
MPV_RENDER_PARAM_SKIP_RENDERING = 12


class mpv_opengl_fbo(ctypes.Structure):
    _fields_ = [
        ('fbo', ctypes.c_int),
        ('w', ctypes.c_int),
        ('h', ctypes.c_int),
        ('internal_format', ctypes.c_int),
    ]


class mpv_render_param(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_int),
        ('data', ctypes.c_void_p),
    ]


_RENDER_CB_REFS = []
_render_cb_refs_lock = threading.Lock()


def init_render_api():
    if not libmpv:
        return False
    try:
        libmpv.mpv_render_context_create.restype = ctypes.c_int
        libmpv.mpv_render_context_create.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(mpv_render_param)
        ]
        libmpv.mpv_render_context_set_parameter.restype = ctypes.c_int
        libmpv.mpv_render_context_set_parameter.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(mpv_render_param)
        ]
        libmpv.mpv_render_context_render.restype = ctypes.c_int
        libmpv.mpv_render_context_render.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(mpv_render_param)
        ]
        libmpv.mpv_render_context_report_swap.restype = None
        libmpv.mpv_render_context_report_swap.argtypes = [ctypes.c_void_p]
        libmpv.mpv_render_context_free.restype = None
        libmpv.mpv_render_context_free.argtypes = [ctypes.c_void_p]
        libmpv.mpv_render_context_set_update_callback.restype = None
        libmpv.mpv_render_context_set_update_callback.argtypes = [
            ctypes.c_void_p,
            ctypes.CFUNCTYPE(None, ctypes.c_void_p),
            ctypes.c_void_p,
        ]
        return True
    except Exception as e:
        logger.error(f"初始化mpv render API失败: {e}")
        return False


def render_context_create(mpv_handle):
    if not libmpv or not mpv_handle:
        return None
    try:
        # 注意：必须显式构造 ctypes 数组，不能直接传 Python list。
        # Windows Python 的 ctypes 对 list -> POINTER(struct) 做了隐式转换，
        # 但 macOS Python 严格检查类型，传 list 会抛
        # "expected LP_mpv_render_param instance instead of list"，
        # 导致 render context 创建失败、画面黑屏（仅有声）。
        params = (mpv_render_param * 2)(
            mpv_render_param(MPV_RENDER_PARAM_API_TYPE,
                             ctypes.cast(ctypes.c_char_p(MPV_RENDER_API_TYPE_OPENGL), ctypes.c_void_p)),
            mpv_render_param(MPV_RENDER_PARAM_INVALID, ctypes.c_void_p(0)),
        )
        ctx = ctypes.c_void_p()
        ret = libmpv.mpv_render_context_create(ctypes.byref(ctx), mpv_handle, params)
        if ret < 0:
            logger.error(f"mpv_render_context_create失败: {ret}")
            return None
        return ctx.value
    except Exception as e:
        logger.error(f"mpv_render_context_create异常: {e}")
        return None


def render_context_render(render_ctx, fbo, width, height, flip_y=False, block_for_target_time=False):
    if not libmpv or not render_ctx:
        return -1
    try:
        gl_fbo = mpv_opengl_fbo(fbo=fbo, w=width, h=height, internal_format=0)
        flip = ctypes.c_int(1 if flip_y else 0)
        # 默认不阻塞：帧到达由 mpv update_callback 驱动，阻塞只会让 GUI 线程
        # 在暂停/低帧率直播时卡在 render 调用里。只有需要按显示时钟节流的
        # 场景才显式传 True。
        block = ctypes.c_int(1 if block_for_target_time else 0)
        # 同 render_context_create：必须用 ctypes 数组而非 list，
        # 否则 macOS Python 会因类型严格检查抛 TypeError。
        # gl_fbo / flip / block 必须保留在栈上直到 render 调用返回，
        # 因为 ctypes 数组只是引用了它们的 byref 指针。
        params = (mpv_render_param * 4)(
            mpv_render_param(MPV_RENDER_PARAM_OPENGL_FBO,
                             ctypes.cast(ctypes.byref(gl_fbo), ctypes.c_void_p)),
            mpv_render_param(MPV_RENDER_PARAM_FLIP_Y,
                             ctypes.cast(ctypes.byref(flip), ctypes.c_void_p)),
            mpv_render_param(MPV_RENDER_PARAM_BLOCK_FOR_TARGET_TIME,
                             ctypes.cast(ctypes.byref(block), ctypes.c_void_p)),
            mpv_render_param(MPV_RENDER_PARAM_INVALID, ctypes.c_void_p(0)),
        )
        return libmpv.mpv_render_context_render(render_ctx, params)
    except Exception as e:
        logger.error(f"mpv_render_context_render异常: {e}")
        return -1


def render_context_report_swap(render_ctx):
    if libmpv and render_ctx:
        try:
            libmpv.mpv_render_context_report_swap(render_ctx)
        except Exception as e:
            logger.debug(f"render_context_report_swap: {e}")


def render_context_set_update_callback(render_ctx, callback, user_data=None):
    if not libmpv or not render_ctx:
        return
    try:
        with _render_cb_refs_lock:
            _RENDER_CB_REFS.append(callback)
            if len(_RENDER_CB_REFS) > _MAX_CALLBACK_REFS:
                _RENDER_CB_REFS[:] = _RENDER_CB_REFS[-_MAX_CALLBACK_REFS:]
        libmpv.mpv_render_context_set_update_callback(render_ctx, callback, user_data or ctypes.c_void_p(0))
    except Exception as e:
        logger.error(f"mpv_render_context_set_update_callback异常: {e}")


def render_context_free(render_ctx):
    if libmpv and render_ctx:
        try:
            libmpv.mpv_render_context_free(render_ctx)
        except Exception as e:
            logger.debug(f"render_context_free: {e}")
