
from core.log_manager import global_logger as logger
from ui.styles import AppStyles


class SettingsMixin:
    """从 IPTVPlayer 提取的设置/主题/语言/对话框职责"""

    def set_language(self, language: str):
        self.settings_ops.set_language(language)

    def set_theme(self, theme: str):
        self.settings_ops.set_theme(theme)

    def set_color_mode(self, mode: str):
        self.settings_ops.set_color_mode(mode)

    def set_visual_style(self, style: str):
        self.settings_ops.set_visual_style(style)

    def show_about(self):
        self.settings_ops.show_about()

    def open_log_directory(self):
        self.settings_ops.open_log_directory()

    def player_settings(self):
        self.settings_ops.player_settings()

    def _toggle_file_association(self):
        from ui.dialogs.file_association_dialog import FileAssociationDialog
        dialog = FileAssociationDialog(self)
        dialog.exec()

    def _reset_statusbar_style(self):
        self.status_bar.setStyleSheet(AppStyles.statusbar_style())

    def _cancel_source_timeout(self):
        timer = getattr(self, '_source_timeout_timer', None)
        if timer is None:
            return
        try:
            timer.stop()
        except RuntimeError:
            # C++ 对象已销毁（退出流程），清掉引用避免反复报错
            self._source_timeout_timer = None

    def _on_source_timeout(self, channel=None):
        """loadfile 超过网络超时仍未出流时的兜底：走与 END_FILE(ERROR) 相同的失败分支。"""
        pc = getattr(self, 'player_controller', None)
        if pc is None or getattr(pc, '_user_stopped', False):
            return
        # FILE_LOADED 后已正常出流（定时器可能尚未取消），不判定失败
        if getattr(pc, 'is_playing', False):
            return
        if getattr(self, 'play_state', None) is not None and self.play_state.is_catchup_or_timeshift:
            return
        url = getattr(pc, 'current_url', '') or ''
        if not url:
            return
        name = (channel or getattr(self, 'current_channel', None) or {}).get('name', '')
        u = url.lower()
        is_network = (u.startswith(('http://', 'https://', 'rtsp://', 'rtp://', 'udp://', 'rtmp://'))
                      or pc._is_network_drive(url))
        if not is_network:
            logger.warning(f"源超时（本地/网络盘文件，不重连）: {name} url={url}")
            return

        logger.warning(f"源超时：loadfile 后超过网络超时仍未出流，按失败重连: {name} url={url}")
        # 与 mpv END_FILE(ERROR) 的失败分支保持一致：先切到停止态，再按次数重连
        pc.is_playing = False
        pc.is_paused = False
        pc._safe_emit(pc.play_state_changed, False)
        if pc._reconnect_count < pc._max_reconnect:
            pc._reconnect_count += 1
            logger.info(f"断线自动重连 ({pc._reconnect_count}/{pc._max_reconnect})")
            pc._safe_emit(pc.reconnect_requested, url)
        else:
            logger.error("已达最大重连次数，停止重连")
            pc._reconnect_count = 0
            # 重连耗尽必须给出可见错误，否则界面只会显示成"已暂停"
            tr = getattr(getattr(self, 'language_manager', None), 'tr', None)
            message = (tr('reconnect_failed', '重连失败，请检查网络或更换频道')
                       if tr else '重连失败，请检查网络或更换频道')
            pc._safe_emit(pc.play_error, message)
