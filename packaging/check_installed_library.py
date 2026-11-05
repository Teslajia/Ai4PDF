"""Verify an installed EXE uses the installer-selected library, with test data only."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests

root = Path(__file__).resolve().parents[1]
executable, home, library = [Path(value).resolve() for value in sys.argv[1:4]]
assert home.is_relative_to(root / 'tmp') and library.is_relative_to(root / 'tmp')
env = dict(os.environ, AI4PDF_HOME=str(home))
env.pop('AI4PDF_DATA', None)
env.pop('PAPERDESK_DATA', None)
with socket.socket() as socket_probe:
    socket_probe.bind(('127.0.0.1', 0))
    port = socket_probe.getsockname()[1]
url = f'http://127.0.0.1:{port}'
session = requests.Session()
session.trust_env = False
process = subprocess.Popen([str(executable), '--no-tray', '--no-browser', '--port', str(port)],
                           env=env, creationflags=subprocess.CREATE_NO_WINDOW)
try:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        assert process.poll() is None, 'Installed app exited before startup'
        try:
            result = session.get(url + '/api/library/storage', timeout=.5)
            if result.ok:
                break
        except requests.RequestException:
            pass
        time.sleep(.1)
    else:
        raise AssertionError('Startup timed out')
    assert Path(result.json()['path']).resolve() == library, result.json()
    sample = (root / 'static/sample.pdf').read_bytes()
    result = session.post(url + '/api/documents', files={'file': ('sample.pdf', sample, 'application/pdf')}, timeout=30)
    assert result.status_code == 200, result.text
    assert (library / result.json()['id'] / 'original.pdf').read_bytes() == sample
    print('PASS: installed app reads the selected library and writes imported PDFs there')
finally:
    process.terminate()
    process.wait(timeout=15)
    session.close()
