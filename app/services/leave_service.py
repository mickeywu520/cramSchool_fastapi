"""Leave & makeup service."""

from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.student import Student
from app.utils.exceptions import ForbiddenException, NotFoundException, ValidationException


async def create_leave_application(
    db: AsyncSession, student_id: int, data: dict
) -> LeaveApplication:
    if data["leave_date"] < date.today():
        raise ValidationException("請假日期不可為過去日期")

    leave = LeaveApplication(
        student_id=student_id,
        course_id=data.get("course_id"),
        leave_date=data["leave_date"],
        leave_type=data["leave_type"],
        reason=data.get("reason"),
        status="pending",
    )
    db.add(leave)
    await db.flush()
    return leave


async def get_my_applications(db: AsyncSession, student_id: int) -> list[LeaveApplication]:
    result = await db.execute(
        select(LeaveApplication)
        .where(LeaveApplication.student_id == student_id)
        .options(selectinload(LeaveApplication.course))
        .order_by(LeaveApplication.created_at.desc())
    )
    return result.scalars().all()


async def get_application_by_id(db: AsyncSession, application_id: int, student_id: int) -> LeaveApplication:
    result = await db.execute(
        select(LeaveApplication)
        .where(LeaveApplication.id == application_id)
        .options(selectinload(LeaveApplication.course))
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
        .options(selectinload(LeaveApplication.course), selectinload(LeaveApplication.student))
        .order_by(LeaveApplication.created_at.desc())
    )
    return result.scalars().all()


async def review_application(
    db: AsyncSession, application_id: int, reviewer_id: int, status: str
) -> LeaveApplication:
    result = await db.execute(
        select(LeaveApplication).where(LeaveApplication.id == application_id)
    )
    leave = result.scalar_one_or_none()
    if not leave:
        raise NotFoundException("Leave application")
    if leave.status != "pending":
        raise ValidationException("此申請已審核過")
    leave.status = status
    leave.reviewed_by = reviewer_id
    leave.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return leave


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


async def create_makeup_class(db: AsyncSession, data: dict) -> MakeupClass:
    start_parts = data["start_time"].split(":")
    end_parts = data["end_time"].split(":")
    makeup = MakeupClass(
        leave_id=data.get("leave_id"),
        student_id=data["student_id"],
        course_id=data["course_id"],
        makeup_date=data["makeup_date"],
        start_time=time(int(start_parts[0]), int(start_parts[1])),
        end_time=time(int(end_parts[0]), int(end_parts[1])),
        classroom=data.get("classroom"),
        notes=data.get("notes"),
    )
    db.add(makeup)
    await db.flush()
    return makeup


LEAVE_RULES = """
補課規範：
1. 請假需於上課前至少2小時提出申請。
2. 病假請於當天上課前通知，並於3日內補交證明。
3. 每學期最多可請假3次，超過需另行安排。
4. 補課將由老師統一安排時間，請留意補課通知。
5. 未依規定請假者，視為曠課，不予補課。
"""