"""Makeup class model."""

from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MakeupClass(Base):
    __tablename__ = "makeup_classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leave_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leave_applications.id"), unique=True, nullable=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    makeup_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    classroom: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    leave_application = relationship("LeaveApplication", back_populates="makeup_class")
    student = relationship("Student", back_populates="makeup_classes")
    course = relationship("Course", back_populates="makeup_classes")