from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


# ── Response schemas ──────────────────────────────────────────────

class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    total_pages: int


class TradeItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    action: str
    exchange: str
    session: str
    price: int
    quantity: int
    amount: int
    fee: int
    buy_price: Optional[int] = None
    pnl: Optional[int] = None
    pnl_pct: Optional[float] = None
    signal_score_id: Optional[int] = None
    sell_reason: Optional[str] = None
    memo: Optional[str] = None
    order_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    meta: PaginationMeta
    data: list[TradeItem]


class SessionBreakdown(BaseModel):
    session: str
    trades: int
    wins: int
    losses: int
    pnl: int


class BestWorstTrade(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    pnl: int
    pnl_pct: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeStatsResponse(BaseModel):
    total_trades: int
    total_sells: int
    wins: int
    losses: int
    win_rate: Optional[float] = None
    total_pnl: int
    avg_pnl: Optional[float] = None
    best_trade: Optional[BestWorstTrade] = None
    worst_trade: Optional[BestWorstTrade] = None
    by_session: list[SessionBreakdown]


# ── Helpers ───────────────────────────────────────────────────────

def _pagination_meta(page: int, size: int, total: int) -> PaginationMeta:
    return PaginationMeta(
        page=page,
        size=size,
        total=total,
        total_pages=(total + size - 1) // size if size > 0 else 0,
    )


def _apply_filters(
    stmt,
    *,
    action: Optional[str],
    session: Optional[str],
    exchange: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
):
    if action:
        stmt = stmt.where(Trade.action == action.upper())
    if session:
        stmt = stmt.where(Trade.session == session.upper())
    if exchange:
        stmt = stmt.where(Trade.exchange == exchange.upper())
    if date_from:
        stmt = stmt.where(func.date(Trade.created_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(Trade.created_at) <= date_to)
    return stmt


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/stats", response_model=TradeStatsResponse)
async def trade_stats(db: AsyncSession = Depends(get_db)):
    """전체 매매 통계 (반드시 /stats 를 /{id} 보다 위에 등록)"""
    total_q = select(func.count()).select_from(Trade)
    total_trades = (await db.execute(total_q)).scalar() or 0

    agg_q = (
        select(
            func.count().label("total_sells"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("wins"),
            func.sum(case((Trade.pnl <= 0, 1), else_=0)).label("losses"),
            func.coalesce(func.sum(Trade.pnl), 0).label("total_pnl"),
            func.avg(Trade.pnl).label("avg_pnl"),
        )
        .where(Trade.action == "SELL")
    )
    agg = (await db.execute(agg_q)).one()

    total_sells = int(agg.total_sells)
    wins = int(agg.wins or 0)
    losses = int(agg.losses or 0)
    total_pnl = int(agg.total_pnl)
    avg_pnl = round(float(agg.avg_pnl), 0) if agg.avg_pnl else None
    win_rate = round(wins / total_sells * 100, 1) if total_sells > 0 else None

    best_q = (
        select(Trade)
        .where(Trade.action == "SELL", Trade.pnl.isnot(None))
        .order_by(desc(Trade.pnl))
        .limit(1)
    )
    worst_q = (
        select(Trade)
        .where(Trade.action == "SELL", Trade.pnl.isnot(None))
        .order_by(Trade.pnl)
        .limit(1)
    )
    best_row = (await db.execute(best_q)).scalar_one_or_none()
    worst_row = (await db.execute(worst_q)).scalar_one_or_none()

    session_q = (
        select(
            Trade.session,
            func.count().label("trades"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("wins"),
            func.sum(case((Trade.pnl <= 0, 1), else_=0)).label("losses"),
            func.coalesce(func.sum(Trade.pnl), 0).label("pnl"),
        )
        .where(Trade.action == "SELL")
        .group_by(Trade.session)
    )
    session_rows = (await db.execute(session_q)).all()

    return TradeStatsResponse(
        total_trades=total_trades,
        total_sells=total_sells,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_pnl=avg_pnl,
        best_trade=BestWorstTrade.model_validate(best_row) if best_row else None,
        worst_trade=BestWorstTrade.model_validate(worst_row) if worst_row else None,
        by_session=[
            SessionBreakdown(
                session=r.session,
                trades=int(r.trades),
                wins=int(r.wins or 0),
                losses=int(r.losses or 0),
                pnl=int(r.pnl),
            )
            for r in session_rows
        ],
    )


@router.get("/", response_model=TradeListResponse)
async def list_trades(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, description="BUY / SELL"),
    session: Optional[str] = Query(None, description="PRE_MARKET / REGULAR / CLOSING / AFTER_MARKET"),
    exchange: Optional[str] = Query(None, description="KRX / NXT / SOR"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    base = select(Trade)
    count_q = select(func.count()).select_from(Trade)

    base = _apply_filters(base, action=action, session=session, exchange=exchange, date_from=date_from, date_to=date_to)
    count_q = _apply_filters(count_q, action=action, session=session, exchange=exchange, date_from=date_from, date_to=date_to)

    total = (await db.execute(count_q)).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(desc(Trade.created_at))
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()

    return TradeListResponse(
        meta=_pagination_meta(page, size, total),
        data=[TradeItem.model_validate(r) for r in rows],
    )


@router.get("/{trade_id}", response_model=TradeItem)
async def get_trade_detail(trade_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(Trade).where(Trade.id == trade_id))
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="거래 내역을 찾을 수 없습니다")

    return TradeItem.model_validate(row)
