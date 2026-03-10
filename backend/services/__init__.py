"""서비스 모듈 — 싱글턴 인스턴스를 제공한다."""

from __future__ import annotations

from typing import Any

from backend.config import get_settings
from backend.utils.logger import logger
from backend.utils.notifications import send_error_alert

from backend.services.session_manager import (
    MarketSession,
    SESSION_PARAMS,
    SCORING_WEIGHTS,
    get_current_session,
    get_session_params,
    get_scoring_weights,
    is_buy_allowed,
    is_nxt_session,
    is_trading_day,
)
from backend.services.nxt_manager import NXTManager
from backend.services.telegram_listener import TelegramListener
from backend.services.dart_monitor import DartMonitor
from backend.services.market_data import MarketDataService
from backend.services.investor_flow import InvestorFlowService
from backend.services.ai_analyzer import AIAnalyzer
from backend.services.signal_scorer import SignalScorer
from backend.services.buy_strategy import BuyStrategy
from backend.services.sell_strategy import SellStrategy
from backend.services.risk_manager import RiskManager

_settings = get_settings()

nxt_manager = NXTManager()
market_data = MarketDataService()
investor_flow = InvestorFlowService()
ai_analyzer = AIAnalyzer()
signal_scorer = SignalScorer()
buy_strategy = BuyStrategy()
sell_strategy = SellStrategy()
risk_manager = RiskManager()

# 콜백 없이 먼저 생성 (아래에서 연결)
telegram_listener = TelegramListener()
dart_monitor = DartMonitor()


# ── 시그널 수신 콜백 ─────────────────────────────────────────────
async def _handle_new_signal(data: dict[str, Any]) -> None:
    """텔레그램/DART 메시지 수신 시 AI 2-Tier 분석을 실행하고 DB에 저장한다."""
    if not _settings.openai_api_key:
        logger.warning("OpenAI API 키 미설정 — AI 분석 스킵")
        return

    try:
        news = await ai_analyzer.analyze_tier1(
            raw_text=data["raw_text"],
            source=data["source"],
            channel=data.get("channel"),
        )

        if news.stock_code:
            await market_data.subscribe(news.stock_code)

        if news.escalated and news.stock_code:
            market_ctx = await market_data.get_current_price(news.stock_code)
            await ai_analyzer.analyze_tier2(news, market_ctx)
        else:
            logger.info(
                f"[Signal] Tier1 결과 {news.tier1_impact} — Tier2 스킵 "
                f"(종목={news.stock_code or 'N/A'}, 소스={data['source']})"
            )

    except Exception as exc:
        logger.error(f"시그널 AI 분석 에러: {exc}")
        await send_error_alert(f"시그널 AI 분석 에러: {exc}")


# 콜백 연결
telegram_listener.on_new_message = _handle_new_signal
dart_monitor.on_disclosure = _handle_new_signal


__all__ = [
    "MarketSession",
    "SESSION_PARAMS",
    "SCORING_WEIGHTS",
    "get_current_session",
    "get_session_params",
    "get_scoring_weights",
    "is_buy_allowed",
    "is_nxt_session",
    "is_trading_day",
    "nxt_manager",
    "telegram_listener",
    "dart_monitor",
    "market_data",
    "investor_flow",
    "ai_analyzer",
    "signal_scorer",
    "buy_strategy",
    "sell_strategy",
    "risk_manager",
]
