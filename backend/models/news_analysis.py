from datetime import datetime
from sqlalchemy import String, Text, Integer, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=True, index=True)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        SAEnum("TELEGRAM", "DART", "MANUAL", name="news_source"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(100), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Tier 1 (GPT-4o mini) 결과
    tier1_impact: Mapped[str] = mapped_column(
        SAEnum("HIGH", "MEDIUM", "LOW", "NONE", name="impact_level"),
        nullable=True,
    )
    tier1_direction: Mapped[str] = mapped_column(
        SAEnum("POSITIVE", "NEGATIVE", "NEUTRAL", name="direction"),
        nullable=True,
    )
    tier1_summary: Mapped[str] = mapped_column(Text, nullable=True)
    tier1_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    tier1_model: Mapped[str] = mapped_column(String(50), nullable=True)
    tier1_tokens: Mapped[int] = mapped_column(Integer, nullable=True)

    # Tier 2 (GPT-4o) 결과
    tier2_action: Mapped[str] = mapped_column(
        SAEnum("STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL", name="action"),
        nullable=True,
    )
    tier2_rationale: Mapped[str] = mapped_column(Text, nullable=True)
    tier2_target_price: Mapped[int] = mapped_column(Integer, nullable=True)
    tier2_stop_loss: Mapped[int] = mapped_column(Integer, nullable=True)
    tier2_impact_duration: Mapped[str] = mapped_column(String(50), nullable=True)
    tier2_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    tier2_model: Mapped[str] = mapped_column(String(50), nullable=True)
    tier2_tokens: Mapped[int] = mapped_column(Integer, nullable=True)

    escalated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
