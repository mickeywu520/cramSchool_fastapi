"""Communication book router."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_student, require_teacher_or_admin
from app.models.user import User
from app.schemas.communication import (
    CommunicationEntryCreateRequest,
    CommunicationEntryResponse,
    CommunicationListResponse,
    FeedbackRequest,
    WeeklyResponse,
)
from app.services import communication_service, student_service

router = APIRouter(prefix="/communication", tags=["Communication Book"])


@router.get("/entries", response_model=CommunicationListResponse)
async def get_my_entries(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    entries = await communication_service.get_entries(db, student.id, date_from, date_to)
    items = [communication_service.format_entry_response(e) for e in entries]
    return {
        "student": {
            "id": student.id, "student_name": student.student_name,
            "grade": student.grade, "student_number": student.student_number,
            "avatar_url": student.avatar_url,
        },
        "entries": items,
    }


@router.get("/weekly", response_model=WeeklyResponse)
async def get_weekly(
    week_start: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    entries = await communication_service.get_weekly_entries(db, student.id, week_start)
    summaries = [
        {
            "id": e.id, "entry_date": e.entry_date,
            "has_feedback": e.parent_feedback is not None and e.parent_feedback.feedback is not None,
            "is_signed": e.parent_feedback.is_signed if e.parent_feedback else False,
        }
        for e in entries
    ]
    from datetime import timedelta
    ws = week_start or (date.today() - timedelta(days=date.today().weekday()))
    return {
        "student": {
            "id": student.id, "student_name": student.student_name,
            "grade": student.grade, "student_number": student.student_number,
            "avatar_url": student.avatar_url,
        },
        "week_start": ws,
        "week_end": ws + timedelta(days=6),
        "entries": summaries,
    }


@router.get("/entries/{entry_id}", response_model=CommunicationEntryResponse)
async def get_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    entry = await communication_service.get_entry_by_id(db, entry_id, student.id)
    return communication_service.format_entry_response(entry)


@router.post("/entries/{entry_id}/feedback")
async def submit_feedback(
    entry_id: int,
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    await communication_service.submit_feedback(db, entry_id, student.id, data.feedback, data.is_signed)
    await db.commit()
    return {"success": True, "message": "回饋已送出"}


@router.post("/entries", response_model=CommunicationEntryResponse, status_code=201)
async def create_entry(
    data: CommunicationEntryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    entry = await communication_service.create_entry(db, data.model_dump())
    await db.commit()
    # Reload with relationships
    entry = await communication_service.get_entry_by_id(db, entry.id, data.student_id)
    return communication_service.format_entry_response(entry)