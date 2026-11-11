"""MariaDB storage for the bridge's existing small SQL repository interfaces.

Only table identifiers and the explicitly used SQLite DML forms are adapted.
Values always use SQLAlchemy bind parameters. Schema creation and migrations are
explicit deployment steps; a running server never falls back to SQLite.
"""
import re
from contextlib import contextmanager
from sqlalchemy import create_engine, text

SCHEMAS = {
 'bridge': {
  'students': '''email VARCHAR(320) PRIMARY KEY, student_number VARCHAR(32),
   moodle_user_id BIGINT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
   display_name TEXT NOT NULL, courses_json LONGTEXT NOT NULL, refreshed_at VARCHAR(40) NOT NULL''',
  'selected_clubs': '''email VARCHAR(320) NOT NULL, title VARCHAR(400) NOT NULL,
   PRIMARY KEY(email,title), FOREIGN KEY(email) REFERENCES students(email) ON DELETE CASCADE''',
  'hidden_activities': '''email VARCHAR(320) NOT NULL, activity_key CHAR(64) NOT NULL,
   expires_at DOUBLE NOT NULL, PRIMARY KEY(email,activity_key), INDEX activity_expiry(expires_at),
   FOREIGN KEY(email) REFERENCES students(email) ON DELETE CASCADE''',
  'catalog': '''id INT PRIMARY KEY CHECK(id=1), payload LONGTEXT NOT NULL, refreshed_at VARCHAR(40) NOT NULL''',
  'documents': '''id BIGINT PRIMARY KEY AUTO_INCREMENT, email VARCHAR(320) NOT NULL,
   section VARCHAR(64) NOT NULL, url TEXT NOT NULL, payload LONGTEXT NOT NULL, refreshed_at VARCHAR(40) NOT NULL,
   url_hash BINARY(32) GENERATED ALWAYS AS (UNHEX(SHA2(url,256))) STORED,
   UNIQUE KEY document_identity(email,section,url_hash), INDEX document_age(email,refreshed_at,id),
   FOREIGN KEY(email) REFERENCES students(email) ON DELETE CASCADE''',
  'remembered_sessions': '''token_hash VARCHAR(64) PRIMARY KEY, email VARCHAR(320) NOT NULL,
   moodle_user_id BIGINT NOT NULL, expires_at DOUBLE NOT NULL, browser_state LONGBLOB NOT NULL,
   FOREIGN KEY(email) REFERENCES students(email) ON DELETE CASCADE'''
 },
 'teacher': {
  'assessments': '''id BIGINT PRIMARY KEY AUTO_INCREMENT, owner VARCHAR(128) NOT NULL,
   kind VARCHAR(16) NOT NULL CHECK(kind IN ('midterm','endterm','final','homework')),
   group_name VARCHAR(100) NOT NULL, course_id VARCHAR(100) NOT NULL,
   title TEXT NOT NULL, description LONGTEXT NOT NULL, scheduled_at VARCHAR(40) NOT NULL,
   duration_minutes INT NOT NULL, created_at VARCHAR(40) NOT NULL, INDEX assessment_owner(owner)''',
  'assessment_files': '''id BIGINT PRIMARY KEY AUTO_INCREMENT, assessment_id BIGINT NOT NULL,
   filename VARCHAR(255) NOT NULL, size BIGINT NOT NULL, content LONGBLOB NOT NULL,
   uploaded_at VARCHAR(40) NOT NULL, FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE''',
  'assessment_file_chunks': '''file_id BIGINT NOT NULL, position INT NOT NULL, content LONGBLOB NOT NULL,
   PRIMARY KEY(file_id,position), FOREIGN KEY(file_id) REFERENCES assessment_files(id) ON DELETE CASCADE''',
  'assessment_grades': '''assessment_id BIGINT NOT NULL, student_id BIGINT NOT NULL,
   grade DOUBLE CHECK(grade IS NULL OR (grade>=0 AND grade<=100)), comment TEXT NOT NULL,
   updated_at VARCHAR(40) NOT NULL, PRIMARY KEY(assessment_id,student_id),
   FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE'''
 },
 'telegram': {
  'members': '''owner BIGINT PRIMARY KEY, name TEXT NOT NULL, telegram_id BIGINT UNIQUE,
   username VARCHAR(32), main VARCHAR(60) NOT NULL DEFAULT '',
   english VARCHAR(60) NOT NULL DEFAULT '', pe VARCHAR(60) NOT NULL DEFAULT '',
   INDEX main_group(main), INDEX english_group(english), INDEX pe_group(pe)''',
  'links': '''digest VARCHAR(64) PRIMARY KEY, owner BIGINT UNIQUE NOT NULL,
   name TEXT NOT NULL, expires DOUBLE NOT NULL''',
  'bot_state': '''`key` VARCHAR(64) PRIMARY KEY, value BIGINT NOT NULL'''
 }
}


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, result):
        self.result = result
        self.rowcount = result.rowcount
        self.lastrowid = result.lastrowid

    def fetchone(self):
        row = self.result.mappings().fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.result.mappings()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, storage, namespace):
        self.storage, self.namespace = storage, namespace
        self.conn = storage.engine.connect()
        self.transaction = self.conn.begin()
        self.locking = False

    def execute(self, sql, parameters=()):
        if sql.strip().upper() == 'BEGIN IMMEDIATE':
            # The SQL transaction already exists; lock checked rows on subsequent reads.
            self.locking = True
            return None
        sql = re.sub(r'ON CONFLICT\([^)]*\) DO UPDATE SET', 'ON DUPLICATE KEY UPDATE', sql, flags=re.I)
        sql = re.sub(r'\bexcluded\.(\w+)', r'VALUES(\1)', sql)
        if 'INSERT OR IGNORE INTO selected_clubs' in sql:
            sql = sql.replace('INSERT OR IGNORE', 'INSERT') + ' ON DUPLICATE KEY UPDATE title=VALUES(title)'
        if 'INSERT OR REPLACE INTO bot_state' in sql:
            sql = sql.replace('INSERT OR REPLACE', 'INSERT') + ' ON DUPLICATE KEY UPDATE value=VALUES(value)'
        if self.namespace == 'bridge':
            sql = re.sub(r'\browid\b', 'id', sql)
        if self.namespace == 'telegram':
            sql = re.sub(r'\bkey\b', '`key`', sql)
        sql = self.storage.qualify(self.namespace, sql)
        parts = sql.split('?')
        if len(parts)-1 != len(parameters):
            raise ValueError('SQL parameter count mismatch')
        bound = parts[0]
        for i, part in enumerate(parts[1:]):
            bound += ':p'+str(i)+part
        if self.locking and bound.lstrip().upper().startswith('SELECT'):
            bound += ' FOR UPDATE'
        values = {f'p{i}': bytes(v) if isinstance(v, memoryview) else v for i,v in enumerate(parameters)}
        return Result(self.conn.execute(text(bound), values))

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None: self.transaction.commit()
        else: self.transaction.rollback()

    def close(self):
        self.conn.close()


class MariaStorage:
    def __init__(self, url, prefix='aitu_'):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,29}', prefix):
            raise ValueError('Invalid table prefix')
        self.prefix = prefix
        self.engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
            pool_timeout=10, connect_args={'connect_timeout':5, 'read_timeout':60, 'write_timeout':60},
            isolation_level='READ COMMITTED')
        if self.engine.dialect.name not in ('mysql','mariadb'):
            raise ValueError('MariaDB/MySQL URL required')

    def table(self, namespace, name):
        if name not in SCHEMAS[namespace]: raise ValueError('Unknown storage table')
        return self.prefix+namespace+'_'+name

    def qualify(self, namespace, sql):
        names = SCHEMAS[namespace]
        return re.sub(r'\b('+ '|'.join(names) +r')\b',
                      lambda match: '`'+self.table(namespace, match.group())+'`', sql)

    def initialize(self):
        with self.engine.begin() as db:
            for namespace, tables in SCHEMAS.items():
                for name, columns in tables.items():
                    db.execute(text('CREATE TABLE IF NOT EXISTS `'+self.table(namespace,name)+'` ('+
                        self.qualify(namespace, columns)+') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'))

    def connect(self, namespace):
        return Connection(self, namespace)

    @contextmanager
    def connection(self, namespace):
        conn = self.connect(namespace)
        try:
            with conn: yield conn
        finally: conn.close()

    def status(self, namespace):
        from sqlalchemy.exc import SQLAlchemyError
        try:
            with self.engine.connect() as conn:
                tables = [{'name': self.table(namespace,name), 'rows': conn.execute(text(
                    'SELECT COUNT(*) FROM `'+self.table(namespace,name)+'`')).scalar_one()} for name in SCHEMAS[namespace]]
                size = conn.execute(text('''SELECT COALESCE(SUM(data_length+index_length),0)
                    FROM information_schema.tables WHERE table_schema=DATABASE()
                    AND LEFT(table_name,:length)=:prefix'''),
                    {'length':len(self.prefix+namespace+'_'),'prefix':self.prefix+namespace+'_'}).scalar_one()
            return {'status':'ok','engine':'MariaDB','name':self.engine.url.database+' / '+namespace,
                    'tables':tables,'size_bytes':int(size)}
        except SQLAlchemyError:
            return {'status':'unavailable','engine':'MariaDB','name':namespace,'tables':[],'size_bytes':None}

    def drop_test_tables(self):
        if not self.prefix.startswith('test_'): raise ValueError('Only isolated test tables may be dropped')
        try:
            with self.engine.begin() as db:
                for namespace,tables in reversed(list(SCHEMAS.items())):
                    for name in reversed(tables):
                        db.execute(text('DROP TABLE IF EXISTS `'+self.table(namespace,name)+'`'))
        finally: self.engine.dispose()
