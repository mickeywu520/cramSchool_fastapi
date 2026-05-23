"""Admin router - administrative endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.student import Student
from app.models.user import User
from app.schemas.communication import CommunicationListResponse
from app.services import communication_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/students")
async def list_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(Student)
        .options(selectinload(Student.user))
        .order_by(Student.student_name)
    )
    students = result.scalars().all()
    return [
        {
            "id": s.id,
            "student_name": s.student_name,
            "grade": s.grade,
            "school": s.school,
        }
        for s in students
    ]


@router.get("/entries", response_model=CommunicationListResponse)
async def get_student_entries(
    student_id: int = Query(..., description="學生 ID"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    entries = await communication_service.get_entries(db, student_id, date_from, date_to)
    items = [communication_service.format_entry_response(e) for e in entries]
    return {
        "student": {
            "id": student.id,
            "student_name": student.student_name,
            "grade": student.grade,
            "student_number": student.student_number,
            "avatar_url": student.avatar_url,
        },
        "entries": items,
    }
