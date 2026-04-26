"""Honor roll router."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.honor import HonorListResponse, HonorResponse
from app.models.honor import Honor
from sqlalchemy import select

router = APIRouter(prefix="/honors", tags=["Honors"])


@router.get("", response_model=HonorListResponse)
async def list_honors(
    year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Honor).order_by(Honor.display_order)
    if year:
        query = query.where(Honor.year == year)
    result = await db.execute(query)
    honors = result.scalars().all()
    return {"total": len(honors), "honors": honors}


@router.get("/years", response_model=list[int])
async def get_years(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Honor.year).distinct().order_by(Honor.year.desc()))
    return [row[0] for row in result.all()]