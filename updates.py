"""Explicit, verified updates from this project's public GitHub Releases only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import urlsplit

import requests
from flask import g, jsonify, request
from werkzeug.wsgi import ClosingIterator

REPOSITORY = 'https://github.com/Teslajia/Ai4PDF'
LATEST_API = 'https://api.github.com/repos/Teslajia/Ai4PDF/releases/latest'
MAX_INSTALLER = 512 * 1024 * 1024


class UpdateError(ValueError):
    pass


def version_tuple(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise UpdateError('更新版本信息无效，请打开发布页面查看。')
    return tuple(int(part) for part in match.groups())


def github_get(url, *, limit, progress=None):
    """Bounded streaming, HTTPS-only GitHub redirects; never send AI credentials."""
    headers = {'User-Agent': 'Ai4PDF-Updater', 'Accept': 'application/vnd.github+json'}
    deadline = time.monotonic() + (900 if progress else 60)
    with requests.Session() as session:
        # Ignore .netrc authentication. System proxy configuration is still supported.
        session.trust_env = False
        proxies = requests.utils.get_environ_proxies(url)
        for _ in range(6):
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                    or parsed.hostname not in ('api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com')):
                raise UpdateError('更新下载地址无效，请打开发布页面查看。')
            with session.get(url, headers=headers, timeout=(10, 30), stream=True,
                             allow_redirects=False, proxies=proxies) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = response.headers.get('Location', '')
                    continue
                if response.status_code in (403, 429):
                    raise UpdateError('GitHub 暂时限制请求，请稍后重试。')
                if response.status_code == 404:
                    raise UpdateError('暂未找到正式版本或安装包，请打开发布页面查看。')
                response.raise_for_status()
                received = 0
                for chunk in response.iter_content(256 * 1024):
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > limit or time.monotonic() > deadline:
                        raise UpdateError('更新下载不完整或超时，请重试。')
                    yield chunk
                    if progress:
                        progress(received)
                return
    raise UpdateError('更新下载地址无效，请打开发布页面查看。')


def parse_release(value, current):
    if not isinstance(value, dict) or value.get('draft') or value.get('prerelease'):
        raise UpdateError('更新版本信息无效，请打开发布页面查看。')
    tag = value.get('tag_name', '')
    parts = version_tuple(tag)
    version = '.'.join(map(str, parts))
    page = f'{REPOSITORY}/releases/tag/{tag}'
    if value.get('html_url') != page:
        raise UpdateError('更新下载地址无效，请打开发布页面查看。')
    name = f'Ai4PDF-{version}-windows-x64-setup.exe'
    assets = value.get('assets', [])
    asset = next((a for a in assets if a.get('name') == name and a.get('state') == 'uploaded'), None)
    checksum = next((a for a in assets if a.get('name') == 'SHA256SUMS.txt' and a.get('state') == 'uploaded'), None)
    for item in (asset, checksum):
        if item and item.get('browser_download_url') != f'{REPOSITORY}/releases/download/{tag}/{item["name"]}':
            raise UpdateError('更新下载地址无效，请打开发布页面查看。')
    if asset and (type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_INSTALLER):
        raise UpdateError('更新安装包大小无效，请打开发布页面查看。')
    digest = asset.get('digest', '') if asset else ''
    digest = digest[7:].lower() if isinstance(digest, str) and re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest) else ''
    return {'version': version, 'tag': tag, 'url': page, 'notes': str(value.get('body') or '')[:12000],
            'isNew': parts > version_tuple(current), 'asset': asset, 'checksum': checksum, 'digest': digest}


def verified_file(path, release):
    if not path or path.is_symlink() or not path.is_file() or path.stat().st_size != release['asset']['size']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == release['digest']


class UpdateManager:
    def __init__(self, home, version):
        self.home, self.version = Path(home), version
        self.lock = threading.RLock()
        self.state, self.error, self.release = 'idle', '', None
        self.downloaded, self.file = 0, None
        self.launcher = None
        self.active_requests = 0

    def snapshot(self):
        with self.lock:
            release = self.release
            info = {key: release[key] for key in ('version', 'tag', 'url', 'notes', 'isNew')} if release else None
            if info is not None:
                info['size'] = release['asset']['size'] if release['asset'] else 0
                info['canDownload'] = bool(release['asset'] and (release['digest'] or release['checksum']))
            return {'currentVersion': self.version, 'canInstall': self.launcher is not None,
                    'state': self.state, 'error': self.error, 'release': info, 'downloaded': self.downloaded}

    def _available(self):
        if self.state in ('checking', 'downloading', 'installing'):
            raise UpdateError('更新正在进行，请稍后操作。')

    def check(self):
        with self.lock:
            self._available()
            self.state, self.error = 'checking', ''
        try:
            release = parse_release(json.loads(b''.join(github_get(LATEST_API, limit=2 * 1024 * 1024))), self.version)
            with self.lock:
                self.release = release
                self.state = 'available' if release['isNew'] else 'current'
                if release['isNew'] and release['asset'] and release['digest'] and verified_file(self.file, release):
                    self.state = 'ready'
        except Exception as exc:
            self._failed(exc)
        return self.snapshot()

    def _failed(self, exc):
        with self.lock:
            self.state = 'error'
            self.error = str(exc) if isinstance(exc, UpdateError) else '无法连接 GitHub 或下载失败，请检查网络后重试。'

    def download(self):
        with self.lock:
            self._available()
            if not self.launcher:
                raise UpdateError('源码版和便携版请从发布页面下载更新。')
            if not self.release or not self.release['isNew'] or not self.release['asset']:
                raise UpdateError('请先检查更新，确认有适用的安装包。')
            self.state, self.error, self.downloaded = 'downloading', '', 0
            threading.Thread(target=self._download, name='Ai4PDF update download', daemon=True).start()
        return self.snapshot()

    def _download(self):
        partial = None
        try:
            release = self.release
            if not release['digest']:
                checksum = release['checksum']
                if not checksum:
                    raise UpdateError('安装包缺少 SHA-256 校验信息，已停止更新。')
                manifest = b''.join(github_get(checksum['browser_download_url'], limit=128 * 1024)).decode('utf-8-sig')
                matches = re.findall(r'^([a-fA-F0-9]{64})\s+\*?' + re.escape(release['asset']['name']) + r'\s*$', manifest, re.M)
                if len(matches) != 1:
                    raise UpdateError('安装包缺少 SHA-256 校验信息，已停止更新。')
                release['digest'] = matches[0].lower()
            cache = self.home / 'updates'
            cache.mkdir(exist_ok=True)
            if cache.is_symlink() or cache.is_junction() or cache.resolve().parent != self.home.resolve():
                raise UpdateError('更新缓存目录不可用，请检查文件夹权限。')
            destination = Path(tempfile.mkdtemp(prefix='download-', dir=cache))
            partial = destination / (release['asset']['name'] + '.part')
            def progress(count):
                with self.lock:
                    self.downloaded = count
            with partial.open('xb') as stream:
                for chunk in github_get(release['asset']['browser_download_url'], limit=release['asset']['size'], progress=progress):
                    stream.write(chunk)
            if not verified_file(partial, release):
                raise UpdateError('安装包校验失败，已停止更新，请重新下载。')
            target = destination / release['asset']['name']
            partial.replace(target)
            with self.lock:
                self.file, self.state = target, 'ready'
        except Exception as exc:
            if partial:
                partial.unlink(missing_ok=True)
            self._failed(exc)

    def install(self, busy=False):
        with self.lock:
            if self.state != 'ready' or not self.launcher:
                raise UpdateError('请先下载并校验更新安装包。')
            if busy or self.active_requests:
                raise UpdateError('请等待文档保存、翻译、问答或文档库迁移完成后再安装。')
            if not verified_file(self.file, self.release):
                self.state = 'error'
                self.error = '安装包校验失败，已停止更新，请重新下载。'
                raise UpdateError(self.error)
            self.state = 'installing'
            try:
                self.launcher(self.file, self.release['digest'])
            except Exception:
                self.state = 'ready'
                raise UpdateError('无法启动更新程序，请重试或从发布页面下载安装。') from None
        return self.snapshot()


def register(server):
    manager = UpdateManager(server.CONFIG_ROOT, server.VERSION)
    app = server.app

    @app.before_request
    def update_guard():
        if request.path.startswith('/api/updates'):
            if request.method == 'POST' and not request.is_json:
                return server.fail('更新请求需要 JSON。', 415)
        elif request.path.startswith('/api/') and request.path != '/api/health':
            with manager.lock:
                if manager.state == 'installing':
                    return server.fail('正在安装更新，请等待软件重新启动。', 503)
                manager.active_requests += 1
                g.update_request_active = True

    def release_request():
        with manager.lock:
            manager.active_requests -= 1

    @app.after_request
    def track_update_request(response):
        if g.pop('update_request_active', False):
            if response.is_streamed:
                response.response = ClosingIterator(response.response, release_request)
            else:
                release_request()
        return response

    @app.teardown_request
    def failed_request(_):
        if g.pop('update_request_active', False):
            release_request()

    @app.get('/api/updates')
    def update_status():
        return jsonify(manager.snapshot())

    @app.post('/api/updates/check')
    def check_update():
        return jsonify(manager.check())

    @app.post('/api/updates/download')
    def download_update():
        return jsonify(manager.download()), 202

    @app.post('/api/updates/install')
    def install_update():
        return jsonify(manager.install(server.library.job_snapshot()['status'] == 'running')), 202

    return manager
