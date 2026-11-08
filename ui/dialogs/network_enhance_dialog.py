"""网络流媒体增强对话框 - Referer + HTTP 代理 + HTTP Headers"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QPlainTextEdit,
    QGroupBox,
)

from ui.floating_dialog import FloatingDialog
from ui.styles import AppStyles
from core.log_manager import global_logger as logger


# 代理格式提示
PROXY_FORMAT_HINT = (
    "HTTP proxy only:\n"
    "  http://host:port\n"
    "  https://host:port\n"
    "SOCKS5 is not supported by mpv (it is ignored and traffic goes direct).\n"
    "Use a local HTTP/mixed port if you only have SOCKS5.\n"
    "Leave empty to disable proxy."
)


class NetworkEnhanceDialog(FloatingDialog):
    """网络流媒体增强对话框
    - HTTP Referer：用于绕过防盗链
    - HTTP/HTTPS 代理：用于访问受限内容
    - HTTP Headers：自定义 HTTP 头（每行一个，格式 Key: Value）
    保存按钮持久化到 config 并实时应用到 mpv
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent, frameless=False, stay_on_top=False)
        self.window = main_window
        tr = main_window.language_manager.tr
        self.setWindowTitle(tr('network_enhance_title', 'Network Stream Enhance'))
        self.setMinimumSize(560, 540)
        self._loading = False
        self._setup_ui()
        self._apply_theme()
        from ui.theme_manager import safe_register_window
        safe_register_window(self)
        self._reload_from_config()

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
            QLineEdit, QPlainTextEdit {{
                background: {c.get('base')};
                color: {text_color};
                border: 1px solid {c.get('mid')};
                border-radius: {r}px;
                padding: 4px;
            }}
        """)

    def _setup_ui(self):
        tr = self.window.language_manager.tr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ===== Referer 组 =====
        referer_group = QGroupBox(tr('network_enhance_group_referer', 'HTTP Referer'))
        rform = QFormLayout(referer_group)
        rform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.referer_edit = QLineEdit()
        self.referer_edit.setPlaceholderText('https://example.com/')
        rform.addRow(tr('network_enhance_referer', 'Referer'), self.referer_edit)
        referer_hint = QLabel(tr('network_enhance_referer_hint',
            'Used to bypass hotlink protection. Leave empty to disable.'))
        referer_hint.setWordWrap(True)
        rform.addRow('', referer_hint)
        layout.addWidget(referer_group)

        # ===== 代理组 =====
        proxy_group = QGroupBox(tr('network_enhance_group_proxy', 'HTTP/HTTPS Proxy'))
        pform = QFormLayout(proxy_group)
        pform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText('http://127.0.0.1:8080')
        pform.addRow(tr('network_enhance_proxy', 'Proxy URL'), self.proxy_edit)
        proxy_hint = QLabel(tr('network_enhance_proxy_hint', PROXY_FORMAT_HINT))
        proxy_hint.setWordWrap(True)
        pform.addRow('', proxy_hint)
        layout.addWidget(proxy_group)

        # ===== HTTP Headers 组 =====
        headers_group = QGroupBox(tr('network_enhance_group_headers', 'HTTP Headers'))
        hform = QVBoxLayout(headers_group)
        self.headers_edit = QPlainTextEdit()
        self.headers_edit.setPlaceholderText('Key: Value\nKey2: Value2')
        self.headers_edit.setFixedHeight(120)
        hform.addWidget(self.headers_edit)
        headers_hint = QLabel(tr('network_enhance_headers_hint',
            'One header per line, format: Key: Value'))
        headers_hint.setWordWrap(True)
        hform.addWidget(headers_hint)
        layout.addWidget(headers_group)

        # ===== 操作按钮（标准设置式：清空 | 应用 + 完成） =====
        def _on_done():
            self._apply_now()
            self._save()
            self.close()

        btn_bar, self.clear_btn, self.apply_btn, self.close_btn = self.build_settings_buttons(
            self._clear_all, self._apply_now, _on_done,
            reset_text=tr('network_enhance_clear', '清空'),
            apply_text=tr('network_enhance_apply', '应用'),
            done_text=tr('playback_queue_close', '完成'),
        )
        self.clear_btn.setToolTip(tr('clear_enhance_tooltip', '清除网络增强设置'))
        self.apply_btn.setToolTip(tr('apply_enhance_tooltip', '应用设置'))
        layout.addWidget(btn_bar)

    def _reload_from_config(self):
        """从 config 加载当前设置"""
        self._loading = True
        try:
            cfg = self.window.config.load_playback_settings()
            self.referer_edit.setText(cfg.get('http_referer', '') or '')
            self.proxy_edit.setText(cfg.get('http_proxy', '') or '')
            self.headers_edit.setPlainText(cfg.get('http_headers', '') or '')
        except Exception as e:
            logger.debug(f"加载网络增强设置失败: {e}")
        finally:
            self._loading = False

    def _collect_settings(self) -> dict:
        return {
            'http_referer': self.referer_edit.text().strip(),
            'http_proxy': self.proxy_edit.text().strip(),
            'http_headers': self.headers_edit.toPlainText().strip(),
        }

    def _apply_to_mpv(self):
        """实时应用到 mpv"""
        pc = self.window.player_controller
        if not pc:
            return
        try:
            settings = self._collect_settings()
            if hasattr(pc, 'set_http_referer'):
                pc.set_http_referer(settings['http_referer'])
            if hasattr(pc, 'set_http_proxy'):
                pc.set_http_proxy(settings['http_proxy'])
            if hasattr(pc, 'set_http_headers'):
                pc.set_http_headers(settings['http_headers'])
        except Exception as e:
            logger.debug(f"应用网络增强设置到 mpv 失败: {e}")

    def _apply_now(self):
        """应用（不保存到 config）"""
        self._apply_to_mpv()
        tr = self.window.language_manager.tr
        if hasattr(self.window, '_show_osd_feedback'):
            self.window._show_osd_feedback(tr('network_enhance_applied', 'Network settings applied'))

    def _save(self):
        """保存到 config 并应用"""
        try:
            settings = self._collect_settings()
            # 合并现有 settings 后保存
            cfg = self.window.config.load_playback_settings()
            cfg.update(settings)
            self.window.config.save_playback_settings(cfg)
            self._apply_to_mpv()
            tr = self.window.language_manager.tr
            if hasattr(self.window, '_show_osd_feedback'):
                self.window._show_osd_feedback(tr('network_enhance_saved', 'Network settings saved'))
        except Exception as e:
            logger.error(f"保存网络增强设置失败: {e}")

    def _clear_all(self):
        """清除所有设置"""
        self.referer_edit.clear()
        self.proxy_edit.clear()
        self.headers_edit.clear()

    def closeEvent(self, event):
        from ui.theme_manager import safe_unregister_window
        safe_unregister_window(self)
        super().closeEvent(event)
