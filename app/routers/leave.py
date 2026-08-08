"""Leave & makeup router."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_student, require_teacher_or_admin
from app.models.student import Student
from app.models.user import User
from app.schemas.leave import (
    LeaveApplicationListResponse,
    LeaveApplicationRequest,
    LeaveApplicationResponse,
    LeaveRulesResponse,
    MakeupClassCreateRequest,
    MakeupClassResponse,
    ReviewRequest,
)
from app.services import leave_service

router = APIRouter(prefix="/leave", tags=["Leave & Makeup"])


async def _resolve_student(
    db: AsyncSession, user_id: int, student_id: int | None = None
) -> Student:
    """解析目前使用者的學生（本人或家長），支援指定 student_id。"""
    if student_id is not None:
        result = await db.execute(select(Student).where(Student.id == student_id))
        student = result.scalar_one_or_none()
        if student and (student.user_id == user_id or student.parent_user_id == user_id):
            return student
        from fastapi import HTTPException
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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Student not found")
    return student


# Student endpoints
@router.post("/applications", response_model=LeaveApplicationResponse, status_code=201)
async def create_application(
    data: LeaveApplicationRequest,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    leave = await leave_service.create_leave_application(db, student.id, data.model_dump())
    await db.commit()
    return {
        "id": leave.id, "leave_date": leave.leave_date, "leave_type": leave.leave_type,
        "reason": leave.reason, "status": leave.status, "course_name": None,
        "created_at": leave.created_at,
    }


@router.get("/applications", response_model=LeaveApplicationListResponse)
async def get_my_applications(
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    applications = await leave_service.get_my_applications(db, student.id)
    items = []
    for a in applications:
        items.append({
            "id": a.id, "leave_date": a.leave_date, "leave_type": a.leave_type,
            "reason": a.reason, "status": a.status,
            "course_name": a.course.name if a.course else None,
            "created_at": a.created_at,
        })
    return {"total": len(items), "applications": items}


@router.put("/applications/{application_id}", response_model=LeaveApplicationResponse)
async def update_application(
    application_id: int,
    data: LeaveApplicationRequest,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    leave = await leave_service.update_application(db, application_id, student.id, data.model_dump())
    await db.commit()
    return {
        "id": leave.id, "leave_date": leave.leave_date, "leave_type": leave.leave_type,
        "reason": leave.reason, "status": leave.status,
        "course_name": leave.course.name if leave.course else None,
        "created_at": leave.created_at,
    }


@router.delete("/applications/{application_id}")
async def cancel_application(
    application_id: int,
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    await leave_service.cancel_application(db, application_id, student.id)
    await db.commit()
    return {"success": True, "message": "已取消請假申請"}


@router.get("/rules", response_model=LeaveRulesResponse)
async def get_rules():
    return {"rules": leave_service.LEAVE_RULES}


# Teacher/Admin endpoints
@router.get("/pending", response_model=LeaveApplicationListResponse)
async def get_pending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    applications = await leave_service.get_pending_applications(db)
    items = []
    for a in applications:
        items.append({
            "id": a.id, "leave_date": a.leave_date, "leave_type": a.leave_type,
            "reason": a.reason, "status": a.status,
            "course_name": a.course.name if a.course else None,
            "created_at": a.created_at,
        })
    return {"total": len(items), "applications": items}


@router.post("/applications/{application_id}/review")
async def review_application(
    application_id: int,
    data: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    await leave_service.review_application(db, application_id, current_user.id, data.status)
    await db.commit()
    return {"success": True, "message": f"已{data.status}"}


# Makeup endpoints
@router.get("/makeup", response_model=list[MakeupClassResponse])
async def get_my_makeup(
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    classes = await leave_service.get_my_makeup_classes(db, student.id)
    return [
        {
            "id": m.id, "leave_id": m.leave_id, "course_id": m.course_id,
            "course_name": m.course.name if m.course else None,
            "makeup_date": m.makeup_date,
            "start_time": m.start_time.strftime("%H:%M") if m.start_time else "",
            "end_time": m.end_time.strftime("%H:%M") if m.end_time else "",
            "classroom": m.classroom, "status": m.status, "notes": m.notes,
        }
        for m in classes
    ]


@router.get("/makeup/upcoming", response_model=list[MakeupClassResponse])
async def get_upcoming_makeup(
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    classes = await leave_service.get_upcoming_makeup(db, student.id)
    return [
        {
            "id": m.id, "leave_id": m.leave_id, "course_id": m.course_id,
            "course_name": m.course.name if m.course else None,
            "makeup_date": m.makeup_date,
            "start_time": m.start_time.strftime("%H:%M") if m.start_time else "",
            "end_time": m.end_time.strftime("%H:%M") if m.end_time else "",
            "classroom": m.classroom, "status": m.status, "notes": m.notes,
        }
        for m in classes
    ]


@router.post("/makeup", response_model=MakeupClassResponse, status_code=201)
async def create_makeup(
    data: MakeupClassCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    m = await leave_service.create_makeup_class(db, data.model_dump())
    await db.commit()
    return {
        "id": m.id, "leave_id": m.leave_id, "course_id": m.course_id,
        "course_name": None, "makeup_date": m.makeup_date,
        "start_time": m.start_time.strftime("%H:%M") if m.start_time else "",
        "end_time": m.end_time.strftime("%H:%M") if m.end_time else "",
        "classroom": m.classroom, "status": m.status, "notes": m.notes,
    }