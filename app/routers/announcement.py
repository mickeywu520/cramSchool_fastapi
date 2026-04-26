"""Announcement router."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.announcement import Announcement
from app.models.user import User
from app.schemas.announcement import AnnouncementCreateRequest, AnnouncementResponse

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get("", response_model=list[AnnouncementResponse])
async def list_announcements(
    target_role: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Announcement).where(Announcement.is_published == True).order_by(Announcement.created_at.desc())
    if target_role:
        query = query.where(
            (Announcement.target_role == target_role) | (Announcement.target_role == "all")
        )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(announcement_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        from app.utils.exceptions import NotFoundException
        raise NotFoundException("Announcement")
    return announcement


@router.post("", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    data: AnnouncementCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    from datetime import datetime, timezone
    announcement = Announcement(
        title=data.title,
        content=data.content,
        priority=data.priority,
        target_role=data.target_role,
        is_published=data.is_published,
        published_at=datetime.now(timezone.utc) if data.is_published else None,
        created_by=current_user.id,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    return announcement