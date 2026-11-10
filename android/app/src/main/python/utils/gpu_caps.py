"""显卡能力探测（仅 Windows 有实际探测逻辑）。

mpv 在 Windows 上的自动渲染后端是 D3D11（gpu-api=d3d11），但 D3D11 需要
显卡支持 Feature Level 11_0。老显卡（如 AMD Radeon HD 4300/4500 只有
D3D10.1）创建 D3D11 设备会失败，mpv 直接无画面。这里在初始化前探测一次，
不支持时让上层退回 OpenGL，避免用户面对黑屏。
"""

import ctypes
import sys

# D3D_FEATURE_LEVEL_11_0 = 0xb000
_D3D_FEATURE_LEVEL_11_0 = 0xB000
_D3D_DRIVER_TYPE_HARDWARE = 1
_D3D11_SDK_VERSION = 7


def d3d11_available():
    """返回当前显卡能否创建 Feature Level >= 11_0 的 D3D11 设备。

    非 Windows 或探测本身出错时返回 True（保持原有默认行为，不误伤）。
    """
    if sys.platform != 'win32':
        return True
    device = ctypes.c_void_p()
    feature_level = ctypes.c_int(0)
    try:
        d3d11 = ctypes.WinDLL('d3d11')
        hr = d3d11.D3D11CreateDevice(
            None,                      # pAdapter：默认适配器
            _D3D_DRIVER_TYPE_HARDWARE, # DriverType
            None,                      # Software
            0,                         # Flags：不启用调试层
            None,                      # pFeatureLevels：默认 11_0 → 9_1
            0,
            _D3D11_SDK_VERSION,
            ctypes.byref(device),
            ctypes.byref(feature_level),
            None,                      # ppImmediateContext
        )
        if hr != 0 or not device.value:
            return False
        return feature_level.value >= _D3D_FEATURE_LEVEL_11_0
    except Exception:
        return True
    finally:
        # 释放探测创建的设备，避免常驻占用显卡资源
        try:
            if device.value:
                vtbl = ctypes.cast(
                    device, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
                release(device)
        except Exception:
            pass
