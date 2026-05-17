"""Settings router for site-wide configuration."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.site_setting import SiteSetting
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["Settings"])


class BannerIntervalRequest(BaseModel):
    seconds: int


@router.get("/banner-interval")
async def get_banner_interval(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SiteSetting).where(SiteSetting.key == "banner_interval"))
    setting = result.scalar_one_or_none()
    return {"seconds": int(setting.value) if setting else 5}


@router.put("/banner-interval")
async def update_banner_interval(
    data: BannerIntervalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    if data.seconds < 3 or data.seconds > 10:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="秒數必須在 3-10 之間")
    result = await db.execute(select(SiteSetting).where(SiteSetting.key == "banner_interval"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = str(data.seconds)
    else:
        setting = SiteSetting(key="banner_interval", value=str(data.seconds))
        db.add(setting)
    await db.commit()
    return {"seconds": data.seconds}
