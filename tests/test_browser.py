import json
import logging
import random
import threading
import time
from pathlib import Path

import pymupdf as fitz
import pytest
from flask import Flask, Response, jsonify, request
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

import app as server


@pytest.fixture
def services(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    mock=Flask('mock_model')
    calls={'translation':0,'failOnce':True,'chat':0,'texts':[],'delay':.04}

    @mock.get('/v1/models')
    def models():
        calls['models']=calls.get('models',0)+1
        if calls.get('modelsStatus'):
            return jsonify(error='Model catalog unavailable'),calls['modelsStatus']
        return jsonify(data=[{'id':m} for m in calls.get('modelIds',['local-test-model','research-model','fast-model'])])

    @mock.post('/v1/chat/completions')
    def completions():
        body=request.get_json()
        assert body['model']==calls.get('expectedModel','local-test-model')
        calls.setdefault('bodies',[]).append(body)
        if body.get('stream'):
            calls['chat']+=1
            calls.setdefault('chatBodies',[]).append(body)
            if calls.get('chatStatus'):
                return jsonify(error='Unsupported image input'),calls['chatStatus']
            def stream():
                for text in calls.get('chatChunks',['**核心观点**：这是本地阅读工具。','\n\n请对照原文 [p2]。']):
                    yield 'data: '+json.dumps({'choices':[{'delta':{'content':text}}]},ensure_ascii=False)+'\n\n'
                    time.sleep(calls.get('chatDelay',.03))
                yield 'data: [DONE]\n\n'
            return Response(stream(),mimetype='text/event-stream')
        if body['messages'][0]['role']=='system':
            calls['translation']+=1
            calls['texts'].append(body['messages'][-1]['content'])
            if calls['translation']==2 and calls['failOnce']:
                calls['failOnce']=False
                return jsonify(error='test rate limit'),429
            time.sleep(calls['delay'])
            text=calls.get('translationText','这是用于验证逐段翻译的模拟译文，保留原文中的关键概念。')
        else:
            text='OK'
        return jsonify(choices=[{'message':{'content':text}}])

    # A port-0 allocation can pick a Chromium-blocked port on this Windows host.
    def safe_server(application):
        for _ in range(20):
            try:
                return make_server('127.0.0.1',random.randint(40000,59999),application,threaded=True)
            except (SystemExit,OSError):
                continue
        raise RuntimeError('No free local test port')
    app_server=safe_server(server.app)
    mock_server=safe_server(mock)
    for s in (app_server,mock_server):threading.Thread(target=s.serve_forever,daemon=True).start()
    yield f'http://127.0.0.1:{app_server.server_port}', f'http://127.0.0.1:{mock_server.server_port}', calls
    app_server.shutdown();mock_server.shutdown()


@pytest.fixture
def browser():
    paths=['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe']
    executable=next((p for p in paths if Path(p).exists()),None)
    if not executable:pytest.skip('Chrome / Edge is required for UI testing')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=executable,headless=True)
        yield browser
        browser.close()


def select_text(page,needle,start=0,end=40):
    page.evaluate('''({needle,start,end})=>{
        const span=[...document.querySelectorAll('.textLayer span')].find(s=>s.textContent.includes(needle));
        if(!span)throw new Error('Text span missing: '+needle);
        const range=document.createRange();range.setStart(span.firstChild,start);range.setEnd(span.firstChild,Math.min(end,span.firstChild.length));
        const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    }''',{'needle':needle,'start':start,'end':end})
    page.locator('#pages').dispatch_event('mouseup')
    expect(page.locator('#selection-toolbar')).to_be_visible()


def other_document():
    pdf=fitz.open();pdf.set_metadata({'title':'Another research paper'})
    page=pdf.new_page(width=500,height=650)
    page.insert_text((50,90),'Another research paper',fontsize=20)
    page.insert_text((50,140),'Different document, independent reading state.',fontsize=12)
    content=pdf.tobytes();pdf.close();return content


def test_switch_documents_and_keep_independent_state(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='第一篇文章保存的译文。'
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#pages .textLayer span').first.wait_for()
    first_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    first_title=page.locator('#doc-title').inner_text()
    select_text(page,'Reading a research paper');page.locator('#highlight-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    page.locator('#next').click();expect(page.locator('#page-number')).to_have_value('2')
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page')).to_have_count(3)
    page.locator('.retry').first.click()
    expect(page.locator('.translated-text').first).to_have_text('第一篇文章保存的译文。')
    page.locator('#translation-from').fill('2');page.locator('#translation-to').fill('2')
    first_worker=page.workers[0]
    # Switch while the bilingual view and its selectable source layers are active.
    payload={'name':'another.pdf','mimeType':'application/pdf','buffer':other_document()}
    page.locator('#file-input').set_input_files(payload)
    expect(page.locator('#doc-title')).to_have_text('Another research paper',timeout=10000)
    expect(page.locator('#loading')).to_be_hidden()
    expect(page.locator('#pages .textLayer')).to_contain_text('Different document',timeout=10000)
    expect(page.locator('#annotation-count')).to_be_hidden()
    expect(page.locator('#toast.error')).to_be_hidden()
    assert len(page.workers)==1 and first_worker not in page.workers
    second_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    assert second_id!=first_id
    calls['translationText']='第二篇文章保存的译文。'
    page.locator('#translation-tab').click();expect(page.locator('.bilingual-page')).to_have_count(1)
    expect(page.locator('#translation-from')).to_have_value('1');expect(page.locator('#translation-to')).to_have_value('1')
    page.locator('.retry').first.click();expect(page.locator('.translated-text').first).to_have_text('第二篇文章保存的译文。')
    for title in [first_title,'Another research paper',first_title,first_title]:
        page.locator('[data-drawer=library]').click()
        page.locator('#drawer-content .document-card').filter(has_text=title).click()
        expect(page.locator('#loading')).to_be_hidden(timeout=15000)
        expect(page.locator('#doc-title')).to_have_text(title)
        expect(page.locator('#toast.error')).to_be_hidden()
        assert len(page.workers)==1
    expect(page.locator('#page-number')).to_have_value('2')
    expect(page.locator('#annotation-count')).to_have_text('1')
    page.locator('#translation-tab').click();expect(page.locator('.bilingual-page')).to_have_count(3)
    expect(page.locator('.translated-text').first).to_have_text('第一篇文章保存的译文。')
    expect(page.locator('#translation-from')).to_have_value('2');expect(page.locator('#translation-to')).to_have_value('2')
    assert len(page.request.get(base+f'/api/documents/{first_id}').json()['state']['annotations'])==1
    assert not page.request.get(base+f'/api/documents/{second_id}').json()['state']['annotations']
    assert not errors,errors
    page.close()


def test_failed_pdf_switch_keeps_previous_document_and_can_retry(browser,services):
    base,_,_=services;page=browser.new_page(viewport={'width':1440,'height':1000})
    page.goto(base);page.locator('#open-sample').click()
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#pages .textLayer span').first.wait_for()
    first_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    page.route('**/api/documents/*/pdf',lambda route:route.abort('failed'))
    payload={'name':'another.pdf','mimeType':'application/pdf','buffer':other_document()}
    page.locator('#file-input').set_input_files(payload)
    expect(page.locator('#toast.error')).to_be_visible(timeout=10000)
    expect(page.locator('#loading')).to_be_hidden()
    assert page.evaluate("localStorage.getItem('paperdesk.last')")==first_id
    expect(page.locator('#pages')).to_contain_text('Reading a research paper')
    assert len(page.workers)==1
    page.unroute('**/api/documents/*/pdf')
    page.locator('#file-input').set_input_files(payload)
    expect(page.locator('#doc-title')).to_have_text('Another research paper',timeout=10000)
    expect(page.locator('#loading')).to_be_hidden()
    expect(page.locator('#toast.error')).to_be_hidden()
    assert len(page.workers)==1
    page.close()


def test_switch_ignores_previous_documents_delayed_layout(browser,services):
    base,_,_=services;page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    first_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    layout=page.request.get(base+f'/api/documents/{first_id}/layout').json()
    held=[]
    page.route(f'**/api/documents/{first_id}/layout',lambda route:held.append(route))
    with page.expect_request(f'**/api/documents/{first_id}/layout'):
        page.locator('#translation-tab').click()
    page.locator('#file-input').set_input_files({'name':'another.pdf','mimeType':'application/pdf','buffer':other_document()})
    expect(page.locator('#doc-title')).to_have_text('Another research paper',timeout=10000)
    expect(page.locator('#loading')).to_be_hidden()
    assert len(held)==1
    held[0].fulfill(status=200,content_type='application/json',body=json.dumps(layout))
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page')).to_have_count(1,timeout=15000)
    expect(page.locator('.bilingual-page')).to_have_attribute('data-selectable','true')
    expect(page.locator('#paragraphs')).to_contain_text('Different document')
    expect(page.locator('#toast.error')).to_be_hidden()
    assert len(page.workers)==1 and not errors,errors
    page.close()


def test_translation_page_range_pause_resume_and_cache(browser,services):
    base,model,calls=services
    calls['failOnce']=False;calls['delay']=.2
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    page.locator('.textLayer span').first.wait_for(timeout=30000)
    expect(page.locator('#loading')).to_be_hidden()
    doc_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    d=page.request.get(base+'/api/documents/'+doc_id).json()
    expected=lambda start,end:[p['translationSource'] for p in d['paragraphs'] if p['translatable'] and start<=p['page']<=end]
    page.locator('#translation-tab').click()
    expect(page.locator('#translation-from')).to_have_value('1')
    expect(page.locator('#translation-to')).to_have_value('3')
    for start,end in [('','3'),('0','3'),('1','4'),('3','2'),('1.5','2')]:
        page.locator('#translation-from').fill(start);page.locator('#translation-to').fill(end)
        expect(page.locator('#translate-all')).to_be_disabled()
        expect(page.locator('#translation-range-hint')).to_contain_text('请输入')
    assert calls['translation']==0
    page.locator('#translation-from').fill('2');page.locator('#translation-to').fill('2')
    page.locator('#settings').click()
    page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    page.locator('#translate-all').click()
    expect(page.locator('#translation-from')).to_be_disabled()
    expect(page.locator('#translation-to')).to_be_disabled()
    page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('继续翻译第 2–2 页',timeout=10000)
    assert 0<len(calls['texts'])<len(expected(2,2))
    page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('所选页翻译已完成',timeout=20000)
    assert calls['texts']==expected(2,2)
    expect(page.locator('#translation-status')).to_contain_text(f"已完成 {len(expected(2,2))} / {len(expected(2,2))} 段")
    # Expanding the selection reuses page 2 and sends only page 3.
    page.locator('#translation-to').fill('3');page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('所选页翻译已完成',timeout=20000)
    assert calls['texts']==expected(2,3)
    out=server.ROOT/'tmp';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'translation-range.png'))
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#translation-tab').click()
    expect(page.locator('#translation-from')).to_have_value('2')
    expect(page.locator('#translation-to')).to_have_value('3')
    expect(page.locator('#translate-all')).to_contain_text('所选页翻译已完成')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'translation-range-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#translation-full').click()
    expect(page.locator('#translation-from')).to_have_value('1')
    page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成',timeout=20000)
    assert calls['texts']==expected(2,3)+expected(1,1)
    assert calls['translation']==sum(p['translatable'] for p in d['paragraphs'])
    assert not errors,errors
    page.close()


def test_translation_empty_page_range(browser,services):
    base,_,calls=services
    source=fitz.open();source.new_page();source.new_page()
    source[0].insert_text((70,100),'Only the first page has text.')
    content=source.tobytes();source.close()
    page=browser.new_page()
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'blank-page.pdf','mimeType':'application/pdf','buffer':content})
    expect(page.locator('#page-total')).to_have_text('2',timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translation-tab').click();page.locator('#translation-from').fill('2')
    expect(page.locator('#translation-range-hint')).to_contain_text('没有可提取的文字')
    expect(page.locator('#translate-all')).to_be_disabled()
    assert calls['translation']==0
    page.close()


def test_bilingual_original_images_columns_and_math(browser,services):
    from test_layout import illustrated_pdf
    base,model,calls=services
    calls['failOnce']=False
    calls['translationText']=r'公式保留：\(E=mc^2\)。显示公式：\[\frac{a}{b}=\sqrt{x}\] <img src=x onerror=alert(1)>'
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'illustrated.pdf','mimeType':'application/pdf','buffer':illustrated_pdf()})
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    expect(page.locator('#page-total')).to_have_text('1',timeout=20000)
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page')).to_have_count(1,timeout=15000)
    expect(page.locator('.layout-row[data-columns="2"]')).not_to_have_count(0)
    page.wait_for_load_state('networkidle')
    image=page.locator('.source-crop img').first
    assert image.evaluate('(img)=>img.complete && img.naturalWidth>0')
    page.locator('#settings').click()
    page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成',timeout=20000)
    expect(page.locator('.translated-text').first.locator('.katex')).to_have_count(2)
    expect(page.locator('.translated-text img')).to_have_count(0)
    out=server.ROOT/'tmp';out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'bilingual-illustrated.png'),full_page=True)
    count=page.locator('.paragraph').count()
    page.locator('#translation-display').select_option('text')
    expect(page.locator('.bilingual-page')).to_have_count(0)
    expect(page.locator('.paragraph')).to_have_count(count)
    expect(page.locator('.translated-text').first.locator('.katex')).to_have_count(2)
    page.locator('#translation-display').select_option('layout')
    expect(page.locator('.paragraph')).to_have_count(count)
    assert calls['translation']==count
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'bilingual-illustrated-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors,errors
    page.close()


def test_full_reading_workflow(browser,services):
    base,model,calls=services
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    out=server.ROOT/'tmp';out.mkdir(exist_ok=True)
    page.goto(base)
    page.locator('#open-sample').click()
    page.locator('.textLayer span').first.wait_for(timeout=30000)
    expect(page.locator('#loading')).to_be_hidden()
    select_text(page,'Reading a research paper')
    page.locator('#note-selection').click()
    page.locator('#note-text').fill('这是一条中文备注：检查导出后的位置。')
    page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    expect(page.locator('.annotation-mark')).to_have_count(1)
    page.locator('#zoom').select_option('1.25')
    page.locator('.textLayer span').first.wait_for()
    expect(page.locator('.annotation-mark')).to_have_count(1)
    with page.expect_download() as dl: page.locator('#export').click()
    export=out/'exported-test.pdf';dl.value.save_as(export)
    with fitz.open(export) as pdf:
        p=pdf[0];a=list(p.annots())[0]
        assert a.info['content'].startswith('这是一条中文备注')
        text_box=p.search_for('Reading a research paper')[0]
        quad=fitz.Quad(a.vertices[:4]).rect
        assert abs(quad.x0-text_box.x0)<1
        assert abs(quad.y0-text_box.y0)<5
        p.get_pixmap(matrix=fitz.Matrix(1,1)).save(out/'exported-test.png')
    page.locator('[data-drawer=annotations]').click()
    expect(page.locator('.annotation-card')).to_have_count(1)
    page.screenshot(path=str(out/'annotations.png'))
    page.locator('#close-drawer').click()
    page.locator('#settings').click()
    page.locator('#api-url').fill(model+'/v1')
    page.locator('#api-model').fill('local-test-model')
    page.locator('#api-key').fill('local-test-key')
    page.locator('#test-connection').click()
    expect(page.locator('#connection-result')).to_contain_text('连接成功',timeout=10000)
    page.locator('#settings-form button[type=submit]').click()
    assert 'local-test-key' not in page.evaluate("localStorage.getItem('paperdesk.config')")
    page.locator('#question').fill('请解释这篇文档。')
    page.locator('#send').click()
    expect(page.locator('.assistant-message .content')).to_contain_text('核心观点',timeout=15000)
    expect(page.locator('#stop-chat')).to_be_hidden()
    page.locator('.page-citation').click()
    expect(page.locator('#page-number')).to_have_value('2')
    page.locator('#translation-tab').click()
    page.locator('#translate-all').click()
    expect(page.locator('.translated-text.failed')).to_have_count(1,timeout=20000)
    expect(page.locator('#translate-all')).to_contain_text('继续翻译')
    page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成',timeout=60000)
    assert calls['translation']==page.locator('.paragraph').count()+1
    page.screenshot(path=str(out/'bilingual.png'))
    with page.expect_download() as dl:page.locator('#export-translation').click()
    md=out/'bilingual.md';dl.value.save_as(md)
    assert '这是用于验证逐段翻译的模拟译文' in md.read_text(encoding='utf-8')
    page.reload()
    expect(page.locator('#annotation-count')).to_have_text('1',timeout=20000)
    expect(page.locator('.assistant-message')).to_have_count(1)
    page.locator('#translation-tab').click()
    expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成')
    page.locator('#settings').click()
    expect(page.locator('#api-key')).to_have_value('')
    page.locator('#settings-dialog .close-dialog').click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors, errors
    page.close()


@pytest.mark.parametrize('rotation',[0,90])
def test_pdf_reference_links_render_and_navigate(browser,services,rotation):
    base,_,_=services
    source=fitz.open()
    source.new_page(width=500,height=600)
    source.new_page(width=500,height=600)
    first=source[0]
    first.insert_text((70,100),'Jump to reference',fontsize=14)
    first.insert_text((70,150),'External reference',fontsize=14)
    first.insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(70,80,220,105),'page':1,'to':fitz.Point(0,0)})
    first.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(70,130,220,155),'uri':'https://example.com/paper'})
    first.set_rotation(rotation)
    source[1].insert_text((70,100),'Reference destination',fontsize=14)
    original=source.tobytes();source.close()
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'linked-paper.pdf','mimeType':'application/pdf','buffer':original})
    expect(page.locator('.page[data-page-number="1"] .link-overlays a')).to_have_count(2,timeout=15000)
    expect(page.locator('#loading')).to_be_hidden()
    expect(page.locator('#toast.error')).to_be_hidden()
    external=page.locator('.link-overlays a[href="https://example.com/paper"]')
    expect(external).to_have_attribute('target','_blank')
    expect(external).to_have_attribute('rel','noopener noreferrer')
    page.locator('.page[data-page-number="1"] .link-overlays a[href="#"]').click()
    expect(page.locator('#page-number')).to_have_value('2')
    expect(page.locator('#toast.error')).to_be_hidden()
    assert not errors,errors
    page.close()


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_cropped_rotated_selection(browser,services,rotation):
    base,_,_=services
    source=fitz.open();p=source.new_page(width=500,height=600)
    p.insert_text((130,180),'Rotated selection alignment',fontsize=16)
    p.set_cropbox(fitz.Rect(40,50,460,550));p.set_rotation(rotation)
    original=source.tobytes();source.close()
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'rotated.pdf','mimeType':'application/pdf','buffer':original})
    page.locator('.textLayer span').first.wait_for(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    select_text(page,'Rotated selection alignment',0,27)
    page.locator('#highlight-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    if rotation==0:
        page.screenshot(path=str(server.ROOT/'tmp'/'cropped-selection.png'))
    with page.expect_download() as download:page.locator('#export').click()
    path=server.ROOT/'tmp'/f'rotated-{rotation}.pdf';download.value.save_as(path)
    with fitz.open(path) as exported:
        p=exported[0]
        rect=p.search_for('Rotated selection alignment')[0]
        a=list(p.annots())[0];actual=fitz.Quad(a.vertices[:4]).rect
        assert abs(actual.x0-rect.x0)<2, (rotation,actual,rect)
        assert abs(actual.y0-rect.y0)<5, (rotation,actual,rect)
        assert abs(actual.x1-rect.x1)<2, (rotation,actual,rect)
        assert a.rect.x0 >= rect.x0-10 and a.rect.x1 <= rect.x1+10, a.rect
    page.close()


def select_bilingual_text(page, selector, start=0, end=None):
    element=page.locator(selector).first
    element.scroll_into_view_if_needed()
    element.evaluate('''(el,{start,end})=>{
        const range=document.createRange();
        if(end===null)range.selectNodeContents(el);
        else {range.setStart(el.firstChild,start);range.setEnd(el.firstChild,end);}
        const selected=window.getSelection();selected.removeAllRanges();selected.addRange(range);
    }''',{'start':start,'end':end})
    page.locator('#paragraphs').dispatch_event('mouseup')
    expect(page.locator('#selection-toolbar')).to_be_visible()


def test_translation_skips_formulas_figures_and_old_fragment_cache(browser,services):
    from test_translation_policy import policy_pdf
    base,model,calls=services;calls['failOnce']=False
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'policy.pdf','mimeType':'application/pdf','buffer':policy_pdf()})
    expect(page.locator('#page-total')).to_have_text('2',timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    doc_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    d=page.request.get(base+f'/api/documents/{doc_id}').json()
    caption=next(p for p in d['paragraphs'] if p['text'].startswith('Fig. 1:'))
    excluded=[p for p in d['paragraphs'] if not p['translatable']]
    mixed=next(p for p in d['paragraphs'] if p['translationSource']!=p['text'])
    with server.LOCK:
        saved=server.state(doc_id)
        saved['translations']['简体中文:'+caption['id']]='已有图注译文，应当继续显示。'
        for p in excluded+[mixed]:saved['translations']['简体中文:'+p['id']]='OLD_FORMULA_FRAGMENT'
        server.write_json(server.folder(doc_id)/'state.json',saved)
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page')).to_have_count(2,timeout=15000)
    eligible=[p for p in d['paragraphs'] if p['translatable']]
    expect(page.locator('.paragraph')).to_have_count(len(eligible))
    for p in excluded:expect(page.locator('#para-'+p['id'])).to_have_count(0)
    expect(page.locator('#paragraphs')).not_to_contain_text('OLD_FORMULA_FRAGMENT')
    expect(page.locator('#para-'+caption['id'])).to_contain_text('已有图注译文')
    expect(page.locator('#para-'+mixed['id'])).to_contain_text('请重新翻译正文')
    page.locator('#translation-from').fill('2');page.locator('#translation-to').fill('2')
    expect(page.locator('#translate-all')).to_be_disabled()
    expect(page.locator('#translation-range-hint')).to_contain_text('无需翻译')
    assert calls['translation']==0
    page.locator('#translation-full').click()
    page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click();page.locator('#translate-all').click()
    expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成',timeout=15000)
    assert calls['texts']==[p['translationSource'] for p in eligible if p['id']!=caption['id']]
    page.locator('.bilingual-page').first.scroll_into_view_if_needed()
    expect(page.locator('.bilingual-page').first).to_have_attribute('data-selectable','true')
    expect(page.locator('.source-crop .textLayer').get_by_text('E = mc',exact=True)).to_have_count(1)
    expect(page.locator('.source-crop .textLayer').get_by_text('ENCODER diagram label',exact=True)).to_have_count(1)
    page.screenshot(path=str(server.ROOT/'tmp'/'translation-policy.png'))
    page.locator('#translation-display').select_option('text')
    expect(page.locator('.paragraph')).to_have_count(len(eligible))
    expect(page.locator('#paragraphs')).not_to_contain_text('OLD_FORMULA_FRAGMENT')
    with page.expect_download() as download:page.locator('#export-translation').click()
    out=server.ROOT/'tmp'/'translation-policy.md';download.value.save_as(out)
    assert 'OLD_FORMULA_FRAGMENT' not in out.read_text(encoding='utf-8')
    restored=page.request.get(base+f'/api/documents/{doc_id}').json()['state']
    assert restored['translations']['简体中文:'+excluded[0]['id']]=='OLD_FORMULA_FRAGMENT'
    assert not errors,errors
    page.close()


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_bilingual_source_selection_export_and_resize(browser,services,rotation):
    base,_,_=services
    source=fitz.open();p=source.new_page(width=500,height=600)
    p.insert_text((130,180),'Selectable original text',fontsize=16)
    p.set_cropbox(fitz.Rect(40,50,460,550));p.set_rotation(rotation)
    original=source.tobytes();source.close()
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'selectable.pdf','mimeType':'application/pdf','buffer':original})
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    expect(page.locator('#page-total')).to_have_text('1')
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page[data-selectable="true"]')).to_have_count(1,timeout=20000)
    selector='.source-page-plane .textLayer span'
    expect(page.locator(selector)).to_have_count(1)
    select_bilingual_text(page,selector)
    assert page.evaluate('getSelection().toString()')=='Selectable original text'
    expect(page.locator('#selection-source')).to_have_text('原文')
    page.locator('#underline-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(200)
    # Both the transparent text layer and its underline move with the crop.
    metrics=page.locator('.source-crop').first.evaluate('''el=>{
        const a=el.querySelector('.textLayer span').getBoundingClientRect(),b=el.querySelector('.annotation-mark').getBoundingClientRect();
        return [Math.abs(a.x-b.x),Math.abs(a.y-b.y),Math.abs(a.width-b.width)];
    }''')
    assert max(metrics)<2,metrics
    doc_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    with fitz.open(stream=page.request.get(base+f'/api/documents/{doc_id}/export').body(),filetype='pdf') as pdf:
        p=pdf[0];expected=p.search_for('Selectable original text')[0]
        a=list(p.annots())[0];actual=fitz.Quad(a.vertices[:4]).rect
        assert abs(actual.x0-expected.x0)<2,(rotation,actual,expected)
        assert abs(actual.x1-expected.x1)<2,(rotation,actual,expected)
        assert abs(actual.y0-expected.y0)<5,(rotation,actual,expected)
    assert not errors,errors
    page.close()


def test_bilingual_translation_annotations_persist_reflow_math_and_stale(browser,services):
    from test_layout import illustrated_pdf
    base,model,calls=services;calls['failOnce']=False
    calls['translationText']=r'译文😀，这是一段可以选择与批注的文字。公式：\(E=mc^2\)，用于核对数学表达式。'*3
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('#file-input').set_input_files({'name':'figures.pdf','mimeType':'application/pdf','buffer':illustrated_pdf()})
    expect(page.locator('#page-total')).to_have_text('1',timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page[data-selectable="true"]')).to_have_count(1,timeout=20000)
    page.locator('#settings').click()
    page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    page.locator('.retry').first.click()
    target='.paragraph:first-of-type .translated-text'
    # Select the first translated paragraph (including a rendered equation).
    element=page.locator('.translated-text').first
    expect(element.locator('.katex')).to_have_count(3,timeout=10000)
    pid=element.evaluate("el=>el.closest('.paragraph').dataset.paragraphId")
    target=f'#para-{pid} .translated-text'
    select_bilingual_text(page,target)
    expect(page.locator('#selection-source')).to_have_text('译文')
    copied=page.evaluate('''()=>{const data=new DataTransfer();document.querySelector('#paragraphs').dispatchEvent(new ClipboardEvent('copy',{clipboardData:data,bubbles:true,cancelable:true}));return data.getData('text/plain');}''')
    assert copied.count('E')==3 and '\\(' not in copied
    page.locator('#note-selection').click()
    page.locator('#note-text').fill('译文笔记：包括公式与换行后的文字')
    page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    marks=page.locator(target+' .annotation-mark')
    expect(marks).not_to_have_count(0)
    doc_id=page.evaluate("localStorage.getItem('paperdesk.last')")
    saved=page.request.get(base+f'/api/documents/{doc_id}').json()['state']['annotations'][0]
    assert saved['source']=='translation' and saved['text'].count('E')==3
    assert '\\(' not in saved['anchorText']  # No hidden MathML/TeX duplicates.
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
    assert marks.count()>0
    assert element.evaluate('''el=>{const b=el.getBoundingClientRect();return [...el.querySelectorAll('.annotation-mark')].every(m=>{const r=m.getBoundingClientRect();return r.left>=b.left-1 && r.right<=b.right+1 && r.bottom<=b.bottom+1;});}''')
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#translation-display').select_option('text')
    expect(marks).not_to_have_count(0)
    with page.expect_download() as download:page.locator('#export-translation').click()
    path=server.ROOT/'tmp'/'translation-notes.md';download.value.save_as(path)
    assert '译文笔记：包括公式' in path.read_text(encoding='utf-8')
    # Translation-only marks must not create annotations at arbitrary original PDF coordinates.
    with fitz.open(stream=page.request.get(base+f'/api/documents/{doc_id}/export').body(),filetype='pdf') as pdf:
        assert all(not list(p.annots()) for p in pdf)
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    expect(page.locator('#annotation-count')).to_have_text('1')
    page.locator('#translation-tab').click();expect(marks).not_to_have_count(0)
    page.locator('#target-language').select_option('English');expect(marks).to_have_count(0)
    page.locator('#target-language').select_option('简体中文');expect(marks).not_to_have_count(0)
    page.locator('#translation-display').select_option('layout')
    expect(page.locator('.bilingual-page[data-selectable="true"]')).to_have_count(1,timeout=15000)
    select_bilingual_text(page,target,5,12);page.locator('#underline-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('2')
    page.screenshot(path=str(server.ROOT/'tmp'/'bilingual-selectable-notes.png'))
    calls['translationText']='重译后的文字与此前不同，不能把旧批注错配到这里。'
    page.locator(f'#para-{pid} .retry').click()
    expect(element).to_contain_text('重译后的文字',timeout=10000)
    expect(marks).to_have_count(0)
    page.locator('[data-drawer=annotations]').click()
    expect(page.locator('.annotation-card')).to_have_count(2)
    expect(page.locator('.annotation-origin').first).to_contain_text('译文已更新')
    page.locator('.annotation-card .edit').first.click();page.locator('#note-text').fill('更新笔记')
    page.locator('#note-form button[type=submit]').click()
    expect(page.locator('.annotation-card').first).to_contain_text('更新笔记')
    page.locator('.annotation-card .delete').last.click();expect(page.locator('#annotation-count')).to_have_text('1')
    assert not errors,errors
    page.close()
