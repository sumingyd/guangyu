import asyncio
import errno
import logging
import threading
import time
from typing import Optional

from aiohttp import web

logger = logging.getLogger('server')

_main_window_ref = None
# 退出流程中置位：新请求一律快速拒绝，避免与主线程销毁 mpv/窗口并发
_shutting_down = False


def is_shutting_down() -> bool:
    return _shutting_down


def set_main_window(main_window):
    global _main_window_ref
    _main_window_ref = main_window
    from server.context import ServerContext
    ServerContext.get_instance(main_window)


def get_main_window():
    return _main_window_ref


def get_context():
    from server.context import ServerContext
    return ServerContext.get_instance(_main_window_ref)


def get_channel_model():
    ctx = get_context()
    return ctx.get_channel_model() if ctx else None


def get_config():
    ctx = get_context()
    return ctx.get_config() if ctx else None


def get_language_manager():
    mw = get_main_window()
    if mw and hasattr(mw, 'language_manager'):
        return mw.language_manager
    return None


def _is_address_in_use(exc: OSError) -> bool:
    """端口被占用：Windows 是 WSAEADDRINUSE(10048)，类 Unix 是 EADDRINUSE(98)。"""
    return getattr(exc, 'errno', None) in (errno.EADDRINUSE, 10048) or \
        getattr(exc, 'winerror', None) == 10048


class IPTVServer:
    # 允许从起始端口向后顺延的次数（8080 -> 8099）
    MAX_PORT_SHIFT = 20

    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        # 用户/配置里指定的端口，用于提示「端口被占用后顺延到了哪个」
        self.requested_port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._start_time = 0.0
        self._started_event = threading.Event()
        self._start_error = ''

    def start(self):
        global _shutting_down
        if self._running:
            logger.warning("Server已在运行中")
            return
        _shutting_down = False
        self._thread = threading.Thread(target=self._run_loop, name="IPTVServer", daemon=True)
        self._thread.start()
        self._running = True
        self._start_time = time.time()
        logger.info(f"IPTV Server 正在启动: http://{self.host}:{self.port}")

    def stop(self):
        global _shutting_down
        if not self._running:
            _shutting_down = True
            return
        _shutting_down = True
        self._running = False
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
            except RuntimeError:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self.app = None
        self.runner = None
        self.site = None
        self._loop = None
        logger.info("IPTV Server 已停止")

    def is_running(self):
        return self._running

    def wait_started(self, timeout: float = 2.0) -> bool:
        """等待端口真正绑定完成，返回是否启动成功。

        start() 只是拉起后台线程，绑定失败（例如端口被另一个实例占用）时
        _running 会在后台被置回 False，调用方必须等这个事件才能给出准确提示。
        """
        if not self._started_event.wait(timeout):
            return False
        return self._running and not self._start_error

    @property
    def start_error(self) -> str:
        return self._start_error

    def get_uptime(self):
        if self._start_time > 0:
            return int(time.time() - self._start_time)
        return 0

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        def _safe_async_exception_handler(loop, context):
            msg = context.get('message', 'Asyncio异常')
            exception = context.get('exception')
            if exception is not None:
                logger.error("Asyncio: %s: %s", msg, exception, exc_info=False)
            else:
                logger.error("Asyncio: %s", msg)

        self._loop.set_exception_handler(_safe_async_exception_handler)
        try:
            self._loop.run_until_complete(self._async_start())
            self._running = True
            self._started_event.set()
            logger.info(f"IPTV Server 已启动: http://{self.host}:{self.port}")
            self._loop.run_forever()
        except Exception as e:
            self._start_error = str(e)
            logger.error(f"Server运行异常: {e}", exc_info=False)
            self._started_event.set()
        finally:
            self._running = False
            try:
                self._loop.close()
            except Exception:
                pass

    async def _async_start(self):
        from server.routes import create_app
        self.app = create_app()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        try:
            await self._bind_site()
        except Exception:
            # 绑定失败时把已 setup 的 runner 收掉，避免下一次启动留下半初始化状态
            try:
                await self.runner.cleanup()
            except Exception:
                pass
            raise

    async def _bind_site(self):
        """从配置端口开始向后找可用端口，命中后把实际端口写回 self.port。

        多开时第二个实例的配置端口通常已被第一个实例占用；这里直接顺延，
        而不是让服务起不来或误报「已启动」。
        """
        requested = self.requested_port
        last_error = None
        for offset in range(self.MAX_PORT_SHIFT + 1):
            candidate = requested + offset
            if candidate > 65535:
                break
            site = web.TCPSite(self.runner, self.host, candidate)
            try:
                await site.start()
            except OSError as e:
                if not _is_address_in_use(e):
                    raise
                last_error = e
                logger.warning(f"端口 {candidate} 已被占用，尝试 {candidate + 1}")
                continue
            self.site = site
            self.port = candidate
            if candidate != requested:
                logger.info(
                    f"端口 {requested} 已被占用，服务改用 {candidate}（http://{self.host}:{candidate}）")
            return
        raise last_error or OSError(
            f"从 {requested} 起连续 {self.MAX_PORT_SHIFT + 1} 个端口均被占用")

    async def _async_stop(self):
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            # 关闭共享的流代理 ClientSession
            from server import routes as _routes
            session = _routes._stream_session
            if session and not session.closed:
                await session.close()
            _routes._stream_session = None
        except Exception as e:
            logger.error(f"Server停止异常: {e}", exc_info=True)
        finally:
            if self._loop and self._loop.is_running():
                self._loop.call_soon(self._loop.stop)


_server_instance: Optional[IPTVServer] = None
_server_lock = threading.Lock()


def get_server() -> IPTVServer:
    global _server_instance
    with _server_lock:
        if _server_instance is None:
            _server_instance = IPTVServer()
        return _server_instance


def start_server(host='0.0.0.0', port=8080):
    global _server_instance
    with _server_lock:
        if _server_instance and _server_instance.is_running():
            return _server_instance
        _server_instance = IPTVServer(host=host, port=port)
        _server_instance.start()
        return _server_instance


def stop_server():
    global _server_instance
    if _server_instance:
        _server_instance.stop()
        _server_instance = None