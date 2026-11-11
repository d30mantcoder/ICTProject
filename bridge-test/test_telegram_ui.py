"""Browser interaction checks with explicit API fixtures; never sends Telegram messages."""
import json
from playwright.sync_api import sync_playwright


def run():
    state={'linked':False,'username':None,'available':True,'groups':{'main':'','english':'','pe':''}}
    calls=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':390,'height':844})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def api(route):
            path=route.request.url.split('/api/')[1]
            calls.append(path)
            if path=='telegram': data=state
            elif path=='telegram/link':data={'url':'https://t.me/test_bot?start=test','expires_in':600}
            elif path=='classmates/groups':
                state['groups']=route.request.post_data_json;data=state
            elif path.startswith('classmates?'):
                data={'items':[{'name':'Test Classmate','username':'test_classmate'}] if state['groups']['main'] else []}
            elif path=='telegram/unlink':state['linked']=False;data={'ok':True}
            else:data={}
            route.fulfill(json=data)
        page.route('**/api/**',api)
        page.goto('http://127.0.0.1:1740')
        page.wait_for_function("()=>typeof classmatesBaseLoad==='function'")
        page.evaluate("connected=true;demo=false;loadContent('classmates')")
        page.get_by_role('button',name='Подключить Telegram',exact=True).click()
        page.get_by_role('link',name='Открыть бота и нажать Start').wait_for()
        assert not any(c.startswith('classmates?') for c in calls)
        state.update(linked=True,username='student_123')
        page.get_by_role('button',name='Проверить привязку',exact=True).click()
        page.locator('input[name=main]').fill('SE-2623')
        page.locator('input[name=english]').fill('B2-1')
        page.locator('input[name=pe]').fill('PE-4')
        page.get_by_role('button',name='Сохранить группы',exact=True).click()
        page.get_by_role('link',name='@test_classmate',exact=True).wait_for()
        page.get_by_placeholder('Поиск по имени или @username').fill('classmate')
        page.get_by_role('button',name='Найти',exact=True).click()
        page.wait_for_timeout(100)
        assert any('q=classmate' in c for c in calls)
        page.locator('.classmates-search select').select_option('english')
        page.wait_for_timeout(100)
        assert any('category=english' in c for c in calls)
        for width in (320,390,1440):
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            assert page.locator('main').evaluate('(e)=>e.scrollWidth<=e.clientWidth'),width
        page.get_by_role('button',name='Отключить Telegram',exact=True).click()
        page.get_by_role('button',name='Подключить Telegram',exact=True).wait_for()
        state['available']=False
        page.get_by_role('button',name='Проверить привязку',exact=True).click()
        page.get_by_text('Бот пока не настроен или временно недоступен.',exact=True).wait_for()
        assert page.get_by_role('button',name='Подключить Telegram',exact=True).is_disabled()
        assert not errors,errors
        browser.close()
    print('PASS: Telegram prompt, link, linked groups, search, category, unlink, unavailable bot, mobile widths; no JS errors. Telegram API was mocked.')

if __name__=='__main__':run()
