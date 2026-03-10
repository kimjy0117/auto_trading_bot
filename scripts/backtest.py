"""
간이 백테스팅 프레임워크 (스켈레톤).

DB에 저장된 news_analysis → signal_scores 이력을 불러와
스코어 임계값 기반으로 가상 매매를 시뮬레이션한다.

지표: 승률, 총 PnL, 최대 낙폭, Sharpe-유사 비율
향후 확장을 위한 플레이스홀더.

실행: python -m scripts.backtest
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select, and_

from backend.database import async_session, init_db, close_db
from backend.models.news_analysis import NewsAnalysis
from backend.models.signal_score import SignalScore
from backend.models.trade import Trade
from backend.utils.logger import logger


@dataclass
class BacktestTrade:
    stock_code: str
    stock_name: str
    score: float
    decision: str
    entry_price: int = 0
    exit_price: int = 0
    pnl: int = 0
    pnl_pct: float = 0.0
    session: str = ""


@dataclass
class BacktestResult:
    period_start: date | None = None
    period_end: date | None = None
    total_signals: int = 0
    buy_signals: int = 0
    simulated_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: int = 0
    avg_pnl_per_trade: float = 0.0
    max_drawdown: float = 0.0
    sharpe_like_ratio: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


async def load_signals(
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[SignalScore]:
    """DB에서 시그널 스코어를 불러온다."""
    async with async_session() as session:
        stmt = select(SignalScore).order_by(SignalScore.created_at)
        conditions = []
        if start_date:
            conditions.append(
                SignalScore.created_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                SignalScore.created_at <= datetime.combine(end_date, datetime.max.time())
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def load_actual_trades(
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[int, Trade]:
    """signal_score_id 기준으로 실제 매도 거래를 매핑."""
    async with async_session() as session:
        stmt = select(Trade).where(Trade.action == "SELL")
        conditions = []
        if start_date:
            conditions.append(
                Trade.created_at >= datetime.combine(start_date, datetime.min.time())
            )
        if end_date:
            conditions.append(
                Trade.created_at <= datetime.combine(end_date, datetime.max.time())
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await session.execute(stmt)
        trades = result.scalars().all()
    return {t.signal_score_id: t for t in trades if t.signal_score_id}


def simulate(
    signals: list[SignalScore],
    actual_trades: dict[int, Trade],
    buy_threshold: float = 70.0,
) -> BacktestResult:
    """
    시그널 스코어 임계값에 따라 가상 매수 판단 후,
    실제 매도 거래가 있으면 그 PnL을 사용하고 없으면 건너뛴다.
    """
    result = BacktestResult(total_signals=len(signals))
    pnl_list: list[int] = []
    running_pnl = 0
    max_dd = 0.0

    for sig in signals:
        if sig.total_score < buy_threshold or not sig.hard_filter_passed:
            continue
        result.buy_signals += 1

        trade = actual_trades.get(sig.id)
        if trade is None:
            continue

        bt = BacktestTrade(
            stock_code=sig.stock_code,
            stock_name=sig.stock_name or "",
            score=sig.total_score,
            decision=sig.decision or "BUY",
            entry_price=trade.buy_price or trade.price,
            exit_price=trade.price,
            pnl=trade.pnl or 0,
            pnl_pct=trade.pnl_pct or 0.0,
            session=sig.session,
        )
        result.trades.append(bt)
        pnl_list.append(bt.pnl)

        running_pnl += bt.pnl
        if running_pnl < max_dd:
            max_dd = running_pnl

    result.simulated_trades = len(result.trades)
    result.wins = sum(1 for t in result.trades if t.pnl > 0)
    result.losses = result.simulated_trades - result.wins
    result.win_rate = (
        round(result.wins / result.simulated_trades * 100, 1)
        if result.simulated_trades
        else 0
    )
    result.total_pnl = sum(t.pnl for t in result.trades)
    result.avg_pnl_per_trade = (
        round(result.total_pnl / result.simulated_trades)
        if result.simulated_trades
        else 0
    )
    result.max_drawdown = max_dd

    if len(pnl_list) >= 2:
        mean_pnl = statistics.mean(pnl_list)
        std_pnl = statistics.stdev(pnl_list)
        result.sharpe_like_ratio = round(mean_pnl / std_pnl, 3) if std_pnl else 0
    elif len(pnl_list) == 1:
        result.sharpe_like_ratio = float("inf") if pnl_list[0] > 0 else 0

    return result


def print_result(res: BacktestResult) -> None:
    sep = "=" * 50
    print(f"\n{sep}")
    print("  백테스트 결과")
    print(sep)
    print(f"  기간         : {res.period_start} ~ {res.period_end}")
    print(f"  총 시그널     : {res.total_signals}")
    print(f"  매수 시그널   : {res.buy_signals}")
    print(f"  시뮬 거래     : {res.simulated_trades}")
    print(f"  승/패         : {res.wins} / {res.losses}")
    print(f"  승률          : {res.win_rate:.1f}%")
    print(f"  총 PnL        : {res.total_pnl:+,}원")
    print(f"  건당 평균     : {res.avg_pnl_per_trade:+,.0f}원")
    print(f"  최대 낙폭     : {res.max_drawdown:,.0f}원")
    print(f"  Sharpe-like   : {res.sharpe_like_ratio:.3f}")
    print(sep)

    if res.trades:
        print("\n  최근 10건:")
        for t in res.trades[-10:]:
            sign = "+" if t.pnl >= 0 else ""
            print(
                f"    {t.stock_name:>10}({t.stock_code}) "
                f"score={t.score:.1f} | {t.entry_price:>8,} → {t.exit_price:>8,} "
                f"| PnL {sign}{t.pnl:,} ({t.pnl_pct:+.1f}%)"
            )
    print()


async def run_backtest(
    start_date: date | None = None,
    end_date: date | None = None,
    threshold: float = 70.0,
) -> BacktestResult:
    """백테스트 실행 메인 함수."""
    signals = await load_signals(start_date, end_date)
    actual_trades = await load_actual_trades(start_date, end_date)

    result = simulate(signals, actual_trades, buy_threshold=threshold)
    result.period_start = start_date
    result.period_end = end_date
    return result


async def main() -> None:
    await init_db()
    try:
        logger.info("=== 백테스트 시작 ===")
        result = await run_backtest(threshold=70.0)
        print_result(result)
        logger.info("=== 백테스트 완료 ===")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
