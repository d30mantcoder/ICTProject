"""Attendance regression tests: real bridge HTTP/Chromium, synthetic LMS only."""
import asyncio
from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
import unittest
from fastapi import HTTPException
import app
import test_multiuser as support
from moodle_reader import content_url
from attendance_reader import day_key, status_kind, report_events

MOODLE = app.MOODLE


class AttendanceURLTests(unittest.TestCase):
    def test_report_is_canonical_and_never_replays_another_student_or_action(self):
        target = content_url(MOODLE + '/mod/attendance/view.php?id=81&studentid=999'
                             '&view=2&curdate=1&mode=1&edit=1&sesskey=secret&chapterid=1', MOODLE)
        self.assertEqual(target, MOODLE + '/mod/attendance/view.php?id=81&view=5')
        self.assertEqual(content_url(target, MOODLE), target)

    def test_calendar_dates_and_statuses_do_not_guess(self):
        for text in ["Thu 22 Oct 2026 09:00", "22 октября 2026", "22 қазан 2026", "2026-10-22", "22.10.2026"]:
            self.assertEqual(day_key(text), "2026-10-22")
        self.assertIsNone(day_key("22 October"))
        self.assertIsNone(day_key("31.02.2026"))
        self.assertEqual(status_kind("Present"), "present")
        self.assertEqual(status_kind("Absent"), "absent")
        self.assertEqual(status_kind("?"), "unmarked")
        self.assertEqual(status_kind("P"), "other")
        self.assertEqual(status_kind("0"), "other")

    def test_marking_and_staff_endpoints_are_not_readable_content(self):
        for path in ('attendance.php?sessid=1', 'take.php?id=1', 'manage.php?id=1',
                     'report.php?id=1', 'view.php', 'view.php?id=oops'):
            with self.subTest(path=path), self.assertRaises(HTTPException):
                content_url(MOODLE + '/mod/attendance/' + path, MOODLE)
        with self.assertRaises(HTTPException):
            content_url('https://example.test/mod/attendance/view.php?id=1', MOODLE)


class AttendanceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = support.MultiUserTests.asyncSetUp
    asyncTearDown = support.MultiUserTests.asyncTearDown
    request = support.MultiUserTests.request
    authenticate_three = support.MultiUserTests.authenticate_three

    async def fixture(self, route, number):
        url = urlsplit(route.request.url)
        if url.netloc not in {'lms.astanait.edu.kz','login.microsoftonline.com'}:
            await route.abort()
            return
        if self.moodle_down or url.path not in {'/course/view.php', '/mod/attendance/view.php'}:
            return await support.MultiUserTests.fixture(self, route, number)
        self.assertIn(f'owner={number}', route.request.headers.get('cookie', ''))
        self.assertEqual(route.request.method, 'GET')
        query = parse_qs(url.query)
        if url.path == '/course/view.php':
            if query['id'] == ['999']:
                content = '<h1>Курс без Attendance</h1><p>Материалы</p>'
            else:
                content = f"""<h1>Course {number}</h1>
                <div hidden><a href="/mod/attendance/view.php?id={number*10}">Attendance lecture {number}</a></div>
                <a href="/mod/attendance/view.php?id={number*10+1}&amp;studentid=999&amp;view=1">Attendance practice {number}</a>
                <a href="/mod/assign/view.php?id={number}">Assignment</a>
                <a href="/mod/attendance/attendance.php?sessid=1&amp;sesskey=secret">Submit attendance</a>"""
        else:
            self.assertEqual(query, {'id': query['id'], 'view': ['5'], 'studentid': [str(number)]})
            if getattr(self, 'failed_journal', None) == int(query['id'][0]):
                await route.fulfill(status=503, body="Unavailable")
                return
            if getattr(self, 'redirect_report', False):
                # Simulate the final redirect URL without a network redirect escaping Playwright routing.
                await route.fulfill(content_type='text/html', body=f'<script>history.replaceState(null,"","/mod/attendance/report.php?id=1");window.M={{cfg:{{userId:{number}}}}}</script><main>Staff report</main>')
                return
            content = f"""<h1>Attendance {number}</h1>
            <table class="generaltable attwidth"><thead><tr><th>Date</th><th>Description</th><th>Status</th><th>Points</th><th>Remarks</th></tr></thead>
            <tbody><tr><td>22 Oct 2026 09:00</td><td>Lecture {number}</td><td>Absent</td><td>0 / 2</td><td>Private note {number}</td></tr>
            <tr><td>23 Oct 2026 09:00</td><td>Practice {number}</td><td>?</td><td>? / 2</td><td></td></tr></tbody></table>
            <table><tr><td>Percentage</td><td>{number*10}.00%</td></tr></table>
            <a href="/mod/attendance/attendance.php?sessid=1&amp;sesskey=secret">Submit attendance</a>"""
        await route.fulfill(content_type='text/html', body=f"""
        <script>window.M={{cfg:{{userId:{number}}}}}</script>
        <div class=usermenu><span class=usertext>User {number}</span></div>
        <main id=region-main>{content}</main>""")

    async def test_three_users_reports_cache_midnight_and_expired_session(self):
        await self.authenticate_three()
        overviews = await asyncio.gather(*(self.request(c, '/api/content', {'section':'attendance'})
                                          for c in self.clients))
        for number, (client, overview) in enumerate(zip(self.clients, overviews), 1):
            self.assertEqual(overview['attendance_view'], 'courses')
            self.assertEqual(overview['courses'][0]['title'], f'Course {number}')
            course = await self.request(client, '/api/content', {
                'section':'attendance', 'url':overview['courses'][0]['url']})
            items = [a for a in course['activities'] if '/mod/attendance/view.php' in a['url']]
            self.assertEqual(len(items), 2, 'Includes collapsed course sections')
            self.assertTrue(all('studentid' not in a['url'] for a in items))
        reports = await asyncio.gather(*(self.request(c, '/api/content', {
            'section':'attendance', 'url':MOODLE+f'/mod/attendance/view.php?id={i*10}&studentid=999'})
            for i,c in enumerate(self.clients, 1)))
        for number, report in enumerate(reports, 1):
            self.assertEqual(report['attendance_view'], 'report')
            self.assertEqual(report['table_headers'], [True, False])
            self.assertEqual(report['tables'][0][1][3], '0 / 2')
            self.assertEqual(report['tables'][0][2][2], '?')
            self.assertIn(f'Private note {number}', report['text'])
            for other in {1,2,3}-{number}:
                self.assertNotIn(f'Private note {other}', report['text'])
            self.assertEqual(report['tables'][1][0][1], f'{number*10}.00%')
            self.assertEqual(report['activities'], [])

        for s in self.owned:
            if s.data_refresh_task:
                await s.data_refresh_task
        payload = {'section':'attendance', 'url':MOODLE+'/mod/attendance/view.php?id=10'}
        cached = await self.request(self.clients[0], '/api/content', payload)
        self.assertTrue(cached['cached'])
        self.assertEqual(cached['tables'], reports[0]['tables'])
        # Midnight refresh includes opened report documents and the attendance overview.
        stamp = cached['cache_updated_at']
        self.clock += timedelta(minutes=2)
        await self.owned[0].refresh_saved_data()
        fresh = await self.request(self.clients[0], '/api/content', payload)
        self.assertNotEqual(fresh['cache_updated_at'], stamp)
        self.assertFalse(fresh['cache_stale'])
        self.owned[0].mark_moodle_expired()
        self.moodle_down = True
        offline = await self.request(self.clients[0], '/api/content', payload)
        self.assertTrue(offline['requires_login'])
        self.assertEqual(offline['tables'], reports[0]['tables'])
        self.assertEqual(offline['cache_updated_at'], fresh['cache_updated_at'])
        self.assertEqual((await self.request(self.clients[0], '/api/content',
            {'section':'attendance'}))['attendance_view'], 'courses')
        self.moodle_down = False
        other = await self.request(self.clients[1], '/api/content', {
            'section':'attendance', 'url':MOODLE+'/mod/attendance/view.php?id=20', 'refresh':True})
        self.assertIn('Private note 2', other['text'])

    async def test_calendar_opens_all_journals_for_three_users_without_extra_clicks(self):
        await self.authenticate_three()
        calendars = await asyncio.gather(*(self.request(c, "/api/attendance", {}) for c in self.clients))
        for number, result in enumerate(calendars,1):
            self.assertEqual(result["attendance_view"], "calendar")
            self.assertEqual(len(result["reports"]), 2)
            self.assertEqual(len(result["events"]), 4)
            self.assertEqual({e["day"] for e in result["events"]}, {"2026-10-22", "2026-10-23"})
            self.assertEqual({e["kind"] for e in result["events"]}, {"absent", "unmarked"})
            self.assertTrue(all(e["course"] == f"Course {number}" for e in result["events"]))
            self.assertTrue(all(e["remarks"] in {"", f"Private note {number}"} for e in result["events"]))
        for session in self.owned:
            if session.data_refresh_task:
                await session.data_refresh_task
        self.failed_journal = 10
        self.clock += timedelta(minutes=2)
        partial = await self.request(self.clients[0], "/api/attendance", {"refresh":True})
        self.assertTrue(partial["partial"])
        self.assertTrue(partial["cache_stale"])
        self.assertEqual(partial["events"], calendars[0]["events"])
        self.assertEqual(partial["cache_updated_at"], calendars[0]["cache_updated_at"])
        self.failed_journal = None
        self.owned[0].mark_moodle_expired()
        self.moodle_down = True
        offline = await self.request(self.clients[0], "/api/attendance", {})
        self.assertTrue(offline["requires_login"])
        self.assertEqual(offline["events"], calendars[0]["events"])
        self.assertTrue(offline["cached"])

    async def test_missing_journal_and_staff_redirect_are_not_report_data(self):
        await self.authenticate_three()
        course = await self.request(self.clients[0], '/api/content', {
            'section':'attendance', 'url':MOODLE+'/course/view.php?id=999'})
        self.assertEqual(course['attendance_view'], 'course')
        self.assertEqual(course['activities'], [])
        self.redirect_report = True
        await self.request(self.clients[0], '/api/content', {
            'section':'attendance', 'url':MOODLE+'/mod/attendance/view.php?id=10'}, status=403)


class AttendanceOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_change_during_collection_discards_response(self):
        session = app.BridgeSession()
        session.identity = {"email":"first@example.test"}
        calls = 0
        async def fake_content(payload, background=False):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"courses":[{"title":"First", "url":MOODLE+"/course/view.php?id=1"}]}
            session.auth_generation += 1
            session.identity = {"email":"second@example.test"}
            return {"activities":[]}
        session.content = fake_content
        with self.assertRaises(HTTPException) as error:
            await session.attendance()
        self.assertEqual(error.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main(verbosity=2)
