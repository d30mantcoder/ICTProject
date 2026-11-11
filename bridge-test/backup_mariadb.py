"""Atomic full MariaDB backups plus the session encryption key, retained for 30 days."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parent
DEFAULT_DEST=ROOT.parents[1]/'backups'/'mariadb'
PATTERN=re.compile(r'^aitu-(\d{8}T\d{12}Z)\.tar\.gz$')
INTERVAL=timedelta(hours=48)
RETENTION=timedelta(days=30)


def list_backups(destination):
    result=[]
    for path in destination.iterdir():
        match=PATTERN.fullmatch(path.name)
        if match and not path.is_symlink() and path.is_file():
            try:stamp=datetime.strptime(match[1],'%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc)
            except ValueError:continue
            result.append((stamp,path))
    return sorted(result)


def due(destination, now):
    backups=list_backups(destination)
    return not backups or now-backups[-1][0]>=INTERVAL


def prune(destination, now):
    for stamp,path in list_backups(destination):
        if now-stamp>RETENTION:path.unlink()


def file_hash(path):
    with path.open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()


@contextmanager
def client_options(url):
    from sqlalchemy.engine import make_url
    parsed=make_url(url)
    if parsed.drivername.split('+')[0] not in ('mysql','mariadb'):
        raise ValueError('MariaDB URL required')
    def quoted(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    with tempfile.TemporaryDirectory(prefix='aitu-db-client-') as tmp:
        path=Path(tmp)/'client.cnf'
        values={'user':parsed.username or '', 'password':parsed.password or '',
                'default-character-set':'utf8mb4'}
        if parsed.query.get('unix_socket'):values['socket']=parsed.query['unix_socket']
        else:values.update(host=parsed.host or 'localhost',port=parsed.port or 3306,protocol='tcp')
        path.write_text('[client]\n'+''.join(k+'='+quoted(v)+'\n' for k,v in values.items()))
        path.chmod(0o600)
        yield path,parsed.database


def dump_database(url, destination):
    with client_options(url) as (options,database), destination.open('wb') as output:
        result=subprocess.run(['mariadb-dump','--defaults-extra-file='+str(options),
            '--single-transaction','--quick','--hex-blob','--routines','--triggers','--events',database],
            stdout=output,stderr=subprocess.PIPE,timeout=600)
        if result.returncode:raise RuntimeError('MariaDB dump failed (exit '+str(result.returncode)+')')
        output.flush();os.fsync(output.fileno())
    if destination.stat().st_size==0:raise RuntimeError('Empty database dump')


def verify_archive(archive):
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        if {m.name for m in members}!={'database.sql','bridge.key','manifest.json'} or len(members)!=3 or not all(m.isfile() for m in members):
            raise ValueError('Unexpected backup contents')
        manifest=json.load(tar.extractfile('manifest.json'))
        for name in ('database.sql','bridge.key'):
            with tar.extractfile(name) as file:
                if hashlib.file_digest(file,'sha256').hexdigest()!=manifest['sha256'][name]:
                    raise ValueError('Backup checksum mismatch')
    return manifest


def create_backup(url,destination,key,now):
    if not key.is_file():raise RuntimeError('Session encryption key is missing')
    destination.mkdir(parents=True,exist_ok=True,mode=0o700);destination.chmod(0o700)
    filename='aitu-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.tar.gz'
    final=destination/filename
    with tempfile.TemporaryDirectory(prefix='.creating-',dir=destination) as tmp:
        work=Path(tmp);sql=work/'database.sql'
        dump_database(url,sql)
        (work/'bridge.key').write_bytes(key.read_bytes())
        manifest={'created_at':now.isoformat(),'interval_hours':48,'retention_days':30,
                  'sha256':{name:file_hash(work/name) for name in ('database.sql','bridge.key')}}
        (work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        archive=work/filename
        with tarfile.open(archive,'w:gz') as tar:
            for name in ('database.sql','bridge.key','manifest.json'):
                (work/name).chmod(0o600);tar.add(work/name,arcname=name)
        archive.chmod(0o600)
        verify_archive(archive)
        with archive.open('rb') as file:os.fsync(file.fileno())
        os.replace(archive,final)
        directory=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    # Never prune before the new dump has completed and passed checksum verification.
    prune(destination,now)
    return final


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--if-due',action='store_true')
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--destination',type=Path,default=DEFAULT_DEST)
    args=parser.parse_args()
    if args.verify:
        print(json.dumps(verify_archive(args.verify),indent=2));return
    os.umask(0o077)
    args.destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (args.destination/'.backup.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        now=datetime.now(timezone.utc)
        if args.if_due and not due(args.destination,now):return
        from dotenv import dotenv_values
        url=dotenv_values(ROOT.parents[1]/'.env')['DATABASE_URL']
        result=create_backup(url,args.destination,ROOT/'data'/'bridge.key',now)
        print('Backup verified: '+str(result),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Client errors can contain secrets and database contents; never log their text.
        print('Backup failed ('+type(error).__name__+'); existing backups retained.',flush=True)
        raise SystemExit(1)
