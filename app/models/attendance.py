"""Attendance models - punch clock raw events + daily aggregation.

設計說明:
- punch_raw_events: 中介軟體送來的每筆原封存檔, event_id UNIQUE 做冪等.
- attendance_daily: 每天每學生一列, 只記 first_punch / last_punch / count.
  前台遲到早退自行用首末筆判斷, 後端不做時間窗分類.
- 卡號對應: 以 students.card_number 比對, 只處理 followup_status='在籍'.
  未知卡 / 非在籍不建 daily, 只留 raw (unknown 時連 raw 也不留, 直接 404 COUNT).
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    # 正規化後的比對鍵: 低 32 bits 大端 HEX 8 碼 (如 FD6374F6), 見 attendance_service.canonical_low32_hex
    card_key: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receiver_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    student = relationship("Student")


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
