import os
import time as _time
import threading
from datetime import datetime, timedelta, timezone
from .log_manager import global_logger as logger
from .config_manager import ConfigManager
from utils.singleton import Singleton

# 单个 EPG 源解压后的内容上限（仅用于防御压缩炸弹）。
# 真实 XMLTV 源体积远超 64MB：sumingyd/epg.xml.gz 压缩包 8.6MB，解压后 105MB，
# 旧上限 64MB 会把正常源判为异常，导致 EPG 永远下载失败。
EPG_MAX_BYTES = 256 * 1024 * 1024
EPG_MAX_MB = EPG_MAX_BYTES // (1024 * 1024)

# 同一 EPG URL 下载结果的复用窗口（秒）。重载风暴期间到达的重复请求
# 直接复用刚完成的结果，避免同一个大文件被并行/连续下载多次。
EPG_DOWNLOAD_REUSE_SECONDS = 60


class SubscriptionManager(Singleton):

    def __init__(self):
        if self._initialized:
            return

        self._config = ConfigManager()
        self._epg_data = {}
        self._epg_channel_names = {}
        self._last_epg_update = None
        self._epg_lock = threading.RLock()
        # 最近一次 EPG 加载失败的可读原因（成功时为空串），供上层提示用户
        self._last_epg_error = ''
        self._update_callbacks = []
        # 全量 EPG 加载单飞锁：同一时刻只允许一个 load_all_epg_data 在跑
        self._epg_load_lock = threading.Lock()
        # 同一 URL 的下载单飞/结果复用表：{url: {'lock': Lock, 'ts': float, 'data': dict|None}}
        self._epg_download_entries = {}
        self._epg_download_guard = threading.Lock()
        self._initialized = True

    def _get_cache_dir(self) -> str:
        from utils.app_paths import get_cache_dir
        cache_dir = self._config.get_value('General', 'cache_dir', 'cache') or 'cache'
        if not os.path.isabs(cache_dir):
            cache_dir = os.path.join(get_cache_dir(), cache_dir)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def get_playlist_sources(self) -> list:
        """获取所有直播源配置

        Returns:
            直播源列表
        """
        return self._config.load_playlist_sources()
    
    def add_playlist_source(self, url: str, name: str | None = None) -> int:
        """添加新的直播源

        Args:
            url: 直播源URL
            name: 直播源名称（可选）

        Returns:
            新添加的源索引
        """
        sources = self.get_playlist_sources()
        
        if not name:
            name = f"Source {len(sources) + 1}"
        
        new_source = {
            'url': url,
            'name': name,
            'enabled': len(sources) == 0
        }
        
        sources.append(new_source)
        self._config.save_playlist_sources(sources)
        
        logger.info(f"已添加直播源: {name} ({url})")
        return len(sources) - 1
    
    def remove_playlist_source(self, index: int):
        """删除指定索引的直播源

        Args:
            index: 要删除的源索引
        """
        sources = self.get_playlist_sources()
        if 0 <= index < len(sources):
            removed = sources.pop(index)
            
            was_enabled = removed.get('enabled', False)
            if was_enabled and sources:
                sources[0]['enabled'] = True
            
            self._config.save_playlist_sources(sources)
            logger.info(f"已删除直播源: {removed.get('name', 'Unknown')}")
    
    def update_playlist_source(self, index: int, url: str, name: str | None = None):
        """更新指定索引的直播源

        Args:
            index: 要更新的源索引
            url: 新的URL
            name: 新的名称（可选，不传则保留原名）
        """
        sources = self.get_playlist_sources()
        if 0 <= index < len(sources):
            source = sources[index]
            source['url'] = url
            if name:
                source['name'] = name
            self._config.save_playlist_sources(sources)
            logger.info(f"已更新直播源: {source.get('name', 'Unknown')} ({url})")
    
    def update_playlist_source_last_update(self, index: int, timestamp: str):
        """更新指定索引的直播源更新时间

        Args:
            index: 源索引
            timestamp: ISO格式时间字符串
        """
        self._config.update_playlist_source_last_update(index, timestamp)
    
    def set_active_playlist_source(self, index: int):
        """设置指定索引的直播源为当前启用状态

        Args:
            index: 源索引
        """
        self._config.set_active_playlist_source(index)
        source = self.get_active_playlist_source()
        if source:
            logger.info(f"已切换到直播源: {source.get('name', 'Unknown')} ({source.get('url', '')})")
    
    def get_active_playlist_source_index(self) -> int:
        """获取当前启用的直播源索引

        Returns:
            启用源的索引，没有则返回 -1
        """
        return self._config.get_active_playlist_source_index()
    
    def get_active_playlist_source(self) -> dict | None:
        """获取当前启用的直播源

        Returns:
            当前启用的直播源字典，如果没有则返回None
        """
        return self._config.get_active_playlist_source()
    
    def get_epg_sources(self) -> list:
        """获取所有EPG源配置

        Returns:
            EPG源列表
        """
        return self._config.load_epg_sources()

    def get_epg_channel_count(self) -> int:
        """获取EPG数据中的频道数量

        Returns:
            有EPG数据的频道数量
        """
        return len(self._epg_data) if self._epg_data else 0

    def get_epg_program_count(self) -> int:
        """获取EPG数据中的节目总数

        Returns:
            所有频道的节目总数
        """
        if not self._epg_data:
            return 0
        return sum(len(progs) for progs in self._epg_data.values())

    def has_epg_data(self) -> bool:
        """是否有EPG数据

        Returns:
            是否存在任何EPG数据
        """
        return bool(self._epg_data)
    
    def add_epg_source(self, url: str, name: str | None = None) -> int:
        """添加新的EPG源

        Args:
            url: EPG源URL
            name: EPG源名称（可选）

        Returns:
            新添加的源索引
        """
        sources = self.get_epg_sources()
        
        if not name:
            name = f"EPG {len(sources) + 1}"
        
        new_source = {
            'url': url,
            'name': name
        }
        
        sources.append(new_source)
        self._config.save_epg_sources(sources)
        
        logger.info(f"已添加EPG源: {name} ({url})")
        return len(sources) - 1
    
    def remove_epg_source(self, index: int):
        """删除指定索引的EPG源

        Args:
            index: 要删除的源索引
        """
        sources = self.get_epg_sources()
        if 0 <= index < len(sources):
            removed = sources.pop(index)
            self._config.save_epg_sources(sources)
            logger.info(f"已删除EPG源: {removed.get('name', 'Unknown')}")
    
    def update_epg_source(self, index: int, url: str, name: str | None = None):
        """更新指定索引的EPG源

        Args:
            index: 要更新的源索引
            url: 新的URL
            name: 新的名称（可选，不传则保留原名）
        """
        sources = self.get_epg_sources()
        if 0 <= index < len(sources):
            source = sources[index]
            source['url'] = url
            if name:
                source['name'] = name
            self._config.save_epg_sources(sources)
            logger.info(f"已更新EPG源: {source.get('name', 'Unknown')} ({url})")

    def update_epg_source_last_update(self, index: int, timestamp: str):
        """更新指定索引EPG源的更新时间

        Args:
            index: 源索引
            timestamp: ISO格式时间字符串
        """
        self._config.update_epg_source_last_update(index, timestamp)
    
    def load_all_epg_data(self, status_callback=None) -> bool:
        """加载所有EPG源的数据（单飞：并发请求合并到正在执行的那一次）

        同一时刻只允许一个全量加载任务；重载风暴期间到达的重复请求直接返回，
        由正在执行的任务完成结果，避免同一 EPG 文件被并行下载多份。
        """
        if not self._epg_load_lock.acquire(blocking=False):
            logger.info("已有 EPG 全量加载在进行中，本次请求合并等待其完成")
            if status_callback:
                status_callback("EPG 正在加载中，已合并本次请求")
            return True
        try:
            return self._load_all_epg_data_inner(status_callback)
        finally:
            self._epg_load_lock.release()

    def _load_all_epg_data_inner(self, status_callback=None) -> bool:
        """加载所有EPG源的数据，多源依次替补

        同一个频道只使用第一个有该频道数据的EPG源，不合并多个源的数据。
        """
        sources = self.get_epg_sources()
        
        if not sources:
            logger.warning("没有配置任何EPG源")
            if status_callback:
                status_callback("没有配置任何EPG源")
            return False
        
        merged_data = {}
        total_sources = len(sources)
        failed_sources = 0
        failed_reasons = []

        for i, source in enumerate(sources):
            if status_callback:
                status_callback(f"正在加载EPG源 {i+1}/{total_sources}: {source.get('name', '')}")

            try:
                data = self._load_single_epg(source['url'])

                if data:
                    new_channels = 0
                    for channel_id, programs in data.items():
                        if channel_id not in merged_data:
                            merged_data[channel_id] = programs
                            new_channels += 1

                    logger.info(f"成功加载EPG源: {source.get('name', '')}, 包含 {len(data)} 个频道, 新增 {new_channels} 个频道")
                    self.update_epg_source_last_update(i, datetime.now().isoformat())
                else:
                    failed_sources += 1
                    reason = self._last_epg_error or '源无可用数据'
                    failed_reasons.append(f"{source.get('name', '')}: {reason}")
                    logger.warning(f"EPG源加载失败或无数据: {source.get('name', '')} - {reason}")

            except Exception as e:
                failed_sources += 1
                failed_reasons.append(f"{source.get('name', '')}: 异常 {e}")
                logger.error(f"加载EPG源异常: {source.get('name', '')} - {str(e)}")

        # 全部源都失败时保留现有内存/磁盘缓存，避免网络异常把本地 EPG 清空
        if not merged_data:
            detail = '；'.join(failed_reasons) if failed_reasons else '未知原因'
            logger.warning(f"所有EPG源均加载失败({failed_sources}/{total_sources})，保留现有EPG缓存: {detail}")
            with self._epg_lock:
                existing_channels = len(self._epg_data)
            if status_callback:
                status_callback(f"EPG加载失败（{detail}），继续使用缓存数据（{existing_channels} 个频道）")
            return False
        
        with self._epg_lock:
            self._epg_data = merged_data
            self._last_epg_update = datetime.now()
        self._clear_epg_matcher_cache()
        
        total_channels = len(merged_data)
        total_programs = sum(len(progs) for progs in merged_data.values())
        
        logger.info(f"EPG数据加载完成: 共 {total_sources} 个源, {total_channels} 个频道, {total_programs} 个节目")
        
        if status_callback:
            status_callback(f"EPG数据加载完成: {total_channels} 个频道, {total_programs} 个节目")
        
        self._save_epg_cache(merged_data)
        self._notify_update_callbacks()
        
        return len(merged_data) > 0
    
    def reload_single_epg_source(self, index: int, status_callback=None) -> bool:
        """增量重载单个EPG源，依次替补

        Args:
            index: 要重载的源索引
            status_callback: 状态回调函数

        Returns:
            是否成功
        """
        sources = self.get_epg_sources()
        if not (0 <= index < len(sources)):
            if status_callback:
                status_callback("无效的EPG源索引")
            return False
        
        source = sources[index]
        
        if status_callback:
            status_callback(f"正在更新EPG源: {source.get('name', '')}")

        try:
            data = self._load_single_epg(source['url'])
            
            if not data:
                reason = self._last_epg_error or '源无可用数据'
                logger.warning(f"EPG源增量加载失败或无数据: {source.get('name', '')} - {reason}")
                if status_callback:
                    status_callback(f"EPG源加载失败: {source.get('name', '')}（{reason}）")
                return False
            
            with self._epg_lock:
                new_channels = 0
                for channel_id, programs in data.items():
                    if channel_id not in self._epg_data:
                        self._epg_data[channel_id] = programs
                        new_channels += 1
                
                self._last_epg_update = datetime.now()
            self._clear_epg_matcher_cache()
            
            total_channels = len(self._epg_data)
            total_programs = sum(len(progs) for progs in self._epg_data.values())
            
            logger.info(f"EPG源增量更新成功: {source.get('name', '')}, 包含 {len(data)} 个频道, 新增 {new_channels} 个频道, 合计 {total_channels} 个频道, {total_programs} 个节目")
            self.update_epg_source_last_update(index, datetime.now().isoformat())
            
            if status_callback:
                status_callback(f"EPG源更新完成: {total_channels} 个频道, {total_programs} 个节目")
            
            with self._epg_lock:
                epg_snapshot = dict(self._epg_data)
            self._save_epg_cache(epg_snapshot)
            self._notify_update_callbacks()

            return True

        except Exception as e:
            logger.error(f"EPG源增量重载异常: {source.get('name', '')} - {str(e)}")
            return False
    
    def load_single_epg(self, epg_url: str, status_callback=None) -> bool:
        """加载单个EPG源的数据并合并到现有数据中（用于从M3U文件的tvg-url等场景）

        同一个频道只保留已有数据，新源仅补充不存在的频道。

        Args:
            epg_url: EPG源URL
            status_callback: 状态回调函数

        Returns:
            是否成功加载
        """
        if not epg_url:
            logger.warning("EPG URL未设置")
            if status_callback:
                status_callback("EPG URL未设置")
            return False

        if status_callback:
            status_callback("正在下载EPG数据...")

        try:
            data = self._load_single_epg(epg_url)

            if data:
                with self._epg_lock:
                    new_channels = 0
                    for channel_id, programs in data.items():
                        if channel_id not in self._epg_data:
                            self._epg_data[channel_id] = programs
                            new_channels += 1
                    self._last_epg_update = datetime.now()
                self._clear_epg_matcher_cache()

                total_channels = len(data)
                total_programs = sum(len(progs) for progs in data.values())

                logger.info(f"EPG补充源加载成功: {total_channels} 个频道, {total_programs} 个节目, 新增 {new_channels} 个频道")

                if status_callback:
                    status_callback(f"EPG数据加载成功: {total_channels} 个频道")

                with self._epg_lock:
                    epg_snapshot = dict(self._epg_data)
                self._save_epg_cache(epg_snapshot)
                if new_channels > 0:
                    self._notify_update_callbacks()

                return True
            else:
                reason = self._last_epg_error or '源无可用数据'
                logger.warning(f"EPG补充源数据为空: {epg_url} - {reason}")
                if status_callback:
                    status_callback(f"EPG数据为空（{reason}）")
                return False

        except Exception as e:
            logger.error(f"加载EPG补充源失败: {e}")
            if status_callback:
                status_callback(f"加载失败: {e}")
            return False
    
    def _load_single_epg(self, epg_url: str) -> dict:
        """加载单个EPG源的数据（同一 URL 单飞 + 结果复用）

        - 同一 URL 同时只允许一个下载+解析任务；
        - 重载期间到达的重复请求等待在途任务结束，并复用其刚完成的结果，
          避免同一个 8MB EPG 被并行下载、并行解析多份。

        失败时把可读原因写入 self._last_epg_error，供上层向用户展示真实原因。

        Args:
            epg_url: EPG源URL

        Returns:
            EPG数据字典
        """
        if not epg_url:
            self._last_epg_error = '未配置EPG地址'
            return {}

        with self._epg_download_guard:
            entry = self._epg_download_entries.get(epg_url)
            if entry is None:
                entry = {'lock': threading.Lock(), 'ts': 0.0, 'data': None}
                self._epg_download_entries[epg_url] = entry

        lock = entry['lock']
        if not lock.acquire(blocking=False):
            # 已有同 URL 下载在跑：等待其结束并直接复用结果（不再重复下载）
            logger.info(f"EPG 下载已在进行中，等待复用其结果: {epg_url}")
            with lock:
                pass
            data = entry['data']
            return dict(data) if data else {}

        try:
            age = _time.time() - entry['ts']
            if entry['data'] is not None and age < EPG_DOWNLOAD_REUSE_SECONDS:
                logger.info(f"复用 {age:.0f}s 内的 EPG 下载结果，跳过重复下载: {epg_url}")
                return dict(entry['data'])
            data = self._download_single_epg(epg_url)
            if data:
                entry['data'] = data
                entry['ts'] = _time.time()
            return data
        finally:
            lock.release()

    def _download_single_epg(self, epg_url: str) -> dict:
        """实际执行单个 EPG 源的下载与解析（调用方需持该 URL 的单飞锁）"""
        if not epg_url:
            self._last_epg_error = '未配置EPG地址'
            return {}
        
        import requests
        from utils.http_session import get as _http_get

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*'
        }

        max_retries = 3
        attempts = 0
        last_error = None
        for attempt in range(1, max_retries + 1):
            attempts = attempt
            try:
                logger.info(f"正在下载EPG数据: {epg_url}" + (f" (第{attempt}次尝试)" if attempt > 1 else ""))
                # 标量超时：连接与读取各自最多 120s（http_session 统一按标量处理）
                response = _http_get(epg_url, timeout=120, headers=headers,
                                     allow_redirects=True, stream=True)
                with response:
                    response.raise_for_status()

                    declared = response.headers.get('Content-Length', '')
                    if declared.isdigit() and int(declared) > EPG_MAX_BYTES:
                        self._last_epg_error = f"文件过大({int(declared) / 1048576:.1f}MB，上限{EPG_MAX_MB}MB)"
                        logger.error(f"EPG文件过大({declared}字节)，已跳过: {epg_url}")
                        return {}

                    buf = bytearray()
                    for chunk in response.iter_content(64 * 1024):
                        if not chunk:
                            continue
                        buf.extend(chunk)
                        if len(buf) > EPG_MAX_BYTES:
                            self._last_epg_error = f"文件超过{EPG_MAX_MB}MB上限"
                            logger.error(f"EPG文件超过 {EPG_MAX_BYTES} 字节上限，已中止下载: {epg_url}")
                            return {}
                    content = bytes(buf)
                    downloaded_size = len(content)

                    content_encoding = response.headers.get('Content-Encoding', '')
                    url_is_gz = epg_url.lower().endswith('.gz')
                    already_decompressed = 'gzip' in content_encoding.lower()
                    if url_is_gz and not already_decompressed and len(content) >= 2 and content[0] == 0x1f and content[1] == 0x8b:
                        import gzip
                        from io import BytesIO
                        with gzip.GzipFile(fileobj=BytesIO(content)) as f:
                            # 解压同样设上限，防御压缩炸弹
                            content = f.read(EPG_MAX_BYTES + 1)
                        if len(content) > EPG_MAX_BYTES:
                            self._last_epg_error = f"解压后{len(content) / 1048576:.1f}MB，超过{EPG_MAX_MB}MB上限"
                            logger.error(f"EPG解压后超过 {EPG_MAX_BYTES} 字节上限，已跳过: {epg_url}")
                            return {}

                try:
                    epg_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        epg_content = content.decode('gbk')
                    except UnicodeDecodeError:
                        self._last_epg_error = '内容编码无法识别（非UTF-8/GBK）'
                        logger.error("无法解码EPG文件内容")
                        return {}
                
                if not epg_content.strip():
                    self._last_epg_error = '下载内容为空'
                    logger.warning(f"EPG下载内容为空: {epg_url}")
                    return {}
                
                logger.info(f"EPG数据下载成功: 解压后 {len(content)} 字节 (下载 {downloaded_size} 字节)")
                parsed = self._parse_epg_content(epg_content, raw_bytes=content)
                if not parsed:
                    self._last_epg_error = '解析后无节目数据'
                    logger.warning(f"EPG内容解析后为空: {epg_url}")
                else:
                    self._last_epg_error = ''
                return parsed

            except requests.exceptions.HTTPError as e:
                # 4xx（除 429 限流外）重试无意义，直接失败
                status = getattr(getattr(e, 'response', None), 'status_code', 0) or 0
                last_error = e
                self._last_epg_error = f"请求返回 HTTP {status}"
                logger.warning(f"EPG数据请求返回 HTTP {status}: {epg_url}")
                if 400 <= status < 500 and status != 429:
                    break
                if attempt < max_retries:
                    import time
                    time.sleep(2)
            except requests.exceptions.Timeout as e:
                last_error = e
                self._last_epg_error = '请求超时(120s)'
                logger.warning(f"EPG数据下载超时(第{attempt}次): {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2)
            except requests.exceptions.RequestException as e:
                last_error = e
                self._last_epg_error = f"网络请求失败: {e}"
                logger.warning(f"EPG数据下载失败(第{attempt}次): {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2)
            except Exception as e:
                last_error = e
                self._last_epg_error = f"处理异常: {e}"
                logger.error(f"加载EPG数据失败(第{attempt}次): {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2)
        
        logger.error(f"EPG数据下载最终失败(共{attempts}次): {last_error}")
        return {}
    
    def _parse_epg_content(self, content: str, raw_bytes: bytes | None = None) -> dict:
        """解析EPG内容

        Args:
            content: EPG内容字符串（已按 UTF-8/GBK 解码，JSON 源直接使用）
            raw_bytes: 原始字节（可选）。XML 源优先用它流式解析，省掉一份大字符串副本

        Returns:
            解析后的EPG数据字典
        """
        try:
            import json
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        import io

        def _make_stream():
            if raw_bytes is not None:
                return io.BytesIO(raw_bytes)
            return io.StringIO(content)

        try:
            return self._parse_xml_epg_stream(_make_stream)
        except Exception as e:
            if raw_bytes is None:
                logger.error(f"XML格式EPG解析失败: {e}")
                return {}
            # 字节流的 XML 声明编码与实际内容不符时，回退到已解码文本重新解析
            logger.warning(f"字节流解析EPG失败({e})，改用已解码文本重试")
            try:
                return self._parse_xml_epg_stream(lambda: io.StringIO(content))
            except Exception as e2:
                logger.error(f"XML格式EPG解析失败: {e2}")
                return {}

    def _parse_xml_epg(self, content: str) -> dict:
        """解析XML格式的EPG数据（保留旧入口，内部走流式解析）"""
        import io
        try:
            return self._parse_xml_epg_stream(lambda: io.StringIO(content))
        except Exception as e:
            logger.error(f"XML格式EPG解析失败: {e}")
            return {}

    def _parse_xml_epg_stream(self, make_stream) -> dict:
        """两遍流式解析 XMLTV，只保留频道表中真实存在的频道节目

        第一遍只收集 <channel>（id -> 显示名），内存与节目数无关；
        第二遍按目标频道 id 过滤 <programme>，逐个 clear() 释放元素，
        不构建整棵 XML 树。取不到频道集合或过滤后无节目时回落到保留全部频道。
        """
        import gc
        gc_was_enabled = gc.isenabled()
        if gc_was_enabled:
            gc.disable()
        try:
            channel_names = self._scan_xmltv_channels(make_stream)
            total_channels = len(channel_names)
            target_ids, match_stats = self._resolve_epg_target_ids(channel_names)

            if not target_ids:
                reason = '频道表为空' if not match_stats.get('table_size') else '频道表未能匹配到任何EPG频道'
                logger.warning(
                    f"EPG未做频道过滤：{reason}（EPG频道 {total_channels} 个），本次保留全部频道"
                )
                result = self._scan_xmltv_programmes(make_stream, None, channel_names)
                kept_names = channel_names
                self._log_epg_match_stats(
                    match_stats, [], filtered=False, note=f"{reason}，因此未做过滤"
                )
            else:
                result = self._scan_xmltv_programmes(make_stream, target_ids, channel_names)
                programme_count = sum(len(programmes) for programmes in result.values())
                if programme_count == 0:
                    logger.warning(
                        f"EPG过滤后无节目（频道表命中 {len(target_ids)} 个EPG频道），"
                        f"回落到保留全部 {total_channels} 个频道"
                    )
                    result = self._scan_xmltv_programmes(make_stream, None, channel_names)
                    kept_names = channel_names
                    self._log_epg_match_stats(
                        match_stats, [], filtered=False, note='过滤后无节目，因此未做过滤'
                    )
                else:
                    kept_names = {cid: name for cid, name in channel_names.items() if cid in result}
                    empty_names = [
                        name for name, cid in match_stats['matched'] if not result.get(cid)
                    ]
                    logger.info(
                        f"EPG频道过滤: EPG共 {total_channels} 个频道, 频道表命中 {len(target_ids)} 个, "
                        f"实际保留 {len(result)} 个频道 / {programme_count} 个节目"
                    )
                    self._log_epg_match_stats(match_stats, empty_names, filtered=True)

            if kept_names:
                with self._epg_lock:
                    self._epg_channel_names.update(kept_names)
            return result
        finally:
            if gc_was_enabled:
                gc.enable()

    def _log_epg_match_stats(self, match_stats: dict, empty_names, filtered: bool, note: str = ''):
        """输出一次 EPG 匹配诊断（三种情况分开统计，不逐频道刷屏）

        Args:
            match_stats: _resolve_epg_target_ids 返回的统计
            empty_names: 匹配到 EPG id 但该 id 没有任何节目的频道名
            filtered: 本次是否真的按频道表做了过滤
            note: 未过滤时的原因说明
        """
        table_size = match_stats.get('table_size', 0)
        matched = match_stats.get('matched', [])
        unmatched = match_stats.get('unmatched', [])
        empty_count = len(empty_names)

        summary = (
            f"EPG匹配: 命中 {len(matched)} / 无匹配 {len(unmatched)} / 空节目 {empty_count}"
            f"（频道表共 {table_size}）"
        )
        summary += "，已按频道表过滤" if filtered else f"，{note or '因此未做过滤'}"

        # 无匹配比例过半通常意味着源本身或匹配规则有问题，提升到 warning
        high_unmatched = bool(table_size) and len(unmatched) > table_size / 2
        emit = logger.warning if high_unmatched else logger.info
        emit(summary)
        if unmatched:
            emit(f"无匹配EPG的频道({len(unmatched)}): {self._format_channel_list(unmatched)}")
        if empty_names:
            emit(f"空节目EPG的频道({empty_count}): {self._format_channel_list(empty_names)}")

    @staticmethod
    def _format_channel_list(names, limit: int = 10) -> str:
        head = '、'.join(names[:limit])
        if len(names) > limit:
            return f"{head} ... 等 {len(names)} 个"
        return head


    def _scan_xmltv_channels(self, make_stream) -> dict:
        """第一遍扫描：只收集 <channel>，返回 id -> 显示名（无显示名的频道不入表）"""
        import xml.etree.ElementTree as ET
        names = {}
        with make_stream() as stream:
            for _event, elem in ET.iterparse(stream, events=('end',)):
                if elem.tag == 'channel':
                    cid = elem.get('id')
                    if cid and cid not in names:
                        for display_name in elem.findall('display-name'):
                            if display_name.text:
                                names[cid] = display_name.text.strip()
                                break
                    elem.clear()
                elif elem.tag == 'programme':
                    # 第一遍不关心节目内容，立即释放
                    elem.clear()
        return names

    def _scan_xmltv_programmes(self, make_stream, keep_ids, channel_names: dict) -> dict:
        """第二遍扫描：按 keep_ids 过滤 <programme>（keep_ids 为 None 表示不过滤）"""
        import xml.etree.ElementTree as ET
        result = {cid: [] for cid in channel_names if keep_ids is None or cid in keep_ids}
        with make_stream() as stream:
            for _event, elem in ET.iterparse(stream, events=('end',)):
                if elem.tag != 'programme':
                    if elem.tag == 'channel':
                        elem.clear()
                    continue

                try:
                    channel_id = elem.get('channel')
                    if not channel_id or (keep_ids is not None and channel_id not in keep_ids):
                        continue
                    start = elem.get('start')
                    if not start:
                        continue

                    title = None
                    for title_elem in elem.findall('title'):
                        if title_elem.text:
                            title = title_elem.text
                            break
                    if not title:
                        continue

                    desc = None
                    for desc_elem in elem.findall('desc'):
                        if desc_elem.text:
                            desc = desc_elem.text
                            break

                    try:
                        start_time = self._parse_xmltv_time(start)
                    except ValueError:
                        # 时间非法的节目直接跳过，避免被错误地显示为“正在播”
                        logger.debug(f"跳过时间非法的EPG节目: {channel_id} {start}")
                        continue

                    end = elem.get('stop') or elem.get('end')
                    if end:
                        try:
                            end_time = self._parse_xmltv_time(end)
                        except ValueError:
                            end_time = start_time + timedelta(minutes=30)
                    else:
                        end_time = start_time + timedelta(minutes=30)

                    result.setdefault(channel_id, []).append({
                        'title': title,
                        'desc': desc or '',
                        'start': start_time.isoformat(),
                        'end': end_time.isoformat()
                    })
                finally:
                    # 无论是否保留都必须释放元素，否则流式解析退化为整树驻留
                    elem.clear()
        return result

    def _resolve_epg_target_ids(self, channel_names: dict) -> tuple[set, dict]:
        """从当前频道表推导要保留的 EPG 频道 id，复用 EpgMatcher 的既有匹配规则

        同时返回诊断统计（命中 / 无匹配），供日志区分“源里没有该频道”与“频道有但没节目”。

        Returns:
            (target_ids, stats)。target_ids 为空集合表示本次不做过滤（调用方回落为保留全部频道）。
        """
        stats = {'table_size': 0, 'matched': [], 'unmatched': []}
        if not channel_names:
            return set(), stats

        try:
            from core.application_state import app_state
            channels = app_state.channels
        except Exception as e:
            logger.warning(f"EPG过滤：读取频道表失败，本次保留全部频道: {e}")
            return set(), stats

        stats['table_size'] = len(channels) if channels else 0
        if not channels:
            logger.info("EPG过滤：频道表为空，本次保留全部频道")
            return set(), stats

        try:
            from services.epg_matcher import EpgMatcher
        except Exception as e:
            logger.warning(f"EPG过滤：EpgMatcher 不可用，本次保留全部频道: {e}")
            return set(), stats

        target_ids = set()
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            display_name = (
                channel.get('name') or channel.get('tvg_name')
                or channel.get('tvg_id') or '(未命名频道)'
            )
            try:
                matched = EpgMatcher.match(
                    channel.get('name', ''),
                    channel_names,
                    tvg_id=channel.get('tvg_id') or None,
                    tvg_name=channel.get('tvg_name') or None,
                    comma_name=channel.get('comma_name') or None,
                )
            except Exception:
                matched = None
            if matched:
                target_ids.add(matched)
                stats['matched'].append((display_name, matched))
            else:
                stats['unmatched'].append(display_name)
        return target_ids, stats


    def _parse_xmltv_time(self, time_str):
        time_str = time_str.strip()
        if not time_str or not time_str[0].isdigit():
            raise ValueError(f"非标准XMLTV时间格式: '{time_str}'")
        parts = time_str.split()
        dt_part = parts[0][:20]
        if len(dt_part) < 14 or not dt_part[:14].isdigit():
            raise ValueError(f"非标准XMLTV时间格式: '{time_str}'")
        tz_part = parts[1] if len(parts) > 1 else None
        dt = datetime(
            int(dt_part[0:4]), int(dt_part[4:6]), int(dt_part[6:8]),
            int(dt_part[8:10]), int(dt_part[10:12]), int(dt_part[12:14]),
        )
        if tz_part:
            sign = 1 if tz_part[0] == '+' else -1
            tz_hours = int(tz_part[1:3])
            tz_minutes = int(tz_part[3:5]) if len(tz_part) >= 5 else 0
            offset = timedelta(hours=tz_hours, minutes=tz_minutes) * sign
            # 明确按 UTC 计算，再交给系统按“该日期”的时区规则转换（正确处理夏令时）
            dt_utc = dt.replace(tzinfo=timezone.utc) - offset
            dt = dt_utc.astimezone().replace(tzinfo=None)
        return dt

    def get_epg_data_copy(self) -> dict:
        """线程安全地获取EPG数据的浅拷贝"""
        with self._epg_lock:
            return dict(self._epg_data)

    def get_epg_channel_names(self) -> dict:
        """线程安全地获取 EPG 频道 id -> 显示名 的映射拷贝"""
        with self._epg_lock:
            return dict(self._epg_channel_names)

    @staticmethod
    def _clear_epg_matcher_cache() -> None:
        """EPG 数据变更后清空匹配缓存，避免旧匹配结果在新数据上继续生效"""
        try:
            from services.epg_matcher import EpgMatcher
            EpgMatcher.clear_cache()
        except Exception:
            pass

    def get_channel_epg(self, channel_name: str, tvg_id: str | None = None,
                        tvg_name: str | None = None, comma_name: str | None = None) -> list:
        """获取频道的EPG节目列表（仅精确匹配）

        匹配优先级：
        1. tvg-name 精确匹配
        2. tvg-id 精确匹配
        3. m3u标签行逗号后的频道名字精确匹配
        4. channel_name 精确匹配

        Args:
            channel_name: 频道名称
            tvg_id: TVG-ID（可选）
            tvg_name: TVG-NAME（可选）
            comma_name: m3u标签行逗号后的频道名字（可选）

        Returns:
            节目列表
        """
        with self._epg_lock:
            if tvg_name:
                if tvg_name in self._epg_data:
                    return list(self._epg_data[tvg_name])

            if tvg_id:
                if tvg_id in self._epg_data:
                    return list(self._epg_data[tvg_id])

            if comma_name:
                if comma_name in self._epg_data:
                    return list(self._epg_data[comma_name])

            if channel_name:
                if channel_name in self._epg_data:
                    return list(self._epg_data[channel_name])

            try:
                from services.epg_matcher import EpgMatcher
                epg_channels = {epg_id: self._epg_channel_names.get(epg_id, epg_id) for epg_id in self._epg_data.keys()}
                matched_id = EpgMatcher.match(
                    channel_name, epg_channels,
                    tvg_id=tvg_id, tvg_name=tvg_name, comma_name=comma_name
                )
                if matched_id and matched_id in self._epg_data:
                    return list(self._epg_data[matched_id])
            except Exception as ex:
                logger.warning(f"EpgMatcher 匹配异常: {ex}")

            return []
    
    def get_current_program(self, channel_name: str, tvg_id: str | None = None,
                            tvg_name: str | None = None, comma_name: str | None = None) -> dict | None:
        """获取当前正在播放的节目"""
        epg_list = self.get_channel_epg(channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
        if not epg_list:
            return None
        
        now = datetime.now()
        for program in epg_list:
            try:
                start_time = datetime.fromisoformat(program.get('start', ''))
                end_time = datetime.fromisoformat(program.get('end', ''))
                if start_time <= now <= end_time:
                    return program
            except Exception:
                continue
        return None
    
    def get_next_program(self, channel_name: str, tvg_id: str | None = None,
                         tvg_name: str | None = None, comma_name: str | None = None) -> dict | None:
        """获取下一个节目"""
        epg_list = self.get_channel_epg(channel_name, tvg_id, tvg_name=tvg_name, comma_name=comma_name)
        if not epg_list:
            return None
        
        now = datetime.now()
        for program in epg_list:
            try:
                start_time = datetime.fromisoformat(program.get('start', ''))
                if start_time > now:
                    return program
            except (ValueError, KeyError):
                continue
        return None
    
    def register_update_callback(self, callback):
        with self._epg_lock:
            if callback not in self._update_callbacks:
                self._update_callbacks.append(callback)
    
    def unregister_update_callback(self, callback):
        with self._epg_lock:
            if callback in self._update_callbacks:
                self._update_callbacks.remove(callback)
    
    def _notify_update_callbacks(self):
        """通知所有注册的更新回调（确保在主线程执行）"""
        with self._epg_lock:
            callbacks = list(self._update_callbacks)
        # PySide6 仅桌面端存在；Android（p4a 共享包）上无 GUI，直接同步执行回调。
        # 延迟导入避免模块级依赖 PySide6（commit e179d8a6 曾上提导致 Android init 崩溃）。
        try:
            from PySide6.QtCore import QThread
            from PySide6.QtWidgets import QApplication
            has_qt = True
        except ImportError:
            has_qt = False
        for callback in callbacks:
            try:
                # 如果当前在子线程，通过 QMetaObject.invokeMethod 调度到主线程
                if not has_qt:
                    callback()
                    continue
                main_thread = QApplication.instance().thread() if QApplication.instance() else None
                if main_thread and QThread.currentThread() != main_thread:
                    from utils.thread_safety import invoke_on_thread
                    app_instance = QApplication.instance()
                    invoke_on_thread(app_instance, callback)
                else:
                    callback()
            except Exception as e:
                logger.error(f"执行EPG更新回调失败: {e}")
    
    def _save_epg_cache(self, data: dict):
        """保存EPG数据到缓存文件

        Args:
            data: EPG数据字典
        """
        import json
        import tempfile

        cache_dir = self._get_cache_dir()

        cache_file = os.path.join(cache_dir, 'epg_cache.json')
        try:
            with self._epg_lock:
                channel_names = dict(self._epg_channel_names)
            cache_payload = {
                'epg_data': data,
                'channel_names': channel_names,
            }
            fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.tmp', prefix='epg_')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(cache_payload, f, ensure_ascii=False, separators=(',', ':'))
                os.replace(tmp_path, cache_file)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"EPG数据已保存到缓存: {cache_file}")
        except Exception as e:
            logger.error(f"保存EPG缓存失败: {e}")
    
    def load_cached_epg_data(self) -> bool:
        """从缓存加载EPG数据

        Returns:
            是否成功加载
        """
        import json
        
        cache_dir = self._get_cache_dir()
        cache_file = os.path.join(cache_dir, 'epg_cache.json')
        
        logger.info(f"load_cached_epg_data: cache_file={cache_file}, exists={os.path.exists(cache_file)}")
        if not os.path.exists(cache_file):
            return False
        
        try:
            file_size = os.path.getsize(cache_file)
            logger.info(f"load_cached_epg_data: loading {file_size} bytes from {cache_file}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self._epg_lock:
                if isinstance(data, dict) and 'epg_data' in data:
                    self._epg_data = data['epg_data']
                    self._epg_channel_names = data.get('channel_names', {})
                else:
                    self._epg_data = data
                    self._epg_channel_names = {}
                    for channel_id in data.keys():
                        self._epg_channel_names[channel_id] = channel_id
                self._last_epg_update = datetime.now()
            self._clear_epg_matcher_cache()
            
            logger.info(f"load_cached_epg_data: 成功加载 {len(self._epg_data)} 个频道")
            return True
        except Exception as e:
            logger.error(f"加载EPG缓存失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def _to_int(value, default: int) -> int:
        """配置值转整数，非法值回退默认值而不是抛异常导致缓存被判定失效"""
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            logger.warning(f"配置值无法转换为整数: {value!r}，使用默认值 {default}")
            return default

    def is_epg_valid(self) -> bool:
        """检查EPG缓存数据是否有效（基于缓存文件修改时间和配置的更新间隔，
        同时检查数据中是否包含今天的节目）

        Returns:
            是否有效
        """
        cache_dir = self._get_cache_dir()
        cache_file = os.path.join(cache_dir, 'epg_cache.json')

        if not os.path.exists(cache_file):
            return False

        try:
            file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
            age_seconds = (datetime.now() - file_mtime).total_seconds()

            update_interval = self._to_int(self._config.get_value('EPGSources', 'update_interval', '60'), 60)
            max_age_seconds = max(update_interval, 1) * 60

            if age_seconds > max_age_seconds:
                logger.debug(f"EPG缓存文件已过期: {age_seconds/60:.0f} 分钟前 (配置间隔: {update_interval} 分钟)")
                return False

            with self._epg_lock:
                epg_snapshot = dict(self._epg_data)
            if epg_snapshot:
                from datetime import date as date_type
                today = date_type.today()
                has_today = False
                for programs in epg_snapshot.values():
                    if programs and isinstance(programs, list):
                        for prog in programs[:3]:
                            start_str = prog.get('start', '')
                            if start_str:
                                try:
                                    from datetime import datetime as dt
                                    if dt.fromisoformat(start_str).date() == today:
                                        has_today = True
                                        break
                                except (ValueError, TypeError):
                                    pass
                        if has_today:
                            break
                if not has_today:
                    logger.info("EPG缓存文件未过期但无今天的节目数据，需要刷新")
                    return False

            return True
        except Exception as e:
            logger.debug(f"检查EPG缓存有效性失败: {e}")
            return False
    
    def refresh_epg(self, status_callback=None) -> bool:
        """刷新所有EPG数据

        Args:
            status_callback: 状态回调函数

        Returns:
            是否成功刷新
        """
        return self.load_all_epg_data(status_callback)


global_subscription_manager = SubscriptionManager()
