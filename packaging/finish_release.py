from pathlib import Path
import hashlib
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from version import VERSION

release = root / 'release'
with zipfile.ZipFile(release / f'Ai4PDF-{VERSION}-windows-x64-portable.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / 'dist' / 'Ai4PDF').rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(root / 'dist').as_posix())
assets = list(release.glob(f'Ai4PDF-{VERSION}-*')) + list(release.glob('*mupdf-*.tar.gz')) + [release / 'THIRD_PARTY_NOTICES.md']
lines = []
for path in sorted(assets):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    lines.append(f'{digest}  {path.name}')
(release / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(f'{p.name}: {p.stat().st_size / 1048576:.1f} MiB' for p in assets))
