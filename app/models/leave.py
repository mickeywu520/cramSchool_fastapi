"""Leave application model."""

from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeaveApplication(Base):
    __tablename__ = "leave_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    course_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("courses.id"), nullable=True)
    leave_date: Mapped[date] = mapped_column(Date, nullable=False)
    leave_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # 家長指定的補課場次（同一課程的未來場次）；老師核准時才寫入 makeup_classes
    requested_makeup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_makeup_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    requested_makeup_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 駁回原因（必填），家長端會顯示
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    student = relationship("Student", back_populates="leave_applications")
    course = relationship("Course", back_populates="leave_applications")
    makeup_class = relationship("MakeupClass", back_populates="leave_application", uselist=False)