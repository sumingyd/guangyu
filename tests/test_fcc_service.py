"""FCC 快速换台服务单元测试（表驱动，mock 真实 UDP 发包）"""

import pytest

from services import fcc_service
from services.fcc_service import (
    DEFAULT_FCC_PORT,
    FCCService,
    is_fcc_url,
    parse_fcc_from_url,
    parse_multicast_from_url,
    resolve_fcc,
)


# ---------------------------------------------------------------------------
# 解析规则
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ('url', 'endpoint', 'multicast'),
    [
        # 直连组播，fcc 为首个参数
        ('rtp://239.1.1.1:5002?fcc=150.138.8.132:8027',
         ('150.138.8.132', 8027), ('239.1.1.1', 5002)),
        # fcc 不是首个参数
        ('http://192.168.50.18:20231/rtp/239.21.1.1:5002?token=abc&fcc=150.138.8.132:8027',
         ('150.138.8.132', 8027), ('239.21.1.1', 5002)),
        # 参数名大写
        ('http://192.168.50.18:20231/rtp/239.21.1.1:5002?FCC=150.138.8.132:8027',
         ('150.138.8.132', 8027), ('239.21.1.1', 5002)),
        # /udp/ 路径回退
        ('http://proxy:8080/udp/239.3.1.7:6000?foo=1&fcc=10.0.0.9:9000',
         ('10.0.0.9', 9000), ('239.3.1.7', 6000)),
        # udp:// 直连
        ('udp://239.2.1.5:5000?fcc=10.0.0.1:9000',
         ('10.0.0.1', 9000), ('239.2.1.5', 5000)),
        # fcc 无端口，使用默认端口
        ('rtp://239.1.1.1:5002?fcc=1.2.3.4',
         ('1.2.3.4', DEFAULT_FCC_PORT), ('239.1.1.1', 5002)),
        # IPv6 FCC 端点（方括号 + 端口）
        ('rtp://239.1.1.1:5002?fcc=[2001:db8::1]:8027',
         ('2001:db8::1', 8027), ('239.1.1.1', 5002)),
        # IPv6 组播源
        ('rtp://[ff3e::1]:5002?fcc=150.138.8.132:8027',
         ('150.138.8.132', 8027), ('ff3e::1', 5002)),
        # 末尾带其他参数
        ('http://proxy/rtp/239.4.1.1:5002?fcc=150.138.8.132:8027&x=1',
         ('150.138.8.132', 8027), ('239.4.1.1', 5002)),
    ],
)
def test_resolve_fcc_success(url, endpoint, multicast):
    result = resolve_fcc(url, log_errors=False)
    assert result.is_fcc is True
    assert result.endpoint == endpoint
    assert result.multicast == multicast
    assert result.error is None


@pytest.mark.parametrize(
    ('url', 'expected_endpoint', 'expected_multicast'),
    [
        ('rtp://239.1.1.1:5002?fcc=1.2.3.4:abc', None, ('239.1.1.1', 5002)),
        ('rtp://239.1.1.1:5002?fcc=', None, ('239.1.1.1', 5002)),
        ('rtp://239.1.1.1:5002?fcc=1.2.3.4:99999', None, ('239.1.1.1', 5002)),
        # 是 FCC 流，但路径地址不是组播
        ('http://proxy/rtp/10.0.0.1:5002?fcc=1.2.3.4:8027', ('1.2.3.4', 8027), None),
        # 是 FCC 流，但组播缺少端口
        ('rtp://239.1.1.1?fcc=1.2.3.4:8027', ('1.2.3.4', 8027), None),
    ],
)
def test_resolve_fcc_partial_failure(url, expected_endpoint, expected_multicast):
    result = resolve_fcc(url, log_errors=False)
    assert result.is_fcc is True
    assert result.endpoint == expected_endpoint
    assert result.multicast == expected_multicast
    assert result.error, 'FCC 地址/组播解析失败时应给出 error 描述'


@pytest.mark.parametrize(
    'url',
    [
        'http://example.com/live.m3u8',
        'rtp://239.1.1.1:5002',
        'udp://239.2.1.5:5000',
        '',
        None,
    ],
)
def test_resolve_non_fcc(url):
    result = resolve_fcc(url, log_errors=False)
    assert result.is_fcc is False
    assert result.endpoint is None
    assert result.multicast is None


def test_legacy_wrappers_delegate_to_authoritative_parser():
    url = 'http://proxy:8080/rtp/239.3.1.7:6000?foo=1&FCC=10.0.0.9:9000'
    assert is_fcc_url(url) is True
    assert parse_fcc_from_url(url) == ('10.0.0.9', 9000)
    assert parse_multicast_from_url(url) == ('239.3.1.7', 6000)


# ---------------------------------------------------------------------------
# 通知语义
# ---------------------------------------------------------------------------
@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_send(fcc_ip, fcc_port, leave_addr=None, join_addr=None, timeout=1.0):
        calls.append({
            'fcc': (fcc_ip, fcc_port),
            'leave': leave_addr,
            'join': join_addr,
        })
        return True

    monkeypatch.setattr(fcc_service, 'send_fcc_notification', fake_send)
    return calls


CH_A = 'rtp://239.1.1.1:5002?fcc=10.0.0.1:8027'
CH_B = 'rtp://239.1.1.2:5002?fcc=10.0.0.2:8027'
CH_OTHER_MC_SAME_FCC = 'rtp://239.1.1.3:5002?fcc=10.0.0.1:8027'
CH_NON_FCC = 'http://example.com/live.m3u8'


def test_first_fcc_channel_sends_join(sent):
    FCCService().on_channel_change(CH_A)
    assert sent == [
        {'fcc': ('10.0.0.1', 8027), 'leave': None, 'join': ('239.1.1.1', 5002)},
    ]


def test_switch_leaves_old_endpoint_then_joins_new_endpoint(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_channel_change(CH_B)

    assert len(sent) == 2
    # 1) LEAVE 必须发往旧端点（不能混用新端点）
    assert sent[0] == {
        'fcc': ('10.0.0.1', 8027),
        'leave': ('239.1.1.1', 5002),
        'join': None,
    }
    # 2) JOIN 发往新端点
    assert sent[1] == {
        'fcc': ('10.0.0.2', 8027),
        'leave': None,
        'join': ('239.1.1.2', 5002),
    }


def test_switch_same_endpoint_different_multicast(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_channel_change(CH_OTHER_MC_SAME_FCC)

    assert [c['leave'] for c in sent] == [('239.1.1.1', 5002), None]
    assert [c['join'] for c in sent] == [None, ('239.1.1.3', 5002)]
    assert all(c['fcc'] == ('10.0.0.1', 8027) for c in sent)


def test_switch_to_non_fcc_sends_leave_to_old_endpoint(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_channel_change(CH_NON_FCC)

    assert sent == [
        {'fcc': ('10.0.0.1', 8027), 'leave': ('239.1.1.1', 5002), 'join': None},
    ]


def test_same_channel_without_force_does_not_resend(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_channel_change(CH_A)

    assert sent == []


def test_same_channel_retry_force_resends_join(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_channel_change(CH_A, force=True)

    assert sent == [
        {'fcc': ('10.0.0.1', 8027), 'leave': None, 'join': ('239.1.1.1', 5002)},
    ]


def test_on_stop_sends_leave_and_clears_state(sent):
    service = FCCService()
    service.on_channel_change(CH_A)
    sent.clear()

    service.on_stop()

    assert sent == [
        {'fcc': ('10.0.0.1', 8027), 'leave': ('239.1.1.1', 5002), 'join': None},
    ]
    assert service._current_fcc is None
    assert service._current_multicast is None

    # 再次 stop 不应重复发送
    sent.clear()
    service.on_stop()
    assert sent == []


def test_on_stop_without_fcc_is_noop(sent):
    service = FCCService()
    service.on_channel_change(CH_NON_FCC)
    sent.clear()

    service.on_stop()

    assert sent == []


# ---------------------------------------------------------------------------
# 纯逻辑：不触碰真实 socket
# ---------------------------------------------------------------------------
def test_ipv6_endpoint_is_passed_through_without_brackets(monkeypatch):
    calls = []

    def fake_udp(ip, port, data, timeout=0.0):
        calls.append((ip, port, data))
        return True

    monkeypatch.setattr(fcc_service, '_send_udp', fake_udp)
    fcc_service.send_fcc_notification('2001:db8::1', 8027, join_addr=('239.1.1.1', 5002))

    assert calls == [('2001:db8::1', 8027, b'JOIN 239.1.1.1 5002\n')]


def test_m3u_parser_uses_authoritative_resolution():
    from services.m3u_parser import parse_m3u_content

    content = (
        '#EXTM3U\n'
        '#EXTINF:-1,A\n'
        'http://proxy/rtp/239.1.1.1:5002?token=x&FCC=1.2.3.4:8027\n'
        '#EXTINF:-1,B\n'
        'http://example.com/live.m3u8\n'
    )
    channels, _ = parse_m3u_content(content)

    assert channels[0]['fcc'] == '1.2.3.4:8027'
    assert not channels[1].get('fcc')
