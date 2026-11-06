import copy
import io
import math

import pymupdf as fitz
import pytest
from PIL import Image, ImageChops

import app as server
from test_app import client
from test_layout import illustrated_pdf
from test_table_captions import table_pdf
from translation_visuals import build_visuals


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_original_visual_crops_include_artwork_exclude_caption_and_preserve_files(client,rotation):
    original=illustrated_pdf(rotation)
    d=client.post('/api/documents',data={'file':(io.BytesIO(original),'visual.pdf')}).json
    base=f"/api/documents/{d['id']}";path=server.folder(d['id'])
    before={name:(path/name).read_bytes() for name in ['original.pdf','document.json','state.json']}
    layout=client.get(base+'/layout').json
    visuals=layout['pages'][0]['visuals']
    assert {'figure','formula'}<={v['kind'] for v in visuals}
    with fitz.open(stream=original,filetype='pdf') as pdf:
        page=pdf[0]
        caption=next(fitz.Rect(p['bbox'])*page.rotation_matrix for p in d['paragraphs'] if p['text'].startswith('Figure 1.'))
        for visual in visuals:
            rect=fitz.Rect(visual['rect'])
            assert (rect&caption).get_area()<1
            response=client.get(base+f"/pages/1/visuals/{visual['id']}/image")
            assert response.status_code==200 and response.mimetype=='image/png'
            result=Image.open(io.BytesIO(response.data)).convert('RGB')
            scale=min(6,1800/rect.width,math.sqrt(4_000_000/rect.get_area()))
            expected_box=(rect*fitz.Matrix(scale,scale)).irect
            full=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False,annots=False)
            expected=Image.frombytes('RGB',(full.width,full.height),full.samples).crop(tuple(expected_box))
            assert result.size==expected.size
            # Interior pixels must match the original page at every rotation.
            inset=(2,2,result.width-2,result.height-2)
            assert ImageChops.difference(result.crop(inset),expected.crop(inset)).getbbox() is None
            assert result.width<=1802 and result.width*result.height<=4_010_000
            assert client.get(base+f"/pages/1/visuals/{visual['id']}/image",headers={'If-None-Match':response.headers['ETag']}).status_code==304
    assert client.get(base+'/pages/1/visuals/unknown/image').status_code==404
    assert client.get(base+f"/pages/2/visuals/{visuals[0]['id']}/image").status_code==404
    for name,data in before.items():assert (path/name).read_bytes()==data


@pytest.mark.parametrize('below',[False,True])
def test_table_body_only_and_old_manual_layout_retains_visuals(client,below):
    d=client.post('/api/documents',data={'file':(io.BytesIO(table_pdf(below=below)),'table.pdf')}).json
    base=f"/api/documents/{d['id']}"
    initial=client.get(base+'/layout').json
    visuals=initial['pages'][0]['visuals'];assert len(visuals)==1 and visuals[0]['kind']=='table'
    body=fitz.Rect(visuals[0]['rect']);assert body.y0<155 and body.y1>=255
    for p in d['paragraphs']:
        if p['translatable']:assert not body.intersects(fitz.Rect(p['bbox']))
    edit=client.get(base+'/layout/pages/1').json
    blocks=copy.deepcopy(edit['blocks'])
    for b in blocks:b['skip']=True
    result=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks})
    assert result.status_code==200,result.json
    assert result.json['layout']['pages'][0]['visuals']==visuals
    assert client.get(base+'/layout').json['pages'][0]['visuals']==visuals
    # A pre-feature cached layout is rebuilt without changing saved manual work.
    cache=copy.deepcopy(initial);cache['version']=6;cache['pages'][0].pop('visuals')
    server.write_json(server.folder(d['id'])/'layout.json',cache)
    before=(server.folder(d['id'])/'manual-layout.json').read_bytes()
    assert client.get(base+'/layout').json['pages'][0]['visuals']==visuals
    assert (server.folder(d['id'])/'manual-layout.json').read_bytes()==before


def test_overlapping_table_graphics_and_embedded_formulas_render_once():
    with fitz.open() as pdf:
        p=pdf.new_page(width=600,height=800)
        regions=[{'kind':'table','bbox':[40,60,550,300],'bodyBbox':[40,110,550,300]},
                 {'kind':'figure','bbox':[40,110,550,300]}, {'kind':'formula','bbox':[60,130,200,150]},
                 {'kind':'formula','bbox':[60,400,250,425]}]
        visuals=build_visuals(p,regions)
        assert [v['kind'] for v in visuals]==['table','formula']
        assert len({v['id'] for v in visuals})==2


def test_detached_equation_number_joins_its_formula_without_crossing_columns():
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        for x in [40,320]:
            for y in [100,200,300]:
                page.insert_textbox(fitz.Rect(x,y,x+240,y+70),'Ordinary prose identifies the two columns. The number must stay with the equation in its own column.',fontsize=10)
        page.insert_text((370,400),'a = b + c',fontsize=11)
        page.insert_text((540,400),'(1)',fontsize=11)
        page.insert_text((250,400),'(2)',fontsize=11)
        # Explicit regions simulate fragmented formula detection.
        regions=[{'kind':'formula','bbox':list(r)} for r in page.search_for('a = b + c')+page.search_for('(1)')+page.search_for('(2)')]
        originals=copy.deepcopy(regions)
        visuals=build_visuals(page,regions)
        assert len(visuals)==2 and regions==originals
        assert any(v['rect'][0]>300 and v['rect'][2]>550 for v in visuals)
        assert any(240<v['rect'][0]<260 and v['rect'][2]<300 for v in visuals)
