"""Course router - course listing, enrollment."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.middleware.auth_middleware import get_current_user, require_student
from app.models.student import Student
from app.models.user import User
from app.schemas.course import CourseListResponse, CourseResponse
from app.services import course_service

router = APIRouter(prefix="/courses", tags=["Courses"])

async def _resolve_student(
    db: AsyncSession, user_id: int, student_id: int | None = None
) -> Student:
    """解析目前使用者的學生（本人或家長），支援指定 student_id。"""
    if student_id is not None:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student and (student.user_id == user_id or student.parent_user_id == user_id):
            return student
        raise HTTPException(status_code=404, detail="Student not found")
    result = await db.execute(select(Student).where(Student.user_id == user_id))
    student = result.scalar_one_or_none()
    if not student:
        result = await db.execute(
            select(Student)
            .where(Student.parent_user_id == user_id)
            .order_by(Student.id.asc())
            .limit(1)
        )
        student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

def _format_course(c):
    return {
        "id": c.id, "name": c.name, "category": c.category, "subject": c.subject,
        "teacher_id": c.teacher_id, "teacher_name": c.teacher.name if c.teacher else None,
        "description": c.description, "schedule": c.schedule,
        "grade_level": c.grade_level, "day_of_week": c.day_of_week,
        "days_of_week": c.days_of_week,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "start_time": c.start_time, "end_time": c.end_time, "location": c.location,
        "tutoring_day_of_week": c.tutoring_day_of_week,
        "tutoring_days_of_week": c.tutoring_days_of_week,
        "tutoring_start_time": c.tutoring_start_time,
        "tutoring_end_time": c.tutoring_end_time,
        "tutoring_location": c.tutoring_location,
        "branch_id": c.branch_id, "branch_name": c.branch.name if c.branch else None,
        "school_year": c.school_year, "semester": c.semester,
        "price": c.price, "max_students": c.max_students,
        "is_early_bird": c.is_early_bird, "early_bird_discount": c.early_bird_discount,
        "is_active": c.is_active, "display_order": c.display_order,
    }


@router.get("", response_model=CourseListResponse)
async def list_courses(
    response: Response,
    category: str | None = Query(None),
    subject: str | None = Query(None),
    grade_level: str | None = Query(None),
    is_early_bird: bool | None = Query(None),
    branch_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    courses = await course_service.get_courses(
        db, category=category, subject=subject, grade_level=grade_level,
        is_early_bird=is_early_bird, branch_id=branch_id, is_active=True,
    )
    result = [_format_course(c) for c in courses]
    response.headers["Cache-Control"] = settings.public_cache_control()
    return {"total": len(result), "courses": result}


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(response: Response, course_id: int, db: AsyncSession = Depends(get_db)):
    c = await course_service.get_course_by_id(db, course_id)
    response.headers["Cache-Control"] = settings.public_cache_control()
    return _format_course(c)


@router.post("/{course_id}/enroll", status_code=201)
async def enroll_course(
    course_id: int,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    await course_service.enroll_course(db, student.id, course_id)
    await db.commit()
    return {"success": True, "message": "報名成功"}


@router.post("/{course_id}/drop")
async def drop_course(
    course_id: int,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    await course_service.drop_course(db, student.id, course_id)
    await db.commit()
    return {"success": True, "message": "已取消報名"}
