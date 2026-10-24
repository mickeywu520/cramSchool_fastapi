"""Leave & makeup service."""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.makeup_room import MakeupRoom
from app.models.student import Student
from app.services import makeup_room_service
from app.services.makeup_room_service import parse_hhmm as _parse_hhmm
from app.utils.exceptions import ForbiddenException, NotFoundException, ValidationException


async def _load_course(db: AsyncSession, course_id: int | None) -> Course:
    if course_id is None:
        raise ValidationException("請選擇要請假的課程")
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundException("Course")
    return course


async def create_leave_application(
    db: AsyncSession, student_id: int, data: dict
) -> LeaveApplication:
    leave_date: date = data["leave_date"]
    if leave_date < date.today():
        raise ValidationException("請假日期不可為過去日期")

    course = await _load_course(db, data.get("course_id"))

    # 補課場次（必填）：補課教室的固定時段，且晚於請假日期
    makeup_date: date | None = data.get("requested_makeup_date")
    start = _parse_hhmm(data.get("requested_makeup_start"))
    end = _parse_hhmm(data.get("requested_makeup_end"))
    room_id = data.get("requested_room_id")
    if makeup_date is None or start is None or end is None or room_id is None:
        raise ValidationException("請選擇補課教室與時段")
    if makeup_date <= leave_date:
        raise ValidationException("補課日期必須晚於請假日期")
    if makeup_date < date.today():
        raise ValidationException("補課日期不可為過去日期")

    room, _slot = await makeup_room_service.resolve_requested_slot(
        db, room_id, makeup_date, start, end
    )
    # 有空位才可選（名額不足直接 409）
    await makeup_room_service.ensure_seat_available(db, room, makeup_date, start)

    leave = LeaveApplication(
        student_id=student_id,
        course_id=course.id,
        leave_date=leave_date,
        leave_type=data["leave_type"],
        reason=data.get("reason"),
        status="pending",
        requested_makeup_date=makeup_date,
        requested_makeup_start=start,
        requested_makeup_end=end,
        requested_room_id=room.id,
    )
    db.add(leave)
    await db.flush()
    return leave


async def get_my_applications(db: AsyncSession, student_id: int) -> list[LeaveApplication]:
    result = await db.execute(
        select(LeaveApplication)
        .where(LeaveApplication.student_id == student_id)
        .options(
            selectinload(LeaveApplication.course),
            selectinload(LeaveApplication.student),
            selectinload(LeaveApplication.requested_room),
        )
        .order_by(LeaveApplication.created_at.desc())
    )
    return result.scalars().all()


async def get_application_by_id(db: AsyncSession, application_id: int, student_id: int) -> LeaveApplication:
    result = await db.execute(
        select(LeaveApplication)
        .where(LeaveApplication.id == application_id)
        .options(
            selectinload(LeaveApplication.course),
            selectinload(LeaveApplication.student),
            selectinload(LeaveApplication.requested_room),
        )
    )
    leave = result.scalar_one_or_none()
    if not leave:
        raise NotFoundException("Leave application")
    if leave.student_id != student_id:
        raise ForbiddenException("只能查看自己的請假申請")
    return leave


async def update_application(
    db: AsyncSession, application_id: int, student_id: int, data: dict
) -> LeaveApplication:
    leave = await get_application_by_id(db, application_id, student_id)
    if leave.status != "pending":
        raise ValidationException("只能修改待審核的請假申請")
    for field in ["leave_date", "leave_type", "reason", "course_id"]:
        if field in data and data[field] is not None:
            setattr(leave, field, data[field])
    if data.get("requested_makeup_date") is not None:
        start = _parse_hhmm(data.get("requested_makeup_start"))
        end = _parse_hhmm(data.get("requested_makeup_end"))
        room_id = data.get("requested_room_id")
        if start is None or end is None or room_id is None:
            raise ValidationException("請選擇補課教室與時段")
        room, _slot = await makeup_room_service.resolve_requested_slot(
            db, room_id, data["requested_makeup_date"], start, end
        )
        await makeup_room_service.ensure_seat_available(
            db, room, data["requested_makeup_date"], start
        )
        leave.requested_makeup_date = data["requested_makeup_date"]
        leave.requested_makeup_start = start
        leave.requested_makeup_end = end
        leave.requested_room_id = room.id
    await db.flush()
    return leave


async def cancel_application(db: AsyncSession, application_id: int, student_id: int):
    leave = await get_application_by_id(db, application_id, student_id)
    if leave.status != "pending":
        raise ValidationException("只能取消待審核的請假申請")
    await db.delete(leave)


async def get_pending_applications(db: AsyncSession) -> list[LeaveApplication]:
    result = await db.execute(
        select(LeaveApplication)
        .where(LeaveApplication.status == "pending")
        .options(
            selectinload(LeaveApplication.course),
            selectinload(LeaveApplication.student),
            selectinload(LeaveApplication.requested_room),
        )
        .order_by(LeaveApplication.created_at.desc())
    )
    return result.scalars().all()


async def get_all_applications(
    db: AsyncSession, status: str | None = None, limit: int = 500
) -> list[LeaveApplication]:
    """後台清單：含已核准／已駁回（新到舊），讓頁籤重整後仍看得到歷史。"""
    stmt = (
        select(LeaveApplication)
        .options(
            selectinload(LeaveApplication.course),
            selectinload(LeaveApplication.student),
            selectinload(LeaveApplication.requested_room),
        )
        .order_by(LeaveApplication.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(LeaveApplication.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


async def _create_requested_makeup(db: AsyncSession, leave: LeaveApplication) -> MakeupClass | None:
    """核准請假時，把家長指定的補課教室場次寫成正式補課紀錄。"""
    if leave.course_id is None:
        return None
    if not (leave.requested_makeup_date and leave.requested_makeup_start and leave.requested_makeup_end):
        return None
    existing = await db.execute(select(MakeupClass.id).where(MakeupClass.leave_id == leave.id))
    if existing.scalar_one_or_none() is not None:
        return None

    room: MakeupRoom | None = None
    if leave.requested_room_id:
        room = await db.get(MakeupRoom, leave.requested_room_id)
    if room is not None:
        # 待審核期間名額可能被別人排滿，核准當下再確認一次
        await makeup_room_service.ensure_seat_available(
            db, room, leave.requested_makeup_date, leave.requested_makeup_start
        )

    course = await db.get(Course, leave.course_id)
    makeup = MakeupClass(
        leave_id=leave.id,
        student_id=leave.student_id,
        course_id=leave.course_id,
        makeup_date=leave.requested_makeup_date,
        start_time=leave.requested_makeup_start,
        end_time=leave.requested_makeup_end,
        classroom=room.display_name if room else (course.location if course else None),
        room_id=room.id if room else None,
        status="scheduled",
        requested_by="parent",
    )
    db.add(makeup)
    await db.flush()
    return makeup


async def review_application(
    db: AsyncSession,
    application_id: int,
    reviewer_id: int,
    status: str,
    reason: str | None = None,
) -> LeaveApplication:
    result = await db.execute(
        select(LeaveApplication).where(LeaveApplication.id == application_id)
    )
    leave = result.scalar_one_or_none()
    if not leave:
        raise NotFoundException("Leave application")
    if leave.status != "pending":
        raise ValidationException("此申請已審核過")

    note = (reason or "").strip()
    if status == "rejected" and not note:
        raise ValidationException("駁回請填寫原因，系統會顯示給家長")

    leave.status = status
    leave.reviewed_by = reviewer_id
    leave.reviewed_at = datetime.now(timezone.utc)
    leave.review_note = note or None
    if status == "approved":
        await _create_requested_makeup(db, leave)
    await db.flush()
    return leave


async def list_makeup_options(
    db: AsyncSession,
    student: Student,
    course_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """家長可選的補課場次（補課教室的固定時段，依學生分校過濾）。

    保留這個入口是為了讓 router 不必直接相依 service；實際邏輯在 makeup_room_service。
    """
    if course_id is not None and not await db.get(Course, course_id):
        raise NotFoundException("Course")
    return await makeup_room_service.list_options(db, student, date_from, date_to)


async def get_my_makeup_classes(db: AsyncSession, student_id: int) -> list[MakeupClass]:
    result = await db.execute(
        select(MakeupClass)
        .where(MakeupClass.student_id == student_id)
        .options(selectinload(MakeupClass.course))
        .order_by(MakeupClass.makeup_date)
    )
    return result.scalars().all()


async def get_upcoming_makeup(db: AsyncSession, student_id: int) -> list[MakeupClass]:
    result = await db.execute(
        select(MakeupClass)
        .where(
            MakeupClass.student_id == student_id,
            MakeupClass.makeup_date >= date.today(),
            MakeupClass.status == "scheduled",
        )
        .options(selectinload(MakeupClass.course))
        .order_by(MakeupClass.makeup_date)
        .limit(5)
    )
    return result.scalars().all()


async def get_makeup_by_id(db: AsyncSession, makeup_id: int) -> MakeupClass | None:
    result = await db.execute(
        select(MakeupClass)
        .where(MakeupClass.id == makeup_id)
        .options(selectinload(MakeupClass.course))
    )
    return result.scalar_one_or_none()


async def create_makeup_class(db: AsyncSession, data: dict) -> MakeupClass:
    start = _parse_hhmm(data["start_time"])
    end = _parse_hhmm(data["end_time"])
    if start is None or end is None:
        raise ValidationException("補課時間格式不正確")

    room: MakeupRoom | None = None
    if data.get("room_id"):
        room = await makeup_room_service.get_room(db, data["room_id"])
        await makeup_room_service.ensure_seat_available(db, room, data["makeup_date"], start)

    makeup = MakeupClass(
        leave_id=data.get("leave_id"),
        student_id=data["student_id"],
        course_id=data["course_id"],
        makeup_date=data["makeup_date"],
        start_time=start,
        end_time=end,
        classroom=room.display_name if room else data.get("classroom"),
        room_id=room.id if room else None,
        notes=data.get("notes"),
        requested_by=data.get("requested_by") or "teacher",
    )
    db.add(makeup)
    await db.flush()
    return makeup


LEAVE_RULES = """
補課規範：
1. 請假需於上課前至少2小時提出申請。
2. 病假請於當天上課前通知，並於3日內補交證明。
3. 每學期最多可請假3次，超過需另行安排。
4. 補課請於請假時一併選擇時段，由老師審核確認。
5. 未依規定請假者，視為曠課，不予補課。
"""
