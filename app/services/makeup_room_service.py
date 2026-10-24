"""補課教室 service：教室／時段 CRUD 與名額計算。

名額規則（家長選課與老師核准都套用）：
    同一間教室 + 同一天 + 同一個開始時間，已排補課數 < capacity 才可補課。
"""

from datetime import date, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.branch import Branch
from app.models.makeup import MakeupClass
from app.models.makeup_room import MakeupRoom, MakeupRoomSlot
from app.models.student import Student
from app.utils.exceptions import ConflictException, NotFoundException, ValidationException

# 一次最多展開幾天的可補課場次
MAX_OPTION_DAYS = 120
# 沒帶日期時，預設往後看幾天
DEFAULT_OPTION_DAYS = 60

WEEKDAY_LABELS = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}

# 不列入名額計算的補課狀態
_INACTIVE_MAKEUP_STATUS = ("cancelled", "canceled")


def parse_hhmm(value: object) -> time | None:
    """接受 "18:00" 或 "1800"，回傳 time；無法解析回 None。"""
    if value is None:
        return None
    raw = str(value).strip().replace("：", ":")
    if not raw:
        return None
    try:
        if ":" in raw:
            hour, minute = raw.split(":", 1)
            return time(int(hour), int(minute))
        if len(raw) == 4 and raw.isdigit():
            return time(int(raw[:2]), int(raw[2:]))
    except ValueError:
        return None
    return None


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


# ── 名額計算 ──

async def _booked_map(
    db: AsyncSession, room_ids: list[int], day_from: date, day_to: date
) -> dict[tuple[int, date, time], int]:
    """回傳 {(room_id, 日期, 開始時間): 已排補課數}。"""
    if not room_ids:
        return {}
    rows = (
        await db.execute(
            select(
                MakeupClass.room_id,
                MakeupClass.makeup_date,
                MakeupClass.start_time,
                func.count(),
            )
            .where(
                MakeupClass.room_id.in_(room_ids),
                MakeupClass.makeup_date >= day_from,
                MakeupClass.makeup_date <= day_to,
                MakeupClass.status.notin_(_INACTIVE_MAKEUP_STATUS),
            )
            .group_by(MakeupClass.room_id, MakeupClass.makeup_date, MakeupClass.start_time)
        )
    ).all()
    return {(row[0], row[1], row[2]): row[3] for row in rows}


async def count_booked(
    db: AsyncSession, room_id: int, day: date, start_time: time
) -> int:
    """某間教室、某天、某個開始時間，已排定的補課人數。"""
    return (
        await db.execute(
            select(func.count())
            .select_from(MakeupClass)
            .where(
                MakeupClass.room_id == room_id,
                MakeupClass.makeup_date == day,
                MakeupClass.start_time == start_time,
                MakeupClass.status.notin_(_INACTIVE_MAKEUP_STATUS),
            )
        )
    ).scalar_one()


async def ensure_seat_available(
    db: AsyncSession, room: MakeupRoom, day: date, start_time: time
) -> None:
    """沒有空位就擋下來（409，前端可直接顯示訊息）。"""
    booked = await count_booked(db, room.id, day, start_time)
    if booked >= room.capacity:
        raise ConflictException(
            f"「{room.display_name}」{_hhmm(start_time)} 場次已滿"
            f"（{room.capacity} 人），請改選其他時段"
        )


# ── 教室查詢 ──

async def get_room(db: AsyncSession, room_id: int) -> MakeupRoom:
    result = await db.execute(
        select(MakeupRoom)
        .where(MakeupRoom.id == room_id)
        .options(selectinload(MakeupRoom.slots), selectinload(MakeupRoom.branch))
    )
    room = result.scalar_one_or_none()
    if not room:
        raise NotFoundException("Makeup room")
    return room


def _room_dict(
    room: MakeupRoom, booked: dict[tuple[int, date, time], int], today: date
) -> dict:
    today_weekday = today.isoweekday()
    today_booked = 0
    slots: list[dict] = []
    for slot in room.slots:
        is_today = slot.is_active and slot.day_of_week == today_weekday
        count = booked.get((room.id, today, slot.start_time), 0) if is_today else 0
        if is_today:
            today_booked += count
        slots.append(
            {
                "id": slot.id,
                "day_of_week": slot.day_of_week,
                "start_time": _hhmm(slot.start_time),
                "end_time": _hhmm(slot.end_time),
                "is_active": slot.is_active,
                "is_today": is_today,
                "today_booked": count,
                "today_seats_left": max(room.capacity - count, 0) if is_today else None,
            }
        )
    return {
        "id": room.id,
        "branch_id": room.branch_id,
        "branch_name": room.branch.name if room.branch else None,
        "code": room.code,
        "name": room.name,
        "display_name": room.display_name,
        "capacity": room.capacity,
        "is_active": room.is_active,
        "display_order": room.display_order,
        "notes": room.notes,
        "slots": slots,
        "today_booked": today_booked,
    }


async def room_payload(db: AsyncSession, room_id: int) -> dict:
    """單一教室的完整資料（含今日剩餘），給 CRUD 回應使用。"""
    room = await get_room(db, room_id)
    today = date.today()
    booked = await _booked_map(db, [room.id], today, today)
    return _room_dict(room, booked, today)


async def list_rooms(
    db: AsyncSession, branch_id: int | None = None, include_inactive: bool = True
) -> list[dict]:
    stmt = (
        select(MakeupRoom)
        .options(selectinload(MakeupRoom.slots), selectinload(MakeupRoom.branch))
        .order_by(MakeupRoom.display_order, MakeupRoom.id)
    )
    if branch_id is not None:
        stmt = stmt.where(MakeupRoom.branch_id == branch_id)
    if not include_inactive:
        stmt = stmt.where(MakeupRoom.is_active == True)  # noqa: E712
    rooms = (await db.execute(stmt)).scalars().all()
    today = date.today()
    booked = await _booked_map(db, [r.id for r in rooms], today, today)
    return [_room_dict(room, booked, today) for room in rooms]


# ── 教室 CRUD ──

async def _ensure_code_unique(
    db: AsyncSession, code: str, branch_id: int | None, exclude_id: int | None = None
) -> None:
    stmt = select(MakeupRoom.id).where(MakeupRoom.code == code.strip())
    if branch_id is None:
        stmt = stmt.where(MakeupRoom.branch_id.is_(None))
    else:
        stmt = stmt.where(MakeupRoom.branch_id == branch_id)
    if exclude_id is not None:
        stmt = stmt.where(MakeupRoom.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise ConflictException(f"這個分校已經有「{code.strip()}」教室了")


async def create_room(db: AsyncSession, data: dict) -> MakeupRoom:
    payload = dict(data)
    slots = payload.pop("slots", None) or []
    branch_id = payload.get("branch_id")
    if branch_id is not None and not await db.get(Branch, branch_id):
        raise NotFoundException("Branch")
    payload["code"] = payload["code"].strip()
    await _ensure_code_unique(db, payload["code"], branch_id)

    room = MakeupRoom(**payload)
    db.add(room)
    await db.flush()
    for slot_data in slots:
        await _add_slot(db, room, slot_data)
    await db.flush()
    return await get_room(db, room.id)


async def update_room(db: AsyncSession, room_id: int, data: dict) -> MakeupRoom:
    room = await get_room(db, room_id)
    payload = dict(data)
    if "branch_id" in payload and payload["branch_id"] is not None:
        if not await db.get(Branch, payload["branch_id"]):
            raise NotFoundException("Branch")
    if payload.get("code"):
        payload["code"] = payload["code"].strip()
        await _ensure_code_unique(
            db,
            payload["code"],
            payload.get("branch_id", room.branch_id),
            exclude_id=room.id,
        )
    for key, value in payload.items():
        if value is not None:
            setattr(room, key, value)
    await db.flush()
    return await get_room(db, room.id)


async def delete_room(db: AsyncSession, room_id: int) -> dict:
    """沒有未來補課就真的刪除；有紀錄則改為停用（保留歷史）。"""
    room = await get_room(db, room_id)
    future = (
        await db.execute(
            select(func.count())
            .select_from(MakeupClass)
            .where(
                MakeupClass.room_id == room.id,
                MakeupClass.makeup_date >= date.today(),
                MakeupClass.status.notin_(_INACTIVE_MAKEUP_STATUS),
            )
        )
    ).scalar_one()
    if future:
        room.is_active = False
        for slot in room.slots:
            slot.is_active = False
        await db.flush()
        return {"deleted": False, "message": "此教室已有補課紀錄，已改為停用（歷史資料保留）"}
    await db.delete(room)
    await db.flush()
    return {"deleted": True, "message": "補課教室已刪除"}


# ── 時段 CRUD ──

def _validate_slot_times(start: time, end: time) -> None:
    if end <= start:
        raise ValidationException("時段結束時間必須晚於開始時間")


async def _add_slot(db: AsyncSession, room: MakeupRoom, data: dict) -> MakeupRoomSlot:
    start = parse_hhmm(data.get("start_time"))
    end = parse_hhmm(data.get("end_time"))
    if start is None or end is None:
        raise ValidationException("請填寫正確的開始與結束時間")
    _validate_slot_times(start, end)
    await _ensure_slot_free(db, room.id, data["day_of_week"], start, end)

    slot = MakeupRoomSlot(
        room_id=room.id,
        day_of_week=data["day_of_week"],
        start_time=start,
        end_time=end,
        is_active=data.get("is_active", True),
    )
    db.add(slot)
    await db.flush()
    return slot


async def _ensure_slot_free(
    db: AsyncSession,
    room_id: int,
    day_of_week: int,
    start: time,
    end: time,
    exclude_id: int | None = None,
) -> None:
    """同一間教室、同一天，時段不可重疊。"""
    stmt = select(MakeupRoomSlot.id).where(
        MakeupRoomSlot.room_id == room_id,
        MakeupRoomSlot.day_of_week == day_of_week,
        MakeupRoomSlot.start_time < end,
        MakeupRoomSlot.end_time > start,
    )
    if exclude_id is not None:
        stmt = stmt.where(MakeupRoomSlot.id != exclude_id)
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        weekday = WEEKDAY_LABELS.get(day_of_week, day_of_week)
        raise ConflictException(f"週{weekday} 這個時段和既有時段重疊了")


async def create_slot(db: AsyncSession, room_id: int, data: dict) -> MakeupRoom:
    room = await get_room(db, room_id)
    await _add_slot(db, room, data)
    await db.flush()
    return await get_room(db, room.id)


async def update_slot(
    db: AsyncSession, room_id: int, slot_id: int, data: dict
) -> MakeupRoom:
    result = await db.execute(
        select(MakeupRoomSlot).where(
            MakeupRoomSlot.id == slot_id, MakeupRoomSlot.room_id == room_id
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise NotFoundException("Makeup room slot")

    day_of_week = data.get("day_of_week") or slot.day_of_week
    start = parse_hhmm(data.get("start_time")) or slot.start_time
    end = parse_hhmm(data.get("end_time")) or slot.end_time
    _validate_slot_times(start, end)
    await _ensure_slot_free(db, room_id, day_of_week, start, end, exclude_id=slot.id)

    slot.day_of_week = day_of_week
    slot.start_time = start
    slot.end_time = end
    if data.get("is_active") is not None:
        slot.is_active = data["is_active"]
    await db.flush()
    return await get_room(db, room_id)


async def delete_slot(db: AsyncSession, room_id: int, slot_id: int) -> dict:
    result = await db.execute(
        select(MakeupRoomSlot).where(
            MakeupRoomSlot.id == slot_id, MakeupRoomSlot.room_id == room_id
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise NotFoundException("Makeup room slot")

    future = (
        await db.execute(
            select(func.count())
            .select_from(MakeupClass)
            .where(
                MakeupClass.room_id == room_id,
                MakeupClass.start_time == slot.start_time,
                MakeupClass.makeup_date >= date.today(),
                MakeupClass.status.notin_(_INACTIVE_MAKEUP_STATUS),
            )
        )
    ).scalar_one()
    if future:
        slot.is_active = False
        await db.flush()
        return {"deleted": False, "message": "此時段已有補課紀錄，已改為停用"}
    await db.delete(slot)
    await db.flush()
    return {"deleted": True, "message": "時段已刪除"}


# ── 家長端：可補課場次 ──

async def resolve_requested_slot(
    db: AsyncSession, room_id: int, day: date, start: time, end: time
) -> tuple[MakeupRoom, MakeupRoomSlot]:
    """驗證家長選的教室／日期／時段確實存在且開放。"""
    room = await get_room(db, room_id)
    if not room.is_active:
        raise ValidationException("這間補課教室已停用，請重新選擇")

    weekday = day.isoweekday()
    slot = next(
        (
            s
            for s in room.slots
            if s.is_active and s.day_of_week == weekday and s.start_time == start
        ),
        None,
    )
    if slot is None:
        raise ValidationException("所選時段不是這間教室的開放時段，請重新選擇")
    if slot.end_time != end:
        raise ValidationException("所選時段的結束時間不符，請重新選擇")
    return room, slot


async def list_options(
    db: AsyncSession,
    student: Student,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """列出學生所屬分校的補課教室場次（含剩餘座位；已滿的仍回傳，前端可灰掉）。"""
    today = date.today()
    start_day = max(date_from or today, today)
    end_day = date_to or (start_day + timedelta(days=DEFAULT_OPTION_DAYS))
    if end_day < start_day:
        raise ValidationException("查詢區間不正確")
    if (end_day - start_day).days > MAX_OPTION_DAYS:
        end_day = start_day + timedelta(days=MAX_OPTION_DAYS)

    stmt = (
        select(MakeupRoom)
        .where(MakeupRoom.is_active == True)  # noqa: E712
        .options(selectinload(MakeupRoom.slots), selectinload(MakeupRoom.branch))
        .order_by(MakeupRoom.display_order, MakeupRoom.id)
    )
    # 學生沒有分校資料時，顯示全部教室（避免完全看不到選項）
    if student.branch_id is not None:
        stmt = stmt.where(MakeupRoom.branch_id == student.branch_id)
    rooms = (await db.execute(stmt)).scalars().all()
    if not rooms:
        return []

    booked = await _booked_map(db, [r.id for r in rooms], start_day, end_day)
    options: list[dict] = []
    day = start_day
    while day <= end_day:
        weekday = day.isoweekday()
        for room in rooms:
            for slot in room.slots:
                if not slot.is_active or slot.day_of_week != weekday:
                    continue
                used = booked.get((room.id, day, slot.start_time), 0)
                seats_left = max(room.capacity - used, 0)
                options.append(
                    {
                        "date": day,
                        "weekday": weekday,
                        "start_time": _hhmm(slot.start_time),
                        "end_time": _hhmm(slot.end_time),
                        "room_id": room.id,
                        "room_code": room.code,
                        "room_name": room.display_name,
                        "branch_name": room.branch.name if room.branch else None,
                        "capacity": room.capacity,
                        "booked": used,
                        "seats_left": seats_left,
                        "full": seats_left <= 0,
                        # 相容第一版前端欄位
                        "classroom": room.display_name,
                        "enrolled": used,
                        "makeup_count": used,
                    }
                )
        day += timedelta(days=1)

    options.sort(key=lambda o: (o["date"], o["start_time"], o["room_code"]))
    return options
