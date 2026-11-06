import os
import hashlib
import time
import json
import threading
from collections import OrderedDict
from PySide6.QtCore import Signal, QUrl, QTimer, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QApplication
from utils.thread_safety import ThreadSafeQObject
from core.log_manager import global_logger as logger


class LogoCacheService(ThreadSafeQObject):
    logo_loaded = Signal(str, QPixmap)

    CACHE_DIR_NAME = 'logo_cache'
    META_FILE = 'meta.json'
    DEFAULT_TTL = 7 * 24 * 3600
    MAX_CACHE_SIZE = 500
    NEGATIVE_CACHE_TTL = 3600
    MIN_IMAGE_DATA_SIZE = 100
    SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')

    @staticmethod
    def scale_logo_pixmap(pixmap, size=60):
        if pixmap.isNull():
            return pixmap

        screen = QApplication.primaryScreen()
        if screen:
            device_pixel_ratio = screen.devicePixelRatio()
        else:
            device_pixel_ratio = 1.0

        target_size = int(size * device_pixel_ratio)
        scaled = pixmap.scaled(target_size, target_size,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(device_pixel_ratio)

        return scaled

    @staticmethod
    def scale_logo_pixmap_to_fit(pixmap, width, height):
        if pixmap.isNull():
            return pixmap

        screen = QApplication.primaryScreen()
        if screen:
            device_pixel_ratio = screen.devicePixelRatio()
        else:
            device_pixel_ratio = 1.0

        target_w = int(width * device_pixel_ratio)
        target_h = int(height * device_pixel_ratio)
        scaled = pixmap.scaled(target_w, target_h,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(device_pixel_ratio)

        return scaled

    def __init__(self, parent=None):
        super().__init__(parent)
        from models.channel_mappings import get_app_data_dir
        app_dir = get_app_data_dir()
        self._cache_dir = os.path.join(app_dir, self.CACHE_DIR_NAME)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._meta_path = os.path.join(self._cache_dir, self.META_FILE)
        self._meta = self._load_meta()
        self._image_cache = OrderedDict()
        self._negative_cache = {}
        self._lock = threading.Lock()
        self._network_manager = QNetworkAccessManager(self)
        self._pending_replies = {}
        self._warmup_queue = []
        self._warmup_timer = QTimer(self)
        self._warmup_timer.setInterval(100)
        self._warmup_timer.timeout.connect(self._process_warmup_queue)
        self._migrate_old_cache()

    def _load_meta(self):
        try:
            if os.path.exists(self._meta_path):
                with open(self._meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"加载台标元数据失败: {e}")
        return {}

    def _save_meta(self):
        """原子写入元数据，避免中断/磁盘满导致 meta.json 损坏后缓存被整体误删"""
        import tempfile
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._cache_dir, suffix='.tmp', prefix='meta.')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(self._meta, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._meta_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.debug(f"保存台标元数据失败: {e}")

    def _cached_at(self, meta_entry, disk_path):
        """获取缓存时间；meta 缺少 time 时回退到文件修改时间，避免把有效缓存误判为过期"""
        cached_at = meta_entry.get('time', 0) or 0
        if cached_at > 0:
            return cached_at
        try:
            return os.path.getmtime(disk_path)
        except OSError:
            return 0

    def _url_to_key(self, url):
        return hashlib.sha1(url.encode('utf-8')).hexdigest()

    def _guess_ext_from_url(self, url):
        from urllib.parse import urlparse, unquote
        path = unquote(urlparse(url).path).lower()
        for ext in self.SUPPORTED_EXTENSIONS:
            if path.endswith(ext):
                return ext
        return '.png'

    def _ext_from_content_type(self, content_type):
        if not content_type or not isinstance(content_type, str):
            return None
        ct = content_type.lower()
        if 'png' in ct:
            return '.png'
        if 'jpeg' in ct or 'jpg' in ct:
            return '.jpg'
        if 'gif' in ct:
            return '.gif'
        if 'webp' in ct:
            return '.webp'
        if 'bmp' in ct:
            return '.bmp'
        if 'svg' in ct:
            return '.svg'
        if 'ico' in ct or 'icon' in ct:
            return '.ico'
        return None

    def _disk_path(self, key, ext='.png'):
        return os.path.join(self._cache_dir, key + ext)

    def _find_disk_path(self, key):
        if key in self._meta:
            ext = self._meta[key].get('ext', '.png')
            path = self._disk_path(key, ext)
            if os.path.exists(path):
                return path
        for ext in self.SUPPORTED_EXTENSIONS:
            path = self._disk_path(key, ext)
            if os.path.exists(path):
                return path
        path = self._disk_path(key, '')
        if os.path.exists(path):
            return path
        return None

    def _migrate_old_cache(self):
        try:
            migrated = False
            for key, meta in list(self._meta.items()):
                if 'ext' not in meta:
                    old_path = self._disk_path(key, '')
                    if os.path.exists(old_path):
                        ext = '.' + meta.get('format', 'png') if 'format' in meta else '.png'
                        new_path = self._disk_path(key, ext)
                        os.rename(old_path, new_path)
                        meta['ext'] = ext
                        migrated = True
                    else:
                        found = self._find_disk_path(key)
                        if found:
                            ext = os.path.splitext(found)[1]
                            meta['ext'] = ext if ext else '.png'
                            migrated = True
                        else:
                            ext = self._guess_ext_from_url(meta.get('url', ''))
                            meta['ext'] = ext
                            migrated = True
            if migrated:
                self._save_meta()
        except Exception as e:
            logger.debug(f"迁移台标缓存失败: {e}")

    @staticmethod
    def _image_to_pixmap(image):
        if image is None or image.isNull():
            return QPixmap()
        return QPixmap.fromImage(image)

    def get(self, url):
        if not url:
            return None
        with self._lock:
            if url in self._negative_cache:
                neg_time = self._negative_cache[url]
                if time.time() - neg_time < self.NEGATIVE_CACHE_TTL:
                    return None
                del self._negative_cache[url]
            if url in self._image_cache:
                self._image_cache.move_to_end(url)
                return self._image_to_pixmap(self._image_cache[url])

        key = self._url_to_key(url)
        disk_path = self._find_disk_path(key)

        if disk_path and os.path.exists(disk_path):
            meta_entry = self._meta.get(key, {})
            cached_at = self._cached_at(meta_entry, disk_path)
            if time.time() - cached_at > self.DEFAULT_TTL:
                try:
                    os.remove(disk_path)
                    self._meta.pop(key, None)
                    self._save_meta()
                except Exception as e:
                    logger.debug(f"淘汰过期台标失败: {e}")
                return None

            image = QImage()
            if image.load(disk_path):
                with self._lock:
                    self._image_cache[url] = image
                    self._image_cache.move_to_end(url)
                    while len(self._image_cache) > self.MAX_CACHE_SIZE:
                        self._image_cache.popitem(last=False)
                return self._image_to_pixmap(image)
        return None

    def get_image(self, url):
        if not url:
            return None
        with self._lock:
            if url in self._negative_cache:
                neg_time = self._negative_cache[url]
                if time.time() - neg_time < self.NEGATIVE_CACHE_TTL:
                    return None
                del self._negative_cache[url]
            if url in self._image_cache:
                self._image_cache.move_to_end(url)
                return QImage(self._image_cache[url])

        key = self._url_to_key(url)
        disk_path = self._find_disk_path(key)

        if disk_path and os.path.exists(disk_path):
            meta_entry = self._meta.get(key, {})
            cached_at = self._cached_at(meta_entry, disk_path)
            if time.time() - cached_at > self.DEFAULT_TTL:
                return None

            image = QImage()
            if image.load(disk_path):
                with self._lock:
                    self._image_cache[url] = image
                    self._image_cache.move_to_end(url)
                    while len(self._image_cache) > self.MAX_CACHE_SIZE:
                        self._image_cache.popitem(last=False)
                return QImage(image)
        return None

    def put(self, url, pixmap_or_image, ext='.png', content_hash=None):
        if not url:
            return

        if isinstance(pixmap_or_image, QPixmap):
            if pixmap_or_image.isNull():
                return
            image = pixmap_or_image.toImage()
        elif isinstance(pixmap_or_image, QImage):
            if pixmap_or_image.isNull():
                return
            image = pixmap_or_image
        else:
            return

        with self._lock:
            self._image_cache[url] = image
            self._image_cache.move_to_end(url)
            while len(self._image_cache) > self.MAX_CACHE_SIZE:
                self._image_cache.popitem(last=False)
        key = self._url_to_key(url)

        old_path = self._find_disk_path(key)
        new_ext = ext if ext else '.png'
        disk_path = self._disk_path(key, new_ext)

        try:
            if old_path and old_path != disk_path and os.path.exists(old_path):
                os.remove(old_path)
            fmt_map = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.gif': 'GIF', '.webp': 'WEBP', '.bmp': 'BMP'}
            save_fmt = fmt_map.get(new_ext.lower(), 'PNG')
            image.save(disk_path)
            meta_entry = {
                'url': url,
                'time': time.time(),
                'ext': new_ext,
            }
            if content_hash:
                meta_entry['content_hash'] = content_hash
            self._meta[key] = meta_entry
            self._save_meta()
        except Exception as e:
            logger.debug(f"缓存台标元数据失败: {e}")

    def mark_negative(self, url, reason=''):
        with self._lock:
            self._negative_cache[url] = time.time()
        if reason:
            logger.debug(f"台标标记为无效: {reason} | {url[:80]}")

    def fetch_async(self, url, force=False):
        if not url:
            return
        if not self._ensure_main_thread(self.fetch_async, url, force):
            return
        with self._lock:
            if url in self._negative_cache:
                if time.time() - self._negative_cache[url] < self.NEGATIVE_CACHE_TTL:
                    return
                del self._negative_cache[url]

        if not force:
            cached = self.get(url)
            if cached:
                self.logo_loaded.emit(url, cached)
                return

        with self._lock:
            if url in self._pending_replies:
                return

        self._start_download(url)

    def _start_download(self, url):
        try:
            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                              'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            try:
                request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                                     QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
            except Exception:
                pass
            # 设置传输超时，避免主机黑洞时请求永久挂起、该 URL 再也无法重试
            if hasattr(request, 'setTransferTimeout'):
                request.setTransferTimeout(10000)
            reply = self._network_manager.get(request)
            with self._lock:
                self._pending_replies[url] = reply
            reply.finished.connect(lambda: self._on_download_finished(url, reply))
        except Exception as ex:
            self.mark_negative(url, f"创建请求异常: {ex}")

    def _on_download_finished(self, url, reply):
        with self._lock:
            self._pending_replies.pop(url, None)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                err = reply.error()
                self.mark_negative(url, f"网络错误: {err}")
                return

            content_type = reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader)
            if content_type and isinstance(content_type, str):
                ct = content_type.lower()
                if 'text/' in ct or 'html' in ct or 'json' in ct:
                    self.mark_negative(url, f"非图片Content-Type: {ct}")
                    return

            data = reply.readAll()
            if not data or len(data) < self.MIN_IMAGE_DATA_SIZE:
                self.mark_negative(url, f"数据过小: {len(data) if data else 0}字节")
                return

            raw_data = data.data()
            content_hash = hashlib.md5(raw_data).hexdigest()

            key = self._url_to_key(url)
            meta_entry = self._meta.get(key, {})
            old_hash = meta_entry.get('content_hash')

            ext = self._ext_from_content_type(content_type)
            if not ext:
                ext = self._guess_ext_from_url(url)

            if old_hash and old_hash == content_hash:
                meta_entry['time'] = time.time()
                meta_entry['ext'] = ext
                self._meta[key] = meta_entry
                self._save_meta()
                return

            image = QImage()
            if image.loadFromData(raw_data):
                self.put(url, image, ext=ext, content_hash=content_hash)
                pixmap = self._image_to_pixmap(image)
                self.logo_loaded.emit(url, pixmap)
            else:
                self.mark_negative(url, f"QImage无法解析图片数据({len(raw_data)}字节)")
        except Exception as e:
            self.mark_negative(url, f"下载回调异常: {e}")
        finally:
            reply.deleteLater()

    def warmup(self, urls):
        if not urls:
            return
        if not self._ensure_main_thread(self.warmup, urls):
            return
        self._warmup_queue.extend(urls)
        if not self._warmup_timer.isActive():
            self._warmup_timer.start()

    def _process_warmup_queue(self):
        if not self._warmup_queue:
            self._warmup_timer.stop()
            return
        batch = 5
        for _ in range(batch):
            if not self._warmup_queue:
                break
            url = self._warmup_queue.pop(0)
            with self._lock:
                in_cache = url in self._image_cache or url in self._negative_cache
            if url and not in_cache:
                cached = self.get(url)
                if not cached:
                    self.fetch_async(url)

    def clear(self):
        with self._lock:
            self._image_cache.clear()
            self._negative_cache.clear()
        try:
            for f in os.listdir(self._cache_dir):
                fp = os.path.join(self._cache_dir, f)
                if os.path.isfile(fp):
                    os.remove(fp)
            self._meta.clear()
            self._save_meta()
        except Exception as e:
            logger.debug(f"清空台标缓存失败: {e}")

    def evict_expired(self):
        now = time.time()
        expired_keys = []
        for key, meta in list(self._meta.items()):
            disk_path = self._find_disk_path(key)
            cached_at = self._cached_at(meta, disk_path) if disk_path else (meta.get('time', 0) or 0)
            if now - cached_at > self.DEFAULT_TTL:
                expired_keys.append(key)
        for key in expired_keys:
            disk_path = self._find_disk_path(key)
            try:
                if disk_path and os.path.exists(disk_path):
                    os.remove(disk_path)
            except Exception as e:
                logger.debug(f"evict_expired: {e}")
            self._meta.pop(key, None)
        if expired_keys:
            self._save_meta()
