"""Schemas for parent/student account management (admin)."""

from datetime import datetime

from pydantic import BaseModel


class AccountStudentBrief(BaseModel):
    id: int
    student_name: str
    id_number: str | None = None
    grade: str | None = None
    followup_status: str | None = None
    active_course_count: int = 0
    active_courses: list[str] = []


class AccountListItem(BaseModel):
    id: int
    account_type: str  # "parent" | "student"
    login_id: str
    display_name: str
    username: str | None = None
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    students: list[AccountStudentBrief] = []
