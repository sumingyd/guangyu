"""本地播放列表域存储 — 上次打开的 m3u 与页签记忆（config.ini）。

只记绝对路径和元信息，不保存文件内容：启动自动打开时按路径重新读取，
文件被移动或删除也能明确发现并回退。
"""

import os
import time

from core.log_manager import global_logger as logger


class LocalPlaylistStore:
    """本地播放列表状态存储，落盘在 [LocalPlaylist] 段。"""

    _SECTION = 'LocalPlaylist'
    # 连续 3 次启动都找不到文件后清掉记录，避免每次启动都提示
    _MAX_MISS = 3

    def __init__(self, facade):
        self._facade = facade

    def save_last_playlist(self, file_path: str, channel_count: int = 0):
        if not file_path or str(file_path).lower().startswith(('http://', 'https://')):
            # 只记本地文件；网络列表由订阅源/最近打开各自维护
            return
        path = os.path.abspath(file_path)
        mtime = 0
        size = 0
        try:
            stat = os.stat(path)
            mtime = int(stat.st_mtime)
            size = int(stat.st_size)
        except OSError:
            pass
        self._facade.set_value(self._SECTION, 'last_file', path)
        self._facade.set_value(self._SECTION, 'last_file_mtime', str(mtime))
        self._facade.set_value(self._SECTION, 'last_file_size', str(size))
        self._facade.set_value(self._SECTION, 'last_channel_count', str(int(channel_count or 0)))
        self._facade.set_value(self._SECTION, 'last_open_at', str(int(time.time())))
        self._facade.set_value(self._SECTION, 'miss_count', '0')
        self._facade.save_config()

    def load_last_playlist(self) -> dict:
        f = self._facade
        return {
            'last_file': f.get_value(self._SECTION, 'last_file', '') or '',
            'last_file_mtime': f._parse_int(f.get_value(self._SECTION, 'last_file_mtime', '0'), 0),
            'last_file_size': f._parse_int(f.get_value(self._SECTION, 'last_file_size', '0'), 0),
            'last_channel_count': f._parse_int(f.get_value(self._SECTION, 'last_channel_count', '0'), 0),
            'last_open_at': f._parse_int(f.get_value(self._SECTION, 'last_open_at', '0'), 0),
            'miss_count': f._parse_int(f.get_value(self._SECTION, 'miss_count', '0'), 0),
        }

    def record_miss(self) -> dict:
        """记录一次「文件不存在」。

        返回 {'miss_count': n, 'cleared': bool}；连续缺失达到上限时清掉路径。
        """
        f = self._facade
        miss = f._parse_int(f.get_value(self._SECTION, 'miss_count', '0'), 0) + 1
        cleared = False
        if miss >= self._MAX_MISS:
            self._clear_file_fields()
            miss = 0
            cleared = True
        else:
            f.set_value(self._SECTION, 'miss_count', str(miss))
            f.save_config()
        return {'miss_count': miss, 'cleared': cleared}

    def clear_last_playlist(self):
        self._clear_file_fields()
        self._facade.save_config()

    def _clear_file_fields(self):
        f = self._facade
        for key in ('last_file', 'last_file_mtime', 'last_file_size',
                    'last_channel_count', 'last_open_at'):
            f.set_value(self._SECTION, key, '')
        f.set_value(self._SECTION, 'miss_count', '0')

    def save_last_active_tab(self, index: int):
        try:
            self._facade.set_value(self._SECTION, 'last_active_tab', str(int(index)))
            self._facade.save_config()
        except Exception as e:
            logger.debug(f"保存上次页签失败: {e}")

    def load_last_active_tab(self) -> int:
        try:
            return self._facade._parse_int(
                self._facade.get_value(self._SECTION, 'last_active_tab', '0'), 0)
        except Exception:
            return 0
