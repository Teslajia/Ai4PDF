import copy
import io
import re
from unittest.mock import patch

import pymupdf as fitz
import pytest
import app as server
from test_layout import client,illustrated_pdf


def stamped_pdf():
    with fitz.open(stream=illustrated_pdf(),filetype='pdf') as pdf:
        pdf[0].insert_text((25,660),'arXiv:1234.56789v2 [cs.CV] 6 Apr 2026',fontsize=18,rotate=90)
        return pdf.tobytes()


def setup_document(client,rotation=0):
    d=client.post('/api/documents',data={'file':(io.BytesIO(illustrated_pdf(rotation)),'manual.pdf')}).json
    base=f"/api/documents/{d['id']}";edit=client.get(base+'/layout/pages/1').json
    assert 'blocks' in edit,edit
    return d,base,edit


def split_body(edit):
    p=next(p for p in edit['paragraphs'] if p['text'].startswith('Left paragraph 1'))
    lines=[l for l in edit['lines'] if l['paragraphId']==p['id']]
    y=(lines[1]['rect'][3]+lines[2]['rect'][1])/2
    block=next(b for b in edit['blocks'] if b['rect'][0]<=lines[0]['rect'][0]<b['rect'][2] and b['rect'][1]<y<b['rect'][3])
    blocks=copy.deepcopy(edit['blocks']);index=blocks.index(block)
    a=copy.deepcopy(block);b=copy.deepcopy(block)
    a.update(id='manual-a',regroup=True);b.update(id='manual-b',regroup=True)
    a['rect'][3]=y;b['rect'][1]=y;blocks[index:index+1]=[a,b]
    return p,block,blocks


def test_split_merge_restore_preserves_cached_translations_and_notes(client):
    d,base,edit=setup_document(client);p,original,blocks=split_body(edit)
    state=server.state(d['id']);state['translations']['简体中文:'+p['id']]='原有译文'
    state['annotations']=[{'id':'kept-note','source':'translation','page':1,'paragraphId':p['id'],'text':'原有','note':'原有批注'}]
    server.write_json(server.folder(d['id'])/'state.json',state)
    before={n:(server.folder(d['id'])/n).read_bytes() for n in ['original.pdf','document.json','state.json']}
    r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks})
    assert r.status_code==200,r.json
    updated=r.json;active=updated['translationParagraphs'];pieces=[q for q in active if q.get('manual')]
    assert len(pieces)==2 and p['id'] not in {q['id'] for q in active}
    assert ' '.join(q['translationSource'] for q in pieces)==p['translationSource']
    assert all(q['translationSourceHash'] for q in pieces)
    other=next(q for q in edit['paragraphs'] if q['text'].startswith('Right paragraph 1'))
    assert other in active
    assert updated['layout']['pages'][0]['manual'] and updated['layout']['pages'][0]['tree']
    assert client.get(base).json['translationParagraphs']==active
    for n,content in before.items():assert (server.folder(d['id'])/n).read_bytes()==content
    with patch.object(server,'complete',return_value='新段落的译文') as model:
        response=client.post(base+'/translate',json={'paragraphId':pieces[0]['id']})
        assert response.status_code==200,response.json
        assert model.call_args.args[1][1]['content']==pieces[0]['translationSource']
    note={'source':'translation','paragraphId':pieces[0]['id'],'language':'简体中文','translationText':'新段落的译文','anchorText':'新段落的译文',
          'start':0,'end':3,'text':'新段落','kind':'highlight'}
    assert client.post(base+'/annotations',json=note).status_code==200
    merged=copy.deepcopy(edit['blocks']);merged[merged.index(original)]['regroup']=True
    r=client.put(base+'/layout/pages/1',json={'revision':updated['manualRevision'],'blocks':merged})
    assert r.status_code==200,r.json
    assert p in r.json['translationParagraphs']  # Original identity and translation recovered.
    restored=client.delete(base+'/layout/pages/1',json={'revision':r.json['manualRevision']})
    assert restored.status_code==200 and not restored.json['manualPages']
    assert restored.json['translationParagraphs']==edit['paragraphs']
    assert server.state(d['id'])['translations']['简体中文:'+p['id']]=='原有译文'
    assert len(server.state(d['id'])['annotations'])==2


def test_custom_text_skip_and_conflicting_edits(client):
    d,base,edit=setup_document(client)
    blocks=copy.deepcopy(edit['blocks']);block=blocks[0];block['text']='手动补充的正文与公式说明';block['regroup']=True
    r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks})
    assert r.status_code==200,r.json
    custom=next(p for p in r.json['translationParagraphs'] if p['text']==block['text'])
    revision=r.json['manualRevision']
    assert client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks}).status_code==409
    assert client.delete(base+'/layout/pages/1',json={'revision':edit['revision']}).status_code==409
    block['skip']=True
    r=client.put(base+'/layout/pages/1',json={'revision':revision,'blocks':blocks})
    assert r.status_code==200,r.json
    assert custom['id'] not in {p['id'] for p in r.json['translationParagraphs']}
    assert client.post(base+'/translate',json={'paragraphId':custom['id']}).status_code==400


def test_invalid_partitions_and_text_cut_are_atomic(client):
    d,base,edit=setup_document(client);p,original,blocks=split_body(edit)
    invalid=[]
    missing=copy.deepcopy(blocks);missing.pop();invalid.append(missing)
    duplicate=copy.deepcopy(blocks);duplicate.append(copy.deepcopy(duplicate[0]));invalid.append(duplicate)
    outside=copy.deepcopy(blocks);outside[0]['rect'][0]=-5;invalid.append(outside)
    cut=copy.deepcopy(blocks);line=next(l for l in edit['lines'] if l['paragraphId']==p['id'])
    y=(line['rect'][1]+line['rect'][3])/2
    next(b for b in cut if b['id']=='manual-a')['rect'][3]=y
    next(b for b in cut if b['id']=='manual-b')['rect'][1]=y
    invalid.append(cut)
    for bad in invalid:
        r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':bad})
        assert r.status_code==400,r.json
        assert client.get(base+'/layout/pages/1').json['revision']=='0'


@pytest.mark.parametrize('rotation',[0,90])
def test_manual_save_covers_entire_rotated_page(client,rotation):
    d,base,edit=setup_document(client,rotation)
    r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':edit['blocks']})
    assert r.status_code==200,r.json
    page=r.json['layout']['pages'][0]
    def tiles(node):return [node['tile']] if 'tile' in node else [t for child in node['children'] for t in tiles(child)]
    all_tiles=tiles(page['tree'])
    assert abs(sum(fitz.Rect(t['rect']).get_area() for t in all_tiles)-page['width']*page['height'])<.1
    assert sorted(pid for t in all_tiles for pid in t['paragraphIds'])==sorted(p['id'] for p in edit['paragraphs'])


def test_long_extraction_chunks_do_not_duplicate_lines_when_regrouped(client):
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        text=' '.join(f'Sentence {i} explains the model assumptions and the experimental observations in detail.' for i in range(50))
        assert page.insert_textbox(fitz.Rect(40,40,560,760),text,fontsize=8)>0
        original=pdf.tobytes()
    d=client.post('/api/documents',data={'file':(io.BytesIO(original),'long.pdf')}).json
    base=f"/api/documents/{d['id']}";edit=client.get(base+'/layout/pages/1').json
    assert len(edit['paragraphs'])>=2
    compact=lambda s:re.sub(r'\s+','',s)
    assert compact(''.join(line['text'] for line in edit['lines']))==compact(''.join(p['text'] for p in edit['paragraphs']))
    positions=sorted({(l['rect'][1],l['rect'][3]) for l in edit['lines']})
    mid=len(positions)//2;y=(positions[mid-1][1]+positions[mid][0])/2
    blocks=[{'id':'top','rect':[0,0,600,y],'regroup':True},{'id':'bottom','rect':[0,y,600,800],'regroup':True}]
    r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks})
    assert r.status_code==200,r.json
    assert compact(''.join(p['translationSource'] for p in r.json['translationParagraphs']))==compact(text)


def test_vertical_margin_stamp_does_not_block_skip_or_safe_splitting(client):
    d=client.post('/api/documents',data={'file':(io.BytesIO(stamped_pdf()),'stamp.pdf')}).json
    base=f"/api/documents/{d['id']}";edit=client.get(base+'/layout/pages/1').json
    stamp=next(line for line in edit['lines'] if line['text'].startswith('arXiv:'))
    assert stamp['protectBoundary'] is False
    assert any(b['rect'][1]>stamp['rect'][1] and b['rect'][1]<stamp['rect'][3] for b in edit['blocks'])
    p,original,split=split_body(edit)
    blocks=copy.deepcopy(edit['blocks']);index=blocks.index(original);blocks[index]['skip']=True
    r=client.put(base+'/layout/pages/1',json={'revision':edit['revision'],'blocks':blocks})
    assert r.status_code==200,r.json
    assert p['id'] not in {q['id'] for q in r.json['translationParagraphs']}
    assert client.get(base+'/layout/pages/1').json['blocks'][index]['skip']
    with patch.object(server,'complete') as model:
        assert client.post(base+'/translate',json={'paragraphId':p['id']}).status_code==400
        model.assert_not_called()
    r=client.put(base+'/layout/pages/1',json={'revision':r.json['manualRevision'],'blocks':split})
    assert r.status_code==200,r.json
    assert sum(bool(p.get('manual')) for p in r.json['translationParagraphs'])==2


def test_existing_clipping_allows_metadata_edit_but_new_clipping_is_rejected():
    from manual_layout import build_manual_page
    with fitz.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        p={'id':'body','page':1,'text':'Existing text line','bbox':[50,200,200,240],'translatable':True,'translationSource':'Existing text line'}
        lines=[{'paragraphId':'body','text':p['text'],'rect':p['bbox'],'include':True}]
        old=[{'id':'top','rect':[0,0,600,210]},{'id':'bottom','rect':[0,210,600,800]}]
        changed=copy.deepcopy(old);changed[0]['skip']=True
        result=build_manual_page(page,1,[p],lines,changed,old)
        assert result['blocks'][0]['skip']
        worse=copy.deepcopy(old);worse[0]['rect'][3]=220;worse[1]['rect'][1]=220
        with pytest.raises(ValueError,match='分界穿过'):
            build_manual_page(page,1,[p],lines,worse,old)
