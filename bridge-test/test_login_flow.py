"""No real credentials: provider pages are intercepted inside the test browser."""
import asyncio
import os
import time
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from pathlib import Path

from fastapi import HTTPException
from playwright.async_api import async_playwright

from login_flow import LoginFlow
from moodle_reader import content_url, read_content
import app

MOODLE = 'https://lms.astanait.edu.kz'
MS = 'https://login.microsoftonline.com'
DOCUMENT = '''<script>window.M={cfg:{userid:17}}</script>
<div class=usermenu><span class=usertext>Test Student</span></div>
<main id=region-main><h1>Мои курсы</h1><p>Дедлайн: пятница</p>
<a href="/course/view.php?id=12">ICT</a><a href="/course/view.php?id=12">ICT duplicate</a>
<a href="/mod/assign/view.php?id=9">Assignment 3</a>
<a href="https://outside.invalid/course/view.php?id=1">External</a>
<a href="/login/logout.php?sesskey=secret">Logout</a>
<table><tr><td>Работа</td><td>Оценка</td></tr><tr><td>Quiz</td><td>95</td></tr></table></main>'''


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.pool = app.BrowserPool()
        self.session = app.BridgeSession()
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch()
        self.context = await self.browser.new_context()
        await self.context.add_init_script(path=str(Path(__file__).with_name('password_login.js')))
        self.page = await self.context.new_page()
        self.untrusted = False
        self.provider = MS
        self.passkey = False
        self.password_available = True
        self.modern_submit = False
        self.password_delay = False
        self.password_remount = False
        self.native_passkey = False
        self.password_tile = False
        self.generic_mfa = False
        self.passkey_back = False
        self.passkey_enrollment = False
        self.enrollment_html = None
        self.password_keeps_remounting = False
        self.mfa_choices = None
        self.mfa_choice_stays = False
        await self.context.route('**/*', self.route)
        async def get_page():
            return self.page
        self.flow = LoginFlow(get_page, asyncio.Lock(), MOODLE, interval=.03)

    async def asyncTearDown(self):
        await self.flow.cancel()
        await self.browser.close()
        await self.pw.stop()
        await self.session.reset_browser()
        await app.pool.close()

    async def route(self, route):
        url = urlsplit(route.request.url)
        if url.netloc == 'lms.astanait.edu.kz':
            if url.path == '/login/index.php':
                html = '<a href="/auth/oidc/">Log in with OpenID Connect</a>'
            elif url.path == '/auth/oidc/':
                # A new navigation keeps the next provider page inside the fixture router.
                target = ('https://unexpected.invalid' if self.untrusted else self.provider) + '/email'
                await route.fulfill(content_type='text/html', body=f'<script>location.replace("{target}")</script>')
                return
            else:
                html = DOCUMENT
        elif url.path == '/email':
            next_page = '/passkey' if self.passkey else '/password'
            button_id = '' if self.modern_submit else 'id=idSIButton9'
            html = f'''<input name=loginfmt type=email><button {button_id}
            onclick="if(document.querySelector('input').value==='student@example.test')location.href='{next_page}'">Next</button>'''
        elif url.path == '/passkey':
            html = '''<h1>Face, fingerprint, PIN or security key</h1>
            <input type=password name=pin autocomplete=one-time-code>
            <a href="/methods">Other ways to sign in</a>'''
            if self.native_passkey:
                html = '''<h1>Sign in with a passkey</h1><p>Waiting for browser</p>
                <script>navigator.credentials.get({publicKey:{challenge:new Uint8Array(32),timeout:60000}})
                .catch(e=>{if(e.name==='NotAllowedError')location.href='/methods'});</script>'''
                if self.passkey_back:
                    html = html.replace("location.href='/methods'", "location.href='/passkey-error'")
        elif url.path == '/passkey-error':
            html = '''<h1>Couldn't sign in with a passkey</h1><button onclick="location.href='/methods'">Back</button>'''
        elif url.path == '/enroll':
            html = '<h1>Create a passkey</h1><button onclick="location.href=\'' + MOODLE + '/my/\'">Skip for now</button>'
            if self.enrollment_html is not None:
                html = self.enrollment_html
        elif url.path == '/methods':
            html = '''<h1>Choose a way to sign in</h1><button>Face, fingerprint, PIN or security key</button>'''
            if self.password_available:
                html += ('<div tabindex="0" onclick="location.href=\'/password\'"><span>Use your password instead</span></div>'
                         if self.password_tile else '<button onclick="location.href=\'/password\'">Use my password</button>')
        elif url.path == '/password':
            button_id = '' if self.modern_submit else 'id=idSIButton9'
            html = f'''<input name=passwd type=password><button {button_id}
            onclick="location.href=document.querySelector('input').value==='fixture-password'?'/mfa':'/error'">Sign in</button>'''
            if self.password_delay:
                html += '''<script>const b=document.querySelector('button');b.remove();
                setTimeout(()=>document.body.append(b),800)</script>'''
            if self.password_remount:
                html += '''<script>const b=document.querySelector('button'),submit=b.onclick;
                b.onclick=()=>{if(!window.remounted){window.remounted=true;
                document.querySelector('input').outerHTML='<input name=passwd type=password>';
                }else submit()};</script>'''
                if self.password_keeps_remounting:
                    html = html.replace('if(!window.remounted)', 'if(true)')
        elif url.path == '/mfa':
            html = '<div id=idRichContext_DisplaySign>42</div><button id=approve onclick="location.href=\'' + MOODLE + '/my/\'">Approve</button>'
            if self.passkey_enrollment:
                html = html.replace(MOODLE + '/my/', '/enroll')
            if self.generic_mfa:
                html = '''<div id=idDiv_SAOTCAS_Description>Approve the sign-in on your phone</div>
                <a href="/methods">Other ways to sign in</a>'''
            if self.mfa_choices is not None:
                html = '<h1>Verify your identity</h1><div id=idDiv_SAOTCS_Proofs>'
                for label, approval in self.mfa_choices:
                    action = ("window.pushCount=(window.pushCount||0)+1" if self.mfa_choice_stays
                              else "location.href='/approval'") if approval else "location.href='/error'"
                    html += f'<div tabindex="0" onclick="{action}"><span>{label}</span></div>'
                html += '</div>'
        elif url.path == '/approval':
            html = '<div id=idRichContext_DisplaySign>42</div><button id=approve onclick="location.href=\'' + MOODLE + '/my/\'">Approve</button>'
        else:
            html = '<div id=passwordError>Incorrect password</div>'
        await route.fulfill(content_type='text/html; charset=utf-8', body=html)

    async def wait_phase(self, phase):
        async with asyncio.timeout(12):
            while self.flow.status['phase'] != phase:
                if self.flow.task.done():
                    self.fail(f"Stopped before {phase}: {self.flow.status}")
                await asyncio.sleep(.03)

    async def test_email_password_mfa_and_authenticated_data(self):
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')
        self.assertIsNone(self.flow.password)
        self.assertNotIn('fixture-password', str(self.flow.status))
        with self.assertRaises(HTTPException) as duplicate:
            self.flow.start('student@example.test', 'fixture-password')
        self.assertEqual(duplicate.exception.status_code, 409)
        await self.page.locator('#approve').click()
        await asyncio.wait_for(self.flow.task, 8)
        self.assertEqual(self.flow.status['phase'], 'authenticated')
        self.assertIsNone(self.flow.email)
        data = await read_content(self.page, MOODLE)
        self.assertEqual(data['profile'], 'Test Student')
        self.assertEqual(len(data['courses']), 1)
        self.assertEqual(data['courses'][0]['title'], 'ICT')
        self.assertEqual(data['activities'][0]['title'], 'Assignment 3')
        self.assertEqual(data['tables'][0][1][1], '95')
        self.assertNotIn('secret', str(data['courses'] + data['activities']))

    async def test_wrong_password_stops_without_retry(self):
        self.flow.start('student@example.test', 'wrong-password')
        await asyncio.wait_for(self.flow.task, 12)
        self.assertEqual(self.flow.status['phase'], 'error')
        self.assertIsNone(self.flow.password)
        self.assertIsNone(self.flow.email)

    async def test_delayed_submit_does_not_lose_password(self):
        self.password_delay = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')
        self.assertIsNone(self.flow.password)

    async def test_replaced_password_field_is_filled_again(self):
        self.password_remount = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')
        self.assertIsNone(self.flow.password)

    async def test_native_passkey_is_declined_before_os_dialog(self):
        self.passkey = self.native_passkey = self.password_tile = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')
        self.assertIsNone(self.flow.password)

    async def test_generic_mfa_does_not_switch_back_to_password(self):
        self.generic_mfa = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        await asyncio.sleep(1.2)
        self.assertEqual(urlsplit(self.page.url).path, '/mfa')
        self.assertIsNone(self.flow.password)

    async def test_verify_identity_selects_authenticator_in_any_position(self):
        for position in (1, 0, 2):
            with self.subTest(position=position):
                self.mfa_choices = [('Use a verification code', False), ('Text my phone', False)]
                self.mfa_choices.insert(position, ('Approve a request on my Microsoft Authenticator app', True))
                self.flow.start('student@example.test', 'fixture-password')
                await self.page.wait_for_url(MS + '/approval', timeout=10000)
                async with asyncio.timeout(5):
                    while self.flow.status['number'] != '42':
                        await asyncio.sleep(.03)
                self.assertIsNone(self.flow.password)
                self.assertTrue(self.flow.running)
                # Selection alone must not approve MFA or complete login.
                self.assertEqual(self.flow.status['phase'], 'mfa')
                await self.page.locator('#approve').click()
                await asyncio.wait_for(self.flow.task, 8)
                self.assertEqual(self.flow.status['phase'], 'authenticated')

    async def test_authenticator_choice_is_not_clicked_again_while_waiting(self):
        self.mfa_choices = [('Approve a request on my Microsoft Authenticator', True)]
        self.mfa_choice_stays = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        await asyncio.sleep(.8)
        self.assertEqual(await self.page.evaluate('window.pushCount'), 1)
        self.assertTrue(self.flow.running)

    async def test_verify_identity_without_push_does_not_choose_second_option(self):
        self.mfa_choices = [('Use a verification code', False), ('Text my phone', False)]
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        await asyncio.sleep(.5)
        self.assertEqual(urlsplit(self.page.url).path, '/mfa')
        self.assertTrue(self.flow.running)

    async def test_russian_authenticator_choice_is_supported(self):
        self.mfa_choices = [('Подтвердить запрос в приложении Microsoft Authenticator', True)]
        self.flow.start('student@example.test', 'fixture-password')
        await self.page.wait_for_url(MS + '/approval', timeout=10000)
        async with asyncio.timeout(5):
            while self.flow.status['number'] != '42':
                await asyncio.sleep(.03)
        self.assertIsNone(self.flow.password)

    async def test_declined_passkey_back_button_returns_to_password(self):
        self.passkey = self.native_passkey = self.passkey_back = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')

    async def test_optional_passkey_enrollment_is_skipped_after_mfa(self):
        self.passkey_enrollment = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        await self.page.locator('#approve').click()
        await asyncio.wait_for(self.flow.task, 8)
        self.assertEqual(self.flow.status['phase'], 'authenticated')
        self.assertIsNone(self.flow.password)


    async def test_keep_account_secure_not_now_completes_login(self):
        for control in ('button', 'link', 'delayed'):
            with self.subTest(control=control):
                self.passkey_enrollment = True
                # An earlier passkey dismissal must not prevent this separate prompt.
                self.passkey = self.native_passkey = self.passkey_back = True
                skip = (f'<a href="{MOODLE}/my/">Not nOw</a>' if control == 'link'
                        else f'<button id=skip onclick="location.href=&quot;{MOODLE}/my/&quot;">Not nOw</button>')
                if control == 'delayed':
                    skip += """<script>const b=document.querySelector('#skip');b.disabled=true;
                    setTimeout(()=>b.disabled=false,700)</script>"""
                self.enrollment_html = (
                    "<h1>Let’s keep your account secure</h1>"
                    '<button onclick="location.href=&quot;/error&quot;">Next</button>' + skip)
                self.flow.start('student@example.test', 'fixture-password')
                await self.wait_phase('mfa')
                await self.page.locator('#approve').click()
                await asyncio.wait_for(self.flow.task, 8)
                self.assertEqual(self.flow.status['phase'], 'authenticated')
                self.assertIsNone(self.flow.password)

    async def security_prompt(self, controls, origin=MS):
        await self.page.goto(origin + '/enroll')
        await self.page.set_content("<h1>Let's keep your account secure</h1>" + controls)
        return {'email': True, 'password': True, 'passkey_dismissed': True}

    async def test_security_prompt_without_skip_waits_for_user(self):
        sent = await self.security_prompt('<button onclick="window.clicked=true">Next</button>')
        self.assertFalse(await self.flow.step(self.page, sent))
        self.assertEqual(self.flow.status['phase'], 'action')
        self.assertIsNone(await self.page.evaluate('window.clicked'))

    async def test_security_prompt_waits_for_delayed_skip(self):
        sent = await self.security_prompt('')
        await self.flow.step(self.page, sent)
        await self.page.evaluate("""() => {
            const b=document.createElement('button');b.textContent='Not now';
            b.onclick=()=>window.clicked=true;document.body.append(b);
        }""")
        await self.flow.step(self.page, sent)
        self.assertTrue(await self.page.evaluate('window.clicked'))

    async def test_security_prompt_disabled_skip_waits_without_clicking(self):
        sent = await self.security_prompt('<button disabled onclick="window.clicked=true">Not now</button>')
        await asyncio.wait_for(self.flow.step(self.page, sent), 1)
        self.assertEqual(self.flow.status['phase'], 'waiting')
        self.assertIsNone(await self.page.evaluate('window.clicked'))

    async def test_security_prompt_skip_is_not_repeated(self):
        sent = await self.security_prompt(
            '<button onclick="window.clicks=(window.clicks||0)+1">Not now</button>')
        for _ in range(3):
            await self.flow.step(self.page, sent)
        self.assertEqual(await self.page.evaluate('window.clicks'), 1)

    async def test_security_prompt_on_untrusted_origin_is_not_clicked(self):
        for origin in ('https://login.microsoftonline.com.unexpected.invalid',
                       'http://login.microsoftonline.com'):
            sent = await self.security_prompt(
                '<button onclick="window.clicked=true">Not now</button>', origin)
            self.assertTrue(await self.flow.step(self.page, sent))
            self.assertEqual(self.flow.status['phase'], 'error')
            self.assertIsNone(await self.page.evaluate('window.clicked'))


    async def test_stay_signed_in_accepts_yes_once_and_never_no(self):
        await self.page.goto(MS + '/email')
        await self.page.set_content("""<div id=KmsiDescription>Stay signed in?</div>
            <button id=idBtn_Back onclick="window.choice='no'">No</button>
            <button id=idSIButton9 onclick="window.choice='yes';window.count=(window.count||0)+1">Yes</button>""")
        self.flow.password = "fixture-password"
        sent = {"email":True,"password":True}
        for _ in range(2):
            self.assertFalse(await self.flow.step(self.page,sent))
        self.assertEqual(await self.page.evaluate("window.choice"),"yes")
        self.assertEqual(await self.page.evaluate("window.count"),1)
        self.assertIsNone(self.flow.password)

    async def test_repeated_field_resets_stop_instead_of_looping(self):
        self.password_remount = self.password_keeps_remounting = True
        self.flow.start('student@example.test', 'fixture-password')
        await asyncio.wait_for(self.flow.task, 12)
        self.assertEqual(self.flow.status['phase'], 'error')
        self.assertIsNone(self.flow.password)

    async def test_passkey_preference_is_scoped_to_exact_microsoft_origins(self):
        for origin, expected in [(MS, True), ('https://login.microsoft.com', True),
                                 ('https://login.live.com', True), (MOODLE, False),
                                 ('https://login.microsoftonline.com.unexpected.invalid', False),
                                 ('http://login.microsoftonline.com', False)]:
            await self.page.goto(origin + '/email')
            installed = await self.page.evaluate("Object.hasOwn(navigator.credentials || {}, 'get')")
            self.assertEqual(installed, expected, origin)

    async def test_passkey_creation_is_declined_and_other_credentials_unchanged(self):
        await self.page.goto(MS + '/email')
        result = await self.page.evaluate('''async () => {
            const error = async fn => {try {await fn(); return 'resolved'} catch(e) {return e.name}};
            return {
                create: await error(()=>navigator.credentials.create({publicKey:{}})),
                get: await error(()=>navigator.credentials.get({publicKey:{}})),
                plain: await error(()=>navigator.credentials.get({})),
                native: await error(()=>CredentialsContainer.prototype.get.call(navigator.credentials,{})),
            };
        }''')
        self.assertEqual(result['create'], 'NotAllowedError')
        self.assertEqual(result['get'], 'NotAllowedError')
        self.assertEqual(result['plain'], result['native'])

    async def test_microsoft_com_passkey_picker_switches_to_password_and_mfa(self):
        self.provider = 'https://login.microsoft.com'
        self.passkey = self.modern_submit = True
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        self.assertEqual(self.flow.status['number'], '42')
        self.assertEqual(urlsplit(self.page.url).netloc, 'login.microsoft.com')
        await self.page.locator('#approve').click()
        await asyncio.wait_for(self.flow.task, 8)
        self.assertEqual(self.flow.status['phase'], 'authenticated')

    async def test_passkey_without_password_option_waits_for_user(self):
        self.provider = 'https://login.microsoft.com'
        self.passkey = True
        self.password_available = False
        self.flow.start('student@example.test', 'fixture-password')
        await self.page.wait_for_url('https://login.microsoft.com/methods', timeout=10000)
        await self.wait_phase('action')
        self.assertTrue(self.flow.running)
        self.assertIn('ключ', self.flow.status['message'])
        self.assertEqual(urlsplit(self.page.url).path, '/methods')

    async def test_popup_selection_blank_loading_and_return_to_opener(self):
        previous = app.pool.browser, self.session.context, self.session.page
        app.pool.browser, self.session.context, self.session.page = self.browser, self.context, self.page
        self.context.on('page', self.session.select_page)
        self.session.select_page(self.page)
        try:
            await self.page.goto(MS + '/email')
            async with self.page.expect_popup() as event:
                await self.page.evaluate("window.open('about:blank')")
            popup = await event.value
            self.assertIs(await self.session.ensure_page(), popup)
            sent = {'email': True, 'password': True}
            self.assertFalse(await self.flow.step(popup, sent))
            self.assertEqual(self.flow.status['phase'], 'waiting')
            sent['blank_since'] = time.monotonic() - 11
            await self.flow.step(popup, sent)
            self.assertEqual(self.flow.status['phase'], 'action')
            await popup.goto(MS + '/mfa?code=fixture-secret#token')
            await self.flow.step(popup, sent)
            self.assertEqual(self.flow.status['number'], '42')
            state = await self.session.state()
            self.assertEqual(len(state['windows']), 2)
            self.assertNotIn('fixture-secret', str(state))
            self.assertNotIn('#token', str(state))
            opener_id, popup_id = [w['id'] for w in state['windows']]
            await self.session.choose_window(app.WindowChoice(id=opener_id))
            self.assertIs(await self.session.ensure_page(), self.page)
            await self.session.choose_window(app.WindowChoice(id=popup_id))
            self.assertIs(await self.session.ensure_page(), popup)
            await popup.close()
            state = await self.session.state()
            self.assertEqual(len(state['windows']), 1)
            self.assertTrue(state['windows'][0]['selected'])
            with self.assertRaises(HTTPException) as failure:
                await self.session.choose_window(app.WindowChoice(id=popup_id))
            self.assertEqual(failure.exception.status_code, 404)
        finally:
            app.pool.browser, self.session.context, self.session.page = previous
            self.session.window_ids.clear()

    def test_visible_browser_on_desktop_and_explicit_headless_override(self):
        for env, expected in [({}, True), ({'DISPLAY': ':0'}, True),
                              ({'WAYLAND_DISPLAY': 'wayland-0'}, True),
                              ({'DISPLAY': ':0', 'BRIDGE_HEADLESS': '1'}, True),
                              ({'BRIDGE_HEADLESS': '0'}, False)]:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                self.assertEqual(app.headless_mode(), expected)

    async def test_similarly_named_microsoft_domain_is_not_trusted(self):
        self.provider = 'https://login.microsoft.com.attacker.invalid'
        self.flow.start('student@example.test', 'fixture-password')
        await asyncio.wait_for(self.flow.task, 8)
        self.assertEqual(self.flow.status['phase'], 'error')
        self.assertEqual(await self.page.locator('input').input_value(), '')

    async def test_cancel_while_waiting_for_mfa(self):
        self.flow.start('student@example.test', 'fixture-password')
        await self.wait_phase('mfa')
        await self.flow.cancel()
        self.assertFalse(self.flow.running)
        self.assertEqual(self.flow.status['phase'], 'idle')
        self.assertIsNone(self.flow.password)
        self.assertIsNone(self.flow.status['number'])

    async def test_mfa_completion_while_reading_number_does_not_stall(self):
        original_visible = self.flow.visible
        redirected = False
        async def visible(page, selector):
            nonlocal redirected
            locator = await original_visible(page, selector)
            if locator and 'DisplaySign' in selector and not redirected:
                redirected = True
                await page.goto(MOODLE + '/my/')
            return locator
        self.flow.visible = visible
        self.flow.start('student@example.test', 'fixture-password')
        await asyncio.wait_for(self.flow.task, 7)
        self.assertTrue(redirected)
        self.assertEqual(self.flow.status['phase'], 'authenticated')

    async def test_does_not_fill_credentials_on_untrusted_host(self):
        self.untrusted = True
        self.flow.start('student@example.test', 'fixture-password')
        await asyncio.wait_for(self.flow.task, 12)
        self.assertEqual(self.flow.status['phase'], 'error')
        self.assertEqual(await self.page.locator('input').input_value(), '')
        self.assertIsNone(self.flow.password)

    async def test_reader_requires_authenticated_moodle(self):
        await self.page.goto(MOODLE + '/login/index.php')
        with self.assertRaises(HTTPException) as failure:
            await read_content(self.page, MOODLE)
        self.assertEqual(failure.exception.status_code, 409)
        for url in ['https://outside.invalid/course/view.php?id=1', MOODLE + '/login/logout.php', MOODLE + '/course/delete.php?id=1']:
            with self.assertRaises(HTTPException):
                content_url(url, MOODLE)
        self.assertEqual(content_url(MOODLE + '/course/view.php?id=12&sesskey=secret', MOODLE), MOODLE + '/course/view.php?id=12')

    async def test_backend_login_content_and_close_use_same_session(self):
        original_flow = self.session.login_flow
        async def get_app_page():
            page = await self.session.ensure_page()
            if not getattr(page, '_fixture_installed', False):
                await page.context.route('**/*', self.route)
                page._fixture_installed = True
            return page
        self.session.login_flow = self.flow = LoginFlow(get_app_page, self.session.lock, MOODLE, interval=.03)
        try:
            started = await self.session.login(app.LoginRequest(email='student@example.test', password='fixture-password'))
            self.assertEqual(started['phase'], 'opening')
            await self.wait_phase('mfa')
            self.assertEqual((await self.session.login_status())['number'], '42')
            await self.session.page.locator('#approve').click()
            await asyncio.wait_for(self.flow.task, 8)
            data = await self.session.content(app.ContentRequest(section='courses'))
            self.assertEqual(data['courses'][0]['title'], 'ICT')
            self.assertEqual(data['tables'][0][1][1], '95')
            # Another attempt must destroy the previous account's browser context.
            previous = self.session.context
            await self.session.login(app.LoginRequest(email='student@example.test', password='fixture-password'))
            await self.wait_phase('mfa')
            self.assertIsNot(self.session.context, previous)
            await self.session.close()
            self.assertFalse(self.flow.running)
            self.assertFalse((await self.session.state())['active'])
            self.assertEqual((await self.session.login_status())['phase'], 'idle')
        finally:
            await self.session.close()
            if app.pool.playwright:
                await app.pool.playwright.stop()
            app.pool.browser = self.session.context = self.session.page = app.pool.playwright = None
            self.session.login_flow = original_flow


if __name__ == '__main__':
    unittest.main(verbosity=2)
