"""快速探测：HTTP 状态码 + 内容嗅探，不做真实拉流。

用于「几万个候选」的批量扫描，也供独立模式（Android/无 GUI）使用。
结论分三档：

- HTTP 状态码 <400 且内容命中媒体特征（#EXTM3U、TS 同步字节、视频/mpegurl
  Content-Type）→ 确证有效
- HTTP 能连上但没有任何媒体特征 → 疑似
- 4xx / 拒连 / DNS 失败 → 不可用
- 连接阶段超时（TCP 握手等不到）：短超时重试一次，仍超时 → 不可用；
  连上之后的读取超时 → 疑似（源站活着，只是慢）
- RTSP 仅 TCP 连通 → 疑似；TCP 连接超时同样重试一次，仍超时 → 不可用
- RTP/UDP 至少收到两个包且校验 0x47 同步字节，才判有效；只有包但不同步 → 疑似
"""
import socket
import time
from typing import Dict, Optional
from urllib.parse import urlparse

from core.log_manager import global_logger
from services.network_context import NetworkContext, build_network_context
from services.validity_tiers import INVALID, SUSPECTED, VALID

TS_PACKET_SIZE = 188
# 组播扫描时每个 URL 最多等待的秒数（避免长时间阻塞线程池）
UDP_MAX_WAIT = 5
# 需要连续收到的 TS 包数量
UDP_TS_PACKETS = 2
# HTTP 连接超时上限（秒）：用户设定更小时尊重用户值；读取超时始终用用户设定
HTTP_CONNECT_TIMEOUT_MAX = 3
# 连接阶段超时的重试次数与重试时的连接超时上限：
# 死地址通常就是「等不到握手」，一次超时不足以断言，重试一次仍超时才判不可用。
# 只缩短重试这一次（首次仍最多 3s），让步死地址最坏 3+1 秒，避免死链多的清单耗时翻倍
CONNECT_ATTEMPTS = 2
CONNECT_RETRY_TIMEOUT = 1


def _timeout_error_type(exc: Exception) -> Optional[str]:
    """把 requests 超时异常映射为错误类型；非超时返回 None。"""
    try:
        from requests import exceptions as req_exc
    except Exception:
        return None
    if isinstance(exc, req_exc.ConnectTimeout):
        return 'connect_timeout'
    if isinstance(exc, req_exc.ReadTimeout):
        return 'read_timeout'
    if isinstance(exc, req_exc.Timeout):
        return 'timeout'
    return None

_MEDIA_CONTENT_TYPES = (
    'video/',
    'audio/',
    'mpegurl',
    'm3u8',
    'mp2t',
    'vnd.apple.mpegurl',
)


def _sniff_http_content(chunk: bytes, content_type: str) -> tuple[str, str]:
    """判断响应内容是否具备明确的媒体特征。

    Returns:
        (是否命中, 描述)
    """
    ct = (content_type or '').lower()
    if any(token in ct for token in _MEDIA_CONTENT_TYPES):
        return True, f'Content-Type: {ct.split(";")[0].strip()}'

    head = (chunk or b'')[:2048]
    # 容忍 BOM 与前置空白
    text = head.lstrip(b'\xef\xbb\xbf \t\r\n')
    if text.startswith(b'#EXTM3U') or b'#EXT-X' in head:
        return True, 'm3u/m3u8'
    if _ts_sync_offset(head) is not None:
        return True, 'mpeg-ts'
    return False, ''


def _ts_sync_offset(data: bytes) -> Optional[int]:
    """返回 TS 同步字节偏移；不足一个包时返回 None。"""
    if not data or len(data) < TS_PACKET_SIZE or data[0] != 0x47:
        return None
    # 有第二个包时要求同样落在 188 字节处，过滤偶然碰撞
    if len(data) >= TS_PACKET_SIZE * 2 and data[TS_PACKET_SIZE] != 0x47:
        return None
    return 0


def _rtp_payload_offset(data: bytes) -> int:
    """RTP 固定头 12 字节（无 CSRC 时），返回载荷起点。"""
    if len(data) < 12:
        return 0
    cc = data[0] & 0x0F
    return 12 + cc * 4


def _looks_like_ts_packet(data: bytes, is_rtp: bool) -> bool:
    """校验一个 UDP/RTP 数据包是否携带 TS 同步字节。"""
    if not data:
        return False
    offset = _rtp_payload_offset(data) if is_rtp else 0
    if offset >= len(data):
        return False
    payload = data[offset:]
    return len(payload) >= TS_PACKET_SIZE and payload[0] == 0x47


def _local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return ''


def _is_self_source(addr, recv_port: int, local_ip: str) -> bool:
    """忽略自身回环/自身发出的数据包。"""
    try:
        src_ip, src_port = addr[0], addr[1]
    except Exception:
        return False
    if src_ip in ('127.0.0.1', '::1', '0.0.0.0'):
        return True
    if local_ip and src_ip == local_ip and src_port == recv_port:
        return True
    return False


def _probe_http(url: str, timeout: int, ctx: NetworkContext, t0: float) -> Dict:
    result = {'url': url, 'valid': False, 'validity': INVALID, 'status': '',
              'latency': 0, 'content_type': '', 'error_type': None}
    try:
        from utils.http_session import get as _http_get
    except Exception as exc:
        result['status'] = f'HTTP 客户端不可用: {exc}'
        result['validity'] = SUSPECTED
        result['error_type'] = 'client_unavailable'
        return result

    headers = ctx.request_headers()
    headers['Range'] = 'bytes=0-2047'
    # 连接超时短、读取超时长：黑洞地址快速失败，慢源仍有完整读取时间
    connect_timeout = min(float(timeout), HTTP_CONNECT_TIMEOUT_MAX)
    resp = None
    for attempt in range(CONNECT_ATTEMPTS):
        attempt_timeout = (connect_timeout if attempt == 0
                           else min(connect_timeout, float(CONNECT_RETRY_TIMEOUT)))
        try:
            resp = _http_get(url, timeout=(attempt_timeout, float(timeout)),
                             allow_redirects=True, headers=headers, stream=True,
                             retry=False)
            break
        except Exception as exc:
            timeout_kind = _timeout_error_type(exc)
            if timeout_kind == 'connect_timeout' and attempt + 1 < CONNECT_ATTEMPTS:
                # 握手超时先重试一次：死地址往往就是等不到 SYN-ACK
                continue
            result['latency'] = int((time.time() - t0) * 1000)
            if timeout_kind == 'connect_timeout':
                # 两次都等不到握手，判定地址侧不可达
                result['validity'] = INVALID
                result['error_type'] = 'connect_timeout'
                result['status'] = '连接超时（重试仍失败）'
                return result
            if timeout_kind:
                # 连上之后的读取超时只说明「没等到数据」，不能断言不可用
                result['validity'] = SUSPECTED
                result['error_type'] = timeout_kind
                result['status'] = f'超时: {str(exc)[:60]}'
                return result
            result['status'] = f'错误: {str(exc)[:60]}'
            result['error_type'] = 'connect_failed'
            return result

    if resp is None:
        result['latency'] = int((time.time() - t0) * 1000)
        result['status'] = '连接失败'
        result['error_type'] = 'connect_failed'
        return result

    try:
        status_code = resp.status_code
        content_type = resp.headers.get('Content-Type', '')
        result['content_type'] = content_type
        result['latency'] = int((time.time() - t0) * 1000)
        if status_code >= 400:
            result['status'] = f'HTTP {status_code}'
            result['error_type'] = f'http_{status_code}'
            return result
        chunk = b''
        try:
            chunk = next(resp.iter_content(2048), b'') or b''
        except Exception as exc:
            timeout_kind = _timeout_error_type(exc)
            if timeout_kind:
                result['validity'] = SUSPECTED
                result['error_type'] = timeout_kind
                result['status'] = f'读取响应超时: {str(exc)[:50]}'
                return result
            chunk = b''
        hit, kind = _sniff_http_content(chunk, content_type)
        if hit:
            result['valid'] = True
            result['validity'] = VALID
            result['status'] = kind
            return result
        # 能连上但没有任何媒体特征：弱证据
        result['validity'] = SUSPECTED
        result['status'] = f'HTTP {status_code} 无媒体特征'
        result['error_type'] = 'no_media_features'
        return result
    finally:
        try:
            resp.close()
        except Exception:
            pass


def _probe_rtsp(url: str, timeout: int, t0: float) -> Dict:
    result = {'url': url, 'valid': False, 'validity': INVALID, 'status': '',
              'latency': 0, 'content_type': '', 'error_type': None}
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ''
        port = parsed.port or 554
        if not host:
            result['status'] = 'RTSP 地址无效'
            result['error_type'] = 'invalid_url'
            return result
        connect_timeout = min(float(timeout), HTTP_CONNECT_TIMEOUT_MAX)
        for attempt in range(CONNECT_ATTEMPTS):
            attempt_timeout = (connect_timeout if attempt == 0
                               else min(connect_timeout, float(CONNECT_RETRY_TIMEOUT)))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # 纯 TCP 握手：同样用短连接超时快速失败；超时先重试一次
                sock.settimeout(attempt_timeout)
                sock.connect((host, port))
                result['latency'] = int((time.time() - t0) * 1000)
                # 仅 TCP 连通属于弱检查
                result['validity'] = SUSPECTED
                result['status'] = 'RTSP 端口可达（未拉流）'
                result['error_type'] = 'weak_check'
                return result
            except (TimeoutError, socket.timeout):
                if attempt + 1 < CONNECT_ATTEMPTS:
                    continue
                # 两次都等不到握手，判定地址侧不可达
                result['latency'] = int((time.time() - t0) * 1000)
                result['validity'] = INVALID
                result['status'] = 'RTSP 连接超时（重试仍失败）'
                result['error_type'] = 'connect_timeout'
                return result
            except Exception as exc:
                result['latency'] = int((time.time() - t0) * 1000)
                result['status'] = f'RTSP: {str(exc)[:40]}'
                result['error_type'] = 'connect_failed'
                return result
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
    except Exception as exc:
        result['latency'] = int((time.time() - t0) * 1000)
        result['status'] = f'RTSP: {str(exc)[:40]}'
        result['error_type'] = 'connect_failed'
        return result


def _probe_udp(url: str, timeout: int, t0: float) -> Dict:
    result = {'url': url, 'valid': False, 'validity': INVALID, 'status': '',
              'latency': 0, 'content_type': '', 'error_type': None}
    is_rtp = url.lower().startswith('rtp://')
    parsed = urlparse(url)
    host = parsed.hostname or ''
    port = parsed.port or 5004
    if not host:
        result['status'] = 'UDP 地址无效'
        result['error_type'] = 'invalid_url'
        return result

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        wait_secs = min(max(timeout // 2, 1), UDP_MAX_WAIT)
        deadline = time.time() + wait_secs
        try:
            parts = host.split('.')
            is_multicast = (len(parts) == 4
                            and 224 <= int(parts[0]) <= 239
                            and all(0 <= int(p) <= 255 for p in parts))
        except ValueError:
            is_multicast = False
        if is_multicast:
            mreq = socket.inet_aton(host) + socket.inet_aton('0.0.0.0')
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.bind(('', port))

        local_ip = _local_ip()
        ts_packets = 0
        received = 0
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            if _is_self_source(addr, port, local_ip):
                continue
            received += 1
            if _looks_like_ts_packet(data, is_rtp):
                ts_packets += 1
                if ts_packets >= UDP_TS_PACKETS:
                    result['latency'] = int((time.time() - t0) * 1000)
                    result['valid'] = True
                    result['validity'] = VALID
                    result['status'] = f'收到连续 {ts_packets} 个 TS 包'
                    return result

        result['latency'] = int((time.time() - t0) * 1000)
        if received > 0:
            result['validity'] = SUSPECTED
            result['status'] = f'收到 {received} 个包，但未校验到 TS 同步'
            result['error_type'] = 'no_ts_sync'
        else:
            # 窗口内没等到数据只说明「没看到」，不能断言不可用
            result['validity'] = SUSPECTED
            result['status'] = '超时无数据'
            result['error_type'] = 'timeout'
        return result
    except socket.timeout:
        result['latency'] = int((time.time() - t0) * 1000)
        result['validity'] = SUSPECTED
        result['status'] = '超时无数据'
        result['error_type'] = 'timeout'
        return result
    except OSError as exc:
        # 端口绑不上、组播加入失败属于本机明确的套接字失败，仍判不可用
        result['latency'] = int((time.time() - t0) * 1000)
        result['status'] = f'无法验证: {str(exc)[:40]}'
        result['error_type'] = 'socket_error'
        return result
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


class FastProbeValidator:
    """与 ffprobe/mpv 校验器同接口的快速探测器。

    供桌面扫描在「快速嗅探」模式下复用现有 ScannerController 架构：
    只做状态码与内容特征判断，不真实拉流。
    """

    _user_agent: str = ''
    _referer: str = ''
    _terminating = False
    # 整轮扫描开始时快照一次，扫描期间用户改设置不作用于本轮
    _scan_context: NetworkContext | None = None

    def __init__(self, main_window=None):
        self.main_window = main_window

    @classmethod
    def set_scan_context(cls, ctx: NetworkContext | None):
        cls._scan_context = ctx

    @classmethod
    def clear_scan_context(cls):
        cls._scan_context = None

    @classmethod
    def set_max_concurrent(cls, value: int):
        # 快速探测没有子进程/解码器，线程数即并发上限，无需再限制
        return

    @classmethod
    def reset_terminating(cls):
        cls._terminating = False

    @classmethod
    def terminate(cls):
        cls._terminating = True

    @classmethod
    def set_terminating(cls):
        cls._terminating = True

    @classmethod
    def destroy_all_handles(cls):
        # 快速探测不持有 mpv/ffprobe 句柄
        return

    @classmethod
    def set_user_agent(cls, value: str):
        cls._user_agent = value or ''

    @classmethod
    def get_user_agent(cls) -> str:
        return cls._user_agent

    @classmethod
    def set_referer(cls, value: str):
        cls._referer = value or ''

    @classmethod
    def get_referer(cls) -> str:
        return cls._referer

    def validate_stream(self, url: str, raw_channel_name: str | None = None,
                        timeout: int = 10) -> Dict:
        if type(self)._terminating:
            return {
                'url': url, 'valid': False, 'validity': INVALID,
                'latency': None, 'resolution': None, 'codec': None,
                'bitrate': None, 'hdr_type': None, 'service_name': None,
                'error': '验证器正在关闭', 'error_type': 'terminating',
                'skipped': False,
            }
        ctx = type(self)._scan_context
        if ctx is None:
            # 未由扫描器快照时（单独调用 / Android 探测）退回逐条构造
            ctx = build_network_context(
                connect_timeout=timeout,
                user_agent=type(self)._user_agent or None,
                referer=type(self)._referer or None,
            )
        probe = probe_stream(url, timeout=timeout, ctx=ctx)
        return {
            'url': url,
            'valid': probe.get('validity') == VALID,
            'validity': probe.get('validity') or INVALID,
            'latency': probe.get('latency'),
            'resolution': None,
            'codec': None,
            'bitrate': None,
            'hdr_type': None,
            'service_name': probe.get('content_type') or None,
            'error': probe.get('status'),
            'error_type': probe.get('error_type'),
            'skipped': False,
        }


def probe_stream(
    url: str,
    timeout: int = 10,
    ctx: NetworkContext | None = None,
) -> Dict:
    """快速探测单个 URL，返回三档结果。

    返回字段：url / valid / validity / status / latency / content_type / error_type
    """
    t0 = time.time()
    low = (url or '').lower()
    if not low:
        return {'url': url, 'valid': False, 'validity': INVALID, 'status': 'URL 为空',
                'latency': 0, 'content_type': '', 'error_type': 'invalid_url'}
    if ctx is None:
        ctx = build_network_context(connect_timeout=timeout, user_agent=None, referer=None)
    try:
        if low.startswith('http://') or low.startswith('https://'):
            return _probe_http(url, timeout, ctx, t0)
        if low.startswith('rtsp://'):
            return _probe_rtsp(url, timeout, t0)
        if low.startswith('rtp://') or low.startswith('udp://'):
            return _probe_udp(url, timeout, t0)
        return {'url': url, 'valid': False, 'validity': INVALID,
                'status': '不支持的协议', 'latency': 0, 'content_type': '',
                'error_type': 'unsupported_protocol'}
    except Exception as exc:
        global_logger.debug(f"快速探测异常 {url}: {exc}")
        return {'url': url, 'valid': False, 'validity': SUSPECTED,
                'status': f'探测异常: {str(exc)[:50]}', 'latency': 0,
                'content_type': '', 'error_type': 'scan_exception'}
