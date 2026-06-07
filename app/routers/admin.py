"""Admin router - administrative endpoints."""

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.branch import Branch
from app.models.communication_session import (
    CommunicationCourseSession,
    CommunicationSessionStudent,
)
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.schemas.branch import BranchCreateRequest, BranchResponse, BranchUpdateRequest
from app.schemas.communication import CommunicationListResponse
from app.schemas.communication_session import (
    ExamColumnDef,
    SessionCreateRequest,
    SessionListItem,
    SessionResponse,
    SessionUpdateRequest,
    StudentSessionResponse,
)
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
        "days_of_week": c.days_of_week,
        "start_date": str(c.start_date) if c.start_date else None,
        "end_date": str(c.end_date) if c.end_date else None,
        "start_time": c.start_time, "end_time": c.end_time, "location": c.location,
        "branch_id": c.branch_id, "branch_name": c.branch.name if c.branch else None,
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
    branch_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = select(Course).options(selectinload(Course.teacher), selectinload(Course.branch))
    if branch_id:
        query = query.where(Course.branch_id == branch_id)
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
    # Reload with teacher and branch
    result = await db.execute(
        select(Course).where(Course.id == course.id).options(selectinload(Course.teacher), selectinload(Course.branch))
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
        select(Course).where(Course.id == course_id).options(selectinload(Course.teacher), selectinload(Course.branch))
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

    result = await db.execute(
        select(Branch).where(Branch.is_active == True).order_by(Branch.display_order)
    )
    branches = [{"id": b.id, "name": b.name} for b in result.scalars().all()]

    return {
        "grade_levels": grade_levels,
        "subjects": subjects,
        "teachers": teachers,
        "branches": branches,
    }


# ── Branch CRUD ──

@router.get("/branches", response_model=list[BranchResponse])
async def list_branches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Branch).order_by(Branch.display_order))
    return result.scalars().all()


@router.post("/branches", response_model=BranchResponse, status_code=201)
async def create_branch(
    data: BranchCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    branch = Branch(**data.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.put("/branches/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: int,
    data: BranchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Branch).where(Branch.id == branch_id))
    branch = result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    for key, val in data.model_dump(exclude_none=True).items():
        setattr(branch, key, val)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.delete("/branches/{branch_id}")
async def delete_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Branch).where(Branch.id == branch_id))
    branch = result.scalar_one_or_none()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    await db.delete(branch)
    await db.commit()
    return {"success": True, "message": "分校已刪除"}


# ── Communication Course Sessions ──

def _parse_exam_columns(raw: str | None) -> list[ExamColumnDef]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return [ExamColumnDef(name=i["name"], display_order=i.get("display_order", 0)) for i in items]
    except (json.JSONDecodeError, KeyError):
        return []


def _tutoring_auto(exam_score: int | None, threshold: int | None) -> bool:
    if exam_score is not None and threshold is not None:
        return exam_score < threshold
    return False


@router.get("/communication-sessions", response_model=list[SessionListItem])
async def list_sessions(
    course_id: int = Query(..., description="課程 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(CommunicationCourseSession)
        .where(CommunicationCourseSession.course_id == course_id)
        .order_by(CommunicationCourseSession.entry_date.desc())
    )
    sessions = result.scalars().all()
    items = []
    for s in sessions:
        cnt_result = await db.execute(
            select(CommunicationSessionStudent)
            .where(CommunicationSessionStudent.session_id == s.id)
        )
        student_count = len(cnt_result.scalars().all())
        items.append(SessionListItem(
            id=s.id,
            course_id=s.course_id,
            entry_date=s.entry_date,
            tutoring_threshold=s.tutoring_threshold,
            student_count=student_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ))
    return items


@router.post("/communication-sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    data: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    existing = await db.execute(
        select(CommunicationCourseSession)
        .where(
            CommunicationCourseSession.course_id == data.course_id,
            CommunicationCourseSession.entry_date == data.entry_date,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="此課程在此日期已有聯絡簿記錄")

    exam_cols_json = json.dumps(
        [{"name": c.name, "display_order": c.display_order} for c in data.exam_columns],
        ensure_ascii=False,
    ) if data.exam_columns else "[]"

    session = CommunicationCourseSession(
        course_id=data.course_id,
        entry_date=data.entry_date,
        tutoring_threshold=data.tutoring_threshold,
        class_progress=data.class_progress,
        class_homework=data.class_homework,
        class_exam_scope=data.class_exam_scope,
        class_announcements=data.class_announcements,
        exam_columns=exam_cols_json,
    )
    db.add(session)
    await db.flush()

    for sd in data.students:
        custom_json = json.dumps(sd.custom_scores, ensure_ascii=False) if sd.custom_scores else "{}"
        student_rec = CommunicationSessionStudent(
            session_id=session.id,
            student_id=sd.student_id,
            arrival_time=sd.arrival_time,
            departure_time=sd.departure_time,
            progress=sd.progress,
            homework=sd.homework,
            exam_scope=sd.exam_scope,
            announcements=sd.announcements,
            handout_status=sd.handout_status,
            exam_score=sd.exam_score,
            custom_scores=custom_json,
            tutoring_attendance=_tutoring_auto(sd.exam_score, data.tutoring_threshold),
            notes=sd.notes,
        )
        db.add(student_rec)

    await db.commit()
    await db.refresh(session)
    return await _build_session_response(db, session.id)


@router.get("/communication-sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    return await _build_session_response(db, session_id)


@router.put("/communication-sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int,
    data: SessionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(CommunicationCourseSession)
        .where(CommunicationCourseSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="找不到此聯絡簿記錄")

    # Update session fields
    update_fields = [
        "entry_date", "tutoring_threshold", "class_progress",
        "class_homework", "class_exam_scope", "class_announcements",
    ]
    for field in update_fields:
        val = getattr(data, field, None)
        if val is not None:
            setattr(session, field, val)
    if data.exam_columns is not None:
        session.exam_columns = json.dumps(
            [{"name": c.name, "display_order": c.display_order} for c in data.exam_columns],
            ensure_ascii=False,
        )

    # Replace student records
    if data.students is not None:
        # Delete old records
        old = await db.execute(
            select(CommunicationSessionStudent)
            .where(CommunicationSessionStudent.session_id == session_id)
        )
        for rec in old.scalars().all():
            await db.delete(rec)
        await db.flush()

        # Add new records
        for sd in data.students:
            custom_json = json.dumps(sd.custom_scores, ensure_ascii=False) if sd.custom_scores else "{}"
            student_rec = CommunicationSessionStudent(
                session_id=session.id,
                student_id=sd.student_id,
                arrival_time=sd.arrival_time,
                departure_time=sd.departure_time,
                progress=sd.progress,
                homework=sd.homework,
                exam_scope=sd.exam_scope,
                announcements=sd.announcements,
                handout_status=sd.handout_status,
                exam_score=sd.exam_score,
                custom_scores=custom_json,
                tutoring_attendance=_tutoring_auto(sd.exam_score, session.tutoring_threshold),
                notes=sd.notes,
            )
            db.add(student_rec)

    await db.commit()
    return await _build_session_response(db, session_id)


@router.delete("/communication-sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(
        select(CommunicationCourseSession)
        .where(CommunicationCourseSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="找不到此聯絡簿記錄")
    await db.delete(session)
    await db.commit()
    return {"success": True, "message": "聯絡簿記錄已刪除"}


async def _build_session_response(db: AsyncSession, session_id: int) -> SessionResponse:
    result = await db.execute(
        select(CommunicationCourseSession)
        .where(CommunicationCourseSession.id == session_id)
        .options(
            selectinload(CommunicationCourseSession.student_records)
            .selectinload(CommunicationSessionStudent.student)
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="找不到此聯絡簿記錄")

    exam_cols = _parse_exam_columns(session.exam_columns)
    students = []
    for sr in session.student_records:
        custom_scores = {}
        if sr.custom_scores:
            try:
                custom_scores = json.loads(sr.custom_scores)
            except json.JSONDecodeError:
                custom_scores = {}
        students.append(StudentSessionResponse(
            id=sr.id,
            student_id=sr.student_id,
            student_name=sr.student.student_name if sr.student else "",
            arrival_time=sr.arrival_time,
            departure_time=sr.departure_time,
            progress=sr.progress,
            homework=sr.homework,
            exam_scope=sr.exam_scope,
            announcements=sr.announcements,
            handout_status=sr.handout_status,
            exam_score=sr.exam_score,
            custom_scores=custom_scores,
            tutoring_attendance=sr.tutoring_attendance,
            notes=sr.notes,
            parent_feedback=sr.parent_feedback,
            parent_signed=sr.parent_signed,
            parent_signed_at=sr.parent_signed_at,
        ))

    return SessionResponse(
        id=session.id,
        course_id=session.course_id,
        entry_date=session.entry_date,
        tutoring_threshold=session.tutoring_threshold,
        class_progress=session.class_progress,
        class_homework=session.class_homework,
        class_exam_scope=session.class_exam_scope,
        class_announcements=session.class_announcements,
        exam_columns=exam_cols,
        students=students,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
