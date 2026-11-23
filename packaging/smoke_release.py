"""Exercise the actual frozen EXE with a temporary profile, never the user's library."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION


def main(executable, browser_check=False):
    executable = Path(executable).resolve()
    assert executable.is_file(), executable
    (ROOT / 'tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-smoke-', dir=ROOT / 'tmp') as temporary:
        scratch = Path(temporary)
        env = dict(os.environ, LOCALAPPDATA=str(scratch / 'profile'),
                   PATH=str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'),
                   PYTHONHOME='', PYTHONPATH='')
        for name in ('AI4PDF_HOME', 'AI4PDF_DATA', 'PAPERDESK_DATA'):
            env.pop(name, None)
        home = scratch / 'profile' / 'Ai4PDF'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        args = [str(executable), '--no-browser', '--no-tray', '--port', str(port)]
        session = requests.Session()
        session.trust_env = False
        process = None

        def start():
            child = subprocess.Popen(args, env=env, cwd=scratch, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline:
                    if child.poll() is not None:
                        raise AssertionError('EXE exited before it became ready')
                    try:
                        response = session.get(url + '/api/health', timeout=.5)
                        if response.ok and response.json()['application'] == 'Ai4PDF':
                            return child
                    except requests.RequestException:
                        pass
                    time.sleep(.2)
                raise AssertionError('EXE startup timeout')
            except BaseException:
                child.terminate()
                child.wait(timeout=15)
                log = home / 'logs' / 'desktop.log'
                if log.exists():
                    print(log.read_text(encoding='utf-8'))
                raise

        def get(path):
            response = session.get(url + path, timeout=60)
            assert response.status_code == 200, (path, response.status_code, response.text[:200])
            return response

        try:
            process = start()
            assert get('/api/health').json()['version'] == VERSION
            assert 'waitress' in get('/').headers.get('Server', '').lower()
            assert get('/api/documents').json() == []
            storage = get('/api/library/storage').json()
            assert Path(storage['path']).resolve() == (home / 'data').resolve(), storage
            for asset in ('/static/app.js', '/static/startup.js', '/static/startup.css', '/static/library.js', '/static/chat-markdown.js',
                          '/static/translated-view.js', '/static/reading-position.js', '/static/references.js',
                          '/static/reading-locales.js', '/static/reading.css', '/static/reasoning-models.json',
                          '/static/app-icon.png', '/vendor/pdfjs-dist/build/pdf.mjs',
                          '/vendor/pdfjs-dist/build/pdf.worker.mjs', '/vendor/pdfjs-dist/web/pdf_viewer.css',
                          '/vendor/pdfjs-dist/legacy/build/pdf.mjs', '/vendor/pdfjs-dist/legacy/build/pdf.worker.mjs',
                          '/vendor/marked/lib/marked.esm.js', '/vendor/dompurify/dist/purify.es.mjs',
                          '/vendor/katex/dist/katex.mjs', '/vendor/katex/dist/fonts/KaTeX_Main-Regular.woff2'):
                response = get(asset)
                assert len(response.content) > 50
                if asset.endswith(('.js', '.mjs')):
                    assert response.headers['Content-Type'].startswith('text/javascript'), asset
            for asset_dir in ('cmaps', 'standard_fonts', 'wasm'):
                candidates = (executable.parent / '_internal' / 'node_modules' / 'pdfjs-dist' / asset_dir).glob('*')
                first = next(p for p in candidates if p.is_file())
                get(f'/vendor/pdfjs-dist/{asset_dir}/{first.name}')
            # A second launch must reuse this instance and exit successfully.
            second = subprocess.run(args, env=env, cwd=scratch, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
            assert second.returncode == 0
            conflicting = dict(env, LOCALAPPDATA=str(scratch / 'another-profile'))
            other = subprocess.run(args, env=conflicting, cwd=scratch, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
            assert other.returncode == 1, 'An occupied port must not serve the wrong library'
            assert get('/api/health').json()['application'] == 'Ai4PDF'
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((72, 100), 'Ai4PDF packaged release annotation test.', fontsize=14)
                page.draw_rect((72,150,260,240),fill=(.2,.5,.7))
                page.insert_text((72,265),'Figure 1. Packaged visual rendering.',fontsize=11)
                quad = page.search_for('annotation')[0].quad * ~page.transformation_matrix
                coords = [v for point in quad for v in point]
                original = pdf.tobytes()
            response = session.post(url + '/api/documents', files={'file': ('smoke.pdf', original, 'application/pdf')}, timeout=60)
            assert response.status_code == 200, response.text
            doc = response.json()
            path = '/api/documents/' + doc['id']
            layout=get(path + '/layout').json()
            visuals=layout['pages'][0]['visuals']
            assert visuals and visuals[0]['kind']=='figure'
            assert get(path+f"/pages/1/visuals/{visuals[0]['id']}/image").headers['Content-Type'].startswith('image/png')
            assert '1' in get(path+'/references').json()['citations']
            assert get(path + '/pages/1/image').headers['Content-Type'].startswith('image/png')
            annotation = {'page': 1, 'kind': 'highlight', 'text': 'annotation', 'note': '打包验证',
                          'color': '#f4ca64', 'rects': [[.1, .1, .2, .03]], 'quads': [coords]}
            response = session.post(url + path + '/annotations', json=annotation, timeout=30)
            assert response.status_code == 200, response.text
            with pymupdf.open(stream=get(path + '/export').content, filetype='pdf') as exported:
                assert list(exported[0].annots())[0].info['content'] == '打包验证'
            assert get(path + '/pdf').content == original
            # Migration must write outside the installation and remain valid after a restart.
            target = scratch / 'moved-library'
            response = session.post(url + '/api/library/migration', json={'source': storage['path'], 'target': str(target)}, timeout=30)
            assert response.status_code == 202, response.text
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                job = get('/api/library/migration').json()
                if job['status'] != 'running':
                    break
                time.sleep(.1)
            assert job['status'] == 'done', job
            assert (home / 'library-location.json').exists()
            process.terminate()
            process.wait(timeout=15)
            process = start()
            assert Path(get('/api/library/storage').json()['path']) == target
            assert get(path).json()['state']['annotations'][0]['note'] == '打包验证'
            assert session.get(url + '/api/health', headers={'Origin': 'https://example.com'}, timeout=10).status_code == 403
            if browser_check:
                from playwright.sync_api import sync_playwright, expect
                with sync_playwright() as playwright:
                    chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
                    browser = playwright.chromium.launch(executable_path=str(chrome) if chrome.exists() else None, headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url)
                    page.locator('#open-sample').click()
                    page.locator('#pages .textLayer span').first.wait_for(timeout=30000)
                    expect(page.locator('#loading')).to_be_hidden(timeout=30000)
                    page.locator('#translation-tab').click()
                    expect(page.locator('.bilingual-page')).to_have_count(3, timeout=20000)
                    expect(page.locator('.translation-toggle').first).to_have_text('折叠')
                    page.locator('.translation-toggle').first.click()
                    expect(page.locator('.translation-toggle').first).to_have_text('展开')
                    assert page.locator('.source-crop .textLayer span').count() > 0
                    page.wait_for_function("""() => {
                        const image = document.querySelector('.source-crop img');
                        return image?.complete && image.naturalWidth > 0;
                    }""", timeout=30000)
                    # Verify the actual bundled KaTeX and Markdown modules, without an AI request.
                    math = page.evaluate("""async () => {
                        const {renderChatMarkdown} = await import('/static/chat-markdown.js');
                        const element = document.createElement('div');
                        renderChatMarkdown(element, 'Formula: $E = mc^2$');
                        return element.querySelectorAll('.katex').length;
                    }""")
                    assert math == 1
                    page.locator('#translated-tab').click()
                    expect(page.locator('.translated-page')).to_have_count(3)
                    assert page.locator('.original-text:visible').count()==0
                    expect(page.locator('.version-tag')).to_have_text('V'+'.'.join(VERSION.split('.')[:2]))
                    assert not errors, errors
                    page.screenshot(path=str(ROOT / 'tmp' / 'release-browser-check.png'))
                    assert 'Frontend ready:' in (home / 'logs/desktop.log').read_text(encoding='utf-8')
                    failed = browser.new_page(viewport={'width': 390, 'height': 844})
                    failed.route('**/static/selection.js', lambda route: route.abort())
                    with failed.expect_response(lambda response: '/api/frontend-diagnostics' in response.url) as diagnostic:
                        failed.goto(url)
                    assert diagnostic.value.status == 204
                    expect(failed.locator('#startup-details')).to_contain_text('module_load')
                    failed.screenshot(path=str(ROOT / 'tmp' / 'frontend-startup-error.png'))
                    assert 'Frontend module_load:' in (home / 'logs/desktop.log').read_text(encoding='utf-8')
                    browser.close()
                    print('PASS: packaged browser PDF text layer, bilingual layout, paragraph folding and frontend diagnostics')
            print('PASS: isolated EXE startup, resources, duplicate launch, PDF/layout/render, annotation/export, migration and restart')
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            session.close()


if __name__ == '__main__':
    main(sys.argv[1], '--browser' in sys.argv)
