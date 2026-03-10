from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=True)

    action: Mapped[str] = mapped_column(
        SAEnum("BUY", "SELL", name="trade_action"), nullable=False
    )
    exchange: Mapped[str] = mapped_column(
        SAEnum("KRX", "NXT", "SOR", name="trade_exchange"),
        nullable=False,
        server_default="SOR",
    )
    session: Mapped[str] = mapped_column(
        SAEnum("PRE_MARKET", "REGULAR", "CLOSING", "AFTER_MARKET", name="trade_session"),
        nullable=False,
    )

    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    fee: Mapped[int] = mapped_column(Integer, default=0)

    # 매도 시에만 채워지는 필드
    buy_price: Mapped[int] = mapped_column(Integer, nullable=True)
    pnl: Mapped[int] = mapped_column(Integer, nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=True)

    signal_score_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    sell_reason: Mapped[str] = mapped_column(
        SAEnum(
            "ATR_STOP", "ATR_TRAILING", "TIME_CUT", "TARGET",
            "MANUAL", "DAILY_CLEANUP", "RISK_LIMIT",
            name="sell_reason_type",
        ),
        nullable=True,
    )
    memo: Mapped[str] = mapped_column(Text, nullable=True)
    order_id: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
