from __future__ import annotations

import json
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QSlider, QToolButton,
    QComboBox, QFrame, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QListWidget
)
from PySide6.QtCore import Qt, Signal, QMimeData, QByteArray, QSize
from PySide6.QtGui import QDrag, QPainter, QPen, QIcon
from PySide6.QtWidgets import QMenu
from ui.styles import AppStyles


class DraggableChannelListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)

    def _get_main_window(self):
        widget = self.parent()
        while widget:
            if hasattr(widget, 'player_controller'):
                return widget
            widget = widget.parent()
        return None

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return

        main_win = self._get_main_window()
        if not main_win:
            return

        if self is getattr(main_win, 'local_channel_list', None):
            channels = getattr(main_win, '_local_channels', [])
        else:
            channels = getattr(main_win, '_sub_channels', [])

        if isinstance(idx, int) and 0 <= idx < len(channels):
            ch_data = channels[idx]
        else:
            row = self.row(item)
            if 0 <= row < len(channels):
                ch_data = channels[row]
            else:
                return

        mime_data = QMimeData()
        data = json.dumps(ch_data, ensure_ascii=False).encode('utf-8')
        mime_data.setData('application/x-channel', QByteArray(data))

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)


class MultiScreenCell(QWidget):
    channel_dropped = Signal(int, dict)
    close_requested = Signal(int)
    volume_changed = Signal(int, int)
    audio_track_changed = Signal(int, int)
    clicked = Signal(int)
    navigation_requested = Signal(int, int)
    exit_requested = Signal()

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._channel = None
        self._player = None
        self._is_playing = False
        self._accepting_drop = True
        self._volume_before_mute = 80
        self.setAcceptDrops(True)
        # 单元格需要接收键盘，才能让方向键/空格作用在当前格而不是隐藏的主播放器
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._info_bar = QHBoxLayout()
        self._info_bar.setContentsMargins(4, 2, 4, 2)
        self._info_bar.setSpacing(4)

        self._channel_label = QLabel()
        self._channel_label.setStyleSheet(self._label_style())
        self._channel_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._channel_label.setMaximumHeight(20)
        self._info_bar.addWidget(self._channel_label, 1)

        self._audio_combo = QComboBox()
        self._audio_combo.setStyleSheet(self._combo_style())
        self._audio_combo.setFixedWidth(60)
        self._audio_combo.setMaximumHeight(18)
        self._audio_combo.hide()
        self._audio_combo.currentIndexChanged.connect(self._on_audio_track_changed)
        self._info_bar.addWidget(self._audio_combo)

        self._close_btn = QToolButton()
        close_color = AppStyles._get_colors().get('player_panel_secondary', '#aaaaaa')
        close_icon_path = AppStyles.get_icon('close', close_color, 12)
        if close_icon_path:
            self._close_btn.setIcon(QIcon(close_icon_path))
            self._close_btn.setIconSize(QSize(12, 12))
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setStyleSheet(self._close_btn_style())
        self._close_btn.clicked.connect(lambda: self.close_requested.emit(self._index))
        self._close_btn.hide()
        self._info_bar.addWidget(self._close_btn)

        layout.addLayout(self._info_bar)

        self._video_frame = QFrame()
        self._video_frame.setStyleSheet(AppStyles.player_background_style())
        self._video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        from utils.platform_utils import is_linux
        needs_native_window = is_linux()
        if needs_native_window:
            self._video_frame.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self._video_frame.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        layout.addWidget(self._video_frame, 1)

        self._placeholder = QLabel(self._video_frame)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(self._placeholder_style())
        self._placeholder.setText(f"{self._index + 1}")

        self._volume_bar = QHBoxLayout()
        self._volume_bar.setContentsMargins(4, 1, 4, 1)

        vol_label = QLabel()
        vol_label.setFixedSize(18, 18)
        vol_icon_color = AppStyles.get_color('player_panel_text')
        vol_icon_path = AppStyles.get_icon('speaker', vol_icon_color, 14)
        if vol_icon_path:
            vol_label.setPixmap(QIcon(vol_icon_path).pixmap(14, 14))
        vol_label.setStyleSheet("background: transparent; border: none;")
        self._volume_bar.addWidget(vol_label)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(80)
        self._volume_slider.setFixedHeight(14)
        self._volume_slider.setStyleSheet(AppStyles.player_volume_slider_style())
        self._volume_slider.valueChanged.connect(lambda v: self.volume_changed.emit(self._index, v))
        self._volume_bar.addWidget(self._volume_slider, 1)

        self._volume_pct = QLabel("80%")
        self._volume_pct.setFixedWidth(32)
        self._volume_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._volume_pct.setStyleSheet(self._label_style())
        self._volume_pct.setMaximumHeight(18)
        self._volume_bar.addWidget(self._volume_pct)

        layout.addLayout(self._volume_bar)

        self._drag_highlight = False

    @property
    def index(self):
        return self._index

    @property
    def channel(self):
        return self._channel

    @property
    def player(self):
        return self._player

    @player.setter
    def player(self, val):
        self._player = val

    @property
    def video_frame(self):
        return self._video_frame

    @property
    def is_playing(self):
        return self._is_playing

    @property
    def volume(self) -> int:
        return self._volume_slider.value()

    @property
    def is_muted(self) -> bool:
        return self._volume_slider.value() <= 0

    def set_channel(self, channel: dict):
        self._channel = channel
        self._is_playing = True
        name = channel.get('name', '') if channel else ''
        self._channel_label.setText(name)
        self._placeholder.hide()
        self._close_btn.show()
        self._audio_combo.show()

    def clear_channel(self):
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
            self._player = None
        self._channel = None
        self._is_playing = False
        self._channel_label.setText('')
        self._placeholder.setText(f"{self._index + 1}")
        self._placeholder.show()
        self._close_btn.hide()
        self._audio_combo.hide()
        self._audio_combo.clear()

    def set_volume(self, vol: int):
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(vol)
        self._volume_slider.blockSignals(False)
        self._volume_pct.setText(f"{vol}%")

    def toggle_mute(self) -> bool:
        """切换本单元格静音，返回切换后是否处于静音。"""
        current = self._volume_slider.value()
        if current > 0:
            self._volume_before_mute = current
            # 使用 setValue（不屏蔽信号），让 controller 同步设置播放器音量
            self._volume_slider.setValue(0)
            return True
        restore = self._volume_before_mute or 80
        self._volume_slider.setValue(restore)
        return False

    def set_audio_tracks(self, tracks: list, tr=None):
        self._audio_combo.blockSignals(True)
        self._audio_combo.clear()
        for t in tracks:
            fallback = (tr('ctx_audio_track_n', 'Track {}').format(t.get('id', 0))) if tr else f"Track {t.get('id', 0)}"
            title = t.get('title', '') or t.get('lang', '') or fallback
            self._audio_combo.addItem(title, t.get('id', 0))
        self._audio_combo.setVisible(len(tracks) > 1)
        self._audio_combo.blockSignals(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_placeholder') and self._placeholder:
            self._placeholder.setGeometry(0, 0, self._video_frame.width(), self._video_frame.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.clicked.emit(self._index)
        elif event.button() == Qt.MouseButton.RightButton and self._is_playing:
            self._show_context_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.toggle_mute()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                   Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.navigation_requested.emit(self._index, key)
            event.accept()
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # 空格/确认：切换当前单元格静音
            self.toggle_mute()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.exit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def _show_context_menu(self, global_pos):
        from ui.styles import AppStyles
        menu = QMenu(self)
        menu.setStyleSheet(AppStyles.player_menu_bar_style())
        tr = self.window().language_manager.tr if self.window() else (lambda k, d='': d)

        menu.addAction(tr('ctx_close_cell', '关闭此单元格'), lambda: self.close_requested.emit(self._index))
        menu.addSeparator()
        menu.addAction(tr('ctx_mute', '静音/取消静音'), self.toggle_mute)
        menu.addAction(tr('ctx_screenshot', '截图'), lambda: self._take_screenshot())
        menu.exec(global_pos)

    def _take_screenshot(self):
        if self._player:
            try:
                self._player.screenshot()
            except Exception:
                pass

    def dragEnterEvent(self, event):
        if self._accepting_drop and event.mimeData().hasFormat('application/x-channel'):
            event.acceptProposedAction()
            self._drag_highlight = True
            self.update()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._accepting_drop and event.mimeData().hasFormat('application/x-channel'):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_highlight = False
        self.update()

    def dropEvent(self, event):
        self._drag_highlight = False
        self.update()
        if event.mimeData().hasFormat('application/x-channel'):
            data = event.mimeData().data('application/x-channel')

            try:
                channel = json.loads(bytes(data).decode('utf-8'))
                self.channel_dropped.emit(self._index, channel)
                event.acceptProposedAction()
            except Exception:
                event.ignore()
        else:
            event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drag_highlight or self.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            from ui.styles import AppStyles, color_to_qcolor
            colors = AppStyles._get_colors()
            width = 3 if self._drag_highlight else 2
            pen = QPen(color_to_qcolor(colors.get('accent', '#00aaff')), width)
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
            painter.end()

    def _on_audio_track_changed(self, idx):
        if idx >= 0:
            track_id = self._audio_combo.itemData(idx)
            if track_id is not None:
                self.audio_track_changed.emit(self._index, track_id)

    def reapply_styles(self):
        self._channel_label.setStyleSheet(self._label_style())
        self._audio_combo.setStyleSheet(self._combo_style())
        self._close_btn.setStyleSheet(self._close_btn_style())
        self._placeholder.setStyleSheet(self._placeholder_style())
        self._video_frame.setStyleSheet(AppStyles.player_background_style())
        self._volume_slider.setStyleSheet(AppStyles.player_volume_slider_style())
        self._volume_pct.setStyleSheet(self._label_style())

    @staticmethod
    def _label_style():
        colors = AppStyles._get_colors()
        return f"color: {colors['player_panel_text']}; font-size: 11px; background: transparent; border: none;"

    @staticmethod
    def _combo_style():
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"""
            QComboBox {{
                background-color: {colors['player_combo']};
                color: {colors['player_panel_text']};
                border: 1px solid {colors['player_line']};
                border-radius: {max(r - 4, 2)}px;
                font-size: 10px;
                padding: 0px 2px;
            }}
            QComboBox::drop-down {{
                width: 12px;
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['player_panel']};
                color: {colors['player_panel_text']};
                selection-background-color: {colors['player_accent']};
                border: 1px solid {colors['player_line']};
            }}
        """

    @staticmethod
    def _close_btn_style():
        colors = AppStyles._get_colors()
        return f"""
            QToolButton {{
                color: {colors['player_panel_secondary']};
                background: transparent;
                border: none;
                font-size: 12px;
            }}
            QToolButton:hover {{
                color: {colors['player_warning']};
                background: transparent;
            }}
        """

    @staticmethod
    def _placeholder_style():
        colors = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        return f"""
            QLabel {{
                font-size: 48px;
                font-weight: bold;
                color: {colors['player_panel_hint']};
                background-color: {colors['player_video_placeholder']};
                border: 1px dashed {colors['player_line']};
                border-radius: {r}px;
            }}
        """


class MultiScreenWidget(QWidget):
    layout_changed = Signal(int)
    cell_channel_dropped = Signal(int, dict)
    cell_close_requested = Signal(int)
    cell_volume_changed = Signal(int, int)
    cell_audio_track_changed = Signal(int, int)
    cell_clicked = Signal(int)
    cell_navigation_requested = Signal(int, int)
    exit_requested = Signal()
    global_mute_toggled = Signal(bool)

    LAYOUT_1x1 = 1
    LAYOUT_2x2 = 4
    LAYOUT_3x3 = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid_count = self.LAYOUT_2x2
        self._cells = []
        self._global_muted = False
        self._saved_volumes = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._toolbar = QHBoxLayout()
        self._toolbar.setContentsMargins(4, 2, 4, 2)

        self._mute_button = QToolButton()
        self._mute_button.setFixedSize(24, 20)
        mute_color = AppStyles.get_color('player_panel_text')
        mute_icon_path = AppStyles.get_icon('volume', mute_color, 14)
        if mute_icon_path:
            self._mute_button.setIcon(QIcon(mute_icon_path))
        self._mute_button.setIconSize(QSize(14, 14))
        self._mute_button.setStyleSheet("QToolButton { background: transparent; border: none; } QToolButton:hover { background: rgba(255,255,255,0.1); }")
        self._mute_button.clicked.connect(self._toggle_global_mute)
        self._toolbar.addWidget(self._mute_button)

        self._mute_label = QLabel()
        self._mute_label.setStyleSheet("color: " + AppStyles._get_colors().get('player_panel_secondary', '#aaa') + "; font-size: 11px; background: transparent;")
        self._mute_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._toolbar.addWidget(self._mute_label)
        self._toolbar.addStretch()

        main_layout.addLayout(self._toolbar)

        self._grid_layout = QGridLayout()
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(2)
        main_layout.addLayout(self._grid_layout, 1)

        self._build_cells(self._grid_count)

    @property
    def grid_count(self):
        return self._grid_count

    @property
    def cells(self):
        return self._cells

    def set_layout(self, count: int):
        if count == self._grid_count:
            return
        # 宫格数量变化会重建单元格，先保留每格音量与全局静音状态
        saved_volumes = {cell.index: cell.volume for cell in self._cells}
        self._grid_count = count
        old_cells = list(self._cells)
        for cell in old_cells:
            cell.clear_channel()
            self._grid_layout.removeWidget(cell)
            cell.setParent(None)
            cell.deleteLater()
        self._build_cells(count)
        for cell in self._cells:
            vol = saved_volumes.get(cell.index)
            if vol is None:
                vol = self._saved_volumes.get(cell.index, 80)
            cell.set_volume(0 if self._global_muted else vol)
            if self._global_muted:
                # 静音状态下重建，补记每格静音前的目标音量，取消静音时才不会全部变成 0
                self._saved_volumes.setdefault(cell.index, vol)
        self.layout_changed.emit(count)

    def _build_cells(self, count: int):
        cols = 1 if count == 1 else (2 if count == 4 else 3)
        rows = 1 if count == 1 else (2 if count == 4 else 3)
        self._columns = cols
        self._cells = []
        for i in range(count):
            cell = MultiScreenCell(i, self)
            cell.channel_dropped.connect(self.cell_channel_dropped.emit)
            cell.close_requested.connect(self.cell_close_requested.emit)
            cell.volume_changed.connect(self.cell_volume_changed.emit)
            cell.audio_track_changed.connect(self.cell_audio_track_changed.emit)
            cell.clicked.connect(self.cell_clicked.emit)
            cell.navigation_requested.connect(self.cell_navigation_requested.emit)
            cell.exit_requested.connect(self.exit_requested.emit)
            row, col = divmod(i, cols)
            self._grid_layout.addWidget(cell, row, col)
            self._cells.append(cell)

    def cell_index_of(self, widget) -> int:
        """返回某个控件所属单元格索引，未找到返回 -1。"""
        while widget is not None:
            if isinstance(widget, MultiScreenCell):
                return widget.index
            widget = widget.parent()
        return -1

    def move_focus(self, index: int, key) -> int:
        """按方向键移动单元格焦点，返回新的单元格索引。"""
        if not self._cells:
            return -1
        if index < 0 or index >= len(self._cells):
            index = 0
        cols = max(1, getattr(self, '_columns', 1))
        total = len(self._cells)
        target = index
        if key == Qt.Key.Key_Left:
            if index % cols > 0:
                target = index - 1
        elif key == Qt.Key.Key_Right:
            if index % cols < cols - 1 and index + 1 < total:
                target = index + 1
        elif key == Qt.Key.Key_Up:
            if index - cols >= 0:
                target = index - cols
        elif key == Qt.Key.Key_Down:
            if index + cols < total:
                target = index + cols
        if 0 <= target < total:
            self._cells[target].setFocus(Qt.FocusReason.OtherFocusReason)
            return target
        return index

    def get_cell(self, index: int) -> Optional[MultiScreenCell]:
        if 0 <= index < len(self._cells):
            return self._cells[index]
        return None

    def find_empty_cell(self) -> Optional[MultiScreenCell]:
        for cell in self._cells:
            if not cell.is_playing:
                return cell
        return None

    def _toggle_global_mute(self):
        if self._global_muted:
            self._global_muted = False
            for cell in self._cells:
                saved_vol = self._saved_volumes.get(cell._index, 80)
                cell.set_volume(saved_vol)
            self._update_mute_button(False)
            self.global_mute_toggled.emit(False)
        else:
            self._saved_volumes = {}
            for cell in self._cells:
                self._saved_volumes[cell._index] = cell._volume_slider.value()
                cell.set_volume(0)
            self._global_muted = True
            self._update_mute_button(True)
            self.global_mute_toggled.emit(True)

    def _update_mute_button(self, muted: bool):
        color = AppStyles.get_color('player_panel_text')
        if muted:
            icon_path = AppStyles.get_icon('volume_mute', color, 14)

            try:
                from core.language_manager import LanguageManager
                self._mute_label.setText(LanguageManager().tr('muted', 'Muted'))
            except Exception:
                self._mute_label.setText("Muted")
        else:
            icon_path = AppStyles.get_icon('volume', color, 14)
            self._mute_label.setText("")
        if icon_path:
            self._mute_button.setIcon(QIcon(icon_path))

    @property
    def is_global_muted(self) -> bool:
        return self._global_muted
