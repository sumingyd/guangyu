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
    """每次取会话时同步代理与默认请求头，保证运行期修改配置即时生效"""
    proxies = getattr(session, '_isep_proxies', None)
    proxy_url = str(_read_config('Playback', 'http_proxy', '') or '').strip()
    desired = {'http': proxy_url, 'https': proxy_url} if proxy_url else {}
    if proxies != desired:
        session.proxies = desired
        session._isep_proxies = desired
    user_agent = _read_config('Network', 'user_agent', '')
    if user_agent:
        session.headers.setdefault('User-Agent', user_agent)
    referer = _read_config('Network', 'referer', '')
    if referer:
        session.headers.setdefault('Referer', referer)


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
        kwargs['timeout'] = DEFAULT_TIMEOUT
    elif isinstance(kwargs['timeout'], (int, float)):
        kwargs['timeout'] = float(kwargs['timeout'])


def get(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.get(url, **kwargs)


def head(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.head(url, **kwargs)


def post(url, **kwargs):
    session = get_session()
    if session is None:
        raise ImportError('requests is not available')
    _prepare_timeout(kwargs)
    return session.post(url, **kwargs)


def close():
    global _session
    if _session is not None:
        with _lock:
            if _session is not None:
                _session.close()
                _session = None
