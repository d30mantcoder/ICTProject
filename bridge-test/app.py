"""Multi-user AITU bridge with private daily SQLite snapshots."""
import asyncio
import os
import secrets
import shlex
import sys
import time
import hashlib
import json
import sqlite3
import logging
from collections import OrderedDict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, SecretStr
from playwright.async_api import async_playwright, Error as BrowserError, TimeoutError as BrowserTimeout
from login_flow import LoginFlow, MICROSOFT_HOSTS
import assistant_service
from attendance_reader import report_events
from student_cache import StudentCache, ASTANA, next_midnight, utc_now
from identity_reader import read_identity
from moodle_reader import content_url, read_content, prepare_timeline, is_authenticated

ROOT = Path(__file__).resolve().parent
MOODLE = "https://lms.astanait.edu.kz"
PORT = int(os.environ.get("BRIDGE_PORT", "1740"))
student_db = StudentCache(os.environ.get("BRIDGE_DB_PATH", str(ROOT / "data" / "bridge.sqlite3")))
SESSION_SECONDS = 8 * 3600
REMEMBER_SECONDS = 30 * 86400
MOODLE_TOUCH_SECONDS = 240
MAX_SESSIONS = max(3, int(os.environ.get("BRIDGE_MAX_SESSIONS", "12")))

def headless_mode():
    # Shared server defaults to headless; opt in to a local window explicitly.
    return os.environ.get("BRIDGE_HEADLESS", "1") != "0"

class BrowserPool:
    def __init__(self):
        self.playwright = self.browser = None
        self.lock = asyncio.Lock()

    async def get(self):
        async with self.lock:
            if self.browser is None or not self.browser.is_connected():
                if self.playwright is None:
                    self.playwright = await async_playwright().start()
                try:
                    self.browser = await self.playwright.chromium.launch(headless=headless_mode())
                except BrowserError as error:
                    if "Executable doesn't exist" in str(error):
                        command = shlex.join([sys.executable, "-m", "playwright", "install", "chromium"])
                        raise HTTPException(503, "Chromium не установлен для пользователя сервера. Выполните: " + command) from error
                    raise HTTPException(503, "Chromium не запустился. Проверьте системные зависимости.") from error
            return self.browser

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = self.playwright = None

pool = BrowserPool()
sessions = {}
sessions_lock = asyncio.Lock()


PAGES = {'attendance': MOODLE + '/my/courses.php', 'login': MOODLE + '/login/index.php', 'dashboard': MOODLE + '/my/', 'home': MOODLE + '/', 'courses': MOODLE + '/my/courses.php', 'calendar': MOODLE + '/calendar/view.php?view=upcoming', 'grades': MOODLE + '/grade/report/overview/index.php', 'demo': f'http://127.0.0.1:{PORT}/demo'}

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)

class ContentRequest(BaseModel):
    refresh: bool = False
    section: str = 'courses'
    url: str | None = Field(default=None, max_length=2000)

def public_url(url):
    parts = urlsplit(url)
    return f'{parts.scheme}://{parts.netloc}{parts.path}'

class WindowChoice(BaseModel):
    id: str = Field(max_length=32)

class Navigate(BaseModel):
    destination: str

class Action(BaseModel):
    kind: str
    x: float = Field(default=0, ge=0, le=1100)
    y: float = Field(default=0, ge=0, le=800)
    text: str = Field(default='', max_length=2000)
    key: str = ''
    delta: int = Field(default=500, ge=-2000, le=2000)

class BridgeSession:
    def __init__(self):
        self.expires = time.monotonic() + SESSION_SECONDS
        self.lock = asyncio.Lock()
        self.lifecycle_lock = asyncio.Lock()
        self.attendance_lock = asyncio.Lock()
        self.auth_generation = 0
        self.context = self.page = None
        self.window_ids = {}
        self.session_saved = False
        self.session_notice = ""
        self.notifications = {}
        self.login_flow = LoginFlow(self.current_page, self.lock, MOODLE)
        self.requests = 0
        self.retired = False
        self.cache = OrderedDict()
        self.login_attempts = deque(maxlen=5)
        self.chat_lock = asyncio.Lock()
        self.identity = None
        self.identity_retry_at = 0
        self.data_refresh_task = None
        self.bootstrap_started = False
        self.pending_storage = None
        self.remembered_until = None
        self.last_persist_at = 0
        self.last_moodle_check = 0
        self.last_sso_attempt = 0
        self.moodle_reauth_required = False
        self.last_seen = time.monotonic()
        self.api_token = None
        self.persistence_ready = asyncio.Event()

    def connection_status(self):
        return {"requires_login": self.moodle_reauth_required,
                "remembered_until": self.remembered_until,
                "email": self.identity["email"] if self.identity else None}

    def mark_moodle_expired(self):
        self.session_saved = False
        self.moodle_reauth_required = True
        self.session_notice = "Подключение к LMS истекло. Сохранённые данные доступны; для обновления восстанови подключение."
        if self.identity:
            self.login_flow.update("authenticated", "Кабинет открыт по сохранённой сессии.")
        else:
            self.login_flow.update("idle", "Войди в Microsoft снова.")

    async def persist_session(self, token):
        if self.retired or not self.identity or self.login_flow.running or self.moodle_reauth_required:
            return
        if self.lock.locked() or time.monotonic() - self.last_persist_at < 60:
            return
        async with self.lock:
            if not self.context or self.retired or not self.identity:
                return
            identity = dict(self.identity)
            try:
                async with asyncio.timeout(5):
                    state = await self.context.storage_state(indexed_db=True)
                if self.retired or self.identity != identity or self.login_flow.status["phase"] != "authenticated":
                    return
                # Persist authentication origins only, never an arbitrary browsing history.
                domains = {"lms.astanait.edu.kz", "microsoftonline.com", "microsoft.com", "live.com"}
                state["cookies"] = [c for c in state["cookies"] if any(
                    c["domain"].lstrip(".") == d or c["domain"].lstrip(".").endswith("."+d) for d in domains)]
                state["origins"] = [o for o in state["origins"]
                    if urlsplit(o["origin"]).scheme == "https" and
                    urlsplit(o["origin"]).netloc in MICROSOFT_HOSTS | {"lms.astanait.edu.kz"}]
                expiry = self.remembered_until or student_db.clock().timestamp() + REMEMBER_SECONDS
                if await student_db.remember(token, identity, state, expiry):
                    self.remembered_until = expiry
                    self.expires = time.monotonic() + max(0, expiry-student_db.clock().timestamp())
                    self.last_persist_at = time.monotonic()
            except (BrowserError, TimeoutError, OSError, sqlite3.Error, ValueError):
                logging.getLogger(__name__).warning("Remembered login could not be saved")
            finally:
                self.persistence_ready.set()

    async def ensure_page(self):
        if self.retired or self.expires <= time.monotonic():
            raise HTTPException(401, 'Сессия истекла. Войди снова.')
        browser = await pool.get()
        if self.context is None or self.context not in browser.contexts:
            restored = self.pending_storage is not None
            self.context = await browser.new_context(viewport={"width":1100,"height":800},
                                                     storage_state=self.pending_storage)
            self.pending_storage = None
            await self.context.add_init_script(path=str(ROOT / "password_login.js"))
            self.context.set_default_timeout(15000)
            self.context.on("page", self.select_page)
            self.page = None
            self.window_ids.clear()
            self.session_saved = False
            if self.identity:
                if not restored:
                    self.mark_moodle_expired()
            else:
                self.cache.clear()
                self.notifications.clear()
                if self.login_flow.status["phase"] == "authenticated":
                    self.login_flow.update("idle", "Браузер перезапущен. Войди в Microsoft снова.")
        if self.page is None or self.page.is_closed():
            remaining = [item for item in self.context.pages if not item.is_closed()]
            self.page = remaining[-1] if remaining else await self.context.new_page()
        return self.page

    async def remember_session(self):
        # The live context is isolated; encrypted snapshots are persisted separately.
        self.session_saved = True

    async def resume(self):
        return {**self.login_flow.status, **self.connection_status(), "expires_in": max(0, int(self.expires-time.monotonic()))}

    async def reset_browser(self):
        if self.data_refresh_task and self.data_refresh_task is not asyncio.current_task():
            self.data_refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.data_refresh_task
        self.data_refresh_task = None
        await self.login_flow.cancel()
        async with self.lock:
            self.auth_generation += 1
            self.bootstrap_started = False
            self.identity = None
            self.identity_retry_at = 0
            self.pending_storage = None
            self.remembered_until = None
            self.last_persist_at = self.last_sso_attempt = self.last_moodle_check = 0
            self.moodle_reauth_required = False
            self.persistence_ready.clear()
            if self.context:
                with suppress(BrowserError):
                    await self.context.close()
            self.context = self.page = None
            self.window_ids.clear()
            self.notifications.clear()
            self.cache.clear()
            self.session_saved = False
            self.session_notice = ""


    def select_page(self, opened):
        self.window_ids.setdefault(opened, secrets.token_hex(8))
        self.page = opened

    async def current_page(self):
        return await self.ensure_page()

    async def login(self, payload: LoginRequest):
        if not payload.password.get_secret_value() or '@' not in payload.email:
            raise HTTPException(400, 'Введи почту и пароль Microsoft.')
        async with self.lifecycle_lock:
            now = time.monotonic()
            if len(self.login_attempts) == 5 and now - self.login_attempts[0] < 600:
                raise HTTPException(429, "Слишком много попыток входа. Подожди 10 минут.", headers={"Retry-After":"600"})
            if self.retired:
                raise HTTPException(401, "Сессия закрыта.")
            if self.login_flow.running:
                raise HTTPException(409, 'Вход уже выполняется. Подтверди его или нажми «Отменить».')
            await self.reset_browser()
            self.login_attempts.append(now)
            self.login_flow.start(payload.email.strip(), payload.password.get_secret_value())
        return dict(self.login_flow.status)

    async def login_status(self):
        if not self.login_flow.running and self.login_flow.status['phase'] != 'authenticated':
            async with self.lock:
                if self.page and (not self.page.is_closed()) and (urlsplit(self.page.url).netloc == urlsplit(MOODLE).netloc):
                    try:
                        if await is_authenticated(self.page, MOODLE):
                            self.login_flow.update('authenticated', 'Вход выполнен.')
                    except BrowserError:
                        pass
        if self.login_flow.status['phase'] == 'authenticated' and (not self.session_saved) and self.context and not self.moodle_reauth_required:
            async with self.lock:
                if self.login_flow.status['phase'] == 'authenticated' and self.context:
                    await self.remember_session()
        return {**self.login_flow.status, **self.connection_status(), 'remembered': self.session_saved, 'notice': self.session_notice}

    async def verified_identity(self, active, force=False):
        if self.login_flow.status["phase"] != "authenticated":
            return None
        if self.identity and not force:
            # Detect a manual switch to another account in the remote browser.
            if await is_authenticated(active, MOODLE):
                owner = await active.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
                if owner != self.identity["moodle_user_id"]:
                    self.identity = None
                    self.cache.clear()
                    self.notifications.clear()
                else:
                    return self.identity
            else:
                return self.identity
        if not force and time.monotonic() < self.identity_retry_at:
            return None
        self.identity_retry_at = time.monotonic() + 300
        try:
            async with asyncio.timeout(8):
                identity = await read_identity(active, MOODLE)
        except (TimeoutError, BrowserError):
            identity = None
        finally:
            self.page = active
            self.window_ids = {page: key for page, key in self.window_ids.items() if not page.is_closed()}
        if identity:
            self.identity = identity
            self.session_notice = ""
            saved = await student_db.get(identity["email"], identity["moodle_user_id"])
            if saved is None:
                await student_db.save(identity, [])
            return identity
        self.session_notice = "Moodle не предоставил почту профиля: постоянный кэш пока недоступен."
        return None

    def cache_result(self, key, result):
        self.collect_notifications(result.get("timeline", []))
        self.cache[key] = (time.monotonic() + 30, result)
        self.cache.move_to_end(key)
        while len(self.cache) > 30:
            self.cache.popitem(last=False)

    def start_data_refresh(self):
        if self.data_refresh_task is None or self.data_refresh_task.done():
            self.data_refresh_task = asyncio.create_task(self.refresh_saved_data())

    async def refresh_saved_data(self):
        if self.api_token and self.remembered_until is None:
            await self.persistence_ready.wait()
        # Refresh known documents, not every link recursively or any submission.
        if not self.identity or self.login_flow.status["phase"] != "authenticated":
            return
        keys = await student_db.document_keys(self.identity["email"], self.identity["moodle_user_id"])
        requests = [ContentRequest(section=section) for section in ("courses", "dashboard", "grades", "attendance")]
        requests += [ContentRequest(section=section, url=url)
                     for section, url in keys if url not in PAGES.values()]
        try:
            async with asyncio.timeout(300):
                for payload in requests:
                    if self.retired or self.expires <= time.monotonic():
                        return
                    try:
                        await self.content(payload, background=True)
                    except (HTTPException, BrowserError, sqlite3.Error, ValueError):
                        logging.getLogger(__name__).warning("Student cache refresh deferred for one document")
                        if self.login_flow.status["phase"] != "authenticated":
                            return
        except TimeoutError:
            logging.getLogger(__name__).warning("Student cache refresh exceeded its time limit")

    async def offline_content(self, payload, target):
        section = "courses" if payload.section == "home" and not payload.url else payload.section
        saved = await student_db.document(self.identity["email"], self.identity["moodle_user_id"], section, target)
        if saved is None:
            cached = self.cache.get((section, target))
            saved = cached[1] if cached else None
        if saved is None:
            raise HTTPException(409, "Этот материал ещё не сохранён. Восстанови подключение к LMS, чтобы открыть его.")
        result = {**saved, "section":payload.section, "cached":True, "requires_login":True,
                  "warnings":[self.session_notice]}
        self.cache_result((section,target), result)
        return result

    async def restore_moodle(self):
        # Caller holds the session lock. Follow only a fresh Moodle OIDC link.
        if not self.identity or time.monotonic()-self.last_sso_attempt < 30:
            return False
        self.last_sso_attempt = time.monotonic()
        original = self.page
        reader = await self.context.new_page()
        self.page = original
        try:
            async with asyncio.timeout(10):
                await reader.goto(MOODLE+"/login/index.php", wait_until="domcontentloaded", timeout=8000)
                if not await is_authenticated(reader, MOODLE):
                    location = urlsplit(reader.url)
                    if location.scheme == "https" and location.netloc == urlsplit(MOODLE).netloc:
                        oidc = reader.locator('a[href*="/auth/oidc/"]').first
                        if await oidc.count():
                            from urllib.parse import urljoin
                            target = urlsplit(urljoin(reader.url, await oidc.get_attribute("href") or ""))
                            if target.scheme != "https" or target.netloc != urlsplit(MOODLE).netloc:
                                return False
                            await oidc.click(timeout=3000)
                kmsi_accepted = False
                while True:
                    try:
                        if await is_authenticated(reader, MOODLE):
                            owner = await reader.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
                            if owner != self.identity["moodle_user_id"]:
                                return False
                            self.moodle_reauth_required = False
                            self.session_notice = ""
                            self.last_moodle_check = time.monotonic()
                            self.last_persist_at = 0
                            return True
                        location = urlsplit(reader.url)
                        if location.scheme != 'https' or location.netloc not in MICROSOFT_HOSTS | {urlsplit(MOODLE).netloc}:
                            return False
                        if location.netloc in MICROSOFT_HOSTS and not kmsi_accepted:
                            prompt = reader.locator("#KmsiDescription")
                            yes = reader.locator("#idSIButton9")
                            if await prompt.count() and await prompt.is_visible() and await yes.count() and await yes.is_enabled():
                                await yes.click(timeout=2500)
                                kmsi_accepted = True
                                continue
                        if await reader.locator('input[name=loginfmt], input[name=passwd], #idRichContext_DisplaySign, #idDiv_SAOTCS_Proofs').count():
                            return False
                    except BrowserError:
                        pass  # OIDC can replace the JS context between two navigations.
                    await asyncio.sleep(.2)
        except (BrowserError, TimeoutError):
            return False
        finally:
            await reader.close()
            self.window_ids.pop(reader, None)
            self.page = original

    async def check_moodle_connection(self, force=False):
        async with self.lock:
            if self.retired or self.login_flow.running or not self.identity:
                return
            if not force and (self.moodle_reauth_required or time.monotonic()-self.last_moodle_check < MOODLE_TOUCH_SECONDS):
                return
            active = await self.ensure_page()
            self.last_moodle_check = time.monotonic()
            if self.moodle_reauth_required:
                await self.restore_moodle()
                return
            reader = await self.context.new_page()
            self.page = active
            try:
                response = await reader.goto(PAGES["dashboard"], wait_until="domcontentloaded", timeout=8000)
                if response and response.status >= 500:
                    raise BrowserError("Moodle is unavailable")
                if await is_authenticated(reader, MOODLE):
                    owner = await reader.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
                    if owner == self.identity["moodle_user_id"]:
                        return
                self.mark_moodle_expired()
                await self.restore_moodle()
            except BrowserError:
                # A network failure is not proof of a revoked login.
                pass
            finally:
                await reader.close()
                self.window_ids.pop(reader, None)
                self.page = active

    async def attendance(self, refresh=False):
        # One crawl per session at a time; other students have independent locks.
        async with self.attendance_lock:
            generation = self.auth_generation
            overview = await self.content(ContentRequest(section="attendance", refresh=refresh), background=True)
            expected_identity = dict(self.identity) if self.identity else None
            events, reports, notices, missing, snapshots = [], [], [], [], [overview]
            seen = set()
            def check_owner():
                if self.retired or self.auth_generation != generation or self.identity != expected_identity or self.login_flow.running:
                    raise HTTPException(409, "Аккаунт изменился. Открой посещаемость заново.")
            async def collect():
                for course in overview.get("courses", []):
                    check_owner()
                    try:
                        data = await self.content(ContentRequest(section="attendance", url=course["url"], refresh=refresh), background=True)
                        check_owner()
                        snapshots.append(data)
                        journals = [a for a in data.get("activities", []) if urlsplit(a["url"]).path == "/mod/attendance/view.php"]
                        if not journals:
                            missing.append(course["title"])
                        for journal in journals:
                            if journal["url"] in seen:
                                continue
                            seen.add(journal["url"])
                            try:
                                report = await self.content(ContentRequest(section="attendance", url=journal["url"], refresh=refresh), background=True)
                                check_owner()
                                snapshots.append(report)
                                events.extend(report_events(report, course, journal))
                                reports.append({"course":course["title"], "journal":journal["title"],
                                                "tables":report.get("tables", []),
                                                "updated":report.get("updated"),
                                                "cache_updated_at":report.get("cache_updated_at")})
                                if not report.get("tables"):
                                    notices.append(course["title"] + ": LMS не предоставила таблицу журнала.")
                            except (HTTPException, BrowserError):
                                check_owner()
                                notices.append(course["title"] + ": не удалось загрузить журнал " + journal["title"] + ".")
                    except (HTTPException, BrowserError):
                        check_owner()
                        notices.append(course["title"] + ": посещаемость пока недоступна.")
            try:
                async with asyncio.timeout(90):
                    await collect()
            except TimeoutError:
                notices.append("LMS отвечает медленно: показана загруженная часть. Нажми обновить, чтобы повторить.")
            check_owner()
            for snapshot in snapshots:
                notices.extend(snapshot.get("warnings", []))
            stamps = [x["cache_updated_at"] for x in snapshots if x.get("cache_updated_at")]
            oldest = min(snapshots, key=lambda x:x.get("cache_updated_at") or "9999")
            return {"section":"attendance", "attendance_view":"calendar", "title":"Посещаемость",
                    "profile":overview.get("profile",""), "events":events, "reports":reports,
                    "courses":overview.get("courses",[]), "missing_courses":missing,
                    "warnings":list(dict.fromkeys(notices)), "partial":bool(notices),
                    "requires_login":self.moodle_reauth_required,
                    "cached":all(x.get("cached") for x in snapshots),
                    "cache_stale":any(x.get("cache_stale") for x in snapshots),
                    "cache_updated_at":min(stamps) if stamps else None,
                    "updated":oldest.get("updated",""),
                    "demo":False, "detail":False}

    async def content(self, payload: ContentRequest, background=False):
        if self.login_flow.running:
            raise HTTPException(409, 'Сначала заверши вход Microsoft.')
        demo = payload.section == 'demo' and payload.url is None
        if payload.url:
            target = content_url(payload.url, MOODLE)
        elif payload.section in {'home', 'courses', 'calendar', 'grades', 'dashboard', 'demo', 'attendance'}:
            target = PAGES['courses'] if payload.section == 'home' else PAGES[payload.section]
        else:
            raise HTTPException(400, 'Неизвестный раздел.')
        async with self.lock:
            if not demo and self.identity and self.moodle_reauth_required:
                return await self.offline_content(payload, target)
            active = await self.ensure_page()
            if not demo and self.identity and self.moodle_reauth_required:
                return await self.offline_content(payload, target)
            if not background:
                return await self.read_cached_content(payload, active, demo, target)
            # Read in a temporary tab, preserving the user's remote browser page.
            reader = await self.context.new_page()
            self.page = active
            try:
                return await self.read_cached_content(payload, reader, demo, target, identity_page=active)
            finally:
                await reader.close()
                self.window_ids.pop(reader, None)
                self.page = active

    async def read_cached_content(self, payload, active, demo, target, identity_page=None, allow_reconnect=True):
        cache_section = 'courses' if payload.section == 'home' and not payload.url else payload.section
        cache_key = (cache_section, target)
        if not demo and self.login_flow.status['phase'] != 'authenticated':
            await read_content(active, MOODLE)
            self.login_flow.update('authenticated', 'Вход выполнен.')
        identity = await self.verified_identity(identity_page or active) if not demo else None
        saved = await student_db.document(identity["email"], identity["moodle_user_id"], cache_section, target) if identity else None
        if saved and not saved["cache_stale"] and not payload.refresh:
            result = {**saved, "section": payload.section}
            self.cache_result(cache_key, result)
            if not self.bootstrap_started:
                self.bootstrap_started = True
                self.start_data_refresh()
            return result
        cached = self.cache.get(cache_key)
        if identity is None and not payload.refresh and cached and cached[0] > time.monotonic():
            return {**cached[1], "cached": True, "section": payload.section}
        try:
            request_target = target
            attendance_report = urlsplit(target).path == '/mod/attendance/view.php'
            attendance_owner = None
            if attendance_report:
                # Explicitly request only the signed-in user's report, including for staff accounts.
                attendance_owner = identity["moodle_user_id"] if identity else await active.evaluate(
                    "Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid ?? 0)")
                if not attendance_owner:
                    raise HTTPException(409, "Сначала войди в LMS.")
                request_target += '&studentid=' + str(int(attendance_owner))
            response = await active.goto(request_target, wait_until='domcontentloaded', timeout=45000)
            if response and response.status >= 400:
                raise BrowserError("Moodle returned an error page")
            if not demo and not await is_authenticated(active, MOODLE):
                raise HTTPException(409, "Подключение к Moodle истекло.")
            if payload.section in {'home', 'courses', 'attendance'} and (not payload.url):
                try:
                    await active.locator('#region-main a[href*="/course/view.php"]').first.wait_for(timeout=6000)
                except BrowserTimeout:
                    pass
            if attendance_report:
                final = urlsplit(active.url)
                shown_student = parse_qs(final.query).get('studentid', [str(int(attendance_owner))])
                current_owner = await active.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid ?? 0)")
                if (final.path != '/mod/attendance/view.php' or shown_student != [str(int(attendance_owner))]
                        or current_owner != attendance_owner):
                    raise HTTPException(403, "LMS не открыла твой личный журнал посещаемости.")
            data = await read_content(active, MOODLE, demo=demo, section=payload.section)
            if identity:
                owner = await active.evaluate("Number(window.M?.cfg?.userId ?? window.M?.cfg?.userid)")
                if owner != identity["moodle_user_id"]:
                    raise HTTPException(409, "Microsoft открыл другой аккаунт. Подтверди вход заново.")
                if cache_section == "courses" and not payload.url and (payload.refresh or (saved and saved["cache_stale"])):
                    identity = await self.verified_identity(active, force=True)
                    if identity_page is not None:
                        self.page = identity_page
            if not demo:
                self.last_moodle_check = time.monotonic()
            warnings = []
            complete = True
            if payload.section == 'dashboard' and (not payload.url):
                warnings = await prepare_timeline(active)
                complete = not warnings
                data = await read_content(active, MOODLE, section=payload.section)
            if not demo:
                self.login_flow.update('authenticated', 'Вход выполнен.')
                await self.remember_session()
                if self.session_notice:
                    warnings.append(self.session_notice)
        except HTTPException as error:
            if not demo and error.status_code == 409:
                self.mark_moodle_expired()
                if self.identity:
                    if allow_reconnect and await self.restore_moodle():
                        return await self.read_cached_content(payload, active, demo, target,
                                                              identity_page, allow_reconnect=False)
                    return await self.offline_content(payload, target)
                self.cache.clear()
                self.notifications.clear()
            raise
        except BrowserError:
            if saved:
                result = {**saved, "section": payload.section, "cache_stale": True,
                          "warnings": ["Moodle недоступен. Показана сохранённая копия; обновление не выполнено."]}
                self.cache_result(cache_key, result)
                return result
            raise HTTPException(502, 'Не удалось прочитать страницу. Для файла или нестандартного материала открой экран браузера.')
        result = {**data, 'section': payload.section, 'detail': payload.url is not None, 'warnings': warnings, 'url': public_url(active.url), 'updated': time.strftime('%H:%M'), 'cached': False}
        if identity and complete:
            if cache_section == 'courses' and not payload.url:
                await student_db.save(identity, data.get("courses", []))
            await student_db.save_document(identity, cache_section, target, result)
            stored = await student_db.document(identity["email"], identity["moodle_user_id"], cache_section, target)
            result.update({key: stored[key] for key in ("cache_updated_at", "cache_stale", "updated")})
            result["cache_source"] = "moodle"
            if not self.bootstrap_started:
                self.bootstrap_started = True
                self.start_data_refresh()
        if identity and not complete:
            result["cache_stale"] = True
        self.cache_result(cache_key, result)
        return result

    def collect_notifications(self, events):
        for event in events:
            key = hashlib.sha256(json.dumps([event.get("url"), event.get("due"), event.get("date"), event.get("time"), event.get("event")], ensure_ascii=False).encode()).hexdigest()[:24]
            if key not in self.notifications:
                self.notifications[key] = {**event, "id":key, "read":False}
        while len(self.notifications) > 500:
            self.notifications.pop(next(iter(self.notifications)))


    async def state(self):
        async with self.lock:
            if self.context and pool.browser and pool.browser.is_connected():
                await self.ensure_page()
            windows = [{'id': self.window_ids[item], 'url': public_url(item.url), 'selected': item is self.page} for item in self.context.pages if not item.is_closed()] if self.context else []
            return {'active': self.page is not None and (not self.page.is_closed()), 'url': public_url(self.page.url) if self.page and (not self.page.is_closed()) else '', 'headless': headless_mode(), 'windows': windows}

    async def choose_window(self, payload: WindowChoice):
        async with self.lock:
            target = next((item for item in self.context.pages if not item.is_closed() and self.window_ids.get(item) == payload.id), None) if self.context else None
            if target is None:
                raise HTTPException(404, 'Окно уже закрыто. Обнови список окон.')
            await target.bring_to_front()
            self.select_page(target)
        return {'ok': True}

    async def navigate(self, payload: Navigate):
        if self.login_flow.running:
            raise HTTPException(409, 'Сначала заверши или отмени вход Microsoft.')
        if payload.destination not in PAGES:
            raise HTTPException(400, 'Неизвестная страница.')
        async with self.lock:
            try:
                active = await self.ensure_page()
                await active.goto(PAGES[payload.destination], wait_until='domcontentloaded', timeout=45000)
            except BrowserTimeout:
                raise HTTPException(504, 'Сайт не ответил за 45 секунд. Проверьте соединение и повторите.')
            except BrowserError:
                raise HTTPException(502, 'Браузер запущен, но сайт не открылся. Проверьте сеть и доступность сайта.')
        return {'ok': True}

    async def screen(self):
        async with self.lock:
            if self.page is None or self.page.is_closed():
                raise HTTPException(409, 'Сначала откройте сайт.')
            try:
                data = await self.page.screenshot(type='jpeg', quality=70, timeout=10000)
            except BrowserError:
                raise HTTPException(502, 'Страница меняется. Повторите запрос.')
        return Response(data, media_type='image/jpeg')

    async def action(self, payload: Action):
        async with self.lock:
            if self.page is None or self.page.is_closed():
                raise HTTPException(409, 'Сначала откройте сайт.')
            try:
                if payload.kind == 'click':
                    await self.page.mouse.click(payload.x, payload.y)
                elif payload.kind == 'text':
                    await self.page.keyboard.insert_text(payload.text)
                elif payload.kind == 'key' and payload.key in {'Enter', 'Tab', 'Backspace', 'Escape', 'ControlOrMeta+A'}:
                    await self.page.keyboard.press(payload.key)
                elif payload.kind == 'scroll':
                    await self.page.mouse.wheel(0, payload.delta)
                else:
                    raise HTTPException(400, 'Неизвестное действие.')
            except BrowserError:
                raise HTTPException(502, 'Не удалось выполнить действие. Обновите экран.')
        return {'ok': True}

    async def extract(self):
        async with self.lock:
            if self.page is None or self.page.is_closed():
                raise HTTPException(409, 'Сначала откройте сайт.')
            parts = urlsplit(self.page.url)
            demo = self.page.url == PAGES['demo']
            if not demo and (parts.scheme != 'https' or parts.netloc != 'lms.astanait.edu.kz'):
                raise HTTPException(409, 'Завершите вход и вернитесь на страницу Moodle.')
            if not demo:
                logged_in = await is_authenticated(self.page, MOODLE)
                if not logged_in:
                    raise HTTPException(409, 'Сначала завершите вход в Moodle. Данные страницы входа не собираются.')
            data = await self.page.evaluate("() => {\n            const root = document.querySelector('[role=main], #region-main, main') || document.body;\n            return {\n                title: document.title,\n                text: root.innerText.slice(0, 60000),\n                tables: [...root.querySelectorAll('table')].slice(0, 30).map(t =>\n                    [...t.rows].slice(0, 200).map(r => [...r.cells].map(c => c.innerText))),\n                links: [...root.querySelectorAll('a[href]')].map(a => ({title: a.innerText.trim(), url: a.href}))\n                    .filter(a => a.title && /^https?:/.test(a.url) && !/logout|sesskey|token|code=/i.test(a.url)).slice(0, 200)\n            };\n        }")
            return {'demo': demo, 'url': public_url(self.page.url), 'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'), **data}

    async def close(self):
        async with self.lifecycle_lock:
            await self.reset_browser()
        return {'ok': True}


async def expire_sessions():
    while True:
        await asyncio.sleep(30)
        async with sessions_lock:
            expired = [token for token, item in sessions.items() if item.requests == 0 and (
                item.expires <= time.monotonic() or
                (item.remembered_until and time.monotonic()-item.last_seen > 1800))]
            retired = [sessions.pop(token) for token in expired]
            for item in retired:
                item.retired = True
        await asyncio.gather(*(item.reset_browser() for item in retired))

async def keep_moodle_sessions():
    while True:
        await asyncio.sleep(30)
        async with sessions_lock:
            active = [(token,item) for token,item in sessions.items() if item.identity and not item.retired
                      and item.expires > time.monotonic() and not item.moodle_reauth_required
                      and time.monotonic()-item.last_moodle_check >= MOODLE_TOUCH_SECONDS]
        async def touch(token,item):
            try:
                await item.check_moodle_connection()
                await item.persist_session(token)
            except (BrowserError, HTTPException):
                pass
        await asyncio.gather(*(touch(token,item) for token,item in active), return_exceptions=True)


async def refresh_daily():
    await student_db.community(ROOT / "community.json", force=True)
    async with sessions_lock:
        active = [item for item in sessions.values() if item.identity and not item.retired
                  and item.expires > time.monotonic() and item.login_flow.status["phase"] == "authenticated"]
    # Only one refresh per account, with at most three browser workflows in flight.
    unique = {item.identity["email"]: item for item in active}
    capacity = asyncio.Semaphore(3)
    async def refresh(item):
        async with capacity:
            if item.data_refresh_task and not item.data_refresh_task.done():
                await item.data_refresh_task
            item.start_data_refresh()
            await item.data_refresh_task
    await asyncio.gather(*(refresh(item) for item in unique.values()), return_exceptions=True)


async def midnight_refresh():
    while True:
        now = utc_now()
        await asyncio.sleep(max(1, (next_midnight(now) - now).total_seconds()))
        try:
            await refresh_daily()
        except (sqlite3.Error, OSError, ValueError):
            logging.getLogger(__name__).warning("Daily cache refresh deferred; will retry on access")


@asynccontextmanager
async def lifespan(app):
    await student_db.community(ROOT / 'community.json')
    task = asyncio.create_task(expire_sessions())
    refresh_task = asyncio.create_task(midnight_refresh())
    keepalive_task = asyncio.create_task(keep_moodle_sessions())
    print(f"Bridge: http://127.0.0.1:{PORT} (isolated sessions)", flush=True)
    try:
        yield
    finally:
        task.cancel()
        refresh_task.cancel()
        keepalive_task.cancel()
        with suppress(asyncio.CancelledError):
            await keepalive_task
        with suppress(asyncio.CancelledError):
            await refresh_task
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.gather(*(item.reset_browser() for item in sessions.values()))
        sessions.clear()
        await pool.close()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

@app.exception_handler(RequestValidationError)
async def invalid_input(request, error):
    return JSONResponse({"detail":"Проверь заполнение полей."}, status_code=422)

@app.exception_handler(sqlite3.Error)
async def database_error(request, error):
    logging.getLogger(__name__).error("Student cache database is unavailable")
    return JSONResponse({"detail": "Кэш временно недоступен. Повтори запрос."}, status_code=503)

@app.exception_handler(BrowserError)
async def browser_error(request, error):
    return JSONResponse({"detail":"Браузер недоступен или страница меняется. Откройте сайт заново."}, status_code=502)

@app.middleware("http")
async def headers(request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET","HEAD") and origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        return Response("Origin rejected", status_code=403)
    response = await call_next(request)
    binding = getattr(request.state, "bridge_session", None)
    if binding:
        token, session = binding
        await session.persist_session(token)
        if session.remembered_until and not session.retired:
            remaining = max(0, int(session.remembered_until-student_db.clock().timestamp()))
            response.set_cookie("bridge_session", token, httponly=True, samesite="strict",
                                secure=request.url.scheme=="https", max_age=remaining)
    response.headers.update({"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff",
                             "Referrer-Policy":"no-referrer", "X-Frame-Options":"DENY",
                             "Content-Security-Policy":"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; frame-src https://yuujiso.github.io; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    return response

async def remembered_session(token):
    if not token:
        return None
    saved = await student_db.remembered(token)
    if saved is None:
        return None
    if len(sessions) >= MAX_SESSIONS:
        raise HTTPException(503, "Все места заняты. Повтори подключение позже.")
    item = BridgeSession()
    item.api_token = token
    item.identity = saved["identity"]
    item.pending_storage = saved["state"]
    item.remembered_until = saved["expires_at"]
    item.expires = time.monotonic() + max(0, saved["expires_at"]-student_db.clock().timestamp())
    item.login_flow.update("authenticated", "Вход восстановлен.")
    if item.pending_storage is None:
        item.mark_moodle_expired()
    sessions[token] = item
    return item


async def authorized(request: Request):
    token = request.cookies.get("bridge_session", "")
    async with sessions_lock:
        session = sessions.get(token)
        if session is None:
            session = await remembered_session(token)
        if session is None or session.retired or session.expires <= time.monotonic():
            raise HTTPException(401, "Сессия истекла. Войди снова.")
        session.requests += 1
        session.last_seen = time.monotonic()
        request.state.bridge_session = (token, session)
    try:
        yield session
    finally:
        async with sessions_lock:
            session.requests -= 1

@app.post("/api/connect")
async def connect(request: Request, response: Response):
    async with sessions_lock:
        now = time.monotonic()
        current_token = request.cookies.get("bridge_session","")
        current = sessions.get(current_token)
        if current is None:
            current = await remembered_session(current_token)
        if current and not current.retired and current.expires > now:
            request.state.bridge_session = (current_token, current)
            return {"ok":True, "expires_in":int(current.expires-now)}
        expired = [token for token,item in sessions.items() if item.expires <= now and item.requests == 0]
        for token in expired:
            item = sessions.pop(token)
            item.retired = True
            await item.reset_browser()
        if len(sessions) >= MAX_SESSIONS:
            raise HTTPException(503, "Все места заняты. Повтори подключение позже.", headers={"Retry-After":"30"})
        token = secrets.token_urlsafe(32)
        sessions[token] = BridgeSession()
        sessions[token].api_token = token
        response.set_cookie("bridge_session", token, httponly=True, samesite="strict",
                            secure=request.url.scheme=="https", max_age=SESSION_SECONDS)
    return {"ok":True, "expires_in":SESSION_SECONDS}

@app.get("/api/health")
async def health():
    return {"status":"ok", "session_capacity":MAX_SESSIONS}


@app.post('/api/resume')
async def resume(session: BridgeSession = Depends(authorized)):
    return await session.resume()


@app.post('/api/login')
async def login(payload: LoginRequest, request: Request, session: BridgeSession = Depends(authorized)):
    result = await session.login(payload)
    # reset_browser waits for any in-flight snapshot; revoke after it finishes.
    await student_db.forget(request.cookies.get("bridge_session",""))
    return result


@app.get('/api/login/status')
async def login_status(session: BridgeSession = Depends(authorized)):
    return await session.login_status()


@app.post("/api/moodle/reconnect")
async def reconnect_moodle(session: BridgeSession = Depends(authorized)):
    await session.check_moodle_connection(force=True)
    return {**session.login_flow.status, **session.connection_status()}


class AttendanceRequest(BaseModel):
    refresh: bool = False


@app.post('/api/attendance')
async def attendance(payload: AttendanceRequest, session: BridgeSession = Depends(authorized)):
    return await session.attendance(payload.refresh)


@app.post('/api/content')
async def content(payload: ContentRequest, session: BridgeSession = Depends(authorized)):
    return await session.content(payload)


@app.get('/api/state')
async def state(session: BridgeSession = Depends(authorized)):
    return await session.state()


@app.post('/api/window')
async def choose_window(payload: WindowChoice, session: BridgeSession = Depends(authorized)):
    return await session.choose_window(payload)


@app.post('/api/navigate')
async def navigate(payload: Navigate, session: BridgeSession = Depends(authorized)):
    return await session.navigate(payload)


@app.get('/api/screen')
async def screen(session: BridgeSession = Depends(authorized)):
    return await session.screen()


@app.post('/api/action')
async def action(payload: Action, session: BridgeSession = Depends(authorized)):
    return await session.action(payload)


@app.post('/api/extract')
async def extract(session: BridgeSession = Depends(authorized)):
    return await session.extract()


@app.post('/api/close')
async def close(request: Request, response: Response, session: BridgeSession = Depends(authorized)):
    session.retired = True
    await session.close()
    # Delete after the browser lock drains, so an older save cannot resurrect logout.
    await student_db.forget(request.cookies.get("bridge_session",""))
    async with sessions_lock:
        sessions.pop(request.cookies.get("bridge_session", ""), None)
    response.delete_cookie("bridge_session", httponly=True, samesite="strict",
                           secure=request.url.scheme == "https")
    return {"ok":True}


@app.get('/')
async def index():
    return FileResponse(ROOT / 'index.html')

@app.get('/demo', response_class=HTMLResponse)
async def demo():
    return '<!doctype html><html lang=ru><meta charset=utf-8><title>Bridge — тест</title>\n    <main><h1>Мои курсы</h1><p>Демонстрация интерфейса. Эти курсы и оценки — тестовые, не данные твоего аккаунта.</p>\n    <a href="https://lms.astanait.edu.kz/course/view.php?id=101">Information and Communication Technologies</a>\n    <a href="https://lms.astanait.edu.kz/course/view.php?id=102">Calculus I</a>\n    <a href="https://lms.astanait.edu.kz/mod/assign/view.php?id=103">Assignment 3 · Database design</a>\n    <label>Проверка ввода <input id=note placeholder=\'Введите текст с телефона\'></label>\n    <button onclick="document.querySelector(\'#result\').textContent=document.querySelector(\'#note\').value">Показать</button>\n    <p id=result></p><table border=1><tr><th>Предмет</th><th>Балл</th></tr>\n    <tr><td>ICT (демо)</td><td>95</td></tr></table></main></html>'


@app.get("/api/notifications")
async def notifications(session: BridgeSession = Depends(authorized)):
    async with session.lock:
        items = list(session.notifications.values())
        return {"items":items, "unread":sum(not item["read"] for item in items)}

@app.post("/api/notifications/read-all")
async def read_all(session: BridgeSession = Depends(authorized)):
    async with session.lock:
        for item in session.notifications.values():
            item["read"] = True
    return {"ok":True, "unread":0}

@app.get("/api/community")
async def community(session: BridgeSession = Depends(authorized)):
    data = await student_db.community(ROOT / "community.json")
    identity = session.identity if session.login_flow.status["phase"] == "authenticated" else None
    profile = await student_db.get(identity["email"], identity["moodle_user_id"]) if identity else None
    return {**data, "selected": profile["clubs"] if profile else [], "can_select": profile is not None}

class ClubChoice(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    selected: bool


@app.post("/api/profile/clubs")
async def choose_club(payload: ClubChoice, session: BridgeSession = Depends(authorized)):
    async with session.lock:
        if session.login_flow.status["phase"] != "authenticated" or not session.identity:
            raise HTTPException(409, "Сначала войди и загрузи профиль Moodle.")
        data = await student_db.community(ROOT / "community.json")
        try:
            await student_db.select_club(session.identity["email"], session.identity["moodle_user_id"],
                                         payload.title, payload.selected, {c["title"] for c in data["clubs"]})
        except ValueError:
            raise HTTPException(400, "Клуб не найден в справочнике.")
    return {"ok": True}


@app.get("/api/profile")
async def profile(session: BridgeSession = Depends(authorized)):
    async with session.lock:
        if session.login_flow.status["phase"] != "authenticated" or not session.identity:
            raise HTTPException(409, "Сначала войди и загрузи профиль Moodle.")
        return await student_db.get(session.identity["email"], session.identity["moodle_user_id"])


@app.get("/features.js", include_in_schema=False)
async def features_js():
    return FileResponse(ROOT / "features.js", media_type="text/javascript")

@app.get("/features.css", include_in_schema=False)
async def features_css():
    return FileResponse(ROOT / "features.css", media_type="text/css")


@app.get("/attendance-preview.webp", include_in_schema=False)
async def attendance_preview():
    return FileResponse(ROOT / "attendance-preview.webp", media_type="image/webp")


@app.get("/attendance-preview.png", include_in_schema=False)
async def attendance_preview_original():
    return FileResponse(ROOT / "attendance-preview.png", media_type="image/png")


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

@app.post("/api/assistant")
async def assistant(payload: AssistantQuestion, session: BridgeSession = Depends(authorized)):
    if session.chat_lock.locked():
        raise HTTPException(429, "Дождись ответа на предыдущий вопрос.")
    async with session.chat_lock:
        async with session.lock:
            context = assistant_service.context_for(session)
        answer = await assistant_service.answer(payload.question, context)
        if session.retired:
            raise HTTPException(401, "Сессия закрыта.")
        return {"answer":answer, "sources":["Загруженные курсы и дедлайны текущей сессии", "https://yuujiso.github.io/aitumap/"]}

@app.get("/attendance.js", include_in_schema=False)
async def attendance_script():
    return FileResponse(ROOT / "attendance.js", media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("BRIDGE_HOST","0.0.0.0"), port=PORT, access_log=False)

