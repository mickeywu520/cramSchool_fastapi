"""Pydantic schemas for course-based communication sessions."""

from datetime import date, datetime
from pydantic import BaseModel


class ExamColumnDef(BaseModel):
    name: str
    display_order: int


class StudentSessionData(BaseModel):
    student_id: int
    arrival_time: str | None = None
    departure_time: str | None = None
    progress: str | None = None
    homework: str | None = None
    vocab: str | None = "優異"
    exam_scope: str | None = None
    announcements: str | None = None
    handout_status: str | None = None
    homework_material: str | None = None
    homework_workbook: str | None = None
    exam_score: int | None = None
    custom_scores: dict[str, int] = {}
    tutoring_attendance: bool = False
    reschedule_date: date | None = None
    notes: str | None = None


class SessionCreateRequest(BaseModel):
    course_id: int
    entry_date: date
    tutoring_threshold: int | None = None
    class_progress: str | None = None
    class_homework: str | None = None
    class_exam_scope: str | None = None
    class_announcements: str | None = None
    exam_columns: list[ExamColumnDef] = []
    students: list[StudentSessionData] = []


class SessionUpdateRequest(BaseModel):
    entry_date: date | None = None
    tutoring_threshold: int | None = None
    class_progress: str | None = None
    class_homework: str | None = None
    class_exam_scope: str | None = None
    class_announcements: str | None = None
    exam_columns: list[ExamColumnDef] | None = None
    students: list[StudentSessionData] | None = None


class StudentSessionResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    arrival_time: str | None = None
    departure_time: str | None = None
    progress: str | None = None
    homework: str | None = None
    vocab: str | None = "優異"
    exam_scope: str | None = None
    announcements: str | None = None
    handout_status: str | None = None
    homework_material: str | None = None
    homework_workbook: str | None = None
    exam_score: int | None = None
    custom_scores: dict[str, int] = {}
    tutoring_attendance: bool = False
    reschedule_date: date | None = None
    notes: str | None = None
    parent_feedback: str | None = None
    parent_signed: bool = False
    parent_signed_at: datetime | None = None
    # 本堂課的請假狀態（approved 時前端鎖住輸入；pending 只提示）
    leave_status: str | None = None
    leave_type: str | None = None
    leave_reason: str | None = None
    # 已核准的補課資訊（給老師參考，例如「補 11/07 補A 14:00-16:00」）
    makeup_date: date | None = None
    makeup_room: str | None = None
    makeup_start: str | None = None
    makeup_end: str | None = None

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: int
    course_id: int
    entry_date: date
    punch_generated: bool = False
    tutoring_threshold: int | None = None
    class_progress: str | None = None
    class_homework: str | None = None
    class_exam_scope: str | None = None
    class_announcements: str | None = None
    exam_columns: list[ExamColumnDef] = []
    students: list[StudentSessionResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionListItem(BaseModel):
    id: int
    course_id: int
    entry_date: date
    tutoring_threshold: int | None = None
    student_count: int = 0
    punch_generated: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
