"""Teacher demo: real HTTP/browser flow, permissions, isolation and lesson boundaries."""
import asyncio
import os
from pathlib import Path
import socket
import tempfile
import unittest
from datetime import datetime, timedelta

# Never open the real student cache while running standalone checks.
_test_db = tempfile.TemporaryDirectory(prefix='aitu-teacher-tests-')
os.environ['BRIDGE_DB_PATH'] = str(Path(_test_db.name) / 'students.sqlite3')
import uvicorn
from playwright.async_api import async_playwright
import app
from school_database import SchoolDatabase
from school_test_fixture import create_school_fixture
_school_dir = tempfile.TemporaryDirectory(prefix='aitu-school-fixture-')
app.school_db = SchoolDatabase(create_school_fixture(Path(_school_dir.name)/'school.sqlite3'))
from teacher_demo import ASTANA, workspace_view


class LessonTests(unittest.TestCase):
    def test_current_and_next_lesson_boundaries(self):
        now = datetime(2026, 10, 28, 23, 30, tzinfo=ASTANA)
        starts=now.replace(minute=0)
        data={'teacher':{},'demo':True,'source':'test','lessons':[{'id':i+1,'starts_at':(starts+timedelta(hours=i*2)).isoformat(),'ends_at':(starts+timedelta(hours=i*2+1)).isoformat()} for i in range(3)]}
        self.assertEqual(workspace_view(data, now)['current_lesson_id'], 1)
        between = workspace_view(data, now.replace(minute=0) + timedelta(hours=1))
        self.assertIsNone(between['current_lesson_id'])
        self.assertEqual(between['next_lesson_id'], 2)
        after = workspace_view(data, now + timedelta(days=1))
        self.assertIsNone(after['current_lesson_id'])
        self.assertIsNone(after['next_lesson_id'])


class TeacherTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_and_api(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(app.app, log_level='error', access_log=False))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.02)
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(viewport={'width':390,'height':844})
                page = await context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(base, wait_until='networkidle')
                await page.locator('#signIn').wait_for(state='visible')
                self.assertEqual((await context.request.get(base+'/api/teacher/workspace')).status, 403)
                await page.locator('#teacherDemoButton').click()
                await page.locator('.teacher-student').first.wait_for()
                self.assertIn('Information and Communication Technologies', await page.locator('#teacherCurrent').inner_text())
                self.assertIn('C1.2.228', await page.locator('#teacherCurrent').inner_text())
                self.assertEqual(await page.locator('.teacher-student').count(), 12)
                self.assertIn('teacher004', await page.locator('.account-label').inner_text())
                # English UI persists across reloads without changing the teacher session.
                await page.locator('header .language-select').select_option('en')
                await page.wait_for_function("()=>document.documentElement.lang==='en'")
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('#pageTitle').inner_text(),'Teacher workspace')
                self.assertEqual(await page.locator('#teacherMarkAll').inner_text(),'Mark all present')
                self.assertEqual(await page.locator('#teacherSearch').get_attribute('placeholder'),'First or last name')
                self.assertEqual(await page.locator('#menuButton').get_attribute('aria-label'),'Open navigation')
                self.assertEqual(await page.locator('#teacher-status-1 option[value="excused"]').inner_text(),'Excused')
                await page.locator('#teacherLesson').select_option('2')
                await page.wait_for_function("()=>document.querySelector('#teacherRoster').textContent.includes('SE-2624')")
                await page.locator('#teacher-status-101').select_option('late')
                await page.wait_for_function("()=>document.querySelector('#teacherSummary').textContent.includes('Marked 1 / 12')")
                await page.reload(wait_until='networkidle')
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('html').get_attribute('lang'),'en')
                # Return to lesson 2, then change language while staying in that lesson.
                await page.locator('#teacherLesson').select_option('2')
                await page.wait_for_function("()=>document.querySelector('#teacher-status-101')?.value==='late'")
                await page.locator('header .language-select').select_option('ru')
                await page.wait_for_function("()=>document.documentElement.lang==='ru'")
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('#teacherLesson').input_value(),'2')
                self.assertEqual(await page.locator('#teacher-status-101').input_value(),'late')
                self.assertEqual(await page.locator('#pageTitle').inner_text(),'Кабинет учителя')
                await page.locator('#teacherLesson').select_option('1')
                await page.wait_for_function("()=>document.querySelector('#teacherRoster').textContent.includes('SE-2623')")
                await page.locator('#teacher-status-1').select_option('absent')
                await page.wait_for_function("() => document.querySelector('#teacherSummary').textContent.includes('отсутствуют 1')")
                await page.reload(wait_until='networkidle')
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('#teacher-status-1').input_value(), 'absent')
                await page.locator('#teacherLesson').select_option('2')
                await page.wait_for_function("() => document.querySelector('#teacherRoster').textContent.includes('SE-2624')")
                self.assertEqual(await page.locator('#teacher-status-101').input_value(), 'late')
                await page.locator('#teacherLesson').select_option('1')
                await page.wait_for_function("() => document.querySelector('#teacher-status-1')?.value === 'absent'")
                await page.locator('#teacherSearch').fill('Нурасыл')
                self.assertEqual(await page.locator('.teacher-student:visible').count(), 1)
                await page.locator('#teacherSearch').fill('')
                await page.locator('#teacherMarkAll').click()
                await page.wait_for_function("() => document.querySelector('#teacherSummary').textContent.includes('присутствуют 12')")
                for width in (320,390,1440):
                    await page.set_viewport_size({'width':width,'height':900})
                    self.assertTrue(await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                    self.assertTrue(await page.locator('main').evaluate('(el)=>el.scrollWidth<=el.clientWidth'))
                await page.screenshot(path=str(Path(_test_db.name)/'teacher-desktop.png'),full_page=True)
                await page.set_viewport_size({'width':390,'height':844})
                await page.locator('main').evaluate('(el)=>el.scrollTop=0')
                await page.screenshot(path=str(Path(_school_dir.name)/'teacher-preview.png'),full_page=True,animations='disabled')
                # Changing status validates lesson and student membership, not just IDs in the UI.
                for payload,status in [({'lesson_id':999,'student_id':1,'status':'present'},404),
                                       ({'lesson_id':1,'student_id':999,'status':'present'},404),
                                       ({'lesson_id':1,'student_id':1,'status':'bad'},422)]:
                    response=await context.request.post(base+'/api/teacher/attendance',data=payload)
                    self.assertEqual(response.status,status)
                other=await pw.request.new_context(base_url=base)
                await other.post('/api/connect',data={})
                self.assertEqual((await other.post('/api/teacher/attendance',data={'lesson_id':1,'student_id':1,'status':'absent'})).status,403)
                await other.post('/api/teacher/demo',data={})
                fresh=await (await other.get('/api/teacher/lessons/1/students')).json()
                self.assertIsNone(fresh['students'][0]['status'])
                # Existing Microsoft identity cannot be silently replaced by a demo role.
                token=next(c['value'] for c in (await other.storage_state())['cookies'] if c['name']=='bridge_session')
                app.sessions[token].identity={'email':'fixture@example.test','moodle_user_id':'42'}
                self.assertEqual((await other.post('/api/teacher/demo',data={})).status,409)
                app.sessions[token].identity=None
                await other.dispose()
                self.assertEqual((await context.request.post(base+'/api/login',data={'email':'fixture@example.test','password':'test'})).status,409)
                # Teacher navigation also survives leaving the lesson to view the map.
                await page.locator('#teacherCurrent button').click()
                await page.locator('.campus-map').wait_for()
                await page.locator('.quick-nav [data-teacher-section=teacher]').click()
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('#teacher-status-1').input_value(),'present')
                await page.locator('#accountButton').click()
                await page.locator('#logout').click()
                await page.locator('#signIn').wait_for(state='visible')
                self.assertEqual((await context.request.get(base+'/api/teacher/workspace')).status,401)
                await page.locator('#teacherDemoButton').click()
                await page.locator('.teacher-student').first.wait_for()
                self.assertEqual(await page.locator('#teacher-status-1').input_value(),'')
                self.assertEqual(errors,[])
                await browser.close()
        finally:
            server.should_exit=True
            await asyncio.wait_for(task,10)
            sock.close()


if __name__=='__main__':
    unittest.main()
