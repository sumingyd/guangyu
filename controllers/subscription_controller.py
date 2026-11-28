"""
订阅控制器 - 负责订阅源管理、EPG加载、频道分组等
从 pyqt_player.py 提取的独立模块
"""

import hashlib
import os
import time
from typing import Optional, Dict, Any
from datetime import datetime
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication

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
        # M3U 文件头里出现的 EPG 地址（可能有多个源）
        self._last_header_epg_urls = []
        # 本地播放列表文件头登记为补充源的 EPG 地址（与订阅源分开，切文件时整体替换）
        self._local_header_epg_urls = []
        # 订阅 / EPG 各自独立的刷新定时器，互不阻塞
        self._subscription_timer = None
        self._epg_timer = None
        self._refresh_busy = False
        self._epg_busy = False
        # 最近一次因「频道表与 EPG 解析表不一致」触发强制重载的频道表指纹
        self._last_epg_force_signature = ''

    def _cleanup_worker(self, worker):
        """从_workers列表中移除已完成的worker"""
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def handle_playlist_subscription(self, need_update: bool, playlist_url: str, source_index=None):
        """在后台线程中处理列表订阅（按源索引独立判断），返回结果分类。"""
        try:
            if not playlist_url:
                logger.debug("无播放列表URL，跳过订阅处理")
                return 'failed'

            logger.debug(f"处理列表订阅: url={playlist_url[:50]}..., need_update={need_update}, source_index={source_index}")

            if need_update:
                logger.info(f"需要更新订阅源，开始下载: {playlist_url[:50]}...")
                content = self._download_subscription_content(playlist_url)

                if content:
                    self._save_to_local_cache(content, playlist_url)
                    return self._process_m3u_content(content, playlist_url, source_index)
                logger.warning(f"下载订阅内容为空: {playlist_url}")
                return 'failed'

            logger.debug("使用缓存数据，无需更新")
            cached_content = self._load_from_local_cache(playlist_url)
            if cached_content:
                logger.debug("从本地缓存加载M3U数据")
                return self._process_m3u_content(cached_content, playlist_url, source_index)
            logger.warning("本地缓存不存在，强制重新下载")
            content = self._download_subscription_content(playlist_url)
            if content:
                self._save_to_local_cache(content, playlist_url)
                return self._process_m3u_content(content, playlist_url, source_index)
            return 'failed'

        except Exception as e:
            logger.error(f"处理列表订阅失败: {e}", exc_info=True)
            return 'failed'

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
                return 'empty'

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

            # 记录文件头EPG地址（在订阅EPG加载后再作为补充源加载）
            epg_url = header_attrs.get('epg_url', '')
            if epg_url:
                urls = list(getattr(self, '_last_header_epg_urls', None) or [])
                if epg_url not in urls:
                    urls.append(epg_url)
                self._last_header_epg_urls = urls
                logger.info(f"M3U文件头包含EPG地址: {epg_url[:80]}，将在订阅EPG加载后补充")

            # 标记订阅来源，并回主线程提交订阅块（不直接改 app_state）
            for ch in channels_data:
                ch['source'] = file_path
            from utils.thread_safety import invoke_on_thread
            invoke_on_thread(
                self.window,
                lambda data=list(channels_data): self._apply_subscription_block(data),
            )

            return 'ok'

        except Exception as e:
            logger.error(f"处理M3U内容失败: {e}", exc_info=True)
            return 'failed'

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

        # 定时器按「间隔」整点触发，下载完成时间总比触发点略晚；
        # 留 1 分钟容差，避免每个周期都被判成“还差几秒”而拖到下一个周期。
        tolerance = min(1.0, max(update_interval * 0.1, 0.05))
        if elapsed >= update_interval - tolerance:
            logger.info(f"订阅源 '{source.get('name', '')}' 缓存已过期（上次: {last_update_str}, 已过 {elapsed:.0f} 分钟, 间隔: {update_interval} 分钟）")
            return True

        logger.debug(f"订阅源 '{source.get('name', '')}' 缓存有效（上次: {last_update_str}, 已过 {elapsed:.0f} 分钟, 间隔: {update_interval} 分钟）")
        return False

    # 一次刷新会话的总时长上限：按顺序刷新多个源，避免慢源把刷新挂死
    REFRESH_SESSION_DEADLINE_SEC = 90.0
    # EPG 定时检查粒度的上限（TTL 可能配得很长，但“今天有没有节目”需要更早发现）
    EPG_CHECK_MAX_MINUTES = 60

    # ---------- 定时器：订阅与 EPG 完全独立 ----------

    def restart_refresh_timers(self):
        """按当前配置重建订阅 / EPG 两个独立定时器（改更新间隔后立即生效）"""
        self._start_subscription_timer()
        self._start_epg_timer()

    def stop_refresh_timers(self):
        """应用退出时停止两个刷新定时器"""
        for attr in ('_subscription_timer', '_epg_timer'):
            timer = getattr(self, attr, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception as e:
                    logger.debug(f"停止定时器 {attr} 失败: {e}")

    @staticmethod
    def _is_main_thread() -> bool:
        """QTimer/QObject 只能在 GUI 线程创建；HTTP API 会从其他线程触发重载"""
        try:
            app = QApplication.instance()
            if app is not None:
                return QThread.currentThread() == app.thread()
        except Exception:
            pass
        return True

    @staticmethod
    def _config_minutes(section: str, default: int = 60) -> int:
        """读取更新间隔（分钟），非法值回退默认值且至少为 1 分钟"""
        try:
            value = int(ConfigManager().get_value(section, 'update_interval', str(default)) or default)
        except (TypeError, ValueError):
            value = default
        return max(value, 1)

    def _drop_timer(self, attr: str):
        timer = getattr(self, attr, None)
        if timer is None:
            return
        try:
            timer.stop()
            timer.deleteLater()
        except Exception as e:
            logger.debug(f"释放定时器 {attr} 失败: {e}")
        setattr(self, attr, None)

    def _start_subscription_timer(self):
        """订阅定时器：周期 = PlaylistSources.update_interval，与 EPG 无耦合"""
        self._drop_timer('_subscription_timer')
        sources = [
            s for s in global_subscription_manager.get_playlist_sources()
            if s.get('url') and s.get('enabled', True)
        ]
        if not sources:
            logger.debug("没有启用的订阅源，不启动订阅刷新定时器")
            return
        interval = self._config_minutes('PlaylistSources', 60)
        timer = QTimer(self.window)
        timer.timeout.connect(self._on_subscription_timer)
        timer.start(interval * 60 * 1000)
        self._subscription_timer = timer
        logger.debug(f"订阅刷新定时器已启动: 每 {interval} 分钟")

    def _start_epg_timer(self):
        """EPG 定时器：TTL 由 EPGSources.update_interval 决定，检查粒度最多 60 分钟"""
        self._drop_timer('_epg_timer')
        if not global_subscription_manager.get_epg_sources():
            logger.debug("没有配置 EPG 源，不启动 EPG 刷新定时器")
            return
        ttl_minutes = self._config_minutes('EPGSources', 60)
        tick_minutes = min(ttl_minutes, self.EPG_CHECK_MAX_MINUTES)
        timer = QTimer(self.window)
        timer.timeout.connect(self._on_epg_timer)
        timer.start(tick_minutes * 60 * 1000)
        self._epg_timer = timer
        logger.debug(
            f"EPG 刷新定时器已启动: 每 {tick_minutes} 分钟检查一次（TTL {ttl_minutes} 分钟）"
        )

    # ---------- 启动 ----------

    def start_subscription_timers(self):
        """启动时调用：重建两个定时器，并先刷新频道再加载 EPG（保持过滤依赖）"""
        logger.debug("start_subscription_timers: 开始")
        try:
            self.restart_refresh_timers()
            sources = [
                s for s in global_subscription_manager.get_playlist_sources()
                if s.get('url') and s.get('enabled', True)
            ]
            if not sources:
                logger.debug("没有启用的订阅源，跳过启动期订阅/EPG 刷新")
                return
            # 顺序不能变：频道表先落盘，EPG 解析才能按频道表过滤
            self._spawn_source_refresh(force=False, with_epg=True)
        except Exception as e:
            logger.error(f"启动订阅定时器失败: {e}", exc_info=True)

    # ---------- 定时器回调 ----------

    def _on_subscription_timer(self):
        """订阅定时器：只刷新订阅源，不再看 EPG 是否有效"""
        sources = [
            s for s in global_subscription_manager.get_playlist_sources()
            if s.get('url') and s.get('enabled', True)
        ]
        if not sources:
            logger.debug("订阅定时器触发：没有启用的订阅源，跳过")
            return
        logger.info(f"订阅定时器触发：按顺序刷新 {len(sources)} 个启用源")
        self._spawn_source_refresh(force=False, with_epg=False)

    def _on_epg_timer(self):
        """EPG 定时器：按自己的 TTL 检查，缓存有效时不做任何事"""
        if not global_subscription_manager.get_epg_sources():
            return
        try:
            from core.application_state import app_state
            has_channels = bool(app_state.channels)
        except Exception:
            has_channels = False
        if not has_channels:
            # EPG 解析会按频道表过滤；没有频道时不下载，避免整份源全量驻留内存
            logger.debug("EPG 定时器触发：频道表为空，跳过（过滤依赖频道表）")
            return
        if global_subscription_manager.is_epg_valid():
            return
        logger.info("EPG 缓存已过期，触发独立刷新")
        self._spawn_epg_refresh()

    # ---------- 订阅刷新 ----------

    def _spawn_source_refresh(self, force: bool, with_epg: bool, only_url: str = ''):
        if self._refresh_busy:
            logger.info("已有订阅刷新在进行中，跳过本次请求")
            return
        self._refresh_busy = True
        # 跨线程调用（HTTP API）时不能把 worker 挂到 GUI 对象上作为子对象
        parent = self.window if self._is_main_thread() else None
        worker = SubscriptionWorker(
            lambda: self._refresh_sources_blocking(
                force=force, with_epg=with_epg, only_url=only_url),
            parent,
        )
        worker.finished.connect(lambda result, w=worker: self._on_refresh_worker_done(w, result))
        worker.error.connect(lambda err, w=worker: self._on_refresh_worker_error(w, err))
        self._workers.append(worker)
        worker.start()

    def _on_refresh_worker_done(self, worker, result):
        self._refresh_busy = False
        self._cleanup_worker(worker)
        # 后台只收集数据，提交订阅块与重建聚合表都在主线程完成
        from utils.thread_safety import invoke_on_thread
        if isinstance(result, dict):
            invoke_on_thread(self.window, lambda: self._apply_refresh_result(result))
        else:
            invoke_on_thread(self.window, lambda: self._on_subscription_finished(result))

    def _apply_refresh_result(self, result):
        """主线程应用订阅刷新结果：先提交订阅块，再刷新界面/EPG。"""
        channels = result.get('channels')
        if channels:
            self._apply_subscription_block(channels)
        self._on_subscription_finished(result.get('stats'))
        if result.get('with_epg'):
            self._spawn_epg_refresh(force=False)

    def _on_refresh_worker_error(self, worker, err):
        self._refresh_busy = False
        logger.error(f"订阅刷新错误: {err}")
        self._cleanup_worker(worker)

    def _refresh_sources_blocking(self, force: bool = False, with_epg: bool = False,
                                  only_url: str = '') -> dict:
        """在后台线程里按配置顺序刷新所有启用源，收集订阅块

        - force=True：忽略缓存强制下载（手动重载 / 设置页保存后）
        - only_url 非空：只刷新指定地址的源
        - with_epg=True：频道提交后由主线程触发 EPG 刷新（启动路径，保证过滤依赖频道表）

        频道提交与聚合重建必须回主线程，这里只返回结果，不直接改 app_state。
        """
        sources = global_subscription_manager.get_playlist_sources()
        targets = []
        for idx, source in enumerate(sources):
            url = source.get('url', '')
            if not url:
                continue
            if only_url:
                if url != only_url:
                    continue
            elif not source.get('enabled', True):
                continue
            targets.append((idx, source))

        stats = {'ok': 0, 'empty': 0, 'failed': 0, 'timeout': 0}
        merged_channels = []
        header_epg_urls = []
        deadline = time.monotonic() + self.REFRESH_SESSION_DEADLINE_SEC

        for pos, (idx, source) in enumerate(targets):
            if time.monotonic() >= deadline:
                remaining = len(targets) - pos
                stats['timeout'] += remaining
                logger.warning(f"订阅刷新会话超时，剩余 {remaining} 个源本次跳过")
                break
            result = self._refresh_one_source(
                idx, source, force, merged_channels, header_epg_urls)
            stats[result] = stats.get(result, 0) + 1

        if header_epg_urls:
            self._last_header_epg_urls = list(dict.fromkeys(header_epg_urls))

        if not merged_channels and targets:
            # 全部失败或全部为空：保留现有频道列表，避免网络抖动把数据洗掉
            logger.warning(f"本次订阅刷新未得到任何频道（{stats}），保留现有频道列表")

        logger.info(
            f"订阅刷新完成：ok={stats['ok']} empty={stats['empty']} "
            f"failed={stats['failed']} timeout={stats['timeout']}，"
            f"共 {len(merged_channels)} 个频道"
        )

        return {
            'stats': stats,
            'channels': merged_channels or None,
            'with_epg': with_epg,
        }

    def _refresh_one_source(self, index: int, source: dict, force: bool,
                            merged_channels: list, header_epg_urls: list) -> str:
        """按缓存策略刷新单个源，成功解析后把频道追加到 merged_channels"""
        url = source.get('url', '')
        name = source.get('name', '') or url
        try:
            if not force and not self._should_update_source(source, index):
                content = self._load_from_local_cache(url)
                if not content:
                    logger.warning(f"订阅源 '{name}' 缓存缺失，强制重新下载")
                    content = self._download_subscription_content(url)
                    if not content:
                        return 'failed'
                    self._save_to_local_cache(content, url)
            else:
                content = self._download_subscription_content(url)
                if not content:
                    return 'failed'
                self._save_to_local_cache(content, url)

            channels, header_attrs = self._parse_m3u_content_pure_python(content)
            if not channels:
                logger.warning(f"M3U内容解析为空: {url[:50]}...")
                return 'empty'

            if url.startswith('http'):
                ConfigManager().add_recent_file(url)
                global_subscription_manager.update_playlist_source_last_update(
                    index, datetime.now().isoformat())

            epg_url = header_attrs.get('epg_url', '') if header_attrs else ''
            if epg_url:
                header_epg_urls.append(epg_url)
                logger.info(f"M3U文件头包含EPG地址: {epg_url[:80]}")

            # 标记订阅来源：本地块保持 source 为空，播放/服务端据此区分两块
            for ch in channels:
                ch['source'] = url

            merged_channels.extend(channels)
            logger.info(f"订阅源 '{name}' 刷新完成: {len(channels)} 个频道")
            return 'ok'
        except Exception as e:
            logger.error(f"刷新订阅源 '{name}' 失败: {e}", exc_info=True)
            return 'failed'

    def _apply_subscription_block(self, channels: list):
        """在主线程提交订阅块：替换 _sub_channels 并重建聚合表。

        订阅刷新只影响订阅块，本地块原样保留；重复地址由聚合函数按
        「本地优先、订阅补齐元数据」处理。
        """
        from services.channel_dedup_service import ChannelDedupService, carry_over_channel_state

        prev = list(getattr(self.window, '_sub_channels', []) or [])
        sub = carry_over_channel_state(list(channels), prev)
        # 多个订阅源之间也要按播放地址去重，页签显示和聚合表口径保持一致
        sub = ChannelDedupService().deduplicate(sub)
        self.window._sub_channels = sub
        rebuild = getattr(self.window, '_rebuild_channel_aggregation', None)
        if callable(rebuild):
            rebuild()
        logger.info(f"订阅块已更新: {len(sub)} 个（本地块保留 {len(getattr(self.window, '_local_channels', []) or [])} 个）")
        self._notify_channels_updated()

    def _notify_channels_updated(self):
        """把频道更新通知回主线程刷新界面"""
        from utils.thread_safety import invoke_on_thread
        if QThread.currentThread() != self.window.thread():
            invoke_on_thread(self.window, self.window._do_on_playlist_updated_in_main_thread)
        else:
            self.window._do_on_playlist_updated_in_main_thread()

    # ---------- EPG 刷新 ----------

    def ensure_epg_for_current_channels(self):
        """频道表换成新播放列表后调用，确保 EPG 是按当前频道表解析的。

        两种需要重载的情况：
        - 冷启动时 EPG 还没加载；
        - 上次 EPG 解析用的是另一份频道表（解析会按频道表过滤，旧结果里没有新频道）。
        同一份频道表只强制重载一次，避免反复下载大文件。
        """
        if not global_subscription_manager.get_epg_sources():
            return
        try:
            from core.application_state import app_state
            if not app_state.channels:
                return
        except Exception:
            return
        signature = global_subscription_manager.current_channel_table_signature()
        if not signature:
            return
        if (global_subscription_manager.has_epg_data()
                and signature == global_subscription_manager.get_epg_filter_signature()):
            return
        if signature == self._last_epg_force_signature:
            return
        self._last_epg_force_signature = signature
        logger.info("当前频道表与已加载的 EPG 不一致，后台按当前频道表重新加载 EPG")
        self._spawn_epg_refresh(force=True)

    def _spawn_epg_refresh(self, force: bool = False):
        if self._epg_busy:
            logger.info("已有 EPG 刷新在进行中，跳过本次请求")
            return
        self._epg_busy = True
        worker = SubscriptionWorker(
            lambda: self._refresh_epg_blocking(force=force), self.window)
        worker.finished.connect(lambda result, w=worker: self._on_epg_worker_done(w, result))
        worker.error.connect(lambda err, w=worker: self._on_epg_worker_error(w, err))
        self._workers.append(worker)
        worker.start()

    def _on_epg_worker_done(self, worker, result):
        self._epg_busy = False
        self._cleanup_worker(worker)
        self._on_epg_refresh_finished(result)

    def _on_epg_worker_error(self, worker, err):
        self._epg_busy = False
        # 强制重载异常时清掉指纹记录，下次加载同一份频道表还能再试
        self._last_epg_force_signature = ''
        logger.error(f"EPG刷新错误: {err}")
        self._cleanup_worker(worker)

    def _refresh_epg_blocking(self, force: bool = False) -> bool:
        """按 TTL 读取缓存或全量重下 EPG（调用方需保证频道表已就绪）

        force=True 时忽略缓存与 60 秒下载结果复用，按当前频道表强制重新解析。
        """
        from core.application_state import app_state

        failure = {'msg': ''}

        def status_callback(msg):
            # 失败原因要留在日志和状态栏里，不能再以 debug 级别吞掉
            if '失败' in msg or '为空' in msg:
                failure['msg'] = msg
                logger.warning(f"EPG加载状态: {msg}")
            else:
                logger.debug(f"EPG加载状态: {msg}")

        self._last_epg_failure_msg = ''
        need_download = force or not global_subscription_manager.is_epg_valid()

        if not need_download:
            logger.debug("EPG缓存有效，从本地缓存加载")
            if global_subscription_manager.load_cached_epg_data():
                app_state.epg_data = global_subscription_manager.get_epg_data_copy()
                return True
            logger.warning("EPG缓存加载失败，改为重新下载")
            need_download = True

        if force:
            logger.info("按当前频道表强制重新加载所有EPG源")
        else:
            logger.info("EPG缓存无效或不存在，重新下载所有EPG源")
        success = global_subscription_manager.load_all_epg_data(
            status_callback, force_download=force)
        if success:
            app_state.epg_data = global_subscription_manager.get_epg_data_copy()

        # 仅在本轮确实下载过 EPG 时补充 M3U 文件头里的 EPG 地址（与旧行为一致）
        self._load_header_epg_urls(status_callback)
        self._last_epg_failure_msg = failure['msg']
        return success

    def register_local_header_epg_url(self, url: str):
        """登记本地播放列表文件头的 EPG 地址（作为补充源）。

        本地文件是独立来源块：换文件时整体替换，不污染订阅源文件头记录。
        """
        self._local_header_epg_urls = [url] if url else []

    def _all_header_epg_urls(self) -> list:
        urls = list(getattr(self, '_last_header_epg_urls', None) or [])
        urls += list(getattr(self, '_local_header_epg_urls', None) or [])
        return list(dict.fromkeys(u for u in urls if u))

    def _load_header_epg_urls(self, status_callback=None):
        """补充加载 M3U 文件头里的 EPG 地址（已配置的源跳过）"""
        urls = self._all_header_epg_urls()
        if not urls:
            return
        from core.application_state import app_state
        configured = {
            src.get('url', '') for src in (global_subscription_manager.get_epg_sources() or [])
        }
        for url in urls:
            if not url or url in configured:
                continue
            logger.info(f"补充加载M3U文件头EPG: {url[:80]}")
            try:
                if global_subscription_manager.load_single_epg(url, status_callback):
                    app_state.epg_data = global_subscription_manager.get_epg_data_copy()
            except Exception as epg_err:
                logger.warning(f"补充加载M3U文件头EPG失败: {epg_err}")

    def _on_epg_refresh_finished(self, result):
        """EPG 刷新完成：立即重绘节目单，失败原因带到状态栏"""
        if not result:
            # 强制重载失败时清掉指纹记录，下次加载同一份频道表还能再试
            self._last_epg_force_signature = ''

        def refresh():
            try:
                if hasattr(self.window, '_populate_epg_list'):
                    self.window._populate_epg_list()
                # 还没开始播放时同步刷新顶部当前节目；播放中不动进度/时间控件
                player = getattr(self.window, 'player_controller', None)
                if (not getattr(player, 'is_playing', False)
                        and hasattr(self.window, 'update_channel_info_on_selection')):
                    self.window.update_channel_info_on_selection()
                failure = getattr(self, '_last_epg_failure_msg', '')
                if failure and hasattr(self.window, 'status_bar_show_message'):
                    self.window.status_bar_show_message(failure, 8000)
                    self._last_epg_failure_msg = ''
            except Exception as e:
                logger.error(f"刷新EPG界面失败: {e}", exc_info=True)

        from utils.thread_safety import invoke_on_thread
        invoke_on_thread(self.window, refresh)

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

    def reload_subscription(self, url: str = ''):
        """手动重载入口：按配置顺序强制刷新所有启用源（传 url 时只刷该源）"""
        try:
            sources = global_subscription_manager.get_playlist_sources()
            targets = [
                s for s in sources
                if s.get('url') and (s.get('url') == url if url else s.get('enabled', True))
            ]
            if not targets:
                logger.warning("没有可重载的订阅源")
                return
            # 首次添加源后也能把定时器补起来（原先只在启动时创建一次）
            if self._is_main_thread():
                self.restart_refresh_timers()
                if hasattr(self.window, 'status_bar_show_message'):
                    tr = getattr(getattr(self.window, 'language_manager', None),
                                 'tr', lambda _k, d='': d)
                    self.window.status_bar_show_message(
                        tr('reloading_subscription', '正在重新加载订阅...'), 0)
            self._spawn_source_refresh(force=True, with_epg=False, only_url=url)
        except Exception as e:
            logger.error(f"重新加载订阅源失败: {e}", exc_info=True)

    def refresh_enabled_sources(self, force: bool = True):
        """设置页保存订阅源后调用：后台按顺序刷新所有启用源"""
        self._spawn_source_refresh(force=force, with_epg=False)
