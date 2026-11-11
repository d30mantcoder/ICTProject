"""Restore a backup into a disposable, socket-only MariaDB server, then check it."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import pymysql
from backup_mariadb import verify_archive
from migrate_mariadb import SOURCES, digest
from maria_storage import SCHEMAS
import sqlite3
from contextlib import closing


def verify(archive, snapshot=None):
    manifest=verify_archive(archive)
    with tempfile.TemporaryDirectory(prefix='aitu-restore-') as tmp:
        root=Path(tmp);data=root/'db';socket=str(root/'server.sock')
        with (root/'init.log').open('wb') as log:
            init=subprocess.run(['mariadb-install-db','--no-defaults','--datadir='+str(data),
                '--auth-root-authentication-method=normal','--skip-test-db'],stdout=log,stderr=subprocess.STDOUT,timeout=120)
        if init.returncode:raise RuntimeError('Could not initialize isolated restore server')
        server=subprocess.Popen(['mariadbd','--no-defaults','--datadir='+str(data),'--socket='+socket,
            '--pid-file='+str(root/'server.pid'),'--skip-networking','--log-error='+str(root/'server.log'),
            '--innodb-buffer-pool-size=64M','--max-allowed-packet=64M'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    db=pymysql.connect(unix_socket=socket,user='root',charset='utf8mb4');break
                except pymysql.Error:
                    if server.poll() is not None:raise RuntimeError('Isolated restore server stopped')
                    time.sleep(.1)
            else:raise RuntimeError('Restore server startup timeout')
            with db:
                with db.cursor() as cursor:cursor.execute('CREATE DATABASE restore_check CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            with tarfile.open(archive,'r:gz') as tar, (root/'database.sql').open('wb') as output:
                shutil.copyfileobj(tar.extractfile('database.sql'),output)
            with (root/'database.sql').open('rb') as source:
                restored=subprocess.run(['mariadb','--no-defaults','--socket='+socket,'--user=root','restore_check'],
                    stdin=source,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
            if restored.returncode:raise RuntimeError('SQL restore failed')
            with pymysql.connect(unix_socket=socket,user='root',database='restore_check',charset='utf8mb4') as db:
                with db.cursor() as cursor:
                    cursor.execute('SHOW TABLES');tables=[row[0] for row in cursor.fetchall()]
                    counts={}
                    for table in tables:
                        quoted='`'+table.replace('`','``')+'`'
                        cursor.execute('CHECK TABLE '+quoted)
                        checks=cursor.fetchall()
                        if any(row[-1]!='OK' for row in checks if row[-2]=='status'):raise RuntimeError('Restored table failed check')
                        cursor.execute('SELECT COUNT(*) FROM '+quoted);counts[table]=cursor.fetchone()[0]
                    if snapshot:
                        for namespace,filename in SOURCES.items():
                            with closing(sqlite3.connect((snapshot/filename).resolve().as_uri()+'?mode=ro',uri=True)) as src:
                                for table in SCHEMAS[namespace]:
                                    if namespace=='teacher' and table=='assessment_file_chunks':continue
                                    columns=[row[1] for row in src.execute('PRAGMA table_info("'+table+'")')]
                                    selection=','.join('"'+c+'"' for c in columns)
                                    if namespace=='bridge' and table=='documents':columns=['id']+columns;selection='rowid,'+selection
                                    expected=src.execute('SELECT '+selection+' FROM "'+table+'"').fetchall()
                                    cursor.execute('SELECT '+','.join('`'+c+'`' for c in columns)+' FROM `aitu_'+namespace+'_'+table+'`')
                                    actual=[list(row) for row in cursor.fetchall()]
                                    if namespace=='teacher' and table=='assessment_files':
                                        for row in actual:
                                            cursor.execute('SELECT content FROM aitu_teacher_assessment_file_chunks WHERE file_id=%s ORDER BY position',(row[columns.index('id')],))
                                            row[columns.index('content')]+=b''.join(part[0] for part in cursor.fetchall())
                                    if digest(expected)!=digest(actual):raise RuntimeError('Restored data differs from migration snapshot')
            return {'restored_tables':counts,'session_key_checksum_verified':True,'migration_values_verified':snapshot is not None}
        finally:
            server.terminate()
            try:server.wait(timeout=20)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--snapshot',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(verify(args.archive,args.snapshot),indent=2))
    except Exception as error:
        print('Restore verification failed ('+type(error).__name__+')');raise SystemExit(1)
