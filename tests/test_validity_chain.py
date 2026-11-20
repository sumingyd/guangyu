from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import fast_probe_service as fast
from services import network_context
from services.channel_dedup_service import carry_over_channel_state
from services.ffprobe_validator_service import FfprobeStreamValidator
from services.validity_tiers import (
    INVALID, SUSPECTED, VALID, apply_tier, channel_tier, status_text_for,
)


def test_channel_tier_maps_legacy_valid_bool():
    assert channel_tier({'valid': True}) == VALID
    assert channel_tier({'valid': False}) == INVALID
    assert channel_tier({'valid': None}) is None
    # validity 优先于老字段
    assert channel_tier({'valid': True, 'validity': SUSPECTED}) == SUSPECTED


def test_apply_tier_keeps_legacy_bool_in_sync():
    ch = {'url': 'http://a'}
    apply_tier(ch, VALID)
    assert ch['valid'] is True and ch['status'] == '有效'
    apply_tier(ch, SUSPECTED)
    assert ch['valid'] is None and ch['status'] == '疑似'
    apply_tier(ch, INVALID)
    assert ch['valid'] is False and ch['status'] == '无效'
    assert status_text_for(None) == '待检测'


def test_carry_over_state_by_normalized_url():
    old = [
        {'url': 'http://a.com/live.m3u8', 'valid': True, 'validity': VALID,
         'status': '有效', 'resolution': '1920x1080'},
        {'url': 'http://b.com/x.m3u8', 'valid': False, 'validity': INVALID,
         'status': '无效'},
    ]
    new = [{'url': 'http://a.com/live.m3u8', 'valid': None},
           {'url': 'http://b.com/x.m3u8'}]
    carry_over_channel_state(new, old)
    assert new[0]['validity'] == VALID and new[0]['resolution'] == '1920x1080'
    assert new[1]['validity'] == INVALID and new[1]['valid'] is False


def test_network_context_referer_falls_back_to_network_section(monkeypatch):
    fake_cfg = MagicMock()
    fake_cfg.load_playback_settings.return_value = {
        'user_agent': 'UA-playback',
        'http_headers': 'X-Test: 1',
        'http_proxy': 'http://proxy:8080',
        'tls_verify': True,
    }
    fake_cfg.load_network_settings.return_value = {'referer': 'http://ref.local'}
    monkeypatch.setattr(
        'core.config_manager.ConfigManager', lambda: fake_cfg
    )
    ctx = network_context.build_network_context(connect_timeout=8)
    assert ctx.referer == 'http://ref.local'
    assert ctx.user_agent == 'UA-playback'
    assert ctx.proxy == 'http://proxy:8080'
    assert ctx.tls_verify is True
    assert ctx.analyze_timeout == 10  # 10–15 秒下限
    assert ctx.request_headers()['Referer'] == 'http://ref.local'
    assert 'X-Test: 1' in ctx.header_lines()


def test_network_context_network_referer_wins_over_header(monkeypatch):
    fake_cfg = MagicMock()
    fake_cfg.load_playback_settings.return_value = {
        'http_headers': 'Referer: http://from-header\r\nX-A: b',
    }
    fake_cfg.load_network_settings.return_value = {'referer': 'http://from-network'}
    monkeypatch.setattr('core.config_manager.ConfigManager', lambda: fake_cfg)
    ctx = network_context.build_network_context(connect_timeout=20)
    # 扫描整理里显式填写的 Network.referer 优先于通用请求头
    assert ctx.referer == 'http://from-network'
    assert ctx.analyze_timeout == 15  # 上限 15 秒
    assert 'Referer' not in ctx.extra_headers


def test_sniff_http_content_recognizes_media_signals():
    assert fast._sniff_http_content(b'#EXTM3U\n#EXT-X-VERSION:3', '')[0]
    ts = bytes([0x47] + [0] * 187) * 2
    assert fast._sniff_http_content(ts, '')[0]
    assert fast._sniff_http_content(b'<html>404</html>', 'video/mp4')[0]
    assert not fast._sniff_http_content(b'<html>hello</html>', 'text/html')[0]


class _FakeResponse:
    def __init__(self, status_code, headers, body=b''):
        self.status_code = status_code
        self.headers = headers
        self._body = body

    def iter_content(self, size):
        yield self._body

    def close(self):
        pass


def _patch_http_get(monkeypatch, response):
    monkeypatch.setattr(
        'utils.http_session.get', lambda *a, **k: response
    )


def test_fast_probe_http_tiers(monkeypatch):
    ctx = network_context.NetworkContext(connect_timeout=3, analyze_timeout=10)
    _patch_http_get(monkeypatch, _FakeResponse(404, {}))
    assert fast.probe_stream('http://a/x', timeout=3, ctx=ctx)['validity'] == INVALID

    _patch_http_get(monkeypatch, _FakeResponse(200, {}))
    assert fast.probe_stream('http://a/x', timeout=3, ctx=ctx)['validity'] == SUSPECTED

    _patch_http_get(monkeypatch, _FakeResponse(
        200, {'Content-Type': 'application/vnd.apple.mpegurl'}))
    result = fast.probe_stream('http://a/x', timeout=3, ctx=ctx)
    assert result['validity'] == VALID and result['valid'] is True


def test_fast_probe_rtsp_tcp_only_is_suspected(monkeypatch):
    class _Sock:
        def __init__(self):
            self.closed = False

        def settimeout(self, _):
            pass

        def connect(self, _):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr('socket.socket', lambda *a, **k: _Sock())
    result = fast.probe_stream('rtsp://cam/live', timeout=2)
    assert result['validity'] == SUSPECTED
    assert result['error_type'] == 'weak_check'


def test_ffprobe_error_classification():
    classify = FfprobeStreamValidator._classify_ffprobe_error
    assert classify('Server returned 404 Not Found', 1)[0] == 'http_404'
    assert classify('Server returned 404 Not Found', 1)[2] == INVALID
    assert classify('Connection refused', 1)[2] == INVALID
    assert classify('Invalid data found when processing input', 1)[2] == SUSPECTED
    assert classify('moov atom not found', 1)[2] == SUSPECTED
    assert classify('some unknown failure', 1)[2] == SUSPECTED
