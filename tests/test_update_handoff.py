import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows updater handoff')
@pytest.mark.parametrize('cancel', [False, True])
def test_helper_waits_for_old_process_and_preserves_launch_context(tmp_path, cancel):
    # Tiny local test executables just record argv; they never install software.
    home = tmp_path / "测试 App's folder & settings"
    home.mkdir()
    source = home / 'fake.cs'
    source.write_text('''using System; using System.IO; using System.Reflection;
class Fake { static int Main(string[] args) {
string exe = Assembly.GetExecutingAssembly().Location;
File.WriteAllLines(exe + ".args", args);
return File.Exists(exe + ".cancel") ? 5 : 0;
} }''', encoding='utf-8')
    compile_script = home / 'compile.ps1'
    compile_script.write_text("param($Source,$Output)\nAdd-Type -Path $Source -OutputAssembly $Output -OutputType ConsoleApplication\n", encoding='utf-8')
    installer = home / 'test-setup.exe'
    subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(compile_script), str(source), str(installer)], check=True, capture_output=True)
    program = home / 'Ai4PDF.exe'
    program.write_bytes(installer.read_bytes())
    if cancel:
        installer.with_suffix('.exe.cancel').touch()
    ready = home / 'ready'
    parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=subprocess.CREATE_NO_WINDOW)
    helper = None
    try:
        helper = subprocess.Popen([POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'packaging/apply-update.ps1'), '-ParentId', str(parent.pid),
            '-Installer', str(installer), '-ExpectedHash', hashlib.sha256(installer.read_bytes()).hexdigest(),
            '-InstallDir', str(home), '-Port', '48765', '-ReadyFile', str(ready)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 12
        while not ready.exists() and helper.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert ready.exists(), helper.communicate(timeout=3)
        assert not installer.with_suffix('.exe.args').exists()
        parent.terminate()
        parent.wait(timeout=5)
        stdout, stderr = helper.communicate(timeout=20)
        assert helper.returncode == 0, (stdout, stderr)
        argv = installer.with_suffix('.exe.args').read_text(encoding='utf-8-sig').splitlines()
        assert '/DIR=' + str(home) in argv
        assert '/NOCLOSEAPPLICATIONS' in argv
        deadline = time.monotonic() + 5
        while not program.with_suffix('.exe.args').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert program.with_suffix('.exe.args').read_text(encoding='utf-8-sig').splitlines() == ['--port', '48765', '--no-browser']
        assert json.loads((home / 'result.json').read_text())['status'] == ('cancelled' if cancel else 'completed')
    finally:
        for process in (parent, helper):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
