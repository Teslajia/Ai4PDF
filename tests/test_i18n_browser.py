import json

from playwright.sync_api import expect

import app as server
from test_browser import browser, services


def test_system_languages_without_api_immediate_persistence_and_live_controls(browser,services):
    base,_,calls=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base)
    expect(page.locator('html')).to_have_attribute('lang','zh-CN')
    assert page.locator('#target-language option').evaluate_all('(items)=>items.map(i=>i.value)')==['简体中文','繁體中文','한국어','日本語','English']
    page.locator('#settings').click()
    for language,open_label,save_label,heading in [('zh-TW','開啟 PDF','儲存設定','設定'),('ko','PDF 열기','설정 저장','설정'),('ja','PDF を開く','設定を保存','設定'),('en','Open PDF','Save settings','Settings'),('zh-CN','打开 PDF','保存设置','设置')]:
        page.locator('#system-language').select_option(language)
        expect(page.locator('html')).to_have_attribute('lang',language)
        expect(page.locator('#import')).to_have_text(open_label)
        expect(page.locator('#settings-form button[type=submit]')).to_have_text(save_label)
        expect(page.locator('#settings-dialog .dialog-heading h2')).to_have_text(heading)
        expect(page.locator('#api-url')).to_have_value('')
        expect(page.locator('#target-language')).to_have_value('简体中文')
        if language in ('ja','en'):
            page.set_viewport_size({'width':390,'height':844})
            panel=page.locator('#settings-dialog').bounding_box()
            assert panel['x']>=0 and panel['x']+panel['width']<=390
            page.screenshot(path=str(server.ROOT/'tmp'/f'language-settings-mobile-{language}.png'))
            page.set_viewport_size({'width':1440,'height':1000})
        if language=='ko':page.screenshot(path=str(server.ROOT/'tmp'/'language-settings-ko.png'))
        if language=='en':page.screenshot(path=str(server.ROOT/'tmp'/'language-settings-en.png'))
        # System-language changes must not require saving an incomplete API form.
        page.locator('#settings-dialog .close-dialog').click()
        page.reload();expect(page.locator('#import')).to_have_text(open_label)
        page.locator('#settings').click();expect(page.locator('#system-language')).to_have_value(language)
    assert not calls.get('bodies') and not calls.get('models')
    assert not errors,errors
    page.close()


def test_user_content_untouched_and_translation_targets_keep_separate_caches(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='保存设置'
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base);page.locator('#open-sample').click()
    page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    doc_id=page.evaluate('localStorage.getItem("paperdesk.last")')
    original=server.folder(doc_id)/'document.json'
    metadata=json.loads(original.read_text(encoding='utf8'));metadata['title']='保存设置';server.write_json(original,metadata)
    page.request.patch(base+f'/api/documents/{doc_id}/state',data={'messages':[{'role':'user','content':'打开 PDF'},{'role':'assistant','content':'保存设置'}]})
    config={'baseUrl':model+'/v1','model':'local-test-model','displayName':'保存设置','apiKey':'','rememberKey':False}
    page.evaluate('(config)=>localStorage.setItem("paperdesk.config",JSON.stringify(config))',config)
    page.reload();page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    page.locator('#settings').click();page.locator('#system-language').select_option('ko')
    page.locator('#settings-dialog .close-dialog').click()
    expect(page.locator('#model-status span:nth-child(2)')).to_have_text('保存设置')
    expect(page.locator('#doc-title')).to_have_text('保存设置')
    expect(page.locator('.message.user .content')).to_have_text('打开 PDF')
    expect(page.locator('.message.assistant-message .content')).to_have_text('保存设置')
    expect(page.locator('#pages')).to_contain_text('Reading a research paper')
    page.locator('#translation-tab').click()
    for target in ['简体中文','繁體中文','한국어','日本語','English']:
        page.locator('#target-language').select_option(target)
        page.locator('.retry').first.click()
        expect(page.locator('.translated-text').first).to_have_text('保存设置')
        expect(page.locator('#target-language')).to_be_enabled()
        assert f'into {target}.' in calls['bodies'][-1]['messages'][0]['content']
    assert calls['translation']==5
    page.locator('#target-language').select_option('繁體中文')
    expect(page.locator('.translated-text').first).to_have_text('保存设置')
    assert calls['translation']==5
    for locale in ['zh-TW','ja','en','ko']:
        page.locator('#settings').click();page.locator('#system-language').select_option(locale)
        page.locator('#settings-dialog .close-dialog').click()
        expect(page.locator('#target-language')).to_have_value('繁體中文')
        expect(page.locator('.translated-text').first).to_have_text('保存设置')
        expect(page.locator('#doc-title')).to_have_text('保存设置')
        page.screenshot(path=str(server.ROOT/'tmp'/f'language-{locale}.png'))
    page.reload();page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    expect(page.locator('html')).to_have_attribute('lang','ko')
    page.locator('#translation-tab').click()
    expect(page.locator('#target-language')).to_have_value('繁體中文')
    expect(page.locator('.translated-text').first).to_have_text('保存设置')
    assert calls['translation']==5
    state=page.request.get(base+f'/api/documents/{doc_id}').json()['state']
    assert len(state['translations'])==5 and state['messages'][0]['content']=='打开 PDF'
    # Freshly generated controls are localized, not just the initial HTML.
    page.locator('.edit-layout').first.click()
    expect(page.locator('#layout-edit-save')).to_have_text('조정 저장')
    expect(page.locator('#layout-editor .layout-edit-body')).to_be_visible()
    page.locator('#layout-editor .layout-edit-close').first.click()
    page.locator('#model-options-toggle').click();page.locator('#quick-model-fetch').click()
    expect(page.locator('#quick-model-hint')).to_contain_text('모델 3개')
    expect(page.locator('#quick-model-list .model-choice')).to_have_count(3)
    assert 'local-test-model' in page.locator('#quick-model-list .model-choice').all_text_contents()
    assert not errors,errors
    page.close()
