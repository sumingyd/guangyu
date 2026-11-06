import re
from typing import List, Tuple, Generator
from core.log_manager import global_logger


class URLRangeParser:
    # 单条 URL 允许展开的最大数量，防止 [1-999999999] 之类表达式耗尽内存
    MAX_EXPAND_COUNT = 200000

    def __init__(self):
        self.logger = global_logger
        # 范围定义：[1-255] 或 [1-255:n]（命名变量 n，可被 {n} 引用并同步变化）
        # 第 1 组=范围表达式，第 2 组=可选变量名（字母/下划线开头）
        self.range_pattern = re.compile(
            r'\[(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)(?::([a-zA-Z_][a-zA-Z0-9_]*))?\]'
        )
        # IPv6 地址（避免误匹配其方括号）
        self.ipv6_pattern = re.compile(r'\[[a-fA-F0-9]*(?::[a-fA-F0-9]*){2,}(?:%[a-zA-Z0-9_]+)?\]')
        # 变量引用：{name} —— 与 [range:name] 定义处同步变化
        self.ref_pattern = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

    def _parse_segment(self, segment: str) -> List[Tuple[int, int, int]]:
        results = []
        if '-' in segment:
            parts = segment.split('-')
            start = int(parts[0])
            end = int(parts[1])
            if start > end:
                start, end = end, start
            zero_pad = len(parts[0])
            results.append((start, end, zero_pad))
        else:
            val = int(segment)
            zero_pad = len(segment)
            results.append((val, val, zero_pad))
        return results

    def _parse_bracket_content(self, content: str) -> Tuple[List[Tuple[int, int, int]], int]:
        all_values = []
        first_pad = None
        for segment in content.split(','):
            segment = segment.strip()
            if not segment:
                continue
            parsed = self._parse_segment(segment)
            all_values.extend(parsed)
            if first_pad is None:
                first_pad = parsed[0][2]
        return all_values, first_pad or 1

    def _count_range_size(self, parsed_segments) -> int:
        total = 0
        seen_ranges = set()
        for start, end, _ in parsed_segments:
            if (start, end) in seen_ranges:
                continue
            seen_ranges.add((start, end))
            total += (end - start + 1)
        return total

    def _iter_range_values(self, parsed_segments, pad_width: int) -> Generator[str, None, None]:
        seen = set()
        for start, end, _ in parsed_segments:
            for num in range(start, end + 1):
                if num not in seen:
                    seen.add(num)
                    yield str(num).zfill(pad_width)

    def _create_range_iterator(self, parsed_segments, pad_width: int):
        class RangeIterator:
            def __init__(self, segments, pad):
                self.segments = segments
                self.pad = pad
                self.seg_idx = 0
                self.current = None
                self.end = None
                self.needs_dedup = len(segments) > 1
                self.seen = set() if self.needs_dedup else None
                self._advance_segment()

            def _advance_segment(self):
                while self.seg_idx < len(self.segments):
                    start, end, _ = self.segments[self.seg_idx]
                    self.current = start
                    self.end = end
                    self.seg_idx += 1
                    if not self.needs_dedup or self.current not in self.seen:
                        return
                self.current = None

            def __iter__(self):
                return self

            def __next__(self):
                while self.current is not None:
                    val = self.current
                    if not self.needs_dedup or val not in self.seen:
                        if self.needs_dedup:
                            self.seen.add(val)
                        result = str(val).zfill(self.pad)
                        self.current += 1
                        if self.current > self.end:
                            self._advance_segment()
                        return result
                    self.current += 1
                    if self.current > self.end:
                        self._advance_segment()
                raise StopIteration

            def reset(self):
                self.seg_idx = 0
                self.current = None
                self.end = None
                if self.needs_dedup:
                    self.seen = set()
                self._advance_segment()

        return RangeIterator(parsed_segments, pad_width)

    def _find_valid_ranges(self, url):
        """找出所有有效的范围定义 match（排除 IPv6 方括号）。"""
        ipv6_spans = [m.span() for m in self.ipv6_pattern.finditer(url)]
        valid_ranges = []
        for match in self.range_pattern.finditer(url):
            match_start, match_end = match.span()
            if not any(ipv6_start <= match_start and match_end <= ipv6_end
                       for ipv6_start, ipv6_end in ipv6_spans):
                valid_ranges.append(match)
        return valid_ranges

    def _find_all_slots(self, url):
        """找出 URL 中所有可替换位置（范围定义 + 已定义的变量引用），按位置排序。

        - 范围定义 [1-255] / [1-255:n] 始终作为 slot
        - 变量引用 {name} 仅在存在对应的 [range:name] 定义时才作为 slot
          （否则保留为字面量，避免破坏 URL 中本身出现的 {xxx} 字符）
        """
        ipv6_spans = [m.span() for m in self.ipv6_pattern.finditer(url)]

        # 第一步：收集所有范围定义，并记录已定义的变量名
        defined_names = set()
        range_slots = []
        for match in self.range_pattern.finditer(url):
            match_start, match_end = match.span()
            if any(ipv6_start <= match_start and match_end <= ipv6_end
                   for ipv6_start, ipv6_end in ipv6_spans):
                continue
            var_name = match.group(2)
            if var_name:
                defined_names.add(var_name)
            range_slots.append({
                'type': 'range_def',
                'content': match.group(1),
                'var_name': var_name,  # 可能为 None
                'start_pos': match_start,
                'end_pos': match_end,
            })

        # 第二步：收集变量引用，只保留已定义的
        ref_slots = []
        for match in self.ref_pattern.finditer(url):
            var_name = match.group(1)
            if var_name in defined_names:
                ref_slots.append({
                    'type': 'ref',
                    'var_name': var_name,
                    'start_pos': match.start(),
                    'end_pos': match.end(),
                })

        slots = range_slots + ref_slots
        slots.sort(key=lambda s: s['start_pos'])
        return slots

    def has_range(self, url: str) -> bool:
        return len(self._find_all_slots(url)) > 0

    def estimate_url_count(self, url: str) -> int:
        slots = self._find_all_slots(url)
        if not slots:
            return 1
        # 命名变量只算一次（定义处），引用不算；未命名范围各自独立
        named_counts = {}  # var_name -> count
        unnamed_counts = []
        for slot in slots:
            if slot['type'] == 'range_def':
                content = slot['content']
                parsed_segments, _ = self._parse_bracket_content(content)
                count = self._count_range_size(parsed_segments)
                if slot['var_name']:
                    if slot['var_name'] not in named_counts:
                        named_counts[slot['var_name']] = count
                else:
                    unnamed_counts.append(count)
        total = 1
        for count in named_counts.values():
            total *= count
        for count in unnamed_counts:
            total *= count
        return total

    def parse_url(
        self, url: str, batch_size: int = 10000
    ) -> Generator[List[str], None, None]:
        """展开 URL 中的范围表达式与变量引用。

        支持两种可替换位置：
        - 范围定义：[1-255] / [1,5,10] / [1-10,20-30]（未命名，各自独立）
        - 命名变量：[1-255:n] 定义变量 n，{n} 引用并与之同步变化
          （同一变量名多处出现共享同一取值，零填充宽度以首次定义为准）

        多个独立变量（命名变量 + 未命名范围）按笛卡尔积展开。
        """
        slots = self._find_all_slots(url)
        if not slots:
            yield [url]
            return

        estimated = self.estimate_url_count(url)
        if estimated > self.MAX_EXPAND_COUNT:
            self.logger.error(
                f"URL解析: 展开数量 {estimated} 超过上限 {self.MAX_EXPAND_COUNT}，已拒绝解析: {url}"
            )
            raise ValueError(
                f"URL 范围展开数量过大({estimated})，单条最多 {self.MAX_EXPAND_COUNT} 个"
            )

        self.logger.info(f"开始解析范围URL: {url}")

        # 第一遍：为每个命名变量创建独立变量条目（取首次定义的范围与零填充）
        independent_vars = []  # [{'segments', 'pad_width'}]
        name_to_var_idx = {}   # var_name -> independent_vars 索引
        for slot in slots:
            if slot['type'] != 'range_def':
                continue
            var_name = slot['var_name']
            if var_name and var_name not in name_to_var_idx:
                content = slot['content']
                parsed_segments, min_pad = self._parse_bracket_content(content)
                name_to_var_idx[var_name] = len(independent_vars)
                independent_vars.append({
                    'segments': parsed_segments,
                    'pad_width': min_pad,
                })
            elif var_name and var_name in name_to_var_idx:
                # 重复定义：警告，后续定义的范围被忽略（当作引用同步）
                self.logger.warning(
                    f"URL解析: 变量 '{var_name}' 重复定义，"
                    f"忽略范围 '{slot['content']}'，按首次定义同步"
                )

        # 第二遍：为每个 slot 分配所属独立变量索引；未命名范围各自新建独立变量
        slot_to_var = [None] * len(slots)
        for i, slot in enumerate(slots):
            if slot['type'] == 'range_def':
                var_name = slot['var_name']
                if var_name:
                    slot_to_var[i] = name_to_var_idx[var_name]
                else:
                    content = slot['content']
                    parsed_segments, min_pad = self._parse_bracket_content(content)
                    var_idx = len(independent_vars)
                    independent_vars.append({
                        'segments': parsed_segments,
                        'pad_width': min_pad,
                    })
                    slot_to_var[i] = var_idx
            else:  # ref
                slot_to_var[i] = name_to_var_idx[slot['var_name']]

        if not independent_vars:
            yield [url]
            return

        # 将 URL 按 slot 位置拆分为固定片段
        url_parts = []
        last_pos = 0
        for slot in slots:
            url_parts.append(url[last_pos:slot['start_pos']])
            last_pos = slot['end_pos']
        url_parts.append(url[last_pos:])

        var_count = len(independent_vars)
        total_urls = self.estimate_url_count(url)
        self.logger.info(
            f"URL解析: 找到 {len(slots)} 个可替换位置，"
            f"{var_count} 个独立变量，将生成 {total_urls} 个URL"
        )

        # 笛卡尔积惰性展开；每个 slot 用其所属变量的当前值填充
        batch = []
        for values in self._generate_range_values_lazy(independent_vars):
            url_str = ""
            for i in range(len(slots)):
                url_str += url_parts[i] + values[slot_to_var[i]]
            url_str += url_parts[-1]
            batch.append(url_str)
            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

    def _generate_range_values_lazy(self, ranges_info):
        if not ranges_info:
            yield ()
            return

        iterators = []
        current_values = []
        for r in ranges_info:
            it = self._create_range_iterator(r['segments'], r['pad_width'])
            first = next(it, None)
            if first is None:
                return
            iterators.append(it)
            current_values.append(first)

        yield tuple(current_values)

        while iterators:
            idx = len(iterators) - 1
            while idx >= 0:
                nxt = next(iterators[idx], None)
                if nxt is not None:
                    current_values[idx] = nxt
                    break
                iterators[idx].reset()
                first = next(iterators[idx], None)
                if first is None:
                    return
                current_values[idx] = first
                idx -= 1

            if idx < 0:
                return

            yield tuple(current_values)

    def _build_url_from_parts(self, url_parts, range_count, values):
        url = ""
        for i in range(range_count):
            url += url_parts[i] + values[i]
        url += url_parts[-1]
        return url

