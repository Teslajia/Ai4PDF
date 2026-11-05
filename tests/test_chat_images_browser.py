import base64
import io

from PIL import Image,ImageDraw
from playwright.sync_api import expect
from test_browser import browser,services,other_document


def picture(kind='PNG'):
    image=Image.new('RGB',(640,360),'#f8faf6');draw=ImageDraw.Draw(image)
    draw.text((35,25),'Attention map / feature similarity',fill='#315541',font_size=24)
    for row in range(6):
        for col in range(10):
            color=(50+row*22,100+col*9,80+row*16)
            draw.rectangle((35+col*55,85+row*35,84+col*55,114+row*35),fill=color)
    out=io.BytesIO();image.save(out,format=kind);return out.getvalue()


def setup(page,base,model):
    page.goto(base);page.locator('#open-sample').click()
    page.locator('#pages .textLayer span').first.wait_for(timeout=30000)
    expect(page.locator('#loading')).to_be_hidden()
    page.locator('#settings').click();page.locator('#api-url').fill(model+'/v1');page.locator('#api-model').fill('local-test-model')
    page.locator('#settings-form button[type=submit]').click()
    return page.evaluate("localStorage.getItem('paperdesk.last')")


def clipboard_or_drop(page,kind,content,name,mime):
    page.evaluate('''({kind,content,name,mime})=>{
        const transfer=new DataTransfer();
        transfer.items.add(new File([Uint8Array.from(atob(content),c=>c.charCodeAt(0))],name,{type:mime}));
        const element=document.querySelector(kind==='paste'?'#question':'.assistant');
        const event=kind==='paste'?new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}):new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true});
        element.dispatchEvent(event);
    }''',{'kind':kind,'content':base64.b64encode(content).decode(),'name':name,'mime':mime})


def test_chat_images_picker_paste_drop_send_history_and_switch(browser,services):
    base,model,calls=services
    page=browser.new_page(viewport={'width':1600,'height':1050});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    doc_id=setup(page,base,model)
    payload={'name':'attention.png','mimeType':'image/png','buffer':picture()}
    with page.expect_file_chooser() as chooser:page.locator('#attach-image').click()
    chooser.value.set_files([payload,payload])
    expect(page.locator('.image-preparing')).to_have_count(0)
    expect(page.locator('.chat-image')).to_have_count(2)
    page.locator('.remove-image').last.click();expect(page.locator('.chat-image')).to_have_count(1)
    page.locator('.chat-image-preview').click();expect(page.locator('#image-dialog')).to_be_visible()
    page.locator('[aria-label="关闭图片预览"]').click()
    clipboard_or_drop(page,'paste',picture('JPEG'),'screenshot.jpg','image/jpeg')
    clipboard_or_drop(page,'drop',picture('WEBP'),'diagram.webp','image/webp')
    expect(page.locator('.chat-image')).to_have_count(3)
    expect(page.locator('.image-preparing')).to_have_count(0)
    expect(page.locator('#drop-overlay')).to_be_hidden()
    assert calls['chat']==0
    page.locator('#question').fill('请解释这三张图，并与论文中的方法对照。')
    page.screenshot(path=str(__import__('app').ROOT/'tmp'/'chat-image-attachments.png'))
    page.locator('#send').click()
    expect(page.locator('.assistant-message .content').last).to_contain_text('核心观点',timeout=15000)
    expect(page.locator('#send')).to_be_visible()
    expect(page.locator('#save-status')).to_have_text('阅读记录已保存到本机')
    expect(page.locator('.message-images img')).to_have_count(3)
    expect(page.locator('.chat-image')).to_have_count(0)
    content=calls['chatBodies'][0]['messages'][-1]['content']
    assert content[0]['text']=='请解释这三张图，并与论文中的方法对照。'
    assert len(content)==4 and all(p['type']=='image_url' for p in content[1:])
    assert content[1]['image_url']['url'].startswith('data:image/png;base64,')
    assert content[2]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert content[3]['image_url']['url'].startswith('data:image/png;base64,')
    data=page.request.get(base+'/api/documents/'+doc_id).json()
    assert len(data['state']['messages'][0]['attachments'])==3
    page.reload();expect(page.locator('.message-images img')).to_have_count(3,timeout=20000)
    page.locator('.message-images button').first.click();expect(page.locator('#image-dialog img')).to_have_js_property('naturalWidth',640)
    page.locator('[aria-label="关闭图片预览"]').click()
    page.locator('#question').fill('继续解释图中的颜色差异。');page.locator('#send').click()
    expect(page.locator('.assistant-message')).to_have_count(2)
    expect(page.locator('#send')).to_be_visible(timeout=15000)
    assert isinstance(calls['chatBodies'][1]['messages'][1]['content'],list)
    assert calls['chatBodies'][1]['messages'][-1]['content']=='继续解释图中的颜色差异。'
    page.locator('#chat-image-input').set_input_files(payload);expect(page.locator('.chat-image')).to_have_count(1)
    page.locator('#file-input').set_input_files({'name':'different.pdf','mimeType':'application/pdf','buffer':other_document()})
    expect(page.locator('#doc-title')).to_have_text('Another research paper',timeout=15000)
    expect(page.locator('.chat-image')).to_have_count(0);expect(page.locator('.message-images img')).to_have_count(0)
    assert not errors,errors
    page.close()


def test_chat_images_limits_failed_send_and_image_only_retry(browser,services):
    base,model,calls=services;calls['chatStatus']=400
    page=browser.new_page(viewport={'width':1440,'height':1000});setup(page,base,model)
    page.locator('#chat-image-input').set_input_files({'name':'bad.svg','mimeType':'image/svg+xml','buffer':b'<svg></svg>'})
    expect(page.locator('#toast')).to_contain_text('支持 PNG')
    expect(page.locator('.chat-image')).to_have_count(0)
    payload={'name':'test.png','mimeType':'image/png','buffer':picture()}
    page.locator('#chat-image-input').set_input_files([payload]*5)
    expect(page.locator('#toast')).to_contain_text('最多添加 4 张')
    expect(page.locator('.chat-image')).to_have_count(4)
    for _ in range(3):page.locator('.remove-image').last.click()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#chat-form').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(__import__('app').ROOT/'tmp'/'chat-image-attachments-mobile.png'))
    page.locator('#send').click()  # No typed question: image-only request.
    expect(page.locator('.message-error')).to_contain_text('支持图片输入',timeout=15000)
    expect(page.locator('#send')).to_be_visible()
    page.locator('.chat-retry').click()
    expect(page.locator('.chat-image')).to_have_count(1)
    expect(page.locator('#question')).to_have_value('请结合论文解释这些图片。')
    calls.pop('chatStatus')
    page.locator('#send').click()
    expect(page.locator('.assistant-message .content').last).to_contain_text('核心观点',timeout=15000)
    expect(page.locator('#send')).to_be_visible()
    assert calls['chat']==2
    assert len(calls['chatBodies'][1]['messages'])==2  # Retry replaces the failed question; no duplicate image payload.
    page.close()
