"""Isolated demo coursework, authorized against the school database's enrolments."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta
import sqlite3
import re
from teacher_demo import ASTANA

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ASSESSMENT_FILES = 10
FILE_CHUNK_BYTES = 4 * 1024 * 1024



class TeacherRecords:
    def __init__(self, path, school, teacher_id, database=None):
        self.database = database
        self.path = path
        self.school = school
        self.teacher_id = teacher_id

    async def call(self, operation):
        def run():
            if self.database is not None:
                with self.database.connection("teacher") as db:
                    return operation(db)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                self.path.chmod(0o600)
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys=ON')
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS assessments (
                        id INTEGER PRIMARY KEY, owner TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('midterm','endterm','final','homework')),
                        group_name TEXT NOT NULL, course_id TEXT NOT NULL,
                        title TEXT NOT NULL, description TEXT NOT NULL,
                        scheduled_at TEXT NOT NULL, duration_minutes INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS teacher_assessments_owner ON assessments(owner);
                    CREATE TABLE IF NOT EXISTS assessment_files (
                        id INTEGER PRIMARY KEY,
                        assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                        filename TEXT NOT NULL, size INTEGER NOT NULL,
                        content BLOB NOT NULL, uploaded_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS teacher_files_assessment ON assessment_files(assessment_id);
                    CREATE TABLE IF NOT EXISTS assessment_grades (
                        assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
                        student_id INTEGER NOT NULL,
                        grade REAL CHECK(grade IS NULL OR (grade>=0 AND grade<=100)),
                        comment TEXT NOT NULL, updated_at TEXT NOT NULL,
                        PRIMARY KEY(assessment_id, student_id)
                    );
                ''')
                return operation(db)
        return await asyncio.to_thread(run)

    @staticmethod
    def view(row, now=None, courses=None):
        item = dict(row)
        item.pop('owner', None)
        item.setdefault('file_count', 0)
        item['course'] = (courses or {}).get(item['course_id'], item['course_id'])
        end = datetime.fromisoformat(item['scheduled_at']) + timedelta(minutes=item['duration_minutes'])
        item['ends_at'] = end.isoformat()
        item['can_grade'] = item['kind'] == 'homework' or (now or datetime.now(ASTANA)) >= end
        return item

    async def create(self, owner, payload):
        catalog = await self.school.catalog(self.teacher_id)
        if payload.course_id not in catalog['groups'].get(payload.group, []):
            raise ValueError('Курс не назначен этой группе.')
        title = payload.title.strip()
        if not title:
            raise ValueError('Укажи название работы.')
        def write(db):
            cursor = db.execute('''INSERT INTO assessments
                (owner,kind,group_name,course_id,title,description,scheduled_at,duration_minutes,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (owner,payload.kind,payload.group,payload.course_id,title,payload.description.strip(),
                 payload.scheduled_at.astimezone(ASTANA).isoformat(),
                 payload.duration_minutes if payload.kind != 'homework' else 0,
                 datetime.now(ASTANA).isoformat()))
            return self.view(db.execute('SELECT * FROM assessments WHERE id=?', (cursor.lastrowid,)).fetchone(), courses=catalog['courses'])
        return await self.call(write)

    async def listing(self, owner, category, group):
        catalog = await self.school.catalog(self.teacher_id)
        if group is not None and group not in catalog['groups']:
            raise ValueError('Группа не найдена.')
        def read(db):
            rows = db.execute('SELECT a.*, (SELECT COUNT(*) FROM assessment_files f WHERE f.assessment_id=a.id) AS file_count FROM assessments a WHERE owner=? ORDER BY scheduled_at DESC, id DESC', (owner,)).fetchall()
            return [self.view(row, courses=catalog['courses']) for row in rows
                    if row['course_id'] in catalog['groups'].get(row['group_name'], [])
                    and (group is None or row['group_name'] == group)
                    and (category is None or (row['kind'] == 'homework') == (category == 'homework'))]
        return await self.call(read)

    async def detail(self, owner, assessment_id):
        catalog = await self.school.catalog(self.teacher_id)
        def read(db):
            row = db.execute('SELECT * FROM assessments WHERE id=? AND owner=?', (assessment_id, owner)).fetchone()
            if row is None or row['course_id'] not in catalog['groups'].get(row['group_name'], []):
                raise LookupError('Работа не найдена.')
            grades = {mark['student_id']: dict(mark) for mark in db.execute(
                'SELECT student_id,grade,comment,updated_at FROM assessment_grades WHERE assessment_id=?', (assessment_id,))}
            files = [dict(file) for file in db.execute('SELECT id,filename,size,uploaded_at FROM assessment_files WHERE assessment_id=? ORDER BY id', (assessment_id,))]
            item = self.view(row, courses=catalog['courses'])
            item['file_count'] = len(files)
            return {'assessment': item, 'grades': grades, 'files': files}
        result = await self.call(read)
        item = result['assessment']
        students = await self.school.students(self.teacher_id, item['group_name'], item['course_id'])
        grades = result.pop('grades')
        result['students'] = [{**student, 'grade': grades.get(student['id'], {}).get('grade'),
                              'comment': grades.get(student['id'], {}).get('comment', ''),
                              'updated_at': grades.get(student['id'], {}).get('updated_at')} for student in students]
        return result

    async def grade(self, owner, assessment_id, payload):
        detail = await self.detail(owner, assessment_id)
        if payload.student_id not in {student['id'] for student in detail['students']}:
            raise LookupError('Ученик не относится к этой группе и курсу.')
        def write(db):
            # One transaction owns authorization, validation and the write.
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM assessments WHERE id=? AND owner=?', (assessment_id, owner)).fetchone()
            if row is None:
                raise LookupError('Работа не найдена.')
            if not self.view(row)['can_grade']:
                raise ValueError('Экзамен ещё не завершён. Оценки можно выставить после окончания.')
            stamp = datetime.now(ASTANA).isoformat()
            db.execute('''INSERT INTO assessment_grades (assessment_id,student_id,grade,comment,updated_at)
                VALUES (?,?,?,?,?) ON CONFLICT(assessment_id,student_id) DO UPDATE SET
                grade=excluded.grade,comment=excluded.comment,updated_at=excluded.updated_at''',
                (assessment_id,payload.student_id,payload.grade,payload.comment.strip(),stamp))
            return {'ok': True, 'grade': payload.grade, 'comment': payload.comment.strip(), 'updated_at': stamp}
        return await self.call(write)


    async def require_assessment(self, owner, assessment_id):
        def read(db):
            if not db.execute('SELECT 1 FROM assessments WHERE id=? AND owner=?', (assessment_id, owner)).fetchone():
                raise LookupError('Работа не найдена.')
        await self.call(read)

    async def add_file(self, owner, assessment_id, filename, content):
        # Store bytes and metadata together; no user-provided filesystem paths.
        filename = re.split(r'[/\\]', filename)[-1]
        filename = ''.join(c for c in filename if ord(c) >= 32 and ord(c) != 127).strip()
        if not filename or filename in {'.', '..'} or len(filename) > 255:
            raise ValueError('Укажи корректное имя файла (до 255 символов).')
        if not content:
            raise ValueError('Нельзя загрузить пустой файл.')
        if len(content) > MAX_FILE_BYTES:
            raise ValueError('Размер файла превышает 20 МБ.')
        def write(db):
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM assessments WHERE id=? AND owner=?', (assessment_id, owner)).fetchone():
                raise LookupError('Работа не найдена.')
            count = db.execute('SELECT COUNT(*) FROM assessment_files WHERE assessment_id=?', (assessment_id,)).fetchone()[0]
            if count >= MAX_ASSESSMENT_FILES:
                raise ValueError('К работе можно прикрепить не более 10 файлов.')
            stamp = datetime.now(ASTANA).isoformat()
            cursor = db.execute('INSERT INTO assessment_files (assessment_id,filename,size,content,uploaded_at) VALUES (?,?,?,?,?)',
                                (assessment_id, filename, len(content), sqlite3.Binary(content[:FILE_CHUNK_BYTES] if self.database is not None else content), stamp))
            file_id = cursor.lastrowid
            if self.database is not None:
                for position, offset in enumerate(range(FILE_CHUNK_BYTES, len(content), FILE_CHUNK_BYTES), 1):
                    db.execute("INSERT INTO assessment_file_chunks (file_id,position,content) VALUES (?,?,?)",
                               (file_id, position, content[offset:offset+FILE_CHUNK_BYTES]))
            return {'id': file_id, 'filename': filename, 'size': len(content), 'uploaded_at': stamp}
        return await self.call(write)

    async def download_file(self, owner, assessment_id, file_id):
        def read(db):
            row = db.execute('SELECT f.filename,f.content FROM assessment_files f JOIN assessments a ON a.id=f.assessment_id WHERE f.id=? AND f.assessment_id=? AND a.owner=?',
                             (file_id, assessment_id, owner)).fetchone()
            if row is None:
                raise LookupError('Файл не найден.')
            content = bytes(row['content'])
            if self.database is not None:
                content += b''.join(bytes(chunk['content']) for chunk in db.execute(
                    'SELECT content FROM assessment_file_chunks WHERE file_id=? ORDER BY position', (file_id,)))
            return row['filename'], content
        return await self.call(read)
