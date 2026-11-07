import asyncio
import contextlib
import ipaddress
import logging
import os
import re
import secrets as _secrets_mod
from datetime import datetime, timezone, timedelta
from aiohttp import web
from urllib.parse import urlparse

from server.app import get_channel_model, get_config, get_main_window, get_server, get_context
from utils.platform_utils import get_android_data_dir, is_android
from utils.general_utils import redact_url

logger = logging.getLogger('server.routes')

# --- 安全配置 ---
# 认证 Token 优先级：环境变量 ISEP_AUTH_TOKEN > config.ini [Server] auth_token > 自动生成并持久化
# 持久化后客户端重启无需重新获取 Token，避免每次启动随机 Token 导致已登录客户端 401
def _resolve_auth_token() -> str:
    env_token = os.environ.get('ISEP_AUTH_TOKEN', '').strip()
    if env_token:
        return env_token
    try:
        from core.config_manager import ConfigManager
        config = ConfigManager()
        token = (config.get_value('Server', 'auth_token', '') or '').strip()
        if token:
            return token
        token = _secrets_mod.token_hex(16)
        config.set_value('Server', 'auth_token', token)
        config.save_config(immediate=True)
        logger.info('已在 config.ini [Server] auth_token 中生成并保存认证 Token')
        return token
    except Exception as e:
        logger.warning(f'读取/持久化认证 Token 失败，使用进程内临时 Token: {e}')
        return _secrets_mod.token_hex(16)


_AUTH_TOKEN = _resolve_auth_token()
# 认证请求头名称（PC 管理面板使用 X-Auth-Token）
_AUTH_HEADER_NAME = 'X-Auth-Token'

# 允许的流代理 URL 协议
_ALLOWED_STREAM_PROTOCOLS = {'http', 'https', 'rtsp', 'rtmp', 'rtp', 'udp', 'srt'}
# 可被流代理转发的协议（aiohttp 只支持 http/https）
_PROXYABLE_STREAM_PROTOCOLS = {'http', 'https'}


def get_auth_token() -> str:
    """返回当前认证 Token"""
    return _AUTH_TOKEN

# 共享 aiohttp ClientSession（流代理用），延迟初始化
_stream_session = None
_stream_session_loop = None
_stream_session_lock = asyncio.Lock()

# 流代理超时：total=None 防止长连接在 30s 后被强制中断；只限制连接与单次读取
_STREAM_TIMEOUT = None


def _get_stream_timeout():
    global _STREAM_TIMEOUT
    if _STREAM_TIMEOUT is None:
        import aiohttp
        _STREAM_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=60)
    return _STREAM_TIMEOUT


async def _get_stream_session():
    """获取共享的 aiohttp ClientSession，避免每个请求创建新连接池"""
    global _stream_session, _stream_session_loop
    loop = asyncio.get_running_loop()
    async with _stream_session_lock:
        # 服务器重启会换事件循环，旧 Session 绑定旧 loop 必须重建
        if (_stream_session is None or _stream_session.closed
                or _stream_session_loop is not loop):
            import aiohttp
            _stream_session = aiohttp.ClientSession(
                timeout=_get_stream_timeout(),
                connector=aiohttp.TCPConnector(limit=20, limit_per_host=5)
            )
            _stream_session_loop = loop
        return _stream_session


_DNS_CACHE: dict = {}
_DNS_CACHE_TTL = 60.0


def _resolve_host_ips(host: str) -> list:
    """解析主机名到 IP 列表，带 60s 缓存；解析失败返回空列表"""
    import socket
    import time as _time
    now = _time.time()
    cached = _DNS_CACHE.get(host)
    if cached and now - cached[0] < _DNS_CACHE_TTL:
        return cached[1]
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({info[4][0] for info in infos})
    except Exception:
        ips = []
    _DNS_CACHE[host] = (now, ips)
    return ips


def _is_private_ip(host: str) -> bool:
    """检查主机名是否为内网地址（用于 SSRF 防护）"""
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
        # 组播地址（224.0.0.0-239.255.255.255）不视为私有，允许 IPTV 组播流
        if ip.is_multicast:
            return False
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # 域名：解析后逐个校验，全部为公网地址才放行（防止 DNS rebinding 绕过）
        ips = _resolve_host_ips(host)
        if not ips:
            return True
        for addr in ips:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                return True
            if ip.is_multicast:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
                return True
        return False


def _is_safe_stream_url(url: str) -> tuple:
    """检查流代理 URL 是否安全
    返回 (是否安全, 拒绝原因)
    """
    if not url:
        return False, 'URL为空'
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or '').lower()
        if scheme not in _ALLOWED_STREAM_PROTOCOLS:
            return False, f'不允许的协议: {scheme}'
        host = parsed.hostname or ''
        if not host:
            return False, '无法解析主机名'
        # 仅对 HTTP/HTTPS 执行 SSRF 防护（rtp/udp/rtsp 等流媒体协议豁免）
        if scheme in _PROXYABLE_STREAM_PROTOCOLS and _is_private_ip(host):
            return False, f'内网地址不允许代理: {host}'
        return True, ''
    except Exception as e:
        return False, f'URL解析失败: {e}'


# 空上下文管理器，用于 getattr(ctx, '_channels_lock', _noop_lock) 时 ctx 无锁的兜底
@contextlib.contextmanager
def _noop_lock():
    yield


def _parse_xmltv_time(time_str: str):
    """解析 XMLTV 时间字符串，支持多种格式：
    - ISO 8601: 2024-01-01T12:00:00+08:00
    - XMLTV:   20240101120000 +0800
    - XMLTV:   20240101120000Z
    """
    if not time_str:
        return None
    s = time_str.strip()
    try:
        # 尝试 ISO 8601 格式
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        pass
    # 尝试 XMLTV 格式: YYYYMMDDHHmmss [+-]ZZZZ

    m = re.match(r'^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\s*([+-]\d{4})?$', s)
    if m:
        year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
        tz_str = m.group(7)
        if tz_str:
            tz_sign = 1 if tz_str[0] == '+' else -1
            tz_hours = int(tz_str[1:3])
            tz_minutes = int(tz_str[3:5])
            tz = timezone(tz_sign * timedelta(hours=tz_hours, minutes=tz_minutes))
        else:
            tz = None
        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=tz)
        except ValueError:
            return None
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


def _register_admin_routes(app):
    """注册管理后台静态文件路由"""
    admin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin')
    if not os.path.isdir(admin_dir):
        logger.warning(f'Admin directory not found: {admin_dir}')
        return

    async def _handle_admin(request):
        rel_path = request.match_info.get('path', 'index.html')
        if not rel_path or rel_path.endswith('/'):
            rel_path += 'index.html'
        # 安全：防止路径穿越（../../../etc/passwd 等）
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
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                     'Pragma': 'no-cache', 'Expires': '0'})

    try:
        app.router.add_get('/admin/', _handle_admin)
        app.router.add_get('/admin/{path:.*}', _handle_admin)
        logger.info(f'Admin UI registered from: {admin_dir}')
    except ValueError:
        # Android 端可能已由 android_bridge.py 注册，忽略重复注册错误
        logger.debug('Admin routes already registered, skipping')


def _get_all_channels():
    ctx = get_context()
    if ctx:
        return ctx.get_all_channels()
    return []


def _call_model_on_qt_thread(model, func, *args, **kwargs):
    """Qt 模型只能在所属线程操作：跨线程调用投递回主线程，避免界面错乱/崩溃"""
    try:
        from utils.thread_safety import invoke_on_thread
        invoke_on_thread(model, lambda: func(*args, **kwargs))
        return True
    except Exception as e:
        logger.warning(f'操作频道模型失败: {e}')
        return False


_I18N = {
    'zh': {
        'title': 'IPTV扫描编辑器专业版',
        'subtitle': '直播Server & RESTful API',
        'status': '服务器状态',
        'running': '运行中',
        'stopped': '已停止',
        'uptime': '运行时间',
        'base_url': '访问地址',
        'playlist': '频道列表',
        'channels': '频道管理',
        'sources': '订阅源',
        'scan': '扫描',
        'epg': '节目单',
        'stream_proxy': '流代理',
        'footer': 'IPTV扫描编辑器专业版 · 内置HTTP Server · 基于 aiohttp',
        'm3u_desc': 'M3U频道列表 (参数: valid=1, search=, group=)',
        'm3u_group_desc': '按分组获取M3U频道列表',
        'ch_list_desc': '频道列表 (参数: valid=1/0, group=, search=, page=, size=, source=)',
        'ch_get_desc': '按索引获取频道',
        'ch_add_desc': '添加频道 (body: {url, name, group})',
        'ch_update_desc': '更新频道',
        'ch_delete_desc': '删除频道',
        'ch_import_desc': '导入M3U内容 (body: {content, name})',
        'src_list_desc': '获取订阅源列表',
        'src_add_desc': '添加订阅源 (body: {url, name})',
        'src_update_desc': '更新订阅源 (启用/禁用)',
        'src_delete_desc': '删除订阅源',
        'src_reload_desc': '重新加载全部订阅源',
        'src_status_desc': '订阅源加载状态',
        'epg_src_list_desc': '获取EPG订阅源列表',
        'epg_src_add_desc': '添加EPG源 (body: {url, name})',
        'epg_src_delete_desc': '删除EPG源',
        'epg_reload_desc': '重新加载EPG数据',
        'scan_start_desc': '开始扫描 (body: {url})',
        'scan_stop_desc': '停止扫描',
        'scan_status_desc': '扫描状态和统计',
        'scan_range_desc': 'URL范围扫描 (body: {url, timeout, threads})',
        'scan_results_desc': '获取扫描结果列表',
        'epg_desc': 'EPG节目单数据 (参数: id=, search=)',
        'stream_desc': '按索引代理频道流',
        'mappings_desc': '频道映射管理 (获取/添加/删除/刷新)',
        'player_desc': '播放器控制 (章节/HDR/截图/状态/遥控)',
        'subtitle_desc': '字幕搜索与下载',
        'log_desc': '日志查看/下载/清空',
        'cache_desc': '缓存清理 (缩略图/截图/字幕)',
        'quick_m3u': 'M3U频道列表',
        'quick_channels': '频道列表',
        'quick_status': '运行状态',
        'quick_epg': '节目单',
        'quick_admin': '管理后台',
        'nav_admin': '管理后台',
        'nav_admin_desc': '完整的频道/订阅源/EPG/扫描/映射/日志管理界面',
        'no_data': '暂无频道数据',
    },
    'en': {
        'title': 'GuangYu',
        'subtitle': 'Live Streaming Server & RESTful API',
        'status': 'Server Status',
        'running': 'Running',
        'stopped': 'Stopped',
        'uptime': 'Uptime',
        'base_url': 'Base URL',
        'playlist': 'Channel List',
        'channels': 'Channels',
        'sources': 'Sources',
        'scan': 'Scan',
        'epg': 'EPG',
        'stream_proxy': 'Stream Proxy',
        'footer': 'GuangYu · Built-in HTTP Server · Powered by aiohttp',
        'm3u_desc': 'M3U channel list (params: valid=1, search=, group=)',
        'm3u_group_desc': 'M3U channel list by group',
        'ch_list_desc': 'Channel list (params: valid=1/0, group=, search=, page=, size=, source=)',
        'ch_get_desc': 'Get channel by index',
        'ch_add_desc': 'Add channel (body: {url, name, group})',
        'ch_update_desc': 'Update channel',
        'ch_delete_desc': 'Delete channel',
        'ch_import_desc': 'Import M3U content (body: {content, name})',
        'src_list_desc': 'List subscription sources',
        'src_add_desc': 'Add source (body: {url, name})',
        'src_update_desc': 'Update source (enable/disable)',
        'src_delete_desc': 'Delete source',
        'src_reload_desc': 'Reload all sources',
        'src_status_desc': 'Source loading status',
        'epg_src_list_desc': 'List EPG sources',
        'epg_src_add_desc': 'Add EPG source (body: {url, name})',
        'epg_src_delete_desc': 'Delete EPG source',
        'epg_reload_desc': 'Reload EPG data',
        'scan_start_desc': 'Start scan (body: {url})',
        'scan_stop_desc': 'Stop scan',
        'scan_status_desc': 'Scan status & stats',
        'scan_range_desc': 'URL range scan (body: {url, timeout, threads})',
        'scan_results_desc': 'Get scan results list',
        'epg_desc': 'EPG data (params: id=, search=)',
        'stream_desc': 'Proxy stream for channel by index',
        'mappings_desc': 'Channel mapping management (get/add/delete/refresh)',
        'player_desc': 'Player control (chapters/HDR/screenshot/status/remote)',
        'subtitle_desc': 'Subtitle search & download',
        'log_desc': 'Log view/download/clear',
        'cache_desc': 'Cache clear (thumbnails/screenshots/subtitles)',
        'quick_m3u': 'M3U Channel List',
        'quick_channels': 'Channels',
        'quick_status': 'Status',
        'quick_epg': 'EPG',
        'quick_admin': 'Admin Panel',
        'nav_admin': 'Admin Panel',
        'nav_admin_desc': 'Full management UI for channels/sources/EPG/scan/mappings/logs',
        'no_data': 'No channel data',
    }
}


def _get_lang(request):
    lang = request.rel_url.query.get('lang', '').strip().lower()
    if lang in ('zh', 'cn', 'zh-cn', 'zh_cn'):
        return 'zh'
    accept = request.headers.get('Accept-Language', '')
    if 'zh' in accept.lower():
        return 'zh'
    return 'en'


def _t(lang, key, default=''):
    return _I18N.get(lang, {}).get(key, _I18N.get('en', {}).get(key, default))


def create_app() -> web.Application:
    # client_max_size：aiohttp 默认 1MB，导入较大的 M3U 内容会被 413 拒绝
    app = web.Application(
        middlewares=[auth_middleware, error_middleware, cors_middleware],
        client_max_size=32 * 1024 * 1024,
    )
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/status', handle_status)
    app.router.add_get('/api/m3u', handle_m3u)
    app.router.add_get('/api/m3u/{group}', handle_m3u)
    app.router.add_get('/api/channels', handle_channels_list)
    app.router.add_get('/api/channels/{id}', handle_channel_get)
    app.router.add_put('/api/channels/{id}', handle_channel_update)
    app.router.add_delete('/api/channels/{id}', handle_channel_delete)
    app.router.add_post('/api/channels', handle_channel_add)
    app.router.add_post('/api/channels/import', handle_channels_import)
    app.router.add_post('/api/channels/batch', handle_channels_batch)
    app.router.add_get('/api/sources', handle_sources_list)
    app.router.add_post('/api/sources', handle_sources_add)
    app.router.add_put('/api/sources/{id}', handle_sources_update)
    app.router.add_delete('/api/sources/{id}', handle_sources_delete)
    app.router.add_post('/api/sources/reload', handle_sources_reload)
    app.router.add_get('/api/sources/status', handle_sources_status)
    app.router.add_get('/api/epg/sources', handle_epg_sources_list)
    app.router.add_post('/api/epg/sources', handle_epg_sources_add)
    app.router.add_delete('/api/epg/sources/{id}', handle_epg_sources_delete)
    app.router.add_post('/api/epg/reload', handle_epg_reload)
    app.router.add_post('/api/scan/start', handle_scan_start)
    app.router.add_post('/api/scan/stop', handle_scan_stop)
    app.router.add_get('/api/scan/status', handle_scan_status)
    app.router.add_post('/api/scan/range', handle_scan_range)
    app.router.add_get('/api/scan/results', handle_scan_results)
    app.router.add_post('/api/scan/validate', handle_scan_validate)
    app.router.add_get('/api/mappings', handle_mappings_list)
    app.router.add_post('/api/mappings', handle_mappings_add)
    app.router.add_delete('/api/mappings/{id}', handle_mappings_delete)
    app.router.add_post('/api/mappings/refresh', handle_mappings_refresh)
    app.router.add_get('/api/epg', handle_epg)
    app.router.add_get('/stream/{id}', handle_stream_proxy)
    # 播放器远程控制
    app.router.add_get('/api/player/chapters', handle_player_chapters)
    app.router.add_post('/api/player/hdr', handle_player_hdr)
    app.router.add_post('/api/player/screenshot', handle_player_screenshot)
    # 字幕在线下载
    app.router.add_get('/api/subtitle/search', handle_subtitle_search)
    app.router.add_post('/api/subtitle/download', handle_subtitle_download)
    # 文件分享与缓存清理
    app.router.add_post('/api/share/file', handle_share_file)
    app.router.add_post('/api/cache/clear', handle_cache_clear)
    # 日志查看与下载
    app.router.add_get('/api/log/view', handle_log_view)
    app.router.add_get('/api/log/download', handle_log_download)
    app.router.add_post('/api/log/clear', handle_log_clear)
    # WebSocket 端点：实时日志流
    app.router.add_get('/ws/logs', handle_ws_logs)
    # 管理后台静态文件（局域网 Web 管理页面）
    _register_admin_routes(app)
    return app


async def handle_ws_logs(request):
    """WebSocket 端点：实时推送日志行到前端。

    连接后持续读取 app.log 文件尾部，有新行时推送到客户端。
    客户端通过 WebSocket 接收日志行，实现实时日志流。
    """
    # 认证检查：从查询参数获取 token
    ws_token = request.rel_url.query.get('token', '').strip()
    if _AUTH_TOKEN and ws_token != _AUTH_TOKEN:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close(code=4001, message=b'Unauthorized')
        return ws

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    from core.log_manager import global_logger

    # 确定日志文件路径
    log_file = None
    try:
        ctx = get_context()
        if ctx:
            log_file = getattr(ctx, '_log_file_path', None)
    except Exception:
        pass

    if not log_file:
        # 回退到默认路径
        from utils.platform_utils import get_android_data_dir
        log_file = os.path.join(get_android_data_dir(), 'ISEP', 'app.log')

    last_pos = 0
    try:
        if os.path.exists(log_file):
            # 从文件尾部开始（最后 200 行）
            file_size = os.path.getsize(log_file)
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                # 先发送现有尾部日志
                f.seek(max(0, file_size - 8192))
                if file_size > 8192:
                    f.readline()  # 跳过可能截断的行
                for line in f:
                    await ws.send_str(line.rstrip())
                last_pos = f.tell()
    except Exception as e:
        global_logger.error(f'ws_logs: error reading initial log: {e}')

    # 持续监听新日志行
    try:
        while True:
            await asyncio.sleep(0.5)
            if not os.path.exists(log_file):
                continue
            try:
                file_size = os.path.getsize(log_file)
                # 文件被截断（轮转）
                if file_size < last_pos:
                    last_pos = 0
                if file_size > last_pos:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(last_pos)
                        for line in f:
                            await ws.send_str(line.rstrip())
                        last_pos = f.tell()
            except Exception:
                pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        global_logger.error(f'ws_logs: error in watch loop: {e}')
    finally:
        await ws.close()
    return ws


# 免认证路由前缀（仅首页和静态资源）
_AUTH_EXEMPT_PREFIXES = ('/',)


def _is_auth_required(request):
    """判断请求是否需要认证"""
    path = request.path
    # 首页和静态资源免认证
    for prefix in _AUTH_EXEMPT_PREFIXES:
        if path == prefix:
            return False
    # 如果未配置 Token，免认证（仅限 localhost 场景）
    if not _AUTH_TOKEN:
        return False
    return True


@web.middleware
async def auth_middleware(request, handler):
    """API 认证中间件
    通过环境变量 ISEP_AUTH_TOKEN 或配置设置认证 Token。
    客户端可任选一种方式携带 Token：Authorization: Bearer <token>、
    X-Auth-Token: <token> 或查询参数 ?token=<token>。
    未配置 Token 时免认证（适用于 localhost 场景）。
    """
    if not _is_auth_required(request):
        return await handler(request)
    # 支持三种携带方式：Authorization: Bearer、?token=、X-Auth-Token（PC 管理面板）
    auth_header = request.headers.get('Authorization', '')
    token = ''
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
    if not token:
        token = (request.headers.get(_AUTH_HEADER_NAME, '') or '').strip()
    if not token:
        token = request.rel_url.query.get('token', '').strip()
    if not _secrets_mod.compare_digest(token, _AUTH_TOKEN):
        return web.json_response(
            {'success': False, 'error': '未授权访问'}, status=401
        )
    return await handler(request)


@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        resp = web.Response(status=204)
    else:
        resp = await handler(request)
    # CORS 限制：仅允许 localhost 和同源请求
    origin = request.headers.get('Origin', '')
    if _is_localhost_origin(origin):
        resp.headers['Access-Control-Allow-Origin'] = origin
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
    else:
        resp.headers['Access-Control-Allow-Origin'] = 'null'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Auth-Token'
    return resp


def _is_localhost_origin(origin: str) -> bool:
    """检查 Origin 是否为 localhost 或 127.0.0.1"""
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ''
        return host in ('localhost', '127.0.0.1', '::1')
    except (ValueError, TypeError):
        return False


@web.middleware
async def error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        logger.error(f"API错误: {e}", exc_info=True)
        return web.json_response({'error': '内部服务器错误'}, status=500)


def _json_success(data=None, **kwargs):
    result = {'success': True}
    if data is not None:
        result['data'] = data
    result.update(kwargs)
    return web.json_response(result)


def _json_error(message, status=400):
    return web.json_response({'success': False, 'error': message}, status=status)


async def handle_index(request):
    # 优先返回管理后台页面（admin/index.html）
    admin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin')
    admin_index = os.path.join(admin_dir, 'index.html')
    if os.path.isfile(admin_index):
        with open(admin_index, 'rb') as f:
            content = f.read()
        return web.Response(
            body=content, content_type='text/html', charset='utf-8',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                     'Pragma': 'no-cache', 'Expires': '0'})
    # fallback: 原来的 API 文档页面
    server = get_server()
    base_url = f"http://{request.host}"
    lang = _get_lang(request)
    html = _render_index_page(base_url, server, lang)
    return web.Response(text=html, content_type='text/html', charset='utf-8')


def _render_index_page(base_url, server, lang='en'):
    is_running = server.is_running() if server else False
    uptime = server.get_uptime() if server else 0
    uptime_str = f"{uptime // 3600}h {uptime % 3600 // 60}m {uptime % 60}s" if uptime > 0 else "-"
    status_color = "#4CAF50" if is_running else "#FF9800"
    status_text = _t(lang, 'running') if is_running else _t(lang, 'stopped')

    api_groups = [
        {
            "title": _t(lang, 'playlist'),
            "icon": "&#9654;",
            "apis": [
                {"method": "GET", "path": "/api/m3u", "desc": _t(lang, 'm3u_desc'), "type": "link"},
                {"method": "GET", "path": "/api/m3u/{group}", "desc": _t(lang, 'm3u_group_desc'), "type": "link"},
            ]
        },
        {
            "title": _t(lang, 'channels'),
            "icon": "&#128250;",
            "apis": [
                {"method": "GET", "path": "/api/channels", "desc": _t(lang, 'ch_list_desc'), "type": "json"},
                {"method": "GET", "path": "/api/channels/{id}", "desc": _t(lang, 'ch_get_desc'), "type": "json"},
                {"method": "POST", "path": "/api/channels", "desc": _t(lang, 'ch_add_desc'), "type": "json"},
                {"method": "POST", "path": "/api/channels/import", "desc": _t(lang, 'ch_import_desc'), "type": "json"},
                {"method": "PUT", "path": "/api/channels/{id}", "desc": _t(lang, 'ch_update_desc'), "type": "json"},
                {"method": "DELETE", "path": "/api/channels/{id}", "desc": _t(lang, 'ch_delete_desc'), "type": "json"},
            ]
        },
        {
            "title": _t(lang, 'sources'),
            "icon": "&#128229;",
            "apis": [
                {"method": "GET", "path": "/api/sources", "desc": _t(lang, 'src_list_desc'), "type": "json"},
                {"method": "POST", "path": "/api/sources", "desc": _t(lang, 'src_add_desc'), "type": "json"},
                {"method": "PUT", "path": "/api/sources/{id}", "desc": _t(lang, 'src_update_desc'), "type": "json"},
                {"method": "DELETE", "path": "/api/sources/{id}", "desc": _t(lang, 'src_delete_desc'), "type": "json"},
                {"method": "POST", "path": "/api/sources/reload", "desc": _t(lang, 'src_reload_desc'), "type": "json"},
                {"method": "GET", "path": "/api/sources/status", "desc": _t(lang, 'src_status_desc'), "type": "json"},
            ]
        },
        {
            "title": _t(lang, 'epg'),
            "icon": "&#128197;",
            "apis": [
                {"method": "GET", "path": "/api/epg", "desc": _t(lang, 'epg_desc'), "type": "json"},
                {"method": "GET", "path": "/api/epg/sources", "desc": _t(lang, 'epg_src_list_desc'), "type": "json"},
                {"method": "POST", "path": "/api/epg/sources", "desc": _t(lang, 'epg_src_add_desc'), "type": "json"},
                {"method": "DELETE", "path": "/api/epg/sources/{id}", "desc": _t(lang, 'epg_src_delete_desc'), "type": "json"},
                {"method": "POST", "path": "/api/epg/reload", "desc": _t(lang, 'epg_reload_desc'), "type": "json"},
            ]
        },
        {
            "title": _t(lang, 'scan'),
            "icon": "&#128269;",
            "apis": [
                {"method": "POST", "path": "/api/scan/start", "desc": _t(lang, 'scan_start_desc'), "type": "json"},
                {"method": "POST", "path": "/api/scan/stop", "desc": _t(lang, 'scan_stop_desc'), "type": "json"},
                {"method": "GET", "path": "/api/scan/status", "desc": _t(lang, 'scan_status_desc'), "type": "json"},
                {"method": "POST", "path": "/api/scan/range", "desc": _t(lang, 'scan_range_desc'), "type": "json"},
                {"method": "GET", "path": "/api/scan/results", "desc": _t(lang, 'scan_results_desc'), "type": "json"},
            ]
        },
        {
            "title": _t(lang, 'mappings_desc').split('(')[0].strip(),
            "icon": "&#128279;",
            "apis": [
                {"method": "GET", "path": "/api/mappings", "desc": _t(lang, 'mappings_desc'), "type": "json"},
                {"method": "POST", "path": "/api/mappings", "desc": _t(lang, 'mappings_desc'), "type": "json"},
                {"method": "DELETE", "path": "/api/mappings/{id}", "desc": _t(lang, 'mappings_desc'), "type": "json"},
                {"method": "POST", "path": "/api/mappings/refresh", "desc": _t(lang, 'mappings_desc'), "type": "json"},
            ]
        },
        {
            "title": _t(lang, 'stream_proxy'),
            "icon": "&#127909;",
            "apis": [
                {"method": "GET", "path": "/stream/{id}", "desc": _t(lang, 'stream_desc'), "type": "stream"},
            ]
        },
    ]

    method_colors = {"GET": "#4CAF50", "POST": "#FF9800", "PUT": "#2196F3", "DELETE": "#F44336"}

    api_sections = ""
    for group in api_groups:
        rows = ""
        for api in group["apis"]:
            mc = method_colors.get(api["method"], "#999")
            type_badge = ""
            if api["type"] == "link":
                type_badge = (
                    f'<a href="{base_url}{api["path"]}" target="_blank" '
                    f'style="color:#4CAF50;font-size:11px;text-decoration:none;">'
                    f'&#128279; Open</a>'
                )
            elif api["type"] == "stream":
                type_badge = '<span style="color:#9C27B0;font-size:11px;">STREAM</span>'
            else:
                type_badge = '<span style="color:#607D8B;font-size:11px;">JSON</span>'
            rows += f"""
            <tr>
                <td style="padding:8px 12px;">
                    <span style="background:{mc};color:#fff;padding:2px 8px;
                               border-radius:4px;font-size:11px;font-weight:600;">
                        {api["method"]}
                    </span>
                </td>
                <td style="padding:8px 12px;font-family:monospace;font-size:13px;color:#E0E0E0;">{api["path"]}</td>
                <td style="padding:8px 12px;font-size:12px;color:#BDBDBD;">{api["desc"]}</td>
                <td style="padding:8px 12px;">{type_badge}</td>
            </tr>"""
        api_sections += f"""
        <div style="margin-bottom:24px;">
            <h3 style="color:#E0E0E0;margin:0 0 8px 0;font-size:15px;">{group["icon"]} {group["title"]}</h3>
            <table style="width:100%;border-collapse:collapse;
                   background:rgba(255,255,255,0.03);
                   border-radius:8px;overflow:hidden;">
                {rows}
            </table>
        </div>"""

    lang_toggle = 'en' if lang == 'zh' else 'zh'
    lang_label = 'English' if lang == 'zh' else '中文'

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_t(lang, 'title')} - API</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#1a1a2e; color:#E0E0E0;
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
        min-height:100vh; }}
.container {{ max-width:960px; margin:0 auto; padding:40px 24px; }}
.header {{ text-align:center; margin-bottom:40px; }}
.header h1 {{ font-size:28px; font-weight:700; color:#fff; margin-bottom:8px; }}
.header p {{ font-size:14px; color:#9E9E9E; }}
.lang-toggle {{ position:absolute; top:16px; right:24px;
                background:rgba(255,255,255,0.08);
                border:1px solid rgba(255,255,255,0.12);
                border-radius:6px; padding:6px 14px; color:#BDBDBD;
                font-size:12px; text-decoration:none; transition:all 0.2s; }}
.lang-toggle:hover {{ background:rgba(255,255,255,0.15); color:#fff; }}
.status-card {{ display:flex; align-items:center; justify-content:center;
                gap:16px; background:rgba(255,255,255,0.05);
                border:1px solid rgba(255,255,255,0.08);
                border-radius:12px; padding:20px; margin-bottom:32px; }}
.status-dot {{ width:12px; height:12px; border-radius:50%;
               background:{status_color};
               box-shadow:0 0 8px {status_color}; }}
.status-info {{ text-align:left; }}
.status-info .label {{ font-size:12px; color:#9E9E9E; text-transform:uppercase; letter-spacing:1px; }}
.status-info .value {{ font-size:16px; font-weight:600; color:#fff; }}
.quick-links {{ display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin-bottom:32px; }}
.quick-link {{ background:rgba(255,255,255,0.06);
               border:1px solid rgba(255,255,255,0.1);
               border-radius:8px; padding:12px 20px;
               text-decoration:none; color:#E0E0E0;
               font-size:13px; transition:all 0.2s; }}
.quick-link:hover {{ background:rgba(255,255,255,0.12); border-color:rgba(255,255,255,0.2); color:#fff; }}
.quick-link .path {{ font-family:monospace; color:#4CAF50; font-size:12px; }}
.footer {{ text-align:center; margin-top:40px; padding-top:20px;
           border-top:1px solid rgba(255,255,255,0.06);
           color:#616161; font-size:12px; }}
</style>
</head>
<body>
<a class="lang-toggle" href="?lang={lang_toggle}">{lang_label}</a>
<div class="container">
    <div class="header">
        <h1>{_t(lang, 'title')}</h1>
        <p>{_t(lang, 'subtitle')}</p>
    </div>
    <div class="status-card">
        <div class="status-dot"></div>
        <div class="status-info">
            <div class="label">{_t(lang, 'status')}</div>
            <div class="value">{status_text} &middot; {_t(lang, 'uptime')}: {uptime_str}</div>
        </div>
        <div class="status-info" style="margin-left:32px;">
            <div class="label">{_t(lang, 'base_url')}</div>
            <div class="value" style="font-family:monospace;font-size:14px;">{base_url}</div>
        </div>
    </div>
    <div class="quick-links">
        <a class="quick-link" href="{base_url}/admin/" target="_blank" style="border-color:rgba(74,126,255,.3);background:rgba(74,126,255,.08)">
            &#128736; {_t(lang, 'quick_admin')} <span class="path">/admin/</span></a>
        <a class="quick-link" href="{base_url}/api/m3u" target="_blank">
            &#9654; {_t(lang, 'quick_m3u')} <span class="path">/api/m3u</span></a>
        <a class="quick-link" href="{base_url}/api/channels" target="_blank">
            &#128250; {_t(lang, 'quick_channels')} <span class="path">/api/channels</span></a>
        <a class="quick-link" href="{base_url}/api/status" target="_blank">
            &#8505; {_t(lang, 'quick_status')} <span class="path">/api/status</span></a>
        <a class="quick-link" href="{base_url}/api/epg" target="_blank">
            &#128197; {_t(lang, 'quick_epg')} <span class="path">/api/epg</span></a>
    </div>
    {api_sections}
    <div class="footer">
        {_t(lang, 'footer')}
    </div>
</div>
</body>
</html>"""


async def handle_status(request):
    server = get_server()
    channels = _get_all_channels()
    total = len(channels)
    valid = sum(1 for ch in channels if ch.get('valid') is True)
    config = get_config()
    port = 8080
    if config:
        try:
            settings = config.load_server_settings()
            port = settings.get('port', 8080)
        except (OSError, ValueError, RuntimeError):
            pass
    return _json_success(
        server='running' if server.is_running() else 'stopped',
        host=server.host if server else '0.0.0.0',
        port=server.port if server else port,
        uptime=server.get_uptime() if server else 0,
        channels={'total': total, 'valid': valid, 'invalid': total - valid}
    )


async def handle_m3u(request):
    channels = _get_all_channels()
    if not channels:
        return web.Response(text='#EXTM3U\n', content_type='audio/mpegurl')
    group_filter = request.match_info.get('group', None)
    valid_only = request.rel_url.query.get('valid', '0') == '1'
    search = request.rel_url.query.get('search', '').strip().lower()
    lines = ['#EXTM3U']
    for ch in channels:
        if valid_only and ch.get('valid') is not True:
            continue
        group = ch.get('group', '')
        if group_filter and group != group_filter:
            continue
        name = ch.get('name', '')
        if search and search not in name.lower() and search not in group.lower():
            continue
        url = ch.get('url', '')
        if not url:
            continue
        tvg_id = ch.get('tvg_id', '')
        tvg_chno = ch.get('tvg_chno', '')
        logo = ch.get('logo', '')
        attrs = []
        if tvg_id:
            attrs.append(f'tvg-id="{tvg_id}"')
        if tvg_chno:
            attrs.append(f'tvg-chno="{tvg_chno}"')
        if logo:
            attrs.append(f'tvg-logo="{logo}"')
        attrs.append(f'group-title="{group}"')
        attr_str = ' '.join(attrs)
        lines.append(f'#EXTINF:-1 {attr_str},{name}')
        lines.append(url)
    content = '\n'.join(lines) + '\n'
    return web.Response(
        text=content,
        content_type='audio/mpegurl',
        charset='utf-8',
        headers={'Content-Disposition': 'attachment; filename="iptv.m3u"'}
    )


async def handle_channels_list(request):
    try:
        ctx = get_context()
        # 使用 get_all_channels 加锁复制，避免并发修改崩溃
        all_channels = ctx.get_all_channels() if ctx else []
        if not all_channels:
            # 返回空列表而非 503，让前端正常显示"暂无频道"
            return _json_success(
                channels=[],
                total=0,
                page=1,
                page_size=min(500, max(1, int(request.rel_url.query.get('size', '100')))),
                groups=[]
            )
        valid_only = request.rel_url.query.get('valid', '').strip()
        group = request.rel_url.query.get('group', '').strip()
        search = request.rel_url.query.get('search', '').strip().lower()
        # source 过滤：source=local 仅显示手动添加/本地频道（source 为空），
        # source=sub 仅显示订阅源频道（source 非空），不传则显示全部
        source_filter = request.rel_url.query.get('source', '').strip()
        page = max(1, int(request.rel_url.query.get('page', '1')))
        page_size = min(500, max(1, int(request.rel_url.query.get('size', '100'))))
        channels = []
        for i, ch in enumerate(all_channels):
            if valid_only == '1' and ch.get('valid') is not True:
                continue
            if valid_only == '0' and ch.get('valid') is False:
                continue
            if group and ch.get('group', '') != group:
                continue
            if search and search not in ch.get('name', '').lower() and search not in ch.get('group', '').lower():
                continue
            if source_filter == 'local' and ch.get('source', ''):
                continue
            if source_filter == 'sub' and not ch.get('source', ''):
                continue
            channels.append({**ch, '_index': i})
        total_filtered = len(channels)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = channels[start:end]
        # 分组按 M3U 文件中的首次出现顺序（保持原序，去重），与 PC 端 _update_groups_for 逻辑一致
        groups = list(dict.fromkeys(ch.get('group', '') for ch in all_channels if ch.get('group')))
        return _json_success(
            channels=page_items,
            total=total_filtered,
            page=page,
            page_size=page_size,
            groups=groups
        )
    except Exception as e:
        logger.error(f"频道列表加载异常: {e}", exc_info=True)
        logger.exception(f'加载失败:')
        return _json_error(f'加载失败:', 500)


async def handle_channel_get(request):
    all_channels = _get_all_channels()
    if not all_channels:
        return _json_error('暂无频道数据', 503)
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的频道ID')
    if not (0 <= idx < len(all_channels)):
        return _json_error('频道不存在', 404)
    ch = all_channels[idx]
    return _json_success(channel={**ch, '_index': idx} if ch else None)


# 频道更新允许的字段白名单，防止注入内部字段
_CHANNEL_UPDATABLE_FIELDS = {
    'name', 'url', 'logo', 'group', '_groups', 'tvg_id', 'tvg_name',
    'tvg_chno', 'tvg_shift', 'catchup', 'catchup_days', 'catchup_source',
    'catchup_correction', 'fcc', 'resolution', 'status', 'valid',
}


def _filter_channel_fields(data: dict) -> dict:
    """过滤频道字段，仅保留白名单中的字段"""
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in _CHANNEL_UPDATABLE_FIELDS}


async def handle_channel_update(request):
    ctx = get_context()
    model = get_channel_model() if ctx else None
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的频道ID')
    data = await request.json()
    # 字段白名单过滤，防止注入 id/source/_raw_extinf 等内部字段
    data = _filter_channel_fields(data)
    if not data:
        return _json_error('没有可更新的字段')
    if model and 0 <= idx < model.rowCount():
        _call_model_on_qt_thread(model, model.update_channel, idx, data)
    elif ctx and hasattr(ctx, '_channels') and 0 <= idx < len(ctx._channels):
        # standalone 模式（Android）：调用带锁方法
        ctx.update_channel(idx, data)
    else:
        mw = get_main_window()
        if mw:
            sub_len = len(getattr(mw, '_sub_channels', []))
            if idx < sub_len:
                mw._sub_channels[idx].update(data)
            else:
                local_idx = idx - sub_len
                local_list = getattr(mw, '_local_channels', [])
                if 0 <= local_idx < len(local_list):
                    local_list[local_idx].update(data)
    return _json_success()


async def handle_channel_delete(request):
    ctx = get_context()
    model = get_channel_model() if ctx else None
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的频道ID')
    if model and 0 <= idx < model.rowCount():
        _call_model_on_qt_thread(model, model.remove_channel, idx)
    elif ctx and hasattr(ctx, '_channels') and 0 <= idx < len(ctx._channels):
        # standalone 模式（Android）：调用带锁方法
        ctx.delete_channel(idx)
    return _json_success()


async def handle_channel_add(request):
    data = await request.json()
    if not data.get('url'):
        return _json_error('URL不能为空')
    data.setdefault('name', data['url'].split('/')[-1])
    data.setdefault('group', '未分类')
    data.setdefault('valid', None)
    data.setdefault('source', '')  # 空源 = 手动添加/本地频道
    # 补全所有字段（与 android_bridge.py add_channel 对齐，
    # 确保 Kotlin IptvChannel 反序列化时字段完整一致）
    data.setdefault('logo', '')
    data.setdefault('tvg_id', '')
    data.setdefault('tvg_name', '')
    data.setdefault('tvg_chno', '')
    data.setdefault('tvg_shift', '')
    data.setdefault('catchup', '')
    data.setdefault('catchup_days', '')
    data.setdefault('catchup_source', '')
    data.setdefault('catchup_correction', '')
    data.setdefault('fcc', '')
    data.setdefault('resolution', '')
    data.setdefault('status', '待检测')
    ctx = get_context()
    model = get_channel_model() if ctx else None
    if model:
        _call_model_on_qt_thread(model, model.add_channel, data)
    elif ctx and hasattr(ctx, '_channels'):
        # standalone 模式（Android）：调用带锁方法
        ctx.add_channel(data)
    return _json_success()


async def handle_channels_import(request):
    try:
        data = await request.json()
    except (ValueError, TypeError):
        return _json_error('无效的请求数据', 400)
    content = data.get('content', '')
    if not content:
        return _json_error('内容为空', 400)
    try:
        from services.m3u_parser import parse_m3u_content
        channels, _ = parse_m3u_content(content)
        # 标记为手动导入（source=''），在 Android 端 LOCAL tab 显示
        # 同时补全 id 字段（与 android_bridge.py import_channels 对齐）
        ctx = get_context()
        if not ctx or not hasattr(ctx, '_channels'):
            return _json_error('上下文未初始化', 503)
        base_id = len(ctx._channels)
        for i, c in enumerate(channels):
            c['source'] = ''
            c.setdefault('id', base_id + i + 1)
        with getattr(ctx, '_channels_lock', _noop_lock):
            ctx._channels.extend(channels)
        # 持久化到缓存，重启后不丢失（写盘为阻塞操作，放到线程池避免卡住事件循环）
        await asyncio.to_thread(ctx._save_channels_to_cache)
        all_groups = list(dict.fromkeys([c.get('group', '未分组') for c in ctx._channels]))
        ctx._channels_list = all_groups if hasattr(ctx, '_channels_list') else None
        return _json_success(imported=len(channels))
    except Exception as e:
        logger.exception(f'解析失败:')
        return _json_error(f'解析失败:', 500)


async def handle_channels_batch(request):
    """批量编辑频道

    body: {action, ...options}
    action 取值：
      - auto_classify: {overwrite: bool} 按省份/规则自动分组
      - clean_names: {rules: {remove_hd, remove_brackets, ...}} 清理频道名
      - match_logo: {overwrite: bool} 匹配台标
      - assign_fields: {action_key, only_empty} 字段赋值
      - clear_params: {fields: [tvg_id, logo, ...]} 清除参数
      - sort_by_group: 按分组排序
    """
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)
    data = await request.json()
    action = data.get('action', '')
    channels = _get_all_channels()
    if not channels:
        return _json_error('暂无频道数据')

    model = get_channel_model() if ctx else None

    async def _persist():
        """持久化修改到模型或缓存"""
        if model:
            # Qt 模型信号必须在主线程发射（本协程运行在事件循环线程）
            try:
                from utils.thread_safety import invoke_on_thread
                invoke_on_thread(
                    model,
                    lambda: (model.layoutAboutToBeChanged.emit(),
                             model.layoutChanged.emit())
                )
            except Exception as e:
                logger.warning(f'刷新频道模型失败: {e}')
        if ctx and hasattr(ctx, '_channels'):
            # 写盘为阻塞操作，放到线程池避免卡住事件循环；内部已有锁保护
            await asyncio.to_thread(ctx._save_channels_to_cache)

    if action == 'auto_classify':
        try:
            from services.channel_classifier import ChannelClassifier
        except ImportError:
            return _json_error('分类模块不可用')
        overwrite = bool(data.get('overwrite', False))
        classifier = ChannelClassifier()
        results = classifier.classify_all(
            [{**ch, '_index': i} for i, ch in enumerate(channels)],
            overwrite=overwrite,
        )
        changed = 0
        for r in results:
            if r['changed']:
                idx = r['index']
                if 0 <= idx < len(channels):
                    channels[idx]['group'] = r['new_group']
                    channels[idx]['_groups'] = [r['new_group']]
                    changed += 1
        await _persist()
        return _json_success(changed=changed, total=len(channels))

    elif action == 'clean_names':
        try:
            from services.channel_cleaner import ChannelCleaner
        except ImportError:
            return _json_error('清理模块不可用')
        rules = data.get('rules', {})
        cleaner = ChannelCleaner()
        changed = 0
        for i, ch in enumerate(channels):
            old_name = ch.get('name', '')
            new_name = cleaner.clean(old_name, rules)
            if new_name != old_name and new_name:
                channels[i]['name'] = new_name
                changed += 1
        await _persist()
        return _json_success(changed=changed, total=len(channels))

    elif action == 'match_logo':
        try:
            from services.logo_matcher import LogoMatcher
        except ImportError:
            return _json_error('台标匹配模块不可用')
        overwrite = bool(data.get('overwrite', False))
        matcher = LogoMatcher()
        matched = 0
        for i, ch in enumerate(channels):
            if not overwrite and ch.get('logo'):
                continue
            logo = matcher.match(ch.get('name', ''))
            if logo:
                channels[i]['logo'] = logo
                matched += 1
        await _persist()
        return _json_success(matched=matched, total=len(channels))

    elif action == 'assign_fields':
        action_key = data.get('action_key', 'name2tvg_id')
        only_empty = bool(data.get('only_empty', True))
        changed = 0
        for i, ch in enumerate(channels):
            if action_key == 'name2tvg_id':
                if not (only_empty and ch.get('tvg_id')):
                    ch['tvg_id'] = ch.get('name', '')
                    changed += 1
            elif action_key == 'tvg_id2name':
                if ch.get('tvg_id') and not (only_empty and ch.get('name')):
                    ch['name'] = ch.get('tvg_id', '')
                    changed += 1
            elif action_key == 'tvg_name2name':
                tvg_name = ch.get('tvg_name', '')
                if tvg_name and not (only_empty and ch.get('name')):
                    ch['name'] = tvg_name
                    changed += 1
            elif action_key == 'tvg_id2tvg_chno':
                if ch.get('tvg_id') and not (only_empty and ch.get('tvg_chno')):
                    ch['tvg_chno'] = ch.get('tvg_id', '')
                    changed += 1
        await _persist()
        return _json_success(changed=changed, total=len(channels))

    elif action == 'clear_params':
        fields = data.get('fields', [])
        if not fields:
            return _json_error('未选择要清除的字段')
        changed = 0
        for i, ch in enumerate(channels):
            modified = False
            for field in fields:
                if field in ch and ch[field]:
                    ch[field] = ''
                    modified = True
            if modified:
                changed += 1
        await _persist()
        return _json_success(changed=changed, total=len(channels))

    elif action == 'sort_by_group':
        try:
            from services.channel_classifier import ChannelClassifier
            classifier = ChannelClassifier()
            category_order = classifier.get_category_order()
        except ImportError:
            category_order = []

        category_index = {cat: i for i, cat in enumerate(category_order)}

        def _sort_key(ch):
            group = ch.get('group', '')
            if category_index:
                cat_idx = category_index.get(group, 99)
            else:
                cat_idx = 0
            return (cat_idx, ch.get('name', ''))

        sorted_channels = sorted(channels, key=_sort_key)
        # 原地替换列表内容
        channels[:] = sorted_channels
        await _persist()
        return _json_success(total=len(channels))

    else:
        return _json_error(f'未知的批量操作: {action}')


async def handle_sources_list(request):
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    try:
        sources = config.load_playlist_sources()
    except (OSError, ValueError, RuntimeError):
        sources = []
    return _json_success(sources=sources)


async def handle_sources_add(request):
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    data = await request.json()
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()
    if not url:
        return _json_error('URL不能为空')
    try:
        sources = config.load_playlist_sources()
    except (OSError, ValueError, RuntimeError):
        sources = []
    sources.append({'url': url, 'name': name or url, 'enabled': True, 'last_update': None})
    config.save_playlist_sources(sources)
    # 添加订阅源后自动触发重载（与 EPG 源行为一致），
    # 确保 Android APP 端打开面板时能看到新加载的频道。
    # standalone 模式下 ctx.reload_sources('') 会加载所有已配置源。
    ctx = get_context()
    if ctx and ctx.is_standalone():
        ctx.reload_sources('')  # url 为空 → 加载所有源
    return _json_success()


async def handle_sources_update(request):
    """更新订阅源字段（如 enabled / name / url）。
    支持多选启用/禁用：每个源可独立切换 enabled 状态。
    """
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的源ID')
    data = await request.json()
    try:
        sources = config.load_playlist_sources()
    except (OSError, ValueError, RuntimeError):
        sources = []
    if not (0 <= idx < len(sources)):
        return _json_error('源不存在', 404)
    # 仅允许更新白名单字段，避免注入意外字段
    for key in ('enabled', 'name', 'url'):
        if key in data:
            sources[idx][key] = data[key]
    config.save_playlist_sources(sources)
    # 禁用/启用源后触发重新加载，确保频道列表与源状态同步
    if 'enabled' in data:
        ctx = get_context()
        if ctx and ctx.is_standalone():
            ctx.reload_sources('')  # url 为空 → 加载所有启用的源
    return _json_success()


async def handle_sources_delete(request):
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的源ID')
    try:
        sources = config.load_playlist_sources()
    except (OSError, ValueError, RuntimeError):
        sources = []
    if not (0 <= idx < len(sources)):
        return _json_error('源不存在', 404)
    sources.pop(idx)
    config.save_playlist_sources(sources)
    # 删除源后触发重新加载，移除该源的频道
    ctx = get_context()
    if ctx and ctx.is_standalone():
        ctx.reload_sources('')  # url 为空 → 加载所有启用的源
    return _json_success()


async def handle_epg_sources_list(request):
    """列出 EPG 订阅源"""
    config = get_config()
    if not config or not hasattr(config, 'load_epg_sources'):
        return _json_success(sources=[])
    try:
        sources = config.load_epg_sources()
    except Exception as e:
        logger.warning(f"加载EPG源失败: {e}")
        sources = []
    return _json_success(sources=sources)


async def handle_epg_sources_add(request):
    """添加 EPG 订阅源"""
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    if not hasattr(config, 'save_epg_sources'):
        return _json_error('当前环境不支持 EPG 订阅源管理', 503)
    data = await request.json()
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()
    if not url:
        return _json_error('URL不能为空')
    try:
        sources = config.load_epg_sources() if hasattr(config, 'load_epg_sources') else []
    except (OSError, ValueError, RuntimeError):
        sources = []
    # 去重
    if any(s.get('url') == url for s in sources):
        return _json_error('该 EPG 源已存在', 409)
    sources.append({'url': url, 'name': name or url, 'last_update': None})
    config.save_epg_sources(sources)
    # 触发后台重新加载 EPG 数据
    ctx = get_context()
    if ctx and hasattr(ctx, 'reload_epg'):
        ctx.reload_epg()
    return _json_success()


async def handle_epg_sources_delete(request):
    """删除 EPG 订阅源"""
    config = get_config()
    if not config:
        return _json_error('配置未初始化', 503)
    if not hasattr(config, 'save_epg_sources'):
        return _json_error('当前环境不支持 EPG 订阅源管理', 503)
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的源ID')
    try:
        sources = config.load_epg_sources() if hasattr(config, 'load_epg_sources') else []
    except (OSError, ValueError, RuntimeError):
        sources = []
    if not (0 <= idx < len(sources)):
        return _json_error('源不存在', 404)
    sources.pop(idx)
    config.save_epg_sources(sources)
    return _json_success()


async def handle_epg_reload(request):
    """重新加载 EPG 数据（独立于添加 EPG 源）"""
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)
    if not hasattr(ctx, 'reload_epg'):
        return _json_error('当前环境不支持 EPG 重载', 503)
    if ctx.reload_epg():
        return _json_success(message='EPG 重新加载已开始')
    return _json_error('EPG 重新加载失败（可能未配置 EPG 源或非独立模式）', 503)


async def handle_sources_reload(request):
    """重新加载订阅源（独立于扫描整理功能）"""
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)
    data = {}
    try:
        data = await request.json()
    except (ValueError, TypeError):
        pass
    url = (data.get('url') or '').strip()
    if ctx.is_standalone():
        if not ctx.reload_sources(url):
            return _json_error('订阅源正在加载中', 409)
        return _json_success(message='订阅源加载已开始')
    # 桌面模式：调用主窗口的加载逻辑
    mw = ctx.get_main_window()
    if mw and hasattr(mw, 'reload_subscription'):
        import threading
        threading.Thread(target=mw.reload_subscription, args=(url,), daemon=True).start()
        return _json_success(message='订阅源加载已开始')
    return _json_error('不支持此操作', 503)


async def handle_sources_status(request):
    """获取订阅源加载状态"""
    ctx = get_context()
    if not ctx:
        return _json_success(loading=False, message='未初始化')
    if ctx.is_standalone():
        status = ctx.get_source_load_status()
        return _json_success(**status)
    return _json_success(loading=False, message='桌面模式')


async def handle_scan_start(request):
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)

    # 独立模式（Android/无 GUI）：使用 URL 范围扫描
    if ctx.is_standalone():
        scanner = ctx.get_standalone_scanner()
        if not scanner:
            return _json_error('扫描器未初始化', 503)
        data = {}
        try:
            data = await request.json()
        except (ValueError, TypeError):
            pass
        url = data.get('url', '').strip()
        if not url:
            return _json_error('请提供扫描URL', 400)
        if scanner.is_scanning():
            return _json_error('扫描已在进行中', 409)
        timeout = max(1, min(int(data.get('timeout', 10)), 60))
        threads = max(1, min(int(data.get('threads', 4)), 32))
        if scanner.start_range_scan(url, timeout, threads):
            return _json_success(message='URL 范围扫描已开始')
        return _json_error('启动扫描失败', 500)

    # 桌面模式：依赖 _scan_dialog
    mw = get_main_window()
    if not mw:
        return _json_error('主窗口未初始化', 503)
    scan_dialog = getattr(mw, '_scan_dialog', None)
    if not scan_dialog:
        return _json_error('扫描窗口未打开，请先打开扫描整理窗口', 400)
    if hasattr(scan_dialog, 'scanner') and scan_dialog.scanner and scan_dialog.scanner.is_scanning():
        return _json_error('扫描已在进行中', 409)
    data = {}
    try:
        data = await request.json()
    except (ValueError, TypeError):
        pass
    url = data.get('url', '').strip()
    if not url:
        return _json_error('需要提供扫描URL')
    from utils.thread_safety import invoke_on_thread

    def _trigger():
        try:
            scan_dialog.ip_range_input.setEditText(url)
            if hasattr(scan_dialog, '_on_scan_clicked'):
                scan_dialog._on_scan_clicked()
        except Exception as e:
            logger.error(f"触发扫描失败: {e}")
    invoke_on_thread(mw, _trigger)
    return _json_success(message='扫描已触发')


async def handle_scan_stop(request):
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)

    # 独立模式：停止 StandaloneScanner
    if ctx.is_standalone():
        scanner = ctx.get_standalone_scanner()
        if scanner:
            scanner.stop_scan()
            return _json_success(message='停止扫描已触发')
        return _json_error('扫描器未初始化', 503)

    # 桌面模式
    mw = get_main_window()
    if not mw:
        return _json_error('主窗口未初始化', 503)
    scan_dialog = getattr(mw, '_scan_dialog', None)
    if not scan_dialog:
        return _json_error('扫描窗口未打开', 400)
    from utils.thread_safety import invoke_on_thread

    def _trigger():
        try:
            if hasattr(scan_dialog, '_on_scan_clicked'):
                scan_dialog._on_scan_clicked()
        except Exception as e:
            logger.error(f"停止扫描失败: {e}")
    invoke_on_thread(mw, _trigger)
    return _json_success(message='停止扫描已触发')


async def handle_scan_status(request):
    ctx = get_context()
    if not ctx:
        return _json_success(scanning=False, validating=False, stats={})

    # 独立模式：返回 StandaloneScanner 状态
    if ctx.is_standalone():
        scanner = ctx.get_standalone_scanner()
        if not scanner:
            return _json_success(scanning=False, validating=False, stats={})
        status = scanner.get_status()
        return _json_success(
            scanning=status.get('running', False),
            validating=False,
            running=status.get('running', False),
            total=status.get('total', 0),
            valid=status.get('valid', 0),
            invalid=status.get('invalid', 0),
            scanned=status.get('scanned', 0),
            message=status.get('message', ''),
            stats={
                'total': status.get('total', 0),
                'valid': status.get('valid', 0),
                'invalid': status.get('invalid', 0),
                'scanned': status.get('scanned', 0),
            }
        )

    # 桌面模式
    mw = get_main_window()
    if not mw:
        return _json_error('主窗口未初始化', 503)
    scan_dialog = getattr(mw, '_scan_dialog', None)
    scanner = getattr(scan_dialog, 'scanner', None) if scan_dialog else None
    if not scanner:
        return _json_success(scanning=False, validating=False, stats={})
    stats = dict(scanner.stats) if hasattr(scanner, 'stats') else {}
    return _json_success(
        scanning=scanner.is_scanning() if hasattr(scanner, 'is_scanning') else False,
        validating=getattr(scanner, 'is_validating', False),
        stats=stats
    )


async def handle_scan_range(request):
    """URL 范围扫描（PC 端"扫描整理"功能）

    body: {url, timeout?, threads?, engine?, retry?, append?}
    url 支持 [1-255] / [1,5,10] / [1-10,20-30] 等方括号范围表达式
    命名变量同步：[1-255:n] 定义变量 n，{n} 引用（两处 n 同步变化）
    engine: 扫描引擎 ('requests'/'ffprobe'/'mpv')，standalone 模式下始终使用 requests
    retry: 是否启用智能重试
    append: 是否追加模式
    """
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)
    if not ctx.is_standalone():
        return _json_error('当前环境不支持 URL 范围扫描（仅独立模式可用）', 503)
    scanner = ctx.get_standalone_scanner()
    if not scanner:
        return _json_error('扫描器未初始化', 503)
    data = {}
    try:
        data = await request.json()
    except (ValueError, TypeError):
        pass
    base_url = (data.get('url') or '').strip()
    if not base_url:
        return _json_error('URL 不能为空')
    if scanner.is_scanning():
        return _json_error('扫描已在进行中', 409)
    timeout = int(data.get('timeout', 10) or 10)
    threads = int(data.get('threads', 4) or 4)
    timeout = max(1, min(timeout, 60))
    threads = max(1, min(threads, 64))
    engine = data.get('engine', 'requests') or 'requests'
    retry = bool(data.get('retry', False))
    append = bool(data.get('append', False))
    if scanner.start_range_scan(base_url, timeout, threads, engine, retry, append):
        return _json_success(message='URL 范围扫描已开始')
    return _json_error('启动扫描失败', 500)


async def handle_scan_results(request):
    """获取 URL 范围扫描结果列表"""
    ctx = get_context()
    if not ctx:
        return _json_success(results=[])
    if not ctx.is_standalone():
        return _json_success(results=[])
    scanner = ctx.get_standalone_scanner()
    if not scanner:
        return _json_success(results=[])
    return _json_success(results=scanner.get_results())


async def handle_scan_validate(request):
    """验证所有频道的 URL 可达性

    body: {timeout?, threads?}
    更新频道的 valid/status 字段并持久化。
    """
    ctx = get_context()
    if not ctx:
        return _json_error('上下文未初始化', 503)
    if not ctx.is_standalone():
        return _json_error('当前环境不支持频道验证（仅独立模式可用）', 503)
    scanner = ctx.get_standalone_scanner()
    if not scanner:
        return _json_error('扫描器未初始化', 503)
    if scanner.is_scanning():
        return _json_error('扫描/验证已在进行中', 409)
    data = {}
    try:
        data = await request.json()
    except (ValueError, TypeError):
        pass
    timeout = max(1, min(int(data.get('timeout', 10) or 10), 60))
    threads = max(1, min(int(data.get('threads', 4) or 4), 32))
    if scanner.start_validate(timeout, threads):
        return _json_success(message='频道验证已开始')
    return _json_error('启动验证失败', 500)


def _get_mapping_manager():
    """获取频道映射管理器（全局单例，不依赖 PySide6）"""
    try:
        from models.channel_mappings import mapping_manager
        return mapping_manager
    except Exception as e:
        logger.warning(f"映射管理器不可用: {e}")
        return None


async def handle_mappings_list(request):
    """列出所有映射条目"""
    mm = _get_mapping_manager()
    if not mm:
        return _json_error('映射管理器不可用', 503)
    try:
        entries = mm.get_mapping_entries()
        remote_url = ''
        config = get_config()
        if config:
            try:
                remote_url = config.get_value('channel_mappings', 'remote_url', '')
            except (ValueError, RuntimeError):
                pass
        return _json_success(entries=entries, remote_url=remote_url)
    except Exception as e:
        logger.exception(f'获取映射失败:')
        return _json_error(f'获取映射失败:', 500)


async def handle_mappings_add(request):
    """添加用户映射 body: {raw_name, standard_name, logo_url?, group_name?}"""
    mm = _get_mapping_manager()
    if not mm:
        return _json_error('映射管理器不可用', 503)
    data = {}
    try:
        data = await request.json()
    except (ValueError, TypeError):
        pass
    raw_name = (data.get('raw_name') or '').strip()
    standard_name = (data.get('standard_name') or '').strip()
    if not raw_name or not standard_name:
        return _json_error('原始名称和标准名称不能为空')
    logo_url = (data.get('logo_url') or '').strip()
    group_name = (data.get('group_name') or '').strip()
    try:
        mm.add_user_mapping(raw_name, standard_name, logo_url, group_name)
        return _json_success(message='映射已添加')
    except Exception as e:
        logger.exception(f'添加映射失败:')
        return _json_error(f'添加映射失败:', 500)


async def handle_mappings_delete(request):
    """删除映射 {id} 格式: standard_name 或 standard_name||raw_name"""
    mm = _get_mapping_manager()
    if not mm:
        return _json_error('映射管理器不可用', 503)
    key = request.match_info['id']
    try:
        if '||' in key:
            standard_name, raw_name = key.split('||', 1)
            mm.remove_user_mapping_entry(standard_name, raw_name)
        else:
            mm.remove_user_mapping(key)
        return _json_success(message='映射已删除')
    except Exception as e:
        logger.exception(f'删除映射失败:')
        return _json_error(f'删除映射失败:', 500)


async def handle_mappings_refresh(request):
    """刷新远程映射缓存"""
    mm = _get_mapping_manager()
    if not mm:
        return _json_error('映射管理器不可用', 503)
    try:
        # 在后台线程中刷新，避免阻塞
        import threading

        def _do_refresh():
            try:
                mm.refresh_cache()
            except Exception as e:
                logger.error(f"刷新远程映射失败: {e}")
        threading.Thread(target=_do_refresh, daemon=True).start()
        return _json_success(message='正在刷新远程映射...')
    except Exception as e:
        logger.exception(f'刷新失败:')
        return _json_error(f'刷新失败:', 500)


async def handle_epg(request):
    ctx = get_context()
    epg_parser = ctx.get_epg_parser() if ctx else None
    if not epg_parser:
        return _json_error('EPG解析器未初始化', 503)
    search = request.rel_url.query.get('search', '').strip().lower()
    channel_id = request.rel_url.query.get('id', '').strip()
    # 额外的频道标识参数（与 PC 端 get_channel_epg 的多参数匹配对齐）
    tvg_id = request.rel_url.query.get('tvg_id', '').strip()
    tvg_name = request.rel_url.query.get('tvg_name', '').strip()
    channel_name = request.rel_url.query.get('name', '').strip()
    comma_name = request.rel_url.query.get('comma_name', '').strip()
    try:
        # SubscriptionManager 接口（standalone 模式）
        if hasattr(epg_parser, 'get_channel_epg'):
            if channel_id:
                # 优先使用多参数匹配（与 PC 端 EPG 匹配逻辑一致）
                # 匹配优先级：tvg_name > tvg_id > comma_name > channel_name > EpgMatcher 模糊匹配
                programmes = epg_parser.get_channel_epg(
                    channel_name or channel_id,
                    tvg_id=tvg_id or (channel_id if not channel_name else None),
                    tvg_name=tvg_name or None,
                    comma_name=comma_name or None,
                ) or []
                # 给每个节目添加 Unix 时间戳字段（前端用此判断当前节目）
                for p in programmes:
                    if 'start_ts' not in p:
                        try:
                            start_str = p.get('start', '')
                            stop_str = p.get('stop', p.get('end', ''))
                            if start_str:
                                dt = _parse_xmltv_time(start_str)
                                if dt:
                                    p['start_ts'] = int(dt.timestamp())
                            if stop_str:
                                dt = _parse_xmltv_time(stop_str)
                                if dt:
                                    p['stop_ts'] = int(dt.timestamp())
                        except (ValueError, TypeError):
                            pass
                return _json_success(programmes=programmes)
            if hasattr(epg_parser, 'get_epg_data_copy'):
                data = epg_parser.get_epg_data_copy() or {}
                # 优先显示 EPG 源里的中文台名，取不到时回退到频道 id
                channel_names = {}
                if hasattr(epg_parser, 'get_epg_channel_names'):
                    try:
                        channel_names = epg_parser.get_epg_channel_names() or {}
                    except Exception as e:
                        logger.debug(f'获取 EPG 频道名失败: {e}')
                channels = [
                    {'id': k, 'name': channel_names.get(k, k), 'programmes': len(v)}
                    for k, v in data.items()
                ]
                if search:
                    channels = [
                        ch for ch in channels
                        if search in ch.get('name', '').lower()
                        or search in ch.get('id', '').lower()
                    ]
                return _json_success(channels=channels)
        # 桌面端 EPG parser 接口
        if hasattr(epg_parser, 'get_programmes_for_channel'):
            if channel_id:
                programmes = epg_parser.get_programmes_for_channel(channel_id)
                for p in programmes:
                    if 'start_ts' not in p:
                        try:
                            start_str = p.get('start', '')
                            stop_str = p.get('stop', p.get('end', ''))
                            if start_str:
                                dt = _parse_xmltv_time(start_str)
                                if dt:
                                    p['start_ts'] = int(dt.timestamp())
                            if stop_str:
                                dt = _parse_xmltv_time(stop_str)
                                if dt:
                                    p['stop_ts'] = int(dt.timestamp())
                        except (ValueError, TypeError):
                            pass
                return _json_success(programmes=programmes)
        if hasattr(epg_parser, 'get_all_channels'):
            channels = epg_parser.get_all_channels()
            if search:
                channels = [
                    ch for ch in channels
                    if search in ch.get('name', '').lower()
                    or search in ch.get('id', '').lower()
                ]
            return _json_success(channels=channels)
    except Exception as e:
        logger.error(f"获取EPG失败: {e}")
    return _json_success(channels=[])


async def handle_stream_proxy(request):
    all_channels = _get_all_channels()
    if not all_channels:
        return _json_error('暂无频道数据', 503)
    try:
        idx = int(request.match_info['id'])
    except ValueError:
        return _json_error('无效的频道ID')
    if not (0 <= idx < len(all_channels)):
        return _json_error('频道不存在', 404)
    ch = all_channels[idx]
    if not ch or not ch.get('url'):
        return _json_error('频道URL为空', 404)
    stream_url = ch['url']
    # SSRF 防护：使用统一的 URL 安全检查
    # 域名解析是阻塞调用，放到线程池避免阻塞事件循环
    is_safe, reject_reason = await asyncio.to_thread(_is_safe_stream_url, stream_url)
    if not is_safe:
        logger.warning(f'Stream proxy blocked: {redact_url(stream_url)} - {reject_reason}')
        return _json_error(f'不允许的流地址: {reject_reason}', 403)
    # aiohttp 只能转发 HTTP(S)；rtsp/rtmp/rtp/udp/srt 应交给播放器直连
    scheme = (urlparse(stream_url).scheme or '').lower()
    if scheme not in _PROXYABLE_STREAM_PROTOCOLS:
        return _json_error(f'该协议不支持 HTTP 流代理: {scheme}', 400)
    session = await _get_stream_session()
    try:
        async with session.get(stream_url) as resp:
            if resp.status >= 400:
                logger.warning(
                    f'流代理上游返回 {resp.status}: {redact_url(stream_url)}')
                return _json_error(f'上游返回错误状态: {resp.status}', 502)
            content_type = resp.headers.get('Content-Type', 'video/mp2t')
            response = web.StreamResponse(
                status=resp.status,
                headers={'Content-Type': content_type}
            )
            await response.prepare(request)
            async for chunk in resp.content.iter_chunked(8192):
                await response.write(chunk)
            await response.write_eof()
            return response
    except asyncio.CancelledError:
        raise
    except ConnectionResetError:
        # 客户端断开连接，正常终止
        return web.Response(status=499)
    except Exception as e:
        logger.error(f"流代理失败: {redact_url(stream_url)} - {e}")
        logger.exception(f'流代理失败:')
        return _json_error(f'流代理失败:', 502)


# ===================== 播放器远程控制 =====================

def _get_player():
    """获取主窗口的 player_controller"""
    mw = get_main_window()
    if mw and hasattr(mw, 'player_controller'):
        return mw.player_controller
    return None


def _get_cache_dir(sub: str) -> str:
    """获取缓存子目录绝对路径，不存在则创建"""
    from utils.app_paths import get_cache_dir
    base = os.path.join(get_cache_dir(), sub)
    os.makedirs(base, exist_ok=True)
    return base


async def handle_player_chapters(request):
    """读取当前播放文件的章节列表"""
    pc = _get_player()
    if not pc:
        return _json_error('播放器未初始化', 503)
    try:
        chapters = pc.get_chapter_list()
        return _json_success(data=chapters)
    except Exception as e:
        logger.error(f"获取章节列表失败: {e}")
        logger.exception(f'获取章节失败:')
        return _json_error(f'获取章节失败:', 500)


async def handle_player_hdr(request):
    """切换 HDR 输出模式（需要重新初始化 mpv）"""
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    mode = (body or {}).get('mode', '').strip().lower()
    valid_modes = {'disable', 'tonemap', 'passthrough', 'scrgb', 'auto'}
    if mode not in valid_modes:
        return _json_error(f'无效的 HDR 模式: {mode}，支持: {", ".join(sorted(valid_modes))}')
    pc = _get_player()
    if not pc:
        return _json_error('播放器未初始化', 503)
    try:
        # reinit_for_hdr_change 是阻塞操作（涉及 mpv 重新初始化）
        # 放到线程池执行，避免阻塞 event loop
        await asyncio.to_thread(pc.reinit_for_hdr_change, mode)
        return _json_success(mode=mode)
    except Exception as e:
        logger.error(f"切换 HDR 模式失败: {e}")
        logger.exception(f'切换 HDR 失败:')
        return _json_error(f'切换 HDR 失败:', 500)


async def handle_player_screenshot(request):
    """截图保存到缓存目录，返回路径"""
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    mode = (body or {}).get('mode', 'video').strip().lower()
    # mpv screenshot-to-file 支持: video / subtitles / window / each-frame
    if mode not in ('video', 'subtitles', 'window', 'each-frame'):
        mode = 'video'
    pc = _get_player()
    if not pc or not pc.is_playing:
        return _json_error('当前无播放内容', 400)
    try:
        import time as _t
        cache_dir = _get_cache_dir('screenshots')
        fname = f"shot_{int(_t.time())}.png"
        fpath = os.path.join(cache_dir, fname)
        # 在线程池执行截图（send_command 是带锁的同步调用）
        ret = await asyncio.to_thread(pc.send_command, ['screenshot-to-file', fpath, mode])
        if ret != 0 and not os.path.exists(fpath):
            return _json_error('截图失败（mpv 返回错误）', 500)
        return _json_success(path=fpath)
    except Exception as e:
        logger.error(f"截图失败: {e}")
        logger.exception(f'截图失败:')
        return _json_error(f'截图失败:', 500)


# ===================== 字幕在线下载 =====================

_subtitle_service_lock = asyncio.Lock()


async def handle_subtitle_search(request):
    """通过 OpenSubtitles 搜索字幕

    Query 参数：
      q: 关键词（片名，可中英文）
      lang: 语言代码（eng/chi/all），默认 all
      imdb: IMDb ID（可选）
      file_path: 视频文件路径（可选，用于哈希精准匹配）
    """
    q = request.rel_url.query.get('q', '').strip()
    lang = request.rel_url.query.get('lang', 'all').strip().lower() or 'all'
    imdb = request.rel_url.query.get('imdb', '').strip()
    file_path = request.rel_url.query.get('file_path', '').strip()
    # URL 解码处理（前端可能传 file:// 路径）
    if file_path:
        from urllib.parse import unquote
        file_path = unquote(file_path)
    if not q and not file_path and not imdb:
        return _json_error('请提供搜索关键词或文件路径')
    try:
        from services.subtitle_download_service import SubtitleDownloadService
        # 复用单例（保持登录 token）
        svc = getattr(handle_subtitle_search, '_svc', None)
        if svc is None:
            svc = SubtitleDownloadService()
            handle_subtitle_search._svc = svc
        # OpenSubtitles 调用是阻塞的，放到线程池
        async with _subtitle_service_lock:
            items = await asyncio.to_thread(svc.search, q, imdb, lang, file_path)
        if not items:
            err = getattr(svc, 'last_error', '') or '未找到字幕'
            return _json_success(data=[], message=err)
        # 转成前端期望的格式
        data = [{
            'filename': it.get('file_name', ''),
            'lang': it.get('language', ''),
            'size': it.get('size', 0),
            'url': it.get('download_link', ''),
            'rating': it.get('rating', 0),
            'movie_name': it.get('movie_name', ''),
        } for it in items]
        return _json_success(data=data)
    except Exception as e:
        logger.error(f"字幕搜索失败: {e}")
        logger.exception(f'字幕搜索失败:')
        return _json_error(f'字幕搜索失败:', 500)


async def handle_subtitle_download(request):
    """下载字幕文件到缓存目录，返回本地路径"""
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    url = (body or {}).get('url', '').strip()
    name = (body or {}).get('name', '').strip()
    if not url:
        return _json_error('URL 不能为空')
    # 接口层先做协议白名单校验，服务层还会再校验一次（防 file:// 本地文件读取）
    if not url.lower().startswith(('http://', 'https://')):
        return _json_error('仅支持 http/https 字幕下载链接', 400)
    try:
        from services.subtitle_download_service import SubtitleDownloadService
        svc = getattr(handle_subtitle_search, '_svc', None) or SubtitleDownloadService()
        handle_subtitle_search._svc = svc
        cache_dir = _get_cache_dir('subtitles')
        # 下载是阻塞的，放到线程池
        path = await asyncio.to_thread(svc.download, url, cache_dir, name)
        if not path:
            err = getattr(svc, 'last_error', '') or '下载失败'
            return _json_error(err)
        return _json_success(path=path)
    except Exception as e:
        logger.error(f"字幕下载失败: {e}")
        logger.exception(f'字幕下载失败:')
        return _json_error(f'字幕下载失败:', 500)


# ===================== 文件分享与缓存清理 =====================

async def handle_share_file(request):
    """分享文件

    PC 端：使用系统默认程序打开文件所在目录
    Android：通过 share intent 分享（由原生层处理，这里仅返回成功）
    """
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    path = (body or {}).get('path', '').strip()
    if not path or not os.path.exists(path):
        return _json_error('文件不存在', 404)
    # 安全：防止路径穿越——确保路径在允许的目录内
    # 允许的根目录：IPTV_DATA_DIR / cache 目录 / 应用文件目录
    allowed_roots = []
    android_data = get_android_data_dir()
    if android_data:
        allowed_roots.append(os.path.realpath(android_data))
    # 新旧缓存目录都允许：迁移前截图的文件仍可能位于程序目录 cache 下
    from utils.app_paths import get_cache_dir
    allowed_roots.append(os.path.realpath(get_cache_dir()))
    _legacy_cache_base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache')
    allowed_roots.append(os.path.realpath(_legacy_cache_base))
    real_path = os.path.realpath(path)
    if not any(real_path.startswith(root + os.sep) or real_path == root for root in allowed_roots):
        return _json_error('文件路径不在允许范围内', 403)
    try:
        import sys
        if sys.platform == 'win32':
            # Windows: 在资源管理器中选中文件
            import subprocess
            subprocess.Popen(['explorer', '/select,', path])
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', '-R', path])
        elif is_android():
            return _json_error('Android 平台不支持在文件管理器中打开', 400)
        else:
            # Linux: 打开所在目录
            import subprocess
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
        return _json_success()
    except Exception as e:
        logger.error(f"分享文件失败: {e}")
        logger.exception(f'分享失败:')
        return _json_error(f'分享失败:', 500)


async def handle_cache_clear(request):
    """清空缓存目录

    Body: {type: 'thumbnails'/'screenshots'/'subtitles'/'all'}
    """
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    cache_type = (body or {}).get('type', 'all').strip().lower()
    valid_types = {'thumbnails', 'screenshots', 'subtitles', 'all'}
    if cache_type not in valid_types:
        return _json_error(f'无效的缓存类型: {cache_type}')
    try:
        from utils.app_paths import get_cache_dir
        cache_root = get_cache_dir()
        targets = [cache_type] if cache_type != 'all' else ['thumbnails', 'screenshots', 'subtitles']
        cleared = []
        for sub in targets:
            sub_dir = os.path.join(cache_root, sub)
            if not os.path.isdir(sub_dir):
                continue
            # 删除目录下所有文件（保留目录本身）
            for fname in os.listdir(sub_dir):
                fpath = os.path.join(sub_dir, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                    elif os.path.isdir(fpath):
                        import shutil
                        shutil.rmtree(fpath, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"删除 {fpath} 失败: {e}")
            cleared.append(sub)
        return _json_success(cleared=cleared)
    except Exception as e:
        logger.error(f"清空缓存失败: {e}")
        logger.exception(f'清空缓存失败:')
        return _json_error(f'清空缓存失败:', 500)


# ===================== 日志查看与下载 =====================

def _get_log_file_path():
    """获取当前日志文件路径（与 LogManager 单例保持一致）"""
    try:
        from core.log_manager import LogManager
        instance = LogManager()
        return instance.log_file
    except Exception:
        pass
    # fallback：与 LogManager 的候选路径保持一致（用户日志目录优先）
    from utils.app_paths import get_log_dir
    return os.path.join(get_log_dir(), 'app.log')


async def handle_log_view(request):
    """查看日志（尾部 N 行）

    Query params:
      - lines: 尾部行数（默认 200，最大 2000）
      - offset: 从文件末尾偏移的字节数（用于轮询增量）

    返回 JSON: { path, size, lines: [...], total_lines, truncated }
    """
    try:
        log_path = _get_log_file_path()
        if not os.path.isfile(log_path):
            return _json_error('日志文件不存在', 404)

        max_lines = min(int(request.query.get('lines', 200)), 2000)
        file_size = os.path.getsize(log_path)

        # 读取尾部内容（最多 1MB，避免大文件内存爆炸）
        read_bytes = min(file_size, 1024 * 1024)
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            if read_bytes < file_size:
                f.seek(file_size - read_bytes)
            content = f.read()

        all_lines = content.splitlines()
        # 如果 seek 了，第一行可能不完整，跳过
        if read_bytes < file_size and all_lines:
            all_lines = all_lines[1:]

        total_lines = len(all_lines)
        tail_lines = all_lines[-max_lines:] if total_lines > max_lines else all_lines

        return _json_success(
            path=log_path,
            size=file_size,
            lines=tail_lines,
            total_lines=total_lines,
            truncated=total_lines > max_lines
        )
    except Exception as e:
        logger.error(f"查看日志失败: {e}")
        logger.exception(f'查看日志失败:')
        return _json_error(f'查看日志失败:', 500)


async def handle_log_download(request):
    """下载完整日志文件"""
    try:
        log_path = _get_log_file_path()
        if not os.path.isfile(log_path):
            return _json_error('日志文件不存在', 404)

        file_size = os.path.getsize(log_path)

        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'app_{timestamp}.log'

        return web.FileResponse(
            log_path,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(file_size),
                'Cache-Control': 'no-cache',
            }
        )
    except Exception as e:
        logger.error(f"下载日志失败: {e}")
        logger.exception(f'下载日志失败:')
        return _json_error(f'下载日志失败:', 500)


async def handle_log_clear(request):
    """清空日志文件内容"""
    try:
        log_path = _get_log_file_path()
        if not os.path.isfile(log_path):
            return _json_error('日志文件不存在', 404)

        # 清空文件内容（截断为 0 字节）
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('')

        logger.info('日志文件已清空')
        return _json_success()
    except Exception as e:
        logger.error(f"清空日志失败: {e}")
        logger.exception(f'清空日志失败:')
        return _json_error(f'清空日志失败:', 500)
