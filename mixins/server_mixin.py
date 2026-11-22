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
                logger.info("HTTP 服务器未启动（默认关闭，可在“设置 > 网络 > 服务设置”中开启）")
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
            logger.info(f"HTTP 服务器已按用户设置启动: http://{host}:{actual_port}（认证码见服务设置）")
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
        """服务设置已并入「网络」页签，入口直接打开主设置对话框并定位到该分组。"""
        self.player_settings('network')