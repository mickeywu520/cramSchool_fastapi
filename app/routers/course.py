"""Course router - course listing, enrollment."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user, require_student
from app.models.user import User
from app.schemas.course import CourseListResponse, CourseResponse
from app.services import course_service

router = APIRouter(prefix="/courses", tags=["Courses"])

def _format_course(c):
    return {
        "id": c.id, "name": c.name, "category": c.category, "subject": c.subject,
        "teacher_id": c.teacher_id, "teacher_name": c.teacher.name if c.teacher else None,
        "description": c.description, "schedule": c.schedule,
        "grade_level": c.grade_level, "day_of_week": c.day_of_week,
        "start_time": c.start_time, "end_time": c.end_time, "location": c.location,
        "school_year": c.school_year, "semester": c.semester,
        "price": c.price, "max_students": c.max_students,
        "is_early_bird": c.is_early_bird, "early_bird_discount": c.early_bird_discount,
        "is_active": c.is_active, "display_order": c.display_order,
    }


@router.get("", response_model=CourseListResponse)
async def list_courses(
    category: str | None = Query(None),
    subject: str | None = Query(None),
    grade_level: str | None = Query(None),
    is_early_bird: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    courses = await course_service.get_courses(
        db, category=category, subject=subject, grade_level=grade_level, is_early_bird=is_early_bird
    )
    result = [_format_course(c) for c in courses]
    return {"total": len(result), "courses": result}


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    c = await course_service.get_course_by_id(db, course_id)
    return _format_course(c)


@router.post("/{course_id}/enroll", status_code=201)
async def enroll_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    await course_service.enroll_course(db, student.id, course_id)
    await db.commit()
    return {"success": True, "message": "報名成功"}


@router.post("/{course_id}/drop")
async def drop_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = current_user.student
    await course_service.drop_course(db, student.id, course_id)
    await db.commit()
    return {"success": True, "message": "已取消報名"}
