import json

from playwright.sync_api import expect

import app as server
from test_browser import browser, services


def test_fetch_select_search_share_and_send_model_from_catalog(browser,services):
    base,model,calls=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base);page.locator('#settings').click()
    page.locator('#api-url').fill(model+'/v1')
    page.locator('#api-display-name').fill('我的科研助手')
    page.locator('#api-key').fill('memory-only-key')
    # No model is filled yet. Discover from the unsaved connection fields.
    page.locator('#api-model-fetch').click()
    expect(page.locator('#api-model-list .model-choice')).to_have_count(3)
    expect(page.locator('#api-model-hint')).to_contain_text('已获取 3 个模型')
    page.locator('#api-model-list .model-choice').filter(has_text='research-model').click()
    expect(page.locator('#api-model')).to_have_value('research-model')
    page.locator('#settings-form button[type=submit]').click()
    expect(page.locator('#model-status')).to_contain_text('我的科研助手')
    page.locator('#model-options-toggle').click()
    page.locator('#quick-model-toggle').click()
    # Expanding an already populated model field still shows ALL models.
    expect(page.locator('#quick-model-list .model-choice')).to_have_count(3)
    page.screenshot(path=str(server.ROOT/'tmp'/'model-catalog-picker.png'))
    page.locator('#quick-model-list input[type=search]').fill('fast')
    expect(page.locator('#quick-model-list .model-choice')).to_have_count(1)
    page.locator('#quick-model-list input[type=search]').press('Enter')
    expect(page.locator('#quick-model')).to_have_value('fast-model')
    page.locator('#model-options-form button[type=submit]').click()
    calls['expectedModel']='fast-model'
    page.locator('#settings').click();page.locator('#test-connection').click()
    expect(page.locator('#connection-result')).to_contain_text('连接成功')
    assert calls['bodies'][0]['model']=='fast-model'
    assert calls['models']==1
    page.locator('#settings-dialog .close-dialog').click()
    page.reload();page.locator('#model-options-toggle').click()
    expect(page.locator('#quick-model')).to_have_value('fast-model')
    page.locator('#quick-model-fetch').click()
    expect(page.locator('#quick-model-list .model-choice')).to_have_count(3)
    expect(page.locator('#model-status')).to_contain_text('我的科研助手')
    assert not errors,errors
    page.close()


def test_failed_catalog_manual_fallback_connection_scope_and_stale_response(browser,services):
    base,model,calls=services
    page=browser.new_page(viewport={'width':1280,'height':800})
    page.goto(base);page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1')
    page.locator('#api-model-fetch').click()
    expect(page.locator('#api-model-list .model-choice')).to_have_count(3)
    page.locator('#api-model').fill('manual-model')
    page.locator('#api-key').fill('changed-key')
    page.locator('#api-model-toggle').click()
    expect(page.locator('#api-model-list .model-choice')).to_have_count(1)
    calls['modelsStatus']=404
    page.locator('#api-model-fetch').click()
    expect(page.locator('#api-model-hint.error')).to_contain_text('手动填写')
    expect(page.locator('#api-model')).to_have_value('manual-model')
    page.locator('#settings-form button[type=submit]').click()
    expect(page.locator('#model-status')).to_contain_text('manual-model')
    page.locator('#settings').click()
    held=[]
    page.route('**/api/models',lambda route:held.append(route))
    with page.expect_request('**/api/models'):page.locator('#api-model-fetch').click()
    page.locator('#api-url').fill('http://127.0.0.1:22222/v1')
    held[0].fulfill(status=200,content_type='application/json',body=json.dumps({'models':['stale-model']}))
    page.locator('#api-model-toggle').click()
    expect(page.locator('#api-model-list .model-choice')).to_have_count(1)
    expect(page.locator('#api-model-list')).not_to_contain_text('stale-model')
    expect(page.locator('#api-model-fetch')).to_be_enabled()
    page.close()
