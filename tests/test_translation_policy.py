import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server
from translation_policy import formula_line


def policy_pdf():
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    page.insert_text((45,45),'A method with figures and equations',fontsize=16)
    page.insert_text((45,75),'The energy E = mc^2 is used to explain our method.',fontsize=11)
    page.draw_rect(fitz.Rect(50,100,550,210),color=(.2,.3,.5),fill=(.9,.95,1))
    page.insert_text((70,135),'ENCODER diagram label',fontsize=11)
    page.insert_text((290,180),'DECODER diagram label',fontsize=11)
    page.insert_text((50,235),'Fig. 1: An overview of the proposed model.',fontsize=11)
    page.insert_text((240,285),'E = mc',fontsize=17)
    page.insert_text((299,276),'2',fontsize=9)
    # A label merged with the next paragraph must be removed without losing prose.
    page.insert_text((50,297),'(3)\nThis continuous reward provides precise guidance.',fontsize=11)
    page.insert_text((50,365),'Reported accuracy: 84.7 +/- 1.4, published in (2017).',fontsize=11)
    page.insert_text((50,390),'Contact: author_name@example.org',fontsize=11)
    second=pdf.new_page(width=600,height=800)
    second.insert_text((240,100),'R_k(x_i) = x^2',fontsize=17)
    second.insert_text((520,100),'(4)',fontsize=11)
    content=pdf.tobytes();pdf.close();return content


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    return server.app.test_client()


def upload(client):
    response=client.post('/api/documents',data={'file':(io.BytesIO(policy_pdf()),'policy.pdf')})
    assert response.status_code==200,response.json
    return response.json


def test_skip_artwork_and_math_but_preserve_explanations(client):
    d=upload(client);paragraphs=d['paragraphs']
    eligible=[p['translationSource'] for p in paragraphs if p['translatable']]
    excluded=[p['text'] for p in paragraphs if not p['translatable']]
    assert any('Fig. 1:' in s for s in eligible)
    assert any('energy E = mc^2' in s for s in eligible)
    assert any('84.7 +/- 1.4' in s and '(2017)' in s for s in eligible)
    assert any('author_name@example.org' in s for s in eligible)
    assert any('ENCODER' in s for s in excluded)
    assert any('DECODER' in s for s in excluded)
    assert any('E = mc' in s for s in excluded)
    assert all(not p['translatable'] for p in paragraphs if p['page']==2)
    body=next(p for p in paragraphs if 'This continuous reward' in p['text'])
    assert body['translatable'] and '(3)' not in body['translationSource']
    with patch.object(server,'complete',return_value='正文译文') as model:
        for p in paragraphs:
            response=client.post(f"/api/documents/{d['id']}/translate",json={'paragraphId':p['id'],'force':True})
            assert response.status_code==200,response.json
            assert bool(response.json.get('skipped')) == (not p['translatable'])
        assert model.call_count==len(eligible)
        assert [call.args[1][1]['content'] for call in model.call_args_list]==eligible


def test_old_translations_and_annotations_remain_while_policy_is_applied(client):
    d=upload(client);path=server.folder(d['id'])
    mixed=next(p for p in d['paragraphs'] if 'This continuous reward' in p['text'])
    formula=next(p for p in d['paragraphs'] if not p['translatable'] and p['translationKind']=='formula')
    prose=next(p for p in d['paragraphs'] if 'energy E' in p['text'])
    saved=server.state(d['id'])
    for p in [mixed,formula,prose]:saved['translations']['简体中文:'+p['id']]='此前的译文'
    saved['annotations']=[{'id':'kept','source':'translation','page':1,'paragraphId':formula['id'],'text':'此前的译文','note':'保留我的笔记'}]
    server.write_json(path/'state.json',saved)
    metadata=json.loads((path/'document.json').read_text(encoding='utf-8'))
    for p in metadata['paragraphs']:p.pop('bbox',None)
    server.write_json(path/'document.json',metadata)
    before=(path/'state.json').read_bytes();original_metadata=(path/'document.json').read_bytes()
    result=client.get(f"/api/documents/{d['id']}").json
    assert result['state']==saved
    assert (path/'state.json').read_bytes()==before
    assert (path/'document.json').read_bytes()==original_metadata
    with patch.object(server,'complete',return_value='只翻译清理后的正文') as model:
        base=f"/api/documents/{d['id']}/translate"
        assert client.post(base,json={'paragraphId':formula['id']}).json['skipped']
        assert client.post(base,json={'paragraphId':prose['id']}).json['cached']
        fresh=client.post(base,json={'paragraphId':mixed['id']}).json
        assert not fresh['cached'] and fresh['sourceHash']==mixed['translationSourceHash']
        assert client.post(base,json={'paragraphId':mixed['id']}).json['cached']
        assert model.call_count==1
    assert server.state(d['id'])['annotations']==saved['annotations']


def test_formula_fonts_and_prose_false_positives():
    def line(parts):return {'spans':[{'text':text,'font':font} for text,font in parts]}
    assert formula_line(line([('ac','CMEX10')]))
    assert formula_line(line([('x','CMMI10')]))
    assert formula_line(line([('MHSA(U) = Concat(Attn(U))','Times-Roman')]))
    assert formula_line(line([('max(0, 1 - x)','Times-Roman')]))
    assert formula_line(line([(r'0, & \\text{otherwise} \\end{cases}', 'Times-Roman')]))
    assert not formula_line(line([('k=1.','CMR7'),(' Here, ','Times-Roman'),('q(x)','CMMI10'),(' denotes','Times-Roman')]))
    for text in ['author_name@example.org','84.7 ± 1.4','(2017)','A short heading','The energy E = mc^2 explains this observation.', 'W = weight matrix for the original feature vectors.']:
        assert not formula_line(line([(text,'Times-Roman')])),text


def margins_pdf(rotation=0):
    pdf=fitz.open()
    for n in range(1,7):
        page=pdf.new_page(width=600,height=800)
        if n==1:
            page.insert_text((50,65),'Short Paper Title',fontsize=18,fontname='hebo')
        elif n%2:
            page.insert_text((390,60),'Short Paper Title',fontsize=9)
            page.insert_text((540,60),str(n),fontsize=9)
        else:
            page.insert_text((50,60),str(n),fontsize=9)
            page.insert_text((80,60),'F. Author et al.',fontsize=9)
        page.insert_text((50,115),'Repeated section heading',fontsize=11,fontname='hebo')
        page.insert_textbox(fitz.Rect(50,145,550,220),
                            f'Body paragraph {n}. We discuss Short Paper Title and the work of F. Author et al. in this explanatory paragraph. These words are content, not running headers.',fontsize=11)
        page.insert_text((50,700),f'A unique footnote explains observation {n}.',fontsize=9)
        page.insert_text((50,760),'Journal of Examples',fontsize=8)
        page.insert_text((480,760),f'Page {n} of 6',fontsize=8)
        page.set_rotation(rotation)
    content=pdf.tobytes();pdf.close();return content


@pytest.mark.parametrize('rotation',[0,90])
def test_running_headers_footers_preserve_title_body_and_cache(client,rotation):
    d=client.post('/api/documents',data={'file':(io.BytesIO(margins_pdf(rotation)),'margins.pdf')}).json
    headers=[p for p in d['paragraphs'] if p['translationKind']=='header']
    footers=[p for p in d['paragraphs'] if p['translationKind']=='footer']
    assert {p['page'] for p in headers}==set(range(2,7))
    assert {p['page'] for p in footers}==set(range(1,7))
    assert all(not p['translatable'] for p in headers+footers)
    assert next(p for p in d['paragraphs'] if p['page']==1 and p['text']=='Short Paper Title')['translatable']
    for p in d['paragraphs']:
        if any(s in p['text'] for s in ['Body paragraph','Repeated section heading','A unique footnote']):
            assert p['translatable'] and p['translationSource']==p['text'],p
    path=server.folder(d['id']);saved=server.state(d['id'])
    saved['translations']['简体中文:'+headers[0]['id']]='旧的页眉译文'
    server.write_json(path/'state.json',saved)
    before=(path/'state.json').read_bytes();metadata=(path/'document.json').read_bytes()
    # Simulate a library with the previous formula-only policy cache.
    cache=json.loads((path/'translation-policy.json').read_text(encoding='utf-8'));cache['version']=1
    for p in cache['paragraphs'].values():p['translatable']=True;p['translationKind']='text'
    server.write_json(path/'translation-policy.json',cache)
    reopened=client.get(f"/api/documents/{d['id']}").json
    assert any(p['translationKind']=='header' and not p['translatable'] for p in reopened['paragraphs'])
    assert (path/'state.json').read_bytes()==before and (path/'document.json').read_bytes()==metadata
    with patch.object(server,'complete',return_value='正文译文') as model:
        for p in headers+footers:
            response=client.post(f"/api/documents/{d['id']}/translate",json={'paragraphId':p['id'],'force':True})
            assert response.json['skipped'] and response.json['reason'] in ('header','footer')
        model.assert_not_called()
