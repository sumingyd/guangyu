try:
    from PySide6.QtGui import QGuiApplication, QWindow
except Exception:  # 安卓（Chaquopy）没有 PySide6，HDR 探测走 pyjnius 分支
    QGuiApplication = None
    QWindow = None
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
# Windows 显示器 HDR 峰值：(时间戳, [(GDI 名, MaxLuminance), ...])
_win_peak_cache = None
_win_peak_time = 0


def clear_hdr_cache():
    global _hdr_cache, _hdr_cache_time, _win_hdr_map, _win_hdr_map_time
    global _win_peak_cache, _win_peak_time
    _hdr_cache = None
    _hdr_cache_time = 0
    _win_hdr_map = None
    _win_hdr_map_time = 0
    _win_peak_cache = None
    _win_peak_time = 0


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
            path = (tgt_name.monitorDevicePath or '').strip()
            key = (friendly or gdi or f'display{i}').lower()
            result[key] = {'gdi': gdi.lower(), 'enabled': enabled,
                           'supported': supported, 'path': path}
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


# ==================== 显示器 HDR 峰值 ====================

def _query_windows_display_peak_list():
    """用 DXGI 1.6 读出每台已连接显示器的 HDR 峰值亮度。

    返回 [(GDI 设备名, MaxLuminance), ...]；任何一步失败返回 None。
    MaxLuminance 是显示器在 HDR 模式下的实际峰值（nits），也是 Windows 上唯一
    可靠的峰值来源（DISPLAYCONFIG 只给 HDR 开关和编码信息）。
    """
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
                        ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_ubyte * 8)]

        def _make_guid(text):
            parts = text.strip('{}').split('-')
            g = _GUID()
            g.Data1 = int(parts[0], 16)
            g.Data2 = int(parts[1], 16)
            g.Data3 = int(parts[2], 16)
            tail = parts[3] + parts[4]
            for i in range(8):
                g.Data4[i] = int(tail[i * 2:i * 2 + 2], 16)
            return g

        class _OUTPUT_DESC1(ctypes.Structure):
            _fields_ = [
                ('DeviceName', ctypes.c_wchar * 32),
                ('DesktopCoordinates', wintypes.RECT),
                ('AttachedToDesktop', wintypes.BOOL),
                ('Rotation', ctypes.c_int),
                ('Monitor', wintypes.HANDLE),
                # BitsPerColor/ColorSpace 两个字段容易漏，漏掉后后面所有 float
                # 都会错位，读出的亮度是一堆垃圾小数
                ('BitsPerColor', ctypes.c_uint32),
                ('ColorSpace', ctypes.c_int),
                ('RedPrimary', ctypes.c_float * 2),
                ('GreenPrimary', ctypes.c_float * 2),
                ('BluePrimary', ctypes.c_float * 2),
                ('WhitePoint', ctypes.c_float * 2),
                ('MinLuminance', ctypes.c_float),
                ('MaxLuminance', ctypes.c_float),
                ('MaxFullFrameLuminance', ctypes.c_float),
            ]

        def _call(obj, index, argtypes, *args):
            vtbl = ctypes.cast(
                obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
            return proto(vtbl[index])(obj, *args)

        iid_factory1 = _make_guid('770aae78-f26f-4dba-a829-253c83d1b387')
        # IID_IDXGIOutput6 = {068346E8-AAEC-4B84-ADD7-137F513F77A1}
        # 曾经误写成 4b21，导致 QueryInterface 直接 E_NOINTERFACE
        iid_output6 = _make_guid('068346e8-aaec-4b84-add7-137f513f77a1')
        dxgi = ctypes.WinDLL('dxgi', use_last_error=True)
        factory = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(iid_factory1),
                                   ctypes.byref(factory)) != 0 or not factory:
            return None

        peaks = []
        try:
            idx = 0
            while idx < 16:
                adapter = ctypes.c_void_p()
                # IDXGIFactory1::EnumAdapters1 = 12
                if _call(factory, 12, [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)],
                         idx, ctypes.byref(adapter)) != 0 or not adapter:
                    break
                try:
                    out_idx = 0
                    while out_idx < 16:
                        output = ctypes.c_void_p()
                        # IDXGIAdapter::EnumOutputs = 7
                        if _call(adapter, 7, [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)],
                                 out_idx, ctypes.byref(output)) != 0 or not output:
                            break
                        try:
                            out6 = ctypes.c_void_p()
                            # IUnknown::QueryInterface = 0
                            if _call(output, 0, [ctypes.POINTER(_GUID),
                                                 ctypes.POINTER(ctypes.c_void_p)],
                                     ctypes.byref(iid_output6),
                                     ctypes.byref(out6)) == 0 and out6:
                                try:
                                    desc = _OUTPUT_DESC1()
                                    # IDXGIOutput6::GetDesc1 在 vtable 中的索引是 27。
                                    # 22 是 GetDisplaySurfaceData1、28 是
                                    # CheckHardwareCompositionSupport，都会踩空/写错
                                    if _call(out6, 27, [ctypes.POINTER(_OUTPUT_DESC1)],
                                             ctypes.byref(desc)) == 0:
                                        name = (desc.DeviceName or '').strip()
                                        peak = float(desc.MaxLuminance)
                                        if name and 0 < peak < 100000:
                                            peaks.append((name, peak))
                                finally:
                                    _call(out6, 2, [])
                        finally:
                            _call(output, 2, [])
                        out_idx += 1
                finally:
                    _call(adapter, 2, [])
                idx += 1
        finally:
            _call(factory, 2, [])
        return peaks or None
    except Exception as e:
        logger.debug(f"DXGI 峰值查询失败: {e}")
        return None


def _parse_edid_hdr_peak(blob):
    """从 EDID 的 CTA-861 HDR 静态元数据块里取最大亮度（nits）。

    该块（扩展 tag 0x06）紧跟在 CTA-861 扩展块的数据块集合里，payload 依次是
    EOTF、静态元数据描述符、最大亮度码、maxFALL 码、最小亮度码。亮度按 CTA-861.3
    的编码换算：50 * 2^(code/32)，这也是 Windows 系统属性里“峰值亮度”的来源。
    没有扩展块或没有该数据块时返回 None。
    """
    try:
        data = bytes(blob)
    except Exception:
        return None
    if len(data) < 128 or data[:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return None
    ext_count = data[126]
    for n in range(ext_count):
        start = 128 * (n + 1)
        ext = data[start:start + 128]
        if len(ext) < 128 or ext[0] != 0x02:
            continue
        # 字节 2 是首个 DTD 的偏移；数据块集合从字节 4 开始（字节 3 是标志位）
        dtd_start = ext[2]
        pos = 4
        end = dtd_start if 4 <= dtd_start <= 127 else 127
        while pos < end:
            header = ext[pos]
            if header == 0:
                break
            tag = header >> 5
            length = header & 0x1f
            if pos + 1 + length > end:
                break
            if tag == 7 and length >= 4:
                block = ext[pos + 1:pos + 1 + length]
                # block[0] 为扩展 tag，0x06 = HDR 静态元数据；
                # block[2] 的 bit0 表示后续带最大亮度/maxFALL/最小亮度三个字节
                if block[0] == 0x06 and (block[2] & 0x01):
                    code = block[3]
                    if code > 0:
                        return 50.0 * (2.0 ** (code / 32.0))
            pos += 1 + length
    return None


def _query_edid_peak_list():
    """枚举注册表里每台显示器的 EDID，读出 HDR 静态元数据的最大亮度。

    返回 [{'hwid':..., 'instance':..., 'peak': float}, ...]；
    非 Windows 或读取失败返回 None。hwid/instance 与 DISPLAYCONFIG 的
    monitorDevicePath（DISPLAY#<hwid>#<instance>#...）一一对应。
    """
    if sys.platform != 'win32' or winreg is None:
        return None
    base = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
    entries = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as h_root:
            i = 0
            while True:
                try:
                    hwid = winreg.EnumKey(h_root, i)
                except OSError:
                    break
                i += 1
                try:
                    h_dev = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{hwid}")
                except OSError:
                    continue
                try:
                    j = 0
                    while True:
                        try:
                            inst = winreg.EnumKey(h_dev, j)
                        except OSError:
                            break
                        j += 1
                        try:
                            with winreg.OpenKey(
                                    winreg.HKEY_LOCAL_MACHINE,
                                    f"{base}\\{hwid}\\{inst}\\Device Parameters") as hp:
                                blob, _ = winreg.QueryValueEx(hp, 'EDID')
                        except OSError:
                            continue
                        peak = _parse_edid_hdr_peak(blob)
                        if peak:
                            entries.append({'hwid': hwid, 'instance': inst, 'peak': peak})
                finally:
                    winreg.CloseKey(h_dev)
    except Exception as e:
        logger.debug(f"EDID 峰值枚举失败: {e}")
        return None
    return entries or None


def _screen_monitor_path(screen_name):
    """取播放窗口所在显示器的 DISPLAYCONFIG monitorDevicePath。

    与 is_windows_hdr_enabled 共用同一份 30 秒缓存的显示器表，避免重复查询。
    """
    import time
    global _win_hdr_map, _win_hdr_map_time
    if not screen_name:
        return None
    now = time.monotonic()
    if _win_hdr_map is None or (now - _win_hdr_map_time) >= _HDR_CACHE_TTL:
        _win_hdr_map = _query_windows_display_hdr()
        _win_hdr_map_time = now
    if not _win_hdr_map:
        return None
    key = str(screen_name).strip().lower()
    for name, info in _win_hdr_map.items():
        path = str(info.get('path') or '')
        if not path:
            continue
        gdi = str(info.get('gdi') or '').lower()
        if key == name or key == gdi or key in name or name in key:
            return path
    return None


def get_windows_display_peak_luminance(screen_name=None):
    """显示器实际 HDR 峰值亮度（nits）；取不到返回 None。

    screen_name 为播放窗口所在显示器名（Qt 的 QScreen.name()，形如 \\\\.\\DISPLAY1）。

    回退顺序：
    1. DXGI 1.6 MaxLuminance，按 DeviceName 匹配播放窗口所在输出；
    2. 同一份 DXGI 结果里第一台峰值有效的显示器（老行为，保持不变）；
    3. DXGI 不可用时读 EDID CTA-861 HDR 静态元数据的最大亮度，
       按 DISPLAYCONFIG monitorDevicePath 精确匹配注册表条目；
    4. 所有 EDID 峰值唯一一致时取该值；
    5. 都没有返回 None，由调用方沿用 1000 的安全默认，不猜一个数。

    结果缓存 30 秒；查询失败缓存空结果，避免每次播放重复枚举。
    """
    import time
    global _win_peak_cache, _win_peak_time
    now = time.monotonic()
    if _win_peak_cache is None or (now - _win_peak_time) >= _HDR_CACHE_TTL:
        _win_peak_cache = {
            'dxgi': _query_windows_display_peak_list() or [],
            'edid': _query_edid_peak_list() or [],
        }
        _win_peak_time = now

    cache = _win_peak_cache if isinstance(_win_peak_cache, dict) else {}
    dxgi = cache.get('dxgi') or []

    if screen_name and dxgi:
        key = str(screen_name).strip().lower()
        for name, peak in dxgi:
            gdi = str(name).strip().lower()
            if key == gdi or key in gdi or gdi in key:
                logger.info(f"显示器峰值(DXGI/{screen_name}): {peak:.0f}nit")
                return peak

    if dxgi:
        logger.info(f"显示器峰值(DXGI/{dxgi[0][0]}): {dxgi[0][1]:.0f}nit")
        return dxgi[0][1]

    edid = cache.get('edid') or []
    if not edid:
        return None

    path = _screen_monitor_path(screen_name)
    if path:
        parts = path.split('#')
        if len(parts) >= 3:
            hwid = parts[1].strip().lower()
            inst = parts[2].strip().lower()
            for entry in edid:
                if (str(entry.get('hwid')).strip().lower() == hwid
                        and str(entry.get('instance')).strip().lower() == inst):
                    peak = float(entry['peak'])
                    logger.info(
                        f"显示器峰值(EDID/{entry['hwid']}/{entry['instance']}): "
                        f"{peak:.0f}nit")
                    return peak

    values = {round(float(e['peak']), 1) for e in edid}
    if len(values) == 1:
        value = values.pop()
        logger.info(f"显示器峰值(EDID/唯一值): {value:.0f}nit")
        return value
    logger.debug(f"EDID 峰值无法唯一定位（{len(values)} 种取值），按取不到处理")
    return None


# ==================== 杜比视界能力（三态） ====================
#
# 能力判断必须按设备真实探测，不能按平台/品牌写死：别的用户可能是显示器支持杜比、
# 电视不支持。这里用三态而不是布尔，“不知道”不能当成“支持”，也不能当成“不支持”
# 后就放心输出 DV——两者都走同一条安全路径（按片源基础层输出）。

DV_STATE_SUPPORTED = 'supported'
DV_STATE_UNSUPPORTED = 'unsupported'
DV_STATE_UNKNOWN = 'unknown'

_DV_STATES = (DV_STATE_SUPPORTED, DV_STATE_UNSUPPORTED, DV_STATE_UNKNOWN)


def get_dolby_vision_output_capability(screen_name=None) -> str:
    """屏幕链路能否把杜比视界原样送出去（面板 + 输出通路）。

    Windows 的 DISPLAYCONFIG / DXGI 没有杜比标志位，应用也没有提交 DV 元数据的
    接口，所以真实探测结果只能是 unknown。unknown 与 unsupported 走同一条安全
    路径（按 HDR10/HLG 基础层输出），区别只在诊断面板的措辞。

    开发者自检：环境变量 GUANGYU_DV_PANEL=supported|unsupported|unknown
    可强制三态，用来验证各分支行为。
    """
    override = (os.environ.get('GUANGYU_DV_PANEL') or '').strip().lower()
    if override in _DV_STATES:
        logger.info(f"杜比视界面板能力(开发者覆盖): {override}")
        return override
    logger.info(f"杜比视界面板能力({screen_name or '当前屏'}): unknown（系统未提供杜比能力接口）")
    return DV_STATE_UNKNOWN


def get_renderer_dv_convert_capability(vo: str) -> str:
    """渲染器能否把杜比视界正确转换成 PQ/SDR（与面板能力无关）。

    gpu-next / libmpv 走 libplacebo，具备 DOVI 解析与 ICtCp 转换能力；
    老的 gpu / direct3d 管线没有可靠支持，按 unknown 处理（不尝试猜测）。
    """
    v = (vo or '').strip().lower()
    if v in ('gpu-next', 'libmpv'):
        return DV_STATE_SUPPORTED
    return DV_STATE_UNKNOWN


# ==================== 杜比视界 profile 传递 ====================
#
# mpv 不暴露 DV profile，直写路径连 DV 标记都读不到，所以 profile 只能在
# ffprobe 扫描阶段解析，再按播放地址带到播放会话。本地文件没有扫描结果时，
# 播放前补一次带缓存的探测（只探测真实存在的本地路径）。

_dv_profile_cache = {}
_DV_PROBE_TIMEOUT = 4


def register_dv_profile(url: str, profile) -> None:
    """扫描阶段登记某个地址的杜比 profile（None 表示探测过但没有）。"""
    if not url:
        return
    try:
        _dv_profile_cache[str(url)] = int(profile) if profile is not None else None
    except (TypeError, ValueError):
        _dv_profile_cache[str(url)] = None


def get_dv_profile(url: str):
    """取扫描阶段登记的 profile；未登记返回 None（未知，按基础层安全处理）。"""
    if not url:
        return None
    return _dv_profile_cache.get(str(url))


def extract_dv_info_from_stream(video_stream: dict):
    """从 ffprobe 视频流信息里解析 (dv_profile, bl_signal_compatibility_id)。"""
    try:
        for sd in (video_stream.get('side_data_list') or []):
            if sd.get('dv_profile') is not None:
                profile = int(sd.get('dv_profile'))
                bl = sd.get('dv_bl_signal_compatibility_id')
                return profile, (int(bl) if bl is not None else None)
    except (TypeError, ValueError):
        pass
    return None, None


def probe_dv_profile(path: str):
    """本地文件兜底探测杜比 profile（结果按路径缓存，含“不是杜比”）。

    只对真实存在的本地路径执行，网络地址直接返回 None，避免播放时卡顿。
    """
    if not path:
        return None
    key = str(path)
    if key in _dv_profile_cache:
        return _dv_profile_cache[key]
    profile = None
    try:
        if os.path.exists(key):
            from utils.platform_utils import get_ffprobe_path
            exe = get_ffprobe_path()
            if exe:
                import json
                kwargs = {}
                try:
                    from utils.platform_utils import get_subprocess_creation_flags
                    kwargs['creationflags'] = get_subprocess_creation_flags()
                except Exception:
                    pass
                proc = subprocess.run(
                    [exe, '-v', 'error', '-select_streams', 'v:0',
                     '-show_streams', '-of', 'json', key],
                    capture_output=True, timeout=_DV_PROBE_TIMEOUT, **kwargs)
                data = json.loads((proc.stdout or b'').decode('utf-8', 'replace') or '{}')
                streams = data.get('streams') or []
                if streams:
                    profile, _bl = extract_dv_info_from_stream(streams[0])
    except Exception as _e:
        logger.debug(f"杜比 profile 探测失败: {_e}")
    _dv_profile_cache[key] = profile
    return profile


