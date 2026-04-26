"""Student router - profile, progress, courses, exams, homework."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_student
from app.models.user import User
from app.schemas.student import (
    CourseSummary,
    ExamScoreResponse,
    HomeworkSummary,
    ProgressResponse,
    StudentResponse,
    StudentUpdateRequest,
)
from app.services import student_service

router = APIRouter(prefix="/student", tags=["Student"])


@router.get("/me", response_model=StudentResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_student_response(db, current_user.id)


@router.put("/me", response_model=StudentResponse)
async def update_my_profile(
    data: StudentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    result = await student_service.update_student(db, current_user.id, data.model_dump(exclude_none=True))
    await db.commit()
    return result


@router.get("/progress", response_model=ProgressResponse)
async def get_my_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_progress(db, current_user.id)


@router.get("/courses", response_model=list[CourseSummary])
async def get_my_courses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_courses(db, current_user.id)


@router.get("/exams", response_model=list[ExamScoreResponse])
async def get_my_exams(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_exams(db, current_user.id)


@router.get("/homework", response_model=list[HomeworkSummary])
async def get_my_homework(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    return await student_service.get_my_homework(db, current_user.id)