from __future__ import annotations

from sqlalchemy import select

from backend.config import get_settings
from backend.database import async_session
from backend.models import SignalScore, Trade, Position, MarketSnapshot
from backend.services.kis_api import KISApi
from backend.services.risk_manager import RiskManager
from backend.services.session_manager import (
    get_current_session,
    get_session_params,
)
from backend.utils.logger import logger
from backend.utils.notifications import send_trade_alert

settings = get_settings()
_kis = KISApi()
_risk = RiskManager()


class BuyStrategy:
    """세션별 매수 전략 — 스코어 임계값 + 포지션 사이징."""

    def __init__(self) -> None:
        self._cached_cash: int = 0

    async def evaluate_and_buy(self, signal_score: SignalScore) -> Trade | None:
        session = get_current_session()
        params = get_session_params(session)

        threshold = params.get("buy_score_threshold", params.get("threshold", 70))
        if signal_score.total_score < threshold:
            logger.info(
                f"[Buy] {signal_score.stock_code} 스코어 미달 "
                f"({signal_score.total_score:.1f} < {threshold})"
            )
            return None

        if not signal_score.hard_filter_passed:
            logger.info(f"[Buy] {signal_score.stock_code} 하드필터 미통과: {signal_score.hard_filter_reason}")
            return None

        if await _risk.check_position_limit(session):
            logger.info(f"[Buy] 포지션 한도 초과 ({session.value})")
            return None

        if await _risk.check_daily_loss_limit():
            logger.info("[Buy] 일일 손실 한도 도달")
            return None

        stock_code = signal_score.stock_code
        exchange = params["exchange"]

        price_data = await _kis.get_current_price(stock_code)
        current_price = int(price_data.get("output", {}).get("stck_prpr", 0))
        if current_price <= 0:
            logger.error(f"[Buy] {stock_code} 현재가 조회 실패")
            return None

        available = await self._get_available_cash()
        qty = self._calculate_position_size(current_price, params, available)
        if qty <= 0:
            logger.info(f"[Buy] {stock_code} 주문 수량 0 — 자금 부족")
            return None

        order_result = await _kis.buy_order(stock_code, qty, current_price, exchange)

        if order_result.get("rt_cd") != "0":
            msg = order_result.get("msg1", "알 수 없는 오류")
            logger.error(f"[Buy] {stock_code} 주문 실패: {msg}")
            return None

        output = order_result.get("output", {})
        order_id = output.get("ODNO", "")

        atr_value = await self._get_atr(stock_code)
        stop_loss = (
            int(current_price - atr_value * params["atr_stop_multiplier"])
            if atr_value else None
        )

        async with async_session() as db:
            position = Position(
                stock_code=stock_code,
                stock_name=signal_score.stock_name,
                exchange=exchange,
                session=session.value,
                quantity=qty,
                avg_price=current_price,
                current_price=current_price,
                atr_value=atr_value,
                stop_loss_price=stop_loss,
                trailing_stop_price=stop_loss,
                highest_price=current_price,
                signal_score_id=signal_score.id,
                status="OPEN",
            )
            db.add(position)
            await db.flush()

            amount = current_price * qty
            fee_rate = 0.0001 if exchange == "NXT" else 0.00015
            fee = int(amount * fee_rate)

            trade = Trade(
                stock_code=stock_code,
                stock_name=signal_score.stock_name,
                action="BUY",
                exchange=exchange,
                session=session.value,
                price=current_price,
                quantity=qty,
                amount=amount,
                fee=fee,
                signal_score_id=signal_score.id,
                order_id=order_id,
            )
            db.add(trade)
            await db.flush()

            position.buy_trade_id = trade.id
            await db.commit()
            await db.refresh(trade)

        logger.info(
            f"[Buy] 매수 완료: {stock_code} {qty}주 @ {current_price:,}원 "
            f"(거래소={exchange}, 세션={session.value})"
        )

        await send_trade_alert(
            action="BUY",
            stock_name=signal_score.stock_name or stock_code,
            stock_code=stock_code,
            price=current_price,
            qty=qty,
            exchange=exchange,
            session=session.value,
            reason=f"Score {signal_score.total_score:.1f}",
        )

        return trade

    @staticmethod
    def _calculate_position_size(price: int, session_params: dict, available_cash: int) -> int:
        max_pct = session_params["max_position_pct"]
        max_amount = available_cash * max_pct // 100
        if price <= 0:
            return 0
        return max_amount // price

    async def _get_available_cash(self) -> int:
        balance = await _kis.get_balance()
        output2 = balance.get("output2", [{}])
        cash = int(output2[0].get("dnca_tot_amt", 0)) if output2 else 0
        self._cached_cash = cash
        return cash

    @staticmethod
    async def _get_atr(stock_code: str) -> float | None:
        async with async_session() as db:
            result = await db.execute(
                select(MarketSnapshot.atr_14)
                .where(MarketSnapshot.stock_code == stock_code)
                .order_by(MarketSnapshot.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return float(row) if row else None
