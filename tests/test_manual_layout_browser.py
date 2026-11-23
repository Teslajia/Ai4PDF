from playwright.sync_api import expect
import pymupdf as fitz
from test_browser import browser,services,select_bilingual_text
from test_layout import illustrated_pdf
from test_manual_layout import stamped_pdf
import app as server


def open_paper(page,base,model,original=None):
    page.goto(base);expect(page.locator('#startup-status')).to_be_hidden();page.locator('#file-input').set_input_files({'name':'manual-layout.pdf','mimeType':'application/pdf','buffer':original or illustrated_pdf()})
    expect(page.locator('#page-total')).to_have_text('1',timeout=20000)
    expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page[data-selectable="true"]')).to_have_count(1,timeout=20000)
    page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    return page.evaluate("localStorage.getItem('paperdesk.last')")


def editor_ready(page):
    page.locator('.edit-layout').click()
    expect(page.locator('#layout-editor')).to_be_visible()
    expect(page.locator('#layout-edit-status')).to_contain_text('修改仅在',timeout=15000)


def test_manual_merge_split_undo_translate_and_restore(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='调整后的段落可以翻译并添加批注。'
    page=browser.new_page(viewport={'width':1600,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=open_paper(page,base,model);url=base+'/api/documents/'+doc_id
    edit=page.request.get(url+'/layout/pages/1').json();paragraphs=edit['paragraphs']
    p1=next(p for p in paragraphs if p['text'].startswith('Left paragraph 1'))
    p2=next(p for p in paragraphs if p['text'].startswith('Left paragraph 2'))
    def owner(p):
        r=p['bbox'];x=(r[0]+r[2])/2;y=(r[1]+r[3])/2
        return next(b for b in edit['blocks'] if b['rect'][0]<=x<b['rect'][2] and b['rect'][1]<=y<b['rect'][3])
    a,b=owner(p1),owner(p2);original_count=len(edit['blocks'])
    # Cache an original translation; it must return after resetting the page.
    page.locator(f"#para-{p1['id']} .retry").click()
    expect(page.locator(f"#para-{p1['id']} .translated-text")).to_contain_text('调整后的段落',timeout=10000)
    editor_ready(page)
    page.locator('[data-mode="merge"]').click()
    page.locator(f'[data-block-id="{a["id"]}"]').click();page.locator(f'[data-block-id="{b["id"]}"]').click()
    page.locator('#layout-merge').click();expect(page.locator('.layout-edit-block')).to_have_count(original_count-1)
    assert 'Left paragraph 1' in page.locator('#layout-block-text').input_value()
    assert 'Left paragraph 2' in page.locator('#layout-block-text').input_value()
    page.locator('#layout-undo').click();expect(page.locator('.layout-edit-block')).to_have_count(original_count)
    page.locator('#layout-redo').click();expect(page.locator('.layout-edit-block')).to_have_count(original_count-1)
    page.screenshot(path=str(server.ROOT/'tmp'/'manual-layout-editor.png'))
    page.locator('#layout-edit-save').click();expect(page.locator('#layout-editor')).not_to_be_visible(timeout=15000)
    expect(page.locator('.bilingual-page-heading')).to_contain_text('已手动调整')
    expect(page.locator(f"#para-{p1['id']}")).to_have_count(0)
    active=page.request.get(url).json()['translationParagraphs'];merged=next(p for p in active if p.get('manual'))
    assert p1['text'] in merged['text'] and p2['text'] in merged['text']
    page.locator(f"#para-{merged['id']} .retry").click()
    element=page.locator(f"#para-{merged['id']} .translated-text")
    expect(element).to_contain_text('调整后的段落',timeout=10000)
    assert calls['texts'][-1]==merged['translationSource']
    select_bilingual_text(page,f"#para-{merged['id']} .translated-text",0,6)
    page.locator('#underline-selection').click();expect(page.locator('#annotation-count')).to_have_text('1')
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#translation-tab').click();expect(element).to_contain_text('调整后的段落',timeout=15000)
    expect(page.locator('.bilingual-page[data-selectable="true"]')).to_have_count(1)
    expect(element.locator('.annotation-mark')).not_to_have_count(0)
    # Source text remains selectable once per run, and native PDF annotation
    # coordinates still refer to the original page after manual regrouping.
    expect(page.locator('.bilingual-page .textLayer').get_by_text('A paper with figures and mathematics',exact=True)).to_have_count(1)
    select_bilingual_text(page,'.bilingual-page .textLayer span',0,12)
    expect(page.locator('#selection-source')).to_have_text('原文')
    page.locator('#highlight-selection').click();expect(page.locator('#annotation-count')).to_have_text('2')
    with fitz.open(stream=page.request.get(url+'/export').body(),filetype='pdf') as pdf:
        assert len(list(pdf[0].annots()))==1
    # Split the merged source back at its old gap using the keyboard-friendly control.
    editor_ready(page);new_edit=page.request.get(url+'/layout/pages/1').json()
    block=next(b for b in new_edit['blocks'] if b['regroup'])
    page.locator(f'[data-block-id="{block["id"]}"]').click();page.locator('[data-mode="horizontal"]').click()
    position=(a['rect'][3]-block['rect'][1])/(block['rect'][3]-block['rect'][1])*100
    page.locator('#layout-cut-percent').fill(str(position));page.locator('#layout-cut-apply').click()
    expect(page.locator('.layout-edit-block')).to_have_count(original_count)
    page.locator('#layout-edit-save').click();expect(page.locator('#layout-editor')).not_to_be_visible(timeout=15000)
    expect(page.locator(f"#para-{p1['id']} .translated-text")).to_contain_text('调整后的段落')
    page.locator('[data-drawer="annotations"]').click()
    expect(page.locator('.annotation-origin')).to_contain_text('切分已调整，保留旧批注')
    page.locator('#close-drawer').click()
    with page.expect_download() as download:page.locator('#export-translation').click()
    path=server.ROOT/'tmp'/'manual-layout-notes.md';download.value.save_as(path)
    assert '历史译文批注' in path.read_text(encoding='utf-8')
    editor_ready(page);page.locator('#layout-reset').click();page.locator('#layout-edit-save').click()
    expect(page.locator('#layout-editor')).not_to_be_visible(timeout=15000)
    expect(page.locator('.bilingual-page-heading')).not_to_contain_text('已手动调整')
    assert not page.request.get(url).json()['manualPages']
    assert not errors,errors
    page.close()


def test_manual_vertical_split_skip_cancel_and_small_screen(browser,services):
    base,model,_=services;page=browser.new_page(viewport={'width':1440,'height':1000})
    doc_id=open_paper(page,base,model)
    editor_ready(page)
    # Whole-page merge followed by a horizontal and vertical cut repairs a missed column boundary.
    page.locator('#layout-select-all').click()
    page.locator('#layout-merge').click();expect(page.locator('.layout-edit-block')).to_have_count(1)
    page.locator('[data-mode="horizontal"]').click();page.locator('#layout-cut-percent').fill('35');page.locator('#layout-cut-apply').click()
    expect(page.locator('.layout-edit-block')).to_have_count(2)
    page.locator('[data-mode="select"]').click();page.locator('.layout-edit-block').last.click()
    page.locator('[data-mode="vertical"]').click();page.locator('#layout-cut-percent').fill('50');page.locator('#layout-cut-apply').click()
    expect(page.locator('.layout-edit-block')).to_have_count(3)
    page.locator('#layout-block-skip').check();expect(page.locator('.layout-edit-block.skipped')).to_have_count(1)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(server.ROOT/'tmp'/'manual-layout-editor-mobile.png'))
    page.locator('.layout-edit-footer .layout-edit-close').click()
    expect(page.locator('#layout-editor')).not_to_be_visible()
    assert not page.request.get(base+'/api/documents/'+doc_id).json()['manualPages']
    page.close()


def test_skip_saves_with_stamp_hides_cached_cards_and_reports_save_failure(browser,services):
    base,model,calls=services;calls['failOnce']=False
    page=browser.new_page(viewport={'width':1500,'height':1050})
    doc_id=open_paper(page,base,model,stamped_pdf());url=base+'/api/documents/'+doc_id
    edit=page.request.get(url+'/layout/pages/1').json()
    p=next(p for p in edit['paragraphs'] if p['text'].startswith('Left paragraph 1'))
    x=(p['bbox'][0]+p['bbox'][2])/2;y=(p['bbox'][1]+p['bbox'][3])/2
    block=next(b for b in edit['blocks'] if b['rect'][0]<x<b['rect'][2] and b['rect'][1]<y<b['rect'][3])
    page.locator(f"#para-{p['id']} .retry").click()
    expect(page.locator(f"#para-{p['id']} .translated-text")).to_contain_text('模拟译文',timeout=10000)
    before=page.request.get(url).json()['state']
    editor_ready(page);page.locator(f'[data-block-id="{block["id"]}"]').click();page.locator('#layout-block-skip').check()
    # A failed request leaves the draft intact and a clear in-dialog error.
    route_pattern=f'**/api/documents/{doc_id}/layout/pages/1'
    page.route(route_pattern,lambda route:route.fulfill(status=409,content_type='application/json',body='{"error":"模拟保存失败，请重试。"}') if route.request.method=='PUT' else route.continue_())
    page.locator('#layout-edit-save').click()
    expect(page.locator('#layout-edit-error')).to_contain_text('未保存：模拟保存失败')
    expect(page.locator('#layout-block-skip')).to_be_checked()
    expect(page.locator('#layout-edit-save')).to_have_text('重试保存')
    page.unroute(route_pattern);page.locator('#layout-edit-save').click()
    expect(page.locator('#layout-editor')).not_to_be_visible(timeout=15000)
    expect(page.locator(f"#para-{p['id']}")).to_have_count(0)
    page.locator('#translation-display').select_option('text')
    expect(page.locator(f"#para-{p['id']}")).to_have_count(0)
    saved=page.request.get(url).json();assert p['id'] not in {q['id'] for q in saved['translationParagraphs']}
    assert saved['state']['translations']==before['translations']
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=20000);page.locator('#translation-tab').click()
    expect(page.locator(f"#para-{p['id']}")).to_have_count(0)
    page.locator('#translation-display').select_option('layout')
    editor_ready(page);page.locator(f'[data-block-id="{block["id"]}"]').click()
    expect(page.locator('#layout-block-skip')).to_be_checked()
    page.locator('[aria-label="关闭切分编辑"]').click()
    page.locator('#translate-all').click();expect(page.locator('#translate-all')).to_contain_text('全文翻译已完成',timeout=20000)
    assert calls['texts'].count(p['translationSource'])==1  # Only the original, pre-skip request.
    page.close()
