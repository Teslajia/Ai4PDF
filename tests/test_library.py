import hashlib
import io
import json
import threading
import time
from pathlib import Path

import pymupdf as fitz
import pytest

import app as server
import library as lib


@pytest.fixture
def client(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    monkeypatch.setattr(server, 'DATA', source)
    monkeypatch.setattr(server, 'LOCATION_FILE', tmp_path / 'library-location.json')
    monkeypatch.setattr(server, 'DATA_FROM_ENV', False)
    server.library.job = {'status': 'idle'}
    server.app.config['TESTING'] = True
    return server.app.test_client()


def upload(client, label='Example'):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 80), label + ' research paper about local document management.')
        pdf.set_metadata({'title': label})
        content = pdf.tobytes()
    response = client.post('/api/documents', data={'file': (io.BytesIO(content), label+'.pdf')})
    assert response.status_code == 200, response.json
    return response.json


def batch(client, action, ids, **fields):
    return client.post('/api/library/batch', json={'action': action, 'ids': ids, **fields})


def wait_migration(client):
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        result = client.get('/api/library/migration').json
        if result['status'] != 'running':
            return result
        time.sleep(.02)
    pytest.fail('Migration did not complete')


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_existing_docs_organization_and_independent_state(client):
    a,b=upload(client,'Alpha'),upload(client,'Beta')
    ids=[a['id'],b['id']]
    original=(server.DATA/a['id']/'original.pdf').read_bytes()
    assert len(client.get('/api/documents').json)==2
    assert not (server.DATA/'library.json').exists()
    folder=client.post('/api/library/folders',json={'name':'研究 / Research'}).json
    assert batch(client,'move',ids,folderId=folder['id']).status_code==200
    assert batch(client,'addTags',ids,tags=['待读','AI','AI']).status_code==200
    assert batch(client,'edit',[ids[0]],title='保存设置',folderId=folder['id'],tags=['精读','AI']).status_code==200
    docs=client.get('/api/library').json['documents']
    assert all(d['folderId']==folder['id'] for d in docs)
    assert client.get('/api/documents/'+ids[0]).json['title']=='保存设置'
    assert (server.DATA/ids[0]/'original.pdf').read_bytes()==original
    assert batch(client,'removeTags',ids,tags=['AI']).status_code==200
    assert all('AI' not in d['tags'] for d in client.get('/api/documents').json)
    # A bad bulk edit must leave all metadata intact.
    before=(server.DATA/'library.json').read_bytes()
    assert batch(client,'addTags',ids,tags=['tag'+str(i) for i in range(30)]).status_code==400
    assert (server.DATA/'library.json').read_bytes()==before
    assert client.post('/api/library/folders',json={'name':'研究 / Research'}).status_code==400
    assert client.patch('/api/library/folders/'+folder['id'],json={'name':'新名称'}).status_code==200
    assert client.delete('/api/library/folders/'+folder['id']).status_code==200
    assert all(d['folderId']=='' for d in client.get('/api/documents').json)


def test_trash_restore_reimport_and_permanent_delete(client):
    a=upload(client);doc_id=a['id'];path=server.DATA/doc_id
    client.patch('/api/documents/'+doc_id+'/state',json={'page':1,'messages':[{'role':'user','content':'Keep this chat'}]})
    before=hashes(path)
    assert batch(client,'purge',[doc_id]).status_code==409
    assert batch(client,'trash',[doc_id]).status_code==200
    assert client.get('/api/documents').json==[]
    assert client.get('/api/documents/'+doc_id).status_code==404
    assert client.get('/api/documents/'+doc_id+'/pdf').status_code==404
    assert hashes(path)==before
    assert batch(client,'restore',[doc_id]).status_code==200
    assert client.get('/api/documents/'+doc_id).json['state']['messages'][0]['content']=='Keep this chat'
    assert batch(client,'trash',[doc_id]).status_code==200
    # Opening exactly the same bytes restores the existing document, not a blank copy.
    response=client.post('/api/documents',data={'file':(io.BytesIO((path/'original.pdf').read_bytes()),'renamed.pdf')})
    assert response.status_code==200 and response.json['id']==doc_id
    assert response.json['state']['messages']
    assert batch(client,'trash',[doc_id]).status_code==200
    assert batch(client,'purge',[doc_id]).status_code==200
    assert not path.exists() and client.get('/api/library').json['documents']==[]


def test_batch_validation_and_stale_state_are_atomic(client):
    a,b=upload(client,'A'),upload(client,'B');ids=[a['id'],b['id']]
    assert batch(client,'trash',[ids[0]]).status_code==200
    assert batch(client,'trash',ids).status_code==409
    assert len(client.get('/api/documents').json)==1
    assert batch(client,'move',[ids[1]],folderId='missing').status_code==400
    for invalid in [[],['../data'],['a'*24],None]:
        assert batch(client,'trash',invalid).status_code in (400,404)
    assert client.post('/api/library/folders',json={'name':' '*3}).status_code==400
    assert client.post('/api/library/batch',json={'action':'trash','ids':[ids[1]]},headers={'Origin':'https://evil.example'}).status_code==403


def test_purge_metadata_failure_rolls_back_directory(client,monkeypatch):
    d=upload(client);doc_id=d['id'];batch(client,'trash',[doc_id])
    before=hashes(server.DATA)
    def deny_write(*args):raise PermissionError('simulated catalog failure')
    monkeypatch.setattr(server,'write_json',deny_write)
    assert batch(client,'purge',[doc_id]).status_code==500
    assert hashes(server.DATA)==before
    assert len(client.get('/api/library').json['documents'])==1


def test_purge_locked_payload_reports_cleanup_and_allows_reimport(client,monkeypatch):
    d=upload(client);doc_id=d['id'];original=(server.DATA/doc_id/'original.pdf').read_bytes()
    batch(client,'trash',[doc_id])
    def deny_delete(*args):raise PermissionError('simulated file lock')
    monkeypatch.setattr(lib.shutil,'rmtree',deny_delete)
    result=batch(client,'purge',[doc_id])
    assert result.status_code==400 and '.purge-' in result.json['error']
    assert (server.DATA/('.purge-'+doc_id)/'original.pdf').exists()
    assert client.get('/api/library').json['documents']==[]
    response=client.post('/api/documents',data={'file':(io.BytesIO(original),'again.pdf')})
    assert response.status_code==200
    assert response.json['state']['messages']==[]


def test_migration_preserves_every_file_and_persists_restart_location(client,tmp_path):
    a=upload(client);folder=client.post('/api/library/folders',json={'name':'研究'}).json
    batch(client,'edit',[a['id']],title='My title',folderId=folder['id'],tags=['AI'])
    path=server.DATA/a['id'];(path/'attachments').mkdir()
    (path/'attachments'/'sample.png').write_bytes(b'image payload')
    (path/'manual-layout.json').write_text('{"revision":"demo","pages":{}}',encoding='utf-8')
    (path/'previews').mkdir();(path/'previews'/'page-1.png').write_bytes(b'preview')
    source=server.DATA;before=hashes(source);target=tmp_path/'new library'
    response=client.post('/api/library/migration',json={'source':str(source.resolve()),'target':str(target)})
    assert response.status_code==202,response.json
    result=wait_migration(client)
    assert result['status']=='done',result
    assert server.DATA==target and hashes(target)==before and hashes(source)==before
    assert lib.initial_location(tmp_path,{})==(target,False)
    assert client.get('/api/documents/'+a['id']).json['title']=='My title'
    # Subsequent writes go only to the new library.
    batch(client,'addTags',[a['id']],tags=['New'])
    assert hashes(source)==before
    assert 'New' in client.get('/api/documents').json[0]['tags']
    assert client.get('/api/library/storage').json['path']==str(target)


@pytest.mark.parametrize('kind',['same','inside','parent','nonempty','relative'])
def test_migration_rejects_unsafe_destinations_without_modifying_source(client,tmp_path,kind):
    upload(client);source=server.DATA;before=hashes(source)
    nonempty=tmp_path/'occupied';nonempty.mkdir();(nonempty/'keep.txt').write_text('keep')
    target={'same':source,'inside':source/'child','parent':tmp_path,'nonempty':nonempty,'relative':Path('relative')}[kind]
    response=client.post('/api/library/migration',json={'source':str(source.resolve()),'target':str(target)})
    assert response.status_code==400,response.json
    assert server.DATA==source and hashes(source)==before
    assert (nonempty/'keep.txt').read_text()=='keep'
    assert not server.LOCATION_FILE.exists()


def test_migration_commit_failure_retains_original_and_source_config(client,tmp_path,monkeypatch):
    upload(client);source=server.DATA;before=hashes(source);target=tmp_path/'target'
    original_write=server.write_json
    def fail_commit(path,value):
        if path==server.LOCATION_FILE:raise PermissionError('simulated')
        original_write(path,value)
    monkeypatch.setattr(server,'write_json',fail_commit)
    assert client.post('/api/library/migration',json={'source':str(source),'target':str(target)}).status_code==202
    assert wait_migration(client)['status']=='error'
    assert server.DATA==source and hashes(source)==before and hashes(target)==before
    assert not server.LOCATION_FILE.exists()


def test_concurrent_state_save_waits_and_writes_to_new_location(client,tmp_path,monkeypatch):
    a=upload(client);source=server.DATA;target=tmp_path/'target';entered=threading.Event();release=threading.Event();saved=threading.Event()
    original_scan=lib.safe_tree
    def paused_scan(root):
        if root==source and not entered.is_set():
            entered.set();assert release.wait(5)
        return original_scan(root)
    monkeypatch.setattr(lib,'safe_tree',paused_scan)
    client.post('/api/library/migration',json={'source':str(source),'target':str(target)})
    assert entered.wait(5)
    assert client.get('/api/library/migration').json['status']=='running'
    assert client.post('/api/library/migration',json={'source':str(source),'target':str(tmp_path/'other')}).status_code==409
    def save():
        with server.app.test_client() as other:
            assert other.patch('/api/documents/'+a['id']+'/state',json={'messages':[{'role':'user','content':'During migration'}]}).status_code==200
            saved.set()
    writer=threading.Thread(target=save);writer.start()
    assert not saved.wait(.05);release.set();writer.join(5)
    assert saved.is_set() and wait_migration(client)['status']=='done'
    assert json.loads((source/a['id']/'state.json').read_text())['messages']==[]
    assert json.loads((target/a['id']/'state.json').read_text())['messages'][0]['content']=='During migration'


def test_environment_override_and_missing_persisted_location(client,tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA_FROM_ENV',True)
    assert client.get('/api/library/storage').json['managedByEnvironment']
    assert client.post('/api/library/migration',json={'source':str(server.DATA),'target':str(tmp_path/'other')}).status_code==400
    assert lib.initial_location(tmp_path,{'AI4PDF_DATA':str(server.DATA)})==(server.DATA,True)
    server.LOCATION_FILE.write_text(json.dumps({'path':str(tmp_path/'missing')}))
    with pytest.raises(RuntimeError):lib.initial_location(tmp_path,{})
