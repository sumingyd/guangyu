"""GitHub 加速代理：统一改写 GitHub 域名的下载/接口请求。

只有 GitHub 相关域名会被改写，用户自己的订阅源、EPG 源等非 GitHub 地址保持原样。
供 PC 端（requests / aiohttp）与 Android 端（Kotlin 更新检查与下载）共用同一份
配置，配置持久化在 config.ini 的 [Network] 段。
"""

from urllib.parse import urlsplit

DEFAULT_PROXY = 'gh-proxy.com'

# 顺序即界面展示顺序，不要随意调整
PROXY_LIST = [
    'github.chenc.dev',
    'github.xxlab.tech',
    'gh-proxy.com',
    'ghfast.top',
    'gh.sixyin.com',
    'cdn.gh-proxy.com',
    'gh.noki.icu',
    'ghproxy.monkeyray.net',
    'cdn.akaere.online',
    'ghfile.geekertao.top',
    'gh.jiji.gv.uy',
    'ghproxy.net',
    'down.mxw.xx.kg',
    'gh.beimengvv.xyz',
    'ghp.keleyaa.com',
    'github.tbap.top',
    'github.ednovas.xyz',
    'gh.dpik.top',
    'gh.idayer.com',
    'cfgh.ikgy.top',
    'proxy.yaoyaoling.net',
    'git.yylx.win',
    '777.z321.cc.cd',
    'gh.acmsz.top',
    'gg.z321.cc.cd',
]

CONFIG_SECTION = 'Network'
KEY_ENABLED = 'github_proxy_enabled'
KEY_PROXY = 'github_proxy'

_GITHUB_HOSTS = {
    'github.com',
    'githubusercontent.com',
    'raw.githubusercontent.com',
    'gist.githubusercontent.com',
    'objects.githubusercontent.com',
    'codeload.github.com',
}


def _config():
    """懒加载配置，避免与 core 模块形成循环导入。"""
    from core.config_manager import ConfigManager
    return ConfigManager()


def _normalize_proxy(value) -> str:
    """把配置值规范成清单中的代理域名；非法值回退默认代理。"""
    proxy = str(value or '').strip().lower()
    for prefix in ('https://', 'http://'):
        if proxy.startswith(prefix):
            proxy = proxy[len(prefix):]
    proxy = proxy.rstrip('/')
    return proxy if proxy in PROXY_LIST else DEFAULT_PROXY


def _parse_enabled(value) -> bool:
    """缺省视为开启；兼容手工编辑产生的多种布尔写法。"""
    if value is None:
        return True
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'y')


def load_settings() -> dict:
    """读取当前配置，配置不可用时回退默认值（开启 + gh-proxy.com）。"""
    enabled, proxy = True, DEFAULT_PROXY
    try:
        cfg = _config()
        enabled = _parse_enabled(cfg.get_value(CONFIG_SECTION, KEY_ENABLED, None))
        proxy = _normalize_proxy(cfg.get_value(CONFIG_SECTION, KEY_PROXY, '') or '')
    except Exception:
        pass
    return {
        'enabled': enabled,
        'proxy': proxy,
        'proxies': list(PROXY_LIST),
    }


def save_settings(enabled: bool, proxy: str) -> dict:
    """保存配置并立即落盘（重启后保留）。"""
    normalized = _normalize_proxy(proxy)
    cfg = _config()
    cfg.set_value(CONFIG_SECTION, KEY_ENABLED, 'true' if enabled else 'false')
    cfg.set_value(CONFIG_SECTION, KEY_PROXY, normalized)
    cfg.save_config(immediate=True)
    return {
        'enabled': bool(enabled),
        'proxy': normalized,
        'proxies': list(PROXY_LIST),
    }


def is_github_url(url: str) -> bool:
    """判断 URL 是否属于需要走加速代理的 GitHub 域名。"""
    try:
        parts = urlsplit(str(url or '').strip())
    except Exception:
        return False
    if parts.scheme not in ('http', 'https'):
        return False
    host = (parts.hostname or '').lower().rstrip('.')
    if not host:
        return False
    if host in _GITHUB_HOSTS:
        return True
    # api.github.com / codeload.github.com 等子域，以及 raw/gist/objects.githubusercontent.com 系列
    return host.endswith('.github.com') or host.endswith('.githubusercontent.com')


def rewrite_url(url: str, enabled: bool | None = None,
                proxy: str | None = None) -> str:
    """按配置改写 GitHub URL，其余地址原样返回。"""
    original = str(url or '').strip()
    if not original:
        return url
    if enabled is None or proxy is None:
        settings = load_settings()
        if enabled is None:
            enabled = settings['enabled']
        if proxy is None:
            proxy = settings['proxy']
    if not enabled:
        return original
    proxy = _normalize_proxy(proxy)
    if not is_github_url(original):
        return original
    # 已经是代理地址时不重复拼接
    try:
        if (urlsplit(original).hostname or '').lower() == proxy:
            return original
    except Exception:
        pass
    return f'https://{proxy}/{original}'
