"""Banner router with public listing and admin management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.banner import Banner
from app.models.user import User
from app.schemas.banner import (
    BannerCreateRequest,
    BannerReorderRequest,
    BannerResponse,
    BannerUpdateRequest,
)

router = APIRouter(prefix="/banners", tags=["Banners"])
MAX_BANNERS = 6


@router.get("", response_model=list[BannerResponse])
async def list_banners(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Banner).where(Banner.is_active == True).order_by(Banner.display_order)
    )
    return result.scalars().all()


@router.get("/all", response_model=list[BannerResponse])
async def list_all_banners(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Banner).order_by(Banner.display_order))
    return result.scalars().all()


@router.get("/{banner_id}", response_model=BannerResponse)
async def get_banner(banner_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Banner).where(Banner.id == banner_id))
    banner = result.scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Banner 不存在")
    return banner


@router.post("", response_model=BannerResponse, status_code=201)
async def create_banner(
    data: BannerCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Banner.id))
    existing_count = len(result.scalars().all())
    if existing_count >= MAX_BANNERS:
        raise HTTPException(
            status_code=400,
            detail=f"已達到最大 Banner 數量上限 ({MAX_BANNERS} 張)",
        )
    banner = Banner(**data.model_dump())
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return banner


@router.put("/{banner_id}", response_model=BannerResponse)
async def update_banner(
    banner_id: int,
    data: BannerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Banner).where(Banner.id == banner_id))
    banner = result.scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Banner 不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(banner, key, value)
    await db.commit()
    await db.refresh(banner)
    return banner


@router.put("/reorder")
async def reorder_banners(
    data: BannerReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    for idx, banner_id in enumerate(data.order):
        result = await db.execute(select(Banner).where(Banner.id == banner_id))
        banner = result.scalar_one_or_none()
        if banner:
            banner.display_order = idx
    await db.commit()
    return {"success": True, "message": "排序已更新"}


@router.delete("/{banner_id}")
async def delete_banner(
    banner_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Banner).where(Banner.id == banner_id))
    banner = result.scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Banner 不存在")
    await db.delete(banner)
    await db.commit()
    return {"success": True, "message": "已刪除"}