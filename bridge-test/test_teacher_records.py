"""Real HTTP/UI checks for group coursework, grading and persistence across restart."""
import asyncio
from datetime import datetime, timedelta
import os
from pathlib import Path
import socket
import tempfile
import unittest

_test_dir = tempfile.TemporaryDirectory(prefix='aitu-teacher-records-')
os.environ['BRIDGE_DB_PATH'] = str(Path(_test_dir.name) / 'students.sqlite3')
import uvicorn
from playwright.async_api import async_playwright
import app
from school_database import SchoolDatabase
from school_test_fixture import create_school_fixture
_school_dir = tempfile.TemporaryDirectory(prefix='aitu-school-fixture-')
app.school_db = SchoolDatabase(create_school_fixture(Path(_school_dir.name)/'school.sqlite3'))
from teacher_demo import ASTANA


class CourseworkTests(unittest.IsolatedAsyncioTestCase):
    async def start_server(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        self.base = 'http://127.0.0.1:' + str(sock.getsockname()[1])
        self.server = uvicorn.Server(uvicorn.Config(app.app, log_level='error', access_log=False))
        self.task = asyncio.create_task(self.server.serve(sockets=[sock]))
        while not self.server.started:
            if self.task.done(): await self.task
            await asyncio.sleep(.02)

    async def stop_server(self):
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 10)

    async def test_complete_teacher_workflow(self):
        await self.start_server()
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(viewport={'width':390,'height':844})
                page = await context.new_page()
                errors=[]
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(self.base, wait_until='networkidle')
                await page.locator('#teacherDemoButton').click()
                await page.locator('.teacher-student').first.wait_for()
                client=context.request
                async def post(path, data):
                    return await client.post(self.base+path, data=data)
                async def get(path):
                    return await client.get(self.base+path)
                async def create(kind, group='SE-2623', course='1', future=False):
                    response=await post('/api/teacher/assessments',{
                        'kind':kind,'group':group,'course_id':course,'title':kind+' test',
                        'description':'Instructions <b>stay text</b>',
                        'scheduled_at':(datetime.now(ASTANA)+timedelta(days=2 if future else -2)).isoformat(),
                        'duration_minutes':90})
                    self.assertEqual(response.status,200,await response.text())
                    return await response.json()
                # Distinct students, correct group membership and course assignments.
                groups=await (await get('/api/teacher/groups')).json()
                self.assertEqual(len(groups['groups']),2)
                one=await (await get('/api/teacher/groups/SE-2623/students')).json()
                two=await (await get('/api/teacher/groups/SE-2624/students')).json()
                self.assertFalse({s['id'] for s in one['students']} & {s['id'] for s in two['students']})
                self.assertEqual((await get('/api/teacher/groups/NO-GROUP/students')).status,404)
                for kind in ['midterm','endterm','final']:
                    item=await create(kind)
                    self.assertTrue(item['can_grade'])
                    response=await post(f"/api/teacher/assessments/{item['id']}/grades",{'student_id':1,'grade':0,'comment':'Needs practice'})
                    self.assertEqual(response.status,200)
                planned=await create('midterm',future=True)
                self.assertFalse(planned['can_grade'])
                self.assertEqual((await post(f"/api/teacher/assessments/{planned['id']}/grades",{'student_id':1,'grade':70})).status,409)
                # Homework may be graded before its deadline; comments may be saved without a grade.
                homework=await create('homework',future=True)
                hid=homework['id']
                self.assertTrue(homework['can_grade'])
                self.assertEqual((await post(f'/api/teacher/assessments/{hid}/grades',{'student_id':1,'grade':98.5,'comment':'Clear solution'})).status,200)
                self.assertEqual((await post(f'/api/teacher/assessments/{hid}/grades',{'student_id':2,'comment':'Please attach your explanation'})).status,200)
                for grade in [-1,101]:
                    self.assertEqual((await post(f'/api/teacher/assessments/{hid}/grades',{'student_id':1,'grade':grade})).status,422)
                self.assertEqual((await post(f'/api/teacher/assessments/{hid}/grades',{'student_id':101,'grade':80})).status,404)
                invalid={'kind':'quiz','group':'SE-2623','course_id':'1','title':'Bad type','scheduled_at':datetime.now(ASTANA).isoformat()}
                self.assertEqual((await post('/api/teacher/assessments',invalid)).status,422)
                invalid.update(kind='homework',group='SE-2624',course_id='2')
                self.assertEqual((await post('/api/teacher/assessments',invalid)).status,422)
                invalid.update(group='SE-2623',course_id='1',scheduled_at='2026-01-01T12:00:00')
                self.assertEqual((await post('/api/teacher/assessments',invalid)).status,422)
                other=await pw.request.new_context()
                await other.post(self.base+'/api/connect',data={})
                self.assertEqual((await other.get(self.base+'/api/teacher/assessments')).status,403)
                await other.post(self.base+'/api/teacher/demo',data={})
                self.assertEqual((await other.get(self.base+f'/api/teacher/assessments/{hid}')).status,404)
                self.assertEqual((await other.post(self.base+f'/api/teacher/assessments/{hid}/grades',data={'student_id':1,'grade':99})).status,404)
                self.assertEqual((await (await other.get(self.base+'/api/teacher/assessments')).json())['assessments'],[])
                await other.dispose()
                # Directory UI supports both group filtering and search.
                await page.locator('.quick-nav [data-teacher-section=teacher-students]').click()
                await page.locator('.teacher-directory-student').first.wait_for()
                self.assertEqual(await page.locator('.teacher-directory-student').count(),24)
                await page.locator('#teacherGroup').select_option('SE-2624')
                await page.wait_for_function("()=>document.querySelectorAll('.teacher-directory-student').length===12")
                await page.locator('#teacherDirectorySearch').fill('Азамат')
                self.assertEqual(await page.locator('.teacher-directory-student:visible').count(),1)
                # Create real records using the teacher form, then grade homework in the UI.
                await page.locator('.quick-nav [data-teacher-section=teacher-homework]').click()
                await page.locator('#teacherAssessmentForm').wait_for(state='visible')
                await page.locator('#assessmentTitle').fill('ICT homework · UI')
                await page.locator('#assessmentDescription').fill('Read chapter 4 and answer the questions.')
                await page.locator('#assessmentDate').fill('2026-11-30T18:00')
                await page.locator('#teacherAssessmentForm button[type=submit]').click()
                await page.locator('.teacher-grade-student').first.wait_for()
                self.assertIn('SE-2624',await page.locator('.teacher-gradebook-header').inner_text())
                form=page.locator('.teacher-grade-form[data-student="101"]')
                await form.locator('input').fill('85.5')
                await form.locator('textarea').fill('Good work. Explain question 3. <script>no execution</script>')
                await form.locator('button').click()
                await page.wait_for_function("()=>document.querySelector('#teacherGradeSummary').textContent.includes('Оценено 1 / 12')")
                created=await (await get('/api/teacher/assessments?category=homework&group=SE-2624')).json()
                ui_homework=next(item for item in created['assessments'] if item['title']=='ICT homework · UI')
                # Changing language preserves the current gradebook, group and saved values.
                await page.locator('header .language-select').select_option('en')
                await page.wait_for_function("()=>document.documentElement.lang==='en'")
                await page.locator('.teacher-grade-student').first.wait_for()
                self.assertEqual(await page.locator('#pageTitle').inner_text(),'Homework')
                form=page.locator('.teacher-grade-form[data-student="101"]')
                self.assertEqual(await form.locator('input').input_value(),'85.5')
                self.assertIn('Explain question 3',await form.locator('textarea').input_value())
                self.assertEqual(await page.locator('#teacherGroup').input_value(),'SE-2624')
                for width in [320,390,1440]:
                    await page.set_viewport_size({'width':width,'height':900})
                    self.assertTrue(await page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                    self.assertTrue(await page.locator('main').evaluate('(el)=>el.scrollWidth<=el.clientWidth'))
                await page.set_viewport_size({'width':390,'height':844})
                await page.locator('main').evaluate('(el)=>el.scrollTop=0')
                await page.screenshot(path=str(Path(_school_dir.name)/'teacher-homework-preview.png'),animations='disabled')
                # Add a past exam through the form and enter its grades.
                await page.locator('.quick-nav [data-teacher-section=teacher-exams]').click()
                await page.locator('#teacherAssessmentForm').wait_for(state='visible')
                await page.locator('#assessmentKind').select_option('final')
                await page.locator('#assessmentTitle').fill('Final · UI')
                await page.locator('#assessmentDate').fill('2026-01-01T10:00')
                await page.locator('#teacherAssessmentForm button[type=submit]').click()
                await page.locator('.teacher-grade-student').first.wait_for()
                form=page.locator('.teacher-grade-form[data-student="101"]')
                await form.locator('input').fill('0')
                await form.locator('textarea').fill('Retake required.')
                await form.locator('button').click()
                await page.wait_for_function("()=>document.querySelector('#teacherGradeSummary').textContent.includes('Graded 1 / 12')")
                # Logout revokes authorization but retains coursework for this demo browser.
                await page.locator('#accountButton').click();await page.locator('#logout').click()
                await page.locator('#signIn').wait_for(state='visible')
                await page.locator('#teacherDemoButton').click();await page.locator('.teacher-student').first.wait_for()
                detail=await (await get(f"/api/teacher/assessments/{ui_homework['id']}")).json()
                self.assertEqual(next(student for student in detail['students'] if student['id']==101)['grade'],85.5)
                self.assertIn('Explain question 3',next(student for student in detail['students'] if student['id']==101)['comment'])
                # A real application shutdown clears sessions; SQLite and owner cookie survive.
                await page.close();await self.stop_server();await self.start_server()
                await client.post(self.base+'/api/connect',data={})
                self.assertEqual((await get('/api/teacher/assessments')).status,403)
                await client.post(self.base+'/api/teacher/demo',data={})
                detail=await (await get(f"/api/teacher/assessments/{ui_homework['id']}")).json()
                self.assertEqual(next(student for student in detail['students'] if student['id']==101)['grade'],85.5)
                self.assertEqual(next(student for student in detail['students'] if student['id']==101)['comment'],'Good work. Explain question 3. <script>no execution</script>')
                self.assertEqual(errors,[])
                await browser.close()
        finally:
            if not self.task.done(): await self.stop_server()

    async def test_file_upload_download_and_persistence(self):
        from urllib.parse import quote
        import http.client
        from unittest.mock import patch
        await self.start_server()
        try:
            async with async_playwright() as pw:
                browser=await pw.chromium.launch(headless=True)
                context=await browser.new_context(viewport={'width':390,'height':844})
                page=await context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                await page.goto(self.base,wait_until='networkidle')
                await page.locator('#teacherDemoButton').click();await page.locator('.teacher-student').first.wait_for()
                await page.locator('.quick-nav [data-teacher-section=teacher-homework]').click()
                await page.locator('#teacherAssessmentForm').wait_for(state='visible')
                pdf=b'%PDF-1.4\nAssignment fixture\x00\xff\n%%EOF'
                doc=b'PK\x03\x04\x00\xff\x01Binary document fixture'
                # One successful file and one interrupted upload must not duplicate the assignment.
                seen={'count':0}
                async def fail_second(route):
                    seen['count']+=1
                    if seen['count']==2: await route.fulfill(status=503,json={'detail':'Не удалось загрузить файл.'})
                    else: await route.continue_()
                pattern='**/api/teacher/assessments/*/files?filename=*'
                await page.route(pattern,fail_second)
                await page.locator('#assessmentFiles').set_input_files([
                    {'name':'Задание 4.pdf','mimeType':'application/pdf','buffer':pdf},
                    {'name':'Answers.docx','mimeType':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','buffer':doc}])
                self.assertEqual(await page.locator('#assessmentTitle').input_value(),'Задание 4.pdf')
                await page.locator('#assessmentDate').fill('2026-11-30T18:00')
                await page.locator('#teacherAssessmentForm button[type=submit]').click()
                await page.locator('#teacherAttachments').wait_for(state='visible')
                self.assertIn('Работа создана.',await page.locator('#status').inner_text())
                self.assertEqual(await page.locator('.teacher-file a').count(),1)
                self.assertEqual(await page.locator('.teacher-file a').inner_text(),'Задание 4.pdf')
                await page.unroute(pattern,fail_second)
                await page.locator('#teacherAdditionalFiles').set_input_files({'name':'Answers.docx','mimeType':'application/octet-stream','buffer':doc})
                await page.locator('#teacherUploadForm button').click()
                await page.wait_for_function("()=>document.querySelectorAll('.teacher-file a').length===2")
                self.assertIn('Файлы загружены.',await page.locator('#teacherUploadForm').inner_text())
                client=context.request
                items=await (await client.get(self.base+'/api/teacher/assessments?category=homework')).json()
                self.assertEqual(len(items['assessments']),1)
                item=items['assessments'][0];aid=item['id']
                self.assertEqual(item['file_count'],2)
                detail=await (await client.get(self.base+f'/api/teacher/assessments/{aid}')).json()
                self.assertEqual([f['size'] for f in detail['files']],[len(pdf),len(doc)])
                # Browser download preserves Unicode name and exact binary content.
                async with page.expect_download() as pending:
                    await page.locator('.teacher-file a').first.click()
                download=await pending.value
                self.assertEqual(download.suggested_filename,'Задание 4.pdf')
                self.assertEqual(Path(await download.path()).read_bytes(),pdf)
                fid=detail['files'][0]['id']
                response=await client.get(self.base+f'/api/teacher/assessments/{aid}/files/{fid}')
                self.assertEqual(await response.body(),pdf)
                self.assertEqual(response.headers['content-type'],'application/octet-stream')
                self.assertTrue(response.headers['content-disposition'].startswith('attachment;'))
                self.assertEqual(response.headers['x-content-type-options'],'nosniff')
                # A different demo owner may neither download nor attach files to this assessment.
                other=await pw.request.new_context()
                await other.post(self.base+'/api/connect',data={})
                self.assertEqual((await other.get(self.base+f'/api/teacher/assessments/{aid}/files/{fid}')).status,403)
                await other.post(self.base+'/api/teacher/demo',data={})
                self.assertEqual((await other.get(self.base+f'/api/teacher/assessments/{aid}/files/{fid}')).status,404)
                self.assertEqual((await other.post(self.base+f'/api/teacher/assessments/{aid}/files?filename=no.txt',data=b'secret')).status,404)
                await other.dispose()
                async def upload(name,data):
                    return await client.post(self.base+f'/api/teacher/assessments/{aid}/files?filename='+quote(name,safe=''),data=data,headers={'Content-Type':'application/octet-stream'})
                self.assertEqual((await upload('empty.txt',b'')).status,422)
                self.assertEqual((await upload('..',b'x')).status,422)
                self.assertEqual((await upload('a'*256,b'x')).status,422)
                sanitized=await (await upload('../../folder\\exam.html',b'<script>alert(1)</script>')).json()
                self.assertEqual(sanitized['filename'],'exam.html')
                # Both declared-length and chunked streams enforce the server size bound.
                self.assertEqual(app.MAX_FILE_BYTES,20*1024*1024)
                with patch.object(app,'MAX_FILE_BYTES',256):
                    self.assertEqual((await upload('too-big.bin',b'x'*257)).status,413)
                    cookies=await context.cookies()
                    cookie='; '.join(c['name']+'='+c['value'] for c in cookies)
                    def chunked():
                        parts=self.base.rsplit(':',1)
                        conn=http.client.HTTPConnection('127.0.0.1',int(parts[1]),timeout=5)
                        conn.request('POST',f'/api/teacher/assessments/{aid}/files?filename=chunked.bin',body=iter([b'x'*200,b'y'*200]),headers={'Cookie':cookie,'Content-Type':'application/octet-stream'},encode_chunked=True)
                        result=conn.getresponse();status=result.status;result.read();conn.close();return status
                    self.assertEqual(await asyncio.to_thread(chunked),413)
                # Upload an exam file too, using the normal creation form.
                await page.locator('.quick-nav [data-teacher-section=teacher-exams]').click()
                await page.locator('#teacherAssessmentForm').wait_for(state='visible')
                await page.locator('#assessmentKind').select_option('endterm')
                await page.locator('#assessmentFiles').set_input_files({'name':'Endterm.zip','mimeType':'application/zip','buffer':doc})
                await page.locator('#assessmentDate').fill('2026-01-01T10:00')
                await page.locator('#teacherAssessmentForm button[type=submit]').click()
                await page.locator('.teacher-file a').wait_for(state='visible')
                self.assertEqual(await page.locator('.teacher-file a').inner_text(),'Endterm.zip')
                # Existing grade/comment flow works when an assessment contains attachments.
                form=page.locator('.teacher-grade-form[data-student="1"]')
                await form.locator('input').fill('91');await form.locator('textarea').fill('Reviewed attached exam.')
                await form.locator('button').click()
                await page.wait_for_function("()=>document.querySelector('#teacherGradeSummary').textContent.includes('Оценено 1 / 12')")
                await page.locator('header .language-select').select_option('en')
                await page.wait_for_function("()=>document.documentElement.lang==='en'")
                await page.locator('.teacher-file a').wait_for(state='visible')
                self.assertEqual(await page.locator('#teacherAttachments h2').inner_text(),'Assessment files')
                self.assertEqual(await page.locator('#teacherUploadForm button').inner_text(),'Upload files')
                for width in [320,390,1440]:
                    await page.set_viewport_size({'width':width,'height':900})
                    self.assertTrue(await page.locator('main').evaluate('(el)=>el.scrollWidth<=el.clientWidth'))
                # Transactional count check enforces ten attachments; failed requests add no rows.
                for index in range(7):self.assertEqual((await upload(f'file-{index}.txt',b'data')).status,200)
                self.assertEqual((await upload('eleventh.txt',b'data')).status,422)
                detail=await (await client.get(self.base+f'/api/teacher/assessments/{aid}')).json()
                self.assertEqual(len(detail['files']),10)
                # Files and original coursework survive a real server restart.
                await page.close();await self.stop_server();await self.start_server()
                await client.post(self.base+'/api/connect',data={});await client.post(self.base+'/api/teacher/demo',data={})
                detail=await (await client.get(self.base+f'/api/teacher/assessments/{aid}')).json()
                self.assertEqual(detail['assessment']['title'],'Задание 4.pdf')
                self.assertEqual(len(detail['files']),10)
                response=await client.get(self.base+f'/api/teacher/assessments/{aid}/files/{fid}')
                self.assertEqual(await response.body(),pdf)
                self.assertEqual(errors,[])
                await browser.close()
        finally:
            if not self.task.done():await self.stop_server()



if __name__=='__main__':
    unittest.main()
