import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from backup_mariadb import create_backup, list_backups, due, prune, verify_archive


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.key=self.root/'bridge.key';self.key.write_bytes(b'test-key')
        self.dest=self.root/'backups';self.dest.mkdir()
        self.now=datetime(2026,11,10,0,0,tzinfo=timezone.utc)

    def backup(self, when):
        def dump(url,path):path.write_bytes(b'CREATE TABLE test (id INT);\n')
        with patch('backup_mariadb.dump_database',side_effect=dump):
            return create_backup('mysql+pymysql://fake',self.dest,self.key,when)

    def test_valid_archive_key_and_48_hour_schedule(self):
        self.assertTrue(due(self.dest,self.now))
        result=self.backup(self.now)
        self.assertEqual(verify_archive(result)['retention_days'],30)
        self.assertFalse(due(self.dest,self.now+timedelta(hours=47,minutes=59)))
        self.assertTrue(due(self.dest,self.now+timedelta(hours=48)))
        self.assertEqual(result.stat().st_mode & 0o777,0o600)

    def test_retention_only_owned_archives(self):
        old=self.backup(self.now-timedelta(days=31))
        recent=self.backup(self.now-timedelta(days=29))
        unrelated=self.dest/'manual.tar.gz';unrelated.write_text('preserve')
        prune(self.dest,self.now)
        self.assertFalse(old.exists());self.assertTrue(recent.exists());self.assertTrue(unrelated.exists())

    def test_failed_dump_does_not_publish_or_prune(self):
        old=self.backup(self.now-timedelta(days=31))
        with patch('backup_mariadb.dump_database',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):create_backup('mysql+pymysql://fake',self.dest,self.key,self.now)
        self.assertTrue(old.exists());self.assertEqual(len(list_backups(self.dest)),1)
        self.assertFalse(list(self.dest.glob('*.partial')))

if __name__=='__main__':unittest.main()
