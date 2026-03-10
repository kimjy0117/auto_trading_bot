from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select

from backend.config import get_settings
from backend.database import async_session
from backend.models import Trade, Position
from backend.redis_client import get_redis
from backend.services.session_manager import (
    MarketSession,
    get_current_session,
    get_session_params,
)
from backend.utils.logger import logger

settings = get_settings()

_SECTOR_MAX_RATIO = 0.4  # 한 섹터에 전체 포지션의 40% 이상 불가
_SECTOR_MAP: dict[str, str] = {
    "005930": "반도체", "000660": "반도체", "042700": "반도체",
    "035420": "인터넷", "035720": "인터넷", "263750": "인터넷",
    "207940": "바이오", "068270": "바이오", "326030": "바이오",
    "055550": "금융", "105560": "금융",
    "006400": "자동차", "012330": "자동차",
    "051910": "화학", "009150": "화학",
}


class RiskManager:

    async def check_daily_loss_limit(self) -> bool:
        """일일 손실 한도 도달 여부. True면 한도 초과."""
        daily_pnl = await self.get_daily_pnl()
        limit = settings.max_daily_loss
        exceeded = daily_pnl <= -limit
        if exceeded:
            logger.warning(f"일일 손실 한도 초과: {daily_pnl:,}원 (한도: -{limit:,}원)")
        return exceeded

    async def check_position_limit(self, session: MarketSession | None = None) -> bool:
        """포지션 한도 도달 여부. True면 한도 초과."""
        if session is None:
            session = get_current_session()
        params = get_session_params(session)
        max_positions = params.get("max_concurrent_positions", params.get("max_positions", 3))

        async with async_session() as db:
            result = await db.execute(
                select(func.count()).select_from(Position).where(Position.status == "OPEN")
            )
            current_count = result.scalar_one()

        exceeded = current_count >= max_positions
        if exceeded:
            logger.info(f"포지션 한도 도달: {current_count}/{max_positions} ({session.value})")
        return exceeded

    async def check_cooldown(self, stock_code: str) -> bool:
        """쿨다운 중 여부. True면 쿨다운 중."""
        redis = await get_redis()
        key = f"cooldown:{stock_code}"
        val = await redis.get(key)
        if val:
            logger.debug(f"{stock_code} 쿨다운 중 (남은 TTL: {await redis.ttl(key)}s)")
            return True
        return False

    async def check_sector_diversification(self, stock_code: str) -> bool:
        """섹터 집중 여부. True면 동일 섹터 과다."""
        target_sector = _SECTOR_MAP.get(stock_code)
        if not target_sector:
            return False

        async with async_session() as db:
            result = await db.execute(
                select(Position.stock_code).where(Position.status == "OPEN")
            )
            open_codes = [row[0] for row in result.all()]

        if not open_codes:
            return False

        same_sector_count = sum(
            1 for code in open_codes if _SECTOR_MAP.get(code) == target_sector
        )
        total = len(open_codes) + 1
        ratio = (same_sector_count + 1) / total

        if ratio > _SECTOR_MAX_RATIO:
            logger.info(f"{stock_code} 섹터({target_sector}) 집중도 {ratio:.0%} > {_SECTOR_MAX_RATIO:.0%}")
            return True
        return False

    async def add_cooldown(self, stock_code: str, minutes: int | None = None) -> None:
        if minutes is None:
            session = get_current_session()
            minutes = get_session_params(session)["cooldown_minutes"]

        redis = await get_redis()
        key = f"cooldown:{stock_code}"
        await redis.setex(key, minutes * 60, "1")
        logger.info(f"{stock_code} 쿨다운 설정: {minutes}분")

    async def record_loss(self, stock_code: str, amount: int) -> None:
        """일일 손실 기록 (Redis 누적)."""
        redis = await get_redis()
        today = date.today().isoformat()
        key = f"daily_loss:{today}"
        await redis.incrbyfloat(key, float(amount))
        await redis.expire(key, 86400)
        logger.info(f"손실 기록: {stock_code} {amount:,}원")

    async def get_daily_pnl(self) -> int:
        """오늘 실현 손익 합계."""
        today_start = datetime.combine(date.today(), datetime.min.time())

        async with async_session() as db:
            result = await db.execute(
                select(func.coalesce(func.sum(Trade.pnl), 0)).where(
                    Trade.action == "SELL",
                    Trade.created_at >= today_start,
                )
            )
            return int(result.scalar_one())

    async def get_session_stats(self, session: MarketSession) -> dict:
        """세션별 매매 통계."""
        today_start = datetime.combine(date.today(), datetime.min.time())

        async with async_session() as db:
            trades_result = await db.execute(
                select(Trade).where(
                    Trade.session == session.value,
                    Trade.created_at >= today_start,
                )
            )
            trades = trades_result.scalars().all()

        sell_trades = [t for t in trades if t.action == "SELL"]
        total_pnl = sum(t.pnl or 0 for t in sell_trades)
        wins = sum(1 for t in sell_trades if (t.pnl or 0) > 0)
        losses = sum(1 for t in sell_trades if (t.pnl or 0) < 0)

        return {
            "session": session.value,
            "total_trades": len(trades),
            "sell_trades": len(sell_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(sell_trades) if sell_trades else 0,
            "total_pnl": total_pnl,
        }
