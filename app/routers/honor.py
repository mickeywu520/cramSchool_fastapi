"""Honor roll router with public listing and admin management."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.honor import Honor
from app.models.user import User
from app.schemas.honor import HonorListResponse, HonorResponse

router = APIRouter(prefix="/honors", tags=["Honors"])
MAX_HONORS = 40


class HonorCreateRequest(BaseModel):
    student_name: str
    school: str
    department: str | None = None
    year: int
    exam_type: str | None = None
    display_order: int = 0


class HonorUpdateRequest(BaseModel):
    student_name: str | None = None
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

    model_config = {"from_attributes": True}


@router.get("", response_model=HonorListResponse)
async def list_honors(
    response: Response,
    year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Honor).order_by(Honor.display_order)
    if year:
        query = query.where(Honor.year == year)
    result = await db.execute(query)
    honors = result.scalars().all()
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return {"total": len(honors), "honors": honors}


@router.get("/years", response_model=list[int])
async def get_honor_years(response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Honor.year).distinct().order_by(Honor.year.desc())
    )
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return [row[0] for row in result.all()]


@router.post("", response_model=HonorAdminResponse, status_code=201)
async def create_honor(
    data: HonorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Honor.id))
    if len(result.scalars().all()) >= MAX_HONORS:
        raise HTTPException(
            status_code=400,
            detail=f"已達到最大榜單人數上限 ({MAX_HONORS} 名)",
        )
    honor = Honor(**data.model_dump())
    db.add(honor)
    await db.commit()
    await db.refresh(honor)
    return honor


@router.put("/{honor_id}", response_model=HonorAdminResponse)
async def update_honor(
    honor_id: int,
    data: HonorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Honor).where(Honor.id == honor_id))
    honor = result.scalar_one_or_none()
    if not honor:
        raise HTTPException(status_code=404, detail="榜單資料不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(honor, key, value)
    await db.commit()
    await db.refresh(honor)
    return honor


@router.delete("/{honor_id}")
async def delete_honor(
    honor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Honor).where(Honor.id == honor_id))
    honor = result.scalar_one_or_none()
    if not honor:
        raise HTTPException(status_code=404, detail="榜單資料不存在")
    await db.delete(honor)
    await db.commit()
    return {"success": True, "message": "已刪除"}