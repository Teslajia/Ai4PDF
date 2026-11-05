import hashlib
import json
import time
from types import SimpleNamespace

from flask import Flask, Response, jsonify
import pytest

import updates

PAYLOAD = b'MZ-test-installer'
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def release(version='1.2.0', **fields):
    tag = 'v' + version
    prefix = f'{updates.REPOSITORY}/releases/download/{tag}/'
    name = f'Ai4PDF-{version}-windows-x64-setup.exe'
    return dict(tag_name=tag, html_url=f'{updates.REPOSITORY}/releases/tag/{tag}',
                draft=False, prerelease=False, body='New version', assets=[
                    dict(name=name, state='uploaded', browser_download_url=prefix + name,
                         size=len(PAYLOAD), digest='sha256:' + DIGEST),
                    dict(name='SHA256SUMS.txt', state='uploaded', browser_download_url=prefix + 'SHA256SUMS.txt'),
                ], **fields)


def remote(monkeypatch, data=None, payload=PAYLOAD, manifest=None):
    data = data or release()
    calls = []
    def get(url, *, limit, progress=None):
        calls.append(url)
        content = (json.dumps(data).encode() if url == updates.LATEST_API else
                   (manifest or '').encode() if url.endswith('.txt') else payload)
        if len(content) > limit:
            raise updates.UpdateError('更新下载不完整或超时，请重试。')
        yield content
        if progress:
            progress(len(content))
    monkeypatch.setattr(updates, 'github_get', get)
    return calls


def wait_download(manager):
    deadline = time.monotonic() + 5
    while manager.snapshot()['state'] == 'downloading' and time.monotonic() < deadline:
        time.sleep(.01)
    return manager.snapshot()


@pytest.mark.parametrize('current,latest,new', [('1.0.9','1.0.10',True), ('1.2.0','1.2.0',False), ('2.0.0','1.9.9',False)])
def test_numeric_versions_never_downgrade(current, latest, new):
    assert updates.parse_release(release(latest), current)['isNew'] is new


@pytest.mark.parametrize('value', ['1.0.1-beta', 'v2', '../2.0.0', '1.02.3', None])
def test_reject_malformed_or_prerelease_version(value):
    with pytest.raises(updates.UpdateError):
        updates.version_tuple(value)


@pytest.mark.parametrize('mutation', ['prerelease', 'draft', 'external', 'oversize', 'wrong_page'])
def test_release_trust_boundaries(mutation):
    data = release()
    if mutation in ('prerelease', 'draft'):
        data[mutation] = True
    elif mutation == 'external':
        data['assets'][0]['browser_download_url'] = 'https://evil.example/setup.exe'
    elif mutation == 'oversize':
        data['assets'][0]['size'] = updates.MAX_INSTALLER + 1
    else:
        data['html_url'] = 'javascript:alert(1)'
    with pytest.raises(updates.UpdateError):
        updates.parse_release(data, '1.0.0')


def test_verified_download_install_preserves_data(tmp_path, monkeypatch):
    docs = tmp_path / 'library'
    docs.mkdir()
    for name, content in [('original.pdf', b'PDF'), ('state.json', b'annotations and translations')]:
        (docs / name).write_bytes(content)
    pointer = tmp_path / 'library-location.json'
    pointer.write_text(json.dumps({'path': str(docs)}))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    launched = []
    manager.launcher = lambda *args: launched.append(args)
    calls = remote(monkeypatch)
    assert manager.check()['state'] == 'available'
    manager.download()
    assert wait_download(manager)['state'] == 'ready'
    assert manager.snapshot()['downloaded'] == len(PAYLOAD)
    assert manager.install()['state'] == 'installing'
    assert launched == [(manager.file, DIGEST)]
    assert len(calls) == 2
    assert {p: p.read_bytes() for p in before} == before


def test_checksum_manifest_fallback(tmp_path, monkeypatch):
    data = release()
    del data['assets'][0]['digest']
    remote(monkeypatch, data, manifest=DIGEST + '  ' + data['assets'][0]['name'] + '\n')
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    manager.launcher = lambda *_: None
    manager.check()
    manager.download()
    assert wait_download(manager)['state'] == 'ready'


@pytest.mark.parametrize('failure', ['wrong_hash', 'truncated', 'missing_hash', 'bad_manifest'])
def test_bad_download_never_launches_or_leaves_partial(tmp_path, monkeypatch, failure):
    data = release()
    payload = PAYLOAD
    if failure == 'wrong_hash':
        payload = b'x' * len(payload)
    elif failure == 'truncated':
        payload = b'MZ'
    else:
        del data['assets'][0]['digest']
        if failure == 'missing_hash':
            data['assets'].pop()
    remote(monkeypatch, data, payload)
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    manager.launcher = lambda *_: pytest.fail('Unverified installer launched')
    manager.check()
    manager.download()
    assert wait_download(manager)['state'] == 'error'
    assert not list(tmp_path.rglob('*.part'))
    with pytest.raises(updates.UpdateError):
        manager.install()


def test_recheck_cached_download_and_reverify_before_install(tmp_path, monkeypatch):
    remote(monkeypatch)
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    manager.launcher = lambda *_: pytest.fail('Modified installer launched')
    manager.check()
    manager.download()
    assert wait_download(manager)['state'] == 'ready'
    assert manager.check()['state'] == 'ready'
    manager.file.write_bytes(b'x' * len(PAYLOAD))
    with pytest.raises(updates.UpdateError, match='校验失败'):
        manager.install()


def test_source_mode_check_but_no_execution(tmp_path, monkeypatch):
    remote(monkeypatch)
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    assert manager.check()['release']['isNew']
    with pytest.raises(updates.UpdateError, match='源码版'):
        manager.download()


def test_network_failure_can_retry_without_erasing_library(tmp_path, monkeypatch):
    manager = updates.UpdateManager(tmp_path, '1.0.0')
    def failed(*_, **__):
        raise OSError('private network details')
    monkeypatch.setattr(updates, 'github_get', failed)
    assert manager.check()['state'] == 'error'
    assert 'private' not in manager.snapshot()['error']
    remote(monkeypatch, release('1.0.0'))
    assert manager.check()['state'] == 'current'


def test_running_jobs_and_streams_block_install_and_shutdown_blocks_new_writes(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config['TESTING'] = True
    server = SimpleNamespace(CONFIG_ROOT=tmp_path, VERSION='1.0.0', app=app,
                             fail=lambda text, code=400: (jsonify(error=text), code),
                             library=SimpleNamespace(job_snapshot=lambda: {'status': 'idle'}))
    @app.errorhandler(updates.UpdateError)
    def invalid(exc):
        return server.fail(str(exc))
    @app.get('/api/chat')
    def chat():
        return Response(iter([b'first', b'second']))
    @app.post('/api/save')
    def save():
        return jsonify(ok=True)
    manager = updates.register(server)
    manager.launcher = lambda *_: None
    remote(monkeypatch)
    client = app.test_client()
    assert client.post('/api/updates/check', data={}).status_code == 415
    assert client.post('/api/updates/check', json={}).json['state'] == 'available'
    assert client.post('/api/updates/download', json={}).status_code == 202
    assert wait_download(manager)['state'] == 'ready'
    stream = client.get('/api/chat', buffered=False)
    assert manager.active_requests == 1
    assert client.post('/api/updates/install', json={}).status_code == 400
    stream.close()
    assert manager.active_requests == 0
    with pytest.raises(updates.UpdateError, match='等待'):
        manager.install(busy=True)
    assert client.post('/api/updates/install', json={}).status_code == 202
    assert client.post('/api/save', json={}).status_code == 503
    assert client.get('/api/updates').status_code == 200


def test_unsafe_redirect_rejected_before_second_request(monkeypatch):
    calls = []
    response = SimpleNamespace(status_code=302, headers={'Location': 'http://127.0.0.1/private'})
    class Context:
        def __init__(self, value): self.value = value
        def __enter__(self): return self.value
        def __exit__(self, *_): pass
    class Session:
        trust_env = True
        def get(self, url, **kwargs):
            assert self.trust_env is False
            assert kwargs['allow_redirects'] is False
            calls.append(url)
            return Context(response)
    monkeypatch.setattr(updates.requests, 'Session', lambda: Context(Session()))
    with pytest.raises(updates.UpdateError, match='地址无效'):
        list(updates.github_get(updates.LATEST_API, limit=100))
    assert calls == [updates.LATEST_API]
