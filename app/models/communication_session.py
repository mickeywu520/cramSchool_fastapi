"""Course-based communication session model (replaces per-student entries)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CommunicationCourseSession(Base):
    __tablename__ = "communication_course_sessions"
    __table_args__ = (UniqueConstraint("course_id", "entry_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    tutoring_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_homework: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_exam_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_announcements: Mapped[str | None] = mapped_column(Text, nullable=True)
    exam_columns: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    course = relationship("Course")
    student_records = relationship(
        "CommunicationSessionStudent",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class CommunicationSessionStudent(Base):
    __tablename__ = "communication_session_students"
    __table_args__ = (UniqueConstraint("session_id", "student_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communication_course_sessions.id"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    arrival_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    homework: Mapped[str | None] = mapped_column(Text, nullable=True)
    vocab: Mapped[str | None] = mapped_column(String(10), nullable=True, default="優異")
    exam_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    announcements: Mapped[str | None] = mapped_column(Text, nullable=True)
    handout_status: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    exam_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_scores: Mapped[str | None] = mapped_column(Text, nullable=True)
    tutoring_attendance: Mapped[bool] = mapped_column(Boolean, default=False)
    reschedule_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    session = relationship("CommunicationCourseSession", back_populates="student_records")
    student = relationship("Student")

    @property
    def student_name(self) -> str:
        return self.student.student_name if self.student else ""
