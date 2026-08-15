"""Communication book service."""

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.communication import CommunicationBookEntry
from app.models.communication_session import (
    CommunicationCourseSession,
    CommunicationSessionStudent,
)
from app.models.course import Course
from app.models.homework import HomeworkRecord
from app.models.parent_feedback import ParentFeedback
from app.models.reminder import Reminder
from app.models.student import Student
from app.models.teacher import Teacher
from app.utils.exceptions import NotFoundException

# ── New: Course-session based queries ──


async def get_session_entries(
    db: AsyncSession, student_id: int, date_from: date | None = None, date_to: date | None = None
) -> list[dict]:
    query = (
        select(CommunicationSessionStudent)
        .where(CommunicationSessionStudent.student_id == student_id)
        .join(CommunicationSessionStudent.session)
        .join(CommunicationCourseSession.course)
        .where(Course.is_teaching == True)
        .options(
            selectinload(CommunicationSessionStudent.session)
            .selectinload(CommunicationCourseSession.course)
            .selectinload(Course.teacher),
            selectinload(CommunicationSessionStudent.session)
            .selectinload(CommunicationCourseSession.course),
        )
        .order_by(CommunicationSessionStudent.id.desc())
    )
    if date_from or date_to:
        conditions = []
        if date_from:
            conditions.append(
                or_(
                    CommunicationCourseSession.entry_date >= date_from,
                    CommunicationSessionStudent.reschedule_date >= date_from,
                )
            )
        if date_to:
            conditions.append(
                or_(
                    CommunicationCourseSession.entry_date <= date_to,
                    CommunicationSessionStudent.reschedule_date <= date_to,
                )
            )
        for condition in conditions:
            query = query.where(condition)

    result = await db.execute(query)
    records = result.scalars().all()
    if not records:
        return []

    session_ids = sorted({r.session_id for r in records if r.session_id})
    class_avgs: dict[int, float | None] = {}
    if session_ids:
        rows = (
            await db.execute(
                select(
                    CommunicationSessionStudent.session_id,
                    CommunicationSessionStudent.exam_score,
                ).where(CommunicationSessionStudent.session_id.in_(session_ids))
            )
        ).all()
        by_session: dict[int, list[int]] = {}
        for sid, score in rows:
            if score is not None:
                by_session.setdefault(sid, []).append(score)
        for sid, scores in by_session.items():
            class_avgs[sid] = round(sum(scores) / len(scores), 1) if scores else None

    return [_format_student_entry(r, class_avgs.get(r.session_id)) for r in records]


async def get_session_weekly(
    db: AsyncSession, student_id: int, week_start: date | None = None
) -> list[dict]:
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    query = (
        select(CommunicationSessionStudent)
        .where(CommunicationSessionStudent.student_id == student_id)
        .options(selectinload(CommunicationSessionStudent.session))
        .join(CommunicationCourseSession)
        .join(CommunicationCourseSession.course)
        .where(
            or_(
                CommunicationCourseSession.entry_date.between(week_start, week_end),
                CommunicationSessionStudent.reschedule_date.between(week_start, week_end),
            ),
            Course.is_teaching == True,
        )
        .order_by(CommunicationCourseSession.entry_date)
    )
    result = await db.execute(query)
    records = result.scalars().all()
    return [
        {
            "id": r.id,
            "entry_date": r.session.entry_date if r.session else None,
            "is_signed": r.parent_signed,
        }
        for r in records
        if r.session
    ]


async def submit_session_feedback(
    db: AsyncSession, entry_id: int, student_id: int, is_signed: bool
) -> CommunicationSessionStudent:
    result = await db.execute(
        select(CommunicationSessionStudent)
        .where(
            CommunicationSessionStudent.id == entry_id,
            CommunicationSessionStudent.student_id == student_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFoundException("Communication entry")

    if record.parent_signed:
        from app.utils.exceptions import ForbiddenException
        raise ForbiddenException("此聯絡簿已簽署，無法再修改")

    record.parent_signed = is_signed
    if is_signed:
        record.parent_signed_at = datetime.now(timezone.utc)

    await db.flush()
    return record


def _format_student_entry(r: CommunicationSessionStudent, class_average: float | None = None) -> dict:
    session = r.session
    course = session.course if session else None
    teacher = course.teacher if course else None

    custom_scores = {}
    if r.custom_scores:
        try:
            custom_scores = json.loads(r.custom_scores)
        except (json.JSONDecodeError, TypeError):
            custom_scores = {}

    return {
        "id": r.id,
        "session_id": session.id if session else 0,
        "entry_date": r.reschedule_date if r.reschedule_date else (session.entry_date if session else None),
        "course_name": f"{course.grade_level} {course.name}" if course else None,
        "tutor_name": teacher.name if teacher else None,
        "class_progress": session.class_progress if session else None,
        "class_homework": session.class_homework if session else None,
        "class_exam_scope": session.class_exam_scope if session else None,
        "class_announcements": session.class_announcements if session else None,
        "arrival_time": r.arrival_time,
        "departure_time": r.departure_time,
        "handout_status": r.handout_status,
        "homework_material": r.homework_material,
        "homework_workbook": r.homework_workbook,
        "exam_score": r.exam_score,
        "custom_scores": custom_scores,
        "class_average": class_average,
        "tutoring_attendance": r.tutoring_attendance,
        "notes": r.notes,
        "parent_signed": r.parent_signed,
        "parent_signed_at": r.parent_signed_at,
    }


# ── Old: per-student entry queries (kept for compatibility) ──


async def get_entries(
    db: AsyncSession, student_id: int, date_from: date | None = None, date_to: date | None = None
) -> list[CommunicationBookEntry]:
    query = (
        select(CommunicationBookEntry)
        .where(CommunicationBookEntry.student_id == student_id)
        .options(
            selectinload(CommunicationBookEntry.teacher),
            selectinload(CommunicationBookEntry.homework_records),
            selectinload(CommunicationBookEntry.reminders),
            selectinload(CommunicationBookEntry.parent_feedback),
        )
        .order_by(CommunicationBookEntry.entry_date.desc())
    )
    if date_from:
        query = query.where(CommunicationBookEntry.entry_date >= date_from)
    if date_to:
        query = query.where(CommunicationBookEntry.entry_date <= date_to)
    result = await db.execute(query)
    return result.scalars().all()


async def get_entry_by_id(db: AsyncSession, entry_id: int, student_id: int) -> CommunicationBookEntry:
    result = await db.execute(
        select(CommunicationBookEntry)
        .where(CommunicationBookEntry.id == entry_id, CommunicationBookEntry.student_id == student_id)
        .options(
            selectinload(CommunicationBookEntry.teacher),
            selectinload(CommunicationBookEntry.homework_records),
            selectinload(CommunicationBookEntry.reminders),
            selectinload(CommunicationBookEntry.parent_feedback),
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundException("Communication book entry")
    return entry


async def get_weekly_entries(
    db: AsyncSession, student_id: int, week_start: date | None = None
) -> list[CommunicationBookEntry]:
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    result = await db.execute(
        select(CommunicationBookEntry)
        .where(
            CommunicationBookEntry.student_id == student_id,
            CommunicationBookEntry.entry_date >= week_start,
            CommunicationBookEntry.entry_date <= week_end,
        )
        .options(selectinload(CommunicationBookEntry.parent_feedback))
        .order_by(CommunicationBookEntry.entry_date)
    )
    return result.scalars().all()


async def submit_feedback(
    db: AsyncSession, entry_id: int, student_id: int, feedback: str | None, is_signed: bool
) -> ParentFeedback:
    entry = await get_entry_by_id(db, entry_id, student_id)

    if entry.parent_feedback and entry.parent_feedback.is_signed:
        from app.utils.exceptions import ForbiddenException
        raise ForbiddenException("此聯絡簿已簽署，無法再修改")

    if entry.parent_feedback:
        pf = entry.parent_feedback
        pf.feedback = feedback
        pf.is_signed = is_signed
        if is_signed:
            pf.signed_at = datetime.now(timezone.utc)
    else:
        pf = ParentFeedback(
            communication_book_id=entry.id,
            feedback=feedback,
            is_signed=is_signed,
            signed_at=datetime.now(timezone.utc) if is_signed else None,
        )
        db.add(pf)

    await db.flush()
    return pf


async def create_entry(db: AsyncSession, data: dict) -> CommunicationBookEntry:
    raw_date = data["entry_date"]
    if isinstance(raw_date, str):
        raw_date = date.fromisoformat(raw_date) if raw_date else date.today()
    entry = CommunicationBookEntry(
        student_id=data["student_id"],
        teacher_id=data["teacher_id"],
        entry_date=raw_date,
        focus_score=data.get("focus_score"),
        interaction_score=data.get("interaction_score"),
        homework_completion=data.get("homework_completion"),
        teacher_comment=data.get("teacher_comment"),
    )
    db.add(entry)
    await db.flush()

    for hw in data.get("homework", []):
        raw_due = hw.get("due_date")
        if isinstance(raw_due, str):
            raw_due = date.fromisoformat(raw_due) if raw_due else None
        db.add(HomeworkRecord(
            communication_book_id=entry.id,
            subject=hw.get("subject", ""),
            content=hw.get("content", ""),
            due_date=raw_due,
        ))

    for rem in data.get("reminders", []):
        db.add(Reminder(
            communication_book_id=entry.id,
            content=rem.get("content", ""),
            priority=rem.get("priority", "normal"),
        ))

    await db.flush()
    return entry


def format_entry_response(entry: CommunicationBookEntry) -> dict:
    return {
        "id": entry.id,
        "entry_date": entry.entry_date,
        "focus_score": entry.focus_score,
        "interaction_score": entry.interaction_score,
        "homework_completion": entry.homework_completion,
        "teacher_comment": entry.teacher_comment,
        "teacher_name": entry.teacher.name if entry.teacher else None,
        "homework": [
            {"id": h.id, "subject": h.subject, "content": h.content, "due_date": h.due_date, "is_completed": h.is_completed}
            for h in (entry.homework_records or [])
        ],
        "reminders": [
            {"id": r.id, "content": r.content, "priority": r.priority}
            for r in (entry.reminders or [])
        ],
        "parent_feedback": {
            "feedback": entry.parent_feedback.feedback,
            "is_signed": entry.parent_feedback.is_signed,
            "signed_at": entry.parent_feedback.signed_at,
        } if entry.parent_feedback else None,
    }
