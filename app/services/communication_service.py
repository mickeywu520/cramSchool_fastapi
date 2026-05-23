"""Communication book service."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.communication import CommunicationBookEntry
from app.models.homework import HomeworkRecord
from app.models.parent_feedback import ParentFeedback
from app.models.reminder import Reminder
from app.models.student import Student
from app.models.teacher import Teacher
from app.utils.exceptions import NotFoundException


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

    # Add homework records
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

    # Add reminders
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