import sys
import os

from utils.early_init import setup_environment
from utils.delay_constants import DelayMs
setup_environment()

# 尽早安装异常兜底与数据迁移：即使后续 Qt 导入/初始化失败也能留下 crash.log
from utils.crash_handler import install_crash_handler
from utils.app_paths import migrate_legacy_data
_crash_log_path = install_crash_handler()
migrate_legacy_data()

# 尽早尝试导入 numpy：失败时只记录诊断，不影响后续启动（频谱/音频可视化降级）
from utils.numpy_compat import should_show_hint, unavailable_message  # noqa: E402


def _log_locations(crash_log_path: str) -> None:
    """把日志目录与各日志文件的绝对路径写进日志开头，便于用户对照排查。"""
    try:
        from core.log_manager import global_logger
        from utils.app_paths import get_log_dir
        global_logger.info(f"日志目录: {get_log_dir()}")
        global_logger.info(f"运行日志: {global_logger.log_file}")
        global_logger.info(f"崩溃日志: {crash_log_path}")
    except Exception:
        pass


_log_locations(_crash_log_path)

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen


def _warn_if_native_wayland(app):
    """Wayland 原生平台下视频无法嵌入窗口，给出可读提示而不是黑屏/静默失败。"""
    if not sys.platform.startswith('linux'):
        return
    try:
        platform_name = (app.platformName() or '').strip().lower()
    except Exception:
        return
    if not platform_name.startswith('wayland'):
        return
    message = (
        '当前运行在 Wayland 原生会话，视频画面依赖 X11 窗口嵌入，可能无法显示。\n'
        '请安装并启用 XWayland，或设置环境变量 QT_QPA_PLATFORM=xcb 后重新启动。\n'
        '频道列表与节目单仍可正常使用。'
    )
    try:
        from core.log_manager import global_logger as logger
        logger.warning(message.replace('\n', ' '))
    except Exception:
        pass
    QTimer.singleShot(0, lambda: QMessageBox.warning(None, 'GuangYu', message))



def _suppress_qfont_pointsize_warning(msg_type, context, msg):
    if msg_type == QtMsgType.QtWarningMsg and 'setPointSize' in msg and 'Point size <= 0' in msg:
        return
    if msg_type == QtMsgType.QtWarningMsg:
        tag = 'Qt Warning'
    elif msg_type == QtMsgType.QtCriticalMsg:
        tag = 'Qt Critical'
    else:
        return
    # PyInstaller --windowed 模式下 sys.stderr 为 None，直接写入会崩溃
    stream = sys.stderr if sys.stderr is not None else sys.__stderr__
    if stream is not None:
        try:
            stream.write(f"{tag}: {msg}\n")
        except Exception:
            pass


def _open_path_from_os(player, file_path):
    """按扩展名打开命令行/访达传入的文件。返回是否已处理。"""
    if not file_path or not os.path.isfile(file_path):
        return False
    lower = file_path.lower()
    if lower.endswith(('.m3u', '.m3u8', '.txt')):
        QTimer.singleShot(
            DelayMs.SPLASH_DISMISS,
            lambda fp=file_path: player.settings_ops.open_specific_file(fp),
        )
        return True
    if lower.endswith(('.mp4', '.mkv', '.avi', '.mov',
                       '.flv', '.wmv', '.ts', '.webm',
                       '.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus',
                       '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta',
                       '.dts', '.ac3', '.mid', '.midi')):
        def _open_video_from_os(fp=file_path):
            player._add_local_video_and_track(fp)
        QTimer.singleShot(DelayMs.SPLASH_DISMISS, _open_video_from_os)
        return True
    return False


class _FileOpenEventFilter(QObject):
    """接住 macOS 的 QFileOpenEvent。

    Info.plist 声明了 m3u/m3u8 文档类型，用户双击播放列表或用"打开方式"时
    系统不会把路径放进 argv，而是投递 QFileOpenEvent；没有这个过滤器时
    应用被唤起却什么都不打开。
    """

    def __init__(self, player):
        super().__init__()
        self._player = player

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                QTimer.singleShot(0, lambda p=path: _open_path_from_os(self._player, p))
                return True
        return False


def main():

    qInstallMessageHandler(_suppress_qfont_pointsize_warning)

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except (AttributeError, TypeError):
        try:
            from PySide6.QtCore import QHighDpiScaleFactorRoundingPolicy
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                QHighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except ImportError:
            pass

    app = QApplication(sys.argv)
    _warn_if_native_wayland(app)

    splash = None
    try:
        from utils.general_utils import get_icon_path
        ico_path = get_icon_path()
        if os.path.exists(ico_path):
            splash_pixmap = QIcon(ico_path).pixmap(128, 128)
        else:
            splash_pixmap = QPixmap(128, 128)
            splash_pixmap.fill(Qt.GlobalColor.transparent)
        splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint)
        splash.showMessage(
            "Loading...",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor(200, 200, 200))
        try:
            from core.config_manager import ConfigManager
            cfg = ConfigManager()
            wx = int(cfg.get_value('UI', 'window_x') or 100)
            wy = int(cfg.get_value('UI', 'window_y') or 100)
            ww = int(cfg.get_value('UI', 'window_width') or 1280)
            wh = int(cfg.get_value('UI', 'window_height') or 780)
            sp = splash.size()
            from utils.platform_utils import wayland_move
            wayland_move(splash, wx + (ww - sp.width()) // 2, wy + (wh - sp.height()) // 2)
        except Exception:
            pass
        splash.show()
        app.processEvents()
    except Exception:
        pass

    from pyqt_player import IPTVPlayer

    player = IPTVPlayer()

    # macOS 双击 m3u/视频文件时路径不在 argv 里，而是以 QFileOpenEvent 投递；
    # 其他平台不会产生该事件，装上也无副作用。
    file_open_filter = _FileOpenEventFilter(player)
    app.installEventFilter(file_open_filter)
    app._file_open_filter = file_open_filter  # 防止被 GC

    if splash:
        splash.finish(player)

    # numpy 不可用（常见于缺少 SSE4.x 的老 CPU）：明确告知降级范围，程序继续可用
    if should_show_hint():
        QTimer.singleShot(
            300,
            lambda: QMessageBox.warning(player, 'GuangYu', unavailable_message()))

    if len(sys.argv) > 1:
        _open_path_from_os(player, sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()