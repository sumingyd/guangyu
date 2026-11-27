from PySide6.QtGui import QGuiApplication, QWindow
import subprocess
import sys
import logging
import os

if sys.platform == 'win32':
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

logger = logging.getLogger(__name__)

_hdr_cache = None
_hdr_cache_time = 0
_HDR_CACHE_TTL = 30
# Windows 按显示器查询的结果：{友好名小写: {'gdi':..., 'enabled': bool, 'supported': bool}}
_win_hdr_map = None
_win_hdr_map_time = 0


def clear_hdr_cache():
    global _hdr_cache, _hdr_cache_time, _win_hdr_map, _win_hdr_map_time
    _hdr_cache = None
    _hdr_cache_time = 0
    _win_hdr_map = None
    _win_hdr_map_time = 0


def is_android_hdr_enabled():
    """检测 Android 设备是否支持 HDR 显示。

    通过 Android Display.getHdrCapabilities() 检测（Android 7.0+）。
    优先使用 pyjnius（chaquopy 环境），回退到 PySide6 Qt 检测。
    """
    global _hdr_cache, _hdr_cache_time
    import time
    now = time.monotonic()
    if _hdr_cache is not None and (now - _hdr_cache_time) < _HDR_CACHE_TTL:
        return _hdr_cache
    result = False
    # 方案1：通过 pyjnius 调用 Android Display.getHdrCapabilities()
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        window_manager = activity.getSystemService('window')
        display = window_manager.getDefaultDisplay()
        types = []
        if hasattr(display, 'getHdrCapabilities'):
            caps = display.getHdrCapabilities()
            types = caps.getSupportedHdrTypes()
            result = len(types) > 0
            logger.info(f"Android HDR检测(pyjnius): supportedTypes={types}, result={result}")
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Android HDR检测(pyjnius)失败: {e}")

    # 方案2：通过 PySide6 Qt 检测（如果 pyjnius 不可用）
    if not result:
        try:
            if QGuiApplication.instance():
                if hasattr(QWindow, 'isHDR'):
                    window = QWindow()
                    screen = QGuiApplication.primaryScreen()
                    if screen:
                        window.setScreen(screen)
                        try:
                            result = window.isHDR()
                            logger.info(f"Android HDR检测(Qt): isHDR()={result}")
                        finally:
                            window.deleteLater()
        except Exception as e:
            logger.debug(f"Android HDR检测(Qt)失败: {e}")

    _hdr_cache = result
    _hdr_cache_time = now
    return result


def is_linux_hdr_enabled():
    """检测 Linux 系统是否启用了 HDR。

    支持的检测方式：
    - Wayland: 检查 COLORHDR_OUTPUT 环境变量或 wlr-randr 输出
    - X11: 检查 xrandr --props 中的 HDR_OUTPUT_METADATA 属性
    """
    global _hdr_cache, _hdr_cache_time
    import time
    now = time.monotonic()
    if _hdr_cache is not None and (now - _hdr_cache_time) < _HDR_CACHE_TTL:
        return _hdr_cache

    result = False

    # Wayland: 检查环境变量
    if os.environ.get('COLORHDR_OUTPUT'):
        result = True
        logger.info("Linux HDR检测(Wayland): COLORHDR_OUTPUT 环境变量已设置")
    else:
        # X11: 检查 xrandr --props 输出中是否包含 HDR_OUTPUT_METADATA
        try:
            result_x = subprocess.run(
                ['xrandr', '--prop'],
                capture_output=True, text=True, timeout=10,
            )
            if 'HDR_OUTPUT_METADATA' in result_x.stdout:
                result = True
                logger.info("Linux HDR检测(X11): xrandr 检测到 HDR_OUTPUT_METADATA")
        except FileNotFoundError:
            logger.debug("Linux HDR检测: xrandr 未安装")
        except Exception as e:
            logger.debug(f"Linux HDR检测(X11)失败: {e}")

        # Wayland: 尝试 wlr-randr（wlroots 合成器）
        if not result:
            try:
                result_w = subprocess.run(
                    ['wlr-randr'],
                    capture_output=True, text=True, timeout=10,
                )
                if 'HDR' in result_w.stdout:
                    result = True
                    logger.info("Linux HDR检测(Wayland): wlr-randr 检测到 HDR")
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Linux HDR检测(Wayland/wlr-randr)失败: {e}")

    _hdr_cache = result
    _hdr_cache_time = now
    return result


def _macos_edr_capable():
    """通过 NSScreen 的 EDR 属性判断显示器是否具备 HDR/EDR 能力。

    返回 True/False；PyObjC 不可用或调用失败时返回 None，由调用方回退到
    system_profiler 文本匹配。注意该值只代表面板能力，是否真正进入 EDR
    渲染还需要 NSView 侧开启 wantsExtendedDynamicRangeContent（本仓库未启用），
    因此这里只作为 HDR 模式开关的参考信号。
    """
    try:
        from AppKit import NSScreen
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"macOS EDR检测导入失败: {e}")
        return None
    try:
        screens = NSScreen.screens()
        if not screens:
            return None
        for screen in screens:
            for selector in (
                'maximumExtendedDynamicRangeColorComponentValue',
                'maximumPotentialExtendedDynamicRangeColorComponentValue',
            ):
                try:
                    getter = getattr(screen, selector)
                except AttributeError:
                    continue
                try:
                    value = getter()
                except Exception:
                    continue
                if value is not None and value > 1.0:
                    logger.info(f"macOS EDR检测: {selector}={value}")
                    return True
        return False
    except Exception as e:
        logger.debug(f"macOS EDR检测失败: {e}")
        return None


def is_macos_hdr_enabled():
    global _hdr_cache, _hdr_cache_time
    import time
    now = time.monotonic()
    if _hdr_cache is not None and (now - _hdr_cache_time) < _HDR_CACHE_TTL:
        return _hdr_cache
    # 优先使用 NSScreen 的 EDR 属性：system_profiler 输出里通常没有 "HDR" 字样，
    # 旧实现基本恒返回 False，HDR 模式永远开不起来。
    edr_capable = _macos_edr_capable()
    if edr_capable is not None:
        _hdr_cache = edr_capable
        _hdr_cache_time = now
        return _hdr_cache
    try:
        result = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout
        _hdr_cache = 'HDR' in output
        _hdr_cache_time = now
        return _hdr_cache
    except Exception as e:
        logger.debug(f"macOS HDR检测失败: {e}")
        _hdr_cache = False
        _hdr_cache_time = now
        return False


def _check_windows_hdr_registry():
    try:
        base_path = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as h_base:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(h_base, i)
                    i += 1
                    if subkey_name.lower() != 'monitordatastore':
                        continue
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base_path}\\{subkey_name}") as h_mds:
                        j = 0
                        while True:
                            try:
                                monitor_name = winreg.EnumKey(h_mds, j)
                                j += 1
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base_path}\\{subkey_name}\\{monitor_name}") as h_mon:
                                    try:
                                        val, val_type = winreg.QueryValueEx(h_mon, 'HDREnabled')
                                        if val_type == winreg.REG_DWORD and val == 1:
                                            logger.info(f"注册表HDR检测: 显示器 {monitor_name} HDREnabled=1")
                                            return True
                                    except OSError:
                                        pass
                            except OSError:
                                break
                except OSError:
                    break
    except Exception as e:
        logger.debug(f"注册表HDR检测失败: {e}")
    return False


def _query_windows_display_hdr():
    """通过 DISPLAYCONFIG 查询每台显示器的 HDR 开关状态。

    返回 {显示器友好名小写: {'gdi': GDI设备名小写, 'enabled': bool, 'supported': bool}}；
    非 Windows 或调用失败返回 None。
    """
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _LUID(ctypes.Structure):
            _fields_ = [('LowPart', ctypes.c_uint32), ('HighPart', ctypes.c_int32)]

        class _PATH_SOURCE(ctypes.Structure):
            _fields_ = [('adapterId', _LUID), ('id', ctypes.c_uint32),
                        ('modeInfoIdx', ctypes.c_uint32), ('statusFlags', ctypes.c_uint32)]

        class _RATIONAL(ctypes.Structure):
            _fields_ = [('Numerator', ctypes.c_uint32), ('Denominator', ctypes.c_uint32)]

        class _PATH_TARGET(ctypes.Structure):
            _fields_ = [('adapterId', _LUID), ('id', ctypes.c_uint32),
                        ('modeInfoIdx', ctypes.c_uint32), ('outputTechnology', ctypes.c_uint32),
                        ('rotation', ctypes.c_uint32), ('scaling', ctypes.c_uint32),
                        ('refreshRate', _RATIONAL), ('scanLineOrdering', ctypes.c_uint32),
                        ('targetAvailable', ctypes.c_uint32), ('statusFlags', ctypes.c_uint32)]

        class _PATH_INFO(ctypes.Structure):
            _fields_ = [('sourceInfo', _PATH_SOURCE), ('targetInfo', _PATH_TARGET),
                        ('flags', ctypes.c_uint32)]

        class _MODE_UNION(ctypes.Union):
            _fields_ = [('buffer', ctypes.c_byte * 48)]

        class _MODE_INFO(ctypes.Structure):
            _fields_ = [('infoType', ctypes.c_uint32), ('id', ctypes.c_uint32),
                        ('adapterId', _LUID), ('modeInfo', _MODE_UNION)]

        class _DEVICE_INFO_HEADER(ctypes.Structure):
            _fields_ = [('type', ctypes.c_uint32), ('size', ctypes.c_uint32),
                        ('adapterId', _LUID), ('id', ctypes.c_uint32)]

        class _SOURCE_DEVICE_NAME(ctypes.Structure):
            _fields_ = [('header', _DEVICE_INFO_HEADER),
                        ('viewGdiDeviceName', ctypes.c_wchar * 32)]

        class _TARGET_DEVICE_NAME(ctypes.Structure):
            _fields_ = [('header', _DEVICE_INFO_HEADER), ('flags', ctypes.c_uint32),
                        ('outputTechnology', ctypes.c_uint32),
                        ('edidManufactureId', ctypes.c_uint16),
                        ('edidProductCodeId', ctypes.c_uint16),
                        ('connectorInstance', ctypes.c_uint32),
                        ('monitorFriendlyDeviceName', ctypes.c_wchar * 64),
                        ('monitorDevicePath', ctypes.c_wchar * 128)]

        class _ADVANCED_COLOR_INFO(ctypes.Structure):
            _fields_ = [('header', _DEVICE_INFO_HEADER), ('value', ctypes.c_uint32),
                        ('colorEncoding', ctypes.c_uint32),
                        ('bitsPerColorChannel', ctypes.c_uint32)]

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        qdc_only_active_paths = 0x00000002
        get_source_name = 1
        get_target_name = 2
        get_advanced_color_info = 9

        num_paths = wintypes.UINT(0)
        num_modes = wintypes.UINT(0)
        if user32.GetDisplayConfigBufferSizes(
                qdc_only_active_paths, ctypes.byref(num_paths), ctypes.byref(num_modes)) != 0:
            return None
        if num_paths.value == 0:
            return None

        paths = (_PATH_INFO * num_paths.value)()
        modes = (_MODE_INFO * max(num_modes.value, 1))()
        count_paths = wintypes.UINT(num_paths.value)
        count_modes = wintypes.UINT(num_modes.value)
        if user32.QueryDisplayConfig(
                qdc_only_active_paths, ctypes.byref(count_paths), paths,
                ctypes.byref(count_modes), modes, None) != 0:
            return None

        result = {}
        for i in range(count_paths.value):
            path = paths[i]
            src = path.sourceInfo
            tgt = path.targetInfo

            src_name = _SOURCE_DEVICE_NAME()
            src_name.header.type = get_source_name
            src_name.header.size = ctypes.sizeof(_SOURCE_DEVICE_NAME)
            src_name.header.adapterId = src.adapterId
            src_name.header.id = src.id

            tgt_name = _TARGET_DEVICE_NAME()
            tgt_name.header.type = get_target_name
            tgt_name.header.size = ctypes.sizeof(_TARGET_DEVICE_NAME)
            tgt_name.header.adapterId = tgt.adapterId
            tgt_name.header.id = tgt.id

            color_info = _ADVANCED_COLOR_INFO()
            color_info.header.type = get_advanced_color_info
            color_info.header.size = ctypes.sizeof(_ADVANCED_COLOR_INFO)
            color_info.header.adapterId = tgt.adapterId
            color_info.header.id = tgt.id

            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(src_name)) != 0:
                continue
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt_name)) != 0:
                continue
            color_ok = user32.DisplayConfigGetDeviceInfo(ctypes.byref(color_info)) == 0
            value = int(color_info.value) if color_ok else 0
            supported = bool(value & 0x1)
            enabled = bool((value >> 1) & 0x1)

            friendly = (tgt_name.monitorFriendlyDeviceName or '').strip()
            gdi = (src_name.viewGdiDeviceName or '').strip()
            key = (friendly or gdi or f'display{i}').lower()
            result[key] = {'gdi': gdi.lower(), 'enabled': enabled, 'supported': supported}
            logger.debug(
                f"显示器 {friendly or gdi}: HDR支持={supported}, HDR开启={enabled}")
        return result or None
    except Exception as e:
        logger.debug(f"DISPLAYCONFIG HDR检测失败: {e}")
        return None


def _check_windows_hdr_qt():
    """通过 Qt 检测 Windows HDR 状态（作为注册表检测的补充）。

    Qt 6.4+ 提供了 QWindow::isHDR() 等接口；
    旧版本通过屏幕深度和格式间接判断。
    """
    try:
        if not QGuiApplication.instance():
            return None

        screen = QGuiApplication.primaryScreen()
        if not screen:
            return None

        if hasattr(QWindow, 'isHDR'):
            window = QWindow()
            window.setScreen(screen)
            try:
                hdr = window.isHDR()
                logger.info(f"Qt HDR检测: isHDR()={hdr}")
                return hdr
            finally:
                window.deleteLater()

        depth = screen.depth()
        geometry = screen.geometry()
        logger.debug(f"Qt屏幕信息: depth={depth}, size={geometry.width()}x{geometry.height()}")
        return None
    except Exception as e:
        logger.debug(f"Qt HDR检测失败: {e}")
        return None


def is_windows_hdr_enabled(screen_name=None):
    """检测 Windows HDR 是否开启。

    screen_name 传入播放窗口所在显示器的名称（Qt 的 QScreen.name()，通常是显示器
    友好名）时，按该显示器的 DISPLAYCONFIG 高级颜色状态判断；不传或匹配失败时
    回退到旧的注册表检测（任意显示器开启即视为开启）。
    """
    import time
    global _win_hdr_map, _win_hdr_map_time
    now = time.monotonic()
    if _win_hdr_map is None or (now - _win_hdr_map_time) >= _HDR_CACHE_TTL:
        _win_hdr_map = _query_windows_display_hdr()
        _win_hdr_map_time = now

    if screen_name and _win_hdr_map:
        key = str(screen_name).strip().lower()
        for name, info in _win_hdr_map.items():
            gdi = str(info.get('gdi') or '').lower()
            if key == name or key == gdi or key in name or name in key:
                enabled = bool(info.get('enabled'))
                logger.info(
                    f"Windows HDR检测({screen_name}): {'已启用' if enabled else '未启用'}")
                return enabled
        logger.debug(f"未匹配到显示器 {screen_name} 的高级颜色信息，回退注册表检测")

    if _win_hdr_map:
        if any(bool(v.get('enabled')) for v in _win_hdr_map.values()):
            logger.info("Windows HDR检测(显示器列表): 至少一台显示器已启用HDR")
            return True

    result = _check_windows_hdr_registry()
    logger.info(f"Windows HDR检测(注册表): {'已启用' if result else '未启用'}")
    return result
