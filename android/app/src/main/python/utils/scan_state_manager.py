"""
扫描状态管理器
提供统一的扫描状态管理，消除重复的扫描状态跟踪逻辑
"""

from typing import Dict, Any, List, Optional
from core.log_manager import global_logger
from utils.singleton import Singleton
import threading
import time

logger = global_logger


class ScanStateManager(Singleton):

    def __init__(self):
        if self._initialized:
            return

        self._lock = threading.Lock()
        self._scan_states: Dict[str, Dict[str, Any]] = {}
        self._retry_states: Dict[str, Dict[str, Any]] = {}
        self._initialized = True
        logger.info("扫描状态管理器已初始化")

    def register_scan(self, scan_id: str, scanner=None):
        """注册扫描任务

        Args:
            scan_id: 扫描ID，可以是'scan'、'validation'、'retry_scan'等
            scanner: 扫描器对象（可选）
        """
        with self._lock:
            if scan_id not in self._scan_states:
                self._scan_states[scan_id] = {
                    'is_scanning': False,
                    'is_validating': False,
                    'stats': {
                        'total': 0,
                        'valid': 0,
                        'invalid': 0,
                        'start_time': 0,
                        'elapsed': 0
                    },
                    'invalid_urls': [],
                    '_url_set': set(),
                    'scanner': scanner,
                    'last_update': time.time()
                }

    def unregister_scan(self, scan_id: str):
        """注销扫描任务"""
        with self._lock:
            if scan_id in self._scan_states:
                del self._scan_states[scan_id]

    def update_scan_state(self, scan_id: str, state: Dict[str, Any]):
        """更新扫描状态"""
        with self._lock:
            if scan_id in self._scan_states:
                self._scan_states[scan_id].update(state)
                self._scan_states[scan_id]['last_update'] = time.time()
                if 'invalid_urls' in state:
                    self._scan_states[scan_id]['_url_set'] = set(
                        entry['url'] for entry in state['invalid_urls'] if isinstance(entry, dict)
                    )

    def get_scan_state(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """获取扫描状态"""
        with self._lock:
            return self._scan_states.get(scan_id)

    def is_scanning(self, scan_id: str = 'scan') -> bool:
        """检查是否正在扫描"""
        with self._lock:
            if scan_id in self._scan_states:
                return self._scan_states[scan_id].get('is_scanning', False)
            return False

    def is_validating(self, scan_id: str = 'validation') -> bool:
        """检查是否正在验证"""
        with self._lock:
            if scan_id in self._scan_states:
                return self._scan_states[scan_id].get('is_validating', False)
            return False

    def update_stats(self, scan_id: str, stats: Dict[str, Any]):
        """更新统计信息"""
        with self._lock:
            if scan_id in self._scan_states:
                self._scan_states[scan_id]['stats'].update(stats)
                self._scan_states[scan_id]['last_update'] = time.time()

    def get_stats(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """获取统计信息"""
        with self._lock:
            if scan_id in self._scan_states:
                return self._scan_states[scan_id].get('stats')
            return None

    def add_invalid_url(self, scan_id: str, url: str, error_type: str | None = None):
        """添加无效URL - 始终使用集合去重，O(1)查找"""
        with self._lock:
            if scan_id in self._scan_states:
                state = self._scan_states[scan_id]
                invalid_urls = state['invalid_urls']
                url_set = state.get('_url_set', set())

                if url not in url_set:
                    url_set.add(url)
                    state['_url_set'] = url_set
                    invalid_urls.append({
                        'url': url,
                        'error_type': error_type
                    })

    def get_invalid_urls(self, scan_id: str) -> List[dict]:
        with self._lock:
            if scan_id in self._scan_states:
                return list(self._scan_states[scan_id].get('invalid_urls', []))
            return []

    def get_retry_urls(self, scan_id: str) -> List[str]:
        """获取需要重试的URL列表（基于失败原因）"""
        with self._lock:
            if scan_id not in self._scan_states:
                return []

            invalid_urls = self._scan_states[scan_id].get('invalid_urls', [])
            retry_urls = []

            for entry in invalid_urls:
                error_type = entry.get('error_type')
                url = entry.get('url')

                # 基于失败原因判断是否需要重试
                if self._should_retry_url(error_type):
                    retry_urls.append(url)

            return retry_urls

    def _should_retry_url(self, error_type: str) -> bool:
        if not error_type:
            return True

        retry_error_types = {
            'timeout',
            'playback_warning',
            'concurrency_limit',
            'mpv_create_failed',
            'stream_ended',
            'scan_exception',
            # 能连上但没解析出流 / 探测失败：换一轮更可能拿到结果
            'no_streams',
            'probe_failed',
            'unknown_error',
        }

        if error_type in retry_error_types:
            return True

        return False

    def clear_invalid_urls(self, scan_id: str):
        """清空无效URL列表"""
        with self._lock:
            if scan_id in self._scan_states:
                self._scan_states[scan_id]['invalid_urls'] = []
                self._scan_states[scan_id]['_url_set'] = set()

    # 重试扫描状态管理
    def register_retry_scan(self, retry_id: str, main_window=None):
        """注册重试扫描任务"""
        with self._lock:
            if retry_id not in self._retry_states:
                self._retry_states[retry_id] = {
                    'is_retry_scan': False,
                    'failed_channels': [],
                    'retry_count': 0,
                    'last_retry_valid_count': 0,
                    'main_window': main_window,
                    'last_update': time.time(),
                    'retried_urls': set()  # 新增：记录已经重试过的 URL
                }

    def update_retry_state(self, retry_id: str, state: Dict[str, Any]):
        """更新重试扫描状态"""
        with self._lock:
            if retry_id in self._retry_states:
                self._retry_states[retry_id].update(state)
                self._retry_states[retry_id]['last_update'] = time.time()

    def get_retry_state(self, retry_id: str) -> Optional[Dict[str, Any]]:
        """获取重试扫描状态"""
        with self._lock:
            return self._retry_states.get(retry_id)

    def is_retry_scan(self, retry_id: str = 'retry') -> bool:
        """检查是否正在重试扫描"""
        with self._lock:
            if retry_id in self._retry_states:
                return self._retry_states[retry_id].get('is_retry_scan', False)
            return False

    def add_failed_channel(self, retry_id: str, url: str):
        """添加失败频道 - 始终使用集合去重，O(1)查找"""
        with self._lock:
            if retry_id in self._retry_states:
                state = self._retry_states[retry_id]
                failed_channels = state['failed_channels']

                if '_failed_url_set' not in state:
                    state['_failed_url_set'] = set(failed_channels)

                url_set = state['_failed_url_set']

                if url not in url_set:
                    url_set.add(url)
                    failed_channels.append(url)

    def get_failed_channels(self, retry_id: str) -> List[str]:
        with self._lock:
            if retry_id in self._retry_states:
                return list(self._retry_states[retry_id].get('failed_channels', []))
            return []

    def clear_failed_channels(self, retry_id: str):
        with self._lock:
            if retry_id in self._retry_states:
                self._retry_states[retry_id]['failed_channels'] = []
                self._retry_states[retry_id].pop('_failed_url_set', None)

    def increment_retry_count(self, retry_id: str) -> int:
        """增加重试计数并返回新值"""
        with self._lock:
            if retry_id in self._retry_states:
                self._retry_states[retry_id]['retry_count'] += 1
                count = self._retry_states[retry_id]['retry_count']
                return count
            return 0

    def reset_retry_count(self, retry_id: str):
        """重置重试计数"""
        with self._lock:
            if retry_id in self._retry_states:
                self._retry_states[retry_id]['retry_count'] = 0

    def get_retry_count(self, retry_id: str) -> int:
        """获取重试计数"""
        with self._lock:
            if retry_id in self._retry_states:
                return self._retry_states[retry_id].get('retry_count', 0)
            return 0

    def update_last_retry_valid_count(self, retry_id: str, count: int):
        """更新上一次重试的有效频道数"""
        with self._lock:
            if retry_id in self._retry_states:
                self._retry_states[retry_id]['last_retry_valid_count'] = count

    def get_last_retry_valid_count(self, retry_id: str) -> int:
        """获取上一次重试的有效频道数"""
        with self._lock:
            if retry_id in self._retry_states:
                return self._retry_states[retry_id].get('last_retry_valid_count', 0)
            return 0

    def add_retried_url(self, retry_id: str, url: str):
        """添加已重试的 URL"""
        with self._lock:
            if retry_id in self._retry_states:
                retried_urls = self._retry_states[retry_id].get('retried_urls', set())
                retried_urls.add(url)

    def is_url_retried(self, retry_id: str, url: str) -> bool:
        """检查 URL 是否已经被重试过"""
        with self._lock:
            if retry_id in self._retry_states:
                retried_urls = self._retry_states[retry_id].get('retried_urls', set())
                return url in retried_urls
            return False

    def get_retried_urls(self, retry_id: str) -> set:
        with self._lock:
            if retry_id in self._retry_states:
                return set(self._retry_states[retry_id].get('retried_urls', set()))
            return set()

    def clear_all_states(self):
        """清除所有状态"""
        with self._lock:
            self._scan_states.clear()
            self._retry_states.clear()
            logger.info("已清除所有扫描状态")


def get_scan_state_manager() -> ScanStateManager:
    """获取全局扫描状态管理器"""
    return ScanStateManager()


def register_retry_task(retry_id: str, main_window=None):
    """注册重试扫描任务（便捷函数）"""
    manager = get_scan_state_manager()
    manager.register_retry_scan(retry_id, main_window)


# 扫描状态上下文管理器
class ScanStateContext:
    """扫描状态上下文管理器"""

    def __init__(self, scan_id: str, scanner=None):
        self.scan_id = scan_id
        self.scanner = scanner

    def __enter__(self):
        """进入上下文时注册扫描任务"""
        get_scan_state_manager().register_scan(self.scan_id, self.scanner)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时不立即注销扫描任务，让重试功能能够获取无效URL"""
        return False


# 重试扫描状态上下文管理器
class RetryScanStateContext:
    """重试扫描状态上下文管理器"""

    def __init__(self, retry_id: str, main_window=None):
        self.retry_id = retry_id
        self.main_window = main_window

    def __enter__(self):
        """进入上下文时注册重试扫描任务"""
        register_retry_task(self.retry_id, self.main_window)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时重置重试状态"""
        return False
