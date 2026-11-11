"""Relational roster and read-only administration: isolated SQL + real HTTP/UI."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from school_database import SchoolDatabase
from school_test_fixture import create_school_fixture

_test_dir = tempfile.TemporaryDirectory(prefix='aitu-admin-test-')
os.environ['BRIDGE_DB_PATH'] = str(Path(_test_dir.name)/'bridge.sqlite3')
import app
import uvicorn
from playwright.async_api import async_playwright


class SchoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_roster_is_live_scoped_and_source_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'school.sqlite3'
            school=SchoolDatabase(create_school_fixture(path))
            statements=[]
            event.listen(school.engine,'before_cursor_execute',lambda conn,cursor,statement,*args:statements.append(statement))
            try:
                workspace=await school.workspace()
                self.assertEqual(workspace['teacher']['username'],'teacher004')
                self.assertEqual(len(await school.students(1)),24)
                self.assertNotIn(999,{s['id'] for s in await school.students(1)})
                self.assertEqual(len(await school.students(1,'SE-2623','1')),12)
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute("UPDATE students SET first_name='Renamed in database' WHERE id=1")
                    db.execute('DELETE FROM enrollments WHERE student_id=2 AND course_id=1')
                rows=await school.students(1,'SE-2623','1')
                self.assertEqual(next(s for s in rows if s['id']==1)['name'],'Renamed in database Test')
                self.assertNotIn(2,{s['id'] for s in rows})
                overview=await school.overview()
                self.assertEqual(overview['counts']['students'],25)
                self.assertEqual(overview['counts']['teachers'],2)
                self.assertTrue(statements)
                self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements),statements)
            finally:
                await school.close()


class AdminTeacherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aitu-school-integration-')
        self.school_path=Path(self.temp.name)/'school.sqlite3'
        self.previous=app.school_db
        app.school_db=SchoolDatabase(create_school_fixture(self.school_path))
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0))
        self.base='http://127.0.0.1:'+str(self.sock.getsockname()[1])
        self.server=uvicorn.Server(uvicorn.Config(app.app,log_level='error',access_log=False))
        self.task=asyncio.create_task(self.server.serve(sockets=[self.sock]))
        while not self.server.started:
            if self.task.done():await self.task
            await asyncio.sleep(.02)
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=True)
        self.context=await self.browser.new_context(viewport={'width':390,'height':844})
        self.page=await self.context.new_page()
        self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        await self.page.goto(self.base,wait_until='networkidle')
        await self.page.locator('#signIn').wait_for(state='visible')

    async def asyncTearDown(self):
        await self.browser.close();await self.pw.stop()
        self.server.should_exit=True;await asyncio.wait_for(self.task,10)
        self.sock.close();app.school_db=self.previous;self.temp.cleanup()

    async def test_admin_ui_counts_role_restore_and_degraded_database(self):
        client=self.context.request
        self.assertEqual((await client.get(self.base+'/api/admin/overview')).status,403)
        await self.page.locator('#adminDemoButton').click()
        await self.page.locator('.admin-metric').first.wait_for()
        response=await client.get(self.base+'/api/admin/overview');self.assertEqual(response.status,200)
        data=await response.json()
        self.assertEqual(data['database']['counts']['students'],25)
        self.assertEqual(data['database']['counts']['teachers'],2)
        self.assertEqual(data['database']['counts']['admins'],1)
        self.assertGreater(data['system']['requests'],0)
        self.assertEqual(data['system']['admin_sessions'],1)
        self.assertGreater(len(data['database']['tables']),0)
        self.assertNotIn('password_hash',str(data));self.assertNotIn('://',data['database']['name'])
        self.assertEqual((await client.get(self.base+'/api/teacher/workspace')).status,403)
        self.assertEqual((await client.post(self.base+'/api/teacher/demo',data={})).status,409)
        self.assertEqual((await client.post(self.base+'/api/login',data={'email':'test@example.test','password':'fixture'})).status,409)
        # Database and people views are real API data and remain usable on mobile.
        await self.page.locator('.quick-nav [data-admin-section=admin-users]').click()
        await self.page.wait_for_function("()=>document.querySelector('#pageTitle').textContent==='Пользователи и группы'")
        await self.page.locator('#document table').first.wait_for()
        self.assertIn('teacher004',await self.page.locator('#document').inner_text())
        self.assertNotIn('999',await self.page.locator('#document').inner_text())
        for width in [320,390,430,1440]:
            await self.page.set_viewport_size({'width':width,'height':900})
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            self.assertTrue(await self.page.locator('main').evaluate('(e)=>e.scrollWidth<=e.clientWidth'))
        await self.page.locator('header .language-select').select_option('en')
        await self.page.wait_for_function("()=>document.documentElement.lang==='en'")
        await self.page.locator('#document table').first.wait_for()
        self.assertEqual(await self.page.locator('#pageTitle').inner_text(),'People and groups')
        self.assertEqual(await self.page.evaluate('currentSection'),'admin-users')
        await self.page.reload(wait_until='networkidle')
        await self.page.locator('.admin-metric').first.wait_for()
        with patch.object(app.school_db,'overview',new=AsyncMock(side_effect=SQLAlchemyError('do not expose credentials'))):
            degraded=await (await client.get(self.base+'/api/admin/overview')).json()
            self.assertEqual(degraded['status'],'degraded')
            self.assertIsNone(degraded['database']['counts'])
            self.assertNotIn('credentials',str(degraded))
            self.assertEqual(len(degraded['local_databases']),2)
        await self.page.locator('#accountButton').click();await self.page.locator('#logout').click()
        await self.page.locator('#signIn').wait_for(state='visible')
        self.assertEqual((await client.get(self.base+'/api/admin/overview')).status,401)
        self.assertEqual(self.errors,[])

    async def test_teacher_enrolment_changes_and_foreign_student_denied(self):
        client=self.context.request
        await self.page.locator('#teacherDemoButton').click()
        await self.page.locator('.teacher-student').first.wait_for()
        self.assertEqual(await self.page.locator('.teacher-student').count(),12)
        with closing(sqlite3.connect(self.school_path)) as db, db:
            db.execute("UPDATE students SET first_name='Database name' WHERE id=1")
            db.execute('DELETE FROM enrollments WHERE student_id=2 AND course_id=1')
        rows=await (await client.get(self.base+'/api/teacher/lessons/1/students')).json()
        self.assertEqual(len(rows['students']),11)
        self.assertIn('Database name Test',[s['name'] for s in rows['students']])
        for student in [2,101,999]:
            self.assertEqual((await client.post(self.base+'/api/teacher/attendance',data={'lesson_id':1,'student_id':student,'status':'present'})).status,404)
        self.assertEqual((await client.get(self.base+'/api/teacher/groups/OTHER/students')).status,404)
        self.assertEqual((await client.get(self.base+'/api/admin/overview')).status,403)
        self.assertEqual((await client.post(self.base+'/api/admin/demo',data={})).status,409)
        created=await client.post(self.base+'/api/teacher/assessments',data={
            'kind':'homework','group':'SE-2623','course_id':'1','title':'Database-linked work',
            'scheduled_at':(datetime.now(app.ASTANA)+timedelta(days=1)).isoformat()})
        self.assertEqual(created.status,200)
        work=await created.json()
        self.assertEqual((await client.post(self.base+f"/api/teacher/assessments/{work['id']}/grades",data={'student_id':2,'grade':90})).status,404)
        self.assertEqual((await client.post(self.base+f"/api/teacher/assessments/{work['id']}/grades",data={'student_id':1,'grade':90})).status,200)
        with patch.object(app.school_db,'students',new=AsyncMock(side_effect=SQLAlchemyError('secret detail'))):
            failed=await client.get(self.base+'/api/teacher/lessons/1/students')
            self.assertEqual(failed.status,503)
            self.assertNotIn('secret',await failed.text())
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main(verbosity=2)
