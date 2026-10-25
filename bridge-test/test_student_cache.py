"""Temporary SQLite databases; no real student data or Moodle accounts."""
import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from student_cache import StudentCache, next_midnight, fresh_today, normalize_email

MOODLE = "https://lms.astanait.edu.kz"


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aitu-db-unit-")
        self.now = datetime(2026,10,22,18,59,59,tzinfo=timezone.utc)
        self.db = StudentCache(Path(self.temp.name)/"cache.sqlite3",clock=lambda:self.now)
        self.identity = {"email":"230001@astanait.edu.kz","moodle_user_id":1,
                         "first_name":"Amina","last_name":"Test","display_name":"Amina Test"}
        self.courses = [{"title":"Databases","url":MOODLE+"/course/view.php?id=1"}]

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_midnight_is_astana_midnight_not_24_hours_after_write(self):
        await self.db.save(self.identity,self.courses)
        self.assertFalse((await self.db.get(self.identity["email"],1))["stale"])
        self.assertEqual(next_midnight(self.now).astimezone(timezone.utc),
                         datetime(2026,10,22,19,0,tzinfo=timezone.utc))
        self.now += timedelta(seconds=1)
        self.assertTrue((await self.db.get(self.identity["email"],1))["stale"])
        self.assertEqual(next_midnight(self.now).astimezone(timezone.utc),
                         datetime(2026,10,23,19,0,tzinfo=timezone.utc))

    async def test_full_email_key_and_moodle_identity_prevent_collisions(self):
        await self.db.save(self.identity,self.courses)
        second={**self.identity,"email":"230001@different.test","moodle_user_id":2,"display_name":"Other"}
        await self.db.save(second,[])
        self.assertEqual((await self.db.get(second["email"],2))["display_name"],"Other")
        self.assertEqual((await self.db.get(self.identity["email"],1))["display_name"],"Amina Test")
        self.assertIsNone(await self.db.get(self.identity["email"],2))
        with self.assertRaises(ValueError):
            await self.db.save({**self.identity,"moodle_user_id":2},[])
        self.assertEqual(normalize_email(" 230001@ASTANAIT.EDU.KZ "),"230001@astanait.edu.kz")

    async def test_selected_clubs_survive_refresh_and_reopening_database(self):
        await self.db.save(self.identity,self.courses)
        await self.db.select_club(self.identity["email"],1,"Robotics",True,{"Robotics"})
        self.now += timedelta(days=1)
        await self.db.save({**self.identity,"first_name":"Updated"},[])
        reopened = StudentCache(self.db.path,clock=lambda:self.now)
        data = await reopened.get(self.identity["email"],1)
        self.assertEqual(data["first_name"],"Updated")
        self.assertEqual(data["clubs"],["Robotics"])
        self.assertEqual(data["student_number"],"230001")
        self.assertEqual(os.stat(self.db.path).st_mode & 0o777,0o600)

    async def test_three_concurrent_users_write_isolated_snapshots(self):
        async def user(number):
            identity={**self.identity,"email":f"23000{number}@astanait.edu.kz","moodle_user_id":number}
            for version in range(10):
                courses=[{"title":f"User {number} v{version}","url":MOODLE+f"/course/view.php?id={number}"}]
                await self.db.save(identity,courses)
                await self.db.save_document(identity,"courses",MOODLE+"/my/courses.php",{"courses":courses})
                own=await self.db.document(identity["email"],number,"courses",MOODLE+"/my/courses.php")
                self.assertEqual(own["courses"],courses)
        await asyncio.gather(*(user(i) for i in (1,2,3)))

    async def test_documents_store_academic_fields_exclude_credentials_and_cap_size(self):
        await self.db.save(self.identity,self.courses)
        for number in range(35):
            await self.db.save_document(self.identity,"courses",MOODLE+f"/course/view.php?id={number}",{
                "text":"Material text","grades":[{"grade":"95"}],"timeline":[{"title":"Deadline"}],
                "password":"secret-password", "cookies":"secret-cookie", "storage_state":"secret-state"})
        keys=await self.db.document_keys(self.identity["email"],1)
        self.assertEqual(len(keys),30)
        data=await self.db.document(self.identity["email"],1,*keys[0])
        self.assertEqual(data["text"],"Material text")
        self.assertEqual(data["grades"][0]["grade"],"95")
        self.assertNotIn("password",data)
        for suffix in ("","-wal"):
            path=Path(str(self.db.path)+suffix)
            if path.exists():
                self.assertNotIn(b"secret-password",path.read_bytes())
                self.assertNotIn(b"secret-cookie",path.read_bytes())
        self.assertIsNone(await self.db.document(self.identity["email"],2,*keys[0]))

    async def test_catalog_reloads_after_midnight_preserves_source_checked_date(self):
        source=Path(self.temp.name)/"community.json"
        source.write_text(json.dumps({"clubs":[],"checked":"2026-01-01"}))
        first=await self.db.community(source)
        source.write_text(json.dumps({"clubs":[{"title":"New"}],"checked":"2026-01-02"}))
        self.assertEqual((await self.db.community(source))["clubs"],[])
        self.now += timedelta(seconds=1)
        changed=await self.db.community(source)
        self.assertEqual(changed["clubs"],[{"title":"New"}])
        self.assertEqual(changed["checked"],"2026-01-02")
        self.assertNotEqual(changed["cache_updated_at"],first["cache_updated_at"])

    async def test_empty_courses_replace_old_enrollments_without_losing_clubs(self):
        await self.db.save(self.identity,self.courses)
        self.now += timedelta(days=1)
        await self.db.save(self.identity,[])
        self.assertEqual((await self.db.get(self.identity["email"],1))["courses"],[])

    async def test_remembered_login_is_encrypted_and_bound_to_token(self):
        await self.db.save(self.identity,self.courses)
        token = "random-browser-cookie-0123456789"
        state = {"cookies":[{"name":"MoodleSession","value":"private-moodle-cookie"}],"origins":[]}
        expiry = self.now.timestamp()+30*86400
        self.assertTrue(await self.db.remember(token,self.identity,state,expiry))
        reopened = StudentCache(self.db.path,clock=lambda:self.now)
        loaded = await reopened.remembered(token)
        self.assertEqual(loaded["state"],state)
        self.assertEqual(loaded["identity"]["email"],self.identity["email"])
        self.assertIsNone(await reopened.remembered("another-token"))
        for suffix in ("","-wal"):
            path=Path(str(self.db.path)+suffix)
            if path.exists():
                self.assertNotIn(b"private-moodle-cookie",path.read_bytes())
                self.assertNotIn(token.encode(),path.read_bytes())
        self.assertEqual(os.stat(self.db.path.with_suffix(".key")).st_mode & 0o777,0o600)
        await reopened.forget(token)
        self.assertIsNone(await reopened.remembered(token))

    async def test_expired_saved_login_cannot_be_restored(self):
        await self.db.save(self.identity,self.courses)
        await self.db.remember("token",self.identity,{"cookies":[],"origins":[]},self.now.timestamp()+60)
        self.now += timedelta(seconds=60)
        self.assertIsNone(await self.db.remembered("token"))

    async def test_swapped_encrypted_state_never_restores_another_users_cookies(self):
        await self.db.save(self.identity,self.courses)
        other = {**self.identity,"email":"230002@astanait.edu.kz","moodle_user_id":2}
        await self.db.save(other,[])
        await self.db.remember("one",self.identity,{"cookies":["one"]},self.now.timestamp()+60)
        await self.db.remember("two",other,{"cookies":["two"]},self.now.timestamp()+60)
        await self.db._call(lambda db:db.execute("""UPDATE remembered_sessions SET browser_state=(
            SELECT browser_state FROM remembered_sessions WHERE email=?) WHERE email=?""",
            (other["email"],self.identity["email"])))
        self.assertIsNone((await self.db.remembered("one"))["state"])
        self.assertEqual((await self.db.remembered("two"))["state"],{"cookies":["two"]})

    async def test_missing_key_preserves_only_cached_identity(self):
        await self.db.save(self.identity,self.courses)
        await self.db.remember("token",self.identity,{"cookies":["private"]},self.now.timestamp()+60)
        self.db.path.with_suffix(".key").unlink()
        loaded=await self.db.remembered("token")
        self.assertEqual(loaded["identity"]["email"],self.identity["email"])
        self.assertIsNone(loaded["state"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
