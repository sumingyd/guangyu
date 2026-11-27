"""播放队列与控制对话框 - 队列模式/AB循环/逐帧 + 当前队列列表"""
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QRadioButton,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)

from ui.floating_dialog import FloatingDialog
from utils.delay_constants import DelayMs
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


# 队列模式定义（与 FileQueueController.QUEUE_MODES 保持一致）
QUEUE_MODES = [
    ('none', 'playback_queue_mode_none', 'No Loop'),
    ('single', 'playback_queue_mode_single', 'Loop Single File'),
    ('all', 'playback_queue_mode_all', 'Loop List'),
    ('shuffle', 'playback_queue_mode_shuffle', 'Shuffle'),
]


class PlaybackQueueDialog(FloatingDialog):
    """播放队列与控制对话框
    - 队列模式切换（实时应用到 mpv loop-file + 持久化）
    - A-B 循环状态显示与操作
    - 逐帧前进/后退
    - 当前队列列表（高亮当前文件，双击切换）
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window, frameless=True, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('playback_queue_title', 'Playback Queue & Control'))
        self.setMinimumSize(560, 600)
        self._loading = False
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        # 启动后短暂延迟加载初始状态
        QTimer.singleShot(DelayMs.QUEUE_RELOAD, self._reload_state)

    @property
    def _queue_ctrl(self) -> Optional[object]:
        qc = getattr(self.window, 'file_queue_ctrl', None)
        return qc

    def reapply_styles(self):
        self._apply_theme()

    def _apply_theme(self):
        c = AppStyles._get_colors()
        r = AppStyles._get_style_border_radius()
        text_color = c.get('window_text')
        self.setStyleSheet(AppStyles.popup_dialog_style() + f"""
            QLabel {{ color: {text_color}; }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                margin-top: 12px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
            QListWidget {{
                background: {c.get('base')};
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background: {c.get('accent')};
                color: {c.get('highlighted_text')};
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== 队列模式组 =====
        queue_group = QGroupBox(tr('playback_queue_group_queue', 'Queue'))
        qg_layout = QVBoxLayout(queue_group)
        # 单选按钮行
        rb_row = QHBoxLayout()
        self._mode_buttons = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for mode, key, fallback in QUEUE_MODES:
            btn = QRadioButton(tr(key, fallback))
            btn.setChecked(mode == 'none')
            btn.toggled.connect(lambda checked, m=mode: self._on_mode_toggled(checked, m))
            self._mode_buttons[mode] = btn
            self._mode_group.addButton(btn)
            rb_row.addWidget(btn)
        rb_row.addStretch()
        qg_layout.addLayout(rb_row)

        # 切换模式 + 随机开关按钮行
        action_row = QHBoxLayout()
        cycle_btn = QPushButton(tr('playback_queue_cycle_mode', 'Cycle Loop Mode'))
        cycle_btn.clicked.connect(lambda: self._call_queue('cycle_queue_mode'))
        cycle_btn.setToolTip(tr('cycle_tooltip', '循环播放开关'))
        action_row.addWidget(cycle_btn)

        shuffle_btn = QPushButton(tr('playback_queue_toggle_shuffle', 'Toggle Shuffle'))
        shuffle_btn.clicked.connect(lambda: self._call_queue('toggle_shuffle'))
        shuffle_btn.setToolTip(tr('shuffle_tooltip', '随机播放开关'))
        action_row.addWidget(shuffle_btn)
        action_row.addStretch()
        qg_layout.addLayout(action_row)

        layout.addWidget(queue_group)

        # ===== A-B 循环组 =====
        ab_group = QGroupBox(tr('playback_queue_group_ab_loop', 'A-B Loop'))
        ab_layout = QGridLayout(ab_group)
        ab_layout.setSpacing(6)

        set_a_btn = QPushButton(tr('playback_queue_ab_set_a', 'Set A Point\tA'))
        set_a_btn.clicked.connect(lambda: self._call_queue('ab_loop_set_a'))
        set_a_btn.setToolTip(tr('set_a_tooltip', '设置A点'))
        ab_layout.addWidget(set_a_btn, 0, 0)

        set_b_btn = QPushButton(tr('playback_queue_ab_set_b', 'Set B Point\tB'))
        set_b_btn.clicked.connect(lambda: self._call_queue('ab_loop_set_b'))
        set_b_btn.setToolTip(tr('set_b_tooltip', '设置B点'))
        ab_layout.addWidget(set_b_btn, 0, 1)

        clear_ab_btn = QPushButton(tr('playback_queue_ab_clear', 'Clear A-B\tC'))
        clear_ab_btn.clicked.connect(lambda: self._call_queue('ab_loop_clear'))
        clear_ab_btn.setToolTip(tr('clear_ab_tooltip', '清除AB段'))
        ab_layout.addWidget(clear_ab_btn, 0, 2)

        self._ab_status_label = QLabel(tr('playback_queue_ab_inactive', 'Inactive'))
        self._ab_status_label.setWordWrap(True)
        ab_layout.addWidget(self._ab_status_label, 1, 0, 1, 3)
        layout.addWidget(ab_group)

        # ===== 逐帧组 =====
        frame_group = QGroupBox(tr('playback_queue_group_frame', 'Frame Step'))
        fg_layout = QHBoxLayout(frame_group)
        frame_back_btn = QPushButton(tr('playback_queue_frame_back', 'Frame Back\t['))
        frame_back_btn.clicked.connect(lambda: self._call_queue('frame_back_step'))
        fg_layout.addWidget(frame_back_btn)

        frame_fwd_btn = QPushButton(tr('playback_queue_frame_forward', 'Frame Forward\t]'))
        frame_fwd_btn.clicked.connect(lambda: self._call_queue('frame_step'))
        fg_layout.addWidget(frame_fwd_btn)
        fg_layout.addStretch()
        layout.addWidget(frame_group)

        # ===== 当前队列列表 =====
        list_group = QGroupBox(tr('playback_queue_group_list', 'Current Queue'))
        lg_layout = QVBoxLayout(list_group)
        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        lg_layout.addWidget(self._list_widget)
        layout.addWidget(list_group, 1)

        # ===== 底部按钮行 =====
        btn_row = QHBoxLayout()
        prev_btn = QPushButton(tr('playback_queue_play_prev', 'Previous File\tPgUp'))
        prev_btn.clicked.connect(lambda: self._call_queue('play_previous'))
        btn_row.addWidget(prev_btn)

        next_btn = QPushButton(tr('playback_queue_play_next', 'Next File\tPgDown'))
        next_btn.clicked.connect(lambda: self._call_queue('play_next'))
        btn_row.addWidget(next_btn)

        btn_row.addStretch()

        refresh_btn = QPushButton(tr('ctx_refresh', 'Refresh'))
        refresh_btn.clicked.connect(self._reload_state)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton(tr('playback_queue_close', 'Close'))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ---------- 调用 queue_ctrl 的辅助方法 ----------
    def _call_queue(self, method_name: str, *args):
        qc = self._queue_ctrl
        if not qc:
            return
        try:
            fn = getattr(qc, method_name, None)
            if fn is None:
                return
            result = fn(*args)
            # 调用后刷新状态（用于显示 A-B 状态等）
            QTimer.singleShot(DelayMs.INPUT_DEBOUNCE, self._reload_state)
            return result
        except Exception as e:
            logger.debug(f"调用 queue_ctrl.{method_name} 失败: {e}")

    def _on_mode_toggled(self, checked: bool, mode: str):
        if not checked or self._loading:
            return
        qc = self._queue_ctrl
        if not qc:
            return
        try:
            qc.set_queue_mode(mode)
        except Exception as e:
            logger.debug(f"切换队列模式失败: {e}")
        finally:
            QTimer.singleShot(DelayMs.INPUT_DEBOUNCE, self._reload_state)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        idx = self._list_widget.row(item)
        if idx < 0:
            return
        channels = self._get_local_channels()
        if 0 <= idx < len(channels):
            channel = channels[idx]
            try:
                QTimer.singleShot(DelayMs.UI_REFRESH, lambda: self.window.play_channel(channel))
            except Exception as e:
                logger.debug(f"播放队列项失败: {e}")

    # ---------- 状态加载 ----------
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(DelayMs.INPUT_DEBOUNCE, self._reload_state)

    def _reload_state(self):
        """重新加载所有状态显示"""
        if self._loading:
            return
        self._loading = True
        try:
            self._reload_mode()
            self._reload_ab_status()
            self._reload_list()
        finally:
            self._loading = False

    def _reload_mode(self):
        qc = self._queue_ctrl
        mode = getattr(qc, 'queue_mode', 'none') if qc else 'none'
        btn = self._mode_buttons.get(mode) or self._mode_buttons.get('none')
        if btn and not btn.isChecked():
            btn.setChecked(True)

    def _reload_ab_status(self):
        tr = self.window.language_manager.tr
        qc = self._queue_ctrl
        status = qc.get_ab_loop_status() if qc else {'a': None, 'b': None, 'active': False}
        a = status.get('a')
        b = status.get('b')
        active = status.get('active', False)
        if active and a is not None and b is not None:
            text = tr('playback_queue_ab_active', 'Active (A={a:.2f}s, B={b:.2f}s)').format(a=a, b=b)
        elif active:
            text = tr('playback_queue_ab_inactive', 'Inactive')
        elif a is not None and b is None:
            text = tr('playback_queue_ab_only_a', 'A set ({a:.2f}s)').format(a=a)
        elif b is not None and a is None:
            text = tr('playback_queue_ab_only_b', 'B set ({b:.2f}s)').format(b=b)
        else:
            text = tr('playback_queue_ab_inactive', 'Inactive')
        self._ab_status_label.setText(text)

    def _reload_list(self):
        tr = self.window.language_manager.tr
        channels = self._get_local_channels()
        cur_url = ''
        cur = getattr(self.window, 'current_channel', None)
        if cur and isinstance(cur, dict):
            cur_url = cur.get('url', '') or ''

        self._list_widget.clear()
        if not channels:
            empty_item = QListWidgetItem(tr('playback_queue_empty', 'Queue is empty (open local video files to populate)'))
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self._list_widget.addItem(empty_item)
            return

        current_label = tr('playback_queue_current', 'Current')
        for i, ch in enumerate(channels):
            if not isinstance(ch, dict):
                continue
            name = ch.get('name', '') or ch.get('url', f'#{i}')
            url = ch.get('url', '')
            is_current = (url and url == cur_url)
            prefix = '▶ ' if is_current else '  '
            text = f"{prefix}{name}"
            if is_current:
                text += f"  [{current_label}]"
            item = QListWidgetItem(text)
            if is_current:
                # 高亮当前项
                try:
                    c = AppStyles._get_colors()
                    item.setForeground(QColor(c.get('accent')))
                except Exception as e:
                    logger.debug(f"_reload_list: {e}")
            self._list_widget.addItem(item)
            if is_current:
                self._list_widget.setCurrentItem(item)

    def _get_local_channels(self) -> list:
        channels = getattr(self.window, '_local_channels', None)
        if channels and isinstance(channels, list):
            return channels
        return []

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
