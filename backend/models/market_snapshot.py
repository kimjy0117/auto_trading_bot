from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    current_price: Mapped[int] = mapped_column(Integer, nullable=True)
    change_pct: Mapped[float] = mapped_column(Float, nullable=True)
    volume: Mapped[int] = mapped_column(Integer, nullable=True)
    volume_ratio: Mapped[float] = mapped_column(Float, nullable=True)

    # 기술지표
    rsi_14: Mapped[float] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float] = mapped_column(Float, nullable=True)
    ma_5: Mapped[float] = mapped_column(Float, nullable=True)
    ma_20: Mapped[float] = mapped_column(Float, nullable=True)
    ma_60: Mapped[float] = mapped_column(Float, nullable=True)
    atr_14: Mapped[float] = mapped_column(Float, nullable=True)
    bb_upper: Mapped[float] = mapped_column(Float, nullable=True)
    bb_lower: Mapped[float] = mapped_column(Float, nullable=True)

    # 수급
    foreign_net: Mapped[int] = mapped_column(Integer, nullable=True)
    institution_net: Mapped[int] = mapped_column(Integer, nullable=True)

    # 호가
    orderbook: Mapped[dict] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
