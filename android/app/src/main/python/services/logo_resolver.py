"""台标来源解析：本地 / M3U / EPG / 规则模板，支持排序与逐级兜底。

优先级语义：
- 只勾选一个来源 = 固定使用该来源；
- 勾选多个来源 = 按设置里的顺序逐级兜底，前一级取不到图才看下一级。

解析结果写入 JSON 缓存（按频道 + 设置签名失效），失败的远程地址也会缓存，
避免每次刷新频道列表都重复请求坏地址。失败状态可在设置里手动清除。
"""
import json
import os
import threading
import time
from urllib.parse import quote

try:
    from core.log_manager import global_logger as logger
except Exception:  # pragma: no cover - 无日志模块时退化为标准 logging
    import logging
    logger = logging.getLogger(__name__)

SOURCE_LOCAL = 'local'
SOURCE_M3U = 'm3u'
SOURCE_EPG = 'epg'
SOURCE_RULE = 'rule'

SOURCE_LABELS = {
    SOURCE_LOCAL: '本地台标文件',
    SOURCE_M3U: 'M3U tvg-logo',
    SOURCE_EPG: 'EPG icon',
    SOURCE_RULE: '规则模板',
}
SOURCE_ORDER = (SOURCE_LOCAL, SOURCE_M3U, SOURCE_EPG, SOURCE_RULE)

CONFIG_SECTION = 'Logo'
PRIORITY_KEY = 'priority'
RULE_TEMPLATE_KEY = 'rule_template'

RESULT_OK_TTL = 7 * 24 * 3600
RESULT_NONE_TTL = 24 * 3600
URL_FAIL_TTL = 24 * 3600
URL_OK_TTL = 7 * 24 * 3600

CACHE_FILE_NAME = 'logo_resolution_cache.json'
LOCAL_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg', '.ico')


def _strip_quotes(value) -> str:
    return str(value or '').strip().strip('`"\'' ).strip()


def _is_remote_url(value: str) -> bool:
    value = (value or '').lower()
    return value.startswith(('http://', 'https://', '//'))


class LogoResolver:
    """四级台标来源解析与缓存。"""

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> 'LogoResolver':
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self._matcher = None
        self._settings = self._load_settings_from_config()
        self._signature = ''
        self._entries = {}
        self._url_status = {}
        self._cache_path = os.path.join(self._cache_dir(), CACHE_FILE_NAME)
        self._local_index = None
        self._local_index_sig = None
        self._save_timer = None
        self._last_signature_check = 0.0
        self._load_cache()
        self._refresh_signature()

    # ── 目录 / 配置 ──

    @staticmethod
    def _cache_dir() -> str:
        try:
            from utils.app_paths import get_cache_dir
            return get_cache_dir()
        except Exception:
            return os.path.join(os.path.expanduser('~'), '.guangyu_cache')

    @staticmethod
    def _config():
        try:
            from core.config_manager import ConfigManager
            return ConfigManager()
        except Exception:
            return None

    def _matcher_instance(self):
        if self._matcher is None:
            from services.logo_matcher import LogoMatcher
            self._matcher = LogoMatcher()
        return self._matcher

    def _epg_manager(self):
        try:
            from core.subscription_manager import global_subscription_manager
            return global_subscription_manager
        except Exception:
            return None

    def _load_settings_from_config(self) -> dict:
        order = list(SOURCE_ORDER)
        template = ''
        config = self._config()
        if config is not None:
            raw = str(config.get_value(CONFIG_SECTION, PRIORITY_KEY, '') or '')
            parsed = [s.strip().lower() for s in raw.split(',') if s.strip()]
            deduped = []
            for item in parsed:
                if item in SOURCE_ORDER and item not in deduped:
                    deduped.append(item)
            if deduped:
                order = deduped
            template = str(config.get_value(CONFIG_SECTION, RULE_TEMPLATE_KEY, '') or '')
        return {'order': order, 'rule_template': template}

    def get_settings(self) -> dict:
        with self._lock:
            return {'order': list(self._settings['order']),
                    'rule_template': self._settings['rule_template']}

    def save_settings(self, order, rule_template: str):
        """保存优先级与规则模板；来源顺序变化后旧的解析结果全部作废。"""
        normalized = []
        for item in order or []:
            item = str(item).strip().lower()
            if item in SOURCE_ORDER and item not in normalized:
                normalized.append(item)
        template = str(rule_template or '').strip()
        if not template and SOURCE_RULE in normalized:
            # 规则来源没有地址模板时等价于未启用，避免缓存里留下永远取不到图的来源
            normalized.remove(SOURCE_RULE)
        if not normalized:
            normalized = [SOURCE_M3U]

        with self._lock:
            changed = (normalized != self._settings['order']
                       or template != self._settings['rule_template'])
            self._settings = {'order': normalized, 'rule_template': template}
            if changed:
                self._entries.clear()
            self._refresh_signature(force_clear=changed)
        config = self._config()
        if config is not None:
            config.set_value(CONFIG_SECTION, PRIORITY_KEY, ','.join(normalized))
            config.set_value(CONFIG_SECTION, RULE_TEMPLATE_KEY, template)
            config.save_config()
        self._schedule_save(immediate=True)

    # ── 缓存持久化 ──

    def _load_cache(self):
        try:
            if not os.path.exists(self._cache_path):
                return
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                payload = json.load(f) or {}
            self._entries = payload.get('entries') or {}
            self._url_status = payload.get('url_status') or {}
            self._signature = payload.get('signature') or ''
        except Exception as e:
            logger.debug(f"加载台标解析缓存失败: {e}")
            self._entries = {}
            self._url_status = {}

    def _save_now(self):
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with self._lock:
                payload = {
                    'signature': self._signature,
                    'entries': dict(self._entries),
                    'url_status': dict(self._url_status),
                }
            import tempfile
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(self._cache_path), suffix='.tmp', prefix='logo_res_')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._cache_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.debug(f"保存台标解析缓存失败: {e}")

    def _schedule_save(self, immediate: bool = False):
        if immediate:
            self._save_now()
            return
        with self._lock:
            if self._save_timer is not None:
                return
            timer = threading.Timer(1.5, self._flush_save)
            timer.daemon = True
            self._save_timer = timer
            timer.start()

    def _flush_save(self):
        with self._lock:
            self._save_timer = None
        self._save_now()

    def _flush_pending(self):
        with self._lock:
            has_timer = self._save_timer is not None
        if has_timer:
            self._save_now()

    # ── 设置签名：优先级 / 模板 / 本地目录 / EPG 数据变化都会作废旧结果 ──

    @staticmethod
    def _local_dirs():
        dirs = []
        try:
            from utils.app_paths import get_config_dir, get_legacy_base_dir
            candidates = (
                os.path.join(get_legacy_base_dir(), 'img'),
                os.path.join(get_config_dir(), 'logos'),
                os.path.join(get_config_dir(), 'img'),
            )
        except Exception:
            candidates = ()
        for path in candidates:
            try:
                if os.path.isdir(path) and path not in dirs:
                    dirs.append(path)
            except OSError:
                continue
        return dirs

    def _local_dirs_signature(self):
        signature = []
        for path in self._local_dirs():
            try:
                signature.append((path, os.path.getmtime(path)))
            except OSError:
                signature.append((path, 0))
        return tuple(signature)

    def _epg_signature(self):
        if SOURCE_EPG not in self._settings['order']:
            return ''
        manager = self._epg_manager()
        if manager is None or not hasattr(manager, 'get_epg_signature'):
            return ''
        try:
            return str(manager.get_epg_signature())
        except Exception:
            return ''

    def _compute_signature(self) -> str:
        local_sig = self._local_dirs_signature() if SOURCE_LOCAL in self._settings['order'] else ()
        return '|'.join((
            ','.join(self._settings['order']),
            self._settings['rule_template'],
            repr(local_sig),
            self._epg_signature(),
        ))

    def _refresh_signature(self, force_clear: bool = False):
        signature = self._compute_signature()
        with self._lock:
            if force_clear or (self._signature and signature != self._signature):
                self._entries.clear()
            self._signature = signature

    # ── 本地台标目录 ──

    def _get_local_index(self):
        signature = self._local_dirs_signature()
        with self._lock:
            if self._local_index is not None and signature == self._local_index_sig:
                return self._local_index
        index = {}
        for directory in self._local_dirs():
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for entry in names:
                stem, ext = os.path.splitext(entry)
                if ext.lower() not in LOCAL_IMAGE_EXTS or not stem:
                    continue
                index.setdefault(stem.lower(), os.path.join(directory, entry))
        with self._lock:
            self._local_index = index
            self._local_index_sig = signature
        return index

    @staticmethod
    def _resolve_local_raw_path(raw: str):
        """M3U/tvg-logo 本身就是一个本地文件路径时，直接当作本地台标。"""
        if not raw or _is_remote_url(raw):
            return None
        path = raw[7:] if raw.lower().startswith('file://') else raw
        path = path.replace('/', os.sep)
        try:
            if not os.path.isabs(path):
                from utils.app_paths import get_legacy_base_dir
                path = os.path.join(get_legacy_base_dir(), path)
            if os.path.isfile(path):
                return os.path.abspath(path)
        except (OSError, ValueError):
            return None
        return None

    def _local_candidate(self, channel: dict, name: str):
        raw = _strip_quotes(channel.get('logo') or channel.get('logo_url'))
        direct = self._resolve_local_raw_path(raw)
        if direct:
            return direct

        index = self._get_local_index()
        if not index or not name:
            return None

        key = name.strip().lower()
        if key in index:
            return index[key]

        try:
            stem = self._matcher_instance().match_stem_exact(name)
        except Exception:
            stem = None
        if stem and stem.lower() in index:
            return index[stem.lower()]
        return None

    # ── 四种来源 ──

    def _m3u_candidate(self, channel: dict):
        raw = _strip_quotes(channel.get('logo') or channel.get('logo_url'))
        return raw or None

    def _epg_candidate(self, channel: dict):
        cached = _strip_quotes(channel.get('_epg_logo') or channel.get('epg_logo'))
        if cached:
            return cached
        manager = self._epg_manager()
        if manager is None or not hasattr(manager, 'get_channel_icon'):
            return None
        try:
            icon = manager.get_channel_icon(
                channel.get('name', '') or '',
                tvg_id=channel.get('tvg_id') or None,
                tvg_name=channel.get('tvg_name') or None,
                comma_name=channel.get('comma_name') or channel.get('name') or None,
            )
        except Exception as e:
            logger.debug(f"EPG 台标解析失败: {e}")
            return None
        return _strip_quotes(icon) or None

    def _rule_candidate(self, name: str):
        template = self._settings['rule_template'].strip()
        if not template or '[name]' not in template or not name:
            return None
        return template.replace('[name]', quote(name.strip(), safe=''))

    def _candidates(self, channel: dict, name: str):
        result = []
        for source in self._settings['order']:
            if source == SOURCE_LOCAL:
                value = self._local_candidate(channel, name)
            elif source == SOURCE_M3U:
                value = self._m3u_candidate(channel)
            elif source == SOURCE_EPG:
                value = self._epg_candidate(channel)
            elif source == SOURCE_RULE:
                value = self._rule_candidate(name)
            else:
                value = None
            if value and value not in [v for _, v in result]:
                result.append((source, value))
        return result

    # ── 远程地址状态（失败缓存） ──

    def _url_state(self, url: str):
        """True=可用，False=失败（未过期），None=未知。"""
        with self._lock:
            status = self._url_status.get(url)
        if not status:
            return None
        age = time.time() - float(status.get('ts', 0) or 0)
        if status.get('ok'):
            return True if age < URL_OK_TTL else None
        return False if age < URL_FAIL_TTL else None

    def note_url_ok(self, url: str):
        url = _strip_quotes(url)
        if not url or not _is_remote_url(url):
            return
        with self._lock:
            self._url_status[url] = {'ok': True, 'ts': time.time()}
        self._schedule_save()

    def invalidate_url(self, url: str):
        """远程图片下载失败：记录失败并删除以该地址为结果的频道缓存。"""
        url = _strip_quotes(url)
        if not url:
            return
        with self._lock:
            self._url_status[url] = {'ok': False, 'ts': time.time()}
            stale = [key for key, entry in self._entries.items() if entry.get('url') == url]
            for key in stale:
                self._entries.pop(key, None)
        # 失败可能成批到达（规则地址 404），合并写盘避免风暴
        self._schedule_save()
        if stale:
            logger.debug(f"台标地址不可用，已回退 {len(stale)} 个频道: {url[:80]}")

    def invalidate_urls(self, urls):
        """批量记录失败（仅记录确实被某个频道用到的地址）。

        安卓图片加载器会把所有失败图片回传，这里先判断地址是否出现在解析
        结果里，避免把缩略图等无关地址写进台标失败缓存。
        返回受影响的频道 key 集合，供桥接层回传新的台标地址。
        """
        normalized = []
        for value in urls or []:
            value = _strip_quotes(value)
            if value and value not in normalized:
                normalized.append(value)
        if not normalized:
            return set()

        removed_keys = set()
        now = time.time()
        with self._lock:
            for url in normalized:
                stale = [key for key, entry in self._entries.items()
                         if entry.get('url') == url]
                if not stale:
                    continue
                self._url_status[url] = {'ok': False, 'ts': now}
                for key in stale:
                    self._entries.pop(key, None)
                    removed_keys.add(key)
        if removed_keys:
            # 失败可能成批到达，合并写盘避免风暴
            self._schedule_save()
            logger.debug(f"台标地址不可用，已回退 {len(removed_keys)} 个频道解析结果")
        return removed_keys

    def channel_key(self, channel: dict) -> str:
        """频道在解析缓存里的 key（供桥接层按 key 反查受影响频道）。"""
        if not isinstance(channel, dict):
            return ''
        name = (channel.get('name') or channel.get('tvg_name') or '').strip()
        return self._channel_key(channel, name)

    # ── 对外解析 ──

    @staticmethod
    def _channel_key(channel: dict, name: str) -> str:
        raw = _strip_quotes(channel.get('logo') or channel.get('logo_url'))
        epg_hint = _strip_quotes(channel.get('_epg_logo') or channel.get('epg_logo'))
        return f"{name}\x1f{raw}\x1f{epg_hint}"

    def resolve(self, channel: dict):
        if not isinstance(channel, dict):
            return None
        now = time.time()
        # 目录/EPG 变化检测做 5 秒节流：列表滚动时不会为每个频道 stat 目录
        if now - self._last_signature_check > 5:
            self._refresh_signature()
            self._last_signature_check = now
        name = (channel.get('name') or channel.get('tvg_name') or '').strip()
        key = self._channel_key(channel, name)

        with self._lock:
            entry = self._entries.get(key)
        if entry:
            ttl = RESULT_OK_TTL if entry.get('status') == 'ok' else RESULT_NONE_TTL
            if now - float(entry.get('ts', 0) or 0) < ttl:
                return entry.get('url') or None

        chosen = None
        for source, value in self._candidates(channel, name):
            if _is_remote_url(value) and self._url_state(value) is False:
                continue
            chosen = (source, value)
            break

        url = chosen[1] if chosen else ''
        with self._lock:
            self._entries[key] = {
                'url': url,
                'source': chosen[0] if chosen else '',
                'status': 'ok' if url else 'none',
                'ts': now,
            }
        self._schedule_save()
        return url or None

    def clear_cache(self):
        """清空解析结果与失败记录（已下载图片由台标缓存服务单独清理）。"""
        with self._lock:
            self._entries.clear()
            self._url_status.clear()
        self._schedule_save(immediate=True)

    def cache_stats(self) -> dict:
        with self._lock:
            entries = list(self._entries.values())
            failed = sum(1 for status in self._url_status.values() if not status.get('ok'))
        return {
            'channels': len(entries),
            'ok': sum(1 for e in entries if e.get('status') == 'ok'),
            'none': sum(1 for e in entries if e.get('status') == 'none'),
            'failed_urls': failed,
        }


def get_logo_resolver() -> LogoResolver:
    return LogoResolver.instance()


def resolve_channel_logo(channel: dict) -> str:
    """供 UI / Android / Web 共用的台标地址解析入口（已去除包裹引号）。"""
    if not isinstance(channel, dict):
        return ''
    try:
        return _strip_quotes(get_logo_resolver().resolve(channel))
    except Exception as e:
        # 解析模块异常时退回原始 logo，避免整个列表没有台标
        logger.debug(f"台标解析失败，回退原始 logo: {e}")
        return _strip_quotes(channel.get('logo') or channel.get('logo_url'))
