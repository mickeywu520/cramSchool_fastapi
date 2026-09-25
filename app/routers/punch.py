"""Punch clock router - SOYAL 打卡機中介軟體寫入 + 前台查詢.

- POST /punch-events: 中介軟體用 X-Api-Key 驗證 (不用 JWT), Body {"events": [...]},
  receiver forwarder 送單筆或批次皆可. 未知卡與非在籍事件保留 raw 稽核,
  全部以 200 + per-item status 回應, 避免 receiver 誤判重送.
- GET /attendance/daily: 老師/管理員查詢每日首末筆.
- GET /attendance/class: 老師/管理員查詢逐課出席.
- GET /student/attendance: 學生查詢自己的每日出勤.
- GET /student/attendance/class: 學生查詢自己的逐課出席.
"""

import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth_middleware import require_student, require_teacher_or_admin
from app.models.attendance import AttendanceDaily
from app.models.student import Student
from app.models.user import User
from app.schemas.punch import (
    AttendanceDailyResponse,
    ClassAttendanceResponse,
    PunchIngestRequest,
    PunchIngestResponse,
)
from app.services import attendance_service
from app.services import student_service
from app.utils.exceptions import UnauthorizedException, ValidationException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Punch"])
punch_bearer = HTTPBearer(auto_error=False)


async def verify_punch_api_key(
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    authorization: HTTPAuthorizationCredentials | None = Depends(punch_bearer),
):
    if not settings.PUNCH_API_KEY:
        raise UnauthorizedException("Punch API key not configured")
    bearer_key = authorization.credentials if authorization else None
    if x_api_key != settings.PUNCH_API_KEY and bearer_key != settings.PUNCH_API_KEY:
        raise UnauthorizedException("Invalid punch API key")
    return True


@router.post("/punch-events", response_model=PunchIngestResponse)
async def ingest_punch_events(
    data: PunchIngestRequest,
    db: AsyncSession = Depends(get_db),
    _ok: bool = Depends(verify_punch_api_key),
):
    results = await attendance_service.ingest_events(db, data.events)
    await db.commit()
    stored = sum(1 for r in results if r.get("stored"))
    logger.info("punch ingest: received=%d stored=%d", len(results), stored)
    return {"received": len(results), "stored": stored, "results": results}


def _fmt_dt(dt) -> str | None:
    return dt.isoformat() if dt else None


def _today_taipei() -> date:
    return datetime.now(attendance_service.TAIPEI_TZ).date()


@router.get("/attendance/daily", response_model=list[AttendanceDailyResponse])
async def get_daily_attendance(
    punch_date: date = Query(..., description="查詢日期 YYYY-MM-DD"),
    student_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    query = (
        select(AttendanceDaily, Student)
        .join(Student, Student.id == AttendanceDaily.student_id)
        .where(AttendanceDaily.punch_date == punch_date)
        .order_by(Student.student_name.asc())
    )
    if student_id is not None:
        query = query.where(AttendanceDaily.student_id == student_id)
    result = await db.execute(query)
    return [
        {
            "student_id": d.student_id,
            "student_name": s.student_name,
            "card_number": s.card_number,
            "punch_date": str(d.punch_date),
            "first_punch": _fmt_dt(d.first_punch),
            "last_punch": _fmt_dt(d.last_punch),
            "punch_count": d.punch_count,
        }
        for d, s in result.all()
    ]


@router.get("/student/attendance", response_model=list[AttendanceDailyResponse])
async def get_my_attendance(
    date_from: date | None = Query(None, description="起始日 YYYY-MM-DD"),
    date_to: date | None = Query(None, description="結束日 YYYY-MM-DD"),
    student_id: int | None = Query(None, description="家長多小孩時指定"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await student_service.get_student_by_user_id(db, current_user.id, student_id)
    query = (
        select(AttendanceDaily)
        .where(AttendanceDaily.student_id == student.id)
        .order_by(AttendanceDaily.punch_date.desc())
    )
    if date_from is not None:
        query = query.where(AttendanceDaily.punch_date >= date_from)
    if date_to is not None:
        query = query.where(AttendanceDaily.punch_date <= date_to)
    result = await db.execute(query.limit(62))
    rows = result.scalars().all()
    return [
        {
            "student_id": d.student_id,
            "student_name": student.student_name,
            "card_number": student.card_number,
            "punch_date": str(d.punch_date),
            "first_punch": _fmt_dt(d.first_punch),
            "last_punch": _fmt_dt(d.last_punch),
            "punch_count": d.punch_count,
        }
        for d in rows
    ]


@router.get("/attendance/class", response_model=list[ClassAttendanceResponse])
async def get_class_attendance(
    date_from: date | None = Query(None, description="起始日 YYYY-MM-DD"),
    date_to: date | None = Query(None, description="結束日 YYYY-MM-DD"),
    student_id: int | None = Query(None),
    course_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    start = date_from or _today_taipei()
    end = date_to or start
    if end < start:
        raise ValidationException("結束日期不可小於起始日期")
    return await attendance_service.get_class_attendance(
        db,
        start,
        end,
        student_id=student_id,
        course_id=course_id,
    )


@router.get("/student/attendance/class", response_model=list[ClassAttendanceResponse])
async def get_my_class_attendance(
    date_from: date | None = Query(None, description="起始日 YYYY-MM-DD"),
    date_to: date | None = Query(None, description="結束日 YYYY-MM-DD"),
    student_id: int | None = Query(None, description="家長多小孩時指定"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
):
    student = await student_service.get_student_by_user_id(db, current_user.id, student_id)
    start = date_from or _today_taipei()
    end = date_to or start
    if end < start:
        raise ValidationException("結束日期不可小於起始日期")
    return await attendance_service.get_class_attendance(
        db,
        start,
        end,
        student_id=student.id,
    )
