"""
字幕在线下载服务 - 多源字幕聚合搜索

数据源：
  1. OpenSubtitles (XML-RPC) - 国际字幕库，支持自动搜索和自动下载（gzip 解压）
  2. SubHD (subhd.me) - 中文字幕站，支持自动搜索；下载需公众号验证码，
     仅提供详情页跳转，由用户在浏览器中完成下载
  3. SubtitleCat (subtitlecat.com) - 国际字幕翻译站，免登录、无验证码、
     支持中文片名搜索（命中率低，英文片名命中率高），下载直接 .srt
     详情页含各语言 .srt 直链，下载时按语言选择

并行搜索三个源，合并去重，按评分排序。OpenSubtitles/SubtitleCat 项支持自动下载，
SubHD 项标记 auto_download=False，UI 应提示用户"在浏览器中打开"。
"""
import os
import re
import socket
import threading
import xmlrpc.client
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from core.log_manager import global_logger as logger

# OpenSubtitles 公共 XML-RPC 端点（实测 2026 年仍可用）
OS_SERVER_URL = "https://api.opensubtitles.org/xml-rpc"
OS_USER_AGENT = "IPTVScannerEditorPro/1.0"

# SubHD 配置（subhd.tv 已被墙，使用 subhd.me）
SUBHD_BASE_URL = "https://subhd.me"
SUBHD_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# SubtitleCat 配置（免登录、无验证码、直接下载 .srt）
SUBCAT_BASE_URL = "https://www.subtitlecat.com"
SUBCAT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 网络超时（秒）—— OpenSubtitles 服务器在欧洲，国内访问可能较慢
DEFAULT_TIMEOUT = 30
# 登录/搜索最大重试次数
MAX_RETRIES = 2

# 语言代码 → SubHD 文本关键词映射（用于过滤 SubHD 搜索结果）
LANG_KEYWORDS = {
    'eng': ['英语', 'English', '双语'],
    'chi': ['简体', '繁体', '中文', '双语'],
    'jpn': ['日语', 'Japanese', '双语'],
}

# SubtitleCat 语言代码映射（OpenSubtitles 风格 → SubtitleCat URL 语言代码）
SUBCAT_LANG_MAP = {
    'chi': ['zh-CN', 'zh-TW'],   # 简体 + 繁体
    'eng': ['en'],
    'jpn': ['ja'],
    'kor': ['ko'],
}

# 只允许通过网络协议下载字幕，禁止 file:// 等本地协议被远端数据注入
_ALLOWED_DOWNLOAD_SCHEMES = ('http', 'https')


def _validate_remote_url(url: str) -> str:
    """校验远端下载链接，拒绝 file://、ftp:// 等非网络协议"""
    raw = (url or '').strip()
    parsed = urllib.parse.urlparse(raw)
    scheme = (parsed.scheme or '').lower()
    if scheme not in _ALLOWED_DOWNLOAD_SCHEMES:
        raise ValueError(f'不支持的下载协议: {scheme or "(空)"}')
    if not parsed.netloc:
        raise ValueError('下载链接缺少主机名')
    return raw


def _safe_subtitle_name(name: str, default: str) -> str:
    """把远端/调用方提供的文件名收敛为单层文件名，防止路径穿越"""
    base = os.path.basename((name or '').replace('\\', '/')).strip()
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', base).strip('. ')
    if not base or base in ('.', '..'):
        base = default
    return base


def _ensure_inside(path: str, dest_dir: str) -> str:
    """校验落点 realpath 确实位于缓存目录内"""
    root = os.path.realpath(dest_dir)
    target = os.path.realpath(path)
    if target != root and not target.startswith(root + os.sep):
        raise ValueError(f'字幕落点超出缓存目录: {target}')
    return target


def _urlopen(request, timeout=DEFAULT_TIMEOUT):
    """统一走 urllib，并按 [Playback] http_proxy 配置应用代理"""
    proxy_url = ''
    try:
        from core.config_manager import ConfigManager
        proxy_url = (ConfigManager().get_value('Playback', 'http_proxy', '') or '').strip()
    except Exception:
        proxy_url = ''
    if proxy_url:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


class _TimeoutTransport(xmlrpc.client.Transport):
    """带超时控制的 XML-RPC Transport"""

    def __init__(self, timeout=DEFAULT_TIMEOUT):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class SubtitleDownloadService:
    """字幕下载服务（多源聚合）

    数据源：
      1. OpenSubtitles - 国际字幕库，支持自动搜索和自动下载
      2. SubHD - 中文字幕站，支持自动搜索，下载需要浏览器跳转

    并行搜索两个源，合并去重，按评分排序。
    """

    def __init__(self):
        self._proxy = None
        self._token = None
        self._lock = threading.Lock()
        # 最近一次错误信息（供 UI 显示具体原因，而非笼统的"没有找到字幕"）
        self.last_error = ''

    # ==================== 公共接口 ====================
    def search(self, query: str = "", imdb_id: str = "", language: str = "eng",
               file_path: str = "") -> list:
        """搜索字幕（多源并行）

        Args:
            query: 文件名/关键词（如片名，支持中英文）
            imdb_id: IMDb ID（如 tt1234567）
            language: 语言代码（eng, chi, jpn 等，多语言用逗号分隔；
                      'all' 或空表示不限语言）
            file_path: 视频文件路径（用于 hash 搜索）

        Returns:
            字幕信息列表，每项含 source/file_name/language/format 等。
            OpenSubtitles/SubtitleCat 项有 auto_download=True，可直接调用 download()；
            SubHD 项有 auto_download=False，应调用 open_in_browser() 跳转下载。
            失败返回空列表，并设置 self.last_error。
        """
        self.last_error = ''

        os_items: list = []
        subhd_items: list = []
        subcat_items: list = []
        errors: list = []

        # 并行搜索三个源
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {
                ex.submit(self._search_opensubtitles, query, imdb_id, language, file_path): 'os',
                ex.submit(self._search_subhd, query, language): 'subhd',
                ex.submit(self._search_subtitlecat, query, language): 'subcat',
            }
            try:
                for fut in as_completed(futs, timeout=DEFAULT_TIMEOUT * 2 + 5):
                    src = futs[fut]
                    try:
                        items, err = fut.result()
                        if src == 'os':
                            os_items = items
                        elif src == 'subhd':
                            subhd_items = items
                        else:
                            subcat_items = items
                        if err:
                            name = {'os': 'OpenSubtitles', 'subhd': 'SubHD', 'subcat': 'SubtitleCat'}[src]
                            errors.append(f'{name}: {err}')
                    except Exception as e:
                        name = {'os': 'OpenSubtitles', 'subhd': 'SubHD', 'subcat': 'SubtitleCat'}[src]
                        errors.append(f'{name}: {type(e).__name__}: {e}')
                        logger.warning(f'字幕搜索 {name} 异常: {e}')
            except FuturesTimeoutError:
                errors.append('搜索超时')

        # 合并去重（按 file_name + language 去重）
        all_items = os_items + subhd_items + subcat_items
        seen = set()
        unique = []
        for item in all_items:
            key = (item.get('file_name', '').lower().strip(),
                   item.get('language', '').lower().strip())
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        # 排序：自动下载优先 > 评分 > 评级
        unique.sort(key=lambda x: (
            x.get('auto_download', False),
            x.get('score', 0),
            x.get('rating', 0),
        ), reverse=True)

        # 设置 last_error
        if not unique:
            if errors:
                self.last_error = ' | '.join(errors)
            else:
                if not query and not file_path and not imdb_id:
                    self.last_error = '请输入片名，或打开本地视频文件以使用哈希精准匹配'
                elif query and not file_path:
                    self.last_error = (f'未找到与"{query}"匹配的字幕。'
                                       f'已尝试 OpenSubtitles、SubHD 和 SubtitleCat 三个字幕源')
                else:
                    self.last_error = ''
        return unique

    def download(self, download_link: str, dest_dir: str, file_name: str = "",
                 language: str = "") -> str:
        """下载字幕文件到 dest_dir，返回最终路径

        支持的链接类型：
          - OpenSubtitles: gzip 自动解压
          - SubtitleCat: 直接 .srt 下载（需 fetch 详情页解析直链，language 参数用于选语言）
          - SubHD: 需要公众号验证码，请用 open_in_browser() 跳转浏览器下载
        """
        # SubHD：需要浏览器跳转
        if 'subhd.me' in download_link or '/down/' in download_link:
            self.last_error = 'SubHD 字幕需要在浏览器中手动下载（需公众号验证码），请使用 open_in_browser()'
            logger.warning(self.last_error)
            return ''
        # 远端来源可能被注入 file:// 等本地协议，先做协议白名单校验
        try:
            download_link = _validate_remote_url(download_link)
        except ValueError as e:
            self.last_error = f'下载链接不合法: {e}'
            logger.warning(f'{self.last_error} | url={download_link[:120]}')
            return ''
        # SubtitleCat：download_link 是详情页 URL，需 fetch 解析 .srt 直链
        if 'subtitlecat.com' in download_link or '/subs/' in download_link:
            return self._download_subtitlecat(download_link, dest_dir, file_name, language)
        # OpenSubtitles：gzip 自动解压
        return self._download_opensubtitles(download_link, dest_dir, file_name)

    @staticmethod
    def _urlopen(request, timeout=DEFAULT_TIMEOUT):
        return _urlopen(request, timeout=timeout)

    def open_in_browser(self, url: str) -> bool:
        """在默认浏览器中打开 URL（用于 SubHD 等需要手动下载的源）"""
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception as e:
            self.last_error = f'打开浏览器失败: {type(e).__name__}: {e}'
            logger.warning(self.last_error)
            return False

    # ==================== OpenSubtitles 实现 ====================
    def _get_proxy(self):
        if self._proxy is None:
            self._proxy = xmlrpc.client.ServerProxy(
                OS_SERVER_URL,
                transport=_TimeoutTransport(DEFAULT_TIMEOUT),
                allow_none=True,
            )
        return self._proxy

    def _login_anonymous(self) -> str:
        """匿名登录，返回 token；失败返回空串"""
        if self._token:
            return self._token
        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                proxy = self._get_proxy()
                result = proxy.LogIn("", "", "en", OS_USER_AGENT)
                status = result.get('status', '')
                if status.startswith('200'):
                    self._token = result.get('token', '')
                    if self._token:
                        return self._token
                # 401 通常是 UA 未注册或被限流
                logger.warning(f'OpenSubtitles 登录被拒绝 (status={status})')
                return ''
            except (socket.timeout, TimeoutError) as e:
                last_exc = e
                logger.warning(f'登录超时 (尝试 {attempt+1}/{MAX_RETRIES+1}): {e}')
                self._proxy = None
            except Exception as e:
                last_exc = e
                logger.warning(f'登录异常 (尝试 {attempt+1}/{MAX_RETRIES+1}): {e}')
                self._proxy = None
        if last_exc:
            logger.warning(f'登录最终失败: {last_exc}')
        return ''

    def search_legacy(self, query: str = "", imdb_id: str = "", language: str = "eng",
                      file_path: str = "") -> list:
        """[已废弃] 仅 OpenSubtitles 单源搜索，保留以兼容旧调用。

        新代码应使用 search() 方法以获得多源聚合结果。
        """
        items, _ = self._search_opensubtitles(query, imdb_id, language, file_path)
        return items

    def _search_opensubtitles(self, query: str, imdb_id: str, language: str,
                              file_path: str) -> tuple:
        """OpenSubtitles 搜索

        策略（按优先级）：
          1. 文件哈希精准匹配（带语言过滤，最准确）
          2. IMDB ID 搜索（query 为中文时通过 SearchMoviesOnIMDB 中转）
          3. 关键词搜索（query 直接搜索）
          4. 纯哈希搜索（不限语言，回退）

        Returns:
            (items, error_message)
        """
        with self._lock:
            token = self._login_anonymous()
            if not token:
                return [], 'OpenSubtitles 登录失败（可能是 UA 被限流或网络问题）'
            try:
                proxy = self._get_proxy()
                # 计算文件哈希
                file_hash = ''
                file_size = 0
                if file_path and os.path.exists(file_path):
                    file_hash, file_size = self._compute_file_hash(file_path)

                # 策略 1：优先用文件哈希精准搜索（带语言过滤）
                if file_hash and file_size:
                    hash_query = {'moviehash': file_hash, 'moviebytesize': file_size}
                    if language and language != 'all':
                        hash_query['sublanguageid'] = language
                    items = self._do_search(proxy, token, hash_query)
                    if items:
                        return items, ''
                    # 哈希搜索未命中，继续尝试关键词搜索

                # 策略 2：IMDB ID 搜索
                # 若用户未提供 imdb_id 且 query 包含中文，先通过 SearchMoviesOnIMDB 中转查询
                effective_imdb = imdb_id
                if not effective_imdb and query and self._contains_cjk(query):
                    effective_imdb = self._search_imdb_by_name(proxy, token, query)
                if effective_imdb:
                    imdb_query = {'imdbid': effective_imdb}
                    if language and language != 'all':
                        imdb_query['sublanguageid'] = language
                    items = self._do_search(proxy, token, imdb_query)
                    if items:
                        return items, ''

                # 策略 3：用关键词搜索
                if query:
                    keyword_query = {}
                    if language and language != 'all':
                        keyword_query['sublanguageid'] = language
                    keyword_query['query'] = query
                    items = self._do_search(proxy, token, keyword_query)
                    if items:
                        return items, ''

                # 策略 4：若有哈希但前几步都未命中，最后用纯哈希搜索（不限语言）
                if file_hash and file_size:
                    hash_only = {'moviehash': file_hash, 'moviebytesize': file_size}
                    items = self._do_search(proxy, token, hash_only)
                    if items:
                        return items, ''

                # 全部策略都未命中
                return [], ''
            except (socket.timeout, TimeoutError) as e:
                self._proxy = None
                self._token = None
                return [], f'搜索请求超时（{DEFAULT_TIMEOUT}s）'
            except Exception as e:
                self._proxy = None
                self._token = None
                return [], f'搜索异常: {type(e).__name__}: {e}'

    def _do_search(self, proxy, token, query_dict: dict) -> list:
        """执行一次 SearchSubtitles 调用，解析结果"""
        result = proxy.SearchSubtitles(token, [query_dict])
        if not isinstance(result, dict):
            return []
        if not result.get('status', '').startswith('200'):
            status = result.get('status', 'unknown')
            logger.warning(f'OpenSubtitles 搜索失败 (status={status})')
            return []
        data = result.get('data', False)
        if not data or data is True:
            return []
        items = []
        for d in data:
            items.append({
                'source': 'OpenSubtitles',
                'id': d.get('IDSubtitleFile', ''),
                'file_name': d.get('SubFileName', ''),
                'download_link': d.get('SubDownloadLink', ''),
                'zip_link': d.get('ZipDownloadLink', ''),
                'movie_name': d.get('MovieName', ''),
                'language': d.get('LanguageName', ''),
                'language_id': d.get('SubLanguageID', ''),
                'score': float(d.get('Score', 0) or 0),
                'format': d.get('SubFormat', 'srt'),
                'encoding': d.get('SubEncoding', 'UTF-8'),
                'rating': float(d.get('SubRating', 0) or 0),
                'bad': d.get('SubBad', '0') == '1',
                'download_count': int(d.get('SubDownloadCnt', 0) or 0),
                'add_date': d.get('SubAddDate', ''),
                'auto_download': True,  # 支持自动下载
            })
        # 按评分降序
        items.sort(key=lambda x: (x['score'], x['rating']), reverse=True)
        return items

    def _download_opensubtitles(self, download_link: str, dest_dir: str,
                                file_name: str = "") -> str:
        """下载 OpenSubtitles 字幕（解压 gzip）到 dest_dir，返回最终路径"""
        try:
            os.makedirs(dest_dir, exist_ok=True)
            download_link = _validate_remote_url(download_link)
            # 只接受单层文件名，防止 file_name 携带 ../ 造成路径穿越
            default_name = os.path.basename(urllib.parse.urlparse(download_link).path) or 'subtitle.srt'
            fname = _safe_subtitle_name(file_name or default_name, 'subtitle.srt')
            # download_link 通常是 .gz 包裹的 srt 文件
            tmp_path = _ensure_inside(os.path.join(dest_dir, fname + ".gz"), dest_dir)
            req = urllib.request.Request(download_link, headers={'User-Agent': OS_USER_AGENT})
            with _urlopen(req, timeout=DEFAULT_TIMEOUT) as resp, \
                    open(tmp_path, 'wb') as f:
                f.write(resp.read())
            # 解压
            final_name = fname if not fname.endswith('.gz') else fname[:-3]
            final_path = _ensure_inside(os.path.join(dest_dir, final_name), dest_dir)
            try:
                import gzip
                with gzip.open(tmp_path, 'rb') as gz, open(final_path, 'wb') as out:
                    out.write(gz.read())
                os.remove(tmp_path)
            except Exception:
                # 若不是 gzip，直接重命名
                os.rename(tmp_path, final_path)
            return final_path
        except Exception as e:
            self.last_error = f'下载字幕失败: {type(e).__name__}: {e}'
            logger.warning(self.last_error)
            return ''

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        """检测字符串是否包含中日韩文字（用于判断是否需要 IMDB 中转搜索）"""
        if not text:
            return False
        # CJK 统一表意文字 + 扩展 + 日文假名 + 韩文
        return bool(re.search(
            r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]', text))

    def _search_imdb_by_name(self, proxy, token, name: str) -> str:
        """通过 OpenSubtitles 的 SearchMoviesOnIMDB 接口搜索 IMDB ID

        返回首个匹配的 IMDB ID（如 tt1234567），失败返回空串。
        IMDB 索引比 OpenSubtitles 字幕库更全，中文片名可能命中。
        """
        try:
            result = proxy.SearchMoviesOnIMDB(token, name)
            if not isinstance(result, dict):
                return ''
            if not result.get('status', '').startswith('200'):
                logger.warning(f"SearchMoviesOnIMDB 失败 (status={result.get('status', '')})")
                return ''
            data = result.get('data', [])
            if not data or data is True:
                return ''
            for item in data:
                imdb = item.get('id', '') or ''
                # IMDB ID 形如 tt1234567
                if imdb.startswith('tt') and len(imdb) >= 3:
                    movie_title = item.get('title', '') or ''
                    logger.info(f"IMDB 搜索 '{name}' 命中: {imdb} - {movie_title}")
                    return imdb
            return ''
        except Exception as e:
            logger.warning(f"SearchMoviesOnIMDB 异常: {e}")
            return ''

    @staticmethod
    def _compute_file_hash(file_path: str):
        """OpenSubtitles 文件 hash 算法，返回 (hash_str, size_bytes)"""
        try:
            size = os.path.getsize(file_path)
            if size < 131072:  # 文件太小，hash 算法要求至少 128KB
                return '', 0
            hash_val = size
            with open(file_path, 'rb') as f:
                # 前 64KB
                for i in range(0, 65536, 8):
                    buf = f.read(8)
                    if len(buf) < 8:
                        break
                    (val,) = _unpack_qword(buf)
                    hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF  # 64-bit
                # 后 64KB
                f.seek(max(0, size - 65536))
                for i in range(0, 65536, 8):
                    buf = f.read(8)
                    if len(buf) < 8:
                        break
                    (val,) = _unpack_qword(buf)
                    hash_val = (hash_val + val) & 0xFFFFFFFFFFFFFFFF
            return f"{hash_val:016x}", size
        except Exception as e:
            logger.debug(f"计算文件 hash 失败: {e}")
            return '', 0

    # ==================== SubHD 实现 ====================
    def _search_subhd(self, query: str, language: str) -> tuple:
        """SubHD 搜索（爬虫 subhd.me）

        Args:
            query: 搜索关键词（片名）
            language: 语言代码（eng/chi/jpn/all）

        Returns:
            (items, error_message)
        """
        if not query:
            return [], ''
        try:
            # 从文件名提取片名（去掉分辨率、编码等后缀）
            search_query = self._extract_title_from_query(query)
            if not search_query:
                return [], ''

            url = f"{SUBHD_BASE_URL}/search/{urllib.parse.quote(search_query)}"
            html = self._fetch_html(url, referer=SUBHD_BASE_URL)
            items = self._parse_subhd_search_results(html)

            # 按语言过滤
            if language and language != 'all':
                items = self._filter_subhd_by_language(items, language)

            logger.info(f"SubHD 搜索 '{search_query}' 返回 {len(items)} 条结果")
            return items, ''
        except urllib.error.HTTPError as e:
            return [], f'SubHD HTTP {e.code}'
        except (socket.timeout, TimeoutError):
            return [], f'SubHD 搜索超时（{DEFAULT_TIMEOUT}s）'
        except Exception as e:
            return [], f'SubHD 搜索异常: {type(e).__name__}: {e}'

    @staticmethod
    def _extract_title_from_query(query: str) -> str:
        """从文件名/查询中提取纯片名（去掉分辨率、来源、编码、年份等后缀）

        SubHD 搜索是精确匹配（不分词），带后缀的关键词如
        "流浪地球2 2023 4K" 会搜不到，必须提取纯片名如 "流浪地球2"。
        """
        if not query:
            return ''
        # 去掉文件扩展名
        title = os.path.splitext(query)[0] if '.' in query else query
        # 在第一个技术标记处截断（分辨率/来源/编码/音频格式）
        # 标记列表：1080p, 2160p, 4K, 720p, BluRay, WEB-DL, HDR, DV, x264, hevc 等
        match = re.search(
            r'[\.\s\-]+(\d{3,4}p|4k|BluRay|BDRip|WEB-?DL|WEBRip|HDTV|REMUX|IMAX|HDR|DoVi|DV|Atmos|'
            r'HALFCD|x264|x265|h264|h265|hevc|aac|ddp|truehd|dts|ac3|10bit|8bit|hybrid|remastered|dolby|vision|'
            r'\u56fd\u8bed|\u7b80\u4f53|\u7e41\u4f53|\u53cc\u8bed|\u4e2d\u5b57|\u7b80\u7e41\u82f1|\u5b57\u5e55)',
            title,
            re.IGNORECASE
        )
        if match:
            title = title[:match.start()]
        # 去掉末尾的年份后缀（如 "片名.2023" → "片名"）
        # 注意：仅去掉末尾年份，避免误删片名中的数字（如"2012"作为片名时不会被删，因为它是整个 title）
        title = re.sub(r'[\.\s\-]+(19|20)\d{2}$', '', title)
        # 替换 . _ 为空格
        title = title.replace('.', ' ').replace('_', ' ').strip()
        return title

    @staticmethod
    def _fetch_html(url: str, referer: str = None) -> str:
        """获取 HTML 内容（模拟浏览器请求）"""
        headers = {
            'User-Agent': SUBHD_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        if referer:
            headers['Referer'] = referer
        req = urllib.request.Request(url, headers=headers)
        with _urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.read().decode('utf-8', errors='ignore')

    @staticmethod
    def _parse_subhd_search_results(html: str) -> list:
        """解析 SubHD 搜索结果页面

        HTML 结构（每项）：
        <div class="bg-white shadow-sm rounded-3 mb-4">
          ...
          <a class="link-dark align-middle" href='/a/{id}'>{title}</a>
          <div class="view-text text-secondary">
            <a href='/a/{id}' class='link-dark'>{video_filename}</a>
          </div>
          <div class="text-truncate py-2 f11">
            <span class="rounded p-1 me-1 text-white">{type}</span>
            <span class="p-1 fw-bold">{lang1}</span>
            <span class="p-1 fw-bold">{lang2}</span>
            <span class="p-1 text-secondary">{format}</span>
          </div>
          <div class="pt-2 text-secondary f12">
            <span class='align-text-top me-3'>{size}</span>
            <span class="align-text-top me-3">{download_count}</span>
            <span class="align-text-top me-3">{add_date}</span>
          </div>
          <div class="pt-1 f12 text-secondary">
            发布人 <a class="fw-bold text-dark" href='/u/{uploader}'>{uploader}</a>
          </div>
        </div>
        """
        items = []
        # 每个搜索结果项：以 <div class="bg-white shadow-sm rounded-3 mb-4"> 开始
        blocks = re.split(r'<div class="bg-white shadow-sm rounded-3 mb-4">', html)
        for block in blocks[1:]:  # 跳过第一段（页面头部）
            # 详情页链接 + 标题
            m = re.search(
                r"<a class=\"link-dark align-middle\" href='/a/([^']+)'>([^<]+)</a>", block)
            if not m:
                continue
            sub_id = m.group(1)
            title = m.group(2).strip()
            if not sub_id or not title:
                continue

            item = {
                'source': 'SubHD',
                'id': sub_id,
                'title': title,
                'detail_url': f"{SUBHD_BASE_URL}/a/{sub_id}",
                'download_link': f"{SUBHD_BASE_URL}/down/{sub_id}",
                'movie_name': title,
                'auto_download': False,  # SubHD 需要浏览器跳转下载
                'bad': False,
                'rating': 0,
                'encoding': 'UTF-8',
            }

            # 副标题（视频文件名）
            m = re.search(
                r"<div class=\"view-text text-secondary\">\s*<a href='/a/[^']+' class='link-dark'>\s*([^<]+?)\s*</a>",
                block)
            item['file_name'] = m.group(1).strip() if m else title

            # 类型（转载精修/官方字幕）
            m = re.search(
                r"<span class=\"rounded p-1 me-1 text-white\"[^>]*>([^<]+)</span>", block)
            item['type'] = m.group(1).strip() if m else ''

            # 语言（可能有多个：简体/繁体/双语/英语）
            lang_spans = re.findall(r"<span class=\"p-1 fw-bold\">([^<]+)</span>", block)
            item['language'] = ' '.join(s.strip() for s in lang_spans) if lang_spans else ''
            item['language_id'] = SubtitleDownloadService._normalize_subhd_language(item['language'])

            # 格式（ASS/SRT/SUP）
            format_spans = re.findall(r"<span class=\"p-1 text-secondary\">([^<]+)</span>", block)
            item['format'] = format_spans[0].strip().lower() if format_spans else 'srt'

            # 文件大小、下载次数、发布时间
            spans = re.findall(r"<span class=['\"]align-text-top me-3['\"]>([^<]+)</span>", block)
            if len(spans) >= 1:
                item['size'] = spans[0].strip()
            if len(spans) >= 2:
                try:
                    item['download_count'] = int(spans[1].strip() or '0')
                except ValueError:
                    item['download_count'] = 0
            else:
                item['download_count'] = 0
            if len(spans) >= 3:
                item['add_date'] = spans[2].strip()

            # 发布人
            m = re.search(r"发布人 <a class=\"fw-bold text-dark\" href='/u/([^']+)'", block)
            item['uploader'] = m.group(1).strip() if m else ''

            # 评分：用下载次数估算（SubHD 没有评分系统）
            item['score'] = float(item['download_count']) / 100.0

            items.append(item)

        return items

    @staticmethod
    def _normalize_subhd_language(lang_text: str) -> str:
        """将 SubHD 的语言文本规范化为 OpenSubtitles 风格的语言代码"""
        if not lang_text:
            return ''
        codes = []
        if '简体' in lang_text or '简中' in lang_text:
            codes.append('chi')
        if '繁体' in lang_text or '繁中' in lang_text:
            codes.append('cht')
        if '英语' in lang_text or 'English' in lang_text:
            codes.append('eng')
        if '双语' in lang_text:
            codes = ['chi', 'eng']
        if '日语' in lang_text or 'Japanese' in lang_text:
            codes.append('jpn')
        return ','.join(codes) if codes else ''

    @staticmethod
    def _filter_subhd_by_language(items: list, language: str) -> list:
        """按语言过滤 SubHD 搜索结果"""
        # language 可能是 'eng'、'chi'、'eng,chi,jpn' 等
        lang_codes = [c.strip() for c in language.split(',') if c.strip()]
        keywords = []
        for code in lang_codes:
            keywords.extend(LANG_KEYWORDS.get(code, []))
        if not keywords:
            return items  # 无匹配关键词，不过滤

        filtered = []
        for item in items:
            item_lang = item.get('language', '')
            if any(kw in item_lang for kw in keywords):
                filtered.append(item)
        return filtered

    # ==================== SubtitleCat 实现 ====================
    def _search_subtitlecat(self, query: str, language: str) -> tuple:
        """SubtitleCat 搜索（爬虫 subtitlecat.com）

        Args:
            query: 搜索关键词（片名）
            language: 语言代码（eng/chi/jpn/all）

        Returns:
            (items, error_message)
        """
        if not query:
            return [], ''
        try:
            # 提取纯片名（与 SubHD 共用提取逻辑）
            search_query = self._extract_title_from_query(query)
            if not search_query:
                return [], ''

            url = f"{SUBCAT_BASE_URL}/?search={urllib.parse.quote(search_query)}"
            html = self._fetch_html_subtitlecat(url)
            items = self._parse_subtitlecat_search_results(html)

            # SubtitleCat 搜索结果不显示具体语言，无法在搜索时按语言过滤
            # 下载时会根据 language 参数选 .srt 链接
            # 限制返回数量，避免过多结果
            items = items[:30]

            logger.info(f"SubtitleCat 搜索 '{search_query}' 返回 {len(items)} 条结果")
            return items, ''
        except urllib.error.HTTPError as e:
            return [], f'SubtitleCat HTTP {e.code}'
        except (socket.timeout, TimeoutError):
            return [], f'SubtitleCat 搜索超时（{DEFAULT_TIMEOUT}s）'
        except Exception as e:
            return [], f'SubtitleCat 搜索异常: {type(e).__name__}: {e}'

    @staticmethod
    def _fetch_html_subtitlecat(url: str) -> str:
        """获取 SubtitleCat HTML 内容（模拟浏览器请求）"""
        headers = {
            'User-Agent': SUBCAT_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        req = urllib.request.Request(url, headers=headers)
        with _urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.read().decode('utf-8', errors='ignore')

    @staticmethod
    def _parse_subtitlecat_search_results(html: str) -> list:
        """解析 SubtitleCat 搜索结果页面

        HTML 结构（每项）：
        <tr>
          <td><a href="subs/{id}/{title}.html">{title}</a> (translated from X)</td>
          <td>&nbsp;</td>
          <td class="sub-table__size-cell">...SIZE...{size}...</td>
          <td>{downloads} downloads</td>
          <td>{languages} languages</td>
        </tr>
        """
        items = []
        # 匹配搜索结果行：<a href="subs/{id}/{title}.html">{title}</a>
        # 注意：跳过表头行（th colspan="2"）
        rows = re.findall(
            r'<td><a href="subs/([^/]+)/([^"]+)\.html">([^<]+)</a>\s*(?:\(([^)]+)\))?</td>'
            r'\s*<td>&nbsp;</td>'
            r'\s*<td class="sub-table__size-cell">.*?<span class="sub-table__metric-value">([^<]+)</span></td>'
            r'\s*<td>([^<]+)</td>'
            r'\s*<td>([^<]+)</td>',
            html, re.DOTALL
        )
        for sub_id, title_slug, title, translated_from, size, downloads_str, languages_str in rows:
            try:
                download_count = int(re.search(r'\d+', downloads_str).group()) if re.search(r'\d+', downloads_str) else 0
            except (ValueError, AttributeError):
                download_count = 0
            try:
                lang_count = int(re.search(r'\d+', languages_str).group()) if re.search(r'\d+', languages_str) else 0
            except (ValueError, AttributeError):
                lang_count = 0

            item = {
                'source': 'SubtitleCat',
                'id': sub_id,
                'title': title.strip(),
                'detail_url': f"{SUBCAT_BASE_URL}/subs/{sub_id}/{title_slug}.html",
                'download_link': f"{SUBCAT_BASE_URL}/subs/{sub_id}/{title_slug}.html",  # 详情页 URL，下载时解析
                'movie_name': title.strip(),
                'file_name': title.strip(),
                'language': translated_from.strip() if translated_from else '',
                'language_id': '',
                'format': 'srt',
                'encoding': 'UTF-8',
                'size': size.strip(),
                'download_count': download_count,
                'languages_count': lang_count,
                'auto_download': True,  # SubtitleCat 支持自动下载（需 fetch 详情页解析直链）
                'bad': False,
                'rating': 0,
                # 评分：下载次数 + 语言数（语言多说明翻译质量好）
                'score': float(download_count) / 50.0 + float(lang_count) / 10.0,
            }
            items.append(item)

        return items

    def _download_subtitlecat(self, detail_url: str, dest_dir: str,
                              file_name: str, language: str) -> str:
        """下载 SubtitleCat 字幕

        流程：fetch 详情页 → 按 language 解析所有 .srt 直链 → 依次尝试下载
        （部分链接可能 404，需逐一尝试直到下载到有效内容）
        """
        try:
            html = self._fetch_html_subtitlecat(detail_url)
            srt_urls = self._parse_subtitlecat_srt_links(html, language)
            if not srt_urls:
                self.last_error = f'SubtitleCat 详情页未找到匹配语言的 .srt 链接（language={language}）'
                logger.warning(self.last_error + f' url={detail_url}')
                return ''

            os.makedirs(dest_dir, exist_ok=True)
            fname = _safe_subtitle_name(file_name or 'subtitle.srt', 'subtitle.srt')
            if not fname.endswith('.srt'):
                fname += '.srt'
            final_path = _ensure_inside(os.path.join(dest_dir, fname), dest_dir)

            # 依次尝试下载，直到获得有效 .srt 内容（非 HTML 404 页面）
            for srt_url in srt_urls:
                try:
                    srt_url = _validate_remote_url(srt_url)
                    req = urllib.request.Request(srt_url, headers={'User-Agent': SUBCAT_UA})
                    with _urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                        content = resp.read()
                    # 检查是否是 HTML 404 页面（SubtitleCat 返回 200 + HTML 404 内容）
                    if self._is_valid_srt_content(content):
                        with open(final_path, 'wb') as f:
                            f.write(content)
                        return final_path
                    logger.debug(f'SubtitleCat .srt 链接返回无效内容: {srt_url}')
                except Exception as e:
                    logger.debug(f'SubtitleCat 下载失败 {srt_url}: {e}')
                    continue

            self.last_error = 'SubtitleCat 所有 .srt 链接均下载失败（可能字幕已被删除）'
            logger.warning(self.last_error + f' url={detail_url}')
            return ''
        except Exception as e:
            self.last_error = f'下载 SubtitleCat 字幕失败: {type(e).__name__}: {e}'
            logger.warning(self.last_error)
            return ''

    @staticmethod
    def _is_valid_srt_content(content: bytes) -> bool:
        """检查下载内容是否是有效的 .srt 字幕（而非 HTML 404 页面）"""
        if not content or len(content) < 50:
            return False
        # HTML 404 页面特征：以 <html 或 <!DOCTYPE 开头
        head = content[:200].lstrip().lower()
        if head.startswith(b'<html') or head.startswith(b'<!doctype') or head.startswith(b'<!doctype html'):
            return False
        # .srt 文件特征：包含时间轴格式 00:00:00,000 --> 00:00:00,000
        # 或者是 UTF-8/GBK 编码的文本（非 HTML）
        try:
            text = content.decode('utf-8', errors='ignore')
        except Exception:
            text = ''
        if '-->' in text:
            return True
        # 没有 --> 但也不是 HTML，且内容较短，可能是空字幕
        if len(content) < 200 and '<' not in text[:100]:
            return True
        return False

    @staticmethod
    def _parse_subtitlecat_srt_links(html: str, language: str) -> list:
        """从 SubtitleCat 详情页 HTML 解析所有 .srt 下载链接（按语言优先级排序）

        详情页 .srt 链接格式：/subs/{file_id}/{title}-{lang_code}.srt
        其中 lang_code 如 zh-CN, zh-TW, en, ja 等

        根据 language 参数（eng/chi/jpn/all）选择对应语言的链接，按优先级排序。
        language='all' 时优先返回 zh-CN（简体中文）。
        返回完整 URL 列表，下载时依次尝试。
        """
        # 收集所有 .srt 链接
        srt_links = re.findall(r'href="(/subs/[^"]+\.srt)"', html)
        if not srt_links:
            return []

        # 构造完整 URL（对路径进行 URL 编码，避免空格导致 InvalidURL）
        # safe='/' 保留路径分隔符，'=%' 保留已编码字符
        full_links = []
        for link in srt_links:
            if link.startswith('/'):
                encoded_path = urllib.parse.quote(link, safe='/%')
                full_links.append(SUBCAT_BASE_URL + encoded_path)
            else:
                full_links.append(link)

        # 解析 language 参数，确定目标语言代码及优先级
        lang_codes = [c.strip() for c in (language or '').split(',') if c.strip()]
        if not lang_codes or 'all' in lang_codes:
            # 不限语言，优先返回中文（zh-CN > zh-TW > en > 其他）
            priority = ['zh-CN', 'zh-TW', 'en', 'ja', 'ko']
        else:
            # 按 language 参数的顺序构造优先级
            priority = []
            for code in lang_codes:
                priority.extend(SUBCAT_LANG_MAP.get(code, []))
            # 补充其他语言作为回退
            for lang in ['zh-CN', 'zh-TW', 'en', 'ja', 'ko']:
                if lang not in priority:
                    priority.append(lang)

        # 按优先级收集链接
        result = []
        for lang in priority:
            for link in full_links:
                if f'-{lang}.srt' in link and link not in result:
                    result.append(link)
        # 补充其他未分类的链接
        for link in full_links:
            if link not in result:
                result.append(link)
        return result


def _unpack_qword(buf: bytes):
    import struct
    return struct.unpack('<Q', buf)
