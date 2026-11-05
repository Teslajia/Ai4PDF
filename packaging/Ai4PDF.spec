# PyInstaller one-directory build. Do not add the project root or data directories as data.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent
datas = [(str(root / 'static'), 'static'), (str(root / 'build' / 'legal'), 'legal')]
datas.append((str(root / 'packaging' / 'apply-update.ps1'), 'packaging'))
for package, folders in {
    'pdfjs-dist': ['build', 'web', 'cmaps', 'standard_fonts', 'wasm'],
    'katex': ['dist'], 'marked': ['lib'], 'dompurify': ['dist'],
}.items():
    for folder in folders:
        datas.append((str(root / 'node_modules' / package / folder), f'node_modules/{package}/{folder}'))
datas += collect_data_files('pymupdf')

a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=collect_dynamic_libs('pymupdf'),
             datas=datas, hiddenimports=['pystray._win32', 'PIL.IcoImagePlugin', 'PIL.PngImagePlugin'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter', 'matplotlib', 'IPython'],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Ai4PDF', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'static' / 'app-icon.ico'), version=str(root / 'build' / 'windows-version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Ai4PDF')
