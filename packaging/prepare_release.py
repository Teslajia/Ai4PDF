"""Build source and license artifacts from an allowlist, never from user data."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION

SOURCE_FILES = (
    '.gitignore', 'LICENSE', 'NOTICE', 'README.md', 'README.en.md',
    'README.zh-TW.md', 'README.ja.md', 'README.ko.md', 'CONTRIBUTING.md',
    'CHANGELOG.md', 'RELEASE.md', 'app.py', 'desktop.py',
    'runtime_paths.py', 'version.py', 'updates.py', 'desktop_update.py', 'reasoning.py', 'layout.py', 'library.py', 'manual_layout.py',
    'pdf_geometry.py', 'translation_policy.py', 'translation_visuals.py', 'table_regions.py', 'figure_regions.py', 'references.py', 'requirements.txt', 'requirements-desktop.txt',
    'requirements-build.lock', 'package.json', 'package-lock.json', 'setup.ps1', 'start.cmd', 'start.ps1',
)
SOURCE_DIRS = ('static', 'tests', 'packaging', '.github', 'docs')


def source_files():
    files = [ROOT / name for name in SOURCE_FILES]
    for directory in SOURCE_DIRS:
        files.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.log'))
    for path in sorted(set(files)):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError('Source archive contains a link outside the project')
        if not path.exists():
            raise FileNotFoundError(path)
        yield path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare():
    package = json.loads((ROOT / 'package.json').read_text())
    lock = json.loads((ROOT / 'package-lock.json').read_text())
    if any(value != VERSION for value in (package['version'], lock['version'], lock['packages']['']['version'])):
        raise RuntimeError('version.py, package.json and package-lock.json versions differ')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    legal = ROOT / 'build' / 'legal'
    legal.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(release / f'Ai4PDF-{VERSION}-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            archive.write(path, f'Ai4PDF-{VERSION}/' + path.relative_to(ROOT).as_posix())
    # Installed copies carry their own application source and complete AGPL text.
    shutil.copy2(release / f'Ai4PDF-{VERSION}-source.zip', legal / 'Ai4PDF-source.zip')
    shutil.copy2(ROOT / 'LICENSE', legal / 'LICENSE')
    shutil.copy2(ROOT / 'NOTICE', legal / 'NOTICE')
    lines = ['# Third-party notices', '', 'Ai4PDF includes the following unmodified dependencies.',
             'License texts and metadata are in the licenses directory.', '',
             '## Python and native dependencies', '']
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        lines.append(f'- {name} {dist.version}')
        destination = legal / 'licenses' / name
        destination.mkdir(parents=True, exist_ok=True)
        for file in dist.files or []:
            path = Path(str(file))
            if any(word in path.name.lower() for word in ('license', 'copying', 'notice')) or path.name == 'METADATA':
                source = Path(dist.locate_file(file))
                if source.is_file():
                    shutil.copy2(source, destination / ('__'.join(path.parts[-3:])))
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, legal / 'PYTHON-LICENSE.txt')
    lines += ['', '## JavaScript dependencies', '']
    for package in ('pdfjs-dist', 'katex', 'marked', 'dompurify'):
        folder = ROOT / 'node_modules' / package
        package_info = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
        lines.append(f'- {package} {package_info["version"]}: {package_info.get("license", "see license files")}')
        destination = legal / 'licenses' / package
        destination.mkdir(parents=True, exist_ok=True)
        for path in folder.rglob('*'):
            if path.is_file() and any(word in path.name.lower() for word in ('license', 'copying', 'notice')):
                target = destination / path.relative_to(folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    # Provide matching PyMuPDF / MuPDF source alongside every binary release.
    version = metadata.version('PyMuPDF')
    response = requests.get(f'https://pypi.org/pypi/PyMuPDF/{version}/json', timeout=60)
    response.raise_for_status()
    sdist = next(file for file in response.json()['urls'] if file['packagetype'] == 'sdist')
    source_archive = release / sdist['filename']
    expected = sdist['digests']['sha256']
    if not source_archive.exists() or sha256(source_archive) != expected:
        temp = source_archive.with_suffix('.download')
        with requests.get(sdist['url'], stream=True, timeout=(15, 120)) as download:
            download.raise_for_status()
            with temp.open('wb') as stream:
                for chunk in download.iter_content(1024 * 1024):
                    stream.write(chunk)
        if sha256(temp) != expected:
            raise RuntimeError('PyMuPDF source hash mismatch')
        temp.replace(source_archive)
    with tarfile.open(source_archive) as archive:
        names = archive.getnames()
        if not any('mupdf' in n.lower() and n.endswith(('.tar.gz', '.tgz', '.tar')) for n in names):
            import pymupdf.mupdf_info
            native_version = pymupdf.mupdf_info.mupdf_version
            native_name = f'mupdf-{native_version}-source.tar.gz'
            native_url = f'https://mupdf.com/downloads/archive/{native_name}'
            native_source = release / native_name
            if not native_source.exists():
                temp = native_source.with_suffix('.download')
                with requests.get(native_url, stream=True, timeout=(15, 120)) as download:
                    download.raise_for_status()
                    with temp.open('wb') as stream:
                        for chunk in download.iter_content(1024 * 1024):
                            stream.write(chunk)
                temp.replace(native_source)
            with tarfile.open(native_source) as native:
                assert any('/source/' in n for n in native.getnames()), 'Invalid MuPDF source archive'
                for file in native.getmembers():
                    if file.isfile() and Path(file.name).name in ('COPYING', 'LICENSE'):
                        destination = legal / 'licenses' / 'MuPDF' / file.name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(native.extractfile(file).read())
            lines += ['', f'MuPDF native source: {native_name}', f'Upstream source: {native_url}',
                      f'SHA256: {sha256(native_source)}']
    lines += ['', '## Corresponding source', '',
              'Ai4PDF: Ai4PDF-source.zip in this directory; build instructions are in RELEASE.md.',
              f'PyMuPDF: {sdist["filename"]}, supplied as a separate Release asset.',
              f'Upstream identical source: {sdist["url"]}', f'SHA256: {expected}', '',
              'PyMuPDF and MuPDF are used under GNU AGPL-3.0. Other components retain their own licenses.',
              'No documents, annotations, API keys or browser settings are included in the release.', '']
    (legal / 'THIRD_PARTY_NOTICES.md').write_text('\n'.join(lines), encoding='utf-8')
    shutil.copy2(legal / 'THIRD_PARTY_NOTICES.md', release / 'THIRD_PARTY_NOTICES.md')
    print(f'Prepared source and licenses for Ai4PDF {VERSION}')


if __name__ == '__main__':
    prepare()
