"""補課教室（makeup room）schemas."""

from pydantic import BaseModel, Field

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class MakeupRoomSlotResponse(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    is_active: bool = True
    # 今天剛好是這個時段時，順便回傳今日已排人數與剩餘座位
    is_today: bool = False
    today_booked: int = 0
    today_seats_left: int | None = None


class MakeupRoomSlotCreateRequest(BaseModel):
    day_of_week: int = Field(ge=1, le=7)
    start_time: str = Field(pattern=_HHMM)
    end_time: str = Field(pattern=_HHMM)
    is_active: bool = True


class MakeupRoomSlotUpdateRequest(BaseModel):
    day_of_week: int | None = Field(default=None, ge=1, le=7)
    start_time: str | None = Field(default=None, pattern=_HHMM)
    end_time: str | None = Field(default=None, pattern=_HHMM)
    is_active: bool | None = None


class MakeupRoomResponse(BaseModel):
    id: int
    branch_id: int | None = None
    branch_name: str | None = None
    code: str
    name: str | None = None
    display_name: str
    capacity: int
    is_active: bool = True
    display_order: int = 0
    notes: str | None = None
    slots: list[MakeupRoomSlotResponse] = []
    # 今日（所有時段加總）已排補課人數
    today_booked: int = 0


class MakeupRoomCreateRequest(BaseModel):
    branch_id: int | None = None
    code: str = Field(min_length=1, max_length=20)
    name: str | None = None
    capacity: int = Field(default=12, ge=1, le=500)
    is_active: bool = True
    display_order: int = 0
    notes: str | None = None
    # 可一併建立固定時段
    slots: list[MakeupRoomSlotCreateRequest] = []


class MakeupRoomUpdateRequest(BaseModel):
    branch_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = None
    capacity: int | None = Field(default=None, ge=1, le=500)
    is_active: bool | None = None
    display_order: int | None = None
    notes: str | None = None
