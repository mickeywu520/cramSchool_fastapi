"""Leave & makeup router."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_student, require_teacher_or_admin
from app.models.student import Student
from app.models.user import User
from app.utils.exceptions import ConflictException
from app.schemas.leave import (
    LeaveApplicationListResponse,
    LeaveApplicationRequest,
    LeaveApplicationResponse,
    LeaveRulesResponse,
    MakeupClassCreateRequest,
    MakeupClassResponse,
    MakeupOptionResponse,
    ReviewRequest,
)
from app.services import leave_service
from app.services import makeup_room_service

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


def _leave_dict(leave) -> dict:
    """統一的請假申請序列化（含課程名稱、學生姓名與家長指定的補課時段）。"""
    return {
        "id": leave.id,
        "student_id": leave.student_id,
        "course_id": leave.course_id,
        "leave_date": leave.leave_date,
        "leave_type": leave.leave_type,
        "reason": leave.reason,
        "status": leave.status,
        "course_name": leave.course.name if leave.course else None,
        "student_name": leave.student.student_name if leave.student else None,
        "requested_room_id": leave.requested_room_id,
        "requested_room_code": (
            leave.requested_room.display_name if leave.requested_room else None
        ),
        "requested_makeup_date": leave.requested_makeup_date,
        "requested_makeup_start": (
            leave.requested_makeup_start.strftime("%H:%M") if leave.requested_makeup_start else None
        ),
        "requested_makeup_end": (
            leave.requested_makeup_end.strftime("%H:%M") if leave.requested_makeup_end else None
        ),
        "review_note": leave.review_note,
        "created_at": leave.created_at,
    }


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
    # 重新載入以帶出 course / student 關聯（async session 不可 lazy load）
    leave = await leave_service.get_application_by_id(db, leave.id, student.id)
    return _leave_dict(leave)


@router.get("/applications", response_model=LeaveApplicationListResponse)
async def get_my_applications(
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await _resolve_student(db, current_user.id, student_id)
    applications = await leave_service.get_my_applications(db, student.id)
    items = [_leave_dict(a) for a in applications]
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
    return _leave_dict(leave)


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
        item = _leave_dict(a)
        # 核准前先算一次名額：待審核期間別人可能已把該時段排滿，
        # 讓老師在按「核准」之前就看得到，而不是按下去才吃 409。
        if a.requested_room and a.requested_makeup_date and a.requested_makeup_start:
            booked = await makeup_room_service.count_booked(
                db, a.requested_room.id, a.requested_makeup_date, a.requested_makeup_start
            )
            left = max(a.requested_room.capacity - booked, 0)
            item["requested_seats_left"] = left
            item["requested_slot_full"] = left <= 0
        items.append(item)
    return {"total": len(items), "applications": items}


@router.post("/applications/{application_id}/review")
async def review_application(
    application_id: int,
    data: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    # 核准時會同步建立家長指定的補課紀錄，IntegrityError 一律轉 409
    try:
        leave = await leave_service.review_application(
            db, application_id, current_user.id, data.status, data.reason
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictException("此請假申請已安排過補課")
    message = "已核准請假並完成補課安排" if data.status == "approved" else "已駁回請假申請"
    return {"success": True, "message": message, "status": leave.status}


# Makeup endpoints
@router.get("/makeup-options", response_model=list[MakeupOptionResponse])
async def get_makeup_options(
    course_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    """家長可選的補課場次（學生分校的補課教室固定時段，含剩餘座位）。"""
    student = await _resolve_student(db, current_user.id, student_id)
    return await leave_service.list_makeup_options(
        db, student, course_id, date_from, date_to
    )


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
            "classroom": m.classroom, "room_id": m.room_id, "status": m.status,
            "requested_by": m.requested_by or "teacher", "notes": m.notes,
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
            "classroom": m.classroom, "room_id": m.room_id, "status": m.status,
            "requested_by": m.requested_by or "teacher", "notes": m.notes,
        }
        for m in classes
    ]


@router.post("/makeup", response_model=MakeupClassResponse, status_code=201)
async def create_makeup(
    data: MakeupClassCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    # flush 在 service 內就會觸發 unique 約束，因此 try 必須涵蓋整個呼叫
    try:
        m = await leave_service.create_makeup_class(db, data.model_dump())
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictException("此請假申請已安排過補課")
    m = await leave_service.get_makeup_by_id(db, m.id)
    return {
        "id": m.id, "leave_id": m.leave_id, "course_id": m.course_id,
        "course_name": m.course.name if m.course else None, "makeup_date": m.makeup_date,
        "start_time": m.start_time.strftime("%H:%M") if m.start_time else "",
        "end_time": m.end_time.strftime("%H:%M") if m.end_time else "",
        "classroom": m.classroom, "room_id": m.room_id, "status": m.status,
        "requested_by": m.requested_by or "teacher", "notes": m.notes,
    }