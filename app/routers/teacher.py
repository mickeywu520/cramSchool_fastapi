"""Teacher router with public listing and admin management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.teacher import Teacher, TeacherSubject
from app.models.user import User
from app.services import teacher_service as ts
from pydantic import BaseModel

router = APIRouter(prefix="/teachers", tags=["Teachers"])


class TeacherCreateRequest(BaseModel):
    name: str
    subject: str = ""
    subjects: list[str] = []
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    branch_id: int | None = None
    display_order: int = 0
    is_active: bool = True


class TeacherUpdateRequest(BaseModel):
    name: str | None = None
    subject: str | None = None
    subjects: list[str] | None = None
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    branch_id: int | None = None
    display_order: int | None = None
    is_active: bool | None = None


class TeacherAdminResponse(BaseModel):
    id: int
    user_id: int | None = None
    name: str
    subject: str
    subjects: list[str] = []
    title: str | None = None
    motto: str | None = None
    description: str | None = None
    photo_url: str | None = None
    life_photo_url: str | None = None
    branch_id: int | None = None
    display_order: int = 0
    is_active: bool = True

    model_config = {"from_attributes": True}


class TeacherListResponse(BaseModel):
    total: int
    teachers: list[TeacherAdminResponse]


@router.get("", response_model=TeacherListResponse)
async def list_teachers(
    response: Response,
    search: str | None = Query(None),
    subject: str | None = Query(None),
    branch_id: int | None = Query(None),
    include_inactive: bool = Query(False, description="管理端顯示包含隱藏師資"),
    db: AsyncSession = Depends(get_db),
):
    teachers = await ts.get_teachers(
        db, search=search, subject=subject, branch_id=branch_id,
        is_active=None if include_inactive else True,
    )
    if include_inactive:
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = settings.public_cache_control()
    return {"total": len(teachers), "teachers": teachers}


def _serialize_teacher(t: Teacher) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "name": t.name,
        "subject": t.subject,
        "subjects": t.subjects,
        "title": t.title,
        "motto": t.motto,
        "description": t.description,
        "photo_url": t.photo_url,
        "life_photo_url": t.life_photo_url,
        "branch_id": t.branch_id,
        "display_order": t.display_order,
        "is_active": t.is_active,
    }


@router.get("/featured")
async def featured_teachers(response: Response, db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = settings.public_cache_control()
    teachers = await ts.get_featured_teachers(db)
    return [_serialize_teacher(t) for t in teachers]


@router.get("/{teacher_id}")
async def get_teacher(response: Response, teacher_id: int, db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = settings.public_cache_control()
    teacher = await ts.get_teacher_by_id(db, teacher_id)
    return _serialize_teacher(teacher)


@router.post("", response_model=TeacherAdminResponse, status_code=201)
async def create_teacher(
    data: TeacherCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    payload = data.model_dump()
    subjects = [s.strip() for s in (payload.pop("subjects") or []) if s and s.strip()]
    if not subjects:
        primary = (payload.get("subject") or "").strip()
        if not primary:
            raise HTTPException(status_code=400, detail="請至少選擇一個科目")
        subjects = [primary]
    payload["subject"] = subjects[0]
    teacher = Teacher(**payload)
    teacher.subjects_rel = [TeacherSubject(subject=s) for s in subjects]
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
    new_subjects: list[str] | None = update_data.pop("subjects", None)
    if new_subjects is not None:
        subjects = [s.strip() for s in new_subjects if s and s.strip()]
        if not subjects:
            raise HTTPException(status_code=400, detail="請至少選擇一個科目")
        teacher.subjects_rel = [TeacherSubject(subject=s) for s in subjects]
        update_data["subject"] = subjects[0]
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