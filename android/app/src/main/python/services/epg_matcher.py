import re
import threading
import unicodedata
from collections import OrderedDict

try:
    from core.log_manager import global_logger as logger
except Exception:  # pragma: no cover - 日志模块不可用时退化为标准 logging
    import logging
    logger = logging.getLogger(__name__)

_MAX_CACHE_SIZE = 5000

# 通用缀词：剥离后仍必须保留至少一个区分性词（地名/品牌名）才允许判等。
# 顺序必须"长词优先"，否则"新闻综合"会被"综合"先吃掉一半。
_GENERIC_SUFFIXES = (
    '新闻综合', '综合频道', '新闻频道',
    '超高清', '高清', '标清',
    '综合', '新闻',
    '频道', '电视台',
    '体育赛事',
    'fhd', 'uhd', 'hd',
    '4k', '8k',
    '台',
)

# 剥离后不允许剩下这些"看起来像频道、其实没有区分度"的核心词
_USELESS_CORES = {'cctv', 'tv', 'hd', 'sd', 'cc', '频道', '电视台', '电视', '新闻', '综合', '台'}
# 剥离后仍只是通用词的组合，同样不允许作为判等依据
_GENERIC_CORES = _USELESS_CORES | {'新闻综合', '综合频道', '新闻频道', '高清', '超高清', '标清',
                                    'fhd', 'uhd', '4k', '8k'}

_COMMON_ALIASES = {
    'cctv1': 'CCTV-1 综合',
    'cctv2': 'CCTV-2 财经',
    'cctv3': 'CCTV-3 综艺',
    'cctv4': 'CCTV-4 中文国际',
    'cctv5': 'CCTV-5 体育',
    'cctv5plus': 'CCTV-5+ 体育赛事',
    'cctv6': 'CCTV-6 电影',
    'cctv7': 'CCTV-7 国防军事',
    'cctv8': 'CCTV-8 电视剧',
    'cctv9': 'CCTV-9 纪录',
    'cctv10': 'CCTV-10 科教',
    'cctv11': 'CCTV-11 戏曲',
    'cctv12': 'CCTV-12 社会与法',
    'cctv13': 'CCTV-13 新闻',
    'cctv14': 'CCTV-14 少儿',
    'cctv15': 'CCTV-15 音乐',
    'cctv16': 'CCTV-16 奥林匹克',
    'cctv17': 'CCTV-17 农业农村',

    'cctv4k': 'CCTV-4K 超高清',
}

_PINYIN_MAP = {
    '央视一套': 'CCTV-1 综合', '央视二套': 'CCTV-2 财经', '央视三套': 'CCTV-3 综艺',
    '央视四套': 'CCTV-4 中文国际', '央视五套': 'CCTV-5 体育', '央视六套': 'CCTV-6 电影',
    '央视七套': 'CCTV-7 国防军事', '央视八套': 'CCTV-8 电视剧', '央视九套': 'CCTV-9 纪录',
    '央视十套': 'CCTV-10 科教', '央视十一套': 'CCTV-11 戏曲', '央视十二套': 'CCTV-12 社会与法',
    '央视十三套': 'CCTV-13 新闻', '央视十四套': 'CCTV-14 少儿', '央视十五套': 'CCTV-15 音乐',
    '新闻频道': 'CCTV-13 新闻', '体育频道': 'CCTV-5 体育', '电影频道': 'CCTV-6 电影',
    '综艺频道': 'CCTV-3 综艺', '戏曲频道': 'CCTV-11 戏曲', '音乐频道': 'CCTV-15 音乐',
    '少儿频道': 'CCTV-14 少儿', '科教频道': 'CCTV-10 科教', '纪录频道': 'CCTV-9 纪录',
    '农业农村频道': 'CCTV-17 农业农村',
}


try:
    from services.epg_channel_aliases import CHANNEL_ALIASES as _CHANNEL_ALIASES
except Exception:  # pragma: no cover - 兼容以包内相对方式导入的场景
    try:
        from .epg_channel_aliases import CHANNEL_ALIASES as _CHANNEL_ALIASES
    except Exception:
        _CHANNEL_ALIASES = {}

# 匹配层级 -> 展示文案（UI 直接显示这一层，便于用户核对为什么是这条节目单）
_TIER_LABELS = {
    'tvg_id 精确': 'tvg-id 精确',
    'tvg_name 精确': 'tvg-name 精确',
    'comma_name 精确': '频道名（逗号后）精确',
    'channel_name 精确': '频道名精确',
    '归一化精确': '归一化精确',
    '别名表': '别名表',
    '核心词精确': '核心词精确',
}

_alias_lookup_cache = None


def _alias_lookup():
    """人工别名表（频道名 -> {epg_id, source, note}），按归一化名索引。"""
    global _alias_lookup_cache
    if _alias_lookup_cache is None:
        _alias_lookup_cache = {_normalize(k): v for k, v in _CHANNEL_ALIASES.items()}
    return _alias_lookup_cache


def _normalize(name):
    if not name:
        return ''
    name = unicodedata.normalize('NFKC', name)
    name = name.lower().strip()
    name = re.sub(r'(\d)\s*\+\s*', r'\1plus', name)
    name = re.sub(r'[\s\-_·.]+', '', name)
    name = name.replace('（', '(').replace('）', ')')
    name = name.replace('：', ':').replace('，', ',')
    name = re.sub(r'[()（）:：,，]', '', name)
    return name


def _core_name(name):
    """剥离通用缀词后的"区分性核心词"，无法得到有效核心时返回空串。

    只在核心词非空、且确实发生了剥离时才返回；这样：
    - 吴江新闻综合 -> 吴江，靖江新闻综合 -> 靖江，镇江新闻综合 -> 镇江（互不相等）
    - 新闻综合/高清/HD/4K 这类纯通用词 -> 空串（不允许作为唯一判等依据）
    - Astro AEC / Astro AOD 不含通用后缀，核心词就是全文（仍要求整词相等）
    """
    if not name:
        return ''
    norm = _normalize(name)
    if not norm:
        return ''
    core = norm
    stripped = False
    changed = True
    while changed:
        changed = False
        for token in _GENERIC_SUFFIXES:
            if not core.endswith(token) or len(core) <= len(token):
                continue
            rest = core[:-len(token)]
            # 纯数字/近似品牌缩写不剥离：CCTV4K 不能被剥成 cctv
            if not rest or rest.isdigit() or rest in _USELESS_CORES:
                continue
            core = rest
            stripped = True
            changed = True
            break
    if not stripped or core == norm:
        return ''
    if len(core) < 2 or core in _GENERIC_CORES:
        return ''
    return core


def _index_add(index, key, epg_id):
    """向索引写入 key -> epg_id；同一 key 命中不同 id 时记为歧义（元组）。"""
    if not key:
        return
    if key not in index:
        index[key] = epg_id
        return
    current = index[key]
    if isinstance(current, tuple):
        if epg_id not in current:
            index[key] = current + (epg_id,)
        return
    if current != epg_id:
        index[key] = (current, epg_id)


def _lookup(index, key):
    """返回 (命中的 epg_id, 歧义候选元组)。两者最多一个非空。"""
    if not key:
        return None, None
    value = index.get(key)
    if value is None:
        return None, None
    if isinstance(value, tuple):
        return None, value
    return value, None


class EpgMatcher:
    """EPG 频道匹配：只做精确/别名/核心词判等，不做相似度、包含、前缀匹配。"""

    _smart_cache: OrderedDict = OrderedDict()
    _cache_lock = threading.Lock()

    @classmethod
    def _build_index(cls, epg_channels):
        by_id = {}
        by_name = {}
        by_norm_name = {}
        by_core_name = {}
        display_names = {}
        if isinstance(epg_channels, dict):
            items = epg_channels.items()
        elif isinstance(epg_channels, list):
            items = []
            for item in epg_channels:
                if isinstance(item, dict):
                    items.append((item.get('id', ''), item.get('name', '')))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    items.append((item[0], item[1]))
        else:
            items = []
        for epg_id, epg_display_name in items:
            if not epg_id:
                continue
            by_id[epg_id] = epg_id
            display_names[epg_id] = epg_display_name or epg_id
            _index_add(by_name, epg_display_name, epg_id)
            _index_add(by_norm_name, _normalize(epg_display_name), epg_id)
            # 核心词索引同时收录"原始归一化名"和"剥离通用词后的核心"，
            # 这样 CCTV1综合(核心 cctv1) 能对上 EPG 的 CCTV-1(归一化 cctv1)，
            # 但匹配仍要求整词相等，不做任何模糊/包含。
            _index_add(by_core_name, _normalize(epg_display_name), epg_id)
            _index_add(by_core_name, _core_name(epg_display_name), epg_id)
        return by_id, by_name, by_norm_name, by_core_name, display_names

    @classmethod
    def _resolve_tier(cls, indexes):
        """在一个匹配层级内按优先级查找，返回 (epg_id, 歧义键, 歧义候选)。

        同层内任一候选出现歧义且没有唯一命中时，向上抛出歧义（宁可留空）。
        """
        ambiguous = None
        for index, key in indexes:
            hit, candidates = _lookup(index, key)
            if hit:
                return hit, None, None
            if candidates and ambiguous is None:
                ambiguous = (key, candidates)
        return None, (ambiguous[0] if ambiguous else None), (ambiguous[1] if ambiguous else None)

    @classmethod
    def match(cls, channel_name, epg_channels, tvg_id=None, tvg_name=None, comma_name=None):
        """兼容入口：只返回匹配到的 epg 频道 id（未匹配返回 None）。"""
        return cls.match_detail(
            channel_name, epg_channels, tvg_id=tvg_id, tvg_name=tvg_name, comma_name=comma_name
        ).get('epg_id')

    @classmethod
    def match_detail(cls, channel_name, epg_channels, tvg_id=None, tvg_name=None, comma_name=None):
        """返回匹配详情（供 UI 展示"匹配到哪个 EPG 源 / 哪个频道 / 走哪一级命中"）。

        Returns:
            {
              'matched': bool,      # 是否匹配到 EPG 频道
              'epg_id': str|None,   # 匹配到的 epg 频道 id
              'epg_name': str,      # epg 频道 display-name（取不到时回退 id）
              'tier': str,          # tvg-id 精确 / 归一化精确 / 别名表 / 核心词精确 / 未匹配
              'field': str,         # 命中的标识符字段
              'key': str,           # 命中的比较值
              'ambiguous': bool,    # 是否因歧义而留空
            }
        """
        if not channel_name and not tvg_id and not tvg_name and not comma_name:
            return cls._empty_detail()

        cache_key = (channel_name, tvg_id, tvg_name, comma_name)
        with cls._cache_lock:
            if cache_key in cls._smart_cache:
                cls._smart_cache.move_to_end(cache_key)
                return dict(cls._smart_cache[cache_key])

        by_id, by_name, by_norm_name, by_core_name, display_names = cls._build_index(epg_channels)

        # 标识符优先级：tvg-id > tvg-name > 逗号后名称 > 频道名
        identifiers = (
            ('tvg_id', tvg_id),
            ('tvg_name', tvg_name),
            ('comma_name', comma_name),
            ('channel_name', channel_name),
        )

        result = None
        tier = ''
        field_hit = ''
        key_hit = ''
        # 先记录歧义、继续尝试更严格的层级：显式别名表允许消解歧义，
        # 但核心词层级在存在歧义时不再尝试（宁可留空）。
        pending_ambiguous = None

        # 第 1 级：原始字符串精确（id 或显示名逐字符相等）
        for field, value in identifiers:
            if not value:
                continue
            hit, amb_key, amb_ids = cls._resolve_tier(
                ((by_id, value), (by_name, value))
            )
            if hit:
                result, tier, field_hit, key_hit = hit, f'{field} 精确', field, value
                break
            if amb_key and pending_ambiguous is None:
                pending_ambiguous = (amb_key, amb_ids, field)

        # 第 2 级：归一化后精确相等
        if result is None:
            norm_indexes = tuple(
                (by_norm_name, _normalize(value))
                for _, value in identifiers if value
            )
            hit, amb_key, amb_ids = cls._resolve_tier(norm_indexes)
            if hit:
                result, tier, field_hit = hit, '归一化精确', '归一化'
            elif amb_key and pending_ambiguous is None:
                pending_ambiguous = (amb_key, amb_ids, '归一化')

        # 第 3 级：严格别名表（人工维护白名单，可显式消解上一级的歧义）
        if result is None:
            alias_indexes = []
            for field, value in identifiers:
                if not value:
                    continue
                alias = _COMMON_ALIASES.get(_normalize(value))
                if alias:
                    alias_indexes.append((by_norm_name, _normalize(alias)))
                    if _core_name(alias):
                        alias_indexes.append((by_core_name, _core_name(alias)))
                pinyin_alias = _PINYIN_MAP.get(str(value).strip())
                if pinyin_alias:
                    alias_indexes.append((by_norm_name, _normalize(pinyin_alias)))
                    if _core_name(pinyin_alias):
                        alias_indexes.append((by_core_name, _core_name(pinyin_alias)))
                # 人工别名表：直接指定 epg 频道 id，且该 id 必须真实存在于当前 EPG 数据
                entry = _alias_lookup().get(_normalize(value))
                if entry:
                    alias_id = entry.get('epg_id')
                    if alias_id and alias_id in by_id:
                        alias_indexes.append((by_id, alias_id))
                        if not key_hit:
                            key_hit = alias_id
            hit, amb_key, amb_ids = cls._resolve_tier(alias_indexes)
            if hit:
                result, tier, field_hit = hit, '别名表', 'alias'
            elif amb_key and pending_ambiguous is None:
                pending_ambiguous = (amb_key, amb_ids, '别名表')

        # 第 4 级：剥离通用词后核心词整词相等（必须仍保留区分性词）
        if result is None and pending_ambiguous is None:
            core_indexes = tuple(
                (by_core_name, _core_name(value))
                for _, value in identifiers if _core_name(value)
            )
            hit, amb_key, amb_ids = cls._resolve_tier(core_indexes)
            if hit:
                result, tier, field_hit = hit, '核心词精确', '核心词'
            elif amb_key:
                pending_ambiguous = (amb_key, amb_ids, '核心词')

        return cls._finish(
            cache_key, result, channel_name, tvg_id, tvg_name, comma_name,
            tier=tier, ambiguous=pending_ambiguous,
            display_name=display_names.get(result, result) if result else '',
            field=field_hit, key=key_hit,
        )

    @staticmethod
    def _empty_detail():
        return {
            'matched': False, 'epg_id': None, 'epg_name': '', 'tier': '未匹配',
            'field': '', 'key': '', 'ambiguous': False,
        }

    @classmethod
    def _finish(cls, cache_key, result, channel_name, tvg_id, tvg_name, comma_name,
                tier='', ambiguous=None, display_name='', field='', key=''):
        if ambiguous:
            amb_key, candidates, level = ambiguous
            logger.debug(
                f"EPG匹配歧义未匹配: channel={channel_name!r} tvg_id={tvg_id!r} "
                f"tvg_name={tvg_name!r} comma_name={comma_name!r} "
                f"层级={level} key={amb_key!r} 候选={list(candidates)!r}"
            )
        else:
            logger.debug(
                f"EPG匹配: channel={channel_name!r} tvg_id={tvg_id!r} "
                f"tvg_name={tvg_name!r} comma_name={comma_name!r} "
                f"-> epg_id={result!r}" + (f" via {tier}" if result else " via 未匹配")
            )
        detail = {
            'matched': bool(result),
            'epg_id': result,
            'epg_name': display_name or (result or ''),
            'tier': _TIER_LABELS.get(tier, tier) if result else '未匹配',
            'field': field,
            'key': key,
            'ambiguous': bool(ambiguous),
        }
        with cls._cache_lock:
            if len(cls._smart_cache) >= _MAX_CACHE_SIZE:
                cls._smart_cache.popitem(last=False)
            cls._smart_cache[cache_key] = detail
        return detail

    @classmethod
    def clear_cache(cls):
        with cls._cache_lock:
            cls._smart_cache.clear()
