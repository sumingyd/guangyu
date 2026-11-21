import threading
import queue
import time
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
from services.url_parser_service import URLRangeParser
from services.network_context import build_network_context
from core.log_manager import global_logger
from models.channel_model import ChannelListModel
from PySide6 import QtCore
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication
from models.channel_mappings import extract_channel_name_from_url
from utils.scan_state_manager import get_scan_state_manager
from utils.delay_constants import DelayMs
from services.validity_tiers import (
    INVALID,
    STATUS_TEXT,
    SUSPECTED,
    VALID,
    VALID_BOOL,
    channel_tier,
)


def calculate_optimal_queue_size(thread_count: int = 10) -> int:
    """根据系统资源动态计算最优队列大小

    Args:
        thread_count: 扫描线程数

    Returns:
        int: 最优队列大小（URL数量）

    算法说明：
    - 基于可用内存：每个URL条目约占用1KB内存
    - 基于线程数：队列应至少能容纳线程数 * 10 的任务量
    - 限制范围：1000 - 50000，避免过大或过小
    """
    try:
        import psutil

        # 获取系统资源信息
        memory_mb = psutil.virtual_memory().available / (1024 * 1024)
        cpu_count = psutil.cpu_count() or 4

        # 基于内存计算（使用5%的可用内存，假设每条目1KB）
        memory_based = int(memory_mb * 0.05 * 1024)  # 转换为条目数

        # 基于线程数计算（每个线程至少有10个待处理任务）
        thread_based = thread_count * 10

        # 基于CPU核心数计算（每个核心至少1000个任务）
        cpu_based = cpu_count * 1000

        # 取三者中的最小值，确保不会过度占用资源
        optimal = min(memory_based, thread_based, cpu_based)

        # 限制在合理范围内
        optimal = max(1000, min(optimal, 50000))

        return optimal

    except ImportError:
        # psutil不可用，使用基于线程数的简单计算
        return max(1000, thread_count * 100)
    except Exception as e:
        # 出错时返回保守的默认值
        global_logger.debug(f"计算最优队列大小失败: {e}，使用默认值")
        return 10000


class ScannerController(QObject):
    """扫描控制器，管理多线程扫描过程"""

    # 定义信号
    progress_updated = Signal(int, int)  # 当前进度, 总数
    channel_found = Signal(dict)  # 有效的频道信息
    scan_completed = Signal()
    stats_updated = Signal(dict)  # 统计信息

    # 在类定义中声明信号（末位为三档有效性：valid / suspected / invalid）
    channel_validated = Signal(int, bool, int, str, str)

    def __init__(self, model: ChannelListModel, main_window=None) -> None:
        super().__init__()
        self.logger = global_logger
        self.model = model
        self.main_window = main_window
        self.url_parser = URLRangeParser()
        self.is_validating = False
        self._is_validation_retry = False
        self.stats_lock = threading.Lock()
        self.scan_queue = queue.Queue()  # 扫描专用队列
        self.validation_queue = queue.Queue()  # 验证专用队列
        self.stop_event = threading.Event()
        self.workers: List[threading.Thread] = []
        self.timeout = 10  # 默认超时时间
        self.channel_counter = 0
        self.counter_lock = threading.Lock()
        self._optimal_queue_size = 10000  # 动态计算的队列大小（默认值）
        self.stats: Dict[str, Any] = {
            'total': 0,
            'valid': 0,
            'suspected': 0,
            'invalid': 0,
            'start_time': 0,
            'elapsed': 0
        }
        # 并发槽位不足时本轮跳过、下一轮再测（不判无效）的尝试计数
        self._skip_attempts: Dict[str, int] = {}
        # 记录无效的URL，用于重试扫描（委托给scan_state_manager）
        self._max_invalid_urls = 50000

        # 扫描状态管理器
        self.scan_state_manager = get_scan_state_manager()
        self.scan_id = 'main_scan'
        self._validator = None
        self._scan_engine = None
        # 本轮是否为「疑似复核」：完成回调与统计口径不同
        self._is_suspected_recheck = False
        # 轮次编号：上一轮统计线程收尾时不能清掉新一轮的上下文快照
        self._round_generation = 0
        self._mapping_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mapper")
        self._pending_channels = []
        self._pending_lock = threading.Lock()
        self._batch_flush_pending = None
        self._pending_mappings = {}
        self._pending_validations = []
        self._validation_flush_timer = None

    def _force_ui_refresh(self):
        try:
            if hasattr(self.model, 'update_view'):
                self.model.update_view()
            elif hasattr(self.model, 'layoutChanged'):
                self.model.layoutChanged.emit()
        except Exception as e:
            self.logger.debug(f"UI刷新失败: {e}")

    @staticmethod
    def _run_on_main(func, *args):
        from utils.thread_safety import invoke_on_thread
        app = QApplication.instance()
        if app:
            invoke_on_thread(app, functools.partial(func, *args))
        else:
            QtCore.QTimer.singleShot(DelayMs.NEXT_TICK, functools.partial(func, *args))

    def _worker(self) -> None:
        """工作线程函数"""
        while not self.stop_event.is_set():
            try:
                url = self.scan_queue.get(timeout=0.5)
            except queue.Empty:
                if hasattr(self, 'filler_thread') and not self.filler_thread.is_alive():
                    try:
                        url = self.scan_queue.get_nowait()
                    except queue.Empty:
                        break
                else:
                    continue

            try:
                result = self._check_channel(url)

                # 并发槽位不足：本轮跳过、下一轮再测，绝不判无效
                if result.get('skipped'):
                    attempts = self._skip_attempts.get(url, 0) + 1
                    self._skip_attempts[url] = attempts
                    if attempts <= 5 and not self.stop_event.is_set():
                        self.scan_queue.put(url)
                        continue
                    # 多次抢不到槽位：保留为疑似弱结果，仍不判无效
                    result['validity'] = SUSPECTED
                    result['valid'] = False
                    result['error_type'] = 'concurrency_limit'
                    result['error'] = '并发数超限（未完成检测）'

                validity = result.get('validity') or (VALID if result.get('valid') else INVALID)
                valid = validity == VALID
                suspected = validity == SUSPECTED
                latency = result['latency']
                resolution = result.get('resolution', '')

                try:
                    channel_info = self._build_channel_info(
                        url, validity == VALID, latency, resolution, result
                    )
                except Exception:
                    channel_info = {
                        'url': url,
                        'name': url.split('/')[-1] if '/' in url else url,
                        'raw_name': url.split('/')[-1] if '/' in url else url,
                        'valid': VALID_BOOL[validity],
                        'validity': validity,
                        'latency': latency,
                        'resolution': resolution,
                        'status': STATUS_TEXT[validity],
                        'group': '未分类',
                        'logo': None,
                        'needs_details': False
                    }

                if valid or suspected:
                    channel_info.setdefault(
                        'name', channel_info.get(
                            'raw_name', extract_channel_name_from_url(url)
                        )
                    )
                    self._run_on_main(self._handle_channel_add, channel_info.copy())
                    if valid:
                        self._start_async_mapping_check(channel_info.copy())

                with self.stats_lock:
                    if valid:
                        self.stats['valid'] += 1
                    elif suspected:
                        self.stats['suspected'] += 1
                        self.logger.debug(
                            f"扫描疑似: {url} | error_type={result.get('error_type')} | "
                            f"error={result.get('error', '')}"
                        )
                    else:
                        self.stats['invalid'] += 1
                        error_type = result.get('error_type') or 'unknown_error'
                        error_msg = result.get('error', '')
                        self.logger.debug(f"扫描无效: {url} | error_type={error_type} | error={error_msg}")
                        if self.stats['invalid'] % 50 == 1:
                            self.logger.debug(
                                f"扫描进度: 有效={self.stats['valid']}, "
                                f"疑似={self.stats['suspected']}, "
                                f"无效={self.stats['invalid']}, "
                                f"最新错误类型={error_type}"
                            )
                        self.scan_state_manager.add_invalid_url(self.scan_id, url, error_type)

                    current = self.stats['valid'] + self.stats['suspected'] + self.stats['invalid']
                    total = self.stats['total']

                if total <= 0:
                    total = 100
                    self._run_on_main(self.progress_updated.emit, current, total)

            except Exception as e:
                self.logger.warning(f"扫描URL异常: {url} - {e}")
                with self.stats_lock:
                    self.stats['invalid'] += 1
                    self.scan_state_manager.add_invalid_url(self.scan_id, url, f'exception: {e}')
                    current = self.stats['valid'] + self.stats['invalid']
                    total = self.stats['total']
                    if total <= 0:
                        total = 100
                    self._run_on_main(self.progress_updated.emit, current, total)

                continue

        self._run_on_main(self._flush_pending_channels)

        with self.stats_lock:
            current = self.stats['valid'] + self.stats['invalid']
            total = self.stats['total']
            if current < total:
                self._run_on_main(self.progress_updated.emit, total, total)

    def _handle_channel_add(self, channel_info: dict):
        """处理频道添加：攒批后一次性插入模型，减少视图通知次数"""
        with self._pending_lock:
            self._pending_channels.append(channel_info)
            if self._batch_flush_pending is not None:
                return
            self._batch_flush_pending = True

        QtCore.QTimer.singleShot(DelayMs.LAYOUT_SETTLE, self._flush_pending_channels)

    def _flush_pending_channels(self):
        """将攒批的频道一次性添加到模型，扫描期间使用 reset 模式避免竞态崩溃"""
        with self._pending_lock:
            channels = self._pending_channels
            self._pending_channels = []
            self._batch_flush_pending = None

        if channels:
            is_scanning = not self.stop_event.is_set()
            self.model.add_channels(channels, is_from_file=False, use_reset=is_scanning)
        self._apply_pending_mappings()
        if channels or self._pending_mappings:
            self._force_ui_refresh()

    def _apply_pending_mappings(self):
        """应用暂存的映射结果到已加入模型的频道"""
        if not self._pending_mappings:
            return
        applied_urls = []
        for url, mapped_info in self._pending_mappings.items():
            success = self.model.update_channel_by_url(url, mapped_info)
            if success:
                applied_urls.append(url)
        for url in applied_urls:
            del self._pending_mappings[url]

    def _apply_pending_mappings_and_refresh(self):
        """应用暂存映射并刷新UI"""
        self._apply_pending_mappings()
        self._force_ui_refresh()

    def _build_channel_info(
        self, url: str, valid: bool, latency: int,
        resolution: str, result: dict
    ) -> dict:
        """构建基本的频道信息字典 - 优化版本，只在异步线程中检查映射"""
        from models.channel_mappings import extract_channel_name_from_url

        try:
            # 直接从URL提取频道名
            channel_name = extract_channel_name_from_url(url)

            # 重要修改：验证有效后不立即检查映射！
            # 只在异步线程中检查映射，避免重复日志和性能浪费

            # 注意：这里不再调用 mapping_manager.get_channel_info
            # 映射检查将在异步线程 _fetch_channel_details 中进行

            validity = result.get('validity') or (VALID if valid else INVALID)

            # 构建频道信息（只包含基本信息，不包含映射信息）
            channel_info = {
                'url': url,
                'name': channel_name,  # 使用URL提取的名称
                'raw_name': channel_name,
                'valid': VALID_BOOL[validity],
                'validity': validity,
                'latency': latency,
                'resolution': result.get('resolution', ''),
                'codec': result.get('codec', '') or '',
                'bitrate': result.get('bitrate', '') or '',
                'status': STATUS_TEXT[validity],
                'group': '未分类',  # 默认分组，异步线程中更新
                'logo': None,   # 默认无logo，异步线程中更新
                'needs_details': False  # 重要：这里设为False，异步线程中再决定是否需要获取详情
            }

            # 计算流质量评分（仅确证有效的频道有意义；疑似不展示评分条）
            if validity == VALID:
                from services.stream_quality_scorer import StreamQualityScorer
                score_info = StreamQualityScorer.score_from_channel(channel_info)
                channel_info['quality_score'] = score_info.get('total', 0)
                channel_info['quality_grade'] = score_info.get('grade', 'F')

            # 注意：这里不启动异步获取详细信息
            # 异步获取将在 _start_async_mapping_check 方法中决定

            return channel_info

        except Exception as e:
            # 返回基本的频道信息，即使构建失败
            validity = result.get('validity') or (VALID if valid else INVALID)
            fallback_info = {
                'url': url,
                'name': extract_channel_name_from_url(url),
                'raw_name': extract_channel_name_from_url(url),
                'valid': VALID_BOOL[validity],
                'validity': validity,
                'latency': latency,
                'resolution': result.get('resolution', ''),
                'codec': result.get('codec', '') or '',
                'bitrate': result.get('bitrate', '') or '',
                'status': STATUS_TEXT[validity],
                'group': '未分类',
                'logo': None,
                'error': str(e),
                'needs_details': False
            }
            if validity == VALID:
                from services.stream_quality_scorer import StreamQualityScorer
                score_info = StreamQualityScorer.score_from_channel(fallback_info)
                fallback_info['quality_score'] = score_info.get('total', 0)
                fallback_info['quality_grade'] = score_info.get('grade', 'F')
            return fallback_info

    def _start_async_details_fetch(self, channel_info: dict):
        if self._mapping_executor is None:
            self._mapping_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mapper")
        self._mapping_executor.submit(self._fetch_channel_details, channel_info)

    def _fetch_channel_details(self, channel_info: dict):
        """获取频道详细信息（仅用于有映射的频道）"""
        max_retries = 3
        retry_delays = [1, 2, 3]  # 重试延迟（秒）

        for retry_count in range(max_retries):
            try:
                url = channel_info['url']

                # 获取映射信息
                from models.channel_mappings import mapping_manager
                channel_info_for_fingerprint = {
                    'service_name': channel_info['raw_name'],
                    'resolution': channel_info.get('resolution', ''),
                    'codec': channel_info.get('codec', ''),
                    'bitrate': channel_info.get('bitrate', '')
                }

                mapped_info = mapping_manager.get_channel_info(
                    channel_info['raw_name'],
                    url,
                    channel_info_for_fingerprint
                )

                # 更新频道信息
                updated_info = channel_info.copy()

                # 更新映射信息
                if mapped_info:
                    # 更新标准名称
                    if mapped_info.get('standard_name'):
                        updated_info['name'] = mapped_info['standard_name']

                    # 更新分组
                    if mapped_info.get('group_name'):
                        updated_info['group'] = mapped_info['group_name']

                    # 更新logo
                    logo_url = mapped_info.get('logo_url')
                    if logo_url and isinstance(logo_url, str) and logo_url.strip():
                        updated_info['logo'] = logo_url.strip()

                    # 更新其他映射字段
                    if mapped_info.get('tvg_id'):
                        updated_info['tvg_id'] = mapped_info['tvg_id']
                    if mapped_info.get('tvg_chno'):
                        updated_info['tvg_chno'] = mapped_info['tvg_chno']
                    if mapped_info.get('tvg_shift'):
                        updated_info['tvg_shift'] = mapped_info['tvg_shift']
                    if mapped_info.get('catchup'):
                        updated_info['catchup'] = mapped_info['catchup']
                    if mapped_info.get('catchup_days'):
                        updated_info['catchup_days'] = mapped_info['catchup_days']
                    if mapped_info.get('catchup_source'):
                        updated_info['catchup_source'] = mapped_info['catchup_source']

                    # 创建指纹
                    updated_info['fingerprint'] = mapping_manager.create_channel_fingerprint(
                        url, channel_info_for_fingerprint
                    )

                updated_info['needs_details'] = False

                self._run_on_main(self._update_channel_details, updated_info)
                return

            except Exception as e:
                self.logger.warning(
                    f"获取频道详细信息失败 (重试 {retry_count + 1}/{max_retries}): {e}"
                )
                if retry_count < max_retries - 1:
                    time.sleep(retry_delays[retry_count])
                else:
                    channel_info['needs_details'] = False
                    self._run_on_main(self._update_channel_details, channel_info)

    def _start_async_mapping_check(self, channel_info: dict):
        """启动异步映射检查 - 所有有效频道都检查映射"""
        from models.channel_mappings import mapping_manager
        if not mapping_manager.enable_mapping:
            return
        self._start_async_details_fetch(channel_info)

    def _update_channel_details(self, channel_info: dict):
        """更新频道详细信息，如果频道尚未加入模型则暂存映射结果"""
        try:
            url = channel_info.get('url')
            if url:
                success = self.model.update_channel_by_url(url, channel_info)
                if not success:
                    self._pending_mappings[url] = channel_info
                    QtCore.QTimer.singleShot(DelayMs.DEFERRED_INIT, self._apply_pending_mappings_and_refresh)
            else:
                self.logger.debug("频道信息缺少URL，跳过更新")

            self._force_ui_refresh()

        except Exception as e:
            self.logger.debug(f"更新频道详细信息失败: {e}")

    def _get_validator_class(self):
        """根据配置获取验证器类"""
        engine = 'ffprobe'
        try:
            from core.config_manager import ConfigManager
            settings = ConfigManager().load_scan_engine_settings()
            engine = settings.get('engine', 'ffprobe')
        except Exception as e:
            global_logger.debug(f"_get_validator_class: {e}")
        self._scan_engine = engine
        if engine == 'ffprobe':
            from services.ffprobe_validator_service import FfprobeStreamValidator
            return FfprobeStreamValidator
        if engine == 'fast':
            from services.fast_probe_service import FastProbeValidator
            return FastProbeValidator
        from services.mpv_validator_service import MpvStreamValidator
        return MpvStreamValidator

    def _snapshot_network_context(self, timeout, user_agent=None, referer=None):
        """整轮扫描开始时快照一次网络上下文，本轮跑完即丢弃。

        扫描途中用户改代理/请求头/超时，不影响正在跑的这一轮。
        """
        try:
            ValidatorClass = self._get_validator_class()
            setter = getattr(ValidatorClass, 'set_scan_context', None)
            if setter is None:
                return
            setter(build_network_context(
                connect_timeout=timeout,
                user_agent=user_agent or None,
                referer=referer or None,
            ))
        except Exception as e:
            self.logger.debug(f"网络上下文快照失败，退回逐条构造: {e}")

    def _clear_network_context(self):
        """丢弃本轮快照；下次扫描会重新读取设置。"""
        try:
            ValidatorClass = self._get_validator_class()
            clearer = getattr(ValidatorClass, 'clear_scan_context', None)
            if clearer is not None:
                clearer()
        except Exception as e:
            self.logger.debug(f"清理网络上下文快照失败: {e}")

    def _check_channel(
        self, url: str, raw_channel_name: str | None = None
    ) -> Dict[str, Any]:
        if self._validator is None:
            ValidatorClass = self._get_validator_class()
            self._validator = ValidatorClass(self.main_window)
            self.logger.info(f"扫描引擎: {self._scan_engine}")
        return self._validator.validate_stream(
            url,
            raw_channel_name=raw_channel_name,
            timeout=self.timeout
        )

    def _fill_queue(self):
        """动态填充扫描队列 - 优化版，避免内存爆炸"""
        try:
            batch_count = 0
            skip_urls = getattr(self, '_skip_urls', set())
            for batch in self.url_generator:
                if self.stop_event.is_set():
                    break

                batch_count += 1

                if skip_urls:
                    filtered = [url for url in batch if url not in skip_urls]
                    skipped = len(batch) - len(filtered)
                    with self.stats_lock:
                        self.stats['total'] += len(filtered)
                    if skipped > 0:
                        self.logger.debug(f"追加扫描跳过 {skipped} 个已存在URL")
                else:
                    filtered = batch
                    with self.stats_lock:
                        self.stats['total'] += len(batch)

                for url in filtered:
                    if self.stop_event.is_set():
                        break
                    self.scan_queue.put(url)

                # 保持队列适度填充，避免内存占用过高（使用动态计算的队列大小）
                while self.scan_queue.qsize() > self._optimal_queue_size and not self.stop_event.is_set():
                    time.sleep(0.1)

                # 每处理100个批次后稍微休息，避免CPU占用过高
                if batch_count % 100 == 0:
                    time.sleep(0.01)

        except Exception as e:
            self.logger.debug(f"队列填充线程异常: {e}")
        finally:
            self.logger.debug(f"队列填充完成，共处理 {batch_count} 个批次")

    def is_scanning(self):
        """检查是否正在扫描"""
        return len(self.workers) > 0 and not self.stop_event.is_set()

    def start_scan(
        self, base_url: str, thread_count: int = 10, timeout: int = 10,
        user_agent: str | None = None, referer: str | None = None,
        skip_urls: set | None = None
    ) -> None:
        """开始扫描 - 优化版本"""
        # 确保停止之前的扫描
        self.stop_scan()
        self.stop_event.clear()

        ValidatorClass = self._get_validator_class()
        ValidatorClass.reset_terminating()
        self._validator = None

        self._skip_urls = skip_urls or set()

        # 注册扫描状态（不使用上下文管理器，因为扫描是异步的）
        self.scan_state_manager.register_scan(self.scan_id, self)
        self._start_scan_internal(base_url, thread_count, timeout, user_agent, referer)

    def _start_scan_internal(
        self, base_url: str, thread_count: int = 10, timeout: int = 10,
        user_agent: str | None = None, referer: str | None = None
    ) -> None:
        """内部扫描启动方法"""

        self.timeout = timeout
        self._skip_attempts = {}
        self._round_generation += 1

        self.scan_state_manager.clear_invalid_urls(self.scan_id)

        self._optimal_queue_size = calculate_optimal_queue_size(thread_count)
        self.logger.debug(f"动态计算最优队列大小: {self._optimal_queue_size}（线程数: {thread_count}）")

        ValidatorClass = self._get_validator_class()
        if self._scan_engine == 'mpv':
            ValidatorClass.set_max_concurrent(min(thread_count, 8))
        else:
            ValidatorClass.set_max_concurrent(thread_count)
        ValidatorClass.reset_terminating()
        if user_agent is not None:
            ValidatorClass.set_user_agent(user_agent)
        if referer is not None:
            ValidatorClass.set_referer(referer)
        # 本轮只读取一次设置；扫描途中改设置不生效
        self._snapshot_network_context(timeout, user_agent, referer)

        # 初始化统计信息
        self.stats = {
            'total': 0,  # 初始为0，由填充线程动态更新
            'valid': 0,
            'suspected': 0,
            'invalid': 0,
            'start_time': time.time(),
            'elapsed': 0
        }

        # 更新扫描状态管理器
        self.scan_state_manager.update_scan_state(self.scan_id, {
            'is_scanning': True,
            'scanner': self
        })
        self.scan_state_manager.update_stats(self.scan_id, self.stats)

        # 初始化队列和生成器
        self.scan_queue = queue.Queue()
        self.url_generator = self.url_parser.parse_url(base_url)

        # 启动队列填充线程（不再预填充，所有URL都由填充线程处理）
        self.filler_thread = threading.Thread(
            target=self._fill_queue,
            name="QueueFiller",
            daemon=True
        )
        self.filler_thread.start()
        optimal_threads = thread_count if thread_count > 0 else 1  # 至少1个线程

        # 使用优化后的线程数
        self.workers = []
        for i in range(optimal_threads):
            worker = threading.Thread(
                target=self._worker,
                name=f"ScannerWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        self.stats_thread = threading.Thread(
            target=self._update_stats,
            name="StatsUpdater",
            args=(self._round_generation,),
            daemon=True
        )
        self.stats_thread.start()

        # 扫描开始时发送进度更新信号
        self._run_on_main(self.progress_updated.emit, 0, 1)

    def start_scan_from_urls(
        self, urls: list, thread_count: int = 10, timeout: int = 10,
        user_agent: str | None = None, referer: str | None = None,
        is_validation_retry: bool = False
    ):
        """从URL列表开始扫描（用于重试扫描）

        Args:
            is_validation_retry: 是否为检测重试模式，为True时is_validating设为True，
                                 确保统计显示正确显示"检测"而非"扫描"
        """
        # 确保停止之前的扫描
        self.stop_scan()
        self.stop_event.clear()

        ValidatorClass = self._get_validator_class()
        ValidatorClass.reset_terminating()
        self._validator = None

        # 清空扫描状态管理器中的无效URL
        self.scan_state_manager.clear_invalid_urls(self.scan_id)

        # 注册扫描状态（不使用上下文管理器，因为扫描是异步的）
        self.scan_state_manager.register_scan(self.scan_id, self)

        if is_validation_retry:
            self.is_validating = True
            self._is_validation_retry = True
            self.scan_state_manager.update_scan_state(self.scan_id, {
                'is_validating': True
            })

        self._start_scan_from_urls_internal(urls, thread_count, timeout, user_agent, referer)

    def _start_scan_from_urls_internal(
        self, urls: list, thread_count: int = 10, timeout: int = 10,
        user_agent: str | None = None, referer: str | None = None
    ):
        """内部从URL列表开始扫描方法"""

        self.timeout = timeout
        self._skip_attempts = {}
        self._round_generation += 1

        ValidatorClass = self._get_validator_class()
        if self._scan_engine == 'mpv':
            ValidatorClass.set_max_concurrent(min(thread_count, 8))
        else:
            ValidatorClass.set_max_concurrent(thread_count)
        ValidatorClass.reset_terminating()
        if user_agent is not None:
            ValidatorClass.set_user_agent(user_agent)
        if referer is not None:
            ValidatorClass.set_referer(referer)
        self._snapshot_network_context(timeout, user_agent, referer)

        # 初始化统计信息
        self.stats = {
            'total': len(urls),
            'valid': 0,
            'suspected': 0,
            'invalid': 0,
            'start_time': time.time(),
            'elapsed': 0
        }

        # 更新扫描状态管理器
        self.scan_state_manager.update_scan_state(self.scan_id, {
            'is_scanning': True,
            'scanner': self
        })
        self.scan_state_manager.update_stats(self.scan_id, self.stats)

        # 初始化队列
        self.scan_queue = queue.Queue()

        # 填充队列
        for url in urls:
            self.scan_queue.put(url)

        # 使用用户设置的线程数
        self.workers = []
        for i in range(thread_count):
            worker = threading.Thread(
                target=self._worker,
                name=f"RetryScannerWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        self.stats_thread = threading.Thread(
            target=self._update_stats,
            name="RetryStatsUpdater",
            args=(self._round_generation,),
            daemon=True
        )
        self.stats_thread.start()

    def stop_scan(self):
        self.stop_event.set()

        self.scan_state_manager.update_scan_state(self.scan_id, {
            'is_scanning': False
        })

        ValidatorClass = self._get_validator_class()
        ValidatorClass.set_terminating()
        self._clear_network_context()

        self._clear_all_queues()

        alive_workers = [w for w in self.workers if w.is_alive()]
        if alive_workers:
            for worker in alive_workers:
                worker.join(timeout=2.0)
            still_alive = [w for w in alive_workers if w.is_alive()]
            if still_alive:
                self.logger.warning(f"{len(still_alive)} 个扫描工作线程未在2秒内退出")

        ValidatorClass.destroy_all_handles()
        self._validator = None

        if self._mapping_executor is not None:
            try:
                self._mapping_executor.shutdown(wait=True)
            except Exception as e:
                global_logger.debug(f"stop_scan: {e}")
            self._mapping_executor = None

        self.workers = []


    def _clear_all_queues(self):
        """清空所有队列"""
        # 清空扫描队列
        while not self.scan_queue.empty():
            try:
                self.scan_queue.get_nowait()
            except queue.Empty:
                break

        # 清空验证队列
        while not self.validation_queue.empty():
            try:
                self.validation_queue.get_nowait()
            except queue.Empty:
                break

        # 如果有队列填充线程，设置标志让它停止
        if hasattr(self, 'filler_thread') and self.filler_thread and self.filler_thread.is_alive():
            pass

    def _terminate_all_processes(self):
        try:
            ValidatorClass = self._get_validator_class()
            ValidatorClass.set_terminating()
            alive_workers = [w for w in self.workers if w.is_alive()]
            if alive_workers:
                for worker in alive_workers:
                    worker.join(timeout=2.0)
            ValidatorClass.destroy_all_handles()
        except Exception as e:
            global_logger.debug(f"_terminate_all_processes: {e}")

    def _cleanup_workers_fast(self):
        """快速清理工作线程"""
        if not self.workers:
            return

        # 记录当前存活的线程
        alive_workers = [w for w in self.workers if w.is_alive()]

        if not alive_workers:
            self.workers = []
            return

        # 第一次尝试：快速等待（0.5秒）
        for worker in alive_workers:
            worker.join(timeout=0.5)

        # 检查哪些线程仍然存活
        still_alive = [w for w in alive_workers if w.is_alive()]

        if still_alive:
            # 记录警告但不阻塞UI
            self.logger.warning(f"{len(still_alive)} 个工作线程仍在运行，将在后台清理")

            # 启动后台线程来等待这些线程
            cleanup_thread = threading.Thread(
                target=self._background_cleanup,
                args=(still_alive,),
                name="BackgroundCleanup",
                daemon=True
            )
            cleanup_thread.start()

        # 清空工作线程列表，让扫描按钮可以立即响应
        self.workers = []

    def _background_cleanup(self, workers):
        """在后台清理工作线程"""
        try:
            # 等待最多3秒
            for worker in workers:
                worker.join(timeout=3.0)

            # 检查是否还有存活的线程
            still_alive = [w for w in workers if w.is_alive()]
            if still_alive:
                self.logger.warning(f"后台清理后仍有 {len(still_alive)} 个线程存活")
        except Exception as e:
            global_logger.debug(f"_background_cleanup: {e}")

    def _cleanup_other_resources(self):
        if hasattr(self, 'stats_thread') and self.stats_thread and self.stats_thread.is_alive():
            self.stats_thread.join(timeout=0.5)

        import gc
        gc.collect(0)

    @staticmethod
    def _collect_validation_targets(model, only_suspected: bool = False):
        """收集待检测的 (url, index)；only_suspected 时只取三档为「疑似」的项。"""
        targets = []
        for i in range(model.rowCount()):
            channel = model.get_channel(i)
            url = (channel.get('url') or '').strip()
            if not url:
                continue
            if only_suspected and channel_tier(channel) != SUSPECTED:
                continue
            targets.append((url, i))
        return targets

    def start_validation(self, model, threads, timeout, user_agent=None, referer=None,
                         *, only_suspected: bool = False,
                         is_suspected_recheck: bool = False):
        """开始有效性验证

        Args:
            only_suspected: 只复核当前三档为「疑似」的频道
            is_suspected_recheck: 本轮是疑似复核，完成时回调专门的槽位
        """
        self.is_validating = True
        self._is_validation_retry = False
        self._is_suspected_recheck = is_suspected_recheck
        self.stop_event.clear()
        self._skip_attempts = {}
        self.timeout = timeout
        self._round_generation += 1

        ValidatorClass = self._get_validator_class()
        ValidatorClass.reset_terminating()
        self._validator = None

        # 更新扫描状态管理器
        self.scan_state_manager.update_scan_state(self.scan_id, {
            'is_validating': True
        })

        ValidatorClass.set_max_concurrent(threads)
        if user_agent is not None:
            ValidatorClass.set_user_agent(user_agent)
        if referer is not None:
            ValidatorClass.set_referer(referer)
        self._snapshot_network_context(timeout, user_agent, referer)

        total = 0
        for url, index in self._collect_validation_targets(model, only_suspected):
            self.validation_queue.put((url, index))
            total += 1

        self.stats = {
            'total': total,
            'valid': 0,
            'suspected': 0,
            'invalid': 0,
            'start_time': time.time(),
            'elapsed': 0
        }

        self.workers = []
        for i in range(threads):
            worker = threading.Thread(
                target=self._validation_worker,
                name=f"ValidationWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        self.stats_thread = threading.Thread(
            target=self._update_stats,
            name="ValidationStatsUpdater",
            args=(self._round_generation,),
            daemon=True
        )
        self.stats_thread.start()

        # 验证开始时发送进度更新信号
        self._run_on_main(self.progress_updated.emit, 0, 1)

    def stop_validation(self):
        """停止有效性验证"""
        self.stop_event.set()
        self.is_validating = False

        self.scan_state_manager.update_scan_state(self.scan_id, {
            'is_validating': False
        })

        ValidatorClass = self._get_validator_class()
        ValidatorClass.set_terminating()
        self._clear_network_context()

        while not self.validation_queue.empty():
            try:
                self.validation_queue.get_nowait()
            except queue.Empty:
                break

        alive_workers = [w for w in self.workers if w.is_alive()]
        if alive_workers:
            for worker in alive_workers:
                worker.join(timeout=2.0)

        ValidatorClass.destroy_all_handles()
        self._validator = None

        self.workers = []


    def _validation_worker(self):
        while not self.stop_event.is_set():
            try:
                try:
                    url, index = self.validation_queue.get(timeout=0.5)
                except queue.Empty:
                    break

                result = self._check_channel(url)

                # 并发槽位不足：本轮跳过、下一轮再测，不判无效
                if result.get('skipped'):
                    attempts = self._skip_attempts.get(url, 0) + 1
                    self._skip_attempts[url] = attempts
                    if attempts <= 5 and not self.stop_event.is_set():
                        self.validation_queue.put((url, index))
                        continue
                    result['validity'] = SUSPECTED
                    result['valid'] = False
                    result['error_type'] = 'concurrency_limit'
                    result['error'] = '并发数超限（未完成检测）'

                validity = result.get('validity') or (VALID if result.get('valid') else INVALID)
                valid = validity == VALID
                latency = result['latency']
                resolution = result.get('resolution', '')

                self._run_on_main(self._handle_validation_result, url, valid, index, latency, resolution, result)

                with self.stats_lock:
                    if valid:
                        self.stats['valid'] += 1
                    elif validity == SUSPECTED:
                        self.stats['suspected'] += 1
                    else:
                        self.stats['invalid'] += 1
                        error_type = result.get('error_type', 'unknown')
                        error_msg = result.get('error', '')
                        self.logger.debug(f"验证无效: {url} | error_type={error_type} | error={error_msg}")

                    current = self.stats['valid'] + self.stats['suspected'] + self.stats['invalid']
                    total = self.stats['total']
                    if total <= 0:
                        total = 1

                    self._run_on_main(self.progress_updated.emit, current, total)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"验证线程错误: {e}", exc_info=True)

    def _handle_validation_result(self, url, valid, index, latency, resolution, result=None):
        """攒批处理验证结果，减少视图通知"""
        validity = (result or {}).get('validity') or (VALID if valid else INVALID)
        with self._pending_lock:
            self._pending_validations.append((url, validity, result))
            if self._validation_flush_timer is None:
                self._validation_flush_timer = True
                QtCore.QTimer.singleShot(DelayMs.LAYOUT_SETTLE, self._flush_pending_validations)
        self.channel_validated.emit(index, valid, latency, resolution, validity)

    def _flush_pending_validations(self):
        """批量应用验证结果"""
        with self._pending_lock:
            validations = self._pending_validations
            self._pending_validations = []
            self._validation_flush_timer = None

        if validations:
            from services.stream_quality_scorer import StreamQualityScorer
            self.model.beginResetModel()
            for url, validity, result in validations:
                for ch in self.model.channels:
                    if ch.get('url') == url:
                        ch['validity'] = validity
                        ch['valid'] = VALID_BOOL[validity]
                        ch['status'] = STATUS_TEXT[validity]
                        # 同步更新验证时探测到的字段（保留最新值）
                        if result:
                            if result.get('latency') is not None:
                                ch['latency'] = result['latency']
                            if result.get('resolution'):
                                ch['resolution'] = result['resolution']
                            if result.get('codec'):
                                ch['codec'] = result['codec']
                            if result.get('bitrate'):
                                ch['bitrate'] = result['bitrate']
                        # 重新计算流质量评分（仅确证有效的频道才有意义）
                        if validity == VALID:
                            score_info = StreamQualityScorer.score_from_channel(ch)
                            ch['quality_score'] = score_info.get('total', 0)
                            ch['quality_grade'] = score_info.get('grade', 'F')
                        else:
                            ch.pop('quality_score', None)
                            ch.pop('quality_grade', None)
                        break
            self.model.endResetModel()

    def _update_stats(self, generation: int | None = None):
        """更新统计信息线程"""
        was_validation = False
        workers_snapshot = list(self.workers)
        try:
            # 简化逻辑：只要没有停止事件就持续更新统计信息
            while not self.stop_event.is_set():
                try:
                    # 使用锁确保获取最新的统计信息
                    with self.stats_lock:
                        self.stats['elapsed'] = time.time() - self.stats['start_time']

                        # 更新扫描状态管理器中的统计信息
                        self.scan_state_manager.update_stats(self.scan_id, self.stats)

                        # 直接调用主窗口的更新方法，避免信号连接问题
                        if self.main_window and hasattr(self.main_window, '_update_stats_display'):
                            stats_copy = self.stats.copy()
                            is_validating = self.is_validating
                            try:
                                self._run_on_main(
                                    self.main_window._update_stats_display,
                                    {'stats': stats_copy, 'is_validation': is_validating}
                                )
                            except RuntimeError:
                                break
                        else:
                            stats_copy = self.stats.copy()
                            is_validating_copy = self.is_validating
                            self._run_on_main(self.stats_updated.emit, {
                                'stats': stats_copy, 'is_validation': is_validating_copy
                            })

                    # 检查扫描是否完成：填充线程结束、所有工作线程都完成且队列为空
                    filler_alive = (
                        self.filler_thread.is_alive()
                        if hasattr(self, 'filler_thread') and self.filler_thread else False
                    )
                    workers_alive = (
                        any(w.is_alive() for w in self.workers)
                        if self.workers else False
                    )
                    queue_empty = (
                        self.scan_queue.empty()
                        if hasattr(self, 'scan_queue') else True
                    )
                    validation_queue_empty = (
                        self.validation_queue.empty()
                        if hasattr(self, 'validation_queue') else True
                    )

                    # 如果填充线程结束、所有工作线程都完成且队列为空，则扫描完成
                    if not filler_alive and not workers_alive and queue_empty and validation_queue_empty:
                        break

                    time.sleep(0.5)  # 恢复到合理的更新频率，避免UI假死
                except RuntimeError:
                    break

            if self.stop_event.is_set():
                self.logger.info("扫描被用户停止")
            elif self.is_validating and not self._is_validation_retry:
                was_validation = True
                self.is_validating = False
                self.workers = []
                self.scan_state_manager.update_scan_state(self.scan_id, {
                    'is_validating': False
                })
                self.logger.info(
                    f"验证完成: 总数={self.stats['total']}, "
                    f"有效={self.stats['valid']}, "
                    f"疑似={self.stats['suspected']}, "
                    f"无效={self.stats['invalid']}"
                )
                if self._is_suspected_recheck:
                    self._is_suspected_recheck = False
                    callback_name = '_on_suspected_recheck_completed'
                else:
                    callback_name = '_on_validation_completed'
                if self.main_window and hasattr(self.main_window, callback_name):
                    try:
                        self._run_on_main(getattr(self.main_window, callback_name))
                    except RuntimeError:
                        self.logger.debug("主窗口已销毁，跳过验证完成回调")
            else:
                self.workers = []
                if self._is_validation_retry:
                    self.is_validating = False
                    self._is_validation_retry = False
                    self.scan_state_manager.update_scan_state(self.scan_id, {
                        'is_validating': False
                    })
                self.logger.info(
                    f"扫描完成: 总数={self.stats['total']}, "
                    f"有效={self.stats['valid']}, "
                    f"疑似={self.stats['suspected']}, "
                    f"无效={self.stats['invalid']}"
                )

                invalid_urls = self.scan_state_manager.get_invalid_urls(self.scan_id)
                if invalid_urls:
                    from collections import Counter
                    error_types = [item.get('error_type', 'unknown') for item in invalid_urls]
                    error_counts = Counter(error_types)
                    top_errors = error_counts.most_common(5)
                    error_summary = ", ".join([f"{err}({cnt})" for err, cnt in top_errors])
                    self.logger.info(f"无效URL错误类型分布（前5）: {error_summary}")
                    if 'timeout' in error_counts:
                        self.logger.warning(f"[WARNING] 有 {error_counts['timeout']} 个URL因超时被标记为无效，考虑增加超时时间")
                    if 'mpv_create_failed' in error_counts:
                        self.logger.error(f"[ERROR] 有 {error_counts['mpv_create_failed']} 个mpv实例创建失败，可能是资源不足")

                try:
                    if self.main_window and hasattr(self.main_window, '_on_scan_completed'):
                        callback = self.main_window._on_scan_completed
                        self._run_on_main(callback)
                    else:
                        self.logger.warning("无法调用主窗口方法")
                except RuntimeError:
                    self.logger.debug("主窗口已销毁，跳过扫描完成回调")
                except Exception as e:
                    self.logger.error(f"调用主窗口方法失败: {e}")
        finally:
            # 等待所有工作线程完成，确保最终的统计信息被发送
            for worker in workers_snapshot:
                if worker.is_alive():
                    worker.join(timeout=1.0)

            # 发送最终的统计信息更新
            try:
                with self.stats_lock:
                    self.stats['elapsed'] = time.time() - self.stats['start_time']

                    if self.main_window and hasattr(self.main_window, '_update_stats_display'):
                        stats_copy = self.stats.copy()
                        is_validating = self.is_validating or was_validation
                        try:
                            self._run_on_main(
                                self.main_window._update_stats_display,
                                {'stats': stats_copy, 'is_validation': is_validating}
                            )
                        except RuntimeError:
                            pass
                    else:
                        try:
                            stats_copy = self.stats.copy()
                            is_validating_copy = self.is_validating or was_validation
                            self._run_on_main(self.stats_updated.emit, {
                                'stats': stats_copy, 'is_validation': is_validating_copy
                            })
                        except RuntimeError:
                            pass
            except Exception as e:
                self.logger.error(f"发送最终统计信息失败: {e}")

            # 本轮结束即丢弃网络上下文快照，下一轮重新读设置
            if generation is None or generation == self._round_generation:
                self._clear_network_context()
