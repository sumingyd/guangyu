"""跨平台用户目录解析、旧数据迁移与降级记录。

打包后的程序目录（exe 同级目录或 PyInstaller 单文件解包目录）不一定可写，
把配置、日志、缓存写在那里会导致设置存不住、日志丢失、截图被临时目录清空。
本模块统一提供可写的用户级目录：

- Windows: %APPDATA%\\GuangYu（配置/日志）、%LOCALAPPDATA%\\GuangYu（缓存）
- macOS:   ~/Library/Application Support/GuangYu、~/Library/Caches/GuangYu
- Linux:   $XDG_CONFIG_HOME/GuangYu、$XDG_CACHE_HOME/GuangYu
- Android: IPTV_DATA_DIR 指向的根目录（文件管理器可见时为 /sdcard/GuangYu），
           内部固定按用途分为 config / logs / cache / data / exports 子目录

当首选目录不可写时按「应用私有目录 -> 程序目录 -> 系统临时目录」降级，并把
降级原因写入降级目录下的 path_fallback.log，保证用户能看到可读记录。
"""

import json
import os
import shutil
import sys
import tempfile
import time

APP_NAME = 'GuangYu'

# Android 共享根目录名（/sdcard/GuangYu）
ANDROID_APP_DIR = 'GuangYu'

# Android 根目录下的固定子目录：配置 / 日志 / 缓存 / 数据 / 导出
SUBDIR_CONFIG = 'config'
SUBDIR_LOGS = 'logs'
SUBDIR_CACHE = 'cache'
SUBDIR_DATA = 'data'
SUBDIR_EXPORTS = 'exports'
ANDROID_SUBDIRS = (SUBDIR_CONFIG, SUBDIR_LOGS, SUBDIR_CACHE, SUBDIR_DATA, SUBDIR_EXPORTS)

# 目录布局版本：布局变更时递增，迁移记录写入 storage_layout.json
LAYOUT_VERSION = 1
LAYOUT_MARKER = 'storage_layout.json'

# 旧版本的应用目录名（迁移来源）
LEGACY_DIR_NAMES = ('ISEP', 'ISEPP', 'IPTV_Scanner_Editor_Pro', 'GuangYu')

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

# 需要迁移到用户缓存目录的子目录（可重新生成，迁移失败不影响使用）
MIGRATION_CACHE_DIRS = ('logo_cache', 'screenshots')

# Android 旧扁平目录里按缓存归类的子目录
ANDROID_CACHE_SUBDIRS = MIGRATION_CACHE_DIRS + (
    'logos', 'thumbnails', 'thumb_cache', 'subtitles', 'subtitle_cache',
    'autocrop', 'epg_cache', 'cache',
)

# Android 旧扁平目录里按「长期数据」归类的文件（不随缓存清理删除）
ANDROID_DATA_FILES = ('favorites.json', 'play_history.json')

_migration_done = False
_android_migration_done = False
_degraded_messages = []
_android_dir_cache: dict = {}


def _app_platform() -> str:
    # Chaquopy 下 sys.platform 可能是 'linux'，不能只靠它判断 Android；
    # Android 桥接层会显式设置 IPTV_ANDROID=1，避免误用桌面端的 XDG 目录。
    if (os.environ.get('IPTV_ANDROID') == '1'
            or getattr(sys, 'platform', '') == 'android'
            or 'ANDROID_ARGUMENT' in os.environ
            or 'ANDROID_ROOT' in os.environ):
        return 'android'
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


# ----------------------------------------------------------------------
# Android 根目录与子目录
# ----------------------------------------------------------------------

def get_android_root() -> str:
    """Android 数据根目录（IPTV_DATA_DIR）；非 Android 环境返回空串。

    新版约定 IPTV_DATA_DIR 直接指向根目录（如 /sdcard/GuangYu 或
    getExternalFilesDir()/GuangYu），子目录由本模块按用途拼出。
    """
    if _app_platform() != 'android':
        return ''
    return os.environ.get('IPTV_DATA_DIR', '').rstrip('/\\')


def get_android_data_dir() -> str:
    """Android 数据根目录（兼容旧调用方，语义已从 ISEP 目录变为根目录）。"""
    return get_android_root()


def get_android_public_root() -> str:
    """Android 共享存储根目录（/sdcard/GuangYu），由 Kotlin 端传入。"""
    if _app_platform() != 'android':
        return ''
    return os.environ.get('IPTV_PUBLIC_ROOT', '').rstrip('/\\')


def get_android_private_root() -> str:
    """Android 应用私有根目录（getExternalFilesDir/GuangYu），由 Kotlin 端传入。"""
    if _app_platform() != 'android':
        return ''
    return os.environ.get('IPTV_PRIVATE_ROOT', '').rstrip('/\\')


def get_legacy_base_dir() -> str:
    """旧版本写数据的目录：打包后为 exe 同级目录，开发环境为项目根目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _preferred_config_dir() -> str:
    android_dir = get_android_root()
    if android_dir:
        return os.path.join(android_dir, SUBDIR_CONFIG)
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
    android_dir = get_android_root()
    if android_dir:
        return os.path.join(android_dir, SUBDIR_CACHE)
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
    if not path:
        return False
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write_probe')
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('')
        os.remove(probe)
        return True
    except OSError:
        return False


def is_writable_dir(path: str) -> bool:
    """公开的可写性探针：创建目录并写入/删除临时文件。"""
    return _ensure_writable_dir(path)


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


def _record_degraded(kind: str, preferred: str, actual: str, reason: str = '') -> None:
    message = f"{kind}目录不可写({preferred})，已降级使用: {actual}"
    if reason:
        message += f"（{reason}）"
    _degraded_messages.append(message)
    _append_record(actual, message)


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


def _resolve_android_dir(name: str) -> str:
    """解析 Android 根目录下的用途子目录：根 -> 私有根 -> 临时目录逐级降级。"""
    root = get_android_root()
    if not root:
        return ''
    private = get_android_private_root()
    cache_key = (root, private, name)
    cached = _android_dir_cache.get(cache_key)
    if cached and os.path.isdir(cached):
        return cached

    primary = os.path.join(root, name)
    if _ensure_writable_dir(primary):
        _android_dir_cache[cache_key] = primary
        return primary
    if private:
        secondary = os.path.join(private, name)
        if os.path.abspath(secondary) != os.path.abspath(primary) and _ensure_writable_dir(secondary):
            _record_degraded(name, primary, secondary)
            _android_dir_cache[cache_key] = secondary
            return secondary
    fallback = os.path.join(tempfile.gettempdir(), APP_NAME, name)
    _record_degraded(name, primary, fallback)
    _android_dir_cache[cache_key] = fallback
    return fallback


def get_config_dir() -> str:
    """用户配置目录（config.ini、订阅、断点续播、书签、映射等）。"""
    if _app_platform() == 'android' and get_android_root():
        return _resolve_android_dir(SUBDIR_CONFIG)
    return _resolve_dir('config', _preferred_config_dir(), get_legacy_base_dir())


def get_cache_dir() -> str:
    """用户缓存目录（缩略图、截图、台标、EPG 缓存等）。"""
    if _app_platform() == 'android' and get_android_root():
        return _resolve_android_dir(SUBDIR_CACHE)
    return _resolve_dir('cache', _preferred_cache_dir(),
                        os.path.join(get_legacy_base_dir(), 'cache'))


def get_log_dir() -> str:
    """日志目录：Android 为根目录下 logs/，桌面端与配置目录同处。"""
    if _app_platform() == 'android' and get_android_root():
        return _resolve_android_dir(SUBDIR_LOGS)
    return get_config_dir()


def get_data_dir() -> str:
    """长期数据目录（收藏、播放历史等不随缓存清理删除的数据）。"""
    if _app_platform() == 'android' and get_android_root():
        return _resolve_android_dir(SUBDIR_DATA)
    return get_config_dir()


def get_export_dir() -> str:
    """导出目录（M3U、EPG、备份文件等用户主动导出的产物）。"""
    if _app_platform() == 'android' and get_android_root():
        return _resolve_android_dir(SUBDIR_EXPORTS)
    return os.path.join(get_config_dir(), SUBDIR_EXPORTS)


def get_degraded_messages() -> list:
    """本次进程内发生过的目录降级原因（供日志/界面提示读取）。"""
    return list(_degraded_messages)


def ensure_android_layout(root: str = None) -> list:
    """创建 Android 根目录下的用途子目录并写入布局标记，返回已就绪目录列表。"""
    root = root or get_android_root()
    if not root:
        return []
    created = []
    for name in ANDROID_SUBDIRS:
        directory = os.path.join(root, name)
        try:
            os.makedirs(directory, exist_ok=True)
            created.append(directory)
        except OSError as e:
            _append_record(root, f"创建目录失败({directory}): {e}", 'migration.log')
    marker = _read_layout_marker(root)
    marker['layout_version'] = LAYOUT_VERSION
    marker['root'] = root
    marker.setdefault('migrated_sources', [])
    _write_layout_marker(root, marker)
    return created


def _layout_marker_path(root: str) -> str:
    return os.path.join(root, LAYOUT_MARKER)


def _read_layout_marker(root: str) -> dict:
    try:
        with open(_layout_marker_path(root), 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _write_layout_marker(root: str, data: dict) -> None:
    try:
        os.makedirs(root, exist_ok=True)
        tmp = _layout_marker_path(root) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _layout_marker_path(root))
    except OSError as e:
        _append_record(root, f"写入布局标记失败: {e}", 'migration.log')


def _android_migration_sources(root: str, private_root: str) -> list:
    """收集需要迁移的旧目录（按优先级），过滤掉当前根目录本身。"""
    sources = []
    seen = set()

    def add(path):
        if not path:
            return
        path = os.path.abspath(path)
        if path in seen:
            return
        if path == os.path.abspath(root):
            return
        seen.add(path)
        sources.append(path)

    root_abs = os.path.abspath(root)
    parent = os.path.dirname(root_abs)
    if os.path.basename(root_abs) == ANDROID_APP_DIR:
        # 旧版共享目录 /sdcard/ISEP
        add(os.path.join(parent, 'ISEP'))
        add(os.path.join(parent, 'ISEPP'))

    bases = [
        private_root,
        os.environ.get('IPTV_EXTERNAL_FILES_DIR', ''),
        os.environ.get('IPTV_INTERNAL_DIR', ''),
    ]
    for base in bases:
        if not base:
            continue
        # 旧目录既可能挂在私有根目录本身下（<ext>/ISEP），
        # 也可能挂在它的父目录下（<ext>/GuangYu 与 <ext>/ISEP 同级）
        for parent in (base, os.path.dirname(os.path.abspath(base))):
            for name in LEGACY_DIR_NAMES:
                add(os.path.join(parent, name))
    return sources


def _classify_android_item(name: str, src_root: str) -> str:
    """把旧扁平目录里的条目归类到新布局：config / logs / cache / data，未知返回空。"""
    # 已经是新布局的子目录（此前在私有目录/共享目录之间切换过）：按名称归位
    if name in ANDROID_SUBDIRS:
        return name
    if name in MIGRATION_FILES:
        return SUBDIR_CONFIG
    lower = name.lower()
    if lower.endswith('.log'):
        return SUBDIR_LOGS
    if name in ANDROID_CACHE_SUBDIRS:
        return SUBDIR_CACHE
    if name in ANDROID_DATA_FILES:
        return SUBDIR_DATA
    if os.path.isdir(os.path.join(src_root, name)):
        return ''
    return SUBDIR_DATA


def _copy_item(src: str, dst: str, is_dir: bool, log_dir: str) -> bool:
    """复制单个条目；目标已存在时跳过（不覆盖用户现有数据）。失败返回 False。"""
    if os.path.exists(dst):
        return True
    try:
        if is_dir:
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)
        return True
    except OSError as e:
        _append_record(log_dir, f"迁移失败({src} -> {dst}): {e}", 'migration.log')
        return False


def migrate_android_layout(root: str = None, private_root: str = None) -> list:
    """把旧目录里的数据迁移到新的分类布局，幂等且失败不丢数据。

    规则：
    - 只复制不覆盖：目标已存在则跳过，复制失败保留源文件；
    - 迁移前先确保新布局目录存在；
    - 每个来源目录处理成功后写入 storage_layout.json 的 migrated_sources，重复调用直接跳过；
    - 只有来源目录里的条目全部迁移成功才删除旧目录，避免残留两份互不一致的数据。
    """
    root = root or get_android_root()
    if not root:
        return []
    private_root = private_root or get_android_private_root()

    ensure_android_layout(root)
    marker = _read_layout_marker(root)
    migrated_sources = list(marker.get('migrated_sources') or [])
    log_dir = os.path.join(root, SUBDIR_LOGS)

    migrated = []
    for src_root in _android_migration_sources(root, private_root):
        if not os.path.isdir(src_root):
            continue
        if src_root in migrated_sources:
            continue

        failed = False
        unhandled = []
        try:
            entries = os.listdir(src_root)
        except OSError as e:
            _append_record(log_dir, f"读取旧目录失败({src_root}): {e}", 'migration.log')
            continue

        for name in entries:
            if name in ('.write_probe', LAYOUT_MARKER):
                continue
            category = _classify_android_item(name, src_root)
            src = os.path.join(src_root, name)
            is_dir = os.path.isdir(src)
            if not category:
                unhandled.append(name)
                continue
            if is_dir and name in ANDROID_SUBDIRS:
                # 来源已是分类布局：把子目录内容合并到目标同名目录，
                # 不能整目录跳过，否则从私有目录切到共享目录时会丢数据
                try:
                    for child in os.listdir(src):
                        child_src = os.path.join(src, child)
                        child_dst = os.path.join(root, name, child)
                        if not _copy_item(child_src, child_dst, os.path.isdir(child_src), log_dir):
                            failed = True
                        else:
                            migrated.append(child_dst)
                except OSError as e:
                    _append_record(log_dir, f"迁移目录失败({src}): {e}", 'migration.log')
                    failed = True
                continue
            dst = os.path.join(root, category, name)
            if _copy_item(src, dst, is_dir, log_dir):
                migrated.append(dst)
            else:
                failed = True

        if failed:
            _append_record(log_dir, f"旧目录未完全迁移，保留原目录: {src_root}", 'migration.log')
            continue
        if unhandled:
            _append_record(
                log_dir,
                f"旧目录存在未识别条目，保留原目录: {src_root} ({', '.join(unhandled[:5])})",
                'migration.log')
            continue

        migrated_sources.append(src_root)
        try:
            shutil.rmtree(src_root)
        except OSError as e:
            _append_record(log_dir, f"删除旧目录失败({src_root}): {e}", 'migration.log')
        _append_record(log_dir, f"已从旧目录迁移数据: {src_root}", 'migration.log')

    marker['migrated_sources'] = migrated_sources
    marker['layout_version'] = LAYOUT_VERSION
    marker['root'] = root
    _write_layout_marker(root, marker)

    if migrated:
        _append_record(log_dir, f"本次迁移 {len(migrated)} 项数据到 {root}", 'migration.log')
    return migrated


def get_storage_info() -> dict:
    """当前实际使用的存储路径信息（供设置/关于页展示）。"""
    android = _app_platform() == 'android'
    root = get_android_root() if android else ''
    info = {
        'platform': _app_platform(),
        'root': root or get_config_dir(),
        'config_dir': get_config_dir(),
        'log_dir': get_log_dir(),
        'cache_dir': get_cache_dir(),
        'data_dir': get_data_dir(),
        'export_dir': get_export_dir(),
    }
    if android:
        public_root = get_android_public_root()
        shared = bool(public_root) and os.path.abspath(root) == os.path.abspath(public_root)
        degraded = get_degraded_messages()
        if not shared and public_root and os.path.isdir(public_root):
            # 共享目录存在但当前进不去：多半是权限被撤销，
            # 必须明确提示，避免用户以为频道/配置丢了
            degraded.append(
                f'检测到共享目录 {public_root} 已存在但当前无权访问，'
                f'重新授予「所有文件访问权限」并重启应用即可恢复其中的数据'
            )
        info.update({
            'shared': shared,
            'public_root': public_root,
            'private_root': get_android_private_root(),
            'degraded': degraded,
            'uninstall_note': (
                '卸载或清除数据不会删除共享目录中的文件' if shared
                else '当前使用应用私有目录，卸载应用会一并删除'
            ),
        })
    return info


def migrate_legacy_data(config_dir: str = None, cache_dir: str = None,
                        legacy_dir: str = None) -> list:
    """首次启动时把旧位置的数据复制到用户目录。

    Android 走 migrate_android_layout（按用途分类迁移到新布局）；
    桌面端只在「新位置还没有 config.ini」时执行，使用复制而不是移动，
    复制失败时旧数据保持原样，不会丢失。返回已迁移的目标路径列表。
    """
    global _migration_done, _android_migration_done
    if _app_platform() == 'android':
        if _android_migration_done:
            return []
        _android_migration_done = True
        return migrate_android_layout(get_android_root(), get_android_private_root())

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
    global _migration_done, _android_migration_done
    _migration_done = False
    _android_migration_done = False
    _degraded_messages.clear()
    _android_dir_cache.clear()
