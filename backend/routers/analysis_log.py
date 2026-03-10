from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import NewsAnalysis, SignalScore

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ── Response schemas ──────────────────────────────────────────────

class PaginationMeta(BaseModel):
    page: int
    size: int
    total: int
    total_pages: int


class NewsItem(BaseModel):
    id: int
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    source: str
    channel: Optional[str] = None
    raw_text: str
    tier1_impact: Optional[str] = None
    tier1_direction: Optional[str] = None
    tier1_summary: Optional[str] = None
    tier1_confidence: Optional[float] = None
    tier2_action: Optional[str] = None
    tier2_rationale: Optional[str] = None
    tier2_target_price: Optional[int] = None
    tier2_stop_loss: Optional[int] = None
    tier2_confidence: Optional[float] = None
    escalated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NewsListResponse(BaseModel):
    meta: PaginationMeta
    data: list[NewsItem]


class NewsDetailResponse(NewsItem):
    tier1_model: Optional[str] = None
    tier1_tokens: Optional[int] = None
    tier2_impact_duration: Optional[str] = None
    tier2_model: Optional[str] = None
    tier2_tokens: Optional[int] = None


class ScoreItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    news_analysis_id: Optional[int] = None
    session: str
    ai_score: float
    investor_flow_score: float
    technical_score: float
    volume_score: float
    market_env_score: float
    total_score: float
    hard_filter_passed: bool
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScoreListResponse(BaseModel):
    meta: PaginationMeta
    data: list[ScoreItem]


class ScoreDetailResponse(ScoreItem):
    hard_filter_reason: Optional[str] = None
    nxt_eligible: Optional[bool] = None
    score_detail: Optional[Any] = None


# ── Helpers ───────────────────────────────────────────────────────

def _pagination_meta(page: int, size: int, total: int) -> PaginationMeta:
    return PaginationMeta(
        page=page,
        size=size,
        total=total,
        total_pages=(total + size - 1) // size if size > 0 else 0,
    )


# ── News endpoints ────────────────────────────────────────────────

@router.get("/news", response_model=NewsListResponse)
async def list_news(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None, description="TELEGRAM / DART / MANUAL"),
    stock_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    base = select(NewsAnalysis)
    count_q = select(func.count()).select_from(NewsAnalysis)

    if source:
        base = base.where(NewsAnalysis.source == source.upper())
        count_q = count_q.where(NewsAnalysis.source == source.upper())
    if stock_code:
        base = base.where(NewsAnalysis.stock_code == stock_code)
        count_q = count_q.where(NewsAnalysis.stock_code == stock_code)

    total = (await db.execute(count_q)).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(desc(NewsAnalysis.created_at))
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()

    return NewsListResponse(
        meta=_pagination_meta(page, size, total),
        data=[NewsItem.model_validate(r) for r in rows],
    )


@router.get("/news/{news_id}", response_model=NewsDetailResponse)
async def get_news_detail(news_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(NewsAnalysis).where(NewsAnalysis.id == news_id))
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="뉴스 분석을 찾을 수 없습니다")

    return NewsDetailResponse.model_validate(row)


# ── Score endpoints ───────────────────────────────────────────────

@router.get("/scores", response_model=ScoreListResponse)
async def list_scores(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: Optional[str] = Query(None, description="PRE_MARKET / REGULAR / AFTER_MARKET"),
    decision: Optional[str] = Query(None, description="BUY / SKIP / WATCH"),
    db: AsyncSession = Depends(get_db),
):
    base = select(SignalScore)
    count_q = select(func.count()).select_from(SignalScore)

    if session:
        base = base.where(SignalScore.session == session.upper())
        count_q = count_q.where(SignalScore.session == session.upper())
    if decision:
        base = base.where(SignalScore.decision == decision.upper())
        count_q = count_q.where(SignalScore.decision == decision.upper())

    total = (await db.execute(count_q)).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(desc(SignalScore.created_at))
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()

    return ScoreListResponse(
        meta=_pagination_meta(page, size, total),
        data=[ScoreItem.model_validate(r) for r in rows],
    )


@router.get("/scores/{score_id}", response_model=ScoreDetailResponse)
async def get_score_detail(score_id: int, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(SignalScore).where(SignalScore.id == score_id))
    ).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="시그널 스코어를 찾을 수 없습니다")

    return ScoreDetailResponse.model_validate(row)
