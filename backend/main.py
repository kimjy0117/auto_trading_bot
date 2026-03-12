"""
한국 주식 AI 자동매매 시스템 — FastAPI 엔트리포인트.

APScheduler 기반 30초 루프로 시그널 감지 → 스코어링 → 매수/매도를 수행한다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.config import get_settings
from backend.database import init_db, close_db
from backend.redis_client import get_redis, close_redis
from backend.utils.logger import logger
from backend.utils.notifications import send_telegram_message, send_error_alert

from backend.routers import dashboard, analysis_log, trades, positions, health, account

from backend.services.session_manager import (
    is_trading_day,
    get_current_session,
    MarketSession,
)
from backend.services import (
    telegram_listener,
    dart_monitor,
    market_data,
    investor_flow,
    ai_analyzer,
    signal_scorer,
    buy_strategy,
    sell_strategy,
    risk_manager,
    nxt_manager,
)

settings = get_settings()
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


# ── 메인 트레이딩 루프 (30초마다) ──────────────────────────────────
async def trading_loop() -> None:
    """30초 주기 메인 루프: 세션 확인 → 시그널 처리 → 매수/매도 판단."""
    try:
        session = get_current_session()

        if session in (
            MarketSession.CLOSED,
            MarketSession.PRE_MARKET_BREAK,
            MarketSession.CLOSING_BREAK,
        ):
            return

        if session == MarketSession.DAILY_CLEANUP:
            from scripts.daily_cleanup import run_daily_cleanup

            await run_daily_cleanup()
            return

        if await risk_manager.check_daily_loss_limit():
            logger.warning("일일 손실 한도 도달 — 매수 중단, 포지션 모니터링만 수행")
        else:
            pending = await _get_pending_analyses()
            for news in pending:
                stock_code = news.stock_code or ""
                await market_data.subscribe(stock_code)
                market_ctx = await market_data.get_current_price(stock_code)
                if not market_ctx:
                    logger.debug(f"[Loop] {stock_code} 시세 데이터 없음 — 스킵")
                    continue
                inv_data = await investor_flow.get_investor_flow(stock_code)
                scored = await signal_scorer.score_signal(
                    news, market_ctx, inv_data, session,
                )
                if scored and scored.decision == "BUY":
                    await buy_strategy.evaluate_and_buy(scored)

        await sell_strategy.monitor_positions()

    except Exception as e:
        logger.error(f"트레이딩 루프 에러: {e}")
        await send_error_alert(f"트레이딩 루프 에러: {e}")


async def _get_pending_analyses():
    """Tier2까지 완료되었으나 아직 스코어링되지 않은 뉴스 분석 목록."""
    from sqlalchemy import select
    from backend.database import async_session
    from backend.models import NewsAnalysis, SignalScore

    async with async_session() as db:
        scored_ids = select(SignalScore.news_analysis_id).where(
            SignalScore.news_analysis_id.isnot(None)
        ).scalar_subquery()

        result = await db.execute(
            select(NewsAnalysis).where(
                NewsAnalysis.escalated.is_(True),
                NewsAnalysis.tier2_action.isnot(None),
                NewsAnalysis.id.notin_(scored_ids),
                NewsAnalysis.stock_code.isnot(None),
            ).limit(20)
        )
        return result.scalars().all()


# ── 라이프스팬 ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    logger.info("=== 시스템 시작 ===")
    await init_db()
    await get_redis()

    if not is_trading_day():
        logger.info("비거래일 — 스케줄러 시작하지 않음")
    else:
        if settings.nxt_enabled:
            await nxt_manager.refresh_nxt_stocks()
        await telegram_listener.start()
        await dart_monitor.start()
        await market_data.start()
        # await investor_flow.start()  # WebSocket(H0STCNI0)으로 대체됨

        scheduler.add_job(
            trading_loop,
            "interval",
            seconds=30,
            id="trading_loop",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("스케줄러 시작 (30초 간격)")

    await send_telegram_message("✅ <b>시스템 시작</b>\n자동매매 시스템이 가동되었습니다.")

    yield

    # ── shutdown ──
    logger.info("=== 시스템 종료 ===")
    if scheduler.running:
        scheduler.shutdown(wait=False)

    for svc, name in [
        (telegram_listener, "텔레그램"),
        (dart_monitor, "DART"),
        (market_data, "시세"),
        # (investor_flow, "수급"),
    ]:
        try:
            await svc.stop()
        except Exception as e:
            logger.warning(f"{name} 서비스 종료 중 에러: {e}")

    await close_redis()
    await close_db()
    await send_telegram_message("🛑 <b>시스템 종료</b>\n자동매매 시스템이 종료되었습니다.")
    logger.info("모든 리소스 정리 완료")


# ── FastAPI 앱 ─────────────────────────────────────────────────────
app = FastAPI(
    title="AI 자동매매 시스템",
    description="한국 주식(KRX/NXT) AI 기반 자동매매 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(analysis_log.router)
app.include_router(trades.router)
app.include_router(positions.router)
app.include_router(account.router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/api/health")
