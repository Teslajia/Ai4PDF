import logging
import mimetypes

import pytest
from playwright.sync_api import expect

import app as server
from test_app import client
from test_browser import browser, services


def poison_mime_types(monkeypatch):
    # Other Windows applications can register these associations system-wide.
    mimetypes.init()
    for extension in ('.js', '.mjs', '.css', '.json', '.wasm'):
        monkeypatch.setitem(mimetypes.types_map, extension, 'text/plain')


@pytest.mark.parametrize('path, mime', [
    ('/static/app.js', 'text/javascript'),
    ('/vendor/pdfjs-dist/build/pdf.mjs', 'text/javascript'),
    ('/vendor/pdfjs-dist/build/pdf.worker.mjs', 'text/javascript'),
    ('/vendor/pdfjs-dist/legacy/build/pdf.mjs', 'text/javascript'),
    ('/vendor/pdfjs-dist/legacy/build/pdf.worker.mjs', 'text/javascript'),
    ('/static/startup.js', 'text/javascript'),
    ('/static/style.css', 'text/css'),
    ('/static/reasoning-models.json', 'application/json'),
    ('/vendor/pdfjs-dist/wasm/qcms_bg.wasm', 'application/wasm'),
])
def test_assets_ignore_windows_file_associations(client, monkeypatch, path, mime):
    poison_mime_types(monkeypatch)
    response = client.get(path)
    assert response.status_code == 200
    assert response.mimetype == mime
    assert 'no-cache' in response.headers['Cache-Control']


def test_buttons_work_with_bad_windows_mime_types(browser, services, monkeypatch):
    poison_mime_types(monkeypatch)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(services[0])
    expect(page.locator('#startup-status')).to_be_hidden()
    assert page.evaluate("typeof document.querySelector('#import').onclick") == 'function', errors
    with page.expect_file_chooser() as chooser:
        page.locator('#import').click()
    chooser.value.set_files(str(server.ROOT / 'static/sample.pdf'))
    page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    page.locator('#settings').click()
    expect(page.locator('#settings-dialog')).to_be_visible()
    assert not errors
    page.close()


def test_pdf_starts_without_promise_try(browser, services):
    page = browser.new_page()
    page.add_init_script('delete Promise.try;')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(services[0])
    expect(page.locator('#startup-status')).to_be_hidden()
    assert page.evaluate("typeof document.querySelector('#import').onclick") == 'function', errors
    page.locator('#open-sample').click()
    page.locator('#pages .textLayer span').first.wait_for(timeout=20000)
    assert not errors
    page.close()


def test_failed_module_shows_diagnostics_and_logs(browser, services, caplog):
    page = browser.new_page()
    page.route('**/static/selection.js', lambda route: route.abort())
    page.goto(services[0])
    expect(page.locator('#startup-title')).to_have_text('页面启动失败')
    expect(page.locator('#startup-details')).to_contain_text('module_load')
    expect(page.locator('#startup-copy')).to_be_visible()
    assert 'Frontend module_load:' in caplog.text
    assert page.evaluate("document.querySelector('#import').onclick") is None
    page.close()


@pytest.mark.parametrize('script, feature', [
    ('delete HTMLElement.prototype.showPopover;', 'popover'),
    ('delete Promise.withResolvers;', 'Promise.withResolvers'),
])
def test_unsupported_browser_gets_instructions(browser, services, caplog, script, feature):
    page = browser.new_page()
    page.add_init_script(script)
    page.goto(services[0])
    expect(page.locator('#startup-title')).to_have_text('浏览器需要更新')
    expect(page.locator('#startup-details')).to_contain_text(feature)
    assert 'Frontend unsupported_browser:' in caplog.text
    page.close()


def test_script_exception_does_not_leak_message(browser, services, caplog):
    page = browser.new_page()
    page.route('**/static/app.js?*', lambda route: route.fulfill(
        content_type='text/javascript', body="throw new Error('secret-api-key-and-document-content');"))
    page.goto(services[0])
    expect(page.locator('#startup-title')).to_have_text('页面启动失败')
    expect(page.locator('#startup-details')).to_contain_text('Error: Error')
    assert 'secret-api-key-and-document-content' not in page.locator('#startup-details').inner_text()
    assert 'secret-api-key-and-document-content' not in caplog.text
    page.close()


def test_diagnostic_endpoint_only_logs_allowed_fields(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.post('/api/frontend-diagnostics', json={
            'code': 'module_load', 'errorType': 'SyntaxError', 'missing': ['popover', 'private-file-name'],
            'message': 'sk-private-secret', 'stack': 'private document contents'},
            headers={'User-Agent': 'Mozilla/5.0 Chrome/140.0.1.2 Edg/140.0.3.4 secret'})
    assert response.status_code == 204
    assert 'Frontend module_load:' in caplog.text and 'Edge/140.0.3.4' in caplog.text
    assert 'SyntaxError missing=popover' in caplog.text
    for forbidden in ('sk-private-secret', 'private-file-name', 'private document contents', ' secret'):
        assert forbidden not in caplog.text
    assert client.post('/api/frontend-diagnostics', json={'code': 'arbitrary-private-data'}).status_code == 400
    assert client.post('/api/frontend-diagnostics', json={'code': 'ready'}, headers={'Origin': 'https://example.com'}).status_code == 403
    assert client.post('/api/frontend-diagnostics', data='x' * 4097, content_type='application/json').status_code == 413


def test_no_javascript_keeps_visible_recovery_instructions(browser, services):
    page = browser.new_page(java_script_enabled=False)
    page.goto(services[0])
    expect(page.locator('#startup-status')).to_be_visible()
    assert '启用 JavaScript' in page.locator('#startup-status noscript').evaluate('(node) => node.textContent')
    expect(page.locator('#startup-reload')).to_be_visible()
    page.close()


def test_missing_script_keeps_json_error_type_and_index_revalidates(client):
    response = client.get('/static/not-present.js')
    assert response.status_code == 404 and response.mimetype != 'text/javascript'
    response = client.get('/')
    assert 'no-cache' in response.headers['Cache-Control']
    response = client.get('/', headers={'If-None-Match': response.headers['ETag']})
    assert response.status_code == 304 and 'no-cache' in response.headers['Cache-Control']
