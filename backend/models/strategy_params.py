from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class StrategyParams(Base):
    __tablename__ = "strategy_params"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    param_value: Mapped[str] = mapped_column(Text, nullable=True)
    param_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
