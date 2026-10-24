"""Leave & makeup schemas."""

from datetime import date, datetime, time
from pydantic import BaseModel, Field


class LeaveApplicationRequest(BaseModel):
    course_id: int | None = None
    leave_date: date
    leave_type: str = Field(pattern=r"^(sick|personal|other)$")
    reason: str | None = None
    # 家長指定要補課的場次（必填；同一課程的未來場次）
    requested_makeup_date: date
    requested_makeup_start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    requested_makeup_end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class LeaveApplicationResponse(BaseModel):
    id: int
    student_id: int | None = None
    course_id: int | None = None
    leave_date: date
    leave_type: str
    reason: str | None = None
    status: str
    course_name: str | None = None
    student_name: str | None = None
    requested_makeup_date: date | None = None
    requested_makeup_start: str | None = None
    requested_makeup_end: str | None = None
    review_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeaveApplicationListResponse(BaseModel):
    total: int
    applications: list[LeaveApplicationResponse]


class ReviewRequest(BaseModel):
    status: str = Field(pattern=r"^(approved|rejected)$")
    # 駁回時必填，會顯示給家長（例如「該補課時段已額滿」）
    reason: str | None = None


class MakeupClassResponse(BaseModel):
    id: int
    leave_id: int | None = None
    course_id: int
    course_name: str | None = None
    makeup_date: date
    start_time: str
    end_time: str
    classroom: str | None = None
    status: str
    requested_by: str = "teacher"
    notes: str | None = None

    model_config = {"from_attributes": True}


class MakeupClassCreateRequest(BaseModel):
    leave_id: int | None = None
    student_id: int
    course_id: int
    makeup_date: date
    start_time: str
    end_time: str
    classroom: str | None = None
    notes: str | None = None


class MakeupOptionResponse(BaseModel):
    """家長可選的補課場次（同一課程的未來場次）。"""

    date: date
    weekday: int
    start_time: str
    end_time: str
    classroom: str | None = None
    enrolled: int = 0
    capacity: int | None = None
    makeup_count: int = 0


class LeaveRulesResponse(BaseModel):
    rules: str
