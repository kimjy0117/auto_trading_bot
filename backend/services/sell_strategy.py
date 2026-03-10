from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from backend.database import async_session
from backend.models import Position, Trade, NewsAnalysis, SignalScore
from backend.services.kis_api import KISApi
from backend.services.risk_manager import RiskManager
from backend.services.session_manager import (
    get_current_session,
    get_session_params,
)
from backend.utils.logger import logger
from backend.utils.notifications import send_trade_alert

_kis = KISApi()
_risk = RiskManager()


class SellStrategy:
    """세션별 ATR EXIT 기반 매도 전략."""

    async def monitor_positions(self) -> list[Trade]:
        """열린 포지션을 순회하며 EXIT 조건을 확인하고 매도 실행."""
        executed_trades: list[Trade] = []

        async with async_session() as db:
            result = await db.execute(
                select(Position).where(Position.status == "OPEN")
            )
            positions = result.scalars().all()

        if not positions:
            return executed_trades

        logger.info(f"[Sell] 오픈 포지션 {len(positions)}건 모니터링 시작")

        for position in positions:
            try:
                price_data = await _kis.get_current_price(position.stock_code)
                current_price = int(price_data.get("output", {}).get("stck_prpr", 0))
                if current_price <= 0:
                    continue

                await self._update_trailing_stop(position, current_price)

                should_sell, reason = await self._check_exit_conditions(position, current_price)
                if should_sell:
                    trade = await self.execute_sell(position, reason, current_price)
                    if trade:
                        executed_trades.append(trade)
            except Exception as e:
                logger.error(f"[Sell] {position.stock_code} 모니터링 오류: {e}")

        return executed_trades

    async def _check_exit_conditions(
        self,
        position: Position,
        current_price: int,
    ) -> tuple[bool, str]:
        session = get_current_session()
        params = get_session_params(session)

        # 1) ATR 고정 손절
        if position.stop_loss_price and current_price <= position.stop_loss_price:
            return True, "ATR_STOP"

        # 2) ATR 트레일링 스톱
        if position.trailing_stop_price and current_price <= position.trailing_stop_price:
            return True, "ATR_TRAILING"

        # 3) 타임 컷
        time_cut = params.get("time_cut_minutes")
        if position.opened_at and time_cut:
            if time_cut == "dynamic":
                now = datetime.now()
                if now.hour >= 15:
                    effective_cut = 20
                elif now.hour == 14 and now.minute >= 30:
                    effective_cut = 60
                else:
                    effective_cut = None
            else:
                effective_cut = int(time_cut)

            if effective_cut is not None:
                elapsed = (datetime.utcnow() - position.opened_at).total_seconds() / 60
                if elapsed >= effective_cut:
                    return True, "TIME_CUT"

        # 4) AI 목표가 도달
        if position.signal_score_id:
            target = await self._get_target_price(position)
            if target and current_price >= target:
                return True, "TARGET"

        # 5) 장 마감 강제 정리 (15:20 이후 미청산 포지션)
        now = datetime.now()
        if now.hour == 15 and now.minute >= 20 and position.session == "REGULAR":
            return True, "DAILY_CLEANUP"
        if now.hour >= 20 and position.session == "AFTER_MARKET":
            return True, "DAILY_CLEANUP"

        return False, ""

    async def execute_sell(
        self,
        position: Position,
        reason: str,
        current_price: int | None = None,
    ) -> Trade | None:
        if current_price is None:
            price_data = await _kis.get_current_price(position.stock_code)
            current_price = int(price_data.get("output", {}).get("stck_prpr", 0))

        if current_price <= 0:
            logger.error(f"[Sell] {position.stock_code} 현재가 조회 실패")
            return None

        exchange = position.exchange or "SOR"
        order_result = await _kis.sell_order(
            position.stock_code,
            position.quantity,
            current_price,
            exchange,
        )

        if order_result.get("rt_cd") != "0":
            msg = order_result.get("msg1", "알 수 없는 오류")
            logger.error(f"[Sell] {position.stock_code} 매도 주문 실패: {msg}")
            return None

        output = order_result.get("output", {})
        order_id = output.get("ODNO", "")

        sell_amount = current_price * position.quantity
        buy_amount = position.avg_price * position.quantity

        buy_fee_rate = 0.0001 if exchange == "NXT" else 0.00015
        sell_fee_rate = buy_fee_rate
        tax_rate = 0.0018  # 증권거래세 0.18%

        buy_fee = int(buy_amount * buy_fee_rate)
        sell_fee = int(sell_amount * sell_fee_rate)
        sell_tax = int(sell_amount * tax_rate)
        total_fee = sell_fee + sell_tax

        pnl = (current_price - position.avg_price) * position.quantity - buy_fee - total_fee
        pnl_pct = (pnl / buy_amount * 100) if buy_amount else 0

        session = get_current_session()

        async with async_session() as db:
            trade = Trade(
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                action="SELL",
                exchange=exchange,
                session=session.value,
                price=current_price,
                quantity=position.quantity,
                amount=sell_amount,
                fee=total_fee,
                buy_price=position.avg_price,
                pnl=pnl,
                pnl_pct=round(pnl_pct, 2),
                signal_score_id=position.signal_score_id,
                sell_reason=reason,
                order_id=order_id,
            )
            db.add(trade)

            pos = await db.merge(position)
            pos.status = "CLOSED"
            pos.closed_at = datetime.utcnow()
            pos.current_price = current_price
            pos.unrealized_pnl = 0
            pos.unrealized_pnl_pct = 0
            await db.commit()
            await db.refresh(trade)

        if pnl < 0:
            await _risk.record_loss(position.stock_code, abs(pnl))
        await _risk.add_cooldown(position.stock_code)

        logger.info(
            f"[Sell] 매도 완료: {position.stock_code} {position.quantity}주 "
            f"@ {current_price:,}원 | PnL={pnl:+,}원 ({pnl_pct:+.2f}%) | 사유={reason}"
        )

        await send_trade_alert(
            action="SELL",
            stock_name=position.stock_name or position.stock_code,
            stock_code=position.stock_code,
            price=current_price,
            qty=position.quantity,
            exchange=exchange,
            session=session.value,
            reason=f"{reason} | PnL {pnl:+,}원 ({pnl_pct:+.2f}%)",
        )

        return trade

    async def _update_trailing_stop(self, position: Position, current_price: int) -> None:
        """최고가 갱신 시 트레일링 스톱도 상향 조정."""
        if not position.atr_value:
            return

        highest = position.highest_price or position.avg_price
        if current_price <= highest:
            async with async_session() as db:
                pos = await db.merge(position)
                pos.current_price = current_price
                pos.unrealized_pnl = (current_price - pos.avg_price) * pos.quantity
                pos.unrealized_pnl_pct = round(
                    (current_price - pos.avg_price) / pos.avg_price * 100, 2
                ) if pos.avg_price else 0
                await db.commit()
            return

        session = get_current_session()
        params = get_session_params(session)
        trailing_mult = params["atr_trailing_multiplier"]
        new_trailing = int(current_price - position.atr_value * trailing_mult)

        async with async_session() as db:
            pos = await db.merge(position)
            pos.highest_price = current_price
            pos.current_price = current_price
            pos.unrealized_pnl = (current_price - pos.avg_price) * pos.quantity
            pos.unrealized_pnl_pct = round(
                (current_price - pos.avg_price) / pos.avg_price * 100, 2
            ) if pos.avg_price else 0

            old_trailing = pos.trailing_stop_price or 0
            if new_trailing > old_trailing:
                pos.trailing_stop_price = new_trailing
                logger.debug(
                    f"[Trail] {position.stock_code} 최고가 {current_price:,}원 → "
                    f"trailing stop {old_trailing:,} → {new_trailing:,}"
                )
            await db.commit()

    @staticmethod
    async def _get_target_price(position: Position) -> int | None:
        """Position에 연결된 AI 분석의 tier2_target_price를 DB에서 조회."""
        if not position.signal_score_id:
            return None
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(NewsAnalysis.tier2_target_price)
                    .join(SignalScore, SignalScore.news_analysis_id == NewsAnalysis.id)
                    .where(SignalScore.id == position.signal_score_id)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[Sell] 목표가 조회 오류 (signal_score_id={position.signal_score_id}): {e}")
            return None
