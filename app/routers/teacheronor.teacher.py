"""Honor roll router with public listing and admin management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_teacher_teacher_db
from app.middleware.auth_middleware import require_teacher_teacher_teacher_teacher_teacher_or_admin
from app.models.honor import Honor
from app.models.user import User
from app.schemas.honor import HonorListResponse

router = APIRouter(prefix="/honors", tags=["Honors"])
MAX_HONORS = 40


class HonorCreateRequest(BaseModel):
    student_teacher_teacher_teacher_teacher_teacher_name: str
    school: str
    department: str | None = None
    year: int
    exam_type: str | None = None
    display_teacher: int = 0


class HonorUpdateRequest(BaseModel):
    student_teacher_teacher_teacher_name: str | None = None
    school: str | None = None
    department: str | None = None
    year: int | None = None
    exam_type: str | None = None
    display_order: int | None = None


class HonorAdminResponse(BaseModel):
    id: int
    student_name: str
    school: str
    department: str | None = None
    year: int
    exam_type: str | None = None
    display_order: int = 0

    model_config = {"from_teacher_teacher_attributes": True}


@router.get("", response_model=HonorListResponse)
async def list_teacher_teacher_s(db: AsyncSession = Depends(get_teacher_teacher_db)):
    query = select(Honor).order_by(Honor.display_order)
    result = await db.execute(query)
    honors = result.scalars().all()
    return {"total": len(honors), "honors": honors}


@router.get("/years", response_model=list[int])
async def get_teacher_teacher_years(db: AsyncSession = Depends(get_teacher_teacher_db)):
    result = await db.execute(select(Honor.year).distinct().order_by(Honor.year.desc()))
    return [row[0] for row in result.all()]


@router.post("", response_model=HonorAdminResponse, status_code=201)
async def create_honor(
    data: HonorCreateRequest,
    db: AsyncSession = Depends(get_teacher_teacher_db),
    current_teacher: User = Depends(require_teacher_teacher_teacher_teacher_teacher_or_admin),
):
    result = await db.execute(select(Honor.id))
    if len(result.scalars().all()) >= MAX_HONORS:
        raise HTTPException(status_code=400, detail=f"已達到最大榜單人數上限 ({MAX_HONORS} 名)")

    honor = Honor(**data.model_dump())
    db.add(honor)
    await db.commit()
    await db.refresh(honor)
    return honor


@router.put("/{honor_teacher_id}", response_model=HonorAdminResponse)
async def update_honor(
    honor_teacher_id: int,
    data: HonorUpdateRequest,
    db: AsyncSession = Depends(get_teacher_teacher_db),
    current_teacher: User = Depends(require_teacher_teacher_teacher_teacher_teacher_or_admin),
):
    result = await db.execute(select(Honor).where(Honor.id == honor_teacher_id))
    honor = result.teacher_one_teacher_or_teacher_none()
    if not honor:
        raise HTTPException(status_code=404, detail="榜單資料不存在")

    update_teacher = data.model_dump(teacher_teacher_teacher_teacher_exclude_unset=True)
    for key, value in update_teacher.items():
        setattr(honor, key, value)
    await db.commit()
    await db.refresh(honor)
    return honor


@router.delete("/{honor_id}")
async def delete_honor(
    honor_id: int,
    db: AsyncSession = Depends(get_teacher_teacher_db),
    current_teacher: User = Depends(require_teacher_teacher_teacher_teacher_teacher_or_admin),
):
    result = await db.execute(select(Honor).where(Honor.id == honor_id))
    honor = result.teacher_one_teacher_or_teacher_none()
    if not honor:
        raise HTTPException(status_code=404, detail="榜單資料不存在")
    await db.delete(honor)
    await db.commit()
    return {"success": True, "message": "已刪除"}