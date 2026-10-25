"""Real HTTP/Chromium, synthetic upstreams: durable login and LMS renewal."""
import asyncio
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from playwright.async_api import expect
import app
import test_multiuser as fixtures
from test_multiuser import MOODLE, MS


class ContinuityTests(unittest.IsolatedAsyncioTestCase):
    user_count = 4
    asyncTearDown = fixtures.MultiUserTests.asyncTearDown
    request = fixtures.MultiUserTests.request
    authenticate_three = fixtures.MultiUserTests.authenticate_three
    wait_refreshes = fixtures.MultiUserTests.wait_refreshes

    async def asyncSetUp(self):
        self.expired = set()
        self.sso = {}
        self.sso_requests = 0
        self.password_requests = 0
        self.keepalive_reads = 0
        await fixtures.MultiUserTests.asyncSetUp(self)

    async def fixture(self, route, number):
        url = urlsplit(route.request.url)
        if url.path == "/password":
            self.password_requests += 1
        if url.path == "/my/":
            self.keepalive_reads += 1
        if number in self.expired and url.path == "/auth/oidc/":
            self.sso_requests += 1
            mode = self.sso.get(number, "prompt")
            if mode == "silent":
                self.expired.discard(number)
                await route.fulfill(content_type="text/html", body=f'<script>location.replace("{MOODLE}/fixture-complete")</script>')
                return
            if mode == "kmsi":
                await route.fulfill(content_type="text/html", body=f'<script>location.replace("{MS}/stay")</script>')
                return
            if mode == "wrong":
                await route.fulfill(content_type="text/html", body='<script>window.M={cfg:{userId:999}}</script><main>Wrong account</main>')
                return
        if url.path == "/stay":
            await route.fulfill(content_type="text/html",body=f"""
                <div id=KmsiDescription>Stay signed in?</div>
                <button id=idBtn_Back onclick="location.href='/error'">No</button>
                <button id=idSIButton9 onclick="location.href='{MOODLE}/fixture-complete'">Yes</button>""")
            return
        if (number in self.expired and url.netloc == urlsplit(MOODLE).netloc
                and url.path not in {"/login/index.php","/auth/oidc/","/fixture-complete"}):
            await route.fulfill(content_type="text/html", body='<script>window.M={cfg:{userId:0}}</script><a href="/auth/oidc/">Log in</a>')
            return
        if url.path == "/fixture-complete":
            self.expired.discard(number)
        await fixtures.MultiUserTests.fixture(self,route,number)

    async def prepare_accounts(self):
        await self.authenticate_three()
        await asyncio.gather(*(self.request(c,"/api/content",{"section":"home"}) for c in self.clients))
        await self.wait_refreshes()

    async def test_four_users_restore_cookies_storage_and_app_login_after_restart(self):
        await self.prepare_accounts()
        passwords_before = self.password_requests
        for number,(client,session) in enumerate(zip(self.clients,self.owned),1):
            await session.context.add_cookies([{"name":"ESTSAUTH","value":f"ms-cookie-{number}",
                "domain":"login.microsoftonline.com","path":"/","httpOnly":True,"secure":True}])
            await session.page.evaluate("(value)=>localStorage.setItem('remember-marker',value)",str(number))
            await session.page.evaluate("""async value => {
                const db=await new Promise((resolve,reject)=>{
                    const request=indexedDB.open('remember-test',1);
                    request.onupgradeneeded=()=>request.result.createObjectStore('tokens');
                    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
                });
                await new Promise((resolve,reject)=>{
                    const tx=db.transaction('tokens','readwrite');
                    tx.objectStore('tokens').put(value,'owner');tx.oncomplete=resolve;tx.onerror=reject;
                });db.close();
            }""",str(number))
            cookie=next(c for c in (await client.storage_state())["cookies"] if c["name"]=="bridge_session")
            self.assertGreater(cookie["expires"],time.time()+29*86400)
            session.last_persist_at=0
            await session.persist_session(cookie["value"])
        # Recreate all process-owned objects; retain only SQLite, encryption key and client cookies.
        for session in self.owned:
            await session.reset_browser()
        app.sessions.clear()
        await app.pool.close()
        app.pool=app.BrowserPool()
        app.student_db=app.StudentCache(app.student_db.path,clock=lambda:self.clock)
        restored=[]
        for number,client in enumerate(self.clients,1):
            await self.request(client,"/api/connect",{})
            cookie=next(c for c in (await client.storage_state())["cookies"] if c["name"]=="bridge_session")
            session=app.sessions[cookie["value"]]
            self.assertEqual(session.login_flow.status["phase"],"authenticated")
            page=await session.ensure_page()
            def route_for(owner):
                async def route(request):
                    await self.fixture(request,owner)
                return route
            await session.context.route("**/*",route_for(number))
            await page.goto(MOODLE+"/my/")
            self.assertEqual(await page.evaluate("localStorage.getItem('remember-marker')"),str(number))
            value=await page.evaluate("""async () => {
                const db=await new Promise(resolve=>{const r=indexedDB.open('remember-test',1);r.onsuccess=()=>resolve(r.result)});
                const value=await new Promise(resolve=>{const r=db.transaction('tokens').objectStore('tokens').get('owner');r.onsuccess=()=>resolve(r.result)});
                db.close();return value;
            }""")
            self.assertEqual(value,str(number))
            ms=await session.context.cookies(MS)
            self.assertEqual(next(c["value"] for c in ms if c["name"]=="ESTSAUTH"),f"ms-cookie-{number}")
            data=await self.request(client,"/api/content",{"section":"home","refresh":True})
            self.assertEqual(data["profile"],f"User {number}")
            restored.append(session)
        self.owned=restored
        await self.wait_refreshes()
        self.assertEqual(self.password_requests,passwords_before)
        self.assertEqual(len({id(s.context) for s in self.owned}),4)

    async def test_expired_moodle_is_renewed_silently_for_same_account(self):
        await self.prepare_accounts()
        before=self.password_requests
        for mode in ("silent","kmsi"):
            self.expired.add(1)
            self.sso[1]=mode
            self.owned[0].last_sso_attempt=0
            data=await self.request(self.clients[0],"/api/content",{"section":"home","refresh":True})
            self.assertFalse(data.get("requires_login",False))
            self.assertFalse(data["cached"])
            self.assertEqual(data["profile"],"User 1")
            self.assertEqual(self.password_requests,before)
            self.assertFalse(self.owned[0].moodle_reauth_required)
        self.assertEqual(self.sso_requests,2)

    async def test_mfa_required_keeps_cached_cabinet_open_after_page_reload(self):
        await self.prepare_accounts()
        self.expired.add(1)
        before=await self.request(self.clients[0],"/api/content",{"section":"home"})
        data=await self.request(self.clients[0],"/api/content",{"section":"home","refresh":True})
        self.assertTrue(data["requires_login"])
        self.assertEqual(data["cache_updated_at"],before["cache_updated_at"])
        self.assertEqual((await self.request(self.clients[0],"/api/login/status"))["phase"],"authenticated")
        self.assertEqual((await self.request(self.clients[0],"/api/profile"))["email"],"230001@astanait.edu.kz")
        await self.request(self.clients[0],"/api/content",{"url":MOODLE+"/mod/page/view.php?id=999"},409)
        for _ in range(3):
            await self.request(self.clients[0],"/api/content",{"section":"home","refresh":True})
        self.assertEqual(self.sso_requests,1)  # No automatic repeated MFA requests.
        self.assertFalse((await self.request(self.clients[1],"/api/login/status"))["requires_login"])
        browser=await self.pw.chromium.launch()
        context=await browser.new_context()
        await context.add_cookies((await self.clients[0].storage_state())["cookies"])
        page=await context.new_page()
        try:
            await page.goto(self.base)
            await expect(page.locator(".course").first).to_be_visible()
            await expect(page.locator("#moodleReconnect")).to_be_visible()
            await expect(page.locator("#signIn")).to_be_hidden()
            await page.reload()
            await expect(page.locator(".course").first).to_be_visible()
            await expect(page.locator("#signIn")).to_be_hidden()
            await page.locator("#reconnectMoodle").click()
            await expect(page.locator("#signIn")).to_be_visible()
            await expect(page.locator("#dashboard")).to_be_visible()
        finally:
            await browser.close()

    async def test_silent_login_to_different_account_never_replaces_saved_identity(self):
        await self.prepare_accounts()
        self.expired.add(1)
        self.sso[1]="wrong"
        data=await self.request(self.clients[0],"/api/content",{"section":"home","refresh":True})
        self.assertTrue(data["requires_login"])
        self.assertEqual(data["profile"],"User 1")
        self.assertNotIn("Wrong account",str(data))
        self.assertEqual(self.owned[0].identity["moodle_user_id"],1)

    async def test_keepalive_preserves_foreground_and_logout_revokes_remembered_cookie(self):
        await self.prepare_accounts()
        original=self.owned[0].page
        original_url=original.url
        before=self.keepalive_reads
        self.owned[0].last_moodle_check=time.monotonic()-app.MOODLE_TOUCH_SECONDS-1
        await self.owned[0].check_moodle_connection()
        self.assertGreater(self.keepalive_reads,before)
        self.assertIs(self.owned[0].page,original)
        self.assertEqual(original.url,original_url)
        self.assertEqual(len(self.owned[0].context.pages),1)
        cookie=next(c for c in (await self.clients[0].storage_state())["cookies"] if c["name"]=="bridge_session")
        self.assertIsNotNone(await app.student_db.remembered(cookie["value"]))
        # Logout must revoke even if an encrypted snapshot is being saved concurrently.
        started, release = asyncio.Event(), asyncio.Event()
        original_storage = self.owned[0].context.storage_state
        async def delayed_storage(**kwargs):
            started.set()
            await release.wait()
            return await original_storage(**kwargs)
        self.owned[0].last_persist_at = 0
        with patch.object(self.owned[0].context,"storage_state",delayed_storage):
            save = asyncio.create_task(self.owned[0].persist_session(cookie["value"]))
            await started.wait()
            logout = asyncio.create_task(self.request(self.clients[0],"/api/close",{}))
            async with asyncio.timeout(3):
                while not self.owned[0].retired:
                    await asyncio.sleep(.01)
            release.set()
            await asyncio.gather(save,logout)
        self.assertIsNone(await app.student_db.remembered(cookie["value"]))
        old=await self.pw.request.new_context(base_url=self.base,extra_http_headers={"Cookie":"bridge_session="+cookie["value"]})
        try:
            await self.request(old,"/api/profile",status=401)
        finally:
            await old.dispose()
        self.assertEqual((await self.request(self.clients[1],"/api/profile"))["moodle_user_id"],2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
