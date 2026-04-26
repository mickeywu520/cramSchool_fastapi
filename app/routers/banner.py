"""Banner router."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.banner import Banner
from app.models.user import User
from app.schemas.banner import BannerCreateRequest, BannerReorderRequest, BannerResponse

router = APIRouter(prefix="/banners", tags=["Banners"])


@router.get("", response_model=list[BannerResponse])
async def list_banners(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Banner).where(Banner.is_active == True).order_by(Banner.display_order)
    )
    return result.scalars().all()


@router.post("", response_model=BannerResponse, status_code=201)
async def create_banner(
    data: BannerCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    banner = Banner(**data.model_dump())
    db.add(banner)
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
        from app.utils.exceptions import NotFoundException
        raise NotFoundException("Banner")
    await db.delete(banner)
    await db.commit()
    return {"success": True, "message": "已刪除"}