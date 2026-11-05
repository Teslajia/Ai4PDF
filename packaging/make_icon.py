"""Render the existing SVG brand mark as Windows icon assets."""
from pathlib import Path
import io

import pymupdf
from PIL import Image

root = Path(__file__).resolve().parents[1]
with pymupdf.open(root / 'static' / 'favicon.svg') as svg:
    with pymupdf.open('pdf', svg.convert_to_pdf()) as pdf:
        pix = pdf[0].get_pixmap(matrix=pymupdf.Matrix(4, 4), alpha=True)
image = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGBA').resize((256, 256), Image.Resampling.LANCZOS)
image.save(root / 'static' / 'app-icon.png')
image.save(root / 'static' / 'app-icon.ico', sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
