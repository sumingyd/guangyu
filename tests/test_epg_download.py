"""EPG 下载链路的回归测试：体积上限、失败原因可观测性。"""

import gzip
import threading

import pytest
import requests

import core.subscription_manager as sm_module
from core.subscription_manager import SubscriptionManager

XMLTV = (
    "<?xml version='1.0' encoding='utf-8'?>\n"
    "<tv>\n"
    "  <channel id=\"CCTV1\"><display-name>CCTV-1</display-name></channel>\n"
    "  <programme start=\"20261108120000 +0800\" stop=\"20261108130000 +0800\" channel=\"CCTV1\">\n"
    "    <title>新闻联播</title>\n"
    "  </programme>\n"
    "</tv>\n"
)


class _FakeResponse:
    def __init__(self, chunks, headers=None):
        self._chunks = chunks
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        return iter(self._chunks)


def _make_manager():
    obj = object.__new__(SubscriptionManager)
    obj._epg_data = {}
    obj._epg_channel_names = {}
    obj._epg_lock = threading.RLock()
    obj._last_epg_error = ''
    obj._last_epg_update = None
    return obj


@pytest.fixture
def manager(monkeypatch):
    obj = _make_manager()

    def fake_get(url, **kwargs):
        raise AssertionError("测试用例必须自行替换 utils.http_session.get")

    monkeypatch.setattr("utils.http_session.get", fake_get)
    return obj


def test_gz_over_limit_reports_size_reason(manager, monkeypatch):
    """解压后超过上限时必须返回失败原因，而不是静默返回空字典。"""
    monkeypatch.setattr(sm_module, "EPG_MAX_BYTES", 1024)
    monkeypatch.setattr(sm_module, "EPG_MAX_MB", 0)
    payload = gzip.compress(("<tv>" + "x" * 4096 + "</tv>").encode("utf-8"))
    monkeypatch.setattr(
        "utils.http_session.get",
        lambda url, **kw: _FakeResponse([payload], {"Content-Length": str(len(payload))}),
    )

    result = manager._load_single_epg("https://example.com/epg.xml.gz")

    assert result == {}
    assert "解压后" in manager._last_epg_error
    assert "上限" in manager._last_epg_error


def test_http_404_reports_status_without_retry(manager, monkeypatch):
    """4xx 不重试，且失败原因要带 HTTP 状态码。"""
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        resp = requests.Response()
        resp.status_code = 404
        raise requests.exceptions.HTTPError("404 Client Error", response=resp)

    monkeypatch.setattr("utils.http_session.get", fake_get)

    result = manager._load_single_epg("https://example.com/missing.xml")

    assert result == {}
    assert manager._last_epg_error == "请求返回 HTTP 404"
    assert len(calls) == 1


def test_timeout_reports_reason(manager, monkeypatch):
    def fake_get(url, **kwargs):
        raise requests.exceptions.ConnectTimeout("connect timed out")

    monkeypatch.setattr("utils.http_session.get", fake_get)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    result = manager._load_single_epg("https://example.com/slow.xml")

    assert result == {}
    assert "超时" in manager._last_epg_error


def test_valid_gzip_parses_and_clears_error(manager, monkeypatch):
    payload = gzip.compress(XMLTV.encode("utf-8"))
    monkeypatch.setattr(
        "utils.http_session.get",
        lambda url, **kw: _FakeResponse([payload[:10], payload[10:]], {"Content-Length": str(len(payload))}),
    )

    data = manager._load_single_epg("https://example.com/epg.xml.gz")

    assert "CCTV1" in data
    assert data["CCTV1"][0]["title"] == "新闻联播"
    assert manager._last_epg_error == ""


def test_empty_content_reports_reason(manager, monkeypatch):
    monkeypatch.setattr(
        "utils.http_session.get",
        lambda url, **kw: _FakeResponse([b""], {"Content-Length": "0"}),
    )

    result = manager._load_single_epg("https://example.com/empty.xml")

    assert result == {}
    assert manager._last_epg_error == "下载内容为空"


def test_load_all_surfaces_failure_reason(manager):
    """全部源失败时，status_callback 必须带出真实原因。"""
    manager.get_epg_sources = lambda: [{"url": "https://example.com/epg.xml.gz", "name": "EPG 1"}]

    def fake_load(url):
        manager._last_epg_error = "解压后120.0MB，超过256MB上限"
        return {}

    manager._load_single_epg = fake_load
    messages = []

    assert manager.load_all_epg_data(messages.append) is False
    assert any("解压后120.0MB" in m for m in messages)
