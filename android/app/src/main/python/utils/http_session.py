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
_lock = threading.Lock()

DEFAULT_TIMEOUT = 30.0
# 仅对幂等请求做瞬时故障重试：4xx 不重试，5xx/限流做有限退避
_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


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
    proxies = getattr(session, '_isep_proxies', None)
    proxy_url = str(_read_config('Playback', 'http_proxy', '') or '').strip()
    desired = {'http': proxy_url, 'https': proxy_url} if proxy_url else {}
    if proxies != desired:
        session.proxies = desired
        session._isep_proxies = desired
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


def get_session():
    global _session
    if not _HAS_REQUESTS:
        return None
    if _session is None:
        with _lock:
            if _session is None:
                _session = requests.Session()
                adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=_build_retry())
                _session.mount('http://', adapter)
                _session.mount('https://', adapter)
    _apply_runtime_config(_session)
    return _session


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


def get(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.get(_rewrite_github(url), **kwargs)


def head(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.head(_rewrite_github(url), **kwargs)


def post(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.post(_rewrite_github(url), **kwargs)


def close():
    global _session
    if _session is not None:
        with _lock:
            if _session is not None:
                _session.close()
                _session = None
