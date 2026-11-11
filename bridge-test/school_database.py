"""Read-only access to the project's existing school database (never imports its app)."""
import asyncio
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from student_cache import ASTANA

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLES = ('students', 'staff_accounts', 'instructors', 'courses', 'groups',
          'enrollments', 'schedule', 'attendance_records', 'rooms', 'preferences')


class SchoolAccessError(LookupError):
    pass


class SchoolDatabase:
    def __init__(self, url=None):
        config = dotenv_values(PROJECT_ROOT / '.env')
        self.url = url or os.environ.get('BRIDGE_SCHOOL_DATABASE_URL') or os.environ.get('DATABASE_URL') or config.get('DATABASE_URL')
        if not self.url:
            raise RuntimeError('Configure DATABASE_URL in the project .env')
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            options = {'connect_timeout': 3, 'read_timeout': 5, 'write_timeout': 5} if self.url.startswith(('mysql', 'mariadb')) else {}
            self._engine = create_engine(self.url, pool_pre_ping=True, pool_size=3,
                                         max_overflow=2, pool_timeout=5, connect_args=options)
        return self._engine

    async def call(self, operation):
        def read():
            with self.engine.connect() as db:
                # This module issues SELECT statements only; closing rolls back the transaction.
                return operation(db)
        return await asyncio.to_thread(read)

    async def close(self):
        if self._engine:
            await asyncio.to_thread(self._engine.dispose)
            self._engine = None

    @staticmethod
    def _teacher(db, teacher_id):
        row = db.execute(text('''SELECT a.id, a.username, a.instructor_id,
                    i.first_name, i.last_name FROM staff_accounts a
                    JOIN instructors i ON i.id=a.instructor_id
                    WHERE a.id=:id AND a.role='teacher' AND a.is_active=1'''), {'id': teacher_id}).mappings().first()
        if row is None:
            raise SchoolAccessError('Аккаунт преподавателя не найден или отключён.')
        return dict(row)

    async def workspace(self):
        def read(db):
            row = db.execute(text("""SELECT id FROM staff_accounts WHERE role='teacher' AND is_active=1
                         ORDER BY CASE WHEN username='teacher004' THEN 0 ELSE 1 END, id LIMIT 1""")).first()
            if row is None:
                raise SchoolAccessError('В учебной базе нет активного преподавателя.')
            teacher = self._teacher(db, row[0])
            lessons = [dict(item) for item in db.execute(text('''
                SELECT sc.id, sc.course_id, c.title AS course, g.name AS `group`,
                       r.name AS room, r.building, sc.weekday, sc.starts_at, sc.ends_at, sc.lesson_date
                FROM schedule sc JOIN courses c ON c.id=sc.course_id
                JOIN `groups` g ON g.id=sc.group_id JOIN rooms r ON r.id=sc.room_id
                WHERE c.instructor_id=:instructor ORDER BY sc.weekday, sc.starts_at, sc.id
            '''), {'instructor': teacher['instructor_id']}).mappings()]
            now = datetime.now(ASTANA)
            for lesson in lessons:
                def clock(value):
                    if isinstance(value, timedelta):
                        seconds = int(value.total_seconds())
                        return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)
                    return time.fromisoformat(value) if isinstance(value, str) else value
                start, end = clock(lesson['starts_at']), clock(lesson['ends_at'])
                fixed = lesson.pop('lesson_date')
                if isinstance(fixed, str):
                    fixed = date.fromisoformat(fixed)
                day = fixed or (now.date() + timedelta(days=(lesson['weekday']-now.weekday()) % 7))
                begins, ends = datetime.combine(day, start, ASTANA), datetime.combine(day, end, ASTANA)
                if not fixed and ends <= now:
                    begins += timedelta(days=7)
                    ends += timedelta(days=7)
                lesson.update(course_id=str(lesson['course_id']), starts_at=begins.isoformat(), ends_at=ends.isoformat())
            lessons.sort(key=lambda item: (item['starts_at'], item['id']))
            return {'teacher': {'id': teacher['id'], 'instructor_id': teacher['instructor_id'],
                                'name': teacher['first_name']+' '+teacher['last_name'],
                                'username': teacher['username'], 'role': 'teacher'},
                    'demo': True, 'source': self.engine.url.database, 'lessons': lessons, 'attendance': {}}
        return await self.call(read)

    async def catalog(self, teacher_id):
        def read(db):
            teacher = self._teacher(db, teacher_id)
            instructor = teacher['instructor_id']
            courses = {str(row['id']): row['title'] for row in db.execute(text(
                'SELECT id,title FROM courses WHERE instructor_id=:instructor ORDER BY title'),
                {'instructor': instructor}).mappings()}
            rows = db.execute(text('''
                SELECT DISTINCT g.name, c.id AS course_id FROM courses c
                JOIN schedule sc ON sc.course_id=c.id JOIN `groups` g ON g.id=sc.group_id
                WHERE c.instructor_id=:instructor
                UNION
                SELECT DISTINCT g.name, c.id AS course_id FROM courses c
                JOIN enrollments e ON e.course_id=c.id JOIN students s ON s.id=e.student_id
                JOIN `groups` g ON g.id=s.group_id
                WHERE c.instructor_id=:instructor AND s.is_active=1
            '''), {'instructor': instructor}).mappings()
            groups = {}
            for row in rows:
                groups.setdefault(row['name'], []).append(str(row['course_id']))
            return {'courses': courses, 'groups': dict(sorted(groups.items()))}
        return await self.call(read)

    async def students(self, teacher_id, group=None, course_id=None):
        def read(db):
            teacher = self._teacher(db, teacher_id)
            rows = db.execute(text('''
                SELECT DISTINCT s.id, s.first_name, s.last_name, g.name AS `group`
                FROM students s JOIN `groups` g ON g.id=s.group_id
                JOIN enrollments e ON e.student_id=s.id JOIN courses c ON c.id=e.course_id
                WHERE c.instructor_id=:instructor AND s.is_active=1
                AND (:group_name IS NULL OR g.name=:group_name)
                AND (:course_id IS NULL OR c.id=:course_id)
                ORDER BY g.name, s.last_name, s.first_name, s.id
            '''), {'instructor': teacher['instructor_id'], 'group_name': group, 'course_id': course_id}).mappings()
            return [{'id': row['id'], 'name': row['first_name']+' '+row['last_name'], 'group': row['group']} for row in rows]
        return await self.call(read)

    async def overview(self):
        def read(db):
            counts = {table: db.execute(text(f'SELECT COUNT(*) FROM `{table}`')).scalar_one() for table in TABLES}
            active_students = db.execute(text('SELECT COUNT(*) FROM students WHERE is_active=1')).scalar_one()
            staff = {row['role']: row['total'] for row in db.execute(text(
                'SELECT role,COUNT(*) AS total FROM staff_accounts GROUP BY role')).mappings()}
            groups = [dict(row) for row in db.execute(text('''SELECT g.name, COUNT(s.id) AS students
                FROM `groups` g LEFT JOIN students s ON s.group_id=g.id GROUP BY g.id,g.name ORDER BY g.name''')).mappings()]
            teachers = [dict(row) for row in db.execute(text('''
                SELECT a.username,i.first_name,i.last_name,COUNT(DISTINCT c.id) AS courses,
                       COUNT(DISTINCT s.id) AS students
                FROM staff_accounts a JOIN instructors i ON i.id=a.instructor_id
                LEFT JOIN courses c ON c.instructor_id=i.id LEFT JOIN enrollments e ON e.course_id=c.id
                LEFT JOIN students s ON s.id=e.student_id AND s.is_active=1
                WHERE a.role='teacher' AND a.is_active=1
                GROUP BY a.id,a.username,i.first_name,i.last_name ORDER BY a.username
            ''')).mappings()]
            size = None
            if self.engine.dialect.name in {'mysql', 'mariadb'}:
                size = db.execute(text('''SELECT COALESCE(SUM(data_length+index_length),0)
                    FROM information_schema.tables WHERE table_schema=DATABASE()''')).scalar_one()
            return {'status': 'ok', 'engine': self.engine.dialect.name, 'name': self.engine.url.database,
                    'size_bytes': int(size) if size is not None else None,
                    'counts': {**counts, 'active_students': active_students, 'teachers': staff.get('teacher', 0), 'admins': staff.get('admin', 0)},
                    'tables': [{'name': name, 'rows': count} for name, count in counts.items()],
                    'groups': groups, 'teachers': teachers}
        return await self.call(read)
