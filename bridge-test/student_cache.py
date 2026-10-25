"""Student snapshots and encrypted, revocable browser sessions."""
import asyncio
import json
import re
import sqlite3
import threading
import hashlib
import os
from cryptography.fernet import Fernet, InvalidToken
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ASTANA = ZoneInfo("Asia/Almaty")


def utc_now():
    return datetime.now(timezone.utc)


def next_midnight(now):
    local = now.astimezone(ASTANA)
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def fresh_today(stamp, now):
    saved = datetime.fromisoformat(stamp)
    return saved <= now and saved.astimezone(ASTANA).date() == now.astimezone(ASTANA).date()


def normalize_email(value):
    email = str(value).strip().casefold()
    if len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Invalid verified email")
    return email


class StudentCache:
    def __init__(self, path, clock=utc_now):
        self.path = Path(path)
        self.clock = clock
        self._ready = False
        self._init_lock = threading.Lock()
        self._key_lock = threading.Lock()

    def _connect(self):
        with self._init_lock:
            if not self._ready:
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with closing(sqlite3.connect(self.path, timeout=10)) as db:
                    self.path.chmod(0o600)
                    db.execute("PRAGMA journal_mode=WAL")
                    db.executescript("""
                        CREATE TABLE IF NOT EXISTS students (
                            email TEXT PRIMARY KEY,
                            student_number TEXT,
                            moodle_user_id INTEGER NOT NULL,
                            first_name TEXT NOT NULL,
                            last_name TEXT NOT NULL,
                            display_name TEXT NOT NULL,
                            courses_json TEXT NOT NULL,
                            refreshed_at TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS selected_clubs (
                            email TEXT NOT NULL REFERENCES students(email) ON DELETE CASCADE,
                            title TEXT NOT NULL,
                            PRIMARY KEY(email, title)
                        );
                        CREATE TABLE IF NOT EXISTS catalog (
                            id INTEGER PRIMARY KEY CHECK(id=1),
                            payload TEXT NOT NULL,
                            refreshed_at TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS documents (
                            email TEXT NOT NULL REFERENCES students(email) ON DELETE CASCADE,
                            section TEXT NOT NULL,
                            url TEXT NOT NULL,
                            payload TEXT NOT NULL,
                            refreshed_at TEXT NOT NULL,
                            PRIMARY KEY(email, section, url)
                        );
                        CREATE TABLE IF NOT EXISTS remembered_sessions (
                            token_hash TEXT PRIMARY KEY,
                            email TEXT NOT NULL REFERENCES students(email) ON DELETE CASCADE,
                            moodle_user_id INTEGER NOT NULL,
                            expires_at REAL NOT NULL,
                            browser_state BLOB NOT NULL
                        );
                        PRAGMA user_version=2;
                    """)
                    db.commit()
                self._ready = True
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    async def _call(self, function):
        def run():
            with closing(self._connect()) as db, db:
                return function(db)
        return await asyncio.to_thread(run)

    async def get(self, email, moodle_user_id):
        email = normalize_email(email)
        def read(db):
            row = db.execute("SELECT * FROM students WHERE email=? AND moodle_user_id=?",
                             (email, moodle_user_id)).fetchone()
            if row is None:
                return None
            data = dict(row)
            data["courses"] = json.loads(data.pop("courses_json"))
            data["clubs"] = [r[0] for r in db.execute(
                "SELECT title FROM selected_clubs WHERE email=? ORDER BY title", (email,))]
            data["stale"] = not fresh_today(data["refreshed_at"], self.clock())
            data["next_refresh_at"] = next_midnight(self.clock()).isoformat()
            return data
        return await self._call(read)

    async def save(self, identity, courses):
        email = normalize_email(identity["email"])
        match = re.match(r"^(\d{6})(?!\d)", email.split("@")[0])
        number = match.group(1) if match else None
        stamp = self.clock().isoformat()
        # Only a whitelist of profile and course fields is persisted.
        from moodle_reader import content_url
        clean, seen = [], set()
        for course in courses:
            target = content_url(course["url"], "https://lms.astanait.edu.kz")
            if "/course/view.php?" not in target or target in seen:
                continue
            seen.add(target)
            clean.append({"title": str(course["title"])[:500], "url": target})
        def write(db):
            existing = db.execute("SELECT moodle_user_id FROM students WHERE email=?", (email,)).fetchone()
            if existing and existing[0] != identity["moodle_user_id"]:
                raise ValueError("Verified Moodle identity changed for this email")
            db.execute("""INSERT INTO students VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET
                student_number=excluded.student_number, first_name=excluded.first_name,
                last_name=excluded.last_name, display_name=excluded.display_name,
                courses_json=excluded.courses_json, refreshed_at=excluded.refreshed_at""",
                (email, number, int(identity["moodle_user_id"]), str(identity.get("first_name", ""))[:200],
                 str(identity.get("last_name", ""))[:200], str(identity["display_name"])[:400],
                 json.dumps(clean, ensure_ascii=False), stamp))
        await self._call(write)
        return await self.get(email, identity["moodle_user_id"])

    async def community(self, source, force=False):
        now = self.clock()
        def read(db):
            row = db.execute("SELECT payload, refreshed_at FROM catalog WHERE id=1").fetchone()
            if force or row is None or not fresh_today(row["refreshed_at"], now):
                data = json.loads(Path(source).read_text())
                stamp = now.isoformat()
                db.execute("INSERT INTO catalog VALUES(1,?,?) ON CONFLICT(id) DO UPDATE "
                           "SET payload=excluded.payload, refreshed_at=excluded.refreshed_at",
                           (json.dumps(data, ensure_ascii=False), stamp))
            else:
                data, stamp = json.loads(row["payload"]), row["refreshed_at"]
            return {**data, "cache_updated_at": stamp}
        return await self._call(read)

    async def select_club(self, email, moodle_user_id, title, selected, allowed):
        email = normalize_email(email)
        if title not in allowed:
            raise ValueError("Unknown club")
        def write(db):
            if not db.execute("SELECT 1 FROM students WHERE email=? AND moodle_user_id=?",
                              (email, moodle_user_id)).fetchone():
                raise ValueError("Profile is not cached")
            if selected:
                db.execute("INSERT OR IGNORE INTO selected_clubs VALUES(?,?)", (email, title))
            else:
                db.execute("DELETE FROM selected_clubs WHERE email=? AND title=?", (email, title))
        await self._call(write)

    async def document(self, email, moodle_user_id, section, url):
        def read(db):
            row = db.execute("""SELECT d.payload, d.refreshed_at FROM documents d
                JOIN students s ON s.email=d.email WHERE d.email=? AND s.moodle_user_id=?
                AND d.section=? AND d.url=?""", (email, moodle_user_id, section, url)).fetchone()
            if row is None:
                return None
            data = json.loads(row["payload"])
            return {**data, "cached": True, "cache_source": "database",
                    "cache_updated_at": row["refreshed_at"],
                    "cache_stale": not fresh_today(row["refreshed_at"], self.clock()),
                    "updated": datetime.fromisoformat(row["refreshed_at"]).astimezone(ASTANA).strftime("%d.%m.%Y %H:%M")}
        return await self._call(read)

    async def save_document(self, identity, section, url, data):
        # Explicit field list excludes browser state, credentials and arbitrary request fields.
        fields = {"title", "profile", "text", "paragraphs", "tables", "timeline", "grades",
                  "courses", "activities", "attendance_view", "table_headers", "demo", "section", "detail", "warnings", "url", "updated"}
        clean = {key: value for key, value in data.items() if key in fields}
        if clean.get("demo"):
            return
        stamp = self.clock().isoformat()
        def write(db):
            if not db.execute("SELECT 1 FROM students WHERE email=? AND moodle_user_id=?",
                              (identity["email"], identity["moodle_user_id"])).fetchone():
                raise ValueError("Profile is not cached")
            db.execute("""INSERT INTO documents VALUES(?,?,?,?,?)
                ON CONFLICT(email,section,url) DO UPDATE SET payload=excluded.payload,
                refreshed_at=excluded.refreshed_at""",
                (identity["email"], section, url, json.dumps(clean, ensure_ascii=False), stamp))
            db.execute("""DELETE FROM documents WHERE email=? AND rowid NOT IN
                (SELECT rowid FROM documents WHERE email=? ORDER BY refreshed_at DESC, rowid DESC LIMIT 30)""",
                (identity["email"], identity["email"]))
        await self._call(write)

    async def document_keys(self, email, moodle_user_id):
        return await self._call(lambda db: [
            (row["section"], row["url"]) for row in db.execute("""
                SELECT d.section,d.url FROM documents d JOIN students s ON s.email=d.email
                WHERE d.email=? AND s.moodle_user_id=? ORDER BY d.refreshed_at DESC""",
                (email, moodle_user_id))])

    def _cipher(self, create=False):
        path = self.path.with_suffix(".key")
        with self._key_lock:
            if not path.exists():
                if not create:
                    return None
                key = Fernet.generate_key()
                try:
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(key)
            return Fernet(path.read_bytes())

    async def remember(self, token, identity, state, expires_at):
        digest = hashlib.sha256(token.encode()).hexdigest()
        def write(db):
            if not db.execute("SELECT 1 FROM students WHERE email=? AND moodle_user_id=?",
                              (identity["email"], identity["moodle_user_id"])).fetchone():
                return False
            envelope = {"token_hash":digest, "email":identity["email"],
                        "moodle_user_id":identity["moodle_user_id"], "state":state}
            encrypted = self._cipher(create=True).encrypt(json.dumps(envelope).encode())
            db.execute("""INSERT INTO remembered_sessions VALUES(?,?,?,?,?)
                ON CONFLICT(token_hash) DO UPDATE SET email=excluded.email,
                moodle_user_id=excluded.moodle_user_id, expires_at=excluded.expires_at,
                browser_state=excluded.browser_state""",
                (digest, identity["email"], identity["moodle_user_id"], expires_at, encrypted))
            db.execute("DELETE FROM remembered_sessions WHERE expires_at<=?", (self.clock().timestamp(),))
            return True
        return await self._call(write)

    async def remembered(self, token):
        if not token or len(token) > 128:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        def read(db):
            row = db.execute("""SELECT r.*, s.first_name, s.last_name, s.display_name
                FROM remembered_sessions r JOIN students s ON s.email=r.email
                AND s.moodle_user_id=r.moodle_user_id WHERE token_hash=? AND expires_at>?""",
                (digest,self.clock().timestamp())).fetchone()
            if row is None:
                return None
            identity = {key:row[key] for key in ("email","moodle_user_id","first_name","last_name","display_name")}
            state = None
            try:
                cipher = self._cipher()
                if cipher:
                    data = json.loads(cipher.decrypt(row["browser_state"]))
                    if all(data.get(k)==row[k] for k in ("token_hash","email","moodle_user_id")):
                        state = data["state"]
            except (InvalidToken, ValueError, OSError):
                pass
            return {"identity":identity, "state":state, "expires_at":row["expires_at"]}
        return await self._call(read)

    async def forget(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        await self._call(lambda db: db.execute("DELETE FROM remembered_sessions WHERE token_hash=?", (digest,)))
