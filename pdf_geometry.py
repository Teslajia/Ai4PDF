"""Shared geometric guards for PDF layout and translation classification."""
from statistics import median
import pymupdf as fitz


def drawing_has_ink(drawing):
    stroke = drawing.get('color') is not None and (drawing.get('stroke_opacity') or 0) > 0
    fill = drawing.get('fill')
    filled = fill is not None and (drawing.get('fill_opacity') or 0) > 0
    # White backing rectangles often extend outside a figure's actual column.
    # They remain in the page image, but must not join unrelated content blocks.
    if filled and not stroke and all(c >= .995 for c in fill):
        return not all(item[0] == 're' for item in drawing.get('items',[]))
    return stroke or filled


def infer_gutter(rectangles, width, minimum=2):
    boxes = [fitz.Rect(r) for r in rectangles]
    left = [r for r in boxes if r.x1 <= width*.55 and (r.x0+r.x1)/2 < width*.44]
    right = [r for r in boxes if r.x0 >= width*.45 and (r.x0+r.x1)/2 > width*.56]
    if len(left) >= minimum and len(right) >= minimum:
        end,start = median(r.x1 for r in left),median(r.x0 for r in right)
        if start-end > 8:
            return (end+start)/2
    return None


def column_of(rect, gutter):
    if gutter is None:
        return 0
    if rect.x1 <= gutter:
        return 0
    if rect.x0 >= gutter:
        return 1
    return -1  # A genuinely spanning object.
