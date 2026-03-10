from __future__ import annotations

import time as _time
from typing import Any

import httpx

from backend.config import get_settings
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

_EXCHANGE_SUFFIX = {
    "NXT": "_NX",
    "SOR": "_AL",
    "KRX": "",
}


class KISApi:
    """한국투자증권 KIS OpenAPI async wrapper."""

    def __init__(self) -> None:
        self._base_url = settings.kis_base_url
        self._app_key = settings.kis_app_key
        self._app_secret = settings.kis_app_secret
        self._account_no = settings.kis_account_no
        self._account_product = settings.kis_account_product
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(15.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── OAuth 토큰 ───────────────────────────────────────

    async def _get_access_token(self) -> str:
        redis = await get_redis()
        cached = await redis.get("kis:access_token")
        if cached:
            return cached

        client = await self._get_client()
        resp = await client.post(
            "/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 86400)

        await redis.setex("kis:access_token", int(expires_in) - 60, token)
        logger.info("KIS 액세스 토큰 갱신 완료")
        return token

    # ── 기본 요청 ────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        tr_id: str = "",
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "Content-Type": "application/json; charset=utf-8",
        }
        if tr_id:
            headers["tr_id"] = tr_id

        client = await self._get_client()
        start = _time.monotonic()

        if method.upper() == "GET":
            resp = await client.get(path, headers=headers, params=params)
        else:
            resp = await client.post(path, headers=headers, json=data)

        elapsed = (_time.monotonic() - start) * 1000
        logger.debug(f"KIS {method} {path} → {resp.status_code} ({elapsed:.0f}ms)")
        resp.raise_for_status()
        return resp.json()

    # ── 주문 ─────────────────────────────────────────────

    def _build_stock_code(self, stock_code: str, exchange: str) -> str:
        suffix = _EXCHANGE_SUFFIX.get(exchange, "")
        return f"{stock_code}{suffix}"

    async def buy_order(
        self,
        stock_code: str,
        qty: int,
        price: int,
        exchange: str = "SOR",
    ) -> dict[str, Any]:
        kis_code = self._build_stock_code(stock_code, exchange)
        body = {
            "CANO": self._account_no,
            "ACNT_PRDT_CD": self._account_product,
            "PDNO": kis_code,
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        tr_id = "TTTC0802U"
        logger.info(f"매수 주문: {stock_code} {qty}주 @ {price:,}원 (거래소={exchange})")
        result = await self._request("POST", "/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, data=body)
        return result

    async def sell_order(
        self,
        stock_code: str,
        qty: int,
        price: int,
        exchange: str = "SOR",
    ) -> dict[str, Any]:
        kis_code = self._build_stock_code(stock_code, exchange)
        body = {
            "CANO": self._account_no,
            "ACNT_PRDT_CD": self._account_product,
            "PDNO": kis_code,
            "ORD_DVSN": "00",
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        tr_id = "TTTC0801U"
        logger.info(f"매도 주문: {stock_code} {qty}주 @ {price:,}원 (거래소={exchange})")
        result = await self._request("POST", "/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, data=body)
        return result

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        body = {
            "CANO": self._account_no,
            "ACNT_PRDT_CD": self._account_product,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_id,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 취소
            "ORD_QTY": "0",
            "ORD_UNPR": "0",
            "QTY_ALL_ORD_YN": "Y",
        }
        tr_id = "TTTC0803U"
        logger.info(f"주문 취소: {order_id}")
        return await self._request("POST", "/uapi/domestic-stock/v1/trading/order-rvsecncl", tr_id=tr_id, data=body)

    # ── 조회 ─────────────────────────────────────────────

    async def get_balance(self) -> dict[str, Any]:
        params = {
            "CANO": self._account_no,
            "ACNT_PRDT_CD": self._account_product,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        tr_id = "TTTC8434R"
        return await self._request("GET", "/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)

    async def get_current_price(self, stock_code: str) -> dict[str, Any]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        tr_id = "FHKST01010100"
        return await self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-price", tr_id=tr_id, params=params)

    async def get_orderbook(self, stock_code: str, exchange: str = "SOR") -> dict[str, Any]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        tr_id = "FHKST01010200"
        return await self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn", tr_id=tr_id, params=params)

    async def get_investor_flow(self, stock_code: str) -> dict[str, Any]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        }
        tr_id = "FHKST01010900"
        return await self._request("GET", "/uapi/domestic-stock/v1/quotations/inquire-investor", tr_id=tr_id, params=params)
