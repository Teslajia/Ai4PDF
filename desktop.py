"""Windows desktop entry point: one instance, loopback WSGI server, tray controls."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from runtime_paths import configuration_root, instance_id
from version import VERSION

ROOT = Path(__file__).resolve().parent


class InstanceLock:
    def __init__(self, path):
        self.path = path
        self.handle = None

    def acquire(self):
        import msvcrt
        self.handle = open(self.path, 'a+b')
        self.handle.seek(0, os.SEEK_END)
        if not self.handle.tell():
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            self.handle.close()
            self.handle = None
            return False

    def close(self):
        if self.handle:
            import msvcrt
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close()
            self.handle = None


def healthy(url, identity):
    # Loopback requests must never go through HTTP_PROXY / a system proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/api/health', timeout=.5) as response:
            value = json.load(response)
            return value.get('application') == 'Ai4PDF' and value.get('instance') == identity
    except (OSError, ValueError, urllib.error.URLError):
        return False


def show_error(message, headless=False):
    logging.error(message)
    if not headless:
        ctypes.windll.user32.MessageBoxW(None, message, 'Ai4PDF · 启动失败 / Startup failed', 0x10)


def run(args):
    home = configuration_root(ROOT)
    home.mkdir(parents=True, exist_ok=True)
    logs = home / 'logs'
    logs.mkdir(exist_ok=True)
    handler = RotatingFileHandler(logs / 'desktop.log', maxBytes=1024 * 1024, backupCount=2, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(asctime)s %(levelname)s %(message)s')
    url = f'http://127.0.0.1:{args.port}'
    identity = instance_id(home)
    lock = InstanceLock(home / 'desktop.lock')
    if not lock.acquire():
        # A second click during startup waits for the first instance to become ready.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if healthy(url, identity):
                if not args.no_browser:
                    webbrowser.open(url)
                return 0
            time.sleep(.2)
        show_error('Ai4PDF 正在启动或使用其他端口，请稍后再试。\nAi4PDF is starting or is using another port.', args.no_tray)
        return 1
    server = None
    icon = None
    update_exit = threading.Event()
    try:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', args.port)) == 0:
                show_error(f'端口 {args.port} 已被使用，请先退出旧版 Ai4PDF 或占用此端口的程序。\nPort {args.port} is in use. Close the previous app, then try again.', args.no_tray)
                return 1
        from app import app, LOCK, updater
        from desktop_update import installed_directory, handoff
        directory = installed_directory()
        if directory:
            def stop_for_update():
                update_exit.set()
                if icon:
                    icon.stop()
            updater.launcher = lambda path, digest: handoff(path, digest, directory, ROOT, args.port, stop_for_update)
        from waitress import create_server
        server = create_server(app, host='127.0.0.1', port=args.port, threads=8,
                               max_request_body_size=110 * 1024 * 1024, channel_timeout=600)
        worker = threading.Thread(target=server.run, daemon=True, name='Ai4PDF HTTP')
        worker.start()
        deadline = time.monotonic() + 15
        while not healthy(url, identity):
            if time.monotonic() > deadline or not worker.is_alive():
                raise RuntimeError('Local server did not become ready')
            time.sleep(.1)
        logging.info('Ai4PDF %s ready on port %s', VERSION, args.port)
        if args.no_tray:
            if not args.no_browser:
                webbrowser.open(url)
            while worker.is_alive() and not update_exit.is_set():
                worker.join(.5)
        else:
            import pystray
            from PIL import Image

            def open_reader(*_):
                webbrowser.open(url)

            def exit_reader(tray, _):
                choice = ctypes.windll.user32.MessageBoxW(None,
                    '退出将停止本地服务。请先等待翻译和 AI 回答完成。\nQuit Ai4PDF? Wait for translations and AI replies to finish first.',
                    'Ai4PDF', 0x24)
                if choice == 6:
                    tray.stop()

            menu = pystray.Menu(
                pystray.MenuItem('打开 Ai4PDF / Open', open_reader, default=True),
                pystray.MenuItem('日志文件夹 / Logs', lambda *_: os.startfile(str(logs))),
                pystray.MenuItem('开源许可与源码 / Source & licenses', lambda *_: os.startfile(str(ROOT / 'legal' if (ROOT / 'legal').exists() else ROOT))),
                pystray.MenuItem('退出 / Quit', exit_reader))
            icon = pystray.Icon('Ai4PDF', Image.open(ROOT / 'static' / 'app-icon.png'), 'Ai4PDF · PDF_AI助手', menu)

            def ready(tray):
                tray.visible = True
                if not args.no_browser:
                    open_reader()
            icon.run(setup=ready)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        # Log exception types only; documents and API credentials do not belong in logs.
        logging.error('Startup failed: %s', type(exc).__name__)
        show_error('启动失败，请查看日志文件夹：\nStartup failed. See logs:\n' + str(logs), args.no_tray)
        return 1
    finally:
        if server:
            server.task_dispatcher.shutdown(timeout=15)
            # A library migration can outlive its HTTP request; let its atomic commit finish.
            from app import LOCK
            with LOCK:
                server.close()
        if icon:
            icon.stop()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description='Ai4PDF desktop launcher')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true', help='Do not open a browser automatically')
    parser.add_argument('--no-tray', action='store_true', help='Run without tray UI (for automated checks)')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
