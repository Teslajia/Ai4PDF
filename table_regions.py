"""Keep a table and its caption together without changing paragraph identities."""
import re

import pymupdf as fitz
from pdf_geometry import infer_gutter

TABLE_CAPTION = re.compile(r'^\s*(?:(?:table|tab\.)\s+(?:\d+[A-Za-z]?|[IVXLCDM]+)\b|[表표]\s*\d+)', re.I)


def text(line):
    return ''.join(span['text'] for span in line['spans']).strip()


def overlap(a, b):
    return max(0, min(a.x1,b.x1)-max(a.x0,b.x0)) / max(1,min(a.width,b.width))


def borderless_tables(lines, caption, height, width):
    """Conservative fallback: several aligned rows with numeric result cells."""
    c=fitz.Rect(caption['bbox'])
    gutter=infer_gutter([line['bbox'] for line in lines if len(text(line))>=45],width,minimum=3)
    left=gutter if gutter and c.x0>=gutter else 0
    right=gutter if gutter and c.x1<=gutter else width
    rows=[]
    for line in sorted(lines,key=lambda l:(l['bbox'][1],l['bbox'][0])):
        r=fitz.Rect(line['bbox'])
        if not c.y1 < r.y0 < min(height,c.y1+320) or r.x0<left or r.x1>right:
            continue
        # PDF producers sometimes put all cells on one line: split wide span gaps.
        cells=[]
        for span in line['spans']:
            s=fitz.Rect(span['bbox']);value=span['text'].strip()
            if not value:continue
            if cells and s.x0-cells[-1][0].x1 < span['size']*1.5:
                cells[-1]=(cells[-1][0]|s,cells[-1][1]+' '+value)
            else:cells.append((s,value))
        cy=(r.y0+r.y1)/2
        row=next((row for row in rows if abs(row['cy']-cy)<max(2,r.height*.35)),None)
        if row is None:
            row={'cy':cy,'rect':r,'cells':[]};rows.append(row)
        row['cells'].extend(cells);row['rect']|=r
    groups=[];current=[]
    for row in rows:
        cells=sorted(row['cells'],key=lambda item:item[0].x0)
        row['cells']=cells
        eligible=len(cells)>=2 and all(len(value)<90 for _,value in cells)
        if current and (not eligible or row['rect'].y0-current[-1]['rect'].y1>24):
            groups.append(current);current=[]
        if eligible:current.append(row)
    if current:groups.append(current)
    found=[]
    for group in groups:
        numeric=[row for row in group if sum(bool(re.search(r'\d',value)) for _,value in row['cells'][1:])>=1]
        if len(group)<3 or len(numeric)<2 or group[0]['rect'].y0-c.y1>85:
            continue
        anchors=[r.x0 for r,_ in numeric[0]['cells']]
        aligned=sum(sum(any(abs(r.x0-x)<=12 for x in anchors) for r,_ in row['cells'])>=2 for row in numeric)
        if aligned<2:continue
        box=fitz.Rect(group[0]['rect'])
        for row in group[1:]:box|=row['rect']
        found.append(box)
    return found


def captioned_tables(page,lines):
    captions=[line for line in lines if TABLE_CAPTION.match(text(line))]
    if not captions:return [],[],set()
    bodies=[]
    rotation=page.rotation
    try:
        # Table detection uses the displayed orientation; prose extraction uses
        # unrotated coordinates. Normalize only this in-memory page operation.
        page.set_rotation(0)
        for table in page.find_tables().tables:
            if table.col_count<2 or table.row_count<2:continue
            body=fitz.Rect(table.bbox)
            header=fitz.Rect(table.header.bbox)
            if not any(header.intersects(fitz.Rect(c['bbox'])) for c in captions):body|=header
            bodies.append(body)
    except (ValueError,RuntimeError):
        pass  # A malformed drawing must not prevent the page from being read.
    finally:
        page.set_rotation(rotation)
    for caption in captions:
        for body in borderless_tables(lines,caption,page.cropbox.height,page.cropbox.width):
            if not any((body&other).get_area()>=body.get_area()*.7 for other in bodies):bodies.append(body)
    regions=[];caption_lines=set();matched=[]
    for caption in captions:
        c=fitz.Rect(caption['bbox'])
        candidates=[]
        for body in bodies:
            gap=body.y0-c.y1 if body.y0>=c.y1 else c.y0-body.y1
            if 0<=gap<=85 and overlap(c,body)>=.4:
                candidates.append((gap,body))
        if not candidates:continue
        _,body=min(candidates,key=lambda item:item[0])
        group=[caption];caption_box=fitz.Rect(c)
        # Include wrapped caption lines, on either side of a table, without
        # absorbing the neighboring column or following body paragraph.
        for line in sorted(lines,key=lambda line:line['bbox'][1]):
            r=fitz.Rect(line['bbox'])
            if line is caption or r.y0<c.y1-.5 or r.intersects(body):continue
            if body.y0>=c.y1 and r.y1>body.y0:continue
            if r.y0-caption_box.y1>max(5,c.height*.6) or overlap(c,r)<.65:continue
            if TABLE_CAPTION.match(text(line)):break
            if len(group)>=6 or r.y1-c.y0>90:break
            group.append(line);caption_box|=r
        region=body|caption_box
        if region.get_area()>page.cropbox.get_area()*.8:continue
        regions.append({'kind':'table','bbox':list(region),'bodyBbox':list(body)})
        matched.append(body)
        caption_lines.update((tuple(round(v,2) for v in line['bbox']),text(line)) for line in group)
    return matched,regions,caption_lines
