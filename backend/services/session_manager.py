from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum

import holidays

from backend.config import get_settings
from backend.utils.logger import logger

settings = get_settings()
_kr_holidays = holidays.KR()


class MarketSession(str, Enum):
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    PRE_MARKET_BREAK = "PRE_BREAK"
    REGULAR = "REGULAR"
    CLOSING_BREAK = "CLOSE_BREAK"
    CLOSING_AUCTION = "CLOSING"
    AFTER_MARKET = "AFTER_MARKET"
    DAILY_CLEANUP = "CLEANUP"


SESSION_PARAMS: dict[str, dict] = {
    "PRE_MARKET": {
        "exchange": "NXT",
        "buy_score_threshold": 80,
        "max_position_pct": 10,
        "max_concurrent_positions": 1,
        "atr_stop_multiplier": 2.5,
        "atr_trailing_multiplier": 1.5,
        "time_cut_minutes": None,
        "cooldown_minutes": 30,
        "nxt_only": True,
        "use_investor_flow": False,
        "tech_indicators": ["rsi", "atr", "volume"],
        "volume_min_ratio": 200,
    },
    "REGULAR": {
        "exchange": "SOR",
        "buy_score_threshold": 70,
        "max_position_pct": 20,
        "max_concurrent_positions": 3,
        "atr_stop_multiplier": 2.0,
        "atr_trailing_multiplier": 1.0,
        "time_cut_minutes": "dynamic",
        "cooldown_minutes": 30,
        "nxt_only": False,
        "use_investor_flow": True,
        "tech_indicators": "all",
        "volume_min_ratio": 300,
    },
    "AFTER_MARKET": {
        "exchange": "NXT",
        "buy_score_threshold": 85,
        "max_position_pct": 8,
        "max_concurrent_positions": 1,
        "atr_stop_multiplier": 3.0,
        "atr_trailing_multiplier": 2.0,
        "time_cut_minutes": 15,
        "cooldown_minutes": 30,
        "nxt_only": True,
        "use_investor_flow": False,
        "tech_indicators": ["rsi", "atr", "volume"],
        "volume_min_ratio": 150,
    },
}

SCORING_WEIGHTS: dict[str, dict[str, int]] = {
    "PRE_MARKET": {"ai": 40, "flow": 0, "tech": 20, "volume": 25, "market": 15},
    "REGULAR": {"ai": 30, "flow": 20, "tech": 25, "volume": 15, "market": 10},
    "CLOSING": {"ai": 30, "flow": 20, "tech": 25, "volume": 15, "market": 10},
    "AFTER_MARKET": {"ai": 40, "flow": 0, "tech": 20, "volume": 25, "market": 15},
}

_SESSION_SCHEDULE: list[tuple[time, time, MarketSession]] = [
    (time(8, 0), time(8, 49, 59), MarketSession.PRE_MARKET),
    (time(8, 50), time(9, 0, 29), MarketSession.PRE_MARKET_BREAK),
    (time(9, 0, 30), time(15, 19, 59), MarketSession.REGULAR),
    (time(15, 20), time(15, 29, 59), MarketSession.CLOSING_BREAK),
    (time(15, 30), time(15, 39, 59), MarketSession.CLOSING_AUCTION),
    (time(15, 40), time(19, 59, 59), MarketSession.AFTER_MARKET),
    (time(20, 0), time(20, 9, 59), MarketSession.DAILY_CLEANUP),
]

_BUY_ALLOWED_SESSIONS = {
    MarketSession.PRE_MARKET,
    MarketSession.REGULAR,
    MarketSession.AFTER_MARKET,
}

_NXT_SESSIONS = {
    MarketSession.PRE_MARKET,
    MarketSession.AFTER_MARKET,
}


def get_current_session() -> MarketSession:
    now = datetime.now().time()
    for start, end, session in _SESSION_SCHEDULE:
        if start <= now <= end:
            return session
    return MarketSession.CLOSED


def is_trading_day(target_date: date | None = None) -> bool:
    d = target_date or date.today()
    if d.weekday() >= 5:
        return False
    if d in _kr_holidays:
        return False
    return True


def is_nxt_session(session: MarketSession | None = None) -> bool:
    if session is None:
        session = get_current_session()
    return session in _NXT_SESSIONS


def is_buy_allowed(session: MarketSession | None = None) -> bool:
    if session is None:
        session = get_current_session()
    if not is_trading_day():
        return False
    return session in _BUY_ALLOWED_SESSIONS


def get_session_params(session: MarketSession | None = None) -> dict:
    if session is None:
        session = get_current_session()
    key = session.value
    if key in ("PRE_BREAK", "CLOSE_BREAK", "CLEANUP", "CLOSED"):
        return SESSION_PARAMS["REGULAR"]
    if key == "CLOSING":
        return SESSION_PARAMS["REGULAR"]
    return SESSION_PARAMS.get(key, SESSION_PARAMS["REGULAR"])


def get_scoring_weights(session: MarketSession | None = None) -> dict[str, int]:
    if session is None:
        session = get_current_session()
    key = session.value
    if key in SCORING_WEIGHTS:
        return SCORING_WEIGHTS[key]
    return SCORING_WEIGHTS["REGULAR"]
