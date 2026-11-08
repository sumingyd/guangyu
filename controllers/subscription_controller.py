"""
订阅控制器 - 负责订阅源管理、EPG加载、频道分组等
从 pyqt_player.py 提取的独立模块
"""

import hashlib
import os
from typing import Optional, Dict, Any
from datetime import datetime
from PySide6.QtCore import QThread, Signal, QTimer

from core.log_manager import global_logger as logger
from core.config_manager import ConfigManager
from core.subscription_manager import global_subscription_manager
from utils.general_utils import get_display_channel_name
from controllers.main_window_protocol import EpgProtocol


class SubscriptionWorker(QThread):
    """后台线程处理订阅更新"""
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def run(self):
        try:
            result = self._callback()
            self.finished.emit(result)
        except TypeError as e:
            if '__init__() should return None' in str(e):
                logger.debug(f"忽略 PySide6/Python 3.14 __init__ 兼容性错误: {e}")
                self.finished.emit(None)
            else:
                self.error.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class SubscriptionController:
    """订阅控制器 - 管理所有订阅源相关的逻辑"""

    def __init__(self, main_window: EpgProtocol):
        self.window: EpgProtocol = main_window
        self._subscription_checked = False
        self._workers = []
        self._last_header_epg_url = None

    def _cleanup_worker(self, worker):
        """从_workers列表中移除已完成的worker"""
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def handle_playlist_subscription(self, need_update: bool, playlist_url: str, source_index=None):
        """在后台线程中处理列表订阅（按源索引独立判断）"""
        try:
            if not playlist_url:
                logger.debug("无播放列表URL，跳过订阅处理")
                return

            logger.debug(f"处理列表订阅: url={playlist_url[:50]}..., need_update={need_update}, source_index={source_index}")

            if need_update:
                logger.info(f"需要更新订阅源，开始下载: {playlist_url[:50]}...")
                content = self._download_subscription_content(playlist_url)

                if content:
                    self._save_to_local_cache(content, playlist_url)
                    self._process_m3u_content(content, playlist_url, source_index)
                else:
                    logger.warning(f"下载订阅内容为空: {playlist_url}")
            else:
                logger.debug("使用缓存数据，无需更新")
                cached_content = self._load_from_local_cache(playlist_url)
                if cached_content:
                    logger.debug("从本地缓存加载M3U数据")
                    self._process_m3u_content(cached_content, playlist_url, source_index)
                else:
                    logger.warning("本地缓存不存在，强制重新下载")
                    content = self._download_subscription_content(playlist_url)
                    if content:
                        self._save_to_local_cache(content, playlist_url)
                        self._process_m3u_content(content, playlist_url, source_index)

        except Exception as e:
            logger.error(f"处理列表订阅失败: {e}", exc_info=True)

    def _download_subscription_content(self, url: str) -> Optional[str]:
        """下载订阅内容"""
        import requests
        from utils.http_session import get as _http_get

        config = ConfigManager()
        timeout = int(config.get_value('Network', 'timeout', '30') or 30)

        from utils.general_utils import sanitize_http_header_value
        headers = {}
        user_agent = sanitize_http_header_value(
            config.get_value('Network', 'user_agent', ''))
        referer = sanitize_http_header_value(
            config.get_value('Network', 'referer', ''))
        if user_agent:
            headers['User-Agent'] = user_agent
        if referer:
            headers['Referer'] = referer

        try:
            ssl_verify = config.get_value('Network', 'ssl_verify', 'true').lower() != 'false'
            response = _http_get(url, timeout=timeout, headers=headers,
                                   allow_redirects=True, verify=ssl_verify)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            logger.warning(f"下载超时: {url}")
            return None
        except Exception as e:
            logger.error(f"下载失败: {url}, 错误: {e}")
            return None

    def _get_cache_file_path(self, url: str) -> str:
        """获取缓存文件路径（基于URL的hash）"""
        from utils.app_paths import get_cache_dir
        cache_dir = get_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(cache_dir, f'm3u_{url_hash}.cache')

    def _save_to_local_cache(self, content: str, url: str):
        """保存M3U内容到本地缓存"""
        try:
            cache_path = self._get_cache_file_path(url)
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"M3U内容已保存到本地缓存: {cache_path}")
        except Exception as e:
            logger.warning(f"保存M3U缓存失败: {e}")

    def _load_from_local_cache(self, url: str) -> str | None:
        """从本地缓存加载M3U内容"""
        try:
            cache_path = self._get_cache_file_path(url)
            if not os.path.exists(cache_path):
                return None
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"从本地缓存加载M3U内容: {cache_path}, 大小: {len(content)} 字节")
            return content
        except Exception as e:
            logger.warning(f"加载M3U缓存失败: {e}")
            return None

    def _process_m3u_content(self, content: str, file_path: str, source_index=None):
        """处理M3U内容（纯Python解析，避免子线程中操作Qt对象）"""
        try:
            # 使用纯 Python 方式解析 M3U 内容（不依赖 Qt 对象）
            channels_data, header_attrs = self._parse_m3u_content_pure_python(content)

            if not channels_data:
                logger.warning(f"M3U内容解析为空: {file_path[:50]}...")
                return

            logger.info(f"M3U处理完成，共 {len(channels_data)} 个频道（数据已准备就绪，等待主线程回调刷新UI）")

            # 保存原始文件内容到配置
            config = ConfigManager()

            if file_path.startswith('http'):
                config.add_recent_file(file_path)

                # 更新订阅源的最后下载时间（用于缓存判断）
                sources = global_subscription_manager.get_playlist_sources()
                for idx, src in enumerate(sources):
                    if src.get('url') == file_path:
                        global_subscription_manager.update_playlist_source_last_update(
                            idx, datetime.now().isoformat()
                        )
                        break

            # 获取 ApplicationState
            from core.application_state import app_state

            app_state.channels = channels_data

            # 记录文件头EPG地址（在订阅EPG加载后再作为补充源加载）
            epg_url = header_attrs.get('epg_url', '')
            if epg_url:
                self._last_header_epg_url = epg_url
                logger.info(f"M3U文件头包含EPG地址: {epg_url[:80]}，将在订阅EPG加载后补充")
            else:
                self._last_header_epg_url = None

        except Exception as e:
            logger.error(f"处理M3U内容失败: {e}", exc_info=True)

    def _parse_m3u_content_pure_python(self, content: str) -> tuple:
        from services.m3u_parser import parse_m3u_content
        channels, header_attrs = parse_m3u_content(content)
        if header_attrs.get('epg_url'):
            logger.info(f"M3U文件头发现EPG地址: {header_attrs['epg_url'][:80]}")
        return channels, header_attrs

    def _get_display_channel_name(self, channel: Dict[str, Any]) -> str:
        """获取用于显示的频道名称（委托给通用工具函数）"""
        language_manager = getattr(self.window, 'language_manager', None)
        return get_display_channel_name(channel, language_manager)

    def _should_update_source(self, source: dict, source_index: int) -> bool:
        """判断订阅源是否需要更新（基于缓存机制）

        Args:
            source: 订阅源配置字典
            source_index: 订阅源索引

        Returns:
            True 表示需要更新，False 表示使用缓存
        """
        # 获取最后更新时间
        last_update_str = source.get('last_update', '')

        if not last_update_str:
            logger.debug(f"订阅源 '{source.get('name', '')}' 无缓存记录，需要下载")
            return True

        try:
            last_update = datetime.fromisoformat(last_update_str)
        except (ValueError, TypeError):
            logger.warning(f"订阅源 '{source.get('name', '')}' 缓存时间格式无效: {last_update_str}，需要重新下载")
            return True

        # 获取更新间隔配置（分钟）
        config = ConfigManager()
        update_interval = int(config.get_value('PlaylistSources', 'update_interval', '60') or 60)

        now = datetime.now()
        elapsed = (now - last_update).total_seconds() / 60  # 转换为分钟

        if elapsed >= update_interval:
            logger.info(f"订阅源 '{source.get('name', '')}' 缓存已过期（上次: {last_update_str}, 已过 {elapsed:.0f} 分钟, 间隔: {update_interval} 分钟）")
            return True

        logger.debug(f"订阅源 '{source.get('name', '')}' 缓存有效（上次: {last_update_str}, 已过 {elapsed:.0f} 分钟, 间隔: {update_interval} 分钟）")
        return False

    def start_subscription_timers(self):
        """启动订阅更新定时器"""
        logger.debug("start_subscription_timers: 开始")

        try:

            active_source = global_subscription_manager.get_active_playlist_source()
            playlist_url = active_source.get('url', '') if active_source else ''

            if not playlist_url:
                logger.debug("无活跃的播放列表源")
                return

            # 启动后台更新
            worker = SubscriptionWorker(
                lambda: self._do_start_subscription(playlist_url),
                self.window
            )
            worker.finished.connect(self._on_subscription_finished)
            worker.finished.connect(lambda: self._cleanup_worker(worker))
            worker.error.connect(lambda err: logger.error(f"订阅更新错误: {err}"))
            self._workers.append(worker)
            worker.start()

            # 启动定期刷新定时器
            if not hasattr(self, '_refresh_timer') or self._refresh_timer is None:
                config = ConfigManager()
                update_interval = int(config.get_value('PlaylistSources', 'update_interval', '60') or 60)
                refresh_ms = min(update_interval, 60) * 60 * 1000
                self._refresh_timer = QTimer(self.window)
                self._refresh_timer.timeout.connect(self._on_refresh_timer)
                self._refresh_timer.start(refresh_ms)
                logger.debug(f"订阅/EPG定期刷新定时器已启动: 每 {refresh_ms // 60000} 分钟")

        except Exception as e:
            logger.error(f"启动订阅定时器失败: {e}", exc_info=True)

    def _on_refresh_timer(self):
        """定期检查并刷新订阅和EPG"""
        try:
            active_source = global_subscription_manager.get_active_playlist_source()
            playlist_url = active_source.get('url', '') if active_source else ''
            if playlist_url:
                if not global_subscription_manager.is_epg_valid():
                    logger.info("EPG缓存已过期，触发后台刷新")
                    worker = SubscriptionWorker(
                        lambda: self._do_start_subscription(playlist_url),
                        self.window
                    )
                    worker.finished.connect(self._on_subscription_finished)
                    worker.finished.connect(lambda: self._cleanup_worker(worker))
                    worker.error.connect(lambda err: logger.error(f"订阅更新错误: {err}"))
                    self._workers.append(worker)
                    worker.start()
        except Exception as e:
            logger.error(f"定期刷新失败: {e}")

    def _do_start_subscription(self, playlist_url: str):
        """执行订阅更新"""
        sources = global_subscription_manager.get_playlist_sources()
        if not sources:
            logger.warning("没有配置播放列表源")
            return False

        for i, source in enumerate(sources):
            if source.get('url') == playlist_url:
                need_update = self._should_update_source(source, i)
                logger.debug(f"订阅源 '{source.get('name', '')}' 需要更新: {need_update}")
                self.handle_playlist_subscription(need_update, playlist_url, i)

                from utils.thread_safety import invoke_on_thread
                if QThread.currentThread() != self.window.thread():
                    invoke_on_thread(self.window, self.window._do_on_playlist_updated_in_main_thread)
                else:
                    self.window._do_on_playlist_updated_in_main_thread()
                break

        def status_callback(msg):
            # 失败原因要留在日志和状态栏里，不能再以 debug 级别吞掉
            if '失败' in msg or '为空' in msg:
                self._last_epg_failure_msg = msg
                logger.warning(f"EPG加载状态: {msg}")
            else:
                logger.debug(f"EPG加载状态: {msg}")

        self._last_epg_failure_msg = ''
        need_download_epg = not global_subscription_manager.is_epg_valid()

        if not need_download_epg:
            logger.debug("EPG缓存有效，从本地缓存加载")
            cached_loaded = global_subscription_manager.load_cached_epg_data()
            if cached_loaded:
                from core.application_state import app_state
                app_state.epg_data = global_subscription_manager.get_epg_data_copy()
                success = True
            else:
                logger.warning("EPG缓存加载失败，重新下载")
                need_download_epg = True

        if need_download_epg:
            logger.info("EPG缓存无效或不存在，重新下载所有EPG源")
            success = global_subscription_manager.load_all_epg_data(status_callback)
            if success:
                from core.application_state import app_state
                app_state.epg_data = global_subscription_manager.get_epg_data_copy()

            header_epg_url = getattr(self, '_last_header_epg_url', None)
            if header_epg_url:
                epg_sources = global_subscription_manager.get_epg_sources()
                existing_urls = [src.get('url', '') for src in epg_sources] if epg_sources else []
                if header_epg_url in existing_urls:
                    logger.info("M3U文件头EPG已存在于订阅源中，跳过")
                else:
                    logger.info(f"补充加载M3U文件头EPG: {header_epg_url[:80]}")
                    try:
                        header_success = global_subscription_manager.load_single_epg(header_epg_url)
                        if header_success:

                            app_state.epg_data = global_subscription_manager.get_epg_data_copy()
                    except Exception as epg_err:
                        logger.warning(f"补充加载M3U文件头EPG失败: {epg_err}")

        return success

    def _on_subscription_finished(self, result):
        """订阅更新完成回调 - EPG加载完成后刷新EPG列表（在主线程中执行）"""
        logger.debug("EPG数据加载完成，准备刷新EPG列表")

        def refresh_ui():
            try:
                if hasattr(self.window, '_populate_epg_list'):
                    self.window._populate_epg_list()
                    logger.debug("刷新UI: EPG列表已填充")

                if hasattr(self.window, 'status_bar_show_message'):
                    from core.application_state import app_state
                    channels_count = len(app_state.channels)
                    tr = getattr(self.window.language_manager, 'tr', lambda x, y: y) if hasattr(self.window, 'language_manager') else lambda x, y: y
                    epg_failure = getattr(self, '_last_epg_failure_msg', '')
                    if epg_failure:
                        # 带上真实原因（HTTP 状态码/超时/体积/解析失败等），避免只显示一句“下载失败”
                        self.window.status_bar_show_message(epg_failure, 8000)
                        self._last_epg_failure_msg = ''
                    else:
                        self.window.status_bar_show_message(tr("channels_loaded", "Channels loaded: {count}").format(count=channels_count))

            except Exception as e:
                logger.error(f"刷新UI失败: {e}", exc_info=True)

        from utils.thread_safety import invoke_on_thread
        invoke_on_thread(self.window, refresh_ui)

    def update_playlist_subscription(self, source_index=None):
        """更新列表订阅 - 使用后台线程避免阻塞UI"""
        try:
            sources = global_subscription_manager.get_playlist_sources()

            if not sources:
                logger.warning("没有配置播放列表源")
                return

            target_source = sources[source_index] if source_index is not None else sources[0]
            playlist_url = target_source.get('url', '')

            if playlist_url:
                worker = SubscriptionWorker(
                    lambda: self.handle_playlist_subscription(True, playlist_url, source_index)
                )
                self._workers.append(worker)
                worker.finished.connect(lambda result: self._cleanup_worker(worker))
                worker.error.connect(lambda err: (logger.error(f"更新列表订阅错误: {err}"), self._cleanup_worker(worker)))
                worker.start()

        except Exception as e:
            logger.error(f"更新列表订阅失败: {e}", exc_info=True)

    def update_channel_groups(self):
        """从CHANNELS中提取分组并更新下拉框"""
        if hasattr(self.window, '_update_groups_for'):
            self.window._update_groups_for('subscription')
            self.window._update_groups_for('local')

    def reload_subscription(self):
        """重新加载订阅源"""
        try:
            sources = global_subscription_manager.get_playlist_sources()
            if sources:
                for i, source in enumerate(sources):
                    if source.get('enabled', True):
                        self.update_playlist_subscription(i)

            logger.info("订阅源重新加载完成")
        except Exception as e:
            logger.error(f"重新加载订阅源失败: {e}", exc_info=True)
