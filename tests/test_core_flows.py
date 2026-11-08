"""核心链路测试：换台、断点续播、配置读写、订阅解析。

这些测试针对真实实现做行为断言，并且每一条都可以通过改坏对应实现而变红，
用于防止"核心逻辑被改坏但测试仍全绿"。
"""

import json
import os
import sys
import threading

from tests.qt_stub import ensure_qt_available

ensure_qt_available()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.event_handler import EventHandler
from core.config_manager import ConfigManager
from core import config_manager as config_manager_module
from core.stores.resume_store import ResumeStore
from services.m3u_parser import parse_m3u_content


# ---------------------------------------------------------------- 换台

class FakeChannelList:
    def __init__(self, items, row=0):
        self._items = list(items)
        self._row = row

    def count(self):
        return len(self._items)

    def currentRow(self):
        return self._row

    def setCurrentRow(self, row):
        self._row = row

    def currentItem(self):
        if 0 <= self._row < len(self._items):
            return self._items[self._row]
        return None


class FakeWindow:
    def __init__(self, channel_list):
        self.active_channel_list = channel_list
        self.channel_list = channel_list
        self.fav_channel_list = None
        self.history_channel_list = None
        self.favorites_ctrl = None
        self.selected = []

    def select_channel(self, item, source_list=None):
        self.selected.append((item, source_list))


def test_switch_channel_wraps_in_both_directions():
    channel_list = FakeChannelList(['a', 'b', 'c'], row=2)
    window = FakeWindow(channel_list)
    handler = EventHandler(window)

    handler._switch_channel(1)
    assert channel_list.currentRow() == 0
    assert window.selected[-1][0] == 'a'

    handler._switch_channel(-1)
    assert channel_list.currentRow() == 2
    assert window.selected[-1][0] == 'c'


def test_switch_channel_without_selection_starts_at_edge():
    channel_list = FakeChannelList(['a', 'b', 'c'], row=-1)
    window = FakeWindow(channel_list)
    handler = EventHandler(window)

    handler._switch_channel(1)
    assert channel_list.currentRow() == 0
    assert window.selected[-1][0] == 'a'

    channel_list._row = -1
    handler._switch_channel(-1)
    assert channel_list.currentRow() == 2
    assert window.selected[-1][0] == 'c'


def test_switch_channel_empty_list_does_nothing():
    channel_list = FakeChannelList([], row=-1)
    window = FakeWindow(channel_list)
    handler = EventHandler(window)

    handler._switch_channel(1)

    assert channel_list.currentRow() == -1
    assert window.selected == []


# ---------------------------------------------------------------- 断点续播

class FakeFacade:
    def __init__(self):
        self._lock = threading.RLock()


def test_resume_position_saved_and_persisted(tmp_path):
    resume_file = str(tmp_path / 'resume_positions.json')
    facade = FakeFacade()
    store = ResumeStore(facade, resume_file)

    store.save_resume_position('http://vod/a.mkv', 42.5, 600.0, '影片A')

    entry = store.load_resume_position('http://vod/a.mkv')
    assert entry is not None
    assert entry['position'] == 42.5
    assert entry['duration'] == 600.0
    assert entry['name'] == '影片A'

    assert os.path.exists(resume_file)
    with open(resume_file, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['http://vod/a.mkv']['position'] == 42.5

    # 新实例从磁盘重新读取（进程重启后的续播依据）
    reloaded = ResumeStore(FakeFacade(), resume_file)
    assert reloaded.load_resume_position('http://vod/a.mkv')['position'] == 42.5


def test_resume_position_ignores_too_early_and_drops_finished(tmp_path):
    resume_file = str(tmp_path / 'resume_positions.json')
    store = ResumeStore(FakeFacade(), resume_file)

    # 播到开头 3 秒不记录断点
    store.save_resume_position('http://vod/early.mkv', 3.0, 600.0)
    assert store.load_resume_position('http://vod/early.mkv') is None

    # 已接近结尾视为播完，不应留下断点
    store.save_resume_position('http://vod/finished.mkv', 100.0, 600.0)
    assert store.load_resume_position('http://vod/finished.mkv') is not None
    store.save_resume_position('http://vod/finished.mkv', 599.0, 600.0)
    assert store.load_resume_position('http://vod/finished.mkv') is None


def test_resume_clear_position(tmp_path):
    resume_file = str(tmp_path / 'resume_positions.json')
    store = ResumeStore(FakeFacade(), resume_file)
    store.save_resume_position('http://vod/a.mkv', 30.0, 600.0)

    store.clear_resume_position('http://vod/a.mkv')

    assert store.load_resume_position('http://vod/a.mkv') is None


# ---------------------------------------------------------------- 配置读写

def _make_sandbox_config(monkeypatch, config_dir):
    monkeypatch.setattr(config_manager_module, 'get_config_dir', lambda: str(config_dir))
    monkeypatch.setattr(config_manager_module, 'migrate_legacy_data', lambda **kwargs: [])
    ConfigManager.reset_instance()
    return ConfigManager()


def test_config_write_then_reload(tmp_path, monkeypatch):
    try:
        config = _make_sandbox_config(monkeypatch, tmp_path)
        config.set_value('Player', 'volume', '35')
        assert config.save_config(immediate=True) is True

        config_path = tmp_path / 'config.ini'
        assert config_path.exists()
        assert 'volume = 35' in config_path.read_text(encoding='utf-8')

        # 模拟重启：重新构造单例并从磁盘读取
        ConfigManager.reset_instance()
        reloaded = _make_sandbox_config(monkeypatch, tmp_path)
        assert reloaded.get_value('Player', 'volume') == '35'
        assert reloaded.get_value('Player', 'missing_key', 'fallback') == 'fallback'
    finally:
        ConfigManager.reset_instance()


def test_server_auto_start_defaults_off_when_key_missing(tmp_path, monkeypatch):
    """配置里没有 [Server] 键时，HTTP 服务器必须默认关闭。"""
    try:
        config = _make_sandbox_config(monkeypatch, tmp_path)
        settings = config.load_server_settings()
        assert settings['auto_start'] is False
        assert settings['enabled'] is False
    finally:
        ConfigManager.reset_instance()


def test_server_auto_start_explicit_true_kept_after_reload(tmp_path, monkeypatch):
    """老配置里显式写入 True 时必须保持开启，不被新默认值覆盖。"""
    try:
        config = _make_sandbox_config(monkeypatch, tmp_path)
        config.save_server_settings(enabled=True, port=9091, host='127.0.0.1', auto_start=True)
        config.flush()

        ConfigManager.reset_instance()
        reloaded = _make_sandbox_config(monkeypatch, tmp_path)
        settings = reloaded.load_server_settings()
        assert settings['auto_start'] is True
        assert settings['enabled'] is True
        assert settings['port'] == 9091
        assert settings['host'] == '127.0.0.1'
    finally:
        ConfigManager.reset_instance()


# ---------------------------------------------------------------- 订阅解析

M3U_SAMPLE = '''#EXTM3U x-tvg-url="http://epg.example/e.xml" catchup-days="2"
#EXTINF:-1 tvg-id="cctv1" tvg-name="CCTV1" tvg-logo="http://logo.example/1.png" group-title="央视;高清",CCTV-1 综合
http://example.com/cctv1.m3u8
#EXTINF:-1 group-title="卫视",湖南卫视
http://example.com/hunan.m3u8
#EXTINF:-1,占位频道
http://0/0.m3u8
'''


def test_parse_m3u_extracts_channel_attributes():
    channels, header = parse_m3u_content(M3U_SAMPLE)

    assert len(channels) == 2
    first = channels[0]
    assert first['name'] == 'CCTV-1 综合'
    assert first['tvg_id'] == 'cctv1'
    assert first['logo'] == 'http://logo.example/1.png'
    assert first['group'] == '央视'
    assert first['_groups'] == ['央视', '高清']
    assert first['url'] == 'http://example.com/cctv1.m3u8'
    assert first['catchup_days'] == '2'
    assert header['epg_url'] == 'http://epg.example/e.xml'

    second = channels[1]
    assert second['name'] == '湖南卫视'
    assert second['group'] == '卫视'


def test_parse_m3u_skips_invalid_urls_and_keeps_ids():
    channels, _ = parse_m3u_content(M3U_SAMPLE)

    assert all(ch['url'] != 'http://0/0.m3u8' for ch in channels)
    assert [ch['id'] for ch in channels] == [1, 2]
