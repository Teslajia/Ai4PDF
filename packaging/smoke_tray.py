"""Check the frozen Windows tray loop and graceful shutdown in an isolated profile."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import requests

root = Path(__file__).resolve().parents[1]
user32 = ctypes.WinDLL('user32', use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def tray_windows(pid):
    found = []

    @callback_type
    def visit(window, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid:
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(window, name, len(name))
            if name.value.startswith('Ai4PDF') and name.value.endswith('SystemTrayIcon'):
                found.append(window)
        return True
    user32.EnumWindows(visit, 0)
    return found


def main(executable):
    with tempfile.TemporaryDirectory(prefix='tray-smoke-', dir=root / 'tmp') as directory:
        env = dict(os.environ, AI4PDF_HOME=directory)
        for name in ('AI4PDF_DATA', 'PAPERDESK_DATA'):
            env.pop(name, None)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        process = subprocess.Popen([str(Path(executable).resolve()), '--no-browser', '--port', str(port)],
                                   env=env, cwd=directory, creationflags=subprocess.CREATE_NO_WINDOW)
        session = requests.Session()
        session.trust_env = False
        try:
            deadline = time.monotonic() + 45
            windows = []
            while time.monotonic() < deadline:
                assert process.poll() is None, 'Tray process exited unexpectedly'
                windows = tray_windows(process.pid)
                if len(windows) >= 2:
                    break
                time.sleep(.2)
            assert len(windows) >= 2, 'Native tray and menu windows not created'
            assert session.get(f'http://127.0.0.1:{port}/api/health', timeout=10).ok
            # WM_USER + 10 is pystray's native stop message. This uses the same
            # cleanup path as the Quit menu, without interacting with user dialogs.
            for window in windows:
                user32.PostMessageW(window, 0x400 + 10, 0, 0)
            assert process.wait(timeout=25) == 0
            with socket.socket() as probe:
                assert probe.connect_ex(('127.0.0.1', port)) != 0, 'Service still listening after tray exit'
            print('PASS: native tray creation and graceful shutdown release the local service')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            session.close()


if __name__ == '__main__':
    main(sys.argv[1])
