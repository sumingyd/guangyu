from core.version import APP_USER_AGENT
import os

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QIcon
import asyncio
import platform
import sys
from core.log_manager import global_logger as logger
from ..floating_dialog import FloatingDialog


class AboutDialog(FloatingDialog):
    DEFAULT_VERSION = None

    def __init__(self, parent=None):
        super().__init__(parent, stay_on_top=False)
        from core.version import CURRENT_VERSION, BUILD_DATE
        self.current_version = CURRENT_VERSION
        self.build_date = BUILD_DATE
        self.language_manager = getattr(parent, 'language_manager', None)
        if not self.language_manager:
            from core.language_manager import LanguageManager
            self.language_manager = LanguageManager()
        from ..styles import AppStyles
        self._colors = AppStyles._get_colors()
        self._init_ui()
        self._latest_version_result = None
        self._closing = False

        from ..theme_manager import get_theme_manager
        get_theme_manager().register_window(self)

    def closeEvent(self, event):
        self._closing = True
        if hasattr(self, '_version_thread') and self._version_thread.is_alive():
            self._version_thread.join(timeout=2.0)
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)

    def _init_ui(self):
        """初始化 UI"""
        from ui.styles import AppStyles
        tr = self.language_manager.tr
        c = self._colors
        self.setWindowTitle(tr("about_dialog_title", "About GuangYu"))
        self.setMinimumSize(420, 380)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(0)

        # 图标居中显示
        logo_label = QtWidgets.QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from utils.general_utils import get_icon_path
        ico_path = get_icon_path()
        if os.path.exists(ico_path):
            # 使用 QIcon 读取 ICO 文件，然后获取最大尺寸的 pixmap
            icon = QIcon(ico_path)
            # 获取所有可用尺寸
            available_sizes = icon.availableSizes()
            if available_sizes:
                # 找到最大的尺寸
                max_size = max(available_sizes, key=lambda s: s.width() * s.height())
                pixmap = icon.pixmap(max_size)
            else:
                pixmap = icon.pixmap(256, 256)  # 默认使用 256x256

            if not pixmap.isNull():
                # 缩放到 128x128，保持宽高比，使用平滑变换
                scaled = pixmap.scaled(
                    128, 128,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(scaled)
        else:

            tv_icon_path = AppStyles.get_icon('tv', AppStyles.get_color('window_text'), 48)
            if tv_icon_path:
                logo_label.setPixmap(QIcon(tv_icon_path).pixmap(128, 128))
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("background-color: transparent;")
        main_layout.addWidget(logo_label)

        main_layout.addSpacing(16)

        card = QtWidgets.QWidget()
        r = AppStyles._get_style_border_radius()
        card.setStyleSheet(f"""
            QWidget#infoCard {{
                background-color: {c['alternate_base']};
                border-radius: {r}px;
                padding: 4px;
            }}
        """)
        card.setObjectName("infoCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        lbl_style = f"font-size: 12px; color: {c['window_text']}; background-color: transparent;"
        val_style = f"font-size: 12px; color: {c['accent']}; background-color: transparent;"

        rows = [
            (f"{tr('current_version', 'Current Version')}", self.current_version, True),
            (f"{tr('latest_version', 'Latest Version')}", None, True),
            (f"{tr('build_date', 'Build Date')}", self.build_date, False),
            (f"{tr('qt_version', 'QT Version')}", QtCore.qVersion(), False),
        ]

        self.latest_version_value = None
        for label_text, value_text, is_accent in rows:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            lbl = QtWidgets.QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setFixedWidth(100)
            val = QtWidgets.QLabel(value_text if value_text else tr("checking_update", "Checking..."))
            val.setStyleSheet(val_style if is_accent else lbl_style)
            if value_text is None:
                self.latest_version_value = val
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            card_layout.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {c['mid']}; max-height: 1px; margin: 4px 0;")
        card_layout.addWidget(sep)

        sys_row = QtWidgets.QHBoxLayout()
        sys_row.setSpacing(8)
        sys_lbl = QtWidgets.QLabel(f"{tr('system_info', 'System Info')}")
        sys_lbl.setStyleSheet(lbl_style)
        sys_lbl.setFixedWidth(100)
        sys_val = QtWidgets.QLabel(f"Python {sys.version.split()[0]}, {platform.system()} {platform.release()}")
        sys_val.setStyleSheet(lbl_style)
        sys_row.addWidget(sys_lbl)
        sys_row.addWidget(sys_val)
        sys_row.addStretch()
        card_layout.addLayout(sys_row)

        main_layout.addWidget(card)

        main_layout.addSpacing(16)

        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setSpacing(12)

        self.copyright_label = QtWidgets.QLabel(tr("copyright_text", "© 2025-2026 GuangYu"))
        self.copyright_label.setStyleSheet(
            f"font-size: 10px; color: {c['player_panel_secondary']};"
            f" background-color: transparent;"
        )

        github_link = QtWidgets.QLabel()
        github_link.setText(
            f'<a href="https://github.com/sumingyd/guangyu" '
            f'style="color: {c["accent"]}; text-decoration: none; font-size: 10px;">'
            f'{tr("github_repo", "GitHub Repository")}</a>'
        )
        github_link.setOpenExternalLinks(True)

        close_btn = QtWidgets.QPushButton(tr("close_button", "Close"))
        close_btn.setFixedSize(72, 28)
        from ui.styles import AppStyles
        close_btn.setStyleSheet(AppStyles.button_style())
        close_btn.clicked.connect(self.close)

        # 在线更新按钮（默认隐藏，版本检查发现新版本后显示）
        self._update_btn = QtWidgets.QPushButton(
            tr("update_progress_title", "Online Update")
        )
        self._update_btn.setFixedSize(90, 28)
        self._update_btn.setStyleSheet(AppStyles.button_style())
        self._update_btn.setVisible(False)
        self._update_btn.clicked.connect(self._on_update_clicked)

        bottom_layout.addWidget(self.copyright_label)
        bottom_layout.addWidget(github_link)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self._update_btn)
        bottom_layout.addWidget(close_btn)

        main_layout.addLayout(bottom_layout)

        self.setStyleSheet(AppStyles.dialog_style())
        # 使用线程异步检查版本，不阻塞 UI
        import threading
        self._version_thread = threading.Thread(target=self._check_version_thread, daemon=True)
        self._version_thread.start()

    def _check_version_thread(self):
        """在线程中检查版本（不阻塞 UI）"""
        tr = self.language_manager.tr
        logger.info("开始检查版本...")
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                latest_version, publish_date = loop.run_until_complete(
                    asyncio.wait_for(self._get_latest_version(), timeout=5)
                )
                if self._closing:
                    return
                self._latest_version_result = latest_version
                from utils.thread_safety import invoke_on_thread
                invoke_on_thread(self, self._update_version_ui)
            finally:
                loop.close()
        except asyncio.TimeoutError:
            if self._closing:
                return
            logger.error("版本检查超时")
            self._latest_version_result = tr("request_timeout_text", "(Request Timeout)")
            from utils.thread_safety import invoke_on_thread
            invoke_on_thread(self, self._update_version_ui)
        except Exception as e:
            if self._closing:
                return
            logger.error(f"版本检查失败：{e}")
            self._latest_version_result = tr("fetch_failed_text", "(Fetch Failed)")
            from utils.thread_safety import invoke_on_thread
            invoke_on_thread(self, self._update_version_ui)


    def _update_version_ui(self):
        """在主线程中更新版本显示"""
        logger.debug(f"更新 UI 版本号：{self._latest_version_result}")
        try:
            if hasattr(self, 'latest_version_value'):
                self.latest_version_value.setText(self._latest_version_result)

            # 检查是否需要显示"在线更新"按钮
            latest = self._latest_version_result
            if latest and not latest.startswith("("):
                from core.version import CURRENT_VERSION
                if self._is_newer_version(CURRENT_VERSION, latest):
                    if hasattr(self, '_update_btn'):
                        self._update_btn.setVisible(True)
        except RuntimeError:
            pass

    def _is_newer_version(self, current_version, latest_version):
        """比较版本号，判断最新版本是否比当前版本新（与主更新器共用同一实现）"""
        from controllers.update_controller import is_newer_version
        return is_newer_version(current_version, latest_version)

    def _on_update_clicked(self):
        """点击"在线更新"按钮"""
        parent = self.parent()
        if parent and hasattr(parent, 'update_ctrl'):
            self.close()
            parent.update_ctrl.download_and_install()

    async def _get_latest_version(self):
        tr = self.language_manager.tr
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/repos/sumingyd/guangyu/releases/latest",
                    headers={'User-Agent': APP_USER_AGENT}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        version = data.get('tag_name', '').lstrip('v')
                        publish_date = data.get('published_at', '')
                        return version, publish_date
                    elif response.status == 403:
                        return tr("api_limit_text", "(API Limit)"), ""
                    else:
                        return tr("fetch_failed_text", "(Fetch Failed)"), ""
        except asyncio.TimeoutError:
            return tr("request_timeout_text", "(Request Timeout)"), ""
        except Exception as e:
            logger.error(f"获取最新版本失败: {str(e)}")
            return tr("fetch_failed_text", "(Fetch Failed)"), ""

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            widget = self.childAt(event.position().toPoint())
            if isinstance(widget, QtWidgets.QLabel) and widget.openExternalLinks():
                return
        super().mousePressEvent(event)

    def reapply_styles(self):
        from ..styles import AppStyles
        self._colors = AppStyles._get_colors()
        c = self._colors
        lbl_style = f"font-size: 12px; color: {c['window_text']}; background-color: transparent;"
        val_style = f"font-size: 12px; color: {c['accent']}; background-color: transparent;"
        for child in self.findChildren(QtWidgets.QLabel):
            child_name = child.objectName()
            if child_name == "infoCard":
                continue
            if child == getattr(self, 'copyright_label', None):
                child.setStyleSheet(
                    f"font-size: 10px; color: {c['player_panel_secondary']};"
                    f" background-color: transparent;"
                )
                continue
            existing = child.styleSheet()
            val_parts = val_style.split(';')
            val_check = val_parts[1] if len(val_parts) > 1 else ''
            if 'accent' in existing or val_check in existing:
                child.setStyleSheet(val_style)
            else:
                child.setStyleSheet(lbl_style)
        for child in self.findChildren(QtWidgets.QPushButton):
            child.setStyleSheet(AppStyles.button_style())
        card = self.findChild(QtWidgets.QWidget, "infoCard")
        if card:
            r = AppStyles._get_style_border_radius()
            card.setStyleSheet(f"""
                QWidget#infoCard {{
                    background-color: {c['alternate_base']};
                    border-radius: {r}px;
                    padding: 4px;
                }}
            """)
