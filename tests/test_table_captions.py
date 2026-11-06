import io
import json

import pymupdf as fitz
import pytest

import app as server
from test_app import client


def table_pdf(ruled=True,below=False,rotation=0,two=False):
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    width=245 if two else 480;x=325 if two else 60
    title_y=315 if below else 115
    page.insert_text((x,title_y),'Table 1. Comparison of results.',fontsize=10)
    page.insert_text((x,title_y+13),'Higher values indicate better quality.',fontsize=10)
    top=155;xs=[x,x+width*.45,x+width*.72,x+width]
    if ruled:
        for yy in [top,top+25,top+50,top+75,top+100]:page.draw_line((x,yy),(x+width,yy))
        for xx in xs:page.draw_line((xx,top),(xx,top+100))
    for i,row in enumerate([['Method','Score','Time'],['Baseline','23.4','1.5'],['Model A','25.6','2.1'],['Ours','27.1','1.8']]):
        for xx,value in zip(xs,row):page.insert_text((xx+5,top+i*25+17),value,fontsize=9)
    for y in [390,490,590]:
        page.insert_textbox(fitz.Rect(x,y,x+width,y+85),'Body paragraph explains the results and assumptions. This text must remain separate from the table and caption when translations are inserted.',fontsize=10)
    if two:
        for y in [60,160,280,400,520,640]:
            page.insert_textbox(fitz.Rect(35,y,280,y+90),'Left column prose describes the method and relevant prior work. It must not be merged with the table in the other column. All these words are ordinary translatable prose.',fontsize=10)
    page.set_rotation(rotation)
    data=pdf.tobytes();pdf.close();return data


@pytest.mark.parametrize('ruled,below,rotation,two',[(True,False,0,False),(False,False,0,False),(True,True,0,False),(True,False,90,False),(True,False,0,True)])
def test_table_and_wrapped_caption_form_one_tile_without_losing_prose(client,ruled,below,rotation,two):
    original=table_pdf(ruled,below,rotation,two)
    response=client.post('/api/documents',data={'file':(io.BytesIO(original),'table.pdf')})
    assert response.status_code==200,response.json
    d=response.json
    policy=json.loads((server.folder(d['id'])/'translation-policy.json').read_text())
    regions=[r for r in policy['pages'][0]['regions'] if r['kind']=='table']
    assert len(regions)==1
    layout=client.get(f"/api/documents/{d['id']}/layout").json
    tiles=[tile for row in layout['pages'][0]['rows'] for column in row['columns'] for tile in column]
    with fitz.open(stream=original,filetype='pdf') as pdf:
        region=fitz.Rect(regions[0]['bbox'])*pdf[0].rotation_matrix
    assert any((region&fitz.Rect(tile['rect'])).get_area()>=region.get_area()-.1 for tile in tiles)
    titles=[p for p in d['paragraphs'] if 'Table 1.' in p['text'] or 'Higher values' in p['text']]
    assert titles and all(p['translatable'] for p in titles)
    assert all(p['translatable'] for p in d['paragraphs'] if 'Body paragraph' in p['text'] or 'Left column prose' in p['text'])
    assert all(not p['translatable'] for p in d['paragraphs'] if p['text'].startswith('Baseline') or p['text'].startswith('Method'))
    assert (server.folder(d['id'])/'original.pdf').read_bytes()==original
