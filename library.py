"""Local library organization and verified, copy-first storage migration."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

from flask import jsonify, request
from werkzeug.exceptions import Conflict, NotFound


def initial_location(root, environ=None):
    environ = os.environ if environ is None else environ
    override = environ.get('AI4PDF_DATA') or environ.get('PAPERDESK_DATA')
    if override:
        return Path(override).expanduser().resolve(), True
    config = root / 'library-location.json'
    if config.exists():
        path = Path(json.loads(config.read_text(encoding='utf-8'))['path'])
        if not path.is_absolute() or not path.is_dir():
            raise RuntimeError('已配置的文档库目录不可用，请连接对应磁盘或检查 library-location.json。')
        return path.resolve(), False
    return root / 'data', False


def catalog(root):
    path = root / 'library.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'folders': [], 'documents': {}}


def trashed(root, doc_id):
    return bool(catalog(root)['documents'].get(doc_id, {}).get('deletedAt'))


def is_link(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def safe_tree(root):
    """Never traverse junctions/symlinks during copy or permanent deletion."""
    if is_link(root):
        raise ValueError('文档库包含链接目录，无法安全执行此操作。')
    files = []
    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            item = Path(parent) / name
            if is_link(item):
                raise ValueError('文档库包含链接目录，无法安全执行此操作。')
        files.extend(Path(parent) / name for name in names)
    return sorted(files)


def clean_name(value, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'名称不能为空，且不能超过 {limit} 个字符。')
    return value.strip()


def clean_tags(value):
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError('每份文档最多添加 30 个标签。')
    return list(dict.fromkeys(clean_name(tag, 40) for tag in value))


class Library:
    def __init__(self, server):
        self.s = server
        self.job_lock = threading.Lock()
        self.job = {'status': 'idle'}

    def listing(self, include_trash=False):
        saved = catalog(self.s.DATA)
        docs = []
        for path in self.s.DATA.glob('*/document.json'):
            if not re.fullmatch('[a-f0-9]{24}', path.parent.name):
                continue
            d = json.loads(path.read_text(encoding='utf-8'))
            item = {k: d[k] for k in ('id', 'name', 'title', 'pageCount', 'created')}
            item.update({'folderId': '', 'tags': [], 'deletedAt': None})
            item.update(saved['documents'].get(d['id'], {}))
            if include_trash or not item['deletedAt']:
                docs.append(item)
        return sorted(docs, key=lambda d: d['created'], reverse=True)

    def restore_import(self, doc_id):
        saved = catalog(self.s.DATA)
        if saved['documents'].get(doc_id, {}).get('deletedAt'):
            saved['documents'][doc_id]['deletedAt'] = None
            self.s.write_json(self.s.DATA / 'library.json', saved)

    def update_job(self, **fields):
        with self.job_lock:
            self.job.update(fields)

    def job_snapshot(self):
        with self.job_lock:
            return dict(self.job)

    def validate_target(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('请填写新的文档库绝对路径。')
        raw = Path(value.strip()).expanduser()
        if not raw.is_absolute():
            raise ValueError('请填写新的文档库绝对路径。')
        # Reject a junction in any existing ancestor, including the target itself.
        if any(is_link(p) for p in [raw, *raw.parents]):
            raise ValueError('目标路径不能包含符号链接或目录联接。')
        target, source = raw.resolve(), self.s.DATA.resolve()
        if target == source or target in source.parents or source in target.parents:
            raise ValueError('新旧文档库不能相同，也不能互相包含。')
        if target.exists() and (not target.is_dir() or any(target.iterdir())):
            raise ValueError('目标文件夹必须为空，或尚不存在。')
        return source, target

    def migrate(self, source, target):
        try:
            with self.s.LOCK:
                # Validate again after acquiring the same lock used by document writes.
                self.validate_target(str(target))
                files = safe_tree(source)
                total = sum(p.stat().st_size for p in files)
                existing = target.parent
                while not existing.exists():
                    existing = existing.parent
                if shutil.disk_usage(existing).free < total + 16 * 1024 * 1024:
                    raise ValueError('目标磁盘空间不足。')
                self.update_job(total=total, copied=0, files=len(files), completedFiles=0)
                target.mkdir(parents=True, exist_ok=True)
                copied = 0
                for index, path in enumerate(files):
                    output = target / path.relative_to(source)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    source_hash = hashlib.sha256()
                    with path.open('rb') as src, output.open('xb') as dst:
                        while chunk := src.read(1024 * 1024):
                            dst.write(chunk)
                            source_hash.update(chunk)
                            copied += len(chunk)
                            self.update_job(copied=copied)
                        dst.flush()
                        os.fsync(dst.fileno())
                    with output.open('rb') as check:
                        if hashlib.file_digest(check, 'sha256').digest() != source_hash.digest():
                            raise ValueError('迁移校验失败，原文档库仍在使用。')
                    # Detect external changes to source files while copying.
                    with path.open('rb') as check:
                        if hashlib.file_digest(check, 'sha256').digest() != source_hash.digest():
                            raise ValueError('迁移期间原目录发生变化，请重试。')
                    self.update_job(completedFiles=index + 1)
                if files != safe_tree(source):
                    raise ValueError('迁移期间原目录发生变化，请重试。')
                # Persist the verified destination before switching the live process.
                self.s.write_json(self.s.LOCATION_FILE, {'path': str(target), 'previousPath': str(source), 'updated': self.s.now()})
                self.s.DATA = target
                self.update_job(status='done', path=str(target), previousPath=str(source))
        except Exception as exc:
            self.s.app.logger.error('Library migration failed: %s', type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else '迁移失败，请检查目录权限和磁盘空间。原文档库仍在使用。'
            self.update_job(status='error', error=message)

    def register(self):
        s = self.s

        @s.app.get('/api/library')
        def get_library():
            with s.LOCK:
                return jsonify(documents=self.listing(True), folders=catalog(s.DATA)['folders'])

        @s.app.post('/api/library/folders')
        def create_folder():
            name = clean_name(request.get_json().get('name'))
            with s.LOCK:
                saved = catalog(s.DATA)
                if any(f['name'].casefold() == name.casefold() for f in saved['folders']):
                    raise ValueError('已存在同名文件夹。')
                item = {'id': uuid.uuid4().hex, 'name': name}
                saved['folders'].append(item)
                s.write_json(s.DATA / 'library.json', saved)
                return jsonify(item)

        @s.app.route('/api/library/folders/<folder_id>', methods=['PATCH', 'DELETE'])
        def edit_folder(folder_id):
            with s.LOCK:
                saved = catalog(s.DATA)
                item = next((f for f in saved['folders'] if f['id'] == folder_id), None)
                if item is None:
                    raise NotFound('文件夹不存在。')
                if request.method == 'DELETE':
                    saved['folders'].remove(item)
                    for d in saved['documents'].values():
                        if d.get('folderId') == folder_id:
                            d['folderId'] = ''
                else:
                    name = clean_name(request.get_json().get('name'))
                    if any(f['id'] != folder_id and f['name'].casefold() == name.casefold() for f in saved['folders']):
                        raise ValueError('已存在同名文件夹。')
                    item['name'] = name
                s.write_json(s.DATA / 'library.json', saved)
                return jsonify(ok=True)

        @s.app.post('/api/library/batch')
        def batch():
            body = request.get_json()
            ids, action = body.get('ids'), body.get('action')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 2000 or any(not isinstance(i, str) or not re.fullmatch('[a-f0-9]{24}', i) for i in ids):
                raise ValueError('请选择有效文档，每次最多 2000 份。')
            ids = list(dict.fromkeys(ids))
            if action not in ('edit', 'move', 'addTags', 'removeTags', 'trash', 'restore', 'purge'):
                raise ValueError('无效的文档库操作。')
            with s.LOCK:
                if self.job_snapshot()['status'] == 'running':
                    raise Conflict('文档库正在迁移，请稍后操作。')
                saved = catalog(s.DATA)
                for doc_id in ids:
                    if not (s.DATA / doc_id / 'document.json').is_file():
                        raise NotFound('文档不存在，请刷新文档库。')
                    deleted = bool(saved['documents'].get(doc_id, {}).get('deletedAt'))
                    if deleted != (action in ('restore', 'purge')):
                        raise Conflict('文档状态已变化，请刷新文档库。')
                changes = {}
                if action in ('move', 'edit'):
                    folder_id = body.get('folderId', '')
                    if not isinstance(folder_id, str) or (folder_id and folder_id not in [f['id'] for f in saved['folders']]):
                        raise ValueError('文件夹不存在。')
                    changes['folderId'] = folder_id
                if action == 'edit':
                    if len(ids) != 1:
                        raise ValueError('请逐份编辑文档名称。')
                    changes.update(title=clean_name(body.get('title'), 300), tags=clean_tags(body.get('tags', [])))
                if action in ('addTags', 'removeTags'):
                    tags = clean_tags(body.get('tags', []))
                if action == 'trash':
                    changes['deletedAt'] = s.now()
                if action == 'restore':
                    changes['deletedAt'] = None
                if action == 'purge':
                    # Validate every deletion path before touching any file.
                    targets = [(s.DATA / doc_id).resolve() for doc_id in ids]
                    root = s.DATA.resolve()
                    for doc_id, target in zip(ids, targets):
                        if target.parent != root or target.name != doc_id or is_link(s.DATA / doc_id):
                            raise ValueError('文档路径异常，未删除文件。')
                        safe_tree(target)
                        quarantine = root / ('.purge-' + doc_id)
                        if quarantine.resolve().parent != root or quarantine.exists() or is_link(quarantine):
                            raise ValueError('存在未完成的清理目录，请先检查文档库目录。')
                    # One directory rename removes it from the live library atomically.
                    # Hidden purge folders are safe to retry if a file is temporarily locked.
                    for doc_id, target in zip(ids, targets):
                        quarantine = root / ('.purge-' + doc_id)
                        target.rename(quarantine)
                        previous = saved['documents'].pop(doc_id, None)
                        try:
                            s.write_json(s.DATA / 'library.json', saved)
                        except Exception:
                            if previous is not None:
                                saved['documents'][doc_id] = previous
                            quarantine.rename(target)
                            raise
                        try:
                            shutil.rmtree(quarantine)
                        except OSError:
                            # Keep it hidden; report that the payload needs manual cleanup.
                            raise ValueError('部分文件被占用，清理目录已保留，请关闭文件后清理文档库中的 .purge- 目录。')
                else:
                    for doc_id in ids:
                        item = saved['documents'].setdefault(doc_id, {})
                        if action == 'addTags':
                            item['tags'] = clean_tags(list(dict.fromkeys(item.get('tags', []) + tags)))
                        elif action == 'removeTags':
                            item['tags'] = [tag for tag in item.get('tags', []) if tag not in tags]
                        item.update(changes)
                    s.write_json(s.DATA / 'library.json', saved)
                return jsonify(ok=True, count=len(ids))

        @s.app.get('/api/library/storage')
        def storage():
            with s.LOCK:
                docs = self.listing(True)
                return jsonify(path=str(s.DATA.resolve()), managedByEnvironment=s.DATA_FROM_ENV,
                               documents=sum(not d['deletedAt'] for d in docs), trash=sum(bool(d['deletedAt']) for d in docs))

        @s.app.get('/api/library/migration')
        def migration_status():
            return jsonify(self.job_snapshot())

        @s.app.post('/api/library/migration')
        def start_migration():
            if s.DATA_FROM_ENV:
                raise ValueError('文档库位置由环境变量指定，请修改环境变量后重启。')
            body = request.get_json()
            # Never wait on a running migration merely to reject a second one.
            if self.job_snapshot()['status'] == 'running':
                raise Conflict('文档库正在迁移，请稍后操作。')
            with s.LOCK:
                if self.job_snapshot()['status'] == 'running':
                    raise Conflict('文档库正在迁移，请稍后操作。')
                if body.get('source') != str(s.DATA.resolve()):
                    raise Conflict('文档库位置已变化，请重新打开设置。')
                source, target = self.validate_target(body.get('target'))
                self.update_job(status='running', source=str(source), target=str(target), copied=0, total=0, completedFiles=0, files=0, error=None)
                threading.Thread(target=self.migrate, args=(source, target), daemon=True).start()
            return jsonify(self.job_snapshot()), 202


def register(server):
    library = Library(server)
    library.register()
    return library
