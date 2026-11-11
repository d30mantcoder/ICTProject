"""Live local browser checks for public campus features (no LMS login)."""
import json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:1740'
PDF = ROOT / 'syllabuses' / '__Browser_Test_Файл.pdf'
LINK = ROOT / 'syllabuses' / '__outside.pdf'

def get(path):
    return urlopen(BASE + path)

def run():
    a=Image.new('RGB',(600,800),'white');ImageDraw.Draw(a).text((50,50),'Syllabus page 1',fill='black')
    b=Image.new('RGB',(600,800),'white');ImageDraw.Draw(b).text((50,50),'Syllabus page 2',fill='black')
    a.save(PDF,save_all=True,append_images=[b])
    LINK.symlink_to(ROOT.parent/'ICT_Assignment_4.pdf')
    try:
        items=json.load(get('/api/syllabuses'))['items']
        assert not any(item['url'].endswith('__outside.pdf') for item in items)
        item=next(item for item in items if item['title']=='  Browser Test Файл')
        response=get(item['url']);assert response.headers['Content-Type']=='application/pdf'
        assert response.headers['Content-Disposition'].startswith('inline;')
        for path in ['/syllabuses/__outside.pdf','/syllabuses/README.md','/syllabuses/%2e%2e%2fapp.py']:
            try:get(path);raise AssertionError('Unsafe file served: '+path)
            except HTTPError as error:assert error.code==404
        manifest=json.load(get('/manifest.webmanifest'))
        assert manifest['display']=='standalone' and manifest['scope']=='/'
        assert {i['sizes'] for i in manifest['icons']}=={'192x192','512x512'}
        assert get('/sw.js').headers['Service-Worker-Allowed']=='/'
        errors=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(viewport={'width':390,'height':844})
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            downloads=[];page.on('download',lambda d:downloads.append(d))
            page.goto(BASE);page.wait_for_function("()=>typeof openSyllabus==='function'")
            # Use real public endpoints without creating an LMS browser session.
            page.evaluate("demo=true;loadContent('aitusa')")
            page.locator('.discount-card').first.wait_for()
            assert page.locator('.discount-card').count()==2
            assert '15%' in page.locator('.discount-card').first.inner_text()
            assert '10%' in page.locator('.discount-card').last.inner_text()
            assert page.locator('.demo-notice').is_visible()
            page.locator('[data-feature=schedule]').first.click()
            assert page.locator('button.schedule-card').count()==7
            # C1.3.324 exists with a room-type suffix K on the original plan.
            page.locator('button[data-room="C1.3.324"]').click()
            frame=page.frame_locator('iframe.campus-map')
            frame.locator('.aitu-selected-room').first.wait_for(timeout=20000)
            assert 'C1.3.324' in frame.locator('#aitu-room-status').inner_text()
            assert 'Выделен' in frame.locator('#aitu-room-status').inner_text()
            assert frame.locator('button[name=F3]').get_attribute('class').endswith('current-floor')
            page.get_by_role('button',name='К расписанию',exact=True).click()
            page.locator('button[data-room="C1.2.324"]').first.click()
            page.frame_locator('iframe.campus-map').locator('.aitu-selected-room').first.wait_for()
            page.locator('[data-feature=attendance]').first.click()
            assert page.locator('.att-calendar').is_visible()
            assert page.locator('.demo-notice').is_visible()
            page.locator('[data-feature=syllabuses]').first.click()
            page.get_by_role('button',name='Открыть силлабус:   Browser Test Файл',exact=True).click()
            page.locator('canvas[data-rendered=true]').wait_for(timeout=20000)
            assert page.locator('.pdf-controls span').inner_text()=='1 / 2'
            page.get_by_role('button',name='Следующая страница',exact=True).click()
            page.wait_for_function("()=>document.querySelector('.pdf-controls span').textContent==='2 / 2'")
            page.get_by_role('combobox',name='Масштаб PDF').select_option('2')
            page.wait_for_timeout(300)
            for width in [320,390,430,1440]:
                page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(150)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                assert page.locator('main').evaluate('(e)=>e.scrollWidth<=e.clientWidth'),width
            assert not downloads
            page.get_by_role('button',name='К списку силлабусов',exact=True).click()
            page.locator('.syllabus-button').wait_for()
            page.evaluate("navigator.serviceWorker.ready")
            page.reload();page.wait_for_function('()=>navigator.serviceWorker.controller!==null')
            cache=page.evaluate("caches.open('aitu-public-v1').then(c=>c.keys()).then(keys=>keys.map(k=>new URL(k.url).pathname))")
            assert sorted(cache)==sorted(['/pwa/offline.html','/pwa/icon-192.png','/pwa/icon-512.png'])
            cdp=context.new_cdp_session(page);cdp.send('Page.enable')
            install_errors=cdp.send('Page.getInstallabilityErrors')['installabilityErrors']
            assert not install_errors,install_errors
            context.set_offline(True);page.reload()
            page.get_by_text('Мой AITU · Нет сети',exact=True).wait_for()
            context.set_offline(False);page.get_by_role('link',name='Повторить / Retry').click()
            page.wait_for_function("()=>typeof openSyllabus==='function'")
            assert not errors, errors
            browser.close()
        print('PASS: syllabus listing/inline PDF, traversal/symlink protection, 2-page embedded PDF and zoom, mobile overflow, demo attendance, discounts, schedule → selected block/floor/room, PWA installability, public-only cache and offline/reconnect; no downloads or JS errors.')
    finally:
        PDF.unlink(missing_ok=True);LINK.unlink(missing_ok=True)

if __name__=='__main__':run()
