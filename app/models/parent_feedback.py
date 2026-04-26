"""Parent feedback model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ParentFeedback(Base):
    __tablename__ = "parent_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    communication_book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communication_book_entries.id"), unique=True, nullable=False
    )
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    communication_entry = relationship("CommunicationBookEntry", back_populates="parent_feedback")