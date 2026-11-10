"""numpy 可选依赖适配层。

numpy 只服务于频谱/音频可视化等非核心功能（WASAPI 环回 FFT、音频可视化、
自动裁边），核心播放、EPG、频道管理都不依赖它。因此 numpy 导入失败时
不能让整个程序打不开：

* 正常环境：行为与 ``import numpy as np`` 完全一致。
* 导入失败：``NUMPY_AVAILABLE`` 为 False、``np`` 为 None，调用方据此跳过
  依赖 numpy 的功能；同时把诊断信息追加到 ``crash.log``。

为什么要这层：numpy>=2.4 的官方 Windows wheel 编译基线是 x86-64-v2
（SSSE3/SSE4.1/SSE4.2/POPCNT）。在 AMD K10（如 Athlon II X4 620）这类
只有 SSE/SSE2/SSE3 的老 CPU 上，导入 numpy 会直接触发非法指令，
numpy 自身把它包装成 "Importing the numpy C-extensions failed"。
"""

import os
import platform
import sys
import time
import traceback

NUMPY_AVAILABLE = False
NUMPY_ERROR = ''
np = None

# 导入失败时置为 True，供 UI 只提示一次
_hint_shown = False


def _cpu_name():
    """读取 CPU 型号字符串；失败时退回 platform 信息。"""
    try:
        if sys.platform == 'win32':
            import winreg
            key_path = r'HARDWARE\DESCRIPTION\System\CentralProcessor\0'
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                return str(winreg.QueryValueEx(key, 'ProcessorNameString')[0]).strip()
    except Exception:
        pass
    try:
        return platform.processor() or platform.machine() or '未知'
    except Exception:
        return '未知'


# Windows IsProcessorFeaturePresent 的特性编号
_WIN_CPU_FEATURES = {
    'SSE3': 13,
    'SSE4.1': 37,
    'SSE4.2': 38,
    'AVX': 39,
    'AVX2': 40,
}


def cpu_features():
    """返回 CPU 指令集支持情况；非 Windows 或探测失败时返回空字典。"""
    if sys.platform != 'win32':
        return {}
    try:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        return {name: bool(kernel32.IsProcessorFeaturePresent(code))
                for name, code in _WIN_CPU_FEATURES.items()}
    except Exception:
        return {}


def _numpy_version():
    """尽量拿到 numpy 版本：导入失败时仍可从包元数据或 version.py 读取。"""
    try:
        from importlib.metadata import version
        return version('numpy')
    except Exception:
        pass
    try:
        import re
        base = os.path.join(getattr(sys, '_MEIPASS', ''), 'numpy')
        for name in ('version.py', '_version.py'):
            path = os.path.join(base, name)
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    match = re.search(r'version\s*=\s*[\'"]([^\'"]+)', f.read())
                if match:
                    return match.group(1)
    except Exception:
        pass
    return '未知'


def meipass_summary():
    """打包版的 _MEIPASS 内容摘要：判定 numpy 扩展与依赖库是否真的进包。"""
    lines = []
    frozen = getattr(sys, 'frozen', False)
    meipass = getattr(sys, '_MEIPASS', '')
    lines.append(f"frozen: {frozen}")
    if not meipass:
        lines.append('_MEIPASS: 无（非 PyInstaller 环境）')
        return lines
    lines.append(f"_MEIPASS: {meipass}")
    try:
        total = 0
        for _root, _dirs, files in os.walk(meipass):
            total += len(files)
        lines.append(f"_MEIPASS 文件数: {total}")
    except Exception as e:
        lines.append(f"_MEIPASS 遍历失败: {e}")

    numpy_dir = os.path.join(meipass, 'numpy')
    lines.append(f"numpy 包目录: {'存在' if os.path.isdir(numpy_dir) else '缺失'}")

    # numpy 2.x 的扩展在 numpy/_core，1.x 在 numpy/core
    found_pyd = []
    for sub in ('numpy/_core', 'numpy/core'):
        d = os.path.join(meipass, *sub.split('/'))
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.startswith('_multiarray_umath') and name.lower().endswith(('.pyd', '.so', '.dylib')):
                size = os.path.getsize(os.path.join(d, name))
                found_pyd.append(f"{sub}/{name} ({size} B)")
    lines.append(f"_multiarray_umath 扩展: {found_pyd or '未找到'}")

    libs_dir = os.path.join(meipass, 'numpy.libs')
    if os.path.isdir(libs_dir):
        lines.append(f"numpy.libs: {sorted(os.listdir(libs_dir))}")
    else:
        lines.append('numpy.libs: 缺失')
    return lines


def _log_dir():
    try:
        from utils.app_paths import get_log_dir
        return get_log_dir()
    except Exception:
        return ''


def record_import_failure(exc):
    """把 numpy 导入失败的关键现场写入 crash.log，便于用户回传定位。"""
    try:
        log_dir = _log_dir()
        if not log_dir:
            return
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, 'crash.log')
        features = cpu_features()
        missing = [name for name, ok in features.items() if not ok]
        header = [
            '=' * 60,
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            '类型: numpy 导入失败（非核心功能降级，程序继续启动）',
            f"CPU: {_cpu_name()}",
            f"CPU 指令集: {features or '未探测'}",
            f"numpy 版本: {_numpy_version()}",
            f"Python: {sys.version.splitlines()[0]}",
            f"平台: {sys.platform}",
            '-' * 60,
        ]
        if missing:
            header.append(f"缺少的指令集: {', '.join(missing)}")
        if 'SSE4.2' in missing or 'SSE4.1' in missing:
            header.append(
                '判定: CPU 不满足 numpy>=2.4 官方 wheel 的 x86-64-v2 基线，'
                '已禁用频谱/音频可视化。'
            )
        header.extend(meipass_summary())
        path_dirs = [p for p in os.environ.get('PATH', '').split(os.pathsep) if p]
        header.append(f"PATH 条目数: {len(path_dirs)}；前 3 项: {path_dirs[:3]}")
        header.append(f"sys.path 前 4 项: {sys.path[:4]}")
        header.append('-' * 60)
        header.append(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(header) + '\n')
    except Exception:
        pass


try:
    import numpy as _numpy
except BaseException as _exc:  # noqa: BLE001 - 非法指令在个别场景表现为 OSError
    NUMPY_ERROR = f"{type(_exc).__name__}: {_exc}"
    record_import_failure(_exc)
else:
    np = _numpy
    NUMPY_AVAILABLE = True


def unavailable_message():
    """给用户看的可读说明：说明降级范围，不影响核心播放。"""
    detail = f"（{NUMPY_ERROR}）" if NUMPY_ERROR else ''
    return (
        '当前设备无法加载 numpy 数值库，频谱与音频可视化功能已禁用，'
        '频道列表、EPG 与视频播放不受影响。\n\n'
        '常见原因是 CPU 过旧（缺少 SSSE3/SSE4.1/SSE4.2 指令集）。\n'
        f'诊断信息已写入 crash.log{detail}'
    )


def should_show_hint():
    """同一次运行只提示一次。"""
    global _hint_shown
    if NUMPY_AVAILABLE or _hint_shown:
        return False
    _hint_shown = True
    return True
