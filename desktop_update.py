"""Hand a verified installer to a helper outside the installation directory."""
from __future__ import annotations

import os
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import time

UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{C65AE3F2-8B1D-4DB1-9CA1-8E28116A449E}_is1'


def installed_directory():
    if not getattr(sys, 'frozen', False) or sys.platform != 'win32':
        return None
    import winreg
    actual = Path(sys.executable).resolve().parent
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                installed = Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve()
                if installed == actual:
                    return actual
        except OSError:
            pass
    return None


def handoff(installer, digest, directory, resource_root, port, stop):
    # The helper must survive PyInstaller resources being replaced by Setup.
    helper = installer.parent / 'apply-update.ps1'
    shutil.copyfile(resource_root / 'packaging' / 'apply-update.ps1', helper)
    ready = installer.parent / 'helper-ready'
    ready.unlink(missing_ok=True)
    powershell = Path(os.environ['SystemRoot']) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    command = [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
               '-File', str(helper), '-ParentId', str(os.getpid()), '-Installer', str(installer),
               '-ExpectedHash', digest, '-InstallDir', str(directory), '-Port', str(port), '-ReadyFile', str(ready)]
    environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    frozen = getattr(sys, 'frozen', False)
    if frozen:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   close_fds=True, cwd=str(installer.parent), env=environment)
    finally:
        if frozen:
            ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
    deadline = time.monotonic() + 15
    while not ready.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            raise RuntimeError('Update helper did not become ready')
        time.sleep(.1)
    # Let the HTTP response reach the browser before closing the local server.
    import threading
    threading.Timer(1, stop).start()
