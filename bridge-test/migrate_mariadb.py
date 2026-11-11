"""Offline, retry-safe SQLite snapshot/import with full-value verification."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
import subprocess
from datetime import datetime, timezone
from dotenv import dotenv_values
from sqlalchemy import text
from maria_storage import MariaStorage, SCHEMAS
from teacher_records import FILE_CHUNK_BYTES

ROOT = Path(__file__).resolve().parent
SOURCES = {'bridge':'bridge.sqlite3','teacher':'bridge-teacher.sqlite3','telegram':'telegram.sqlite3'}


def digest(rows):
    def value(v):
        if isinstance(v, bytes): return {'bytes':base64.b64encode(v).decode()}
        return v
    encoded = sorted(json.dumps([value(v) for v in row], ensure_ascii=False, separators=(',',':')) for row in rows)
    return hashlib.sha256('\n'.join(encoded).encode()).hexdigest()


def snapshot(source, destination):
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    for filename in SOURCES.values():
        original = source/filename
        if not original.is_file(): raise RuntimeError('Missing source database: '+filename)
        with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(destination/filename)) as dst:
                src.backup(dst)
        (destination/filename).chmod(0o600)
    key = source/'bridge.key'
    if key.is_file():
        shutil.copy2(key,destination/key.name)
        (destination/key.name).chmod(0o600)


def migrate(storage, source):
    storage.initialize()
    manifest = {}
    with storage.engine.begin() as target:
        for namespace, filename in SOURCES.items():
            with closing(sqlite3.connect((source/filename).resolve().as_uri()+'?mode=ro',uri=True)) as src:
                integrity = src.execute('PRAGMA integrity_check').fetchone()[0]
                if integrity != 'ok':raise RuntimeError('SQLite integrity check failed: '+filename)
                if src.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('SQLite foreign key check failed: '+filename)
                for name in SCHEMAS[namespace]:
                    columns = [r[1] for r in src.execute('PRAGMA table_info("'+name+'")')]
                    # Snapshots made before personal activity hiding have no such table.
                    if namespace=='bridge' and name=='hidden_activities' and not columns:
                        continue
                    if namespace=='teacher' and name=='assessment_file_chunks':
                        continue
                    if not columns:raise RuntimeError('Missing source table: '+name)
                    selection = ','.join('"'+c+'"' for c in columns)
                    if namespace=='bridge' and name=='documents':
                        columns=['id']+columns;selection='rowid,'+selection
                    rows=src.execute('SELECT '+selection+' FROM "'+name+'"').fetchall()
                    table=storage.table(namespace,name)
                    quoted=','.join('`'+c+'`' for c in columns)
                    def target_rows():
                        values=[list(row) for row in target.execute(text('SELECT '+quoted+' FROM `'+table+'`'))]
                        if namespace=='teacher' and name=='assessment_files':
                            for row in values:
                                extra=target.execute(text('SELECT content FROM `'+storage.table('teacher','assessment_file_chunks')+'` WHERE file_id=:id ORDER BY position'),{'id':row[columns.index('id')]})
                                row[columns.index('content')]+=b''.join(part[0] for part in extra)
                        return values
                    old=target_rows()
                    if old:
                        if digest(old)!=digest(rows):raise RuntimeError('Target differs; refusing to overwrite '+table)
                    elif rows:
                        statement=text('INSERT INTO `'+table+'` ('+quoted+') VALUES ('+','.join(':v'+str(i) for i in range(len(columns)))+')')
                        for row in rows:
                            values=list(row)
                            if namespace=='teacher' and name=='assessment_files':
                                values[columns.index('content')]=values[columns.index('content')][:FILE_CHUNK_BYTES]
                            target.execute(statement,{f'v{i}':v for i,v in enumerate(values)})
                            if namespace=='teacher' and name=='assessment_files':
                                content=row[columns.index('content')]
                                for position,offset in enumerate(range(FILE_CHUNK_BYTES,len(content),FILE_CHUNK_BYTES),1):
                                    target.execute(text('INSERT INTO `'+storage.table('teacher','assessment_file_chunks')+'` (file_id,position,content) VALUES (:id,:position,:content)'),
                                        {'id':row[columns.index('id')],'position':position,'content':content[offset:offset+FILE_CHUNK_BYTES]})
                    actual=target_rows()
                    if digest(actual)!=digest(rows):raise RuntimeError('Full-value verification failed: '+table)
                    manifest[table]={'rows':len(rows),'sha256':digest(rows)}
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',type=Path,help='Use an existing immutable SQLite snapshot')
    args=parser.parse_args()
    active=subprocess.run(['systemctl','--user','is-active','--quiet','aitu-bridge.service']).returncode==0
    if active:raise RuntimeError('Stop aitu-bridge.service before migration')
    source=args.snapshot
    if source is None:
        source=ROOT.parents[1]/'backups'/'sqlite-migration'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        snapshot(ROOT/'data',source)
    url=dotenv_values(ROOT.parents[1]/'.env')['DATABASE_URL']
    storage=MariaStorage(url)
    try:manifest=migrate(storage,source)
    finally:storage.engine.dispose()
    report=source/'migration-manifest.json'
    report.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');report.chmod(0o600)
    print(json.dumps({'snapshot':str(source),'verified_tables':manifest},ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except Exception as error:
        # DB errors may embed bound personal data or credentials; do not print them.
        print('Migration failed ('+type(error).__name__+'). Service must remain stopped until resolved.')
        raise SystemExit(1)
