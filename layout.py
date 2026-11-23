"""Lossless page partitioning for interleaved bilingual reading.

Original pixels are partitioned, never reconstructed from extracted text. Text
and graphic bounding boxes only decide safe places to insert translations.
"""
from collections import defaultdict, deque
import pymupdf as fitz
from pdf_geometry import visible_drawings, infer_gutter
from translation_visuals import build_visuals

VERSION = 10


def merged_intervals(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if hi <= lo:
            continue
        if result and lo <= result[-1][1] + .1:
            result[-1][1] = max(hi, result[-1][1])
        else:
            result.append([lo, hi])
    return result


def safe_spanning_intervals(intervals, obstacles):
    """Move every column transition into whitespace on BOTH sides of the page."""
    intervals = merged_intervals(intervals)
    while True:
        expanded=[]
        for lo,hi in intervals:
            for r in obstacles:
                if r.y0 < lo < r.y1:
                    lo = r.y0
                if r.y0 < hi < r.y1:
                    hi = r.y1
            expanded.append((lo,hi))
        expanded=merged_intervals(expanded)
        if expanded==intervals:
            return expanded
        intervals=expanded


def build_layout(pdf, stored, fresh, protected_pages=()):
    # Match existing IDs by text, not position: translations must never be reassigned.
    locations = defaultdict(deque)
    for p in fresh:
        locations[(p['page'], p['text'])].append(p['bbox'])
    by_page = defaultdict(list)
    for p in stored:
        matches = locations[(p['page'], p['text'])]
        bbox = matches.popleft() if matches else p.get('bbox')
        by_page[p['page']].append(dict(p, bbox=bbox))
    pages = []
    for n, page in enumerate(pdf, 1):
        bounds = page.rect
        protected_regions=next((item['regions'] for item in protected_pages if item['page']==n),[])
        paragraphs = by_page[n]
        obstacles = []
        graphics = []

        def displayed(rect):
            rect = fitz.Rect(rect) * page.rotation_matrix
            return fitz.Rect(rect.x0-.7, rect.y0-.7, rect.x1+.7, rect.y1+.7) & bounds

        for p in paragraphs:
            if p['bbox']:
                p['bbox'] = list(displayed(p['bbox']))
            else:
                # Older extraction versions may have different paragraph boundaries.
                hits = page.search_for(p['text'][:100])
                if hits:
                    p['bbox'] = list(displayed(hits[0]))
        for b in page.get_text('blocks'):
            rect = displayed(b[:4])
            # A vertical margin stamp must not merge an entire page into one slice.
            if rect.height > bounds.height*.3 and rect.width < rect.height*.15 and (rect.x1 < bounds.width*.1 or rect.x0 > bounds.width*.9):
                continue
            if not rect.is_empty:
                obstacles.append(rect)
        for image in page.get_image_info():
            graphics.append(displayed(image['bbox']))
        for drawing in visible_drawings(page):
            rect = displayed(drawing['rect'])
            # Page borders/backgrounds are still in the image, but are not content dividers.
            if rect.width > bounds.width*.95 and rect.height > bounds.height*.95:
                continue
            graphics.append(rect)
        graphics = [r for r in graphics if not r.is_empty]
        obstacles += graphics
        for protected in protected_pages:
            if protected['page'] == n:
                obstacles += [displayed(region['bbox']) for region in protected['regions']]
                graphics += [displayed(region['bbox']) for region in protected['regions'] if region['kind']=='table']
        obstacles += [fitz.Rect(p['bbox']) for p in paragraphs if p['bbox'] and not (
            fitz.Rect(p['bbox']).height > bounds.height*.3 and fitz.Rect(p['bbox']).width < 30)]

        # Long labels inside a full-width figure are not column evidence. Their
        # irregular x positions can move the median gutter into the right body
        # column, turning every overlapping paragraph into a spanning obstacle.
        # Classification is already available here; keep all labels in the
        # original pixels but use only translatable prose to locate the gutter.
        body = [p for p in paragraphs if p['bbox'] and len(p['text']) >= 70
                and p.get('translatable', True) and p.get('translationKind', 'text') == 'text']
        gutter = infer_gutter([p['bbox'] for p in body],bounds.width) if page.rotation in (0,180) else None

        zones = []
        if gutter is None:
            zones.append((0, bounds.height, False))
        else:
            wide = safe_spanning_intervals([(r.y0, r.y1) for r in obstacles if r.x0 < gutter-2 and r.x1 > gutter+2],obstacles)
            cursor = 0
            for lo, hi in wide:
                if lo > cursor:
                    zones.append((cursor, lo, True))
                zones.append((lo, hi, False))
                cursor = hi
            if cursor < bounds.height:
                zones.append((cursor, bounds.height, True))
        used = set()

        def column_tiles(x0, y0, x1, y1):
            region = fitz.Rect(x0,y0,x1,y1)
            relevant = [r & region for r in obstacles if r.intersects(region)]
            intervals = merged_intervals([(r.y0, r.y1) for r in relevant])
            cuts = [y0] + [(a[1]+b[0])/2 for a,b in zip(intervals,intervals[1:])] + [y1]
            tiles = []
            for top,bottom in zip(cuts,cuts[1:]):
                if bottom-top < .01:
                    continue
                rect = fitz.Rect(x0,top,x1,bottom)
                ids = []
                boxes = []
                for p in paragraphs:
                    if not p['bbox'] or p['id'] in used:
                        continue
                    box = fitz.Rect(p['bbox'])
                    cx,cy = (box.x0+box.x1)/2,(box.y0+box.y1)/2
                    if x0 <= cx < x1 and top <= cy < bottom:
                        ids.append(p['id']); boxes.append(box); used.add(p['id'])
                # Align the translation with the original text's left/right margins.
                pad_left = max(0,min(b.x0 for b in boxes)-x0)/(x1-x0) if boxes else .04
                pad_right = max(0,x1-max(b.x1 for b in boxes))/(x1-x0) if boxes else .04
                visible = fitz.Rect(rect)
                content = [r & rect for r in obstacles if r.intersects(rect)]
                if content:
                    if top == 0:
                        visible.y0 = max(top,min(r.y0 for r in content)-8)
                    if bottom == bounds.height:
                        visible.y1 = min(bottom,max(r.y1 for r in content)+8)
                tiles.append({'rect':list(rect),'displayRect':list(visible),'paragraphIds':ids,
                              'padding':[min(pad_left,.35),min(pad_right,.35)],
                              'hasGraphics':any(r.intersects(rect) for r in graphics)})
            return tiles

        rows = []
        for top,bottom,two in zones:
            if bottom-top < .01:
                continue
            columns = [column_tiles(0,top,gutter,bottom),column_tiles(gutter,top,bounds.width,bottom)] if two else [column_tiles(0,top,bounds.width,bottom)]
            rows.append({'columns':columns})
        pages.append({'page':n,'width':bounds.width,'height':bounds.height,'twoColumns':gutter is not None,
                      'rows':rows,'unplacedIds':[p['id'] for p in paragraphs if p['id'] not in used],
                      'visuals':build_visuals(page,protected_regions)})
    return {'version':VERSION,'pages':pages}
