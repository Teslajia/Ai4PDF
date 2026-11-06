import io
import json

import pymupdf as fitz
import pytest

import app as server
from pdf_geometry import visible_drawings
from test_app import client


def clipped_graphics_pdf(rotation=0):
    with fitz.open() as source,fitz.open() as output:
        original=source.new_page(width=600,height=800)
        original.draw_rect((60,90,240,160),fill=(.2,.5,.7))
        original.draw_rect((210,190,330,270),fill=(.7,.3,.1))  # Partly clipped.
        original.draw_rect((420,100,475,138),fill=(.2,.5,.7))  # Fully clipped.
        page=output.new_page(width=600,height=800)
        clip=fitz.Rect(40,70,280,250)
        page.show_pdf_page(clip,source,0,clip=clip)
        page.insert_textbox((320,75,565,190),'This ordinary body paragraph describes the training pairs and loss functions. The original figure contains an invisible path behind these words. These sentences must all remain translatable.',fontsize=10)
        page.insert_text((40,280),'Figure 1. A clipped drawing.',fontsize=10)
        # This object is outside the form and must not inherit its clipping.
        page.draw_rect((420,390,480,430),fill=(.1,.6,.3))
        page.set_rotation(rotation)
        return output.tobytes()


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_embedded_form_clip_removes_phantom_figure_but_preserves_prose(client,rotation):
    raw=clipped_graphics_pdf(rotation)
    with fitz.open(stream=raw,filetype='pdf') as pdf:
        page=pdf[0];ghost=fitz.Rect(420,100,475,138)
        assert any((fitz.Rect(d['rect'])&ghost).get_area()>1000 for d in page.get_drawings())
        visible=list(visible_drawings(page))
        assert not any(fitz.Rect(d['rect']).intersects(ghost) for d in visible)
        assert any(fitz.Rect(d['rect'])==fitz.Rect(210,190,280,250) for d in visible)
        assert any(fitz.Rect(d['rect'])==fitz.Rect(420,390,480,430) for d in visible)
    d=client.post('/api/documents',data={'file':(io.BytesIO(raw),'clipped.pdf')}).json
    path=server.folder(d['id'])
    prose=next(p for p in d['paragraphs'] if 'ordinary body paragraph' in p['text'])
    assert prose['translatable'] and prose['translationSource']==prose['text']
    policy=json.loads((path/'translation-policy.json').read_text(encoding='utf-8'))
    assert not any(fitz.Rect(r['bbox']).intersects(ghost) for r in policy['pages'][0]['regions'])
    layout=client.get(f"/api/documents/{d['id']}/layout").json
    figures=[v for v in layout['pages'][0]['visuals'] if v['kind']=='figure']
    assert len(figures)==3  # Two visible form panels plus the following object.
    assert (path/'original.pdf').read_bytes()==raw


def test_previous_phantom_region_cache_refresh_keeps_saved_work(client):
    raw=clipped_graphics_pdf()
    d=client.post('/api/documents',data={'file':(io.BytesIO(raw),'clipped.pdf')}).json
    path=server.folder(d['id']);base=f"/api/documents/{d['id']}"
    layout=client.get(base+'/layout').json
    policy=json.loads((path/'translation-policy.json').read_text(encoding='utf-8'))
    policy['version']=5;policy['pages'][0]['regions'].append({'kind':'figure','bbox':[420,100,475,138]})
    layout['version']=8;layout['pages'][0]['visuals'].append({'id':'stale','kind':'figure','rect':[420,100,475,138]})
    server.write_json(path/'translation-policy.json',policy);server.write_json(path/'layout.json',layout)
    state=server.state(d['id']);state['translations']['saved']='Keep this translation'
    state['annotations']=[{'id':'kept-note','text':'Keep this annotation'}]
    server.write_json(path/'state.json',state)
    before={name:(path/name).read_bytes() for name in ['original.pdf','document.json','state.json']}
    refreshed=client.get(base+'/layout').json
    assert len(refreshed['pages'][0]['visuals'])==3
    assert all(v['id']!='stale' for v in refreshed['pages'][0]['visuals'])
    for name,data in before.items():assert (path/name).read_bytes()==data
