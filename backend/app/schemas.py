from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "student"
    display_name: str = ""


class GradeUpdate(BaseModel):
    grade: int | None = Field(ge=0, le=100)


class AttendanceUpdate(BaseModel):
    schedule_id: int
    student_id: int
    status: str = Field(pattern="^(present|absent|late|excused)$")


class StaffAccountCreate(BaseModel):
    username: str = Field(min_length=4, max_length=64, pattern="^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    role: str = Field(pattern="^(teacher|admin)$")
    instructor_id: int | None = None


class InstructorAssignment(BaseModel):
    instructor_id: int


class StudentResponse(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    group: str
    model_config = ConfigDict(from_attributes=True)


class PreferenceResponse(BaseModel):
    language: str
    theme: str
    notifications_enabled: bool


class CourseResponse(BaseModel):
    id: int
    code: str
    title: str
    instructor: str
    progress: int
    grade: int | None


class ScheduleResponse(BaseModel):
    id: int
    course: str
    weekday: int
    starts_at: str
    ends_at: str
    room: str
