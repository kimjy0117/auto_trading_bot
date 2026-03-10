"""
DB 테이블 초기화 & 기본 전략 파라미터 삽입.

실행: python -m scripts.init_db
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select, func

from backend.config import get_settings
from backend.database import init_db, close_db, async_session, Base  # noqa: F401
from backend.models import (  # noqa: F401  — Base.metadata에 등록시키기 위해 임포트
    NewsAnalysis,
    SignalScore,
    Trade,
    Position,
    MarketSnapshot,
    StrategyParams,
    DailySummary,
)
from backend.utils.logger import logger

settings = get_settings()

DEFAULT_STRATEGY_PARAMS: list[dict] = [
    {
        "param_key": "buy_threshold_pre_market",
        "param_value": "80",
        "description": "프리마켓 매수 임계점수",
    },
    {
        "param_key": "buy_threshold_regular",
        "param_value": "70",
        "description": "정규장 매수 임계점수",
    },
    {
        "param_key": "buy_threshold_after_market",
        "param_value": "85",
        "description": "애프터마켓 매수 임계점수",
    },
    {
        "param_key": "atr_stop_multiplier",
        "param_value": "2.0",
        "description": "ATR 기반 손절 배수",
    },
    {
        "param_key": "trailing_stop_pct",
        "param_value": "3.0",
        "description": "트레일링 스탑 비율(%)",
    },
    {
        "param_key": "max_position_count",
        "param_value": str(settings.max_position_count),
        "description": "최대 동시 보유 종목 수",
    },
    {
        "param_key": "max_daily_loss",
        "param_value": str(settings.max_daily_loss),
        "description": "일일 최대 허용 손실(원)",
    },
    {
        "param_key": "cooldown_minutes",
        "param_value": str(settings.cooldown_minutes),
        "description": "손절 후 쿨다운 시간(분)",
    },
    {
        "param_key": "score_weights",
        "param_value": None,
        "param_json": {
            "ai": 30,
            "flow": 20,
            "tech": 25,
            "vol": 15,
            "market": 10,
        },
        "description": "정규장 기본 스코어링 가중치",
    },
]


async def seed_strategy_params() -> None:
    """strategy_params 테이블이 비어 있으면 기본값 삽입."""
    async with async_session() as session:
        count = await session.scalar(select(func.count()).select_from(StrategyParams))
        if count and count > 0:
            logger.info(f"strategy_params 이미 {count}건 존재 — 시딩 건너뜀")
            return

        for row in DEFAULT_STRATEGY_PARAMS:
            param = StrategyParams(
                param_key=row["param_key"],
                param_value=row.get("param_value"),
                param_json=row.get("param_json"),
                description=row.get("description"),
            )
            session.add(param)
        await session.commit()
        logger.info(f"strategy_params {len(DEFAULT_STRATEGY_PARAMS)}건 삽입 완료")


async def main() -> None:
    logger.info("=== DB 초기화 시작 ===")
    await init_db()
    logger.info("테이블 생성 완료")

    await seed_strategy_params()

    await close_db()
    logger.info("=== DB 초기화 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
