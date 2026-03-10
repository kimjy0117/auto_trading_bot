from __future__ import annotations

import os
import time
from datetime import datetime

import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import Position, Trade
from backend.redis_client import get_redis
from backend.services.session_manager import (
    MarketSession,
    get_current_session,
    is_trading_day,
)

router = APIRouter(prefix="/api/health", tags=["health"])

_START_TIME = time.time()


# ── Response schemas ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    current_session: str
    is_trading_day: bool
    uptime_seconds: float
    db_ok: bool
    redis_ok: bool
    timestamp: datetime


class MetricsResponse(BaseModel):
    open_positions: int
    today_trades: int
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await db.execute(select(1))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        r = await get_redis()
        await r.ping()
    except Exception:
        redis_ok = False

    session: MarketSession = get_current_session()

    return HealthResponse(
        status="ok" if (db_ok and redis_ok) else "degraded",
        current_session=session.value,
        is_trading_day=is_trading_day(),
        uptime_seconds=round(time.time() - _START_TIME, 1),
        db_ok=db_ok,
        redis_ok=redis_ok,
        timestamp=datetime.utcnow(),
    )


@router.get("/metrics", response_model=MetricsResponse)
async def system_metrics(db: AsyncSession = Depends(get_db)):
    today = datetime.utcnow().date()

    open_pos_q = select(func.count()).select_from(Position).where(
        Position.status == "OPEN",
    )
    today_trades_q = select(func.count()).select_from(Trade).where(
        func.date(Trade.created_at) == today,
    )

    open_count = (await db.execute(open_pos_q)).scalar() or 0
    trade_count = (await db.execute(today_trades_q)).scalar() or 0

    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()

    return MetricsResponse(
        open_positions=open_count,
        today_trades=trade_count,
        memory_usage_mb=round(mem.rss / 1024 / 1024, 2),
        memory_percent=round(proc.memory_percent(), 2),
        cpu_percent=proc.cpu_percent(interval=None),
    )
