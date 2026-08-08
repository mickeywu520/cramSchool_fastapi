"""Student schemas."""

from datetime import date, datetime
from pydantic import BaseModel, Field


class StudentResponse(BaseModel):
    id: int
    student_name: str
    gender: str
    birth_date: date
    school: str
    grade: str
    class_name: str | None = None
    parent_name: str
    parent_title: str | None = None
    phone: str
    parent2_name: str | None = None
    parent2_title: str | None = None
    parent2_phone: str | None = None
    home_phone: str | None = None
    id_number: str | None = None
    branch_id: int | None = None
    avatar_url: str | None = None
    student_number: str | None = None
    remark: str | None = None
    email: str = ""

    model_config = {"from_attributes": True}


class StudentUpdateRequest(BaseModel):
    student_name: str | None = Field(None, max_length=50)
    gender: str | None = None
    birth_date: date | None = None
    school: str | None = Field(None, max_length=100)
    grade: str | None = Field(None, max_length=20)
    class_name: str | None = None
    branch_id: int | None = None
    parent_name: str | None = Field(None, max_length=50)
    parent_title: str | None = None
    phone: str | None = Field(None, max_length=20)
    parent2_name: str | None = None
    parent2_title: str | None = None
    parent2_phone: str | None = None
    home_phone: str | None = None
    id_number: str | None = None
    branch_id: int | None = None


class SubjectProgress(BaseModel):
    subject: str
    progress: float
    total_lessons: int
    completed_lessons: int


class ProgressResponse(BaseModel):
    overall_progress: float
    subjects: list[SubjectProgress]


class CourseSummary(BaseModel):
    id: int
    name: str
    subject: str
    category: str
    schedule: str | None = None
    teacher_name: str | None = None
    grade_level: str | None = None
    location: str | None = None
    branch_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    days_of_week: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    model_config = {"from_attributes": True}


class ExamScoreResponse(BaseModel):
    id: int
    exam_name: str
    subject: str
    score: float
    full_score: int
    exam_date: date

    model_config = {"from_attributes": True}


class StudentRegistrationResponse(BaseModel):
    id: int
    student_name: str
    gender: str
    birth_date: date
    school: str
    grade: str
    class_name: str | None = None
    parent_name: str
    parent_title: str | None = None
    phone: str
    parent2_name: str | None = None
    parent2_title: str | None = None
    parent2_phone: str | None = None
    home_phone: str | None = None
    id_number: str | None = None
    followup_status: str = "待聯繫"
    remark: str | None = None
    email: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class FollowupUpdateRequest(BaseModel):
    followup_status: str = Field(..., pattern=r"^(待聯繫|在籍|離籍)$")


class StudentRegistrationUpdateRequest(BaseModel):
    student_name: str | None = Field(None, max_length=50)
    gender: str | None = None
    birth_date: date | None = None
    school: str | None = Field(None, max_length=100)
    grade: str | None = Field(None, max_length=20)
    class_name: str | None = None
    parent_name: str | None = Field(None, max_length=50)
    parent_title: str | None = None
    phone: str | None = Field(None, max_length=20)
    parent2_name: str | None = None
    parent2_title: str | None = None
    parent2_phone: str | None = None
    home_phone: str | None = None
    id_number: str | None = None
    remark: str | None = None


class HomeworkSummary(BaseModel):
    id: int
    subject: str
    content: str
    due_date: date | None = None
    is_completed: bool

    model_config = {"from_attributes": True}


class ScorePoint(BaseModel):
    date: str
    scores: dict[str, int]
    average: float


class CourseScoreHistory(BaseModel):
    course_id: int
    course_name: str
    subject: str
    points: list[ScorePoint]
    average: float | None = None