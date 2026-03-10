"""
DART(전자공시) 모니터링 모듈.

DART OpenAPI를 1분 간격으로 폴링하여 신규 공시를 감지하고,
종목코드 추출 후 AI 분석 콜백을 트리거한다.
09:00~18:00 사이에만 동작한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time
from typing import Any

import httpx

from backend.config import get_settings
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

_DART_BASE = "https://opendart.fss.or.kr/api"
_POLL_INTERVAL = 60  # 1분

_RELEVANT_REPORT_TYPES = frozenset([
    "A",   # 사업보고서
    "B",   # 반기보고서
    "C",   # 분기보고서
    "D",   # 등록법인 결산서류
    "F",   # 주요사항보고
    "G",   # 발행공시
    "I",   # 지분공시
    "J",   # 기타공시
])

_RELEVANT_KEYWORDS = [
    "실적", "매출", "영업이익", "순이익", "적자전환", "흑자전환",
    "주요사항", "공정공시", "자기주식", "무상증자", "유상증자",
    "합병", "분할", "대규모", "수주", "계약", "투자",
    "최대주주", "지분변동", "배당",
]

OnDisclosureCallback = Callable[[dict[str, Any]], Awaitable[None]]


class DartMonitor:
    """DART 공시 모니터."""

    def __init__(self, on_disclosure: OnDisclosureCallback | None = None) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self.on_disclosure = on_disclosure

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("DART 모니터 시작")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DART 모니터 중지")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                now = datetime.now().time()
                if time(9, 0) <= now <= time(18, 0):
                    await self._poll_disclosures()
                else:
                    logger.debug("DART 폴링 — 운영시간(09~18시) 외, 대기")
            except Exception as exc:
                logger.error(f"DART 폴링 에러: {exc}")

            await asyncio.sleep(_POLL_INTERVAL)

    async def _poll_disclosures(self) -> None:
        """DART API에서 당일 최신 공시를 조회."""
        if not settings.dart_api_key:
            return

        r = await get_redis()
        today_str = datetime.now().strftime("%Y%m%d")
        params = {
            "crtfc_key": settings.dart_api_key,
            "bgn_de": today_str,
            "end_de": today_str,
            "page_count": "100",
            "sort": "date",
            "sort_mth": "desc",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{_DART_BASE}/list.json", params=params)
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") != "000":
                logger.debug(f"DART 응답 상태: {data.get('status')} / {data.get('message')}")
                return

            items = data.get("list", [])
            for item in items:
                rcept_no = item.get("rcept_no", "")
                already = await r.sismember("dart:processed", rcept_no)
                if already:
                    continue

                if self._is_relevant(item):
                    await r.sadd("dart:processed", rcept_no)
                    await r.expire("dart:processed", 60 * 60 * 24)
                    await self._process_disclosure(item)

        except httpx.HTTPStatusError as exc:
            logger.error(f"DART API HTTP 에러: {exc.response.status_code}")
        except Exception as exc:
            logger.error(f"DART 공시 조회 실패: {exc}")

    def _is_relevant(self, item: dict) -> bool:
        """공시가 매매에 영향을 줄 만한 유형인지 필터링."""
        report_nm = item.get("report_nm", "")
        pblntf_ty = item.get("pblntf_ty", "")

        if pblntf_ty and pblntf_ty in _RELEVANT_REPORT_TYPES:
            return True

        return any(kw in report_nm for kw in _RELEVANT_KEYWORDS)

    async def _process_disclosure(self, item: dict) -> None:
        """추출된 공시를 분석 파이프라인으로 전달."""
        stock_code = item.get("stock_code", "").strip()
        corp_name = item.get("corp_name", "")
        report_nm = item.get("report_nm", "")
        rcept_no = item.get("rcept_no", "")
        rcept_dt = item.get("rcept_dt", "")

        if not stock_code:
            logger.debug(f"DART 공시 종목코드 없음: {report_nm} / {corp_name}")
            return

        disclosure_data: dict[str, Any] = {
            "source": "DART",
            "stock_code": stock_code,
            "stock_name": corp_name,
            "report_name": report_nm,
            "rcept_no": rcept_no,
            "rcept_date": rcept_dt,
            "raw_text": f"[DART] {corp_name} - {report_nm}",
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(f"DART 공시 감지 — {corp_name}({stock_code}): {report_nm}")

        if self.on_disclosure:
            await self.on_disclosure(disclosure_data)
