import copy
import io
import json
from unittest.mock import patch

import pymupdf as fitz
import pytest

import app as server
from manual_layout import apply_document
from translation_policy import formula_line, page_policy, line_key
from test_app import client


def chart_pdf(rotation=0,caption=True):
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    # The same visual chart may consist entirely of zero-height/width paths.
    page.draw_line((360,180),(360,330),width=.5)
    page.draw_line((360,330),(455,330),width=.5)
    for y,label in [(205,'0.7'),(250,'0.65'),(295,'0.6')]:
        page.insert_text((334,y),label,fontsize=8)
        page.draw_line((358,y-3),(363,y-3),width=.5)
    page.insert_text((329,275),'Reward',fontsize=8,rotate=90)
    page.insert_text((410,344),'Step',fontsize=8)
    if caption:
        # Disconnected panels / legends must be united across one column.
        page.draw_rect(fitz.Rect(365,95,445,145),fill=(.2,.5,.7),color=None)
        page.insert_text((365,160),'Ours   User Study',fontsize=7)
        page.draw_rect(fitz.Rect(480,95,560,335),fill=(.6,.7,.8),color=None)
        page.insert_text((355,360),'(a) Comparison of model scores',fontsize=7)
        page.insert_text((480,360),'(b) Ground Truth',fontsize=7)
        page.insert_textbox(fitz.Rect(315,380,565,430),'Figure 1. Comparison of methods and their scores. The caption must still be translated.',fontsize=10)
    for x in [45,315]:
        for y in ([70,190,310,440,560,670] if x==45 else [450,555,660]):
            page.insert_textbox(fitz.Rect(x,y,x+245,y+80),'The body paragraph explains why the measured reward improves. Numeric results such as 0.7 remain useful in ordinary sentences.',fontsize=10)
    page.set_rotation(rotation);raw=pdf.tobytes();pdf.close();return raw


@pytest.mark.parametrize('rotation,caption',[(0,True),(90,True),(180,True),(270,True),(0,False)])
def test_disconnected_panels_thin_axes_and_outside_labels(client,rotation,caption):
    raw=chart_pdf(rotation,caption)
    d=client.post('/api/documents',data={'file':(io.BytesIO(raw),'chart.pdf')}).json
    labels={'0.7','0.65','0.6','Reward','Step','Ours   User Study','(a) Comparison of model scores','(b) Ground Truth'}
    for p in d['paragraphs']:
        if p['text'] in labels or 'User Study' in p['text']:
            assert not p['translatable'],p
        if 'body paragraph' in p['text'] or p['text'].startswith('Figure 1.'):
            assert p['translatable'] and p['translationSource']==p['text'],p
    layout=client.get(f"/api/documents/{d['id']}/layout").json
    tiles=[fitz.Rect(t['rect']) for row in layout['pages'][0]['rows'] for col in row['columns'] for t in col]
    with fitz.open(stream=raw,filetype='pdf') as pdf:
        _,_,regions=page_policy(pdf[0])
        for r in regions:
            rect=fitz.Rect(r['bbox'])*pdf[0].rotation_matrix
            assert any((t&rect).get_area()>=rect.get_area()-.01 for t in tiles)
    assert client.get(f"/api/documents/{d['id']}/pdf").data==raw


def test_prose_between_figure_and_caption_stops_region_growth():
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    page.draw_rect((50,70,550,120),fill=(.2,.5,.7))
    page.insert_text((50,140),'This ordinary body sentence must not be hidden as a figure label.',fontsize=11)
    page.insert_text((50,165),'Figure 2. This caption follows prose, not the artwork.',fontsize=10)
    lines,kinds,_=page_policy(page)
    assert all(kinds[line_key(line)]=='text' for line in lines)
    pdf.close()


def test_roman_subscripts_functions_and_inline_prose():
    def line(parts):return {'spans':[{'text':text,'font':font,'size':size} for text,font,size in parts]}
    assert formula_line(line([('{S','CMMI10',10),('fgc-global','Times-Roman',7),(', M','CMMI10',10),('fg-pdm','Times-Roman',7),('} = RM(x)','CMMI10',10)]))
    for text in ['Mfg-pdm = Sigmoid(Decoder(x))','Sfgc-global = MLP(fN * interpolate(Mfg-pdm))','Diffpixel = x; Difffeat = 1 - cos(f, g)','Mgt = Normalize (a * x + (1 - a) * y)']:
        assert formula_line(line([(text,'Times-Roman',10)])),text
    for text in ['i=1. Through a series of up-sampling operations,','We use E = mc^2.','The function Sigmoid(x) is used to normalize scores.','W = weight matrix for the original feature vectors.']:
        assert not formula_line(line([(text,'Times-Roman',10)])),text


def test_old_policy_and_manual_geometry_refresh_without_touching_saved_work(client):
    d=client.post('/api/documents',data={'file':(io.BytesIO(chart_pdf()),'chart.pdf')}).json
    path=server.folder(d['id']);marker=next(p for p in d['paragraphs'] if p['text']=='0.7')
    saved=server.state(d['id']);saved['translations']['简体中文:'+marker['id']]='0.7'
    saved['annotations']=[{'id':'old-note','source':'translation','paragraphId':marker['id'],'note':'Keep my original note'}]
    server.write_json(path/'state.json',saved);before=(path/'state.json').read_bytes()
    cache=json.loads((path/'translation-policy.json').read_text(encoding='utf-8'));cache['version']=4
    for p in cache['paragraphs'].values():p['translatable']=True;p['translationKind']='text'
    server.write_json(path/'translation-policy.json',cache)
    restored=client.get(f"/api/documents/{d['id']}").json
    assert not next(p for p in restored['paragraphs'] if p['id']==marker['id'])['translatable']
    assert (path/'state.json').read_bytes()==before
    with patch.object(server,'complete') as model:
        assert client.post(f"/api/documents/{d['id']}/translate",json={'paragraphId':marker['id'],'force':True}).json['skipped']
        model.assert_not_called()
    old=copy.deepcopy(marker);old['translatable']=True
    custom={'id':'m1-custom','manual':True,'page':1,'text':'My explicit replacement','translatable':True}
    manual={'pages':{'1':{'paragraphs':[old,custom]}}};original=copy.deepcopy(manual)
    result=apply_document(restored,manual)['translationParagraphs']
    assert not result[0]['translatable'] and result[1]==custom and manual==original
