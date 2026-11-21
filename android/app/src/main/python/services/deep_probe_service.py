"""深度检测：用 ffmpeg 实际解码约 2 秒，能解才算真有效。

默认不参与扫描，只由用户在扫描整理里对单个频道手工触发。
"""
import subprocess
import threading
import time
from typing import Dict

from core.log_manager import global_logger
from services.network_context import PROBESIZE_BYTES, build_network_context
from services.validity_tiers import INVALID, SUSPECTED, VALID
from utils.platform_utils import get_ffmpeg_path, get_subprocess_creation_flags

# 正在运行的深度检测子进程：退出时必须全部结束，
# 否则 onefile 引导器无法删除 _MEI 临时目录。
_active_procs = set()
_procs_lock = threading.Lock()


def terminate_all_deep_probes():
    """结束所有在跑的深度检测子进程，返回未能确认退出的 PID 列表。"""
    with _procs_lock:
        procs = list(_active_procs)
    leftover = []
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception as e:
            global_logger.debug(f"终止深度检测子进程失败: {e}")
    deadline = time.monotonic() + 1.5
    for proc in procs:
        try:
            proc.wait(timeout=max(0.05, deadline - time.monotonic()))
        except Exception:
            leftover.append(proc.pid)
    with _procs_lock:
        _active_procs.difference_update(procs)
    return leftover


def deep_probe_stream(url: str, duration: float = 2.0, timeout: int = 10) -> Dict:
    """实际解码约 ``duration`` 秒。

    Returns:
        {url, valid, validity, status, error_type, elapsed}
    """
    t0 = time.time()
    result = {
        'url': url,
        'valid': False,
        'validity': INVALID,
        'status': '',
        'error_type': None,
        'elapsed': 0,
    }
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        result['status'] = '未找到 ffmpeg，无法深度检测'
        result['error_type'] = 'ffmpeg_missing'
        result['validity'] = SUSPECTED
        return result

    ctx = build_network_context(connect_timeout=timeout)
    low = (url or '').lower()
    is_http = low.startswith('http://') or low.startswith('https://')
    connect_us = ctx.connect_timeout * 1_000_000

    cmd = [
        ffmpeg,
        '-v', 'error',
        '-xerror',
        '-analyzeduration', str(ctx.analyze_timeout * 1_000_000),
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
            cmd.extend(['-tls_verify', '1'])
    if low.startswith('rtsp://'):
        try:
            from core.config_manager import ConfigManager
            rtsp_transport = ConfigManager().load_playback_settings().get(
                'rtsp_transport', 'tcp')
        except Exception:
            rtsp_transport = 'tcp'
        cmd.extend(['-rtsp_transport', rtsp_transport])
    if low.startswith('rtp://') or low.startswith('udp://'):
        cmd.extend(['-f', 'mpegts'])
    if low.endswith('.ts') and not is_http:
        cmd.extend(['-f', 'mpegts'])
    header_lines = ctx.header_lines()
    if header_lines:
        cmd.extend(['-headers', '\r\n'.join(header_lines)])

    cmd.extend(['-i', url, '-t', str(duration), '-f', 'null', '-'])

    max_wait = ctx.connect_timeout + ctx.analyze_timeout + int(duration) + 10
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=get_subprocess_creation_flags(),
        )
        with _procs_lock:
            _active_procs.add(proc)
        try:
            _, stderr_bytes = proc.communicate(timeout=max_wait)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                _, stderr_bytes = proc.communicate(timeout=2)
            except Exception:
                stderr_bytes = b''
            result['elapsed'] = int((time.time() - t0) * 1000)
            result['status'] = '深度检测超时'
            result['error_type'] = 'timeout'
            return result
        returncode = proc.returncode
    except Exception as exc:
        result['elapsed'] = int((time.time() - t0) * 1000)
        result['status'] = f'深度检测失败: {str(exc)[:60]}'
        result['error_type'] = 'probe_failed'
        result['validity'] = SUSPECTED
        return result
    finally:
        if proc is not None:
            with _procs_lock:
                _active_procs.discard(proc)

    result['elapsed'] = int((time.time() - t0) * 1000)
    stderr = (stderr_bytes or b'').decode('utf-8', errors='replace')
    if returncode == 0:
        result['valid'] = True
        result['validity'] = VALID
        result['status'] = f'解码 {duration:g} 秒成功'
        return result

    from services.ffprobe_validator_service import FfprobeStreamValidator
    error_type, message, tier = FfprobeStreamValidator._classify_ffprobe_error(
        stderr, returncode)
    result['error_type'] = error_type
    result['validity'] = tier
    result['status'] = message
    global_logger.debug(f"深度检测失败 {url}: {message}")
    return result
