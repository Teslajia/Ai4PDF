from unittest.mock import patch

from test_app import client
from test_model_settings import response
from reasoning import available_efforts


def test_official_and_gateway_same_model_have_different_verified_choices():
    config={'model':'gpt-6-sol','baseUrl':'https://api.openai.com/v1'}
    assert available_efforts(config)==['default','none','low','medium','high','xhigh','max']
    assert 'max' not in available_efforts(config | {'baseUrl':'https://example.invalid/v1'})
    assert 'max' not in available_efforts(config | {'baseUrl':'https://api.openai.com.example.invalid/v1'})
    assert 'max' not in available_efforts(config | {'model':'unknown-model'})


def test_invalid_gateway_max_is_blocked_before_request(client):
    with patch('app.requests.post') as upstream:
        r=client.post('/api/test',json={'config':{'baseUrl':'https://gateway.invalid/v1','model':'gpt-6-sol','reasoningEffort':'max'}})
        assert r.status_code==400 and '未声明支持' in r.json['error']
        upstream.assert_not_called()


def test_provider_declared_capabilities_are_scoped_to_credentials(client):
    config={'baseUrl':'https://declared.invalid/v1','model':'custom-model','apiKey':'test-key-one'}
    catalog=response()
    catalog.json.return_value={'data':[{'id':'custom-model','supported_reasoning_efforts':['low','high','max']}]}
    with patch('app.requests.get',return_value=catalog):
        r=client.post('/api/models',json={'config':config})
        assert r.json['reasoningEfforts']=={'custom-model':['low','high','max']}
    assert available_efforts(config)==['default','low','high','max']
    assert 'max' not in available_efforts(config | {'apiKey':'test-key-two'})
    with patch('app.requests.post',return_value=response()) as upstream:
        r=client.post('/api/test',json={'config':config | {'reasoningEffort':'max'}})
        assert r.status_code==200
        assert upstream.call_args.kwargs['json']['reasoning_effort']=='max'
