"""Integration tests use uniquely prefixed tables in MariaDB; never touch live rows."""
import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from dotenv import dotenv_values
from maria_storage import MariaStorage
from student_cache import StudentCache
from telegram_groups import TelegramStore
from teacher_records import TeacherRecords


class MariaTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_activity_weekly_expiry_and_isolation(self):
        now=datetime(2026,11,11,tzinfo=timezone.utc)
        self.cache.clock=lambda:now
        await self.cache.save(self.identity,[])
        other={**self.identity,'email':'other@unit.invalid','moodle_user_id':2}
        await self.cache.save(other,[])
        await self.cache.hide_activity(self.identity['email'],1,'b'*64)
        await self.cache.hide_activity(self.identity['email'],1,'b'*64)
        from upgrade_activity_preferences import upgrade
        upgrade(self.db)
        upgrade(self.db)
        reopened=StudentCache(self.cache.path,clock=lambda:now,database=self.db)
        self.assertEqual(await reopened.hidden_activities(self.identity['email'],1),{'b'*64})
        self.assertEqual(await reopened.hidden_activities(other['email'],2),set())
        now+=timedelta(days=7)
        await reopened.prune_hidden_activities()
        self.assertEqual(await reopened.hidden_activities(self.identity['email'],1),set())
        self.assertEqual(await reopened._call(lambda db:db.execute('SELECT COUNT(*) FROM hidden_activities').fetchone()[0]),0)

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=MariaStorage(dotenv_values(Path(__file__).resolve().parents[2]/'.env')['DATABASE_URL'],prefix='test_'+uuid.uuid4().hex[:12]+'_')
        self.db.initialize()
        self.addCleanup(self.db.drop_test_tables)
        self.cache=StudentCache(Path(self.tmp.name)/'bridge.sqlite3',database=self.db)
        self.tg=TelegramStore(Path(self.tmp.name)/'telegram.sqlite3',database=self.db)
        self.identity={'email':'test@unit.invalid','moodle_user_id':1,'display_name':'Тест 😀','first_name':'Тест','last_name':'User'}

    async def test_cache_documents_and_encrypted_session(self):
        await self.cache.save(self.identity,[])
        self.assertEqual((await self.cache.get(self.identity['email'],1))['display_name'],'Тест 😀')
        self.assertIsNone(await self.cache.get(self.identity['email'],2))
        with self.assertRaises(ValueError):await self.cache.save({**self.identity,'moodle_user_id':2},[])
        await self.cache.select_club(self.identity['email'],1,'Club',True,{'Club'})
        await self.cache.select_club(self.identity['email'],1,'Club',True,{'Club'})
        await self.cache.save(self.identity,[])
        self.assertEqual((await self.cache.get(self.identity['email'],1))['clubs'],['Club'])
        for n in range(35):await self.cache.save_document(self.identity,'courses','https://example.test/'+str(n),{'text':'Курс 😀','password':'not saved'})
        keys=await self.cache.document_keys(self.identity['email'],1)
        self.assertEqual(len(keys),30)
        doc=await self.cache.document(self.identity['email'],1,*keys[0])
        self.assertEqual(doc['text'],'Курс 😀');self.assertNotIn('password',doc)
        await self.cache.save_document(self.identity,*keys[0],{'text':'Updated'})
        self.assertEqual((await self.cache.document(self.identity['email'],1,*keys[0]))['text'],'Updated')
        await self.cache.remember('token',self.identity,{'cookies':['private']},datetime.now(timezone.utc).timestamp()+100)
        self.assertEqual((await self.cache.remembered('token'))['state'],{'cookies':['private']})
        await self.cache.forget('token');self.assertIsNone(await self.cache.remembered('token'))
        source=Path(self.tmp.name)/'community.json';source.write_text('{"clubs": []}')
        self.assertEqual((await self.cache.community(source))['clubs'],[])
        self.assertEqual((await self.cache.community(source,force=True))['clubs'],[])

    async def test_telegram_atomic_tokens_search_and_rollback(self):
        for owner in (1,2):
            code=self.tg.issue(owner,'Student '+str(owner))
            self.tg.consume(code,{'id':owner*100,'username':'student_'+str(owner)})
            self.tg.set_groups(owner,{'main':' SE-2623 ','english':'b2','pe':'PE-4'})
            with self.assertRaises(ValueError):self.tg.consume(code,{'id':300,'username':'other'})
        self.assertEqual(len(self.tg.search(1,'main','')),1)
        code=self.tg.issue(3,'Third')
        with self.assertRaises(ValueError):self.tg.consume(code,{'id':100,'username':'student_1'})
        self.assertFalse(self.tg.profile(3)['linked'])
        self.tg.consume(code,{'id':300,'username':'third'})
        self.tg.refresh_user({'id':300,'username':'new_username'})
        self.assertEqual(self.tg.profile(3)['username'],'new_username')
        self.tg.offset(42);self.assertEqual(self.tg.offset(),42)
        self.tg.offset(43);self.assertEqual(self.tg.offset(),43)
        self.tg.unlink(2);self.assertEqual(self.tg.search(1,'main',''),[])

    async def test_migration_is_exact_idempotent_and_refuses_overwrite(self):
        from migrate_mariadb import snapshot, migrate
        source=Path(self.tmp.name)/'source';source.mkdir()
        cache=StudentCache(source/'bridge.sqlite3')
        await cache.save(self.identity,[])
        await cache.save_document(self.identity,'courses','https://example.test/course?id=1',{'text':'Saved 😀'})
        await cache.remember('saved-token',self.identity,{'cookies':['private']},datetime.now(timezone.utc).timestamp()+100)
        # An old deployment's snapshot predates the new optional preference table.
        await cache._call(lambda db: db.execute('DROP TABLE hidden_activities'))
        tg=TelegramStore(source/'telegram.sqlite3')
        tg.consume(tg.issue(1,'Test'),{'id':100,'username':'student'})
        records=TeacherRecords(source/'bridge-teacher.sqlite3',None,None)
        await records.call(lambda db: None)
        frozen=Path(self.tmp.name)/'snapshot';snapshot(source,frozen)
        first=migrate(self.db,frozen)
        self.assertEqual(first,migrate(self.db,frozen))
        reopened=StudentCache(frozen/'bridge.sqlite3',database=self.db)
        self.assertEqual((await reopened.remembered('saved-token'))['state'],{'cookies':['private']})
        self.assertTrue(self.tg.profile(1)['linked'])
        self.tg.unlink(1)
        # Empty tables can be safely refilled from the same snapshot before cutover.
        migrate(self.db,frozen)
        self.tg.refresh_user({'id':100,'username':'changed'})
        with self.assertRaises(RuntimeError):migrate(self.db,frozen)
        self.assertEqual(self.tg.profile(1)['username'],'changed')

    async def test_teacher_files_grades_and_ownership(self):
        class School:
            async def catalog(self, teacher):return {'groups':{'A':['c1']},'courses':{'c1':'Course'}}
            async def students(self,*args):return [{'id':1,'name':'Student'}]
        records=TeacherRecords(Path(self.tmp.name)/'teacher.sqlite3',School(),1,database=self.db)
        payload=SimpleNamespace(course_id='c1',group='A',title='Работа 😀',kind='homework',description='Text',scheduled_at=datetime.now(timezone.utc)-timedelta(days=1),duration_minutes=0)
        item=await records.create('owner',payload)
        attachment=await records.add_file('owner',item['id'],'test.bin',b'\x00\xffdata')
        self.assertEqual((await records.download_file('owner',item['id'],attachment['id']))[1],b'\x00\xffdata')
        with self.assertRaises(LookupError):await records.download_file('other',item['id'],attachment['id'])
        mark=SimpleNamespace(student_id=1,grade=91.5,comment='Good')
        await records.grade('owner',item['id'],mark)
        mark.grade=95;await records.grade('owner',item['id'],mark)
        self.assertEqual((await records.detail('owner',item['id']))['students'][0]['grade'],95)
        large=b'x'*(20*1024*1024)
        large_file=await records.add_file('owner',item['id'],'large.bin',large)
        self.assertEqual((await records.download_file('owner',item['id'],large_file['id']))[1],large)
        self.assertEqual(len(await records.listing('owner',None,None)),1)
        self.assertEqual(await records.listing('other',None,None),[])

if __name__=='__main__':unittest.main()
