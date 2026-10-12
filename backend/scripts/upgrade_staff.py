"""Add demo teacher/admin accounts and attendance records without replacing project data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.database import Base, SessionLocal, engine
from app.models import AttendanceRecord, Course, Enrollment, Instructor, ScheduleEntry, StaffAccount, Student
from app.security import hash_password

Base.metadata.create_all(engine)
with engine.begin() as conn:
    constraints = [
        ("enrollments", "ck_enrollment_progress", "progress BETWEEN 0 AND 100"),
        ("enrollments", "ck_enrollment_grade", "grade IS NULL OR grade BETWEEN 0 AND 100"),
        ("schedule", "ck_schedule_weekday", "weekday BETWEEN 0 AND 6"),
        ("schedule", "ck_schedule_time_order", "starts_at < ends_at"),
    ]
    for table, name, expression in constraints:
        exists = conn.execute(text("""
            SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = :table
              AND CONSTRAINT_NAME = :name
        """), {"table": table, "name": name}).first()
        if not exists:
            conn.execute(text(f"ALTER TABLE `{table}` ADD CONSTRAINT `{name}` CHECK ({expression})"))
db = SessionLocal()
try:
    instructors = db.execute(select(Instructor).order_by(Instructor.id)).scalars().all()
    for index, instructor in enumerate(instructors, start=1):
        username = f"teacher{index:03d}"
        account = db.scalar(select(StaffAccount).where(StaffAccount.instructor_id == instructor.id))
        if account:
            account.username = username
        elif not db.scalar(select(StaffAccount.id).where(StaffAccount.username == username)):
            db.add(StaffAccount(username=username, password_hash=hash_password("Study2026!"), role="teacher", instructor_id=instructor.id))
    for username in ("admin001", "admin002"):
        if not db.scalar(select(StaffAccount.id).where(StaffAccount.username == username)):
            db.add(StaffAccount(username=username, password_hash=hash_password("Study2026!"), role="admin"))
    db.commit()

    staff_by_instructor = {
        row.instructor_id: row
        for row in db.execute(select(StaffAccount).where(StaffAccount.role == "teacher")).scalars().all()
    }
    existing = set(db.execute(select(AttendanceRecord.schedule_id, AttendanceRecord.student_id)).all())
    created = 0
    statuses = ("present", "present", "present", "late", "absent", "excused")
    lessons = db.execute(select(ScheduleEntry).order_by(ScheduleEntry.id)).scalars().all()
    for lesson in lessons:
        course = db.get(Course, lesson.course_id)
        marker = staff_by_instructor.get(course.instructor_id)
        if not marker:
            continue
        roster = db.execute(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Enrollment.course_id == lesson.course_id,
                Student.group_id == lesson.group_id,
            )
            .order_by(Student.id)
        ).scalars().all()
        for student in roster:
            key = (lesson.id, student.id)
            if key in existing or created >= 70:
                continue
            db.add(AttendanceRecord(
                schedule_id=lesson.id,
                student_id=student.id,
                status=statuses[created % len(statuses)],
                marked_by_staff_id=marker.id,
            ))
            existing.add(key)
            created += 1
    db.commit()
    print(f"Staff accounts ready: {db.query(StaffAccount).filter_by(role='teacher').count()} teachers, {db.query(StaffAccount).filter_by(role='admin').count()} admins.")
    print(f"Attendance records total: {db.query(AttendanceRecord).count()} (added {created}).")
    print("Demo staff password: Study2026!")
finally:
    db.close()
