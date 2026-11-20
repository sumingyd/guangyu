"""智能场景检测与自适应参数服务 — 第三阶段高级功能

根据视频流实时参数（分辨率、帧率、编码、码率）自动判断内容类型，
并动态调整运动补偿、缩放算法、细节增强和着色器预设。

内容类型识别策略：
  - 动画：低帧率(24/25fps) + H.264/HEVC + 中低码率 → Anime4K 着色器 + 轻度 MC
  - 体育：高帧率(50/60fps) + H.264 + 高码率 → 强力 MC + Lanczos
  - 电影：低帧率(24/25fps) + 高码率 + 10bit → 中度 MC + EWA Lanczos Sharp
  - 新闻：中帧率 + 中码率 → 轻度 MC + 双线性
  - 4K 高清：4K 分辨率 → 关闭 MC（防卡顿）+ 高质量缩放

检测方式：
  - 主动模式：通过 MPV 属性读取 video-params / fps / width / height / pix-format
  - 被动模式：监听 file-loaded 事件后一次性检测，定时刷新
"""
import threading
from core.log_manager import global_logger as logger


class SceneDetectService:
    """智能场景检测与自适应参数调整"""

    # 内容类型枚举
    TYPE_ANIME = 'anime'
    TYPE_SPORTS = 'sports'
    TYPE_MOVIE = 'movie'
    TYPE_NEWS = 'news'
    TYPE_4K = '4k_hdr'
    TYPE_UNKNOWN = 'unknown'

    # 各类型对应的推荐参数
    PRESETS = {
        TYPE_ANIME: {
            'motion_comp': 'low',
            'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczos',
            'superres_detail': 20,
            'shader_preset': 'anime4k',
        },
        TYPE_SPORTS: {
            'motion_comp': 'high',
            'motion_comp_fps': 60,
            'superres_scale': 'lanczos',
            'superres_detail': 30,
            'shader_preset': 'off',
        },
        TYPE_MOVIE: {
            'motion_comp': 'medium',
            'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczossharp',
            'superres_detail': 40,
            'shader_preset': 'off',
        },
        TYPE_NEWS: {
            'motion_comp': 'low',
            'motion_comp_fps': 60,
            'superres_scale': 'off',
            'superres_detail': 0,
            'shader_preset': 'off',
        },
        TYPE_4K: {
            'motion_comp': 'off',
            'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczossharp',
            'superres_detail': 10,
            'shader_preset': 'off',
        },
        TYPE_UNKNOWN: {
            'motion_comp': 'off',
            'motion_comp_fps': 60,
            'superres_scale': 'off',
            'superres_detail': 0,
            'shader_preset': 'off',
        },
    }

    def __init__(self):
        self._enabled = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._last_scene_type = None
        self._last_params = {}
        self._callback = None
        self._interval = 5.0  # 检测间隔（秒）
        self._lock = threading.Lock()
        self._player_controller = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_scene_type(self) -> str:
        return self._last_scene_type or self.TYPE_UNKNOWN

    @property
    def last_params(self) -> dict:
        return self._last_params.copy()

    def set_callback(self, callback):
        """设置参数变更回调

        :param callback: 回调函数，签名 callback(params: dict, scene_type: str)
        """
        self._callback = callback

    def start(self, player_controller, callback=None):
        """启动场景检测

        :param player_controller: 播放器控制器，需提供 get_property 方法
        :param callback: 参数变更回调
        """
        if self._enabled:
            logger.debug("场景检测已在运行")
            return
        if callback:
            self._callback = callback
        self._enabled = True
        self._stop_event.clear()
        self._player_controller = player_controller
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name='SceneDetect'
        )
        self._monitor_thread.start()
        logger.info("智能场景检测已启动")

    def stop(self):
        """停止场景检测"""
        if not self._enabled:
            return
        self._enabled = False
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self._monitor_thread = None
        logger.info("智能场景检测已停止")

    def detect_once(self, player_controller) -> tuple:
        """执行一次场景检测

        :param player_controller: 播放器控制器
        :return: (scene_type: str, params: dict)
        """
        try:
            props = self._collect_video_params(player_controller)
            scene_type = self._classify_scene(props)
            params = self.PRESETS.get(scene_type, self.PRESETS[self.TYPE_UNKNOWN]).copy()
            params['scene_type'] = scene_type
            params['scene_label'] = self._get_scene_label(scene_type)
            return scene_type, params
        except Exception as e:
            logger.debug(f"场景检测失败: {e}")
            return self.TYPE_UNKNOWN, self.PRESETS[self.TYPE_UNKNOWN].copy()

    def _monitor_loop(self):
        """后台监控循环"""
        while not self._stop_event.is_set():
            try:
                if self._player_controller and self._player_controller.is_playing:
                    scene_type, params = self.detect_once(self._player_controller)
                    with self._lock:
                        changed = (
                            scene_type != self._last_scene_type
                            or params != self._last_params
                        )
                        if changed:
                            self._last_scene_type = scene_type
                            self._last_params = params
                            logger.info(
                                f"场景变更: type={scene_type}, "
                                f"mc={params.get('motion_comp')}, "
                                f"sr={params.get('superres_scale')}"
                            )
                            if self._callback:
                                try:
                                    self._callback(params, scene_type)
                                except Exception as e:
                                    logger.debug(f"场景检测回调失败: {e}")
            except Exception as e:
                logger.debug(f"场景监控异常: {e}")
            self._stop_event.wait(self._interval)

    def _collect_video_params(self, pc) -> dict:
        """从播放器收集视频参数"""
        props = {}
        try:
            props['width'] = pc.get_property('width') or 0
            props['height'] = pc.get_property('height') or 0
            props['fps'] = float(pc.get_property('container-fps') or 0)
            props['video_format'] = pc.get_property('video-format') or ''
            props['pix_format'] = pc.get_property('video-params/pixelformat') or ''
            props['primaries'] = pc.get_property('video-params/primaries') or ''
            props['gamma'] = pc.get_property('video-params/gamma') or ''
            props['hwdec'] = pc.get_property('hwdec') or ''
            props['av_bitrate'] = int(pc.get_property('video-bitrate') or 0)
        except Exception as e:
            logger.debug(f"收集视频参数失败: {e}")
        return props

    def _classify_scene(self, props: dict) -> str:
        """根据视频参数分类内容类型

        判断逻辑：
        1. 4K/HDR → 4K 高清类型，关闭 MC 防卡顿
        2. 低帧率(<=30) + 高码率 → 电影
        3. 高帧率(>=50) → 体育
        4. 低帧率 + 低码率 + 特定编码 → 动画
        5. 其他 → 新闻/未知
        """
        w = props.get('width', 0)
        h = props.get('height', 0)
        fps = props.get('fps', 0)
        vfmt = (props.get('video_format') or '').lower()
        pix = (props.get('pix_format') or '').lower()
        primaries = (props.get('primaries') or '').lower()
        gamma = (props.get('gamma') or '').lower()
        bitrate = props.get('av_bitrate', 0)

        is_4k = w >= 3840 or h >= 2160
        is_hdr = (
            'bt2020' in primaries
            or 'pq' in gamma
            or 'hlg' in gamma
            or '10' in pix
        )

        # 4K HDR 内容：关闭 MC 防卡顿
        if is_4k and is_hdr:
            return self.TYPE_4K
        if is_4k:
            return self.TYPE_4K

        # 高帧率 → 体育（50/60fps 通常为体育/直播）
        if fps >= 49:
            return self.TYPE_SPORTS

        # 低帧率 + 高码率 → 电影
        if fps <= 30 and bitrate > 4000000:
            # 10bit 高码率 → 高质量电影
            if '10' in pix or 'bt2020' in primaries:
                return self.TYPE_MOVIE
            # H.265/HEVC 高码率 → 电影
            if 'hevc' in vfmt or 'h265' in vfmt:
                return self.TYPE_MOVIE
            return self.TYPE_MOVIE

        # 低帧率 + 低码率 → 动画
        if fps <= 30 and bitrate > 0 and bitrate < 3000000:
            return self.TYPE_ANIME

        # 低帧率 + 无码率信息 → 根据分辨率判断
        if fps <= 30:
            if w <= 1280 and h <= 720:
                return self.TYPE_ANIME
            return self.TYPE_MOVIE

        # 中帧率 → 新闻
        if 30 < fps < 49:
            return self.TYPE_NEWS

        return self.TYPE_UNKNOWN

    def _get_scene_label(self, scene_type: str) -> str:
        """获取场景类型的中英文标签"""
        labels = {
            self.TYPE_ANIME: '动画',
            self.TYPE_SPORTS: '体育',
            self.TYPE_MOVIE: '电影',
            self.TYPE_NEWS: '新闻',
            self.TYPE_4K: '4K/HDR',
            self.TYPE_UNKNOWN: '未知',
        }
        return labels.get(scene_type, '未知')


# 单例
_instance = None


def get_scene_detect_service() -> SceneDetectService:
    global _instance
    if _instance is None:
        _instance = SceneDetectService()
    return _instance
