"""Communication book entry model."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CommunicationBookEntry(Base):
    __tablename__ = "communication_book_entries"
    __table_args__ = (UniqueConstraint("student_id", "entry_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    focus_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interaction_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    homework_completion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    student = relationship("Student", back_populates="communication_entries")
    teacher = relationship("Teacher", back_populates="communication_entries")
    homework_records = relationship("HomeworkRecord", back_populates="communication_entry")
    reminders = relationship("Reminder", back_populates="communication_entry")
    parent_feedback = relationship("ParentFeedback", back_populates="communication_entry", uselist=False)