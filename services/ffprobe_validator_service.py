import json
import os
import subprocess
import threading
import time
from typing import Dict
from core.log_manager import global_logger
from utils.platform_utils import get_ffprobe_path as _find_ffprobe_path, get_subprocess_creation_flags
from services.network_context import (
    PROBESIZE_BYTES,
    NetworkContext,
    build_network_context,
)
from services.validity_tiers import INVALID, SUSPECTED, VALID


def _get_ffprobe_path():
    result = _find_ffprobe_path()
    if not result:
        global_logger.warning(f"未找到ffprobe可执行文件")
    return result


def get_optimal_thread_count():
    cpu = os.cpu_count() or 4
    return min(max(cpu, 4), 32)


class FfprobeStreamValidator:
    _semaphore: threading.Semaphore = threading.Semaphore(get_optimal_thread_count())
    _user_agent: str | None = None
    _referer: str | None = None
    _headers_lock = threading.Lock()
    _terminating = False
    _ffprobe_path: str | None = None
    _ffprobe_checked = False
    # 整轮扫描开始时快照一次；本轮内改设置不生效，结束后由扫描器丢弃
    _scan_context: NetworkContext | None = None
    _active_processes: Dict[int, subprocess.Popen] = {}
    _process_lock = threading.Lock()

    @classmethod
    def set_scan_context(cls, ctx: NetworkContext | None):
        cls._scan_context = ctx

    @classmethod
    def clear_scan_context(cls):
        cls._scan_context = None

    @classmethod
    def _get_ffprobe_path(cls):
        if not cls._ffprobe_checked:
            cls._ffprobe_path = _get_ffprobe_path()
            cls._ffprobe_checked = True
        return cls._ffprobe_path

    @classmethod
    def _get_semaphore(cls) -> threading.Semaphore:

        return cls._semaphore

    def __init__(self, main_window=None):
        self.logger = global_logger
        self.main_window = main_window

    def validate_stream(self, url: str, raw_channel_name: str | None = None, timeout: int = 3) -> Dict:
        result = {
            'url': url,
            'valid': False,
            'validity': INVALID,
            'latency': None,
            'error': None,
            'error_type': None,
            'service_name': None,
            'resolution': None,
            'codec': None,
            'bitrate': None,
            'hdr_type': None,
            'skipped': False,
        }

        ffprobe_path = self._get_ffprobe_path()
        if not ffprobe_path:
            result['error'] = 'ffprobe不可用'
            result['error_type'] = 'ffprobe_unavailable'
            return result

        if self._terminating:
            result['error'] = '验证器正在关闭'
            result['error_type'] = 'terminating'
            return result

        sem = self._get_semaphore()
        acquired = False
        for _ in range(60):
            if self._terminating:
                result['error'] = '验证器正在关闭'
                result['error_type'] = 'terminating'
                return result
            acquired = sem.acquire(timeout=0.5)
            if acquired:
                break

        if not acquired:
            # 并发槽位不足不代表频道无效：交给扫描器本轮跳过、下一轮再测
            result['error'] = '并发数超限（本轮跳过）'
            result['error_type'] = 'concurrency_limit'
            result['skipped'] = True
            return result

        try:
            ctx = type(self)._scan_context
            if ctx is None:
                ctx = build_network_context(
                    connect_timeout=timeout,
                    user_agent=self.get_user_agent(),
                    referer=self.get_referer(),
                )
            cmd = self._build_ffprobe_command(ffprobe_path, url, ctx)
            url_lower = url.lower()
            if url_lower.startswith('rtp://') or url_lower.startswith('udp://'):
                # 组播沿用 30 秒分析下限
                max_wait = max(ctx.analyze_timeout, 30) + 15
            else:
                max_wait = ctx.connect_timeout + ctx.analyze_timeout + 5
            start_time = time.time()

            creation_flags = get_subprocess_creation_flags()
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags
            )

            with self._process_lock:
                self._active_processes[proc.pid] = proc

            try:
                while proc.poll() is None:
                    if self._terminating:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception as e:
                            global_logger.debug(f"validate_stream: {e}")
                        result['error'] = '验证器正在关闭'
                        result['error_type'] = 'terminating'
                        return result
                    elapsed = time.time() - start_time
                    if elapsed > max_wait:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception as e:
                            global_logger.debug(f"validate_stream: {e}")
                        latency = int(elapsed * 1000)
                        result['latency'] = latency
                        result['error'] = f'超时({timeout}秒)'
                        result['error_type'] = 'timeout'
                        return result
                    time.sleep(0.2)

                if proc.returncode is None:
                    latency = int((time.time() - start_time) * 1000)
                    result['latency'] = latency
                    result['error'] = f'超时({timeout}秒)'
                    result['error_type'] = 'timeout'
                    return result
            finally:
                with self._process_lock:
                    self._active_processes.pop(proc.pid, None)


            latency = int((time.time() - start_time) * 1000)
            result['latency'] = latency

            stdout_data = proc.stdout.read() if proc.stdout else b''
            stderr_data = proc.stderr.read() if proc.stderr else b''
            
            try:
                proc.stdout.close()
                proc.stderr.close()
            except Exception as e:
                global_logger.debug(f"validate_stream: {e}")

            stderr_output = stderr_data.decode('utf-8', errors='ignore').strip()

            probe_data = self._parse_probe_output(stdout_data)
            if probe_data is not None:
                streams = probe_data.get('streams', [])
                if streams:
                    result['valid'] = True
                    result['validity'] = VALID

                    video_stream = None
                    audio_stream = None
                    for s in streams:
                        if s.get('codec_type') == 'video' and video_stream is None:
                            video_stream = s
                        elif s.get('codec_type') == 'audio' and audio_stream is None:
                            audio_stream = s

                    if video_stream:
                        width = video_stream.get('width')
                        height = video_stream.get('height')
                        if width and height:
                            result['resolution'] = f"{width}x{height}"
                        codec_name = video_stream.get('codec_name')
                        if codec_name:
                            result['codec'] = codec_name
                        # HDR 元数据提取（与 detect_hdr_type 统一逻辑）
                        result['hdr_type'] = self._extract_hdr_type(
                            video_stream, probe_data.get('frames', [])
                        )

                    format_info = probe_data.get('format', {})
                    bitrate = format_info.get('bit_rate')
                    if bitrate:
                        try:
                            bitrate_kbps = int(int(bitrate) / 1000)
                            result['bitrate'] = f"{bitrate_kbps}kbps"
                        except (ValueError, TypeError):
                            pass

                    try:
                        from models.channel_mappings import extract_channel_name_from_url
                        result['service_name'] = extract_channel_name_from_url(url)
                    except Exception:
                        result['service_name'] = ''

                    return result

            if proc.returncode != 0:
                error_type, error_msg, tier = self._classify_ffprobe_error(
                    stderr_output, proc.returncode
                )
                result['error'] = error_msg
                result['error_type'] = error_type
                result['validity'] = tier
                return result

            # ffprobe 正常退出但没有解析出任何流：能连上但没拿到流，按疑似处理
            result['error'] = '无媒体流'
            result['error_type'] = 'no_streams'
            result['validity'] = SUSPECTED

        except Exception as e:
            global_logger.debug(f"ffprobe 验证未知异常: {e}")
            result['error'] = '内部错误'
            result['error_type'] = 'unknown_error'
        finally:
            sem.release()

        if not result.get('valid', False):
            global_logger.debug(
                f"验证无效: {url} | "
                f"latency={result.get('latency', 0)}ms | "
                f"error_type={result.get('error_type', 'unknown')} | "
                f"error={result.get('error', '')}"
            )

        return result

    def _build_ffprobe_command(
        self, ffprobe_path: str, url: str, ctx: NetworkContext
    ) -> list:
        """按统一网络上下文构造 ffprobe 命令。

        - 连接超时沿用扫描设置；analyzeduration 单独给 10–15 秒
        - probesize 提到 10MB，组播沿用 30 秒分析下限
        - ``-v error`` 让错误分类能真正读到 stderr
        - HTTP(S) 走配置代理、TLS 跟随用户设置，并开启有限重连
        """
        u = url.lower()
        is_multicast = u.startswith('rtp://') or u.startswith('udp://')
        is_http = u.startswith('http://') or u.startswith('https://')
        connect_us = ctx.connect_timeout * 1_000_000
        analyze_secs = max(ctx.analyze_timeout, 30) if is_multicast else ctx.analyze_timeout

        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            '-analyzeduration', str(analyze_secs * 1_000_000),
            '-probesize', str(PROBESIZE_BYTES),
            '-rw_timeout', str(connect_us),
        ]

        if is_http:
            cmd.extend([
                '-timeout', str(connect_us),
                '-reconnect', '1',
                '-reconnect_streamed', '1',
                '-reconnect_delay_max', '2',
            ])
            if ctx.proxy:
                cmd.extend(['-http_proxy', ctx.proxy])
            if ctx.tls_verify:
                # ffprobe 默认不校验证书，仅在用户开启校验时显式打开
                cmd.extend(['-tls_verify', '1'])

        if u.startswith('rtsp://'):
            rtsp_transport = 'tcp'
            try:
                from core.config_manager import ConfigManager
                playback = ConfigManager().load_playback_settings()
                rtsp_transport = playback.get('rtsp_transport', 'tcp')
            except Exception as e:
                global_logger.debug(f"_build_ffprobe_command: {e}")
            cmd.extend(['-rtsp_transport', rtsp_transport])

        if u.startswith('udp://') or u.startswith('rtp://'):
            cmd.extend(['-f', 'mpegts'])

        if u.endswith('.ts') and not is_http:
            cmd.extend(['-f', 'mpegts'])

        header_lines = ctx.header_lines()
        if header_lines:
            cmd.extend(['-headers', '\r\n'.join(header_lines)])

        cmd.append(url)
        return cmd

    @staticmethod
    def _classify_ffprobe_error(stderr: str, returncode: int) -> tuple[str, str, str]:
        """把 ffprobe stderr 归类成 (error_type, 用户文案, 三档结果)。

        明确的 4xx / 拒连 / 域名解析失败判不可用；
        其余连上了但读不出内容（无效数据、超时重试后的探测失败）判疑似。
        """
        text = (stderr or '')
        low = text.lower()

        if 'server returned 404' in low or '404 not found' in low:
            return 'http_404', '服务器返回404', INVALID
        if 'server returned 403' in low or '403 forbidden' in low:
            return 'http_403', '服务器返回403', INVALID
        if 'server returned 401' in low or '401 unauthorized' in low:
            return 'http_401', '服务器返回401', INVALID
        if 'connection refused' in low:
            return 'connection_refused', '连接被拒绝', INVALID
        if 'certificate' in low or 'ssl' in low or 'tls' in low or 'handshake' in low:
            return 'tls_error', 'TLS 握手/证书错误', INVALID
        # 媒体数据不完整先于通用 not found 判断，避免 moov atom not found 被误判 404
        if 'moov atom not found' in low or 'end of file' in low:
            return 'probe_failed', '媒体数据不完整', SUSPECTED
        if 'no such file' in low or 'not found' in low or 'could not resolve host' in low \
                or 'name or service not known' in low:
            return 'not_found', '资源未找到', INVALID
        if 'timed out' in low or 'operation timed out' in low:
            return 'timeout', '连接超时', INVALID
        if 'invalid data found' in low or 'could not find codec parameters' in low:
            return 'probe_failed', '返回内容不是可识别的媒体流', SUSPECTED

        return 'probe_failed', f'探测失败(返回码:{returncode})', SUSPECTED

    @staticmethod
    def _extract_hdr_type(video_stream: dict, frames: list) -> str:
        """从 ffprobe 输出提取 HDR 类型（与 detect_hdr_type 逻辑统一）。

        ffprobe 提供更丰富的元数据，可以准确检测 HDR10+（ST.2094-40 side_data）。
        检测优先级：DV → HDR10+ → HDR10 → HLG → WCG → SDR

        Args:
            video_stream: ffprobe 视频流字典
            frames: ffprobe -show_frames 输出的帧列表
        """
        codec_name = (video_stream.get('codec_name') or '').lower()
        codec_tag = (video_stream.get('codec_tag_string') or '').lower()
        color_transfer = (video_stream.get('color_transfer') or '').lower()
        color_space = (video_stream.get('color_space') or '').lower()
        color_primaries = (video_stream.get('color_primaries') or '').lower()

        # 杜比视界检测：优先用可靠信号
        # 1) stream 级 side_data 里的 DOVI configuration record
        # 2) codec_tag_string（dvh1/dvhe/dav1 等容器标记）
        # 3) codec_name 兜底（少数封装会把编码名写成 dvhe）
        has_dovi = False
        for sd in (video_stream.get('side_data_list') or []):
            sd_type = (sd.get('side_data_type') or '').lower()
            if 'dovi' in sd_type or 'dolby vision' in sd_type:
                has_dovi = True
                break
        if not has_dovi and codec_tag in ('dvhe', 'dvh1', 'dav1', 'dva1', 'dvav', 'davc'):
            has_dovi = True
        if not has_dovi:
            has_dovi = ('dovi' in codec_name or 'dolbyvision' in codec_name or
                        'dvhe' in codec_name or 'dvh1' in codec_name or
                        'dav1' in codec_name or 'dvc' in codec_name)

        # PQ 传输特性 (SMPTE ST 2084)
        is_pq = 'smpte2084' in color_transfer or 'pq' in color_transfer
        # HLG 传输特性 (ARIB STD-B67)
        is_hlg = 'arib-std-b67' in color_transfer or 'hlg' in color_transfer
        # BT.2020 色域
        is_bt2020 = ('bt2020' in color_space or 'bt.2020' in color_space or
                     'bt2100' in color_space or 'bt.2100' in color_space or
                     'bt2020' in color_primaries or 'bt.2020' in color_primaries or
                     'bt2100' in color_primaries or 'bt.2100' in color_primaries)

        # HDR10+ 检测：检查 side_data 中是否有 ST.2094-40 动态元数据
        has_hdr10plus = False
        for frame in frames:
            side_data_list = frame.get('side_data_list', [])
            for sd in side_data_list:
                sd_type = (sd.get('side_data_type') or '').lower()
                if 'hdr dynamic metadata smpte st 2094-40' in sd_type:
                    has_hdr10plus = True
                    break
            if has_hdr10plus:
                break

        # 检测优先级：DV → HDR10+ → HDR10 → HLG → WCG → SDR
        if has_dovi:
            return 'DV'
        if is_pq:
            return 'HDR10+' if has_hdr10plus else 'HDR10'
        if is_hlg:
            return 'HLG'
        if is_bt2020:
            return 'WCG'
        return 'SDR'

    @staticmethod
    def _parse_probe_output(stdout_bytes: bytes) -> dict | None:
        try:
            text = stdout_bytes.decode('utf-8', errors='ignore').strip()
            if not text:
                return None
            return json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @classmethod
    def set_max_concurrent(cls, max_count):
        cls._semaphore = threading.Semaphore(max(1, max_count))

    @classmethod
    def set_user_agent(cls, user_agent: str):
        with cls._headers_lock:
            cls._user_agent = user_agent if user_agent else None

    @classmethod
    def set_referer(cls, referer: str):
        with cls._headers_lock:
            cls._referer = referer if referer else None

    @classmethod
    def get_headers(cls) -> dict:
        with cls._headers_lock:
            headers = {}
            if cls._user_agent:
                headers['user-agent'] = cls._user_agent
            if cls._referer:
                headers['referer'] = cls._referer
            return headers

    @classmethod
    def get_user_agent(cls) -> str | None:
        with cls._headers_lock:
            return cls._user_agent

    @classmethod
    def get_referer(cls) -> str | None:
        with cls._headers_lock:
            return cls._referer

    @classmethod
    def terminate_all(cls):
        cls._terminating = True
        with cls._process_lock:
            for pid, proc in list(cls._active_processes.items()):
                if proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=1)
                    except Exception as e:
                        global_logger.debug(f"terminate_all: {e}")
            cls._active_processes.clear()

    @classmethod
    def set_terminating(cls):
        cls._terminating = True

    @classmethod
    def destroy_all_handles(cls):
        with cls._process_lock:
            for pid, proc in list(cls._active_processes.items()):
                if proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=1)
                    except Exception as e:
                        global_logger.debug(f"destroy_all_handles: {e}")
            cls._active_processes.clear()

    @classmethod
    def reset_terminating(cls):
        cls._terminating = False
