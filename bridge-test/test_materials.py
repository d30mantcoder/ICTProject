"""Saved pages are DOM fixtures only: original scripts/tokens are never replayed."""
import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path

from playwright.async_api import async_playwright, expect

import app
from moodle_reader import content_url, read_content, prepare_timeline, is_authenticated
from login_flow import LoginFlow
from fastapi import HTTPException

MATERIALS = Path(__file__).resolve().parents[2] / 'mid-term/materials'
MOODLE = app.MOODLE


class MaterialTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch()
        self.page = await self.browser.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def fixture(self, name):
        fixture_path = MATERIALS / (name + '.html')
        if not fixture_path.exists():
            self.skipTest('Original Moodle HTML fixture unavailable: ' + name)
        source = fixture_path.read_text()
        match = re.search(r'M\.cfg\s*=\s*(\{.*?\});', source, re.S)
        actual_config = json.loads(match.group(1))
        # Preserve the real authentication field name, with an anonymized ID.
        safe_config = {key: 17 if int(value or 0) > 0 else 0
                       for key, value in actual_config.items() if key in {'userId', 'userid'}}
        source = re.sub(r'<script\b[^>]*>.*?</script>', '', source, flags=re.I | re.S)
        # Only the test identity marker runs; network assets are blocked.
        source += '<script>window.M={cfg:' + json.dumps(safe_config) + '}</script><style>.d-none{display:none!important}</style>'
        async def route(request):
            if request.request.resource_type == 'document':
                await request.fulfill(content_type='text/html', body=source)
            else:
                await request.abort()
        await self.page.route('**/*', route)
        await self.page.goto(MOODLE + '/fixture')
        return await read_content(self.page, MOODLE, section=name)

    async def test_actual_saved_moodle_config_completes_login_flow(self):
        await self.fixture('home')
        self.assertTrue(await self.page.evaluate('() => M.cfg.userId > 0 && M.cfg.userid === undefined'))
        async def get_page():
            return self.page
        flow = LoginFlow(get_page, asyncio.Lock(), MOODLE)
        self.assertTrue(await flow.step(self.page, {'email': True, 'password': True}))
        self.assertEqual(flow.status['phase'], 'authenticated')

    async def test_actual_saved_login_page_is_not_authenticated(self):
        with self.assertRaises(HTTPException) as error:
            await self.fixture('Log in to the site _ frontpage')
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(await is_authenticated(self.page, MOODLE))

    async def test_zero_camelcase_user_id_is_not_overridden_by_legacy_value(self):
        await self.fixture('home')
        await self.page.evaluate('() => {M.cfg={userId:0,userid:17}}')
        self.assertFalse(await is_authenticated(self.page, MOODLE))

    async def test_home_seven_current_courses(self):
        data = await self.fixture('home')
        self.assertEqual(len(data['courses']), 7)
        for name in ['Physical Education', 'Linear Algebra', 'Information and Communication',
                     'Introduction to Programming', 'Foreign Language', 'Calculus', 'Cultural Studies']:
            self.assertTrue(any(name in course['title'] for course in data['courses']), name)

    async def test_dashboard_every_saved_event_has_course_and_deadline(self):
        data = await self.fixture('dashboard')
        self.assertEqual(len(data['timeline']), 5)
        for item in data['timeline']:
            self.assertTrue(item['title'])
            self.assertTrue(item['course'])
            self.assertTrue(item['date'])
            self.assertTrue(item['due'])
            self.assertNotIn('editsubmission', item['url'])
        first = data['timeline'][0]
        self.assertEqual(first['title'], 'Assignment 3')
        self.assertIn('Foreign Language', first['course'])
        self.assertEqual(first['time'], '23:59')
        self.assertEqual(first['action'], 'Add submission')

    async def test_grades_keep_zero_and_link_to_current_users_report(self):
        data = await self.fixture('grades')
        self.assertEqual(len(data['grades']), 7)
        self.assertEqual(len(data['tables'][0]), 8)  # Header + seven courses; no empty padding rows.
        self.assertEqual(data['grades'][0]['grade'], '0.00')
        for item in data['grades']:
            self.assertIn('/grade/report/user/index.php?id=', item['url'])
            self.assertNotIn('user=', item['url'])
        self.assertEqual(content_url(MOODLE + '/course/user.php?mode=grade&id=12&user=999', MOODLE),
                         MOODLE + '/grade/report/user/index.php?id=12')

    async def test_timeline_all_filter_and_async_show_more(self):
        await self.page.set_content('''<div data-region="timeline">
          <div data-region="view-selector"><button>Sort</button>
          <a data-filtername="sortbydates" onclick="document.body.dataset.sort='dates'">Dates</a></div>
          <div data-region="day-filter"><button>Filter</button>
          <a data-filtername="all" onclick="document.body.dataset.filter='all'">All</a></div>
          <div data-region="event-list-item">First event</div>
          <button data-action="more-events" onclick="setTimeout(()=>{
            this.insertAdjacentHTML('beforebegin','<div data-region=event-list-item>Second event</div>');
            this.remove();},100)">More</button></div>''')
        self.assertEqual(await prepare_timeline(self.page), [])
        self.assertEqual(await self.page.locator('body').get_attribute('data-filter'), 'all')
        self.assertEqual(await self.page.locator('body').get_attribute('data-sort'), 'dates')
        self.assertEqual(await self.page.locator('[data-region="event-list-item"]').count(), 2)

    async def test_grade_details_preserve_spanning_headers_and_zero(self):
        await self.page.route('**/*', lambda r: r.fulfill(content_type='text/html; charset=utf-8', body='''
          <script>window.M={cfg:{userid:17}}</script><main><h1>ICT — User report</h1>
          <table><tr><th rowspan=2>Категория</th><th>Работа</th><th>Балл</th></tr>
          <tr><td>Quiz 1</td><td>0.00</td></tr><tr><td>Assignments</td><td>Assignment 1</td><td>95.00</td></tr></table></main>'''))
        await self.page.goto(MOODLE+'/grade/report/user/index.php?id=12')
        data=await read_content(self.page, MOODLE, section='grades')
        self.assertEqual(data['tables'][0][1], ['Категория', 'Quiz 1', '0.00'])
        self.assertEqual(data['tables'][0][2], ['Assignments', 'Assignment 1', '95.00'])

    async def test_mobile_ui_renders_saved_sections_and_opens_grade_details(self):
        documents = {}
        for section in ['home', 'dashboard', 'grades']:
            await self.page.unroute('**/*')
            documents[section] = await self.fixture(section)
        phone = await self.browser.new_page(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
        errors=[]
        phone.on('pageerror', lambda error: errors.append(str(error)))
        requests=[]
        async def route(request):
            path = request.request.url.split('bridge.test',1)[-1]
            if path=='/':
                await request.fulfill(content_type='text/html', body=(Path(__file__).parent/'index.html').read_text())
            elif path=='/api/connect':
                await request.fulfill(json={'ok':True})
            elif path=='/api/state':
                await request.fulfill(json={'active':False,'headless':True,'windows':[]})
            elif path in {'/api/resume','/api/login/status'}:
                await request.fulfill(json={'phase':'authenticated','message':'Restored fixture','number':None})
            elif path=='/api/content':
                body=request.request.post_data_json
                requests.append(body)
                data=documents[body['section']]
                if body.get('url'):
                    self.assertIn('/grade/report/user/index.php?id=',body['url'])
                    data={**data,'title':'ICT — User report','courses':[],'activities':[],'paragraphs':[],
                          'tables':[['Работа','Балл'],['Quiz 1','95.00']]}
                    data['tables']=[data['tables']]
                await request.fulfill(json={**data,'section':body['section'],'detail':bool(body.get('url')),'updated':'12:00','warnings':[]})
            else:
                await request.abort()
        await phone.route('**/*',route)
        await phone.goto('http://bridge.test/')
        await expect(phone.locator('#document .course')).to_have_count(7)
        await phone.locator('#menuButton').click()
        await phone.locator('#mobileDrawer [data-section=dashboard]').click()
        await expect(phone.locator('#document .card')).to_have_count(5)
        await expect(phone.locator('#document')).to_contain_text('24 October 2026')
        await phone.locator('#menuButton').click()
        await phone.locator('#mobileDrawer [data-section=grades]').click()
        await expect(phone.locator('.grade-table tbody tr')).to_have_count(7)
        await expect(phone.locator('#document')).to_contain_text('0.00')
        await phone.locator('.grade-link').nth(2).click()
        await expect(phone.locator('#document')).to_contain_text('Quiz 1')
        await expect(phone.locator('#document')).to_contain_text('95.00')
        self.assertNotIn('user=',requests[-1]['url'])
        self.assertFalse(errors,errors)
        self.assertTrue(await phone.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        await phone.close()


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.pool = app.BrowserPool()
        self.session = app.BridgeSession()

    async def asyncTearDown(self):
        await self.session.reset_browser()
        await app.pool.close()

    async def test_reload_reuses_memory_session_and_logout_clears_it(self):
        page = await self.session.ensure_page()
        await page.context.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<script>window.M={cfg:{userId:17}}</script><main>Fixture</main>"))
        await page.goto(MOODLE + "/")
        await self.session.login_status()
        self.assertEqual((await self.session.resume())["phase"], "authenticated")
        self.assertIs(await self.session.ensure_page(), page)
        await self.session.close()
        self.assertEqual((await self.session.resume())["phase"], "idle")
        self.assertIsNone(self.session.context)

    async def test_new_session_never_restores_another_users_cookies(self):
        page = await self.session.ensure_page()
        await page.context.add_cookies([{"name":"fixture-session","value":"private","url":MOODLE}])
        other = app.BridgeSession()
        try:
            await other.ensure_page()
            self.assertEqual(await other.context.cookies(), [])
            self.assertEqual((await other.resume())["phase"], "idle")
        finally:
            await other.reset_browser()


if __name__ == '__main__':
    unittest.main(verbosity=2)
