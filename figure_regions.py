"""Caption-guided artwork regions, including labels outside vector paths."""
import re

import pymupdf as fitz
from pdf_geometry import visible_drawings, infer_gutter, column_of

CAPTION = re.compile(r'^\s*(?:fig(?:ure)?\.?\s*\d+|[图圖図]\s*\d+|그림\s*\d+)',re.I)


def text(line):
    return ''.join(span['text'] for span in line['spans']).strip()


def close(a,b,gap=8):
    return a.x0<=b.x1+gap and b.x0<=a.x1+gap and a.y0<=b.y1+gap and b.y0<=a.y1+gap


def merged(rects,gutter=None):
    result=[]
    for rect in rects:
        box=fitz.Rect(rect);index=0
        while index<len(result):
            if column_of(box,gutter)==column_of(result[index],gutter) and close(box,result[index]):
                box|=result.pop(index);index=0
            else:index+=1
        result.append(box)
    return result


def figure_regions(page,lines,font_size):
    bounds=fitz.Rect(0,0,page.cropbox.width,page.cropbox.height)
    prose=[line for line in lines if len(text(line))>=35 and max(s['size'] for s in line['spans'])>=font_size*.85]
    gutter=infer_gutter([line['bbox'] for line in prose],bounds.width,minimum=3)
    cores=[];thin=[];axes=[]
    for image in page.get_image_info():
        r=fitz.Rect(image['bbox'])&bounds
        if r.width>=8 and r.height>=8 and r.get_area()<bounds.get_area()*.8:cores.append(r)
    for drawing in visible_drawings(page):
        raw=fitz.Rect(drawing['rect'])
        if raw.width>=bounds.width*.95 and raw.height>=bounds.height*.95:continue
        r=(raw+(-.3,-.3,.3,.3))&bounds
        if r.get_area()>=bounds.get_area()*.8:continue
        if raw.width>=25 and raw.height>=20:cores.append(r)
        elif raw.width>=25 or raw.height>=20:
            thin.append(r)
            if raw.width<2 and raw.height>=20:axes.append(r)
    captions=[fitz.Rect(line['bbox']) for line in lines if CAPTION.match(text(line))]
    # A graph may contain only separate strokes, with no image or large path.
    # Require a vertical axis and numeric ticks, or a nearby caption, before
    # promoting a stroke cluster. Fraction rules and underlines alone do not count.
    for group in merged(thin,gutter):
        if group.width<25 or group.height<20:continue
        ticks=sum(bool(re.fullmatch(r'[−+\-]?\d+(?:\.\d+)?%?',text(line))) and close(group,fitz.Rect(line['bbox']),22) for line in lines)
        caption=any(0<=c.y0-group.y1<45 and min(c.x1,group.x1)>max(c.x0,group.x0) for c in captions)
        if (ticks>=2 and any(group.contains(a) for a in axes)) or caption:
            band=(group+(-max(24,font_size*4),-10,14,16))&bounds
            if gutter:
                if column_of(group,gutter)==1:band.x0=max(band.x0,gutter)
                elif column_of(group,gutter)==0:band.x1=min(band.x1,gutter)
            for line in lines:
                r=fitz.Rect(line['bbox'])
                if (band&r).get_area()>=r.get_area()*.9 and len(text(line))<=30 and line not in prose and not CAPTION.match(text(line)):
                    if max(s['size'] for s in line['spans'])<=font_size and not any(s.get('flags',0)&16 for s in line['spans']):group|=r
            cores.append(group)
    figures=merged(cores,gutter)

    def barrier(region,caption):
        for line in prose:
            r=fitz.Rect(line['bbox'])
            if r.y0>=caption.y0-1 or r.y1<=region.y0+1:continue
            overlap=(r&region).get_area()/max(1,r.get_area())
            if overlap>.5:return True
        # Other main captions must not be swallowed when extending upward.
        return any(c!=caption and c.y0>=region.y0 and c.y1<caption.y0 and c.intersects(region) for c in captions)

    for caption in captions:
        candidates=[r for r in figures if r.y1<=caption.y0+1 and caption.y0-r.y1<55
                    and min(r.x1,caption.x1)-max(r.x0,caption.x0)>min(r.width,caption.width)*.25
                    and not barrier(r|fitz.Rect(r.x0,r.y1,r.x1,caption.y0),caption)]
        if not candidates:continue
        seed=min(candidates,key=lambda r:caption.y0-r.y1)
        region=fitz.Rect(seed);members=[seed]
        column=column_of(region,gutter)
        left=0 if gutter is None or column!=1 else gutter
        right=bounds.width if gutter is None or column!=0 else gutter
        # Assemble panels across the caption's column, with prose as a hard stop.
        changed=True
        while changed:
            changed=False
            for r in figures:
                if r in members or r.y1>caption.y0+1 or r.x0<left or r.x1>right:continue
                if r.y1<region.y0-28 or r.y0>region.y1+28:continue
                candidate=region|r
                if candidate.height>bounds.height*.65 or barrier(candidate,caption):continue
                if min(r.x1,caption.x1)<=max(r.x0,caption.x0):continue
                region=candidate;members.append(r);changed=True
        # Text labels belong to the complete figure, not only to the pixels
        # inside an image / plotted curve. Keep the following caption separate.
        band=fitz.Rect(max(left,min(region.x0-22,caption.x0)),max(0,region.y0-8),
                       min(right,max(region.x1+12,caption.x1)),caption.y0-.5)
        for line in lines:
            r=fitz.Rect(line['bbox']);value=text(line)
            if CAPTION.match(value) or not band.contains(r):continue
            if line in prose:continue
            if max(s['size'] for s in line['spans'])>font_size*1.1:continue
            region|=r
        for r in members:figures.remove(r)
        figures.append(region)
    return figures
