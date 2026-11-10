"""EPG 流式解析与频道过滤的回归测试。"""

import gzip
import json
import threading

import pytest
import requests

import core.subscription_manager as sm_module
from core.application_state import app_state
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
    # 单飞相关状态（与 SubscriptionManager.__init__ 保持一致）
    obj._epg_load_lock = threading.Lock()
    obj._epg_download_entries = {}
    obj._epg_download_guard = threading.Lock()
    return obj


@pytest.fixture
def manager(monkeypatch):
    obj = _make_manager()

    def fake_get(url, **kwargs):
        raise AssertionError("测试用例必须自行替换 utils.http_session.get")

    monkeypatch.setattr("utils.http_session.get", fake_get)
    return obj


@pytest.fixture
def playlist(monkeypatch):
    """按用例设置频道表，并在用例结束后清空，避免污染单例状态"""
    original = app_state.channels
    app_state.channels = []
    try:
        yield app_state
    finally:
        app_state.channels = original


def _xmltv(channels, programmes):
    """channels: [(id, display_name)], programmes: [(channel, title, start, stop)]"""
    parts = ["<?xml version='1.0' encoding='utf-8'?>\n<tv>\n"]
    for cid, name in channels:
        parts.append(f'  <channel id="{cid}"><display-name>{name}</display-name></channel>\n')
    for cid, title, start, stop in programmes:
        parts.append(
            f'  <programme start="{start}" stop="{stop}" channel="{cid}">'
            f"<title>{title}</title></programme>\n"
        )
    parts.append("</tv>\n")
    return "".join(parts)


# ---------- 下载链路（保留既有覆盖） ----------

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


def test_valid_gzip_parses_and_clears_error(manager, monkeypatch, playlist):
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


# ---------- 流式解析 / 频道过滤 ----------

def test_programme_before_channel_is_parsed(manager, playlist):
    """programme 出现在 channel 之前时（两遍扫描）仍能正确解析。"""
    playlist.channels = [{"name": "顺序测试一台", "tvg_id": "ORDER1"}]
    content = (
        "<?xml version='1.0' encoding='utf-8'?>\n<tv>\n"
        '  <programme start="20261108200000 +0800" stop="20261108210000 +0800" channel="ORDER1">'
        "<title>先出现的节目</title></programme>\n"
        '  <channel id="ORDER1"><display-name>顺序测试一台</display-name></channel>\n'
        "</tv>\n"
    )

    data = manager._parse_xml_epg(content)

    assert data["ORDER1"][0]["title"] == "先出现的节目"
    assert manager._epg_channel_names["ORDER1"] == "顺序测试一台"


def test_filter_keeps_only_playlist_channels(manager, playlist):
    """频道表只含目标频道时，其他频道的节目应被过滤掉。"""
    playlist.channels = [{"name": "滤镜测试一台", "tvg_id": "FILTER1"}]
    content = _xmltv(
        [("FILTER1", "滤镜测试一台"), ("FILTER2", "滤镜测试二台")],
        [
            ("FILTER1", "保留节目", "20261108120000 +0800", "20261108130000 +0800"),
            ("FILTER2", "丢弃节目", "20261108120000 +0800", "20261108130000 +0800"),
        ],
    )

    data = manager._parse_xml_epg(content)

    assert set(data.keys()) == {"FILTER1"}
    assert data["FILTER1"][0]["title"] == "保留节目"
    assert "FILTER2" not in manager._epg_channel_names


def test_filter_falls_back_when_result_empty(manager, playlist, caplog):
    """命中频道没有任何节目时，必须回落到保留全部频道，避免 EPG 全空。"""
    playlist.channels = [{"name": "兜底测试九台", "tvg_id": "FALL9"}]
    content = _xmltv(
        [("FALL8", "兜底测试八台"), ("FALL9", "兜底测试九台")],
        [("FALL8", "兜底前节目", "20261108120000 +0800", "20261108130000 +0800")],
    )

    data = manager._parse_xml_epg(content)

    assert "FALL8" in data
    assert data["FALL8"][0]["title"] == "兜底前节目"
    assert any("回落" in record.message for record in caplog.records)
    assert any("因此未做过滤" in record.message for record in caplog.records)


def test_unmatched_channels_are_counted_and_logged(manager, playlist, caplog):
    """源里没有的频道要单独统计并列出名称。"""
    caplog.set_level("INFO")
    playlist.channels = [
        {"name": "苹果测试台", "tvg_id": "DIAG_NO_1"},
        {"name": "香蕉测试台", "tvg_id": "DIAG_NO_2"},
        {"name": "橘子测试台", "tvg_id": "DIAG_YES"},
    ]
    content = _xmltv(
        [("DIAG_YES", "橘子测试台")],
        [("DIAG_YES", "正常节目", "20261108120000 +0800", "20261108130000 +0800")],
    )

    manager._parse_xml_epg(content)

    messages = [record.message for record in caplog.records]
    assert any(
        "EPG匹配: 命中 1 / 无匹配 2 / 空节目 0（频道表共 3）" in m for m in messages
    )
    unmatched_line = next(m for m in messages if m.startswith("无匹配EPG的频道"))
    assert "苹果测试台" in unmatched_line and "香蕉测试台" in unmatched_line


def test_empty_programme_channels_are_counted_separately(manager, playlist, caplog):
    """匹配到 EPG 频道但该频道无节目，要计入“空节目”而不是“命中”。"""
    caplog.set_level("INFO")
    playlist.channels = [
        {"name": "空节目频道A", "tvg_id": "EMPTY_A"},
        {"name": "空节目频道B", "tvg_id": "EMPTY_B"},
    ]
    content = _xmltv(
        [("EMPTY_A", "空节目频道A"), ("EMPTY_B", "空节目频道B")],
        [("EMPTY_A", "只有A有节目", "20261108120000 +0800", "20261108130000 +0800")],
    )

    manager._parse_xml_epg(content)

    messages = [record.message for record in caplog.records]
    assert any(
        "EPG匹配: 命中 2 / 无匹配 0 / 空节目 1（频道表共 2）" in m for m in messages
    )
    empty_line = next(m for m in messages if m.startswith("空节目EPG的频道"))
    assert "空节目频道B" in empty_line
    assert "空节目频道A" not in empty_line


def test_channel_list_truncated_to_ten(manager, playlist, caplog):
    """无匹配列表最多 10 条，超出用“... 等 N 个”收尾。"""
    caplog.set_level("INFO")
    playlist.channels = [{"name": f"截断频道{i:02d}", "tvg_id": f"TRUNC_NO_{i}"} for i in range(12)]
    content = _xmltv([("TRUNC_YES", "截断源内频道")], [])

    manager._parse_xml_epg(content)

    messages = [record.message for record in caplog.records]
    unmatched_line = next(m for m in messages if m.startswith("无匹配EPG的频道"))
    assert "截断频道00" in unmatched_line
    assert "截断频道09" in unmatched_line
    assert "截断频道10" not in unmatched_line
    assert "... 等 12 个" in unmatched_line


def test_empty_playlist_reports_not_filtered(manager, playlist, caplog):
    """频道表为空时必须说明“因此未做过滤”，避免统计数字被误读。"""
    caplog.set_level("INFO")
    playlist.channels = []
    content = _xmltv(
        [("NF_1", "未过滤测试一台")],
        [("NF_1", "节目", "20261108120000 +0800", "20261108130000 +0800")],
    )

    manager._parse_xml_epg(content)

    messages = [record.message for record in caplog.records]
    assert any("EPG匹配: 命中 0 / 无匹配 0 / 空节目 0（频道表共 0）" in m for m in messages)
    assert any("频道表为空，因此未做过滤" in m for m in messages)



def test_filter_disabled_when_playlist_empty(manager, playlist):
    """频道表为空时不做过滤，保留全部频道。"""
    playlist.channels = []
    content = _xmltv(
        [("EMPTY1", "空表测试一台"), ("EMPTY2", "空表测试二台")],
        [
            ("EMPTY1", "节目A", "20261108120000 +0800", "20261108130000 +0800"),
            ("EMPTY2", "节目B", "20261108120000 +0800", "20261108130000 +0800"),
        ],
    )

    data = manager._parse_xml_epg(content)

    assert set(data.keys()) == {"EMPTY1", "EMPTY2"}


def test_truncated_xml_returns_empty_without_partial_data(manager, playlist):
    """截断/畸形 XML 不崩溃，也不能留下半截数据或频道名。"""
    playlist.channels = []
    content = (
        "<?xml version='1.0' encoding='utf-8'?>\n<tv>\n"
        '  <channel id="BROKEN1"><display-name>截断测试一台</display-name></channel>\n'
        '  <programme start="20261108120000 +0800" stop="20261108130000 +0800" channel="BROKEN1">'
        "<title>半截节目</title>\n"
    )

    data = manager._parse_xml_epg(content)

    assert data == {}
    assert manager._epg_channel_names == {}


def test_old_cache_format_is_readable(manager, monkeypatch, tmp_path):
    """旧缓存（无 channel_names 的裸字典）仍需可读，不能被判为损坏。"""
    monkeypatch.setattr(manager, "_get_cache_dir", lambda: str(tmp_path))
    legacy = {"LEGACY1": [{"title": "旧缓存节目", "desc": "", "start": "2026-11-08T12:00:00",
                           "end": "2026-11-08T13:00:00"}]}
    (tmp_path / "epg_cache.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    assert manager.load_cached_epg_data() is True
    assert manager.get_epg_data_copy()["LEGACY1"][0]["title"] == "旧缓存节目"


def test_new_cache_format_roundtrip(manager, monkeypatch, tmp_path):
    """新缓存格式（epg_data + channel_names）写后可读。"""
    monkeypatch.setattr(manager, "_get_cache_dir", lambda: str(tmp_path))
    manager._epg_data = {"ROUND1": [{"title": "往返节目", "desc": "", "start": "2026-11-08T12:00:00",
                                     "end": "2026-11-08T13:00:00"}]}
    manager._epg_channel_names = {"ROUND1": "往返测试一台"}

    manager._save_epg_cache(manager.get_epg_data_copy())

    manager._epg_data = {}
    manager._epg_channel_names = {}
    assert manager.load_cached_epg_data() is True
    assert manager.get_epg_channel_names()["ROUND1"] == "往返测试一台"


def test_corrupt_cache_does_not_crash(manager, monkeypatch, tmp_path):
    """损坏的缓存文件只返回 False，不得让启动失败。"""
    monkeypatch.setattr(manager, "_get_cache_dir", lambda: str(tmp_path))
    (tmp_path / "epg_cache.json").write_text("{not json", encoding="utf-8")

    assert manager.load_cached_epg_data() is False
