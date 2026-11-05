from playwright.sync_api import expect

import app as server
from test_browser import browser, services, select_text


def test_note_window_clear_background_drag_preserves_anchor_and_stays_visible(browser,services):
    base,_,_=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    select_text(page,'Reading a research paper')
    page.locator('#note-selection').click()
    dialog=page.locator('#note-dialog');handle=page.locator('.note-drag-handle')
    expect(dialog).to_be_visible()
    original_quote=page.locator('#note-quote').inner_text()
    page.locator('#note-text').fill('Drag the window while preserving the selected PDF text.')
    backdrop=dialog.evaluate("el=>{const s=getComputedStyle(el,'::backdrop');return {filter:s.backdropFilter,background:s.backgroundColor};}")
    assert backdrop=={'filter':'none','background':'rgba(0, 0, 0, 0)'}
    before=dialog.bounding_box();heading=handle.bounding_box()
    page.mouse.move(heading['x']+90,heading['y']+20);page.mouse.down()
    page.mouse.move(heading['x']+410,heading['y']-160,steps=12);page.mouse.up()
    after=dialog.bounding_box()
    assert abs(after['x']-before['x']-320)<2 and abs(after['y']-before['y']+180)<2
    expect(page.locator('#note-text')).to_be_focused()
    expect(page.locator('#note-text')).to_have_value('Drag the window while preserving the selected PDF text.')
    expect(page.locator('#note-quote')).to_have_text(original_quote)
    page.screenshot(path=str(server.ROOT/'tmp'/'note-draggable-desktop.png'))
    page.locator('#note-form button[type=submit]').click()
    expect(dialog).to_be_hidden();expect(page.locator('#annotation-count')).to_have_text('1')
    doc_id=page.evaluate('localStorage.getItem("paperdesk.last")')
    saved=page.request.get(base+f'/api/documents/{doc_id}').json()['state']['annotations'][0]
    assert saved['text']==original_quote and saved['note'].startswith('Drag the window')
    page.locator('[data-drawer="annotations"]').click();page.locator('.annotation-card .edit').click()
    reopened=dialog.bounding_box()
    assert abs(reopened['x']-after['x'])<2 and abs(reopened['y']-after['y'])<2
    handle.focus();handle.press('ArrowLeft');handle.press('Shift+ArrowDown')
    moved=dialog.bounding_box()
    assert abs(moved['x']-reopened['x']+10)<2 and abs(moved['y']-reopened['y']-40)<2
    heading=handle.bounding_box()
    page.mouse.move(heading['x']+80,heading['y']+20);page.mouse.down();page.mouse.move(1439,999,steps=10);page.mouse.up()
    edge=dialog.bounding_box()
    assert edge['x']>=8 and edge['y']>=8 and edge['x']+edge['width']<=1432 and edge['y']+edge['height']<=992
    page.set_viewport_size({'width':390,'height':600})
    expect(dialog).to_be_in_viewport(ratio=1)
    page.wait_for_function('''()=>{const b=document.querySelector('#note-dialog').getBoundingClientRect();return b.left>=8&&b.top>=8&&b.right<=382&&b.bottom<=592;}''')
    expect(page.locator('#note-dialog .close-dialog')).to_be_in_viewport()
    expect(page.locator('#note-form button[type=submit]')).to_be_in_viewport()
    page.screenshot(path=str(server.ROOT/'tmp'/'note-draggable-mobile.png'))
    page.locator('#note-text').fill('Unsaved draft');page.locator('#note-text').press('Escape')
    expect(dialog).to_be_hidden()
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('.annotation-card .edit').click()
    expect(page.locator('#note-text')).to_have_value(saved['note'])
    page.locator('#note-text').fill('Updated after moving')
    page.locator('#note-form button[type=submit]').click()
    expect(page.locator('.annotation-card')).to_contain_text('Updated after moving')
    # Other modal dialogs keep their existing backdrop.
    page.locator('#settings').click()
    assert page.locator('#settings-dialog').evaluate("el=>getComputedStyle(el,'::backdrop').backdropFilter")=='blur(3px)'
    page.locator('#system-language').select_option('en');page.locator('#settings-dialog .close-dialog').click()
    page.locator('.annotation-card .edit').click()
    expect(page.locator('.note-move-hint')).to_have_text('Drag the title bar to move')
    page.locator('#note-dialog .close-dialog').click();expect(dialog).to_be_hidden()
    assert not errors,errors
    page.close()
