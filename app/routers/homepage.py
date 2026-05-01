"""Homepage router - aggregated data for landing page."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.about_card import AboutCard
from app.models.announcement import Announcement
from app.models.banner import Banner
from app.models.course import Course
from app.models.honor import Honor
from app.models.teacher import Teacher

router = APIRouter(prefix="/homepage", tags=["Homepage"])


@router.get("")
async def get_homepage_data(db: AsyncSession = Depends(get_db)):
    # Banners (active only, ordered)
    banner_result = await db.execute(
        select(Banner).where(Banner.is_active == True).order_by(Banner.display_order)
    )
    banners = banner_result.scalars().all()

    # About Us cards (active only, ordered, max 5)
    about_result = await db.execute(
        select(AboutCard)
        .where(AboutCard.is_active == True)
        .order_by(AboutCard.display_order)
        .limit(5)
    )
    about_cards = about_result.scalars().all()

    # Latest announcements (top 5)
    announcement_result = await db.execute(
        select(Announcement)
        .where(Announcement.is_published == True)
        .order_by(Announcement.created_at.desc())
        .limit(5)
    )
    announcements = announcement_result.scalars().all()

    # Featured teachers (active, ordered, top 4)
    teacher_result = await db.execute(
        select(Teacher)
        .where(Teacher.is_active == True)
        .order_by(Teacher.display_order)
        .limit(4)
    )
    teachers = teacher_result.scalars().all()

    # Latest honors (ordered, top 10)
    honor_result = await db.execute(
        select(Honor).order_by(Honor.display_order).limit(10)
    )
    honors = honor_result.scalars().all()

    # Early bird courses (active, ordered, top 6)
    course_result = await db.execute(
        select(Course)
        .where(Course.is_active == True, Course.is_early_bird == True)
        .order_by(Course.display_order)
        .limit(6)
    )
    early_bird_courses = course_result.scalars().all()

    return {
        "banners": [
            {
                "id": b.id,
                "title": b.title,
                "image_url": b.image_url,
                "link_url": b.link_url,
            }
            for b in banners
        ],
        "about_cards": [
            {
                "id": c.id,
                "title": c.title,
                "content": c.content,
                "icon": c.icon,
            }
            for c in about_cards
        ],
        "announcements": [
            {
                "id": a.id,
                "title": a.title,
                "content": a.content[:200],
                "priority": a.priority,
                "published_at": a.published_at,
            }
            for a in announcements
        ],
        "featured_teachers": [
            {
                "id": t.id,
                "name": t.name,
                "subject": t.subject,
                "title": t.title,
                "motto": t.motto,
                "photo_url": t.photo_url,
            }
            for t in teachers
        ],
        "latest_honors": [
            {
                "id": h.id,
                "student_name": h.student_name,
                "school": h.school,
                "department": h.department,
                "year": h.year,
            }
            for h in honors
        ],
        "early_bird_courses": [
            {
                "id": c.id,
                "name": c.name,
                "subject": c.subject,
                "category": c.category,
                "price": c.price,
                "early_bird_discount": c.early_bird_discount,
            }
            for c in early_bird_courses
        ],
    }