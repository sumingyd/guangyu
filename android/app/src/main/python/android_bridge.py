import logging
import os
import sys
import time
import secrets

_t0 = time.time()

# 应用版本信息（由 Kotlin 端通过 set_app_info() 设置）
_app_version = '0.0.0.0'
_app_build_date = 'unknown'

# 管理服务器认证 token（首次启动时生成，局域网访问需携带此 token）
# Kotlin 端通过 get_admin_token() 获取，显示在 UI 上供用户扫码或手动输入
_admin_auth_token = ''


# android_bridge 专用 logger：消息通过传播到 root logger 写入 app.log
_ab_logger = logging.getLogger('android_bridge')


def _log(msg, level='I'):
    """统一日志输出：同时写入 logcat（via print）和 app.log（via logging）

    Chaquopy 会把 print() 重定向到 logcat 的 python 标签，
    logging 模块的消息通过 root logger 的 handler 写入 app.log 文件。
    """
    elapsed = time.time() - _t0
    print(f'[{level}][{elapsed:6.2f}s] {msg}', flush=True)
    # 同步写入 app.log（level 映射：I→INFO, W→WARNING, E→ERROR, D→DEBUG）
    py_level = {'I': logging.INFO, 'W': logging.WARNING,
                'E': logging.ERROR, 'D': logging.DEBUG}.get(level, logging.INFO)
    _ab_logger.log(py_level, msg)


def _setup_android_paths(ext_files_dir='', files_dir='', native_lib_dir='',
                         public_root='', private_root=''):
    """设置 Android 数据根目录（IPTV_DATA_DIR 环境变量）与子目录布局。

    根目录优先级：
    1. public_root（共享存储 /sdcard/GuangYu，需要 MANAGE_EXTERNAL_STORAGE）
    2. private_root（getExternalFilesDir()/GuangYU，无需权限，覆盖安装不丢失）
    3. ext_files_dir/GuangYu（Kotlin 传递的外部私有目录）
    4. files_dir/GuangYu（最终兜底）

    根目录下固定创建 config / logs / cache / data / exports 子目录，
    并把旧目录（ISEP / ISEPP / IPTV_Scanner_Editor_Pro）的数据分类迁移过来。
    """
    from utils.app_paths import (
        APP_NAME, ensure_android_layout, is_writable_dir, migrate_android_layout,
    )

    # Chaquopy 下 sys.platform 可能是 'linux'，显式标记 Android 平台，
    # 否则 app_paths 会退回桌面端的 XDG 目录（曾导致配置读到 .config/GuangYu）
    os.environ['IPTV_ANDROID'] = '1'

    target_dir = None

    # 尝试通过 jnius 获取路径（Chaquopy 某些版本支持）
    try:
        from jnius import autoclass  # type: ignore
        Python = autoclass('com.chaquo.python.Python')
        app = Python.getPlatform().getApplication()
        Environment = autoclass('android.os.Environment')

        # 确保 sys.path 包含 files_dir（Chaquopy 需要）
        jnius_files_dir = app.getFilesDir().getAbsolutePath()
        if jnius_files_dir not in sys.path:
            sys.path.insert(0, jnius_files_dir)
        # 同步 Kotlin 传递的路径（jnius 可用时以 jnius 为准）
        if not files_dir:
            files_dir = jnius_files_dir
        if not ext_files_dir:
            ext_files_dir = app.getExternalFilesDir(None).getAbsolutePath()
        if not public_root or not private_root:
            try:
                ext_storage = Environment.getExternalStorageDirectory().getAbsolutePath()
                public_root = public_root or os.path.join(ext_storage, APP_NAME)
            except Exception as e:
                _log(f'_setup_android_paths: resolve public root failed: {e}', 'W')
            if not private_root and ext_files_dir:
                private_root = os.path.join(ext_files_dir, APP_NAME)
    except Exception as e:
        _log(f'_setup_android_paths: jnius unavailable ({e}), using Kotlin-provided paths')

    if not private_root and ext_files_dir:
        private_root = os.path.join(ext_files_dir, APP_NAME)

    # 记录候选目录，供目录解析与迁移使用
    if public_root:
        os.environ['IPTV_PUBLIC_ROOT'] = public_root
    if private_root:
        os.environ['IPTV_PRIVATE_ROOT'] = private_root
    if ext_files_dir:
        os.environ['IPTV_EXTERNAL_FILES_DIR'] = ext_files_dir
    if files_dir:
        os.environ['IPTV_INTERNAL_DIR'] = files_dir

    # 1. 共享存储根目录（写入探针验证真实可写性，不只看权限声明）
    candidates = []
    if public_root:
        candidates.append(public_root)
    if private_root:
        candidates.append(private_root)
    if ext_files_dir:
        candidates.append(os.path.join(ext_files_dir, APP_NAME))
    if files_dir:
        candidates.append(os.path.join(files_dir, APP_NAME))

    for candidate in candidates:
        try:
            # 必须先用写探针确认真正可写，再建子目录：
            # 权限未授予时 makedirs 会失败但不抛到调用方，只看返回值会误判
            if not is_writable_dir(candidate):
                _log(f'_setup_android_paths: data root not writable ({candidate})', 'W')
                continue
            ensure_android_layout(candidate)
            target_dir = candidate
            _log(f'_setup_android_paths: using data root {target_dir}')
            break
        except Exception as e:
            _log(f'_setup_android_paths: data root failed ({candidate}): {e}', 'W')

    # 最终兜底：home 目录
    if not target_dir:
        try:
            candidate = os.path.join(os.path.expanduser('~'), APP_NAME)
            ensure_android_layout(candidate)
            target_dir = candidate
            _log(f'_setup_android_paths: using home dir {target_dir}', 'W')
        except Exception as e:
            _log(f'_setup_android_paths: home dir failed: {e}', 'E')

    if target_dir:
        os.environ['IPTV_DATA_DIR'] = target_dir

    # 保存 native 库目录路径（供 mpv_common 加载 libmpv.so 使用）
    if native_lib_dir:
        os.environ['IPTV_NATIVE_LIB_DIR'] = native_lib_dir
        _log(f'_setup_android_paths: native_lib_dir={native_lib_dir}')
    else:
        # 尝试通过 jnius 获取
        try:
            from jnius import autoclass  # type: ignore
            Python = autoclass('com.chaquo.python.Python')
            app = Python.getPlatform().getApplication()
            app_info = app.getApplicationInfo()
            native_lib_dir = str(app_info.nativeLibraryDir)
            os.environ['IPTV_NATIVE_LIB_DIR'] = native_lib_dir
            _log(f'_setup_android_paths: native_lib_dir (jnius)={native_lib_dir}')
        except Exception as e:
            _log(f'_setup_android_paths: native_lib_dir not available ({e})')

    # 迁移旧数据（旧共享目录 /sdcard/ISEP、私有 ISEP / ISEPP / IPTV_Scanner_Editor_Pro
    # → 新根目录下按用途分类的 config / logs / cache / data）
    if target_dir:
        try:
            from utils.app_paths import migrate_android_layout
            migrate_android_layout(target_dir, private_root)
        except Exception as e:
            _log(f'_setup_android_paths: migrate layout failed: {e}', 'W')
# 日志等级映射：字符串 → logging 常量
_LOG_LEVEL_MAP = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warn': logging.WARNING,
    'warning': logging.WARNING,
    'error': logging.ERROR,
}

# 当前 Python 日志等级（初始默认 INFO，由 Kotlin 端通过 set_log_level 更新）
_current_log_level = logging.INFO


def _get_log_file_path():
    """获取 app.log 文件路径（统一走目录解析，Android 为 <root>/logs/app.log）"""
    try:
        from utils.app_paths import get_log_dir
        return os.path.join(get_log_dir(), 'app.log')
    except Exception as e:
        _log(f'_get_log_file_path failed: {e}', 'W')
        return os.path.join(os.path.expanduser('~'), 'GuangYu', 'logs', 'app.log')


def _add_file_handler(root_logger):
    """为 root logger 添加 RotatingFileHandler，写入 app.log 文件。

    与 PC 端 core/log_manager.py 保持一致：
    - 每次启动清除旧日志（非追加模式）
    - maxBytes=5MB, backupCount=0
    - 格式: '2026-07-09 01:52:43 - server.context - WARNING - 消息内容'
    """
    try:
        from logging.handlers import RotatingFileHandler

        log_path = _get_log_file_path()
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 每次启动时清除旧日志文件（与 PC 端 LogManager 一致）
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception as e:
                _log(f'remove old log file failed: {e}', 'D')

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=0,
            encoding='utf-8',
            mode='w',
        )
        file_handler.setLevel(_current_log_level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        file_handler.setFormatter(formatter)

        # 避免重复添加
        if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
            root_logger.addHandler(file_handler)

        _log(f'File logging to {log_path} (level={logging.getLevelName(_current_log_level)})')
    except Exception as e:
        _log(f'File logging setup failed: {e}', 'W')


def _setup_android_logging():
    """设置 Android 日志：logcat + app.log 文件双通道输出

    1. logcat：优先用 AndroidLog (jnius)，失败则用 print() fallback
    2. app.log：RotatingFileHandler 写入 ISEP 目录，与 PC 端格式一致
    """
    # --- logcat handler ---
    try:
        from jnius import autoclass  # type: ignore
        AndroidLog = autoclass('android.util.Log')

        class AndroidLogHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                level = record.levelno
                tag = record.name[:23]
                if level >= logging.ERROR:
                    AndroidLog.e(tag, msg)
                elif level >= logging.WARNING:
                    AndroidLog.w(tag, msg)
                elif level >= logging.INFO:
                    AndroidLog.i(tag, msg)
                elif level >= logging.DEBUG:
                    AndroidLog.d(tag, msg)
                else:
                    AndroidLog.v(tag, msg)
        root = logging.getLogger()
        if not any(isinstance(h, AndroidLogHandler) for h in root.handlers):
            root.addHandler(AndroidLogHandler())
        _log('Android logging via jnius OK')
    except Exception as e:
        _log(f'jnius logging unavailable, using print fallback: {e}', 'W')

        # Fallback: 用 print() 输出日志（Chaquopy 会重定向到 logcat 的 python 标签）
        class PrintLogHandler(logging.Handler):
            def emit(self, record):
                msg = self.format(record)
                level = record.levelname[0]
                print(f'[{level}] {record.name}: {msg}', flush=True)
        root = logging.getLogger()
        if not any(isinstance(h, PrintLogHandler) for h in root.handlers):
            root.addHandler(PrintLogHandler())
        _log('Android logging via print fallback OK')

    # --- file handler (app.log) ---
    # 注意：不在此处创建 RotatingFileHandler！
    # LogManager（core/log_manager.py）在 server.context 导入时会创建自己的
    # RotatingFileHandler 写入同一个 app.log 文件。如果此处也创建一个，
    # LogManager 初始化时会删除 app.log 再重新创建，导致此处的 handler
    # 指向已删除的文件，所有通过 root logger 的日志（如 server.context）全部丢失。
    # 正确做法：在 init_context() 中 server.context 导入后，将 LogManager 的
    # file handler 添加到 root logger，使所有 logger 共享同一个 handler。
    root = logging.getLogger()
    root.setLevel(_current_log_level)


def set_log_level(level_str='info'):
    """运行时切换 Python 日志等级（由 Kotlin 端通过 Chaquopy callAttr 调用）。

    同时影响 logcat 输出和 app.log 文件输出。
    与 PC 端 core/log_manager.py 的 LogManager.set_level() 对齐。

    参数：
        level_str: 'debug' / 'info' / 'warn' / 'error'
    返回 'OK' 表示成功。
    """
    global _current_log_level
    level = _LOG_LEVEL_MAP.get(level_str.lower(), logging.INFO)
    _current_log_level = level

    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)

    _log(f'Python log level set to {level_str} ({logging.getLevelName(level)})')
    return 'OK'


def _find_admin_dir():
    try:
        import server
        server_dir = os.path.dirname(os.path.abspath(server.__file__))
        admin_dir = os.path.join(server_dir, 'admin')
        if os.path.isdir(admin_dir):
            return admin_dir
    except Exception as e:
        _log(f'_find_admin_dir: import server module failed: {e}', 'W')
    this_dir = os.path.dirname(os.path.abspath(__file__))
    for candidate in [
        os.path.join(this_dir, 'server', 'admin'),
        os.path.join(this_dir, 'admin'),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return None

_MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.webmanifest': 'application/manifest+json',
}


def _register_admin_routes_fallback(app, admin_dir):
    # 注册管理后台路由（局域网 Web 管理页面）
    # 注意：routes.py 中的 _register_admin_routes 在 Android 上可能找不到目录
    # 因为 Chaquopy 打包后 server.__file__ 可能指向非标准路径
    # 这里通过 _find_admin_dir 找到的 admin_dir 来注册路由
    if os.path.isdir(admin_dir):
        async def _handle_admin(request):
            from aiohttp import web
            rel_path = request.match_info.get('path', 'index.html')
            if not rel_path or rel_path.endswith('/'):
                rel_path += 'index.html'
            # 安全：防止路径穿越
            file_path = os.path.realpath(os.path.join(admin_dir, rel_path))
            admin_real = os.path.realpath(admin_dir)
            if not file_path.startswith(admin_real + os.sep):
                return web.Response(text='403: Forbidden', status=403)
            if not os.path.isfile(file_path):
                return web.Response(text='404: Not Found', status=404)
            ext = os.path.splitext(rel_path)[1].lower()
            content_type = _MIME_TYPES.get(ext, 'application/octet-stream')
            with open(file_path, 'rb') as f:
                content = f.read()
            return web.Response(
                body=content, content_type=content_type,
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0',
                })

        # create_app() 内部已调用 _register_admin_routes 注册了 /admin/ 路由
        # 这里重复注册会抛 ValueError，用 try/except 忽略
        try:
            app.router.add_get('/admin/', _handle_admin)
            app.router.add_get('/admin/{path:.*}', _handle_admin)
            _log(f'admin UI registered from: {admin_dir}')
        except ValueError:
            _log('admin routes already registered by create_app(), skipping')


# ===================================================================
# 阶段 1：Chaquopy 直调入口（替代 HTTP endpoint）
# 设计原则：
#  - 与现有 start_server 并存，不破坏 WebView 流程
#  - Compose 端通过 Python.getInstance().getModule("android_bridge")
#       .callAttr("method_name", *args).toString() 调用
#  - 返回值统一为 JSON 字符串（Chaquopy 不能直接传 dict/list）
#  - 耗时操作（reload_sources / start_scan / reload_epg / refresh_mappings /
#    search_subtitles / download_subtitle）立即返回，内部启动 daemon 线程
#  - 调用者应在 Kotlin Dispatchers.IO 中调用，避免阻塞 UI 线程
# ===================================================================

import json as _json  # noqa: E402
import threading as _threading  # noqa: E402

_ctx_lock = _threading.Lock()
_inited = False


def _ok(data):
    """序列化成功响应。data 可以是 dict/list/str/int/bool/None"""
    return _json.dumps(data, ensure_ascii=False, default=str)


def _err(message, **extra):
    """序列化错误响应。message 是错误描述，extra 附加字段"""
    payload = {'error': str(message)}
    payload.update(extra)
    return _json.dumps(payload, ensure_ascii=False)


def set_app_info(version='', build_date=''):
    """设置应用版本信息（由 Kotlin 端通过 Chaquopy callAttr 调用）。

    版本信息存储在全局变量中，供 API 端点和管理界面使用。

    参数：
        version: 应用版本号（如 '48.2.0.2'），来自 PackageManager.versionName
        build_date: 编译日期（如 '2026-07-07'），来自 BuildConfig
    """
    global _app_version, _app_build_date
    if version:
        _app_version = version
    if build_date:
        _app_build_date = build_date
    _log(f'set_app_info: version={_app_version}, build_date={_app_build_date}')
    return 'OK'


def get_storage_info():
    """返回当前实际使用的存储路径（供设置/关于页展示）。

    包含根目录与 config/logs/cache/data/exports 子目录、是否共享存储、
    以及降级原因，Kotlin 端据此显示真实路径而不是猜测。
    """
    try:
        from utils.app_paths import get_storage_info as _info
        return _ok(_info())
    except Exception as e:
        _ab_logger.exception('get_storage_info failed')
        return _err(f'get_storage_info failed: {e}')


def init_context(ext_files_dir='', files_dir='', log_level='info', native_lib_dir='',
                 public_root='', private_root=''):
    """初始化 Python 环境 + ServerContext 单例，立即返回（不阻塞）。

    参数 ext_files_dir / files_dir 由 Kotlin 端通过 Chaquopy callAttr 传入，
    用于在 jnius 不可用时定位 Android 数据目录。
    public_root / private_root 分别是共享目录（/sdcard/GuangYu）与应用私有目录
    （getExternalFilesDir()/GuangYu），由 Kotlin 端按权限状态传入。
    参数 log_level 由 Kotlin 端传入，设置 Python 日志等级（debug/info/warn/error）。

    返回 'OK' 表示成功，'FAILED: ...' 表示错误。
    Compose 端应在 Dispatchers.IO 调用，调用后用 get_status_json() 轮询加载进度。
    """
    global _inited
    with _ctx_lock:
        if _inited:
            return 'OK'
        try:
            _setup_android_paths(ext_files_dir, files_dir, native_lib_dir,
                                 public_root, private_root)
            # 在设置日志前先应用 Kotlin 端传入的日志等级
            if log_level:
                set_log_level(log_level)
            _setup_android_logging()
            _log(f'init_context: paths and logging setup done (log_level={log_level})')

            # 设置配置目录（与 start_server() 保持一致）
            # 不使用 os.chdir（全局状态，多线程不安全）
            from utils.app_paths import get_config_dir
            config_dir = get_config_dir()
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
                os.environ['IPTV_CONFIG_DIR'] = config_dir
                _log(f'init_context: config_dir={config_dir}')

            from server.context import ServerContext

            # 在 ServerContext.get_instance() 之前，先将 LogManager 的 file handler
            # 添加到 root logger，使 get_instance() 内部的日志（如"从缓存加载了 N 个频道"）
            # 也能写入 app.log。LogManager 在 server.context 导入时已初始化，此时
            # handler 已挂在 'IPTVScanner' logger 上，共享到 root logger 后所有子 logger
            # 的日志通过传播机制都能写入 app.log。
            try:
                from core.log_manager import global_logger as _glm
                _glm_logger = _glm.get_logger()
                if _glm_logger.handlers:
                    _glm_handler = _glm_logger.handlers[0]
                    # 将 handler 从 IPTVScanner logger 移到 root logger，
                    # 使所有 logger（IPTVScanner, server.context 等）的消息
                    # 通过传播到 root 统一写入 app.log + logcat，且不重复。
                    _glm_logger.removeHandler(_glm_handler)
                    root = logging.getLogger()
                    if not any(h is _glm_handler for h in root.handlers):
                        root.addHandler(_glm_handler)
                    # 同步 file handler 的日志级别（LogManager 创建时可能用了不同级别）
                    _glm_handler.setLevel(_current_log_level)
                    _log('Moved LogManager file handler to root logger (app.log)')
                else:
                    _log('LogManager has no file handler, skipping move', 'W')
            except Exception as _e:
                _log(f'Failed to move LogManager handler: {_e}', 'W')

            ServerContext.get_instance(main_window=None)

            try:
                _ctx = ServerContext.get_instance(main_window=None)
                _sm = _ctx.get_epg_parser()
                # EPG 缓存的「探测 + 加载 + 是否需要下载」统一由
                # ServerContext._init_epg_parser 在后台线程完成（同一路径、同一判定）。
                # 这里只读取它的结果，不要再做一次独立的 exists 探测：否则会出现
                # 「探测说没缓存、紧接着又从同一文件加载 81MB」的矛盾日志，
                # 并让每次冷启动都被误判为需要重下 EPG。
                if _sm is None:
                    _log('init_context: EPG parser init in progress (background)')
                elif getattr(_sm, '_epg_data', None):
                    _log(f'init_context: EPG cache ready ({len(_sm._epg_data)} channels)')
                else:
                    _log('init_context: EPG cache not loaded yet (background init pending)')
            except Exception as _e:
                _log(f'init_context: load EPG cache failed: {_e}', 'W')

            _log('init_context: ServerContext initialized (standalone mode)')
            _inited = True
            return 'OK'
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log(f'init_context failed: {e}', 'E')
            _ab_logger.exception('init_context failed')
            # 错误信息带回 Kotlin 端 logcat（'操作失败' 无法定位根因）
            return _err(f'init_context failed: {e}')


def _get_ctx():
    """获取已初始化的 ServerContext 实例。未初始化时返回 None。"""
    if not _inited:
        return None
    try:
        from server.context import ServerContext
        return ServerContext.get_instance(main_window=None)
    except Exception as e:
        _log(f'_get_ctx failed: {e}', 'W')
        return None


# -------------------------------------------------------------------
# 状态与频道查询
# -------------------------------------------------------------------

def get_status_json():
    """返回 standalone 状态 JSON：channels_total / source_loading / source_message / source_warning"""
    if not _inited:
        return _ok({'inited': False, 'channels_total': 0,
                    'source_loading': False, 'source_message': 'not inited',
                    'source_warning': ''})
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('no context')
        status = ctx.get_source_load_status() or {}
        channels = ctx.get_all_channels() or []
        return _ok({
            'inited': True,
            'channels_total': len(channels),
            'source_loading': bool(status.get('loading', False)),
            'source_message': str(status.get('message', '')),
            'source_warning': str(status.get('warning', '')),
        })
    except Exception as e:
        _ab_logger.exception('get_status_json failed')
        return _err(str(e))


def get_channels_json(page=1, size=100, group='', search='', valid_filter='', source_filter=''):
    """频道分页列表。返回 {total, page, page_size, channels, groups}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        all_channels = ctx.get_all_channels() or []
        # 过滤
        filtered = all_channels
        if group:
            filtered = [c for c in filtered if c.get('group', '') == group]
        if search:
            s = search.lower()
            filtered = [c for c in filtered if s in c.get('name', '').lower() or s in c.get('group', '').lower()]
        if valid_filter in ('valid', 'suspected', 'invalid'):
            from services.validity_tiers import channel_tier
            filtered = [c for c in filtered if channel_tier(c) == valid_filter]
        if source_filter == 'local':
            filtered = [c for c in filtered if not c.get('source', '')]
        elif source_filter == 'sub':
            filtered = [c for c in filtered if c.get('source', '')]
        total = len(filtered)
        # 分页（单页上限放宽：Kotlin 端 loadChannels 依赖大页一次性拉取做本地过滤）
        page = max(1, int(page))
        size = max(1, min(int(size), 10_000))
        start = (page - 1) * size
        end = start + size
        page_channels = filtered[start:end]
        # 保留 _index 字段（server 端包含），去掉其他内部下划线字段
        clean = []
        for i, c in enumerate(page_channels):
            item = {k: v for k, v in c.items() if not k.startswith('_')}
            item['_index'] = all_channels.index(c) if c in all_channels else start + i
            clean.append(item)
        # 分组列表（按首次出现顺序去重，与 server 端一致）
        groups = list(dict.fromkeys(c.get('group', '') for c in all_channels if c.get('group')))
        return _ok({
            'total': total,
            'page': page,
            'page_size': size,
            'channels': clean,
            'groups': groups,
        })
    except Exception as e:
        _ab_logger.exception('get_channels_json failed')
        return _err(str(e))


def get_channel_json(idx):
    """返回单个频道 JSON。idx 是频道索引（基于 get_all_channels 全量列表）"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        channels = ctx.get_all_channels() or []
        idx = int(idx)
        if idx < 0 or idx >= len(channels):
            return _err('idx out of range')
        c = channels[idx]
        return _ok({k: v for k, v in c.items() if not k.startswith('_')})
    except Exception as e:
        _ab_logger.exception('get_channel_json failed')
        return _err(str(e))


def get_groups_json():
    """返回所有频道分组列表（按 M3U 顺序去重）。[{name, count}]"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        channels = ctx.get_all_channels() or []
        from collections import OrderedDict
        groups = OrderedDict()
        for c in channels:
            g = c.get('group', '未分类') or '未分类'
            groups[g] = groups.get(g, 0) + 1
        return _ok([{'name': k, 'count': v} for k, v in groups.items()])
    except Exception as e:
        _ab_logger.exception('get_groups_json failed')
        return _err(str(e))


# -------------------------------------------------------------------
# 频道 CRUD（standalone 模式直接操作 _channels）
# -------------------------------------------------------------------

def add_channel(url, name, group=''):
    """添加频道到列表末尾。返回 {idx} 或 {error}"""
    try:
        _log(f'add_channel: name={name}, url={url}, group={group}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        new_ch = {
            'name': str(name), 'url': str(url), 'group': str(group or '未分类'),
            'logo': '', 'tvg_id': '', 'tvg_name': '', 'tvg_chno': '',
            'tvg_shift': '', 'catchup': '', 'catchup_days': '',
            'catchup_source': '', 'catchup_correction': '', 'fcc': '',
            'resolution': '', 'valid': None, 'validity': None, 'status': '待检测',
            'id': len(ctx._channels) + 1,
            'source': '',  # 空源 = 手动添加/本地频道
        }
        ctx._channels.append(new_ch)
        # 持久化：进程重启后添加的频道不丢失
        ctx._save_channels_to_cache()
        return _ok({'idx': len(ctx._channels) - 1})
    except Exception as e:
        _ab_logger.exception('add_channel failed')
        return _err(str(e))


def update_channel(idx, json_data):
    """更新频道字段。json_data 是 JSON 字符串，键为字段名。返回 {ok} 或 {error}"""
    try:
        _log(f'update_channel: idx={idx}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        idx = int(idx)
        if idx < 0 or idx >= len(ctx._channels):
            return _err('idx out of range')
        data = _json.loads(json_data) if isinstance(json_data, str) else json_data
        ctx._channels[idx].update(data)
        # 持久化：更新频道信息后立即保存
        ctx._save_channels_to_cache()
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('update_channel failed')
        return _err(str(e))


def delete_channel(idx):
    """删除指定索引的频道。返回 {ok} 或 {error}"""
    try:
        _log(f'delete_channel: idx={idx}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        idx = int(idx)
        if idx < 0 or idx >= len(ctx._channels):
            return _err('idx out of range')
        ctx._channels.pop(idx)
        # 持久化：删除后立即保存，防止已删除频道在重启后复活
        ctx._save_channels_to_cache()
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('delete_channel failed')
        return _err(str(e))


def clear_local_channels():
    """清空所有本地频道（source 为空的频道）。返回 {cleared} 或 {error}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        before = len(ctx._channels)
        ctx._channels = [c for c in ctx._channels if c.get('source', '')]
        cleared = before - len(ctx._channels)
        ctx._save_channels_to_cache()
        return _ok({'cleared': cleared})
    except Exception as e:
        _ab_logger.exception('clear_local_channels failed')
        return _err(str(e))


def import_channels(content, name=''):
    """解析 M3U 内容并追加到频道列表。返回 {imported, epg_url} 或 {error}

    如果 M3U 头部包含 x-tvg-url 属性，会提取 EPG URL 并返回，
    调用方可据此自动添加 EPG 订阅源。
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from services.m3u_parser import parse_m3u_content, extract_tvg_url_from_header
        channels, header_attrs = parse_m3u_content(content)
        # 提取 M3U 头部的 x-tvg-url EPG 地址
        epg_url = ''
        if header_attrs and header_attrs.get('epg_url'):
            epg_url = header_attrs['epg_url']
        else:
            # fallback: 直接从第一行提取
            for line in content.splitlines()[:5]:
                if line.startswith('#EXTM3U'):
                    epg_url = extract_tvg_url_from_header(line) or ''
                    break
        if channels:
            # 给新频道 id 和 source 标记
            # source='' 表示手动导入的频道（非订阅源），在 Android 端 LOCAL tab 显示
            base_id = len(ctx._channels)
            for i, c in enumerate(channels):
                c['id'] = base_id + i + 1
                c['source'] = ''  # 手动导入 = 本地频道
            ctx._channels.extend(channels)
            # 持久化：导入的频道重启后不丢失
            ctx._save_channels_to_cache()
            result = {'imported': len(channels)}
            if epg_url:
                result['epg_url'] = epg_url
            return _ok(result)
        return _ok({'imported': 0})
    except Exception as e:
        _ab_logger.exception('import_channels failed')
        return _err(str(e))
# -------------------------------------------------------------------
# 订阅源管理
# -------------------------------------------------------------------

def get_sources_json():
    """返回订阅源列表 JSON"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_playlist_sources() or []
        return _ok(sources)
    except Exception as e:
        _ab_logger.exception('get_sources_json failed')
        return _err(str(e))


def export_config():
    """导出所有可备份的配置为 JSON 字符串。

    包含：playlist_sources + epg_sources。
    用于备份/恢复功能：导出后写入外部存储，卸载重装后可恢复。

    返回 {config: {version, playlist_sources, epg_sources}}
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        playlist_sources = config.load_playlist_sources() or []
        epg_sources = config.load_epg_sources() or []
        data = {
            'version': 1,
            'playlist_sources': playlist_sources,
            'epg_sources': epg_sources,
        }
        return _ok(data)
    except Exception as e:
        _ab_logger.exception('export_config failed')
        return _err(str(e))


def import_config(json_data):
    """从 JSON 恢复配置。

    恢复：playlist_sources + epg_sources，并触发 reload。
    用于备份/恢复功能：从外部存储读取 JSON 后恢复配置。

    Args:
        json_data: JSON 字符串或 dict，包含 playlist_sources 和/或 epg_sources
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        data = _json.loads(json_data) if isinstance(json_data, str) else json_data

        # 恢复 playlist_sources
        if 'playlist_sources' in data and isinstance(data['playlist_sources'], list):
            config.save_playlist_sources(data['playlist_sources'])

        # 恢复 epg_sources
        if 'epg_sources' in data and isinstance(data['epg_sources'], list):
            config.save_epg_sources(data['epg_sources'])

        # 触发 reload 以加载频道和 EPG
        try:
            ctx.reload_sources()
            _log('import_config: reload_sources triggered')
        except Exception as e:
            _log(f'import_config: reload_sources failed: {e}', 'W')
        try:
            ctx.reload_epg()
            _log('import_config: reload_epg triggered')
        except Exception as e:
            _log(f'import_config: reload_epg failed: {e}', 'W')

        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('import_config failed')
        return _err(str(e))


def add_source(url, name=''):
    """添加订阅源。返回 {ok}"""
    try:
        _log(f'add_source: url={url}, name={name}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_playlist_sources() or []
        sources.append({
            'url': str(url),
            'name': str(name or f'Source {len(sources) + 1}'),
            'enabled': True,
            'last_update': None,
        })
        config.save_playlist_sources(sources)
        _log(f'add_source: done, total sources={len(sources)}')
        return _ok({'ok': True, 'count': len(sources)})
    except Exception as e:
        _ab_logger.exception('add_source failed')
        return _err(str(e))


def delete_source(idx):
    """删除订阅源。返回 {ok}"""
    try:
        _log(f'delete_source: idx={idx}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_playlist_sources() or []
        idx = int(idx)
        if idx < 0 or idx >= len(sources):
            return _err('idx out of range')
        sources.pop(idx)
        config.save_playlist_sources(sources)
        return _ok({'ok': True, 'count': len(sources)})
    except Exception as e:
        _ab_logger.exception('delete_source failed')
        return _err(str(e))


def update_source(idx, json_data):
    """更新订阅源字段（如 enabled / name / url）。"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_playlist_sources() or []
        idx = int(idx)
        if idx < 0 or idx >= len(sources):
            return _err('idx out of range')
        data = _json.loads(json_data) if isinstance(json_data, str) else json_data
        sources[idx].update(data)
        config.save_playlist_sources(sources)
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('update_source failed')
        return _err(str(e))


def reload_sources(url=''):
    """触发订阅源重载（异步，立即返回 True/False）。url 空则加载所有已配置源。"""
    try:
        _log(f'reload_sources: url={url or "(all)"}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        result = ctx.reload_sources(url)
        _log(f'reload_sources: started={result}')
        return _ok({'started': bool(result)})
    except Exception as e:
        _ab_logger.exception('reload_sources failed')
        return _err(str(e))


def get_source_status_json():
    """返回订阅源加载状态 JSON"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        status = ctx.get_source_load_status() or {}
        return _ok(status)
    except Exception as e:
        _ab_logger.exception('get_source_status_json failed')
        return _err(str(e))


# -------------------------------------------------------------------
# EPG 订阅源管理
# -------------------------------------------------------------------

def get_epg_sources_json():
    """返回 EPG 订阅源列表 JSON"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_epg_sources() or []
        return _ok(sources)
    except Exception as e:
        _ab_logger.exception('get_epg_sources_json failed')
        return _err(str(e))


def add_epg_source(url, name=''):
    """添加 EPG 订阅源并触发重载。返回 {ok}"""
    try:
        _log(f'add_epg_source: url={url}, name={name}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_epg_sources() or []
        sources.append({
            'url': str(url),
            'name': str(name or f'EPG Source {len(sources) + 1}'),
            'last_update': None,
        })
        config.save_epg_sources(sources)
        # 异步重载 EPG（不阻塞）
        try:
            ctx.reload_epg()
        except Exception as e:
            _log(f'add_epg_source: reload_epg failed: {e}', 'W')
        return _ok({'ok': True, 'count': len(sources)})
    except Exception as e:
        _ab_logger.exception('add_epg_source failed')
        return _err(str(e))


def delete_epg_source(idx):
    """删除 EPG 订阅源。返回 {ok}"""
    try:
        _log(f'delete_epg_source: idx={idx}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        config = ctx.get_config()
        if config is None:
            return _err('no config')
        sources = config.load_epg_sources() or []
        idx = int(idx)
        if idx < 0 or idx >= len(sources):
            return _err('idx out of range')
        sources.pop(idx)
        config.save_epg_sources(sources)
        return _ok({'ok': True, 'count': len(sources)})
    except Exception as e:
        _ab_logger.exception('delete_epg_source failed')
        return _err(str(e))


def reload_epg():
    """异步重新加载 EPG 数据。返回 {started}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        result = ctx.reload_epg()
        return _ok({'started': bool(result)})
    except Exception as e:
        _ab_logger.exception('reload_epg failed')
        return _err(str(e))


def get_epg_status_json():
    """返回 EPG 加载状态 JSON（has_epg_data / channel_count / program_count）"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        sm = ctx.get_epg_parser()
        if sm is None:
            return _ok({'has_epg_data': False, 'channel_count': 0, 'program_count': 0})
        return _ok({
            'has_epg_data': bool(sm.has_epg_data()),
            'channel_count': int(sm.get_epg_channel_count()),
            'program_count': int(sm.get_epg_program_count()),
        })
    except Exception as e:
        _ab_logger.exception('get_epg_status_json failed')
        return _err(str(e))


# -------------------------------------------------------------------
# EPG 节目单
# -------------------------------------------------------------------

def get_epg_json(channel_name='', tvg_id='', tvg_name='', comma_name=''):
    """获取指定频道的节目单 JSON。

    匹配优先级：tvg_id > tvg_name > comma_name > channel_name > EpgMatcher 分级匹配。
    除节目列表外还返回匹配元数据（EPG 源、epg 频道 id/display-name、命中层级），
    供播放页信息弹窗显示"这个频道匹配到了哪个 EPG 源的哪个频道"。
    返回 {programmes: [...], matched, epg_matched, epg_id, epg_name, match_tier,
          epg_source_name, epg_source_url} 或 {error}
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        sm = ctx.get_epg_parser()
        if sm is None:
            return _ok({'programmes': [], 'matched': False, 'epg_matched': False,
                        'epg_id': '', 'epg_name': '', 'match_tier': '未匹配',
                        'epg_source_name': '', 'epg_source_url': ''})
        meta = {}
        if hasattr(sm, 'get_channel_epg_detail'):
            programmes, meta = sm.get_channel_epg_detail(
                channel_name=channel_name,
                tvg_id=tvg_id or None,
                tvg_name=tvg_name or None,
                comma_name=comma_name or None,
            )
        else:
            programmes = sm.get_channel_epg(
                channel_name=channel_name,
                tvg_id=tvg_id or None,
                tvg_name=tvg_name or None,
                comma_name=comma_name or None,
            )
        # 填充 Unix 时间戳字段（Kotlin 端用此判断当前节目，与 server/routes.py handle_epg 逻辑一致）
        for p in (programmes or []):
            if 'start_ts' not in p:
                try:
                    from datetime import datetime, timezone, timedelta
                    import re as _re
                    start_str = p.get('start', '')
                    stop_str = p.get('stop', p.get('end', ''))
                    def _parse_xmltv_time(s):
                        if not s:
                            return None
                        s = s.strip()
                        try:
                            return datetime.fromisoformat(s)
                        except (ValueError, TypeError):
                            pass
                        m = _re.match(r'^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\s*([+-]\d{4})?$', s)
                        if m:
                            y, mo, d, h, mi, se = (int(m.group(i)) for i in range(1, 7))
                            tz_s = m.group(7)
                            if tz_s:
                                sign = 1 if tz_s[0] == '+' else -1
                                tz = timezone(sign * timedelta(hours=int(tz_s[1:3]), minutes=int(tz_s[3:5])))
                            else:
                                tz = None
                            try:
                                return datetime(y, mo, d, h, mi, se, tzinfo=tz)
                            except ValueError:
                                return None
                        return None
                    if start_str:
                        dt = _parse_xmltv_time(start_str)
                        if dt:
                            p['start_ts'] = int(dt.timestamp())
                    if stop_str:
                        dt = _parse_xmltv_time(stop_str)
                        if dt:
                            p['stop_ts'] = int(dt.timestamp())
                except Exception as e:
                    _log(f'get_epg_json: parse stop_ts failed: {e}', 'D')
        return _ok({
            'programmes': programmes or [],
            'matched': bool(programmes),
            'epg_matched': bool(meta.get('matched')),
            'epg_id': meta.get('epg_id', '') or '',
            'epg_name': meta.get('epg_name', '') or '',
            'match_tier': meta.get('tier', '未匹配') or '未匹配',
            'epg_source_name': meta.get('source_name', '') or '',
            'epg_source_url': meta.get('source_url', '') or '',
        })
    except Exception as e:
        _ab_logger.exception('get_epg_json failed')
        return _err(str(e))


def get_epg_channels_json():
    """返回所有有 EPG 数据的频道 ID 列表（用于搜索界面）。"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        sm = ctx.get_epg_parser()
        if sm is None:
            return _ok({'channels': []})
        data = sm.get_epg_data_copy() or {}
        return _ok({'channels': list(data.keys())})
    except Exception as e:
        _ab_logger.exception('get_epg_channels_json failed')
        return _err(str(e))


# -------------------------------------------------------------------
# 扫描（URL 范围扫描）
# -------------------------------------------------------------------

def start_scan(base_url, timeout=10, threads=4, engine='requests', retry=False, append=False):
    """启动 URL 范围扫描（异步）。base_url 支持 [1-255] 范围表达式。
    命名变量同步：[1-255:n] 定义变量 n，{n} 引用（两处 n 同步变化）。

    Args:
        engine: 扫描引擎 ('requests' / 'ffprobe' / 'mpv')。
        standalone 模式下始终使用 requests（ffprobe/mpv 不可用）。
        retry: 是否启用智能重试（失败 URL 用 2x 超时重试）
        append: 是否追加模式（不清空已有扫描结果，不覆盖已有频道）
    返回 {started} 或 {error}
    """
    try:
        _log(f'start_scan: base_url={base_url}, timeout={timeout}, '
             f'threads={threads}, engine={engine}, retry={retry}, append={append}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        scanner = ctx.get_standalone_scanner()
        if scanner is None:
            return _err('no scanner')
        result = scanner.start_range_scan(
            base_url=str(base_url),
            timeout=int(timeout),
            threads=int(threads),
            engine=str(engine) if engine else 'requests',
            retry=bool(retry),
            append=bool(append),
        )
        _log(f'start_scan: started={result}')
        return _ok({'started': bool(result)})
    except Exception as e:
        _ab_logger.exception('start_scan failed')
        return _err(str(e))


def stop_scan():
    """请求停止扫描（异步）。返回 {ok}"""
    try:
        _log('stop_scan requested')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        scanner = ctx.get_standalone_scanner()
        if scanner is None:
            return _err('no scanner')
        scanner.stop_scan()
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('stop_scan failed')
        return _err(str(e))


def get_scan_status_json():
    """返回扫描状态 JSON：running / total / valid / invalid / scanned / message / mode"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        scanner = ctx.get_standalone_scanner()
        if scanner is None:
            return _err('no scanner')
        status = scanner.get_status() or {}
        return _ok(status)
    except Exception as e:
        _ab_logger.exception('get_scan_status_json failed')
        return _err(str(e))


def get_scan_results_json():
    """返回 URL 范围扫描结果列表 JSON。"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        scanner = ctx.get_standalone_scanner()
        if scanner is None:
            return _err('no scanner')
        results = scanner.get_results() or []
        return _ok(results)
    except Exception as e:
        _ab_logger.exception('get_scan_results_json failed')
        return _err(str(e))


def get_dv_profile(url):
    """返回扫描阶段为该地址登记的杜比视界 profile；没有登记返回 0。

    Android 的播放器是 Kotlin 侧的 libmpv，读不到杜比 profile，也没有 ffprobe；
    扫描阶段若由 Python 验证器读出 profile 会登记在 utils.hdr_detect 里，
    这里给 Kotlin 一个稳定入口，拿不到时返回 0 由播放侧按未知处理。
    """
    try:
        if not url:
            return 0
        from utils.hdr_detect import get_dv_profile as _get_profile
        profile = _get_profile(url)
        return int(profile) if profile is not None else 0
    except Exception as e:
        _ab_logger.debug(f'get_dv_profile failed: {e}')
        return 0


def start_validate(timeout=10, threads=4, engine='auto'):
    """开始验证所有频道的 URL 可达性（异步）。

    与 PC 端 scanner_service.validate_channels 和
    routes.handle_scan_validate 对齐。
    engine: 'auto'（默认，libmpv 可用时真实拉流）/ 'mpv' / 'fast'
    更新频道的 valid/validity/status 字段并持久化。
    """
    try:
        _log(f'start_validate: timeout={timeout}, threads={threads}, engine={engine}')
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        scanner = ctx.get_standalone_scanner()
        if scanner is None:
            return _err('no scanner')
        result = scanner.start_validate(
            timeout=int(timeout),
            threads=int(threads),
            engine=str(engine or 'auto'),
        )
        _log(f'start_validate: started={result}')
        return _ok({'started': bool(result)})
    except Exception as e:
        _ab_logger.exception('start_validate failed')
        return _err(str(e))


# -------------------------------------------------------------------
# 频道映射
# -------------------------------------------------------------------

def get_mappings_json():
    """返回所有频道映射条目 JSON。"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from models.channel_mappings import mapping_manager
        entries = mapping_manager.get_mapping_entries() or []
        return _ok(entries)
    except Exception as e:
        _ab_logger.exception('get_mappings_json failed')
        return _err(str(e))


def add_mapping(raw_name, standard_name, logo_url='', group_name=''):
    """添加用户映射。返回 {ok}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from models.channel_mappings import mapping_manager
        mapping_manager.add_user_mapping(
            raw_name=str(raw_name),
            standard_name=str(standard_name),
            logo_url=str(logo_url) or None,
            group_name=str(group_name) or None,
        )
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('add_mapping failed')
        return _err(str(e))


def delete_mapping(standard_name, raw_name=''):
    """删除映射。
    - 只传 standard_name：删除该 standard_name 下所有 raw_name
    - 同时传 standard_name 和 raw_name：删除单条
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from models.channel_mappings import mapping_manager
        if raw_name:
            mapping_manager.remove_user_mapping_entry(
                standard_name=str(standard_name),
                raw_name=str(raw_name),
            )
        else:
            mapping_manager.remove_user_mapping(standard_name=str(standard_name))
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('delete_mapping failed')
        return _err(str(e))


def refresh_mappings():
    """刷新远程映射缓存（同步阻塞，Kotlin 端必须在 IO 调用）。返回 {ok}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from models.channel_mappings import mapping_manager
        mapping_manager.refresh_cache()
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('refresh_mappings failed')
        return _err(str(e))


def get_github_proxy_json():
    """读取 GitHub 加速代理配置。返回 {enabled, proxy, proxies}"""
    try:
        from utils import github_proxy
        return _ok(github_proxy.load_settings())
    except Exception as e:
        _ab_logger.exception('get_github_proxy_json failed')
        return _err(str(e))


def set_github_proxy(enabled='true', proxy='gh-proxy.com'):
    """保存 GitHub 加速代理配置（配置写入 config.ini，重启后保留）。返回最新配置"""
    try:
        from utils import github_proxy
        is_enabled = str(enabled).strip().lower() in ('1', 'true', 'yes', 'on', 'y')
        return _ok(github_proxy.save_settings(is_enabled, proxy))
    except Exception as e:
        _ab_logger.exception('set_github_proxy failed')
        return _err(str(e))


# -------------------------------------------------------------------
# 字幕
# -------------------------------------------------------------------

def search_subtitles(query='', imdb_id='', language='all', file_path=''):
    """字幕搜索。返回 {subtitles: [...], last_error: str}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from services.subtitle_download_service import SubtitleDownloadService
        svc = SubtitleDownloadService()
        results = svc.search(
            query=str(query),
            imdb_id=str(imdb_id),
            language=str(language or 'all'),
            file_path=str(file_path),
        )
        return _ok({
            'subtitles': results or [],
            'last_error': getattr(svc, 'last_error', '') or '',
        })
    except Exception as e:
        _ab_logger.exception('search_subtitles failed')
        return _err(str(e))


def download_subtitle(download_link, dest_dir, file_name='', language=''):
    """下载字幕到指定目录。返回 {path} 或 {error}"""
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        from services.subtitle_download_service import SubtitleDownloadService
        svc = SubtitleDownloadService()
        result_path = svc.download(
            download_link=str(download_link),
            dest_dir=str(dest_dir),
            file_name=str(file_name),
            language=str(language),
        )
        if result_path:
            return _ok({'path': result_path})
        return _err(getattr(svc, 'last_error', '下载失败') or '下载失败')
    except Exception as e:
        _ab_logger.exception('download_subtitle failed')
        return _err(str(e))


# -------------------------------------------------------------------
# 缓存清理
# -------------------------------------------------------------------

def clear_cache(cache_type='all'):
    """清空指定类型缓存。
    cache_type: 'all' / 'logo' / 'epg' / 'thumbnails' / 'subtitle'
    返回 {ok, deleted_count}
    """
    try:
        ctx = _get_ctx()
        if ctx is None:
            return _err('not inited')
        import os
        import shutil
        from utils.app_paths import get_cache_dir
        cache_dir = get_cache_dir()
        deleted = 0

        cache_dirs = {
            'logo': ['logo_cache', 'logos'],
            'epg': ['epg_cache'],
            'thumbnails': ['thumbnails', 'thumb_cache'],
            'subtitle': ['subtitles', 'subtitle_cache'],
        }
        if cache_type == 'all':
            target_dirs = []
            for dirs in cache_dirs.values():
                target_dirs.extend(dirs)
        else:
            target_dirs = cache_dirs.get(cache_type, [])

        for d in target_dirs:
            full = os.path.join(cache_dir, d)
            if os.path.isdir(full):
                try:
                    shutil.rmtree(full)
                    deleted += 1
                except Exception as e:
                    _log(f'clear_cache: rmtree {full} failed: {e}', 'W')

        # 台标缓存同时清掉解析结果和失败地址记录，否则会继续跳过坏地址
        if cache_type in ('logo', 'all'):
            try:
                from services.logo_resolver import get_logo_resolver
                get_logo_resolver().clear_cache()
            except Exception as e:
                _log(f'clear_cache: clear logo resolver failed: {e}', 'W')

        return _ok({'ok': True, 'deleted_count': deleted})
    except Exception as e:
        _ab_logger.exception('clear_cache failed')
        return _err(str(e))


def get_thumbnail_paths(urls_json='[]'):
    """批量获取频道缩略图文件路径。
    urls_json: JSON 数组，包含频道 URL 列表
    返回 {ok: true, paths: {url: file_path, ...}}
    """
    try:
        import os
        import json
        import hashlib
        from utils.app_paths import get_cache_dir

        thumb_dir = os.path.join(get_cache_dir(), 'thumbnails')
        thumb_cache_dir = os.path.join(get_cache_dir(), 'thumb_cache')

        urls = json.loads(urls_json) if isinstance(urls_json, str) else urls_json
        paths = {}
        for url in urls:
            if not url:
                continue
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
            # 检查两个可能的缩略图目录
            for d in [thumb_dir, thumb_cache_dir]:
                p = os.path.join(d, f'{url_hash}.png')
                if os.path.exists(p):
                    paths[url] = p
                    break
        return _ok({'paths': paths})
    except Exception as e:
        _ab_logger.exception('get_thumbnail_paths failed')
        return _err(str(e))


def capture_thumbnail(url, file_path):
    """保存指定文件路径的截图作为频道缩略图（由 Kotlin 调用 mpv screenshotToFile 后调用）。
    将截图文件复制到缩略图缓存目录。
    """
    try:
        import os
        import shutil
        import hashlib

        if not url or not os.path.exists(file_path):
            return _err('invalid url or file not found')

        from utils.app_paths import get_cache_dir
        thumb_dir = os.path.join(get_cache_dir(), 'thumbnails')
        os.makedirs(thumb_dir, exist_ok=True)

        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        dest = os.path.join(thumb_dir, f'{url_hash}.png')
        shutil.copy2(file_path, dest)
        return _ok({'path': dest})
    except Exception as e:
        _ab_logger.exception('capture_thumbnail failed')
        return _err(str(e))


def generate_thumbnail_bg(url):
    """后台生成频道缩略图（使用独立 libmpv handle，不影响前台播放器）。

    通过 ctypes 加载 libmpv.so，创建一个独立的 mpv 实例：
    - vo=null（不需要显示 surface，Android 上无需窗口）
    - ao=null（不需要音频输出）
    - 截取解码后的视频帧保存为 PNG

    Returns:
        {ok: true, path: thumbnail_path} 或 {ok: false, error: msg}
    """
    try:
        import os
        import hashlib
        import time

        _log(f'generate_thumbnail_bg: url={url}')

        if not url:
            return _err('empty url')

        # 缩略图保存路径
        from utils.app_paths import get_cache_dir
        thumb_dir = os.path.join(get_cache_dir(), 'thumbnails')
        os.makedirs(thumb_dir, exist_ok=True)
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        thumb_path = os.path.join(thumb_dir, f'{url_hash}.png')

        # 已存在则跳过
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            _log(f'generate_thumbnail_bg: already exists for {url}')
            return _ok({'path': thumb_path, 'cached': True})

        # 尝试加载 libmpv
        # 如果 IPTV_NATIVE_LIB_DIR 未设置，尝试通过 jnius 获取
        if not os.environ.get('IPTV_NATIVE_LIB_DIR'):
            try:
                from jnius import autoclass  # type: ignore
                Python = autoclass('com.chaquo.python.Python')
                app = Python.getPlatform().getApplication()
                app_info = app.getApplicationInfo()
                native_lib_dir = str(app_info.nativeLibraryDir)
                os.environ['IPTV_NATIVE_LIB_DIR'] = native_lib_dir
                _log(f'generate_thumbnail_bg: set IPTV_NATIVE_LIB_DIR={native_lib_dir} via jnius')
            except Exception as e:
                _log(f'generate_thumbnail_bg: jnius get nativeLibraryDir failed: {e}')

        # 强制重置 mpv_common 的加载状态（之前可能因找不到 libmpv 而标记为已加载）
        try:
            import services.mpv_common as _mpv_common
            if not _mpv_common.MPV_AVAILABLE and _mpv_common._mpv_loaded:
                _mpv_common._mpv_loaded = False
                _log('generate_thumbnail_bg: reset mpv_common._mpv_loaded for retry')
        except Exception as e:
            _log(f'generate_thumbnail_bg: reset mpv_common failed: {e}', 'D')

        try:
            from services.mpv_common import (
                create_mpv_handle,
                initialize_mpv,
                destroy_mpv,
                set_option_string as _mpv_set_option_string,
                send_command as _mpv_send_command,
                wait_for_specific_event,
                _is_mpv_available,
                MPV_EVENT_FILE_LOADED,
                MPV_EVENT_END_FILE,
            )
        except Exception as e:
            _log(f'generate_thumbnail_bg: cannot import mpv_common: {e}')
            return _err(f'mpv not available: {e}')

        if not _is_mpv_available():
            _log('generate_thumbnail_bg: libmpv not available')
            return _err('libmpv not available')

        handle = None
        try:
            handle = create_mpv_handle()
            if not handle:
                return _err('failed to create mpv handle')

            # 配置：无显示、无音频、无窗口
            _mpv_set_option_string(handle, 'vo', 'null')
            _mpv_set_option_string(handle, 'ao', 'null')
            _mpv_set_option_string(handle, 'osc', 'no')
            _mpv_set_option_string(handle, 'osd-bar', 'no')
            _mpv_set_option_string(handle, 'idle', 'yes')
            _mpv_set_option_string(handle, 'ytdl', 'no')
            _mpv_set_option_string(handle, 'keep-open', 'yes')
            _mpv_set_option_string(handle, 'log-level', 'error')
            _mpv_set_option_string(handle, 'config', 'no')
            _mpv_set_option_string(handle, 'force-window', 'no')

            # RTSP 传输方式
            u = url.lower()
            if u.startswith('rtsp://'):
                _mpv_set_option_string(handle, 'rtsp-transport', 'tcp')
            elif '/rtp/' in u or u.endswith('.ts') or u.startswith('udp://'):
                _mpv_set_option_string(handle, 'demuxer-lavf-format', 'mpegts')

            # HTTP headers
            try:
                from services.ffprobe_validator_service import FfprobeStreamValidator
                headers = FfprobeStreamValidator.get_headers()
                if headers:
                    import json
                    headers_json = json.dumps(headers).encode('utf-8')
                    _mpv_set_option_string(handle, 'http-header-fields', headers_json)
            except Exception as e:
                _log(f'generate_thumbnail_bg: set http-header-fields failed: {e}', 'D')

            if not initialize_mpv(handle):
                destroy_mpv(handle)
                handle = None
                return _err('failed to initialize mpv')

            # 加载 URL
            _mpv_send_command(handle, ['loadfile', url])

            # 等待文件加载或结束（最多 10 秒）
            event_id, _, _ = wait_for_specific_event(handle, 10, {MPV_EVENT_FILE_LOADED, MPV_EVENT_END_FILE})

            if event_id == MPV_EVENT_FILE_LOADED:
                # 等待解码器产出帧
                time.sleep(1.0)

                # 截图
                _mpv_send_command(handle, ['screenshot-to-file', thumb_path, 'video'])
                time.sleep(0.5)

                if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                    _log(f'generate_thumbnail_bg: success for {url}')
                    return _ok({'path': thumb_path})
                else:
                    _log(f'generate_thumbnail_bg: screenshot file not created for {url}')
                    return _err('screenshot not created')
            else:
                _log(f'generate_thumbnail_bg: file not loaded for {url} (event={event_id})')
                return _err('file load timeout or failed')
        finally:
            if handle:
                try:
                    destroy_mpv(handle)
                except Exception as e:
                    _log(f'generate_thumbnail_bg: destroy_mpv failed: {e}', 'W')
    except Exception as e:
        _log(f'generate_thumbnail_bg: error: {e}')
        _ab_logger.exception('generate_thumbnail_bg failed')
        return _err(str(e))

# -----------------------------------------------------------------
# 局域网管理服务器（TV 端遥控器输入不便，手机浏览器扫码管理）
# -----------------------------------------------------------------

_admin_server_thread = None
_admin_server_url = ''
_admin_server_port = 0
_admin_server_running = False
_admin_server_error = ''
_admin_loop = None
# 保存 _run() 协程的 task 引用，用于优雅取消（task.cancel() 触发 CancelledError，
# 让 _run() 的 finally 块执行 runner.cleanup() 释放 socket；
# 而 loop.stop() 会跳过 finally 导致 socket 泄漏 → 下次 bind 失败）
_admin_server_task = None
_admin_server_lock = _threading.Lock()


def set_admin_token(token=''):
    """设置局域网管理服务器的认证 token。

    传入空字符串则清除自定义 token，下次启动时自动生成 6 位数字认证码。
    传入非空字符串则使用该字符串作为 token（必须是 6 位数字）。
    注意：仅在服务器未运行时生效。
    """
    global _admin_auth_token
    token = token.strip()
    # 认证码统一为 6 位纯数字；留空表示清除自定义值，启动时自动生成
    if token and not (len(token) == 6 and token.isascii() and token.isdigit()):
        return _err('访问令牌必须是 6 位数字')
    with _admin_server_lock:
        if _admin_server_running:
            return _err('服务器运行中，请先停止后再修改令牌')
        _admin_auth_token = token
    if _admin_auth_token:
        _log('Admin server token set to custom')
    else:
        _log('Admin server token cleared, will auto-generate on start')
    return _ok({'ok': True, 'token': _admin_auth_token})


def start_admin_server(port=8080):
    """在后台线程启动 HTTP 管理服务器，返回局域网 URL。

    复用 create_app() + _register_admin_routes_fallback()，暴露 /api/ 和 /admin/ 路由。
    其他设备通过浏览器访问 http://<设备IP>:<port>/admin/ 即可管理。
    """
    global _admin_server_thread, _admin_server_url, _admin_server_port
    global _admin_server_running, _admin_loop, _admin_server_error, _admin_server_task
    global _admin_auth_token

    if _admin_server_running:
        return _ok({'url': _admin_server_url, 'port': _admin_server_port,
                    'already_running': True, 'running': True, 'token': _admin_auth_token})

    # 如果旧 server 线程还在运行（_admin_server_running=False 但线程活着），
    # 说明上一次启动的 import 还在进行中（Chaquopy 首次 import 慢）。
    # 不要停止它，直接返回"正在启动中"，让 Kotlin 端继续轮询。
    # 这样避免用户重复点击导致重启 import（浪费之前的进度）。
    if _admin_server_thread is not None and _admin_server_thread.is_alive():
        _log('Admin server thread still running (importing), returning starting status')
        return _ok({'url': _admin_server_url, 'port': _admin_server_port, 'running': False, 'token': _admin_auth_token})

    # 如果旧线程已结束但有错误（_admin_server_error 非空），需要先清理
    # （旧线程已死，不需要 cancel/join，直接重置状态）
    if _admin_server_thread is not None and not _admin_server_thread.is_alive():
        _log(f'Previous admin server thread ended with error: {_admin_server_error}')
        _admin_server_running = False
        _admin_loop = None
        _admin_server_task = None
        _admin_server_error = ''

    # 重置错误状态
    _admin_server_error = ''

    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        _admin_server_url = f'http://{local_ip}:{port}'
        _admin_server_port = port
    except Exception as e:
        return _err(f'获取局域网 IP 失败: {e}')

    # 生成认证码（首次启动时生成，之后复用）
    # 6 位纯数字认证码（000000-999999），便于在浏览器上手动输入
    if not _admin_auth_token:
        _admin_auth_token = f'{secrets.randbelow(1_000_000):06d}'
        _log('Admin server auth token generated (6-digit PIN)')

    def _run_server():
        global _admin_server_running, _admin_loop, _admin_server_error, _admin_server_task
        try:
            import asyncio
            import time
            from server.routes import create_app
            from server.app import get_server
            from aiohttp import web

            # 同步 admin token 到 server.routes，避免双重认证冲突
            import server.routes as _srv_routes
            _srv_routes._AUTH_TOKEN = _admin_auth_token

            app = create_app()

            # 移除 server.routes 的 auth_middleware，由 _auth_middleware 统一处理
            from aiohttp.frozenlist import FrozenList
            app._middlewares = FrozenList(
                [m for m in app.middlewares if m.__name__ != 'auth_middleware']
            )

            # 注册认证中间件：所有 /api/ 路由需要携带有效 token
            # 静态文件路由（/admin/ /）免认证，页面加载后由前端 JS 在 API 请求中携带 token

            @web.middleware
            async def _auth_middleware(request, handler):
                path = request.path
                # 健康检查端点不需要认证
                if path == '/api/status':
                    return await handler(request)
                # 静态文件路由（/admin/ /）免认证，让页面可以加载
                # 前端 JS 从 URL ?token=xxx 提取令牌后在 API 请求中携带
                if path == '/' or path.startswith('/admin'):
                    return await handler(request)
                # 从 Header 或 query 参数获取 token
                token = request.headers.get('X-Auth-Token', '') or request.query.get('token', '')
                if not secrets.compare_digest(token, _admin_auth_token):
                    return web.json_response(
                        {'error': 'Unauthorized', 'message': '请通过应用端获取访问令牌'},
                        status=401
                    )
                return await handler(request)
            app.middlewares.insert(0, _auth_middleware)

            admin_dir = _find_admin_dir()
            if admin_dir:
                _register_admin_routes_fallback(app, admin_dir)
                _log(f'Admin server admin routes from: {admin_dir}')
            else:
                _log('Admin server: admin dir not found', 'W')

            # 注册虚拟遥控器路由
            _ALLOWED_REMOTE_CMDS = frozenset({
                'up', 'down', 'left', 'right', 'ok', 'back', 'menu',
                'play', 'pause', 'play_pause', 'stop', 'mute',
                'vol_up', 'vol_down', 'seek_forward', 'seek_backward',
                'osd', 'prev_channel', 'next_channel',
            })

            async def _handle_remote(request):
                cmd = request.match_info.get('cmd', '')
                if not cmd:
                    return web.json_response({'success': False, 'error': 'missing cmd'})
                if cmd not in _ALLOWED_REMOTE_CMDS:
                    return web.json_response({'success': False, 'error': 'invalid cmd'}, status=400)
                push_remote_command(cmd)
                return web.json_response({'success': True, 'cmd': cmd})

            app.router.add_post('/api/remote/{cmd}', _handle_remote)
            _log('Admin server remote control routes registered')

            # 注册播放状态查询路由（供 admin 遥控器页面轮询显示当前播放信息）
            async def _handle_player_status(request):
                return web.json_response({'success': True, 'status': get_player_status()})

            app.router.add_get('/api/player/status', _handle_player_status)
            _log('Admin server player status route registered')

            # 注册 logcat 日志查看路由（供 admin 日志页面查看 Kotlin/Android 端日志）
            async def _handle_logcat_view(request):
                import subprocess
                try:
                    lines = max(1, min(int(request.query.get('lines', 200)), 2000))
                except (ValueError, TypeError):
                    lines = 200
                try:
                    # 获取当前应用 PID
                    pid_result = subprocess.run(
                        ['sh', '-c', 'pidof com.iptv.scanner.editor.pro || echo 0'],
                        capture_output=True, text=True, timeout=2
                    )
                    pid = pid_result.stdout.strip().split()[0] if pid_result.stdout.strip() else '0'
                    result = subprocess.run(
                        ['logcat', '-d', '--pid=' + pid],
                        capture_output=True, text=True, timeout=5
                    )
                    all_lines = result.stdout.splitlines() if result.stdout else []
                    # 过滤掉 chatty 和无用日志
                    filtered = [line for line in all_lines if 'chatty' not in line]
                    tail = filtered[-lines:] if len(filtered) > lines else filtered
                    return web.json_response({
                        'success': True,
                        'data': {
                            'lines': tail,
                            'total_lines': len(filtered),
                            'pid': pid,
                            'truncated': len(filtered) > lines
                        }
                    })
                except Exception as e:
                    return web.json_response({'success': False, 'error': str(e)})

            app.router.add_get('/api/logcat/view', _handle_logcat_view)
            _log('Admin server logcat view route registered')

            # 注册音量控制路由（供 admin 遥控器页面通过 HTTP 控制音量）
            async def _handle_set_volume(request):
                data = await request.json()
                vol = max(0, min(int(data.get('volume', 100)), 100))
                push_remote_command(f'set_volume:{vol}')
                return web.json_response({'success': True, 'volume': vol})

            app.router.add_post('/api/player/volume', _handle_set_volume)

            async def _handle_set_mute(request):
                data = await request.json()
                muted = bool(data.get('muted', False))
                push_remote_command('set_mute:true' if muted else 'set_mute:false')
                return web.json_response({'success': True, 'muted': muted})

            app.router.add_post('/api/player/mute', _handle_set_mute)
            _log('Admin server volume/mute control routes registered')

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _admin_loop = loop

            async def _run():
                global _admin_server_running, _admin_server_url, _admin_server_port
                runner = web.AppRunner(app)
                await runner.setup()
                # 端口自动选择：从 port 开始尝试，被占用则递增，最多尝试 10 个端口
                # 不会强行停止占用端口的其他服务，而是自动寻找可用端口
                actual_port = port
                site = None
                for attempt in range(10):
                    try_port = port + attempt
                    try:
                        site = web.TCPSite(runner, '0.0.0.0', try_port)
                        await site.start()
                        actual_port = try_port
                        break
                    except OSError as e:
                        if 'address already in use' in str(e).lower():
                            _log(f'Port {try_port} in use, trying {try_port + 1}...')
                            continue
                        raise
                if site is None:
                    raise OSError(f'No available port in range {port}-{port + 9}')
                # 更新实际使用的端口和 URL（端口可能因冲突而递增）
                if actual_port != _admin_server_port:
                    _admin_server_port = actual_port
                    # 从现有 URL 提取 host，重新构造
                    import re as _re
                    _admin_server_url = _re.sub(r':\d+$', f':{actual_port}', _admin_server_url)
                _admin_server_running = True
                # 同步标记 IPTVServer 为运行中，使 /api/status 返回 running（管理页面状态显示正确）
                svr = get_server()
                if svr:
                    svr._running = True
                    svr._start_time = time.time()
                _log(f'Admin server running at {_admin_server_url} (port={actual_port})')
                try:
                    while True:
                        await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    _log('Admin server task cancelled, cleaning up...')
                    pass
                finally:
                    # 关键：runner.cleanup() 释放 server socket，避免端口泄漏
                    await runner.cleanup()
                    _log('Admin server runner.cleanup() done')
                    _admin_server_running = False
                    # 同步标记 IPTVServer 为已停止
                    svr = get_server()
                    if svr:
                        svr._running = False

            # 用 task 模式：保存 task 引用，外部用 task.cancel() 优雅取消
            # task.cancel() 触发 CancelledError → _run() 的 except 捕获 → finally 执行 runner.cleanup()
            # （对比：loop.stop() 会让 run_until_complete 抛 RuntimeError，跳过 finally，socket 泄漏）
            _admin_server_task = loop.create_task(_run())
            loop.run_until_complete(_admin_server_task)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            # 包含 traceback 在错误信息中，方便 Kotlin 端排查（OSD 会显示，logcat 也会捕获）
            _admin_server_error = f'{e}\n{tb}'
            _log(f'Admin server failed: {e}\n{tb}', 'E')
            _admin_server_running = False
        finally:
            _admin_server_task = None

    _admin_server_thread = _threading.Thread(target=_run_server, daemon=True)
    _admin_server_thread.start()

    # 立即返回，不等待 server 启动完成。
    # 原因：Chaquopy 的 callAttr 在 Python 函数执行期间会持有 GIL，
    # 导致 _run_server 子线程的 import 被阻塞，主线程的等待循环检测不到 _admin_server_running=True。
    # Kotlin 端通过 get_admin_url() 轮询 running 状态来检测后台启动是否完成。
    # 短暂等待 1 秒，让 _run_server 线程有机会启动并报告早期错误（如端口被占用）。
    import time as _time
    _time.sleep(1)
    if _admin_server_error:
        return _err(f'服务器启动失败: {_admin_server_error}')
    # 返回 running=False 表示"正在后台启动中"，Kotlin 端会启动轮询
    return _ok({'url': _admin_server_url, 'port': _admin_server_port,
                'running': _admin_server_running, 'token': _admin_auth_token})


def stop_admin_server():
    """停止 HTTP 管理服务器。"""
    global _admin_server_running, _admin_loop, _admin_server_error, _admin_server_thread, _admin_server_task
    was_running = _admin_server_running
    _admin_server_running = False
    _admin_server_error = ''
    # 用 task.cancel() 代替 loop.stop()：
    # - loop.stop() 让 run_until_complete 抛 RuntimeError，跳过 _run() 的 finally 块 → runner.cleanup() 不执行 → socket 泄漏
    # - task.cancel() 触发 CancelledError → _run() 的 except 捕获 → finally 执行 runner.cleanup() → socket 正确释放
    if _admin_server_task is not None and _admin_loop is not None:
        try:
            _admin_loop.call_soon_threadsafe(_admin_server_task.cancel)
        except Exception as e:
            _log(f'stop_server: cancel task failed: {e}', 'D')
    # 等待 server 线程结束，确保 socket 释放（避免下次启动时 address already in use）
    if _admin_server_thread is not None and _admin_server_thread.is_alive():
        _admin_server_thread.join(timeout=5)
    _admin_loop = None
    _admin_server_task = None
    _log('Admin server stopped')
    return _ok({'ok': True, 'was_running': was_running})


def get_admin_url():
    """返回管理服务器 URL 和运行状态。

    注意：只在有错误时包含 error 字段，避免 Kotlin 端 callPyTyped 误判空字符串为错误。
    """
    result = {
        'url': _admin_server_url,
        'running': _admin_server_running,
        'port': _admin_server_port,
        'token': _admin_auth_token,
    }
    if _admin_server_error:
        result['error'] = _admin_server_error
    return _ok(result)


# -------------------------------------------------------------------
# 虚拟遥控器：从 admin 页面发送遥控命令到 Android 端
#
# 机制：
# 1. admin 页面发送 HTTP POST /api/remote/{cmd}
# 2. Python 端将命令放入 _remote_command_queue
# 3. Kotlin 端每 100ms 轮询 poll_remote_command()，获取命令后执行
#
# 支持的命令：
# up/down/left/right/ok/back/menu/play/pause/play_pause/stop
# mute/vol_up/vol_down/seek_forward/seek_backward/osd
# prev_channel/next_channel
# -------------------------------------------------------------------

import queue as _queue  # noqa: E402
_remote_command_queue = _queue.Queue()

# 播放状态存储（由 Kotlin 端定期更新，供 admin 遥控器页面查询）
_player_status = {
    'channel_name': '',
    'channel_group': '',
    'is_playing': False,
    'is_paused': False,
    'player_type': 'MPV',
    'hardware_decode': True,
    'play_mode': 'live',
    'volume': 100,
    'muted': False,
    'current_program': '',
    'width': 0,
    'height': 0,
    'video_codec': '',
    'audio_codec': '',
    'fps': 0.0,
    'bitrate': 0,
    'hdr': '',
}


def push_remote_command(cmd):
    """将遥控命令放入队列（供 HTTP 路由调用）"""
    try:
        _remote_command_queue.put_nowait(cmd)
        return _ok({'cmd': cmd})
    except Exception as e:
        return _err(f'push command failed: {e}')


def poll_remote_command():
    """轮询遥控命令（供 Kotlin 端调用）。返回命令字符串或 None。"""
    try:
        cmd = _remote_command_queue.get_nowait()
        return _ok({'cmd': cmd})
    except _queue.Empty:
        return _ok({'cmd': None})


def set_player_status(json_str):
    """更新播放状态（供 Kotlin 端定期调用，参数为 JSON 字符串）"""
    try:
        import json as _json
        status_dict = _json.loads(json_str) if isinstance(json_str, str) else json_str
        _player_status.update(status_dict)
        return _ok({'ok': True})
    except Exception as e:
        return _err(f'set_player_status failed: {e}')


def get_player_status():
    """获取当前播放状态（供 HTTP 路由调用）"""
    return _player_status.copy()


# -------------------------------------------------------------------
# 每文件播放设置持久化（#24）
# -------------------------------------------------------------------

_playback_settings_store = None


def _get_settings_store():
    global _playback_settings_store
    if _playback_settings_store is None:
        ctx = _get_ctx()
        if ctx is None:
            return None
        config = ctx.get_config() if hasattr(ctx, 'get_config') else None
        config_dir = ''
        if config and hasattr(config, 'config_dir'):
            config_dir = config.config_dir
        if not config_dir:
            config_dir = getattr(ctx, '_files_dir', '') or ''
        if not config_dir:
            return None
        from core.playback_settings_store import PlaybackSettingsStore
        _playback_settings_store = PlaybackSettingsStore(config_dir)
    return _playback_settings_store


def load_playback_settings(url):
    """读取指定 URL 的播放设置（音轨/字幕轨/音量/比例等）。

    返回 {settings: {...}} 或 {error}
    """
    try:
        store = _get_settings_store()
        if store is None:
            return _ok({'settings': {}})
        settings = store.load_settings(url or '')
        return _ok({'settings': settings})
    except Exception as e:
        _ab_logger.exception('load_playback_settings failed')
        return _err(str(e))


def save_playback_settings(url, settings_json, name=''):
    """保存指定 URL 的播放设置。

    settings_json 是 JSON 字符串，包含音轨/字幕轨/音量/比例等。
    """
    try:
        import json
        store = _get_settings_store()
        if store is None:
            return _err('settings store not available')
        settings = json.loads(settings_json) if settings_json else {}
        store.save_settings(url or '', settings, name or '')
        return _ok({'ok': True})
    except Exception as e:
        _ab_logger.exception('save_playback_settings failed')
        return _err(str(e))
