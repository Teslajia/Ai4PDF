"""Run the real update helper and isolated test installer, preserving a library."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


def main():
    executable, home, library, installer = [Path(arg).resolve() for arg in sys.argv[1:]]
    for path in (executable, home, library, installer):
        assert path.is_relative_to(ROOT / 'tmp'), 'Only isolated test installations are allowed'
    assert installer.name == 'Ai4PDF-installer-test.exe'
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in library.rglob('*') if path.is_file()}
    pointer = home / 'library-location.json'
    pointer_bytes = pointer.read_bytes()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        with opener.open(f'http://127.0.0.1:{port}' + path, timeout=1) as response:
            return json.load(response)
    environment = dict(os.environ, AI4PDF_HOME=str(home), PYINSTALLER_RESET_ENVIRONMENT='1')
    environment.pop('AI4PDF_DATA', None)
    environment.pop('PAPERDESK_DATA', None)
    parent = subprocess.Popen([str(executable), '--port', str(port), '--no-tray', '--no-browser'], env=environment)
    helper = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                assert get('/api/health')['application'] == 'Ai4PDF'
                break
            except (OSError, ValueError):
                time.sleep(.1)
        else:
            raise RuntimeError('Test app did not start')
        ready = installer.parent / 'update-ready'
        helper = subprocess.Popen([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'packaging/apply-update.ps1'), '-ParentId', str(parent.pid),
            '-Installer', str(installer), '-ExpectedHash', hashlib.sha256(installer.read_bytes()).hexdigest(),
            '-InstallDir', str(executable.parent), '-Port', str(port), '-ReadyFile', str(ready)], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 15
        while not ready.exists() and helper.poll() is None and time.monotonic() < deadline:
            time.sleep(.1)
        assert ready.exists(), 'Update helper did not become ready'
        # Close only our isolated child; the helper must wait before running Setup.
        parent.terminate()
        parent.wait(timeout=10)
        stdout, stderr = helper.communicate(timeout=180)
        assert helper.returncode == 0, (stdout, stderr)
        assert json.loads((installer.parent / 'result.json').read_text())['status'] == 'completed'
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                assert Path(get('/api/library/storage')['path']) == library
                break
            except (OSError, ValueError):
                time.sleep(.2)
        else:
            raise RuntimeError('Updated app did not restart on the original port')
        assert pointer.read_bytes() == pointer_bytes
        assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before} == before
        print('PASS: real update helper installs in place, restarts on the same port, preserves selected library and all existing file hashes')
    finally:
        for process in (parent, helper):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        # The helper spawned this copy; stop only the executable under this test root.
        cleanup = installer.parent / 'close-test-app.ps1'
        cleanup.write_text("param($Executable)\nGet-Process Ai4PDF -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $Executable } | Stop-Process\n", encoding='utf-8')
        subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(cleanup), str(executable)], capture_output=True, timeout=10)


if __name__ == '__main__':
    main()
