"""Makeup room（補課教室）models.

補課教室是「播放課程影片複習」的空間，容量只看座位數；
教室與課程無關，同一間教室可以播放不同課程的影片。
"""

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MakeupRoom(Base):
    """補課教室（例：補A，可容納 12 人）。"""

    __tablename__ = "makeup_rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("branches.id"), nullable=True)
    # 教室編號，家長端會看到（例：補A）
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    # 顯示名稱（選填；沒填就用編號）
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    branch = relationship("Branch")
    slots = relationship(
        "MakeupRoomSlot",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="MakeupRoomSlot.day_of_week, MakeupRoomSlot.start_time",
    )
    makeups = relationship("MakeupClass", back_populates="room")

    @property
    def display_name(self) -> str:
        return self.name or self.code


class MakeupRoomSlot(Base):
    """教室的每週固定時段（例：補A 每週六 14:00-16:00）。"""

    __tablename__ = "makeup_room_slots"
    __table_args__ = (
        UniqueConstraint("room_id", "day_of_week", "start_time", name="uq_makeup_room_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("makeup_rooms.id"), nullable=False
    )
    # 1=週一 … 7=週日（與 courses.days_of_week 慣例一致）
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    room = relationship("MakeupRoom", back_populates="slots")
