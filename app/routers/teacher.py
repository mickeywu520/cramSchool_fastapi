"""Teacher router - public teacher listing."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.teacher import TeacherListResponse, TeacherResponse
from app.services import teacher_service

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.get("", response_model=TeacherListResponse)
async def list_teachers(
    search: str | None = Query(None),
    subject: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    teachers = await teacher_service.get_teachers(db, search=search, subject=subject)
    return {"total": len(teachers), "teachers": teachers}


@router.get("/featured", response_model=list[TeacherResponse])
async def featured_teachers(db: AsyncSession = Depends(get_db)):
    return await teacher_service.get_featured_teachers(db)


@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(teacher_id: int, db: AsyncSession = Depends(get_db)):
    return await teacher_service.get_teacher_by_id(db, teacher_id)