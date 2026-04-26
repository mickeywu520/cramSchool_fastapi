"""Homework record model."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class HomeworkRecord(Base):
    __tablename__ = "homework_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    communication_book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communication_book_entries.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    communication_entry = relationship("CommunicationBookEntry", back_populates="homework_records")