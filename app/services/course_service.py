"""Course service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.utils.exceptions import ConflictException, NotFoundException


async def get_courses(
    db: AsyncSession,
    category: str | None = None,
    subject: str | None = None,
    grade_level: str | None = None,
    is_early_bird: bool | None = None,
) -> list[Course]:
    query = select(Course).options(selectinload(Course.teacher))
    if category:
        query = query.where(Course.category == category)
    if subject:
        query = query.where(Course.subject == subject)
    if grade_level:
        query = query.where(Course.grade_level == grade_level)
    if is_early_bird is not None:
        query = query.where(Course.is_early_bird == is_early_bird)
    query = query.order_by(Course.display_order)
    result = await db.execute(query)
    return result.scalars().all()


async def get_course_by_id(db: AsyncSession, course_id: int) -> Course:
    result = await db.execute(
        select(Course).where(Course.id == course_id).options(selectinload(Course.teacher))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise NotFoundException("Course")
    return course


async def enroll_course(db: AsyncSession, student_id: int, course_id: int) -> Enrollment:
    course = await get_course_by_id(db, course_id)
    if not course.is_active:
        raise ConflictException("此課程目前未開放報名")

    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException("已報名此課程")

    enrollment = Enrollment(student_id=student_id, course_id=course_id, status="active")
    db.add(enrollment)
    await db.flush()
    return enrollment


async def drop_course(db: AsyncSession, student_id: int, course_id: int):
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
            Enrollment.status == "active",
        )
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise NotFoundException("Enrollment")
    enrollment.status = "dropped"