"""About Card router for admin management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import require_teacher_or_admin
from app.models.about_card import AboutCard
from app.models.user import User
from app.schemas.about_card import (
    AboutCardCreateRequest,
    AboutCardListResponse,
    AboutCardReorderRequest,
    AboutCardResponse,
    AboutCardUpdateRequest,
)

router = APIRouter(prefix="/about-cards", tags=["About Cards"])

MAX_CARDS = 5


@router.get("", response_model=AboutCardListResponse)
async def list_about_cards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AboutCard).where(AboutCard.is_active == True).order_by(AboutCard.display_order)
    )
    cards = result.scalars().all()
    return {"total": len(cards), "cards": cards}


@router.get("/all", response_model=AboutCardListResponse)
async def list_all_about_cards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AboutCard).order_by(AboutCard.display_order))
    cards = result.scalars().all()
    return {"total": len(cards), "cards": cards}


@router.get("/{card_id}", response_model=AboutCardResponse)
async def get_about_card(card_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AboutCard).where(AboutCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return card


@router.post("", response_model=AboutCardResponse, status_code=201)
async def create_about_card(
    data: AboutCardCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(AboutCard.id))
    existing_count = len(result.scalars().all())
    if existing_count >= MAX_CARDS:
        raise HTTPException(
            status_code=400,
            detail=f"已達到最大卡片數量上限 ({MAX_CARDS} 張)",
        )
    card = AboutCard(**data.model_dump())
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.put("/{card_id}", response_model=AboutCardResponse)
async def update_about_card(
    card_id: int,
    data: AboutCardUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(AboutCard).where(AboutCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(card, key, value)
    await db.commit()
    await db.refresh(card)
    return card


@router.put("/reorder")
async def reorder_about_cards(
    data: AboutCardReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    for idx, card_id in enumerate(data.order):
        result = await db.execute(select(AboutCard).where(AboutCard.id == card_id))
        card = result.scalar_one_or_none()
        if card:
            card.display_order = idx
    await db.commit()
    return {"success": True, "message": "排序已更新"}


@router.delete("/{card_id}")
async def delete_about_card(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher_or_admin),
):
    result = await db.execute(select(AboutCard).where(AboutCard.id == card_id))
    card = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    await db.delete(card)
    await db.commit()
    return {"success": True, "message": "已刪除"}