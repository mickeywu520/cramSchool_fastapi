"""Student service - profile, progress, courses, exams, homework."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.communication import CommunicationBookEntry
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.exam_score import ExamScore
from app.models.homework import HomeworkRecord
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.utils.exceptions import NotFoundException


async def get_student_by_user_id(db: AsyncSession, user_id: int) -> Student:
    result = await db.execute(
        select(Student).where(Student.user_id == user_id).options(selectinload(Student.user))
    )
    student = result.scalar_one_or_none()
    if not student:
        raise NotFoundException("Student")
    return student


async def get_student_response(db: AsyncSession, user_id: int) -> dict:
    student = await get_student_by_user_id(db, user_id)
    subjects = json.loads(student.interested_subjects) if student.interested_subjects else []
    return {
        "id": student.id,
        "student_name": student.student_name,
        "birth_date": student.birth_date,
        "parent_name": student.parent_name,
        "phone": student.phone,
        "grade": student.grade,
        "school": student.school,
        "interested_subjects": subjects,
        "avatar_url": student.avatar_url,
        "student_number": student.student_number,
        "email": student.user.email if student.user else "",
    }


async def update_student(db: AsyncSession, user_id: int, data: dict) -> dict:
    student = await get_student_by_user_id(db, user_id)
    for field in ["student_name", "parent_name", "phone", "grade", "school"]:
        if data.get(field) is not None:
            setattr(student, field, data[field])
    if data.get("interested_subjects") is not None:
        student.interested_subjects = json.dumps(data["interested_subjects"], ensure_ascii=False)
    await db.flush()
    return await get_student_response(db, user_id)


async def get_progress(db: AsyncSession, user_id: int) -> dict:
    student = await get_student_by_user_id(db, user_id)
    # Get enrolled courses
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.student_id == student.id, Enrollment.status == "active")
        .options(selectinload(Enrollment.course))
    )
    enrollments = result.scalars().all()

    subjects_progress = []
    total_progress = 0
    for enrollment in enrollments:
        course = enrollment.course
        # Count communication entries for this course as completed lessons
        entry_result = await db.execute(
            select(CommunicationBookEntry).where(
                CommunicationBookEntry.student_id == student.id,
                CommunicationBookEntry.teacher_id == course.teacher_id,
            )
        )
        completed = len(entry_result.scalars().all())
        total_lessons = 20  # default estimate
        progress = min(round((completed / total_lessons) * 100, 1), 100) if total_lessons > 0 else 0
        subjects_progress.append({
            "subject": course.subject,
            "progress": progress,
            "total_lessons": total_lessons,
            "completed_lessons": completed,
        })
        total_progress += progress

    overall = round(total_progress / len(subjects_progress), 1) if subjects_progress else 0
    return {"overall_progress": overall, "subjects": subjects_progress}


async def get_my_courses(db: AsyncSession, user_id: int) -> list[dict]:
    student = await get_student_by_user_id(db, user_id)
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.student_id == student.id, Enrollment.status == "active")
        .options(selectinload(Enrollment.course).selectinload(Course.teacher))
    )
    enrollments = result.scalars().all()
    courses = []
    for enrollment in enrollments:
        course = enrollment.course
        courses.append({
            "id": course.id,
            "name": course.name,
            "subject": course.subject,
            "category": course.category,
            "schedule": course.schedule,
            "teacher_name": course.teacher.name if course.teacher else None,
        })
    return courses


async def get_my_exams(db: AsyncSession, user_id: int) -> list[dict]:
    student = await get_student_by_user_id(db, user_id)
    result = await db.execute(
        select(ExamScore)
        .where(ExamScore.student_id == student.id)
        .order_by(ExamScore.exam_date.desc())
    )
    exams = result.scalars().all()
    return [
        {
            "id": e.id,
            "exam_name": e.exam_name,
            "subject": e.subject,
            "score": float(e.score),
            "full_score": e.full_score,
            "exam_date": e.exam_date,
        }
        for e in exams
    ]


async def get_my_homework(db: AsyncSession, user_id: int) -> list[dict]:
    student = await get_student_by_user_id(db, user_id)
    result = await db.execute(
        select(HomeworkRecord)
        .join(CommunicationBookEntry)
        .where(CommunicationBookEntry.student_id == student.id)
        .order_by(HomeworkRecord.due_date.desc())
        .limit(20)
    )
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "subject": r.subject,
            "content": r.content,
            "due_date": r.due_date,
            "is_completed": r.is_completed,
        }
        for r in records
    ]