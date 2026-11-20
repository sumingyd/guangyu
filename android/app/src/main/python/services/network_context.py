"""扫描 / 探测 / 播放共用的网络上下文。

统一从配置读取代理、User-Agent、Referer、自定义请求头、TLS 校验与超时，
避免各探测链路口径分裂：

- ffprobe 校验器原先不设代理；
- Referer 原先只在 ``Playback.http_headers`` 里找，扫描整理对话框填的
  Referer 存在 ``Network.referer``；
- mpv 校验器原先写死 ``tls-verify=no``。

播放侧（``services/mpv_playback.py``）读取的是同一组 ``Playback.*`` 键，
因此扫描与播放从此共用同一份来源。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# 探测分析时长（秒）：给足 10–15 秒，避免源站起播慢被误判
ANALYZE_TIMEOUT_MIN = 10
ANALYZE_TIMEOUT_MAX = 15

# ffprobe / mpv 探测量：10MB，足以跨过 HLS 播放列表与 TS 头
PROBESIZE_BYTES = 10 * 1024 * 1024

# 自定义请求头里由上下文单独管理的键，避免重复写入
_MANAGED_HEADERS = ('user-agent', 'referer')


def _parse_header_lines(raw: str) -> List[Tuple[str, str]]:
    """把多行请求头文本拆成 (name, value) 列表，跳过空行与非法行。"""
    result: List[Tuple[str, str]] = []
    text = (raw or '').replace('\r\n', '\n').replace('\r', '\n')
    for line in text.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        name, value = line.split(':', 1)
        name, value = name.strip(), value.strip()
        if name and value:
            result.append((name, value))
    return result


def _find_header(pairs: List[Tuple[str, str]], name: str) -> str:
    lower = name.lower()
    for key, value in pairs:
        if key.lower() == lower:
            return value
    return ''


@dataclass(frozen=True)
class NetworkContext:
    """一次探测使用的网络上下文（不可变，可安全跨线程传递）。"""

    user_agent: str = ''
    referer: str = ''
    proxy: str = ''
    tls_verify: bool = False
    connect_timeout: int = 10
    analyze_timeout: int = ANALYZE_TIMEOUT_MIN
    raw_headers: str = ''
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def request_headers(self) -> Dict[str, str]:
        """requests 使用的请求头（不含代理/TLS）。"""
        headers = dict(self.extra_headers)
        if self.user_agent:
            headers['User-Agent'] = self.user_agent
        if self.referer:
            headers['Referer'] = self.referer
        return headers

    def header_lines(self) -> List[str]:
        """ffprobe ``-headers`` 使用的 "Name: Value" 行（调用方用 CRLF 拼接）。"""
        lines = [f'{k}: {v}' for k, v in self.extra_headers.items()]
        if self.user_agent:
            lines.insert(0, f'User-Agent: {self.user_agent}')
        if self.referer:
            lines.append(f'Referer: {self.referer}')
        return lines

    def custom_headers_without_managed(self) -> List[Tuple[str, str]]:
        """仅自定义头（去掉 User-Agent / Referer），供 mpv 使用。"""
        return [(k, v) for k, v in self.extra_headers.items()
                if k.lower() not in _MANAGED_HEADERS]


def build_network_context(
    connect_timeout: int = 10,
    user_agent: str | None = None,
    referer: str | None = None,
) -> NetworkContext:
    """从配置构造网络上下文。

    Args:
        connect_timeout: 连接超时（秒），沿用调用方（扫描设置）的现有值。
        user_agent / referer: 调用方显式传入时优先，其次按配置回退。

    读取失败（无 PySide6 / 配置损坏）时返回安全默认值，不抛异常。
    """
    try:
        from core.config_manager import ConfigManager
        cfg = ConfigManager()
        playback = cfg.load_playback_settings() or {}
        network = cfg.load_network_settings() or {}
    except Exception:
        playback, network = {}, {}

    raw_headers = str(playback.get('http_headers', '') or '')
    header_pairs = _parse_header_lines(raw_headers)

    resolved_ua = (
        (user_agent or '').strip()
        or str(network.get('user_agent', '') or '').strip()
        or str(playback.get('user_agent', '') or '').strip()
    )
    resolved_referer = (
        (referer or '').strip()
        or str(playback.get('http_referer', '') or '').strip()
        or str(network.get('referer', '') or '').strip()
        or _find_header(header_pairs, 'Referer').strip()
    )

    try:
        timeout_int = int(connect_timeout)
    except (TypeError, ValueError):
        timeout_int = 10
    if timeout_int <= 0:
        timeout_int = 10
    analyze_int = max(ANALYZE_TIMEOUT_MIN, min(ANALYZE_TIMEOUT_MAX, timeout_int))

    extra: Dict[str, str] = {}
    for key, value in header_pairs:
        if key.lower() in _MANAGED_HEADERS:
            continue
        extra[key] = value

    return NetworkContext(
        user_agent=resolved_ua,
        referer=resolved_referer,
        proxy=str(playback.get('http_proxy', '') or '').strip(),
        tls_verify=bool(playback.get('tls_verify', False)),
        connect_timeout=timeout_int,
        analyze_timeout=analyze_int,
        raw_headers=raw_headers,
        extra_headers=extra,
    )
