import os
import sys
import re
import json
import hashlib
import time
import threading
from typing import Dict, List

from core.log_manager import global_logger as logger
from core.config_manager import ConfigManager


def get_app_data_dir() -> str:
    """获取应用数据目录（兼容 Android Chaquopy / PyInstaller / 开发环境）

    Returns:
        str: 应用数据目录的绝对路径

    Note:
        - Android (Chaquopy): IPTV_DATA_DIR 环境变量指向的目录
        - PyInstaller 打包后: exe文件所在目录
        - 开发环境: 项目根目录
    """
    # Android Chaquopy 环境：优先使用 IPTV_DATA_DIR
    android_data = os.environ.get('IPTV_DATA_DIR', '')
    if android_data:
        return android_data
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的情况
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：从models目录向上两级到项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(current_dir)


# 尝试导入requests，如果失败则提供备用方案
try:
    import requests
    from utils.http_session import get as _http_get, head as _http_head
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests模块未安装，远程映射功能将不可用")

# 默认远程URL - 优先使用CSV格式，如果不存在则尝试TXT格式
DEFAULT_REMOTE_URL = (
    "https://raw.githubusercontent.com/sumingyd/guangyu/main/local_channel_mappings.csv"
)

# 本地缓存文件路径（使用绝对路径，兼容PyInstaller打包）
CACHE_FILE = os.path.join(get_app_data_dir(), "channel_mappings_cache.json")
USER_MAPPINGS_FILE = os.path.join(get_app_data_dir(), "user_channel_mappings.json")
CHANNEL_FINGERPRINT_FILE = os.path.join(get_app_data_dir(), "channel_fingerprints.json")


def load_mappings_from_file(file_path: str) -> Dict[str, dict]:
    """从文件加载映射规则，支持txt和csv格式"""
    mappings = {}
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        return _parse_mappings_content(content, file_path)
    except Exception as e:
        logger.error(f"加载映射文件失败 {file_path}: {e}")
        return {}


def _looks_like_csv(content: str, source_hint: str = '') -> bool:
    """判断映射文本是否为 CSV 格式。

    不能再用 str.isalpha() 判断首字符：中文同样满足 isalpha()，会把
    "CCTV1,中央一台" 这类 TXT 映射误判成 CSV 并静默解析为空。
    """
    hint = (source_hint or '').lower()
    if hint.endswith('.csv'):
        return True
    if hint.endswith('.txt'):
        return False
    head = content.lstrip('\ufeff').strip()
    if not head:
        return False
    first_line = head.splitlines()[0].lstrip('\ufeff')
    return 'standard_name' in first_line and ',' in first_line


def _parse_mappings_content(content: str, source_hint: str = '') -> Dict[str, dict]:
    """从文本内容解析映射规则"""
    mappings = {}
    try:
        if _looks_like_csv(content, source_hint):
            import csv
            from io import StringIO
            reader = csv.DictReader(StringIO(content))
            for row in reader:
                standard_name = row.get('standard_name', '').strip().lstrip('\ufeff')
                if standard_name.startswith('##########') and standard_name.endswith('##########'):
                    continue
                raw_names = (
                    [name.strip() for name in row.get('raw_names', '').split(',')]
                    if row.get('raw_names')
                    else []
                )
                logo_url = row.get('logo_url', '').strip() if row.get('logo_url') else None
                group_name = row.get('group_name', '').strip() if row.get('group_name') else None
                tvg_id = row.get('tvg_id', '').strip() if row.get('tvg_id') else None
                tvg_chno = row.get('tvg_chno', '').strip() if row.get('tvg_chno') else None
                tvg_shift = row.get('tvg_shift', '').strip() if row.get('tvg_shift') else None
                catchup_raw = row.get('catchup', '')
                catchup = catchup_raw.strip() if catchup_raw is not None and catchup_raw.strip() else None
                catchup_days = row.get('catchup_days', '').strip() if row.get('catchup_days') else None
                catchup_source = row.get('catchup_source', '').strip() if row.get('catchup_source') else None
                resolution = row.get('resolution', '').strip() if row.get('resolution') else None

                if standard_name:
                    for raw_name in raw_names:
                        if raw_name:
                            unique_key = f"{standard_name}||{raw_name}"
                            mappings[unique_key] = {
                                'standard_name': standard_name,
                                'raw_names': [raw_name],
                                'logo_url': logo_url if logo_url and logo_url.lower() not in ['', 'none', 'null'] else None,
                                'group_name': group_name if group_name and group_name.lower() not in ['', 'none', 'null'] else None,
                                'tvg_id': tvg_id if tvg_id and tvg_id.lower() not in ['', 'none', 'null'] else None,
                                'tvg_chno': tvg_chno if tvg_chno and tvg_chno.lower() not in ['', 'none', 'null'] else None,
                                'tvg_shift': tvg_shift if tvg_shift and tvg_shift.lower() not in ['', 'none', 'null'] else None,
                                'catchup': catchup,
                                'catchup_days': catchup_days if catchup_days and catchup_days.lower() not in ['', 'none', 'null'] else None,
                                'catchup_source': catchup_source if catchup_source and catchup_source.lower() not in ['', 'none', 'null'] else None,
                                'resolution': resolution if resolution and resolution.lower() not in ['', 'none', 'null'] else None
                            }
        else:
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    mappings.update(parse_mapping_line(line))
    except Exception as e:
        logger.error(f"解析映射内容失败: {e}")
    return mappings


def create_reverse_mappings(mappings: Dict[str, dict]) -> Dict[str, dict]:
    """创建反向映射字典
    返回格式: {raw_name: {'standard_name': str, 'logo_url': str, 'group_name': str, ...}}
    """
    reverse_mappings = {}
    for unique_key, data in mappings.items():
        # 从unique_key中提取标准名称（格式为"标准名称||原始名称"）
        if '||' in unique_key:
            standard_name = unique_key.split('||')[0]
        else:
            standard_name = unique_key

        for raw_name in data['raw_names']:
            reverse_mappings[raw_name] = {
                'standard_name': standard_name,
                'logo_url': data['logo_url'],
                'group_name': data.get('group_name'),
                'tvg_id': data.get('tvg_id'),
                'tvg_chno': data.get('tvg_chno'),
                'tvg_shift': data.get('tvg_shift'),
                'catchup': data.get('catchup'),
                'catchup_days': data.get('catchup_days'),
                'catchup_source': data.get('catchup_source'),
                'resolution': data.get('resolution')
            }
    return reverse_mappings


def _atomic_write_json(path: str, payload) -> None:
    """原子写入 JSON 文件，避免进程中断/磁盘满产生半截文件导致缓存损坏"""
    import tempfile
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix='.tmp', prefix=os.path.basename(path) + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_text(path: str, text: str) -> None:
    """原子写入文本文件"""
    import tempfile
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix='.tmp', prefix=os.path.basename(path) + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _decode_remote_text(response) -> str:
    """解码远端映射内容：优先 UTF-8，其次 GB18030，最后替换非法字符"""
    raw = response.content
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def load_remote_mappings() -> Dict[str, dict]:
    """加载远程映射规则（失败返回空字典，兼容旧调用）"""
    return try_load_remote_mappings() or {}


def try_load_remote_mappings():
    """加载远程映射规则。

    Returns:
        成功时返回映射字典；失败时返回 None，供调用方区分“失败”与“确实为空”，
        避免用空结果覆盖本地缓存。
    """
    # 检查requests模块是否可用
    if not REQUESTS_AVAILABLE:
        logger.warning("requests模块不可用，无法加载远程映射")
        return None

    try:
        config = ConfigManager()
        try:
            remote_url = config.get_value('channel_mappings', 'remote_url', DEFAULT_REMOTE_URL) or DEFAULT_REMOTE_URL
        except Exception as e:
            logger.debug(f"读取远程映射URL配置失败: {e}")
            remote_url = DEFAULT_REMOTE_URL

        # 简化版本：只尝试一次，不重试
        try:
            # 先尝试CSV格式
            response = _http_get(remote_url, timeout=5)
            if response.status_code == 404:
                txt_url = remote_url.replace('.csv', '.txt')
                logger.info(f"CSV映射文件不存在，尝试TXT格式: {txt_url}")
                response = _http_get(txt_url, timeout=5)

            response.raise_for_status()

            # 根据文件扩展名确定格式
            source_hint = response.url
            facts = _parse_mappings_content(_decode_remote_text(response), source_hint)
            logger.info(f"成功加载远程映射规则，共 {len(facts)} 条映射")
            return facts

        except Exception as e:
            # 只记录一次错误，不重试；返回 None 由调用方决定是否保留缓存
            logger.warning(f"加载远程映射失败: {e}, 使用本地缓存")
            return None

    except Exception as e:
        logger.warning(f"加载远程映射失败: {e}, 使用本地映射")
        return None


class ChannelMappingManager:
    """频道映射管理器，包含本地缓存、频道指纹、智能学习和用户自定义映射功能"""

    def __init__(self):
        self.logger = logger
        self.cache_file = CACHE_FILE
        self.user_mappings_file = USER_MAPPINGS_FILE
        self.fingerprint_file = CHANNEL_FINGERPRINT_FILE
        self.cache_lock = threading.Lock()
        self.user_mappings_lock = threading.Lock()
        self.fingerprint_lock = threading.Lock()
        self._mapping_lock = threading.RLock()
        self._fingerprint_dirty = False
        self._fingerprint_save_timer = None

        # 映射功能开关（默认开启）
        self.enable_mapping = True

        # 加载各种映射数据
        self.remote_mappings = self._load_cached_mappings()
        self.user_mappings = self._load_user_mappings()
        self.channel_fingerprints = self._load_channel_fingerprints()

        # 组合所有映射
        self.combined_mappings = self._combine_mappings()
        self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
        self._normalized_index = self._build_normalized_index()

    def _load_cached_mappings(self) -> Dict[str, dict]:
        """加载缓存的远程映射规则（构造时仅读缓存，不触发网络请求）"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    mappings = data.get('mappings', {})
                    if mappings:
                        self.logger.debug(f"从缓存加载远程映射规则，共 {len(mappings)} 条映射")
                        return mappings
        except Exception as e:
            self.logger.error(f"加载缓存映射失败: {e}")

        return {}

    def _load_and_cache_remote_mappings(self):
        """加载远程映射并缓存到本地。

        Returns:
            成功时返回映射字典；网络/解析失败时返回 None，且不写缓存，
            避免用空结果覆盖已有映射缓存。
        """
        mappings = try_load_remote_mappings()
        if mappings is None:
            self.logger.warning("远程映射加载失败，保留本地缓存")
            return None

        # 缓存到本地文件（原子写入，防止中断损坏）
        try:
            with self.cache_lock:
                cache_data = {
                    'timestamp': time.time(),
                    'mappings': mappings
                }
                _atomic_write_json(self.cache_file, cache_data)
            self.logger.debug(f"远程映射已缓存到本地，共 {len(mappings)} 条映射")
        except Exception as e:
            self.logger.error(f"缓存远程映射失败: {e}")

        return mappings

    def _load_user_mappings(self) -> Dict[str, dict]:
        """加载用户自定义映射规则（兼容旧格式键）"""
        try:
            if os.path.exists(self.user_mappings_file):
                with open(self.user_mappings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return self._migrate_user_mappings(data)
        except Exception as e:
            self.logger.error(f"加载用户映射失败: {e}")
        return {}

    def _migrate_user_mappings(self, data: Dict[str, dict]) -> Dict[str, dict]:
        """将旧格式键(standard_name)迁移为新格式键(standard_name||raw_name)"""
        migrated = {}
        for key, value in data.items():
            if '||' in key:
                migrated[key] = value
                continue
            standard_name = key
            raw_names = value.get('raw_names', [])
            if not raw_names:
                continue
            for raw_name in raw_names:
                unique_key = f"{standard_name}||{raw_name}"
                migrated[unique_key] = {
                    'standard_name': standard_name,
                    'raw_names': [raw_name],
                    'logo_url': value.get('logo_url'),
                    'group_name': value.get('group_name'),
                    'tvg_id': value.get('tvg_id'),
                    'tvg_chno': value.get('tvg_chno'),
                    'tvg_shift': value.get('tvg_shift'),
                    'catchup': value.get('catchup'),
                    'catchup_days': value.get('catchup_days'),
                    'catchup_source': value.get('catchup_source'),
                    'resolution': value.get('resolution')
                }
        return migrated

    def _save_user_mappings(self):
        """保存用户自定义映射规则（原子写入）"""
        try:
            with self.user_mappings_lock:
                _atomic_write_json(self.user_mappings_file, self.user_mappings)
        except Exception as e:
            self.logger.error(f"保存用户映射失败: {e}")

    def _load_channel_fingerprints(self) -> Dict[str, dict]:
        """加载频道指纹数据"""
        try:
            if os.path.exists(self.fingerprint_file):
                with open(self.fingerprint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"加载频道指纹失败: {e}")
        return {}

    def _save_channel_fingerprints(self):
        """保存频道指纹数据（原子写入，并限制文件无限增长）"""
        try:
            with self.fingerprint_lock:
                # 指纹文件会随扫描量无限膨胀：超过阈值时丢弃仅出现 1-2 次的弱证据
                if len(self.channel_fingerprints) > 20000:
                    self.channel_fingerprints = {
                        k: v for k, v in self.channel_fingerprints.items()
                        if v.get('count', 0) >= 3
                    }
                    self.logger.info(f"频道指纹条目过多，已精简为 {len(self.channel_fingerprints)} 条")
                _atomic_write_json(self.fingerprint_file, self.channel_fingerprints)
        except Exception as e:
            self.logger.error(f"保存频道指纹失败: {e}")

    def _schedule_fingerprint_save(self):
        """延迟批量保存指纹数据，避免频繁写磁盘"""
        with self.fingerprint_lock:
            self._fingerprint_dirty = True
            if self._fingerprint_save_timer is not None:
                return

            def _do_save():
                with self.fingerprint_lock:
                    self._fingerprint_save_timer = None
                    if self._fingerprint_dirty:
                        self._fingerprint_dirty = False
                    else:
                        return
                self._save_channel_fingerprints()

            self._fingerprint_save_timer = threading.Timer(5.0, _do_save)
            self._fingerprint_save_timer.daemon = True
            self._fingerprint_save_timer.start()

    def _combine_mappings(self) -> Dict[str, dict]:
        """组合远程映射和用户自定义映射（用户映射优先级更高）"""
        combined = self.remote_mappings.copy()
        combined.update(self.user_mappings)
        return combined

    def add_user_mapping(self, raw_name: str, standard_name: str, logo_url: str | None = None, group_name: str | None = None):
        """添加用户自定义映射"""
        with self._mapping_lock:
            unique_key = f"{standard_name}||{raw_name}"
            if unique_key not in self.user_mappings:
                self.user_mappings[unique_key] = {
                    'standard_name': standard_name,
                    'raw_names': [raw_name],
                    'logo_url': logo_url,
                    'group_name': group_name
                }
            else:
                if raw_name not in self.user_mappings[unique_key]['raw_names']:
                    self.user_mappings[unique_key]['raw_names'].append(raw_name)

            # 更新组合映射和反向映射
            self.combined_mappings = self._combine_mappings()
            self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
            self._normalized_index = self._build_normalized_index()

            # 保存用户映射
            self._save_user_mappings()

            self.logger.info(f"添加用户映射: {raw_name} -> {standard_name}")

    def remove_user_mapping(self, standard_name: str):
        """移除用户自定义映射（整个 standard_name 下所有 raw_name）"""
        with self._mapping_lock:
            keys_to_remove = [k for k in self.user_mappings if k.split('||')[0] == standard_name or k == standard_name]
            for key in keys_to_remove:
                del self.user_mappings[key]
            if keys_to_remove:
                self.combined_mappings = self._combine_mappings()
                self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
                self._normalized_index = self._build_normalized_index()
                self._save_user_mappings()
                self.logger.info(f"移除用户映射: {standard_name}")

    def remove_user_mapping_entry(self, standard_name: str, raw_name: str):
        """移除用户自定义映射中的单条 raw_name"""
        with self._mapping_lock:
            unique_key = f"{standard_name}||{raw_name}"
            if unique_key in self.user_mappings:
                del self.user_mappings[unique_key]
                self.combined_mappings = self._combine_mappings()
                self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
                self._normalized_index = self._build_normalized_index()
                self._save_user_mappings()
                self.logger.info(f"移除用户映射条目: {raw_name} -> {standard_name}")
            elif standard_name in self.user_mappings:
                raw_names = self.user_mappings[standard_name].get('raw_names', [])
                if raw_name in raw_names:
                    raw_names.remove(raw_name)
                    if not raw_names:
                        del self.user_mappings[standard_name]
                self.combined_mappings = self._combine_mappings()
                self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
                self._normalized_index = self._build_normalized_index()
                self._save_user_mappings()
                self.logger.info(f"移除用户映射条目: {raw_name} -> {standard_name}")

    def import_user_mappings(self, mappings: Dict[str, dict]):
        """批量导入用户自定义映射"""
        with self._mapping_lock:
            for key, data in mappings.items():
                standard_name = key.split('||')[0] if '||' in key else key
                raw_names = data.get('raw_names', [])
                if not raw_names:
                    continue
                for raw_name in raw_names:
                    unique_key = f"{standard_name}||{raw_name}"
                    if unique_key not in self.user_mappings:
                        self.user_mappings[unique_key] = {
                            'standard_name': standard_name,
                            'raw_names': [raw_name],
                            'logo_url': data.get('logo_url'),
                            'group_name': data.get('group_name')
                        }
                    else:
                        if raw_name not in self.user_mappings[unique_key]['raw_names']:
                            self.user_mappings[unique_key]['raw_names'].append(raw_name)
                        if data.get('logo_url'):
                            self.user_mappings[unique_key]['logo_url'] = data['logo_url']
                        if data.get('group_name'):
                            self.user_mappings[unique_key]['group_name'] = data['group_name']
            self.combined_mappings = self._combine_mappings()
            self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
            self._normalized_index = self._build_normalized_index()
            self._save_user_mappings()
            self.logger.info(f"批量导入用户映射: {len(mappings)} 条")

    def create_channel_fingerprint(self, url: str, channel_info: dict) -> str:
        """创建频道指纹"""
        # 使用URL和频道信息创建唯一指纹
        fingerprint_data = {
            'url': url,
            'service_name': channel_info.get('service_name', ''),
            'resolution': channel_info.get('resolution', ''),
            'codec': channel_info.get('codec', ''),
            'bitrate': channel_info.get('bitrate', '')
        }

        # 生成SHA256哈希作为指纹
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    def learn_from_scan_result(self, url: str, raw_name: str, channel_info: dict, mapped_name: str):
        """从扫描结果中学习并完善映射规则 - 优化版本"""
        if mapped_name == raw_name:
            return

        fingerprint = self.create_channel_fingerprint(url, channel_info)

        with self.fingerprint_lock:
            if fingerprint not in self.channel_fingerprints:
                self.channel_fingerprints[fingerprint] = {
                    'raw_name': raw_name,
                    'mapped_name': mapped_name,
                    'url': url,
                    'last_seen': time.time(),
                    'count': 1
                }
            else:
                self.channel_fingerprints[fingerprint]['count'] += 1
                self.channel_fingerprints[fingerprint]['last_seen'] = time.time()

            if self.channel_fingerprints[fingerprint]['count'] >= 3:
                current_mapped = self.channel_fingerprints[fingerprint]['mapped_name']

                if (current_mapped and mapped_name and
                    current_mapped != mapped_name and
                    current_mapped != raw_name and
                    mapped_name != raw_name):
                    self.logger.warning(f"频道映射不稳定: {raw_name} -> {current_mapped} vs {mapped_name}")

        self._schedule_fingerprint_save()

    def get_channel_info(self, raw_name: str, url: str | None = None, channel_info: dict | None = None) -> dict:
        """获取频道信息，支持智能学习和指纹匹配"""
        # 如果映射功能关闭，直接返回原始名称
        if not self.enable_mapping:
            return {
                'standard_name': raw_name,
                'logo_url': None,
                'group_name': None,
                'tvg_id': None,
                'tvg_chno': None,
                'tvg_shift': None,
                'catchup': None,
                'catchup_days': None,
                'catchup_source': None,
                'resolution': None
            }

        if not raw_name or raw_name.isspace():
            return {'standard_name': '', 'logo_url': None}

        # 重要修改：不再将原始名称转换为小写，保持原始大小写
        # 只进行基本的清理，不改变大小写
        cleaned_name = raw_name.strip()

        if not cleaned_name:
            return {'standard_name': raw_name, 'logo_url': None}

        # 1. 首先检查精确匹配（使用原始大小写）
        result = self._get_exact_match(cleaned_name)

        # 检查是否找到了映射（标准名称与输入名称不同）
        if result['standard_name'] != cleaned_name:  # 如果找到了映射
            self.logger.debug(f"找到映射: '{raw_name}' -> '{result['standard_name']}'")
            # 记录学习数据
            if url and channel_info:
                self.learn_from_scan_result(url, raw_name, channel_info, result['standard_name'])
            return result

        # 2. 如果没有精确匹配，尝试指纹匹配
        if url and channel_info:
            fingerprint = self.create_channel_fingerprint(url, channel_info)
            if fingerprint in self.channel_fingerprints:
                mapped_name = self.channel_fingerprints[fingerprint]['mapped_name']
                if mapped_name != raw_name:
                    self.logger.debug(f"通过指纹匹配找到映射: {raw_name} -> {mapped_name}")
                    # 通过指纹匹配找到映射后，再次尝试获取完整的频道信息
                    fingerprint_result = self._get_exact_match(mapped_name)
                    if fingerprint_result['standard_name'] != mapped_name:  # 如果找到了完整映射
                        return fingerprint_result
                    else:
                        # 如果没有找到完整映射，返回基本映射信息（包含所有字段）
                        return {
                            'standard_name': mapped_name,
                            'logo_url': None,
                            'group_name': None,
                            'tvg_id': None,
                            'tvg_chno': None,
                            'tvg_shift': None,
                            'catchup': None,
                            'catchup_days': None,
                            'catchup_source': None,
                            'resolution': None
                        }

            # 记录当前映射关系用于学习
            self.learn_from_scan_result(url, raw_name, channel_info, raw_name)

        # 3. 返回原始名称（包含所有字段，即使为空）
        # 移除调试日志：没有找到匹配的映射
        return {
            'standard_name': raw_name,
            'logo_url': None,
            'group_name': None,
            'tvg_id': None,
            'tvg_chno': None,
            'tvg_shift': None,
            'catchup': None,
            'catchup_days': None,
            'catchup_source': None,
            'resolution': None
        }

    def _build_normalized_index(self):
        index = {}
        for raw_pattern, info in self.reverse_mappings.items():
            if not raw_pattern or raw_pattern.isspace():
                continue
            norm = re.sub(r'\s+', ' ', raw_pattern.strip()).lower()
            index[norm] = info
        for unique_key, info in self.combined_mappings.items():
            standard_name = unique_key.split('||')[0] if '||' in unique_key else unique_key
            if not standard_name or standard_name.isspace():
                continue
            norm = re.sub(r'\s+', ' ', standard_name.strip()).lower()
            if norm not in index:
                index[norm] = {
                    'standard_name': standard_name,
                    'logo_url': info['logo_url'],
                    'group_name': info.get('group_name'),
                    'tvg_id': info.get('tvg_id'),
                    'tvg_chno': info.get('tvg_chno'),
                    'tvg_shift': info.get('tvg_shift'),
                    'catchup': info.get('catchup'),
                    'catchup_days': info.get('catchup_days'),
                    'catchup_source': info.get('catchup_source'),
                    'resolution': info.get('resolution')
                }
        return index

    def _get_exact_match(self, cleaned_name: str) -> dict:
        """精确匹配映射规则"""
        try:
            if cleaned_name in self.reverse_mappings:
                return self.reverse_mappings[cleaned_name]
        except Exception as e:
            self.logger.error(f"反向映射查找失败: {e}")

        normalized_name = re.sub(r'\s+', ' ', cleaned_name.strip()).lower()
        if normalized_name in self._normalized_index:
            return self._normalized_index[normalized_name]

        return {
            'standard_name': cleaned_name,
            'logo_url': None,
            'group_name': None,
            'tvg_id': None,
            'tvg_chno': None,
            'tvg_shift': None,
            'catchup': None,
            'catchup_days': None,
            'catchup_source': None,
            'resolution': None
        }

    def get_mapping_suggestions(self, raw_name: str) -> List[str]:
        """获取映射建议"""
        suggestions = []

        # 基于指纹历史记录提供建议 - 使用锁保护字典访问
        with self.fingerprint_lock:
            # 创建字典的副本进行遍历，避免迭代时字典被修改
            fingerprints_copy = self.channel_fingerprints.copy()

            for fingerprint, data in fingerprints_copy.items():
                if data['raw_name'] == raw_name and data['mapped_name'] != raw_name:
                    suggestions.append(data['mapped_name'])

        # 去重并返回
        return list(set(suggestions))

    def get_mapping_entries(self) -> List[dict]:
        """获取映射文件中的所有映射条目，按标准名称排序返回（与展示顺序一致）"""
        entries = []
        try:
            # 获取组合映射中的所有条目
            for unique_key, data in self.combined_mappings.items():
                # 从unique_key中提取标准名称和原始名称（格式为"标准名称||原始名称"）
                if '||' in unique_key:
                    standard_name = unique_key.split('||')[0]
                    raw_name = unique_key.split('||')[1]
                else:
                    standard_name = unique_key
                    raw_name = data.get('raw_names', [''])[0] if data.get('raw_names') else ''

                entry = {
                    'unique_key': unique_key,
                    'standard_name': standard_name,
                    'raw_name': raw_name,
                    'raw_names': data.get('raw_names', []),
                    'logo_url': data.get('logo_url'),
                    'group_name': data.get('group_name'),
                    'tvg_id': data.get('tvg_id'),
                    'tvg_chno': data.get('tvg_chno'),
                    'tvg_shift': data.get('tvg_shift'),
                    'catchup': data.get('catchup'),
                    'catchup_days': data.get('catchup_days'),
                    'catchup_source': data.get('catchup_source'),
                    'resolution': data.get('resolution')
                }
                entries.append(entry)

            # 按标准名称排序，保持一致性（文件中的顺序可能无法完全保留）
            entries.sort(key=lambda x: x['standard_name'])

            return entries
        except Exception as e:
            self.logger.error(f"获取映射条目失败: {e}")
            return []

    def check_remote_update_status(self) -> dict:
        """检查远程映射是否有更新，返回状态信息"""
        result = {
            'has_update': False,
            'last_cache_time': 0,
            'local_count': len(self.remote_mappings),
            'remote_count': 0,
            'error': None
        }

        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                result['last_cache_time'] = data.get('timestamp', 0)

            if not REQUESTS_AVAILABLE:
                result['error'] = 'requests模块不可用'
                return result

            remote_url = DEFAULT_REMOTE_URL
            try:
                config = ConfigManager()
                remote_url = config.get_value('channel_mappings', 'remote_url', DEFAULT_REMOTE_URL) or DEFAULT_REMOTE_URL
            except Exception as e:
                logger.debug(f"获取远程映射URL失败: {e}")

            try:
                head_resp = _http_head(remote_url, timeout=5, allow_redirects=True)
                try:
                    remote_etag = ''
                    if head_resp.status_code == 200:
                        remote_etag = head_resp.headers.get('ETag', '')
                        remote_last_modified = head_resp.headers.get('Last-Modified', '')

                        etag_file = self.cache_file + '.etag'
                        local_etag = ''
                        if os.path.exists(etag_file):
                            with open(etag_file, 'r', encoding='utf-8') as f:
                                local_etag = f.read().strip()

                        if remote_etag and local_etag and remote_etag != local_etag:
                            result['has_update'] = True
                            return result
                        if not remote_etag and not remote_last_modified:
                            pass
                    else:
                        with _http_get(remote_url, timeout=10, stream=True) as get_resp:
                            if get_resp.status_code == 200:
                                content = get_resp.content
                                content_hash = hashlib.md5(content).hexdigest()
                                hash_file = self.cache_file + '.hash'
                                local_hash = ''
                                if os.path.exists(hash_file):
                                    with open(hash_file, 'r', encoding='utf-8') as f:
                                        local_hash = f.read().strip()
                                if local_hash and content_hash != local_hash:
                                    result['has_update'] = True
                                decoded = content.decode('utf-8-sig', errors='replace')
                                result['remote_count'] = len(_parse_mappings_content(decoded, remote_url))
                                # 无论本地是否已有记录都要更新哈希，否则“有更新”会一直保持
                                try:
                                    _atomic_write_text(hash_file, content_hash)
                                except Exception as e:
                                    logger.debug(f"写入映射哈希失败: {e}")
                                if remote_etag:
                                    etag_file = self.cache_file + '.etag'
                                    try:
                                        _atomic_write_text(etag_file, remote_etag)
                                    except Exception as e:
                                        logger.debug(f"写入映射ETag失败: {e}")
                                return result
                finally:
                    try:
                        head_resp.close()
                    except Exception:
                        pass
            except requests.exceptions.RequestException as e:
                result['error'] = str(e)

        except Exception as e:
            result['error'] = str(e)

        return result

    def refresh_cache(self):
        """刷新远程映射缓存（失败时保留现有映射，不清空）"""
        new_remote = self._load_and_cache_remote_mappings()
        if new_remote is None:
            self.logger.warning("远程映射刷新失败，保留现有映射")
            return False
        with self._mapping_lock:
            self.remote_mappings = new_remote
            self.combined_mappings = self._combine_mappings()
            self.reverse_mappings = create_reverse_mappings(self.combined_mappings)
            self._normalized_index = self._build_normalized_index()
        try:
            if REQUESTS_AVAILABLE:
                remote_url = DEFAULT_REMOTE_URL
                try:
                    config = ConfigManager()
                    remote_url = config.get_value('channel_mappings', 'remote_url', DEFAULT_REMOTE_URL) or DEFAULT_REMOTE_URL
                except Exception:
                    pass
                try:
                    head_resp = _http_head(remote_url, timeout=5)
                    try:
                        if head_resp.status_code == 200 and head_resp.headers.get('ETag'):
                            etag_file = self.cache_file + '.etag'
                            _atomic_write_text(etag_file, head_resp.headers['ETag'])
                    finally:
                        head_resp.close()
                except Exception as e:
                    logger.debug(f"保存ETag失败: {e}")
        except Exception as e:
            logger.debug(f"刷新频道映射失败: {e}")
        self.logger.info("远程映射缓存已刷新")
        return True


def get_mapping_manager():
    """获取映射管理器实例（延迟加载）"""
    return ChannelMappingManager()


class MappingManagerProxy:
    """映射管理器代理类，提供延迟加载和后台刷新功能"""
    def __init__(self):
        self._manager = None
        self._bg_refresh_done = False
        self._init_lock = threading.Lock()

    def _get_manager(self):
        if self._manager is None:
            with self._init_lock:
                if self._manager is None:
                    self._manager = ChannelMappingManager()
                    if not self._bg_refresh_done:
                        self._bg_refresh_done = True
                        self._start_background_refresh()
        return self._manager

    def _start_background_refresh(self):
        def _do_refresh():
            try:
                new_remote = self._manager._load_and_cache_remote_mappings()
                if new_remote is None:
                    self._manager.logger.warning("后台刷新远程映射失败，保留现有映射")
                    return
                new_combined = self._manager._combine_mappings()
                new_reverse = create_reverse_mappings(new_combined)
                new_index = self._manager._build_normalized_index()
                with self._manager._mapping_lock:
                    self._manager.remote_mappings = new_remote
                    self._manager.combined_mappings = new_combined
                    self._manager.reverse_mappings = new_reverse
                    self._manager._normalized_index = new_index
                self._manager.logger.info("后台刷新远程映射完成")
            except Exception as e:
                self._manager.logger.warning(f"后台刷新远程映射失败: {e}")

        t = threading.Thread(target=_do_refresh, daemon=True)
        t.start()

    def __getattr__(self, name):
        return getattr(self._get_manager(), name)

    def __call__(self, *args, **kwargs):
        return self._get_manager()


# 创建代理实例
mapping_manager = MappingManagerProxy()


def extract_channel_name_from_url(url: str) -> str:
    """从URL提取频道名，支持多种协议格式"""
    try:
        # 标准化URL为小写
        url_lower = url.lower()

        # 组播地址提取 - 保留完整组播地址作为频道名
        for proto in ['rtp', 'stp', 'udp', 'rtsp']:
            proto_prefix = f'/{proto}/'
            if proto_prefix in url_lower:
                full_addr = url.split(proto_prefix)[1].split('?')[0].split('#')[0].strip()
                return full_addr

        # 处理单播URL中的频道ID模式
        if '/channel' in url_lower:
            import re
            match = re.search(r'/channel(\d+)/', url_lower)
            if match:
                return f"CHANNEL{match.group(1)}"

        # 处理PLTV/数字/数字/数字/index.m3u8模式
        if '/pltv/' in url_lower and '/index.m3u8' in url_lower:
            import re
            match = re.search(r'/pltv/(\d+)/(\d+)/(\d+)/', url_lower)
            if match:
                return f"PLTV_{match.group(3)}"

        # 处理数字ID.smil/.smail格式
        if url_lower.endswith(('.smil', '.smail')):
            import re
            match = re.search(r'/(\d+)\.(smil|smail)$', url_lower)
            if match:
                return match.group(1)

        # HTTP/HTTPS地址提取
        if url_lower.startswith(('http://', 'https://')):
            # 移除查询参数和片段标识符
            clean_url = url.split('?')[0].split('#')[0]
            parts = [p for p in clean_url.split('/') if p]  # 过滤空部分

            # 1. 优先提取路径中的数字ID - 检查所有部分
            for part in parts:
                # 先尝试直接匹配纯数字
                if part.isdigit():
                    return part
                # 尝试从混合字符串中提取数字
                digits = ''.join(filter(str.isdigit, part))
                if digits:
                    return digits

            # 2. 处理特殊文件名情况
            for i in range(len(parts)):
                part = parts[i]
                if part in ['playlist.m3u8', 'index.m3u8']:
                    # 尝试从整个URL路径中提取数字ID
                    for p in parts:
                        if p.isdigit():
                            return p
                    # 如果没有数字，返回前一部分
                    prev_part = parts[i-1] if i > 0 else part
                    # 检查前一部分是否是数字ID
                    if prev_part.isdigit():
                        return prev_part
                    return prev_part

            # 3. 处理类似3221225530这样的长数字ID
            last_part = parts[-1]
            if last_part.isdigit() and len(last_part) >= 6:  # 长数字ID
                return last_part

            # 4. 最后处理默认情况
            return parts[-1].split('.')[0] if '.' in parts[-1] else parts[-1]

        # 默认提取URL最后部分
        return url.split('/')[-1].split('?')[0].split('#')[0].strip()
    except Exception as e:
        logger.error(f"提取频道名失败: {e}")
        return url  # 如果提取失败，返回完整URL


def parse_mapping_line(line: str) -> Dict[str, dict]:
    """解析单行映射规则
    新格式: 标准名称 = "原始名称1" "原始名称2" = logo地址 = 分组名
    """
    if '=' not in line:
        return {}

    parts = [p.strip() for p in line.split('=', 3)]
    standard_name = parts[0]

    # 解析原始名称列表 - 保留引号内的原始空格
    import shlex
    raw_names = []
    try:
        # 使用shlex处理带引号的字符串
        parsed = shlex.split(parts[1])
        for name in parsed:
            # 只去除最外层的引号，保留内部空格
            if (name.startswith('"') and name.endswith('"')) or (name.startswith("'") and name.endswith("'")):
                name = name[1:-1]
            raw_names.append(name)
    except (ValueError, IndexError) as e:
        logger.debug(f"使用shlex解析映射行失败，回退到原始方法: {e}")
        # 如果解析失败，回退到原始方法
        raw_names = [name.strip('"\' ') for name in parts[1].split()]
    except Exception as e:
        logger.warning(f"解析映射行时发生意外错误: {e}")
        raw_names = [name.strip('"\' ') for name in parts[1].split()]

    # 解析logo地址(如果有)
    logo_url = parts[2].strip('"\' ') if len(parts) > 2 else None

    # 解析分组名(如果有)
    group_name = parts[3].strip('"\' ') if len(parts) > 3 else None

    return {
        standard_name: {
            'raw_names': raw_names,
            'logo_url': logo_url if logo_url and logo_url.lower() not in ['', 'none', 'null'] else None,
            'group_name': group_name if group_name and group_name.lower() not in ['', 'none', 'null'] else None
        }
    }


def get_channel_info(raw_name: str) -> dict:
    """获取频道信息(标准名称、logo地址和分组名)"""
    # 使用新的映射管理器
    return mapping_manager.get_channel_info(raw_name)


# 创建代理实例