"""Student schemas."""

from datetime import date, datetime
from pydantic import BaseModel, Field


class StudentResponse(BaseModel):
    id: int
    student_name: str
    birth_date: date
    parent_name: str
    phone: str
    grade: str
    school: str
    interested_subjects: list[str] = []
    avatar_url: str | None = None
    student_number: str | None = None
    email: str = ""

    model_config = {"from_attributes": True}


class StudentUpdateRequest(BaseModel):
    student_name: str | None = Field(None, max_length=50)
    parent_name: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=20)
    grade: str | None = Field(None, max_length=20)
    school: str | None = Field(None, max_length=100)
    interested_subjects: list[str] | None = None


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

    model_config = {"from_attributes": True}


class ExamScoreResponse(BaseModel):
    id: int
    exam_name: str
    subject: str
    score: float
    full_score: int
    exam_date: date

    model_config = {"from_attributes": True}


class HomeworkSummary(BaseModel):
    id: int
    subject: str
    content: str
    due_date: date | None = None
    is_completed: bool

    model_config = {"from_attributes": True}