#!/usr/bin/env python3
"""
GuangYu - 独立 Web 服务器模式
无需 GUI，直接启动 Web 服务器，提供 RESTful API 和移动端 Web UI
支持 Windows/macOS/Linux 桌面端和 Android (Chaquopy) 环境
"""

import asyncio
import importlib
import logging
import os
import sys
import signal

from aiohttp import web


def _is_android():
    return getattr(sys, 'platform', '') == 'android' or 'ANDROID_ARGUMENT' in os.environ


def _setup_android_env():
    if not _is_android():
        return
    try:
        Python = importlib.import_module('chaquopy.python').Python
        app = Python.getPlatform().getApplication()
        files_dir = app.getFilesDir().getAbsolutePath()
        os.environ.setdefault('IPTV_DATA_DIR', files_dir)
        # 使用统一辅助函数获取 ISEP 目录（兜底处理）
        from utils.platform_utils import get_android_data_dir
        config_dir = get_android_data_dir() or os.path.join(files_dir, 'ISEP')
        os.makedirs(config_dir, exist_ok=True)
        os.chdir(config_dir)
    except Exception as e:
        logging.getLogger('server_main').warning(f'_setup_android_env 失败: {e}')


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('server_main')


def _get_mobile_dir():
    """返回移动端静态目录，不存在时返回空串"""
    base = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(base, 'server', 'mobile'), os.path.join(base, 'mobile')):
        if os.path.isdir(candidate):
            return candidate
    return ''


def _get_admin_dir():
    """返回管理面板静态目录，不存在时返回空串"""
    admin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server', 'admin')
    return admin_dir if os.path.isdir(admin_dir) else ''


def create_standalone_app():
    from server.context import ServerContext
    from server.routes import create_app

    ServerContext.get_instance(main_window=None)
    app = create_app()

    mobile_dir = _get_mobile_dir()
    if mobile_dir:
        app.router.add_static('/mobile', mobile_dir, name='mobile')

    return app


async def main(host='127.0.0.1', port=8080):
    if _is_android():
        host = '127.0.0.1'

    app = create_standalone_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"IPTV Web Server 启动于 http://{host}:{port}")
    # 仅在移动端静态目录存在时才提示 /mobile/，否则打印实际可用的入口
    if _get_mobile_dir():
        logger.info(f"移动端访问: http://{host}:{port}/mobile/")
    elif _get_admin_dir():
        logger.info(f"管理面板入口: http://{host}:{port}/admin/")
    else:
        logger.info(f"Web 入口: http://{host}:{port}/")
    logger.info(f"API 文档: http://{host}:{port}/")

    stop_event = asyncio.Event()

    def _signal_handler():
        stop_event.set()

    if sys.platform != 'win32' and not _is_android():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("正在停止服务器...")
        await runner.cleanup()


if __name__ == '__main__':
    _setup_android_env()

    from utils.crash_handler import install_crash_handler
    from utils.app_paths import migrate_legacy_data
    install_crash_handler()
    migrate_legacy_data()

    import argparse
    parser = argparse.ArgumentParser(description='GuangYu - Web Server')
    parser.add_argument('--host', default='127.0.0.1',
                        help='监听地址 (默认: 127.0.0.1，局域网访问请用 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='监听端口 (默认: 8080)')
    args = parser.parse_args()

    try:
        asyncio.run(main(host=args.host, port=args.port))
    except KeyboardInterrupt:
        logger.info("服务器已停止")
