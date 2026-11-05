"""Exercise update UI without touching real settings, installers, or AI APIs."""
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='updates-ui-', dir=ROOT / 'tmp') as scratch:
        os.environ['AI4PDF_HOME'] = scratch
        os.environ.pop('AI4PDF_DATA', None)
        os.environ.pop('PAPERDESK_DATA', None)
        import app as server
        import updates
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        payload = b'MZ-ui-test-only'
        name = 'Ai4PDF-9.0.0-windows-x64-setup.exe'
        release = {'tag_name': 'v9.0.0', 'html_url': updates.REPOSITORY + '/releases/tag/v9.0.0',
                   'body': 'Test notes <script>alert(1)</script>', 'assets': [{'name': name, 'state': 'uploaded',
                   'browser_download_url': updates.REPOSITORY + '/releases/download/v9.0.0/' + name,
                   'size': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}]}
        calls = []
        def network(url, *, limit, progress=None):
            calls.append(url)
            yield json.dumps(release).encode() if url == updates.LATEST_API else payload
            if progress: progress(len(payload))
        updates.github_get = network
        http = make_server('127.0.0.1', 0, server.app, threaded=True)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{http.server_port}/')
                saved = {'baseUrl':'https://example.invalid/v1','model':'custom-model','displayName':'Demo connection','rememberKey':True,'apiKey':'synthetic-test-key'}
                page.evaluate('(config)=>localStorage.setItem("paperdesk.config",JSON.stringify(config))', saved)
                page.reload()
                page.locator('#settings').click()
                expect(page.locator('#update-mode')).to_be_visible()
                assert not calls, 'Opening settings should not contact GitHub automatically'
                page.locator('#update-check').click()
                expect(page.locator('#update-status')).to_have_text('发现新版本：9.0.0')
                expect(page.locator('#update-download')).to_be_hidden()
                for language, label in [('en','Check for updates'),('zh-TW','檢查更新'),('ja','更新を確認'),('ko','업데이트 확인'),('zh-CN','检查更新')]:
                    page.locator('#system-language').select_option(language)
                    expect(page.locator('#update-check')).to_have_text(label)
                launched = []
                server.updater.launcher = lambda *args: launched.append(args)
                page.locator('#settings-dialog .close-dialog').click()
                page.locator('#settings').click()
                page.locator('#update-download').click()
                expect(page.locator('#update-install')).to_be_visible(timeout=10000)
                page.locator('#update-notes summary').click()
                expect(page.locator('#update-notes-text')).to_contain_text('<script>alert(1)</script>')
                page.locator('#update-title').scroll_into_view_if_needed()
                page.screenshot(path=str(ROOT / 'tmp/updates-ui.png'))
                page.locator('#update-install').click()
                expect(page.locator('#update-restart-dialog')).to_be_visible()
                assert len(launched) == 1
                assert page.evaluate('JSON.parse(localStorage.getItem("paperdesk.config"))') == saved
                assert page.evaluate('localStorage.getItem("paperdesk.locale")') == 'zh-CN'
                assert not errors, errors
                browser.close()
        finally:
            http.shutdown()
    print('PASS: update UI, five languages, verified download, safe release notes, explicit install and browser settings preservation')


if __name__ == '__main__':
    main()
