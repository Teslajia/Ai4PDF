from playwright.sync_api import expect

import app as server
from test_browser import browser, services, select_text, select_bilingual_text
from test_chat_images_browser import setup


def click_mark(page,selector):
    marks=page.locator(selector)
    marks.first.wait_for(state='attached')
    # A bilingual page paints a whole PDF plane in each crop. Only click its
    # visible intersection, never a clipped copy of the same annotation.
    for index in range(marks.count()):
        mark=marks.nth(index)
        if not mark.evaluate('''el=>{const b=el.getBoundingClientRect(),r=el.closest('.source-crop,.translated-text,.page').getBoundingClientRect();return Math.min(b.right,r.right)-Math.max(b.left,r.left)>3&&Math.min(b.bottom,r.bottom)-Math.max(b.top,r.top)>3;}'''):
            continue
        # ResizeObserver repaints annotation spans after reflow. Scroll
        # synchronously instead of retaining a span while waiting for stability.
        mark.evaluate("el=>el.scrollIntoView({block:'center',behavior:'instant'})")
        page.evaluate('''()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))''')
        point=mark.evaluate('''el=>{const b=el.getBoundingClientRect(),r=el.closest('.source-crop,.translated-text,.page').getBoundingClientRect();return {x:(Math.max(b.left,r.left)+Math.min(b.right,r.right))/2,y:(Math.max(b.top,r.top)+Math.min(b.bottom,r.bottom))/2};}''')
        page.mouse.click(point['x'],point['y'])
        return point
    raise AssertionError('No visible annotation fragment')


def test_original_quick_edit_overlap_drag_and_bilingual_crop(browser,services):
    base,_,_=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    select_text(page,'Reading a research paper',0,45);page.locator('#note-selection').click()
    page.locator('#note-text').fill('First note');page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    doc_id=page.evaluate('localStorage.getItem("paperdesk.last")')
    def saved():return page.request.get(base+f'/api/documents/{doc_id}').json()['state']['annotations']
    first=saved()[0];aid=first['id'];selector=f'#pages .annotation-mark[data-annotation-id="{aid}"]'
    popup=page.locator('#annotation-actions')
    click_mark(page,selector)
    expect(popup).to_be_visible();expect(popup.locator('.annotation-quick-edit')).to_have_count(1)
    expect(popup).to_contain_text('First note');expect(page.locator('#selection-toolbar')).to_be_hidden()
    page.screenshot(path=str(server.ROOT/'tmp'/'annotation-quick-edit-original.png'))
    popup.locator('.annotation-quick-edit').click()
    expect(popup).to_be_hidden();expect(page.locator('#note-text')).to_have_value('First note')
    expect(page.locator('#note-quote')).to_have_text(first['text'])
    page.locator('#note-text').fill('Revised from highlighted text');page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#note-dialog')).to_be_hidden()
    updated=saved()[0]
    assert updated['id']==aid and updated['note']=='Revised from highlighted text'
    assert updated['quads']==first['quads'] and updated['rects']==first['rects']
    # Native dragging over a highlight still selects text instead of opening edit.
    rect=page.locator(selector).first.bounding_box()
    page.mouse.move(rect['x']+2,rect['y']+rect['height']/2);page.mouse.down()
    page.mouse.move(rect['x']+rect['width']-3,rect['y']+rect['height']/2,steps=12);page.mouse.up()
    expect(page.locator('#selection-toolbar')).to_be_visible();expect(popup).to_be_hidden()
    assert page.evaluate('window.getSelection().toString().length')>5
    # Overlap: choose the second annotation explicitly; the first stays unchanged.
    select_text(page,'Reading a research paper',0,45);page.locator('#underline-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('2')
    second=saved()[1]
    click_mark(page,selector);expect(popup.locator('.annotation-quick-edit')).to_have_count(2)
    popup.locator(f'[data-annotation-id="{second["id"]}"] .annotation-quick-edit').click()
    page.locator('#note-text').fill('Underline note');page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#note-dialog')).to_be_hidden()
    assert saved()[0]['note']=='Revised from highlighted text' and saved()[1]['note']=='Underline note'
    click_mark(page,selector);page.keyboard.press('Escape');expect(popup).to_be_hidden()
    click_mark(page,selector);page.locator('.brand').hover();page.mouse.wheel(0,200)
    # The wheel outside a scrollable area may not scroll; explicitly scroll the reader.
    page.locator('#pdf-scroll').evaluate('el=>el.scrollTop+=120');expect(popup).to_be_hidden()
    page.locator('#zoom').select_option('1.25')
    expect(page.locator(selector)).not_to_have_count(0)
    click_mark(page,selector);expect(popup).to_be_visible()
    page.locator('#translation-tab').click();expect(popup).to_be_hidden()
    expect(page.locator('.bilingual-page[data-selectable="true"]').first).to_be_visible(timeout=20000)
    translated_original=f'#paragraphs .source-crop .annotation-mark[data-annotation-id="{aid}"]'
    expect(page.locator(translated_original)).not_to_have_count(0)
    click_mark(page,translated_original);expect(popup).to_be_visible()
    popup.locator(f'[data-annotation-id="{aid}"] .annotation-quick-edit').click()
    expect(page.locator('#note-text')).to_have_value('Revised from highlighted text')
    page.locator('#note-dialog .close-dialog').click()
    assert len(saved())==2 and not errors,errors
    page.close()


def test_translation_quick_edit_reflow_localization_and_stale_anchor(browser,services):
    base,model,calls=services;calls['failOnce']=False
    calls['translationText']=r'这是一段可以划线、点击和修改批注的译文。公式 \(E=mc^2\) 保持可读。'*3
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    page.locator('#translation-tab').click();page.locator('.retry').first.click()
    element=page.locator('.translated-text').first
    expect(element).to_contain_text('这是一段',timeout=15000)
    pid=element.evaluate("el=>el.closest('.paragraph').dataset.paragraphId")
    target=f'#para-{pid} .translated-text'
    select_bilingual_text(page,target,0,22);page.locator('#underline-selection').click()
    expect(page.locator('#annotation-count')).to_have_text('1')
    first=page.request.get(base+f'/api/documents/{doc_id}').json()['state']['annotations'][0]
    aid=first['id'];selector=f'{target} .annotation-mark[data-annotation-id="{aid}"]'
    popup=page.locator('#annotation-actions')
    click_mark(page,selector);expect(popup).to_be_visible();popup.locator('.annotation-quick-edit').click()
    expect(page.locator('#note-quote')).to_have_text(first['text'])
    page.locator('#note-text').fill('取消');page.locator('#note-form button[type=submit]').click()
    expect(page.locator('#note-dialog')).to_be_hidden()
    updated=page.request.get(base+f'/api/documents/{doc_id}').json()['state']['annotations'][0]
    assert updated['id']==aid and updated['source']=='translation' and updated['note']=='取消'
    assert updated['start']==first['start'] and updated['end']==first['end']
    page.locator('#settings').click();page.locator('#system-language').select_option('en');page.locator('#settings-dialog .close-dialog').click()
    page.set_viewport_size({'width':390,'height':844})
    click_mark(page,selector);expect(popup).to_be_visible()
    expect(popup.locator('.annotation-quick-edit')).to_have_text('Edit')
    expect(popup.locator('.annotation-action-preview p')).to_have_text('取消')
    expect(popup).to_be_in_viewport(ratio=1)
    page.screenshot(path=str(server.ROOT/'tmp'/'annotation-quick-edit-mobile.png'))
    page.set_viewport_size({'width':1440,'height':1000});expect(popup).to_be_hidden()
    page.locator('#translation-display').select_option('text')
    click_mark(page,selector);expect(popup).to_be_visible()
    page.locator('#translation-display').select_option('layout');expect(popup).to_be_hidden()
    calls['translationText']='Completely replaced translation.'
    page.locator(f'#para-{pid} .retry').click();expect(element).to_have_text('Completely replaced translation.')
    expect(page.locator(selector)).to_have_count(0)
    element.click();expect(popup).to_be_hidden()
    assert not errors,errors
    page.close()
