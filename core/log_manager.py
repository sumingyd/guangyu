import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from utils.singleton import Singleton
from utils.app_paths import get_log_dir, get_cache_dir


class LogManager(Singleton):

    def __init__(self, log_file: str = 'app.log', max_bytes: int = 5*1024*1024,
                 backup_count: int = 5, level: int = logging.INFO):
        if self._initialized:
            return

        self.primary_log_file = os.path.join(get_log_dir(), log_file)
        self.log_file = self.primary_log_file
        self.level = level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.init_errors: list[str] = []
        self._setup_logger()
        self._initialized = True

    def _candidate_log_paths(self, log_file: str) -> list[str]:
        """按优先级返回可尝试的日志路径：用户目录 -> 用户缓存目录 -> 系统临时目录。"""
        candidates = []
        for directory in (get_log_dir(), get_cache_dir(),
                          os.path.join(tempfile.gettempdir(), 'GuangYu', 'logs')):
            path = os.path.join(directory, log_file)
            if os.path.abspath(path) not in {os.path.abspath(p) for p in candidates}:
                candidates.append(path)
        return candidates

    def _setup_logger(self):
        self.logger = logging.getLogger('IPTVScanner')
        self.logger.setLevel(self.level)

        if self.logger.handlers:
            # 已有处理器（例如模块被重复导入）时沿用既有日志文件
            return

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        failures = []
        for path in self._candidate_log_paths(os.path.basename(self.primary_log_file)):
            try:
                log_dir = os.path.dirname(path)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                # 追加模式 + 轮转备份：崩溃后重启不会清掉上一次的现场
                file_handler = RotatingFileHandler(
                    path,
                    maxBytes=self.max_bytes,
                    backupCount=self.backup_count,
                    encoding='utf-8',
                    mode='a'
                )
                file_handler.setLevel(self.level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
                self.log_file = path
                if failures:
                    reason = '; '.join(failures)
                    self.init_errors.append(reason)
                    self.logger.warning(
                        f"日志初始化降级: 原路径不可用({self.primary_log_file})，"
                        f"已改用 {path}；原因: {reason}")
                return
            except Exception as e:
                failures.append(f"{path}: {type(e).__name__}: {e}")

        # 所有候选目录都失败：至少把原因写到临时文件与标准错误，绝不静默
        reason = '; '.join(failures) or '未知原因'
        self.init_errors.append(reason)
        self.logger.addHandler(logging.NullHandler())
        self._report_total_failure(reason)

    def _report_total_failure(self, reason: str):
        message = f"日志初始化完全失败，无法写入任何日志文件: {reason}"
        try:
            fallback = os.path.join(tempfile.gettempdir(), 'GuangYu_log_init_error.txt')
            with open(fallback, 'a', encoding='utf-8') as f:
                f.write(f"{message}\n")
        except OSError:
            pass
        stream = sys.stderr if sys.stderr is not None else getattr(sys, '__stderr__', None)
        if stream is not None:
            try:
                stream.write(message + '\n')
            except Exception:
                pass

    def debug(self, message: str):
        self.logger.debug(message)

    def info(self, message: str):
        self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str, exc_info: bool = False):
        if exc_info:
            self.logger.error(message, exc_info=True)
        else:
            self.logger.error(message)

    def critical(self, message: str):
        self.logger.critical(message)

    def set_level(self, level: int):
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    def get_logger(self) -> logging.Logger:
        return self.logger


global_logger = LogManager()


def get_logger(name: str = 'IPTVScanner') -> logging.Logger:
    return logging.getLogger(name)
