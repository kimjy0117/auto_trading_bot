"""
외국인·기관 수급 데이터 서비스.

정규장(09:00~15:30) 동안 KIS REST API를 폴링하여
외국인/기관 순매수 상위 종목 데이터를 수집하고 Redis에 캐싱한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time
from typing import Any

import httpx

from backend.config import get_settings
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

_POLL_INTERVAL = 60  # 1분
_CACHE_TTL = 90      # 1분 30초 (폴링 주기보다 약간 길게)
_FLOW_KEY_PREFIX = "investor_flow"


class InvestorFlowService:
    """외국인·기관 투자자 수급 서비스."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._access_token: str | None = None
        self._token_expires: datetime | None = None

    async def _ensure_token(self) -> str:
        """KIS OAuth 토큰을 발급/갱신."""
        now = datetime.now()
        if self._access_token and self._token_expires and now < self._token_expires:
            return self._access_token

        url = f"{settings.kis_base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        from datetime import timedelta
        self._token_expires = now + timedelta(seconds=expires_in - 600)

        logger.debug("KIS 수급조회 토큰 발급/갱신 완료")
        return self._access_token

    def _build_headers(self, token: str, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": tr_id,
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("수급 데이터 서비스 시작")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("수급 데이터 서비스 중지")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                now = datetime.now().time()
                if time(9, 0) <= now <= time(15, 30):
                    await self._poll_flow_data()
                else:
                    logger.debug("수급 폴링 — 정규장(09:00~15:30) 외, 대기")
            except Exception as exc:
                logger.error(f"수급 데이터 폴링 에러: {exc}")

            await asyncio.sleep(_POLL_INTERVAL)

    async def _poll_flow_data(self) -> None:
        """외국인/기관 순매수 상위 종목을 조회하여 Redis에 저장."""
        token = await self._ensure_token()
        r = await get_redis()

        for investor_type, tr_id, label in [
            ("foreign", "FHPST01710000", "외국인"),
            ("institution", "FHPST01720000", "기관"),
        ]:
            await self._fetch_and_cache(token, r, investor_type, tr_id, label)

    async def _fetch_and_cache(
        self, token: str, r: Any, investor_type: str, tr_id: str, label: str,
    ) -> None:
        """단일 투자자 유형의 순매수/순매도 데이터를 조회."""
        url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/investor-trend"
        headers = self._build_headers(token, tr_id)

        for buy_sell, bs_label in [("1", "순매수"), ("2", "순매도")]:
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": "0000",
                "FID_DIV_CLS_CODE": buy_sell,
                "FID_RANK_SORT_CLS_CODE": "0",
                "FID_ETC_CLS_CODE": "",
            }

            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                items = data.get("output", [])
                for item in items:
                    stock_code = item.get("stck_shrn_iscd", "")
                    if not stock_code:
                        continue

                    net_key = f"net_buy" if buy_sell == "1" else "net_sell"
                    volume = int(item.get("seln_qty", 0) or 0) if buy_sell == "2" else int(item.get("shnu_qty", 0) or 0)
                    amount = int(item.get("seln_tr_pbmn", 0) or 0) if buy_sell == "2" else int(item.get("shnu_tr_pbmn", 0) or 0)

                    flow_key = f"{_FLOW_KEY_PREFIX}:{stock_code}"
                    field_prefix = f"{investor_type}_{net_key}"

                    await r.hset(flow_key, mapping={
                        f"{field_prefix}_volume": str(volume),
                        f"{field_prefix}_amount": str(amount),
                        f"{investor_type}_type": label,
                        "updated_at": datetime.now().isoformat(),
                    })
                    await r.expire(flow_key, _CACHE_TTL)

            except httpx.HTTPStatusError as exc:
                logger.error(f"{label} {bs_label} 조회 HTTP 에러: {exc.response.status_code}")
            except Exception as exc:
                logger.error(f"{label} {bs_label} 조회 실패: {exc}")

    async def get_investor_flow(self, stock_code: str) -> dict:
        """특정 종목의 외국인/기관 수급 데이터 반환."""
        r = await get_redis()
        data = await r.hgetall(f"{_FLOW_KEY_PREFIX}:{stock_code}")
        if not data:
            return {"foreign_net": 0, "institution_net": 0}

        def _safe_int(key: str) -> int:
            return int(data.get(key, 0) or 0)

        foreign_net = _safe_int("foreign_net_buy_amount") - _safe_int("foreign_net_sell_amount")
        institution_net = _safe_int("institution_net_buy_amount") - _safe_int("institution_net_sell_amount")

        return {
            "foreign_net": foreign_net,
            "institution_net": institution_net,
            "foreign_buy_volume": _safe_int("foreign_net_buy_volume"),
            "foreign_sell_volume": _safe_int("foreign_net_sell_volume"),
            "institution_buy_volume": _safe_int("institution_net_buy_volume"),
            "institution_sell_volume": _safe_int("institution_net_sell_volume"),
            "updated_at": data.get("updated_at", ""),
        }
