"""
FCC (Fast Channel Change) 快速换台服务

IPTV 组播场景中，FCC 代理用于加速频道切换：
- 客户端换台时通过 UDP 向 FCC 代理发送 leave/join 通知
- FCC 代理在服务端侧完成 IGMP leave/join，快速转发新频道流
- 客户端无需等待 IGMP 加入延迟

支持的 URL 形态（fcc 参数大小写不敏感、位置任意）：
  rtp://239.1.1.1:5002?fcc=150.138.8.132:8027
  udp://239.2.1.5:5000?fcc=10.0.0.1:9000
  http://192.168.1.10:20231/rtp/239.1.1.1:5002?fcc=150.138.8.132:8027
  http://192.168.1.10:20231/udp/239.1.1.1:5002?token=x&FCC=150.138.8.132

FCC 通知协议（UDP 文本）：
  LEAVE <multicast_ip> <multicast_port>\n
  JOIN <multicast_ip> <multicast_port>\n

注意：FCC 实际加速效果依赖服务端（FCC 服务器 / rtp2httpd 等代理）是否
支持该协议，客户端只负责按约定发送 LEAVE/JOIN。
"""

import ipaddress
import re
import socket
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

from core.log_manager import global_logger as logger


DEFAULT_FCC_PORT = 8027

# 代理路径形态：/rtp/<ip>:<port> 或 /udp/<ip>:<port>
_MULTICAST_PATH_RE = re.compile(
    r'/(?:rtp|udp)/(?P<host>\[[0-9A-Fa-f:]+\]|[^/:]+):(?P<port>\d{1,5})',
    re.IGNORECASE,
)
_BRACKET_ENDPOINT_RE = re.compile(r'^\[([^\]]+)\](?::(\d{1,5}))?$')
_HOSTNAME_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$')


@dataclass(frozen=True)
class FccResolution:
    """FCC 解析结果。

    is_fcc:     URL 中是否存在 fcc 参数（即使地址非法也为 True）
    endpoint:   FCC 代理地址 (ip, port)，解析失败为 None
    multicast:  组播源地址 (ip, port)，无法确定时为 None
    error:      仅在 is_fcc=True 时有意义，描述地址解析失败原因
    """

    is_fcc: bool
    endpoint: Optional[Tuple[str, int]] = None
    multicast: Optional[Tuple[str, int]] = None
    error: Optional[str] = None


# 解析失败日志去重：同一 URL + 原因只告警一次，避免大播放列表刷屏
_logged_errors: Set[str] = set()
_logged_errors_lock = threading.Lock()


def _log_parse_error_once(url: str, message: str) -> None:
    key = f'{url}|{message}'
    with _logged_errors_lock:
        already = key in _logged_errors
        if not already:
            if len(_logged_errors) > 512:
                _logged_errors.clear()
            _logged_errors.add(key)
    if already:
        logger.debug(f"FCC 解析失败(已告警): {message}, url={url}")
    else:
        logger.warning(f"FCC 解析失败: {message}, url={url}")


def _strip_brackets(host: str) -> str:
    host = (host or '').strip()
    if host.startswith('[') and host.endswith(']'):
        return host[1:-1]
    return host


def _is_valid_host(host: str) -> bool:
    """IP 或合法主机名（FCC 端点允许填域名，由系统解析）。"""
    host = _strip_brackets(host)
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(_HOSTNAME_RE.match(host))


def _parse_fcc_endpoint(value: str) -> Tuple[Optional[Tuple[str, int]], Optional[str]]:
    """解析 fcc 参数值，返回 ((ip, port), error)。"""
    raw = (value or '').strip()
    if not raw:
        return None, 'fcc 参数为空'

    if raw.startswith('['):
        match = _BRACKET_ENDPOINT_RE.match(raw)
        if not match:
            return None, f'FCC 地址格式非法: {raw}'
        host = match.group(1)
        port_text = match.group(2)
        port = int(port_text) if port_text else DEFAULT_FCC_PORT
    elif raw.count(':') == 1:
        host, port_text = raw.rsplit(':', 1)
        if not port_text.isdigit():
            return None, f'FCC 端口非法: {raw}'
        port = int(port_text)
    elif raw.count(':') == 0:
        host, port = raw, DEFAULT_FCC_PORT
    else:
        # 未加方括号的裸 IPv6（无法携带端口），使用默认端口
        host, port = raw, DEFAULT_FCC_PORT

    host = _strip_brackets(host)
    if not _is_valid_host(host):
        return None, f'FCC 主机非法: {raw}'
    if not (1 <= port <= 65535):
        return None, f'FCC 端口越界: {raw}'
    return (host, port), None


def _resolve_multicast(parsed) -> Tuple[Optional[Tuple[str, int]], Optional[str]]:
    """优先取 URL host 中的组播地址，否则回退解析 /rtp/、/udp/ 路径。"""
    host = _strip_brackets(parsed.hostname or '')
    if host:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None and ip.is_multicast:
            try:
                port = parsed.port
            except ValueError:
                return None, '组播地址端口非法'
            if port is None:
                return None, f'组播地址缺少端口: {host}'
            if not (1 <= port <= 65535):
                return None, f'组播端口越界: {port}'
            return (str(ip), port), None

    match = _MULTICAST_PATH_RE.search(parsed.path or '')
    if not match:
        return None, None

    path_host = _strip_brackets(match.group('host'))
    try:
        ip = ipaddress.ip_address(path_host)
    except ValueError:
        return None, f'路径中的组播地址非法: {path_host}'
    if not ip.is_multicast:
        return None, f'路径地址不是组播地址: {path_host}'

    port = int(match.group('port'))
    if not (1 <= port <= 65535):
        return None, f'路径组播端口越界: {port}'
    return (str(ip), port), None


def resolve_fcc(url: str, log_errors: bool = True) -> FccResolution:
    """权威 FCC 解析入口。

    判定规则：
    - 查询参数名大小写不敏感、位置任意；
    - 组播源优先取 URL host（本身是组播 IP），否则回退 /rtp/ 或 /udp/ 路径；
    - 能区分“不是 FCC 流”和“是 FCC 流但地址解析失败”。
    """
    if not url or not isinstance(url, str):
        return FccResolution(is_fcc=False)

    try:
        parsed = urlparse(url.strip())
    except ValueError as e:
        _log_parse_error_once(url, f'URL 解析异常: {e}')
        return FccResolution(is_fcc=False, error=str(e))

    query = parse_qs(parsed.query, keep_blank_values=True)
    fcc_value: Optional[str] = None
    has_fcc = False
    for key, values in query.items():
        if key.lower() == 'fcc':
            has_fcc = True
            fcc_value = values[0] if values else ''
            break

    if not has_fcc:
        return FccResolution(is_fcc=False)

    multicast, multicast_error = _resolve_multicast(parsed)
    endpoint, endpoint_error = _parse_fcc_endpoint(fcc_value or '')

    error = endpoint_error
    if error is None and multicast is None:
        error = multicast_error or '无法从 URL 解析组播源地址'

    if error and log_errors:
        _log_parse_error_once(url, error)

    return FccResolution(
        is_fcc=True,
        endpoint=endpoint,
        multicast=multicast,
        error=error,
    )


def is_fcc_url(url: str, log_errors: bool = False) -> bool:
    """判断 URL 是否为 FCC 流（fcc 参数存在即视为 FCC，即使地址非法）。"""
    return resolve_fcc(url, log_errors=log_errors).is_fcc


def parse_fcc_from_url(url: str) -> Optional[Tuple[str, int]]:
    """从频道 URL 中解析 FCC 代理地址（兼容旧调用方）。"""
    return resolve_fcc(url, log_errors=False).endpoint


def parse_multicast_from_url(url: str) -> Optional[Tuple[str, int]]:
    """从 URL 中提取组播源地址（兼容旧调用方）。"""
    return resolve_fcc(url, log_errors=False).multicast


def _is_multicast_ip(ip: str) -> bool:
    """判断是否为组播 IP（IPv4 224.0.0.0/4 或 IPv6 ff00::/8）。"""
    try:
        return ipaddress.ip_address(_strip_brackets(ip)).is_multicast
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# 持久化 UDP socket —— 避免每次通知都创建/关闭 socket 的开销
# ---------------------------------------------------------------------------
_udp_sock_lock = threading.Lock()
_udp_socks: Dict[int, socket.socket] = {}


def _get_udp_socket(family: int) -> socket.socket:
    """获取（必要时创建）指定地址族的持久化 UDP socket。

    使用非阻塞模式（setblocking(False)），sendto 永不阻塞，
    实现 fire-and-forget 语义——UDP 本身不保证送达，无需等待。
    """
    sock = _udp_socks.get(family)
    if sock is not None:
        return sock
    with _udp_sock_lock:
        sock = _udp_socks.get(family)
        if sock is None:
            sock = socket.socket(family, socket.SOCK_DGRAM)
            sock.setblocking(False)  # 非阻塞：sendto 立即返回
            _udp_socks[family] = sock
            logger.debug(f"FCC持久化UDP socket已创建: family={family}")
    return sock


def _close_udp_socket():
    """关闭所有持久化 UDP socket（应用退出时调用）"""
    with _udp_sock_lock:
        for family, sock in list(_udp_socks.items()):
            try:
                sock.close()
            except Exception as e:
                logger.debug(f"_close_udp_socket({family}): {e}")
        _udp_socks.clear()


def send_fcc_notification(
    fcc_ip: str,
    fcc_port: int,
    leave_addr: Optional[Tuple[str, int]] = None,
    join_addr: Optional[Tuple[str, int]] = None,
    timeout: float = 1.0,
) -> bool:
    """向 FCC 代理发送换台通知（UDP）

    使用持久化非阻塞 socket，LEAVE+JOIN 可合并为单个 UDP 包发送。
    需要分别发往不同端点时，请分两次调用（见 FCCService.on_channel_change）。

    Args:
        fcc_ip: FCC 代理 IP
        fcc_port: FCC 代理端口
        leave_addr: 要离开的组播地址 (ip, port)，可为 None
        join_addr: 要加入的组播地址 (ip, port)，可为 None
        timeout: 已弃用（非阻塞模式无需超时），保留以保持向后兼容

    Returns:
        是否发送成功
    """
    messages = []
    if leave_addr:
        messages.append(f"LEAVE {leave_addr[0]} {leave_addr[1]}")
    if join_addr:
        messages.append(f"JOIN {join_addr[0]} {join_addr[1]}")

    if not messages:
        return True

    payload = '\n'.join(messages) + '\n'
    return _send_udp(fcc_ip, fcc_port, payload.encode('utf-8'))


def _send_udp(ip: str, port: int, data: bytes, timeout: float = 0.0) -> bool:
    """发送 UDP 数据包（使用持久化非阻塞 socket，自动适配 IPv4/IPv6）。"""
    try:
        host = _strip_brackets(ip)
        try:
            family = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
        except ValueError:
            family = socket.AF_INET
        sock = _get_udp_socket(family)
        sock.sendto(data, (host, port))
        logger.debug(f"FCC通知已发送: {ip}:{port}, 数据: {data!r}")
        return True
    except BlockingIOError:
        # 内核发送缓冲区满，UDP 本就不保证送达，静默忽略
        logger.debug(f"FCC通知发送缓冲区满，已丢弃: {ip}:{port}")
        return False
    except Exception as e:
        logger.debug(f"FCC通知发送失败: {e}")
        return False


class FCCService:
    """FCC 快速换台服务管理器

    跟踪当前播放频道的组播地址，换台时自动向 FCC 代理发送 leave/join。

    通知语义：
    - 换台：先向“旧端点”发 LEAVE（旧组播），再向“新端点”发 JOIN（新组播）；
      两端点不同时分别发送，不混用地址；
    - 从 FCC 频道切到非 FCC 频道、停止播放：向旧端点补发 LEAVE；
    - 同一频道重试：force=True 时强制重发 JOIN，不被“同地址早退”拦截。
    """

    def __init__(self):
        self._current_multicast: Optional[Tuple[str, int]] = None
        self._current_fcc: Optional[Tuple[str, int]] = None

    def on_channel_change(self, new_url: str, force: bool = False) -> None:
        """频道切换时调用。

        Args:
            new_url: 新频道的 URL
            force: True 时即使地址未变化也重发 JOIN（用于重连/重试）
        """
        resolution = resolve_fcc(new_url)
        new_fcc = resolution.endpoint if resolution.is_fcc else None
        new_multicast = resolution.multicast if resolution.is_fcc else None

        old_fcc = self._current_fcc
        old_multicast = self._current_multicast
        changed = (old_fcc != new_fcc) or (old_multicast != new_multicast)

        # 1) 先向旧端点发 LEAVE，避免把旧组播的 LEAVE 发给新端点
        if old_fcc and old_multicast and changed:
            self._notify(old_fcc, leave_addr=old_multicast)

        # 2) 再向新端点发 JOIN
        if new_fcc and new_multicast and (changed or force):
            self._notify(new_fcc, join_addr=new_multicast)

        if resolution.is_fcc and (new_fcc is None or new_multicast is None):
            logger.info(
                "FCC 流已识别但通知无法发送（endpoint=%s, multicast=%s）: %s",
                new_fcc, new_multicast, resolution.error,
            )

        self._current_fcc = new_fcc
        self._current_multicast = new_multicast

    def on_stop(self) -> None:
        """停止播放时调用——向当前端点发送 LEAVE 并清理状态。"""
        if self._current_fcc and self._current_multicast:
            self._notify(self._current_fcc, leave_addr=self._current_multicast)
        self._current_multicast = None
        self._current_fcc = None

    @staticmethod
    def _notify(
        endpoint: Tuple[str, int],
        leave_addr: Optional[Tuple[str, int]] = None,
        join_addr: Optional[Tuple[str, int]] = None,
    ) -> None:
        try:
            send_fcc_notification(
                endpoint[0], endpoint[1],
                leave_addr=leave_addr,
                join_addr=join_addr,
            )
        except Exception as e:
            logger.debug(f"FCC通知发送失败: {e}")
