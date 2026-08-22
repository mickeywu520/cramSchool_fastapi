"""Admin router - administrative endpoints."""

import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth_middleware import require_admin, require_teacher_or_admin
from app.utils.security import hash_password
from app.models.branch import Branch
from app.models.communication_session import (
    CommunicationCourseSession,
    CommunicationSessionStudent,
)
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.user import User
from app.schemas.admin_user import (
    AdminUserCreateRequest,
    AdminUserResetPasswordRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
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
    BatchCopyEnrollmentsRequest,
    BatchEnrollRequest,
    CourseCreateRequest,
    CourseResponse,
    CourseUpdateRequest,
    EnrollmentCreateRequest,
    EnrollmentResponse,
)
from app.schemas.student import FollowupUpdateRequest, StudentRegistrationResponse, StudentRegistrationUpdateRequest
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
        "tutoring_day_of_week": c.tutoring_day_of_week,
        "tutoring_days_of_week": c.tutoring_days_of_week,
        "tutoring_start_time": c.tutoring_start_time,
        "tutoring_end_time": c.tutoring_end_time,
        "tutoring_location": c.tutoring_location,
        "branch_id": c.branch_id, "branch_name": c.branch.name if c.branch else None,
        "school_year": c.school_year, "semester": c.semester,
        "price": c.price, "max_students": c.max_students,
        "is_early_bird": c.is_early_bird, "early_bird_discount": c.early_bird_discount,
        "is_active": c.is_active, "is_teaching": c.is_teaching, "display_order": c.display_order,
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
    query = query.order_by(Student.created_at.asc())
    result = await db.execute(query)
    students = result.scalars().all()
    return [
        {
            "id": s.id,
            "student_name": s.student_name,
            "grade": s.grade,
            "school": s.school,
            "followup_status": s.followup_status,
            "remark": s.remark,
        }
        for s in students
    ]


# ── Student Registrations ──

@router.get("/student-registrations", response_model=list[StudentRegistrationResponse])
async def list_student_registrations(
    search: str | None = Query(None, description="姓名關鍵字"),
    followup_status: str | None = Query(None, description="篩選跟進狀態"),
    grade: str | None = Query(None, description="篩選年級"),
    school: str | None = Query(None, description="篩選學校"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = (
        select(Student)
        .options(selectinload(Student.user))
        .order_by(Student.created_at.desc())
    )
    if search:
        query = query.where(Student.student_name.contains(search))
    if followup_status:
        query = query.where(Student.followup_status == followup_status)
    if grade:
        query = query.where(Student.grade == grade)
    if school:
        query = query.where(Student.school.contains(school))
    result = await db.execute(query)
    students = result.scalars().all()
    return [
        _format_registration(s)
        for s in students
    ]


@router.put("/student-registrations/{student_id}/followup")
async def update_followup_status(
    student_id: int,
    data: FollowupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="找不到此學生")
    student.followup_status = data.followup_status
    if data.followup_status == "在籍" and not student.user_id:
        await _auto_create_student_user(db, student)
    if data.followup_status == "離籍":
        enrollments_result = await db.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.status == "active",
            )
        )
        for enroll in enrollments_result.scalars().all():
            enroll.status = "dropped"
    await db.commit()
    return {"success": True, "followup_status": data.followup_status}


async def _auto_create_student_user(db: AsyncSession, student: Student) -> None:
    """在籍時自動建立學生帳號（帳號＝密碼＝身分證字號）。"""
    id_number = (student.id_number or "").strip()
    if not id_number:
        return
    if student.user_id:
        return
    # 先查同身分證的其他學生是否已有專屬帳號，避免重複建立
    same_id = (
        await db.execute(
            select(Student).where(Student.id_number == id_number, Student.user_id.isnot(None)).limit(1)
        )
    ).scalar_one_or_none()
    if same_id and same_id.user_id:
        student.user_id = same_id.user_id
        return
    user = User(
        email=None,
        password_hash=hash_password(id_number),
        role="student",
        auth_provider="id_number",
    )
    db.add(user)
    await db.flush()
    student.user_id = user.id


@router.put("/student-registrations/{student_id}")
async def update_student_registration(
    student_id: int,
    data: StudentRegistrationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="找不到此學生")
    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(student, key, value)
    await db.commit()
    return {"success": True, "message": "學生資料已更新"}


def _format_registration(s: Student) -> dict:
    return {
        "id": s.id,
        "student_name": s.student_name,
        "gender": s.gender,
        "birth_date": s.birth_date,
        "school": s.school,
        "grade": s.grade,
        "class_name": s.class_name,
        "parent_name": s.parent_name,
        "parent_title": s.parent_title,
        "phone": s.phone,
        "parent2_name": s.parent2_name,
        "parent2_title": s.parent2_title,
        "parent2_phone": s.parent2_phone,
        "home_phone": s.home_phone,
        "id_number": s.id_number,
        "card_number": s.card_number,
        "followup_status": s.followup_status,
        "remark": s.remark,
        "email": (s.user.email or s.id_number or "") if s.user else (s.id_number or ""),
        "created_at": s.created_at,
    }


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
    query = query.order_by(Course.created_at.desc())
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
    if course.is_teaching is False:
        course.is_active = False
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
    # 先刪除相依資料，避免外鍵約束錯誤（enrollments.course_id 為 NOT NULL）
    await db.execute(delete(Enrollment).where(Enrollment.course_id == course_id))
    session_result = await db.execute(
        select(CommunicationCourseSession.id).where(CommunicationCourseSession.course_id == course_id)
    )
    session_ids = session_result.scalars().all()
    if session_ids:
        await db.execute(
            delete(CommunicationSessionStudent).where(CommunicationSessionStudent.session_id.in_(session_ids))
        )
        await db.execute(
            delete(CommunicationCourseSession).where(CommunicationCourseSession.course_id == course_id)
        )
    await db.execute(delete(MakeupClass).where(MakeupClass.course_id == course_id))
    await db.execute(delete(LeaveApplication).where(LeaveApplication.course_id == course_id))
    await db.delete(course)
    await db.commit()
    return {"success": True, "message": "課程已刪除"}


@router.post("/courses/batch-toggle")
async def batch_toggle_courses(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    course_ids = data.get("course_ids", [])
    is_teaching = data.get("is_teaching", True)
    if not course_ids:
        raise HTTPException(status_code=400, detail="請選擇至少一門課程")
    result = await db.execute(
        select(Course).where(Course.id.in_(course_ids))
    )
    courses = result.scalars().all()
    for c in courses:
        c.is_teaching = is_teaching
        if not is_teaching:
            c.is_active = False
    await db.flush()
    return {"success": True, "message": f"已{'開課' if is_teaching else '停課'} {len(courses)} 門課程"}


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
            "school": e.student.school if e.student else "",
            "remark": e.student.remark if e.student else None,
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


@router.post("/enrollments/batch", status_code=201)
async def batch_enroll_students(
    data: BatchEnrollRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    course_result = await db.execute(select(Course).where(Course.id == data.course_id))
    if not course_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="課程不存在")

    existing_result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == data.course_id,
            Enrollment.status == "active",
        )
    )
    existing_ids = {e.student_id for e in existing_result.scalars().all()}

    added = 0
    for student_id in data.student_ids:
        if student_id in existing_ids:
            continue
        enrollment = Enrollment(
            student_id=student_id,
            course_id=data.course_id,
            status="active",
        )
        db.add(enrollment)
        added += 1

    await db.commit()
    return {"success": True, "message": f"已加入 {added} 位學生", "added": added}


@router.post("/enrollments/batch-copy")
async def batch_copy_enrollments(
    data: BatchCopyEnrollmentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    source_result = await db.execute(
        select(Enrollment)
        .where(
            Enrollment.course_id == data.source_course_id,
            Enrollment.status == "active",
        )
        .options(selectinload(Enrollment.student))
    )
    source_enrollments = source_result.scalars().all()
    source_course_result = await db.execute(
        select(Course).where(Course.id == data.target_course_id)
    )
    target_course = source_course_result.scalar_one_or_none()
    if not target_course:
        raise HTTPException(status_code=404, detail="目標課程不存在")

    existing_result = await db.execute(
        select(Enrollment).where(
            Enrollment.course_id == data.target_course_id,
            Enrollment.status == "active",
        )
    )
    existing_ids = {e.student_id for e in existing_result.scalars().all()}

    added = 0
    for se in source_enrollments:
        if se.student_id not in existing_ids:
            enrollment = Enrollment(
                student_id=se.student_id,
                course_id=data.target_course_id,
                status="active",
            )
            db.add(enrollment)
            added += 1

    await db.commit()
    return {"success": True, "message": f"已新增 {added} 位學生", "added": added}


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
            vocab=sd.vocab,
            exam_scope=sd.exam_scope,
            announcements=sd.announcements,
            handout_status=sd.handout_status,
            homework_material=sd.homework_material,
            homework_workbook=sd.homework_workbook,
            exam_score=sd.exam_score,
            custom_scores=custom_json,
            tutoring_attendance=_tutoring_auto(sd.exam_score, data.tutoring_threshold),
            reschedule_date=sd.reschedule_date,
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
                vocab=sd.vocab,
                exam_scope=sd.exam_scope,
                announcements=sd.announcements,
            handout_status=sd.handout_status,
            homework_material=sd.homework_material,
            homework_workbook=sd.homework_workbook,
            exam_score=sd.exam_score,
            custom_scores=custom_json,
            tutoring_attendance=_tutoring_auto(sd.exam_score, session.tutoring_threshold),
            reschedule_date=sd.reschedule_date,
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
            vocab=sr.vocab,
            exam_scope=sr.exam_scope,
            announcements=sr.announcements,
            handout_status=sr.handout_status,
            homework_material=sr.homework_material,
            homework_workbook=sr.homework_workbook,
            exam_score=sr.exam_score,
            custom_scores=custom_scores,
            tutoring_attendance=sr.tutoring_attendance,
            reschedule_date=sr.reschedule_date,
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


# ── Admin User Management ──

ADMIN_ROLES = {"admin", "maintainer", "user"}


@router.get("/users", response_model=list[AdminUserResponse])
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all backend management accounts (admin / maintainer / user)."""
    result = await db.execute(
        select(User).where(User.role.in_(ADMIN_ROLES)).order_by(User.created_at.desc())
    )
    return result.scalars().all()


@router.post("/users", response_model=AdminUserResponse, status_code=201)
async def create_admin_user(
    data: AdminUserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new backend management account."""
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="此 Email 已被使用")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        auth_provider="email",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    data: AdminUserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an admin user's role or active status."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能修改自己的帳號")

    result = await db.execute(
        select(User).where(User.id == user_id, User.role.in_(ADMIN_ROLES))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="找不到此帳號")

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete an admin user account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能刪除自己的帳號")

    result = await db.execute(
        select(User).where(User.id == user_id, User.role.in_(ADMIN_ROLES))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="找不到此帳號")

    await db.delete(user)
    await db.commit()
    return {"success": True, "message": "帳號已刪除"}


@router.put("/users/{user_id}/reset-password")
async def reset_admin_user_password(
    user_id: int,
    data: AdminUserResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reset password for an admin user."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.role.in_(ADMIN_ROLES))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="找不到此帳號")

    user.password_hash = hash_password(data.password)
    await db.commit()
    return {"success": True, "message": "密碼已重設"}
