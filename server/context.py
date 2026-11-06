from core.version import APP_USER_AGENT
import os
import json
import time
import threading
import logging
from typing import Optional, List, Dict

from core.config_manager import ConfigManager
from services.m3u_parser import load_m3u_from_url_data, parse_m3u_content, extract_tvg_url_from_header
from utils.general_utils import redact_url

logger = logging.getLogger('server.context')


class StandaloneScanner:
    """独立模式（Android/无 GUI）下的扫描器

    不依赖 PySide6，使用 requests + 线程池实现：
    - 重新加载订阅源（start_scan）
    - 验证频道 URL 可达性（start_validate）
    - 维护扫描统计与停止控制
    """

    def __init__(self, ctx: "ServerContext"):
        self._ctx = ctx
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats: Dict[str, int] = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'scanned': 0,
        }
        self.running = False
        self.last_message = '空闲'
        self._scan_mode: Optional[str] = None  # 'subscription' 或 'range'
        self._scan_results: List[Dict] = []  # URL 范围扫描结果列表

    def is_scanning(self) -> bool:
        return self.running

    def start_scan(self, url: str = '') -> bool:
        """开始扫描：重新加载订阅源

        - url 为空：重新加载所有已配置的订阅源
        - url 非空：将该 URL 作为新订阅源添加并加载
        返回 True 表示已成功启动，False 表示已有扫描在运行
        """
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._stop_event.clear()
            self.stats = {'total': 0, 'valid': 0, 'invalid': 0, 'scanned': 0}
            self._scan_mode = 'subscription'
        self._thread = threading.Thread(target=self._scan_worker, args=(url,), daemon=True)
        self._thread.start()
        return True

    def stop_scan(self):
        """请求停止扫描"""
        self._stop_event.set()

    def start_range_scan(
        self, base_url: str, timeout: int = 10, threads: int = 4,
        engine: str = 'requests', retry: bool = False, append: bool = False
    ) -> bool:
        """开始 URL 范围扫描（PC 端"扫描整理"功能）

        解析方括号范围表达式（如 rtp://239.1.1.[1-255]:5002），
        命名变量同步：[1-255:n] 定义变量 n，{n} 引用（两处 n 同步变化）。
        对每个 URL 做可达性检查（HTTP/HTTPS 用 requests HEAD），
        将有效 URL 添加为频道。rtp/udp/rtsp 等非 HTTP 协议直接添加不验证。

        Args:
            engine: 扫描引擎 ('requests' / 'ffprobe' / 'mpv')。
                    standalone 模式下始终使用 requests（ffprobe/mpv 不可用）。
            retry: 是否启用智能重试（失败 URL 用 2x 超时重试）
            append: 是否追加模式（不清空已有扫描结果，不覆盖已有频道）
        """
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._stop_event.clear()
            self.stats = {'total': 0, 'valid': 0, 'invalid': 0, 'scanned': 0}
            self._scan_mode = 'range'
        self._thread = threading.Thread(
            target=self._range_scan_worker, args=(base_url, timeout, threads, engine, retry, append), daemon=True
        )
        self._thread.start()
        return True

    def _range_scan_worker(
        self, base_url: str, timeout: int, threads: int,
        engine='requests', retry=False, append=False
    ):
        """URL 范围扫描工作线程"""
        try:
            from services.url_parser_service import URLRangeParser
            parser = URLRangeParser()
            # 先统计总 URL 数
            all_urls: List[str] = []
            for batch in parser.parse_url(base_url, batch_size=1000):
                for u in batch:
                    if self._stop_event.is_set():
                        break
                    all_urls.append(u)
                if self._stop_event.is_set():
                    break
            with self._lock:
                self.stats['total'] = len(all_urls)
                if not append:
                    self._scan_results = []  # 清空上次扫描结果（追加模式保留）
            if not all_urls:
                self.last_message = '无 URL 可扫描（检查范围表达式）'
                return
            self.last_message = f'开始扫描 {len(all_urls)} 个 URL（{threads} 线程）'
            logger.info(f"URL 范围扫描：共 {len(all_urls)} 个 URL")

            from concurrent.futures import ThreadPoolExecutor, as_completed
            from utils.http_session import get as _http_get
            import socket
            from urllib.parse import urlparse
            found_channels: List[Dict] = []
            scan_results: List[Dict] = []  # 完整扫描结果列表（含有效/无效）
            scanned_count = 0
            valid_count = 0
            invalid_count = 0

            def _check_one(u: str):
                """验证单个 URL，返回 (url, valid, status, latency_ms, channel_or_none)"""
                if self._stop_event.is_set():
                    return (u, False, '已取消', 0, None)
                low = u.lower()
                name = u.split('/')[-1] or u.split('://')[-1] or u
                t0 = time.time()
                # HTTP/HTTPS：用 GET stream 验证可达性（HEAD 很多 IPTV 服务器不支持）
                if low.startswith('http://') or low.startswith('https://'):
                    try:
                        # GET + Range（只读前 2KB，避免下载整个流）
                        r = _http_get(u, timeout=timeout, allow_redirects=True,
                                          headers={'User-Agent': APP_USER_AGENT,
                                                   'Range': 'bytes=0-2047'},
                                          stream=True)
                        latency = int((time.time() - t0) * 1000)
                        status_code = r.status_code
                        # 2xx / 3xx / 206（Partial Content）视为可达
                        if status_code < 400:
                            # 读取前 2KB 检查是否为有效媒体内容
                            content_type = r.headers.get('Content-Type', '').lower()
                            chunk = b''
                            try:
                                chunk = next(r.iter_content(2048), b'') or b''
                            except Exception:
                                pass
                            try:
                                r.close()
                            except Exception:
                                pass
                            # 判断内容类型
                            is_media = False
                            media_kind = ''
                            # 1. Content-Type 为媒体类型
                            if any(t in content_type for t in
                                   ('video/', 'audio/', 'mpegurl', 'm3u', 'octet-stream', 'mp2t')):
                                is_media = True
                                media_kind = content_type.split(';')[0].strip()
                            # 2. M3U/M3U8 文本特征
                            elif chunk[:7] == b'#EXTM3U' or b'#EXT-X' in chunk[:2048]:
                                is_media = True
                                media_kind = 'm3u/m3u8'
                            # 3. MPEG-TS 同步字节 0x47（每 188 字节一个）
                            elif len(chunk) >= 188 and chunk[0] == 0x47:
                                is_media = True
                                media_kind = 'mpeg-ts'
                            # 4. 任意 2xx 响应都视为可达（保守策略，避免漏报）
                            else:
                                is_media = True
                                media_kind = f'HTTP {status_code}'
                            if is_media:
                                ch = {'name': name, 'url': u, 'group': '扫描结果', 'logo': '',
                                      'tvg_id': '', 'tvg_name': name, 'valid': True}
                                return (u, True, media_kind, latency, ch)
                            return (u, False, f'HTTP {status_code} 非媒体', latency, None)
                        return (u, False, f'HTTP {status_code}', latency, None)
                    except Exception as e:
                        latency = int((time.time() - t0) * 1000)
                        logger.debug(f"扫描频道失败 {redact_url(u)}: {e}")
                        return (u, False, f'错误: {str(e)[:60]}', latency, None)
                # RTSP：用 TCP socket 连接检查
                if low.startswith('rtsp://'):
                    try:
                        parsed = urlparse(u)
                        host = parsed.hostname or ''
                        port = parsed.port or 554
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        try:
                            sock.settimeout(timeout)
                            sock.connect((host, port))
                            latency = int((time.time() - t0) * 1000)
                            ch = {'name': name, 'url': u, 'group': '扫描结果', 'logo': '',
                                  'tvg_id': '', 'tvg_name': name, 'valid': True}
                            return (u, True, 'RTSP 可达', latency, ch)
                        finally:
                            sock.close()
                    except Exception as e:
                        latency = int((time.time() - t0) * 1000)
                        return (u, False, f'RTSP: {str(e)[:40]}', latency, None)
                # RTP/UDP：尝试加入组播组并接收数据包验证可达性
                # 与 PC 端 ffprobe 验证效果类似：能收到数据则视为有效
                if low.startswith('rtp://') or low.startswith('udp://'):
                    try:
                        parsed = urlparse(u)
                        host = parsed.hostname or ''
                        port = parsed.port or 5004
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        # 短超时：扫描时使用 timeout/2（最多 5 秒），避免长时间阻塞
                        sock_timeout = min(max(timeout // 2, 1), 5) if timeout else 3
                        sock.settimeout(sock_timeout)
                        try:
                            # 组播地址（224.0.0.0 - 239.255.255.255）需要 join 才能接收
                            parts = host.split('.')
                            try:
                                is_multicast = (len(parts) == 4
                                                and 224 <= int(parts[0]) <= 239
                                                and all(0 <= int(p) <= 255 for p in parts))
                            except ValueError:
                                is_multicast = False
                            if is_multicast:
                                # IP_ADD_MEMBERSHIP：加入组播组
                                mreq = socket.inet_aton(host) + socket.inet_aton('0.0.0.0')
                                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                            # 绑定到组播端口（监听任意来源）
                            sock.bind(('', port))
                            # 尝试接收第一个数据包
                            data, addr = sock.recvfrom(2048)
                            latency = int((time.time() - t0) * 1000)
                            ch = {'name': name, 'url': u, 'group': '扫描结果', 'logo': '',
                                  'tvg_id': '', 'tvg_name': name, 'valid': True}
                            return (u, True, f'收到数据 {len(data)}B', latency, ch)
                        finally:
                            try:
                                sock.close()
                            except Exception:
                                pass
                    except socket.timeout:
                        latency = int((time.time() - t0) * 1000)
                        # 超时未收到数据：不添加为频道（避免生成大量无效频道）
                        return (u, False, '超时无数据', latency, None)
                    except OSError as e:
                        latency = int((time.time() - t0) * 1000)
                        # 组播 join 失败/权限不足等：标记无效但不影响其他扫描
                        return (u, False, f'无法验证: {str(e)[:40]}', latency, None)
                # 其他协议：标记为不支持
                return (u, False, '不支持的协议', 0, None)

            with ThreadPoolExecutor(max_workers=max(1, min(threads, 64))) as pool:
                futures = {pool.submit(_check_one, u): u for u in all_urls}
                for fut in as_completed(futures):
                    if self._stop_event.is_set():
                        break
                    scanned_count += 1
                    try:
                        url, valid, status, latency, ch = fut.result()
                        # 记录扫描结果（用于前端列表显示）
                        result_item = {
                            'url': url, 'name': ch['name'] if ch else url.split('/')[-1],
                            'valid': valid, 'status': status, 'latency': latency,
                            'group': '扫描结果'
                        }
                        scan_results.append(result_item)
                        if ch:
                            found_channels.append(ch)
                            if valid is True:
                                valid_count += 1
                        else:
                            invalid_count += 1
                    except Exception as e:
                        scan_results.append({
                            'url': futures[fut], 'name': futures[fut].split('/')[-1],
                            'valid': False, 'status': f'异常: {str(e)[:40]}', 'latency': 0,
                            'group': '扫描结果'
                        })
                        invalid_count += 1
                    with self._lock:
                        self.stats['scanned'] = scanned_count
                        self.stats['valid'] = valid_count
                        self.stats['invalid'] = invalid_count
                        # 每 50 个结果或最后一批时才更新完整列表，避免 O(n²) 复制
                        if scanned_count % 50 == 0 or scanned_count == len(all_urls):
                            self._scan_results = list(scan_results)
                    if scanned_count % 10 == 0:
                        self.last_message = f'已扫描 {scanned_count}/{len(all_urls)}（有效 {valid_count}）'

            # 智能重试：对失败的 URL 用 2x 超时重新扫描（与 PC 端 _start_retry_scan 对齐）
            if retry and not self._stop_event.is_set():
                failed_urls = [r['url'] for r in scan_results if not r.get('valid')]
                if failed_urls:
                    retry_timeout = min(timeout * 2, 60)
                    self.last_message = f'智能重试：{len(failed_urls)} 个失败 URL（超时 {retry_timeout}s）'
                    logger.info(f"智能重试扫描：{len(failed_urls)} 个 URL，超时={retry_timeout}s")
                    retry_found: List[Dict] = []
                    retry_scanned = 0
                    retry_valid = 0
                    with ThreadPoolExecutor(max_workers=max(1, min(threads, 64))) as pool:
                        futures = {pool.submit(_check_one, u): u for u in failed_urls}
                        for fut in as_completed(futures):
                            if self._stop_event.is_set():
                                break
                            retry_scanned += 1
                            try:
                                url, valid, status, latency, ch = fut.result()
                                if valid and ch:
                                    # 重试成功：替换原结果
                                    retry_found.append(ch)
                                    retry_valid += 1
                                    # 更新原结果列表中对应条目
                                    for i, r in enumerate(scan_results):
                                        if r['url'] == url:
                                            scan_results[i] = {
                                                'url': url, 'name': ch['name'],
                                                'valid': True, 'status': status + ' (重试)',
                                                'latency': latency, 'group': '扫描结果'
                                            }
                                            break
                                    found_channels.append(ch)
                                    valid_count += 1
                                    invalid_count -= 1
                                else:
                                    pass  # 重试仍失败，保留原结果
                            except Exception:
                                pass
                            with self._lock:
                                self.stats['scanned'] = scanned_count + retry_scanned
                                self.stats['valid'] = valid_count
                                self.stats['invalid'] = invalid_count
                                self._scan_results = list(scan_results)
                    logger.info(f"智能重试完成：新增 {retry_valid} 个有效频道")

            # 保存完整结果列表
            with self._lock:
                self._scan_results = scan_results
            if found_channels and not self._stop_event.is_set():
                # 追加到现有频道列表（不覆盖订阅源加载的频道）
                with self._ctx._channels_lock:
                    if append:
                        # 追加模式：按 URL 去重后追加
                        existing_urls = {c.get('url', '') for c in self._ctx._channels if c.get('url', '')}
                        new_channels = [c for c in found_channels if c.get('url', '') not in existing_urls]
                        self._ctx._channels = self._ctx._channels + new_channels
                        self.last_message = f'完成：追加 {len(new_channels)} 个有效频道（共 {len(self._ctx._channels)} 个）'
                    else:
                        self._ctx._channels = self._ctx._channels + found_channels
                        self.last_message = f'完成：发现 {len(found_channels)} 个有效频道'
                # 持久化到 channels_cache.json：进程重启后扫描频道不丢失
                self._ctx._save_channels_to_cache()
                self._ctx._last_load_time = time.time()
                logger.info(f"URL 范围扫描完成，发现 {len(found_channels)} 个有效频道，已持久化")
            elif self._stop_event.is_set():
                self.last_message = '已停止'
            else:
                self.last_message = f'完成：未发现有效频道（扫描 {scanned_count} 个）'
        except Exception as e:
            logger.error(f"URL 范围扫描异常: {e}")
            self.last_message = f'扫描异常: {e}'
        finally:
            with self._lock:
                self.running = False
                self._scan_mode = None

    def get_status(self) -> Dict:
        with self._lock:
            return {
                'running': self.running,
                'total': self.stats.get('total', 0),
                'valid': self.stats.get('valid', 0),
                'invalid': self.stats.get('invalid', 0),
                'scanned': self.stats.get('scanned', 0),
                'message': self.last_message,
                'mode': getattr(self, '_scan_mode', None),
            }

    def start_validate(self, timeout: int = 10, threads: int = 4) -> bool:
        """开始验证所有频道的 URL 可达性

        与 PC 端 scanner_service.validate_channels 对齐：
        - HTTP/HTTPS：GET + Range 检查
        - RTSP：TCP socket 连接检查
        - RTP/UDP：组播 join + 接收数据包
        - 其他协议：跳过
        更新频道的 valid/status 字段并持久化。
        """
        with self._lock:
            if self.running:
                return False
            self.running = True
            self._stop_event.clear()
            self.stats = {'total': 0, 'valid': 0, 'invalid': 0, 'scanned': 0}
            self._scan_mode = 'validate'
        self._thread = threading.Thread(
            target=self._validate_worker, args=(timeout, threads), daemon=True
        )
        self._thread.start()
        return True

    def _validate_worker(self, timeout: int, threads: int):
        """频道验证工作线程"""
        try:
            with self._ctx._channels_lock:
                channels = list(self._ctx._channels)
            with self._lock:
                self.stats['total'] = len(channels)
            if not channels:
                self.last_message = '无频道可验证'
                return
            self.last_message = f'开始验证 {len(channels)} 个频道'
            logger.info(f"频道验证：共 {len(channels)} 个频道")

            from concurrent.futures import ThreadPoolExecutor, as_completed
            from utils.http_session import get as _http_get
            import socket
            from urllib.parse import urlparse
            scanned_count = 0
            valid_count = 0
            invalid_count = 0

            def _validate_one(idx: int, url: str):
                """验证单个频道 URL，返回 (idx, valid, status)"""
                if self._stop_event.is_set():
                    return (idx, False, '已取消')
                low = url.lower() if url else ''
                if not low:
                    return (idx, False, 'URL 为空')
                if low.startswith('http://') or low.startswith('https://'):
                    try:
                        r = _http_get(url, timeout=timeout, allow_redirects=True,
                                          headers={'User-Agent': APP_USER_AGENT,
                                                   'Range': 'bytes=0-2047'},
                                          stream=True)
                        status_code = r.status_code
                        if status_code < 400:
                            try:
                                r.close()
                            except Exception:
                                pass
                            return (idx, True, f'HTTP {status_code}')
                        try:
                            r.close()
                        except Exception:
                            pass
                        return (idx, False, f'HTTP {status_code}')
                    except Exception as e:
                        logger.debug(f"扫描频道失败 {redact_url(url)}: {e}")
                        return (idx, False, f'错误: {str(e)[:50]}')
                if low.startswith('rtsp://'):
                    try:
                        parsed = urlparse(url)
                        host = parsed.hostname or ''
                        port = parsed.port or 554
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        try:
                            sock.settimeout(timeout)
                            sock.connect((host, port))
                            return (idx, True, 'RTSP 可达')
                        finally:
                            sock.close()
                    except Exception as e:
                        return (idx, False, f'RTSP: {str(e)[:40]}')
                if low.startswith('rtp://') or low.startswith('udp://'):
                    try:
                        parsed = urlparse(url)
                        host = parsed.hostname or ''
                        port = parsed.port or 5004
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.settimeout(min(max(timeout // 2, 1), 5))
                        try:
                            parts = host.split('.')
                            is_multicast = (len(parts) == 4 and 224 <= int(parts[0]) <= 239)
                            if is_multicast:
                                mreq = socket.inet_aton(host) + socket.inet_aton('0.0.0.0')
                                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                            sock.bind(('', port))
                            data, addr = sock.recvfrom(2048)
                            return (idx, True, f'收到数据 {len(data)}B')
                        finally:
                            try:
                                sock.close()
                            except Exception:
                                pass
                    except socket.timeout:
                        return (idx, False, '超时无数据')
                    except OSError as e:
                        return (idx, False, f'无法验证: {str(e)[:40]}')
                # 其他协议（file:// 等）：跳过
                return (idx, None, '跳过')

            with ThreadPoolExecutor(max_workers=max(1, min(threads, 32))) as pool:
                futures = {pool.submit(_validate_one, i, ch.get('url', '')): i for i, ch in enumerate(channels)}
                for fut in as_completed(futures):
                    if self._stop_event.is_set():
                        break
                    scanned_count += 1
                    try:
                        idx, valid, status = fut.result()
                        if valid is True:
                            valid_count += 1
                            with self._ctx._channels_lock:
                                if 0 <= idx < len(self._ctx._channels):
                                    self._ctx._channels[idx]['valid'] = True
                                    self._ctx._channels[idx]['status'] = status
                        elif valid is False:
                            invalid_count += 1
                            with self._ctx._channels_lock:
                                if 0 <= idx < len(self._ctx._channels):
                                    self._ctx._channels[idx]['valid'] = False
                                    self._ctx._channels[idx]['status'] = status
                        # valid is None: 跳过，不计数
                    except Exception:
                        invalid_count += 1
                    with self._lock:
                        self.stats['scanned'] = scanned_count
                        self.stats['valid'] = valid_count
                        self.stats['invalid'] = invalid_count
                    if scanned_count % 20 == 0:
                        self.last_message = f'已验证 {scanned_count}/{len(channels)}（有效 {valid_count}）'

            # 持久化验证结果
            self._ctx._save_channels_to_cache()
            self.last_message = (
                f'验证完成：{valid_count} 有效 / {invalid_count} 无效 / '
                f'{scanned_count - valid_count - invalid_count} 跳过'
            )
            logger.info(f"频道验证完成：{valid_count} 有效，{invalid_count} 无效")
        except Exception as e:
            logger.error(f"频道验证异常: {e}")
            self.last_message = f'验证异常: {e}'
        finally:
            with self._lock:
                self.running = False
                self._scan_mode = None

    def get_results(self) -> List[Dict]:
        """获取 URL 范围扫描结果列表"""
        with self._lock:
            return list(self._scan_results)

    def _scan_worker(self, url: str):
        """扫描工作线程"""
        try:
            config = self._ctx.get_config()
            if not config:
                self.last_message = '配置未初始化'
                return

            # 收集要扫描的源
            sources_to_scan = []
            if url:
                # 单 URL 扫描：临时加入源列表
                sources_to_scan.append({'url': url, 'name': url, 'enabled': True})
            else:
                # 扫描所有已配置的源
                try:
                    sources_to_scan = config.load_playlist_sources()
                except Exception as e:
                    logger.warning(f"加载订阅源列表失败: {e}")
                    sources_to_scan = []

            if not sources_to_scan:
                self.last_message = '无订阅源'
                return

            self.last_message = f'正在加载 {len(sources_to_scan)} 个订阅源'
            all_channels: List[Dict] = []
            with self._lock:
                self.stats['total'] = len(sources_to_scan)

            for idx, source in enumerate(sources_to_scan):
                if self._stop_event.is_set():
                    self.last_message = '已停止'
                    break
                src_url = source.get('url', '')
                if not src_url or not source.get('enabled', True):
                    continue
                try:
                    from utils.http_session import get as _http_get
                    resp = _http_get(src_url, timeout=30, headers={'User-Agent': APP_USER_AGENT})
                    content = load_m3u_from_url_data(resp.content)
                    channels, header_attrs = parse_m3u_content(content)
                    if channels:
                        all_channels.extend(channels)
                        with self._lock:
                            self.stats['valid'] += len(channels)
                    # 提取 M3U 头部的 x-tvg-url EPG 地址，自动添加为 EPG 源
                    epg_url = ''
                    if header_attrs and header_attrs.get('epg_url'):
                        epg_url = header_attrs['epg_url']
                    else:
                        for line in content.splitlines()[:5]:
                            if line.startswith('#EXTM3U'):
                                epg_url = extract_tvg_url_from_header(line) or ''
                                break
                    if epg_url:
                        try:
                            config = self._ctx.get_config()
                            if config:
                                epg_sources = config.load_epg_sources() or []
                                if not any(s.get('url') == epg_url for s in epg_sources):
                                    epg_sources.append({'url': epg_url, 'name': 'M3U 内嵌 EPG', 'enabled': True})
                                    config.save_epg_sources(epg_sources)
                                    logger.info(f'自动添加 M3U 内嵌 EPG 源: {redact_url(epg_url)}')
                        except Exception as e:
                            logger.warning(f'自动添加 EPG 源失败: {e}')
                    self.last_message = f'已加载 {src_url[:40]}: {len(channels)} 个频道'
                except Exception as e:
                    logger.warning(f"扫描源 {redact_url(src_url)} 失败: {e}")
                    with self._lock:
                        self.stats['invalid'] += 1
                    self.last_message = f'加载失败: {src_url[:40]}'
                finally:
                    with self._lock:
                        self.stats['scanned'] = idx + 1

            # 更新 context 的频道列表
            if all_channels and not self._stop_event.is_set():
                with self._ctx._channels_lock:
                    self._ctx._channels = all_channels
                self._ctx._last_load_time = time.time()
                self.last_message = f'完成：共 {len(all_channels)} 个频道'
                logger.info(f"独立模式扫描完成，加载了 {len(all_channels)} 个频道")
            elif self._stop_event.is_set():
                self.last_message = '已停止'
            else:
                self.last_message = '未加载到任何频道'
        except Exception as e:
            logger.error(f"独立模式扫描异常: {e}")
            self.last_message = f'扫描异常: {e}'
        finally:
            with self._lock:
                self.running = False


class ServerContext:
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, main_window=None):

        self._main_window = main_window
        self._config: Optional[ConfigManager] = None
        self._channels: List[Dict] = []
        self._channels_lock = threading.Lock()
        self._sources: List[Dict] = []
        self._sources_lock = threading.Lock()
        self._epg_data: Dict = {}
        self._standalone = main_window is None
        self._last_load_time = 0.0
        self._standalone_scanner: Optional[StandaloneScanner] = None
        self._epg_parser = None  # standalone 模式下使用的 EPG 解析器
        # 订阅源加载状态（独立于扫描整理功能）
        self._source_loading = False
        self._source_load_status: Dict = {'loading': False, 'total': 0, 'loaded': 0, 'channels': 0, 'message': '空闲', 'warning': ''}
        self._source_load_lock = threading.Lock()

        if self._standalone:
            self._config = ConfigManager()
            self._standalone_scanner = StandaloneScanner(self)
            # 先从本地缓存加载频道（进程重启后立即可用，无需等待网络）
            self._load_channels_from_cache()
            threading.Thread(target=self._load_channels_from_file, daemon=True).start()
            # 异步初始化 EPG 解析器（不依赖 PySide6）
            threading.Thread(target=self._init_epg_parser, daemon=True).start()

    @classmethod
    def get_instance(cls, main_window=None):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(main_window)
            elif main_window is not None:
                cls._instance._main_window = main_window
                cls._instance._standalone = False
        return cls._instance

    def _get_channels_cache_path(self) -> str:
        """频道缓存文件路径（与 config.ini 同目录）"""
        return os.path.join(self._config.config_dir, 'channels_cache.json')

    def _load_channels_from_cache(self):
        """从本地缓存文件加载频道（进程重启后立即可用，无需等待网络）"""
        if not self._config:
            return
        try:
            cache_path = self._get_channels_cache_path()
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                channels = data.get('channels', [])
                if channels:
                    with self._channels_lock:
                        self._channels = channels
                    # 设置 _last_load_time 防止 reload_if_needed 立即触发同步 HTTP 重载
                    # （后台 _load_channels_from_file 线程会异步更新频道和网络拉取完成后刷新此时间戳）
                    self._last_load_time = time.time()
                    logger.info(f"从缓存加载了 {len(channels)} 个频道")
        except Exception as e:
            logger.warning(f"加载频道缓存失败: {e}")

    def _save_channels_to_cache(self):
        """将频道列表保存到本地缓存文件（供下次进程重启时快速恢复）

        使用原子写入模式（临时文件 + rename），避免写入过程中崩溃导致缓存损坏。
        """
        if not self._config:
            return
        try:
            cache_path = self._get_channels_cache_path()
            with self._channels_lock:
                channels_snapshot = list(self._channels)
            data = {'channels': channels_snapshot, 'saved_at': time.time()}
            # 原子写入：临时文件名唯一，避免导入/重载并发写同一 .tmp 互相截断
            import tempfile
            cache_dir = os.path.dirname(cache_path) or '.'
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.tmp', prefix='channels.')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, cache_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.warning(f"保存频道缓存失败: {e}")

    def _load_channels_from_file(self):
        if not self._config:
            return
        try:
            sources = self._config.load_playlist_sources()
            with self._sources_lock:
                self._sources = sources
            all_channels = []
            for source in sources:
                if not source.get('enabled', True):
                    continue
                url = source.get('url', '')
                if not url:
                    continue
                try:

                    from utils.http_session import get as _http_get
                    from services.m3u_parser import looks_like_m3u
                    resp = _http_get(url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': '*/*',
                    })
                    if resp.status_code != 200:
                        logger.warning(f"加载源 {url} 返回 HTTP {resp.status_code}，跳过")
                        continue
                    content = load_m3u_from_url_data(resp.content)
                    if not looks_like_m3u(content):
                        logger.warning(f"加载源 {url} 返回内容不是 M3U（可能是错误页），跳过")
                        continue
                    channels, _ = parse_m3u_content(content)
                    if channels:
                        # 标记频道来源（订阅源 URL），用于 Android 端区分 SUB/LOCAL tab
                        # 若不设置 source，Android 端 LOCAL tab 的 source.isEmpty() 过滤条件
                        # 会将所有订阅频道误判为本地频道显示
                        for c in channels:
                            c['source'] = url
                        all_channels.extend(channels)
                except Exception as e:
                    logger.warning(f"加载源 {url} 失败: {e}")
            # 网络加载到频道时更新内存+缓存；加载为空时保留已有频道（不覆盖）
            if all_channels:
                # 合并而非覆盖：保留不在订阅源中的手动添加/本地频道（按 URL 去重）
                # 根因：之前 self._channels = all_channels 完全覆盖，导致手动添加的本地频道丢失
                # （与 _reload_sources_worker 的合并逻辑对齐）
                existing_urls = {c.get('url', '') for c in all_channels if c.get('url', '')}
                with self._channels_lock:
                    extra_channels = [
                        c for c in self._channels
                        if c.get('url', '') and c.get('url', '') not in existing_urls
                    ]
                    if extra_channels:
                        self._channels = all_channels + extra_channels
                        logger.info(f"独立模式加载了 {len(all_channels)} 个频道，保留 {len(extra_channels)} 个本地频道")
                    else:
                        self._channels = all_channels
                        logger.info(f"独立模式加载了 {len(all_channels)} 个频道")
                self._save_channels_to_cache()
            else:
                with self._channels_lock:
                    existing = len(self._channels)
                if existing > 0:
                    logger.info(f"网络加载为空，保留现有 {existing} 个频道")
                else:
                    with self._channels_lock:
                        self._channels = all_channels
                    logger.info("独立模式加载了 0 个频道（无缓存可保留）")
            self._last_load_time = time.time()
        except Exception as e:
            logger.error(f"加载频道数据失败: {e}")

    def reload_if_needed(self, max_age=300):
        """独立模式：仅在内存完全没有频道时兜底异步重载（60s 节流）。

        周期性自动刷新已移除：弱网下每 5 分钟反复拉源失败，会反复触发
        「网络异常」提示打扰用户；启动时 _load_channels_from_file 线程已
        负责首次在线刷新，后续更新由用户在订阅源面板手动触发（reload_sources）。
        """
        if not self._standalone:
            return
        with self._channels_lock:
            if self._channels:
                return
        # 无任何频道（如启动时网络失败且无缓存可恢复）：低频兜底重试
        if time.time() - self._last_load_time < 60:
            return
        self.reload_sources('')

    def reload_sources(self, url: str = '') -> bool:
        """重新加载订阅源（独立于扫描整理功能）

        - url 为空：重新加载所有已配置的订阅源
        - url 非空：加载指定 URL 的订阅源
        返回 True 表示已启动加载，False 表示已有加载在运行
        """
        with self._source_load_lock:
            if self._source_loading:
                return False
            self._source_loading = True
            self._source_load_status = {'loading': True, 'total': 0, 'loaded': 0, 'channels': 0, 'message': '开始加载', 'warning': ''}
        threading.Thread(target=self._reload_sources_worker, args=(url,), daemon=True).start()
        return True

    def _reload_sources_worker(self, url: str):
        """订阅源加载工作线程（后台静默执行，不使用扫描状态）"""
        try:
            config = self._config
            if not config:
                with self._source_load_lock:
                    self._source_loading = False
                    self._source_load_status = {
                        'loading': False, 'total': 0, 'loaded': 0,
                        'channels': 0, 'message': '配置未初始化', 'warning': ''}
                return

            # 收集要加载的源
            if url:
                sources = [{'url': url, 'name': url, 'enabled': True}]
            else:
                try:
                    sources = config.load_playlist_sources()
                except Exception as e:
                    logger.warning(f"加载订阅源列表失败: {e}")
                    sources = []

            with self._source_load_lock:
                self._source_load_status['total'] = len(sources)

            if not sources:
                with self._source_load_lock:
                    self._source_loading = False
                    self._source_load_status = {
                        'loading': False, 'total': 0, 'loaded': 0,
                        'channels': 0, 'message': '无订阅源', 'warning': ''}
                return

            all_channels: List[Dict] = []
            errors: List[str] = []  # 记录每个源的加载失败原因
            fetch_errors: List[str] = []  # 仅网络/格式层面的失败，用于区分“源可用但内容为空”
            epg_urls_from_m3u: List[str] = []  # M3U 内嵌 EPG 地址（后台异步加载，不阻塞频道入库）
            for idx, source in enumerate(sources):
                src_url = source.get('url', '')
                if not src_url or not source.get('enabled', True):
                    continue
                with self._source_load_lock:
                    self._source_load_status['loaded'] = idx + 1
                    self._source_load_status['message'] = f'加载中 {idx+1}/{len(sources)}'
                try:
                    from utils.http_session import get as _http_get
                    # 弱网下单次请求容易读超时（raw.githubusercontent.com 常见 20s+），
                    # 每个源失败后自动重试一次，显著提高订阅源加载成功率
                    resp = None
                    last_err = ''
                    for _attempt in range(2):
                        try:
                            _resp = _http_get(src_url, timeout=30, headers={'User-Agent': APP_USER_AGENT})
                            if _resp.status_code == 200:
                                resp = _resp
                                break
                            last_err = f'HTTP {_resp.status_code}'
                        except Exception as fetch_err:
                            last_err = str(fetch_err)
                        if _attempt == 0:
                            logger.warning(f"加载源 {redact_url(src_url)} 第 1 次失败: {last_err}，1.5s 后重试")
                            time.sleep(1.5)
                    if resp is None:
                        err = (last_err or '加载失败')[:60]
                        errors.append(err)
                        fetch_errors.append(err)
                        logger.warning(f"加载源 {redact_url(src_url)} 失败（已重试 1 次）: {last_err}")
                        continue
                    content = load_m3u_from_url_data(resp.content)
                    from services.m3u_parser import looks_like_m3u
                    if not looks_like_m3u(content):
                        err = '内容不是 M3U 格式'
                        errors.append(err)
                        fetch_errors.append(err)
                        logger.warning(f"加载源 {redact_url(src_url)} 返回内容不是 M3U（可能是错误页）")
                        continue
                    channels, header_attrs = parse_m3u_content(content)
                    # 提取 M3U 头部 x-tvg-url 定义的 EPG 地址，稍后统一异步加载。
                    # EPG 文件可能很大（几十 MB），同步下载会让 source_loading 长时间为 true，
                    # Android 端启动门禁误判初始化超时导致无法进入主界面。
                    epg_url_from_m3u = header_attrs.get('epg_url', '') if header_attrs else ''
                    if epg_url_from_m3u:
                        logger.info(f"M3U 源 {redact_url(src_url)} 包含 EPG 地址: {redact_url(epg_url_from_m3u)}")
                        epg_urls_from_m3u.append(epg_url_from_m3u)
                    # 更新该源的 last_update 时间戳（无论是否解析到频道，HTTP 拉取已成功）
                    from datetime import datetime
                    config.update_playlist_source_last_update(idx, datetime.now().isoformat())
                    if channels:
                        # 标记频道来源（订阅源 URL），用于 Android 端区分 SUB/LOCAL tab
                        for c in channels:
                            c['source'] = src_url
                        all_channels.extend(channels)
                    else:
                        err = 'M3U 解析为空'
                        errors.append(err)
                        logger.warning(f"加载源 {redact_url(src_url)} M3U 解析为空（内容长度 {len(content)}）")
                except Exception as e:
                    err = str(e)[:60]
                    errors.append(err)
                    fetch_errors.append(err)
                    logger.warning(f"加载源 {redact_url(src_url)} 异常: {e}")

            # 更新频道列表
            # 合并策略：保留本地频道（扫描/导入，无 source 字段），
            # 替换所有订阅频道（有 source 字段）为本次加载的结果。
            # 这样禁用/删除源后，其频道会被正确移除。
            cache_dirty = True
            with self._channels_lock:
                local_channels = [
                    c for c in self._channels
                    if not c.get('source', '')
                ]
                if all_channels:
                    # 去重：本地频道中 URL 与订阅频道重复的移除
                    sub_urls = {c.get('url', '') for c in all_channels if c.get('url', '')}
                    local_channels = [
                        c for c in local_channels
                        if not c.get('url', '') or c.get('url', '') not in sub_urls
                    ]
                    self._channels = all_channels + local_channels
                    ch_count = len(self._channels)
                    logger.info(f"订阅源 {len(all_channels)} 个 + 本地保留 {len(local_channels)} 个（扫描/导入）")
                elif fetch_errors:
                    # 存在网络/格式层面的失败且无一成功（网络故障/源暂时损坏）：
                    # 保留现有频道（含订阅频道），不覆盖缓存。
                    # 否则瞬时网络抖动会把可用订阅数据洗掉并污染缓存，
                    # 重启后也无法恢复（频道全空的根因）。
                    with self._channels_lock:
                        ch_count = len(self._channels)
                    logger.warning(
                        f"订阅源加载全部失败（{';'.join(fetch_errors[:3])}），"
                        f"保留现有 {ch_count} 个频道，不覆盖缓存")
                    cache_dirty = False
                else:
                    # 所有源都可正常拉取但内容为空（或全部源被禁用/删除）：只保留本地频道
                    self._channels = local_channels
                    ch_count = len(self._channels)
                    logger.info(f"订阅源无频道，保留本地 {len(local_channels)} 个")
            if cache_dirty:
                self._save_channels_to_cache()
            self._last_load_time = time.time()
            with self._source_load_lock:
                self._source_loading = False
                self._source_load_status = {
                    'loading': False, 'total': len(sources),
                    'loaded': len(sources), 'channels': ch_count,
                    'message': f'完成：{ch_count} 个频道',
                    # 全部源下载失败时保留缓存频道，提示用户网络异常而非数据丢失
                    'warning': ('' if cache_dirty else '网络异常，已使用缓存频道')}
            logger.info(f"订阅源加载完成，共 {ch_count} 个频道")

            # M3U 内嵌 EPG 后台异步加载：频道已入库，EPG 下载/解析不阻塞加载完成状态
            if epg_urls_from_m3u:
                threading.Thread(
                    target=self._load_m3u_epg_async,
                    args=(epg_urls_from_m3u,),
                    daemon=True,
                ).start()
        except Exception as e:
            logger.error(f"订阅源加载异常: {e}")
            with self._source_load_lock:
                self._source_loading = False
                self._source_load_status = {
                    'loading': False, 'total': 0, 'loaded': 0,
                    'channels': 0, 'message': f'异常: {e}'}

    def _load_m3u_epg_async(self, epg_urls: List[str]):
        """后台加载 M3U 内嵌 EPG（不阻塞订阅源加载完成状态）"""
        for epg_url in epg_urls:
            try:
                if hasattr(self, '_epg_parser') and self._epg_parser:
                    self._epg_parser.load_single_epg(epg_url)
                else:
                    from core.subscription_manager import SubscriptionManager
                    SubscriptionManager().load_single_epg(epg_url)
            except Exception as epg_e:
                logger.warning(f"后台加载 M3U 内嵌 EPG 失败: {epg_e}")

    def get_source_load_status(self) -> Dict:
        """获取订阅源加载状态"""
        with self._source_load_lock:
            return dict(self._source_load_status)

    def get_all_channels(self) -> List[Dict]:
        if self._main_window:
            channels = []
            # 使用 _channels_lock 保护读取，避免订阅加载线程并发修改
            with self._channels_lock:
                sub = getattr(self._main_window, '_sub_channels', [])
                local = getattr(self._main_window, '_local_channels', [])
                seen = set()
                for ch in sub:
                    url = ch.get('url', '')
                    if url and url not in seen:
                        channels.append(ch)
                        seen.add(url)
                for ch in local:
                    url = ch.get('url', '')
                    if url and url not in seen:
                        channels.append(ch)
                        seen.add(url)
            if not channels:
                model = getattr(self._main_window, 'channel_model', None)
                if model:
                    for i in range(model.rowCount()):
                        ch = model.get_channel(i)
                        if ch:
                            channels.append(ch)
            return channels
        self.reload_if_needed()
        with self._channels_lock:
            return list(self._channels)

    def update_channel(self, idx: int, data: dict) -> bool:
        """线程安全地更新指定索引的频道

        Returns: True 如果更新成功，False 如果索引越界
        """
        with self._channels_lock:
            if 0 <= idx < len(self._channels):
                self._channels[idx].update(data)
                return True
            return False

    def delete_channel(self, idx: int) -> bool:
        """线程安全地删除指定索引的频道

        Returns: True 如果删除成功，False 如果索引越界
        """
        with self._channels_lock:
            if 0 <= idx < len(self._channels):
                self._channels.pop(idx)
                return True
            return False

    def add_channel(self, data: dict) -> int:
        """线程安全地添加频道

        Returns: 新频道的索引
        """
        with self._channels_lock:
            data['id'] = len(self._channels) + 1
            self._channels.append(data)
            return len(self._channels) - 1

    def import_channels(self, channels: List[Dict]) -> int:
        """线程安全地批量导入频道

        Returns: 导入的频道数量
        """
        with self._channels_lock:
            base_id = len(self._channels)
            for i, c in enumerate(channels):
                c.setdefault('id', base_id + i + 1)
            self._channels.extend(channels)
            return len(channels)

    def get_channel_count(self) -> int:
        """线程安全地获取频道数量"""
        with self._channels_lock:
            return len(self._channels)

    def get_channel_model(self):
        if self._main_window and hasattr(self._main_window, 'channel_model'):
            return self._main_window.channel_model
        return None

    def get_config(self) -> Optional[ConfigManager]:
        if self._main_window and hasattr(self._main_window, 'config'):
            return self._main_window.config
        return self._config

    def get_epg_parser(self):
        if self._main_window and hasattr(self._main_window, 'epg_parser'):
            return self._main_window.epg_parser
        return self._epg_parser

    def _init_epg_parser(self):
        """独立模式：初始化 EPG 解析器（使用 SubscriptionManager 单例）

        SubscriptionManager 不依赖 PySide6，可在 Android/无 GUI 环境运行。
        若已配置 EPG 订阅源，则后台加载 EPG 数据。
        """
        try:
            from core.subscription_manager import SubscriptionManager
            sm = SubscriptionManager()
            self._epg_parser = sm
            # 先尝试从缓存加载EPG数据（进程重启后立即可用）
            if sm.load_cached_epg_data():
                logger.info("独立模式：EPG缓存加载成功")
            # 若已有 EPG 源则后台加载（下载新数据）
            sources = sm.get_epg_sources() if hasattr(sm, 'get_epg_sources') else []
            if sources:
                logger.info(f"独立模式：检测到 {len(sources)} 个 EPG 源，开始后台加载 EPG 数据")
                threading.Thread(target=self._load_epg_async, args=(sm,), daemon=True).start()
            else:
                logger.info("独立模式：未配置 EPG 源，跳过 EPG 加载")
        except Exception as e:
            logger.error(f"独立模式初始化 EPG 解析器失败: {e}")

    def _load_epg_async(self, sm):
        """后台加载 EPG 数据"""
        try:
            sm.load_all_epg_data()
        except Exception as e:
            logger.error(f"独立模式后台加载 EPG 失败: {e}")

    def reload_epg(self):
        """重新加载 EPG 数据（添加 EPG 源后调用）"""
        if not self._standalone or not self._epg_parser:
            return False
        threading.Thread(target=self._load_epg_async, args=(self._epg_parser,), daemon=True).start()
        return True

    def get_scan_dialog(self):
        if self._main_window and hasattr(self._main_window, '_scan_dialog'):
            return self._main_window._scan_dialog
        return None

    def get_standalone_scanner(self) -> Optional[StandaloneScanner]:
        """获取独立模式扫描器（standalone 模式下可用）"""
        return self._standalone_scanner

    def get_main_window(self):
        return self._main_window

    def is_standalone(self):
        return self._standalone
