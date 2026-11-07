"""断点续播控制器 - 保存/恢复播放位置"""
from typing import Optional

from PySide6.QtCore import QObject, QTimer

from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


class ResumePlaybackController(QObject):
    """断点续播控制器
    - 监听 local_file_position_to_save 信号，保存位置到 config
    - 监听 file_loaded 信号，自动恢复到上次播放位置（通过 OSD 反馈）
    - 提供 set_skip_next_resume() 用于跳过下次自动恢复（队列切换时）
    - 提供 show_resume_list_dialog() 查看所有断点
    """

    # 自动恢复的最小位置（秒），小于此值不恢复
    _RESUME_MIN_RESTORE_SEC = 5.0

    def __init__(self, main_window):
        super().__init__()
        self.window = main_window
        # 跳过下次自动恢复的 URL（队列自动切换时设置）
        self._skip_next_url: Optional[str] = None
        # 当前是否已为某 URL 恢复过（避免重复恢复）
        self._restored_url: Optional[str] = None

        pc = main_window.player_controller
        if pc:
            if hasattr(pc, 'local_file_position_to_save'):
                pc.local_file_position_to_save.connect(self._on_position_to_save)
            if hasattr(pc, 'file_loaded'):
                pc.file_loaded.connect(self._on_file_loaded)
            if hasattr(pc, 'play_state_changed'):
                pc.play_state_changed.connect(self._on_play_state_changed)

    def _on_play_state_changed(self, playing: bool):
        """播放会话结束时清空已恢复标记。

        暂停也会通过该信号发 False，需要按 is_paused 排除；否则同一次播放中
        暂停后恢复会被误判为新会话。此前该标记从不清空，导致停止后重新打开
        同一个文件再也不会自动恢复断点。
        """
        if playing:
            return
        try:
            pc = self.window.player_controller
            if pc and getattr(pc, 'is_paused', False):
                return
        except Exception:
            pass
        self._restored_url = None

    # ---------- 保存位置 ----------
    def _on_position_to_save(self, url: str, position: float, duration: float):
        """接收 mpv 发来的播放位置，保存到 config"""
        try:
            if not url or position <= 0:
                return
            # 获取文件名
            name = self._get_channel_name_for_url(url)
            self.window.config.save_resume_position(url, position, duration, name)
            logger.debug(f"保存断点: {url[:60]} pos={position:.1f}s dur={duration:.1f}s name={name}")
        except Exception as e:
            logger.debug(f"保存断点失败: {e}")

    def _get_channel_name_for_url(self, url: str) -> str:
        """根据 URL 获取频道/文件名"""
        try:
            cur = getattr(self.window, 'current_channel', None)
            if cur and isinstance(cur, dict) and cur.get('url') == url:
                return cur.get('name', '') or ''
            channels = getattr(self.window, '_local_channels', None)
            if channels and isinstance(channels, list):
                for ch in channels:
                    if isinstance(ch, dict) and ch.get('url') == url:
                        return ch.get('name', '') or ''
        except Exception as e:
            logger.debug(f"获取频道名失败: {e}")
        # 回退到文件名
        try:
            import os
            return os.path.basename(url.replace('file://', '').split('?')[0])
        except Exception:
            return ''

    # ---------- 自动恢复 ----------
    def _on_file_loaded(self):
        """文件加载时检查断点"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            url = pc.current_url or ''
            if not url:
                return
            # 切换到其它文件后，上一次的恢复标记不再适用于新 URL
            if self._restored_url and self._restored_url != url:
                self._restored_url = None
            # 跳过队列自动切换
            if self._skip_next_url and self._skip_next_url == url:
                logger.debug(f"跳过自动恢复（队列切换）: {url[:60]}")
                self._skip_next_url = None
                return
            # 避免重复恢复
            if self._restored_url == url:
                return
            entry = self.window.config.load_resume_position(url)
            if not entry:
                return
            position = float(entry.get('position', 0) or 0)
            duration = float(entry.get('duration', 0) or 0)
            if position < self._RESUME_MIN_RESTORE_SEC:
                return
            # 如果时长已知且位置距结尾太近，不恢复
            if duration and duration > 0 and position + 3.0 >= duration:
                return
            # 延迟 seek（等 mpv 真正开始播放）
            def _safe_seek():
                try:
                    self._do_seek(url, position)
                except RuntimeError:
                    pass
            QTimer.singleShot(DelayMs.RESUME_SEEK, _safe_seek)
        except Exception as e:
            logger.debug(f"自动恢复检查失败: {e}")

    def _do_seek(self, url: str, position: float):
        """执行 seek 并通过 OSD 反馈"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            if pc.current_url != url:
                return
            pc.seek_absolute(position)
            self._restored_url = url
            tr = self.window.language_manager.tr
            osd_text = f"{tr('osd_resume_restored', 'Resumed')}: {self._format_time(position)}"
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(osd_text)
            logger.info(f"已恢复播放位置: {url[:60]} -> {position:.1f}s")
        except Exception as e:
            logger.debug(f"恢复位置失败: {e}")

    def set_skip_next_resume(self, url: str):
        """设置下次加载该 URL 时跳过自动恢复（队列切换时调用）"""
        self._skip_next_url = url

    # ---------- 手动操作 ----------
    def show_resume_list_dialog(self):
        """打开断点列表对话框"""
        try:
            from ui.dialogs.resume_position_dialog import ResumeListDialog
            if not hasattr(self.window, '_resume_list_dialog') or not self.window._resume_list_dialog:
                self.window._resume_list_dialog = ResumeListDialog(self.window)
            self.window._resume_list_dialog.show()
            self.window._resume_list_dialog.raise_()
            self.window._resume_list_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开断点列表对话框失败: {e}")

    def clear_all_resume_positions(self):
        """清除所有断点"""
        try:
            self.window.config.clear_all_resume_positions()
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('osd_resume_cleared', 'Resume positions cleared'))
            # 如果列表对话框已打开，刷新它
            dlg = getattr(self.window, '_resume_list_dialog', None)
            if dlg and dlg.isVisible():
                dlg._reload_list()
        except Exception as e:
            logger.debug(f"清除断点失败: {e}")

    def resume_specific(self, url: str):
        """从断点列表中恢复指定 URL"""
        try:
            entry = self.window.config.load_resume_position(url)
            if not entry:
                return
            position = float(entry.get('position', 0) or 0)
            name = entry.get('name', '') or ''
            # 设置待恢复标志（避免 play_channel 后立即恢复冲突）
            self._restored_url = None
            # 尝试播放该 URL
            channel = self._find_channel_by_url(url, name)
            if channel:
                # 标记下次加载时恢复
                self._skip_next_url = None
                # 由于 play_channel 是异步的，延迟清除 restored_url
                QTimer.singleShot(DelayMs.LAYOUT_SETTLE, lambda: self.window.play_channel(channel))
                # 在文件加载后由 _on_file_loaded 处理恢复
            else:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('osd_resume_not_in_list', 'File not in current channel list'))
        except Exception as e:
            logger.debug(f"恢复指定断点失败: {e}")

    def _find_channel_by_url(self, url: str, name: str = '') -> Optional[dict]:
        """在 _local_channels 中查找指定 URL 的频道"""
        channels = getattr(self.window, '_local_channels', None)
        if channels and isinstance(channels, list):
            for ch in channels:
                if isinstance(ch, dict) and ch.get('url') == url:
                    return ch
        return None

    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化时间为 HH:MM:SS"""
        try:
            from utils.general_utils import format_time
            return format_time(seconds)
        except Exception:
            return f"{seconds:.1f}s"
