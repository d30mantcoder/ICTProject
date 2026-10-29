"""Mobile UI + actual local backend. MFA UI uses explicit fixture responses."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:1741'


async def run():
    with tempfile.TemporaryFile() as logs, tempfile.TemporaryDirectory() as state_dir:
        server = subprocess.Popen([sys.executable, str(ROOT / 'app.py')],
            env={**os.environ, 'BRIDGE_PORT':'1741', 'BRIDGE_HEADLESS':'1', 'BRIDGE_STATE_DIR':state_dir, 'BRIDGE_DB_PATH':str(Path(state_dir)/'cache.sqlite3')}, stdout=logs, stderr=logs)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Server exited')
                try:
                    with urllib.request.urlopen(BASE,timeout=1) as r:
                        if r.status == 200:
                            break
                except OSError:
                    await asyncio.sleep(.1)
            else:
                raise RuntimeError('Server not ready')
            async with async_playwright() as pw:
                client = await pw.request.new_context(base_url=BASE)
                assert (await client.post('/api/login',data={'email':'test@example.test','password':'fake'})).status == 401
                assert (await client.post('/api/window',data={'id':'fake'})).status == 401
                assert (await client.post('/api/connect',data={},headers={'Origin':'https://other.invalid'})).status == 403
                assert (await client.post('/api/connect',data={})).ok
                invalid = await client.post('/api/login',data={'email':'','password':'private-fixture'})
                assert invalid.status == 422 and 'private-fixture' not in await invalid.text()
                assert (await client.post('/api/content',data={'section':'courses'})).status == 409
                assert (await client.post('/api/content',data={'url':'https://other.invalid'})).status == 400
                print('PASS: authenticated access, origin checks, credential-safe validation, no data before Moodle login')

                browser = await pw.chromium.launch()
                phone = await browser.new_page(base_url=BASE,viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
                errors=[]
                phone.on('pageerror',lambda e:errors.append(str(e)))
                await client.dispose()
                client = phone.context.request
                await phone.goto(BASE)
                await expect(phone.locator('#code')).to_have_count(0)
                await expect(phone.locator('#signIn')).to_be_visible()
                phase={'phase':'idle','message':'Fixture','number':None}
                async def login_fixture(route):
                    body=route.request.post_data_json
                    assert body['email']=='student@example.test' and body['password']=='fixture-only'
                    phase.update(phase='mfa',message='Подтверди вход',number='42')
                    await route.fulfill(json=phase)
                async def status_fixture(route):
                    await route.fulfill(json=phase)
                await phone.route('**/api/login',login_fixture)
                await phone.route('**/api/login/status',status_fixture)
                await phone.locator('#email').fill('student@example.test')
                await phone.locator('#password').fill('fixture-only')
                await phone.get_by_role('button',name='Войти через Microsoft',exact=True).click()
                await expect(phone.locator('#mfaNumber')).to_have_text('42')
                await expect(phone.locator('#mfaNumber')).to_be_visible()
                await expect(phone.locator('#password')).to_have_value('')
                phase.update(phase='action',message='Microsoft предлагает ключ доступа.',number=None)
                await expect(phone.locator('#authTitle')).to_have_text('Нужно действие в окне входа',timeout=6000)
                await expect(phone.locator('#authProgress .pulse')).to_be_hidden()
                await expect(phone.locator('#support')).to_have_attribute('open','')
                await expect(phone.locator('#browserMode')).to_contain_text('без видимого окна')
                await expect(phone.locator('#focusWindow')).to_be_hidden()
                assert await phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                phase.update(phase='error',message='Fixture: вход отклонён',number=None)
                await expect(phone.locator('#signIn')).to_be_visible(timeout=6000)
                await expect(phone.locator('#status')).to_contain_text('вход отклонён')
                async def content_fixture(route):
                    await route.fulfill(json={'title':'Мои реальные курсы (fixture)','profile':'Test Student',
                        'courses':[{'title':'ICT <script>','url':'https://lms.astanait.edu.kz/course/view.php?id=12'}],
                        'activities':[],'paragraphs':[],'tables':[[['Работа','Балл'],['Quiz','95']]],
                        'text':'Test content','demo':False,'updated':'12:00'})
                await phone.route('**/api/content',content_fixture)
                await phone.locator('#password').fill('fixture-only')
                await phone.locator('#loginButton').click()
                await expect(phone.locator('#mfaNumber')).to_be_visible()
                phase.update(phase='authenticated',message='Вход выполнен',number=None)
                await expect(phone.locator('#dashboard')).to_be_visible(timeout=6000)
                await expect(phone.locator('#document')).to_contain_text('ICT <script>')
                await expect(phone.locator('#authProgress')).not_to_be_visible()
                assert not await phone.locator('#document script').count()
                await phone.unroute('**/api/content',content_fixture)
                await phone.unroute('**/api/login',login_fixture)
                await phone.unroute('**/api/login/status',status_fixture)
                await phone.locator('#accountButton').click()
                await phone.locator('#logout').click()
                await expect(phone.locator('#signIn')).to_be_visible()
                print('PASS: mobile login, MFA number, cleared password, retry and automatic course display (provider fixtures)')

                await phone.locator('#demoButton').click()
                await expect(phone.locator('#dashboard')).to_be_visible(timeout=20000)
                await expect(phone.locator('#demoTag')).to_be_visible()
                await expect(phone.locator('#document')).to_contain_text('95')
                await expect(phone.locator('#menuButton')).to_be_visible()
                assert not await phone.locator('#document script').count()
                assert await phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
                await phone.screenshot(path=str(ROOT / 'smoke-preview.png'),full_page=True)
                await phone.locator('#menuButton').click()
                await phone.locator('#mobileDrawer [data-section=grades]').click()
                await expect(phone.locator('#mobileDrawer [data-section=grades]')).to_have_attribute('aria-current','true')
                await phone.locator('#support > summary').click()
                await expect(phone.locator('#remote')).to_be_visible(timeout=12000)
                await expect(phone.locator('#browserWindows option')).to_have_count(1)
                window_state = await (await client.get('/api/state')).json()
                assert (await client.post('/api/window',data={'id':window_state['windows'][0]['id']})).ok
                assert (await client.post('/api/window',data={'id':'closed-window'})).status == 404
                probe=await browser.new_page(viewport={'width':1100,'height':800})
                await probe.goto(BASE + '/demo')
                field=await probe.locator('#note').bounding_box()
                assert (await client.post('/api/action',data={'kind':'click','x':field['x']+field['width']/2,'y':field['y']+field['height']/2})).ok
                assert (await client.post('/api/action',data={'kind':'text','text':'Remote input works'})).ok
                assert (await client.post('/api/action',data={'kind':'key','key':'Tab'})).ok
                assert (await client.post('/api/action',data={'kind':'key','key':'Enter'})).ok
                response=await client.post('/api/extract',data={})
                assert response.ok,await response.text()
                extracted=await response.json()
                assert 'Remote input works' in extracted['text']
                await phone.locator('#accountButton').click()
                await phone.locator('#logout').click()
                await expect(phone.locator('#signIn')).to_be_visible()
                assert (await client.get('/api/state')).status == 401
                assert (await client.post('/api/connect',data={})).ok
                assert not (await (await client.get('/api/state')).json())['active']
                print('PASS: real browser data rendered as mobile tables, navigation, remote fallback, logout')

                if os.environ.get('BRIDGE_LIVE_SMOKE') == '1':
                    live=await client.post('/api/navigate',data={'destination':'login'},timeout=60000)
                    assert live.ok,await live.text()
                    await probe.goto('https://lms.astanait.edu.kz/login/index.php',wait_until='domcontentloaded')
                    await probe.locator('a[href*="/auth/oidc/"]').click()
                    await probe.wait_for_url('https://login.microsoftonline.com/**',timeout=30000)
                    await expect(probe.locator('input[name=loginfmt]')).to_be_visible(timeout=15000)
                else:
                    print('SKIP: live university SSO probe; enable BRIDGE_LIVE_SMOKE=1 explicitly')
                assert not errors,errors
                await browser.close()
                await client.dispose()
                print('PASS: local smoke complete; no real credentials used; no JavaScript errors')
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill();server.wait()


if __name__=='__main__':
    asyncio.run(run())
