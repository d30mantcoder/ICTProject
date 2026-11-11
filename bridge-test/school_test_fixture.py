"""A temporary relational school database for tests; never touches MariaDB."""
from datetime import datetime
from contextlib import closing
import sqlite3
from zoneinfo import ZoneInfo


def create_school_fixture(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
          CREATE TABLE students(id INTEGER PRIMARY KEY,first_name TEXT,last_name TEXT,group_id INTEGER,is_active INTEGER);
          CREATE TABLE staff_accounts(id INTEGER PRIMARY KEY,username TEXT,instructor_id INTEGER,role TEXT,is_active INTEGER);
          CREATE TABLE instructors(id INTEGER PRIMARY KEY,first_name TEXT,last_name TEXT);
          CREATE TABLE courses(id INTEGER PRIMARY KEY,title TEXT,instructor_id INTEGER);
          CREATE TABLE `groups`(id INTEGER PRIMARY KEY,name TEXT);
          CREATE TABLE enrollments(id INTEGER PRIMARY KEY,student_id INTEGER,course_id INTEGER);
          CREATE TABLE rooms(id INTEGER PRIMARY KEY,name TEXT,building TEXT);
          CREATE TABLE schedule(id INTEGER PRIMARY KEY,course_id INTEGER,group_id INTEGER,room_id INTEGER,weekday INTEGER,starts_at TEXT,ends_at TEXT,lesson_date TEXT);
          CREATE TABLE attendance_records(id INTEGER PRIMARY KEY,schedule_id INTEGER,student_id INTEGER,status TEXT);
          CREATE TABLE preferences(id INTEGER PRIMARY KEY);
          INSERT INTO instructors VALUES(1,'Diana','Kazbekova'),(2,'Other','Teacher');
          INSERT INTO staff_accounts VALUES(1,'teacher004',1,'teacher',1),(2,'teacher002',2,'teacher',1),(3,'admin001',NULL,'admin',1);
          INSERT INTO courses VALUES(1,'Information and Communication Technologies',1),(2,'Digital Literacy',1),(3,'Other course',2);
          INSERT INTO `groups` VALUES(1,'SE-2623'),(2,'SE-2624'),(3,'OTHER');
          INSERT INTO rooms VALUES(1,'C1.2.228','Главный корпус AITU'),(2,'C1.2.229','Главный корпус AITU'),(3,'C1.2.230','Главный корпус AITU');
        ''')
        number=0
        for group,offset in [(1,0),(2,100)]:
            for index in range(1,13):
                student=offset+index
                first='Нурасыл' if student==4 else 'Азамат' if student==101 else 'Student'+str(student)
                db.execute('INSERT INTO students VALUES(?,?,?,?,1)',(student,first,'Test',group))
                number+=1;db.execute('INSERT INTO enrollments VALUES(?,?,1)',(number,student))
                if group==1:
                    number+=1;db.execute('INSERT INTO enrollments VALUES(?,?,2)',(number,student))
        db.execute("INSERT INTO students VALUES(999,'Not','Assigned',3,1)")
        db.execute('INSERT INTO enrollments VALUES(?,999,3)',(number+1,))
        weekday=datetime.now(ZoneInfo('Asia/Almaty')).weekday()
        for index,course,group,start in [(1,1,1,'00:00:00'),(2,1,2,'00:00:00'),(3,2,1,'00:00:00')]:
            db.execute('INSERT INTO schedule VALUES(?,?,?,?,?,?,?,NULL)',(index,course,group,index,weekday,start,'23:59:59'))
    return 'sqlite:///'+str(path)
