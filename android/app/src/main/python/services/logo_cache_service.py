import os
import hashlib
import time
import json
import threading
from collections import OrderedDict
from PySide6.QtCore import Signal, QUrl, QTimer, Qt, QBuffer, QSize, QIODevice
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QPixmap, QImage, QImageReader
from PySide6.QtWidgets import QApplication
from utils.thread_safety import ThreadSafeQObject
from core.log_manager import global_logger as logger


class LogoCacheService(ThreadSafeQObject):
    logo_loaded = Signal(str, QPixmap)
    # 远程台标下载/解码失败（404、空数据、非图片等），供上层触发来源兜底
    logo_failed = Signal(str)

    CACHE_DIR_NAME = 'logo_cache'
    META_FILE = 'meta.json'
    DEFAULT_TTL = 7 * 24 * 3600
    MAX_CACHE_SIZE = 500
    NEGATIVE_CACHE_TTL = 3600
    MIN_IMAGE_DATA_SIZE = 100
    SUPPORTED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')
    # 按显示尺寸解码：尺寸键缓存与单图解码像素上限，避免 1080p 台标整图进内存
    SCALED_CACHE_MAX = 800
    MAX_DECODE_PIXELS = 2_000_000
    PREVIEW_MAX_PIXELS = 240_000

    @staticmethod
    def _device_pixel_ratio():
        screen = QApplication.primaryScreen()
        return screen.devicePixelRatio() if screen else 1.0

    @classmethod
    def _scaled_size(cls, source_w, source_h, width, height, max_pixels):
        """把源图等比缩进目标框，并受单图像素上限约束。"""
        dpr = cls._device_pixel_ratio()
        target_w = max(1, int(width * dpr))
        target_h = max(1, int(height * dpr))
        if source_w <= 0 or source_h <= 0:
            return target_w, target_h
        scale = min(target_w / source_w, target_h / source_h, 1.0)
        w = max(1, int(source_w * scale))
        h = max(1, int(source_h * scale))
        if max_pixels and w * h > max_pixels:
            factor = (max_pixels / float(w * h)) ** 0.5
            w = max(1, int(w * factor))
            h = max(1, int(h * factor))
        return w, h

    @classmethod
    def _read_image_reader(cls, reader, width, height, max_pixels):
        size = reader.size()
        if not size.isValid():
            image = reader.read()
            return image if not image.isNull() else None
        w, h = cls._scaled_size(size.width(), size.height(), width, height, max_pixels)
        if (w, h) != (size.width(), size.height()):
            reader.setScaledSize(QSize(w, h))
        image = reader.read()
        return image if not image.isNull() else None

    def _read_image_at_size(self, path, width, height, max_pixels=None):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        try:
            return self._read_image_reader(
                reader, width, height, max_pixels or self.MAX_DECODE_PIXELS)
        except Exception as e:
            logger.debug(f"按尺寸解码台标失败: {e}")
            return None

    def _read_image_from_bytes(self, raw_data, width, height, max_pixels=None):
        buffer = QBuffer()
        buffer.setData(raw_data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        try:
            reader = QImageReader(buffer)
            reader.setAutoTransform(True)
            return self._read_image_reader(
                reader, width, height, max_pixels or self.MAX_DECODE_PIXELS)
        except Exception as e:
            logger.debug(f"解码下载台标失败: {e}")
            return None
        finally:
            buffer.close()


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
        from utils.app_paths import get_cache_dir
        app_dir = get_cache_dir()
        self._cache_dir = os.path.join(app_dir, self.CACHE_DIR_NAME)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._meta_path = os.path.join(self._cache_dir, self.META_FILE)
        self._meta = self._load_meta()
        self._image_cache = OrderedDict()
        self._scaled_cache = OrderedDict()
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

    @staticmethod
    def _local_file_path(url):
        """台标地址本身就是本地文件（本地台标来源）时返回绝对路径，否则 None。"""
        if not url:
            return None
        path = url[7:] if str(url).lower().startswith('file://') else str(url)
        try:
            if os.path.isfile(path):
                return path
        except (OSError, ValueError):
            return None
        return None

    def _local_scaled(self, path, width, height, max_pixels=None):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cache_key = f'local|{path}|{mtime}|{int(width)}x{int(height)}'
        with self._lock:
            if cache_key in self._scaled_cache:
                self._scaled_cache.move_to_end(cache_key)
                return QPixmap(self._scaled_cache[cache_key])
        image = self._read_image_at_size(path, width, height, max_pixels)
        if image is None:
            return None
        pixmap = self._image_to_pixmap(image)
        pixmap.setDevicePixelRatio(self._device_pixel_ratio())
        with self._lock:
            self._scaled_cache[cache_key] = pixmap
            self._scaled_cache.move_to_end(cache_key)
            while len(self._scaled_cache) > self.SCALED_CACHE_MAX:
                self._scaled_cache.popitem(last=False)
        return QPixmap(pixmap)

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
        local_path = self._local_file_path(url)
        if local_path:
            image = self._read_image_at_size(
                local_path, 4096, 4096, self.MAX_DECODE_PIXELS)
            return self._image_to_pixmap(image) if image is not None else None
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

            image = self._read_image_at_size(
                disk_path, 4096, 4096, self.MAX_DECODE_PIXELS)
            if image is not None:
                with self._lock:
                    self._image_cache[url] = image
                    self._image_cache.move_to_end(url)
                    while len(self._image_cache) > self.MAX_CACHE_SIZE:
                        self._image_cache.popitem(last=False)
                return self._image_to_pixmap(image)
        return None

    def get_scaled(self, url, width, height=None):
        """按控件显示尺寸解码并缓存；同一 URL 的不同尺寸互不复用整图。"""
        if not url:
            return None
        width = max(1, int(width or 60))
        height = max(1, int(height or width))
        local_path = self._local_file_path(url)
        if local_path:
            return self._local_scaled(local_path, width, height)
        cache_key = f'{url}|{width}x{height}'
        with self._lock:
            if url in self._negative_cache:
                if time.time() - self._negative_cache[url] < self.NEGATIVE_CACHE_TTL:
                    return None
                del self._negative_cache[url]
            if cache_key in self._scaled_cache:
                self._scaled_cache.move_to_end(cache_key)
                return QPixmap(self._scaled_cache[cache_key])

        key = self._url_to_key(url)
        disk_path = self._find_disk_path(key)
        if not disk_path or not os.path.exists(disk_path):
            return None
        meta_entry = self._meta.get(key, {})
        cached_at = self._cached_at(meta_entry, disk_path)
        if time.time() - cached_at > self.DEFAULT_TTL:
            return None

        image = self._read_image_at_size(disk_path, width, height)
        if image is None:
            return None
        pixmap = self._image_to_pixmap(image)
        pixmap.setDevicePixelRatio(self._device_pixel_ratio())
        with self._lock:
            self._scaled_cache[cache_key] = pixmap
            self._scaled_cache.move_to_end(cache_key)
            while len(self._scaled_cache) > self.SCALED_CACHE_MAX:
                self._scaled_cache.popitem(last=False)
        return QPixmap(pixmap)

    def get_image(self, url):
        if not url:
            return None
        local_path = self._local_file_path(url)
        if local_path:
            image = QImage()
            return image if image.load(local_path) else None
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

    def _store_raw(self, url, raw_data, ext, content_hash):
        """把下载到的原始图片字节写盘；返回是否成功写入且可被 Qt 识别。"""
        key = self._url_to_key(url)
        new_ext = ext if ext else '.png'
        disk_path = self._disk_path(key, new_ext)
        old_path = self._find_disk_path(key)
        try:
            if old_path and old_path != disk_path and os.path.exists(old_path):
                os.remove(old_path)
            with open(disk_path, 'wb') as f:
                f.write(raw_data)
            self._meta[key] = {
                'url': url,
                'time': time.time(),
                'ext': new_ext,
                'content_hash': content_hash,
            }
            self._save_meta()
            with self._lock:
                self._image_cache.pop(url, None)
                for cache_key in [k for k in self._scaled_cache if k.startswith(url + '|')]:
                    self._scaled_cache.pop(cache_key, None)
            return self._read_image_at_size(disk_path, 64, 64, self.PREVIEW_MAX_PIXELS) is not None
        except Exception as e:
            logger.debug(f"保存台标原图失败: {e}")
            return False

    def mark_negative(self, url, reason=''):
        is_new = False
        with self._lock:
            is_new = url not in self._negative_cache
            self._negative_cache[url] = time.time()
        if reason:
            logger.debug(f"台标标记为无效: {reason} | {url[:80]}")
        if is_new and not self._local_file_path(url):
            self.logo_failed.emit(url)

    def fetch_async(self, url, force=False):
        if not url:
            return
        # 本地台标文件不需要下载，get_scaled/get 会直接读盘
        if self._local_file_path(url):
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
            # 台标等 GitHub 图片按「GitHub 加速代理」配置改写；缓存键仍用原始 URL
            from utils.github_proxy import rewrite_url
            request = QNetworkRequest(QUrl(rewrite_url(url)))
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

            # 直接落盘原始字节，避免下载时解码整图；显示时再按控件尺寸解码
            if self._store_raw(url, raw_data, ext, content_hash):
                preview = self._read_image_from_bytes(
                    raw_data, 320, 180, self.PREVIEW_MAX_PIXELS)
                if preview is not None:
                    with self._lock:
                        self._image_cache[url] = preview
                        self._image_cache.move_to_end(url)
                        while len(self._image_cache) > self.MAX_CACHE_SIZE:
                            self._image_cache.popitem(last=False)
                    self.logo_loaded.emit(url, self._image_to_pixmap(preview))
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
