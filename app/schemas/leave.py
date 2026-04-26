"""Leave & makeup schemas."""

from datetime import date, datetime, time
from pydantic import BaseModel, Field


class LeaveApplicationRequest(BaseModel):
    course_id: int | None = None
    leave_date: date
    leave_type: str = Field(pattern=r"^(sick|personal|other)$")
    reason: str | None = None


class LeaveApplicationResponse(BaseModel):
    id: int
    leave_date: date
    leave_type: str
    reason: str | None = None
    status: str
    course_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeaveApplicationListResponse(BaseModel):
    total: int
    applications: list[LeaveApplicationResponse]


class ReviewRequest(BaseModel):
    status: str = Field(pattern=r"^(approved|rejected)$")
    review_comment: str | None = None


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


class LeaveRulesResponse(BaseModel):
    rules: str