"""Communication book schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class StudentInfo(BaseModel):
    id: int
    student_name: str
    grade: str
    student_number: str | None = None
    avatar_url: str | None = None


class StudentSessionEntry(BaseModel):
    id: int
    session_id: int
    entry_date: date
    course_name: str | None = None
    tutor_name: str | None = None
    class_progress: str | None = None
    class_homework: str | None = None
    class_exam_scope: str | None = None
    class_announcements: str | None = None
    arrival_time: str | None = None
    departure_time: str | None = None
    handout_completed: bool = False
    exam_score: int | None = None
    custom_scores: dict[str, int] = {}
    tutoring_attendance: bool = False
    notes: str | None = None
    parent_signed: bool = False
    parent_signed_at: datetime | None = None

    model_config = {"from_attributes": True}


class StudentEntryListResponse(BaseModel):
    student: StudentInfo
    entries: list[StudentSessionEntry]


class WeeklyEntrySummary(BaseModel):
    id: int
    entry_date: date
    is_signed: bool = False


class WeeklyResponse(BaseModel):
    student: StudentInfo
    week_start: date
    week_end: date
    entries: list[WeeklyEntrySummary]


class FeedbackRequest(BaseModel):
    is_signed: bool = False


# ── Old schemas kept for admin compatibility ──

class HomeworkItem(BaseModel):
    id: int
    subject: str
    content: str
    due_date: date | None = None
    is_completed: bool = False
    model_config = {"from_attributes": True}


class ReminderItem(BaseModel):
    id: int
    content: str
    priority: str = "normal"
    model_config = {"from_attributes": True}


class ParentFeedbackResponse(BaseModel):
    feedback: str | None = None
    is_signed: bool = False
    signed_at: datetime | None = None
    model_config = {"from_attributes": True}


class CommunicationEntryResponse(BaseModel):
    id: int
    entry_date: date
    focus_score: int | None = None
    interaction_score: int | None = None
    homework_completion: str | None = None
    teacher_comment: str | None = None
    teacher_name: str | None = None
    homework: list[HomeworkItem] = []
    reminders: list[ReminderItem] = []
    parent_feedback: ParentFeedbackResponse | None = None
    model_config = {"from_attributes": True}


class CommunicationListResponse(BaseModel):
    student: StudentInfo
    entries: list[CommunicationEntryResponse]


class CommunicationEntryCreateRequest(BaseModel):
    student_id: int
    teacher_id: int
    entry_date: date
    focus_score: int | None = None
    interaction_score: int | None = None
    homework_completion: str | None = None
    teacher_comment: str | None = None
    homework: list[dict] = []
    reminders: list[dict] = []
