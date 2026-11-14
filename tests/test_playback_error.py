import pytest

from utils.playback_error import classify_playback_error


@pytest.mark.parametrize(
    "message, expected_key",
    [
        ("HTTP 403 Forbidden", "error_play_auth"),
        ("401 Unauthorized: token expired", "error_play_auth"),
        ("HTTP 404 Not Found", "error_play_expired"),
        ("读取超时 timed out", "error_play_network"),
        ("getaddrinfo failed: name resolution", "error_play_network"),
        ("audio decoder failure: mp2", "error_play_audio"),
        ("mediacodec init failed", "error_play_decode"),
        ("PARSING_CONTAINER_UNSUPPORTED", "error_play_format"),
        ("DRM license unavailable", "error_play_drm"),
        ("something odd happened", "error_play_generic"),
        ("", "error_play_generic"),
    ],
)
def test_classify_playback_error(message, expected_key):
    key, default = classify_playback_error(message)
    assert key == expected_key
    assert default


def test_dead_local_proxy_detection():
    requests = pytest.importorskip("requests")
    from utils import http_session

    refused = requests.exceptions.ProxyError(
        "Unable to connect to proxy 127.0.0.1:7890: "
        "ConnectionRefusedError(10061, '由于目标计算机积极拒绝，无法连接。')"
    )
    assert http_session._is_dead_local_proxy_error(refused) is True

    linux_refused = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='localhost', port=7890): "
        "[Errno 111] Connection refused"
    )
    assert http_session._is_dead_local_proxy_error(linux_refused) is True

    # 远端域名解析失败不是「本地代理已死」，不能自动改直连
    remote = requests.exceptions.ConnectionError("getaddrinfo failed for example.com")
    assert http_session._is_dead_local_proxy_error(remote) is False
