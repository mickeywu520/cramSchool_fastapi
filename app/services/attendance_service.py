"""Attendance service for punch ingestion and per-class attendance."""

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attendance import AttendanceDaily, ClassAttendance, PunchRawEvent
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.leave import LeaveApplication
from app.models.makeup import MakeupClass
from app.models.student import Student
from app.schemas.punch import GcpPunchEvent

logger = logging.getLogger(__name__)

TAIPEI_TZ = timezone(timedelta(hours=8))
ATTENDANCE_EVENT_CODES = {"M11", "M03"}


@dataclass(frozen=True)
class ClassOccurrence:
    course_id: int
    course_name: str
    attendance_date: date
    session_type: str
    session_ref: int
    start_at: datetime
    end_at: datetime
    location: str | None = None
    makeup_class_id: int | None = None


def _reverse_bytes_hex(hex_str: str) -> str | None:
    try:
        return bytes.fromhex(hex_str)[::-1].hex().upper()
    except ValueError:
        return None


def incoming_low32(
    uid_hex: str,
    uid_decimal: int | None,
    hi: int | None,
    lo: int | None,
) -> int | None:
    if hi is not None and lo is not None:
        try:
            return ((int(hi) & 0xFFFF) << 16) | (int(lo) & 0xFFFF)
        except (TypeError, ValueError):
            pass
    if uid_hex:
        value = uid_hex.strip().upper()
        if value.startswith("0X"):
            value = value[2:]
        if value:
            try:
                return int(value[-8:], 16) & 0xFFFFFFFF
            except ValueError:
                pass
    if uid_decimal is not None:
        try:
            return int(uid_decimal) & 0xFFFFFFFF
        except (TypeError, ValueError):
            pass
    return None


def stored_card_candidates(card_number: str | None) -> set[int]:
    result: set[int] = set()
    if not card_number:
        return result

    value = card_number.strip()
    if not value:
        return result

    if ":" in value:
        parts = [part.strip() for part in value.split(":")]
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            result.add(((int(parts[0]) & 0xFFFF) << 16) | (int(parts[1]) & 0xFFFF))
            return result
        try:
            raw = bytes.fromhex("".join(parts))
            if len(raw) in (4, 7, 8):
                result.add(int.from_bytes(raw[-4:], "big") & 0xFFFFFFFF)
                result.add(int.from_bytes(raw[-4:], "little") & 0xFFFFFFFF)
        except ValueError:
            pass
        return result

    if value.isdigit():
        result.add(int(value) & 0xFFFFFFFF)
        return result

    normalized = value.upper().replace(" ", "")
    if normalized.startswith("0X"):
        normalized = normalized[2:]
    if len(normalized) >= 4 and all(char in "0123456789ABCDEF" for char in normalized):
        try:
            value32 = int(normalized[-8:], 16) & 0xFFFFFFFF
            result.add(value32)
            reversed_value = _reverse_bytes_hex(normalized[-8:])
            if reversed_value:
                result.add(int(reversed_value, 16) & 0xFFFFFFFF)
        except ValueError:
            pass
    return result


def canonical_key(low32: int) -> str:
    return f"{low32 & 0xFFFFFFFF:08X}"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI_TZ)
    return parsed


def _taipei(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=TAIPEI_TZ)
    return value.astimezone(TAIPEI_TZ)


def _parse_clock(value: object) -> time | None:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        try:
            return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        except (TypeError, ValueError):
            return None
    if len(text) in (3, 4) and text.isdigit():
        if len(text) == 3:
            return time(int(text[0]), int(text[1:]))
        return time(int(text[:2]), int(text[2:]))
    try:
        return time.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _combine_local(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=TAIPEI_TZ)


def _course_day_numbers(course: Course) -> set[int]:
    values: set[int] = set()
    raw = course.days_of_week
    if raw:
        for part in str(raw).replace("、", ",").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                number = int(part)
            except ValueError:
                continue
            if number == 0:
                number = 7
            if 1 <= number <= 7:
                values.add(number)
    if not values and course.day_of_week is not None:
        number = int(course.day_of_week)
        values.add(7 if number == 0 else number)
    return values


def _course_is_enabled(course: Course) -> bool:
    return course.is_active is not False and course.is_teaching is not False


def _course_on_date(course: Course, day: date) -> bool:
    if not _course_is_enabled(course):
        return False
    if course.start_date and day < course.start_date:
        return False
    if course.end_date and day > course.end_date:
        return False
    return day.isoweekday() in _course_day_numbers(course)


def _regular_occurrence(course: Course, day: date) -> ClassOccurrence | None:
    if not _course_on_date(course, day):
        return None
    start_clock = _parse_clock(course.start_time)
    end_clock = _parse_clock(course.end_time)
    if start_clock is None or end_clock is None:
        return None
    start_at = _combine_local(day, start_clock)
    end_at = _combine_local(day, end_clock)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return ClassOccurrence(
        course_id=course.id,
        course_name=course.name,
        attendance_date=day,
        session_type="regular",
        session_ref=course.id,
        start_at=start_at,
        end_at=end_at,
        location=course.location,
    )


def _makeup_occurrence(makeup: MakeupClass, course: Course, day: date) -> ClassOccurrence | None:
    if makeup.makeup_date != day or makeup.status in {"cancelled", "canceled"}:
        return None
    start_clock = _parse_clock(makeup.start_time)
    end_clock = _parse_clock(makeup.end_time)
    if start_clock is None or end_clock is None:
        return None
    start_at = _combine_local(day, start_clock)
    end_at = _combine_local(day, end_clock)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return ClassOccurrence(
        course_id=course.id,
        course_name=course.name,
        attendance_date=day,
        session_type="makeup",
        session_ref=makeup.id,
        start_at=start_at,
        end_at=end_at,
        location=makeup.classroom,
        makeup_class_id=makeup.id,
    )


async def _load_occurrences(
    db: AsyncSession,
    student_id: int,
    day: date,
    course_id: int | None = None,
) -> list[ClassOccurrence]:
    enrollment_query = (
        select(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.student_id == student_id, Enrollment.status == "active")
    )
    if course_id is not None:
        enrollment_query = enrollment_query.where(Course.id == course_id)
    enrollment_rows = (await db.execute(enrollment_query)).all()
    occurrences = [
        occurrence
        for _, course in enrollment_rows
        if (occurrence := _regular_occurrence(course, day)) is not None
    ]

    makeup_query = (
        select(MakeupClass, Course)
        .join(Course, Course.id == MakeupClass.course_id)
        .where(MakeupClass.student_id == student_id, MakeupClass.makeup_date == day)
    )
    if course_id is not None:
        makeup_query = makeup_query.where(Course.id == course_id)
    makeup_rows = (await db.execute(makeup_query)).all()
    occurrences.extend(
        occurrence
        for makeup, course in makeup_rows
        if (occurrence := _makeup_occurrence(makeup, course, day)) is not None
    )
    return occurrences


def _occurrence_rank(occurrence: ClassOccurrence, occurred_at: datetime) -> tuple:
    if occurred_at < occurrence.start_at:
        distance = (occurrence.start_at - occurred_at).total_seconds()
    elif occurred_at > occurrence.end_at:
        distance = (occurred_at - occurrence.end_at).total_seconds()
    else:
        distance = 0
    start_distance = abs((occurred_at - occurrence.start_at).total_seconds())
    return (
        distance,
        start_distance,
        -occurrence.start_at.timestamp(),
        0 if occurrence.session_type == "makeup" else 1,
    )


async def _find_occurrence(
    db: AsyncSession,
    student_id: int,
    occurred_at: datetime,
) -> ClassOccurrence | None:
    day = occurred_at.astimezone(TAIPEI_TZ).date()
    occurrences = await _load_occurrences(db, student_id, day)
    before = timedelta(minutes=max(0, settings.PUNCH_ATTENDANCE_BEFORE_MINUTES))
    after = timedelta(minutes=max(0, settings.PUNCH_ATTENDANCE_AFTER_MINUTES))
    eligible = [
        occurrence
        for occurrence in occurrences
        if occurrence.start_at - before <= occurred_at <= occurrence.end_at + after
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda item: _occurrence_rank(item, occurred_at))


def _is_attendance_event(event: GcpPunchEvent) -> bool:
    return (event.event.event_code or "").strip().upper() in ATTENDANCE_EVENT_CODES


def _status_for_punch(occurrence: ClassOccurrence, occurred_at: datetime) -> tuple[str, int | None]:
    late_cutoff = occurrence.start_at + timedelta(
        minutes=max(0, settings.PUNCH_ATTENDANCE_LATE_MINUTES)
    )
    if occurred_at <= late_cutoff:
        return "on_time", 0
    late_minutes = max(1, math.ceil((occurred_at - occurrence.start_at).total_seconds() / 60))
    return "late", late_minutes


async def _build_card_map(db: AsyncSession) -> dict[int, Student]:
    result = await db.execute(select(Student).where(Student.card_number.isnot(None)))
    card_map: dict[int, Student] = {}
    for student in result.scalars().all():
        for candidate in stored_card_candidates(student.card_number):
            if candidate in card_map:
                logger.warning("重複卡號 low32=%08X: student %s 與 %s", candidate, card_map[candidate].id, student.id)
                continue
            card_map[candidate] = student
    return card_map


async def _existing_event(db: AsyncSession, event_id: str) -> PunchRawEvent | None:
    result = await db.execute(select(PunchRawEvent).where(PunchRawEvent.event_id == event_id))
    return result.scalar_one_or_none()


async def _student_by_id(db: AsyncSession, student_id: int | None) -> Student | None:
    if student_id is None:
        return None
    result = await db.execute(select(Student).where(Student.id == student_id))
    return result.scalar_one_or_none()


async def _class_record(
    db: AsyncSession,
    student_id: int,
    occurrence: ClassOccurrence,
) -> ClassAttendance | None:
    result = await db.execute(
        select(ClassAttendance).where(
            ClassAttendance.student_id == student_id,
            ClassAttendance.course_id == occurrence.course_id,
            ClassAttendance.attendance_date == occurrence.attendance_date,
            ClassAttendance.session_type == occurrence.session_type,
            ClassAttendance.session_ref == occurrence.session_ref,
        )
    )
    return result.scalar_one_or_none()


async def _get_or_create_class_record(
    db: AsyncSession,
    student_id: int,
    occurrence: ClassOccurrence,
) -> ClassAttendance:
    record = await _class_record(db, student_id, occurrence)
    if record is not None:
        return record
    record = ClassAttendance(
        student_id=student_id,
        course_id=occurrence.course_id,
        attendance_date=occurrence.attendance_date,
        session_type=occurrence.session_type,
        session_ref=occurrence.session_ref,
        status="absent",
    )
    db.add(record)
    await db.flush()
    return record


async def _approved_leave_id(
    db: AsyncSession,
    student_id: int,
    course_id: int,
    day: date,
) -> int | None:
    result = await db.execute(
        select(LeaveApplication.id)
        .where(
            LeaveApplication.student_id == student_id,
            LeaveApplication.leave_date == day,
            LeaveApplication.status == "approved",
            or_(LeaveApplication.course_id.is_(None), LeaveApplication.course_id == course_id),
        )
        .order_by(LeaveApplication.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _update_daily(
    db: AsyncSession,
    student_id: int,
    occurred_at: datetime,
    device_ip: str | None,
) -> None:
    day = occurred_at.astimezone(TAIPEI_TZ).date()
    result = await db.execute(
        select(AttendanceDaily).where(
            AttendanceDaily.student_id == student_id,
            AttendanceDaily.punch_date == day,
        )
    )
    daily = result.scalar_one_or_none()
    if daily is None:
        db.add(
            AttendanceDaily(
                student_id=student_id,
                punch_date=day,
                first_punch=occurred_at,
                last_punch=occurred_at,
                punch_count=1,
                device_ip=device_ip,
            )
        )
        return
    first_punch = _taipei(daily.first_punch)
    last_punch = _taipei(daily.last_punch)
    if first_punch is None or occurred_at < first_punch:
        daily.first_punch = occurred_at
    if last_punch is None or occurred_at > last_punch:
        daily.last_punch = occurred_at
    daily.punch_count = (daily.punch_count or 0) + 1
    if daily.device_ip is None:
        daily.device_ip = device_ip


def _class_result(
    event_id: str,
    status: str,
    student: Student | None,
    *,
    stored: bool,
    record: ClassAttendance | None = None,
    attendance_status: str | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "status": status,
        "student_id": student.id if student else None,
        "student_name": student.student_name if student else None,
        "stored": stored,
        "class_attendance_id": record.id if record else None,
        "course_id": record.course_id if record else None,
        "session_type": record.session_type if record else None,
        "session_ref": record.session_ref if record else None,
        "attendance_status": attendance_status or (record.status if record else None),
    }


async def _duplicate_result(db: AsyncSession, event_id: str) -> dict:
    existing = await _existing_event(db, event_id)
    student = await _student_by_id(db, existing.student_id if existing else None)
    record = None
    if existing and existing.class_attendance_id is not None:
        result = await db.execute(
            select(ClassAttendance).where(ClassAttendance.id == existing.class_attendance_id)
        )
        record = result.scalar_one_or_none()
    return _class_result(
        event_id,
        "duplicate",
        student,
        stored=False,
        record=record,
    )


async def _error_result(event_id: str) -> dict:
    return _class_result(event_id, "error", None, stored=False, attendance_status="error")


async def ingest_events(db: AsyncSession, events: list[GcpPunchEvent]) -> list[dict]:
    """Store each event independently and assign valid card events to class sessions."""
    card_map = await _build_card_map(db)
    results: list[dict] = []

    for event in events:
        if await _existing_event(db, event.event_id) is not None:
            results.append(await _duplicate_result(db, event.event_id))
            continue

        occurred_at = parse_dt(event.occurred_at)
        if occurred_at is None:
            results.append(_error_result(event.event_id))
            continue
        occurred_at = occurred_at.astimezone(TAIPEI_TZ)
        received_at = parse_dt(event.received_at)
        hi = event.card.card_number_hi if event.card.card_number_hi is not None else event.card.site_code
        lo = event.card.card_number_lo if event.card.card_number_lo is not None else event.card.card_code
        low32 = incoming_low32(event.card.uid_hex, event.card.uid_decimal, hi, lo)
        student = card_map.get(low32) if low32 is not None else None

        try:
            async with db.begin_nested():
                raw = PunchRawEvent(
                    event_id=event.event_id,
                    student_id=student.id if student else None,
                    uid_hex=event.card.uid_hex.upper() if event.card.uid_hex else None,
                    uid_decimal=event.card.uid_decimal,
                    card_hi=hi,
                    card_lo=lo,
                    card_key=canonical_key(low32) if low32 is not None else None,
                    occurred_at=occurred_at,
                    received_at=received_at,
                    node_id=event.device.node_id,
                    device_ip=event.device.ip or None,
                    receiver_id=event.ingested_by.receiver_id if event.ingested_by else None,
                    event_code=event.event.event_code.upper() if event.event.event_code else None,
                    source_sub_code=event.device.source_sub_code,
                    port_number=event.device.port_number,
                    raw_message=event.raw_message or None,
                )
                db.add(raw)
                await db.flush()

                if student is None:
                    result = _class_result(
                        event.event_id,
                        "unknown_card",
                        None,
                        stored=True,
                    )
                elif student.followup_status != "在籍":
                    result = _class_result(
                        event.event_id,
                        "inactive",
                        student,
                        stored=True,
                    )
                else:
                    await _update_daily(db, student.id, occurred_at, event.device.ip or None)
                    record = None
                    if _is_attendance_event(event):
                        occurrence = await _find_occurrence(db, student.id, occurred_at)
                        if occurrence is not None:
                            record = await _get_or_create_class_record(db, student.id, occurrence)
                            first_punch = _taipei(record.first_punch)
                            if first_punch is None or occurred_at < first_punch:
                                record.first_punch = occurred_at
                            last_punch = _taipei(record.last_punch)
                            if last_punch is None or occurred_at > last_punch:
                                record.last_punch = occurred_at
                            record.punch_count = (record.punch_count or 0) + 1
                            record.status, record.late_minutes = _status_for_punch(
                                occurrence,
                                _taipei(record.first_punch) or occurred_at,
                            )
                            record.leave_id = None
                            raw.class_attendance_id = record.id
                    result = _class_result(
                        event.event_id,
                        "ok",
                        student,
                        stored=True,
                        record=record,
                        attendance_status=record.status if record else "unmatched",
                    )
                await db.flush()
        except IntegrityError:
            if await _existing_event(db, event.event_id) is not None:
                results.append(await _duplicate_result(db, event.event_id))
            else:
                results.append(_error_result(event.event_id))
            continue
        results.append(result)

    await db.flush()
    return results


async def _record_for_occurrence(
    db: AsyncSession,
    student_id: int,
    occurrence: ClassOccurrence,
) -> ClassAttendance:
    return await _get_or_create_class_record(db, student_id, occurrence)


async def _reconcile_record(
    db: AsyncSession,
    record: ClassAttendance,
    occurrence: ClassOccurrence,
    now: datetime,
) -> None:
    has_punch = (record.punch_count or 0) > 0 or record.first_punch is not None
    if has_punch:
        record.status, record.late_minutes = _status_for_punch(
            occurrence,
            _taipei(record.first_punch) or occurrence.start_at,
        )
        return
    if occurrence.end_at + timedelta(minutes=max(0, settings.PUNCH_ATTENDANCE_AFTER_MINUTES)) > now:
        record.status = "pending"
        record.late_minutes = None
        return
    leave_id = await _approved_leave_id(
        db,
        record.student_id,
        occurrence.course_id,
        occurrence.attendance_date,
    )
    record.leave_id = leave_id
    record.status = "leave" if leave_id is not None else "absent"
    record.late_minutes = None


async def ensure_class_attendance(
    db: AsyncSession,
    date_from: date,
    date_to: date | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
    now: datetime | None = None,
) -> list[ClassAttendance]:
    """Create missing regular/makeup class records and reconcile absence/leave."""
    end_date = date_to or date_from
    if end_date < date_from:
        return []
    if (end_date - date_from).days > 366:
        end_date = date_from + timedelta(days=366)
    current = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    days = [date_from + timedelta(days=offset) for offset in range((end_date - date_from).days + 1)]

    enrollment_query = (
        select(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.status == "active")
    )
    if student_id is not None:
        enrollment_query = enrollment_query.where(Enrollment.student_id == student_id)
    if course_id is not None:
        enrollment_query = enrollment_query.where(Course.id == course_id)
    enrollment_rows = (await db.execute(enrollment_query)).all()

    records: list[ClassAttendance] = []
    for enrollment, course in enrollment_rows:
        for day in days:
            occurrence = _regular_occurrence(course, day)
            if occurrence is None:
                continue
            record = await _record_for_occurrence(db, enrollment.student_id, occurrence)
            await _reconcile_record(db, record, occurrence, current)
            records.append(record)

    makeup_query = (
        select(MakeupClass, Course)
        .join(Course, Course.id == MakeupClass.course_id)
        .where(MakeupClass.makeup_date >= date_from, MakeupClass.makeup_date <= end_date)
    )
    if student_id is not None:
        makeup_query = makeup_query.where(MakeupClass.student_id == student_id)
    if course_id is not None:
        makeup_query = makeup_query.where(Course.id == course_id)
    makeup_rows = (await db.execute(makeup_query)).all()
    for makeup, course in makeup_rows:
        occurrence = _makeup_occurrence(makeup, course, makeup.makeup_date)
        if occurrence is None:
            continue
        record = await _record_for_occurrence(db, makeup.student_id, occurrence)
        await _reconcile_record(db, record, occurrence, current)
        records.append(record)

    await db.flush()
    return records


async def get_class_attendance(
    db: AsyncSession,
    date_from: date,
    date_to: date | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
) -> list[dict]:
    """Return per-class attendance rows, generating missing absence/leave rows."""
    await ensure_class_attendance(
        db,
        date_from,
        date_to,
        student_id=student_id,
        course_id=course_id,
    )
    query = (
        select(ClassAttendance, Student, Course, LeaveApplication)
        .join(Student, Student.id == ClassAttendance.student_id)
        .join(Course, Course.id == ClassAttendance.course_id)
        .outerjoin(LeaveApplication, LeaveApplication.id == ClassAttendance.leave_id)
        .where(ClassAttendance.attendance_date >= date_from)
        .where(ClassAttendance.attendance_date <= (date_to or date_from))
    )
    if student_id is not None:
        query = query.where(ClassAttendance.student_id == student_id)
    if course_id is not None:
        query = query.where(ClassAttendance.course_id == course_id)
    rows = (await db.execute(query.order_by(
        ClassAttendance.attendance_date.asc(),
        Student.student_name.asc(),
        ClassAttendance.course_id.asc(),
        ClassAttendance.session_ref.asc(),
    ))).all()

    return [
        {
            "id": record.id,
            "student_id": record.student_id,
            "student_name": student.student_name,
            "card_number": student.card_number,
            "course_id": record.course_id,
            "course_name": course.name,
            "attendance_date": str(record.attendance_date),
            "session_type": record.session_type,
            "session_ref": record.session_ref,
            "status": record.status,
            "first_punch": record.first_punch.isoformat() if record.first_punch else None,
            "last_punch": record.last_punch.isoformat() if record.last_punch else None,
            "late_minutes": record.late_minutes,
            "punch_count": record.punch_count or 0,
            "leave_id": record.leave_id,
            "leave_type": leave.leave_type if leave else None,
        }
        for record, student, course, leave in rows
    ]
