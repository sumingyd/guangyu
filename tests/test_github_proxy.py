"""GitHub 加速代理配置与 URL 改写测试。"""

import utils.github_proxy as gp


def _settings(enabled=True, proxy=gp.DEFAULT_PROXY):
    return {'enabled': enabled, 'proxy': proxy, 'proxies': list(gp.PROXY_LIST)}


def test_proxy_list_order_and_default():
    assert gp.DEFAULT_PROXY == 'gh-proxy.com'
    assert len(gp.PROXY_LIST) == 25
    assert gp.PROXY_LIST[0] == 'github.chenc.dev'
    assert gp.PROXY_LIST[2] == 'gh-proxy.com'
    assert gp.PROXY_LIST[10] == 'gh.jiji.gv.uy'
    assert gp.PROXY_LIST[-1] == 'gg.z321.cc.cd'
    assert 'gh.jïji.gv.uy' not in gp.PROXY_LIST


def test_rewrite_only_github_hosts():
    cases = [
        'https://github.com/a/b/releases/download/v1/app.apk',
        'https://api.github.com/repos/a/b/releases/latest',
        'https://raw.githubusercontent.com/a/b/main/c.json',
        'https://gist.githubusercontent.com/a/b/raw/x.csv',
        'https://objects.githubusercontent.com/x/y',
        'https://codeload.github.com/a/b/zip/main',
    ]
    for url in cases:
        assert gp.is_github_url(url) is True
        assert gp.rewrite_url(url, True, 'gh-proxy.com') == f'https://gh-proxy.com/{url}'


def test_non_github_urls_untouched():
    for url in (
        'https://example.com/playlist.m3u',
        'https://my-epg.example.org/epg.xml',
        'https://notgithub.com/a/b',
        'https://github.com.evil.example/a/b',
        'http://github.chenc.dev/https://github.com/a/b',
    ):
        assert gp.rewrite_url(url, True, 'gh-proxy.com') == url


def test_rewrite_disabled_and_already_proxied():
    url = 'https://github.com/a/b'
    assert gp.rewrite_url(url, False, 'gh-proxy.com') == url
    proxied = 'https://gh-proxy.com/https://github.com/a/b'
    assert gp.rewrite_url(proxied, True, 'gh-proxy.com') == proxied


def test_normalize_proxy_fallback():
    assert gp._normalize_proxy('https://GHFAST.top/') == 'ghfast.top'
    assert gp._normalize_proxy('unknown.proxy') == gp.DEFAULT_PROXY
    assert gp._normalize_proxy('') == gp.DEFAULT_PROXY


def test_http_session_rewrites_github(monkeypatch):
    import utils.http_session as hs

    captured = {}

    class FakeSession:
        def get(self, url, **kwargs):
            captured['url'] = url
            return 'ok'

    monkeypatch.setattr(hs, 'get_session', lambda: FakeSession())
    monkeypatch.setattr(gp, 'load_settings', lambda: _settings(True, 'ghfast.top'))

    assert hs.get('https://github.com/a/b') == 'ok'
    assert captured['url'] == 'https://ghfast.top/https://github.com/a/b'


def test_http_session_keeps_non_github(monkeypatch):
    import utils.http_session as hs

    captured = {}

    class FakeSession:
        def get(self, url, **kwargs):
            captured['url'] = url
            return 'ok'

    monkeypatch.setattr(hs, 'get_session', lambda: FakeSession())
    monkeypatch.setattr(gp, 'load_settings', lambda: _settings(True))

    hs.get('https://example.com/list.m3u')
    assert captured['url'] == 'https://example.com/list.m3u'
