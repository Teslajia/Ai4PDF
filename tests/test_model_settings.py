from unittest.mock import MagicMock, patch

import pytest

import app as server
from test_app import client, upload


def response(status=200):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.ok = status == 200
    result.is_redirect = False
    result.headers = {'Content-Type': 'application/json'}
    result.json.return_value = {'choices': [{'message': {'content': '本地模拟回答'}}]}
    return result


@pytest.mark.parametrize('effort', [None, 'default', 'none', 'high', 'max'])
def test_actual_model_and_reasoning_sent_for_chat_translation_and_test(client, effort):
    doc = upload(client)
    pid = next(p['id'] for p in doc['paragraphs'] if p['translatable'])
    config = {'baseUrl': 'https://api.openai.com/v1' if effort == 'max' else 'http://localhost:44444/v1', 'model': 'gpt-6-sol' if effort == 'max' else 'actual-model-id',
              'displayName': 'ChatGPT 官方', 'apiKey': 'test-only-key', 'recentModels': ['old-model']}
    if effort is not None:
        config['reasoningEffort'] = effort
    endpoints = [('/api/test', {}),
                 (f"/api/documents/{doc['id']}/translate", {'paragraphId': pid}),
                 (f"/api/documents/{doc['id']}/chat", {'messages': [{'role': 'user', 'content': '解释方法'}]})]
    with patch.object(server.requests, 'post', return_value=response()) as upstream:
        for endpoint, body in endpoints:
            result = client.post(endpoint, json={'config': config, **body})
            assert result.status_code == 200, result.data
            assert '本地模拟回答' in (str(result.json) if result.is_json else result.get_data(as_text=True))
            outgoing = upstream.call_args.kwargs['json']
            assert outgoing['model'] == config['model']
            assert 'displayName' not in outgoing and 'recentModels' not in outgoing
            assert 'apiKey' not in outgoing
            if effort in (None, 'default'):
                assert 'reasoning_effort' not in outgoing
            else:
                assert outgoing['reasoning_effort'] == effort
            assert upstream.call_args.kwargs['headers']['Authorization'] == 'Bearer test-only-key'
    saved = server.state(doc['id'])
    assert 'test-only-key' not in str(saved) and 'reasoningEffort' not in saved


def test_invalid_effort_rejected_before_any_upstream_request(client):
    doc = upload(client)
    with patch.object(server.requests, 'post') as upstream:
        for effort in ('invalid', ['high'], True):
            body = {'config': {'baseUrl': 'http://localhost:44444', 'model': 'actual-model', 'reasoningEffort': effort},
                    'messages': [{'role': 'user', 'content': '解释方法'}]}
            for endpoint in ('/api/test', f"/api/documents/{doc['id']}/chat"):
                result = client.post(endpoint, json=body)
                assert result.status_code == 400
                assert '思考强度无效' in result.json['error']
        upstream.assert_not_called()


def test_unsupported_effort_has_actionable_error_and_no_silent_retry(client):
    doc = upload(client)
    body = {'config': {'baseUrl': 'http://localhost:44444', 'model': 'actual-model', 'reasoningEffort': 'high'},
            'messages': [{'role': 'user', 'content': '解释方法'}]}
    with patch.object(server.requests, 'post', return_value=response(400)) as upstream:
        result = client.post('/api/test', json=body)
        assert result.status_code == 400 and '跟随模型默认' in result.json['error']
        result = client.post(f"/api/documents/{doc['id']}/chat", json=body)
        assert '跟随模型默认' in result.get_data(as_text=True)
        assert upstream.call_count == 2


@pytest.mark.parametrize('base,expected', [
    ('http://localhost:44444', 'http://localhost:44444/v1/models'),
    ('https://example.com/api/v1/', 'https://example.com/api/v1/models'),
    ('https://example.com/custom/chat/completions', 'https://example.com/custom/models'),
])
def test_catalog_uses_current_credentials_without_requiring_a_model(client, base, expected):
    upstream_response=response()
    upstream_response.json.return_value={'data':[{'id':'model-b'}, {'id':'model-a'}, {'id':'model-b'}, {'id':''}, {'id':None}, 'invalid']}
    with patch.object(server.requests,'get',return_value=upstream_response) as get, patch.object(server.requests,'post') as generate:
        result=client.post('/api/models',json={'config':{'baseUrl':base,'apiKey':'test-catalog-key'}})
        assert result.status_code==200 and result.json['models']==['model-a','model-b']
        assert get.call_args.args==(expected,)
        assert get.call_args.kwargs['headers']['Authorization']=='Bearer test-catalog-key'
        assert get.call_args.kwargs['allow_redirects'] is False
        generate.assert_not_called()
        assert not list(server.DATA.iterdir())


def test_catalog_errors_are_safe_and_empty_lists_are_valid(client):
    config={'baseUrl':'http://localhost:44444','apiKey':'test-catalog-key'}
    for status in (401,404,405,500):
        upstream_response=response(status)
        upstream_response.text='test-catalog-key'
        with patch.object(server.requests,'get',return_value=upstream_response):
            result=client.post('/api/models',json={'config':config})
            assert result.status_code==400 and 'test-catalog-key' not in result.get_data(as_text=True)
            if status in (404,405):assert '手动填写' in result.json['error']
    for payload,code in [({'data':[]},200),({'models':[]},400),([],400)]:
        upstream_response=response();upstream_response.json.return_value=payload
        with patch.object(server.requests,'get',return_value=upstream_response):
            assert client.post('/api/models',json={'config':config}).status_code==code
    upstream_response=response();upstream_response.json.side_effect=ValueError('sensitive upstream data')
    with patch.object(server.requests,'get',return_value=upstream_response):
        result=client.post('/api/models',json={'config':config})
        assert result.status_code==400 and 'sensitive' not in result.json['error']
    with patch.object(server.requests,'get',side_effect=server.requests.Timeout('sensitive credentials')):
        result=client.post('/api/models',json={'config':config})
        assert result.status_code==400 and 'sensitive' not in result.json['error']


@pytest.mark.parametrize('language,expected',[('zh-CN','简体中文'),('zh-TW','繁體中文'),('ko','韩语'),('ja','日语'),('en','English')])
def test_chat_default_reply_language_matches_system_setting(client,language,expected):
    doc=upload(client)
    with patch.object(server.requests,'post',return_value=response()) as upstream:
        result=client.post(f"/api/documents/{doc['id']}/chat",json={
            'config':{'baseUrl':'http://localhost:44444','model':'actual-model','uiLanguage':language},
            'messages':[{'role':'user','content':'Explain the method'}]})
        assert result.status_code==200
        result.get_data()
        body=upstream.call_args.kwargs['json']
        assert f'默认用{expected}回答' in body['messages'][0]['content']
        assert 'uiLanguage' not in body

