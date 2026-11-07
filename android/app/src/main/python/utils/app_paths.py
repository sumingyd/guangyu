"""跨平台用户目录解析、旧数据迁移与降级记录。

打包后的程序目录（exe 同级目录或 PyInstaller 单文件解包目录）不一定可写，
把配置、日志、缓存写在那里会导致设置存不住、日志丢失、截图被临时目录清空。
本模块统一提供可写的用户级目录：

- Windows: %APPDATA%\\GuangYu（配置/日志）、%LOCALAPPDATA%\\GuangYu（缓存）
- macOS:   ~/Library/Application Support/GuangYu、~/Library/Caches/GuangYu
- Linux:   $XDG_CONFIG_HOME/GuangYu、$XDG_CACHE_HOME/GuangYu
- Android: IPTV_DATA_DIR 指向的 ISEP 目录（沿用原有约定）

当首选目录不可写时按「程序目录 -> 系统临时目录」降级，并把降级原因写入
降级目录下的 path_fallback.log，保证用户能看到可读记录。
"""

import os
import shutil
import sys
import tempfile
import time

APP_NAME = 'GuangYu'

# 需要从旧位置迁移到用户配置目录的文件（用户设置、订阅、断点、收藏、映射）
MIGRATION_FILES = (
    'config.ini',
    'resume_positions.json',
    'bookmarks.json',
    'playback_settings.json',
    'channel_mappings_cache.json',
    'channel_mappings_cache.json.etag',
    'user_channel_mappings.json',
    'channel_fingerprints.json',
    'channels_cache.json',
    'temp_channels_cache.json',
    'video_presets.json',
)

# 需要迁移到用户缓存目录的子目录
MIGRATION_CACHE_DIRS = ('logo_cache', 'screenshots')

_migration_done = False
_degraded_messages = []


def _app_platform() -> str:
    if getattr(sys, 'platform', '') == 'android' or 'ANDROID_ARGUMENT' in os.environ:
        return 'android'
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


def get_android_data_dir() -> str:
    """Android 数据目录（ISEP）；非 Android 环境返回空串。"""
    if _app_platform() != 'android':
        return ''
    data = os.environ.get('IPTV_DATA_DIR', '')
    if not data:
        return ''
    if os.path.basename(data.rstrip('/\\')) == 'ISEP':
        return data
    return os.path.join(data, 'ISEP')


def get_legacy_base_dir() -> str:
    """旧版本写数据的目录：打包后为 exe 同级目录，开发环境为项目根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _preferred_config_dir() -> str:
    android_dir = get_android_data_dir()
    if android_dir:
        return android_dir
    override = os.environ.get('IPTV_CONFIG_DIR', '')
    if override:
        return override
    platform = _app_platform()
    if platform == 'windows':
        base = os.environ.get('APPDATA') or os.path.join(
            os.path.expanduser('~'), 'AppData', 'Roaming')
    elif platform == 'macos':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(
            os.path.expanduser('~'), '.config')
    return os.path.join(base, APP_NAME)


def _preferred_cache_dir() -> str:
    android_dir = get_android_data_dir()
    if android_dir:
        return os.path.join(android_dir, 'cache')
    platform = _app_platform()
    if platform == 'windows':
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.path.join(
            os.path.expanduser('~'), 'AppData', 'Local')
    elif platform == 'macos':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Caches')
    else:
        base = os.environ.get('XDG_CACHE_HOME') or os.path.join(
            os.path.expanduser('~'), '.cache')
    return os.path.join(base, APP_NAME)


def _ensure_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write_probe')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('')
        os.remove(probe)
        return True
    except OSError:
        return False


def _append_record(directory: str, message: str, filename: str = 'path_fallback.log') -> None:
    """把降级/迁移原因写入目录下的可读日志，失败时静默（不能因此崩溃）。"""
    try:
        os.makedirs(directory, exist_ok=True)
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n"
        with open(os.path.join(directory, filename), 'a', encoding='utf-8') as f:
            f.write(line)
    except OSError:
        pass
    stream = sys.stderr if sys.stderr is not None else getattr(sys, '__stderr__', None)
    if stream is not None:
        try:
            stream.write(f"[GuangYu] {message}\n")
        except Exception:
            pass


def _resolve_dir(kind: str, preferred: str, legacy: str) -> str:
    if _ensure_writable_dir(preferred):
        return preferred
    if os.path.abspath(preferred) != os.path.abspath(legacy) and _ensure_writable_dir(legacy):
        message = f"{kind}目录不可写({preferred})，已降级使用程序目录: {legacy}"
        _degraded_messages.append(message)
        _append_record(legacy, message)
        return legacy
    fallback = os.path.join(tempfile.gettempdir(), APP_NAME, kind)
    message = f"{kind}目录不可写({preferred})，已降级使用临时目录: {fallback}"
    _degraded_messages.append(message)
    _append_record(fallback, message)
    return fallback


def get_config_dir() -> str:
    """用户配置目录（config.ini、订阅、断点续播、书签、映射等）。"""
    return _resolve_dir('config', _preferred_config_dir(), get_legacy_base_dir())


def get_cache_dir() -> str:
    """用户缓存目录（缩略图、截图、台标、EPG 缓存等）。"""
    return _resolve_dir('cache', _preferred_cache_dir(),
                        os.path.join(get_legacy_base_dir(), 'cache'))


def get_log_dir() -> str:
    """日志目录：与配置目录同处用户目录，便于用户找到。"""
    return get_config_dir()


def get_degraded_messages() -> list:
    """本次进程内发生过的目录降级原因（供日志/界面提示读取）。"""
    return list(_degraded_messages)


def migrate_legacy_data(config_dir: str = None, cache_dir: str = None,
                        legacy_dir: str = None) -> list:
    """首次启动时把旧位置的数据复制到用户目录。

    只在「新位置还没有 config.ini」时执行；使用复制而不是移动，复制失败时
    旧数据保持原样，不会丢失。返回已迁移的目标路径列表。
    """
    global _migration_done
    if _migration_done:
        return []
    _migration_done = True

    config_dir = config_dir or get_config_dir()
    cache_dir = cache_dir or get_cache_dir()
    legacy_dir = legacy_dir or get_legacy_base_dir()

    if os.path.abspath(config_dir) == os.path.abspath(legacy_dir):
        return []
    if os.path.exists(os.path.join(config_dir, 'config.ini')):
        return []

    migrated = []
    for name in MIGRATION_FILES:
        src = os.path.join(legacy_dir, name)
        dst = os.path.join(config_dir, name)
        if not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            os.makedirs(config_dir, exist_ok=True)
            shutil.copy2(src, dst)
            migrated.append(dst)
        except OSError as e:
            _append_record(config_dir, f"迁移文件失败({src} -> {dst}): {e}", 'migration.log')

    for name in MIGRATION_CACHE_DIRS:
        src = os.path.join(legacy_dir, name)
        dst = os.path.join(cache_dir, name)
        if not os.path.isdir(src) or os.path.isdir(dst):
            continue
        try:
            os.makedirs(cache_dir, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)
            migrated.append(dst)
        except OSError as e:
            _append_record(cache_dir, f"迁移缓存目录失败({src} -> {dst}): {e}", 'migration.log')

    if migrated:
        _append_record(config_dir, f"已从旧目录迁移 {len(migrated)} 项数据: {legacy_dir}",
                       'migration.log')
    return migrated


def reset_for_tests() -> None:
    """重置模块级状态（仅测试使用）。"""
    global _migration_done
    _migration_done = False
    _degraded_messages.clear()
