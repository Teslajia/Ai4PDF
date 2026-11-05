"""Capture public README images using only the bundled sample and clearly marked demo content."""
import io
import logging
import os
from pathlib import Path
import random
import sys
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    output = ROOT / 'docs/assets'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='docs-capture-', dir=ROOT / 'tmp') as scratch:
        os.environ['AI4PDF_HOME'] = scratch
        os.environ.pop('AI4PDF_DATA', None)
        os.environ.pop('PAPERDESK_DATA', None)
        import app as server
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        client = server.app.test_client()
        response = client.post('/api/documents', data={'file': (io.BytesIO((ROOT / 'static/sample.pdf').read_bytes()), 'Ai4PDF-sample.pdf')})
        assert response.status_code == 200
        document = response.json
        doc_id = document['id']
        saved = server.state(doc_id)
        saved['messages'] = [
            {'role': 'user', 'content': '怎样把读论文变成可以积累的研究笔记？'},
            {'role': 'assistant', 'content': '**先找到问题，再核对证据，最后留下自己的判断。**\n\n这份示例把阅读过程分成三个动作：\n\n1. **理解原文**：先定位研究问题和关键结论，保留公式、图表与上下文一起阅读。[p1]\n2. **追问细节**：针对选中的段落提出具体问题，把作者的论断与支持它的证据分开。[p2]\n3. **记录想法**：用批注记下一个限制、一个疑问或下一步实验，之后再回到原文核实。[p3]\n\n可以从这个小练习开始：选择一段正文，写下“它说了什么、依据是什么、我还想知道什么”。\n\n*此回答为项目截图中的演示内容。*'}
        ]
        translations = {
            'A quieter way': '安静一点，把论文读懂',
            'A practical introduction': '实用入门  |  示例文档  |  01',
            'Abstract': '摘要',
            'Reading a research paper': '阅读论文不只是翻过一页又一页，更是与页面上的思想展开对话。这份示例介绍一个本地阅读工作台，将原文、个人批注、双语翻译和 AI 助手放在一起。',
            '1. A workspace': '1. 为你的好奇心准备的工作台',
            'Ai4PDF keeps': 'Ai4PDF 将 PDF 原文放在左侧，将助手放在右侧。你可以打开本机文档、浏览页面，并在下次回来时继续原来的阅读进度。原文排版保持完整，包括图片、公式和参考文献。',
            '2. Read actively': '2. 带着问题主动阅读',
            'Select a few words': '选择这段文字中的几个词，试试高亮。选区工具栏也可以添加下划线、写笔记，或将选中段落发送给助手。批注保存在本地，并可导出为 PDF 原生批注。',
            '3. Bring your': '3. 连接你自己的模型',
            'The assistant connects': '助手连接到你自行选择的 API 地址和模型。本地服务将请求转发到兼容的 Chat Completions 接口。应用不包含共享模型账号，也不预设 API Key。'
        }
        for paragraph in document['paragraphs']:
            if paragraph['page'] != 1 or not paragraph.get('translatable', True):
                continue
            text = ' '.join(paragraph.get('translationSource', paragraph['text']).split())
            translated = next((value for prefix, value in translations.items() if text.startswith(prefix)), None)
            if translated:
                key = '简体中文:' + paragraph['id']
                saved['translations'][key] = translated
                saved.setdefault('translationSources', {})[key] = paragraph['translationSourceHash']
        server.write_json(server.folder(doc_id) / 'state.json', saved)
        http = None
        for _ in range(30):
            try:
                http = make_server('127.0.0.1', random.randint(40000, 59999), server.app, threaded=True)
                break
            except (OSError, SystemExit):
                pass
        assert http
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 980}, device_scale_factor=1)
                page.goto(f'http://127.0.0.1:{http.server_port}')
                page.evaluate('''id => {
                    localStorage.setItem('paperdesk.last', id);
                    localStorage.setItem('paperdesk.config', JSON.stringify({displayName:'演示助手 · 自定义 API',model:'demo-model',baseUrl:'http://127.0.0.1:9/v1',apiKey:'',rememberKey:false}));
                }''', doc_id)
                page.reload()
                expect(page.locator('#loading')).to_be_hidden(timeout=30000)
                expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=30000)
                expect(page.locator('.assistant-message')).to_be_visible()
                page.locator('#messages').evaluate('(element) => element.scrollTop = 0')
                page.locator('#pdf-scroll').evaluate('(element) => element.scrollTop = 110')
                page.screenshot(path=str(output / 'workspace.png'))
                page.locator('#translation-tab').click()
                expect(page.locator('.bilingual-page')).to_have_count(3, timeout=20000)
                page.wait_for_function("() => [...document.querySelectorAll('.source-crop img')].slice(0,3).every(image => image.complete && image.naturalWidth > 0)")
                page.locator('#translation-view').evaluate('(element) => element.scrollTop = 850')
                page.locator('#messages').evaluate('(element) => element.scrollTop = 0')
                page.screenshot(path=str(output / 'bilingual.png'))
                browser.close()
        finally:
            http.shutdown()
        print('Created public screenshots from isolated sample-only data.')


if __name__ == '__main__':
    main()
