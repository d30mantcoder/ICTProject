import tempfile
import unittest
from pathlib import Path
from telegram_groups import TelegramStore


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 1000
        self.db = TelegramStore(Path(self.tmp.name) / 'telegram.sqlite3', lambda: self.now)

    def link(self, owner, telegram):
        code = self.db.issue(owner, 'Student ' + str(owner))
        self.db.consume(code, {'id': telegram, 'username': 'student_' + str(telegram)})
        return code

    def test_single_use_and_expiry(self):
        code = self.link(1, 100)
        with self.assertRaises(ValueError): self.db.consume(code, {'id': 200, 'username': 'other'})
        code = self.db.issue(2, 'Second')
        self.now += 601
        with self.assertRaises(ValueError): self.db.consume(code, {'id': 200, 'username': 'other'})
        self.assertFalse(self.db.profile(2)['linked'])

    def test_new_link_invalidates_previous(self):
        first = self.db.issue(1, 'One')
        second = self.db.issue(1, 'One')
        with self.assertRaises(ValueError): self.db.consume(first, {'id': 100, 'username': 'first'})
        self.db.consume(second, {'id': 100, 'username': 'first'})

    def test_telegram_cannot_belong_to_two_students(self):
        self.link(1, 100)
        code = self.db.issue(2, 'Second')
        with self.assertRaises(ValueError): self.db.consume(code, {'id': 100, 'username': 'student_100'})
        self.assertFalse(self.db.profile(2)['linked'])

    def test_search_requires_link_and_uses_own_tag_per_category(self):
        with self.assertRaises(PermissionError): self.db.search(1, 'main', '')
        for owner in (1, 2, 3): self.link(owner, owner * 100)
        self.db.set_groups(1, {'main': ' SE-2623 ', 'english': 'b2-1', 'pe': 'pe-4'})
        self.db.set_groups(2, {'main': 'se-2623', 'english': 'B2-2', 'pe': 'PE-4'})
        self.db.set_groups(3, {'main': 'SE-2624', 'english': 'B2-1', 'pe': 'PE-5'})
        self.assertEqual([r['username'] for r in self.db.search(1, 'main', '')], ['student_200'])
        self.assertEqual([r['username'] for r in self.db.search(1, 'english', '')], ['student_300'])
        self.assertEqual(len(self.db.search(1, 'pe', '@student_200')), 1)
        self.assertEqual(self.db.search(1, 'main', 'student_300'), [])
        self.assertEqual(self.db.search(1, 'main', '%'), [])
        with self.assertRaises(ValueError): self.db.search(1, 'invalid', '')

    def test_unlink_removes_visibility_and_pending_codes(self):
        self.link(1, 100); self.link(2, 200)
        for owner in (1, 2): self.db.set_groups(owner, {'main': 'A', 'english': '', 'pe': ''})
        code = self.db.issue(2, 'Second')
        self.db.unlink(2)
        self.assertEqual(self.db.search(1, 'main', ''), [])
        with self.assertRaises(ValueError): self.db.consume(code, {'id': 200, 'username': 'second'})

    def test_username_required_and_refreshed(self):
        code = self.db.issue(1, 'One')
        with self.assertRaises(ValueError): self.db.consume(code, {'id': 100})
        self.db.consume(code, {'id': 100, 'username': 'first_name'})
        self.db.refresh_user({'id': 100, 'username': 'new_name'})
        self.assertEqual(self.db.profile(1)['username'], 'new_name')

    def test_persistence(self):
        self.link(1, 100)
        reopened = TelegramStore(self.db.path)
        self.assertEqual(reopened.profile(1)['username'], 'student_100')



class TelegramApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import json
        from types import SimpleNamespace
        from fastapi import FastAPI, Request
        from telegram_groups import TelegramBot, install
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TelegramStore(Path(self.tmp.name) / 'db')
        self.bot = TelegramBot(self.store)
        self.bot.token = ''
        self.web = FastAPI()
        async def authorized(request: Request):
            authenticated = request.headers.get('x-test-auth') == 'yes'
            return SimpleNamespace(login_flow=SimpleNamespace(status={'phase': 'authenticated' if authenticated else 'idle'}),
                identity={'moodle_user_id': 1, 'display_name': 'Test Student'}, teacher_demo=None, admin_demo=False)
        install(self.web, authorized, self.store, self.bot)

    async def request(self, path, body=None, authenticated=True):
        import json
        messages = []
        async def receive(): return {'type': 'http.request', 'body': json.dumps(body).encode() if body is not None else b''}
        async def send(message): messages.append(message)
        scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'POST' if body is not None else 'GET',
                 'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'',
                 'headers':[(b'content-type',b'application/json'),(b'x-test-auth',b'yes' if authenticated else b'no')],
                 'server':('test',80),'client':('test',1),'root_path':''}
        await self.web(scope, receive, send)
        return messages[0]['status'], json.loads(b''.join(m.get('body',b'') for m in messages[1:]))

    async def test_authentication_and_link_gate(self):
        for path, body in [('/api/telegram',None),('/api/telegram/link',{}),('/api/telegram/unlink',{}),
                           ('/api/classmates',None),('/api/classmates/groups',{'main':'a'})]:
            status, _ = await self.request(path, body, False)
            self.assertEqual(status, 401)
        self.assertEqual((await self.request('/api/classmates'))[0],403)
        self.assertEqual((await self.request('/api/classmates/groups',{'main':'a'}))[0],403)
        self.assertEqual((await self.request('/api/telegram/link',{}))[0],503)

    async def test_start_link_groups_and_unlink(self):
        from unittest.mock import Mock
        self.bot.ready = True; self.bot.username = 'test_bot'
        self.bot.request = Mock(return_value={})
        status, link = await self.request('/api/telegram/link',{})
        self.assertEqual(status,200)
        code=link['url'].split('start=')[1]
        message={'text':'/start '+code,'from':{'id':123,'username':'student_123'},'chat':{'id':123,'type':'private'}}
        await self.bot.handle({'message':message})
        self.assertTrue((await self.request('/api/telegram'))[1]['linked'])
        self.assertEqual((await self.request('/api/classmates/groups',{'main':'SE-2623'}))[0],200)
        self.assertEqual((await self.request('/api/telegram/unlink',{}))[0],200)
        self.assertFalse((await self.request('/api/telegram'))[1]['linked'])

    async def test_group_start_cannot_link(self):
        from unittest.mock import Mock
        self.bot.request=Mock()
        code=self.store.issue(1,'One')
        await self.bot.handle({'message':{'text':'/start '+code,'from':{'id':123,'username':'student_123'},'chat':{'id':-1,'type':'group'}}})
        self.assertFalse(self.store.profile(1)['linked'])
        self.bot.request.assert_not_called()

if __name__ == '__main__': unittest.main()
