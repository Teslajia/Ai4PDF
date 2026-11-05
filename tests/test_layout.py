import io
import json
import math
import sys
from pathlib import Path

import pymupdf as fitz
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server
from layout import safe_spanning_intervals


def illustrated_pdf(rotation=0):
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    page.insert_text((65,55),'A paper with figures and mathematics',fontsize=21)
    bitmap=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,100,45))
    bitmap.set_rect(bitmap.irect,(225,80,60))
    page.insert_image(fitz.Rect(60,85,540,205),stream=bitmap.tobytes('png'),keep_proportion=False)
    page.draw_rect(fitz.Rect(70,110,160,170),color=(0,.2,.7),fill=(.1,.3,.8))
    page.insert_text((65,225),'Figure 1. Raster image and vector graphics.',fontsize=11)
    page.insert_text((240,253),'E = mc',fontsize=17)
    page.insert_text((296,246),'2',fontsize=10)
    page.draw_line((238,260),(312,260),color=(0,0,0))
    for x,label in [(45,'Left'),(320,'Right')]:
        for i,y in enumerate([300,405,510]):
            text=f'{label} paragraph {i+1}. This paragraph explains the method and its assumptions. Original equations and figures should remain intact when translations are inserted into this document.'
            assert page.insert_textbox(fitz.Rect(x,y,x+235,y+90),text,fontsize=10)>0
    page.insert_text((290,770),'1',fontsize=10)
    page.set_rotation(rotation)
    content=pdf.tobytes();pdf.close()
    return content


def narrow_gutter_pdf():
    pdf=fitz.open();page=pdf.new_page(width=612,height=792)
    page.insert_text((220,385),'L(x) = u',fontsize=12)
    page.insert_text((288,385),'(1)',fontsize=10)
    page.insert_text((48,30),'Running heading',fontsize=8)
    page.insert_text((558,30),'1',fontsize=8)
    for i,y in enumerate([60,180,310,425,570]):
        text=f'Left body paragraph {i+1}. This paragraph explains the method and assumptions. The explanation belongs to the left column and must remain intact when translations are inserted. It continues across several original lines.'
        assert page.insert_textbox(fitz.Rect(48,y,300,y+110),text,fontsize=10)>0
    # A white backing sheet crosses the gutter, although the visible figure does not.
    page.draw_rect(fitz.Rect(297,42,584,172),fill=(1,1,1),color=None)
    page.draw_rect(fitz.Rect(338,65,540,150),fill=(.2,.4,.8),color=(.2,.4,.8))
    page.insert_textbox(fitz.Rect(312,185,564,230),'Fig. 1: A diagram inside the right column. Its white backing rectangle must not span the neighboring text.',fontsize=10)
    page.insert_textbox(fitz.Rect(312,255,564,335),'Right body paragraph. The explanation introduces a sampling method and its properties. All original sentences should remain together before the display equation.',fontsize=10)
    page.insert_textbox(fitz.Rect(312,345,564,390),'The following two equations describe the sampling operation. They are formulated as:',fontsize=10)
    page.insert_text((320,400),'k =',fontsize=12)
    page.insert_text((350,400),'max(0, 1 - x)',fontsize=12)
    page.insert_text((350,420),'max(0, 1 - y)',fontsize=12)
    page.insert_text((320,448),'v =',fontsize=12)
    page.insert_text((350,448),'max(0, 1 - x)',fontsize=12)
    page.insert_text((350,468),'max(0, 1 - y)',fontsize=12)
    page.insert_text((551,434),'(2)',fontsize=10)
    page.insert_textbox(fitz.Rect(312,495,564,560),'Here, the vectors represent the coordinates of the sampled image. This explanation follows the entire equation and should stay in its own column.',fontsize=10)
    page.insert_textbox(fitz.Rect(312,610,564,710),'Another right paragraph explains the results and limitations. The method produces independent values for each location and preserves the original dimensions.',fontsize=10)
    content=pdf.tobytes();pdf.close();return content


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    return server.app.test_client()


@pytest.mark.parametrize('rotation',[0,90])
def test_layout_covers_original_and_preserves_existing_translations(client,rotation):
    original=illustrated_pdf(rotation)
    d=client.post('/api/documents',data={'file':(io.BytesIO(original),'illustrated.pdf')}).json
    path=server.folder(d['id'])
    # Simulate existing library metadata, created before bounding boxes were stored.
    metadata=server.read_doc(d['id'])
    for p in metadata['paragraphs']:p.pop('bbox',None)
    server.write_json(path/'document.json',metadata)
    state=server.state(d['id']);state['translations']['简体中文:'+d['paragraphs'][0]['id']]='已有译文，必须原样保留。'
    server.write_json(path/'state.json',state)
    before=(path/'state.json').read_bytes()
    response=client.get(f"/api/documents/{d['id']}/layout")
    assert response.status_code==200,response.json
    layout=response.json;page=layout['pages'][0]
    assert page['twoColumns']==(rotation==0)
    tiles=[t for row in page['rows'] for col in row['columns'] for t in col]
    area=sum(fitz.Rect(t['rect']).get_area() for t in tiles)
    assert math.isclose(area,page['width']*page['height'],abs_tol=.1)
    for i,a in enumerate(tiles):
        for b in tiles[i+1:]:assert (fitz.Rect(a['rect'])&fitz.Rect(b['rect'])).get_area()<.01
    ids=[pid for t in tiles for pid in t['paragraphIds']]+page['unplacedIds']
    assert sorted(ids)==sorted(p['id'] for p in d['paragraphs'])
    assert any(t['hasGraphics'] for t in tiles)
    assert client.get(f"/api/documents/{d['id']}/layout").json==layout
    assert (path/'state.json').read_bytes()==before
    assert (path/'document.json').read_text(encoding='utf-8')==json.dumps(metadata,ensure_ascii=False)
    image=client.get(f"/api/documents/{d['id']}/pages/1/image")
    assert image.status_code==200 and image.mimetype=='image/png'
    bitmap=fitz.Pixmap(image.data)
    assert bitmap.width>page['width']
    assert bitmap.width*bitmap.height<=4_010_000
    assert client.get(f"/api/documents/{d['id']}/pages/0/image").status_code==404
    assert client.get(f"/api/documents/{d['id']}/pages/2/image").status_code==404
    assert client.get(f"/api/documents/{d['id']}/pdf").data==original


def test_spanning_transitions_cannot_cut_paragraphs():
    boxes=[fitz.Rect(40,90,290,170),fitz.Rect(310,160,550,230),fitz.Rect(40,220,290,260)]
    assert safe_spanning_intervals([(100,120)],boxes)==[[90,260]]


def test_narrow_gutter_keeps_equations_and_prose_in_their_columns(client):
    original=narrow_gutter_pdf()
    d=client.post('/api/documents',data={'file':(io.BytesIO(original),'narrow-gutter.pdf')}).json
    assert 'paragraphs' in d,d
    before=server.state(d['id'])
    layout=client.get(f"/api/documents/{d['id']}/layout").json
    page=layout['pages'][0]
    assert page['twoColumns']
    # Below the running heading there is no genuinely full-width artwork/equation.
    assert all(len(row['columns'])==2 for row in page['rows'] if row['columns'][0][0]['rect'][1]>40)
    boxes={p['id']:fitz.Rect(p['bbox']) for p in d['paragraphs']}
    for row in page['rows']:
        for column in row['columns']:
            for tile in column:
                for pid in tile['paragraphIds']:
                    box=boxes[pid];crop=fitz.Rect(tile['rect'])
                    assert (box&crop).get_area()>=box.get_area()-.05,(pid,box,crop)
    with fitz.open(stream=original,filetype='pdf') as pdf:
        metadata=json.loads((server.folder(d['id'])/'translation-policy.json').read_text(encoding='utf-8'))
        equations=[fitz.Rect(r['bbox']) for r in metadata['pages'][0]['regions'] if r['kind']=='formula']
        assert equations and all(r.x1<=306 or r.x0>=306 for r in equations),equations
    for p in d['paragraphs']:
        if any(s in p['text'] for s in ['Left body','Right body','Here, the vectors','following two equations']):
            assert p['translatable'] and p['translationSource']==p['text'],p
        if p['text'].startswith('v ='):
            assert not p['translatable'],p
    assert server.state(d['id'])==before
