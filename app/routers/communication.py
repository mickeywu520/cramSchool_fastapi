"""Communication book router."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_student
from app.models.student import Student
from app.models.user import User
from app.schemas.communication import (
    FeedbackRequest,
    StudentEntryListResponse,
    StudentSessionEntry,
    WeeklyResponse,
    StudentInfo,
)
from app.services import communication_service

router = APIRouter(prefix="/communication", tags=["Communication Book"])


async def _get_student(db: AsyncSession, user_id: int, student_id: int | None = None) -> Student:
    if student_id is not None:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student and (student.user_id == user_id or student.parent_user_id == user_id):
            return student
        raise HTTPException(status_code=404, detail="Student not found")
    result = await db.execute(select(Student).where(Student.user_id == user_id))
    student = result.scalar_one_or_none()
    if not student:
        result = await db.execute(
            select(Student)
            .where(Student.parent_user_id == user_id)
            .order_by(Student.id.asc())
            .limit(1)
        )
        student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/entries", response_model=StudentEntryListResponse)
async def get_my_entries(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _get_student(db, current_user.id, student_id)
    entries = await communication_service.get_session_entries(db, student.id, date_from, date_to)
    items = [StudentSessionEntry(**e) for e in entries]
    return StudentEntryListResponse(
        student=StudentInfo(
            id=student.id, student_name=student.student_name,
            grade=student.grade, student_number=student.student_number,
            avatar_url=student.avatar_url,
        ),
        entries=items,
    )


@router.get("/weekly", response_model=WeeklyResponse)
async def get_weekly(
    week_start: date | None = Query(None),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _get_student(db, current_user.id, student_id)
    entries = await communication_service.get_session_weekly(db, student.id, week_start)
    from datetime import timedelta
    ws = week_start or (date.today() - timedelta(days=date.today().weekday()))
    return WeeklyResponse(
        student=StudentInfo(
            id=student.id, student_name=student.student_name,
            grade=student.grade, student_number=student.student_number,
            avatar_url=student.avatar_url,
        ),
        week_start=ws,
        week_end=ws + timedelta(days=6),
        entries=entries,
    )


@router.post("/entries/{entry_id}/feedback")
async def submit_feedback(
    entry_id: int,
    data: FeedbackRequest,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _get_student(db, current_user.id, student_id)
    await communication_service.submit_session_feedback(
        db, entry_id, student.id, data.is_signed
    )
    await db.commit()
    return {"success": True, "message": "簽署成功"}
