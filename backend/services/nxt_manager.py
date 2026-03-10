"""
NXT(넥스트) 거래소 종목 관리 모듈.

NXT 대상 약 800종목 리스트를 Redis에 캐싱하고,
거래소별 종목코드 변환을 제공한다.
"""

from __future__ import annotations

import httpx

from backend.config import get_settings
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

_REDIS_KEY = "nxt_stocks"
_NXT_LIST_TTL = 60 * 60 * 12  # 12시간


class NXTManager:
    """NXT 대상종목 관리."""

    def __init__(self) -> None:
        self._headers: dict[str, str] = {}

    async def _ensure_headers(self) -> dict[str, str]:
        if not self._headers:
            self._headers = {
                "content-type": "application/json; charset=utf-8",
                "appkey": settings.kis_app_key,
                "appsecret": settings.kis_app_secret,
            }
        return self._headers

    async def refresh_nxt_stocks(self) -> int:
        """KIS API에서 NXT 대상종목을 조회하여 Redis Set에 저장."""
        r = await get_redis()
        headers = await self._ensure_headers()

        url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/nxt-eligible"
        params = {"FID_COND_MRKT_DIV_CODE": "J"}
        headers_with_tr = {**headers, "tr_id": "FHPST01710000"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers_with_tr, params=params)
                resp.raise_for_status()
                data = resp.json()

            items = data.get("output", [])
            if not items:
                logger.warning("NXT 대상종목 리스트가 비어 있음")
                return 0

            stock_codes = [item["stck_shrn_iscd"] for item in items if item.get("stck_shrn_iscd")]

            pipe = r.pipeline()
            await pipe.delete(_REDIS_KEY)
            if stock_codes:
                await pipe.sadd(_REDIS_KEY, *stock_codes)
                await pipe.expire(_REDIS_KEY, _NXT_LIST_TTL)
            await pipe.execute()

            logger.info(f"NXT 대상종목 {len(stock_codes)}개 갱신 완료")
            return len(stock_codes)

        except httpx.HTTPStatusError as exc:
            logger.error(f"NXT 종목 조회 HTTP 에러: {exc.response.status_code}")
        except Exception as exc:
            logger.error(f"NXT 종목 조회 실패: {exc}")
        return 0

    async def is_nxt_eligible(self, stock_code: str) -> bool:
        """해당 종목이 NXT 거래 대상인지 확인."""
        r = await get_redis()
        return await r.sismember(_REDIS_KEY, stock_code)

    @staticmethod
    def get_stock_code_for_exchange(stock_code: str, exchange: str) -> str:
        """거래소별 종목코드 형식 변환.

        KRX → 원본, NXT → "{code}_NX", SOR → "{code}_AL"
        """
        base = stock_code.split("_")[0]
        exchange_upper = exchange.upper()
        if exchange_upper == "NXT":
            return f"{base}_NX"
        if exchange_upper == "SOR":
            return f"{base}_AL"
        return base

    async def get_all_nxt_stocks(self) -> list[str]:
        """Redis에 저장된 NXT 대상종목 전체 반환."""
        r = await get_redis()
        members = await r.smembers(_REDIS_KEY)
        return sorted(members) if members else []
