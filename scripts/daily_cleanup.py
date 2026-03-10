"""
일일 정산 스크립트 (DAILY_CLEANUP 세션, 20:00~20:10).

- 미청산 포지션 경고
- 일일 PnL 집계 → daily_summary 저장
- Redis 캐시 정리 (가격·호가·분봉, 쿨다운/손실카운터는 유지)
- 텔레그램 일일 리포트 발송

실행: python -m scripts.daily_cleanup  (단독 실행 가능)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

from sqlalchemy import select, func, and_

from backend.config import get_settings
from backend.database import async_session, init_db, close_db
from backend.redis_client import get_redis, close_redis, delete_pattern
from backend.models.trade import Trade
from backend.models.position import Position
from backend.models.daily_summary import DailySummary
from backend.utils.logger import logger
from backend.utils.notifications import (
    send_telegram_message,
    send_daily_report,
    send_error_alert,
)

settings = get_settings()


async def _check_unclosed_positions() -> int:
    """미청산 포지션이 있으면 텔레그램 경고를 보내고 건수를 반환."""
    async with async_session() as session:
        result = await session.execute(
            select(Position).where(Position.status == "OPEN")
        )
        open_positions = result.scalars().all()

    if not open_positions:
        return 0

    lines = [f"⚠️ <b>미청산 포지션 {len(open_positions)}건</b>"]
    for p in open_positions:
        pnl_sign = "+" if p.unrealized_pnl >= 0 else ""
        lines.append(
            f"  • {p.stock_name}({p.stock_code}) "
            f"{p.quantity}주 | 평단 {p.avg_price:,} | "
            f"평가손익 {pnl_sign}{p.unrealized_pnl:,}원"
        )
    await send_telegram_message("\n".join(lines))
    return len(open_positions)


async def _calculate_daily_pnl(trade_date: date) -> DailySummary | None:
    """당일 체결된 매도 거래를 집계하여 DailySummary를 생성·저장한다."""
    start_dt = datetime.combine(trade_date, datetime.min.time())
    end_dt = datetime.combine(trade_date, datetime.max.time())

    async with async_session() as session:
        existing = await session.scalar(
            select(DailySummary).where(DailySummary.trade_date == trade_date)
        )
        if existing:
            logger.info(f"{trade_date} 일일 집계 이미 존재 — 건너뜀")
            return existing

        sells = (
            await session.execute(
                select(Trade).where(
                    and_(
                        Trade.action == "SELL",
                        Trade.created_at >= start_dt,
                        Trade.created_at <= end_dt,
                    )
                )
            )
        ).scalars().all()

        if not sells:
            logger.info(f"{trade_date} 매도 거래 없음")
            summary = DailySummary(
                trade_date=trade_date,
                total_trades=0, wins=0, losses=0,
                win_rate=0, realized_pnl=0,
                pre_market_pnl=0, regular_pnl=0, after_market_pnl=0,
            )
            session.add(summary)
            await session.commit()
            return summary

        total = len(sells)
        wins = sum(1 for t in sells if t.pnl and t.pnl > 0)
        losses = total - wins
        realized_pnl = sum(t.pnl or 0 for t in sells)
        win_rate = round(wins / total * 100, 1) if total else 0

        pre_pnl = sum(t.pnl or 0 for t in sells if t.session == "PRE_MARKET")
        reg_pnl = sum(
            t.pnl or 0
            for t in sells
            if t.session in ("REGULAR", "CLOSING")
        )
        after_pnl = sum(t.pnl or 0 for t in sells if t.session == "AFTER_MARKET")

        running_pnl, max_dd = 0, 0.0
        for t in sorted(sells, key=lambda x: x.created_at):
            running_pnl += t.pnl or 0
            dd = min(running_pnl, 0)
            if dd < max_dd:
                max_dd = dd

        summary = DailySummary(
            trade_date=trade_date,
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            realized_pnl=realized_pnl,
            pre_market_pnl=pre_pnl,
            regular_pnl=reg_pnl,
            after_market_pnl=after_pnl,
            max_drawdown=float(max_dd),
        )
        session.add(summary)
        await session.commit()
        logger.info(f"일일 집계 저장: {trade_date} | 거래 {total}건 | PnL {realized_pnl:+,}")
        return summary


async def _clean_redis_caches() -> None:
    """시세·호가·분봉 캐시를 삭제하고, 쿨다운/손실카운터는 유지."""
    for pattern in ("price:*", "orderbook:*", "volume_1min:*"):
        await delete_pattern(pattern)
        logger.debug(f"Redis 캐시 삭제: {pattern}")
    logger.info("Redis 시세 캐시 정리 완료")


def _format_daily_report(summary: DailySummary, unclosed: int) -> str:
    pnl_sign = "+" if summary.realized_pnl >= 0 else ""
    lines = [
        f"📅 일자: {summary.trade_date}",
        f"📈 총 거래: {summary.total_trades}건 (승 {summary.wins} / 패 {summary.losses})",
        f"🎯 승률: {summary.win_rate:.1f}%",
        f"💰 실현손익: {pnl_sign}{summary.realized_pnl:,}원",
        "",
        "<b>세션별 손익</b>",
        f"  프리마켓: {summary.pre_market_pnl:+,}원",
        f"  정규장:   {summary.regular_pnl:+,}원",
        f"  애프터:   {summary.after_market_pnl:+,}원",
    ]
    if summary.max_drawdown:
        lines.append(f"📉 최대 낙폭: {summary.max_drawdown:,.0f}원")
    if unclosed:
        lines.append(f"\n⚠️ 미청산 포지션: {unclosed}건")
    return "\n".join(lines)


async def run_daily_cleanup() -> None:
    """일일 정산 메인 함수. main.py 루프에서 호출되거나 단독 실행 가능."""
    logger.info("=== 일일 정산 시작 ===")
    today = date.today()

    try:
        unclosed = await _check_unclosed_positions()
        summary = await _calculate_daily_pnl(today)
        await _clean_redis_caches()

        if summary:
            report = _format_daily_report(summary, unclosed)
            await send_daily_report(report)
    except Exception as e:
        logger.error(f"일일 정산 에러: {e}")
        await send_error_alert(f"일일 정산 에러: {e}")

    logger.info("=== 일일 정산 완료 ===")


async def main() -> None:
    """단독 실행 시 DB/Redis 커넥션 관리."""
    await init_db()
    await get_redis()
    try:
        await run_daily_cleanup()
    finally:
        await close_redis()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
