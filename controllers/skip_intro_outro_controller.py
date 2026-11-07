"""跳过片头片尾控制器

依据全局播放设置中的 auto_skip_intro / skip_intro_seconds / auto_skip_outro / skip_outro_seconds，
在本地视频文件加载后定时检查 time-pos：
  - 若仍在片头区间（time-pos < skip_intro_seconds）则 seek 到片头结束位置
  - 若进入片尾区间（duration - time-pos < skip_outro_seconds）则触发停止/下一个

仅在以下条件全部满足时生效：
  1. 配置启用相应开关
  2. 当前播放的是本地视频文件（duration > 0 且 url 不是直播流协议）
  3. duration 显著大于跳过秒数（避免误跳过短文件）

注意：与 ResumePlaybackController 互不干扰，本控制器只做 seek/stop，
不修改保存的播放位置；恢复播放时若位置已在片头后，则正常恢复。
"""
from PySide6.QtCore import QObject, QTimer

from core.log_manager import global_logger as logger
from utils.delay_constants import DelayMs


# 直播流协议前缀（这些协议不应用跳过片头片尾）
_LIVE_PROTOCOLS = ('rtmp://', 'rtsp://', 'rtp://', 'udp://', 'http://', 'https://')


def _is_local_file(url: str) -> bool:
    """判断 URL 是否为本地视频文件（非直播流）"""
    if not url:
        return False
    low = url.lower()
    if low.startswith('file://'):
        return True
    # Windows 绝对路径
    if len(low) >= 3 and low[1:3] == ':\\':
        return True
    # 不属于直播协议则视为本地文件（mms 等少见协议按直播处理）
    return not any(low.startswith(p) for p in _LIVE_PROTOCOLS)


class SkipIntroOutroController(QObject):
    """跳过片头片尾控制器"""

    _CHECK_INTERVAL_MS = 1000  # 每秒检查一次

    def __init__(self, main_window):
        super().__init__()
        self.window = main_window
        pc = main_window.player_controller
        if pc and hasattr(pc, 'file_loaded'):
            pc.file_loaded.connect(self._on_file_loaded)
        # 检查定时器
        self._timer = QTimer(self)
        self._timer.setInterval(self._CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        # 当前文件的目标 intro 结束位置（秒）；None 表示不跳过
        self._intro_end_sec = None
        # 当前文件的 outro 起始位置（秒）；None 表示不跳过
        self._outro_start_sec = None
        # 标记是否已为当前文件跳过片头（避免重复 seek）
        self._intro_skipped = False
        # 标记是否已为当前文件跳过片尾
        self._outro_skipped = False

    # ---------- 文件加载 ----------
    def _on_file_loaded(self):
        try:
            self._reset_state()
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                return
            url = pc.current_url or ''
            if not _is_local_file(url):
                return
            # 读取配置
            config = self.window.config
            if not config:
                return
            try:
                settings = config.load_playback_settings()
            except Exception:
                settings = {}
            intro_enabled = bool(settings.get('auto_skip_intro', False))
            intro_sec = float(settings.get('skip_intro_seconds', 0.0) or 0.0)
            outro_enabled = bool(settings.get('auto_skip_outro', False))
            outro_sec = float(settings.get('skip_outro_seconds', 0.0) or 0.0)
            # 必须 duration > 0 才有意义
            duration_ms = pc.get_total_time() if hasattr(pc, 'get_total_time') else 0
            duration_sec = duration_ms / 1000.0 if duration_ms else 0.0
            if duration_sec <= 0:
                # duration 还未就绪，延迟 1s 再试一次（最多5次）
                if not hasattr(self, '_duration_retry_count'):
                    self._duration_retry_count = 0
                self._duration_retry_count += 1
                if self._duration_retry_count <= 5:
                    QTimer.singleShot(DelayMs.MEDIA_INFO, self._on_file_loaded)
                else:
                    self._duration_retry_count = 0
                return
            self._duration_retry_count = 0
            # 跳过秒数必须小于 duration 的 80%（避免误判整片为片头/片尾）
            if intro_enabled and 0 < intro_sec < duration_sec * 0.8:
                self._intro_end_sec = intro_sec
            if outro_enabled and 0 < outro_sec < duration_sec * 0.8:
                self._outro_start_sec = max(0.0, duration_sec - outro_sec)
            if self._intro_end_sec is not None or self._outro_start_sec is not None:
                self._timer.start()
                logger.debug(f"启用跳过片头片尾: intro={self._intro_end_sec}s, outro={self._outro_start_sec}s, dur={duration_sec}s")
        except Exception as e:
            logger.debug(f"跳过片头片尾 file_loaded 失败: {e}")

    def _reset_state(self):
        self._intro_end_sec = None
        self._outro_start_sec = None
        self._intro_skipped = False
        self._outro_skipped = False

    # ---------- 定时检查 ----------
    def _tick(self):
        try:
            pc = self.window.player_controller
            if not pc or not pc.is_playing:
                self._timer.stop()
                return
            # 跳过片头
            if (self._intro_end_sec is not None and not self._intro_skipped):
                cur_ms = pc.get_current_time() if hasattr(pc, 'get_current_time') else 0
                cur_sec = cur_ms / 1000.0 if cur_ms else 0.0
                if 0 < cur_sec < self._intro_end_sec:
                    pc.seek_absolute(self._intro_end_sec)
                    self._intro_skipped = True
                    tr = self.window.language_manager.tr if hasattr(self.window, 'language_manager') else (lambda k, d='': d)
                    if hasattr(self.window, '_show_osd_feedback'):
                        self.window._show_osd_feedback(
                            tr('osd_skip_intro', '已跳过片头（{secs:.1f}s）').format(secs=self._intro_end_sec))
                    logger.info(f"跳过片头到 {self._intro_end_sec:.1f}s")
                elif cur_sec >= self._intro_end_sec:
                    # 已超过片头位置，标记为已跳过
                    self._intro_skipped = True
            # 跳过片尾
            if (self._outro_start_sec is not None and not self._outro_skipped):
                cur_ms = pc.get_current_time() if hasattr(pc, 'get_current_time') else 0
                cur_sec = cur_ms / 1000.0 if cur_ms else 0.0
                if cur_sec > 0 and cur_sec >= self._outro_start_sec:
                    self._outro_skipped = True
                    tr = self.window.language_manager.tr if hasattr(self.window, 'language_manager') else (lambda k, d='': d)
                    if hasattr(self.window, '_show_osd_feedback'):
                        self.window._show_osd_feedback(tr('osd_skip_outro', 'Skipped outro'))
                    # 停止播放（让队列机制决定下一个）
                    if hasattr(pc, 'stop'):
                        pc.stop()
                    logger.info(f"跳过片尾（当前 {cur_sec:.1f}s >= outro_start {self._outro_start_sec:.1f}s）")
        except Exception as e:
            logger.debug(f"跳过片头片尾检查失败: {e}")
