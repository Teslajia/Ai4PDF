"""Conservative numbered bibliography index; PDF text and bytes stay untouched."""
import re

import pymupdf as fitz
from pdf_geometry import infer_gutter

VERSION = 2
HEADING = re.compile(r'^(?:\d+[.\s]*)?(?:references|bibliography|参考文献|參考文獻|参考文獻|참고\s*문헌)\s*[:：]?$', re.I)
ENTRY = re.compile(r'^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.、])\s*(\S.*)')
CITATION = re.compile(r'\[(\d{1,4}(?:\s*[,，;；–—-]\s*\d{1,4})*)\]')
STOP = re.compile(r'^(?:[A-Z\d]+[.\s]+)?(?:appendix|appendices|supplementary material|附录|附錄|付録|부록)\b', re.I)


def numbers(text):
    result = []
    for part in re.split(r'[,，;；]', text):
        ends = re.split(r'[–—-]', part.strip())
        a, b = int(ends[0]), int(ends[-1])
        if 0 < a <= b <= a + 100:
            result.extend(range(a, b + 1))
    return list(dict.fromkeys(result))


def normalized(page, rect):
    r = fitz.Rect(rect) * page.rotation_matrix
    return [r.x0/page.rect.width, r.y0/page.rect.height, r.x1/page.rect.width, r.y1/page.rect.height]


def build_references(pdf):
    pages = []
    for page in pdf:
        lines = []
        for block in page.get_text('dict', flags=fitz.TEXTFLAGS_TEXT)['blocks']:
            for line in block.get('lines', []):
                text = ''.join(s['text'] for s in line['spans']).strip()
                if text:
                    lines.append((text, line['bbox']))
        gutter=infer_gutter([bbox for text,bbox in lines if len(text)>30],page.cropbox.width,minimum=3)
        pages.append(sorted(lines, key=lambda item:(bool(gutter and item[1][0]>gutter),round(item[1][1],1),item[1][0])))
    entries, ambiguous, active = {}, set(), False
    for index, lines in enumerate(pages):
        for text, bbox in lines:
            if HEADING.fullmatch(text):
                active = True
                continue
            if active and STOP.match(text):
                active = False
            match = ENTRY.match(text) if active else None
            if not match or len(match[3]) < 8:
                continue
            label = str(int(match[1] or match[2]))
            if label in entries:
                ambiguous.add(label)
                continue
            entries[label] = {'id':label, 'page':index+1, 'rect':normalized(pdf[index], bbox), 'text':text[:500]}
    for label in ambiguous:
        entries.pop(label, None)
    citations = {}
    for index, lines in enumerate(pages):
        page, hits = pdf[index], []
        for text, bbox in lines:
            for match in CITATION.finditer(text):
                ids = [str(n) for n in numbers(match[1]) if str(n) in entries]
                if not ids:
                    continue
                # Bibliography labels themselves are destinations, not self-links.
                if match.start() == 0 and any(entries[n]['page']==index+1 and abs(entries[n]['rect'][1]-normalized(page,bbox)[1])<.002 for n in ids):
                    continue
                for rect in page.search_for(match[0], clip=fitz.Rect(bbox)+(-1,-1,1,1)):
                    hit = {'ids':ids, 'rect':normalized(page, rect)}
                    if hit not in hits:
                        hits.append(hit)
        citations[str(index+1)] = hits
    return {'version':VERSION, 'entries':entries, 'citations':citations}
