"""Admin router - administrative endpoints."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.schemas.communication import CommunicationListResponse
from app.schemas.course import (
    CourseCreateRequest,
    CourseResponse,
    CourseUpdateRequest,
    EnrollmentCreateRequest,
    EnrollmentResponse,
)
from app.services import communication_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


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


# ── Students ──

@router.get("/students")
async def list_students(
    course_id: int | None = Query(None),
    grade_level: str | None = Query(None, description="年級: 小四/小五/小六/國七/國八/國九/高一/高二/高三"),
    search: str | None = Query(None, description="姓名關鍵字"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = select(Student).options(selectinload(Student.user))
    if grade_level:
        query = query.where(Student.grade.like(f"{grade_level}%"))
    if search:
        query = query.where(Student.student_name.contains(search))
    if course_id:
        query = query.join(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.status == "active"
        )
    query = query.order_by(Student.student_name)
    result = await db.execute(query)
    students = result.scalars().all()
    return [
        {
            "id": s.id,
            "student_name": s.student_name,
            "grade": s.grade,
            "school": s.school,
        }
        for s in students
    ]


# ── Communication Book Entries ──

@router.get("/entries", response_model=CommunicationListResponse)
async def get_student_entries(
    student_id: int = Query(..., description="學生 ID"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    student_result = await db.execute(select(Student).where(Student.id == student_id))
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    entries = await communication_service.get_entries(db, student_id, date_from, date_to)
    items = [communication_service.format_entry_response(e) for e in entries]
    return {
        "student": {
            "id": student.id,
            "student_name": student.student_name,
            "grade": student.grade,
            "student_number": student.student_number,
            "avatar_url": student.avatar_url,
        },
        "entries": items,
    }


# ── Courses CRUD ──

@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    category: str | None = Query(None),
    grade_level: str | None = Query(None),
    subject: str | None = Query(None),
    teacher_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = select(Course).options(selectinload(Course.teacher))
    if category:
        query = query.where(Course.category == category)
    if grade_level:
        query = query.where(Course.grade_level == grade_level)
    if subject:
        query = query.where(Course.subject == subject)
    if teacher_id:
        query = query.where(Course.teacher_id == teacher_id)
    query = query.order_by(Course.category, Course.grade_level, Course.day_of_week, Course.display_order)
    result = await db.execute(query)
    courses = result.scalars().all()
    return [_format_course(c) for c in courses]


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    data: CourseCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    course = Course(**data.model_dump())
    db.add(course)
    await db.flush()
    await db.refresh(course)
    # Reload with teacher
    result = await db.execute(
        select(Course).where(Course.id == course.id).options(selectinload(Course.teacher))
    )
    return _format_course(result.scalar_one())


@router.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    data: CourseUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id).options(selectinload(Course.teacher))
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for key, val in data.model_dump(exclude_none=True).items():
        setattr(course, key, val)
    await db.flush()
    await db.refresh(course)
    return _format_course(course)


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.delete(course)
    await db.commit()
    return {"success": True, "message": "課程已刪除"}


# ── Enrollment Management ──

@router.get("/enrollments", response_model=list[EnrollmentResponse])
async def list_enrollments(
    course_id: int | None = Query(None),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = (
        select(Enrollment)
        .options(selectinload(Enrollment.student), selectinload(Enrollment.course))
    )
    if course_id:
        query = query.where(Enrollment.course_id == course_id)
    if student_id:
        query = query.where(Enrollment.student_id == student_id)
    query = query.order_by(Enrollment.enrolled_at.desc())
    result = await db.execute(query)
    enrollments = result.scalars().all()
    return [
        {
            "id": e.id,
            "student_id": e.student_id,
            "student_name": e.student.student_name if e.student else "",
            "course_id": e.course_id,
            "course_name": e.course.name if e.course else "",
            "status": e.status,
            "enrolled_at": str(e.enrolled_at) if e.enrolled_at else None,
        }
        for e in enrollments
    ]


@router.post("/enrollments", status_code=201)
async def create_enrollment(
    data: EnrollmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == data.student_id,
            Enrollment.course_id == data.course_id,
            Enrollment.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="該學生已選此課程")
    enrollment = Enrollment(
        student_id=data.student_id,
        course_id=data.course_id,
        status="active",
    )
    db.add(enrollment)
    await db.commit()
    await db.refresh(enrollment)
    return {"success": True, "message": "選課成功", "id": enrollment.id}


@router.delete("/enrollments/{enrollment_id}")
async def delete_enrollment(
    enrollment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await db.delete(enrollment)
    await db.commit()
    return {"success": True, "message": "已取消選課"}


# ── Utility endpoints for dropdowns ──

@router.get("/course-filters")
async def get_course_filters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(Course.grade_level).distinct().where(Course.grade_level.isnot(None)).order_by(Course.grade_level)
    )
    grade_levels = [r[0] for r in result.all()]

    result = await db.execute(
        select(Course.subject).distinct().order_by(Course.subject)
    )
    subjects = [r[0] for r in result.all()]

    result = await db.execute(
        select(Teacher).order_by(Teacher.name)
    )
    teachers = [{"id": t.id, "name": t.name} for t in result.scalars().all()]

    return {
        "grade_levels": grade_levels,
        "subjects": subjects,
        "teachers": teachers,
    }
