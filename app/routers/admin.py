"""Admin router - administrative endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.student import Student
from app.models.user import User

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
