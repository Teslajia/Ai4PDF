import base64
import io
import json
from unittest.mock import patch,MagicMock

import pymupdf as fitz
import pytest
from test_app import client,upload
import app as server


def image_bytes():
    pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,120,80))
    pix.set_rect(pix.irect,(200,110,60))
    return pix.tobytes('png')


def attach(client,doc_id):
    r=client.post(f'/api/documents/{doc_id}/attachments',data={'file':(io.BytesIO(image_bytes()),'测试截图.png')})
    assert r.status_code==200,r.json
    return r.json


def test_image_upload_restore_and_document_isolation(client):
    d=upload(client);a=attach(client,d['id']);base=f"/api/documents/{d['id']}"
    assert a['width']==120 and a['height']==80 and a['mime']=='image/png'
    r=client.get(base+'/attachments/'+a['id'])
    assert r.data==image_bytes() and r.mimetype=='image/png'
    message={'role':'user','content':'解释图片中的公式','attachments':[{'id':a['id'],'name':'client-forged-name','url':'https://example.invalid'}]}
    assert client.patch(base+'/state',json={'messages':[message]}).status_code==200
    restored=client.get(base).json['state']['messages'][0]
    assert restored['attachments']==[a] and 'url' not in restored['attachments'][0]
    with fitz.open() as pdf:
        pdf.new_page();second=upload(client,pdf.tobytes())
    assert client.get(f"/api/documents/{second['id']}/attachments/{a['id']}").status_code==400
    assert client.patch(f"/api/documents/{second['id']}/state",json={'messages':[message]}).status_code==400
    assert client.patch(base+'/state',json={'messages':[message|{'attachments':[a]*5}]}).status_code==400
    assert client.get(base).json['state']['messages'][0]==restored


def test_image_rejects_invalid_data_and_limits(client,monkeypatch):
    d=upload(client);url=f"/api/documents/{d['id']}/attachments"
    for data in [b'<svg onload="alert(1)"></svg>',b'\x89PNG\r\n\x1a\ninvalid',b'%PDF-1.5']:
        assert client.post(url,data={'file':(io.BytesIO(data),'fake.png')}).status_code==400
    monkeypatch.setattr(server,'IMAGE_MAX_BYTES',8)
    assert client.post(url,data={'file':(io.BytesIO(image_bytes()),'big.png')}).status_code==400


def test_image_chat_sends_real_bytes_and_retains_text_protocol(client):
    d=upload(client);a=attach(client,d['id']);base=f"/api/documents/{d['id']}"
    config={'baseUrl':'http://localhost:44444','model':'local-vision'}
    image_message={'role':'user','content':'看这张图','attachments':[a]}
    history=[image_message,{'role':'assistant','content':'此前的回答'},{'role':'user','content':'继续解释'}]
    response=MagicMock();response.ok=True;response.is_redirect=False;response.headers={'Content-Type':'application/json'}
    response.json.return_value={'choices':[{'message':{'content':'图片回答'}}]}
    response.__enter__.return_value=response
    with patch.object(server.requests,'post',return_value=response) as upstream:
        result=client.post(base+'/chat',json={'config':config,'messages':history})
        assert result.status_code==200 and '图片回答' in result.get_data(as_text=True)
        messages=upstream.call_args.kwargs['json']['messages']
        assert messages[1]['content'][0]=={'type':'text','text':'看这张图'}
        data_url=messages[1]['content'][1]['image_url']['url']
        assert data_url.startswith('data:image/png;base64,')
        assert base64.b64decode(data_url.split(',')[1])==image_bytes()
        assert messages[-1]['content']=='继续解释' and isinstance(messages[2]['content'],str)
        assert all('attachments' not in m for m in messages)
        # Image-only messages work even with a scanned PDF / no extracted prose.
        doc=server.read_doc(d['id']);doc['paragraphs']=[]
        with patch.object(server,'read_doc',return_value=doc):
            result=client.post(base+'/chat',json={'config':config,'messages':[image_message|{'content':''}]})
        assert '"done": true' in result.get_data(as_text=True)
        assert client.post(base+'/chat',json={'config':config,'messages':[{'role':'user','content':''}]}).status_code==400


def test_unsupported_vision_hint_does_not_leak_upstream_secrets(client):
    d=upload(client);a=attach(client,d['id'])
    response=MagicMock();response.ok=False;response.is_redirect=False;response.status_code=400
    response.text='SECRET API KEY';response.__enter__.return_value=response
    with patch.object(server.requests,'post',return_value=response):
        r=client.post(f"/api/documents/{d['id']}/chat",json={'config':{'baseUrl':'http://localhost:44444','model':'text-only'},'messages':[{'role':'user','content':'解释','attachments':[a]}]})
        text=r.get_data(as_text=True)
    assert '支持图片输入' in text and 'SECRET' not in text
