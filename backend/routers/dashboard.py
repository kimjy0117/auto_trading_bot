from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Trade, Position, DailySummary
from backend.services.session_manager import get_current_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ── Response schemas ──────────────────────────────────────────────

class SessionPnL(BaseModel):
    pre_market: int = 0
    regular: int = 0
    after_market: int = 0


class DashboardSummary(BaseModel):
    current_session: str
    total_pnl: int
    session_pnl: SessionPnL
    open_positions: int
    today_trades: int
    win_rate: Optional[float] = None


class DailyPnLItem(BaseModel):
    trade_date: date
    realized_pnl: int
    total_trades: int
    wins: int
    losses: int
    win_rate: Optional[float] = None
    pre_market_pnl: int = 0
    regular_pnl: int = 0
    after_market_pnl: int = 0
    max_drawdown: Optional[float] = None


class DailyPnLResponse(BaseModel):
    days: int
    data: list[DailyPnLItem]


class SessionPerformanceItem(BaseModel):
    session: str
    total_sells: int
    wins: int
    losses: int
    win_rate: Optional[float] = None
    total_pnl: int
    avg_pnl: Optional[float] = None
    avg_return_pct: Optional[float] = None


class SessionPerformanceResponse(BaseModel):
    data: list[SessionPerformanceItem]


class MonthlyPnLItem(BaseModel):
    year: int
    month: int
    realized_pnl: int
    total_trades: int
    wins: int
    losses: int
    win_rate: Optional[float] = None
    trading_days: int = 0


class MonthlyPnLResponse(BaseModel):
    year: int
    data: list[MonthlyPnLItem]


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    today = datetime.utcnow().date()

    daily_q = select(DailySummary).where(DailySummary.trade_date == today)
    daily_row = (await db.execute(daily_q)).scalar_one_or_none()

    open_pos_q = select(func.count()).select_from(Position).where(
        Position.status == "OPEN",
    )
    open_count = (await db.execute(open_pos_q)).scalar() or 0

    today_trades_q = select(func.count()).select_from(Trade).where(
        func.date(Trade.created_at) == today,
    )
    trade_count = (await db.execute(today_trades_q)).scalar() or 0

    if daily_row:
        total_pnl = daily_row.realized_pnl
        session_pnl = SessionPnL(
            pre_market=daily_row.pre_market_pnl,
            regular=daily_row.regular_pnl,
            after_market=daily_row.after_market_pnl,
        )
        win_rate = daily_row.win_rate
    else:
        sells_q = (
            select(
                func.coalesce(func.sum(Trade.pnl), 0).label("total_pnl"),
                func.count().label("sell_count"),
                func.sum(case((Trade.pnl > 0, 1), else_=0)).label("wins"),
            )
            .where(Trade.action == "SELL", func.date(Trade.created_at) == today)
        )
        sells_row = (await db.execute(sells_q)).one()
        total_pnl = int(sells_row.total_pnl)
        sell_count = int(sells_row.sell_count)
        wins = int(sells_row.wins or 0)
        win_rate = round(wins / sell_count * 100, 1) if sell_count > 0 else None

        pre_q = select(func.coalesce(func.sum(Trade.pnl), 0)).where(
            Trade.action == "SELL",
            Trade.session == "PRE_MARKET",
            func.date(Trade.created_at) == today,
        )
        reg_q = select(func.coalesce(func.sum(Trade.pnl), 0)).where(
            Trade.action == "SELL",
            Trade.session == "REGULAR",
            func.date(Trade.created_at) == today,
        )
        aft_q = select(func.coalesce(func.sum(Trade.pnl), 0)).where(
            Trade.action == "SELL",
            Trade.session.in_(["AFTER_MARKET", "CLOSING"]),
            func.date(Trade.created_at) == today,
        )
        pre_pnl = (await db.execute(pre_q)).scalar() or 0
        reg_pnl = (await db.execute(reg_q)).scalar() or 0
        aft_pnl = (await db.execute(aft_q)).scalar() or 0

        session_pnl = SessionPnL(
            pre_market=int(pre_pnl),
            regular=int(reg_pnl),
            after_market=int(aft_pnl),
        )

    return DashboardSummary(
        current_session=get_current_session().value,
        total_pnl=total_pnl,
        session_pnl=session_pnl,
        open_positions=open_count,
        today_trades=trade_count,
        win_rate=win_rate,
    )


@router.get("/daily-pnl", response_model=DailyPnLResponse)
async def daily_pnl(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(DailySummary)
        .order_by(desc(DailySummary.trade_date))
        .limit(days)
    )
    rows = (await db.execute(q)).scalars().all()

    data = [
        DailyPnLItem(
            trade_date=r.trade_date,
            realized_pnl=r.realized_pnl,
            total_trades=r.total_trades,
            wins=r.wins,
            losses=r.losses,
            win_rate=r.win_rate,
            pre_market_pnl=r.pre_market_pnl,
            regular_pnl=r.regular_pnl,
            after_market_pnl=r.after_market_pnl,
            max_drawdown=r.max_drawdown,
        )
        for r in rows
    ]

    return DailyPnLResponse(days=days, data=data)


@router.get("/session-performance", response_model=SessionPerformanceResponse)
async def session_performance(db: AsyncSession = Depends(get_db)):
    q = (
        select(
            Trade.session,
            func.count().label("total_sells"),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label("wins"),
            func.sum(case((Trade.pnl <= 0, 1), else_=0)).label("losses"),
            func.coalesce(func.sum(Trade.pnl), 0).label("total_pnl"),
            func.avg(Trade.pnl).label("avg_pnl"),
            func.avg(Trade.pnl_pct).label("avg_return_pct"),
        )
        .where(Trade.action == "SELL")
        .group_by(Trade.session)
    )
    rows = (await db.execute(q)).all()

    data = []
    for r in rows:
        total = int(r.total_sells)
        wins = int(r.wins or 0)
        losses = int(r.losses or 0)
        data.append(
            SessionPerformanceItem(
                session=r.session,
                total_sells=total,
                wins=wins,
                losses=losses,
                win_rate=round(wins / total * 100, 1) if total > 0 else None,
                total_pnl=int(r.total_pnl),
                avg_pnl=round(float(r.avg_pnl), 0) if r.avg_pnl else None,
                avg_return_pct=round(float(r.avg_return_pct), 2) if r.avg_return_pct else None,
            )
        )

    return SessionPerformanceResponse(data=data)


@router.get("/monthly-pnl", response_model=MonthlyPnLResponse)
async def monthly_pnl(
    year: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if year is None:
        year = datetime.utcnow().year

    q = (
        select(
            func.extract("month", DailySummary.trade_date).label("month"),
            func.sum(DailySummary.realized_pnl).label("realized_pnl"),
            func.sum(DailySummary.total_trades).label("total_trades"),
            func.sum(DailySummary.wins).label("wins"),
            func.sum(DailySummary.losses).label("losses"),
            func.count().label("trading_days"),
        )
        .where(func.extract("year", DailySummary.trade_date) == year)
        .group_by(func.extract("month", DailySummary.trade_date))
        .order_by(func.extract("month", DailySummary.trade_date))
    )
    rows = (await db.execute(q)).all()

    data = []
    for r in rows:
        total_trades = int(r.total_trades or 0)
        wins = int(r.wins or 0)
        losses = int(r.losses or 0)
        sell_count = wins + losses
        data.append(
            MonthlyPnLItem(
                year=year,
                month=int(r.month),
                realized_pnl=int(r.realized_pnl or 0),
                total_trades=total_trades,
                wins=wins,
                losses=losses,
                win_rate=round(wins / sell_count * 100, 1) if sell_count > 0 else None,
                trading_days=int(r.trading_days or 0),
            )
        )

    return MonthlyPnLResponse(year=year, data=data)
