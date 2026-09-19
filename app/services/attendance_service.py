"""Attendance service - punch clock ingest + daily aggregation.

卡號正規化 (對應使用者實測):
- 打卡機送 site:card 十進位, 如 "64867:29942" (= hi 0xFD63, lo 0x74F6)
- 同一張悠遊卡用 NFC apk 讀到 "F6:74:63:FD", 即低 4 bytes 反轉 (little-endian)
  FD 63 74 F6 (大端, SOYAL) <-> F6 74 63 FD (小端, NFC app)
- 因此比對一律換算為 low32 (低 32 bits 整數), 並同時接受大小端兩種解讀.
  canonical card_key = f"{low32:08X}" (大端 8 碼, 如 FD6374F6)
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceDaily, PunchRawEvent
from app.models.student import Student
from app.schemas.punch import GcpPunchEvent

logger = logging.getLogger(__name__)

TAIPEI_TZ = timezone(timedelta(hours=8))


def _reverse_bytes_hex(hex_str: str) -> str | None:
    """反轉 hex 字串的位元組順序, 如 FD6374F6 -> F67463FD."""
    try:
        b = bytes.fromhex(hex_str)
        return b[::-1].hex().upper()
    except ValueError:
        return None


def incoming_low32(uid_hex: str, uid_decimal: int | None,
                   hi: int | None, lo: int | None) -> int | None:
    """從 receiver 送來的卡片欄位算出 low32, 優先 hi/lo."""
    if hi is not None and lo is not None:
        try:
            return ((int(hi) & 0xFFFF) << 16) | (int(lo) & 0xFFFF)
        except (TypeError, ValueError):
            pass
    if uid_hex:
        h = uid_hex.strip().upper()
        if h:
            try:
                return int(h[-8:], 16) & 0xFFFFFFFF
            except ValueError:
                pass
    if uid_decimal is not None:
        try:
            return int(uid_decimal) & 0xFFFFFFFF
        except (TypeError, ValueError):
            pass
    return None


def stored_card_candidates(card_number: str | None) -> set[int]:
    """把 DB 裡既有的 card_number (各種格式) 換算為可能的 low32 集合.

    支援格式:
    - "64867:29942" (site:card 十進位)
    - "00000000FD6374F6" / "FD6374F6" (hex, 含大小寫)
    - "F6:74:63:FD" (NFC app 小端 hex bytes) -> 同時試大端/小端解讀
    - 純十進位字串
    """
    out: set[int] = set()
    if not card_number:
        return out
    s = card_number.strip()
    if not s:
        return out

    if ":" in s:
        parts = [p.strip() for p in s.split(":")]
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            try:
                out.add(((int(parts[0]) & 0xFFFF) << 16) | (int(parts[1]) & 0xFFFF))
                return out
            except ValueError:
                pass
        # hex bytes (如 F6:74:63:FD), 大小端都試
        try:
            raw = bytes.fromhex("".join(parts))
            if len(raw) in (4, 7, 8):
                out.add(int.from_bytes(raw[-4:], "big") & 0xFFFFFFFF)
                out.add(int.from_bytes(raw[-4:], "little") & 0xFFFFFFFF)
                return out
        except ValueError:
            pass
        return out

    if s.isdigit() and not any(c in "ABCDEFabcdef" for c in s):
        # 純十進位: 可能是 uid_decimal 或 card code; 取低 32 bits
        try:
            out.add(int(s) & 0xFFFFFFFF)
        except ValueError:
            pass
        return out

    # hex 字串
    h = s.upper().replace(" ", "")
    if all(c in "0123456789ABCDEF" for c in h) and len(h) >= 4:
        try:
            val = int(h[-8:], 16) & 0xFFFFFFFF
            out.add(val)
            rev = _reverse_bytes_hex(h[-8:] if len(h) >= 8 else h)
            if rev:
                out.add(int(rev, 16) & 0xFFFFFFFF)
        except ValueError:
            pass
    return out


def canonical_key(low32: int) -> str:
    return f"{low32 & 0xFFFFFFFF:08X}"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        return dt
    except ValueError:
        return None


async def _build_card_map(db: AsyncSession) -> dict[int, Student]:
    """只載入有卡號的學生, low32 -> Student (含大小端相容)."""
    result = await db.execute(
        select(Student).where(Student.card_number.isnot(None))
    )
    card_map: dict[int, Student] = {}
    for st in result.scalars().all():
        for cand in stored_card_candidates(st.card_number):
            if cand not in card_map:
                card_map[cand] = st
            else:
                logger.warning("重複卡號 low32=%08X: student %s 與 %s", cand, card_map[cand].id, st.id)
    return card_map


async def ingest_events(db: AsyncSession, events: list[GcpPunchEvent]) -> list[dict]:
    """寫入一批 punch events, 回傳每筆結果 dict."""
    card_map = await _build_card_map(db)
    results: list[dict] = []

    for ev in events:
        hi = ev.card.card_number_hi if ev.card.card_number_hi is not None else ev.card.site_code
        lo = ev.card.card_number_lo if ev.card.card_number_lo is not None else ev.card.card_code
        low32 = incoming_low32(ev.card.uid_hex, ev.card.uid_decimal, hi, lo)
        occurred = parse_dt(ev.occurred_at)
        received = parse_dt(ev.received_at)

        if low32 is None:
            results.append({"event_id": ev.event_id, "status": "unknown_card",
                            "student_id": None, "student_name": None})
            continue

        student = card_map.get(low32)
        if student is None:
            # 未知卡: 不存 raw, 前台不處理 (receiver 收到 200 + status, 不重送)
            results.append({"event_id": ev.event_id, "status": "unknown_card",
                            "student_id": None, "student_name": None})
            continue
        if student.followup_status != "在籍":
            results.append({"event_id": ev.event_id, "status": "inactive",
                            "student_id": student.id, "student_name": student.student_name})
            continue

        # 冪等: event_id 重複直接回 duplicate
        dup = await db.execute(
            select(PunchRawEvent.id).where(PunchRawEvent.event_id == ev.event_id)
        )
        if dup.scalar_one_or_none() is not None:
            results.append({"event_id": ev.event_id, "status": "duplicate",
                            "student_id": student.id, "student_name": student.student_name})
            continue

        raw = PunchRawEvent(
            event_id=ev.event_id,
            student_id=student.id,
            uid_hex=ev.card.uid_hex.upper() if ev.card.uid_hex else None,
            uid_decimal=ev.card.uid_decimal,
            card_hi=hi, card_lo=lo,
            card_key=canonical_key(low32),
            occurred_at=occurred,
            received_at=received,
            node_id=ev.device.node_id,
            device_ip=ev.device.ip or None,
            receiver_id=ev.ingested_by.receiver_id if ev.ingested_by else None,
            event_code=ev.event.event_code,
            raw_message=ev.raw_message or None,
        )
        db.add(raw)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            results.append({"event_id": ev.event_id, "status": "duplicate",
                            "student_id": student.id, "student_name": student.student_name})
            continue

        # 日彙總: punch_date 取 occurred_at 的台北日期
        day = (occurred.astimezone(TAIPEI_TZ) if occurred else datetime.now(TAIPEI_TZ)).date()
        daily_res = await db.execute(
            select(AttendanceDaily).where(
                AttendanceDaily.student_id == student.id,
                AttendanceDaily.punch_date == day,
            )
        )
        daily = daily_res.scalar_one_or_none()
        if daily is None:
            daily = AttendanceDaily(
                student_id=student.id, punch_date=day,
                first_punch=occurred, last_punch=occurred, punch_count=1,
                device_ip=ev.device.ip or None,
            )
            db.add(daily)
        else:
            if occurred:
                if daily.first_punch is None or occurred < daily.first_punch:
                    daily.first_punch = occurred
                if daily.last_punch is None or occurred > daily.last_punch:
                    daily.last_punch = occurred
            daily.punch_count = (daily.punch_count or 0) + 1

        results.append({"event_id": ev.event_id, "status": "ok",
                        "student_id": student.id, "student_name": student.student_name})

    await db.flush()
    return results
