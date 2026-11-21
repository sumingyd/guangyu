import re
import threading

try:
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
    except Exception:  # pragma: no cover - 兼容极老版本 urllib3
        Retry = None
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    requests = None
    HTTPAdapter = None
    Retry = None

_session = None
_probe_session = None
_lock = threading.Lock()

DEFAULT_TIMEOUT = 30.0
# 连接池与扫描线程上限（32）对齐，避免高并发下「Connection pool is full, discarding connection」
POOL_CONNECTIONS = 10
POOL_MAXSIZE = 32
# 仅对幂等请求做瞬时故障重试：4xx 不重试，5xx/限流做有限退避
_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

# 本地系统代理（Clash/V2Ray 等）进程退出后会残留监听端口，
# 表现是所有请求立刻 Connection refused。此时记住直连，避免订阅/EPG/台标全线超时。
_direct_mode = False
_LOCAL_PROXY_HOST_RE = re.compile(r'127\.0\.0\.1|\[::1\]|localhost', re.IGNORECASE)
_REFUSED_RE = re.compile(r'10061|errno\s*111|errno\s*61|connection refused|拒绝', re.IGNORECASE)


def _build_retry():
    if Retry is None:
        return 0
    return Retry(
        total=2,
        connect=2,
        read=0,
        status=2,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUS_CODES,
        allowed_methods=frozenset(['GET', 'HEAD']),
        raise_on_status=False,
    )


def _read_config(section, key, default=''):
    """懒加载读取配置，避免与 ConfigManager 形成导入环"""
    try:
        from core.config_manager import ConfigManager
        value = ConfigManager().get_value(section, key, default)
        return value if value not in (None, '') else default
    except Exception:
        return default


def _apply_runtime_config(session):
    """每次取会话时同步代理与默认请求头，保证运行期修改配置即时生效

    配置来源统一到「设置 → 网络 → 流媒体请求」：
    - 代理 / Referer / 自定义请求头：播放与订阅源/EPG 下载共用
    - User-Agent：下载优先用扫描整理里的值（Network.user_agent），
      为空时回落到网络页的 Playback.user_agent
    """
    global _direct_mode
    proxy_url = str(_read_config('Playback', 'http_proxy', '') or '').strip()
    # 代理配置变更新一轮探测：用户换了代理地址后重新允许走代理
    if proxy_url != getattr(session, '_isep_proxy_setting', None):
        session._isep_proxy_setting = proxy_url
        _direct_mode = False
    proxies = getattr(session, '_isep_proxies', None)
    if _direct_mode:
        desired = {}
    else:
        desired = {'http': proxy_url, 'https': proxy_url} if proxy_url else {}
    if proxies != desired:
        session.proxies = desired
        session._isep_proxies = desired
    # 直连模式同时绕开环境变量里的系统代理
    if session.trust_env == _direct_mode:
        session.trust_env = not _direct_mode
    user_agent = (_read_config('Network', 'user_agent', '')
                  or _read_config('Playback', 'user_agent', ''))
    if user_agent:
        session.headers['User-Agent'] = user_agent
    # 自定义请求头：整体替换，并在配置清空时移除上一次写入的键
    desired_headers = {}
    raw_headers = str(_read_config('Playback', 'http_headers', '') or '')
    for line in raw_headers.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key, value = key.strip(), value.strip()
        if key:
            desired_headers[key] = value
    applied_headers = getattr(session, '_isep_custom_headers', {}) or {}
    desired_lower = {k.lower() for k in desired_headers}
    for key in list(applied_headers):
        if key.lower() not in desired_lower:
            session.headers.pop(key, None)
    for key, value in desired_headers.items():
        session.headers[key] = value
    session._isep_custom_headers = desired_headers

    referer = str(_read_config('Playback', 'http_referer', '') or '').strip()
    if not referer:
        referer = str(_read_config('Network', 'referer', '') or '').strip()
    if 'referer' not in desired_lower:
        if referer:
            session.headers['Referer'] = referer
        elif getattr(session, '_isep_referer', ''):
            session.headers.pop('Referer', None)
    session._isep_referer = referer


def _build_session(max_retries):
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=POOL_CONNECTIONS,
        pool_maxsize=POOL_MAXSIZE,
        max_retries=max_retries,
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def get_session():
    global _session
    if not _HAS_REQUESTS:
        return None
    if _session is None:
        with _lock:
            if _session is None:
                _session = _build_session(_build_retry())
    _apply_runtime_config(_session)
    return _session


def get_probe_session():
    """探测专用会话：同样的连接池配置，但连接失败不重试。

    urllib3 的 connect 重试会把「连接超时 3s」放大成 3 次握手（约 10s），
    批量扫描需要真实的单次超时，因此探测请求单独走这个会话。
    """
    global _probe_session
    if not _HAS_REQUESTS:
        return None
    if _probe_session is None:
        with _lock:
            if _probe_session is None:
                _probe_session = _build_session(0)
    _apply_runtime_config(_probe_session)
    return _probe_session


def _prepare_timeout(kwargs):
    # 统一用标量超时：此环境实测 requests 会把 (connect, read) 元组按相反顺序解释，
    # 传 (10, 30) 实际读超时只有 10s，弱网下载订阅源必然超时。
    # 标量 t 保证读超时完整为调用方指定值（订阅源加载传 30s）。
    if 'timeout' not in kwargs:
        # 「设置 → 网络 → 网络超时」对下载同样生效；Auto(0) 时用统一默认值
        try:
            configured = float(_read_config('Playback', 'network_timeout_sec', 0) or 0)
        except (TypeError, ValueError):
            configured = 0
        kwargs['timeout'] = configured if configured > 0 else DEFAULT_TIMEOUT
    elif isinstance(kwargs['timeout'], (int, float)):
        kwargs['timeout'] = float(kwargs['timeout'])


def _rewrite_github(url):
    """GitHub 加速代理：只改写 GitHub 域名，其余地址保持原样。"""
    try:
        from .github_proxy import rewrite_url
        return rewrite_url(url)
    except Exception:
        return url


def _is_dead_local_proxy_error(exc) -> bool:
    """判断异常是否指向「本地代理端口拒绝连接」。"""
    if not _HAS_REQUESTS or not isinstance(exc, requests.exceptions.RequestException):
        return False
    text = str(exc)
    return bool(_LOCAL_PROXY_HOST_RE.search(text) and _REFUSED_RE.search(text))


def _send(method, url, retry: bool = True, **kwargs):
    global _direct_mode
    session = get_session() if retry else get_probe_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    target = _rewrite_github(url)
    try:
        return getattr(session, method)(target, **kwargs)
    except Exception as exc:
        if _direct_mode or not _is_dead_local_proxy_error(exc):
            raise
        # 本地代理已死：本次改直连重试一次，之后所有请求都保持直连
        _direct_mode = True
        session.proxies = {}
        session._isep_proxies = {}
        session.trust_env = False
        return getattr(session, method)(target, **kwargs)


def get(url, retry: bool = True, **kwargs):
    """retry=False 用于扫描探测：连接失败只试一次，不吃 urllib3 的连接重试。"""
    return _send('get', url, retry=retry, **kwargs)


def head(url, **kwargs):
    return _send('head', url, **kwargs)


def post(url, **kwargs):
    return _send('post', url, **kwargs)


def close():
    global _session, _probe_session
    with _lock:
        if _session is not None:
            _session.close()
            _session = None
        if _probe_session is not None:
            _probe_session.close()
            _probe_session = None
