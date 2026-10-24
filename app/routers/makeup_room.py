"""補課教室（makeup room）admin router。

補課教室是「播放課程影片複習」的空間；家長請假時依剩餘座位選教室時段。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.user import User
from app.schemas.makeup_room import (
    MakeupRoomCreateRequest,
    MakeupRoomResponse,
    MakeupRoomSlotCreateRequest,
    MakeupRoomSlotUpdateRequest,
    MakeupRoomUpdateRequest,
)
from app.services import makeup_room_service

router = APIRouter(prefix="/admin/makeup-rooms", tags=["admin-makeup-rooms"])


@router.get("", response_model=list[MakeupRoomResponse])
async def list_makeup_rooms(
    branch_id: int | None = Query(None),
    include_inactive: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    """教室清單（含固定時段與今日剩餘座位）。"""
    return await makeup_room_service.list_rooms(db, branch_id, include_inactive)


@router.post("", response_model=MakeupRoomResponse, status_code=201)
async def create_makeup_room(
    data: MakeupRoomCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    room = await makeup_room_service.create_room(db, data.model_dump())
    await db.commit()
    return await makeup_room_service.room_payload(db, room.id)


@router.put("/{room_id}", response_model=MakeupRoomResponse)
async def update_makeup_room(
    room_id: int,
    data: MakeupRoomUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    await makeup_room_service.update_room(db, room_id, data.model_dump())
    await db.commit()
    return await makeup_room_service.room_payload(db, room_id)


@router.delete("/{room_id}")
async def delete_makeup_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await makeup_room_service.delete_room(db, room_id)
    await db.commit()
    return {"success": True, **result}


@router.post("/{room_id}/slots", response_model=MakeupRoomResponse, status_code=201)
async def create_makeup_room_slot(
    room_id: int,
    data: MakeupRoomSlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    await makeup_room_service.create_slot(db, room_id, data.model_dump())
    await db.commit()
    return await makeup_room_service.room_payload(db, room_id)


@router.put("/{room_id}/slots/{slot_id}", response_model=MakeupRoomResponse)
async def update_makeup_room_slot(
    room_id: int,
    slot_id: int,
    data: MakeupRoomSlotUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    await makeup_room_service.update_slot(db, room_id, slot_id, data.model_dump())
    await db.commit()
    return await makeup_room_service.room_payload(db, room_id)


@router.delete("/{room_id}/slots/{slot_id}")
async def delete_makeup_room_slot(
    room_id: int,
    slot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await makeup_room_service.delete_slot(db, room_id, slot_id)
    await db.commit()
    return {"success": True, **result}
