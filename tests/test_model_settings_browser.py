import json

from playwright.sync_api import expect

import app as server
from test_browser import browser, services


def test_old_config_alias_quick_switch_persistence_and_real_request_body(browser, services):
    base, model, calls = services
    calls['failOnce'] = False
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    # Migrate the old shape without changing its model or remembered key.
    old = {'baseUrl': model+'/v1', 'model': 'local-test-model', 'apiKey': 'test-only-key', 'rememberKey': True}
    page.evaluate('(config)=>localStorage.setItem("paperdesk.config",JSON.stringify(config))', old)
    page.reload()
    expect(page.locator('#chat-empty h3')).to_have_text('科研有嘉，探索有新')
    expect(page.locator('#model-status')).to_contain_text('local-test-model')
    page.locator('#model-options-toggle').click()
    expect(page.locator('#quick-model')).to_have_value('local-test-model')
    expect(page.locator('#quick-reasoning')).to_have_value('default')
    # Dismissed drafts must not change the active configuration.
    page.locator('#quick-model').fill('discard-this-model')
    page.keyboard.press('Escape')
    expect(page.locator('#model-options')).to_be_hidden()
    page.locator('#settings').click()
    expect(page.locator('#api-key')).to_have_value('test-only-key')
    expect(page.locator('#api-model')).to_have_value('local-test-model')
    page.locator('#api-display-name').fill('ChatGPT 官方')
    page.locator('#settings-form button[type=submit]').click()
    expect(page.locator('#model-status span:nth-child(2)')).to_have_text('ChatGPT 官方')
    page.locator('#question').fill('保留输入框中的草稿')
    page.locator('#model-options-toggle').click()
    page.locator('#quick-model').fill('local-switched-model')
    page.locator('#quick-reasoning').select_option('high')
    page.locator('#model-options-form button[type=submit]').click()
    expect(page.locator('#question')).to_have_value('保留输入框中的草稿')
    expect(page.locator('#model-options')).to_be_hidden()
    expect(page.locator('#model-status span:nth-child(2)')).to_have_text('ChatGPT 官方')
    calls['expectedModel'] = 'local-switched-model'
    page.locator('#settings').click()
    expect(page.locator('#api-model')).to_have_value('local-switched-model')
    expect(page.locator('#api-reasoning')).to_have_value('high')
    expect(page.locator('#api-key')).to_have_value('test-only-key')
    page.locator('#test-connection').click()
    expect(page.locator('#connection-result')).to_contain_text('连接成功')
    page.locator('#settings-dialog .close-dialog').click()
    page.reload()
    expect(page.locator('#model-status span:nth-child(2)')).to_have_text('ChatGPT 官方')
    page.locator('#model-options-toggle').click()
    expect(page.locator('#quick-model')).to_have_value('local-switched-model')
    expect(page.locator('#quick-reasoning')).to_have_value('high')
    page.locator('#quick-model-toggle').click()
    assert page.locator('#quick-model-list .model-choice').all_text_contents() == ['local-switched-model', 'local-test-model']
    page.locator('#quick-model-toggle').click()
    page.keyboard.press('Escape')
    page.locator('#open-sample').click()
    page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#question').fill('解释这篇论文的方法')
    page.locator('#send').click()
    expect(page.locator('#stop-chat')).to_be_hidden(timeout=15000)
    expect(page.locator('.assistant-message .content')).to_contain_text('核心观点')
    page.locator('#translation-tab').click()
    page.locator('.retry').first.click()
    expect(page.locator('.translated-text').first).to_contain_text('模拟译文')
    assert len(calls['bodies']) == 3
    for body in calls['bodies']:
        assert body['model'] == 'local-switched-model' and body['reasoning_effort'] == 'high'
        assert 'displayName' not in body and 'recentModels' not in body
    assert not errors, errors
    page.close()


def test_quick_settings_default_key_privacy_and_responsive_layout(browser, services):
    base, model, calls = services
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    page.goto(base)
    page.locator('#settings').click()
    page.locator('#api-display-name').fill('ChatGPT 官方')
    page.locator('#api-url').fill(model+'/v1')
    page.locator('#api-model').fill('local-test-model')
    page.locator('#api-key').fill('memory-only-test-key')
    page.locator('#api-reasoning').select_option('high')
    page.locator('#settings-form button[type=submit]').click()
    page.locator('#model-options-toggle').click()
    page.locator('#quick-reasoning').select_option('default')
    page.locator('#model-options-form button[type=submit]').click()
    saved = json.loads(page.evaluate('localStorage.getItem("paperdesk.config")'))
    assert saved['apiKey'] == '' and saved['rememberKey'] is False
    assert saved['displayName'] == 'ChatGPT 官方' and saved['reasoningEffort'] == 'default'
    page.locator('#model-options-toggle').click()
    page.locator('#model-connection-settings').click()
    expect(page.locator('#model-options')).to_be_hidden()
    expect(page.locator('#api-key')).to_have_value('memory-only-test-key')
    page.locator('#test-connection').click()
    expect(page.locator('#connection-result')).to_contain_text('连接成功')
    assert 'reasoning_effort' not in calls['bodies'][0]
    out = server.ROOT/'tmp'
    out.mkdir(exist_ok=True)
    page.screenshot(path=str(out/'assistant-connection-settings.png'))
    page.locator('#settings-dialog .close-dialog').click()
    page.locator('#model-options-toggle').click()
    page.screenshot(path=str(out/'assistant-model-settings.png'))
    for width, height in [(1440, 1000), (1024, 768), (800, 600), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        page.locator('#model-options').evaluate('(el)=>el.hidePopover()')
        page.locator('#model-options-toggle').click()
        panel = page.locator('#model-options').bounding_box()
        assert panel['x'] >= 0 and panel['y'] >= 0
        assert panel['x'] + panel['width'] <= width and panel['y'] + panel['height'] <= height
        page.locator('#model-options-form button[type=submit]').click()
        image = page.locator('#attach-image').bounding_box()
        settings = page.locator('#model-options-toggle').bounding_box()
        send = page.locator('#send').bounding_box()
        assert image['x']+image['width'] <= settings['x']
        assert settings['x']+settings['width'] <= send['x']
    page.reload()
    page.locator('#settings').click()
    expect(page.locator('#api-key')).to_have_value('')
    expect(page.locator('#api-display-name')).to_have_value('ChatGPT 官方')
    page.close()
