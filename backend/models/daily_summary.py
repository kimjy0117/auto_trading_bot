from datetime import date
from sqlalchemy import Integer, Float, Date
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DailySummary(Base):
    __tablename__ = "daily_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[int] = mapped_column(Integer, default=0)
    pre_market_pnl: Mapped[int] = mapped_column(Integer, default=0)
    regular_pnl: Mapped[int] = mapped_column(Integer, default=0)
    after_market_pnl: Mapped[int] = mapped_column(Integer, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, nullable=True)
