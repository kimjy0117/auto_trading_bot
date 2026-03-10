"""
주간 리포트 생성 & 텔레그램 발송.

최근 7일간 daily_summary를 집계하여 총 거래, 승률, 총 PnL,
건당 평균 PnL, 세션별 성과를 분석하고,
승률 40% 미만 세션에 대해 비활성화를 권장한다.

실행: python -m scripts.weekly_report
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from backend.database import async_session, init_db, close_db
from backend.redis_client import get_redis, close_redis
from backend.models.daily_summary import DailySummary
from backend.models.trade import Trade
from backend.utils.logger import logger
from backend.utils.notifications import send_telegram_message

from sqlalchemy import and_


async def _collect_weekly_data(
    start_date: date, end_date: date
) -> list[DailySummary]:
    async with async_session() as session:
        result = await session.execute(
            select(DailySummary)
            .where(
                and_(
                    DailySummary.trade_date >= start_date,
                    DailySummary.trade_date <= end_date,
                )
            )
            .order_by(DailySummary.trade_date)
        )
        return list(result.scalars().all())


async def _session_breakdown(
    start_date: date, end_date: date
) -> dict[str, dict]:
    """세션별 매도 거래를 집계하여 {session: {trades, wins, pnl, win_rate}} 반환."""
    from datetime import datetime

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    async with async_session() as session:
        result = await session.execute(
            select(Trade).where(
                and_(
                    Trade.action == "SELL",
                    Trade.created_at >= start_dt,
                    Trade.created_at <= end_dt,
                )
            )
        )
        sells = result.scalars().all()

    breakdown: dict[str, dict] = {}
    for t in sells:
        key = t.session
        if key not in breakdown:
            breakdown[key] = {"trades": 0, "wins": 0, "pnl": 0}
        breakdown[key]["trades"] += 1
        if t.pnl and t.pnl > 0:
            breakdown[key]["wins"] += 1
        breakdown[key]["pnl"] += t.pnl or 0

    for v in breakdown.values():
        v["win_rate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0

    return breakdown


def _format_weekly_report(
    summaries: list[DailySummary],
    breakdown: dict[str, dict],
    start_date: date,
    end_date: date,
) -> str:
    total_trades = sum(s.total_trades for s in summaries)
    total_wins = sum(s.wins for s in summaries)
    total_pnl = sum(s.realized_pnl for s in summaries)
    win_rate = round(total_wins / total_trades * 100, 1) if total_trades else 0
    avg_pnl = round(total_pnl / total_trades) if total_trades else 0
    pnl_sign = "+" if total_pnl >= 0 else ""

    lines = [
        f"📊 <b>주간 리포트</b>",
        f"기간: {start_date} ~ {end_date}",
        "",
        f"총 거래: {total_trades}건",
        f"승률: {win_rate:.1f}% ({total_wins}승 / {total_trades - total_wins}패)",
        f"총 손익: {pnl_sign}{total_pnl:,}원",
        f"건당 평균: {avg_pnl:+,}원",
        "",
        "<b>세션별 성과</b>",
    ]

    session_labels = {
        "PRE_MARKET": "프리마켓",
        "REGULAR": "정규장",
        "CLOSING": "장마감",
        "AFTER_MARKET": "애프터마켓",
    }
    alerts: list[str] = []
    for session_key, label in session_labels.items():
        info = breakdown.get(session_key)
        if not info or info["trades"] == 0:
            lines.append(f"  {label}: 거래 없음")
            continue
        s_pnl_sign = "+" if info["pnl"] >= 0 else ""
        lines.append(
            f"  {label}: {info['trades']}건 | "
            f"승률 {info['win_rate']:.1f}% | "
            f"{s_pnl_sign}{info['pnl']:,}원"
        )
        if info["win_rate"] < 40:
            alerts.append(
                f"⚠️ {label} 승률 {info['win_rate']:.1f}% — 세션 비활성화를 권장합니다."
            )

    if alerts:
        lines.append("")
        lines.append("<b>권장 조치</b>")
        lines.extend(alerts)

    return "\n".join(lines)


async def run_weekly_report() -> None:
    """주간 리포트 생성 및 발송."""
    logger.info("=== 주간 리포트 생성 시작 ===")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=6)

    summaries = await _collect_weekly_data(start_date, end_date)
    if not summaries:
        msg = f"📊 주간 리포트\n{start_date} ~ {end_date}: 거래 데이터 없음"
        await send_telegram_message(msg)
        logger.info("주간 데이터 없음 — 빈 리포트 발송")
        return

    breakdown = await _session_breakdown(start_date, end_date)
    report = _format_weekly_report(summaries, breakdown, start_date, end_date)
    await send_telegram_message(report)
    logger.info("주간 리포트 발송 완료")


async def main() -> None:
    await init_db()
    await get_redis()
    try:
        await run_weekly_report()
    finally:
        await close_redis()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
