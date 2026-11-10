import configparser
import os
import time
import threading
from .log_manager import global_logger as logger
from utils.config_notifier import notify_config_change
from utils.singleton import Singleton
from utils.app_paths import get_config_dir, migrate_legacy_data
from core.stores.window_layout_store import WindowLayoutStore
from core.stores.network_settings_store import NetworkSettingsStore
from core.stores.resume_store import ResumeStore
from core.stores.bookmark_store import BookmarkStore
from core.stores.video_eq_store import VideoEqStore
from core.stores.audio_eq_store import AudioEqStore


class ConfigManager(Singleton):

    def __init__(self, config_file='config.ini'):
        if self._initialized:
            return

        config_dir = get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self.config_dir = config_dir
        # 首次启动：旧版本把数据写在程序目录，先复制到用户目录再读取
        migrate_legacy_data(config_dir=config_dir)
        self.config_file = os.path.join(config_dir, config_file)
        self.config = configparser.ConfigParser(interpolation=None, strict=False)
        self._lock = threading.RLock()
        self._resume_file = os.path.join(config_dir, 'resume_positions.json')
        self._resume_cache: dict | None = None
        self._bookmark_file = os.path.join(config_dir, 'bookmarks.json')
        self._bookmark_cache: dict | None = None
        self._save_timer: threading.Timer | None = None
        self._save_timer_lock = threading.Lock()
        self._config_write_blocked = False
        self.load_config()
        # 域存储实例
        self._window_layout_store = WindowLayoutStore(self)
        self._network_settings_store = NetworkSettingsStore(self)
        self._resume_store = ResumeStore(self, self._resume_file)
        self._bookmark_store = BookmarkStore(self, self._bookmark_file)
        self._video_eq_store = VideoEqStore(self)
        self._audio_eq_store = AudioEqStore(self)
        self._initialized = True

    def save_window_layout(self, x, y, width, height, dividers):
        return self._window_layout_store.save_window_layout(x, y, width, height, dividers)

    def load_window_layout(
            self, default_x=100,
            default_y=100,
            default_width=800,
            default_height=600,
            default_dividers=None
            ):
        """加载窗口布局（包括位置和大小）"""
        def _load_int(section, key, default):
            val = self.get_value(section, key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
            return default
        x = _load_int('UI', 'window_x', default_x)
        y = _load_int('UI', 'window_y', default_y)
        width = _load_int('UI', 'window_width', default_width)
        height = _load_int('UI', 'window_height', default_height)
        dividers = []
        i = 0
        while True:
            pos = self.get_value('UI', f'divider_{i}')
            if pos is None:
                break
            try:
                dividers.append(int(pos))
            except (ValueError, TypeError):
                logger.debug(f"divider_{i} 值无效: {pos}，跳过")
            i += 1
        return x, y, width, height, dividers or default_dividers

    def save_network_settings(self, url, timeout, threads, user_agent, referer):
        return self._network_settings_store.save_network_settings(url, timeout, threads, user_agent, referer)

    def load_network_settings(self):
        return self._network_settings_store.load_network_settings()

    def save_url_history(self, urls):
        return self._network_settings_store.save_url_history(urls)

    def load_url_history(self):
        return self._network_settings_store.load_url_history()

    def save_language_settings(self, language_code):
        """保存语言设置"""
        self.set_value('Language', 'current_language', language_code)
        return self.save_config()

    def load_language_settings(self):
        """加载语言设置"""
        return self.get_value('Language', 'current_language', 'zh')

    def save_display_settings(self, font_size_tier, ui_scale_percent):
        """保存 PC 端字号档位与界面缩放档位。

        字号档位与缩放的真源在 ui/typography.py，这里只负责持久化；
        非法值由 typography 在校验层兜底，不会把坏配置写坏界面。
        """
        self.set_value('UI', 'font_size_tier', str(font_size_tier))
        self.set_value('UI', 'ui_scale_percent', str(int(ui_scale_percent)))
        return self.save_config()

    def load_display_settings(self):
        """加载字号档位与界面缩放，返回 (tier, percent)。"""
        tier = self.get_value('UI', 'font_size_tier', 'standard') or 'standard'
        percent = self.get_value('UI', 'ui_scale_percent', '100') or '100'
        return tier, percent

    def save_scan_retry_settings(self, enable_retry):
        return self._network_settings_store.save_scan_retry_settings(enable_retry)

    def load_scan_retry_settings(self):
        return self._network_settings_store.load_scan_retry_settings()

    def load_config(self):
        with self._lock:
            if os.path.exists(self.config_file):
                try:
                    # utf-8-sig 兼容带 BOM 的配置文件（用户手工编辑常见）
                    self.config.read(self.config_file, encoding='utf-8-sig')
                    logger.debug(f"配置管理-成功加载配置文件: {self.config_file}")
                    return True
                except configparser.Error as e:
                    logger.error(f"配置管理-解析配置文件失败: {str(e)}", exc_info=True)
                    self._backup_broken_config('parse_error')
                    return False
                except IOError as e:
                    logger.error(f"配置管理-读取配置文件失败: {str(e)}", exc_info=True)
                    return False
                except Exception as e:
                    logger.error(f"配置管理-加载配置文件失败: {str(e)}", exc_info=True)
                    return False
            # 配置文件不存在：立即创建空文件，避免后续"缺少 config.ini"提示
            logger.info(f"配置管理-配置文件不存在，自动创建: {self.config_file}")
            try:
                config_dir = os.path.dirname(self.config_file)
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    self.config.write(f)
                return True
            except Exception as e:
                logger.warning(f"配置管理-自动创建配置文件失败: {e}")
                return False

    def _backup_broken_config(self, reason: str):
        """配置解析失败时备份原文件并重置解析器。

        若备份失败则阻止后续写入，避免用空配置覆盖用户原文件造成不可恢复的数据丢失。
        """
        try:
            import shutil
            backup = f"{self.config_file}.bad.{reason}.{int(time.time())}"
            shutil.copy2(self.config_file, backup)
            self._config_write_blocked = False
            logger.error(f"配置管理-已备份损坏的配置文件: {backup}")
        except Exception as e:
            self._config_write_blocked = True
            logger.error(f"配置管理-备份损坏配置文件失败，已禁止写入配置: {e}")
        # 丢弃可能已被部分解析的内容，避免半截配置参与后续读写
        self.config = configparser.ConfigParser(interpolation=None, strict=False)

    def save_config(self, immediate: bool = False):
        if immediate:
            self._cancel_save_timer()
            return self._do_save_config()
        with self._save_timer_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(0.5, self._do_save_config)
            self._save_timer.daemon = True
            self._save_timer.start()
        return True

    def _cancel_save_timer(self):
        with self._save_timer_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

    def flush(self):
        self._cancel_save_timer()
        return self._do_save_config()

    def _do_save_config(self):
        with self._save_timer_lock:
            self._save_timer = None
        if self._config_write_blocked:
            logger.error("配置管理-配置文件损坏且备份失败，已跳过写入以避免覆盖原文件")
            return False
        with self._lock:
            try:
                config_dir = os.path.dirname(self.config_file)
                if not os.path.exists(config_dir):
                    os.makedirs(config_dir)
                    logger.info(f"配置管理-创建配置目录: {config_dir}")

                # 原子写入：先写入临时文件，再 rename 覆盖目标文件
                import tempfile
                fd, tmp_path = tempfile.mkstemp(
                    dir=config_dir, suffix='.tmp', prefix='cfg_'
                )
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        self.config.write(f)
                    os.replace(tmp_path, self.config_file)
                except Exception:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    raise
                logger.debug(f"配置管理-成功保存配置文件: {self.config_file}")
                return True
            except IOError as e:
                logger.error(f"配置管理-写入配置文件失败: {str(e)}", exc_info=True)
                return False
            except Exception as e:
                logger.error(f"配置管理-保存配置文件失败: {str(e)}", exc_info=True)
                return False

    def _parse_bool(self, value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        # 兼容旧版本/手工编辑产生的多种布尔写法
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y')

    def _parse_int(self, value, default=0):
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _parse_float(self, value, default=0.0):
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def get_value(self, section, key, default=None):
        with self._lock:
            try:
                if not self.config.has_section(section):
                    self.config.add_section(section)
                return self.config.get(section, key)
            except configparser.NoOptionError:
                return default
            except Exception as e:
                logger.error(f"配置管理-获取配置值失败: {str(e)}", exc_info=True)
                return default

    def set_value(self, section, key, value):
        with self._lock:
            try:
                if not self.config.has_section(section):
                    self.config.add_section(section)
                    logger.debug(f"配置管理-创建section: {section}")

                try:
                    old_value = self.config.get(section, key)
                except (configparser.NoSectionError, configparser.NoOptionError):
                    old_value = None

                self.config.set(section, key, value)

                if old_value != value:
                    notify_config_change(section, key, old_value, value)
                    logger.debug(f"配置管理-配置变更: {section}.{key} = {old_value} -> {value}")
            except Exception as e:
                logger.error(f"配置管理-设置配置值失败: {str(e)}", exc_info=True)

    def remove_option(self, section, key):
        with self._lock:
            try:
                if self.config.has_section(section) and self.config.has_option(section, key):
                    self.config.remove_option(section, key)
            except Exception as e:
                logger.debug(f"配置管理-移除选项失败: {section}.{key}: {e}")

    def save_ui_settings(self, settings: dict):
        return self._window_layout_store.save_ui_settings(settings)

    def load_ui_settings(self, defaults: dict | None = None) -> dict:
        return self._window_layout_store.load_ui_settings(defaults)

    def save_scan_engine_settings(self, engine: str):
        return self._network_settings_store.save_scan_engine_settings(engine)

    def load_scan_engine_settings(self) -> dict:
        return self._network_settings_store.load_scan_engine_settings()

    def save_server_settings(self, enabled: bool = False, port: int = 8080,
                             host: str = '0.0.0.0', auto_start: bool = False):
        """保存Server后端设置（默认关闭，按需手动开启）"""
        return self._network_settings_store.save_server_settings(
            enabled=enabled, port=port, host=host, auto_start=auto_start
        )

    def load_server_settings(self) -> dict:
        return self._network_settings_store.load_server_settings()

    def save_mapping_settings(self, enable_mapping: bool = True):
        return self._network_settings_store.save_mapping_settings(enable_mapping)

    def load_mapping_settings(self) -> dict:
        return self._network_settings_store.load_mapping_settings()

    def save_close_behavior(self, action: str):
        return self._window_layout_store.save_close_behavior(action)

    def load_close_behavior(self) -> str | None:
        """加载关闭行为设置，返回 'minimize_tray'、'exit' 或 None（未设置则弹窗询问）"""
        value = self.get_value('UI', 'close_action')
        if value in ('minimize_tray', 'exit'):
            return value
        return None

    def clear_close_behavior(self):
        return self._window_layout_store.clear_close_behavior()

    def save_playlist_sources(self, sources: list):
        """保存多个直播源配置

        Args:
            sources: 直播源列表，每个元素为字典格式：
                    {'url': str, 'name': str, 'enabled': bool, 'last_update': str|None}
        """
        self.set_value('PlaylistSources', 'count', str(len(sources)))
        for i, source in enumerate(sources):
            self.set_value('PlaylistSources', f'url_{i}', source.get('url', ''))
            self.set_value('PlaylistSources', f'name_{i}', source.get('name', f'Source {i+1}'))
            self.set_value('PlaylistSources', f'enabled_{i}', str(source.get('enabled', True)))
            self.set_value('PlaylistSources', f'last_update_{i}', source.get('last_update', '') or '')
        self._cleanup_stale_indexed_keys('PlaylistSources', len(sources))
        self._cleanup_legacy_playlist_keys()
        return self.save_config()

    def _cleanup_stale_indexed_keys(self, section: str, count: int, suffixes=('url', 'name', 'enabled', 'last_update')):
        """删除序号 >= count 的残留键，避免配置文件随着增删条目无限膨胀"""
        with self._lock:
            if not self.config.has_section(section):
                return
            for option in list(self.config.options(section)):
                for suffix in suffixes:
                    prefix = f'{suffix}_'
                    if not option.startswith(prefix):
                        continue
                    idx_part = option[len(prefix):]
                    if not idx_part.isdigit():
                        continue
                    if int(idx_part) >= count:
                        self.config.remove_option(section, option)
                        logger.debug(f"配置清理-移除残留键: {section}.{option}")
                    break

    def _cleanup_legacy_playlist_keys(self):
        """清理旧[Playlist]段中已迁移到[PlaylistSources]的遗留键"""
        legacy_keys = ['url', 'name', 'last_update', 'last_url']
        for key in legacy_keys:
            if self.config.has_option('Playlist', key):
                self.config.remove_option('Playlist', key)
                logger.debug(f"配置清理-移除旧键: Playlist.{key}")
        if self.config.has_option('Playlist', 'update_interval'):
            old_val = self.get_value('Playlist', 'update_interval')
            if old_val and not self.config.has_option('PlaylistSources', 'update_interval'):
                self.set_value('PlaylistSources', 'update_interval', old_val)
            self.config.remove_option('Playlist', 'update_interval')
            logger.debug("配置清理-迁移 Playlist.update_interval -> PlaylistSources.update_interval")
        if self.config.has_section('Playlist') and not self.config.options('Playlist'):
            self.config.remove_section('Playlist')
            logger.debug("配置清理-移除空段: [Playlist]")

    def load_playlist_sources(self) -> list:
        """加载多个直播源配置

        Returns:
            直播源列表
        """
        sources = []
        count = self._parse_int(self.get_value('PlaylistSources', 'count', '0') or '0')
        for i in range(count):
            url = self.get_value('PlaylistSources', f'url_{i}')
            if url:
                sources.append({
                    'url': url,
                    'name': self.get_value('PlaylistSources', f'name_{i}', f'Source {i+1}'),
                    'enabled': self._parse_bool(self.get_value('PlaylistSources', f'enabled_{i}', 'True'), True),
                    'last_update': self.get_value('PlaylistSources', f'last_update_{i}', '') or None
                })

        if not sources:
            legacy_url = self.get_value('Playlist', 'url', '')
            if legacy_url:
                sources.append({
                    'url': legacy_url,
                    'name': self.get_value('Playlist', 'name', 'Default'),
                    'enabled': True
                })
                self._cleanup_legacy_playlist_keys()
                if sources:
                    self.save_playlist_sources(sources)
        return sources

    def get_active_playlist_source(self) -> dict | None:
        """获取当前启用的直播源

        Returns:
            当前启用的直播源字典，如果没有则返回None
        """
        sources = self.load_playlist_sources()
        for source in sources:
            if source.get('enabled'):
                return source
        return sources[0] if sources else None

    def set_active_playlist_source(self, index: int):
        """设置指定索引的直播源为启用状态

        Args:
            index: 直播源索引
        """
        sources = self.load_playlist_sources()
        if 0 <= index < len(sources):
            for i, source in enumerate(sources):
                source['enabled'] = (i == index)
            self.save_playlist_sources(sources)

    def get_active_playlist_source_index(self) -> int:
        """获取当前启用的直播源索引

        Returns:
            启用源的索引，没有则返回 -1
        """
        sources = self.load_playlist_sources()
        for i, source in enumerate(sources):
            if source.get('enabled'):
                return i
        return 0 if sources else -1

    def update_playlist_source_last_update(self, index: int, timestamp: str):
        """更新指定索引直播源的更新时间

        Args:
            index: 源索引
            timestamp: ISO格式时间字符串
        """
        sources = self.load_playlist_sources()
        if 0 <= index < len(sources):
            sources[index]['last_update'] = timestamp
            self.save_playlist_sources(sources)

    def save_epg_sources(self, sources: list):
        """保存多个EPG源配置

        Args:
            sources: EPG源列表，每个元素为字典格式：
                    {'url': str, 'name': str, 'last_update': str|None}
        """
        self.set_value('EPGSources', 'count', str(len(sources)))
        for i, source in enumerate(sources):
            self.set_value('EPGSources', f'url_{i}', source.get('url', ''))
            self.set_value('EPGSources', f'name_{i}', source.get('name', f'EPG {i+1}'))
            self.set_value('EPGSources', f'last_update_{i}', source.get('last_update', '') or '')
        self._cleanup_legacy_epg_keys()
        return self.save_config()

    def _cleanup_legacy_epg_keys(self):
        """清理旧[EPG]段中已迁移到[EPGSources]的遗留键"""
        legacy_keys = ['epg_url', 'epg_source', 'last_update', 'last_url']
        for key in legacy_keys:
            if self.config.has_option('EPG', key):
                self.config.remove_option('EPG', key)
                logger.debug(f"配置清理-移除旧键: EPG.{key}")
        if self.config.has_option('EPG', 'update_interval'):
            old_val = self.get_value('EPG', 'update_interval')
            if old_val and not self.config.has_option('EPGSources', 'update_interval'):
                self.set_value('EPGSources', 'update_interval', old_val)
            self.config.remove_option('EPG', 'update_interval')
            logger.debug("配置清理-迁移 EPG.update_interval -> EPGSources.update_interval")
        if self.config.has_section('EPG') and not self.config.options('EPG'):
            self.config.remove_section('EPG')
            logger.debug("配置清理-移除空段: [EPG]")

    def load_epg_sources(self) -> list:
        """加载多个EPG源配置

        Returns:
            EPG源列表
        """
        sources = []
        count = self._parse_int(self.get_value('EPGSources', 'count', '0') or '0')
        for i in range(count):
            url = self.get_value('EPGSources', f'url_{i}')
            if url:
                sources.append({
                    'url': url,
                    'name': self.get_value('EPGSources', f'name_{i}', f'EPG {i+1}'),
                    'last_update': self.get_value('EPGSources', f'last_update_{i}', '') or None
                })

        if not sources:
            legacy_url = self.get_value('EPG', 'epg_url', '')
            if legacy_url:
                sources.append({
                    'url': legacy_url,
                    'name': self.get_value('EPG', 'epg_source', 'Default')
                })
                self._cleanup_legacy_epg_keys()
                if sources:
                    self.save_epg_sources(sources)
        return sources

    def update_epg_source_last_update(self, index: int, timestamp: str):
        """更新指定索引EPG源的更新时间

        Args:
            index: 源索引
            timestamp: ISO格式时间字符串
        """
        sources = self.load_epg_sources()
        if 0 <= index < len(sources):
            sources[index]['last_update'] = timestamp
            self.save_epg_sources(sources)

    def save_recent_files(self, recent_files):
        """保存最近打开的文件列表"""
        recent_files = recent_files[:10]
        old_count = self._parse_int(self.get_value('RecentFiles', 'count', '0') or '0')
        self.set_value('RecentFiles', 'count', str(len(recent_files)))
        for i, file_path in enumerate(recent_files):
            self.set_value('RecentFiles', f'file_{i}', file_path)
        with self._lock:
            for i in range(len(recent_files), old_count + 5):
                try:
                    self.config.remove_option('RecentFiles', f'file_{i}')
                except (configparser.NoSectionError, configparser.NoOptionError):
                    pass
        return self.save_config()

    def load_recent_files(self):
        """加载最近打开的文件列表"""
        recent_files = []
        count = self._parse_int(self.get_value('RecentFiles', 'count', '0') or '0')
        for i in range(count):
            file_path = self.get_value('RecentFiles', f'file_{i}')
            if file_path:
                recent_files.append(file_path)
        return recent_files

    def add_recent_file(self, file_path):
        recent_files = self.load_recent_files()
        if file_path in recent_files:
            recent_files.remove(file_path)
        recent_files.insert(0, file_path)
        return self.save_recent_files(recent_files)

    def remove_recent_file(self, file_path):
        recent_files = self.load_recent_files()
        if file_path in recent_files:
            recent_files.remove(file_path)
            self.save_recent_files(recent_files)
            return True
        return False

    def save_theme_settings(self, color_mode, visual_style='flat'):
        return self._window_layout_store.save_theme_settings(color_mode, visual_style)

    def load_theme_settings(self):
        return self._window_layout_store.load_theme_settings()

    def save_all_settings(self, settings_dict: dict):
        """保存所有设置"""
        for section, section_settings in settings_dict.items():
            for key, value in section_settings.items():
                self.set_value(section, key, str(value))
        return self.save_config()

    def save_playback_settings(self, settings=None):
        defaults = {
            'hwdec': 'auto-copy',
            'hls_readahead_secs': 0,
            'user_agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'tls_verify': False,
            'http_headers': '',
            'rtsp_transport': 'tcp',
            'rtsp_user_agent': 'VLC/3.0.18Libmpv',
            'network_timeout_sec': 30,
            'audio_passthrough': 'never',
            'hdr_output_mode': 'disable',
            'queue_mode': 'none',
            'http_referer': '',
            'http_proxy': '',
            'auto_skip_intro': False,
            'skip_intro_seconds': 0.0,
            'auto_skip_outro': False,
            'skip_outro_seconds': 0.0,
            # 高级播放器参数（与安卓端 PlayerSettingsPanel 对齐）
            # vo: 'auto' 表示按 hdr_output_mode 自动推导
            'vo': 'auto',
            # video-sync: 'audio' 默认以音频时钟为基准
            'video_sync': 'audio',
            # framedrop: 'vo' 默认 VO 慢时丢帧
            'framedrop': 'vo',
            # 缓存覆盖：0 或空表示使用动态智能调整（按流类型/分辨率/HDR 计算）
            'cache_secs_override': 0,
            'demuxer_readahead_secs_override': 0,
            'demuxer_max_bytes_mib_override': 0,
            # demuxer 探测参数覆盖：0 表示使用自动值（按流类型自动选择）
            'probesize_override': 0,
            'analyzeduration_override': 0,
            # 隔行扫描：'no' 默认不启用（与 mpv_player_service.py 默认值同步）
            'deinterlace': 'no',
        }
        if settings:
            defaults.update(settings)
        for key, value in defaults.items():
            if isinstance(value, bool):
                self.set_value('Playback', key, str(value))
            elif isinstance(value, float):
                self.set_value('Playback', key, str(value))
            elif isinstance(value, int):
                self.set_value('Playback', key, str(value))
            else:
                self.set_value('Playback', key, str(value))
        return self.save_config()

    def load_playback_settings(self):
        defaults = {
            'hwdec': 'auto-copy',
            'hls_readahead_secs': 0,
            'user_agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'tls_verify': False,
            'http_headers': '',
            'rtsp_transport': 'tcp',
            'rtsp_user_agent': 'VLC/3.0.18Libmpv',
            'network_timeout_sec': 30,
            'audio_passthrough': 'never',
            'hdr_output_mode': 'disable',
            'queue_mode': 'none',
            'http_referer': '',
            'http_proxy': '',
            'auto_skip_intro': False,
            'skip_intro_seconds': 0.0,
            'auto_skip_outro': False,
            'skip_outro_seconds': 0.0,
            # 高级播放器参数（与安卓端 PlayerSettingsPanel 对齐）
            'vo': 'auto',
            'video_sync': 'audio',
            'framedrop': 'vo',
            'cache_secs_override': 0,
            'demuxer_readahead_secs_override': 0,
            'demuxer_max_bytes_mib_override': 0,
            # demuxer 探测参数覆盖：0 表示使用自动值（按流类型自动选择）
            'probesize_override': 0,
            'analyzeduration_override': 0,
            # 隔行扫描：'no' 默认不启用（与 mpv_player_service.py 默认值同步）
            'deinterlace': 'no',
        }
        result = {}
        need_save = False
        # 批量收集缺失的键，减少锁争用和通知开销
        missing_keys = {}
        for key, default in defaults.items():
            raw = self.get_value('Playback', key)
            if raw is None:
                result[key] = default
                missing_keys[key] = str(default)
                need_save = True
            elif isinstance(default, bool):
                result[key] = self._parse_bool(raw)
            elif isinstance(default, float):
                try:
                    result[key] = float(raw)
                except (ValueError, TypeError):
                    result[key] = default
            elif isinstance(default, int):
                try:
                    result[key] = int(raw)
                except (ValueError, TypeError):
                    result[key] = default
            else:
                result[key] = raw
        # 批量写入缺失的键，避免逐个 set_value 时的重复锁争用
        if missing_keys:
            with self._lock:
                if not self.config.has_section('Playback'):
                    self.config.add_section('Playback')
                for key, value in missing_keys.items():
                    self.config.set('Playback', key, value)
        if need_save:
            self.save_config()
        return result

    def save_last_channel(self, file_path, channel_name, channel_index):
        return self._resume_store.save_last_channel(file_path, channel_name, channel_index)

    def load_last_channel(self):
        return self._resume_store.load_last_channel()

    # ---------- 断点续播（JSON 文件存储）----------
    def _load_resume_cache(self):
        return self._resume_store._load_resume_cache()

    def _save_resume_cache(self):
        return self._resume_store._save_resume_cache()

    def save_resume_position(self, url: str, position: float, duration: float, name: str = ''):
        return self._resume_store.save_resume_position(url, position, duration, name)

    def load_resume_position(self, url: str) -> dict | None:
        """加载指定 URL 的播放位置"""
        return self._resume_store.load_resume_position(url)

    def load_all_resume_positions(self) -> list:
        return self._resume_store.load_all_resume_positions()

    def clear_resume_position(self, url: str):
        return self._resume_store.clear_resume_position(url)

    def clear_all_resume_positions(self):
        return self._resume_store.clear_all_resume_positions()

    # ---------- 书签管理（JSON 文件存储）----------
    # 一个 URL 可对应多个书签，每个书签结构：{position, name, created_at}
    def _load_bookmark_cache(self):
        return self._bookmark_store._load_bookmark_cache()

    def _save_bookmark_cache(self):
        return self._bookmark_store._save_bookmark_cache()

    def save_bookmark(self, url: str, position: float, name: str = ''):
        return self._bookmark_store.save_bookmark(url, position, name)

    def load_bookmarks(self, url: str) -> list:
        return self._bookmark_store.load_bookmarks(url)

    def load_all_bookmarks(self) -> list:
        return self._bookmark_store.load_all_bookmarks()

    def delete_bookmark(self, url: str, position: float) -> bool:
        return self._bookmark_store.delete_bookmark(url, position)

    def clear_bookmarks(self, url: str):
        return self._bookmark_store.clear_bookmarks(url)

    def clear_all_bookmarks(self):
        return self._bookmark_store.clear_all_bookmarks()

    # ---------- 字幕样式与控制 ----------

    def save_subtitle_style(self, settings: dict):
        return self._video_eq_store.save_subtitle_style(settings)

    def load_subtitle_style(self) -> dict:
        return self._video_eq_store.load_subtitle_style()

    # ---------- 视频图像调整 ----------

    def save_video_eq(self, settings: dict):
        return self._video_eq_store.save_video_eq(settings)

    def load_video_eq(self) -> dict:
        return self._video_eq_store.load_video_eq()

    # ---------- 音频系统增强 ----------

    def save_audio_eq(self, settings: dict):
        return self._audio_eq_store.save_audio_eq(settings)

    def load_audio_eq(self) -> dict:
        return self._audio_eq_store.load_audio_eq()

    def load_all_settings(self) -> dict:
        """加载所有设置"""
        all_settings = {}
        for section in self.config.sections():
            all_settings[section] = {}
            for key in self.config.options(section):
                all_settings[section][key] = self.config.get(section, key)
        return all_settings
