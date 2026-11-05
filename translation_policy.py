"""Identify prose to translate without rebuilding or renumbering PDF paragraphs.

All geometry stays in MuPDF's unrotated page coordinates. Formula/figure regions
also act as indivisible obstacles in the bilingual page partitioner.
"""
from collections import defaultdict, deque
import hashlib
import re
import pymupdf as fitz
from pdf_geometry import drawing_has_ink, infer_gutter, column_of

VERSION = 3
MATH_FONT = re.compile(r'(?:CMMI|CMSY|CMEX|MSAM|MSBM|MATH|SYMBOL|MTEX|STIX.*(?:SY|EX))', re.I)
CAPTION = re.compile(r'^\s*(?:fig(?:ure)?\.?\s*\d+|图\s*\d+)', re.I)
EQUATION_NUMBER = re.compile(r'^\s*[（(]\s*\d{1,3}[a-z]?\s*[）)]\s*[,.;]?\s*$', re.I)


def normalized(text):
    text = re.sub(r'(\w)-\s*\n(\w)', r'\1\2', text)
    return re.sub(r'\s+', ' ', text).strip()


def line_key(line):
    return tuple(round(v, 2) for v in line['bbox']), ''.join(s['text'] for s in line['spans']).strip()


def near(a, b, dx, dy):
    return a.x0 <= b.x1+dx and b.x0 <= a.x1+dx and a.y0 <= b.y1+dy and b.y0 <= a.y1+dy


def union_regions(rects, dx=0, dy=0, gutter=None):
    result = []
    for source in rects:
        box = fitz.Rect(source)
        i = 0
        while i < len(result):
            if column_of(box,gutter) == column_of(result[i],gutter) and near(box, result[i], dx, dy):
                box |= result.pop(i); i = 0
            else:
                i += 1
        result.append(box)
    return result


def formula_line(line):
    text = ''.join(s['text'] for s in line['spans']).strip()
    if not text:
        return False
    if re.search(r'https?://|www\.|@',text) or re.fullmatch(r'[\s\d.,%±+\-−–()]+',text):
        return False
    # Some tagged PDFs expose fragments of LaTeX as glyphs' ActualText. A long
    # English sentence inside a cases environment is still part of the equation.
    if re.search(r'\\\s*(?:label|tag|begin|end)\s*\{', text):
        return True
    total = sum(len(s['text'].strip()) for s in line['spans']) or 1
    math = sum(len(s['text'].strip()) for s in line['spans'] if MATH_FONT.search(s['font']))
    plain = ' '.join(s['text'] for s in line['spans'] if not MATH_FONT.search(s['font']))
    words = re.findall(r'[A-Za-z]{3,}', plain)
    cjk = re.findall(r'[\u3400-\u9fff]', plain)
    # Preserve prose with inline variables, references, and explanatory clauses.
    prose_words = [w for w in words if w.lower() not in {'sin','cos','tan','log','exp','max','min','lim','arg','sum','frac','sqrt','text','left','right'}]
    if re.search(r'\b(?:here|where|resulting|denotes|given|using)\b',plain,re.I):
        return False
    if len(prose_words)<=3 and len(cjk)<6 and re.match(r'^[A-Za-z][A-Za-z0-9_′’]*(?:\([^)]*\))?\s*=',text):
        return True  # A displayed assignment such as MHSA(U) = Concat(...).
    if len(words) >= 4 or len(cjk) >= 6 or (len(prose_words) >= 2 and sum(map(len,prose_words)) >= 9):
        return False
    if math/total >= .35:
        return True
    if re.search(r'\b(?:sin|cos|tan|log|exp|max|min|lim)\s*\(',text) and not prose_words:
        return True
    operators = re.findall(r'[=+−∑∫√±≈≠≤≥∈∞∂∇]|\\[A-Za-z]+|[_^{}]', text)
    if operators and len(words) <= 2 and len(cjk) < 3:
        return True
    return False


def weighted_font_size(lines, default=10):
    samples = sorted((span['size'],len(span['text'].strip())) for line in lines for span in line['spans'] if span['text'].strip())
    halfway = sum(weight for _,weight in samples)/2
    for size,weight in samples:
        halfway -= weight
        if halfway <= 0:
            return size
    return default


def margin_pattern(text):
    """Ignore changing page numbers, including opposite odd/even placement."""
    text = normalized(text).casefold()
    number = r'(?:\d+|[ivxlcdm]+)'
    text = re.sub(r'^(?:page\s+)?'+number+r'\b(?:\s+(?:of|/)\s*\d+)?[\s|·–—-]*','',text)
    text = re.sub(r'\s+(?:page\s+)?'+number+r'(?:\s*(?:of|/)\s*\d+)?\s*$','',text)
    return text.strip() or '#'


def mark_running_margins(pdf, analyses):
    """Recognize recurring outer rows, not everything near the top of a page.

    Require a gap to body text, compatible size/style, recurrence on separate
    pages, and the same vertical position. The first-page title and body headings
    therefore remain prose even when they contain the running header's words.
    """
    body_lines = [line for page,(lines,kinds,_) in zip(pdf,analyses) for line in lines
                  if kinds[line_key(line)] == 'text' and len(line_key(line)[1]) >= 35
                  and page.cropbox.height*.18 < line['bbox'][1] < page.cropbox.height*.82]
    body_size = weighted_font_size(body_lines)
    patterns = defaultdict(list)
    for index,(page,(lines,kinds,_)) in enumerate(zip(pdf,analyses)):
        height = page.cropbox.height
        page_body = [line for line in lines if kinds[line_key(line)] == 'text' and len(line_key(line)[1]) >= 35
                     and height*.18 < line['bbox'][1] < height*.82]
        font_size = weighted_font_size(page_body,body_size)
        rows = []
        for line in sorted(lines,key=lambda line:(line['bbox'][1],line['bbox'][0])):
            if abs(line.get('dir',(1,0))[0]) < .9:
                continue  # Vertical margin stamps are not running header rows.
            rect = fitz.Rect(line['bbox'])
            if rows and abs((rect.y0+rect.y1)/2-(rows[-1]['rect'].y0+rows[-1]['rect'].y1)/2) < min(rect.height,rows[-1]['rect'].height)*.4:
                rows[-1]['rect'] |= rect; rows[-1]['lines'].append(line)
            else:
                rows.append({'rect':rect,'lines':[line]})
        for side in ('header','footer'):
            for count in range(1,min(3,len(rows)-1)+1):
                outer = rows[:count] if side=='header' else rows[-count:]
                rect = fitz.Rect(outer[0]['rect'])
                for row in outer[1:]:rect |= row['rect']
                if (side=='header' and rect.y1 > height*.18) or (side=='footer' and rect.y0 < height*.82) or rect.height > height*.055:
                    break
                members = [line for row in outer for line in sorted(row['lines'],key=lambda line:line['bbox'][0])]
                if any(kinds[line_key(line)] not in ('text','page-marker') for line in members):
                    break
                spans = [span for line in members for span in line['spans'] if span['text'].strip()]
                largest = max(span['size'] for span in spans)
                if largest > font_size*1.08 or any((span.get('flags',0)&16 or re.search(r'bold|sfbx|cmbx',span['font'],re.I)) and span['size'] >= font_size*.98 for span in spans):
                    break
                gap = rows[count]['rect'].y0-rect.y1 if side=='header' else rect.y0-rows[-count-1]['rect'].y1
                if gap < max(6,largest*.8):
                    continue
                text = ' '.join(line_key(line)[1] for line in members)
                if len(text) > 220:
                    break
                pattern = margin_pattern(text)
                patterns[(side,pattern)].append({'page':index,'position':rect.y0/height,'size':largest,'lines':members})
                break
    for (side,pattern),candidates in patterns.items():
        for candidate in candidates:
            peers = {other['page'] for other in candidates if abs(other['position']-candidate['position']) <= .012
                     and abs(other['size']-candidate['size']) <= 1}
            if len(peers) < 2 and pattern != '#':
                continue
            kinds = analyses[candidate['page']][1]
            for line in candidate['lines']:
                kinds[line_key(line)] = side


def page_policy(page):
    lines = [line for block in page.get_text('dict', flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']
             if block['type'] == 0 for line in block['lines'] if line_key(line)[1]]
    bounds = fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
    candidates = []
    for image in page.get_image_info():
        r = fitz.Rect(image['bbox']) & bounds
        # A scanned full-page image is not a figure: its OCR prose must remain usable.
        if r.width >= 8 and r.height >= 8 and r.get_area() < bounds.get_area()*.8:
            candidates.append(r)
    for drawing in page.get_drawings():
        if not drawing_has_ink(drawing):
            continue
        r = drawing['rect'] & bounds
        # Exclude text outlines, equation rules, page borders and page backgrounds.
        if r.width >= 25 and r.height >= 20 and r.get_area() < bounds.get_area()*.8:
            candidates.append(r)
    figures = union_regions(candidates, 8, 8)
    captions = [fitz.Rect(line['bbox']) for line in lines if CAPTION.match(line_key(line)[1])]
    for caption in captions:
        above = [r for r in figures if r.y1 <= caption.y0+1 and 0 <= caption.y0-r.y1 < 45
                 and min(r.x1,caption.x1)-max(r.x0,caption.x0) > min(r.width,caption.width)*.25]
        if above:
            # Capture axis labels and panel headings around the artwork, while
            # never consuming the separately translated figure caption.
            for r in above:
                r.y0 = max(0, r.y0-12); r.y1 = max(r.y1, caption.y0-2)
                r.x0 = max(0, r.x0-5); r.x1 = min(bounds.x1, r.x1+5)
    figures = union_regions(figures)
    kinds = {}
    for line in lines:
        key = line_key(line); r = fitz.Rect(line['bbox']); text = key[1]
        if CAPTION.match(text):
            kind = 'text'
        elif any((r & region).get_area() >= r.get_area()*.7 for region in figures):
            kind = 'figure'
        elif formula_line(line):
            kind = 'formula'
        elif text.isdigit() and (r.y0 < bounds.height*.15 or r.y1 > bounds.height*.85):
            kind = 'page-marker'
        else:
            kind = 'text'
        kinds[key] = kind
    # A subscript may be extracted as its own line next to prose. Its geometry
    # must not turn the containing explanatory paragraph into an equation.
    prose_lines = [line for line in lines if kinds[line_key(line)] == 'text'
                   and (len(re.findall(r'[A-Za-z]{3,}',line_key(line)[1])) >= 3 or len(re.findall(r'[\u3400-\u9fff]',line_key(line)[1])) >= 6)]
    gutter = infer_gutter([line['bbox'] for line in prose_lines if len(line_key(line)[1]) >= 35],bounds.width,minimum=3)
    def same_column(a,b):
        return column_of(a,gutter)==column_of(b,gutter)
    for line in lines:
        key=line_key(line);r=fitz.Rect(line['bbox'])
        if kinds[key] != 'formula' or len(key[1]) > 20:
            continue
        for prose in prose_lines:
            b=fitz.Rect(prose['bbox'])
            if same_column(r,b) and min(r.y1,b.y1)-max(r.y0,b.y0) > min(r.height,b.height)*.2 and near(r,b,22,0):
                kinds[key]='text';break
    # A wrapped, math-heavy line inside a prose paragraph is not a display
    # equation. Require prose immediately above AND below within the same column.
    for line in lines:
        key=line_key(line);r=fitz.Rect(line['bbox'])
        if kinds[key]!='formula' or r.width < (bounds.width if gutter is None else bounds.width/2)*.55:
            continue
        neighbors=[fitz.Rect(p['bbox']) for p in prose_lines if same_column(r,fitz.Rect(p['bbox']))]
        above=any(-1 <= r.y0-b.y1 <= 3 and min(r.x1,b.x1)-max(r.x0,b.x0) > r.width*.6 for b in neighbors)
        below=any(-1 <= b.y0-r.y1 <= 3 and min(r.x1,b.x1)-max(r.x0,b.x0) > r.width*.6 for b in neighbors)
        if above and below:
            kinds[key]='text'
    # Join superscripts, equation numbers, and isolated glyphs to their equation.
    # Use a small horizontal tolerance to avoid consuming the neighboring column.
    equations = union_regions([line['bbox'] for line in lines if kinds[line_key(line)] == 'formula'], 35, 8, gutter)
    for line in lines:
        key = line_key(line); text = key[1]; r = fitz.Rect(line['bbox'])
        short_fragment = bool(re.fullmatch(r'[\d\W_]{1,12}|[A-Za-z]{1,4}|otherwise', text))
        equation_number = EQUATION_NUMBER.fullmatch(text) and any(same_column(r,eq) and near(r,eq,bounds.width*.4,5) for eq in equations)
        inline = any(same_column(r,b) and min(r.y1,b.y1)-max(r.y0,b.y0) > min(r.height,b.height)*.2 and near(r,b,22,0)
                     for prose in prose_lines if prose is not line for b in [fitz.Rect(prose['bbox'])])
        if kinds[key] == 'text' and not inline and (equation_number or short_fragment and any(same_column(r,eq) and near(r,eq,8,5) for eq in equations)):
            kinds[key] = 'formula'; equations.append(r)
    equations = union_regions(equations,35,8,gutter)
    return lines, kinds, [{'kind':'figure','bbox':list(r)} for r in figures] + [{'kind':'formula','bbox':list(r)} for r in equations]


def build_policy(pdf, stored, fresh):
    locations = defaultdict(deque)
    for p in fresh:
        locations[(p['page'],p['text'])].append(p)
    by_page = defaultdict(list)
    for p in stored:
        matches = locations[(p['page'],p['text'])]
        by_page[p['page']].append((p, matches.popleft() if matches else p))
    result = {'version':VERSION, 'paragraphs':{}, 'pages':[]}
    analyses = [page_policy(page) for page in pdf]
    mark_running_margins(pdf,analyses)
    for number,(lines,kinds,regions) in enumerate(analyses,1):
        result['pages'].append({'page':number,'regions':regions})
        for p,geometry in by_page[number]:
            matched = geometry.get('_lines')
            if matched is None:
                box = fitz.Rect(geometry['bbox']) if geometry.get('bbox') else None
                compact = re.sub(r'[\s-]+','',p['text'])
                matched = [line for line in lines if (not box or box.intersects(fitz.Rect(line['bbox'])))
                           and re.sub(r'[\s-]+','',line_key(line)[1]) in compact]
            skip_kinds = {'formula','figure','header','footer'}
            if matched and all(kinds.get(line_key(line)) == 'page-marker' for line in matched):
                skip_kinds.add('page-marker')
            skipped = [(line,kinds.get(line_key(line),'text')) for line in matched if kinds.get(line_key(line),'text') in skip_kinds]
            translatable = not matched or len(skipped) < len(matched)
            kind = 'text' if translatable else next((kind for kind in ('header','footer','figure','formula') if any(k==kind for _,k in skipped)),'page-marker')
            source = p['text']
            if translatable and skipped:
                # Keep IDs and original extraction intact; remove only recognized
                # non-prose lines from the text sent to the translation service.
                for line,_ in skipped:
                    fragment = normalized(line_key(line)[1])
                    source = source.replace(fragment,' ',1)
                source = normalized(source)
            if not source:
                translatable = False
            result['paragraphs'][p['id']] = {
                'translatable':translatable, 'translationKind':kind,
                'translationSource':source,
                'translationSourceHash':hashlib.sha256(source.encode()).hexdigest(),
            }
    return result
