import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    server.app.config['TESTING']=True
    return server.app.test_client()


def upload(client, content=None):
    if content is None:
        content=(server.ROOT/'static'/'sample.pdf').read_bytes()
    response=client.post('/api/documents',data={'file':(io.BytesIO(content),'paper.pdf')})
    assert response.status_code==200, response.json
    return response.json


def test_upload_extract_cache_and_states(client):
    d=upload(client)
    assert d['pageCount']==3
    assert any('Reading a research paper' in p['text'] for p in d['paragraphs'])
    assert any('Reading a research paper' in p['text'] and 'into one place.' in p['text'] for p in d['paragraphs'])
    assert len(d['outline'])==3
    assert upload(client)['id']==d['id']
    client.patch(f"/api/documents/{d['id']}/state",json={'page':2,'messages':[{'role':'user','content':'hello'}]})
    restored=client.get(f"/api/documents/{d['id']}").json
    assert restored['state']['page']==2
    assert restored['state']['messages'][0]['content']=='hello'
    assert len(client.get('/api/documents').json)==1


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_annotation_export_native_and_original_untouched(client,rotation):
    source=fitz.open();page=source.new_page(width=500,height=600)
    page.insert_text((80,120),'Test selected words',fontsize=15)
    original_rect=page.search_for('selected')[0]
    page.add_text_annot((30,30),'Existing note')
    page.set_rotation(rotation)
    pdf_quad=original_rect.quad*~page.transformation_matrix
    coords=[v for point in pdf_quad for v in point]
    original=source.tobytes();source.close();d=upload(client,original)
    annotation={'page':1,'kind':'highlight','text':'selected','note':'中文测试备注','color':'#f4ca64','rects':[[.1,.1,.2,.03]],'quads':[coords]}
    response=client.post(f"/api/documents/{d['id']}/annotations",json=annotation)
    assert response.status_code==200,response.json
    aid=response.json['id']
    exported=client.get(f"/api/documents/{d['id']}/export")
    assert exported.status_code==200
    with fitz.open(stream=exported.data,filetype='pdf') as pdf:
        result_page=pdf[0]
        annots=list(result_page.annots())
        assert len(annots)==2
        assert annots[0].info['content']=='Existing note'
        assert annots[1].type[0]==fitz.PDF_ANNOT_HIGHLIGHT
        assert annots[1].info['content']=='中文测试备注'
        points=annots[1].vertices
        actual=fitz.Quad(points).rect
        assert abs(actual.x0-original_rect.x0)<.1
        assert abs(actual.y0-original_rect.y0)<.1
    assert client.get(f"/api/documents/{d['id']}/pdf").data==original
    assert client.patch(f"/api/documents/{d['id']}/annotations/{aid}",json={'note':'Updated'}).status_code==200
    assert client.delete(f"/api/documents/{d['id']}/annotations/{aid}").status_code==200
    assert not client.get(f"/api/documents/{d['id']}").json['state']['annotations']


def test_translation_caching_failure_resume_and_languages(client):
    d=upload(client);pid=next(p['id'] for p in d['paragraphs'] if p['translatable']);url=f"/api/documents/{d['id']}/translate"
    with patch.object(server,'complete',return_value='示例翻译') as model:
        assert client.post(url,json={'paragraphId':pid}).json['text']=='示例翻译'
        assert client.post(url,json={'paragraphId':pid}).json['cached']
        assert model.call_count==1
        client.post(url,json={'paragraphId':pid,'language':'English'})
        assert model.call_count==2
    with patch.object(server,'complete',side_effect=ValueError('rate limit')):
        assert client.post(url,json={'paragraphId':pid,'force':True}).status_code==400
    assert client.get(f"/api/documents/{d['id']}").json['state']['translations']['简体中文:'+pid]=='示例翻译'


def test_security_and_invalid_inputs(client):
    assert client.get('/api/documents',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/documents',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/api/documents',data={'file':(io.BytesIO(b'no pdf'),'fake.pdf')}).status_code==400
    pdf=fitz.open();pdf.new_page();data=pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='secret');pdf.close()
    assert client.post('/api/documents',data={'file':(io.BytesIO(data),'locked.pdf')}).status_code==400
    d=upload(client)
    assert client.post(f"/api/documents/{d['id']}/annotations",json={'page':1,'rects':[],'quads':[]}).status_code==400
    assert client.post('/api/test',json={'config':{'baseUrl':'file:///secret','model':'x'}}).status_code==400


def test_api_urls():
    for base,expected in [('http://localhost:1234','http://localhost:1234/v1/chat/completions'),('https://example.com/api/v1','https://example.com/api/v1/chat/completions'),('https://example.com/custom/chat/completions','https://example.com/custom/chat/completions')]:
        assert server.api_config({'config':{'baseUrl':base,'model':'demo'}})[0]==expected


def test_translation_annotation_anchor_and_export(client):
    d=upload(client);pid=next(p['id'] for p in d['paragraphs'] if p['translatable']);url=f"/api/documents/{d['id']}"
    text='译文😀，支持批注。'
    with patch.object(server,'complete',return_value=text):
        client.post(url+'/translate',json={'paragraphId':pid})
    body={'source':'translation','paragraphId':pid,'language':'简体中文','translationText':text,
          'anchorText':text,'start':5,'end':9,'text':'支持批注','kind':'underline','note':'译文笔记'}
    response=client.post(url+'/annotations',json=body)
    assert response.status_code==200,response.json
    annotation=response.json
    assert annotation['page']==1 and annotation['text']=='支持批注'
    for changes in [{'translationText':'旧译文'},{'language':'English'},{'start':-1},{'end':100},{'text':'其他文字'},{'start':3,'end':4,'text':'😀'}]:
        assert client.post(url+'/annotations',json=body|changes).status_code==400
    with fitz.open(stream=client.get(url+'/export').data,filetype='pdf') as pdf:
        assert all(not list(p.annots()) for p in pdf)
    assert client.patch(url+'/annotations/'+annotation['id'],json={'note':'更新笔记'}).status_code==200
    with patch.object(server,'complete',return_value='新的译文'):
        client.post(url+'/translate',json={'paragraphId':pid,'force':True})
    saved=client.get(url).json['state']['annotations'][0]
    assert saved['translationText']==text and saved['note']=='更新笔记'
    assert client.post(url+'/annotations',json=body).status_code==400
    assert client.delete(url+'/annotations/'+annotation['id']).status_code==200


def test_context_limits():
    d={'paragraphs':[{'page':i+1,'text':'relevant information '*200} for i in range(100)]}
    text,truncated=server.context_for(d,'information','',budget=10000)
    assert truncated and len(text)<10100 and '[p1]' in text
