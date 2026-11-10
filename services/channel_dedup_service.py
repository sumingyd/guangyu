from typing import Dict, Any, List, Tuple
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit
from core.log_manager import global_logger as logger


def normalize_stream_url(url: str) -> str:
    """归一化播放地址，用于判断两个频道是否指向同一路流。

    只做不改变流身份的归一化：
    - 去掉首尾空白、行尾逗号，以及 `$` 之后的重定向/附加后缀（与 m3u_parser 一致）
    - 协议与主机名小写、去掉 URL 片段
    路径与查询参数（如 `fcc=`）原样保留：它们参与流地址，改了就不是同一路流。
    """
    if not url:
        return ''
    u = str(url).strip()
    if '$' in u:
        u = u.split('$', 1)[0]
    u = u.rstrip(',').strip()
    if not u:
        return ''
    try:
        parts = urlsplit(u)
    except ValueError:
        return u.lower()
    if not parts.scheme or not parts.netloc:
        return u.lower()
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ''))


class ChannelDedupService:
    def __init__(self, name_threshold: float = 0.8, url_similarity: bool = True):
        self._name_threshold = name_threshold
        # 保留该参数兼容旧调用方；名称相似度已不参与去重判定
        self._url_similarity = url_similarity

    def find_duplicates(self, channels: List[Dict[str, Any]]) -> List[Tuple[int, int, float, str]]:
        """返回重复频道对 [(i, j, score, reason)]。

        去重口径：同一路流只保留一条。只有归一化后播放地址完全相同的频道
        才算重复；名称相同但地址不同（不同分辨率/码流/线路）不返回。
        """
        url_groups = {}
        for i, ch in enumerate(channels):
            key = normalize_stream_url(ch.get('url', ''))
            if key:
                url_groups.setdefault(key, []).append(i)

        results = []
        for indices in url_groups.values():
            if len(indices) < 2:
                continue
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    results.append((indices[a], indices[b], 1.0, 'url_exact'))

        results.sort(key=lambda x: x[0])
        return results

    def find_similar_names(self, channels: List[Dict[str, Any]]) -> List[Tuple[int, int, float, str]]:
        """名称相近且播放地址不同的频道对，仅用于提示，不参与删除/合并。

        同名但地址不同的频道通常是同一频道的多路流（高清/标清），应当各自保留，
        这里只给出“疑似同一频道”的参考信息。
        """
        results = []
        name_groups = {}
        for i, ch in enumerate(channels):
            name = str(ch.get('name', '')).strip().lower()
            if name:
                key = name[:3] if len(name) >= 3 else name
                name_groups.setdefault(key, []).append(i)

        for indices in name_groups.values():
            if len(indices) < 2:
                continue
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    i, j = indices[a], indices[b]
                    if (normalize_stream_url(channels[i].get('url', '')) ==
                            normalize_stream_url(channels[j].get('url', ''))):
                        # 地址相同已由 find_duplicates 覆盖，不再重复提示
                        continue
                    score = self._name_similarity(channels[i], channels[j])
                    if score >= self._name_threshold:
                        results.append((i, j, score, 'name_similar'))

        results.sort(key=lambda x: x[2], reverse=True)
        return results

    def _name_similarity(self, ch1: Dict[str, Any], ch2: Dict[str, Any]) -> float:
        name1 = str(ch1.get('name', '')).strip().lower()
        name2 = str(ch2.get('name', '')).strip().lower()
        if not name1 or not name2:
            return 0.0
        return SequenceMatcher(None, name1, name2).ratio()

    def deduplicate(self, channels: List[Dict[str, Any]],
                    strategy: str = 'keep_first') -> List[Dict[str, Any]]:
        """按播放地址去重：归一化地址相同的才算重复。

        - 保留原有顺序与首个出现位置（收藏/频道号/自定义排序不受影响；
          收藏按 URL 存储时，地址相同的重复项会自动指向保留下来的那条）
        - 同名但地址不同的频道（不同分辨率/码流）全部保留
        - 被删条目的非空元数据会补齐到保留条目上，避免丢 logo/回看/tvg 信息
        """
        duplicates = self.find_duplicates(channels)
        remove_indices = set()
        for i, j, _score, _reason in duplicates:
            if strategy == 'keep_last':
                keep, drop = j, i
            elif strategy == 'keep_shorter_url':
                url_i = channels[i].get('url', '')
                url_j = channels[j].get('url', '')
                keep, drop = (i, j) if len(url_i) <= len(url_j) else (j, i)
            else:
                keep, drop = i, j
            if keep in remove_indices or drop in remove_indices:
                continue
            remove_indices.add(drop)
            self._fill_missing(channels[keep], channels[drop])

        result = [ch for idx, ch in enumerate(channels) if idx not in remove_indices]
        logger.info(f"频道去重(按播放地址): 原始{len(channels)}个, 移除{len(remove_indices)}个重复, 保留{len(result)}个")
        return result

    @staticmethod
    def _fill_missing(kept: Dict[str, Any], other: Dict[str, Any]) -> None:
        """把 other 中保留条目缺失的元数据补齐（不改动地址/名称/序号）"""
        for key in ('logo', 'logo_url', 'tvg_id', 'tvg_name', 'resolution',
                    'group', '_groups', 'catchup', 'catchup_days',
                    'catchup_source', 'catchup_correction', 'fcc'):
            if not kept.get(key) and other.get(key):
                val = other[key]
                kept[key] = list(val) if isinstance(val, list) else val

    def merge_duplicates(self, channels: List[Dict[str, Any]],
                         pairs: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        merged_indices = set()
        result = list(channels)
        for i, j in pairs:
            if i in merged_indices or j in merged_indices:
                continue
            ch1 = result[i]
            ch2 = result[j]
            merged = dict(ch1)
            for key in ('logo', 'logo_url', 'tvg_id', 'group', '_groups', 'catchup', 'catchup_days', 'catchup_source'):
                if not merged.get(key) and ch2.get(key):
                    val = ch2[key]
                    merged[key] = list(val) if isinstance(val, list) else val
            result[i] = merged
            merged_indices.add(j)
        result = [ch for idx, ch in enumerate(result) if idx not in merged_indices]
        return result
