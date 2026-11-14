from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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

    def __init__(self, fn):
        self.fn = fn
        self.finished = _Signal()
        self.error = _Signal()
        self.started = False
        _FakeWorker.instances.append(self)

    def start(self):
        self.started = True

    def deleteLater(self):
        pass

    def finish(self, result='ok'):
        self.finished.emit(result)


def _make(sources):
    window = SimpleNamespace(
        language_manager=SimpleNamespace(tr=lambda _k, d='': d),
        status_bar_show_message=MagicMock(),
    )
    ctrl = SubscriptionController(window)
    ctrl._sources = sources
    return ctrl, window


@pytest.fixture(autouse=True)
def _patch_sources(monkeypatch):
    _FakeWorker.instances = []
    monkeypatch.setattr(sub_module, 'SubscriptionWorker', _FakeWorker)
    monkeypatch.setattr(
        sub_module, 'global_subscription_manager',
        SimpleNamespace(get_playlist_sources=lambda: _FakeWorker.sources)
    )


def test_concurrency_window_limits_started_workers():
    _FakeWorker.sources = [
        {'url': f'http://source{i}', 'enabled': True} for i in range(6)
    ]
    ctrl, _ = _make(_FakeWorker.sources)
    ctrl.reload_subscription()

    assert len(_FakeWorker.instances) == 4
    assert ctrl._reload_session['active'] == 4

    _FakeWorker.instances[0].finish('ok')
    assert len(_FakeWorker.instances) == 5
    assert ctrl._reload_session['active'] == 4


def test_reload_summary_classifies_results():
    _FakeWorker.sources = [
        {'url': 'http://a', 'enabled': True},
        {'url': 'http://b', 'enabled': True},
        {'url': 'http://c', 'enabled': True},
        {'url': 'http://d', 'enabled': True},
    ]
    ctrl, window = _make(_FakeWorker.sources)
    ctrl.reload_subscription()

    results = ['ok', 'empty', 'failed', 'ok']
    for worker, result in zip(list(_FakeWorker.instances), results):
        worker.finish(result)

    assert ctrl._reload_session is None
    window.status_bar_show_message.assert_called_once()
    message = window.status_bar_show_message.call_args[0][0]
    assert '成功' in message


def test_session_deadline_marks_pending_timeout():
    _FakeWorker.sources = [
        {'url': f'http://source{i}', 'enabled': True} for i in range(6)
    ]
    ctrl, window = _make(_FakeWorker.sources)
    ctrl.RELOAD_SESSION_DEADLINE_SEC = -1
    ctrl.reload_subscription()

    assert _FakeWorker.instances == []
    assert ctrl._reload_session is None
    assert window.status_bar_show_message.call_count == 1
