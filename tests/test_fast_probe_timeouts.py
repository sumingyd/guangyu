"""快速嗅探：超时拆分、错误分级、上下文快照与疑似复核目标筛选。"""
import requests

from services import fast_probe_service as fast
from services import network_context
from services.scanner_service import ScannerController
from services.validity_tiers import INVALID, SUSPECTED, VALID


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, body=b''):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body

    def iter_content(self, size):
        yield self._body

    def close(self):
        pass


def _ctx():
    return network_context.NetworkContext(connect_timeout=5, analyze_timeout=10)


def test_http_connect_timeout_is_suspected_and_capped(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        raise requests.exceptions.ConnectTimeout('connect timed out')

    monkeypatch.setattr('utils.http_session.get', fake_get)
    result = fast.probe_stream('http://a/x.m3u8', timeout=5, ctx=_ctx())

    assert result['validity'] == SUSPECTED
    assert result['error_type'] == 'connect_timeout'
    # 连接超时取 min(用户 5s, 3s)，读取超时保留用户值；探测请求不重试
    assert seen['timeout'] == (3.0, 5.0)
    assert seen['retry'] is False


def test_http_connect_timeout_respects_smaller_user_value(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        raise requests.exceptions.ConnectTimeout('connect timed out')

    monkeypatch.setattr('utils.http_session.get', fake_get)
    result = fast.probe_stream('http://a/x.m3u8', timeout=2, ctx=_ctx())

    assert result['validity'] == SUSPECTED
    assert seen['timeout'] == (2.0, 2.0)


def test_http_read_timeout_is_suspected(monkeypatch):
    def fake_get(url, **kwargs):
        raise requests.exceptions.ReadTimeout('read timed out')

    monkeypatch.setattr('utils.http_session.get', fake_get)
    result = fast.probe_stream('http://a/x.m3u8', timeout=5, ctx=_ctx())

    assert result['validity'] == SUSPECTED
    assert result['error_type'] == 'read_timeout'


def test_http_connection_refused_stays_invalid(monkeypatch):
    def fake_get(url, **kwargs):
        raise requests.exceptions.ConnectionError('Connection refused')

    monkeypatch.setattr('utils.http_session.get', fake_get)
    result = fast.probe_stream('http://a/x.m3u8', timeout=5, ctx=_ctx())

    assert result['validity'] == INVALID
    assert result['error_type'] == 'connect_failed'


def test_http_404_stays_invalid(monkeypatch):
    monkeypatch.setattr(
        'utils.http_session.get',
        lambda *a, **k: _FakeResponse(404),
    )
    result = fast.probe_stream('http://a/x.m3u8', timeout=5, ctx=_ctx())
    assert result['validity'] == INVALID


def test_rtsp_connect_timeout_is_suspected(monkeypatch):
    class _Sock:
        def settimeout(self, _):
            pass

        def connect(self, _):
            raise TimeoutError('timed out')

        def close(self):
            pass

    monkeypatch.setattr('socket.socket', lambda *a, **k: _Sock())
    result = fast.probe_stream('rtsp://cam/live', timeout=2)

    assert result['validity'] == SUSPECTED
    assert result['error_type'] == 'timeout'


class _FakeUdpSocket:
    def __init__(self, bind_error=None):
        self._bind_error = bind_error

    def setsockopt(self, *args):
        pass

    def bind(self, addr):
        if self._bind_error:
            raise self._bind_error

    def settimeout(self, _):
        pass

    def recvfrom(self, _):
        raise TimeoutError('no data')

    def close(self):
        pass


def test_udp_no_data_is_suspected(monkeypatch):
    monkeypatch.setattr('socket.socket', lambda *a, **k: _FakeUdpSocket())
    monkeypatch.setattr(fast, '_local_ip', lambda: '')
    result = fast.probe_stream('udp://239.2.1.5:5000', timeout=2)

    assert result['validity'] == SUSPECTED
    assert result['error_type'] == 'timeout'


def test_udp_bind_failure_stays_invalid(monkeypatch):
    monkeypatch.setattr(
        'socket.socket', lambda *a, **k: _FakeUdpSocket(OSError('bind failed'))
    )
    monkeypatch.setattr(fast, '_local_ip', lambda: '')
    result = fast.probe_stream('udp://239.2.1.5:5000', timeout=2)

    assert result['validity'] == INVALID
    assert result['error_type'] == 'socket_error'


def test_fast_validator_uses_scan_context_snapshot(monkeypatch):
    ctx = network_context.NetworkContext(user_agent='snapshot-UA', connect_timeout=5)
    captured = {}

    def fake_probe(url, timeout=10, ctx=None):
        captured['ctx'] = ctx
        captured['timeout'] = timeout
        return {'validity': VALID, 'latency': 1, 'status': 'ok', 'error_type': None,
                'content_type': ''}

    monkeypatch.setattr(fast, 'probe_stream', fake_probe)
    monkeypatch.setattr(
        fast, 'build_network_context',
        lambda **kwargs: (_ for _ in ()).throw(AssertionError('不应逐条重建上下文')),
    )
    fast.FastProbeValidator.set_scan_context(ctx)
    try:
        fast.FastProbeValidator().validate_stream('http://a/x.m3u8', timeout=5)
    finally:
        fast.FastProbeValidator.clear_scan_context()

    assert captured['ctx'] is ctx
    assert captured['timeout'] == 5


def test_collect_validation_targets_only_suspected():
    class _Model:
        channels = [
            {'url': 'http://a/1', 'validity': VALID},
            {'url': 'http://a/2', 'validity': SUSPECTED},
            {'url': 'http://a/3', 'validity': INVALID},
            {'url': 'http://a/4'},
            {'url': '   ', 'validity': SUSPECTED},
        ]

        def rowCount(self):
            return len(self.channels)

        def get_channel(self, index):
            return self.channels[index]

    model = _Model()
    all_targets = ScannerController._collect_validation_targets(model)
    assert [url for url, _ in all_targets] == [
        'http://a/1', 'http://a/2', 'http://a/3', 'http://a/4',
    ]

    suspected_only = ScannerController._collect_validation_targets(model, only_suspected=True)
    assert suspected_only == [('http://a/2', 1)]


def test_probe_session_pool_matches_thread_cap():
    from utils import http_session as hs

    assert hs.POOL_MAXSIZE == 32
    session = hs.get_probe_session()
    adapter = session.get_adapter('http://')
    assert adapter._pool_maxsize == 32
