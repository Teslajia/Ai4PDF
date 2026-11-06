import json

from playwright.sync_api import expect
from test_browser import browser, services
from test_browser import select_bilingual_text
from test_chat_images_browser import setup


def test_reasoning_changes_with_model_and_endpoint_without_network_probe(browser,services):
    base,model,calls=services
    page=browser.new_page()
    page.goto(base)
    old={'baseUrl':model+'/v1','model':'gpt-6-sol','reasoningEffort':'max','apiKey':'test-memory','rememberKey':True}
    page.evaluate('(v)=>localStorage.setItem("paperdesk.config",JSON.stringify(v))',old)
    page.reload();page.locator('#settings').click()
    expect(page.locator('#api-reasoning')).to_have_value('default')
    assert page.locator('#api-reasoning option[value=max]').count()==0
    assert page.locator('#api-reasoning option[value=minimal]').count()==0
    page.locator('#api-url').fill('https://api.openai.com/v1')
    assert page.locator('#api-reasoning option[value=max]').count()==1
    page.locator('#api-reasoning').select_option('max')
    page.locator('#api-url').fill(model+'/v1')
    expect(page.locator('#api-reasoning')).to_have_value('default')
    page.locator('#settings-form button[type=submit]').click()
    saved=json.loads(page.evaluate('localStorage.getItem("paperdesk.config")'))
    assert saved['reasoningEffort']=='default' and saved['apiKey']=='test-memory'
    page.locator('#model-options-toggle').click()
    assert page.locator('#quick-reasoning option[value=max]').count()==0
    assert not calls.get('bodies')
    page.close()


def test_translation_only_reuses_math_annotations_and_exports_without_original(browser,services,tmp_path):
    base,model,calls=services;calls['failOnce']=False
    calls['translationText']=r'只读译文，保留公式 \(E=mc^2\) 与笔记。'
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    page.locator('#translation-tab').click();page.locator('.retry').first.click()
    expect(page.locator('.translated-text .katex')).to_have_count(1,timeout=15000)
    pid=page.locator('.paragraph').first.get_attribute('data-paragraph-id')
    card=page.locator(f'#para-{pid}');text=card.locator('.translated-text')
    select_bilingual_text(page,f'#para-{pid} .translated-text',0,4)
    page.locator('#underline-selection').click();expect(page.locator('#annotation-count')).to_have_text('1')
    page.locator('#translated-tab').click()
    expect(card.locator('.original-text')).to_be_hidden()
    expect(text.locator('.katex')).to_have_count(1)
    expect(text.locator('.annotation-mark')).not_to_have_count(0)
    assert page.locator('.source-crop').count()==0 and calls['translation']==1
    card.locator('.translation-toggle').click();expect(text).to_be_hidden()
    page.locator('#translation-tab').click();expect(text).to_be_hidden()
    card.locator('.translation-toggle').click()
    page.locator('#translated-tab').click();expect(text).to_be_visible()
    with page.expect_download() as event:page.locator('#export-translation').click()
    download=event.value;path=tmp_path/download.suggested_filename;download.save_as(path)
    exported=path.read_text(encoding='utf-8')
    data=page.request.get(base+f'/api/documents/{doc_id}').json()
    original=next(p['text'] for p in data['paragraphs'] if p['id']==pid)
    assert calls['translationText'] in exported and original not in exported.split('\n',1)[1]
    assert download.suggested_filename.endswith('-translation.md')
    page.locator('#settings').click();page.locator('#system-language').select_option('en')
    page.locator('#settings-dialog .close-dialog').click()
    expect(page.locator('#translated-tab')).to_have_text('Translation only')
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#translated-tab')).to_be_in_viewport()
    assert not errors,errors
    page.close()
