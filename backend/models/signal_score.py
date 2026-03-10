from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, Enum as SAEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class SignalScore(Base):
    __tablename__ = "signal_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    stock_name: Mapped[str] = mapped_column(String(100), nullable=True)
    news_analysis_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)

    session: Mapped[str] = mapped_column(
        SAEnum("PRE_MARKET", "REGULAR", "AFTER_MARKET", name="signal_session"),
        nullable=False,
    )
    nxt_eligible: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # 개별 점수
    ai_score: Mapped[float] = mapped_column(Float, default=0)
    investor_flow_score: Mapped[float] = mapped_column(Float, default=0)
    technical_score: Mapped[float] = mapped_column(Float, default=0)
    volume_score: Mapped[float] = mapped_column(Float, default=0)
    market_env_score: Mapped[float] = mapped_column(Float, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0, index=True)

    # Hard 필터 결과
    hard_filter_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    hard_filter_reason: Mapped[str] = mapped_column(String(200), nullable=True)

    # 상세 데이터
    score_detail: Mapped[dict] = mapped_column(JSON, nullable=True)
    decision: Mapped[str] = mapped_column(
        SAEnum("BUY", "SKIP", "WATCH", name="signal_decision"),
        nullable=True,
    )
    decision_reason: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
