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

        # 통합 API 사용 (FHPTJ04400000)
        await self._fetch_and_cache_total(token, r)

    async def _fetch_and_cache_total(self, token: str, r: Any) -> None:
        """외국인/기관 매매종목 가집계(FHPTJ04400000) 조회 및 캐싱."""
        url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        tr_id = "FHPTJ04400000"
        headers = self._build_headers(token, tr_id)

        # 파라미터 설정 (가집계 조회용)
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",      # 시장 구분 (J: 전체)
            "FID_COND_SCR_DIV_CODE": "16449",   # 화면 번호
            "FID_INPUT_ISCD": "0000",           # 종목 코드 (0000: 전체)
            "FID_DIV_CLS_CODE": "0",            # 분류 코드
            "FID_BLNG_CLS_CODE": "0",           # 소속 코드
            "FID_TRGT_CLS_CODE": "11111111",    # 대상 코드
            "FID_TRGT_EXLS_CLS_CODE": "000000", # 제외 코드
            "FID_INPUT_PRICE_1": "",            # 가격 범위 시작
            "FID_INPUT_PRICE_2": "",            # 가격 범위 끝
            "FID_VOL_CNT": "",                  # 거래량 조건
            "FID_INPUT_DATE_1": ""              # 날짜 조건
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

            items = data.get("output", [])
            if not items:
                logger.debug("수급 데이터 없음 (output 비어있음)")
                return

            # 디버깅용: 첫 번째 아이템의 키 출력 (필드명 확인)
            # logger.debug(f"수급 데이터 샘플 키: {items[0].keys()}")

            count = 0
            for item in items:
                stock_code = item.get("stck_shrn_iscd", "")
                if not stock_code:
                    continue

                # 필드명 매핑 (API 응답 필드명에 따라 조정 필요할 수 있음)
                # frgn_ntby_tr_pbmn: 외국인 순매수 거래대금
                # orgn_ntby_tr_pbmn: 기관 순매수 거래대금
                # (값이 없으면 0 처리)
                foreign_net_amount = int(item.get("frgn_ntby_tr_pbmn", 0) or 0)
                institution_net_amount = int(item.get("orgn_ntby_tr_pbmn", 0) or 0)
                
                # 수량 데이터도 있으면 저장 (옵션)
                foreign_net_vol = int(item.get("frgn_ntby_qty", 0) or 0)
                institution_net_vol = int(item.get("orgn_ntby_qty", 0) or 0)

                flow_key = f"{_FLOW_KEY_PREFIX}:{stock_code}"
                
                await r.hset(flow_key, mapping={
                    "foreign_net_amount": str(foreign_net_amount),
                    "institution_net_amount": str(institution_net_amount),
                    "foreign_net_volume": str(foreign_net_vol),
                    "institution_net_volume": str(institution_net_vol),
                    "updated_at": datetime.now().isoformat(),
                })
                await r.expire(flow_key, _CACHE_TTL)
                count += 1
            
            logger.info(f"수급 데이터 갱신 완료: {count}개 종목")

        except httpx.HTTPStatusError as exc:
            logger.error(f"수급 데이터(FHPTJ04400000) 조회 HTTP 에러: {exc.response.status_code} - {exc.response.text}")
        except Exception as exc:
            logger.error(f"수급 데이터 조회 실패: {exc}")

    async def get_investor_flow(self, stock_code: str) -> dict:
        """특정 종목의 외국인/기관 수급 데이터 반환."""
        r = await get_redis()
        data = await r.hgetall(f"{_FLOW_KEY_PREFIX}:{stock_code}")
        if not data:
            return {"foreign_net": 0, "institution_net": 0}

        def _safe_int(key: str) -> int:
            return int(data.get(key, 0) or 0)

        # 기존 로직은 매수금액 - 매도금액이었으나, 
        # 새 API는 순매수금액(Net)을 바로 제공하므로 그대로 사용
        foreign_net = _safe_int("foreign_net_amount")
        institution_net = _safe_int("institution_net_amount")

        return {
            "foreign_net": foreign_net,
            "institution_net": institution_net,
            # 볼륨 정보는 필요 시 사용 (현재 스코어링에는 금액만 사용됨)
            "foreign_net_volume": _safe_int("foreign_net_volume"),
            "institution_net_volume": _safe_int("institution_net_volume"),
            "updated_at": data.get("updated_at", ""),
        }
