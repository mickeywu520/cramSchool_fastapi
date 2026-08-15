"""Student service - profile, progress, courses, exams, homework."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.communication import CommunicationBookEntry
from app.models.communication_session import CommunicationCourseSession
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.exam_score import ExamScore
from app.models.homework import HomeworkRecord
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.utils.exceptions import NotFoundException


async def get_student_by_user_id(
    db: AsyncSession, user_id: int, student_id: int | None = None
) -> Student:
    if student_id is not None:
        result = await db.execute(
            select(Student).where(Student.id == student_id).options(selectinload(Student.user))
        )
        student = result.scalar_one_or_none()
        if not student:
            raise NotFoundException("Student")
        # 僅限本人帳號或其家長帳號可存取
        if student.user_id != user_id and student.parent_user_id != user_id:
            raise NotFoundException("Student")
        return student
    result = await db.execute(
        select(Student).where(Student.user_id == user_id).options(selectinload(Student.user))
    )
    student = result.scalar_one_or_none()
    if not student:
        # 家長帳號：回傳第一位小孩資料
        result = await db.execute(
            select(Student)
            .where(Student.parent_user_id == user_id)
            .order_by(Student.id.asc())
            .limit(1)
            .options(selectinload(Student.user))
        )
        student = result.scalar_one_or_none()
    if not student:
        raise NotFoundException("Student")
    return student


async def get_students_for_user(db: AsyncSession, user_id: int) -> list[Student]:
    """回傳目前使用者（本人或家長）可存取的全部學生。"""
    result = await db.execute(
        select(Student)
        .where(
            (Student.user_id == user_id) | (Student.parent_user_id == user_id)
        )
        .order_by(Student.id.asc())
        .options(selectinload(Student.user))
    )
    return list(result.scalars().all())


async def get_student_response(
    db: AsyncSession, user_id: int, student_id: int | None = None
) -> dict:
    student = await get_student_by_user_id(db, user_id, student_id)
    subjects = json.loads(student.interested_subjects) if student.interested_subjects else []
    return {
        "id": student.id,
        "student_name": student.student_name,
        "gender": student.gender,
        "birth_date": student.birth_date,
        "school": student.school,
        "grade": student.grade,
        "class_name": student.class_name,
        "parent_name": student.parent_name,
        "parent_title": student.parent_title,
        "phone": student.phone,
        "parent2_name": student.parent2_name,
        "parent2_title": student.parent2_title,
        "parent2_phone": student.parent2_phone,
        "home_phone": student.home_phone,
        "id_number": student.id_number,
        "interested_subjects": subjects,
        "avatar_url": student.avatar_url,
        "student_number": student.student_number,
        "email": (student.user.email or student.id_number or "") if student.user else (student.id_number or ""),
    }


async def update_student(
    db: AsyncSession, user_id: int, data: dict, student_id: int | None = None
) -> dict:
    student = await get_student_by_user_id(db, user_id, student_id)
    for field in ["student_name", "gender", "birth_date", "school", "grade", "class_name", "parent_name", "parent_title", "phone", "parent2_name", "parent2_title", "parent2_phone", "home_phone", "id_number"]:
        if data.get(field) is not None:
            setattr(student, field, data[field])
    if data.get("interested_subjects") is not None:
        student.interested_subjects = json.dumps(data["interested_subjects"], ensure_ascii=False)
    await db.flush()
    return await get_student_response(db, user_id, student.id)


async def get_progress(db: AsyncSession, user_id: int, student_id: int | None = None) -> dict:
    student = await get_student_by_user_id(db, user_id, student_id)
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


async def get_my_courses(db: AsyncSession, user_id: int, student_id: int | None = None) -> list[dict]:
    student = await get_student_by_user_id(db, user_id, student_id)
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.student_id == student.id, Enrollment.status == "active")
        .options(selectinload(Enrollment.course).selectinload(Course.teacher), selectinload(Enrollment.course).selectinload(Course.branch))
    )
    enrollments = result.scalars().all()
    courses = []
    for enrollment in enrollments:
        course = enrollment.course
        courses.append({
            "id": course.id,
            "name": course.name,              # NOTE: key is "name", NOT "course_name"
            "subject": course.subject,
            "category": course.category,       # 學部
            "schedule": course.schedule,
            "teacher_name": course.teacher.name if course.teacher else None,
            "grade_level": course.grade_level,
            "location": course.location,
            "branch_name": course.branch.name if course.branch else None,
            "start_date": course.start_date,
            "end_date": course.end_date,
            "days_of_week": course.days_of_week,
            "start_time": course.start_time,
            "end_time": course.end_time,
        })
    return courses


async def get_my_exams(db: AsyncSession, user_id: int, student_id: int | None = None) -> list[dict]:
    student = await get_student_by_user_id(db, user_id, student_id)
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


async def get_my_homework(db: AsyncSession, user_id: int, student_id: int | None = None) -> list[dict]:
    student = await get_student_by_user_id(db, user_id, student_id)
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


async def get_my_score_history(db: AsyncSession, user_id: int, student_id: int | None = None) -> list[dict]:
    """各課程聯絡簿成績歷史，供折線圖使用（來源：聯絡簿 exam_score + custom_scores）。"""
    student = await get_student_by_user_id(db, user_id, student_id)
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.student_id == student.id, Enrollment.status == "active")
        .options(selectinload(Enrollment.course).selectinload(Course.teacher))
    )
    enrollments = result.scalars().all()

    history = []
    for enrollment in enrollments:
        course = enrollment.course
        session_result = await db.execute(
            select(CommunicationCourseSession)
            .where(CommunicationCourseSession.course_id == course.id)
            .options(selectinload(CommunicationCourseSession.student_records))
            .order_by(CommunicationCourseSession.entry_date.asc())
        )
        sessions = session_result.scalars().all()

        points = []
        all_scores: list[int] = []
        for session in sessions:
            record = next(
                (r for r in session.student_records if r.student_id == student.id),
                None,
            )
            if not record:
                continue
            class_scores = [
                r.exam_score
                for r in session.student_records
                if r.exam_score is not None
            ]
            class_average = (
                round(sum(class_scores) / len(class_scores), 1) if class_scores else None
            )
            scores: dict[str, int] = {}
            if record.exam_score is not None:
                scores["分數"] = record.exam_score
            custom = {}
            if record.custom_scores:
                try:
                    custom = json.loads(record.custom_scores)
                except (json.JSONDecodeError, TypeError):
                    custom = {}
            for name, val in custom.items():
                if val is not None:
                    try:
                        scores[str(name)] = int(val)
                    except (ValueError, TypeError):
                        continue
            if not scores:
                continue
            avg = round(sum(scores.values()) / len(scores), 1)
            all_scores.extend(scores.values())
            points.append({
                "date": str(session.entry_date),
                "scores": scores,
                "average": avg,
                "class_average": class_average,
            })

        if points:
            history.append({
                "course_id": course.id,
                "course_name": course.name,
                "subject": course.subject,
                "points": points,
                "average": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
            })
    return history