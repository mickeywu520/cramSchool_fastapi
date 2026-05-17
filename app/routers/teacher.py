"""Teacher router with public listing and admin management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.teacher import Teacher
from app.models.user import User
from app.services import teacher_service as ts
from pydantic import BaseModel

router = APIRouter(prefix="/teachers", tags=["Teachers"])


class TeacherCreateRequest(BaseModel):
    name: str
    subject: str
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    display_order: int = 0
    is_active: bool = True


class TeacherUpdateRequest(BaseModel):
    name: str | None = None
    subject: str | None = None
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class TeacherAdminResponse(BaseModel):
    id: int
    user_id: int | None = None
    name: str
    subject: str
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    display_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


class TeacherListResponse(BaseModel):
    total: int
    teachers: list[TeacherAdminResponse]


@router.get("", response_model=TeacherListResponse)
async def list_teachers(
    search: str | None = Query(None),
    subject: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    teachers = await ts.get_teachers(db, search=search, subject=subject)
    return {"total": len(teachers), "teachers": teachers}


@router.get("/featured")
async def featured_teachers(db: AsyncSession = Depends(get_db)):
    return await ts.get_featured_teachers(db)


@router.get("/{teacher_id}")
async def get_teacher(teacher_id: int, db: AsyncSession = Depends(get_db)):
    return await ts.get_teacher_by_id(db, teacher_id)


@router.post("", response_model=TeacherAdminResponse, status_code=201)
async def create_teacher(
    data: TeacherCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherAdminResponse)
async def update_teacher(
    teacher_id: int,
    data: TeacherUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="老師不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(teacher, key, value)
    await db.commit()
    await db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}")
async def delete_teacher(
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="老師不存在")
    await db.delete(teacher)
    await db.commit()
    return {"success": True, "message": "已刪除"}