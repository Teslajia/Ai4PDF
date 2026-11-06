import pymupdf as fitz
from playwright.sync_api import expect

import app as server
from test_browser import browser,services
from test_layout import illustrated_pdf
from test_table_captions import table_pdf


def mixed_pdf():
    with fitz.open() as pdf:
        for raw in [illustrated_pdf(),table_pdf(),table_pdf(below=True)]:
            with fitz.open(stream=raw,filetype='pdf') as source:pdf.insert_pdf(source)
        return pdf.tobytes()


def open_visuals(page,base):
    page.goto(base)
    page.evaluate("localStorage.setItem('paperdesk.display','text')")
    page.reload()
    page.locator('#file-input').set_input_files({'name':'visuals.pdf','mimeType':'application/pdf','buffer':mixed_pdf()})
    expect(page.locator('#loading')).to_be_hidden(timeout=30000)
    page.locator('#pages .textLayer span').first.wait_for()
    return page.evaluate("localStorage.getItem('paperdesk.last')")


def test_translation_only_figures_tables_caption_order_copy_annotations_and_preview(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='图一：保留原图、矢量图形与图注。'
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=open_visuals(page,base)
    page.locator('#translated-tab').click()
    expect(page.locator('.translation-visual')).to_have_count(4,timeout=20000)
    assert page.locator('.source-crop:not(.visual-crop)').count()==0
    assert page.locator('.original-text:visible').count()==0
    formula=page.locator('.translation-visual[data-visual-kind="formula"] .visual-crop')
    assert formula.evaluate('el=>el.clientWidth<200&&el.clientHeight<100')
    data=page.request.get(base+f'/api/documents/{doc_id}').json()
    # The table caption belongs above or below its table according to the PDF.
    for number,above in [(2,True),(3,False)]:
        ids=[p['id'] for p in data['paragraphs'] if p['page']==number and ('Table 1.' in p['text'] or 'Higher values' in p['text'])]
        for pid in ids:
            assert page.locator(f'#para-{pid}').evaluate('''(el,n)=>!!(el.compareDocumentPosition(document.querySelector(`.translated-page[data-source-page="${n}"] .translation-visual`))&Node.DOCUMENT_POSITION_FOLLOWING)''',number)==above
    caption=next(p for p in data['paragraphs'] if p['text'].startswith('Figure 1.'))
    page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    page.locator(f'#para-{caption["id"]} .retry').click()
    expect(page.locator(f'#para-{caption["id"]} .translated-text')).to_have_text(calls['translationText'])
    table=page.locator('.translated-page[data-source-page="2"] .translation-visual')
    table.scroll_into_view_if_needed()
    expect(table.locator('.textLayer span').filter(has_text='Baseline')).to_have_count(1)
    expect(table.locator('img')).to_have_js_property('complete',True)
    assert table.locator('img').evaluate('el=>el.naturalWidth')>1000
    page.evaluate('''()=>{
      const span=[...document.querySelectorAll('.translated-page[data-source-page="2"] .textLayer span')].find(el=>el.textContent==='Baseline');
      const range=document.createRange();range.selectNodeContents(span);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
    }''')
    assert page.evaluate('getSelection().toString()')=='Baseline'
    page.locator('#paragraphs').dispatch_event('mouseup')
    expect(page.locator('#selection-toolbar')).to_be_visible()
    page.locator('#highlight-selection').click();expect(page.locator('#annotation-count')).to_have_text('1')
    expect(table.locator('.annotation-mark')).not_to_have_count(0)
    position=page.locator('#translation-view').evaluate('el=>el.scrollTop')
    table.locator('.visual-zoom').click();expect(page.locator('#image-dialog')).to_be_visible()
    expect(page.locator('#image-dialog img')).to_have_js_property('complete',True)
    page.locator('#image-dialog .close-dialog').click()
    assert abs(page.locator('#translation-view').evaluate('el=>el.scrollTop')-position)<2
    page.screenshot(path=str(server.ROOT/'tmp'/'translated-table.png'))
    page.locator('#pdf-tab').click();page.locator('#page-number').fill('2');page.locator('#page-number').press('Enter')
    expect(page.locator('.page[data-page-number="2"] .annotation-mark')).not_to_have_count(0)
    page.locator('#translated-tab').click()
    expect(table.locator('.annotation-mark')).not_to_have_count(0)
    assert calls['translation']==1
    page.locator('#settings').click();page.locator('#system-language').select_option('en');page.locator('#settings-dialog .close-dialog').click()
    expect(table.locator('.visual-zoom')).to_have_text('View larger')
    expect(table.locator('figcaption span')).to_have_text('Page 2 · Table')
    page.set_viewport_size({'width':390,'height':844});table.scroll_into_view_if_needed()
    assert page.locator('#translation-view').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
    assert not errors,errors
    page.close()


def test_layout_and_visual_download_failures_can_be_retried(browser,services):
    base,_,calls=services;page=browser.new_page()
    open_visuals(page,base)
    page.route('**/layout',lambda route:route.fulfill(status=503,json={'error':'Simulated failure'}),times=1)
    page.locator('#translated-tab').click()
    expect(page.locator('#retry-layout')).to_be_visible()
    assert page.locator('.paragraph').count()>0
    page.route('**/visuals/*/image',lambda route:route.fulfill(status=503),times=1)
    page.locator('#retry-layout').click()
    expect(page.locator('.translation-visual')).to_have_count(4)
    retry=page.locator('.visual-retry:visible');expect(retry).to_have_count(1)
    crop=page.locator('.visual-crop.image-error');crop_id=crop.locator('..').get_attribute('data-visual-id')
    retry.click()
    expect(page.locator('.visual-crop.image-error')).to_have_count(0)
    assert page.locator(f'[data-visual-id="{crop_id}"] img').evaluate('el=>el.naturalWidth')>0
    assert calls['translation']==0
    page.close()


def test_small_and_tall_figures_keep_source_scale_and_fit_viewport(browser,services):
    base,_,calls=services
    with fitz.open() as pdf:
        bitmap=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,60,40));bitmap.set_rect(bitmap.irect,(90,160,120))
        for rect in [(60,90,120,130),(60,90,130,730)]:
            p=pdf.new_page(width=600,height=800)
            p.insert_image(rect,stream=bitmap.tobytes('png'),keep_proportion=False)
        raw=pdf.tobytes()
    page=browser.new_page(viewport={'width':1440,'height':1000});page.goto(base)
    page.locator('#file-input').set_input_files({'name':'small-and-tall.pdf','mimeType':'application/pdf','buffer':raw})
    expect(page.locator('#page-total')).to_have_text('2',timeout=30000)
    expect(page.locator('#loading')).to_be_hidden()
    page.locator('#translated-tab').click()
    expect(page.locator('.visual-crop')).to_have_count(2,timeout=15000)
    small=page.locator('.translated-page[data-source-page="1"] .visual-crop')
    tall=page.locator('.translated-page[data-source-page="2"] .visual-crop')
    for width,height in [(1440,1000),(390,600)]:
        page.set_viewport_size({'width':width,'height':height})
        assert small.evaluate('el=>el.clientWidth<=125&&el.clientHeight<=85')
        assert tall.evaluate('el=>el.clientHeight<=Math.min(640,innerHeight*.7)+1')
        for crop in [small,tall]:
            assert crop.evaluate('''el=>{const r=JSON.parse(el.dataset.displayRect);return Math.abs(el.clientWidth/el.clientHeight-(r[2]-r[0])/(r[3]-r[1]))<.02;}''')
        assert page.locator('#translation-view').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
    small.locator('..').locator('.visual-zoom').click()
    expect(page.locator('#image-dialog')).to_be_visible()
    page.wait_for_function('document.querySelector("#image-dialog img").naturalWidth>0')
    page.locator('#image-dialog .close-dialog').click()
    assert calls['translation']==0
    page.close()
