from playwright.sync_api import expect

import app as server
from test_browser import browser, services
from test_chat_images_browser import setup


def test_restored_assistant_math_preserves_tex_markdown_citations_and_code(browser,services):
    base,model,calls=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    source=r'''就这篇论文而言，作者将生成器概括为一个基于 T2I 先验的 Real-ISR 模型，表示为 \(ISR=G_\theta(I_{LR},z)\)；不过这段内容没有展开具体生成器如何注入条件或实现扩散过程。[p3]

**加粗中的公式 \(a_i+b_j\)**，行内美元公式 $E=mc^2$。

- 下标和星号保持原样：\(a_i b_j + c^*\)。
- 数学中的页码标记不是引用：\(x_{[p2]}\)。

\[
\begin{aligned}
L &= \frac{1}{N}\sum_{i=1}^{N}(x_i-y_i)^2 \\
A &= \begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}
\end{aligned}
\]

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

| 符号 | 含义 |
| --- | --- |
| \(\theta_i\) | 参数 |

代码保留：`\(x_i\)`，`$y$`。

```tex
\[x_i+y_i\]
$$do_not_render$$
```

价格：$5 and $10；转义价格：\$20。

错误公式：\(\frac{1}\)；后续仍能渲染 \(z^2\)。
'''
    messages=[{'role':'user','content':r'请解释 \(ISR\)'},{'role':'assistant','content':source}]
    assert page.request.patch(base+f'/api/documents/{doc_id}/state',data={'messages':messages}).ok
    page.reload();content=page.locator('.assistant-message .content')
    expect(content.locator('.katex')).to_have_count(9)
    expect(content.locator('.katex-display')).to_have_count(2)
    expect(content.locator('strong .katex')).to_have_count(1)
    expect(content.locator('table .katex')).to_have_count(1)
    expect(content.locator('code .katex')).to_have_count(0)
    expect(page.locator('.message.user .katex')).to_have_count(0)
    expect(content.locator('code').first).to_have_text(r'\(x_i\)')
    expect(content.locator('pre code')).to_contain_text('do_not_render')
    expect(content.locator('.page-citation')).to_have_count(1)
    tex=content.locator('annotation[encoding="application/x-tex"]').all_text_contents()
    assert tex[0]==r'ISR=G_\theta(I_{LR},z)'
    assert r'a_i b_j + c^*' in tex and r'x_{[p2]}' in tex
    expect(content).to_contain_text('$5 and $10')
    expect(content).to_contain_text('$20')
    expect(content.locator('.chat-math-fallback')).to_have_text(r'\(\frac{1}\)')
    content.locator('.page-citation').click()
    expect(page.locator('#page-number')).to_have_value('3')
    # Same stored source is rendered again on reload; no conversation rewrite.
    assert page.request.get(base+f'/api/documents/{doc_id}').json()['state']['messages']==messages
    assert not errors,errors
    page.close()


def test_streamed_formulas_split_across_chunks_and_saved_history(browser,services):
    base,model,calls=services
    calls['chatChunks']=['就这篇论文而言，作者将生成器概括为一个基于 T2I 先验的 Real-ISR 模型，表示为 \\',
                         '(ISR=G_\\theta(I_{LR},', 'z)\\', ')；不过这段内容没有展开具体生成器如何注入条件或实现扩散过程。[p3]',
                         '\n\n\\[\\frac{1}{N}\\sum_{i=1}^{N}x_i', '^2\\]']
    calls['chatDelay']=.15
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    page.locator('#question').fill('请解释生成器公式');page.locator('#send').click()
    content=page.locator('.assistant-message .content').last
    expect(content.locator('.katex')).to_have_count(2,timeout=15000)
    expect(page.locator('#send')).to_be_visible()
    expect(page.locator('#save-status')).to_have_text('阅读记录已保存到本机')
    expect(content.locator('.page-citation')).to_have_count(1)
    expect(content.locator('.chat-math-fallback')).to_have_count(0)
    page.screenshot(path=str(server.ROOT/'tmp'/'assistant-math-fixed.png'))
    saved=page.request.get(base+f'/api/documents/{doc_id}').json()['state']['messages']
    assert saved[-1]['content']==''.join(calls['chatChunks'])
    page.reload();expect(page.locator('.assistant-message .katex')).to_have_count(2)
    assert calls['chat']==1
    assert not errors,errors
    page.close()


def test_untrusted_math_and_wide_equations_stay_inside_assistant(browser,services):
    base,model,_=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    formula=' + '.join('x_{'+str(i)+'}' for i in range(45))
    source=r'<img src=x onerror="window.badMath=true"><script>window.badMath=true</script>'+'\n\n'+r'\(\href{javascript:alert(1)}{x}\)'+ '\n\n$$'+formula+'$$\n\n'+r'原始 HTML 代码：<code>\(literal\)</code>'
    page.request.patch(base+f'/api/documents/{doc_id}/state',data={'messages':[{'role':'assistant','content':source}]})
    page.reload();content=page.locator('.assistant-message .content')
    expect(content.locator('.katex-display')).to_have_count(1)
    expect(content.locator('script,img,iframe,a[href^="javascript:"]')).to_have_count(0)
    expect(content.locator('code .katex')).to_have_count(0)
    expect(content.locator('code')).to_contain_text('literal')
    assert page.evaluate('window.badMath') is None
    display=content.locator('.chat-math-display')
    assert display.evaluate('(el)=>el.scrollWidth>el.clientWidth')
    assert page.locator('.messages').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    assert not errors,errors
    page.close()
