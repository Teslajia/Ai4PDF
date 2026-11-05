from playwright.sync_api import expect

import app as server
from test_browser import browser, services, select_bilingual_text, other_document
from test_chat_images_browser import setup


def test_independent_translation_folds_persist_and_restore_math_notes(browser,services):
    base,model,calls=services;calls['failOnce']=False
    calls['translationText']=r'这里是已翻译的段落，折叠后可以再次展开。公式 \(E=mc^2\) 和批注都会保留。'*3
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    page.locator('#translation-tab').click();page.locator('.retry').first.click()
    text=page.locator('.translated-text').first
    expect(text.locator('.katex')).to_have_count(3,timeout=15000)
    pid=text.evaluate("el=>el.closest('.paragraph').dataset.paragraphId")
    card=page.locator(f'#para-{pid}');text=card.locator('.translated-text');toggle=card.locator('.translation-toggle')
    select_bilingual_text(page,f'#para-{pid} .translated-text',0,15);page.locator('#underline-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    stored=page.request.get(base+f'/api/documents/{doc_id}').json()['state']
    expect(toggle).to_have_text('折叠');expect(toggle).to_have_attribute('aria-expanded','true')
    toggle_box=toggle.bounding_box();retry_box=card.locator('.retry').bounding_box()
    assert toggle_box['x']+toggle_box['width']<=retry_box['x']
    expanded_height=card.bounding_box()['height']
    toggle.click();expect(text).to_be_hidden();expect(toggle).to_have_text('展开')
    expect(toggle).to_have_attribute('aria-expanded','false')
    expect(page.locator('.translated-text').nth(1)).to_be_visible()
    assert card.bounding_box()['height']<expanded_height/2
    page.screenshot(path=str(server.ROOT/'tmp'/'translation-fold-collapsed.png'))
    # Layout switches retain the fold, and original text remains visible.
    page.locator('#translation-display').select_option('text')
    expect(text).to_be_hidden();expect(card.locator('.original-text')).to_be_visible()
    page.locator('#translation-display').select_option('layout');expect(text).to_be_hidden()
    page.reload();expect(page.locator('#page-total')).to_have_text('3',timeout=20000)
    expect(page.locator('#loading')).to_be_hidden();page.locator('#translation-tab').click()
    expect(toggle).to_have_text('展开');expect(text).to_be_hidden()
    toggle.click();expect(text).to_be_visible();expect(text.locator('.katex')).to_have_count(3)
    expect(text.locator('.annotation-mark')).not_to_have_count(0)
    assert text.evaluate('''el=>{const b=el.getBoundingClientRect();return [...el.querySelectorAll('.annotation-mark')].every(m=>{const r=m.getBoundingClientRect();return r.width>0&&r.left>=b.left-1&&r.right<=b.right+1;});}''')
    state=page.request.get(base+f'/api/documents/{doc_id}').json()['state']
    assert state['translations']==stored['translations'] and state['annotations']==stored['annotations']
    assert calls['translation']==1
    page.screenshot(path=str(server.ROOT/'tmp'/'translation-fold-expanded.png'))
    # Jumping from the annotations drawer opens its folded translation first.
    toggle.click();page.locator('[data-drawer="annotations"]').click()
    page.locator('.annotation-card .page-link').click()
    expect(text).to_be_visible();expect(toggle).to_have_text('折叠')
    expect(text.locator('.annotation-mark')).not_to_have_count(0)
    assert not errors,errors
    page.close()


def test_folds_are_separate_by_language_and_document_and_allow_retranslation(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='初次翻译'
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    page.locator('#translation-tab').click();page.locator('.retry').first.click()
    expect(page.locator('.translated-text').first).to_have_text('初次翻译',timeout=15000)
    pid=page.locator('.paragraph').first.get_attribute('data-paragraph-id')
    card=page.locator(f'#para-{pid}');toggle=card.locator('.translation-toggle');text=card.locator('.translated-text')
    toggle.click();expect(text).to_be_hidden()
    page.locator('#target-language').select_option('English');expect(toggle).to_have_text('折叠');expect(text).to_be_visible()
    page.locator('#target-language').select_option('简体中文');expect(toggle).to_have_text('展开');expect(text).to_be_hidden()
    calls['translationText']='重新翻译的新内容'
    card.locator('.retry').click()
    expect(card.locator('.retry')).to_be_enabled(timeout=15000)
    expect(text).to_have_text('重新翻译的新内容');expect(text).to_be_hidden()
    toggle.click();expect(text).to_be_visible();assert calls['translation']==2
    page.locator('#settings').click();page.locator('#system-language').select_option('en');page.locator('#settings-dialog .close-dialog').click()
    expect(toggle).to_have_text('Collapse');toggle.click();expect(toggle).to_have_text('Expand')
    page.set_viewport_size({'width':390,'height':844})
    toggle.scroll_into_view_if_needed();expect(toggle).to_be_in_viewport()
    assert card.locator('.paragraph-meta').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
    page.screenshot(path=str(server.ROOT/'tmp'/'translation-fold-mobile-en.png'))
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#file-input').set_input_files({'name':'other.pdf','mimeType':'application/pdf','buffer':other_document()})
    expect(page.locator('#doc-title')).to_have_text('Another research paper');expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translation-tab').click()
    assert page.locator('.translation-toggle[aria-expanded="false"]').count()==0
    # Restoring the original document also restores its own fold preference.
    page.evaluate('(id)=>localStorage.setItem("paperdesk.last",id)',doc_id);page.reload()
    expect(page.locator('#page-total')).to_have_text('3',timeout=20000);expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translation-tab').click();expect(toggle).to_have_text('Expand');expect(text).to_be_hidden()
    assert not errors,errors
    page.close()
