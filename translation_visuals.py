"""Original artwork to retain in the translated reading view."""
import hashlib
import json
import re

import pymupdf as fitz
from pdf_geometry import column_of, infer_gutter


def join_equation_numbers(page,regions):
    """Keep a detached right-hand equation number in its equation's crop."""
    formulas=[dict(r) for r in regions if r['kind']=='formula']
    if not formulas:return regions
    textpage=page.get_textpage()
    numbers=[r for r in formulas if re.fullmatch(r'\(\s*[A-Za-z]?\d+(?:[.\-]\d+)*[a-z]?\s*\)',page.get_textbox(fitz.Rect(r['bbox'])+(-.5,-.5,.5,.5),textpage=textpage).strip())]
    if not numbers:return regions
    blocks=page.get_text('blocks',textpage=textpage)
    gutter=infer_gutter([b[:4] for b in blocks if b[6]==0 and len(b[4].strip())>=35],page.cropbox.width,minimum=3)
    for number in numbers:
        n=fitz.Rect(number['bbox']);matches=[]
        for body in formulas:
            if body in numbers:continue
            r=fitz.Rect(body['bbox'])
            overlap=min(n.y1,r.y1)-max(n.y0,r.y0)
            gap=n.x0-r.x1
            if column_of(r,gutter)==column_of(n,gutter) and overlap>=min(n.height,r.height)*.5 and -2<=gap<=page.cropbox.width*.35:
                matches.append((max(0,gap),body,r))
        if matches:
            _,body,r=min(matches,key=lambda item:item[0])
            body['bbox']=list(r|n);formulas.remove(number)
    return [r for r in regions if r['kind']!='formula']+formulas


def build_visuals(page,regions):
    candidates=[]
    for region in join_equation_numbers(page,regions):
        kind=region['kind']
        if kind not in ('figure','table','formula'):continue
        # The table's protected region also includes its caption. Only retain
        # the body as an image; the caption already has its own translated text.
        source=fitz.Rect(region.get('bodyBbox',region['bbox']))
        rect=source*page.rotation_matrix
        rect=(rect+(-1,-1,1,1))&page.rect
        if rect.width<1 or rect.height<1:continue
        candidates.append((kind,rect))
    candidates.sort(key=lambda value:({'table':0,'figure':1,'formula':2}[value[0]],-value[1].get_area()))
    visuals=[]
    for kind,rect in candidates:
        # Table rules may also form a detected vector figure; formulas can be
        # embedded inside a figure. Show the original content only once.
        if any((rect&other).get_area()>=min(rect.get_area(),other.get_area())*.85 for _,other in visuals):continue
        visuals.append((kind,rect))
    result=[]
    for kind,rect in sorted(visuals,key=lambda value:(value[1].y0,value[1].x0)):
        coordinates=[round(v,4) for v in rect]
        identity=hashlib.sha256(json.dumps([kind,coordinates]).encode()).hexdigest()[:16]
        result.append({'id':'v'+identity,'kind':kind,'rect':coordinates})
    return result
