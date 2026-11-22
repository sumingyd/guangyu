"""扫描列表的「只看有效」筛选。"""
from models.channel_model import ChannelListModel
from services.validity_tiers import INVALID, SUSPECTED, VALID


def _model(channels):
    model = ChannelListModel()
    model.channels = channels
    return model


def test_hide_invalid_keeps_only_confirmed_channels():
    model = _model([
        {'url': 'a', 'validity': VALID},
        {'url': 'b', 'validity': SUSPECTED},
        {'url': 'c', 'validity': INVALID},
        {'url': 'd'},                      # 未检测
        {'url': 'e', 'valid': True},       # 老缓存：布尔有效
        {'url': 'f', 'valid': False},      # 老缓存：布尔无效
    ])

    model.hide_invalid()

    assert [c['url'] for c in model.channels] == ['a', 'e']
    assert model._is_hiding_invalid is True


def test_show_all_restores_every_tier():
    model = _model([
        {'url': 'a', 'validity': VALID},
        {'url': 'b', 'validity': SUSPECTED},
        {'url': 'c', 'validity': INVALID},
    ])

    model.hide_invalid()
    model.show_all()

    assert [c['url'] for c in model.channels] == ['a', 'b', 'c']
    assert model._is_hiding_invalid is False


def test_clear_discards_filter_snapshot():
    model = _model([{'url': 'a', 'validity': VALID}, {'url': 'b', 'validity': SUSPECTED}])

    model.hide_invalid()
    model.clear()
    model.show_all()

    assert model.channels == []
    assert model._is_hiding_invalid is False
