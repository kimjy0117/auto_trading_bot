from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.database import async_session
from backend.models import NewsAnalysis
from backend.services.session_manager import get_current_session
from backend.utils.logger import logger

settings = get_settings()
_openai = AsyncOpenAI(api_key=settings.openai_api_key)


class AIAnalyzer:
    """2-Tier AI 뉴스 분석기.

    Tier 1: GPT-4o-mini 빠른 스크리닝 (전 건)
    Tier 2: GPT-4o 정밀 분석 (HIGH/MEDIUM만)
    """

    # ── Tier 1 ───────────────────────────────────────────

    async def analyze_tier1(
        self,
        raw_text: str,
        source: str,
        channel: str | None = None,
    ) -> NewsAnalysis:
        prompt = self._build_tier1_prompt(raw_text, source)

        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )

        content = response.choices[0].message.content or "{}"
        usage = response.usage
        total_tokens = usage.total_tokens if usage else 0
        parsed = self._safe_parse_json(content)

        news = NewsAnalysis(
            stock_code=parsed.get("stock_code"),
            stock_name=parsed.get("stock_name"),
            source=source,
            channel=channel,
            raw_text=raw_text,
            tier1_impact=parsed.get("impact", "NONE"),
            tier1_direction=parsed.get("direction", "NEUTRAL"),
            tier1_summary=parsed.get("summary", ""),
            tier1_confidence=parsed.get("confidence", 0.0),
            tier1_model="gpt-4o-mini",
            tier1_tokens=total_tokens,
            escalated=parsed.get("impact") in ("HIGH", "MEDIUM"),
        )

        async with async_session() as db:
            db.add(news)
            await db.commit()
            await db.refresh(news)

        logger.info(
            f"[Tier1] {news.stock_code or '미식별'} | "
            f"impact={news.tier1_impact} dir={news.tier1_direction} "
            f"conf={news.tier1_confidence:.2f} tokens={total_tokens}"
        )
        return news

    # ── Tier 2 ───────────────────────────────────────────

    async def analyze_tier2(
        self,
        news_analysis: NewsAnalysis,
        market_context: dict[str, Any],
    ) -> NewsAnalysis:
        if news_analysis.tier1_impact not in ("HIGH", "MEDIUM"):
            logger.debug(f"[Tier2] 스킵 — impact={news_analysis.tier1_impact}")
            return news_analysis

        session = get_current_session()
        market_context["session"] = session.value

        prompt = self._build_tier2_prompt(news_analysis, market_context)

        response = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=800,
        )

        content = response.choices[0].message.content or "{}"
        usage = response.usage
        total_tokens = usage.total_tokens if usage else 0
        parsed = self._safe_parse_json(content)

        async with async_session() as db:
            merged = await db.merge(news_analysis)
            merged.tier2_action = parsed.get("action", "HOLD")
            merged.tier2_rationale = parsed.get("rationale", "")
            raw_target = parsed.get("target_price")
            merged.tier2_target_price = int(raw_target) if raw_target is not None else None
            raw_stop = parsed.get("stop_loss")
            merged.tier2_stop_loss = int(raw_stop) if raw_stop is not None else None
            merged.tier2_impact_duration = parsed.get("impact_duration", "hours")
            merged.tier2_confidence = parsed.get("confidence", 0.0)
            merged.tier2_model = "gpt-4o"
            merged.tier2_tokens = total_tokens
            await db.commit()
            await db.refresh(merged)
            news_analysis = merged

        logger.info(
            f"[Tier2] {news_analysis.stock_code} | "
            f"action={news_analysis.tier2_action} "
            f"target={news_analysis.tier2_target_price} "
            f"stop={news_analysis.tier2_stop_loss} "
            f"tokens={total_tokens}"
        )
        return news_analysis

    # ── 프롬프트 빌더 ────────────────────────────────────

    @staticmethod
    def _build_tier1_prompt(raw_text: str, source: str) -> dict[str, str]:
        system = (
            "너는 한국 주식시장 전문 뉴스 분석가야. "
            "주어진 뉴스/공시를 분석하여 JSON으로 응답해.\n\n"
            "반드시 아래 키를 포함한 JSON만 출력:\n"
            "{\n"
            '  "stock_code": "종목코드 6자리 또는 null",\n'
            '  "stock_name": "종목명 또는 null",\n'
            '  "impact": "HIGH | MEDIUM | LOW | NONE",\n'
            '  "direction": "POSITIVE | NEGATIVE | NEUTRAL",\n'
            '  "summary": "1~2문장 한국어 요약",\n'
            '  "confidence": 0.0~1.0\n'
            "}\n\n"
            "판단 기준:\n"
            "- HIGH: 실적 서프라이즈, 대규모 M&A, 정부 정책 수혜, 대형 수주\n"
            "- MEDIUM: 업종 호재, 신사업 진출, 경영진 변동\n"
            "- LOW: 단순 루머, 시장 일반 뉴스\n"
            "- NONE: 주식과 무관하거나 판단 불가\n"
            "종목을 특정할 수 없으면 stock_code와 stock_name을 null로."
        )
        user = f"[출처: {source}]\n\n{raw_text}"
        return {"system": system, "user": user}

    @staticmethod
    def _build_tier2_prompt(
        news: NewsAnalysis,
        context: dict[str, Any],
    ) -> dict[str, str]:
        ctx_str = json.dumps(context, ensure_ascii=False, default=str)
        system = (
            "너는 한국 주식시장 퀀트 애널리스트야. "
            "Tier1 분석 결과와 시장 컨텍스트를 종합하여 매매 판단을 내려.\n\n"
            "반드시 아래 키를 포함한 JSON만 출력:\n"
            "{\n"
            '  "action": "STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL",\n'
            '  "rationale": "판단 근거 2~3문장",\n'
            '  "target_price": 목표가(정수) 또는 null,\n'
            '  "stop_loss": 손절가(정수) 또는 null,\n'
            '  "impact_duration": "minutes | hours | days",\n'
            '  "confidence": 0.0~1.0\n'
            "}\n\n"
            "고려 사항:\n"
            "- 현재 세션(PRE_MARKET/REGULAR/AFTER_MARKET)에 따라 유동성·스프레드 감안\n"
            "- 기술적 지표(RSI, MACD, 이평선)와 수급 데이터 반영\n"
            "- 뉴스 임팩트 지속 시간 현실적 추정\n"
            "- HOLD는 확신이 부족할 때, SELL/STRONG_SELL은 악재일 때"
        )
        user = (
            f"종목: {news.stock_name} ({news.stock_code})\n"
            f"Tier1 요약: {news.tier1_summary}\n"
            f"Tier1 영향도: {news.tier1_impact} / 방향: {news.tier1_direction}\n"
            f"Tier1 확신도: {news.tier1_confidence}\n\n"
            f"시장 컨텍스트:\n{ctx_str}"
        )
        return {"system": system, "user": user}

    @staticmethod
    def _safe_parse_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"AI JSON 파싱 실패: {text[:200]}")
            return {}
