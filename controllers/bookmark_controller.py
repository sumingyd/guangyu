"""书签与章节控制器 - 管理用户书签和视频内置章节"""
from typing import Optional

from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer

from core.log_manager import global_logger as logger
from utils.thread_safety import safe_single_shot


class BookmarkController(QObject):
    """书签与章节控制器
    - 用户书签：在播放过程中标记位置，持久化到 JSON 文件
    - 章节：从 mpv 获取视频内置章节列表（只读）
    - 提供跳转/添加/删除等操作，并维护对话框实例
    """

    def __init__(self, main_window):
        super().__init__()
        self.window = main_window
        # 待恢复的书签位置（跨文件跳转时使用）
        self._pending_seek_url: Optional[str] = None
        self._pending_seek_position: float = 0.0

        pc = main_window.player_controller
        if pc and hasattr(pc, 'file_loaded'):
            pc.file_loaded.connect(self._on_file_loaded)

    # ---------- 辅助 ----------
    def _get_current_url(self) -> str:
        pc = self.window.player_controller
        if pc and pc.is_playing:
            return pc.current_url or ''
        return ''

    def _get_current_position(self) -> float:
        pc = self.window.player_controller
        if pc and pc.is_playing:
            try:
                t = pc.get_current_time() or 0
                # get_current_time 返回毫秒
                return float(t) / 1000.0
            except Exception:
                return 0.0
        return 0.0

    def _get_current_name(self) -> str:
        """获取当前频道/文件名（用于书签展示）"""
        try:
            cur = getattr(self.window, 'current_channel', None)
            if cur and isinstance(cur, dict):
                name = cur.get('name', '') or ''
                if name:
                    return name
                url = cur.get('url', '') or ''
                if url:
                    import os
                    return os.path.basename(url.replace('file://', '').split('?')[0]) or url
        except Exception as e:
            logger.debug(f"提取书签文件名失败: {e}")
        return ''

    @staticmethod
    def _format_time(seconds: float) -> str:
        try:
            from utils.general_utils import format_time
            return format_time(seconds)
        except Exception:
            return "0:00"

    # ---------- 用户书签 ----------
    def add_bookmark(self, name: str = '') -> bool:
        """在当前位置添加书签"""
        try:
            url = self._get_current_url()
            if not url:
                return False
            position = self._get_current_position()
            if position <= 0:
                return False
            ch_name = name or self._get_current_name()
            self.window.config.save_bookmark(url, position, ch_name)
            tr = self.window.language_manager.tr
            osd_text = f"{tr('osd_bookmark_added', 'Bookmark added')}: {self._format_time(position)}"
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(osd_text)
            logger.info(f"添加书签: {url[:60]} @ {position:.1f}s name={ch_name}")
            # 刷新对话框（若已打开）
            dlg = getattr(self.window, '_bookmark_dialog', None)
            if dlg and dlg.isVisible():
                dlg._reload_bookmarks()
            return True
        except Exception as e:
            logger.error(f"添加书签失败: {e}")
            return False

    def seek_to_bookmark(self, url: str, position: float):
        """跳转到指定 URL 的书签位置
        - 若 URL 是当前播放项，直接 seek
        - 否则尝试在本地频道列表中查找并播放，文件加载后自动 seek
        """
        try:
            pc = self.window.player_controller
            if not pc:
                return
            current_url = pc.current_url or ''
            if current_url == url:
                pc.seek_absolute(position)
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(
                        f"{tr('osd_bookmark_seek', 'Bookmark')}: {self._format_time(position)}")
                return
            # URL 不是当前项，尝试在本地列表中查找
            channel = self._find_channel_by_url(url)
            if not channel:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('osd_bookmark_not_in_list', 'File not in current channel list'))
                return
            # 设置待恢复位置，文件加载后由 _on_file_loaded 执行 seek
            self._pending_seek_url = url
            self._pending_seek_position = position
            # 通知断点续播控制器跳过下次自动恢复（避免恢复到上次位置覆盖书签位置）
            resume_ctrl = getattr(self.window, 'resume_ctrl', None)
            if resume_ctrl and hasattr(resume_ctrl, 'set_skip_next_resume'):
                resume_ctrl.set_skip_next_resume(url)

            def _play_channel_safe():
                try:
                    self.window.play_channel(channel)
                except RuntimeError:
                    pass

            safe_single_shot(100, self.window, _play_channel_safe)
        except Exception as e:
            logger.error(f"跳转书签失败: {e}")

    def _on_file_loaded(self):
        """文件加载完成时检查是否有待处理的书签 seek"""
        try:
            if not self._pending_seek_url or self._pending_seek_position <= 0:
                return
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            current_url = pc.current_url or ''
            if current_url != self._pending_seek_url:
                return
            url = self._pending_seek_url
            position = self._pending_seek_position
            self._pending_seek_url = None
            self._pending_seek_position = 0.0
            # 延迟 seek（等 mpv 真正开始播放）

            def _seek_safe():
                try:
                    self._do_pending_seek(url, position)
                except RuntimeError:
                    pass

            safe_single_shot(400, self.window, _seek_safe)
        except Exception as e:
            logger.debug(f"书签恢复检查失败: {e}")
            self._pending_seek_url = None
            self._pending_seek_position = 0.0

    def _do_pending_seek(self, url: str, position: float):
        """执行待处理的书签 seek"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            if pc.current_url != url:
                return
            pc.seek_absolute(position)
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(
                    f"{tr('osd_bookmark_seek', 'Bookmark')}: {self._format_time(position)}")
        except Exception as e:
            logger.debug(f"执行书签 seek 失败: {e}")

    def _find_channel_by_url(self, url: str) -> Optional[dict]:
        channels = getattr(self.window, '_local_channels', None)
        if channels and isinstance(channels, list):
            for ch in channels:
                if isinstance(ch, dict) and ch.get('url') == url:
                    return ch
        return None

    def delete_bookmark(self, url: str, position: float) -> bool:
        """删除指定书签"""
        try:
            ok = self.window.config.delete_bookmark(url, position)
            if ok:
                dlg = getattr(self.window, '_bookmark_dialog', None)
                if dlg and dlg.isVisible():
                    dlg._reload_bookmarks()
            return ok
        except Exception as e:
            logger.debug(f"删除书签失败: {e}")
            return False

    def clear_bookmarks(self, url: str):
        """清除指定 URL 的所有书签"""
        try:
            self.window.config.clear_bookmarks(url)
            dlg = getattr(self.window, '_bookmark_dialog', None)
            if dlg and dlg.isVisible():
                dlg._reload_bookmarks()
        except Exception as e:
            logger.debug(f"清除书签失败: {e}")

    def clear_all_bookmarks(self):
        """清除所有书签"""
        try:
            self.window.config.clear_all_bookmarks()
            dlg = getattr(self.window, '_bookmark_dialog', None)
            if dlg and dlg.isVisible():
                dlg._reload_bookmarks()
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('osd_bookmarks_cleared', 'All bookmarks cleared'))
        except Exception as e:
            logger.debug(f"清除所有书签失败: {e}")

    def load_bookmarks(self, url: str = '') -> list:
        """加载书签列表（默认当前 URL）"""
        try:
            if not url:
                url = self._get_current_url()
            if not url:
                return []
            return self.window.config.load_bookmarks(url)
        except Exception as e:
            logger.debug(f"加载书签失败: {e}")
            return []

    def load_all_bookmarks(self) -> list:
        """加载所有书签"""
        try:
            return self.window.config.load_all_bookmarks()
        except Exception as e:
            logger.debug(f"加载所有书签失败: {e}")
            return []

    # ---------- 章节 ----------
    def get_chapters(self) -> list:
        """获取当前视频的章节列表"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'get_chapter_list'):
                return []
            return pc.get_chapter_list()
        except Exception as e:
            logger.debug(f"获取章节失败: {e}")
            return []

    def get_current_chapter(self) -> int:
        """获取当前章节索引（无章节返回 -1）"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'get_current_chapter'):
                return -1
            return pc.get_current_chapter()
        except Exception:
            return -1

    def seek_to_chapter(self, idx: int) -> bool:
        """跳转到指定章节"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'set_chapter'):
                return False
            ok = pc.set_chapter(idx)
            if ok:
                tr = self.window.language_manager.tr
                chapters = self.get_chapters()
                if 0 <= idx < len(chapters):
                    title = chapters[idx].get('title', '') or ''
                    label = title if title else f"#{idx + 1}"
                else:
                    label = f"#{idx + 1}"
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(
                        f"{tr('osd_chapter_seek', 'Chapter')}: {label}")
            return ok
        except Exception as e:
            logger.debug(f"跳转章节失败: {e}")
            return False

    def next_chapter(self) -> bool:
        """跳转到下一章"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'chapter_next'):
                return False
            ok = pc.chapter_next()
            if ok:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('osd_chapter_next', 'Next Chapter'))
            return ok
        except Exception as e:
            logger.debug(f"下一章失败: {e}")
            return False

    def prev_chapter(self) -> bool:
        """跳转到上一章"""
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing or not hasattr(pc, 'chapter_prev'):
                return False
            ok = pc.chapter_prev()
            if ok:
                tr = self.window.language_manager.tr
                if hasattr(self.window, '_show_osd_feedback'):
                    self.window._show_osd_feedback(tr('osd_chapter_prev', 'Previous Chapter'))
            return ok
        except Exception as e:
            logger.debug(f"上一章失败: {e}")
            return False

    # ---------- 对话框 ----------
    def show_bookmark_dialog(self):
        """打开书签/章节对话框"""
        try:
            from ui.dialogs.bookmark_dialog import BookmarkDialog
            if not hasattr(self.window, '_bookmark_dialog') or not self.window._bookmark_dialog:
                self.window._bookmark_dialog = BookmarkDialog(self.window)
            self.window._bookmark_dialog.show()
            self.window._bookmark_dialog.raise_()
            self.window._bookmark_dialog.activateWindow()
        except Exception as e:
            logger.error(f"打开书签对话框失败: {e}")
