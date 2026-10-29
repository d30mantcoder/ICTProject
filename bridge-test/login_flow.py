"""Interactive Microsoft login in the laptop browser, including user-approved MFA."""
import asyncio
import re
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from playwright.async_api import Error as BrowserError
from moodle_reader import is_authenticated

# Exact authentication hosts listed by Microsoft; never trust a suffix wildcard.
MICROSOFT_HOSTS = {'login.microsoftonline.com', 'login.microsoft.com', 'login.live.com'}
PASSWORD_OPTION = re.compile(
    r'^(Use my password|Use your password|Use a password|Sign in with a password|'
    r'Sign in with your password|Use (?:my |your |a )?password instead|Password|Использовать пароль|Использовать мой пароль|'
    r'Войти с паролем|Войти с помощью пароля|Пароль)$', re.I)
OTHER_METHODS = re.compile(
    r'^(Other ways to sign in|Sign-in options|Sign in another way|Use another method|'
    r'Try another way|Use a different sign-in method|I can.t use my passkey|'
    r'Другие способы входа|Параметры входа|Войти другим способом|Другие способы проверки)$', re.I)
SUBMIT = re.compile(r'^(Next|Sign in|Log in|Continue|Далее|Войти|Продолжить)$', re.I)
PASSKEY = re.compile(r'passkey|security key|face.{0,20}fingerprint|ключ доступа|ключ безопасности', re.I)
PASSKEY_BACK = re.compile(r'^(Back|Cancel|Go back|Назад|Отмена|Отменить)$', re.I)
PASSKEY_SKIP = re.compile(r'^(Skip for now|Not now|Maybe later|Пропустить|Не сейчас|Позже)$', re.I)
SECURITY_SETUP = re.compile(r"\bkeep\s+your\s+account\s+secure\b", re.I)
AUTHENTICATOR_APPROVAL = re.compile(
    r'^(?:Approve (?:a |the )?(?:request|notification) (?:on|in) '
    r'(?:(?:my|your|the) )?(?:Microsoft )?Authenticator(?: app)?|'
    r'Подтвердить запрос (?:в|через) (?:приложении |приложение )?Microsoft Authenticator|'
    r'Подтверждение запроса в (?:приложении )?Microsoft Authenticator)[.!]?$', re.I)


class LoginFlow:
    def __init__(self, get_page, lock, moodle, interval=1):
        self.get_page, self.lock, self.moodle = get_page, lock, moodle
        self.interval = interval
        self.task = None
        self.email = self.password = None
        self.status = {'phase': 'idle', 'message': 'Войди в свой аккаунт AITU.', 'number': None}

    def update(self, phase, message, number=None):
        self.status = {'phase': phase, 'message': message, 'number': number}

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    def start(self, email, password):
        if self.running:
            raise HTTPException(409, 'Вход уже выполняется. Подтверди его или нажми «Отменить».')
        self.email, self.password = email, password
        self.update('opening', 'Открываем вход AITU на ноутбуке…')
        self.task = asyncio.create_task(self.run())

    async def cancel(self):
        if self.running:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.email = self.password = None
        self.update('idle', 'Войди в свой аккаунт AITU.')

    async def visible(self, page, selector):
        matches = page.locator(selector)
        for i in range(min(await matches.count(), 10)):
            locator = matches.nth(i)
            if await locator.is_visible():
                return locator
        return None

    async def named_control(self, page, pattern):
        for role in ('button', 'link'):
            controls = page.get_by_role(role, name=pattern)
            for i in range(min(await controls.count(), 10)):
                control = controls.nth(i)
                if await control.is_visible():
                    return control
        # New Microsoft layouts also use clickable text tiles without a role.
        controls = page.get_by_text(pattern, exact=True)
        for i in range(min(await controls.count(), 10)):
            control = controls.nth(i)
            if await control.is_visible():
                return control
        return None

    async def submit(self, page):
        control = await self.visible(page, '#idSIButton9')
        if control is None:
            control = await self.named_control(page, SUBMIT)
        if control is None or not await control.is_enabled():
            return False
        await control.click(timeout=2500)
        return True

    async def password_method(self, page, sent):
        # Choose only an offered password option. Never select/enroll a passkey.
        if self.password is None:
            return False
        if time.monotonic() - sent.get('method_at', 0) < 1:
            return False
        if sent.get('method_attempts', 0) >= 6:
            return False
        for pattern in (PASSWORD_OPTION, OTHER_METHODS):
            choice = await self.named_control(page, pattern)
            if choice is not None:
                await choice.click(timeout=2500)
                sent['method_at'] = time.monotonic()
                sent['method_attempts'] = sent.get('method_attempts', 0) + 1
                self.update('password', 'Выбираем доступный вход по паролю…')
                return True
        return False

    async def authenticator_method(self, page, sent):
        # Select the offered push method by its label, never by list position.
        # This requests approval; only the owner approves it in Authenticator.
        choice = await self.named_control(page, AUTHENTICATOR_APPROVAL)
        if choice is None:
            return False
        self.password = None
        if not sent.get('authenticator_chosen'):
            if not await choice.is_enabled():
                self.update('mfa', 'Ожидаем доступности Microsoft Authenticator…')
                return True
            # Mark before clicking: a redirect may interrupt click completion.
            # Polling must not send another push while the first is pending.
            sent['authenticator_chosen'] = True
            await choice.click(timeout=2500)
        self.update('mfa', 'Открой Microsoft Authenticator и подтверди запрос. Ожидаем число Microsoft…')
        return True

    async def step(self, page, sent):
        # A popup is emitted before its first navigation commits. Do not mistake
        # that temporary empty page for an untrusted credentials destination.
        if page.url == 'about:blank':
            started = sent.setdefault('blank_since', time.monotonic())
            if time.monotonic() - started >= 10:
                self.update('action', 'Новое окно осталось пустым. Выбери другое окно в списке ниже.')
            else:
                self.update('waiting', 'Ожидаем загрузки нового окна Microsoft…')
            return False
        sent.pop('blank_since', None)
        location = urlsplit(page.url)
        if location.scheme != 'https':
            self.update('error', 'Вход остановлен: страница авторизации не использует HTTPS.')
            return True
        if location.netloc == urlsplit(self.moodle).netloc:
            if await is_authenticated(page, self.moodle):
                self.update('authenticated', 'Вход выполнен. Загружаем твои курсы.')
                return True
            self.update('waiting', 'Ожидаем завершения входа в Moodle…')
            return False
        if location.netloc not in MICROSOFT_HOSTS:
            self.update('error', 'Провайдер входа отличается от Microsoft. Автоматическая передача пароля остановлена.')
            return True
        error = await self.visible(page, '#usernameError, #passwordError, #idDiv_SAOTCS_ErrorMsg, #idDiv_SAOTCAS_Error')
        if error and (await error.inner_text(timeout=1000)).strip():
            self.update('error', 'Microsoft не принял вход. Проверь данные или открой экран входа ниже.')
            return True
        # These nodes hold Microsoft's number-matching challenge, not an invented OTP.
        number_node = await self.visible(page, '#idRichContext_DisplaySign, #idDiv_SAOTCAS_DisplaySign, .displaySign')
        if number_node:
            number = (await number_node.inner_text(timeout=1000)).strip()
            self.password = None
            self.update('mfa', 'Открой Microsoft Authenticator и подтверди запрос с этим числом.',
                        number if re.fullmatch(r'\d{1,3}', number) else None)
            return False
        kmsi = await self.visible(page, '#KmsiDescription')
        if kmsi:
            self.password = None
            # The user requested remembered login: accept the provider's KMSI prompt.
            button = await self.visible(page, '#idSIButton9')
            if button is None:
                button = await self.named_control(page, re.compile(r'^(Yes|Да)$', re.I))
            if button and await button.is_enabled() and not sent.get('kmsi_accepted'):
                await button.click(timeout=2500)
                sent['kmsi_accepted'] = True
            self.update('waiting', 'Сохраняем вход Microsoft и возвращаемся в Moodle…')
            return False
        email = await self.visible(page, 'input[name=loginfmt], input[type=email]')
        if email and not sent['email']:
            await email.fill(self.email)
            if await self.submit(page):
                sent['email'] = True
                self.update('password', 'Microsoft проверяет аккаунт…')
            else:
                self.update('action', 'Почта введена. Нажми «Далее» на экране входа ниже.')
            return False
        password = await self.visible(page, 'input[name=passwd], input[autocomplete=current-password], '
                                     'input#passwordInput, input#passwordEntry, input#i0118, '
                                     'input[type=password][name=password], input[type=password][name=Password]')
        if password and self.password is not None:
            # Filling a field is not a completed submission. The provider can
            # render its submit button later, replace the field, or redirect.
            # Retain the in-memory secret until MFA/terminal state, never disk.
            if not await password.is_editable():
                self.update('password', 'Ожидаем готовности формы Microsoft…')
                return False
            if sent['password'] and await password.input_value():
                self.update('waiting', 'Ожидаем ответ Microsoft…')
                return False
            if time.monotonic() - sent.get('password_at', 0) < 1:
                return False
            if sent.get('password_attempts', 0) >= 3:
                self.update('error', 'Microsoft несколько раз вернул форму пароля. Начни вход заново.')
                return True
            await password.fill(self.password)
            if await self.submit(page):
                sent['password'] = True
                sent['password_at'] = time.monotonic()
                sent['password_attempts'] = sent.get('password_attempts', 0) + 1
                self.update('waiting', 'Ожидаем ответ Microsoft…')
            else:
                self.update('password', 'Ожидаем кнопку входа Microsoft. Пароль будет отправлен автоматически…')
            return False
        text = (await page.locator('body').inner_text(timeout=1000))[:12000]
        if SECURITY_SETUP.search(text):
            # Microsoft also offers optional enrollment without mentioning passkeys.
            # Only use an explicit postponement control on the trusted HTTPS origin.
            # Keep this separate from an earlier passkey Back/Cancel action.
            if sent.get('security_setup_dismissed'):
                self.update('waiting', 'Ожидаем завершения перехода в Moodle…')
                return False
            skip = await self.named_control(page, PASSKEY_SKIP)
            if skip is None:
                self.update('action', 'Microsoft просит настроить защиту аккаунта. '
                            'Если кнопки «Not now» нет, продолжи на экране входа ниже.')
            elif not await skip.is_enabled():
                self.update('waiting', 'Ожидаем доступности кнопки «Not now»…')
            else:
                await skip.click(timeout=2500)
                sent['security_setup_dismissed'] = True
                self.update('waiting', 'Дополнительная настройка отложена. Возвращаемся в Moodle…')
            return False
        if await self.authenticator_method(page, sent):
            return False
        mfa = await self.visible(page, '#idDiv_SAOTCAS_Description, #idDiv_SAOTCS_Proofs, #idDiv_SAOTCC_Description')
        if mfa:
            self.password = None
            self.update('mfa', 'Подтверди запрос Microsoft. Если нужен код или выбор способа, открой экран входа ниже.')
        else:
            if await self.password_method(page, sent):
                return False
            if PASSKEY.search(text):
                # A declined WebAuthn request can leave an error/registration
                # page with only Back or Skip. Do not click retry/enroll.
                back = await self.named_control(page, PASSKEY_SKIP)
                if back is None and self.password is not None:
                    back = await self.named_control(page, PASSKEY_BACK)
                if back is not None and not sent.get('passkey_dismissed'):
                    await back.click(timeout=2500)
                    sent['passkey_dismissed'] = True
                    self.update('password', 'Пропускаем ключ доступа и возвращаемся к другим способам входа…')
                    return False
                self.update('action', 'Запрос ключа доступа отклонён. Если Microsoft не предложил пароль '
                            'автоматически, выбери другой доступный способ на экране входа ниже. '
                            'Если организация требует ключ, понадобится разрешённый ею способ входа.')
            else:
                self.update('action', 'Если Microsoft просит дополнительное действие, открой экран входа ниже.')
        return False

    async def run(self):
        sent = {'email': False, 'password': False}
        try:
            async with self.lock:
                page = await self.get_page()
                await page.goto(self.moodle + '/login/index.php', wait_until='domcontentloaded', timeout=45000)
                # Follow the fresh Moodle-generated OIDC request; never reuse saved tokens.
                await page.locator('a[href*="/auth/oidc/"]').first.click(timeout=20000)
            deadline = time.monotonic() + 600
            failures = 0
            while time.monotonic() < deadline:
                try:
                    async with self.lock:
                        page = await self.get_page()
                        if await self.step(page, sent):
                            return
                    failures = 0
                except BrowserError:
                    # Redirects can temporarily destroy the JavaScript execution context.
                    failures += 1
                    if failures >= 8:
                        raise
                await asyncio.sleep(self.interval)
            self.update('error', 'Время ожидания истекло. Начни вход заново.')
        except HTTPException as error:
            self.update('error', str(error.detail))
        except BrowserError:
            self.update('error', 'Не удалось продолжить вход. Проверь соединение или открой экран входа ниже.')
        except asyncio.CancelledError:
            raise
        except Exception:
            self.update('error', 'Вход прервался. Попробуй ещё раз.')
        finally:
            self.email = self.password = None
