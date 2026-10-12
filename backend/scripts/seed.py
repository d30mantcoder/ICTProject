"""Create a reproducible local demo dataset. Demo password for all accounts: Study2026!"""
import random
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Base, SessionLocal, engine
from app.models import Course, Enrollment, Group, Instructor, Preference, Room, ScheduleEntry, Student
from app.security import hash_password

random.seed(20261011)
Base.metadata.create_all(engine)
first_names = ["Aruzhan", "Amina", "Diana", "Madina", "Aliya", "Adilet", "Dias", "Nursultan", "Alikhan", "Sanzhar", "Miras", "Aigerim", "Dana", "Timur", "Yerasyl", "Kamila", "Islam", "Zhansaya", "Arman", "Sabina"]
last_names = ["Sarsen", "Akhmet", "Nurgali", "Omar", "Kassym", "Bekov", "Iskakov", "Tulegen", "Murat", "Zhaksylyk", "Ibrayeva", "Suleimen", "Abdulla", "Kairat", "Yessen"]
course_names = ["Calculus 1", "Cultural Studies", "Foreign Language 1", "Information and Communication Technologies", "Introduction to Programming 1", "Linear Algebra", "Physical Education", "Discrete Mathematics", "Academic Writing", "Physics", "Data Structures", "Digital Systems", "Probability and Statistics", "History of Kazakhstan", "Algorithms"]
instructor_names = [("Zhanat", "Zhuldasov"), ("Gaukhar", "Alzhanova"), ("Ardakh", "Bayan"), ("Diana", "Kazbekova"), ("Nurtas", "Nadirov"), ("Anara", "Mukhamedina"), ("Saltanat", "Sadvokassova"), ("Aibek", "Smailov"), ("Aigerim", "Tursyn"), ("Maksat", "Kaliyev"), ("Aruzhan", "Serik"), ("Dias", "Oraz"), ("Madina", "Kenzhe"), ("Timur", "Aman"), ("Dana", "Bektas")]
db = SessionLocal()
try:
    if db.query(Student).count() >= 100:
        print("Seed skipped: at least 100 students already exist.")
        raise SystemExit(0)
    # Seed is intended for a fresh demo database; refuse accidental duplicate partial loads.
    if any(db.query(model).count() for model in [Group, Course, Instructor, Room, Student]):
        raise SystemExit("Database contains partial data. Back it up and recreate the empty study_lms database before seeding.")
    groups = [Group(name=f"SE-{year}{number:02d}", year=year) for year in range(1, 5) for number in range(1, 4)]
    instructors = [Instructor(first_name=a, last_name=b, email=f"{a.lower()}.{b.lower()}@aitu.demo") for a, b in instructor_names]
    rooms = [Room(name=f"{block}-{number:02d}", building=f"AITU корпус {block}") for block in "ABCD" for number in range(1, 4)]
    db.add_all(groups + instructors + rooms)
    db.flush()
    courses = [Course(code=f"AITU{100+i}", title=name, description=f"Демонстрационный курс {name}", instructor_id=instructors[i].id) for i, name in enumerate(course_names)]
    db.add_all(courses)
    db.flush()
    students = []
    for i in range(100):
        fn, ln = first_names[i % len(first_names)], last_names[(i * 7) % len(last_names)]
        students.append(Student(username=f"student{i+1:03d}", password_hash=hash_password("Study2026!"), first_name=fn, last_name=ln, group_id=groups[i % len(groups)].id))
    db.add_all(students)
    db.flush()
    for i, student in enumerate(students[:70]):
        db.add(Preference(student_id=student.id, language=["ru", "en", "kk"][i % 3], theme="light" if i % 4 else "dark", notifications_enabled=i % 5 != 0))
    for i in range(70):
        student = students[i]
        course = courses[i % len(courses)]
        db.add(Enrollment(student_id=student.id, course_id=course.id, progress=random.randint(0, 100), grade=random.randint(55, 100) if random.random() > .2 else None))
    for group in groups:
        weekday = (group.id - 1) % 5
        for slot in range(5):
            course = courses[(group.id * 3 + slot) % len(courses)]
            start_hour = 9 + (slot % 3) * 2
            db.add(ScheduleEntry(course_id=course.id, group_id=group.id, room_id=rooms[(group.id + slot) % len(rooms)].id, weekday=weekday, starts_at=time(start_hour, 0), ends_at=time(start_hour + 1, 30)))
    db.commit()
    print("Seed complete: 100 students, 12 groups, 70 preferences, 15 instructors, 15 courses, 70 enrollments, 12 rooms, 60 schedule entries.")
    print("Demo login: student001 / Study2026!")
finally:
    db.close()
