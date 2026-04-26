"""Teacher service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.teacher import Teacher
from app.utils.exceptions import NotFoundException


async def get_teachers(
    db: AsyncSession,
    search: str | None = None,
    subject: str | None = None,
    is_active: bool = True,
) -> list[Teacher]:
    query = select(Teacher).where(Teacher.is_active == is_active)
    if subject:
        query = query.where(Teacher.subject == subject)
    if search:
        query = query.where(Teacher.name.contains(search))
    query = query.order_by(Teacher.display_order)
    result = await db.execute(query)
    return result.scalars().all()


async def get_teacher_by_id(db: AsyncSession, teacher_id: int) -> Teacher:
    result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise NotFoundException("Teacher")
    return teacher


async def get_featured_teachers(db: AsyncSession, limit: int = 4) -> list[Teacher]:
    result = await db.execute(
        select(Teacher)
        .where(Teacher.is_active == True)
        .order_by(Teacher.display_order)
        .limit(limit)
    )
    return result.scalars().all()