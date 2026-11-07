import sys
import os

from utils.early_init import setup_environment
from utils.delay_constants import DelayMs
setup_environment()

# 尽早安装异常兜底与数据迁移：即使后续 Qt 导入/初始化失败也能留下 crash.log
from utils.crash_handler import install_crash_handler
from utils.app_paths import migrate_legacy_data
install_crash_handler()
migrate_legacy_data()

from PySide6.QtCore import QTimer, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen



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

    if splash:
        splash.finish(player)

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.isfile(file_path):
            if file_path.lower().endswith(('.m3u', '.m3u8', '.txt')):
                QTimer.singleShot(DelayMs.SPLASH_DISMISS, lambda fp=file_path: player.settings_ops.open_specific_file(fp))
            elif file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov',
                                             '.flv', '.wmv', '.ts', '.webm',
                                             '.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus',
                                             '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta',
                                             '.dts', '.ac3', '.mid', '.midi')):
                def _open_video_from_cmdline(fp=file_path):
                    player._add_local_video_and_track(fp)
                QTimer.singleShot(DelayMs.SPLASH_DISMISS, _open_video_from_cmdline)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()