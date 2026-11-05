"""Validate the installer helper with Windows PowerShell 5.1 and isolated profiles."""
import configparser
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
pytestmark = pytest.mark.skipif(not POWERSHELL.exists(), reason='Windows PowerShell is required')


def call(tmp, mode='Inspect', path=None, expected=None, env=None):
    home = tmp / 'profile'
    result = tmp / 'result.ini'
    environment = dict(os.environ)
    for key in ('AI4PDF_HOME', 'AI4PDF_DATA', 'PAPERDESK_DATA'):
        environment.pop(key, None)
    environment.update(env or {})
    args = [str(POWERSHELL), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'packaging/library-location.ps1'), '-Mode', mode,
            '-ConfigRoot', str(home), '-ResultFile', str(result)]
    if mode != 'Inspect':
        args += ['-LibraryPath', str(path), '-InstallDir', str(tmp / 'program'),
                 '-ExpectedPath', expected['path'], '-ExpectedMode', expected['mode']]
    process = subprocess.run(args, env=environment, capture_output=True, timeout=20,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(result, encoding='utf-16')
    return process.returncode, dict(parser['Library'])


def test_new_selection_validates_without_writing_then_commits_unicode_path(tmp_path):
    _, state = call(tmp_path)
    target = tmp_path / "中文 论文库 % ! O'Brien"
    code, result = call(tmp_path, 'Validate', target, state)
    assert code == 0, result
    assert not target.exists()
    assert not (tmp_path / 'profile').exists()
    code, result = call(tmp_path, 'Commit', target, state)
    assert code == 0, result
    assert target.is_dir()
    pointer = tmp_path / 'profile/library-location.json'
    assert json.loads(pointer.read_text(encoding='utf-8'))['path'] == str(target)
    assert not pointer.read_bytes().startswith(b'\xef\xbb\xbf')


def test_adopts_existing_library_without_modifying_documents(tmp_path):
    target = tmp_path / 'existing'
    target.mkdir()
    catalog = target / 'library.json'
    catalog.write_text('{"folders": [], "documents": {}}')
    before = catalog.read_bytes()
    _, state = call(tmp_path)
    code, result = call(tmp_path, 'Commit', target, state)
    assert code == 0, result
    assert catalog.read_bytes() == before


def test_empty_previously_configured_library_can_be_changed(tmp_path):
    _, state = call(tmp_path)
    first = tmp_path / 'first-empty-library'
    assert call(tmp_path, 'Commit', first, state)[0] == 0
    _, state = call(tmp_path)
    assert state['mode'] == 'new'
    second = tmp_path / 'second-library'
    code, result = call(tmp_path, 'Commit', second, state)
    assert code == 0, result
    assert first.is_dir() and second.is_dir()
    assert json.loads((tmp_path / 'profile/library-location.json').read_text())['path'] == str(second)


@pytest.mark.parametrize('kind', ['program', 'nested-program', 'relative', 'file', 'unrelated', 'root'])
def test_invalid_destination_does_not_create_config(tmp_path, kind):
    candidates = {'program': tmp_path / 'program', 'nested-program': tmp_path / 'program/data',
                  'relative': 'relative-library', 'file': tmp_path / 'a-file',
                  'unrelated': tmp_path / 'other-files', 'root': Path(tmp_path.anchor)}
    (tmp_path / 'a-file').write_text('keep')
    (tmp_path / 'other-files').mkdir()
    (tmp_path / 'other-files/keep.pdf').write_bytes(b'keep')
    _, state = call(tmp_path)
    code, _ = call(tmp_path, 'Commit', candidates[kind], state)
    assert code != 0
    assert not (tmp_path / 'profile/library-location.json').exists()
    assert (tmp_path / 'a-file').read_text() == 'keep'
    assert (tmp_path / 'other-files/keep.pdf').read_bytes() == b'keep'


@pytest.mark.parametrize('missing', [False, True])
def test_upgrade_keeps_existing_pointer_and_rejects_switch(tmp_path, missing):
    home = tmp_path / 'profile'
    home.mkdir()
    target = tmp_path / 'original-library'
    if not missing:
        target.mkdir()
        (target / 'library.json').write_text('{"folders": [], "documents": {}}')
    pointer = home / 'library-location.json'
    pointer.write_text(json.dumps({'path': str(target)}))
    original = pointer.read_bytes()
    _, state = call(tmp_path)
    assert state['mode'] == 'existing'
    assert call(tmp_path, 'Commit', target, state)[0] == 0
    assert call(tmp_path, 'Commit', tmp_path / 'replacement', state)[0] != 0
    assert pointer.read_bytes() == original
    assert target.exists() is not missing


def test_environment_managed_library_is_preserved(tmp_path):
    target = tmp_path / 'managed'
    env = {'AI4PDF_DATA': str(target)}
    _, state = call(tmp_path, env=env)
    assert state['mode'] == 'environment'
    assert call(tmp_path, 'Commit', target, state, env)[0] == 0
    assert not (tmp_path / 'profile/library-location.json').exists()
    assert call(tmp_path, 'Commit', tmp_path / 'other', state, env)[0] != 0


def test_concurrent_change_and_running_app_do_not_overwrite_setting(tmp_path):
    import msvcrt
    _, state = call(tmp_path)
    home = tmp_path / 'profile'
    home.mkdir()
    with (home / 'desktop.lock').open('w+b') as guard:
        guard.write(b'0'); guard.flush(); guard.seek(0)
        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            assert call(tmp_path, 'Commit', tmp_path / 'selected', state)[0] != 0
            assert not (home / 'library-location.json').exists()
        finally:
            guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
    (home / 'data').mkdir()
    (home / 'data/document.txt').write_text('created while the installer was open')
    assert call(tmp_path, 'Commit', tmp_path / 'selected', state)[0] != 0


def test_broken_existing_config_is_reported_not_overwritten(tmp_path):
    home = tmp_path / 'profile'
    home.mkdir()
    pointer = home / 'library-location.json'
    pointer.write_bytes(b'invalid JSON')
    code, state = call(tmp_path)
    assert code != 0 and state['mode'] == 'error'
    assert pointer.read_bytes() == b'invalid JSON'
