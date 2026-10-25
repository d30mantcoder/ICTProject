"""Real HTTP + Chromium tests; upstream Moodle/Microsoft pages are local fixtures."""
import asyncio
import json
import math
import socket
import time
import tempfile
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from playwright.async_api import async_playwright, expect
import app

MOODLE = app.MOODLE
MS = "https://login.microsoftonline.com"


class MultiUserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_dir = tempfile.TemporaryDirectory(prefix="aitu-multi-db-")
        self.previous_db = app.student_db
        self.clock = datetime(2026, 10, 22, 18, 59, 0, tzinfo=timezone.utc)
        app.student_db = app.StudentCache(Path(self.db_dir.name)/"students.sqlite3", clock=lambda:self.clock)
        self.course_version = 1
        self.course_reads = 0
        self.moodle_down = False
        app.pool = app.BrowserPool()
        app.sessions.clear()
        app.sessions_lock = asyncio.Lock()
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.base = "http://127.0.0.1:" + str(self.socket.getsockname()[1])
        self.server = uvicorn.Server(uvicorn.Config(app.app, log_level="error", access_log=False))
        self.task = asyncio.create_task(self.server.serve(sockets=[self.socket]))
        while not self.server.started:
            if self.task.done():
                await self.task
            await asyncio.sleep(.02)
        self.pw = await async_playwright().start()
        self.clients = [await self.pw.request.new_context(base_url=self.base) for _ in range(getattr(self,"user_count",3))]
        self.owned = []
        self.timings = []
        for number, client in enumerate(self.clients, 1):
            response = await client.post("/api/connect", data={})
            self.assertEqual(response.status, 200)
            cookies = (await client.storage_state())["cookies"]
            token = next(c["value"] for c in cookies if c["name"] == "bridge_session")
            session = app.sessions[token]
            session.login_flow.interval = .03
            original = session.ensure_page

            async def get_page(original=original, number=number):
                page = await original()
                if not getattr(page, "_fixture", False):
                    async def route(request):
                        await self.fixture(request, number)
                    await page.context.route("**/*", route)
                    page._fixture = True
                return page
            session.login_flow.get_page = get_page
            self.owned.append(session)

    async def asyncTearDown(self):
        for client in self.clients:
            await client.dispose()
        await self.pw.stop()
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 10)
        self.socket.close()
        app.student_db = self.previous_db
        self.db_dir.cleanup()

    async def fixture(self, route, number):
        url = urlsplit(route.request.url)
        if self.moodle_down and url.netloc == "lms.astanait.edu.kz":
            if self.moodle_down == "server":
                await route.fulfill(status=503, content_type="text/html", body="<h1>Unavailable</h1>")
            else:
                await route.abort("failed")
            return
        if url.path == "/my/courses.php":
            self.course_reads += 1
        if url.path in {"/user/edit.php", "/user/profile.php"}:
            body = f"""<script>window.M={{cfg:{{userId:{number}}}}}</script>
            <div class=usermenu><span class=usertext>User {number}</span></div>
            <input name=email value="{230000+number}@astanait.edu.kz">
            <input name=firstname value="User"><input name=lastname value="{number}">"""
        elif url.path == "/login/index.php":
            body = '<a href="/auth/oidc/">OpenID Connect</a>'
        elif url.path == "/auth/oidc/":
            await route.fulfill(content_type="text/html", body='<script>location.replace("'+MS+'/email")</script>')
            return
        elif url.path == "/email":
            body = f"""<input name=loginfmt type=email><button id=idSIButton9 onclick="location.href=document.querySelector('input').value==='user{number}@example.test'?'/password':'/error'">Next</button>"""
        elif url.path == "/password":
            body = f"""<input name=passwd type=password><button id=idSIButton9 onclick="location.href=document.querySelector('input').value==='fixture{number}'?'/mfa':'/error'">Sign in</button>"""
        elif url.path == "/mfa":
            body = f"""<div id=idRichContext_DisplaySign>{40+number}</div><button id=approve onclick="location.href='{MOODLE}/fixture-complete'">Approve</button>"""
        elif url.path == "/fixture-complete":
            await route.fulfill(content_type="text/html", body=f'<script>document.cookie="owner={number}; Path=/; Secure; SameSite=Lax";location.replace("{MOODLE}/my/")</script>')
            return
        elif url.path == "/error":
            body = "<div id=passwordError>Incorrect credentials</div>"
        else:
            self.assertIn(f"owner={number}", route.request.headers.get("cookie",""))
            day = int(time.time()) // 86400 * 86400
            body = f"""<script>window.M={{cfg:{{userId:{number}}}}};localStorage.owner='{number}'</script>
            <div class=usermenu><span class=usertext>User {number}</span></div>
            <main id=region-main><h1>Courses {number}</h1>
            <div class=coursename><a href="/course/view.php?id={number}">Course {number}{" v2" if self.course_version == 2 else ""}</a></div>
            <div data-region=timeline><div data-region=event-list-content-date data-timestamp="{day}">Today</div>
            <div data-region=event-list-item><div class=timeline-name><small>23:59</small></div>
            <div class=event-name-container><div class=event-name><a href="/mod/assign/view.php?id={number}">Assignment {number}</a></div><small>Assignment · Course {number}</small></div></div></div>
            <table id=overview-grade><tbody><tr><td>Course {number}</td><td>{number*10}</td></tr></tbody></table></main>"""
        await route.fulfill(content_type="text/html; charset=utf-8", body=body)

    async def request(self, client, path, body=None, status=200):
        start = time.perf_counter()
        response = await (client.get(path) if body is None else client.post(path, data=body))
        self.timings.append(time.perf_counter()-start)
        self.assertEqual(response.status, status, await response.text())
        return await response.json()

    async def authenticate_three(self):
        await asyncio.gather(*(self.request(client, "/api/login", {"email":f"user{i}@example.test","password":f"fixture{i}"})
                               for i,client in enumerate(self.clients,1)))
        async with asyncio.timeout(15):
            while any(item.login_flow.status["phase"] != "mfa" for item in self.owned):
                failed = [s for s in self.owned if s.login_flow.status["phase"] == "error"]
                if failed:
                    self.fail(str([(s.login_flow.status, s.page.url if s.page else None) for s in failed]))
                await asyncio.sleep(.05)
        for i,(session,client) in enumerate(zip(self.owned,self.clients),1):
            data = await self.request(client,"/api/login/status")
            self.assertEqual(data["number"],str(40+i))
            self.assertIsNone(session.login_flow.password)
        await self.owned[0].page.locator("#approve").click()
        await asyncio.wait_for(self.owned[0].login_flow.task,5)
        self.assertEqual(self.owned[1].login_flow.status["phase"],"mfa")
        self.assertEqual(self.owned[2].login_flow.status["phase"],"mfa")
        await asyncio.gather(*(s.page.locator("#approve").click() for s in self.owned[1:]))
        await asyncio.gather(*(s.login_flow.task for s in self.owned))
        for s in self.owned:
            self.assertEqual(s.login_flow.status["phase"],"authenticated")

    async def test_three_users_login_load_notifications_and_logout_isolation(self):
        await self.authenticate_three()
        cold_start=time.perf_counter()
        cold=await asyncio.gather(*(self.request(c,"/api/content",{"section":"dashboard","refresh":True}) for c in self.clients))
        cold_seconds=time.perf_counter()-cold_start
        for i,(data,session) in enumerate(zip(cold,self.owned),1):
            self.assertEqual(data["profile"],f"User {i}")
            self.assertEqual(await session.page.evaluate("localStorage.owner"),str(i))
            self.assertEqual((await session.context.cookies(MOODLE))[0]["value"],str(i))
        await self.request(self.clients[0],"/api/notifications/read-all",{})
        for i,c in enumerate(self.clients):
            notices=await self.request(c,"/api/notifications")
            self.assertEqual(notices["unread"],0 if i==0 else 1)
        first_state=await self.request(self.clients[0],"/api/state")
        await self.request(self.clients[1],"/api/window",{"id":first_state["windows"][0]["id"]},404)
        # A slow request or MFA in one context must not block another account.
        async with self.owned[0].lock:
            await asyncio.wait_for(self.request(self.clients[1],"/api/content",{"section":"dashboard"}),2)
        async def workload(i,client):
            for iteration in range(20):
                data=await self.request(client,"/api/content",{"section":"dashboard","refresh":iteration%10==0})
                self.assertEqual(data["profile"],f"User {i}")
                self.assertEqual(data["courses"][0]["title"],f"Course {i}")
                await self.request(client,"/api/state")
                await self.request(client,"/api/login/status")
                await self.request(client,"/api/notifications")
                await self.request(client,"/api/resume",{})
        started=time.perf_counter()
        await asyncio.gather(*(workload(i,c) for i,c in enumerate(self.clients,1)))
        workload_seconds=time.perf_counter()-started
        cookies=(await self.clients[0].storage_state())["cookies"]
        old_cookie=next(c["value"] for c in cookies if c["name"]=="bridge_session")
        await self.request(self.clients[0],"/api/close",{})
        self.assertIsNone(self.owned[0].context)
        forged=await self.pw.request.new_context(base_url=self.base,extra_http_headers={"Cookie":"bridge_session="+old_cookie})
        try: await self.request(forged,"/api/state",status=401)
        finally: await forged.dispose()
        for i,c in enumerate(self.clients[1:],2):
            data=await self.request(c,"/api/content",{"section":"dashboard"})
            self.assertEqual(data["profile"],f"User {i}")
        values=sorted(self.timings)
        report={"users":3,"http_requests":len(values),"workload_requests":300,"errors":0,"p95_seconds":round(values[math.ceil(len(values)*.95)-1],4),
                "max_seconds":round(max(values),4),"cold_three_seconds":round(cold_seconds,4),"workload_seconds":round(workload_seconds,4),
                "scope":"Real HTTP and Chromium; Microsoft/Moodle responses are isolated synthetic fixtures, not university load testing."}
        self.assertLess(max(values),3)
        (Path(__file__).parent/"test-results.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report))


    async def test_mobile_calendar_notifications_map_and_directory(self):
        await self.authenticate_three()
        browser=await self.pw.chromium.launch()
        context=await browser.new_context(viewport={"width":390,"height":844})
        await context.add_cookies((await self.clients[0].storage_state())["cookies"])
        page=await context.new_page()
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        # UI integration uses our real API; only the public external map is intercepted.
        await page.route("https://yuujiso.github.io/aitumap/**",lambda route:route.fulfill(content_type="text/html",body="<main>Public map fixture</main>"))
        try:
            await page.goto(self.base)
            await page.locator(".course").first.wait_for(state="visible")
            await page.locator('.quick-nav [data-feature="calendar"]').click()
            await page.locator(".calendar-grid").wait_for(state="visible")
            self.assertGreater(await page.locator(".calendar-day").count(),27)
            event=self.owned[0].notifications[next(iter(self.owned[0].notifications))]
            from datetime import datetime
            from zoneinfo import ZoneInfo
            day=datetime.fromtimestamp(event["due"],ZoneInfo("Asia/Almaty")).strftime("%Y-%m-%d")
            await page.locator('.calendar-day[aria-label^="'+day+'"]').click()
            self.assertIn("Assignment 1",await page.locator(".calendar-event").inner_text())
            await page.locator('.quick-nav [data-feature="notifications"]').click()
            await page.locator(".notification-card.unread").wait_for(state="visible")
            await page.get_by_role("button",name="Прочитать все",exact=True).click()
            await page.locator(".notification-card.unread").wait_for(state="detached")
            await page.reload()
            await page.locator(".course").first.wait_for(state="visible")
            await page.locator('.quick-nav [data-feature="notifications"]').click()
            await page.locator(".notification-card").wait_for(state="visible")
            self.assertEqual(await page.locator(".notification-card.unread").count(),0)
            self.assertEqual((await self.request(self.clients[1],"/api/notifications"))["unread"],0)
            # Second user has not loaded Timeline: first user's events never appear there.
            await page.locator('.quick-nav [data-feature="map"]').click()
            await page.locator(".campus-map").wait_for(state="visible")
            self.assertEqual(await page.locator(".campus-map").get_attribute("src"),"https://yuujiso.github.io/aitumap/")
            self.assertIn("Данных о занятости",await page.locator("#document").inner_text())
            await page.locator("#menuButton").click()
            await page.locator('#mobileDrawer [data-feature="clubs"]').click()
            await page.locator(".club-card").first.wait_for(state="visible")
            await page.get_by_role("searchbox",name="Поиск клуба").fill("GDSC")
            self.assertEqual(await page.locator(".club-card").count(),1)
            self.assertEqual(await page.locator(".club-card a").get_attribute("href"),"https://www.instagram.com/gdsc_aitu")
            choice = page.get_by_role("checkbox", name="Мой клуб: Google Developer Student Club (GDSC)", exact=True)
            await choice.check()
            await expect(page.locator("#status")).to_have_text("Выбор сохранён")
            self.assertIn("Google Developer Student Club (GDSC)", (await self.request(self.clients[0], "/api/profile"))["clubs"])
            await page.reload()
            await page.locator(".course").first.wait_for(state="visible")
            await page.locator("#menuButton").click()
            await page.locator('#mobileDrawer [data-feature="clubs"]').click()
            await expect(page.get_by_role("checkbox", name="Мой клуб: Google Developer Student Club (GDSC)", exact=True)).to_be_checked()
            await page.get_by_role("checkbox", name="Только мои клубы").check()
            self.assertEqual(await page.locator(".club-card").count(), 1)
            await page.locator("#menuButton").click()
            await page.locator('#mobileDrawer [data-feature="assistant"]').click()
            await page.locator("#assistantQuestion").fill("Карта?")
            with patch.object(app.assistant_service,"generate",return_value="Карта: https://yuujiso.github.io/aitumap/"):
                await page.get_by_role("button",name="Спросить",exact=True).click()
                await expect(page.locator("#assistantReply")).to_have_text("Карта: https://yuujiso.github.io/aitumap/")
            for width,height in [(320,568),(390,844),(430,700),(1440,900)]:
                await page.set_viewport_size({"width":width,"height":height})
                self.assertTrue(await page.evaluate("document.documentElement.scrollWidth<=innerWidth"))
                self.assertTrue(await page.locator("main").evaluate("(e)=>e.scrollWidth<=e.clientWidth"))
            await page.set_viewport_size({"width":390,"height":844})
            await page.locator('.quick-nav [data-feature="calendar"]').click()
            await page.locator(".calendar-grid").wait_for(state="visible")
            await page.screenshot(path=str(Path(__file__).parent/"mobile-preview.png"),full_page=True,animations="disabled")
            self.assertEqual(errors,[])
        finally:
            await browser.close()



    async def wait_refreshes(self):
        await asyncio.gather(*(s.data_refresh_task for s in self.owned if s.data_refresh_task))

    async def test_database_persists_across_relogin_and_isolates_accounts(self):
        await self.request(self.clients[0], "/api/profile", status=409)
        await self.authenticate_three()
        await asyncio.gather(*(self.request(c, "/api/content", {"section":"home"}) for c in self.clients))
        await self.wait_refreshes()
        for i,c in enumerate(self.clients,1):
            profile = await self.request(c, "/api/profile")
            self.assertEqual(profile["email"], f"{230000+i}@astanait.edu.kz")
            self.assertEqual(profile["student_number"], str(230000+i))
            self.assertEqual(profile["first_name"], "User")
            self.assertEqual(profile["last_name"], str(i))
        catalog = await self.request(self.clients[0], "/api/community")
        title = catalog["clubs"][0]["title"]
        await self.request(self.clients[0], "/api/profile/clubs", {"title":title,"selected":True})
        self.assertEqual((await self.request(self.clients[1], "/api/profile"))["clubs"], [])
        await self.request(self.clients[0], "/api/profile/clubs", {"title":"Unknown","selected":True},400)
        await self.owned[0].reset_browser()
        # A new database object simulates process restart; authentication must still be repeated.
        app.student_db = app.StudentCache(app.student_db.path, clock=lambda:self.clock)
        await self.request(self.clients[0], "/api/profile", status=409)
        await self.request(self.clients[0], "/api/login", {"email":"user1@example.test","password":"fixture1"})
        async with asyncio.timeout(10):
            while self.owned[0].login_flow.status["phase"] != "mfa":
                await asyncio.sleep(.03)
        await self.owned[0].page.locator("#approve").click()
        await self.owned[0].login_flow.task
        reads = self.course_reads
        data = await self.request(self.clients[0], "/api/content", {"section":"home"})
        await self.wait_refreshes()
        self.assertTrue(data["cached"])
        self.assertEqual(data["cache_source"], "database")
        self.assertEqual(self.course_reads, reads)
        self.assertEqual((await self.request(self.clients[0], "/api/profile"))["clubs"], [title])
        self.assertNotIn("fixture1", app.student_db.path.read_bytes().decode(errors="ignore"))

    async def test_midnight_refresh_and_offline_user_refreshes_next_login(self):
        await self.authenticate_three()
        await asyncio.gather(*(self.request(c, "/api/content", {"section":"home"}) for c in self.clients))
        await self.wait_refreshes()
        old = await app.student_db.get("230003@astanait.edu.kz",3)
        await self.owned[2].reset_browser()
        self.clock += timedelta(minutes=2)  # 00:01 in Astana, not server-local midnight.
        self.course_version = 2
        await app.refresh_daily()
        for i in (1,2):
            profile = await app.student_db.get(f"{230000+i}@astanait.edu.kz",i)
            self.assertFalse(profile["stale"])
            self.assertIn("v2",profile["courses"][0]["title"])
        offline = await app.student_db.get("230003@astanait.edu.kz",3)
        self.assertTrue(offline["stale"])
        self.assertEqual(offline["refreshed_at"],old["refreshed_at"])
        await self.request(self.clients[2],"/api/login",{"email":"user3@example.test","password":"fixture3"})
        async with asyncio.timeout(10):
            while self.owned[2].login_flow.status["phase"] != "mfa":
                await asyncio.sleep(.03)
        await self.owned[2].page.locator("#approve").click()
        await self.owned[2].login_flow.task
        data=await self.request(self.clients[2],"/api/content",{"section":"home"})
        self.assertIn("v2",data["courses"][0]["title"])
        self.assertFalse(data["cache_stale"])
        await self.wait_refreshes()

    async def test_failed_refresh_preserves_old_snapshot_and_marks_it_stale(self):
        await self.authenticate_three()
        await self.request(self.clients[0], "/api/content", {"section":"home"})
        await self.wait_refreshes()
        before = await self.request(self.clients[0], "/api/profile")
        self.clock += timedelta(days=1)
        for failure in (True, "server"):
            self.moodle_down = failure
            data = await self.request(self.clients[0], "/api/content", {"section":"home"})
            self.assertTrue(data["cache_stale"])
            self.assertIn("Moodle недоступен",data["warnings"][0])
            self.assertEqual((await self.request(self.clients[0], "/api/profile"))["refreshed_at"],before["refreshed_at"])

    async def test_assistant_uses_only_own_sanitized_context_and_reports_failure(self):
        await self.authenticate_three()
        await asyncio.gather(*(self.request(c,"/api/content",{"section":"dashboard"}) for c in self.clients))
        for session in self.owned:
            for _,data in session.cache.values():
                data["grades"]=[{"grade":"secret-grade"}]
                data["text"]="secret-raw-page"
                data["profile"]="secret-profile"
        def fixture_answer(question, context):
            return json.dumps(context)
        with patch.object(app.assistant_service,"generate",side_effect=fixture_answer):
            results=await asyncio.gather(*(self.request(c,"/api/assistant",{"question":"Мои курсы?"}) for c in self.clients))
        for i,result in enumerate(results,1):
            self.assertIn("Course "+str(i),result["answer"])
            self.assertNotIn("secret-",result["answer"])
            for other in set(range(1,4))-{i}:
                self.assertNotIn("Course "+str(other),result["answer"])
        with patch.object(app.assistant_service,"generate",side_effect=HTTPException(503,"Fixture: unavailable")):
            await self.request(self.clients[0],"/api/assistant",{"question":"Тест"},503)
        await self.request(self.clients[0],"/api/assistant",{"question":""},422)

    async def test_expiry_limits_and_validation(self):
        c=self.clients[0]
        invalid=await c.post("/api/login",data={"email":"","password":"never-echo-this"})
        self.assertEqual(invalid.status,422)
        self.assertNotIn("never-echo-this",await invalid.text())
        response=await c.post("/api/connect",data={},headers={"Origin":"https://other.invalid"})
        self.assertEqual(response.status,403)
        await self.request(c,"/api/content",{"url":"https://other.invalid/mod/assign/view.php?id=1"},400)
        self.owned[0].expires=time.monotonic()-1
        await self.request(c,"/api/state",status=401)
        await self.request(c,"/api/connect",{})
        self.assertTrue(self.owned[0].retired)
        self.assertIsNone(self.owned[0].context)
        old_limit=app.MAX_SESSIONS
        app.MAX_SESSIONS=3
        fourth=await self.pw.request.new_context(base_url=self.base)
        try:
            await self.request(fourth,"/api/connect",{},503)
        finally:
            app.MAX_SESSIONS=old_limit
            await fourth.dispose()

if __name__=="__main__":
    unittest.main(verbosity=2)
