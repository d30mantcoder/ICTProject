"""Isolated browser regressions: local assets, synthetic APIs, no live accounts."""
import mimetypes
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent
CATALOG = {
    'checked': '2026-11-10', 'source': 'https://example.test/clubs',
    'can_select': True, 'selected': [],
    'clubs': [
        {'title': 'Robotics', 'category': 'Technology'},
        {'title': 'Chess', 'category': 'Sport'},
    ],
}


class UsabilityTests(unittest.TestCase):
    def test_hide_is_disabled_during_timeline_reload(self):
        held=[]
        data={'section':'dashboard','can_hide_activities':True,'timeline':[
            {'title':'Task','url':'https://lms.astanait.edu.kz/mod/assign/view.php?id=123'}]}
        self.page.route('**/api/content',lambda route:held.append(route))
        self.page.evaluate("data=>{currentSection='dashboard';$('signIn').hidden=true;$('dashboard').hidden=false;render(data)}",data)
        button=self.page.get_by_role('button',name='Не моё',exact=True)
        expect(button).to_be_enabled()
        self.page.evaluate("void loadContent('dashboard',null,true)")
        expect(button).to_be_disabled()
        held.pop().fulfill(json=data)
        expect(button).to_be_enabled()

    def test_hide_completion_does_not_navigate_back_after_leaving_tasks(self):
        held=[];refreshes=[]
        self.page.route('**/api/activities/hide',lambda route:held.append(route))
        self.page.route('**/api/content',lambda route:(refreshes.append(route.request.post_data_json),route.fulfill(json={})))
        self.page.evaluate("""()=>{currentSection='dashboard';$('signIn').hidden=true;$('dashboard').hidden=false;
            render({section:'dashboard',can_hide_activities:true,timeline:[{title:'Unwanted',url:'https://lms.astanait.edu.kz/mod/assign/view.php?id=123'}]});}""")
        self.page.get_by_role('button',name='Не моё',exact=True).click()
        self.clubs()
        held.pop().fulfill(json={'ok':True})
        self.page.wait_for_function('!hidingActivity')
        expect(self.page.locator('.club-card')).to_have_count(2)
        self.assertEqual(refreshes,[])

    def test_hide_assignment_saves_before_removing_and_refreshes_all_activities(self):
        held=[];reads=[]
        url='https://lms.astanait.edu.kz/mod/assign/view.php?id=123'
        def content(route):
            reads.append(route.request.post_data_json)
            route.fulfill(json={'section':'dashboard','can_hide_activities':True,'hidden_activity_count':1,
                'timeline':[{'title':'Next activity','url':url+'4','course':'Course'}]})
        self.page.route('**/api/content',content)
        self.page.route('**/api/activities/hide',lambda route:held.append(route))
        self.page.evaluate("""url=>{currentSection='dashboard';$('signIn').hidden=true;$('dashboard').hidden=false;
            render({section:'dashboard',can_hide_activities:true,timeline:[{title:'Unwanted',url,course:'Course'}]});} """,url)
        button=self.page.get_by_role('button',name='Не моё',exact=True)
        button.click()
        expect(self.page.get_by_text('Unwanted',exact=True)).to_be_visible()
        expect(button).to_be_disabled()
        self.assertEqual(held[0].request.post_data_json,{'url':url})
        held.pop().fulfill(status=503,json={'detail':'Try again'})
        expect(button).to_be_enabled()
        expect(self.page.get_by_text('Unwanted',exact=True)).to_be_visible()
        button.click();held.pop().fulfill(json={'ok':True,'hidden_until':2000000000})
        expect(self.page.get_by_text('Next activity',exact=True)).to_be_visible()
        expect(self.page.get_by_text('Unwanted',exact=True)).to_have_count(0)
        self.assertTrue(reads[-1]['refresh'])
        expect(self.page.locator('#document')).to_contain_text('Скрыто на неделю: 1')

    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={'width': 390, 'height': 844}, service_workers='block',
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1',
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(3000)
        self.errors, self.writes, self.navigations = [], [], []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('framenavigated', lambda frame: self.navigations.append(frame.url) if frame == self.page.main_frame else None)
        self.context.route('**/*', self.route)
        self.page.goto('https://bridge.test/')
        self.page.wait_for_function("typeof renderClubs === 'function' && typeof classmatesBaseLoad === 'function' && connected")
        expect(self.page.locator('#signIn')).to_be_visible()

    def tearDown(self):
        for route in self.writes:
            try:
                route.abort()
            except Exception:
                pass  # Completed routes have already been handled.
        self.context.close()
        self.assertEqual(self.errors, [])

    def route(self, route):
        path = urlsplit(route.request.url).path
        if path.startswith('/api/'):
            name = path[5:]
            if name == 'profile/clubs':
                self.writes.append(route)
                return
            data = {'community': CATALOG, 'login/status': {'phase': 'idle'},
                    'notifications': {'items': [], 'unread': 0}}.get(name, {})
            route.fulfill(json=data)
            return
        asset = ROOT / ('index.html' if path == '/' else path.lstrip('/'))
        if ROOT in asset.resolve().parents and asset.is_file() and asset.suffix in {'.html', '.js', '.css', '.png', '.webp', '.webmanifest'}:
            route.fulfill(body=asset.read_bytes(), content_type=mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
        else:
            route.fulfill(status=404, body='Fixture unavailable')

    def clubs(self):
        self.page.evaluate("loadContent('clubs')")
        expect(self.page.locator('.club-card')).to_have_count(2)
        return self.page.get_by_role('checkbox', name='Мой клуб: Robotics', exact=True)

    def test_pending_selection_survives_filter_and_success(self):
        choice = self.clubs()
        choice.check()
        self.page.get_by_role('searchbox').fill('Rob')
        expect(choice).to_be_checked()
        expect(choice).to_be_disabled()
        expect(self.page.locator('.club-save-summary')).to_contain_text('Сохраняем')
        self.page.locator('#myClubs').check()
        expect(choice).to_be_checked()
        self.writes[0].fulfill(json={'ok': True})
        expect(choice).to_be_enabled()
        expect(choice).to_be_checked()
        expect(self.page.locator('.club-save-summary')).to_contain_text('Выбор сохранён')
        choice.uncheck()
        self.writes[1].fulfill(json={'ok': True})
        expect(self.page.locator('.club-card')).to_have_count(0)

    def test_failed_save_rolls_back_current_checkbox_and_keeps_error(self):
        choice = self.clubs()
        choice.check()
        self.page.get_by_role('searchbox').fill('Rob')
        self.writes[0].fulfill(status=503, json={'detail': 'Temporary failure'})
        expect(choice).not_to_be_checked()
        expect(choice).to_be_enabled()
        expect(self.page.locator('.club-save-summary')).to_contain_text('Не удалось сохранить')
        self.page.get_by_role('searchbox').fill('Chess')
        self.page.get_by_role('checkbox', name='Мой клуб: Chess', exact=True).check()
        self.page.locator('header .language-select').select_option('en')
        expect(self.page.locator('.club-save-summary')).to_have_text('Saving selection… Could not save selection. Try again.')
        self.page.locator('header .language-select').select_option('ru')
        self.writes[1].fulfill(json={'ok': True})
        expect(self.page.locator('.club-save-summary')).to_contain_text('Не удалось сохранить')
        self.page.get_by_role('searchbox').fill('Rob')
        choice.check()
        self.writes[2].fulfill(json={'ok': True})
        expect(self.page.locator('.club-save-summary')).to_have_text('Выбор сохранён')

    def test_language_preserves_form_and_changes_both_ways_without_navigation(self):
        self.page.locator('#email').fill('student@example.test')
        self.page.locator('#password').fill('unsent password')
        self.page.evaluate('window.usabilitySentinel = 42')
        self.page.locator('header .language-select').select_option('en')
        expect(self.page.locator('html')).to_have_attribute('lang', 'en')
        expect(self.page.locator('#email')).to_have_value('student@example.test')
        expect(self.page.locator('#password')).to_have_value('unsent password')
        expect(self.page.locator('#loginButton')).to_have_text('Sign in with Microsoft')
        self.page.locator('header .language-select').select_option('ru')
        expect(self.page.locator('#loginButton')).to_have_text('Войти через Microsoft')
        self.assertEqual(self.page.evaluate('window.usabilitySentinel'), 42)
        self.assertEqual(len(self.navigations), 1)

    def test_language_during_save_preserves_filters_and_completion(self):
        choice = self.clubs()
        choice.check()
        self.page.get_by_role('searchbox').fill('Rob')
        self.page.locator('header .language-select').select_option('en')
        choice = self.page.get_by_role('checkbox', name='My club: Robotics', exact=True)
        expect(choice).to_be_checked()
        expect(choice).to_be_disabled()
        expect(self.page.get_by_role('searchbox')).to_have_value('Rob')
        self.writes[0].fulfill(json={'ok': True})
        expect(choice).to_be_enabled()
        expect(self.page.locator('.club-save-summary')).to_have_text('Selection saved')
        self.assertEqual(len(self.navigations), 1)

    def test_four_isolated_users_filter_during_simultaneous_saves(self):
        pages = [self.page]
        contexts = []
        try:
            for _ in range(3):
                context = self.browser.new_context(service_workers='block')
                contexts.append(context)
                context.route('**/*', self.route)
                page = context.new_page()
                page.on('pageerror', lambda error: self.errors.append(str(error)))
                page.goto('https://bridge.test/')
                page.wait_for_function("typeof classmatesBaseLoad === 'function' && connected")
                pages.append(page)
            for page in pages:
                page.evaluate("loadContent('clubs')")
                page.get_by_role('checkbox', name='Мой клуб: Robotics', exact=True).check()
                page.get_by_role('searchbox').fill('Rob')
                expect(page.locator('.club-card input')).to_be_checked()
                expect(page.locator('.club-card input')).to_be_disabled()
            self.assertEqual(len(self.writes), 4)
            # Complete out of order; only the second user's save fails.
            for index in (3, 1, 0, 2):
                self.writes[index].fulfill(status=503 if index == 1 else 200,
                                          json={'detail': 'Temporary failure'} if index == 1 else {'ok': True})
            for index, page in enumerate(pages):
                expect(page.locator('.club-card input')).to_be_enabled()
                expect(page.locator('.club-card input')).to_be_checked(checked=index != 1)
                expect(page.locator('.club-save-summary')).to_contain_text(
                    'Не удалось сохранить' if index == 1 else 'Выбор сохранён')
        finally:
            for context in contexts:
                context.close()

    def test_calendar_language_preserves_date_filter_and_moodle_status(self):
        self.page.evaluate("""() => {
            featureShell('attendance');
            renderAttendance({attendance_view:'calendar',reports:[{course:'English',journal:'Attendance',tables:[]}],
                courses:[{title:'English',url:'course1'}],events:[{day:'2026-10-22',date_label:'22 October',
                course:'English',course_url:'course1',description:'Практика',status:'Absent',kind:'absent'}]});
        }""")
        self.page.locator('#attendanceCourse').select_option('course1')
        self.page.locator('[data-day="2026-10-22"]').click()
        for language, month in [('en', 'October 2026'), ('ru', 'октябрь 2026')]:
            self.page.locator('header .language-select').select_option(language)
            expect(self.page.locator('.att-month-title')).to_contain_text(month)
            expect(self.page.locator('[data-day="2026-10-22"]')).to_have_attribute('aria-pressed', 'true')
            expect(self.page.locator('#attendanceCourse')).to_have_value('course1')
            expect(self.page.locator('.att-session h3')).to_have_text('English')
            expect(self.page.locator('.att-status')).to_have_text('Absent')
            expect(self.page.locator('.att-session-top p')).to_have_text('Практика')

    def test_language_persists_and_new_labels_use_current_locale(self):
        self.page.locator('header .language-select').select_option('en')
        self.page.reload()
        self.page.wait_for_function("typeof classmatesBaseLoad === 'function' && connected")
        expect(self.page.locator('html')).to_have_attribute('lang', 'en')
        self.page.locator('header .language-select').select_option('ru')
        self.page.evaluate("loadContent('clubs')")
        expect(self.page.locator('#pageTitle')).to_have_text('Клубы')
        expect(self.page.get_by_role('checkbox', name='Мой клуб: Robotics', exact=True)).to_be_visible()
        expect(self.page.locator('.language-select option[value=en]').first).to_have_text('EN')

    def test_teacher_language_updates_dates_and_summary_without_losing_search(self):
        lesson = {'id': 1, 'course': 'English', 'group': 'SE-1', 'room': '101', 'building': 'Campus',
                  'starts_at': '2026-01-10T09:00:00+05:00', 'ends_at': '2026-01-10T10:00:00+05:00'}
        self.page.route('**/api/teacher/workspace', lambda route: route.fulfill(json={
            'teacher': {'name': 'Teacher', 'username': 'teacher'}, 'source': 'fixture',
            'lessons': [lesson], 'current_lesson_id': 1, 'next_lesson_id': None}))
        self.page.route('**/api/teacher/lessons/1/students', lambda route: route.fulfill(json={
            'students': [{'id': 1, 'name': 'English', 'group': 'SE-1', 'status': 'present'}]}))
        self.page.evaluate('openTeacher()')
        self.page.locator('#teacherSearch').fill('English')
        self.page.locator('header .language-select').select_option('en')
        expect(self.page.locator('#teacherLesson option')).to_contain_text('10 January')
        expect(self.page.locator('#teacherSummary')).to_have_text('Marked 1 / 1 · present 1 · absent 0')
        expect(self.page.locator('#teacherSearch')).to_have_value('English')
        expect(self.page.locator('.teacher-student h3')).to_have_text('English')

    def test_teacher_course_title_and_unsaved_work_survive_language_change(self):
        self.page.evaluate("""() => {
            teacherGroups=[{name:'SE-1',courses:[{id:1,title:'Practice'}]}];
            featureShell('teacher-homework');
            renderTeacherCreateForm($('document'),'homework','teacher-homework',$('document'));
        }""")
        self.page.locator('#assessmentTitle').fill('Unsaved draft')
        self.page.locator('#assessmentDescription').fill('Original instructions')
        for language in ('ru', 'en', 'ru'):
            self.page.locator('header .language-select').select_option(language)
            expect(self.page.locator('#assessmentCourse option')).to_have_text('Practice')
            expect(self.page.locator('#assessmentTitle')).to_have_value('Unsaved draft')
            expect(self.page.locator('#assessmentDescription')).to_have_value('Original instructions')

    def test_iphone_install_is_visible_without_drawer_or_browser_prompt(self):
        button = self.page.locator('header .pwa-install')
        expect(button).to_be_visible()
        button.click()
        expect(self.page.locator('.pwa-help')).to_be_visible()
        expect(self.page.locator('.pwa-help')).to_contain_text('Safari')
        expect(self.page.locator('.pwa-help')).to_contain_text('На экран Домой')
        for width in (320, 390, 1440):
            self.page.set_viewport_size({'width': width, 'height': 844})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            self.assertTrue(self.page.locator('header').evaluate('(e) => e.scrollWidth <= e.clientWidth'))
        self.clubs()
        self.page.set_viewport_size({'width': 320, 'height': 844})
        expect(button).to_be_visible()
        self.assertTrue(self.page.locator('header').evaluate('(e) => e.scrollWidth <= e.clientWidth'))

    def test_install_instructions_match_platform_and_hide_when_installed(self):
        for agent, setup, expected in [
            ('Mozilla/5.0 Android', '', 'На Android'),
            ('Mozilla/5.0 X11 Linux x86_64', '', 'Chrome или Edge'),
            ('Mozilla/5.0 Macintosh', "Object.defineProperty(navigator,'platform',{value:'MacIntel'});Object.defineProperty(navigator,'maxTouchPoints',{value:5});", 'iPhone или iPad'),
            ('Mozilla/5.0 iPhone', "Object.defineProperty(navigator,'standalone',{value:true});", None),
        ]:
            with self.subTest(agent=agent, expected=expected):
                context = self.browser.new_context(user_agent=agent, service_workers='block')
                try:
                    context.route('**/*', self.route)
                    page = context.new_page()
                    page.on('pageerror', lambda error: self.errors.append(str(error)))
                    if setup:
                        page.add_init_script(setup)
                    page.goto('https://bridge.test/')
                    page.wait_for_function("typeof classmatesBaseLoad === 'function'")
                    button = page.locator('header .pwa-install')
                    if expected:
                        button.click()
                        expect(page.locator('.pwa-help')).to_contain_text(expected)
                    else:
                        expect(button).to_be_hidden()
                finally:
                    context.close()

    def test_install_dismissal_and_failure_keep_manual_help_available(self):
        self.page.evaluate("""() => {
            const event = new Event('beforeinstallprompt', {cancelable: true});
            event.prompt = async () => {};
            event.userChoice = Promise.resolve({outcome: 'dismissed'});
            window.dispatchEvent(event);
        }""")
        button = self.page.locator('header .pwa-install')
        button.click()
        expect(button).to_be_visible()
        button.click()
        expect(self.page.locator('.pwa-help')).to_be_visible()
        self.page.evaluate("""() => {
            const event = new Event('beforeinstallprompt', {cancelable: true});
            event.prompt = async () => {throw new Error('Prompt unavailable')};
            window.dispatchEvent(event);
        }""")
        button.click()
        expect(button).to_be_enabled()
        expect(self.page.locator('.pwa-help')).to_be_visible()
        self.page.evaluate("window.dispatchEvent(new Event('appinstalled'))")
        expect(button).to_be_hidden()
        expect(self.page.locator('.pwa-help')).to_be_hidden()


if __name__ == '__main__':
    unittest.main()
