from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp';OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8765/')
    page.screenshot(path=str(OUT/'welcome.png'))
    page.locator('#open-sample').click()
    page.locator('.textLayer span').first.wait_for(timeout=30000)
    page.screenshot(path=str(OUT/'reader.png'))
    print('text spans',page.locator('.textLayer span').count())
    print('errors',errors)
    assert not errors
    browser.close()
