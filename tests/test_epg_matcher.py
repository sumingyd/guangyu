"""EPG 频道匹配规则回归测试。

覆盖用户反馈的两类串台：
1. 吴江/靖江/镇江新闻综合 因"一字之差"被相似度兜底收敛到同一个 EPG 频道；
2. Astro AEC 在自己的 EPG 条目缺失时被相似度兜底顶到 Astro AOD。
"""

import pytest

from services.epg_matcher import EpgMatcher, _core_name


@pytest.fixture(autouse=True)
def _clear_matcher_cache():
    EpgMatcher.clear_cache()
    yield
    EpgMatcher.clear_cache()


EPG = {
    '吴江新闻综合': '吴江新闻综合',
    '湛江新闻综合': '湛江新闻综合',
    '镇江1': '镇江1',
    '镇江2': '镇江2',
    'Astro AEC': 'Astro AEC',
    'Astro AOD': 'Astro AOD',
    'CCTV1': 'CCTV-1',
    'CCTV5': 'CCTV-5',
    '湖南卫视': '湖南卫视',
}


def test_exact_id_wins_over_name():
    assert EpgMatcher.match('完全不同的名字', EPG, tvg_id='CCTV5') == 'CCTV5'


def test_name_exact_match():
    assert EpgMatcher.match('湖南卫视', EPG) == '湖南卫视'


def test_generic_suffix_stripped_but_keeps_city_core():
    # 南京新闻综合 -> 核心词 南京，要求整词相等；这里没有南京条目，必须留空
    assert EpgMatcher.match('南京新闻综合', EPG) is None


def test_different_cities_never_cross_match():
    """靖江/镇江 与湛江只差一个字，也不允许互相顶替。"""
    assert EpgMatcher.match('靖江新闻综合', EPG) is None
    assert EpgMatcher.match('镇江新闻综合', EPG) is None
    # 自己有条目时照常命中
    assert EpgMatcher.match('吴江新闻综合', EPG) == '吴江新闻综合'


def test_generic_words_alone_are_not_enough():
    for name in ('新闻综合', '综合', '新闻', '高清', 'HD', '4K', '频道', '电视台'):
        assert EpgMatcher.match(name, EPG) is None, name
        assert _core_name(name) == ''


def test_astro_aec_missing_must_not_fall_back_to_aod():
    epg = {k: v for k, v in EPG.items() if k != 'Astro AEC'}
    assert EpgMatcher.match('Astro AEC', epg) is None
    assert EpgMatcher.match('Astro AOD', epg) == 'Astro AOD'


def test_astro_hd_variant_matches_itself():
    assert EpgMatcher.match('Astro AEC HD', EPG) == 'Astro AEC'
    assert EpgMatcher.match('Astro AOD HD', EPG) == 'Astro AOD'


def test_containment_is_not_a_match():
    # 不允许 "包含即命中"：CCTV1 不能吃掉 CCTV10
    epg = {'CCTV10': 'CCTV-10'}
    assert EpgMatcher.match('CCTV1', epg) is None
    epg = {'湖南卫视': '湖南卫视'}
    assert EpgMatcher.match('湖南', epg) is None


def test_ambiguous_candidates_are_left_blank():
    epg = {'ID_A': '新闻综合', 'ID_B': '新闻综合'}
    assert EpgMatcher.match('新闻综合', epg) is None
    # 核心词歧义同样留空：两个 EPG 频道都剥离成"南京"
    epg = {'ID_A': '南京新闻综合', 'ID_B': '南京综合'}
    assert EpgMatcher.match('南京高清', epg) is None


def test_cctv_alias_table_still_works():
    epg = {'CCTV1': 'CCTV-1', 'CCTV5': 'CCTV-5'}
    assert EpgMatcher.match('央视一套', epg) == 'CCTV1'
    assert EpgMatcher.match('CCTV1综合', epg) == 'CCTV1'


def test_match_detail_reports_tier_and_display_name():
    """UI 信息弹窗依赖的匹配元数据：epg id / display-name / 命中层级。"""
    d = EpgMatcher.match_detail('完全不同的名字', EPG, tvg_id='CCTV5')
    assert d['matched'] is True
    assert d['epg_id'] == 'CCTV5'
    assert d['epg_name'] == 'CCTV-5'
    assert d['tier'] == 'tvg-id 精确'

    d = EpgMatcher.match_detail('湖南卫视', EPG)
    assert d['tier'] == '频道名精确'


def test_match_detail_unmatched_is_explicit():
    d = EpgMatcher.match_detail('靖江新闻综合', EPG)
    assert d['matched'] is False
    assert d['epg_id'] is None
    assert d['tier'] == '未匹配'
    assert EpgMatcher.match('靖江新闻综合', EPG) is None


def test_alias_table_backfills_only_existing_epg_ids():
    """人工别名表：命中记为"别名表"层级；登记的 id 不在当前 EPG 数据里时不得凭空命中。"""
    epg = {'临淄TV-1': '临淄TV-1'}
    d = EpgMatcher.match_detail('临淄综合', epg, tvg_id='临淄综合', tvg_name='临淄综合')
    assert d['epg_id'] == '临淄TV-1'
    assert d['tier'] == '别名表'

    assert EpgMatcher.match('临淄综合', {'其他频道': '其他频道'}) is None
