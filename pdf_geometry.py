"""Shared geometric guards for PDF layout and translation classification."""
from statistics import median
import pymupdf as fitz


def visible_drawings(page):
    """Bound vector paths by the active PDF clips, in unrotated coordinates.

    Embedded figures can retain off-canvas paths in their content streams.
    get_drawings() alone reports these even when the PDF clips them away.
    Extended paths expose the clip/group scope through their nesting levels.
    """
    bounds=fitz.Rect(0,0,page.cropbox.width,page.cropbox.height)
    scopes=[]
    for drawing in page.get_drawings(extended=True):
        level=drawing['level']
        while scopes and scopes[-1][0]>=level:scopes.pop()
        clip,opacity=scopes[-1][1:] if scopes else (bounds,1)
        kind=drawing['type']
        if kind=='clip':
            scopes.append((level,clip&fitz.Rect(drawing['scissor']),opacity));continue
        if kind=='group':
            scopes.append((level,clip,opacity*drawing.get('opacity',1)));continue
        if opacity<=0 or clip.is_empty or not drawing_has_ink(drawing):continue
        raw=fitz.Rect(drawing['rect'])
        rect=fitz.Rect(max(raw.x0,clip.x0),max(raw.y0,clip.y0),min(raw.x1,clip.x1),min(raw.y1,clip.y1))
        # Zero-height/width strokes are real axes and rules; keep them.
        if rect.x1<rect.x0 or rect.y1<rect.y0:continue
        yield drawing|{'rect':rect}


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
