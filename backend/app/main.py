from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .models import AttendanceRecord, Course, Enrollment, Group, Instructor, Preference, ScheduleEntry, StaffAccount, Student
from .schemas import AttendanceUpdate, GradeUpdate, InstructorAssignment, LoginRequest, PreferenceResponse, ScheduleResponse, StaffAccountCreate, StudentResponse, TokenResponse
from .security import create_access_token, hash_password, read_identity, verify_password

Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name, version="1.0.0")
local_origin_regex = (
    r"https?://(?:localhost|127\.0\.0\.1|"
    r"10(?:\.[0-9]{1,3}){3}|"
    r"172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}|"
    r"192\.168(?:\.[0-9]{1,3}){2}|"
    r"100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])(?:\.[0-9]{1,3}){2}|"
    r"[A-Za-z0-9-]+|(?:[A-Za-z0-9-]+\.)+ts\.net)(?::[0-9]{1,5})?"
)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_origin_regex=local_origin_regex, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)
project_root = Path(__file__).resolve().parents[2]


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def frontend():
    return FileResponse(project_root / "index.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    student = db.scalar(select(Student).where(Student.username == payload.username, Student.is_active.is_(True)))
    if student and verify_password(payload.password, student.password_hash):
        return TokenResponse(access_token=create_access_token(student.id, "student"), role="student", display_name=f"{student.first_name} {student.last_name}")
    staff = db.scalar(select(StaffAccount).where(StaffAccount.username == payload.username, StaffAccount.is_active.is_(True)))
    if not staff or not verify_password(payload.password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    display_name = "Administrator"
    if staff.instructor:
        display_name = f"{staff.instructor.first_name} {staff.instructor.last_name}"
    return TokenResponse(access_token=create_access_token(staff.id, staff.role), role=staff.role, display_name=display_name)


@app.get("/api/auth/me")
def auth_me(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    identity = read_identity(credentials.credentials) if credentials else None
    if not identity:
        raise HTTPException(status_code=401, detail="Требуется вход")
    role, account_id = identity
    if role == "student":
        account = db.get(Student, account_id)
        if not account or not account.is_active:
            raise HTTPException(status_code=401, detail="Аккаунт отключён")
        return {"role": role, "display_name": f"{account.first_name} {account.last_name}"}
    account = db.get(StaffAccount, account_id)
    if not account or not account.is_active or account.role != role:
        raise HTTPException(status_code=401, detail="Аккаунт отключён")
    name = f"{account.instructor.first_name} {account.instructor.last_name}" if account.instructor else account.username
    return {"role": role, "display_name": name}


def current_student(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> Student:
    identity = read_identity(credentials.credentials) if credentials else None
    student_id = identity[1] if identity and identity[0] == "student" else None
    student = db.get(Student, student_id) if student_id else None
    if not student or not student.is_active:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return student


def current_staff(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> StaffAccount:
    identity = read_identity(credentials.credentials) if credentials else None
    if not identity or identity[0] not in {"teacher", "admin"}:
        raise HTTPException(status_code=401, detail="Требуется аккаунт сотрудника")
    staff = db.get(StaffAccount, identity[1])
    if not staff or not staff.is_active or staff.role != identity[0]:
        raise HTTPException(status_code=401, detail="Аккаунт сотрудника отключён")
    return staff


def current_teacher(staff: StaffAccount = Depends(current_staff)) -> StaffAccount:
    if staff.role != "teacher" or staff.instructor_id is None:
        raise HTTPException(status_code=403, detail="Доступ только для учителя")
    return staff


def current_admin(staff: StaffAccount = Depends(current_staff)) -> StaffAccount:
    if staff.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ только для администрации")
    return staff


@app.get("/api/me", response_model=StudentResponse)
def me(student: Student = Depends(current_student)):
    return {"id": student.id, "username": student.username, "first_name": student.first_name, "last_name": student.last_name, "group": student.group.name}


@app.get("/api/me/preferences", response_model=PreferenceResponse)
def preferences(student: Student = Depends(current_student)):
    pref = student.preference
    if not pref:
        return {"language": "ru", "theme": "light", "notifications_enabled": True}
    return {"language": pref.language, "theme": pref.theme, "notifications_enabled": pref.notifications_enabled}


@app.get("/api/me/courses")
def courses(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    rows = db.execute(select(Enrollment, Course).join(Course, Enrollment.course_id == Course.id).where(Enrollment.student_id == student.id).order_by(Course.title)).all()
    return [{"id": course.id, "code": course.code, "title": course.title, "instructor": f"{course.instructor.first_name} {course.instructor.last_name}", "progress": enrollment.progress, "grade": enrollment.grade} for enrollment, course in rows]


@app.get("/api/me/schedule", response_model=list[ScheduleResponse])
def schedule(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    rows = db.execute(select(ScheduleEntry).where(ScheduleEntry.group_id == student.group_id).order_by(ScheduleEntry.weekday, ScheduleEntry.starts_at)).scalars().all()
    return [{"id": row.id, "course": row.course.title, "weekday": row.weekday, "starts_at": row.starts_at.strftime("%H:%M"), "ends_at": row.ends_at.strftime("%H:%M"), "room": row.room.name} for row in rows]


@app.get("/api/teacher/me")
def teacher_me(staff: StaffAccount = Depends(current_teacher)):
    return {"username": staff.username, "role": staff.role, "name": f"{staff.instructor.first_name} {staff.instructor.last_name}"}


@app.get("/api/teacher/courses")
def teacher_courses(staff: StaffAccount = Depends(current_teacher), db: Session = Depends(get_db)):
    rows = db.execute(select(Course).where(Course.instructor_id == staff.instructor_id).order_by(Course.title)).scalars().all()
    return [{"id": c.id, "code": c.code, "title": c.title, "students": db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == c.id)) or 0} for c in rows]


@app.get("/api/teacher/courses/{course_id}/roster")
def teacher_roster(course_id: int, staff: StaffAccount = Depends(current_teacher), db: Session = Depends(get_db)):
    course = db.scalar(select(Course).where(Course.id == course_id, Course.instructor_id == staff.instructor_id))
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден или не назначен этому учителю")
    lessons = db.execute(select(ScheduleEntry).where(ScheduleEntry.course_id == course_id)).scalars().all()
    group_ids = {lesson.group_id for lesson in lessons}
    if not group_ids:
        return []
    enrollments = db.execute(select(Enrollment, Student, Group).join(Student, Student.id == Enrollment.student_id).join(Group, Group.id == Student.group_id).where(Enrollment.course_id == course_id, Student.group_id.in_(group_ids)).order_by(Group.name, Student.last_name, Student.first_name)).all()
    output = []
    for enrollment, student, group in enrollments:
        lesson = next((x for x in lessons if x.group_id == student.group_id), None)
        attendance = db.scalar(select(AttendanceRecord.status).where(AttendanceRecord.schedule_id == lesson.id, AttendanceRecord.student_id == student.id)) if lesson else None
        output.append({"enrollment_id": enrollment.id, "student_id": student.id, "name": f"{student.first_name} {student.last_name}", "group": group.name, "progress": enrollment.progress, "grade": enrollment.grade, "schedule_id": lesson.id if lesson else None, "attendance": attendance})
    return output


@app.put("/api/teacher/enrollments/{enrollment_id}/grade")
def teacher_update_grade(enrollment_id: int, payload: GradeUpdate, staff: StaffAccount = Depends(current_teacher), db: Session = Depends(get_db)):
    enrollment = db.get(Enrollment, enrollment_id)
    course = db.get(Course, enrollment.course_id) if enrollment else None
    if not enrollment or not course or course.instructor_id != staff.instructor_id:
        raise HTTPException(status_code=404, detail="Запись не найдена среди курсов этого учителя")
    allowed_group = db.scalar(select(ScheduleEntry.id).where(ScheduleEntry.course_id == course.id, ScheduleEntry.group_id == db.scalar(select(Student.group_id).where(Student.id == enrollment.student_id))))
    if not allowed_group:
        raise HTTPException(status_code=403, detail="Студент не состоит в группе, назначенной этому курсу")
    enrollment.grade = payload.grade
    db.commit()
    return {"ok": True, "enrollment_id": enrollment.id, "grade": enrollment.grade}


@app.put("/api/teacher/attendance")
def teacher_mark_attendance(payload: AttendanceUpdate, staff: StaffAccount = Depends(current_teacher), db: Session = Depends(get_db)):
    lesson = db.get(ScheduleEntry, payload.schedule_id)
    student = db.get(Student, payload.student_id)
    course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not student or not course or course.instructor_id != staff.instructor_id or student.group_id != lesson.group_id:
        raise HTTPException(status_code=404, detail="Занятие или ученик не относятся к курсу этого учителя")
    if not db.scalar(select(Enrollment.id).where(Enrollment.student_id == student.id, Enrollment.course_id == course.id)):
        raise HTTPException(status_code=404, detail="Ученик не записан на этот курс")
    record = db.scalar(select(AttendanceRecord).where(AttendanceRecord.schedule_id == lesson.id, AttendanceRecord.student_id == student.id))
    if record:
        record.status = payload.status
        record.marked_by_staff_id = staff.id
    else:
        record = AttendanceRecord(schedule_id=lesson.id, student_id=student.id, status=payload.status, marked_by_staff_id=staff.id)
        db.add(record)
    db.commit()
    return {"ok": True, "status": record.status}


@app.get("/api/admin/overview")
def admin_overview(_: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    counts = {"students": db.scalar(select(func.count(Student.id))) or 0, "teachers": db.scalar(select(func.count(StaffAccount.id)).where(StaffAccount.role == "teacher")) or 0, "admins": db.scalar(select(func.count(StaffAccount.id)).where(StaffAccount.role == "admin")) or 0, "courses": db.scalar(select(func.count(Course.id))) or 0, "groups": db.scalar(select(func.count(Group.id))) or 0}
    return counts


@app.get("/api/admin/staff")
def admin_staff_list(_: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(StaffAccount).order_by(StaffAccount.role, StaffAccount.username)).scalars().all()
    return [{"id": x.id, "username": x.username, "role": x.role, "active": x.is_active, "instructor": f"{x.instructor.first_name} {x.instructor.last_name}" if x.instructor else None} for x in rows]


@app.get("/api/admin/instructors")
def admin_instructors(_: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Instructor).order_by(Instructor.last_name, Instructor.first_name)).scalars().all()
    return [{"id": x.id, "name": f"{x.first_name} {x.last_name}"} for x in rows]


@app.get("/api/admin/courses")
def admin_courses(_: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Course).order_by(Course.title)).scalars().all()
    return [{"id": x.id, "code": x.code, "title": x.title, "instructor_id": x.instructor_id, "instructor": f"{x.instructor.first_name} {x.instructor.last_name}"} for x in rows]


@app.post("/api/admin/staff", status_code=201)
def admin_create_staff(payload: StaffAccountCreate, _: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Student.id).where(Student.username == payload.username)) or db.scalar(select(StaffAccount.id).where(StaffAccount.username == payload.username)):
        raise HTTPException(status_code=409, detail="Имя пользователя уже занято")
    if payload.role == "teacher":
        if payload.instructor_id is None or not db.get(Instructor, payload.instructor_id):
            raise HTTPException(status_code=422, detail="Для учителя требуется существующая запись преподавателя")
        if db.scalar(select(StaffAccount.id).where(StaffAccount.instructor_id == payload.instructor_id)):
            raise HTTPException(status_code=409, detail="У этого преподавателя уже есть аккаунт")
    elif payload.instructor_id is not None:
        raise HTTPException(status_code=422, detail="Аккаунту администрации не назначается instructor_id")
    staff = StaffAccount(username=payload.username, password_hash=hash_password(payload.password), role=payload.role, instructor_id=payload.instructor_id)
    db.add(staff)
    db.commit()
    return {"id": staff.id, "username": staff.username, "role": staff.role}


@app.put("/api/admin/staff/{staff_id}/active")
def admin_set_staff_active(staff_id: int, active: bool, admin: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    staff = db.get(StaffAccount, staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    if staff.id == admin.id and not active:
        raise HTTPException(status_code=409, detail="Нельзя отключить текущий аккаунт администрации")
    if staff.role == "admin" and staff.is_active and not active:
        active_admins = db.scalar(select(func.count(StaffAccount.id)).where(StaffAccount.role == "admin", StaffAccount.is_active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="Нельзя отключить последнего активного администратора")
    staff.is_active = active
    db.commit()
    return {"id": staff.id, "active": staff.is_active}


@app.put("/api/admin/courses/{course_id}/instructor")
def admin_assign_course(course_id: int, payload: InstructorAssignment, _: StaffAccount = Depends(current_admin), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    active_teacher = db.scalar(select(StaffAccount.id).where(StaffAccount.instructor_id == payload.instructor_id, StaffAccount.role == "teacher", StaffAccount.is_active.is_(True)))
    if not course or not db.get(Instructor, payload.instructor_id):
        raise HTTPException(status_code=404, detail="Курс или преподаватель не найден")
    if not active_teacher:
        raise HTTPException(status_code=409, detail="У преподавателя нет активного аккаунта teacher")
    course.instructor_id = payload.instructor_id
    db.commit()
    return {"ok": True, "course_id": course.id, "instructor_id": course.instructor_id}
