import gzip
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urljoin

from core.log_manager import global_logger as logger


def detect_and_decode_text(raw_bytes: Union[bytes, None]) -> str:
    if not raw_bytes:
        return ''
    for enc in ('utf-8-sig', 'utf-8'):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    # 文件主体是 UTF-8、但夹杂个别坏字节时，不应整体按 GB18030 解码（会把中文全变乱码）。
    # 用替换字符比例判断：比例很低说明仍是 UTF-8，保留正确内容。
    try:
        replaced = raw_bytes.decode('utf-8', errors='replace')
        bad_ratio = replaced.count('\ufffd') / max(len(replaced), 1)
        if replaced.count('\ufffd') and bad_ratio < 0.005:
            logger.debug(f"M3U含少量非法UTF-8字节({bad_ratio:.4%})，保留UTF-8并替换非法字符")
            return replaced
    except Exception:
        pass
    for enc in ('gb18030', 'gbk', 'gb2312'):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    for enc in ('big5', 'shift_jis', 'euc-kr', 'euc-jp'):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    try:
        import locale
        return raw_bytes.decode(locale.getpreferredencoding(), errors='replace')
    except Exception:
        return raw_bytes.decode('utf-8', errors='replace')


def looks_like_m3u(content: str) -> bool:
    """粗判内容是否像 M3U 播放列表，用于拦截 HTML/JSON 错误页被当作列表解析"""
    if not content:
        return False
    head = content.lstrip('\ufeff').lstrip()
    if head.startswith('#EXTM3U'):
        return True
    return '#EXTINF' in head[:8192]


MAX_M3U_BYTES = 128 * 1024 * 1024


def is_gzip(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B


def load_m3u_file(filepath: str) -> str:
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    with open(filepath, 'rb') as f:
        raw = f.read()
    if is_gzip(raw):
        try:
            raw = gzip.decompress(raw)
        except Exception as e:
            logger.debug(f"gzip解压raw数据失败: {e}")
    if len(raw) > MAX_M3U_BYTES:
        logger.error(f"M3U文件过大({len(raw)}字节)，已跳过")
        return ''
    return detect_and_decode_text(raw)


def load_m3u_from_url_data(data: bytes) -> str:
    if is_gzip(data):
        try:
            data = gzip.decompress(data)
        except Exception as e:
            logger.debug(f"gzip解压data失败: {e}")
    if len(data) > MAX_M3U_BYTES:
        logger.error(f"M3U数据过大({len(data)}字节)，已跳过")
        return ''
    return detect_and_decode_text(data)


def parse_attributes(attr_string: str) -> Dict[str, str]:
    result = {}
    if not attr_string:
        return result
    i = 0
    n = len(attr_string)
    while i < n:
        while i < n and attr_string[i] in ' \t':
            i += 1
        if i >= n:
            break
        key_start = i
        while i < n and attr_string[i] not in '= \t':
            i += 1
        key = attr_string[key_start:i].strip()
        if not key:
            i += 1
            continue
        while i < n and attr_string[i] in ' \t':
            i += 1
        if i >= n or attr_string[i] != '=':
            result[key] = ''
            continue
        i += 1
        while i < n and attr_string[i] in ' \t':
            i += 1
        if i >= n:
            result[key] = ''
            break
        if attr_string[i] == '"':
            i += 1
            val_start = i
            while i < n and attr_string[i] != '"':
                i += 1
            result[key] = attr_string[val_start:i]
            if i < n:
                i += 1
        else:
            val_start = i
            while i < n and attr_string[i] not in ' \t':
                i += 1
            result[key] = attr_string[val_start:i]
    return result


def guess_protocol(url: str) -> str:
    if not url:
        return 'unknown'
    u = url.lower()
    if '.m3u8' in u or u.startswith('hls+'):
        return 'hls'
    if '.mpd' in u or u.startswith('dash+'):
        return 'dash'
    if u.startswith('rtsp://'):
        return 'rtsp'
    if u.startswith('rtp://') or u.startswith('udp://'):
        return 'rtp'
    if u.startswith('srt://'):
        return 'srt'
    if u.startswith('http://') or u.startswith('https://'):
        return 'http'
    if u.startswith('file://') or '://' not in url:
        return 'file'
    return 'unknown'


def guess_quality_from_name(name: str) -> Tuple[str, str]:
    if not name:
        return 'SD', 'H.264'
    n = name.upper()
    resolution = 'SD'
    codec = ''
    if '4K' in n or 'UHD' in n or '2160' in n:
        resolution = '4K'
    elif '1080' in n or 'FHD' in n or 'FULL' in n:
        resolution = 'FHD'
    elif '720' in n or 'HD' in n:
        resolution = 'HD'
    if 'HEVC' in n or 'H265' in n or 'H.265' in n:
        codec = 'H.265'
    elif 'H264' in n or 'H.264' in n or 'AVC' in n:
        codec = 'H.264'
    elif 'AV1' in n:
        codec = 'AV1'
    return resolution, codec


def normalize_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    if '$' in url:
        url = url.split('$')[0]
    url = url.rstrip(',')
    return url


def resolve_url(url: str, base_url: Optional[str] = None) -> str:
    url = normalize_url(url)
    if not url:
        return url
    if '://' in url or url.startswith('/'):
        if base_url and url.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        return url
    if base_url:
        return urljoin(base_url, url)
    return url


def extract_tvg_url_from_header(line: str) -> Optional[str]:
    if not line or not line.startswith('#EXTM3U'):
        return None
    m = re.search(r'x-tvg-url="([^"]+)"', line, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"x-tvg-url='([^']+)'", line, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'x-tvg-url=(\S+)', line, re.IGNORECASE)
    if m:
        return m.group(1).rstrip('"').rstrip("'")
    return None


def extract_header_attributes(line: str) -> Dict[str, str]:
    if not line or not line.startswith('#EXTM3U'):
        return {}
    attrs = parse_attributes(line[7:])
    result = {}
    epg_keys = ['x-tvg-url', 'tvg-url', 'url-tvg', 'epg-url', 'url-epg']
    for k in epg_keys:
        if k in attrs and attrs[k]:
            result['epg_url'] = attrs[k]
            break
    catchup_keys = ['catchup', 'catchup-correction', 'catchup-source',
                    'catchup-days', 'catchup-type']
    for k in catchup_keys:
        if k in attrs and attrs[k]:
            result[k] = attrs[k]
    return result


def is_valid_channel_url(url: str) -> tuple:
    """返回 (是否有效, 无效原因)"""
    if not url or not url.strip():
        return False, 'URL为空'
    u = url.strip()
    if u.startswith('#'):
        return False, 'URL以#开头'
    if u in ('http://0/0.m3u8', 'http://0', 'rtmp://0'):
        return False, '已知占位URL'
    if u.startswith('http://0/') or u.startswith('http://0:'):
        return False, 'http://0占位地址'
    if u.startswith('rtp://0.') or u.startswith('udp://0.'):
        return False, '组播0.x占位地址'
    # 允许本地文件 URL（file:// 协议不需要 hostname）
    # 修复：之前 file:// URL 因 hostname 为空被拒绝，导致本地 M3U 中的本地条目被静默丢弃
    if u.startswith('file://'):
        return True, ''
    if '://' not in u:
        # 无协议的可能是本地绝对路径（如 /sdcard/Movies/test.mp4 或 D:\Videos\test.mp4）
        # Unix 绝对路径以 / 开头，Windows 绝对路径以盘符开头（如 D:）
        if u.startswith('/') or (len(u) >= 2 and u[1] == ':' and u[0].isalpha()):
            return True, ''
        return False, '缺少协议scheme'
    try:
        parsed = urlparse(u)
        host = parsed.hostname
        if not host:
            return False, '无法解析主机名'
        if host in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9'):
            return False, f'单数字主机名({host})'
        octets = host.split('.')
        if len(octets) == 4:
            try:
                if all(0 <= int(o) <= 255 for o in octets):
                    if int(octets[0]) == 0:
                        return False, 'IP首字节为0'
            except ValueError:
                pass
        return True, ''
    except Exception as e:
        return True, ''


_TAG_MAPPING = {
    "group-title": "group",
    "tvg-id": "tvg_id",
    "tvg-name": "name",
    "tvg-logo": "logo",
    "tvg-chno": "tvg_chno",
    "tvg-shift": "tvg_shift",
    "catchup": "catchup",
    "catchup-days": "catchup_days",
    "catchup-source": "catchup_source",
    "catchup-correction": "catchup_correction",
    "catchup-type": "catchup",
    "resolution": "resolution",
    "tvg-language": "tvg_language",
    "audio-track": "audio_track",
    "aspect-ratio": "aspect_ratio",
    "parent-code": "parent_code",
}

_HEADER_CATCHUP_MAP = {
    'catchup': 'catchup',
    'catchup-correction': 'catchup_correction',
    'catchup-source': 'catchup_source',
    'catchup-days': 'catchup_days',
    'catchup-type': 'catchup',
}


def _extract_fcc_to_channel(url: str, channel: Dict[str, Any]):
    """从频道URL中提取FCC代理地址并保存到频道字典"""
    try:
        from urllib.parse import urlparse, parse_qs
        if '?fcc=' in url.lower():
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            fcc_val = qs.get('fcc', [None])
            if fcc_val and fcc_val[0]:
                channel['fcc'] = fcc_val[0]
    except Exception as e:
        logger.debug(f"_extract_fcc_to_channel: {e}")


def detect_catchup_pattern(url: str) -> Optional[Tuple[str, str]]:
    """从频道URL自动检测回看模式，返回 (catchup_type, catchup_source) 或 None。

    支持的模式（均为单播可回看地址，无需在源里配置 catchup-source）：
      1. PLTV/TVOD 模式（华为/电信/移动 IPTV 平台）
         - 协议：http/https/rtsp/rtmp
         - 路径：/PLTV/<n>/<n>/<n>/<文件名>，文件名可为 index.m3u8、xxx.smil、xxx.flv 等
         - 回看 URL：将 /PLTV/ 替换为 /TVOD/，追加 ?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}
      2. SNM/TVOD 模式（华为 IPTV 平台另一种路径）
         - 协议：http/https/rtsp/rtmp
         - 路径：/SNM/CHANNEL<数字>/<文件名>
         - 回看 URL：将 /SNM/ 替换为 /TVOD/，追加 ?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}
    """
    if not url:
        return None
    try:
        import re as _re
        # PLTV 模式：匹配 /PLTV/数字/数字/数字/任意文件名（支持 .m3u8/.smil/.flv 等后缀）
        m = _re.search(r'/PLTV/\d+/\d+/\d+/[^/?#]+', url, _re.IGNORECASE)
        if m:
            live_path = m.group(0)
            tvod_path = _re.sub(r'^/PLTV/', '/TVOD/', live_path, flags=_re.IGNORECASE)
            base_url = url[:m.start()]
            catchup_source = base_url + tvod_path + '?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}'
            return 'pltv', catchup_source
        # SNM 模式：匹配 /SNM/CHANNEL数字/任意文件名
        m = _re.search(r'/SNM/CHANNEL\d+/[^/?#]+', url, _re.IGNORECASE)
        if m:
            live_path = m.group(0)
            tvod_path = _re.sub(r'^/SNM/', '/TVOD/', live_path, flags=_re.IGNORECASE)
            base_url = url[:m.start()]
            catchup_source = base_url + tvod_path + '?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}'
            return 'pltv', catchup_source
    except Exception as e:
        logger.debug(f"detect_catchup_pattern: {e}")
    return None


def _auto_detect_catchup_from_url(url: str, channel: Dict[str, Any]):
    """从频道URL中自动检测回看模式并填充catchup字段（如PLTV/TVOD、SNM/TVOD模式）"""
    try:
        if not url or channel.get('catchup') or channel.get('catchup_source'):
            return
        result = detect_catchup_pattern(url)
        if result:
            catchup_type, catchup_source = result
            channel['catchup'] = catchup_type
            channel['catchup_days'] = channel.get('catchup_days') or '3'
            channel['catchup_source'] = catchup_source
    except Exception as e:
        logger.debug(f"_auto_detect_catchup_from_url: {e}")


def safe_detect_catchup_source(url: str) -> Optional[str]:
    """安全检测 catchup 源，失败时返回 None"""
    try:
        detected = detect_catchup_pattern(url)
        return detected[1] if detected else None
    except Exception:
        return None


def _make_empty_channel(group: str = '未分类', groups: Optional[List[str]] = None, extinf: str = '') -> Dict[str, Any]:
    return {
        'name': '未命名',
        'url': '',
        'logo': '',
        'group': group,
        '_groups': groups or [group],
        'tvg_id': '',
        'tvg_chno': '',
        'tvg_shift': '',
        'catchup': '',
        'catchup_days': '',
        'catchup_source': '',
        'catchup_correction': '',
        'fcc': '',
        'resolution': '',
        'valid': None,
        'status': '待检测',
        '_raw_extinf': extinf,
        '_all_tags': {},
    }


def _parse_extinf_line(extinf_content: str, current_group: Union[str, List[str]], genre_group_active: bool) -> Tuple[Optional[Dict[str, Any]], Union[str, List[str]], bool]:
    genre_match = re.search(r',\s*#genre#\s*', extinf_content)
    if genre_match:
        before_genre = extinf_content[:genre_match.start()].strip()
        group_name = before_genre
        comma_pos = before_genre.rfind(',')
        if comma_pos >= 0:
            group_name = before_genre[comma_pos + 1:].strip()
        group_name = group_name.strip('=').strip()
        if group_name:
            current_group = group_name
        return None, current_group, True

    last_comma = extinf_content.rfind(",")
    if last_comma >= 0:
        attrs_part = extinf_content[:last_comma].strip()
        name = extinf_content[last_comma + 1:].strip()
    else:
        attrs_part = ''
        name = extinf_content.strip()

    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1]

    channel = _make_empty_channel(
        group=current_group if isinstance(current_group, str) and genre_group_active else '未分类',
        extinf=extinf_content,
    )

    attr_pattern = r'([\w-]+)=["\']([^"\']*)["\']'
    matches = re.findall(attr_pattern, attrs_part)

    all_tags = {}
    groups = []

    for key, value in matches:
        all_tags[key] = value
        field_name = _TAG_MAPPING.get(key) or key.replace('-', '_')
        if key == 'group-title' and value:
            groups = [g.strip() for g in value.split(';') if g.strip()]
            genre_group_active = False
        if key != 'tvg-name':
            channel[field_name] = value

    final_comma_name = ''
    if extinf_content and ',' in extinf_content:
        final_comma_name = extinf_content.split(',', 1)[-1].strip()
        if final_comma_name.startswith('"') and final_comma_name.endswith('"'):
            final_comma_name = final_comma_name[1:-1]
    if final_comma_name:
        channel['name'] = final_comma_name
    else:
        tvg_name = all_tags.get('tvg-name', '')
        if tvg_name:
            channel['name'] = tvg_name
        elif name:
            channel['name'] = name

    if groups:
        channel['_groups'] = groups
        channel['group'] = groups[0]
    elif isinstance(current_group, list):
        channel['_groups'] = current_group
        channel['group'] = current_group[0] if current_group else '未分类'
    else:
        channel['_groups'] = [current_group] if current_group else ['未分类']
        channel['group'] = current_group if current_group else '未分类'

    channel['_all_tags'] = all_tags
    return channel, current_group, genre_group_active


def _inherit_header_attrs(channel: Dict[str, Any], header_attrs: Dict[str, str]) -> None:
    if not channel or not header_attrs:
        return
    for k, v in header_attrs.items():
        if k == 'epg_url':
            continue
        field = _HEADER_CATCHUP_MAP.get(k, k.replace('-', '_'))
        if field and not channel.get(field):
            channel[field] = v
            if '_all_tags' in channel:
                channel['_all_tags'][k] = v


def parse_m3u_content(content: str) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    channels: List[Dict[str, Any]] = []
    if not content:
        return channels, {}
    lines = content.splitlines()
    current_channel: Optional[Dict[str, Any]] = None
    current_group: Union[str, List[str]] = '未分类'
    genre_group_active = False
    header_attrs = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('#EXTM3U'):
            header_attrs = extract_header_attributes(line)
            continue

        if line.startswith('#EXTGRP:'):
            current_group = line[8:].strip()
            if current_group.startswith('"') and current_group.endswith('"'):
                current_group = current_group[1:-1]
            continue

        if line.startswith('#EXTINF:'):
            extinf_content = line[8:].strip()
            current_channel, current_group, genre_group_active = _parse_extinf_line(
                extinf_content, current_group, genre_group_active
            )
            if current_channel:
                _inherit_header_attrs(current_channel, header_attrs)
            continue

        if line.startswith('#EXTVLCOPT:video-resolution=') and current_channel:
            resolution = line.split('=', 1)[1].strip()
            current_channel['resolution'] = resolution
            continue

        if line.startswith('#'):
            continue

        txt_parsed = False
        if ',' in line and not current_channel:
            parts = line.split(',', 1)
            if len(parts) == 2:
                maybe_name = parts[0].strip()
                maybe_url = parts[1].strip()
                valid, reason = is_valid_channel_url(maybe_url)
                if valid:
                    groups_list = [g.strip() for g in current_group.split(';') if g.strip()] if isinstance(current_group, str) else (current_group if isinstance(current_group, list) else ['未分类'])
                    primary_group = groups_list[0] if groups_list else '未分类'
                    ch = _make_empty_channel(group=primary_group, groups=groups_list)
                    ch['name'] = maybe_name if maybe_name else '未命名'
                    ch['url'] = maybe_url
                    _extract_fcc_to_channel(maybe_url, ch)
                    _auto_detect_catchup_from_url(maybe_url, ch)
                    _inherit_header_attrs(ch, header_attrs)
                    channels.append(ch)
                    txt_parsed = True
                else:
                    valid2, reason2 = is_valid_channel_url(line.strip())
                    if valid2:
                        groups_list = [g.strip() for g in current_group.split(';') if g.strip()] if isinstance(current_group, str) else (current_group if isinstance(current_group, list) else ['未分类'])
                        primary_group = groups_list[0] if groups_list else '未分类'
                        ch = _make_empty_channel(group=primary_group, groups=groups_list)
                        ch['name'] = maybe_name if maybe_name else '未命名'
                        ch['url'] = line.strip()
                        _auto_detect_catchup_from_url(line.strip(), ch)
                        _inherit_header_attrs(ch, header_attrs)
                        channels.append(ch)
                        txt_parsed = True

        if not txt_parsed:
            if current_channel:
                url = line.strip()
                valid, reason = is_valid_channel_url(url)
                if valid:
                    current_channel['url'] = url
                    _extract_fcc_to_channel(url, current_channel)
                    _auto_detect_catchup_from_url(url, current_channel)
                    channels.append(current_channel)
                else:
                    ch_name = current_channel.get('name', '?')
                    logger.debug(f"M3U解析跳过: 频道'{ch_name}' URL无效({reason}): {url}")
                current_channel = None
            else:
                url = line.strip()
                valid, reason = is_valid_channel_url(url)
                if valid:
                    try:
                        from models.channel_mappings import extract_channel_name_from_url
                        ch_name = extract_channel_name_from_url(url)
                    except Exception:
                        ch_name = ''
                    groups_list = [g.strip() for g in current_group.split(';') if g.strip()] if isinstance(current_group, str) else (current_group if isinstance(current_group, list) else ['未分类'])
                    primary_group = groups_list[0] if groups_list else '未分类'
                    ch = _make_empty_channel(group=primary_group, groups=groups_list)
                    ch['name'] = ch_name if ch_name else '未命名'
                    ch['url'] = url
                    _auto_detect_catchup_from_url(url, ch)
                    _inherit_header_attrs(ch, header_attrs)
                    channels.append(ch)
                else:
                    logger.debug(f"M3U解析跳过: 裸URL无效({reason}): {url}")

    for i, ch in enumerate(channels):
        ch['id'] = i + 1

    return channels, header_attrs
