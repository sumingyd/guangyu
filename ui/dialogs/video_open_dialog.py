import os
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QSizePolicy,
    QStyle,
    QLineEdit,
    QInputDialog,
    QMenu,
)
from PySide6.QtCore import Qt, QDir, QSize, QTimer
from PySide6.QtGui import QAction
from utils.platform_utils import is_windows
from ..floating_dialog import FloatingDialog
from utils.delay_constants import DelayMs


_VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.m2ts', '.webm')
_AUDIO_EXTS = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma', '.m4a', '.ape', '.alac', '.wv', '.tta', '.dts', '.ac3', '.mid', '.midi')
_MEDIA_EXTS = _VIDEO_EXTS + _AUDIO_EXTS


class VideoOpenDialog(FloatingDialog):
    def __init__(self, parent=None, language_manager=None):
        try:
            super().__init__(parent, stay_on_top=False)
        except TypeError:
            super().__init__(parent)
        self._selected_path = None
        self._lm = language_manager
        self._current_dir = QDir.homePath()
        self._show_video_only = True
        self._show_audio_only = False

        self.setWindowTitle(self._tr("open_media", "打开音视频"))
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        from ui.styles import AppStyles
        self.setStyleSheet(AppStyles.popup_dialog_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        nav = QHBoxLayout()
        nav.setSpacing(4)

        self._up_btn = QPushButton(self._tr("parent_folder", "上级目录"))
        self._up_btn.setFixedWidth(90)
        self._up_btn.clicked.connect(self._go_up)
        self._up_btn.setToolTip(self._tr("parent_folder_tooltip", "返回上级目录"))
        nav.addWidget(self._up_btn)

        self._drive_btn = None
        self._drives_cache = None
        if is_windows():
            self._drive_btn = QPushButton(self._tr("drive", "盘符"))
            self._drive_btn.setFixedWidth(70)
            self._drive_btn.setMenu(self._build_drive_menu())
            self._drive_btn.setToolTip(self._tr("drive_list_tooltip", "选择磁盘/驱动器"))
            nav.addWidget(self._drive_btn)

        self._path_edit = QLineEdit(self._current_dir)
        self._path_edit.returnPressed.connect(self._on_path_entered)
        nav.addWidget(self._path_edit, 1)

        go_btn = QPushButton(self._tr("go", "转到"))
        go_btn.setFixedWidth(50)
        go_btn.clicked.connect(self._on_path_entered)
        go_btn.setToolTip(self._tr("go_to_tooltip", "转到指定路径"))
        nav.addWidget(go_btn)

        self._filter_combo = QComboBox()
        self._filter_combo.addItem(self._tr("media_files_only", "音视频文件"))
        self._filter_combo.addItem(self._tr("video_files_only", "仅视频文件"))
        self._filter_combo.addItem(self._tr("audio_files_only", "仅音频文件"))
        self._filter_combo.addItem(self._tr("all_files", "所有文件"))
        self._filter_combo.setFixedWidth(120)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._filter_combo.setToolTip(self._tr("filter_tooltip", "过滤文件类型"))
        nav.addWidget(self._filter_combo)

        layout.addLayout(nav)

        self._list = QListWidget()
        self._list.setObjectName("videoFileList")
        self._list.setIconSize(QSize(20, 20))
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.itemClicked.connect(self._on_single_click)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._select_btn = QPushButton(self._tr("select_confirm", "选定"))
        self._select_btn.setFixedWidth(100)
        self._select_btn.setDefault(True)
        self._select_btn.clicked.connect(self._on_select)
        self._select_btn.setToolTip(self._tr("select_tooltip", "选定当前文件"))
        btn_row.addWidget(self._select_btn)

        cancel_btn = QPushButton(self._tr("cancel", "取消"))
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setToolTip(self._tr("cancel_tooltip", "取消"))
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

        self._refresh_list()
        QTimer.singleShot(DelayMs.NEXT_TICK, self._list.setFocus)
        # 必须等控件全部建好再注册主题：register_window 会立即回调
        # reapply_styles，此时 _drive_btn 尚未创建会抛 AttributeError
        from ui.theme_manager import safe_register_window
        safe_register_window(self)

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)

    def reapply_styles(self):
        from ui.styles import AppStyles
        self.setStyleSheet(AppStyles.popup_dialog_style())
        drive_btn = getattr(self, '_drive_btn', None)
        if drive_btn is not None:
            drive_btn.setMenu(self._build_drive_menu())

    def _tr(self, key, default=''):
        if self._lm:
            return self._lm.tr(key, default)
        return default

    def _get_volume_label(self, root_path):
        if not is_windows():
            return ''
        try:
            import ctypes
            import threading
            result = [None]
            def _query():
                try:
                    kernel32 = ctypes.windll.kernel32
                    vol_name_buf = ctypes.create_unicode_buffer(256)
                    fs_name_buf = ctypes.create_unicode_buffer(256)
                    serial = ctypes.c_uint32(0)
                    max_comp = ctypes.c_uint32(0)
                    fs_flags = ctypes.c_uint32(0)
                    ret = kernel32.GetVolumeInformationW(
                        root_path, vol_name_buf, ctypes.sizeof(vol_name_buf) // 2,
                        ctypes.byref(serial), ctypes.byref(max_comp),
                        ctypes.byref(fs_flags), fs_name_buf, ctypes.sizeof(fs_name_buf) // 2
                    )
                    if ret:
                        result[0] = vol_name_buf.value
                except Exception:
                    pass
            t = threading.Thread(target=_query, daemon=True)
            t.start()
            t.join(timeout=0.3)
            return result[0] or ''
        except Exception:
            return ''

    def _get_win_drives(self):
        if not is_windows():
            return []
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            size = kernel32.GetLogicalDriveStringsW(0, None)
            if size <= 0:
                return []
            buf = ctypes.create_unicode_buffer(size + 1)
            kernel32.GetLogicalDriveStringsW(size + 1, buf)
            drives = []
            offset = 0
            while offset < size:
                s = ctypes.wstring_at(ctypes.addressof(buf) + offset * 2)
                if not s:
                    break
                drives.append(s)
                offset += len(s) + 1
            return drives
        except Exception:
            return []

    def _get_drives_cached(self):
        if self._drives_cache is not None:
            return self._drives_cache
        drives = self._get_win_drives()
        if not drives:
            for d in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                root = f'{d}:\\'
                if os.path.isdir(root):
                    drives.append(root)
        result = []
        for root_path in drives:
            root_path = root_path.rstrip('\\') + '\\'
            display = root_path
            try:
                vol_label = self._get_volume_label(root_path)
                if vol_label:
                    display = f"{root_path} ({vol_label})"
            except Exception:
                pass
            result.append((root_path, display))
        self._drives_cache = result
        return result

    def _build_drive_menu(self):
        menu = QMenu(self)
        from ui.styles import AppStyles
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {c.get('player_panel')};
                color: {c.get('window_text')};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 24px;
                color: {c.get('window_text')};
            }}
            QMenu::item:selected {{
                background-color: {c.get('highlight')};
                color: {c.get('highlighted_text')};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {c.get('mid')};
                margin: 4px 8px;
            }}
        """)
        current_drive = os.path.splitdrive(self._current_dir)[0]
        for root_path, display in self._get_drives_cached():
            action = QAction(display, self)
            action.setData(root_path)
            action.triggered.connect(self._on_drive_action)
            if root_path.rstrip('\\') == current_drive:
                f = action.font()
                f.setBold(True)
                action.setFont(f)
            menu.addAction(action)

        menu.addSeparator()
        net_action = QAction(self._tr("network_path", "网络路径 (\\\\server\\share)"), self)
        net_action.triggered.connect(self._on_network_path)
        menu.addAction(net_action)
        return menu

    def _on_drive_action(self):
        action = self.sender()
        if not action:
            return
        root = action.data()
        if root and os.path.isdir(root):
            self._current_dir = root
            self._refresh_list()

    def _on_network_path(self):
        net_path, ok = QInputDialog.getText(
            self,
            self._tr("network_path", "网络路径"),
            self._tr("enter_network_path", "输入网络路径 (\\\\server\\share):")
        )
        if ok and net_path.strip():
            net_path = net_path.strip()
            if os.path.isdir(net_path):
                self._current_dir = net_path
                self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        self._path_edit.setText(self._current_dir)


        try:
            entries = sorted(os.listdir(self._current_dir))
        except PermissionError:
            return
        except OSError:
            return

        dirs = []
        files = []
        for name in entries:
            full = os.path.join(self._current_dir, name)
            try:
                is_dir = os.path.isdir(full)
            except OSError:
                continue
            if is_dir:
                dirs.append(name)
            elif os.path.isfile(full):
                if self._show_audio_only:
                    if name.lower().endswith(_AUDIO_EXTS):
                        files.append(name)
                elif self._show_video_only:
                    if name.lower().endswith(_MEDIA_EXTS):
                        files.append(name)
                else:
                    files.append(name)

        for d in sorted(dirs, key=str.lower):
            item = QListWidgetItem(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), d)
            item.setData(Qt.ItemDataRole.UserRole, ('dir', os.path.join(self._current_dir, d)))
            self._list.addItem(item)

        for f in sorted(files, key=str.lower):
            item = QListWidgetItem(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), f)
            item.setData(Qt.ItemDataRole.UserRole, ('file', os.path.join(self._current_dir, f)))
            self._list.addItem(item)

        if not dirs and not files:
            empty_item = QListWidgetItem(self._tr("empty_dir", "此目录为空"))
            empty_item.setFlags(Qt.ItemDataFlag.NoItemFlags)
            self._list.addItem(empty_item)

    def _show_drives_root(self):
        self._list.clear()
        self._path_edit.setText('')

        if is_windows():
            for root_path, display in self._get_drives_cached():
                item = QListWidgetItem(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), display)
                item.setData(Qt.ItemDataRole.UserRole, ('drive', root_path))
                self._list.addItem(item)

            net_item = QListWidgetItem(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon),
                self._tr("network_path", "网络路径 (\\\\server\\share)")
            )
            net_item.setData(Qt.ItemDataRole.UserRole, ('network', ''))
            self._list.addItem(net_item)

    def _go_up(self):
        parent = os.path.dirname(self._current_dir)
        if parent and parent != self._current_dir:
            self._current_dir = parent
            self._refresh_list()
        elif is_windows():
            self._current_dir = ''
            self._show_drives_root()

    def _on_path_entered(self):
        path = self._path_edit.text().strip()
        if not path:
            if is_windows():
                self._current_dir = ''
                self._show_drives_root()
            return
        path = os.path.normpath(path)
        if os.path.isdir(path):
            self._current_dir = path
            self._refresh_list()

    def _on_filter_changed(self, index):
        self._show_video_only = (index == 0 or index == 1)
        self._show_audio_only = (index == 2)
        self._refresh_list()

    def _on_single_click(self, item):
        pass

    def _on_double_click(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, path = data
        if kind == 'drive':
            if os.path.isdir(path):
                self._current_dir = path
                self._refresh_list()
        elif kind == 'network':
            self._on_network_path()
        elif kind == 'dir':
            self._current_dir = path
            self._refresh_list()
        else:
            self._selected_path = path
            self.accept()

    def _on_select(self):
        item = self._list.currentItem()
        if not item:
            self._selected_path = self._current_dir
            self.accept()
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            self._selected_path = self._current_dir
            self.accept()
            return
        kind, path = data
        if kind == 'drive':
            if os.path.isdir(path):
                self._current_dir = path
                self._refresh_list()
            return
        if kind == 'network':
            self._on_network_path()
            return
        if kind == 'dir':
            self._current_dir = path
            self._refresh_list()
            return
        self._selected_path = path
        self.accept()

    def get_selected_path(self):
        return self._selected_path
