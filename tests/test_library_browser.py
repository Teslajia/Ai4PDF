from pathlib import Path

from playwright.sync_api import expect

import app as server
from test_browser import browser, services, other_document


def test_organize_filter_bulk_trash_restore_and_protected_labels(browser,services):
    base,_,calls=services
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click()
    expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=20000)
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    page.locator('#file-input').set_input_files({'name':'second.pdf','mimeType':'application/pdf','buffer':other_document()})
    expect(page.locator('#doc-title')).to_have_text('Another research paper')
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    active_id=page.evaluate('localStorage.getItem("paperdesk.last")')
    page.locator('[data-drawer="library"]').click();page.locator('#library-manage').click()
    expect(page.locator('.library-card')).to_have_count(2)
    page.once('dialog',lambda d:d.accept('全部标签'))
    page.locator('#library-folder-add').click()
    expect(page.locator('.library-folder.active')).to_contain_text('全部标签')
    folder_id=page.locator('.library-folder.active').get_attribute('data-folder')
    page.locator('[data-folder="all"]').click();page.locator('#library-select-all').check()
    expect(page.locator('#library-selected')).to_have_text('已选择 2 份')
    page.locator('[data-batch="move"]').click();page.locator('#library-doc-folder').select_option(folder_id);page.locator('#library-edit-save').click()
    expect(page.locator('#library-editor')).to_be_hidden()
    expect(page.locator('.library-folder-chip').first).to_have_text('全部标签')
    page.locator('#library-select-all').check();page.locator('[data-batch="addTags"]').click()
    page.locator('#library-doc-tags').fill('取消, AI');page.locator('#library-edit-save').click()
    expect(page.locator('#library-editor')).to_be_hidden()
    page.locator('#library-tag-filter').select_option('取消');expect(page.locator('.library-card')).to_have_count(2)
    page.locator('#library-search').fill('second.pdf');expect(page.locator('.library-card')).to_have_count(1)
    page.locator('[data-action="edit"]').click();page.locator('#library-doc-title').fill('全部文档');page.locator('#library-edit-save').click()
    expect(page.locator('#library-editor')).to_be_hidden();expect(page.locator('#doc-title')).to_have_text('全部文档')
    page.locator('#library-search').fill('');page.locator('#library-tag-filter').select_option('')
    page.locator('#library-dialog').screenshot(path=str(server.ROOT/'tmp'/'library-manager-zh.png'))
    # Deleting the open document closes its reader but retains the management panel.
    page.once('dialog',lambda d:d.accept());page.locator(f'[data-id="{active_id}"] [data-action="trash"]').click()
    expect(page.locator('#welcome')).to_be_visible();expect(page.locator('#library-dialog')).to_be_visible()
    page.locator('[data-folder="trash"]').click();expect(page.locator('.library-card')).to_have_count(1)
    expect(page.locator('.library-doc-open')).to_be_disabled()
    page.locator('[data-action="restore"]').click();expect(page.locator('.library-card')).to_have_count(0)
    page.locator('[data-folder="all"]').click();expect(page.locator('.library-card')).to_have_count(2)
    # Folder deletion only changes classification.
    page.locator(f'[data-folder="{folder_id}"]').click()
    page.once('dialog',lambda d:d.accept());page.locator('#library-folder-delete').click()
    expect(page.locator('[data-folder="unfiled"]')).to_contain_text('2')
    page.locator('#library-close').click();page.locator('#settings').click();page.locator('#system-language').select_option('en')
    page.locator('#library-open-settings').click()
    expect(page.locator('#library-title')).to_have_text('Manage library')
    expect(page.locator(f'[data-id="{active_id}"] .library-doc-open')).to_have_text('全部文档')
    expect(page.locator(f'[data-id="{active_id}"] .library-tag').first).to_have_text('取消')
    page.set_viewport_size({'width':390,'height':844})
    dialog=page.locator('#library-dialog');box=dialog.bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=390
    assert dialog.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
    page.screenshot(path=str(server.ROOT/'tmp'/'library-manager-mobile-en.png'))
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#library-select-all').check();page.once('dialog',lambda d:d.accept());page.locator('[data-batch="trash"]').click()
    expect(page.locator('.library-card')).to_have_count(0)
    page.locator('[data-folder="trash"]').click();page.locator('#library-select-all').check()
    page.once('dialog',lambda d:d.accept());page.locator('[data-batch="purge"]').click()
    expect(page.locator('.library-card')).to_have_count(0)
    assert page.request.get(base+'/api/library').json()['documents']==[]
    assert not errors,errors
    assert not calls.get('bodies')
    page.close()


def test_settings_migration_validates_paths_and_keeps_reader(browser,services,tmp_path,monkeypatch):
    base,_,calls=services
    monkeypatch.setattr(server,'LOCATION_FILE',tmp_path.parent/(tmp_path.name+'-location.json'))
    monkeypatch.setattr(server,'DATA_FROM_ENV',False)
    server.library.job={'status':'idle'}
    source=server.DATA
    target=tmp_path.parent/(tmp_path.name+'-new')
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#open-sample').click();expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=20000);expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    doc_id=page.evaluate('localStorage.getItem("paperdesk.last")')
    page.locator('#settings').click();expect(page.locator('#library-current-path')).to_have_value(str(source.resolve()))
    page.locator('.library-migration-options summary').click()
    page.locator('#library-new-path').fill(str(source/'nested'))
    page.once('dialog',lambda d:d.accept());page.locator('#library-migrate').click()
    expect(page.locator('#library-migration-status')).to_contain_text('互相包含')
    assert server.DATA==source
    page.locator('#library-new-path').fill(str(target))
    page.once('dialog',lambda d:d.accept());page.locator('#library-migrate').click()
    expect(page.locator('#library-migration-status')).to_contain_text('迁移完成',timeout=20000)
    expect(page.locator('#library-current-path')).to_have_value(str(target.resolve()))
    page.locator('#library-storage-title').scroll_into_view_if_needed()
    page.screenshot(path=str(server.ROOT/'tmp'/'library-storage-settings.png'))
    assert (source/doc_id/'original.pdf').read_bytes()==(target/doc_id/'original.pdf').read_bytes()
    page.locator('#settings-dialog .close-dialog').click();page.reload()
    expect(page.locator('#loading')).to_be_hidden(timeout=20000)
    expect(page.locator('#pages .textLayer span').first).to_be_visible(timeout=20000)
    assert page.evaluate('localStorage.getItem("paperdesk.last")')==doc_id
    assert not errors,errors
    assert not calls.get('bodies')
    page.close()
