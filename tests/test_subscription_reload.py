from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import core.application_state as app_state_module
from controllers import subscription_controller as sub_module
from controllers.subscription_controller import SubscriptionController


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *args):
        for fn in list(self._slots):
            fn(*args)


class _FakeWorker:
    instances = []
    sources = []
    epg_sources = []

    def __init__(self, fn, parent=None):
        self.fn = fn
        self.finished = _Signal()
        self.error = _Signal()
        self.started = False
        _FakeWorker.instances.append(self)

    def start(self):
        self.started = True

    def deleteLater(self):
        pass


def _make():
    window = SimpleNamespace(
        language_manager=SimpleNamespace(tr=lambda _k, d='': d),
        status_bar_show_message=MagicMock(),
        _do_on_playlist_updated_in_main_thread=MagicMock(),
    )
    return SubscriptionController(window), window


@pytest.fixture(autouse=True)
def _patch_sources(monkeypatch):
    _FakeWorker.instances = []
    _FakeWorker.sources = []
    _FakeWorker.epg_sources = []
    monkeypatch.setattr(sub_module, 'SubscriptionWorker', _FakeWorker)
    monkeypatch.setattr(
        sub_module, 'global_subscription_manager',
        SimpleNamespace(
            get_playlist_sources=lambda: _FakeWorker.sources,
            get_epg_sources=lambda: _FakeWorker.epg_sources,
            update_playlist_source_last_update=lambda *a: None,
            is_epg_valid=lambda: True,
        )
    )


def test_reload_starts_single_sequential_worker():
    """手动重载只起一个 worker，按顺序处理全部源（不再并发 4 个）"""
    _FakeWorker.sources = [
        {'url': f'http://source{i}', 'name': f's{i}', 'enabled': True}
        for i in range(6)
    ]
    ctrl, window = _make()
    ctrl.restart_refresh_timers = MagicMock()
    ctrl.reload_subscription()

    assert len(_FakeWorker.instances) == 1
    assert _FakeWorker.instances[0].started
    window.status_bar_show_message.assert_called_once()


def test_refresh_sources_processes_enabled_in_order_and_aggregates():
    _FakeWorker.sources = [
        {'url': 'http://a', 'name': 'a', 'enabled': True},
        {'url': 'http://b', 'name': 'b', 'enabled': False},
        {'url': 'http://c', 'name': 'c', 'enabled': True},
    ]
    ctrl, _ = _make()
    order = []

    def fake_one(index, source, force, merged, headers):
        order.append((index, source['url'], force))
        merged.append({'url': f'http://ch{index}'})
        return 'ok'

    committed = []
    ctrl._refresh_one_source = fake_one
    ctrl._apply_subscription_block = lambda chans: committed.append(list(chans))

    result = ctrl._refresh_sources_blocking(force=False)

    assert order == [(0, 'http://a', False), (2, 'http://c', False)]
    assert result['stats']['ok'] == 2
    assert [c['url'] for c in result['channels']] == ['http://ch0', 'http://ch2']
    # 后台刷新只返回订阅块，不再在 worker 线程里直接提交
    assert committed == []


def test_refresh_with_only_url_targets_single_source_even_if_disabled():
    _FakeWorker.sources = [
        {'url': 'http://a', 'name': 'a', 'enabled': True},
        {'url': 'http://b', 'name': 'b', 'enabled': False},
    ]
    ctrl, _ = _make()
    order = []

    def fake_one(index, source, force, merged, headers):
        order.append((index, source['url'], force))
        return 'ok'

    ctrl._refresh_one_source = fake_one
    ctrl._apply_subscription_block = MagicMock()

    ctrl._refresh_sources_blocking(force=True, only_url='http://b')

    assert order == [(1, 'http://b', True)]


def test_no_channels_keeps_existing_list():
    """全部源失败/为空时不提交空列表，避免把已有频道洗掉"""
    _FakeWorker.sources = [{'url': 'http://a', 'name': 'a', 'enabled': True}]
    ctrl, _ = _make()
    ctrl._refresh_one_source = lambda *a: 'failed'
    ctrl._apply_subscription_block = MagicMock()

    result = ctrl._refresh_sources_blocking(force=True)

    assert result['stats']['failed'] == 1
    assert result['channels'] is None
    ctrl._apply_subscription_block.assert_not_called()


def test_refresh_one_source_respects_cache_when_not_forced():
    source = {'url': 'local.m3u', 'name': 'local'}
    ctrl, _ = _make()
    ctrl._should_update_source = lambda s, i: False
    ctrl._load_from_local_cache = MagicMock(return_value='#EXTM3U')
    ctrl._parse_m3u_content_pure_python = lambda content: ([{'url': 'http://x/1'}], {})
    ctrl._download_subscription_content = MagicMock()

    merged, headers = [], []
    assert ctrl._refresh_one_source(0, source, False, merged, headers) == 'ok'

    ctrl._download_subscription_content.assert_not_called()
    assert merged == [{'url': 'http://x/1', 'source': 'local.m3u'}]


def test_epg_timer_requires_channel_table(monkeypatch):
    """EPG 过滤依赖频道表：没有频道时不触发下载"""
    _FakeWorker.epg_sources = [{'url': 'http://epg', 'name': 'e'}]
    ctrl, _ = _make()
    ctrl._spawn_epg_refresh = MagicMock()
    monkeypatch.setattr(
        app_state_module, 'app_state', SimpleNamespace(channels=[]))

    ctrl._on_epg_timer()

    ctrl._spawn_epg_refresh.assert_not_called()


def test_epg_timer_skips_valid_cache(monkeypatch):
    _FakeWorker.epg_sources = [{'url': 'http://epg', 'name': 'e'}]
    ctrl, _ = _make()
    ctrl._spawn_epg_refresh = MagicMock()
    monkeypatch.setattr(
        app_state_module, 'app_state',
        SimpleNamespace(channels=[{'url': 'http://ch'}]))

    ctrl._on_epg_timer()  # is_epg_valid 为 True

    ctrl._spawn_epg_refresh.assert_not_called()


def test_should_update_source_honours_interval_with_tolerance(monkeypatch):
    """定时器整点触发、下载略晚完成时，下一周期仍应判定为过期（1 分钟容差）"""
    from datetime import datetime, timedelta

    ctrl, _ = _make()
    monkeypatch.setattr(
        sub_module, 'ConfigManager',
        lambda: SimpleNamespace(get_value=lambda *a: '30'))

    recent = {'url': 'http://a', 'last_update': (datetime.now() - timedelta(minutes=25)).isoformat()}
    almost = {'url': 'http://a', 'last_update': (datetime.now() - timedelta(minutes=29.5)).isoformat()}

    assert ctrl._should_update_source(recent, 0) is False
    assert ctrl._should_update_source(almost, 0) is True


def test_interval_save_restarts_timers_immediately():
    """设置页保存后立即重建定时器，不需要重启"""
    from controllers.settings_file_ops import SettingsFileOperations

    window = SimpleNamespace(subscription_ctrl=MagicMock())
    ops = SettingsFileOperations(window)

    ops._apply_refresh_interval_changes()

    window.subscription_ctrl.restart_refresh_timers.assert_called_once()


def test_epg_save_done_refreshes_epg_panel(monkeypatch):
    """设置页 EPG 源保存后立刻重绘节目单，不依赖播放中的 30 秒重绘"""
    import utils.thread_safety as thread_safety
    from controllers.settings_file_ops import SettingsFileOperations

    window = SimpleNamespace(
        subscription_ctrl=MagicMock(),
        _populate_epg_list=MagicMock(),
        status_bar_show_message=MagicMock(),
    )
    ops = SettingsFileOperations(window)
    monkeypatch.setattr(
        thread_safety, 'invoke_on_thread', lambda owner, cb: cb())

    ops._on_epg_reload_done('')
    window._populate_epg_list.assert_called_once()
    window.status_bar_show_message.assert_not_called()

    ops._on_epg_reload_done('EPG 下载失败: timeout')
    assert window._populate_epg_list.call_count == 2
    window.status_bar_show_message.assert_called_once()


def test_epg_timer_triggers_when_cache_invalid(monkeypatch):
    _FakeWorker.epg_sources = [{'url': 'http://epg', 'name': 'e'}]
    ctrl, _ = _make()
    ctrl._spawn_epg_refresh = MagicMock()
    monkeypatch.setattr(
        sub_module.global_subscription_manager,
        'is_epg_valid', lambda: False)
    monkeypatch.setattr(
        app_state_module, 'app_state',
        SimpleNamespace(channels=[{'url': 'http://ch'}]))

    ctrl._on_epg_timer()

    ctrl._spawn_epg_refresh.assert_called_once()
