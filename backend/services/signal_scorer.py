from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from backend.database import async_session
from backend.models import NewsAnalysis, SignalScore, Position, MarketSnapshot
from backend.redis_client import get_redis
from backend.services.risk_manager import RiskManager
from backend.services.session_manager import (
    MarketSession,
    SCORING_WEIGHTS,
    get_current_session,
    get_session_params,
    get_scoring_weights,
)
from backend.utils.logger import logger

_risk = RiskManager()

_MIN_MARKET_CAP = 1000_0000_0000  # 1000억


class SignalScorer:
    """세션별 가중 스코어링 엔진."""

    async def score_signal(
        self,
        news_analysis: NewsAnalysis,
        market_data: dict[str, Any],
        investor_data: dict[str, Any] | None = None,
        session: MarketSession | None = None,
    ) -> SignalScore:
        if session is None:
            session = get_current_session()

        stock_code = news_analysis.stock_code or ""
        weights = get_scoring_weights(session)

        passed, reason = await self._hard_filter(stock_code, session)

        if passed:
            ai = self._calc_ai_score(news_analysis)
            inv = self._calc_investor_score(investor_data) if investor_data else 0.0
            tech = self._calc_technical_score(market_data)
            vol = self._calc_volume_score(market_data)
            mkt = await self._calc_market_env_score()

            total = (
                ai * weights["ai"] / 100
                + inv * weights["flow"] / 100
                + tech * weights["tech"] / 100
                + vol * weights["volume"] / 100
                + mkt * weights["market"] / 100
            )
            sp = get_session_params(session)
            threshold = sp.get("buy_score_threshold", sp.get("threshold", 70))
            decision = "BUY" if total >= threshold else "WATCH"
        else:
            ai = inv = tech = vol = mkt = total = 0.0
            decision = "SKIP"

        score = SignalScore(
            stock_code=stock_code,
            stock_name=news_analysis.stock_name,
            news_analysis_id=news_analysis.id,
            session=session.value,
            nxt_eligible=session in (MarketSession.PRE_MARKET, MarketSession.AFTER_MARKET),
            ai_score=round(ai, 2),
            investor_flow_score=round(inv, 2),
            technical_score=round(tech, 2),
            volume_score=round(vol, 2),
            market_env_score=round(mkt, 2),
            total_score=round(total, 2),
            hard_filter_passed=passed,
            hard_filter_reason=reason if not passed else None,
            score_detail={
                "weights": weights,
                "raw": {"ai": ai, "inv": inv, "tech": tech, "vol": vol, "mkt": mkt},
            },
            decision=decision,
            decision_reason=reason if not passed else f"총점 {total:.1f}",
        )

        async with async_session() as db:
            db.add(score)
            await db.commit()
            await db.refresh(score)

        logger.info(
            f"[Score] {stock_code} | {session.value} | "
            f"total={total:.1f} decision={decision} "
            f"(ai={ai:.1f} inv={inv:.1f} tech={tech:.1f} vol={vol:.1f} mkt={mkt:.1f})"
        )
        return score

    # ── Hard Filter ──────────────────────────────────────

    async def _hard_filter(
        self,
        stock_code: str,
        session: MarketSession,
    ) -> tuple[bool, str]:
        if not stock_code:
            return False, "종목코드 미식별"

        if await _risk.check_cooldown(stock_code):
            return False, "쿨다운 중"

        if await _risk.check_daily_loss_limit():
            return False, "일일 손실 한도 초과"

        if await _risk.check_position_limit(session):
            return False, "포지션 한도 초과"

        if await _risk.check_sector_diversification(stock_code):
            return False, "동일 섹터 과다"

        redis = await get_redis()
        cap_str = await redis.get(f"market_cap:{stock_code}")
        if cap_str:
            market_cap = int(float(cap_str))
            if market_cap < _MIN_MARKET_CAP:
                return False, f"시가총액 부족 ({market_cap / 1_0000_0000:.0f}억)"

        return True, ""

    # ── 개별 스코어 계산 (0~100) ──────────────────────────

    @staticmethod
    def _calc_ai_score(news: NewsAnalysis) -> float:
        base = 0.0

        impact_map = {"HIGH": 40, "MEDIUM": 25, "LOW": 10, "NONE": 0}
        base += impact_map.get(news.tier1_impact or "NONE", 0)

        direction_map = {"POSITIVE": 20, "NEUTRAL": 5, "NEGATIVE": -10}
        base += direction_map.get(news.tier1_direction or "NEUTRAL", 0)

        base += (news.tier1_confidence or 0) * 15

        if news.tier2_action:
            action_map = {"STRONG_BUY": 25, "BUY": 15, "HOLD": 0, "SELL": -15, "STRONG_SELL": -25}
            base += action_map.get(news.tier2_action, 0)

        return max(0.0, min(100.0, base))

    @staticmethod
    def _calc_investor_score(investor_data: dict[str, Any] | None) -> float:
        if not investor_data:
            return 50.0

        foreign_net = investor_data.get("foreign_net", 0)
        inst_net = investor_data.get("institution_net", 0)

        score = 50.0
        if foreign_net > 0:
            score += min(25.0, foreign_net / 1_0000_0000)
        else:
            score -= min(25.0, abs(foreign_net) / 1_0000_0000)

        if inst_net > 0:
            score += min(25.0, inst_net / 1_0000_0000)
        else:
            score -= min(25.0, abs(inst_net) / 1_0000_0000)

        return max(0.0, min(100.0, score))

    @staticmethod
    def _calc_technical_score(market_data: dict[str, Any]) -> float:
        score = 50.0

        rsi = market_data.get("rsi_14")
        if rsi is not None:
            if 40 <= rsi <= 60:
                score += 10
            elif 30 <= rsi < 40:
                score += 15  # 과매도 반등 기대
            elif rsi < 30:
                score += 5   # 너무 과매도는 약간만
            elif rsi > 70:
                score -= 15

        macd = market_data.get("macd")
        macd_signal = market_data.get("macd_signal")
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                score += 10
            else:
                score -= 10

        ma5 = market_data.get("ma_5")
        ma20 = market_data.get("ma_20")
        ma60 = market_data.get("ma_60")
        if ma5 and ma20 and ma60:
            if ma5 > ma20 > ma60:
                score += 15  # 정배열
            elif ma5 < ma20 < ma60:
                score -= 15  # 역배열

        return max(0.0, min(100.0, score))

    @staticmethod
    def _calc_volume_score(market_data: dict[str, Any]) -> float:
        score = 50.0
        volume_ratio = market_data.get("volume_ratio")
        if volume_ratio is not None:
            if volume_ratio >= 3.0:
                score += 30
            elif volume_ratio >= 2.0:
                score += 20
            elif volume_ratio >= 1.5:
                score += 10
            elif volume_ratio < 0.5:
                score -= 20

        return max(0.0, min(100.0, score))

    @staticmethod
    async def _calc_market_env_score() -> float:
        """코스피 전체 환경 점수 (Redis 캐시 기반)."""
        redis = await get_redis()
        kospi_change = await redis.get("market:kospi_change_pct")
        if kospi_change is None:
            return 50.0

        change = float(kospi_change)
        score = 50.0 + change * 10
        return max(0.0, min(100.0, score))
