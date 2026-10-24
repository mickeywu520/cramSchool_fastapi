"""Leave & makeup service."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.student import Student
from app.services.attendance_service import _course_on_date, _regular_occurrence
from app.utils.exceptions import ForbiddenException, NotFoundException, ValidationException

# 一次最多回傳幾天的可補課場次（避免家長亂送超大區間）
MAX_OPTION_DAYS = 120
# 沒帶日期時，預設往後看幾天的場次
DEFAULT_OPTION_DAYS = 60


def _parse_hhmm(value: object) -> time | None:
    """接受 "18:00" 或 "1800"，回傳 time；無法解析回 None。"""
    if value is None:
        return None
    raw = str(value).strip().replace("：", ":")
    if not raw:
        return None
    try:
        if ":" in raw:
            hour, minute = raw.split(":", 1)
            return time(int(hour), int(minute))
        if len(raw) == 4 and raw.isdigit():
            return time(int(raw[:2]), int(raw[2:]))
    except ValueError:
        return None
    return None


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

    # 補課時段（必填）：必須是同一門課的未來場次，且晚於請假日期
    makeup_date: date | None = data.get("requested_makeup_date")
    start = _parse_hhmm(data.get("requested_makeup_start"))
    end = _parse_hhmm(data.get("requested_makeup_end"))
    if makeup_date is None or start is None or end is None:
        raise ValidationException("請選擇補課時段")
    if end <= start:
        raise ValidationException("補課結束時間必須晚於開始時間")
    if makeup_date <= leave_date:
        raise ValidationException("補課日期必須晚於請假日期")
    if makeup_date < date.today():
        raise ValidationException("補課日期不可為過去日期")
    if not _course_on_date(course, makeup_date):
        raise ValidationException("所選日期不是這門課的上課日，請重新選擇補課時段")

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
        if start is None or end is None:
            raise ValidationException("請選擇補課時段")
        leave.requested_makeup_date = data["requested_makeup_date"]
        leave.requested_makeup_start = start
        leave.requested_makeup_end = end
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


async def _create_requested_makeup(db: AsyncSession, leave: LeaveApplication) -> MakeupClass | None:
    """核准請假時，把家長指定的補課場次寫成正式補課紀錄。"""
    if leave.course_id is None:
        return None
    if not (leave.requested_makeup_date and leave.requested_makeup_start and leave.requested_makeup_end):
        return None
    existing = await db.execute(select(MakeupClass.id).where(MakeupClass.leave_id == leave.id))
    if existing.scalar_one_or_none() is not None:
        return None

    course = await db.get(Course, leave.course_id)
    makeup = MakeupClass(
        leave_id=leave.id,
        student_id=leave.student_id,
        course_id=leave.course_id,
        makeup_date=leave.requested_makeup_date,
        start_time=leave.requested_makeup_start,
        end_time=leave.requested_makeup_end,
        classroom=course.location if course else None,
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
    course_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """列出某門課在指定區間內可補課的場次（同一課程的未來場次）。"""
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundException("Course")

    today = date.today()
    start_day = max(date_from or today, today)
    end_day = date_to or (start_day + timedelta(days=DEFAULT_OPTION_DAYS))
    if end_day < start_day:
        raise ValidationException("查詢區間不正確")
    if (end_day - start_day).days > MAX_OPTION_DAYS:
        end_day = start_day + timedelta(days=MAX_OPTION_DAYS)

    enrolled = (
        await db.execute(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.course_id == course_id, Enrollment.status == "active")
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(MakeupClass.makeup_date, func.count())
            .where(
                MakeupClass.course_id == course_id,
                MakeupClass.makeup_date >= start_day,
                MakeupClass.makeup_date <= end_day,
                MakeupClass.status.notin_(("cancelled", "canceled")),
            )
            .group_by(MakeupClass.makeup_date)
        )
    ).all()
    makeup_counts = {row[0]: row[1] for row in rows}

    options: list[dict] = []
    day = start_day
    while day <= end_day:
        occurrence = _regular_occurrence(course, day)
        if occurrence:
            options.append(
                {
                    "date": day,
                    "weekday": day.isoweekday(),
                    "start_time": occurrence.start_at.strftime("%H:%M"),
                    "end_time": occurrence.end_at.strftime("%H:%M"),
                    "classroom": course.location,
                    "enrolled": enrolled,
                    "capacity": course.max_students,
                    "makeup_count": makeup_counts.get(day, 0),
                }
            )
        day += timedelta(days=1)
    return options


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
