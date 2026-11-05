from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from version import VERSION

numbers = tuple(map(int, VERSION.split('.'))) + (0,)
text = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f,
                   flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Teslajia'),
    StringStruct('FileDescription', 'Ai4PDF - PDF AI Assistant'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('InternalName', 'Ai4PDF'),
    StringStruct('LegalCopyright', 'Copyright (C) 2026 Teslajia and contributors; AGPL-3.0'),
    StringStruct('OriginalFilename', 'Ai4PDF.exe'),
    StringStruct('ProductName', 'Ai4PDF'),
    StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
(root / 'build' / 'windows-version.txt').write_text(text, encoding='utf-8')
