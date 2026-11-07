"""动态裁剪黑边服务

通过 mpv 的 screenshot-to-file 命令抓取一帧，用 Pillow 分析上下左右边缘的黑色像素，
计算实际内容裁剪区域，再通过 lavfi=[crop=w:h:x:y] 滤镜应用。

特性：
- 异步执行，避免阻塞 GUI 线程
- 可配置黑边阈值（默认 16，0-255 灰度）
- 可配置最小裁剪宽度比（避免误裁太窄）
- 使用 @iptv_autocrop 命名标签，便于后续移除/替换
"""
import os
import threading
import time

from core.log_manager import global_logger as logger


# 黑边判定阈值（灰度 < 该值视为黑色）
DEFAULT_BLACK_THRESHOLD = 16
# 最小裁剪宽高比（避免裁出极窄区域）
MIN_ASPECT_RATIO = 0.5


class AutoCropService:
    """动态裁剪黑边服务"""

    def __init__(self, main_window):
        self.window = main_window
        # 黑边阈值
        self.threshold = DEFAULT_BLACK_THRESHOLD
        # 是否正在分析（避免并发）
        self._analyzing = False
        self._analyzing_lock = threading.Lock()
        # 最近一次裁剪参数
        self._last_crop = None

    def set_threshold(self, value: int):
        """设置黑边阈值（0-255）"""
        self.threshold = max(0, min(255, int(value)))

    def analyze_and_apply(self, done_callback=None):
        """异步分析当前帧并应用裁剪

        Args:
            done_callback: 可选回调，参数 (success: bool, crop: tuple|None, message: str)
        """
        with self._analyzing_lock:
            if self._analyzing:
                if done_callback:
                    done_callback(False, None, '正在分析中')
                return
            self._analyzing = True
        pc = getattr(self.window, 'player_controller', None)
        if not pc or not pc.is_playing:
            with self._analyzing_lock:
                self._analyzing = False
            if done_callback:
                done_callback(False, None, '当前无播放内容')
            return
        t = threading.Thread(
            target=self._worker,
            args=(pc, done_callback),
            daemon=True,
        )
        t.start()

    def remove_crop(self):
        """移除已应用的裁剪滤镜"""
        try:
            pc = getattr(self.window, 'player_controller', None)
            if not pc:
                return False
            pc.send_command(['vf', 'remove', '@iptv_autocrop'])
            self._last_crop = None
            return True
        except Exception as e:
            logger.debug(f"移除裁剪滤镜失败: {e}")
            return False

    def _worker(self, pc, done_callback):
        """工作线程：截图 -> 分析 -> 应用滤镜"""
        try:
            # 1. 截图到临时文件（放在用户缓存目录，避免打包目录不可写/被清理）
            from utils.app_paths import get_cache_dir
            cache_dir = os.path.join(get_cache_dir(), 'autocrop')
            os.makedirs(cache_dir, exist_ok=True)
            tmp_path = os.path.join(cache_dir, f'frame_{int(time.time())}.png')
            ret = pc.send_command(['screenshot-to-file', tmp_path, 'video'])
            if ret != 0 or not os.path.exists(tmp_path):
                self._finish(done_callback, False, None, '截图失败')
                return
            # 2. 用 PIL 分析
            try:
                from PIL import Image
            except ImportError:
                self._finish(done_callback, False, None,
                             '未安装 Pillow，无法分析黑边（pip install Pillow）')
                return
            try:
                img = Image.open(tmp_path).convert('L')  # 转灰度
            except Exception as e:
                self._finish(done_callback, False, None, f'读取截图失败: {e}')
                return
            finally:
                # 删除临时文件
                try:
                    os.remove(tmp_path)
                except Exception as e:
                    logger.debug(f"_worker: {e}")
            w, h = img.size
            if w < 16 or h < 16:
                self._finish(done_callback, False, None, '图像太小')
                return
            # 3. 计算黑边边界
            import numpy as np
            try:
                arr = np.asarray(img)
            except Exception as e:
                self._finish(done_callback, False, None, f'转换为 numpy 数组失败: {e}')
                return
            threshold = self.threshold
            # 上下边：逐行检查黑色像素比例
            top = self._find_edge(arr, axis=0, threshold=threshold, max_ratio=0.4)
            bottom = h - 1 - self._find_edge(arr[::-1, :], axis=0, threshold=threshold, max_ratio=0.4)
            left = self._find_edge(arr, axis=1, threshold=threshold, max_ratio=0.4)
            right = w - 1 - self._find_edge(arr[:, ::-1], axis=1, threshold=threshold, max_ratio=0.4)
            # 校验
            crop_w = right - left + 1
            crop_h = bottom - top + 1
            if crop_w < w * MIN_ASPECT_RATIO or crop_h < h * MIN_ASPECT_RATIO:
                # 裁剪区域过小，可能误判，不应用
                self._finish(done_callback, False, None,
                            f'裁剪区域过小 ({crop_w}x{crop_h} / {w}x{h})，跳过')
                return
            if top == 0 and left == 0 and bottom == h - 1 and right == w - 1:
                # 无黑边
                self._finish(done_callback, True, None, '未检测到黑边')
                return
            # 4. 应用 crop 滤镜（先移除旧的）
            try:
                pc.send_command(['vf', 'remove', '@iptv_autocrop'])
            except Exception as e:
                logger.debug(f"_worker: {e}")
            # crop 滤镜参数：w:h:x:y
            # 注意 crop 宽高应为偶数（H.264 编码要求）
            crop_w = crop_w - (crop_w % 2)
            crop_h = crop_h - (crop_h % 2)
            filter_str = f'lavfi=[crop={crop_w}:{crop_h}:{left}:{top}]'
            ret = pc.send_command(['vf', 'add', f'@iptv_autocrop:{filter_str}'])
            if ret != 0:
                self._finish(done_callback, False, None, '应用裁剪滤镜失败（mpv 返回错误）')
                return
            crop = (left, top, crop_w, crop_h)
            self._last_crop = crop
            self._finish(done_callback, True, crop,
                        f'已裁剪到 {crop_w}x{crop_h} (offset {left},{top})')
        except Exception as e:
            logger.error(f"动态裁剪黑边失败: {e}")
            self._finish(done_callback, False, None, f'异常: {e}')
        finally:
            self._analyzing = False

    def _finish(self, callback, success, crop, message):
        """回调通知（在子线程执行；调用方需自行处理跨线程）"""
        if callback:
            try:
                callback(success, crop, message)
            except Exception as e:
                logger.debug(f"_finish: {e}")

    @staticmethod
    def _find_edge(arr, axis: int, threshold: int, max_ratio: float = 0.4) -> int:
        """查找某条边的黑色边界偏移

        Args:
            arr: numpy 2D 数组（灰度）
            axis: 0=查找上边（扫描行），1=查找左边（扫描列）
            threshold: 灰度小于此值视为黑色
            max_ratio: 最大允许裁剪比例（避免误判整片暗场）

        Returns:
            边界偏移（0 表示无黑边）
        """
        try:
            h, w = arr.shape
            # axis=0: 上边扫描，limit 基于 h（行数）
            # axis=1: 左边扫描，limit 基于 w（列数）
            limit = int((h if axis == 0 else w) * max_ratio)
            for i in range(limit):
                if axis == 0:
                    line = arr[i, :]
                else:
                    line = arr[:, i]
                # 该行/列中黑色像素占比
                black_ratio = float((line < threshold).sum()) / float(line.size)
                # 阈值：该行/列超过 95% 为黑色才视为黑边
                if black_ratio < 0.95:
                    return i
            return limit
        except Exception:
            return 0
