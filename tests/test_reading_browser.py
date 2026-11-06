from playwright.sync_api import expect
import app as server

from test_browser import browser,services
from test_chat_images_browser import setup
from test_references import reference_pdf


def open_references(page,base,model,native=False):
    setup(page,base,model)
    page.locator('#file-input').set_input_files({'name':'references.pdf','mimeType':'application/pdf','buffer':reference_pdf(native=native)})
    expect(page.locator('#loading')).to_be_hidden(timeout=30000)
    expect(page.locator('.page[data-page-number="1"] .link-overlays a')).not_to_have_count(0)


def test_numbered_references_original_bilingual_translation_and_return(browser,services):
    base,model,calls=services;calls['failOnce']=False;calls['translationText']='对比已有方法 [1] 和多篇参考文献 [2, 3]。'
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    open_references(page,base,model)
    link=page.locator('.page[data-page-number="1"] [data-reference-ids="1"]').first
    old=page.locator('#pdf-scroll').evaluate('el=>el.scrollTop')
    link.click();expect(page.locator('#page-number')).to_have_value('3')
    expect(page.locator('#reading-back')).to_be_visible();page.locator('#reading-back').click()
    assert abs(page.locator('#pdf-scroll').evaluate('el=>el.scrollTop')-old)<2
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page[data-source-page="1"]')).to_have_attribute('data-selectable','true',timeout=20000)
    link=page.locator('.bilingual-page[data-source-page="1"] [data-reference-ids="2,3"]').first
    link.click();expect(page.locator('.reference-menu')).to_be_visible()
    page.screenshot(path=str(server.ROOT/'tmp'/'reference-picker.png'))
    page.locator('.reference-menu [data-reference-id="3"]').click()
    expect(page.locator('#page-number')).to_have_value('3')
    page.locator('#reading-back').click();expect(page.locator('#translation-view')).to_be_visible()
    page.locator('.retry').first.click()
    expect(page.locator('.translated-text .reference-citation')).to_have_count(2,timeout=15000)
    page.locator('#translated-tab').click()
    link=page.locator('.translated-text [data-reference-ids="1"]').first
    link.scroll_into_view_if_needed();old=page.locator('#translation-view').evaluate('el=>el.scrollTop')
    link.click();expect(page.locator('#page-number')).to_have_value('3')
    page.locator('#reading-back').click();expect(page.locator('#translated-tab')).to_have_class('active')
    assert abs(page.locator('#translation-view').evaluate('el=>el.scrollTop')-old)<2
    assert calls['translation']==1 and not errors,errors
    page.close()


def test_native_pdf_links_land_at_destination_not_page_top(browser,services):
    base,model,_=services;page=browser.new_page(viewport={'width':1440,'height':1000})
    open_references(page,base,model,native=True)
    page.locator('.page[data-page-number="1"] .link-overlays a:not([data-reference-ids])').first.click()
    expect(page.locator('#page-number')).to_have_value('3')
    page.locator('.page[data-page-number="3"] .textLayer span').first.wait_for()
    offset=page.locator('.page[data-page-number="3"]').evaluate("el=>el.getBoundingClientRect().top-document.querySelector('#pdf-scroll').getBoundingClientRect().top")
    assert offset < -100
    page.close()


def test_views_keep_paragraph_position_and_source_link_returns_exactly(browser,services):
    base,model,_=services;page=browser.new_page(viewport={'width':1440,'height':900})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    open_references(page,base,model)
    page.locator('#page-number').fill('2');page.locator('#page-number').press('Enter')
    page.locator('#pdf-scroll').evaluate("el=>el.scrollTop+=350")
    original=page.locator('#pdf-scroll').evaluate('el=>el.scrollTop')
    page.locator('#translation-tab').click()
    expect(page.locator('.bilingual-page[data-source-page="2"]')).to_have_attribute('data-selectable','true',timeout=20000)
    assert page.locator('#translation-view').evaluate('el=>el.scrollTop')>500
    page.locator('#pdf-tab').click()
    assert abs(page.locator('#pdf-scroll').evaluate('el=>el.scrollTop')-original)<3
    page.locator('#translation-tab').click()
    target=page.locator('.bilingual-page[data-source-page="2"] .paragraph').nth(3)
    pid=target.get_attribute('data-paragraph-id')
    target.evaluate("el=>{const s=document.querySelector('#translation-view');s.scrollTop+=el.getBoundingClientRect().top-s.getBoundingClientRect().top-80;}")
    position=page.locator('#translation-view').evaluate('el=>el.scrollTop')
    target.locator('.source-page').click()
    expect(page.locator('#page-number')).to_have_value('2')
    source_offset=page.locator('.page[data-page-number="2"]').evaluate("el=>el.getBoundingClientRect().top-document.querySelector('#pdf-scroll').getBoundingClientRect().top")
    assert source_offset<-100
    # The tab itself restores the position; the explicit back action does too.
    page.locator('#translation-tab').click()
    assert abs(page.locator('#translation-view').evaluate('el=>el.scrollTop')-position)<3
    target.locator('.source-page').click();page.locator('#reading-back').click()
    assert abs(page.locator('#translation-view').evaluate('el=>el.scrollTop')-position)<3
    page.locator('#translated-tab').click()
    card=page.locator(f'#para-{pid}');expect(card).to_be_in_viewport()
    page.screenshot(path=str(server.ROOT/'tmp'/'translation-only-position.png'))
    offset=card.evaluate("el=>el.getBoundingClientRect().top-document.querySelector('#translation-view').getBoundingClientRect().top")
    assert abs(offset-80)<3
    page.locator('#translation-tab').click()
    assert abs(page.locator('#translation-view').evaluate('el=>el.scrollTop')-position)<3
    page.locator('#translation-display').select_option('text')
    expect(card).to_be_in_viewport()
    page.locator('#translation-display').select_option('layout')
    expect(card).to_be_in_viewport()
    assert not errors,errors
    page.close()


def test_pdf_zoom_and_reload_preserve_page_coordinates(browser,services):
    base,model,_=services;page=browser.new_page(viewport={'width':1440,'height':900})
    open_references(page,base,model)
    page.locator('#page-number').fill('2');page.locator('#page-number').press('Enter')
    page.locator('#pdf-scroll').evaluate('el=>el.scrollTop+=300')
    def coordinate():
        return page.locator('.page[data-page-number="2"]').evaluate("el=>{const r=el.getBoundingClientRect();return (document.querySelector('#pdf-scroll').getBoundingClientRect().top+80-r.top)/r.height;}")
    y=coordinate();page.locator('#zoom').select_option('1.5')
    assert abs(coordinate()-y)<.003
    page.reload();expect(page.locator('#loading')).to_be_hidden(timeout=30000)
    expect(page.locator('.page[data-page-number="2"]')).to_be_visible()
    assert abs(coordinate()-y)<.003
    page.close()
