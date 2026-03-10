from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Position, Trade

router = APIRouter(prefix="/api/positions", tags=["positions"])


# ── Response schemas ──────────────────────────────────────────────

class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    total_pages: int


class PositionItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    exchange: str
    session: str
    quantity: int
    avg_price: int
    current_price: int
    unrealized_pnl: int
    unrealized_pnl_pct: float
    atr_value: Optional[float] = None
    stop_loss_price: Optional[int] = None
    trailing_stop_price: Optional[int] = None
    highest_price: Optional[int] = None
    signal_score_id: Optional[int] = None
    buy_trade_id: Optional[int] = None
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OpenPositionsResponse(BaseModel):
    total: int
    total_unrealized_pnl: int
    data: list[PositionItem]


class PositionHistoryResponse(BaseModel):
    meta: PaginationMeta
    data: list[PositionItem]


class LinkedTrade(BaseModel):
    id: int
    action: str
    exchange: str
    session: str
    price: int
    quantity: int
    amount: int
    fee: int
    pnl: Optional[int] = None
    pnl_pct: Optional[float] = None
    sell_reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionDetailResponse(PositionItem):
    linked_trades: list[LinkedTrade]


# ── Helpers ───────────────────────────────────────────────────────

def _pagination_meta(page: int, size: int, total: int) -> PaginationMeta:
    return PaginationMeta(
        page=page,
        size=size,
        total=total,
        total_pages=(total + size - 1) // size if size > 0 else 0,
    )


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/", response_model=OpenPositionsResponse)
async def open_positions(db: AsyncSession = Depends(get_db)):
    q = (
        select(Position)
        .where(Position.status == "OPEN")
        .order_by(desc(Position.opened_at))
    )
    rows = (await db.execute(q)).scalars().all()

    total_unrealized = sum(r.unrealized_pnl for r in rows)

    return OpenPositionsResponse(
        total=len(rows),
        total_unrealized_pnl=total_unrealized,
        data=[PositionItem.model_validate(r) for r in rows],
    )


@router.get("/history", response_model=PositionHistoryResponse)
async def position_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count()).select_from(Position).where(
        Position.status == "CLOSED",
    )
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Position)
        .where(Position.status == "CLOSED")
        .order_by(desc(Position.closed_at))
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = (await db.execute(q)).scalars().all()

    return PositionHistoryResponse(
        meta=_pagination_meta(page, size, total),
        data=[PositionItem.model_validate(r) for r in rows],
    )


@router.get("/{position_id}", response_model=PositionDetailResponse)
async def get_position_detail(position_id: int, db: AsyncSession = Depends(get_db)):
    pos = (
        await db.execute(select(Position).where(Position.id == position_id))
    ).scalar_one_or_none()

    if not pos:
        raise HTTPException(status_code=404, detail="포지션을 찾을 수 없습니다")

    trades_q = (
        select(Trade)
        .where(
            Trade.stock_code == pos.stock_code,
            Trade.signal_score_id == pos.signal_score_id,
        )
        .order_by(Trade.created_at)
    )
    linked = (await db.execute(trades_q)).scalars().all()

    pos_data = PositionItem.model_validate(pos).model_dump()
    pos_data["linked_trades"] = [LinkedTrade.model_validate(t) for t in linked]

    return PositionDetailResponse(**pos_data)
