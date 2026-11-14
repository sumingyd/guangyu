from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QSpinBox, QCheckBox, QPushButton, QComboBox
from PySide6.QtCore import Qt
from core.log_manager import global_logger as logger


class ServerMixin:
    """从 IPTVPlayer 提取的 Server 管理职责"""

    def _auto_start_server(self):
        try:
            from server.app import set_main_window, start_server, get_server
            from server.routes import get_auth_token
            set_main_window(self)
            settings = self.config.load_server_settings()
            if not settings.get('auto_start', False):
                logger.info("HTTP 服务器未启动（默认关闭，可在“工具 > 服务 > 服务设置”中开启）")
                return
            port = settings.get('port', 8080)
            host = settings.get('host', '0.0.0.0')
            server = start_server(host=host, port=port)
            if not (server is not None and server.wait_started(2.0)):
                err = getattr(server, 'start_error', '') if server is not None else ''
                tr = getattr(self, 'language_manager', None)
                tr = tr.tr if tr is not None else (lambda key, default: default)
                self.status_bar_show_message(
                    tr('server_start_failed', '服务启动失败') + (f': {err}' if err else ''), 8000)
                logger.error(f"HTTP 服务器自动启动失败: {err or '端口未绑定成功'}")
                return
            tr = self.language_manager.tr
            token = get_auth_token()
            # server.port 是绑定成功后的实际端口：配置端口被占用时会自动顺延
            actual_port = server.port
            msg = (tr('server_started', '服务已启动') + f' http://localhost:{actual_port}  ' +
                   tr('server_auth_token', '认证码') + f': {token}')
            if server.requested_port != actual_port:
                msg += '  ' + tr('server_port_shifted', '端口 {requested} 已被占用，已改用 {port}').format(
                    requested=server.requested_port, port=actual_port)
            self.status_bar_show_message(msg, 10000)
            logger.info(f"HTTP 服务器已按用户设置启动: http://{host}:{actual_port}, 认证码: {token}")
            if self._server_action is not None:
                self._server_action.setText(tr('server_stop', '停止服务'))
        except Exception as e:
            logger.error(f"自动启动服务失败: {e}")

    def _toggle_server(self):
        try:
            from server.app import get_server, start_server, stop_server, set_main_window
            from server.routes import get_auth_token
            set_main_window(self)
            server = get_server()
            tr = self.language_manager.tr
            if server.is_running():
                stop_server()
                self.status_bar_show_message(tr('server_stopped', '服务已停止'))
                self._server_action.setText(tr('server_start', '启动服务'))
            else:
                settings = self.config.load_server_settings()
                port = settings.get('port', 8080)
                host = settings.get('host', '0.0.0.0')
                server = start_server(host=host, port=port)
                if not (server is not None and server.wait_started(2.0)):
                    err = getattr(server, 'start_error', '') if server is not None else ''
                    self.status_bar_show_message(
                        tr('server_start_failed', '服务启动失败') + (f': {err}' if err else ''), 8000)
                    logger.error(f"启动服务失败: {err or '端口未绑定成功'}")
                    return
                token = get_auth_token()
                actual_port = server.port
                msg = (tr('server_started', '服务已启动') + f' http://localhost:{actual_port}  ' +
                       tr('server_auth_token', '认证码') + f': {token}')
                if server.requested_port != actual_port:
                    msg += '  ' + tr(
                        'server_port_shifted', '端口 {requested} 已被占用，已改用 {port}').format(
                        requested=server.requested_port, port=actual_port)
                self.status_bar_show_message(msg, 10000)
                self._server_action.setText(tr('server_stop', '停止服务'))
        except Exception as e:
            logger.error(f"切换服务失败: {e}")

    def _open_server_api(self):
        try:
            from server.app import get_server
            from server.routes import get_auth_token
            server = get_server()
            if not server or not server.is_running():
                tr = self.language_manager.tr
                self.status_bar_show_message(
                    tr('server_not_running_hint', '服务未运行，请先在“工具 > 服务”中启动服务'), 5000
                )
                return
            port = server.port
            token = get_auth_token()
            import webbrowser
            webbrowser.open(f'http://localhost:{port}/?token={token}')
        except Exception as e:
            logger.error(f"打开Server API失败: {e}")

    def _show_server_settings(self):

        from ui.styles import AppStyles
        from ui.floating_dialog import FloatingDialog
        tr = self.language_manager.tr
        dialog = FloatingDialog(self, frameless=False, stay_on_top=False)
        dialog.setWindowTitle(tr('server_settings', 'Server设置'))
        dialog.setStyleSheet(AppStyles.dialog_style())
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        settings = self.config.load_server_settings()

        from server.app import get_server
        from server.routes import get_auth_token
        server = get_server()
        is_running = server.is_running()
        configured_port = settings.get('port', 8080)
        # 运行中显示实际绑定端口：配置端口被占用时会自动顺延
        port = server.port if is_running else configured_port

        status_label = QLabel()
        token = get_auth_token()
        if is_running:
            text = (
                f"● {tr('server_running', '服务运行中')}\n"
                f"  {tr('server_address', '地址')}: http://localhost:{port}\n"
                f"  {tr('server_auth_token', '认证码')}: {token}"
            )
            if configured_port != port:
                text += "\n  " + tr(
                    'server_port_shifted', '端口 {requested} 已被占用，已改用 {port}').format(
                    requested=configured_port, port=port)
            status_label.setText(text)
            status_label.setStyleSheet(AppStyles.status_label_style(True))
        else:
            # 未启动时也把地址与认证码显示出来，方便先配置好客户端再启动服务
            status_label.setText(
                f"○ {tr('server_not_running', '服务未运行')}\n"
                f"  {tr('server_address', '地址')}: http://localhost:{port}\n"
                f"  {tr('server_auth_token', '认证码')}: {token}"
            )
            status_label.setStyleSheet(AppStyles.status_label_style(False))
        status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(status_label)

        layout.addSpacing(4)

        auto_start_cb = QCheckBox(tr('server_auto_start', '启动时自动运行服务'))
        auto_start_cb.setChecked(settings.get('auto_start', False))
        layout.addWidget(auto_start_cb)

        port_layout = QHBoxLayout()
        port_label = QLabel(tr('server_port', '端口:'))
        port_label.setFixedWidth(70)
        port_layout.addWidget(port_label)
        port_spin = QSpinBox()
        port_spin.setRange(1024, 65535)
        # 端口框保留配置值（起始端口），实际端口见上方状态；避免把顺延后的端口写回配置
        port_spin.setValue(configured_port)
        port_layout.addWidget(port_spin, 1)
        layout.addLayout(port_layout)

        host_layout = QHBoxLayout()
        host_label = QLabel(tr('server_host', '监听地址:'))
        host_label.setFixedWidth(70)
        host_layout.addWidget(host_label)
        host_combo = QComboBox()
        host_combo.addItem(f"0.0.0.0 ({tr('all_interfaces', '所有接口')})", '0.0.0.0')
        host_combo.addItem(f"127.0.0.1 ({tr('localhost_only', '仅本机')})", '127.0.0.1')
        host_idx = host_combo.findData(settings.get('host', '127.0.0.1'))
        if host_idx >= 0:
            host_combo.setCurrentIndex(host_idx)
        host_layout.addWidget(host_combo, 1)
        layout.addLayout(host_layout)

        host_hint = QLabel(tr('server_host_hint',
                              '仅本机：只有这台电脑能访问；所有接口：同一局域网的其他设备也能访问。'))
        host_hint.setWordWrap(True)
        host_hint.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        layout.addWidget(host_hint)

        layout.addSpacing(8)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton(tr('save', '保存'))
        cancel_btn = QPushButton(tr('cancel', '取消'))
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_save():
            auto_start = auto_start_cb.isChecked()
            self.config.save_server_settings(
                enabled=auto_start,
                port=port_spin.value(),
                host=host_combo.currentData(),
                auto_start=auto_start
            )
            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        save_btn.setStyleSheet(AppStyles.common_button_style())
        cancel_btn.setStyleSheet(AppStyles.common_button_style())

        dialog.setStyleSheet(AppStyles.popup_dialog_style())
        dialog.exec()