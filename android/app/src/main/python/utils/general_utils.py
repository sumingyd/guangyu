try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QApplication, QMenu
    _HAS_QT = True
except ImportError:
    # Android（p4a 共享包）/ 无 GUI 环境没有 PySide6；
    # 本模块被 server 初始化路径导入，必须保持可导入。
    # Qt 类型仅被桌面端 GUI 辅助函数使用。
    _HAS_QT = False
    Qt = QIcon = QPixmap = QApplication = QMenu = None
import os
import sys
import logging
import time
from typing import Any, Dict
from utils.platform_utils import is_windows


def get_display_channel_name(channel: Dict[str, Any], language_manager=None) -> str:
    """统一的频道显示名称获取函数

    Args:
        channel: 频道数据字典
        language_manager: 语言管理器实例（可选，用于国际化）

    Returns:
        str: 格式化后的频道显示名称

    功能：
    - 支持国际化（通过language_manager）
    - 处理逗号分隔的名称（取最后一部分）
    - 添加频道号前缀（如果有tvg_chno）
    - 添加分组名后缀（如果不同于默认分组）
    """
    if not channel:
        return 'Unknown Channel'

    tr = getattr(language_manager, 'tr', lambda x, y: x) if language_manager else lambda x, y: x

    all_tags = channel.get('_all_tags', {})
    name = all_tags.get('name') or channel.get('name', '') or ''
    number = channel.get('tvg_chno', '')
    group_name = all_tags.get('group-name') or ''

    # 处理逗号分隔的名称（如 "CCTV1,央视一套" 取 "央视一套"）
    if ',' in name:
        parts = name.split(',', 1)
        if len(parts) > 1 and parts[1].strip():
            name = parts[1].strip()

    # 添加频道号
    if number and name:
        name = f"{number} {name}"

    # 添加分组名（如果不同于默认分组）
    if group_name and group_name != channel.get('group', ''):
        name = f"{name} ({group_name})"

    return name or tr('unknown_channel', 'Unknown Channel')


def get_resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径"""
    if getattr(sys, 'frozen', False):
        # 打包成exe的情况
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


def get_icon_path() -> str:
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys.platform == 'darwin':
        icns = os.path.join(base_path, 'resources', 'logo.icns')
        if os.path.exists(icns):
            return icns
        png = os.path.join(base_path, 'resources', 'logo.png')
        if os.path.exists(png):
            return png
    if sys.platform.startswith('linux'):
        png = os.path.join(base_path, 'resources', 'logo.png')
        if os.path.exists(png):
            return png
    ico = os.path.join(base_path, 'resources', 'logo.ico')
    if os.path.exists(ico):
        return ico
    png = os.path.join(base_path, 'resources', 'logo.png')
    if os.path.exists(png):
        return png
    return os.path.join(base_path, 'resources', 'logo.ico')


def get_project_root() -> str:
    """获取项目根目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # 从utils目录向上两级到项目根目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def set_default_channel_logo(label, width: int = 100, height: int = 36) -> None:
    """将 QLabel 设为应用默认台标图标（居中缩放适应，不拉伸）。
    当频道无 logo 或处于未选择状态时调用，避免显示 emoji 占位符。
    兼容 PyInstaller 打包和开发环境。
    """

    ico_path = get_icon_path()
    label.setPixmap(QPixmap())  # 先清除旧图
    if os.path.exists(ico_path):
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        # 请求 2x 分辨率像素，让 Qt 从 ICO 选最清晰帧
        req = int(max(width, height) * dpr)
        pixmap = QIcon(ico_path).pixmap(req, req)
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(dpr)
            # 缩放到控件尺寸，保持宽高比，平滑缩放
            scaled = pixmap.scaled(
                width, height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            label.setPixmap(scaled)
            label.setText("")
            return
    # 无 ico 文件时使用 SVG 图标
    from ui.styles import AppStyles
    tv_icon_path = AppStyles.get_icon('tv', AppStyles._get_colors().get('window_text', '#ffffff'), 48)
    if tv_icon_path:
        label.setPixmap(QIcon(tv_icon_path).pixmap(label.width() or 48, label.height() or 48))
    else:
        label.setText("")


def is_valid_url(url: str) -> bool:
    """检查URL是否有效"""
    if not url or not isinstance(url, str):
        return False

    # 基本URL格式检查
    url = url.strip()
    if not url:
        return False

    # 检查常见协议
    valid_schemes = ('http://', 'https://', 'rtp://', 'udp://', 'rtsp://', 'file://')
    return any(url.startswith(scheme) for scheme in valid_schemes)


def sanitize_http_header_value(value: str) -> str:
    """清除 HTTP 头值中的非 ASCII 字符。

    requests 库使用 latin-1 编码 header 值，如果配置的 User-Agent 或
    Referer 包含中文等非 latin-1 字符，会导致
    ``'latin-1' codec can't encode characters in position 0-1`` 错误。

    本函数将非 ASCII 字符替换为空字符串，并记录警告日志。
    """
    if not value:
        return value
    try:
        value.encode('latin-1')
        return value
    except UnicodeEncodeError:
        # 保留所有 latin-1 可编码字符，丢弃其余字符
        sanitized = value.encode('latin-1', errors='ignore').decode('latin-1')
        if sanitized != value:
            try:
                from core.log_manager import global_logger as logger
                logger.warning(
                    f"HTTP头值包含非ASCII字符，已清洗: 原始值前30字符={repr(value[:30])}"
                )
            except Exception:
                pass
        return sanitized


def build_mpv_http_header_fields(headers: str, referer: str = '') -> str:
    """把多行 HTTP 头文本转换为 mpv ``http-header-fields`` 可解析的字符串。

    mpv 的 http-header-fields 是 string list：条目之间用**真实换行**分隔。
    实测（mpv 0.41）：
    - 传入字面的反斜杠+n 不会被当作分隔符，只会污染第一个头的值；
    - 值内的逗号会被当作条目分隔符，必须转义（逗号前加反斜杠）；
    - 反斜杠本身不参与转义，原样保留，因此不能重复转义；
    - 逐条 ``add`` 该属性返回 invalid parameter，不可用。

    因此这里按行拆分、丢弃空行、仅转义逗号，最后用真实换行拼接。
    referer 非空且列表里尚无 Referer 时追加一条。
    """
    items = []
    has_referer = False
    text = (headers or '').replace('\r\n', '\n').replace('\r', '\n')
    for raw in text.split('\n'):
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith('referer:'):
            has_referer = True
        items.append(line.replace(',', '\\,'))
    if referer:
        referer = referer.strip()
        if referer and not has_referer:
            items.append(f'Referer: {referer}'.replace(',', '\\,'))
    return '\n'.join(items)


def format_file_size(size_bytes: float) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    if size_bytes < 0:
        return f"{size_bytes:.2f} B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.2f} {size_names[i]}"


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """截断文本，超过最大长度时添加后缀"""
    if len(text) <= max_length:
        return text
    if max_length <= len(suffix):
        return suffix[:max_length]
    return text[:max_length - len(suffix)] + suffix


def safe_connect(signal, slot):
    """安全连接信号，避免重复连接

    Args:
        signal: PyQt信号对象
        slot: 槽函数或可调用对象

    Returns:
        bool: 连接是否成功
    """
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass
    except Exception:
        pass

    try:
        signal.connect(slot)
        return True
    except Exception as e:
        logging.getLogger('utils').error(f"连接信号失败: {e}")
        return False


def safe_connect_button(button, callback):
    """安全连接按钮点击信号

    Args:
        button: QPushButton或类似按钮对象
        callback: 回调函数

    Returns:
        bool: 连接是否成功
    """
    return safe_connect(button.clicked, callback)


def format_time(seconds: float) -> str:
    """格式化时间（秒）为时分秒格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    elif minutes > 0:
        return f"{minutes:02d}:{secs:02d}"
    else:
        return f"00:{secs:02d}"


def retry_operation(operation, max_retries: int = 3, delay: float = 1.0, exceptions: tuple = (Exception,)) -> Any:
    """带重试机制的操作执行

    Args:
        operation: 要执行的操作函数
        max_retries: 最大重试次数
        delay: 重试间隔（秒）
        exceptions: 要捕获的异常类型

    Returns:
        Any: 操作的返回值

    Raises:
        Exception: 如果所有重试都失败
    """
    actual_retries = max(1, max_retries)
    for attempt in range(actual_retries):
        try:
            return operation()
        except exceptions as e:
            if attempt == actual_retries - 1:
                raise
            time.sleep(delay)
            logging.getLogger('utils').warning(f"操作失败，重试 {attempt + 1}/{actual_retries}: {e}")


def deep_merge_dicts(target: Dict, source: Dict) -> Dict:
    """深度合并两个字典

    Args:
        target: 目标字典
        source: 源字典

    Returns:
        Dict: 合并后的字典
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge_dicts(target[key], value)
        else:
            target[key] = value
    return target


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除或替换无效字符

    Args:
        filename: 原始文件名

    Returns:
        str: 清理后的文件名
    """
    # 移除或替换Windows文件名中的无效字符
    invalid_chars = '\\/:*?"<>|'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename.strip()


def _get_prog_id_for_ext(ext):
    ext_key = ext.lstrip('.').replace('.', '_')
    return f"IPTVScannerEditor.{ext_key}"


def _get_exe_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" "%1"'
    else:
        return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" "%1"'


def _ensure_prog_id(prog_id, app_name=None):
    try:
        import winreg
    except ImportError:
        return False
    try:
        if app_name is None:
            app_name = "GuangYu"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}", 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, app_name)

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\shell\\open\\command", 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, _get_exe_command())

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}\\DefaultIcon", 0, winreg.KEY_WRITE) as key:
            if getattr(sys, 'frozen', False):
                icon_path = sys.executable
            else:
                icon_path = get_icon_path()
            if os.path.exists(icon_path):
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, icon_path)
        return True
    except Exception as e:
        logging.warning(f"创建ProgID失败: {e}")
        return False


def _delete_prog_id(prog_id):
    try:
        import winreg
    except ImportError:
        return
    for sub in ["\\shell\\open\\command", "\\shell\\open", "\\shell", "\\DefaultIcon", ""]:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{prog_id}{sub}")
        except Exception:
            pass


def _notify_shell_change():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x1000, None, None)
    except Exception:
        pass


def register_extension(ext: str) -> bool:
    if not is_windows():
        return False
    try:
        import winreg
    except ImportError:
        return False

    prog_id = _get_prog_id_for_ext(ext)
    if not _ensure_prog_id(prog_id):
        return False

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}\\OpenWithProgids", 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, prog_id, 0, winreg.REG_NONE, b"")
    except Exception as e:
        logging.warning(f"注册 {ext} 文件关联失败: {e}")
        return False

    _notify_shell_change()
    return True


def unregister_extension(ext: str) -> bool:
    if not is_windows():
        return False
    try:
        import winreg
    except ImportError:
        return False

    prog_id = _get_prog_id_for_ext(ext)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}\\OpenWithProgids", 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, prog_id)
    except Exception:
        pass

    _delete_prog_id(prog_id)
    _notify_shell_change()
    return True


def is_extension_registered(ext: str) -> bool:
    if not is_windows():
        return False
    try:
        import winreg
    except ImportError:
        return False
    prog_id = _get_prog_id_for_ext(ext)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"Software\\Classes\\{ext}\\OpenWithProgids", 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, prog_id)
        return True
    except Exception:
        return False


def register_file_association() -> bool:
    extensions = ['.m3u', '.m3u8']
    success = True
    for ext in extensions:
        if not register_extension(ext):
            success = False
    return success


def unregister_file_association() -> bool:
    extensions = ['.m3u', '.m3u8']
    success = True
    for ext in extensions:
        if not unregister_extension(ext):
            success = False
    return success


def is_file_association_registered() -> bool:
    return is_extension_registered('.m3u')


def calculate_adaptive_delay(base_delay_ms: int = 200, min_delay_ms: int = 50, max_delay_ms: int = 500) -> int:
    """根据设备性能自适应计算延迟时间"""
    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        cpu_count = psutil.cpu_count() or 2
        if memory_gb > 8 and cpu_count > 4:
            factor = 0.5
        elif memory_gb >= 4 and cpu_count >= 2:
            factor = 1.0
        else:
            factor = 1.5
        adaptive_delay = int(base_delay_ms * factor)
        return max(min_delay_ms, min(max_delay_ms, adaptive_delay))
    except ImportError:
        return base_delay_ms
    except Exception:
        return base_delay_ms


def redact_url(url: str) -> str:
    """移除 URL 中的用户凭证信息，用于日志记录。"""
    if not url:
        return url
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.username or p.password:
            return urlunparse((p.scheme, p.hostname or '', p.path, '', '', ''))
        return url
    except Exception:
        return url


def setup_i18n_context_menu(widget, language_manager=None):
    """为 QLineEdit/QPlainTextEdit 设置国际化右键菜单，适配暗色/日间主题。"""
    try:
        from ui.styles import AppStyles
    except Exception:
        AppStyles = None

    tr = language_manager.tr if language_manager else (lambda k, d: d)

    def _show_menu(pos):
        menu = QMenu(widget)
        if AppStyles:
            try:
                menu.setStyleSheet(AppStyles.popup_dialog_style())
            except Exception:
                pass

        is_read_only = widget.isReadOnly()
        has_selection = widget.textCursor().hasSelection() if hasattr(widget, 'textCursor') else widget.hasSelectedText()
        if hasattr(widget, 'document'):
            can_undo = widget.document().isUndoAvailable()
            can_redo = widget.document().isRedoAvailable()
        else:
            can_undo = widget.isUndoAvailable() if hasattr(widget, 'isUndoAvailable') else False
            can_redo = widget.isRedoAvailable() if hasattr(widget, 'isRedoAvailable') else False
        clipboard_text = ''
        try:
            clipboard_text = QApplication.clipboard().text()
        except Exception:
            pass

        act_undo = menu.addAction(tr("ctx_undo", "撤销"))
        act_undo.setEnabled(can_undo and not is_read_only)
        act_redo = menu.addAction(tr("ctx_redo", "重做"))
        act_redo.setEnabled(can_redo and not is_read_only)
        menu.addSeparator()
        act_cut = menu.addAction(tr("ctx_cut", "剪切"))
        act_cut.setEnabled(has_selection and not is_read_only)
        act_copy = menu.addAction(tr("ctx_copy", "复制"))
        act_copy.setEnabled(has_selection)
        act_paste = menu.addAction(tr("ctx_paste", "粘贴"))
        act_paste.setEnabled(bool(clipboard_text) and not is_read_only)
        menu.addSeparator()
        act_select_all = menu.addAction(tr("ctx_select_all", "全选"))

        action = menu.exec(widget.viewport().mapToGlobal(pos) if hasattr(widget, 'viewport') else widget.mapToGlobal(pos))
        if action is None:
            return
        if action == act_undo:
            widget.undo()
        elif action == act_redo:
            widget.redo()
        elif action == act_cut:
            widget.cut()
        elif action == act_copy:
            widget.copy()
        elif action == act_paste:
            widget.paste()
        elif action == act_select_all:
            widget.selectAll()

    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    widget.customContextMenuRequested.connect(_show_menu)


def suppress_urllib3_warnings():
    """抑制 urllib3 SSL 警告"""
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except ImportError:
        pass
    except Exception:
        pass
    try:
        import logging as _logging
        _logging.getLogger('urllib3').setLevel(_logging.CRITICAL)
        _logging.getLogger('urllib3.connectionpool').setLevel(_logging.CRITICAL)
    except Exception:
        pass
