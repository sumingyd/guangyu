"""网络设置域存储 — 网络/扫描/服务器/映射/URL 历史。"""


class NetworkSettingsStore:
    """网络配置域存储，通过 facade 访问共享 ConfigParser。"""

    def __init__(self, facade):
        self._facade = facade

    def save_network_settings(self, url, timeout, threads, user_agent, referer):
        """保存网络设置"""
        self._facade.set_value('Network', 'url', url)
        self._facade.set_value('Network', 'timeout', str(timeout))
        self._facade.set_value('Network', 'threads', str(threads))
        self._facade.set_value('Network', 'user_agent', user_agent)
        self._facade.set_value('Network', 'referer', referer)
        return self._facade.save_config()

    def load_network_settings(self):
        f = self._facade
        return {
            'url': f.get_value('Network', 'url', ''),
            'timeout': f._parse_int(f.get_value('Network', 'timeout', '5'), 5),
            'threads': f._parse_int(f.get_value('Network', 'threads', '4'), 4),
            'user_agent': f.get_value('Network', 'user_agent', ''),
            'referer': f.get_value('Network', 'referer', '')
        }

    def save_url_history(self, urls):
        self._facade.set_value('Network', 'url_count', str(len(urls)))
        for i, url in enumerate(urls):
            self._facade.set_value('Network', f'url_{i}', url)
        return self._facade.save_config()

    def load_url_history(self):
        f = self._facade
        count = f._parse_int(f.get_value('Network', 'url_count', '0') or '0')
        return [f.get_value('Network', f'url_{i}', '') for i in range(count) if f.get_value('Network', f'url_{i}')]

    def save_scan_retry_settings(self, enable_retry):
        self._facade.set_value('ScanRetry', 'enable_retry', str(enable_retry))
        return self._facade.save_config()

    def load_scan_retry_settings(self):
        return {
            'enable_retry': self._facade._parse_bool(self._facade.get_value('ScanRetry', 'enable_retry', 'False'))
        }

    def save_scan_engine_settings(self, engine: str):
        """保存扫描引擎设置，engine: 'mpv' 或 'ffprobe'"""
        self._facade.set_value('ScanEngine', 'engine', engine)
        return self._facade.save_config()

    def load_scan_engine_settings(self) -> dict:
        """加载扫描引擎设置"""
        return {
            'engine': self._facade.get_value('ScanEngine', 'engine', 'ffprobe')
        }

    def save_server_settings(self, enabled: bool = False, port: int = 8080,
                             host: str = '0.0.0.0', auto_start: bool = False):
        """保存Server后端设置（默认关闭，按需手动开启）"""
        self._facade.set_value('Server', 'enabled', str(enabled))
        self._facade.set_value('Server', 'port', str(port))
        self._facade.set_value('Server', 'host', host)
        self._facade.set_value('Server', 'auto_start', str(auto_start))
        return self._facade.save_config()

    def load_server_settings(self) -> dict:
        """加载Server后端设置

        默认关闭：配置键不存在（新用户/新配置）时返回 auto_start=False；
        配置里显式写入 True 的老用户保持开启，不受默认值变更影响。
        """
        f = self._facade
        return {
            'enabled': f._parse_bool(f.get_value('Server', 'enabled', 'False'), False),
            'port': f._parse_int(f.get_value('Server', 'port', '8080'), 8080),
            'host': f.get_value('Server', 'host', '0.0.0.0') or '0.0.0.0',
            'auto_start': f._parse_bool(f.get_value('Server', 'auto_start', 'False'), False)
        }

    def save_mapping_settings(self, enable_mapping: bool = True):
        """保存映射功能设置"""
        self._facade.set_value('Mapping', 'enable_mapping', str(enable_mapping))
        return self._facade.save_config()

    def load_mapping_settings(self) -> dict:
        return {
            'enable_mapping': self._facade._parse_bool(self._facade.get_value('Mapping', 'enable_mapping', 'True'), True)
        }