import math
import random
import subprocess
import threading
import time
import os


from utils.numpy_compat import np, NUMPY_AVAILABLE
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer, Qt, QRectF, QPointF
from PySide6.QtGui import (

    QPen,
    QBrush,
    QPixmap,
    QImage,
    QPolygonF,
    QColor,
    QPainter,
    QPainterPath,
    QRadialGradient,
    QLinearGradient,
    QConicalGradient,
)

# 封面显示模式常量（任务B：封面位置/大小/形式 可配置）
COVER_POS_X = {'center': 0.5, 'left': 0.26, 'right': 0.74}
COVER_SCALE = {'small': 0.22, 'medium': 0.30, 'large': 0.40}

try:
    from core.log_manager import global_logger as logger
except Exception:
    logger = None

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma', '.m4a',
                    '.ape', '.alac', '.wv', '.tta', '.dts', '.ac3', '.mid', '.midi')

AUDIO_VISUAL_STYLES = {
    'spectrum': {
        'name_key': 'audio_vis_spectrum',
        'name_default': '3D频谱',
    },
    'waves': {
        'name_key': 'audio_vis_waves',
        'name_default': '3D波形',
    },
    'circular': {
        'name_key': 'audio_vis_circular',
        'name_default': '3D环形',
    },
    'terrain': {
        'name_key': 'audio_vis_terrain',
        'name_default': '3D地形',
    },
    'cosmos': {
        'name_key': 'audio_vis_cosmos',
        'name_default': '3D宇宙',
    },
    'fluid': {
        'name_key': 'audio_vis_fluid',
        'name_default': '3D流体',
    },
    'ripple': {
        'name_key': 'audio_vis_ripple',
        'name_default': '粒子震荡洞洞波',
    },
    'galaxy': {
        'name_key': 'audio_vis_galaxy',
        'name_default': '银河轨道',
    },
    'none': {
        'name_key': 'audio_vis_none',
        'name_default': '关闭可视化',
    },
}

STYLE_KEYS = [k for k in AUDIO_VISUAL_STYLES if k != 'none']

FFT_SIZE = 4096
SAMPLE_RATE = 44100
AUDIO_CHANNELS = 2
NUM_BARS = 64

# numpy 不可用时可视化整体禁用，这里只保留类型占位，数组永远不会被消费
_F32 = np.float32 if NUMPY_AVAILABLE else None
_I32 = np.int32 if NUMPY_AVAILABLE else None


def _zeros(count, dtype=None):
    """numpy 缺失时返回空元组：调用方在此之前已跳过可视化链路。"""
    if np is None:
        return ()
    return np.zeros(count) if dtype is None else np.zeros(count, dtype=dtype)


class AudioPCMProvider:
    def __init__(self):
        self._lock = threading.Lock()
        self._pcm_mono = _zeros(0, _F32)
        self._pcm_left = _zeros(0, _F32)
        self._pcm_right = _zeros(0, _F32)
        self._sample_rate = SAMPLE_RATE
        self._duration = 0.0
        self._time_pos = 0.0
        self._loading = False
        self._decode_generation = 0

    def start(self, file_path):
        with self._lock:
            self._decode_generation += 1
            my_gen = self._decode_generation
            self._pcm_mono = _zeros(0, _F32)
            self._pcm_left = _zeros(0, _F32)
            self._pcm_right = _zeros(0, _F32)
            self._duration = 0.0
            self._time_pos = 0.0
            self._loading = True
        threading.Thread(target=self._decode_file, args=(file_path, my_gen), daemon=True).start()

    def stop(self):
        with self._lock:
            self._pcm_mono = _zeros(0, _F32)
            self._pcm_left = _zeros(0, _F32)
            self._pcm_right = _zeros(0, _F32)
            self._duration = 0.0

    def update_time_pos(self, time_pos):
        self._time_pos = max(0.0, time_pos)

    def get_samples(self, count=FFT_SIZE):
        if np is None:
            return _zeros(count, _F32)
        with self._lock:
            if len(self._pcm_mono) == 0:
                return _zeros(count, _F32)
            idx = int(self._time_pos * self._sample_rate)
            start = max(0, idx - count)
            end = start + count
            if end > len(self._pcm_mono):
                end = len(self._pcm_mono)
                start = max(0, end - count)
            chunk = self._pcm_mono[start:end].copy()
        if len(chunk) < count:
            padded = _zeros(count, _F32)
            padded[:len(chunk)] = chunk
            return padded
        return chunk

    def get_stereo_samples(self, count=256):
        if np is None:
            return _zeros(count, _F32), _zeros(count, _F32)
        with self._lock:
            if len(self._pcm_left) == 0:
                return _zeros(count, _F32), _zeros(count, _F32)
            idx = int(self._time_pos * self._sample_rate)
            start = max(0, idx - count)
            end = start + count
            left = self._pcm_left[start:end].copy()
            right = self._pcm_right[start:end].copy()
        if len(left) < count:
            padded_l = _zeros(count, _F32)
            padded_r = _zeros(count, _F32)
            padded_l[:len(left)] = left
            padded_r[:len(right)] = right
            return padded_l, padded_r
        return left, right

    def _decode_file(self, file_path, my_gen):
        from core.log_manager import global_logger as _log
        if np is None:
            _log.warning('音频可视化预解码跳过：numpy 不可用')
            return
        proc = None
        try:
            native_path = os.path.normpath(file_path)
            _log.info(f"音频可视化: 开始预解码 {native_path}")
            cmd = [
                'ffmpeg', '-i', native_path,
                '-f', 's16le', '-acodec', 'pcm_s16le',
                '-ar', str(SAMPLE_RATE), '-ac', str(AUDIO_CHANNELS),
                '-v', 'error', '-'
            ]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            chunks = []
            deadline = time.time() + 60
            while time.time() < deadline:
                raw = proc.stdout.read(SAMPLE_RATE * AUDIO_CHANNELS * 2)
                if not raw:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                chunks.append(samples)
            stderr_out = proc.stderr.read().decode('utf-8', errors='ignore') if proc.stderr else ''
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if chunks:
                all_samples = np.concatenate(chunks)
                with self._lock:
                    if my_gen != self._decode_generation:
                        return
                    self._pcm_left = all_samples[0::2].copy()
                    self._pcm_right = all_samples[1::2].copy()
                    self._pcm_mono = (self._pcm_left + self._pcm_right) / 2.0
                    self._duration = len(self._pcm_mono) / self._sample_rate
                _log.info(f"音频可视化: 预解码完成, {self._duration:.1f}s, {len(self._pcm_mono)} samples")
            else:
                _log.warning(f"音频可视化: 预解码无数据, stderr={stderr_out[:500]}")
        except Exception as e:
            _log.error(f"音频可视化: 预解码失败 {e}")
        finally:
            self._loading = False
            if proc is not None:
                try:
                    proc.kill()
                except Exception as e:
                    logger.debug(f"_decode_file: {e}")
                try:
                    proc.wait(timeout=5)
                except Exception as e:
                    logger.debug(f"_decode_file: {e}")


def compute_spectrum(samples, fft_size=FFT_SIZE, num_bars=NUM_BARS):
    if np is None:
        # numpy 不可用：调用方（_tick/paintEvent）已跳过绘制，这里只做安全兜底
        return [0.0] * num_bars
    if len(samples) < fft_size:
        padded = np.zeros(fft_size, dtype=np.float32)
        padded[:len(samples)] = samples
        samples = padded
    window = np.hanning(fft_size)
    windowed = samples[-fft_size:] * window
    fft_data = np.fft.rfft(windowed)
    magnitudes = np.abs(fft_data)
    freqs = np.fft.rfftfreq(fft_size, 1.0 / SAMPLE_RATE)
    min_freq = 20
    max_freq = min(18000, SAMPLE_RATE / 2)
    freq_res = SAMPLE_RATE / fft_size
    linear_bars = int(num_bars * 0.5)
    log_bars = num_bars - linear_bars
    linear_freqs = np.linspace(min_freq, 500, linear_bars + 1)
    min_bin_width = freq_res * 1.5
    for i in range(linear_bars):
        if linear_freqs[i + 1] - linear_freqs[i] < min_bin_width:
            linear_freqs[i + 1] = linear_freqs[i] + min_bin_width
    log_freqs = np.logspace(np.log10(max(500, linear_freqs[-1])), np.log10(max_freq), log_bars + 1)
    bar_freqs = np.concatenate([linear_freqs, log_freqs[1:]])
    bars = np.zeros(num_bars)
    for i in range(num_bars):
        mask = (freqs >= bar_freqs[i]) & (freqs < bar_freqs[i + 1])
        if np.any(mask):
            bars[i] = np.mean(magnitudes[mask])
    ref = np.percentile(magnitudes, 90) * 4.0
    if ref > 0:
        bars = bars / ref
    return np.clip(bars, 0, 1)


def _project_3d(x, y, z, w, h, cam_dist=8.0, fov_scale=0.1, pitch=0.45, yaw=0.0):
    cos_p = math.cos(-pitch)
    sin_p = math.sin(-pitch)
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    y1 = y * cos_p - z * sin_p
    z1 = y * sin_p + z * cos_p
    x2 = x * cos_y - z1 * sin_y
    z2 = x * sin_y + z1 * cos_y
    y2 = y1
    depth = z2 + cam_dist
    if depth < 0.3:
        depth = 0.3
    scale = cam_dist / depth
    sx = w / 2 + x2 * scale * w * fov_scale
    sy = h / 2 - y2 * scale * h * fov_scale
    return sx, sy, depth, scale


def _galaxy_rand(seed):
    """确定性伪随机：基于种子的稳定哈希，保证粒子初始化不随帧抖动。

    与 Mineradio wallpaper.html 中的 rand(seed) 完全一致：
    Math.abs(Math.sin(seed * 3187.917) * 43758.5453) % 1
    """
    return abs(math.sin(seed * 3187.917) * 43758.5453) % 1.0


class AudioVisualWidget(QWidget):
    def __init__(self, parent=None, player_controller=None):
        super().__init__(parent)
        self._style = 'spectrum'
        self._active = False
        self._pc = player_controller
        self._pcm = AudioPCMProvider()
        self._bars = _zeros(NUM_BARS)
        self._smooth_bars = _zeros(NUM_BARS)
        self._peak_bars = _zeros(NUM_BARS)
        self._peak_decay = _zeros(NUM_BARS, _I32)
        self._wave_left = _zeros(512)
        self._wave_right = _zeros(512)
        self._cover_pixmap = None
        self._cover_blurred_pixmap = None  # 预计算的模糊封面（用于光晕渲染，缓存避免每帧重算）
        self._frame_count = 0
        # 封面显示配置（任务B）：位置/大小/形式，持久化到 ConfigManager
        self._cover_pos = 'center'    # center / left / right
        self._cover_size = 'medium'   # small / medium / large
        self._cover_shape = 'card'    # card / circle / hidden
        self._load_cover_settings()

        self._cosmos_bg_stars = []
        self._cosmos_particles = []
        self._cosmos_meteors = []
        self._cosmos_rotation = 0.0
        self._fluid_hue = 0.0
        self._fluid_phase = 0.0
        self._fluid_buf = None
        self._fluid_buf_w = 0
        self._fluid_buf_h = 0
        self._spectrum_angle = 0.0
        self._ripple_phase = 0.0
        self._ripple_cam_x = 0.0  # 相机跟随的世界轴心 X（洞洞波：光核沿轴向左移动）
        self._ripple_beat_cooldown = 0.0
        self._ripple_prev_bass = 0.0
        self._ripple_prev_high = 0.0  # 高频上一帧值（双通道起音检测）
        self._ripple_pulse = 0.0  # 快攻击节拍包络（光核亮度）
        self._ripple_bass_hist = []  # 低频通道近期起音（自适应阈值参考）
        self._ripple_high_hist = []  # 高频通道近期起音
        self._ripple_time = 0.0  # 效果运行时间（节拍周期估计用）
        self._ripple_warmup = 45  # 预热帧数（切样式后包络爬升期禁触发）
        self._ripple_trig_times = []  # 近期触发间隔（节拍周期估计）
        self._ripple_interval = 0.0  # 当前节拍周期（秒），0=未锁定
        self._ripple_last_trig = -1.0  # 上次触发时间
        self._ripple_shells = []  # 节拍爆出的粒子球壳（世界坐标原地膨胀）
        self._ripple_dust = []  # 轴线微粒（核心洒落，增强水平光带质感）
        self._ripple_bg_particles = []
        self._ripple_hue = 200.0
        self._ripple_sprites = {}  # 预渲染粒子辉光贴图（按色相分档）
        # galaxy 银河俯视状态：螺旋双臂粒子 + 图案旋转 + 节奏脉冲 + 固定背景星空
        self._galaxy_particles = []
        self._galaxy_hue = 200.0
        self._galaxy_time = 0.0
        self._galaxy_pulse = 0.0
        self._galaxy_bg_stars = []
        # 统一色彩语言：「深空夜色 + 霓虹流光」——全局色相在 青(190°)~蓝紫(260°)~品红(310°)
        # 之间以 sin 摆动（避免循环扫撞上橙绿土色），各效果共享并叠加自身偏移。
        self._hue_t = random.uniform(0.0, 2000.0)
        self._hue_drift = 250.0
        self._random_mode = False
        self._random_timer = QTimer(self)
        self._random_timer.setInterval(15000)
        self._random_timer.timeout.connect(self._on_random_tick)
        self._fade_alpha = 1.0
        self._fade_state = 'visible'
        self._pending_style = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(16)

    def set_style(self, style_key):
        is_random = (style_key == 'random')
        self._random_mode = is_random
        if is_random:
            style_key = random.choice(STYLE_KEYS)
            self._random_timer.start()
        else:
            self._random_timer.stop()
        if self._style == style_key and self._fade_state == 'visible':
            return
        if self._fade_alpha < 0.05:
            self._apply_style_now(style_key)
        else:
            self._pending_style = style_key
            self._fade_state = 'fading_out'

    def _apply_style_now(self, style_key):
        self._style = style_key
        if style_key == 'terrain':
            self._terrain_phase = 0.0
        elif style_key == 'cosmos':
            self._cosmos_bg_stars = []
            self._cosmos_particles = []
            self._cosmos_meteors = []
        elif style_key == 'fluid':
            self._fluid_buf = None
        elif style_key == 'ripple':
            self._ripple_phase = 0.0
            self._ripple_cam_x = 0.0
            self._ripple_beat_cooldown = 0.0
            self._ripple_prev_bass = 0.0
            self._ripple_prev_high = 0.0
            self._ripple_pulse = 0.0
            self._ripple_bass_hist = []
            self._ripple_high_hist = []
            self._ripple_time = 0.0
            self._ripple_warmup = 45
            self._ripple_trig_times = []
            self._ripple_interval = 0.0
            self._ripple_last_trig = -1.0
            self._ripple_shells = []
            self._ripple_dust = []
            self._ripple_bg_particles = []
            self._ripple_hue = 200.0
        elif style_key == 'galaxy':
            # 银河俯视：螺旋双臂粒子
            self._galaxy_particles = []
            self._galaxy_hue = 200.0
            self._galaxy_time = 0.0
            self._galaxy_pulse = 0.0
        self._peak_bars = _zeros(NUM_BARS)
        self._peak_decay = _zeros(NUM_BARS, _I32)
        self._smooth_bars = _zeros(NUM_BARS)

    def _on_random_tick(self):
        if not self._random_mode or not self._active:
            return
        available = [k for k in STYLE_KEYS if k != self._style]
        if available:
            new_style = random.choice(available)
        else:
            new_style = STYLE_KEYS[0]
        self._pending_style = new_style
        self._fade_state = 'fading_out'

    def get_style(self):
        return self._style

    def _theme_hue(self, offset=0.0):
        """全局主题色相 + 效果私有偏移，范围被 sin 摆动限制在 190~310 邻域。"""
        return (self._hue_drift + offset) % 360.0

    @staticmethod
    def _hsv(h, s, v, a=255):
        """带钳位的 HSV 颜色构造，避免参数越界抛异常。"""
        c = QColor()
        c.setHsv(int(h) % 360,
                 0 if s < 0 else (255 if s > 255 else int(s)),
                 0 if v < 0 else (255 if v > 255 else int(v)),
                 0 if a < 0 else (255 if a > 255 else int(a)))
        return c

    @staticmethod
    def _depth_fog(scale, gain=0.5, floor=0.2):
        """景深雾化系数：投影 scale 越小（越远）越接近背景。"""
        f = (scale - 0.7) * gain
        if f < floor:
            return floor
        if f > 1.0:
            return 1.0
        return f

    def start(self, file_path=None):
        if np is None:
            # numpy 缺失时可视化整体禁用，不能拉起预解码线程
            logger.warning('音频可视化不可用：numpy 导入失败，详见 crash.log')
            return
        self._active = True
        if file_path and os.path.exists(file_path):
            self._pcm.start(file_path)
        self._timer.start()
        self.show()
        self.raise_()

    def stop(self):
        self._active = False
        self._pcm.stop()
        self._timer.stop()
        self.hide()

    def is_active(self):
        return self._active

    def set_cover(self, pixmap):
        self._cover_pixmap = pixmap
        # 预计算模糊封面：先缩小到 1/10 再放大回原尺寸，利用双线性插值实现平滑模糊
        # 对应 Mineradio wallpaper.html 中的 ctx.filter = 'blur(28px) saturate(1.25)'
        if pixmap is not None and not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
            small_w = max(1, pixmap.width() // 10)
            small_h = max(1, pixmap.height() // 10)
            small = pixmap.scaled(small_w, small_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._cover_blurred_pixmap = small.scaled(pixmap.width(), pixmap.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            self._cover_blurred_pixmap = None

    # ---- 封面显示配置（任务B）：持久化 + setter/getter ----

    _COVER_CFG_SECTION = 'Player'
    _COVER_CFG_KEYS = {
        'pos': 'cover_position',
        'size': 'cover_size',
        'shape': 'cover_shape',
    }

    def _load_cover_settings(self):
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            pos = config.get_value(self._COVER_CFG_SECTION, self._COVER_CFG_KEYS['pos'], 'center')
            size = config.get_value(self._COVER_CFG_SECTION, self._COVER_CFG_KEYS['size'], 'medium')
            shape = config.get_value(self._COVER_CFG_SECTION, self._COVER_CFG_KEYS['shape'], 'card')
            if pos in COVER_POS_X:
                self._cover_pos = pos
            if size in COVER_SCALE:
                self._cover_size = size
            if shape in ('card', 'circle', 'hidden'):
                self._cover_shape = shape
        except Exception:
            pass

    @classmethod
    def _save_cover_setting(cls, key, value):
        """直接写配置（widget 尚未创建时菜单兜底也走这里）。"""
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            config.set_value(cls._COVER_CFG_SECTION, cls._COVER_CFG_KEYS[key], value)
            config.save_config()
        except Exception as e:
            if logger:
                logger.debug(f"保存封面显示设置失败: {e}")

    def set_cover_pos(self, mode):
        if mode not in COVER_POS_X:
            return
        self._cover_pos = mode
        self._save_cover_setting('pos', mode)
        self.update()

    def get_cover_pos(self):
        return self._cover_pos

    def set_cover_size(self, mode):
        if mode not in COVER_SCALE:
            return
        self._cover_size = mode
        self._save_cover_setting('size', mode)
        self.update()

    def get_cover_size(self):
        return self._cover_size

    def set_cover_shape(self, mode):
        if mode not in ('card', 'circle', 'hidden'):
            return
        self._cover_shape = mode
        self._save_cover_setting('shape', mode)
        self.update()

    def get_cover_shape(self):
        return self._cover_shape

    def _tick(self):
        if not self._active or np is None:
            return
        self._sync_parent_size()
        self._update_fade()
        if self._pc and hasattr(self._pc, '_get_mpv_property_double'):
            try:
                t = self._pc._get_mpv_property_double('time-pos')
                if t is not None:
                    self._pcm.update_time_pos(t)
            except Exception as e:
                logger.debug(f"_tick: {e}")
        self._update_data()
        self.update()

    def _sync_parent_size(self):
        parent = self.parent()
        if parent:
            pw, ph = parent.width(), parent.height()
            if pw > 0 and ph > 0 and (self.width() != pw or self.height() != ph):
                self.setGeometry(0, 0, pw, ph)

    def _update_fade(self):
        if self._fade_state == 'fading_out':
            self._fade_alpha -= 0.06
            if self._fade_alpha <= 0.0:
                self._fade_alpha = 0.0
                if self._pending_style:
                    self._apply_style_now(self._pending_style)
                    self._pending_style = None
                self._fade_state = 'fading_in'
        elif self._fade_state == 'fading_in':
            self._fade_alpha += 0.04
            if self._fade_alpha >= 1.0:
                self._fade_alpha = 1.0
                self._fade_state = 'visible'

    def _update_data(self):
        self._frame_count += 1
        # 全局色相缓慢漂移：sin 摆动于青(190°)~蓝紫(260°)~品红(310°)，连续无跳变
        self._hue_t += 0.02
        self._hue_drift = 250.0 + 60.0 * math.sin(self._hue_t * 0.3)
        needs_bars = self._style in ('spectrum', 'circular', 'terrain', 'cosmos', 'fluid', 'ripple', 'galaxy')
        if needs_bars:
            samples = self._pcm.get_samples(FFT_SIZE)
            self._bars = compute_spectrum(samples, FFT_SIZE, NUM_BARS)
            self._smooth_bars += (self._bars - self._smooth_bars) * 0.55
            for i in range(NUM_BARS):
                if self._bars[i] > self._peak_bars[i]:
                    self._peak_bars[i] = self._bars[i]
                    self._peak_decay[i] = 0
                else:
                    self._peak_decay[i] += 1
                    if self._peak_decay[i] > 10:
                        self._peak_bars[i] *= 0.9
        if self._style == 'waves':
            self._wave_left, self._wave_right = self._pcm.get_stereo_samples(512)
        if self._style == 'cosmos':
            self._update_cosmos()
        if self._style == 'terrain':
            self._terrain_phase += 0.015 + float(np.mean(self._bars[:8])) * 0.04
        if self._style == 'fluid':
            self._update_fluid()
        if self._style == 'spectrum':
            self._spectrum_angle += 0.003
        if self._style == 'ripple':
            self._update_ripple()
        if self._style == 'galaxy':
            self._update_galaxy()


    def _update_cosmos(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        bass = float(np.mean(self._bars[:8]))
        mid = float(np.mean(self._bars[8:30]))
        high = float(np.mean(self._bars[30:]))
        cx, cy = w / 2, h / 2
        self._cosmos_rotation += 0.003 + bass * 0.01
        if len(self._cosmos_bg_stars) < 300:
            for _ in range(5):
                self._cosmos_bg_stars.append({
                    'x': random.uniform(-4, 4),
                    'y': random.uniform(-3, 3),
                    'z': random.uniform(-8, 2),
                    'size': random.uniform(0.02, 0.08),
                    'twinkle': random.uniform(0, math.pi * 2),
                    'speed': random.uniform(0.02, 0.06),
                })
        for s in self._cosmos_bg_stars:
            s['twinkle'] += s['speed']
        energy = bass + mid + high
        if energy > 0.15:
            count = int(energy * 8) + 2
            spawn_hue = self._theme_hue(0.0)
            for _ in range(count):
                angle = random.uniform(0, 2 * math.pi)
                speed = 0.03 + bass * 0.15
                dist = random.uniform(0, 0.3)
                hue = (spawn_hue + random.uniform(-18, 18)) % 360
                self._cosmos_particles.append({
                    'x': math.cos(angle) * dist,
                    'y': random.uniform(-0.1, 0.1),
                    'z': math.sin(angle) * dist,
                    'vx': math.cos(angle) * speed,
                    'vy': random.uniform(-0.005, 0.005),
                    'vz': math.sin(angle) * speed,
                    'life': 1.0,
                    'size': 0.03 + bass * 0.1 + random.random() * 0.03,
                    'hue': hue,
                })
        alive = []
        for p in self._cosmos_particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['z'] += p['vz']
            p['vx'] *= 0.995
            p['vy'] *= 0.995
            p['vz'] *= 0.995
            p['life'] -= 0.008
            if p['life'] > 0:
                alive.append(p)
        self._cosmos_particles = alive[-600:]
        if random.random() < 0.02 + bass * 0.15:
            angle = random.uniform(0, 2 * math.pi)
            speed = 0.1 + bass * 0.2
            self._cosmos_meteors.append({
                'x': math.cos(angle) * 4,
                'y': random.uniform(-1, 1),
                'z': math.sin(angle) * 4,
                'vx': -math.cos(angle) * speed,
                'vy': random.uniform(-0.01, 0.01),
                'vz': -math.sin(angle) * speed,
                'life': 1.0,
                'len': 0.5 + bass * 1.0,
                'hue': (self._theme_hue(20.0) + random.uniform(-15, 15)) % 360,
            })
        m_alive = []
        for m in self._cosmos_meteors:
            m['x'] += m['vx']
            m['y'] += m['vy']
            m['z'] += m['vz']
            m['life'] -= 0.02
            if m['life'] > 0:
                m_alive.append(m)
        self._cosmos_meteors = m_alive[-30:]

    def _update_fluid(self):
        # 流体色相同步全局主题，仅做小幅自摆动，保持统一色彩语言
        self._fluid_hue = (self._hue_drift + 25.0 * math.sin(self._fluid_phase * 0.35)) % 360
        bass = float(np.mean(self._bars[:8]))
        mid = float(np.mean(self._bars[8:30]))
        self._fluid_phase += 0.02 + bass * 0.06 + mid * 0.03

    def _update_ripple(self):
        """粒子震荡洞洞波（AE 原工程复刻）：侧视光核沿轴左移 + 节拍球壳拖尾成串。

        - 光核沿水平轴向左匀速移动（屏幕左侧），节拍触发时在光核处爆出粒子球壳
        - 壳在世界坐标原地缓慢膨胀并留在身后 → 侧视下成一串由新到旧的「洋葱串」
        - 粒子极小极密（每壳数百颗），壳带径向厚度抖动形成蜂窝「洞洞」质感
        - 颜色沿壳年龄渐变：新壳青白 → 老壳深蓝（原版 Alan Walker 配色）
        - 节拍检测：低频主导起音 + 相对阈值 + 拍点窗口锁定（与银河效果同源）
        """
        bass = float(np.mean(self._bars[:8]))
        mid = float(np.mean(self._bars[8:30]))
        high = float(np.mean(self._bars[30:]))
        self._ripple_phase += 0.012 + bass * 0.04
        self._ripple_time += 1 / 60.0  # 效果运行时间（节拍周期估计）
        # 色相同步全局主题（青蓝系基础上轻微漂移）
        self._ripple_hue = (self._hue_drift + 22.0 * math.sin(self._ripple_phase * 0.5)) % 360
        # 光核沿轴左移：基础匀速 + 低频微加速（壳串随节拍向右拉伸）
        self._ripple_cam_x -= (0.60 + bass * 0.40) / 60.0
        # 远景星空：世界固定坐标，漂出视野则在附近重生
        if len(self._ripple_bg_particles) < 44:
            for _ in range(44 - len(self._ripple_bg_particles)):
                self._ripple_bg_particles.append(self._make_ripple_star())
        kept_stars = []
        for p in self._ripple_bg_particles:
            p['twinkle'] += p['speed']
            if abs(p['x'] - self._ripple_cam_x) > 24.0:
                kept_stars.append(self._make_ripple_star())
            else:
                kept_stars.append(p)
        self._ripple_bg_particles = kept_stars
        # 节拍检测：双通道起音（低频重震 + 高频碎震），任一超阈值即震荡
        level = min(1.0, bass * 0.75 + mid * 0.20 + high * 0.05)
        prev_pulse = self._ripple_pulse
        self._ripple_pulse = max(level, prev_pulse * 0.90)  # 全频包络（光核亮度）
        base_hue = int(self._ripple_hue) % 360
        # 双通道起音增量：低频（鼓/贝斯）与高频（镲片/节奏细节）独立检测
        bass_onset = bass - self._ripple_prev_bass
        high_onset = high - self._ripple_prev_high
        self._ripple_prev_bass = bass
        self._ripple_prev_high = high
        self._ripple_beat_cooldown -= 1 / 60.0
        # 各通道自适应阈值：起音超过近期触发中位数的一半即有效（自动适配响度）
        bh = self._ripple_bass_hist
        hh = self._ripple_high_hist
        bass_gate = max(0.045, (sorted(bh)[len(bh) // 2] if bh else 0.06) * 0.5)
        high_gate = max(0.035, (sorted(hh)[len(hh) // 2] if hh else 0.05) * 0.5)
        # 预热期（样式切换后约 1 秒）：包络从零爬升会产生假起音，禁止触发
        warm_ok = self._ripple_warmup <= 0
        if self._ripple_warmup > 0:
            self._ripple_warmup -= 1
        # 触发：低频或高频任一通道起音超过自身阈值即震荡（全频段节奏都有响应）；
        # 同帧双通道都超阈值时取较强者——低频爆大伞（重震），高频爆小伞（碎震）
        trig_onset = 0.0
        trig_hf = False
        if warm_ok and self._ripple_beat_cooldown <= 0:
            bass_hit = bass_onset > bass_gate and bass > 0.22
            high_hit = high_onset > high_gate and high > 0.18
            if bass_hit and (not high_hit or bass_onset >= high_onset):
                trig_onset, trig_hf = bass_onset, False
            elif high_hit:
                trig_onset, trig_hf = high_onset, True
        if trig_onset > 0:
            beat_strength = min(1.0, max(0.10, trig_onset * (1.15 if trig_hf else 1.7)))
            h_ = hh if trig_hf else bh
            h_.append(trig_onset)
            if len(h_) > 12:
                h_.pop(0)
            # 记录触发间隔，估计节拍周期（0.22~1.5s 内的有效间隔取中位数）
            if self._ripple_last_trig >= 0:
                iv = self._ripple_time - self._ripple_last_trig
                if 0.22 <= iv <= 1.5:
                    self._ripple_trig_times.append(iv)
                    if len(self._ripple_trig_times) > 6:
                        self._ripple_trig_times.pop(0)
                    self._ripple_interval = sorted(self._ripple_trig_times)[len(self._ripple_trig_times) // 2]
            self._ripple_last_trig = self._ripple_time
            # 节拍爆壳（Particular 持续发射器）：记录发射器状态，爆壳后一段时间
            # 内持续自锥顶喷出粒子流（方向偏向 +X 的薄锥角），粒子带阻尼减速——
            # 早出的飞得远、晚出的还在锥顶附近，纯粒子沿母线连续分布构成伞面
            self._ripple_shells.append({
                'x': self._ripple_cam_x,
                'birth': self._ripple_time,
                'life': 3.8,
                'tau': 1.1,  # 阻尼时间常数（爆发→减速→凝固的节奏感）
                'bs': beat_strength,                    # 强度（发射密度随之缩放）
                'base_v': 0.55 + beat_strength * 0.30,  # 爆发初速
                'emit_left': 0.55,                      # 剩余发射时长（秒）
                'pts': [],                              # (ux, uy, uz, v, size_f, birth)
            })
            # 轴线微粒：爆壳时沿轴撒一把，增强水平光带质感
            for _ in range(14):
                self._ripple_dust.append({
                    'x': self._ripple_cam_x + random.uniform(0.0, 1.4),
                    'y': random.uniform(-0.06, 0.06),
                    'z': random.uniform(-0.06, 0.06),
                    'vx': random.uniform(0.0, 0.04),
                    'vy': random.uniform(-0.02, 0.02),
                    'age': 0.0,
                    'life': random.uniform(1.2, 2.4),
                    'size_f': random.uniform(0.5, 1.1),
                })
            self._ripple_beat_cooldown = 0.14  # 短冷却：高频碎震也放行（震荡密）
        # 轴线微粒：光核持续洒落少量，维持水平光带
        for _ in range(1 + int(level * 2)):
            self._ripple_dust.append({
                'x': self._ripple_cam_x + random.uniform(0.0, 0.5),
                'y': random.uniform(-0.05, 0.05),
                'z': random.uniform(-0.05, 0.05),
                'vx': random.uniform(0.0, 0.04),
                'vy': random.uniform(-0.02, 0.02),
                'age': 0.0,
                'life': random.uniform(1.0, 2.0),
                'size_f': random.uniform(0.4, 1.0),
            })
        # 更新与剔除：微粒按寿命与视野，壳按寿命与右侧出界
        dt = 1 / 60.0
        alive_dust = []
        for p in self._ripple_dust:
            p['age'] += dt
            if p['age'] >= p['life']:
                continue
            p['x'] += p['vx'] * dt
            p['y'] += p['vy'] * dt
            if p['x'] - self._ripple_cam_x < 5.2:
                alive_dust.append(p)
        if len(alive_dust) > 240:
            alive_dust = alive_dust[-240:]
        self._ripple_dust = alive_dust
        alive_shells = []
        for sh in self._ripple_shells:
            age = self._ripple_time - sh['birth']
            if age >= sh['life'] or sh['x'] - self._ripple_cam_x > 6.4:
                continue
            # 持续发射：粒子流自锥顶沿锥面母线喷出（早出的飞得远、晚出的
            # 还在锥顶附近），粒子沿母线连续分布——纯粒子构成伞面
            if sh.get('emit_left', 0) > 0 and len(sh['pts']) < 320:
                sh['emit_left'] -= 1 / 60.0
                base_v = sh['base_v']
                for _ in range(4 + int(sh['bs'] * 9)):  # 强伞喷得密、弱伞疏
                    theta = math.radians(random.uniform(55.0, 75.0))  # 薄锥角
                    az = random.uniform(0, 2 * math.pi)               # 环轴方位均匀
                    st = math.sin(theta)
                    sh['pts'].append((
                        math.cos(theta),       # 轴向分量（伞尖方向）
                        st * math.cos(az),     # 径向分量（伞面张开）
                        st * math.sin(az),
                        base_v * random.uniform(0.88, 1.12),
                        random.uniform(0.75, 1.15),
                        self._ripple_time,
                    ))
            alive_shells.append(sh)
        if len(alive_shells) > 10:
            alive_shells = alive_shells[-10:]
        self._ripple_shells = alive_shells

    def _make_ripple_star(self):
        """生成一颗洞洞波远景星空粒子（世界固定坐标，散布在轴周围）。"""
        return {
            'x': self._ripple_cam_x + random.uniform(-20.0, 8.0),
            'y': random.uniform(-1.8, 1.8),
            'z': random.uniform(-1.0, 1.0),
            'twinkle': random.uniform(0, math.pi * 2),
            'speed': random.uniform(0.03, 0.08),
            'size': random.uniform(0.05, 0.14),
            'hue': (self._hue_drift + random.uniform(-25, 25)) % 360,
        }

    def _update_galaxy(self):
        """银河俯视：粒子锚定多圈缠绕对数螺旋双臂 + 图案刚性旋转 + 节奏明暗脉冲。

        - 粒子基准角沿对数螺旋双臂分布（每臂约 1.5 圈缠绕），随图案统一旋转，臂形永久清晰
        - 70% 粒子窄散布锚定臂上，30% 粒子大散布弥散盘面（填充盘面尘星）
        - 每颗星有缓慢沿轨摆动与柔和闪烁
        - 节奏驱动：中心核球与全部星球亮度同步呼吸
        """
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        self._galaxy_time += 1 / 60.0
        # 节拍包络：快攻击慢释放——原始低频瞬响立即到达峰值（节奏响起同时最亮），
        # 随后约 0.4s 平滑衰减（0.90/帧 @60fps），避免平滑频谱抹平瞬态的问题
        level = min(1.0, float(np.mean(self._bars[:8])))
        self._galaxy_pulse = max(level, self._galaxy_pulse * 0.90)
        # 色相同步全局主题（小幅摆动），保持统一色彩语言
        self._galaxy_hue = (self._hue_drift + 18.0 * math.sin(self._galaxy_time * 0.6)) % 360
        # 自适应粒子数量：按屏幕面积（密度约为原先 1.7 倍），总量上限保证流畅
        target = min(1300, max(750, int((w * h) / 900)))
        while len(self._galaxy_particles) < target:
            i = len(self._galaxy_particles) + 1
            z = _galaxy_rand(i * 5.9)
            ring = 0.18 + z * 0.82
            # 银河俯视结构：粒子锚定在对数螺旋双臂上（多圈缠绕，每臂约 1.5 圈；
            # 基准角为常量，绘制时叠加统一的图案旋转角，旋臂形态永久保持清晰）
            spiral_theta = math.log(ring * 12.0 + 1.0) / 0.16
            if _galaxy_rand(i * 3.1) < 0.70:
                # 70% 臂上星：三角分布近似高斯的窄散布（±0.30），臂形清晰
                spread = (_galaxy_rand(i * 7.3) + _galaxy_rand(i * 13.7) - 1.0) * 0.30
                disk = False
            else:
                # 30% 盘面尘星：大角度散布（0.5~1.6 rad，正负随机），填充旋臂之间
                spread = (0.5 + _galaxy_rand(i * 13.7) * 1.1) * (1.0 if _galaxy_rand(i * 19.3) > 0.5 else -1.0)
                disk = True
            size = 0.5 + _galaxy_rand(i * 4.2) * 1.6
            self._galaxy_particles.append({
                'seed': i * 11.37,
                'phase': spiral_theta + (i % 2) * math.pi + spread,
                'z': z,
                'disk': disk,
                'size': size,
                'twinkle_freq': 0.50 + _galaxy_rand(i * 9.1) * 0.42,
                # 沿轨道的小幅缓慢摆动（生命感，不破坏臂形）
                'wobble': 0.06 + _galaxy_rand(i * 8.5) * 0.10,
                'wobble_freq': 0.08 + _galaxy_rand(i * 2.3) * 0.10,
                # 盘面厚度：内圈鼓起（核球），外圈压平（星系盘）
                'flatten': min(0.98, 0.50 + 0.45 * z + (_galaxy_rand(i * 6.4) - 0.5) * 0.12),
            })
        if len(self._galaxy_particles) > target + 80:
            self._galaxy_particles = self._galaxy_particles[:target + 80]

    def paintEvent(self, event):
        if not self._active or np is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        painter.fillRect(0, 0, w, h, QColor(5, 5, 10))

        # 封面光晕：Mineradio wallpaper.html 同款两层渲染
        # Layer 1: 模糊封面放大 1.24x 作为光晕 halo（低透明度）
        # Layer 2: 原始封面显示（稍高透明度）
        # 配合 sin 函数实现轻微脉动与上下浮动；位置/大小/形状可配置（任务B）
        if (self._cover_pixmap and not self._cover_pixmap.isNull()
                and self._cover_shape != 'hidden'):
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            now = self._frame_count / 60.0
            side = min(w, h) * (COVER_SCALE.get(self._cover_size, 0.30) + math.sin(now * 0.21) * 0.012)
            cover_w = side
            cover_h = side
            cx = w * COVER_POS_X.get(self._cover_pos, 0.5)
            cy_cover = h / 2 + math.sin(now * 0.37) * 8
            x = cx - cover_w / 2
            y = cy_cover - cover_h / 2
            radius = side * 0.06
            main_rect = QRectF(x, y, cover_w, cover_h)
            painter.save()
            # Layer 1: 模糊光晕（放大 1.24x，透明度 0.16，随形状裁剪）
            if self._cover_blurred_pixmap and not self._cover_blurred_pixmap.isNull():
                halo_w = cover_w * 1.24
                halo_h = cover_h * 1.24
                halo_rect = QRectF(x - halo_w * 0.12, y - halo_h * 0.12, halo_w, halo_h)
                painter.setOpacity(0.16)
                halo_path = QPainterPath()
                if self._cover_shape == 'circle':
                    halo_path.addEllipse(halo_rect)
                else:
                    halo_path.addRoundedRect(halo_rect, radius * 1.24, radius * 1.24)
                painter.setClipPath(halo_path)
                painter.drawPixmap(halo_rect, self._cover_blurred_pixmap, QRectF(0, 0, self._cover_blurred_pixmap.width(), self._cover_blurred_pixmap.height()))
            # Layer 2: 原始封面（透明度 0.20，圆角卡片 / 圆形裁剪）
            painter.setOpacity(0.20)
            main_path = QPainterPath()
            if self._cover_shape == 'circle':
                main_path.addEllipse(main_rect)
            else:
                main_path.addRoundedRect(main_rect, radius, radius)
            painter.setClipPath(main_path)
            painter.drawPixmap(main_rect, self._cover_pixmap, QRectF(0, 0, self._cover_pixmap.width(), self._cover_pixmap.height()))
            painter.restore()
            painter.setOpacity(1.0)

        style_map = {
            'spectrum': self._paint_spectrum,
            'waves': self._paint_waves,
            'circular': self._paint_circular,
            'terrain': self._paint_terrain,
            'cosmos': self._paint_cosmos,
            'fluid': self._paint_fluid,
            'ripple': self._paint_ripple,
            'galaxy': self._paint_galaxy,
        }
        paint_fn = style_map.get(self._style, self._paint_spectrum)
        painter.setOpacity(self._fade_alpha)
        paint_fn(painter, w, h)

        bass = float(np.mean(self._smooth_bars[:8])) if len(self._smooth_bars) > 0 else 0
        cx, cy = w / 2, h / 2
        max_dist = math.sqrt(cx * cx + cy * cy)
        vignette = QRadialGradient(cx, cy, max_dist)
        vignette.setColorAt(0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.45, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.75, QColor(0, 0, 0, int(50 + (1 - min(bass * 2, 1)) * 70)))
        vignette.setColorAt(1, QColor(0, 0, 0, 210))
        painter.setOpacity(self._fade_alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(vignette))
        painter.drawRect(QRectF(0, 0, w, h))

        painter.end()

    def _paint_spectrum(self, painter, w, h):
        bars = self._smooth_bars
        peaks = self._peak_bars
        n = len(bars)
        bass = float(np.mean(bars[:8]))
        hue0 = self._theme_hue(0.0)
        cx = w / 2
        pitch = 0.5
        proj = lambda x, y, z: _project_3d(x, y, z, w, h, pitch=pitch)
        painter.setPen(Qt.PenStyle.NoPen)
        # 落地光晕：主题色柔光，随 bass 脉动
        floor_grad = QRadialGradient(cx, h * 1.02, h * 0.72)
        floor_grad.setColorAt(0, self._hsv(hue0, 190, 255, int(8 + bass * 58)))
        floor_grad.setColorAt(0.5, self._hsv(hue0 + 25, 220, 190, int(3 + bass * 20)))
        floor_grad.setColorAt(1, QColor(5, 5, 10, 0))
        painter.setBrush(QBrush(floor_grad))
        painter.drawRect(QRectF(0, 0, w, h))

        # 极淡地面网格：alpha<=18，z 向线随距离衰减
        grid_z_start = -2.0
        grid_z_end = 2.0
        grid_x_start = -4.0
        grid_x_end = 4.0
        grid_y_base = -1.5
        grid_steps_z = 10
        grid_steps_x = 12
        grid_pen = QPen()
        grid_pen.setWidthF(1.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(grid_pen)
        for gi in range(grid_steps_z + 1):
            z = grid_z_start + gi * (grid_z_end - grid_z_start) / grid_steps_z
            near = 1.0 - 0.6 * (z - grid_z_start) / (grid_z_end - grid_z_start)
            grid_pen.setColor(self._hsv(hue0, 170, 160, int(18 * near)))
            painter.setPen(grid_pen)
            sx1, sy1, _, _ = proj(grid_x_start, grid_y_base, z)
            sx2, sy2, _, _ = proj(grid_x_end, grid_y_base, z)
            painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
        for gi in range(grid_steps_x + 1):
            x = grid_x_start + gi * (grid_x_end - grid_x_start) / grid_steps_x
            grid_pen.setColor(self._hsv(hue0, 170, 160, 14))
            painter.setPen(grid_pen)
            sx1, sy1, _, _ = proj(x, grid_y_base, grid_z_start)
            sx2, sy2, _, _ = proj(x, grid_y_base, grid_z_end)
            painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

        bar_spacing = (grid_x_end - grid_x_start) / n
        bar_width_3d = bar_spacing * 0.7
        sorted_bars = []
        for i in range(n):
            x3d = grid_x_start + i * bar_spacing + bar_spacing * 0.15
            z3d = grid_z_start + 0.5 + (i % 3) * 0.3
            val = bars[i]
            peak_val = peaks[i]
            sorted_bars.append((z3d, x3d, val, peak_val, val * 3.0, peak_val * 3.0, i))
        sorted_bars.sort(key=lambda b: -b[0])

        # 复用颜色/渐变对象，避免每帧大量临时分配
        c_top = QColor()
        c_fhi = QColor()
        c_flo = QColor()
        c_side = QColor()
        c_glow = QColor()
        c_peak = QColor()
        c_refl = QColor()
        front_grad = QLinearGradient(0, 0, 0, 1)
        refl_grad = QLinearGradient(0, 0, 0, 1)
        dot_grad = QRadialGradient(0, 0, 1)
        hue_span = 56.0  # 沿 x 轴色相跨度，保持在主题邻域
        plus_mode = QPainter.CompositionMode.CompositionMode_Plus
        src_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        no_pen = Qt.PenStyle.NoPen

        painter.setPen(no_pen)
        for z3d, x3d, val, peak_val, bar_h, peak_h, i in sorted_bars:
            fl_sx, fl_sy, fl_d, fl_sc = proj(x3d, grid_y_base, z3d)
            fr_sx, fr_sy, _, _ = proj(x3d + bar_width_3d, grid_y_base, z3d)
            tl_sx, tl_sy, _, _ = proj(x3d, grid_y_base + bar_h, z3d)
            tr_sx, tr_sy, _, _ = proj(x3d + bar_width_3d, grid_y_base + bar_h, z3d)
            bl_sx, bl_sy, _, _ = proj(x3d, grid_y_base, z3d + bar_width_3d * 0.5)
            br_sx, br_sy, _, _ = proj(x3d + bar_width_3d, grid_y_base, z3d + bar_width_3d * 0.5)
            btl_sx, btl_sy, _, _ = proj(x3d, grid_y_base + bar_h, z3d + bar_width_3d * 0.5)
            btr_sx, btr_sy, _, _ = proj(x3d + bar_width_3d, grid_y_base + bar_h, z3d + bar_width_3d * 0.5)

            fog = self._depth_fog(fl_sc, 0.55, 0.18)
            hue_i = hue0 + ((x3d - grid_x_start) / (grid_x_end - grid_x_start) - 0.5) * hue_span
            hue_i_i = int(hue_i) % 360
            bright = 150.0 + val * 105.0  # 亮度随电平呼吸

            # ---- 地面反射：y 镜像 + 向下渐隐 ----
            if val > 0.08:
                mtl_sx, mtl_sy, _, _ = proj(x3d, grid_y_base - bar_h, z3d)
                mtr_sx, mtr_sy, _, _ = proj(x3d + bar_width_3d, grid_y_base - bar_h, z3d)
                refl_grad.setStart(fl_sx, fl_sy)
                refl_grad.setFinalStop(mtl_sx, mtl_sy)
                c_refl.setHsv(hue_i_i, 200, int(bright * 0.85), int(75 * fog * min(1.0, val * 1.5)))
                refl_grad.setColorAt(0, c_refl)
                c_refl.setAlpha(0)
                refl_grad.setColorAt(1, c_refl)
                painter.setBrush(QBrush(refl_grad))
                painter.drawPolygon(QPolygonF([
                    QPointF(fl_sx, fl_sy), QPointF(fr_sx, fr_sy),
                    QPointF(mtr_sx, mtr_sy), QPointF(mtl_sx, mtl_sy),
                ]))

            # ---- 柱体：顶面最亮 / 正面渐变 / 侧面 0.45 倍暗 ----
            c_side.setHsv(hue_i_i, 210, int(bright * 0.45), int(255 * fog))
            painter.setBrush(c_side)
            painter.drawPolygon(QPolygonF([
                QPointF(fr_sx, fr_sy), QPointF(tr_sx, tr_sy),
                QPointF(btr_sx, btr_sy), QPointF(br_sx, br_sy),
            ]))

            c_top.setHsv(hue_i_i, 80, 255, int(235 * fog))
            painter.setBrush(c_top)
            painter.drawPolygon(QPolygonF([
                QPointF(tl_sx, tl_sy), QPointF(tr_sx, tr_sy),
                QPointF(btr_sx, btr_sy), QPointF(btl_sx, btl_sy),
            ]))

            c_fhi.setHsv(hue_i_i, 170, min(255, int(bright * 1.15)), int(245 * fog))
            c_flo.setHsv(hue_i_i, 220, int(bright * 0.55), int(245 * fog))
            front_grad.setStart(fl_sx, tl_sy)
            front_grad.setFinalStop(fl_sx, fl_sy)
            front_grad.setColorAt(0, c_fhi)
            front_grad.setColorAt(1, c_flo)
            painter.setBrush(QBrush(front_grad))
            front_poly = QPolygonF([
                QPointF(fl_sx, fl_sy), QPointF(fr_sx, fr_sy),
                QPointF(tr_sx, tr_sy), QPointF(tl_sx, tl_sy),
            ])
            painter.drawPolygon(front_poly)

            # ---- 峰值帽 ----
            if peak_val > 0.02:
                pk_y = grid_y_base + peak_h
                pfl_sx, pfl_sy, _, _ = proj(x3d, pk_y, z3d)
                pfr_sx, pfr_sy, _, _ = proj(x3d + bar_width_3d, pk_y, z3d)
                pbtl_sx, pbtl_sy, _, _ = proj(x3d, pk_y, z3d + bar_width_3d * 0.5)
                pbtr_sx, pbtr_sy, _, _ = proj(x3d + bar_width_3d, pk_y, z3d + bar_width_3d * 0.5)
                c_peak.setHsv(hue_i_i, 55, 255, int(220 * fog))
                painter.setBrush(c_peak)
                painter.drawPolygon(QPolygonF([
                    QPointF(pfl_sx, pfl_sy), QPointF(pfr_sx, pfr_sy),
                    QPointF(pbtr_sx, pbtr_sy), QPointF(pbtl_sx, pbtl_sy),
                ]))

            # ---- additive 辉光：正面低透明度叠加 + 顶部光斑（圆角顶高光）----
            if val > 0.1:
                painter.setCompositionMode(plus_mode)
                if val > 0.18:
                    c_glow.setHsv(hue_i_i, 150, 255, int((26 + val * 64) * fog))
                    painter.setBrush(c_glow)
                    painter.drawPolygon(front_poly)
                top_cx = (tl_sx + tr_sx) * 0.5
                top_cy = (tl_sy + tr_sy) * 0.5
                dot_r = max(2.0, (2.0 + val * 7.0) * fl_sc)
                dot_grad.setCenter(top_cx, top_cy)
                dot_grad.setFocalPoint(top_cx, top_cy)
                dot_grad.setRadius(dot_r)
                c_glow.setHsv(hue_i_i, 60, 255, int(210 * fog * min(1.0, val * 2.0)))
                dot_grad.setColorAt(0, c_glow)
                c_glow.setHsv(hue_i_i, 160, 255, 0)
                dot_grad.setColorAt(1, c_glow)
                painter.setBrush(QBrush(dot_grad))
                painter.drawEllipse(QPointF(top_cx, top_cy), dot_r, dot_r)
                painter.setCompositionMode(src_mode)

    def _paint_waves(self, painter, w, h):
        n = len(self._wave_left)
        if n < 2:
            return
        smooth = self._smooth_bars
        bass = float(np.mean(smooth[:8])) if len(smooth) > 0 else 0.0
        mid = float(np.mean(smooth[8:30])) if len(smooth) > 30 else 0.0
        hue0 = self._theme_hue(20.0)
        pitch = 0.45
        proj = lambda x, y, z: _project_3d(x, y, z, w, h, pitch=pitch)
        painter.setPen(Qt.PenStyle.NoPen)

        # 中央柔光底色，随 bass 呼吸
        glow = QRadialGradient(w / 2, h / 2, min(w, h) * 0.52)
        glow.setColorAt(0, self._hsv(hue0, 190, 255, int(14 + bass * 38)))
        glow.setColorAt(0.55, self._hsv(hue0 + 30, 220, 160, 6))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.drawRect(QRectF(0, 0, w, h))

        plus_mode = QPainter.CompositionMode.CompositionMode_Plus
        src_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        t = self._frame_count / 60.0
        step = max(1, n // 72)
        # 多条半透明正弦绸带：层间色相差 20°，垂直起伏随 mid，纵深递进
        for li in range(4):
            hue_li = hue0 + li * 20.0
            z_base = -0.7 + li * 0.55
            amp_scale = 1.55 - li * 0.18
            y_drift = math.sin(t * 0.8 + li * 1.3) * (0.12 + mid * 0.55)
            pts = []
            for si in range(0, n, step):
                x3d = -3.5 + 7.0 * si / (n - 1)
                amp = float(self._wave_left[si]) * amp_scale
                sx, sy, _, _ = proj(x3d, -0.55 + y_drift + amp, z_base)
                pts.append(QPointF(sx, sy))
            if len(pts) < 2:
                continue
            poly = QPolygonF(pts)

            # additive 光晕线（6-10px 递增）
            painter.setCompositionMode(plus_mode)
            halo_pen = QPen(self._hsv(hue_li, 170, 255, int(20 + bass * 46)),
                            6.0 + li * 1.3,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin)
            painter.setPen(halo_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(poly)

            # 主体 2.5px 渐变描边（色相 → 近白高光）
            painter.setCompositionMode(src_mode)
            line_grad = QLinearGradient(pts[0].x(), 0, pts[-1].x(), 0)
            line_grad.setColorAt(0, self._hsv(hue_li, 195, 255, 230))
            line_grad.setColorAt(0.5, self._hsv(hue_li + 14, 55, 255, 255))
            line_grad.setColorAt(1, self._hsv(hue_li, 150, 235, 200))
            line_pen = QPen(QBrush(line_grad), 2.5,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin)
            painter.setPen(line_pen)
            painter.drawPolyline(poly)
        painter.setPen(Qt.PenStyle.NoPen)

    def _paint_circular(self, painter, w, h):
        bars = self._smooth_bars
        peaks = self._peak_bars
        n = len(bars)
        bass = float(np.mean(bars[:8]))
        hue0 = self._theme_hue(-25.0)
        cx, cy = w / 2, h / 2
        pitch = 0.5
        proj = lambda x, y, z: _project_3d(x, y, z, w, h, pitch=pitch)
        ring_radius = 2.0
        ring_y = 0.0

        painter.setPen(Qt.PenStyle.NoPen)
        # 地面柔光
        floor_grad = QRadialGradient(cx, cy + h * 0.06, min(w, h) * 0.42)
        floor_grad.setColorAt(0, self._hsv(hue0, 200, 255, int(10 + bass * 42)))
        floor_grad.setColorAt(1, QColor(5, 5, 10, 0))
        painter.setBrush(QBrush(floor_grad))
        painter.drawRect(QRectF(0, 0, w, h))

        # 闭合平滑径向频谱曲线：64 点投影，半径随频谱起伏（相邻平均去毛刺）
        edge_pts = []
        peak_marks = []
        for i in range(n):
            angle = i * 2 * math.pi / n
            v = (bars[i] + bars[(i + 1) % n]) * 0.5
            r = ring_radius * (0.60 + 0.42 * v)
            sx, sy, _, _ = proj(r * math.cos(angle), ring_y, r * math.sin(angle))
            edge_pts.append(QPointF(sx, sy))
            pv = (peaks[i] + peaks[(i + 1) % n]) * 0.5
            if pv > 0.12:
                pr = ring_radius * (0.60 + 0.42 * pv)
                peak_marks.append((angle, pr))
        if len(edge_pts) < 3:
            return
        edge_poly = QPolygonF(edge_pts)

        # 内圈柔光填充（径向渐变：中心透明 → 边缘主题色）
        inner_grad = QRadialGradient(cx, cy, min(w, h) * 0.36)
        inner_grad.setColorAt(0.0, QColor(5, 5, 10, 0))
        inner_grad.setColorAt(0.72, self._hsv(hue0, 180, 200, 20))
        inner_grad.setColorAt(1.0, self._hsv(hue0, 190, 255, 85))
        painter.setBrush(QBrush(inner_grad))
        painter.drawPolygon(edge_poly)

        # 外圈 additive 光晕（双层递减 alpha / 递增笔宽）
        plus_mode = QPainter.CompositionMode.CompositionMode_Plus
        src_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        painter.setCompositionMode(plus_mode)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        halo_a = int(24 + bass * 52)
        painter.setPen(QPen(self._hsv(hue0, 160, 255, halo_a), 8.0,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolygon(edge_poly)
        painter.setPen(QPen(self._hsv(hue0 + 15, 110, 255, min(255, halo_a * 2)), 3.5,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolygon(edge_poly)

        # 峰值点光斑粒子
        c_dot = QColor()
        for angle, pr in peak_marks:
            sx, sy, _, sc = proj(pr * math.cos(angle), ring_y, pr * math.sin(angle))
            r = max(2.0, 3.2 * sc)
            dot = QRadialGradient(sx, sy, r)
            c_dot.setHsv(int(hue0) % 360, 60, 255, 150)
            dot.setColorAt(0, c_dot)
            c_dot.setHsv(int(hue0) % 360, 180, 255, 0)
            dot.setColorAt(1, c_dot)
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(QPointF(sx, sy), r, r)
        painter.setCompositionMode(src_mode)

        # 主体描边：锥形渐变（沿环同一色彩语言内扫动）
        conic = QConicalGradient(cx, cy, 90.0)
        conic.setColorAt(0.0, self._hsv(hue0, 150, 255, 240))
        conic.setColorAt(0.33, self._hsv(hue0 + 55, 190, 255, 255))
        conic.setColorAt(0.66, self._hsv(hue0 - 45, 170, 250, 255))
        conic.setColorAt(1.0, self._hsv(hue0, 150, 255, 240))
        painter.setPen(QPen(QBrush(conic), 2.2,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(edge_poly)
        painter.setPen(Qt.PenStyle.NoPen)

        # 中央天体辉光（随 bass 脉动）
        core_sx, core_sy, _, core_sc = proj(0, ring_y, 0)
        core_r = max(4, 13 * core_sc)
        core_grad = QRadialGradient(core_sx, core_sy, core_r * 4)
        core_grad.setColorAt(0, QColor(240, 245, 255, int(110 + bass * 125)))
        core_grad.setColorAt(0.25, self._hsv(hue0, 150, 255, int(55 + bass * 70)))
        core_grad.setColorAt(1, self._hsv(hue0, 200, 200, 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(core_sx, core_sy), core_r * 4, core_r * 4)

    def _paint_terrain(self, painter, w, h):
        bars = self._smooth_bars
        n = len(bars)
        bass = float(np.mean(bars[:8]))
        mid = float(np.mean(bars[8:30]))
        phase = self._terrain_phase
        pitch = 0.55
        # 相机缓慢漂移：yaw 正弦摆动（峰值角速度 ~0.05 rad/s），连续无跳变
        t = self._frame_count / 60.0
        yaw = 0.12 * math.sin(t * 0.42)
        hue0 = self._theme_hue(10.0)

        grid_x = np.linspace(-4, 4, n)
        grid_z = np.linspace(-3.2, 3.2, 22)
        # 高度图：频谱 + 连续波纹
        height_map = []
        for zi, z in enumerate(grid_z):
            row = []
            for xi, x in enumerate(grid_x):
                freq_idx = min(xi, n - 1)
                h_val = bars[freq_idx] * 2.5
                h_val += math.sin(x * 0.8 + phase) * 0.3 * (1 + bass)
                h_val += math.cos(z * 0.6 + phase * 0.7) * 0.2 * (1 + mid)
                h_val += math.sin(x * 1.5 + z * 1.2 + phase * 1.3) * 0.15
                row.append(h_val)
            height_map.append(row)

        # 预投影 + 每行雾化系数（z 越大越远，向背景色雾化）
        rows_count = len(grid_z)
        proj_rows = []
        for zi in range(rows_count):
            fog_row = 1.0 - (zi / (rows_count - 1)) * 0.72
            row_pts = []
            for xi in range(n):
                sx, sy, _, _ = _project_3d(float(grid_x[xi]), height_map[zi][xi], float(grid_z[zi]),
                                           w, h, pitch=pitch, yaw=yaw)
                row_pts.append((sx, sy, height_map[zi][xi]))
            proj_rows.append((row_pts, fog_row))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        line_pen = QPen()
        line_pen.setWidthF(1.0)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        c_line = QColor()

        # 行线（沿 x）：颜色按行内峰值高度映射（低=深蓝紫，高=亮青白）
        for row_pts, fog_row in proj_rows:
            v_max = 0.0
            for _, _, h_val in row_pts:
                v = (h_val + 0.5) / 3.2
                if v > v_max:
                    v_max = v
            if v_max > 1.0:
                v_max = 1.0
            elif v_max < 0.0:
                v_max = 0.0
            c_line.setHsv(int(hue0 + 22 - v_max * 42) % 360,
                          int(200 - v_max * 150),
                          int(105 + v_max * 150),
                          int((70 + v_max * 120) * fog_row))
            line_pen.setColor(c_line)
            painter.setPen(line_pen)
            painter.drawPolyline(QPolygonF([QPointF(p[0], p[1]) for p in row_pts]))

        # 列线（沿 z，隔 5 列）：低亮度衬托，随距离雾化
        c_line.setHsv(int(hue0 + 8) % 360, 190, 140, 40)
        line_pen.setColor(c_line)
        painter.setPen(line_pen)
        for xi in range(0, n, 5):
            painter.drawPolyline(QPolygonF([
                QPointF(proj_rows[zi][0][xi][0], proj_rows[zi][0][xi][1])
                for zi in range(rows_count)
            ]))

        # 峰值行加光：高处顶点 additive 光斑
        plus_mode = QPainter.CompositionMode.CompositionMode_Plus
        painter.setCompositionMode(plus_mode)
        painter.setPen(Qt.PenStyle.NoPen)
        c_dot = QColor()
        for row_pts, fog_row in proj_rows:
            for xi in range(0, n, 4):
                sx, sy, h_val = row_pts[xi]
                v = (h_val + 0.5) / 3.2
                if v < 0.55:
                    continue
                r = 2.0 + v * 3.5
                dot = QRadialGradient(sx, sy, r)
                c_dot.setHsv(int(hue0 - 10) % 360, 40, 255, int(150 * v * fog_row))
                dot.setColorAt(0, c_dot)
                c_dot.setAlpha(0)
                dot.setColorAt(1, c_dot)
                painter.setBrush(QBrush(dot))
                painter.drawEllipse(QPointF(sx, sy), r, r)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _paint_cosmos(self, painter, w, h):
        bars = self._smooth_bars
        bass = float(np.mean(bars[:8]))
        mid = float(np.mean(bars[8:30]))
        high = float(np.mean(bars[30:]))
        cx, cy = w / 2, h / 2
        pitch = 0.35
        proj = lambda x, y, z: _project_3d(x, y, z, w, h, pitch=pitch)
        hue0 = self._theme_hue(35.0)
        plus_mode = QPainter.CompositionMode.CompositionMode_Plus
        src_mode = QPainter.CompositionMode.CompositionMode_SourceOver
        painter.setPen(Qt.PenStyle.NoPen)

        # 星云底色：3 个大径向渐变叠加，随色相漂移、随 bass/mid 呼吸
        # 辅助星云按各自包围盒局部绘制，减少全屏渐变填充开销
        span = max(w, h)
        neb1 = QRadialGradient(cx, cy * 0.92, span * 0.58)
        neb1.setColorAt(0, self._hsv(hue0, 180, 255, int(12 + bass * 28)))
        neb1.setColorAt(0.55, self._hsv(hue0 + 40, 190, 210, 8))
        neb1.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(neb1))
        painter.drawRect(QRectF(0, 0, w, h))
        neb2_r = span * 0.36
        neb2_x = cx - w * 0.3
        neb2_y = cy * 1.18
        neb2 = QRadialGradient(neb2_x, neb2_y, neb2_r)
        neb2.setColorAt(0, self._hsv(hue0 - 35, 200, 220, int(9 + mid * 18)))
        neb2.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(neb2))
        painter.drawRect(QRectF(neb2_x - neb2_r, neb2_y - neb2_r, neb2_r * 2, neb2_r * 2))
        neb3_r = span * 0.34
        neb3_x = cx + w * 0.32
        neb3_y = cy * 0.72
        neb3 = QRadialGradient(neb3_x, neb3_y, neb3_r)
        neb3.setColorAt(0, self._hsv(hue0 + 55, 190, 230, int(8 + high * 16)))
        neb3.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(neb3))
        painter.drawRect(QRectF(neb3_x - neb3_r, neb3_y - neb3_r, neb3_r * 2, neb3_r * 2))

        # 视差星空：远层（z<-3）随旋转以 2.4 倍角速度移动，形成两层视差
        rot_near = self._cosmos_rotation
        rot_far = self._cosmos_rotation * 2.4
        pt_grad = QRadialGradient(0, 0, 1)  # 复用的粒子径向渐变
        for s in self._cosmos_bg_stars:
            is_far = s['z'] < -3.0
            rot = rot_far if is_far else rot_near
            cos_r = math.cos(rot)
            sin_r = math.sin(rot)
            rx = s['x'] * cos_r - s['z'] * sin_r
            rz = s['x'] * sin_r + s['z'] * cos_r
            sx, sy, depth, scale = proj(rx, s['y'], rz)
            if not (0 <= sx <= w and 0 <= sy <= h):
                continue
            brightness = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(s['twinkle']))
            fog = self._depth_fog(scale, 0.4, 0.2)
            alpha = int(brightness * 200 * fog)
            screen_size = max(1, s['size'] * scale * 40)
            star_hue = hue0 - 15 if is_far else hue0 + 5
            pt_grad.setCenter(sx, sy)
            pt_grad.setFocalPoint(sx, sy)
            pt_grad.setRadius(screen_size * 2)
            pt_grad.setColorAt(0, QColor(255, 255, 255, int(alpha * 0.85)))
            pt_grad.setColorAt(0.35, self._hsv(star_hue, 90, 255, alpha))
            pt_grad.setColorAt(1, self._hsv(star_hue, 150, 220, 0))
            painter.setBrush(QBrush(pt_grad))
            painter.drawEllipse(QPointF(sx, sy), screen_size * 2, screen_size * 2)

        # 中央天体辉光：随 bass 脉动
        core_sx, core_sy, core_d, core_sc = proj(0, 0, 0)
        core_r = max(5, 18 * core_sc)
        core_grad = QRadialGradient(core_sx, core_sy, core_r * 5)
        core_grad.setColorAt(0, QColor(245, 248, 255, int(140 + bass * 115)))
        core_grad.setColorAt(0.12, self._hsv(hue0, 90, 255, int(100 + bass * 90)))
        core_grad.setColorAt(0.35, self._hsv(hue0 + 20, 160, 230, int(35 + bass * 55)))
        core_grad.setColorAt(1, self._hsv(hue0 + 10, 190, 150, 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(core_sx, core_sy), core_r * 5, core_r * 5)

        # 螺旋臂尘埃点：色相锁定主题邻域
        spiral_arms = 4
        for arm in range(spiral_arms):
            arm_angle = self._cosmos_rotation * 2 + arm * 2 * math.pi / spiral_arms
            for seg in range(25):
                t = seg / 25.0
                r = 0.3 + t * 3.0
                a = arm_angle + t * 3.5
                x3d = r * math.cos(a)
                z3d = r * math.sin(a)
                y3d = (math.sin(a * 2 + t * 4) * 0.3) * (1 - t * 0.5)
                sx, sy, d, sc = proj(x3d, y3d, z3d)
                if not (-20 <= sx <= w + 20 and -20 <= sy <= h + 20):
                    continue
                arm_val = bass * (1.0 - t * 0.6)
                dot_size = max(1, (0.04 + arm_val * 0.12) * sc * 30)
                hue = hue0 + arm * 14 + t * 40 - 20
                fog = self._depth_fog(sc, 0.4, 0.2)
                alpha = int((30 + arm_val * 150) * fog * (1.0 - t * 0.6))
                pt_grad.setCenter(sx, sy)
                pt_grad.setFocalPoint(sx, sy)
                pt_grad.setRadius(dot_size * 2)
                pt_grad.setColorAt(0, QColor(255, 255, 255, int(alpha * 0.5)))
                pt_grad.setColorAt(0.3, self._hsv(hue, 160, 255, alpha))
                pt_grad.setColorAt(1, self._hsv(hue, 180, 200, 0))
                painter.setBrush(QBrush(pt_grad))
                painter.drawEllipse(QPointF(sx, sy), dot_size * 2, dot_size * 2)

        # 能量粒子（hue 已在 update 中主题化）
        for p in self._cosmos_particles:
            alpha = int(p['life'] * 200)
            sx, sy, d, sc = proj(p['x'], p['y'], p['z'])
            if not (-20 <= sx <= w + 20 and -20 <= sy <= h + 20):
                continue
            fog = self._depth_fog(sc, 0.4, 0.2)
            alpha = int(alpha * fog)
            if alpha < 4:
                continue
            screen_size = max(1, p['size'] * sc * 30)
            pt_grad.setCenter(sx, sy)
            pt_grad.setFocalPoint(sx, sy)
            pt_grad.setRadius(screen_size * 1.5)
            pt_grad.setColorAt(0, QColor(255, 255, 255, int(alpha * 0.4)))
            pt_grad.setColorAt(0.4, self._hsv(p['hue'], 180, 255, alpha))
            pt_grad.setColorAt(1, self._hsv(p['hue'], 200, 200, 0))
            painter.setBrush(QBrush(pt_grad))
            painter.drawEllipse(QPointF(sx, sy), screen_size * 1.5, screen_size * 1.5)

        # 流星：柔化拖尾（外层宽 additive 光晕 + 内层亮核），色相主题化
        for m in self._cosmos_meteors:
            alpha = int(m['life'] * 220)
            sx, sy, d, sc = proj(m['x'], m['y'], m['z'])
            tail_x = m['x'] - m['vx'] / (abs(m['vx']) + abs(m['vz']) + 0.01) * m['len']
            tail_z = m['z'] - m['vz'] / (abs(m['vx']) + abs(m['vz']) + 0.01) * m['len']
            tsx, tsy, _, _ = proj(tail_x, m['y'], tail_z)
            fog = self._depth_fog(sc, 0.4, 0.3)
            grad = QLinearGradient(tsx, tsy, sx, sy)
            grad.setColorAt(0, self._hsv(m['hue'], 120, 255, 0))
            grad.setColorAt(0.7, self._hsv(m['hue'], 100, 255, int(alpha * 0.5 * fog)))
            grad.setColorAt(1, QColor(245, 248, 255, int(alpha * fog)))
            painter.setCompositionMode(plus_mode)
            soft_pen = QPen(QBrush(grad), max(2.5, 5.0 * fog))
            soft_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(soft_pen)
            painter.drawLine(QPointF(tsx, tsy), QPointF(sx, sy))
            painter.setCompositionMode(src_mode)
            core_pen = QPen(QBrush(grad), max(1.0, 1.6 * fog))
            core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(core_pen)
            painter.drawLine(QPointF(tsx, tsy), QPointF(sx, sy))
            painter.setPen(Qt.PenStyle.NoPen)

    def _paint_fluid(self, painter, w, h):
        bars = self._smooth_bars
        bass = float(np.mean(bars[:8]))
        mid = float(np.mean(bars[8:30]))
        high = float(np.mean(bars[30:]))
        cx, cy = w / 2, h / 2
        phase = self._fluid_phase
        hue = self._fluid_hue

        if self._fluid_buf is None or self._fluid_buf_w != w or self._fluid_buf_h != h:
            self._fluid_buf = QImage(w, h, QImage.Format.Format_ARGB32)
            self._fluid_buf.fill(QColor(0, 0, 0, 0))
            self._fluid_buf_w = w
            self._fluid_buf_h = h

        fade_painter = QPainter(self._fluid_buf)
        fade_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        fade_alpha = max(8, min(40, int(12 + (bass + mid) * 15)))
        fade_painter.fillRect(0, 0, w, h, QColor(0, 0, 0, fade_alpha))
        fade_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        fade_painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        n = len(bars)
        hue_half_span = n * 0.7  # 粒子色相跨度 ±45° 左右，锁定主题邻域
        for i in range(n):
            val = bars[i]
            if val < 0.02:
                continue
            angle = phase + i * 0.15 + math.sin(phase * 0.7 + i * 0.05) * 2
            x3d = math.cos(angle) * (0.5 + val * 2.0) * 0.3
            y3d = math.sin(phase * 0.3 + i * 0.1) * val * 0.5
            z3d = math.sin(angle) * (0.5 + val * 2.0) * 0.3
            pitch = 0.45
            proj = lambda x, y, z: _project_3d(x, y, z, w, h, pitch=pitch)
            sx, sy, d, sc = proj(x3d, y3d, z3d)
            if not (-30 <= sx <= w + 30 and -30 <= sy <= h + 30):
                continue
            depth_fade = max(0.3, min(1.0, sc * 0.4))
            size = max(2, (3 + val * 15) * depth_fade)
            bar_hue = int(hue + (i - n / 2) / hue_half_span * 45) % 360
            alpha = int(val * 200 * depth_fade)
            grad = QRadialGradient(sx - size * 0.15, sy - size * 0.15, size * 1.5)
            grad.setColorAt(0, QColor(245, 248, 255, int(alpha * 0.4)))
            grad.setColorAt(0.3, QColor.fromHsv(bar_hue, 180, 255, alpha))
            grad.setColorAt(0.7, QColor.fromHsv(bar_hue, 200, 220, int(alpha * 0.4)))
            grad.setColorAt(1, QColor.fromHsv(bar_hue, 220, 180, 0))
            fade_painter.setPen(Qt.PenStyle.NoPen)
            fade_painter.setBrush(QBrush(grad))
            fade_painter.drawEllipse(QRectF(sx - size * 1.5, sy - size * 1.5, size * 3, size * 3))

        for layer in range(3):
            prev = None
            line_hue = int(hue + (layer - 1) * 20) % 360
            line_color = QColor.fromHsv(line_hue, 150, 255, int((40 + bass * 80)))
            line_pen = QPen(line_color, (2 + bass * 3))
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            fade_painter.setPen(line_pen)
            for xi in range(0, w + 12, 12):
                dist_from_center = abs(xi - cx) / (w / 2)
                depth_fade = max(0.3, 1.0 - dist_from_center * 0.5)
                wave = math.sin(xi * 0.006 + phase + layer * 1.2) * 40 * depth_fade * (1 + bass)
                wave += math.sin(xi * 0.013 + phase * 1.5 + layer * 0.8) * 15 * depth_fade * (1 + mid)
                y = h * (0.3 + layer * 0.15) + wave
                if prev is not None:
                    fade_painter.drawLine(int(prev[0]), int(prev[1]), int(xi), int(y))
                prev = (xi, y)

        # 边缘 vignette 淡出：每帧在缓冲上叠加边缘向背景色的渐变，使拖尾向四周柔和消散
        edge_grad = QRadialGradient(cx, cy, math.hypot(cx, cy))
        edge_grad.setColorAt(0, QColor(5, 5, 10, 0))
        edge_grad.setColorAt(0.62, QColor(5, 5, 10, 0))
        edge_grad.setColorAt(1, QColor(5, 5, 10, 22))
        fade_painter.setPen(Qt.PenStyle.NoPen)
        fade_painter.setBrush(QBrush(edge_grad))
        fade_painter.drawRect(QRectF(0, 0, w, h))

        fade_painter.end()
        painter.drawImage(0, 0, self._fluid_buf)

    def _paint_ripple(self, painter, w, h):
        """粒子震荡洞洞波渲染：侧视轴线壳串 + 预渲染粒子贴图（高密度低开销）。"""
        bass = float(np.mean(self._smooth_bars[:8]))
        high = float(np.mean(self._smooth_bars[30:]))
        pulse = self._ripple_pulse
        base_hue = int(self._ripple_hue) % 360
        cam_x = self._ripple_cam_x
        now = self._ripple_time
        # 光核固定在屏幕左中位置，壳串向右延伸
        core_sx = w * 0.16
        core_cy = h * 0.5 + math.sin(now * 0.23) * h * 0.02  # 轻微上下漂移
        scale = h * 0.21  # 世界单位→屏幕缩放
        fp = 4.2 + 0.5 * math.sin(now * 0.045)  # 相机距离呼吸（推拉感，长焦弱透视）
        # 摄像机全向漂移视角（yaw 改变深度 + pitch 把深度转为垂直位移，
        # 两者耦合 = 相机绕场景飞行，轴线远端随视角明显摆动）
        yaw = 0.45 * math.sin(now * 0.083) + 0.20 * math.sin(now * 0.037 + 2.0)
        pitch = 0.50 * math.sin(now * 0.061 + 1.3) + 0.18 * math.sin(now * 0.026)
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        def proj(x, y, z):
            rx = x - cam_x
            x1 = rx * cos_y + z * sin_y
            z1 = -rx * sin_y + z * cos_y
            y2 = y * cos_p - z1 * sin_p
            z2 = y * sin_p + z1 * cos_p
            persp = fp / (fp + z2)
            return core_sx + x1 * scale * persp, core_cy - y2 * scale * persp, persp

        # 粒子辉光贴图（青/蓝/白 三档预渲染，drawPixmap 高效绘制海量小粒子）
        if not self._ripple_sprites:
            for key, hue_s in (('cyan', 187), ('mid', 205), ('blue', 225)):
                pm = QPixmap(20, 20)
                pm.fill(Qt.GlobalColor.transparent)
                g = QRadialGradient(10, 10, 10)
                g.setColorAt(0.0, QColor(255, 255, 255, 235))
                g.setColorAt(0.30, QColor.fromHsv(hue_s, 130, 255, 215))
                g.setColorAt(0.65, QColor.fromHsv(hue_s, 160, 235, 70))
                g.setColorAt(1.0, QColor.fromHsv(hue_s, 170, 220, 0))
                p2 = QPainter(pm)
                p2.setBrush(QBrush(g))
                p2.setPen(Qt.PenStyle.NoPen)
                p2.drawEllipse(0, 0, 20, 20)
                p2.end()
                self._ripple_sprites[key] = pm

        def sprite_for(hue_v):
            if hue_v < 198:
                return self._ripple_sprites['cyan']
            if hue_v < 216:
                return self._ripple_sprites['mid']
            return self._ripple_sprites['blue']

        painter.setPen(Qt.PenStyle.NoPen)
        full_rect = QRectF(0, 0, 20, 20)

        # 1. 远景星空（很暗的点缀，几乎隐入黑底）
        for p in self._ripple_bg_particles:
            sx, sy, persp = proj(p['x'], p['y'], p['z'])
            if not (-20 <= sx <= w + 20 and -20 <= sy <= h + 20):
                continue
            brightness = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(p['twinkle']))
            painter.setOpacity(min(1.0, brightness * 0.20 * (1.0 + high * 0.4)))
            size = max(1.2, p['size'] * persp * 7.0)
            painter.drawPixmap(QRectF(sx - size, sy - size, size * 2, size * 2),
                               sprite_for(int(p['hue']) % 360), full_rect)
        painter.setOpacity(1.0)

        # 2. 轴线光带：核心向右延伸的渐变亮线（Optical Flares 横向 streak 质感）
        tx, ty, _ = proj(cam_x + 6.0, 0, 0)
        axis_grad = QLinearGradient(core_sx, core_cy, tx, ty)
        axis_grad.setColorAt(0.0, QColor(240, 255, 255, 200))
        axis_grad.setColorAt(0.25, QColor.fromHsv(187, 120, 255, 130))
        axis_grad.setColorAt(0.7, QColor.fromHsv(215, 160, 255, 55))
        axis_grad.setColorAt(1.0, QColor.fromHsv(225, 170, 255, 0))
        glow_pen = QPen(QBrush(axis_grad), max(2.0, h * 0.010 + pulse * h * 0.008))
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(glow_pen)
        painter.setOpacity(0.35)
        painter.drawLine(QPointF(core_sx, core_cy), QPointF(tx, ty))
        fine_pen = QPen(QBrush(axis_grad), max(1.0, h * 0.0035))
        fine_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fine_pen)
        painter.setOpacity(0.85)
        painter.drawLine(QPointF(core_sx, core_cy), QPointF(tx, ty))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(1.0)

        # 3. 轴线微粒（核心洒落，沿水平光带闪烁）
        for p in self._ripple_dust:
            sx, sy, persp = proj(p['x'], p['y'], p['z'])
            if not (-30 <= sx <= w + 30 and -30 <= sy <= h + 30):
                continue
            life_fade = 1.0 - p['age'] / p['life']
            op = 0.5 * life_fade
            if op < 0.03:
                continue
            painter.setOpacity(op)
            size = max(1.2, 0.022 * scale * persp * p['size_f'])
            painter.drawPixmap(QRectF(sx - size, sy - size, size * 2, size * 2),
                               self._ripple_sprites['cyan'], full_rect)

        # 4. 节拍伞面串：粒子流自锥顶持续喷出（早出的飞得远、晚出的还在锥顶
        # 附近），粒子沿锥面母线连续分布构成伞面（纯粒子，无连线）
        for sh in self._ripple_shells:  # append 顺序即旧→新
            age = now - sh['birth']
            life_ratio = age / sh['life']
            fade = (1.0 - life_ratio) ** 1.6
            shell_hue = 187.0 + life_ratio * 40.0  # 新青白 → 老深蓝
            pm = sprite_for(int(shell_hue))
            bright = (0.60 + 0.40 * (1.0 - life_ratio)) * (0.85 + bass * 0.35)
            flash = 1.0 + 1.2 * math.exp(-age * 10.0)  # 爆出瞬间闪光
            tau = sh['tau']
            sh_x = sh['x']
            for (ux, uy, uz, v, size_f, p_birth) in sh['pts']:
                age_i = now - p_birth
                d = v * tau * (1.0 - math.exp(-age_i / tau))  # 各自阻尼飞行距离
                sx, sy, persp = proj(sh_x + ux * d, uy * d, uz * d)
                if not (-30 <= sx <= w + 30 and -30 <= sy <= h + 30):
                    continue
                op = min(1.0, fade * bright * flash * (0.55 + 0.45 * persp))
                if op < 0.03:
                    continue
                painter.setOpacity(op)
                size = max(1.0, 0.019 * scale * persp * size_f)
                painter.drawPixmap(QRectF(sx - size, sy - size, size * 2, size * 2), pm, full_rect)
        painter.setOpacity(1.0)

        # 5. 中心光核（Optical Flares 质感：核心 + 光芒 + 多层辉光，节拍脉冲最亮）
        core_r = max(6.0, h * 0.030)
        # 光芒线条（随节奏伸长，缓慢旋转）
        num_rays = 10
        ray_length = core_r * (3.0 + pulse * 9.0)
        for i in range(num_rays):
            angle = i * 2 * math.pi / num_rays + self._ripple_phase * 0.3
            x2 = core_sx + math.cos(angle) * ray_length
            y2 = core_cy + math.sin(angle) * ray_length
            ray_alpha = int(50 + pulse * 150)
            ray_grad = QLinearGradient(core_sx, core_cy, x2, y2)
            ray_grad.setColorAt(0, QColor(255, 255, 255, ray_alpha))
            ray_grad.setColorAt(0.3, QColor.fromHsv(base_hue, 120, 255, int(ray_alpha * 0.6)))
            ray_grad.setColorAt(1, QColor.fromHsv(base_hue, 150, 200, 0))
            painter.setPen(QPen(QBrush(ray_grad), max(1.0, 2 + pulse * 3)))
            painter.drawLine(QPointF(core_sx, core_cy), QPointF(x2, y2))
        painter.setPen(Qt.PenStyle.NoPen)
        # 多层光晕（节拍包络驱动：重拍瞬间最亮）
        brightness = 0.45 + pulse * 0.55
        core_grad = QRadialGradient(core_sx, core_cy, core_r * 7)
        core_grad.setColorAt(0, QColor(255, 255, 255, int(min(255, 185 + pulse * 70))))
        core_grad.setColorAt(0.05, QColor(225, 250, 255, int(min(255, 140 + pulse * 105))))
        core_grad.setColorAt(0.2, QColor.fromHsv(120, 140, 255, min(255, int((60 + pulse * 110) * brightness))))
        core_grad.setColorAt(0.5, QColor.fromHsv(base_hue, 180, 200, int((20 + pulse * 45) * brightness)))
        core_grad.setColorAt(1, QColor(20, 30, 80, 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QRectF(core_sx - core_r * 7, core_cy - core_r * 7,
                                   core_r * 14, core_r * 14))
        # 亮白内核
        core_grad2 = QRadialGradient(core_sx, core_cy, core_r)
        core_grad2.setColorAt(0, QColor(255, 255, 255, 250))
        core_grad2.setColorAt(0.6, QColor(230, 252, 255, 160))
        core_grad2.setColorAt(1, QColor.fromHsv(base_hue, 100, 255, 0))
        painter.setBrush(QBrush(core_grad2))
        painter.drawEllipse(QRectF(core_sx - core_r, core_cy - core_r, core_r * 2, core_r * 2))

        # 6. 冲击环：新伞爆出瞬间自光核荡开的亮环（视觉上「震荡从核心发出」）
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for sh in self._ripple_shells:
            age = now - sh['birth']
            if age >= 0.35:
                continue
            rr = age / 0.35
            cx0, cy0, _ = proj(sh['x'], 0.0, 0.0)
            ring_r = core_r * (1.2 + rr * 7.0)
            painter.setOpacity((1.0 - rr) ** 1.5 * (0.35 + pulse * 0.5))
            ring_pen = QPen(QColor(215, 250, 255, 220), max(1.5, h * 0.0035 * (1.0 - rr)))
            painter.setPen(ring_pen)
            painter.drawEllipse(QPointF(cx0, cy0), ring_r, ring_r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setOpacity(1.0)

    def _paint_galaxy(self, painter, w, h):
        """银河俯视图渲染（对照真实星系照片调色）。

        渲染分层：
        0. 背景星空（60 颗固定小星，确定性生成，不随节奏/时间变化）
        1. 环境底光（bass 驱动，暖核 + 蓝臂色系）
        2. 旋臂气体带（沿多圈缠绕对数螺线的连续柔光带，冷蓝白，随图案旋转）
        3. 核球（暖黄白双层柔光，随节奏强烈呼吸）
        4. 星球（臂上冷蓝白 + 近白高光，盘面尘星淡蓝灰；全体亮度随节奏呼吸）
        """
        bars = self._smooth_bars
        bass = float(np.mean(bars[:8]))
        mid = float(np.mean(bars[8:30]))
        high = float(np.mean(bars[30:]))
        cx = w / 2
        # 中心点带轻微上下浮动（呼吸感）
        cy = h / 2 + math.sin(self._galaxy_time * 0.28) * h * 0.018
        rx = w * 0.40
        ry = h * 0.30
        now = self._galaxy_time
        # 真实星系照片配色：暖黄白核球 / 冷蓝白旋臂 / 淡蓝灰盘面尘星
        warm = self._hsv(42.0, 100, 255)                        # 暖黄白（核球）
        arm_blue = self._hsv(self._theme_hue(-35.0), 120, 255)  # 冷蓝白（臂，主题色相偏 -35）
        dust = self._hsv(215.0, 60, 170)                        # 盘面尘星 淡蓝灰
        star_white = QColor(255, 252, 244)                      # 近白高光
        painter.setPen(Qt.PenStyle.NoPen)

        # 0. 背景星空：约 60 颗固定小星（_galaxy_rand 确定性生成，不随节奏/时间变化，最先绘制）
        if not self._galaxy_bg_stars:
            for k in range(1, 61):
                self._galaxy_bg_stars.append((
                    _galaxy_rand(k * 91.3),
                    _galaxy_rand(k * 37.7),
                    0.5 + _galaxy_rand(k * 53.9) * 0.7,
                    int(15 + _galaxy_rand(k * 17.9) * 30),
                ))
        star_col = QColor(215, 225, 245)
        for nx, ny, sr, sa in self._galaxy_bg_stars:
            x = nx * w
            y = ny * h
            star_col.setAlpha(sa)
            painter.setBrush(star_col)
            painter.drawEllipse(QRectF(x - sr, y - sr, sr * 2, sr * 2))

        # 1. 中心径向光晕（bass 驱动亮度，暖核 + 蓝臂环境底光）
        aura_radius = max(w, h) * 0.50
        aura = QRadialGradient(cx, cy, aura_radius)
        aura_alpha_core = int(14 + bass * 38)
        aura_alpha_mid = int(10 + mid * 18)
        aura.setColorAt(0, QColor(255, 246, 228, aura_alpha_core))
        aura.setColorAt(0.34, QColor(arm_blue.red(), arm_blue.green(), arm_blue.blue(), aura_alpha_mid))
        aura.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(aura))
        painter.drawRect(QRectF(0, 0, w, h))

        # 2. 旋臂气体带：沿多圈缠绕对数螺线画连续柔光带（冷蓝白，与粒子锚定角同步旋转）
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        breath = math.sin(now * 0.42) * 3.0  # 全局共享的缓慢呼吸偏移
        pattern_rot = now * 0.020            # 图案旋转角速度（约 5 分钟/圈）
        rib_grad = QRadialGradient(0, 0, 1)  # 复用的气体带径向渐变
        rib_alpha = 0.085 + bass * 0.075     # 节奏驱动气体带亮度（承担臂的连续性）
        c_rib0 = QColor(arm_blue.red(), arm_blue.green(), arm_blue.blue())
        c_rib1 = QColor(arm_blue.red(), arm_blue.green(), arm_blue.blue(), 0)
        min_wh = min(w, h)
        for arm in range(2):
            for k in range(48):
                ring_k = 0.18 + 0.82 * (k / 47.0)
                theta_k = math.log(ring_k * 12.0 + 1.0) / 0.16 + arm * math.pi + pattern_rot
                xk = cx + math.cos(theta_k) * rx * ring_k
                yk = cy + math.sin(theta_k) * ry * ring_k * (0.55 + 0.43 * ring_k) + breath
                rk = min_wh * (0.010 + 0.020 * ring_k)
                a_k = int(rib_alpha * (0.72 + 0.28 * math.sin(k * 0.7)) * 255)
                rib_grad.setCenter(xk, yk)
                rib_grad.setFocalPoint(xk, yk)
                rib_grad.setRadius(rk)
                c_rib0.setAlpha(a_k)
                rib_grad.setColorAt(0, c_rib0)
                rib_grad.setColorAt(1, c_rib1)
                painter.setBrush(QBrush(rib_grad))
                painter.drawEllipse(QRectF(xk - rk, yk - rk, rk * 2, rk * 2))

        # 3. 核球：暖黄白双层柔光，随节奏强烈呼吸
        #    （scale 变换绘制椭圆渐变：渐变在形状边缘精确归零，杜绝硬边）
        beat = self._galaxy_pulse  # 快攻击节拍包络（节拍瞬响同时最亮）
        bulge_rx = min(w, h) * (0.070 + beat * 0.030)
        bulge_ry = bulge_rx * (0.55 + 0.05 * math.sin(now * 0.5))
        bulge_a = int(40 + beat * 150)  # 中心亮度随节拍瞬闪（对比拉开）
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, bulge_ry / bulge_rx)
        halo = QRadialGradient(0, 0, bulge_rx * 2.4)
        halo.setColorAt(0.0, QColor(255, 252, 242, int(bulge_a * 0.50)))
        halo.setColorAt(0.30, QColor(warm.red(), warm.green(), warm.blue(), int(bulge_a * 0.22)))
        halo.setColorAt(0.65, QColor(warm.red(), warm.green(), warm.blue(), int(bulge_a * 0.07)))
        halo.setColorAt(1.0, QColor(warm.red(), warm.green(), warm.blue(), 0))
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(0, 0), bulge_rx * 2.4, bulge_rx * 2.4)
        core_g = QRadialGradient(0, 0, bulge_rx * 0.75)
        core_g.setColorAt(0.0, QColor(255, 255, 255, min(255, int(bulge_a * 1.4))))
        core_g.setColorAt(0.45, QColor(warm.red(), warm.green(), warm.blue(), int(bulge_a * 0.55)))
        core_g.setColorAt(0.80, QColor(warm.red(), warm.green(), warm.blue(), int(bulge_a * 0.15)))
        core_g.setColorAt(1.0, QColor(warm.red(), warm.green(), warm.blue(), 0))
        painter.setBrush(QBrush(core_g))
        painter.drawEllipse(QPointF(0, 0), bulge_rx * 0.75, bulge_rx * 0.75)
        painter.restore()

        # 4. 星球：锚定螺旋双臂随图案刚性旋转，全部星球亮度随节奏呼吸
        p_grad = QRadialGradient(0, 0, 1)  # 复用的粒子径向渐变
        pulse = 0.68 + beat * 0.75         # 节拍脉冲系数（鼓点响起瞬间全体最亮）
        c_white = QColor(255, 255, 255)    # 复用颜色对象（setColorAt 内部按值拷贝）
        c_core = QColor()
        c_edge = QColor()
        for p in self._galaxy_particles:
            ring = 0.18 + p['z'] * 0.82
            angle = (p['phase'] + pattern_rot
                     + math.sin(now * p['wobble_freq'] + p['seed']) * p['wobble'])
            x = cx + math.cos(angle) * rx * ring
            y = cy + math.sin(angle) * ry * ring * p['flatten'] + breath
            # 柔和闪烁：底亮较高，偶发高光
            tw = 0.5 + 0.5 * math.sin(now * p['twinkle_freq'] + p['seed'])
            r = max(0.6, p['size'] * (0.85 + tw * 0.7) * (0.92 + bass * 0.16))
            if p['disk']:
                # 盘面尘星：淡蓝灰、很暗，填充旋臂之间的空旷区
                on_arm = 0.0
                col = dust
                alpha = int((0.03 + tw * 0.05) * pulse * 255)
            else:
                # 臂上/臂间配色（粒子锚定在臂上，spread 决定偏离度；与初始化同一 theta 公式）
                off_arm = abs(p['phase'] - math.log(ring * 12.0 + 1.0) / 0.16) % math.pi
                on_arm = max(0.0, 1.0 - off_arm * 2.2)
                col = star_white if (tw > 0.93 and on_arm > 0.35) else arm_blue
                # 星球亮度 = 底亮 + 闪烁 + 臂上加成，整体乘节奏脉冲
                alpha = int((0.065 + tw * 0.11 + on_arm * 0.30) * pulse * 255)
            alpha = max(0, min(255, alpha))
            p_grad.setCenter(x, y)
            p_grad.setFocalPoint(x, y)
            p_grad.setRadius(r * 2.0)
            c_white.setAlpha(min(255, int(alpha * 0.85)))
            p_grad.setColorAt(0, c_white)
            c_core.setRgb(col.red(), col.green(), col.blue())
            c_core.setAlpha(alpha)
            p_grad.setColorAt(0.32, c_core)
            c_edge.setRgb(col.red(), col.green(), col.blue(), 0)
            p_grad.setColorAt(1, c_edge)
            painter.setBrush(QBrush(p_grad))
            painter.drawEllipse(QRectF(x - r * 2.0, y - r * 2.0, r * 4.0, r * 4.0))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)


class AudioVisualService:
    def __init__(self, player_controller):
        self._pc = player_controller
        self._current_style = 'none'
        self._is_audio_only = False
        self._widget = None
        self._current_file = None

    @property
    def current_style(self):
        return self._current_style

    @property
    def is_audio_only(self):
        return self._is_audio_only

    def is_audio_file(self, url):
        if not url:
            return False
        path = url.split('?')[0].split('#')[0]
        return path.lower().endswith(AUDIO_EXTENSIONS)

    def prepare_before_loadfile(self, url):
        if not self.is_audio_file(url):
            self._is_audio_only = False
            self._hide_widget()
            self._current_style = 'none'
            self._current_file = None
            return
        self._is_audio_only = True
        self._current_file = url

    def auto_enable_if_audio(self):
        from core.log_manager import global_logger as _log
        if np is None:
            return False
        if self.detect_audio_only():
            if self._current_style == 'none':
                saved = self._load_saved_style()
                if saved and saved != 'none':
                    self._current_style = saved
                else:
                    self._current_style = random.choice(STYLE_KEYS)
            _log.info(f"音频可视化自动启用: style={self._current_style}, file={self._current_file}")
            self._show_widget()
            self._auto_show_lyrics()
            return True
        else:
            if self._current_style != 'none':
                self._hide_widget()
            self._auto_hide_lyrics()
            return False

    def detect_audio_only(self):
        if not self._pc or not self._pc.is_playing:
            self._is_audio_only = False
            return False
        try:
            track_list_str = self._pc._get_mpv_property_string('track-list') or ''
            has_real_video = False
            has_audio = False
            if track_list_str:
                import json
                try:
                    tracks = json.loads(track_list_str)
                    for t in tracks:
                        if t.get('type') == 'video':
                            if not t.get('albumart', False):
                                has_real_video = True
                        elif t.get('type') == 'audio':
                            has_audio = True
                except Exception as e:
                    logger.debug(f"track-list JSON 解析失败: {e}")
            is_audio = has_audio and not has_real_video
            self._is_audio_only = is_audio
            return is_audio
        except Exception:
            self._is_audio_only = False
            return False

    def apply_visual_style(self, style_key):
        if np is None or style_key not in AUDIO_VISUAL_STYLES:
            return False
        self._current_style = style_key
        if style_key == 'none':
            self._hide_widget()
        else:
            self._show_widget()
        self.save_current_style()
        return True

    def clear_visual(self):
        self._hide_widget()
        self._current_style = 'none'
        self._auto_hide_lyrics()

    def _raise_lyrics_above(self):
        try:
            w = self._get_main_window()
            if w and hasattr(w, '_lyrics_widget') and w._lyrics_widget and w._lyrics_widget.isVisible():
                w._lyrics_widget.raise_()
        except Exception as e:
            logger.debug(f"_raise_lyrics_above: {e}")

    def _auto_show_lyrics(self):
        try:
            from services.audio_visual_service import extract_lyrics
            lyrics = extract_lyrics(self._current_file) if self._current_file else None
            if not lyrics:
                return
            w = self._get_main_window()
            if not w:
                return
            if not hasattr(w, '_lyrics_widget') or not w._lyrics_widget:
                from ui.lyrics_widget import LyricsWidget
                w._lyrics_widget = LyricsWidget(w.video_frame)
            vf = w.video_frame
            if vf:
                w._lyrics_widget.setGeometry(0, 0, vf.width(), vf.height())
            w._lyrics_widget.set_lyrics(lyrics, is_lrc='[' in lyrics)
            w._lyrics_widget.show()
            w._lyrics_widget.raise_()
            w._lyrics_widget.start()
        except Exception as e:
            logger.debug(f"歌词自动加载失败: {e}")

    def _auto_hide_lyrics(self):
        try:
            w = self._get_main_window()
            if w and hasattr(w, '_lyrics_widget') and w._lyrics_widget:
                w._lyrics_widget.stop()
                w._lyrics_widget.hide()
        except Exception as e:
            logger.debug(f"_auto_hide_lyrics: {e}")

    def _get_main_window(self):
        if self._widget and self._widget.parent():
            p = self._widget.parent()
            while p:
                if hasattr(p, 'player_controller'):
                    return p
                p = p.parent()
        return None

    def apply_random_style(self):
        self._current_style = 'random'
        self._show_widget()
        self.save_current_style()
        return True

    def _show_widget(self):
        if not self._widget:
            return
        self._widget.set_style(self._current_style)
        parent = self._widget.parent()
        if parent:
            self._widget.setGeometry(0, 0, parent.width(), parent.height())
        if self._pc and hasattr(self._pc, 'video_widget'):
            self._pc.video_widget.hide()
        self._widget.start(self._current_file)
        self._raise_lyrics_above()

    def _hide_widget(self):
        if self._widget:
            self._widget.stop()
        if self._pc and hasattr(self._pc, 'video_widget'):
            self._pc.video_widget.show()

    def resize_widget(self):
        if self._widget and self._widget.isVisible():
            parent = self._widget.parent()
            if parent:
                self._widget.setGeometry(0, 0, parent.width(), parent.height())

    def get_visual_widget(self):
        """返回可视化 widget（封面显示菜单读写其配置用，可能为 None）。"""
        return self._widget

    def _load_saved_style(self):
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            return config.get_value('Player', 'audio_visual_style', 'none') or 'none'
        except Exception:
            return 'none'

    def save_current_style(self):
        try:
            from core.config_manager import ConfigManager
            config = ConfigManager()
            config.set_value('Player', 'audio_visual_style', self._current_style)
            config.save_config()
        except Exception as e:
            logger.warning(f"保存音频可视化样式失败: {e}")

    def get_style_display_name(self, style_key, language_manager=None):
        style = AUDIO_VISUAL_STYLES.get(style_key)
        if not style:
            return style_key
        if language_manager:
            return language_manager.tr(style['name_key'], style['name_default'])
        return style['name_default']

    def get_all_styles(self):
        return AUDIO_VISUAL_STYLES


def extract_cover_art(file_path):
    try:
        import mutagen
        audio = mutagen.File(file_path)  # type: ignore[reportPrivateImportUsage]
        if audio is None:
            return None
        if hasattr(audio, 'tags') and audio.tags:
            for tag in audio.tags.values():
                if hasattr(tag, 'data') and hasattr(tag, 'mime_type'):
                    if tag.mime_type and tag.mime_type.startswith('image/'):
                        img = QImage()
                        if img.loadFromData(tag.data):
                            return QPixmap.fromImage(img)
        if hasattr(audio, 'pictures'):
            for pic in audio.pictures:
                if pic.data and pic.mime and pic.mime.startswith('image/'):
                    img = QImage()
                    if img.loadFromData(pic.data):
                        return QPixmap.fromImage(img)
    except Exception as e:
        logger.debug(f"extract_cover_art: {e}")
    return None


def extract_lyrics(file_path):
    try:
        import mutagen
        audio = mutagen.File(file_path)  # type: ignore[reportPrivateImportUsage]
        if audio is None:
            return None
        if hasattr(audio, 'tags') and audio.tags:
            for key in ('USLT', 'SYLT', 'lyrics:eng', 'lyrics', 'LYRICS', 'unsyncedlyrics'):
                if key in audio.tags:
                    val = audio.tags[key]
                    if hasattr(val, 'text'):
                        for t in val.text:
                            if isinstance(t, str) and t.strip():
                                return t.strip()
                    elif isinstance(val, list):
                        for item in val:
                            if hasattr(item, 'text'):
                                for t in item.text:
                                    if isinstance(t, str) and t.strip():
                                        return t.strip()
                            elif isinstance(item, str) and item.strip():
                                return item.strip()
        if hasattr(audio, 'get'):
            for key in ('lyrics', 'LYRICS', 'synctext'):
                val = audio.get(key)
                if val:
                    if isinstance(val, str):
                        return val.strip()
                    if isinstance(val, list):
                        for item in val:
                            text = str(item).strip()
                            if text:
                                return text
    except Exception as e:
        logger.debug(f"extract_lyrics: {e}")
    return None
