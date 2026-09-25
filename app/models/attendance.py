"""Attendance models for raw punches, daily summaries, and class sessions."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PunchRawEvent(Base):
    __tablename__ = "punch_raw_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    student_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("students.id"), nullable=True)
    uid_hex: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uid_decimal: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_hi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_lo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_key: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receiver_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_sub_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_attendance_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("class_attendance.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student = relationship("Student")
    class_attendance = relationship("ClassAttendance", back_populates="raw_events")


class AttendanceDaily(Base):
    __tablename__ = "attendance_daily"
    __table_args__ = (UniqueConstraint("student_id", "punch_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    punch_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_punch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_punch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    punch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    student = relationship("Student")


class ClassAttendance(Base):
    __tablename__ = "class_attendance"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            "attendance_date",
            "session_type",
            "session_ref",
            name="uq_class_attendance_session",
        ),
        Index("ix_class_attendance_student_date", "student_id", "attendance_date"),
        Index("ix_class_attendance_course_date", "course_id", "attendance_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False, default="regular")
    session_ref: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="absent")
    first_punch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_punch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    punch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leave_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leave_applications.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    student = relationship("Student")
    course = relationship("Course")
    leave = relationship("LeaveApplication")
    raw_events = relationship("PunchRawEvent", back_populates="class_attendance")
