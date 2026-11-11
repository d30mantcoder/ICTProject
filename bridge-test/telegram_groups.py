"""Verified Telegram linking and opt-in classmate directory, separate from LMS data."""
import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

CATEGORIES = ('main', 'english', 'pe')


def tag(value):
    return ' '.join(unicodedata.normalize('NFKC', value).strip().lstrip('#').split()).casefold()


class TelegramStore:
    def __init__(self, path, clock=time.time, database=None):
        self.path, self.clock = Path(path), clock
        self.database = database
        if database is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS members (
                    owner INTEGER PRIMARY KEY, name TEXT NOT NULL, telegram_id INTEGER UNIQUE,
                    username TEXT, main TEXT NOT NULL DEFAULT '',
                    english TEXT NOT NULL DEFAULT '', pe TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS links (
                    digest TEXT PRIMARY KEY, owner INTEGER UNIQUE NOT NULL,
                    name TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        if self.database is not None:
            with self.database.connection("telegram") as db:
                yield db
            return
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def issue(self, owner, name):
        code = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute('DELETE FROM links WHERE owner=? OR expires<=?', (owner, self.clock()))
            db.execute('INSERT INTO links VALUES (?,?,?,?)',
                       (hashlib.sha256(code.encode()).hexdigest(), owner, name, self.clock()+600))
        return code

    def consume(self, code, user):
        username = user.get('username', '')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', username):
            raise ValueError('Укажи username в настройках Telegram и снова нажми ссылку подключения.')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            link = db.execute('SELECT * FROM links WHERE digest=? AND expires>?',
                              (hashlib.sha256(code.encode()).hexdigest(), self.clock())).fetchone()
            if not link: raise ValueError('Ссылка истекла или уже использована. Создай новую в кабинете AITU.')
            existing = db.execute('SELECT owner FROM members WHERE telegram_id=?', (user['id'],)).fetchone()
            if existing and existing['owner'] != link['owner']:
                raise ValueError('Этот Telegram уже привязан к другому аккаунту. Сначала отключи его там.')
            db.execute('''INSERT INTO members(owner,name,telegram_id,username) VALUES(?,?,?,?)
                ON CONFLICT(owner) DO UPDATE SET name=excluded.name,
                telegram_id=excluded.telegram_id,username=excluded.username''',
                       (link['owner'], link['name'], user['id'], username))
            db.execute('DELETE FROM links WHERE owner=?', (link['owner'],))

    def refresh_user(self, user):
        with self.connection() as db:
            db.execute('UPDATE members SET username=? WHERE telegram_id=?', (user.get('username'), user['id']))

    def profile(self, owner):
        with self.connection() as db:
            row = db.execute('SELECT username,main,english,pe FROM members WHERE owner=?', (owner,)).fetchone()
        return {'linked': bool(row), 'username': row['username'] if row else None,
                'groups': {key: row[key] if row else '' for key in CATEGORIES}}

    def set_groups(self, owner, groups):
        values = [tag(groups[k]) for k in CATEGORIES]
        if any(len(v)>60 or any(unicodedata.category(c).startswith('C') for c in v) for v in values):
            raise ValueError('Тег группы должен быть короче 61 символа и не содержать управляющих символов.')
        with self.connection() as db:
            if not db.execute('UPDATE members SET main=?,english=?,pe=? WHERE owner=?', (*values, owner)).rowcount:
                raise PermissionError('Сначала привяжи Telegram.')
        return self.profile(owner)

    def search(self, owner, category, query):
        if category not in CATEGORIES: raise ValueError('Неизвестный тип группы.')
        profile = self.profile(owner)
        if not profile['linked']: raise PermissionError('Сначала привяжи Telegram.')
        group = profile['groups'][category]
        if not group: return []
        query = query.strip().lstrip('@').casefold()
        with self.connection() as db:
            rows = db.execute(f'''SELECT name,username FROM members WHERE {category}=?
                AND owner!=? AND username IS NOT NULL AND username!='' ORDER BY name,owner''', (group, owner))
            result = []
            for row in rows:
                if query in row['name'].casefold() or query in row['username'].casefold():
                    result.append(dict(row))
                    if len(result) == 100: break
            return result

    def unlink(self, owner):
        with self.connection() as db:
            db.execute('DELETE FROM members WHERE owner=?', (owner,))
            db.execute('DELETE FROM links WHERE owner=?', (owner,))

    def offset(self, value=None):
        with self.connection() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO bot_state VALUES ('offset',?)", (value,))
            row = db.execute("SELECT value FROM bot_state WHERE key='offset'").fetchone()
            return row[0] if row else 0


class TelegramBot:
    def __init__(self, store):
        self.store = store
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
        self.username = None
        self.ready = False

    def request(self, method, payload):
        # Never log exceptions or URLs: the Bot API embeds the secret token in the URL.
        req = Request('https://api.telegram.org/bot'+self.token+'/'+method,
                      json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        with urlopen(req, timeout=35) as response:
            data = json.load(response)
        if not data.get('ok'): raise RuntimeError('Telegram API request failed')
        return data['result']

    async def handle(self, update):
        msg = update.get('message', {})
        user, chat = msg.get('from', {}), msg.get('chat', {})
        if chat.get('type') != 'private' or not user.get('id') or user.get('is_bot'): return
        self.store.refresh_user(user)
        words = msg.get('text', '').split()
        if not words or words[0].split('@')[0] != '/start': return
        reply = 'Для привязки открой «Одногруппники» в кабинете AITU и нажми «Подключить Telegram».'
        if len(words) == 2:
            try:
                self.store.consume(words[1], user)
                reply = 'Telegram привязан! Вернись в кабинет AITU, нажми «Проверить привязку» и укажи свои группы.'
            except ValueError as error: reply = str(error)
        await asyncio.to_thread(self.request, 'sendMessage', {'chat_id': chat['id'], 'text': reply})

    async def run(self):
        if not self.token: return
        while True:
            try:
                if not self.username:
                    me = await asyncio.to_thread(self.request, 'getMe', {})
                    self.username = me['username']
                updates = await asyncio.to_thread(self.request, 'getUpdates',
                    {'offset': self.store.offset(), 'timeout': 20, 'allowed_updates': ['message']})
                if not self.ready:
                    logging.getLogger("uvicorn.error").info("Telegram polling connected (@%s)", self.username)
                self.ready = True
                for update in updates:
                    await self.handle(update)
                    self.store.offset(update['update_id']+1)
            except asyncio.CancelledError: raise
            except Exception:
                self.ready = False
                logging.getLogger(__name__).warning('Telegram polling unavailable; retrying in 10 seconds')
                await asyncio.sleep(10)


class Groups(BaseModel):
    main: str = Field(default='', max_length=60)
    english: str = Field(default='', max_length=60)
    pe: str = Field(default='', max_length=60)


def install(app, authorized, store, bot):
    async def student(session=Depends(authorized)):
        if session.login_flow.status['phase'] != 'authenticated' or not session.identity or session.teacher_demo or session.admin_demo:
            raise HTTPException(401, 'Войди в свой студенческий аккаунт AITU.')
        return session.identity

    @app.get('/api/telegram')
    async def status(identity=Depends(student)):
        return {**store.profile(identity['moodle_user_id']), 'available': bot.ready}

    @app.post('/api/telegram/link')
    async def link(identity=Depends(student)):
        if not bot.ready: raise HTTPException(503, 'Бот пока недоступен. Попробуй позже.')
        code = store.issue(identity['moodle_user_id'], identity['display_name'])
        return {'url': f'https://t.me/{bot.username}?start={code}', 'expires_in': 600}

    @app.post('/api/telegram/unlink')
    async def unlink(identity=Depends(student)):
        store.unlink(identity['moodle_user_id'])
        return {'ok': True}

    @app.post('/api/classmates/groups')
    async def groups(payload: Groups, identity=Depends(student)):
        try: return store.set_groups(identity['moodle_user_id'], payload.model_dump())
        except PermissionError as error: raise HTTPException(403, str(error)) from None
        except ValueError as error: raise HTTPException(422, str(error)) from None

    @app.get('/api/classmates')
    async def classmates(category: str = 'main', q: str = '', identity=Depends(student)):
        if len(q)>100: raise HTTPException(422, 'Поисковый запрос слишком длинный.')
        try: return {'items': store.search(identity['moodle_user_id'], category, q)}
        except PermissionError as error: raise HTTPException(403, str(error)) from None
        except ValueError as error: raise HTTPException(422, str(error)) from None
