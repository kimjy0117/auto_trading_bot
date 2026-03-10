from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=True)

    exchange: Mapped[str] = mapped_column(
        SAEnum("KRX", "NXT", "SOR", name="position_exchange"),
        nullable=False,
        server_default="SOR",
    )
    session: Mapped[str] = mapped_column(
        SAEnum("PRE_MARKET", "REGULAR", "AFTER_MARKET", name="position_session"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[int] = mapped_column(Integer, nullable=False)
    current_price: Mapped[int] = mapped_column(Integer, default=0)
    unrealized_pnl: Mapped[int] = mapped_column(Integer, default=0)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, default=0)

    # ATR EXIT 기준값
    atr_value: Mapped[float] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[int] = mapped_column(Integer, nullable=True)
    trailing_stop_price: Mapped[int] = mapped_column(Integer, nullable=True)
    highest_price: Mapped[int] = mapped_column(Integer, nullable=True)

    signal_score_id: Mapped[int] = mapped_column(Integer, nullable=True)
    buy_trade_id: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        SAEnum("OPEN", "CLOSED", name="position_status"),
        default="OPEN",
        index=True,
    )

    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
