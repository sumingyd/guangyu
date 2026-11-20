"""硬件检测服务 — 检测 CPU/GPU/RAM 并推荐视频增强参数

用于第二阶段 AI 增强：根据硬件能力自动推荐运动补偿强度、
缩放算法和着色器选择，避免在低端设备上开启过重的处理导致卡顿。
"""
import os
import subprocess

from core.log_manager import global_logger as logger
from utils.platform_utils import is_windows, is_macos, is_linux


class HardwareDetectService:
    """硬件检测与智能推荐"""

    def __init__(self):
        self._cpu_info = None
        self._gpu_info = None
        self._ram_gb = None
        self._perf_score = None

    # ---------- CPU 检测 ----------
    def get_cpu_info(self) -> dict:
        """获取 CPU 信息"""
        if self._cpu_info is not None:
            return self._cpu_info
        info = {'cores': 1, 'name': 'Unknown', 'freq_ghz': 0.0}
        try:
            import psutil
            info['cores'] = psutil.cpu_count(logical=True) or 1
            physical = psutil.cpu_count(logical=False) or 1
            info['physical_cores'] = physical
            try:
                freq = psutil.cpu_freq()
                if freq:
                    info['freq_ghz'] = round(freq.max / 1000.0, 2)
            except Exception as e:
                logger.debug(f"get_cpu_info: {e}")
        except ImportError:
            info['cores'] = os.cpu_count() or 1
            info['physical_cores'] = info['cores']

        # 获取 CPU 型号名
        try:
            if is_windows():
                result = subprocess.run(
                    ['wmic', 'cpu', 'get', 'name'],
                    capture_output=True, text=True, timeout=5
                )
                lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                if len(lines) > 1:
                    info['name'] = lines[1]
            elif is_macos():
                info['name'] = subprocess.check_output(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    text=True, timeout=5
                ).strip()
            elif is_linux():
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('model name'):
                            info['name'] = line.split(':')[1].strip()
                            break
        except Exception as e:
            logger.debug(f"获取CPU型号失败: {e}")

        self._cpu_info = info
        return info

    # ---------- RAM 检测 ----------
    def get_ram_gb(self) -> float:
        """获取可用内存（GB）"""
        if self._ram_gb is not None:
            return self._ram_gb
        try:
            import psutil
            mem = psutil.virtual_memory()
            self._ram_gb = round(mem.total / (1024 ** 3), 1)
        except ImportError:
            self._ram_gb = 8.0
        return self._ram_gb

    # ---------- GPU 检测 ----------
    def get_gpu_info(self) -> dict:
        """获取 GPU 信息"""
        if self._gpu_info is not None:
            return self._gpu_info
        info = {'name': 'Unknown', 'vram_mb': 0, 'type': 'unknown'}
        try:
            if is_windows():
                result = subprocess.run(
                    ['wmic', 'path', 'win32_VideoController', 'get', 'name,AdapterRAM'],
                    capture_output=True, text=True, timeout=5
                )
                lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                if len(lines) > 1:
                    parts = lines[1].rsplit(None, 1)
                    if len(parts) >= 2:
                        info['name'] = parts[0]
                        try:
                            info['vram_mb'] = int(parts[1])
                        except ValueError:
                            pass
                    else:
                        info['name'] = lines[1]
            elif is_macos():
                result = subprocess.run(
                    ['system_profiler', 'SPDisplaysDataType'],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split('\n'):
                    if 'Chipset' in line or 'VRAM' in line:
                        if 'VRAM' in line:
                            try:
                                info['vram_mb'] = int(
                                    line.split(':')[1].strip().replace('MB', '').strip()
                                )
                            except ValueError:
                                pass
                        if 'Chipset' in line:
                            info['name'] = line.split(':')[1].strip()
            elif is_linux():
                try:
                    result = subprocess.run(
                        ['lspci', '-v'],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in result.stdout.split('\n'):
                        if 'VGA' in line or '3D' in line or 'Display' in line:
                            info['name'] = line.split(':')[-1].strip()
                            break
                except FileNotFoundError:
                    pass
        except Exception as e:
            logger.debug(f"获取GPU信息失败: {e}")

        # 判断 GPU 类型
        name_lower = info['name'].lower()
        if any(k in name_lower for k in ('nvidia', 'geforce', 'rtx', 'gtx', 'quadro')):
            info['type'] = 'nvidia'
        elif any(k in name_lower for k in ('amd', 'radeon', 'rx ')):
            info['type'] = 'amd'
        elif any(k in name_lower for k in ('intel', 'iris', 'uhd', 'hd graphics')):
            info['type'] = 'intel'
        elif any(k in name_lower for k in ('apple', 'm1', 'm2', 'm3', 'm4')):
            info['type'] = 'apple'

        self._gpu_info = info
        return info

    # ---------- 综合性能评分 ----------
    def get_performance_score(self) -> int:
        """计算综合性能评分（0-100）

        评分维度：
        - CPU 核心数和频率（40%）
        - 内存大小（20%）
        - GPU 性能（40%）
        """
        if self._perf_score is not None:
            return self._perf_score

        cpu = self.get_cpu_info()
        ram = self.get_ram_gb()
        gpu = self.get_gpu_info()

        # CPU 评分（0-40）
        cores = cpu.get('cores', 1)
        freq = cpu.get('freq_ghz', 0.0)
        cpu_score = min(40, cores * 2 + freq * 8)

        # 内存评分（0-20）
        ram_score = min(20, ram * 1.5)

        # GPU 评分（0-40）
        gpu_type = gpu.get('type', 'unknown')
        gpu_vram = gpu.get('vram_mb', 0)
        if gpu_type == 'nvidia':
            gpu_score = min(40, 25 + gpu_vram / (1024 * 64) * 15)
        elif gpu_type == 'amd':
            gpu_score = min(40, 22 + gpu_vram / (1024 * 64) * 15)
        elif gpu_type == 'apple':
            gpu_score = 35  # Apple Silicon GPU 性能较好
        elif gpu_type == 'intel':
            gpu_score = min(20, 10 + gpu_vram / (1024 * 128) * 10)
        else:
            gpu_score = 10  # 未知 GPU，保守评分

        self._perf_score = int(cpu_score + ram_score + gpu_score)
        return self._perf_score

    # ---------- 智能推荐 ----------
    def get_recommended_settings(self) -> dict:
        """根据硬件性能推荐视频增强参数

        :return: {
            'motion_comp': 'off'/'low'/'medium'/'high',
            'motion_comp_fps': int,
            'superres_scale': str,
            'superres_detail': int,
            'shader_preset': str,
            'perf_level': 'low'/'medium'/'high',
        }
        """
        score = self.get_performance_score()
        ram = self.get_ram_gb()

        if score >= 75 and ram >= 16:
            # 高性能设备
            return {
                'motion_comp': 'medium',
                'motion_comp_fps': 60,
                'superres_scale': 'ewa_lanczossharp',
                'superres_detail': 40,
                'shader_preset': 'fsrcnnx',
                'perf_level': 'high',
            }
        elif score >= 50 and ram >= 8:
            # 中等性能设备
            return {
                'motion_comp': 'low',
                'motion_comp_fps': 60,
                'superres_scale': 'lanczos',
                'superres_detail': 20,
                'shader_preset': 'off',
                'perf_level': 'medium',
            }
        else:
            # 低性能设备
            return {
                'motion_comp': 'off',
                'motion_comp_fps': 60,
                'superres_scale': 'off',
                'superres_detail': 0,
                'shader_preset': 'off',
                'perf_level': 'low',
            }

    def get_hardware_summary(self) -> str:
        """获取硬件信息摘要文本"""
        cpu = self.get_cpu_info()
        ram = self.get_ram_gb()
        gpu = self.get_gpu_info()
        score = self.get_performance_score()
        parts = [
            f"CPU: {cpu.get('name', '?')} ({cpu.get('cores', 1)}核)",
            f"RAM: {ram:.1f}GB",
            f"GPU: {gpu.get('name', '?')}",
            f"性能评分: {score}/100",
        ]
        return ' | '.join(parts)


# 单例
_instance = None
_instance_lock = __import__('threading').Lock()


def get_hardware_detect_service() -> HardwareDetectService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HardwareDetectService()
    return _instance
