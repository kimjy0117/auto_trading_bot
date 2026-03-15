"""
KIS WebSocket 실시간 시세 서비스.

KRX·NXT 양쪽 체결가/호가를 구독하고,
Redis에 캐싱하면서 기술적 지표(RSI, MACD, MA, ATR, BB)를 계산한다.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import httpx
import websockets

from backend.config import get_settings
from backend.database import async_session
from backend.models import MarketSnapshot
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

_PRICE_KEY_PREFIX = "price"
_ORDERBOOK_KEY_PREFIX = "orderbook"
_CACHE_TTL = 60 * 30  # 30분
_MAX_PRICE_HISTORY = 200  # 지표 계산용 체결가 히스토리


class MarketDataService:
    """KIS WebSocket 실시간 시세 서비스."""

    _SNAPSHOT_INTERVAL = 300  # 5분

    def __init__(self) -> None:
        self._ws_krx: Any = None
        self._ws_nxt: Any = None
        self._running = False
        self._subscriptions: dict[str, set[str]] = defaultdict(set)  # code → {exchange, ...}
        self._tasks: list[asyncio.Task] = []
        self._price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_PRICE_HISTORY))
        self._approval_key: str | None = None
        self._snapshot_cooldown: dict[str, datetime] = {}

    async def _get_approval_key(self, force_refresh: bool = False) -> str:
        """WebSocket 접속용 approval key 발급. 재접속 시 만료 방지를 위해 force_refresh=True 권장."""
        if self._approval_key and not force_refresh:
            return self._approval_key
        if force_refresh:
            self._approval_key = None

        url = f"{settings.kis_base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": settings.kis_app_key,
            "secretkey": settings.kis_app_secret,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            self._approval_key = resp.json()["approval_key"]

        return self._approval_key

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        self._tasks.append(asyncio.create_task(
            self._ws_loop(settings.kis_ws_url, "KRX")
        ))
        if settings.nxt_enabled:
            nxt_ws_url = settings.kis_ws_url.replace("21000", "21002")
            self._tasks.append(asyncio.create_task(
                self._ws_loop(nxt_ws_url, "NXT")
            ))

        self._tasks.append(asyncio.create_task(self._poll_market_index()))
        logger.info("시세 WebSocket 연결 시작")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        for ws in (self._ws_krx, self._ws_nxt):
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._ws_krx = None
        self._ws_nxt = None
        logger.info("시세 WebSocket 연결 종료")

    async def _ws_loop(self, ws_url: str, exchange: str) -> None:
        """WebSocket 연결 유지 + 자동 재접속. 재접속 시 approval_key 재발급으로 만료 방지."""
        while self._running:
            try:
                # 매 연결(첫 접속·재접속)마다 새 approval_key 사용 — KIS 유휴/만료로 끊김 완화
                approval_key = await self._get_approval_key(force_refresh=True)

                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    if exchange == "KRX":
                        self._ws_krx = ws
                    else:
                        self._ws_nxt = ws

                    logger.info(f"{exchange} WebSocket 연결됨: {ws_url}")

                    for code, exchanges in self._subscriptions.items():
                        if exchange in exchanges:
                            await self._send_subscribe(ws, code, exchange, approval_key)

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        await self._on_raw_message(raw_msg, exchange)

            except websockets.ConnectionClosed:
                logger.warning(f"{exchange} WebSocket 연결 끊김 — 5초 후 재접속")
            except Exception as exc:
                logger.error(f"{exchange} WebSocket 에러: {exc}")
            finally:
                # 끊긴 소켓 참조 제거 — trading_loop의 subscribe()가 죽은 ws에 send하지 않도록
                if exchange == "KRX":
                    self._ws_krx = None
                else:
                    self._ws_nxt = None

            if self._running:
                await asyncio.sleep(5)

    async def _send_subscribe(
        self, ws: Any, stock_code: str, exchange: str, approval_key: str,
    ) -> None:
        """체결가 및 수급 실시간 구독 요청."""
        header = {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8",
        }

        # 1. 체결가 (H0STCNT0)
        body_price = {
            "input": {
                "tr_id": "H0STCNT0" if exchange == "KRX" else "H0STCNT9",
                "tr_key": stock_code,
            }
        }
        await ws.send(json.dumps({"header": header, "body": body_price}))
        
        # 2. 실시간 수급 (H0STCNI0) - KRX만 지원
        if exchange == "KRX":
            body_flow = {
                "input": {
                    "tr_id": "H0STCNI0",
                    "tr_key": stock_code,
                }
            }
            await ws.send(json.dumps({"header": header, "body": body_flow}))

        logger.debug(f"구독 요청 (시세+수급) — {exchange}:{stock_code}")

    async def subscribe(self, stock_code: str, exchange: str = "KRX") -> None:
        """종목 실시간 시세 구독."""
        if stock_code in self._subscriptions and exchange in self._subscriptions[stock_code]:
            return
        self._subscriptions[stock_code].add(exchange)
        ws = self._ws_krx if exchange == "KRX" else self._ws_nxt
        # 연결이 살아 있을 때만 send (끊긴 소켓에 send 시 no close frame 에러 방지)
        if ws and getattr(ws, "open", True) and self._approval_key:
            try:
                await self._send_subscribe(ws, stock_code, exchange, self._approval_key)
            except Exception as exc:
                logger.warning(f"시세 구독 요청 실패 ({exchange}:{stock_code}) — 재접속 시 자동 재구독: {exc}")
        await self._cache_market_cap(stock_code)

    async def unsubscribe(self, stock_code: str) -> None:
        """종목 구독 해제."""
        self._subscriptions.pop(stock_code, None)
        r = await get_redis()
        await r.delete(f"{_PRICE_KEY_PREFIX}:{stock_code}")
        await r.delete(f"{_ORDERBOOK_KEY_PREFIX}:{stock_code}")
        logger.debug(f"구독 해제 — {stock_code}")

    async def _on_raw_message(self, raw: str, exchange: str) -> None:
        """WebSocket 수신 메시지 파싱 → 가격 업데이트."""
        try:
            if raw.startswith("{"):
                return

            parts = raw.split("|")
            if len(parts) < 4:
                return

            tr_id = parts[1]
            data_str = parts[3]
            fields = data_str.split("^")

            if tr_id in ("H0STCNT0", "H0STCNT9") and len(fields) >= 20:
                price_data = {
                    "stock_code": fields[0],
                    "current_price": int(fields[2]),
                    "change": int(fields[4]),
                    "change_rate": float(fields[5]),
                    "volume": int(fields[12]),
                    "accum_volume": int(fields[13]),
                    "high": int(fields[8]),
                    "low": int(fields[9]),
                    "open": int(fields[7]),
                    "exchange": exchange,
                    "timestamp": datetime.now().isoformat(),
                }
                await self._on_price_update(price_data)

            elif tr_id == "H0STCNI0":
                # 실시간 외국인/기관 수급 (H0STCNI0)
                # 필드 순서 (추정):
                # 0: 종목코드
                # 1: 시간
                # 2: 외국인 순매수 수량
                # 3: 기관 순매수 수량
                # 4: 외국인 순매수 금액? (확인 필요)
                # ...
                # 문서가 없으므로 일단 수량 위주로 파싱하고 로그로 확인
                
                # 안전하게 파싱
                try:
                    stock_code = fields[0]
                    # 수량 정보 (보통 2, 3번째 필드)
                    foreign_net_vol = int(fields[2] or 0)
                    institution_net_vol = int(fields[3] or 0)
                    
                    # 금액 정보가 있다면 좋겠지만, 없으면 수량 * 현재가로 추정하거나
                    # 일단 수량만 저장
                    
                    flow_data = {
                        "stock_code": stock_code,
                        "foreign_net_volume": foreign_net_vol,
                        "institution_net_volume": institution_net_vol,
                        "timestamp": datetime.now().isoformat(),
                    }
                    await self._on_flow_update(flow_data)
                except (ValueError, IndexError):
                    logger.debug(f"수급 메시지 파싱 실패: {raw}")

        except (IndexError, ValueError) as exc:
            logger.debug(f"시세 메시지 파싱 에러: {exc}")

    async def _on_flow_update(self, data: dict) -> None:
        """실시간 수급 데이터를 Redis에 캐싱."""
        stock_code = data["stock_code"]
        r = await get_redis()
        
        # investor_flow 키에 저장 (기존 investor_flow 서비스와 호환)
        flow_key = f"investor_flow:{stock_code}"
        
        foreign_vol = int(data["foreign_net_volume"])
        institution_vol = int(data["institution_net_volume"])
        
        update_map = {
            "foreign_net_volume": str(foreign_vol),
            "institution_net_volume": str(institution_vol),
            "updated_at": data["timestamp"],
        }
        
        # 금액 정보가 없으면 수량 * 현재가로 대략적 계산 (옵션)
        # SignalScorer는 금액(Amount)을 기준으로 점수를 매기므로 필수
        
        # 현재가 조회 (Redis 캐시)
        price_data = await r.hgetall(f"{_PRICE_KEY_PREFIX}:{stock_code}")
        current_price = int(price_data.get("current_price", 0)) if price_data else 0
        
        if current_price > 0:
            # 1주당 가격 * 수량 = 거래대금 (추정치)
            # 정확한 금액은 아니지만, 수급 강도를 판단하기엔 충분함
            foreign_amt = foreign_vol * current_price
            institution_amt = institution_vol * current_price
            
            update_map["foreign_net_amount"] = str(foreign_amt)
            update_map["institution_net_amount"] = str(institution_amt)
            
            # 기존에는 매수/매도 금액이 따로 있었으나, 순매수 금액만 있으면 됨
            # InvestorFlowService.get_investor_flow()에서 순매수 금액을 우선 사용하도록 되어 있음
        
        await r.hset(flow_key, mapping=update_map)
        await r.expire(flow_key, _CACHE_TTL)

    async def _on_price_update(self, data: dict) -> None:
        """가격 업데이트를 Redis에 캐싱하고 지표를 계산."""
        stock_code = data["stock_code"]
        r = await get_redis()

        await r.hset(f"{_PRICE_KEY_PREFIX}:{stock_code}", mapping={
            k: str(v) for k, v in data.items()
        })
        await r.expire(f"{_PRICE_KEY_PREFIX}:{stock_code}", _CACHE_TTL)

        self._price_history[stock_code].append(data["current_price"])

        if len(self._price_history[stock_code]) >= 14:
            indicators = self._calculate_indicators(stock_code)
            await r.hset(f"indicators:{stock_code}", mapping={
                k: str(v) for k, v in indicators.items()
            })
            await r.expire(f"indicators:{stock_code}", _CACHE_TTL)
            await self._save_snapshot(stock_code, data, indicators)

    _INDICATOR_KEY_MAP = {
        "rsi": "rsi_14",
        "ma5": "ma_5",
        "ma20": "ma_20",
        "ma60": "ma_60",
        "atr": "atr_14",
        "macd": "macd",
        "macd_signal": "macd_signal",
        "macd_histogram": "macd_histogram",
        "bb_upper": "bb_upper",
        "bb_middle": "bb_middle",
        "bb_lower": "bb_lower",
    }

    async def get_current_price(self, stock_code: str) -> dict:
        """Redis에서 최신 체결가 + 기술적 지표를 병합하여 반환."""
        r = await get_redis()
        data = await r.hgetall(f"{_PRICE_KEY_PREFIX}:{stock_code}")
        if data:
            for key in ("current_price", "change", "volume", "accum_volume", "high", "low", "open"):
                if key in data:
                    data[key] = int(data[key])
            if "change_rate" in data:
                data["change_rate"] = float(data["change_rate"])

        indicators = await r.hgetall(f"indicators:{stock_code}")
        if indicators:
            if not data:
                data = {}
            for src, dst in self._INDICATOR_KEY_MAP.items():
                if src in indicators:
                    data[dst] = float(indicators[src])

        if data and "volume_ratio" not in data:
            history = self._price_history.get(stock_code)
            if history and len(history) >= 20:
                avg_vol_str = await r.hget(f"indicators:{stock_code}", "avg_volume")
                if avg_vol_str:
                    avg_vol = float(avg_vol_str)
                    cur_vol = data.get("accum_volume", 0)
                    if avg_vol > 0:
                        data["volume_ratio"] = round(cur_vol / avg_vol, 2)

        return data or {}

    async def _poll_market_index(self) -> None:
        """코스피 지수 변동률을 5분 간격으로 Redis에 저장."""
        while self._running:
            try:
                url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"
                headers = {
                    "content-type": "application/json; charset=utf-8",
                    "appkey": settings.kis_app_key,
                    "appsecret": settings.kis_app_secret,
                    "tr_id": "FHPUP02100000",
                }
                params = {
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": "0001",
                }
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        output = data.get("output", {})
                        change_pct = output.get("bstp_nmix_prdy_ctrt", "0")
                        r = await get_redis()
                        await r.setex("market:kospi_change_pct", 600, str(change_pct))
                        logger.debug(f"코스피 변동률 캐싱: {change_pct}%")
            except Exception as exc:
                logger.error(f"코스피 지수 조회 에러: {exc}")

            await asyncio.sleep(300)

    async def _cache_market_cap(self, stock_code: str) -> None:
        """KIS REST API로 시가총액을 조회하여 Redis에 캐싱 (24시간)."""
        r = await get_redis()
        existing = await r.get(f"market_cap:{stock_code}")
        if existing:
            return
        try:
            url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
            headers = {
                "content-type": "application/json; charset=utf-8",
                "appkey": settings.kis_app_key,
                "appsecret": settings.kis_app_secret,
                "tr_id": "FHKST01010100",
            }
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    cap_str = data.get("output", {}).get("hts_avls", "0")
                    cap_value = int(cap_str.replace(",", "")) * 1_0000 if cap_str else 0
                    await r.setex(f"market_cap:{stock_code}", 86400, str(cap_value))
                    logger.debug(f"시가총액 캐싱: {stock_code} = {cap_value:,}원")
        except Exception as exc:
            logger.debug(f"시가총액 조회 실패 ({stock_code}): {exc}")

    async def _save_snapshot(self, stock_code: str, price_data: dict, indicators: dict) -> None:
        """종목별 5분 간격으로 MarketSnapshot을 DB에 저장."""
        now = datetime.now()
        last = self._snapshot_cooldown.get(stock_code)
        if last and (now - last).total_seconds() < self._SNAPSHOT_INTERVAL:
            return
        self._snapshot_cooldown[stock_code] = now

        try:
            async with async_session() as db:
                snapshot = MarketSnapshot(
                    stock_code=stock_code,
                    current_price=price_data.get("current_price"),
                    volume=price_data.get("accum_volume"),
                    rsi_14=indicators.get("rsi"),
                    macd=indicators.get("macd"),
                    macd_signal=indicators.get("macd_signal"),
                    ma_5=indicators.get("ma5"),
                    ma_20=indicators.get("ma20"),
                    ma_60=indicators.get("ma60"),
                    atr_14=indicators.get("atr"),
                    bb_upper=indicators.get("bb_upper"),
                    bb_lower=indicators.get("bb_lower"),
                )
                db.add(snapshot)
                await db.commit()
        except Exception as exc:
            logger.error(f"MarketSnapshot 저장 실패 ({stock_code}): {exc}")

    async def get_orderbook(self, stock_code: str, exchange: str = "KRX") -> dict:
        """Redis에서 호가 정보 반환."""
        r = await get_redis()
        data = await r.hgetall(f"{_ORDERBOOK_KEY_PREFIX}:{stock_code}")
        return data or {}

    def _calculate_indicators(self, stock_code: str) -> dict:
        """보유 가격 히스토리로 기술적 지표를 계산."""
        prices = list(self._price_history[stock_code])
        n = len(prices)
        result: dict[str, float] = {}

        # SMA
        if n >= 5:
            result["ma5"] = round(sum(prices[-5:]) / 5, 2)
        if n >= 20:
            result["ma20"] = round(sum(prices[-20:]) / 20, 2)
        if n >= 60:
            result["ma60"] = round(sum(prices[-60:]) / 60, 2)

        # RSI (14)
        if n >= 15:
            gains, losses = [], []
            for i in range(-14, 0):
                diff = prices[i] - prices[i - 1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss == 0:
                result["rsi"] = 100.0
            else:
                rs = avg_gain / avg_loss
                result["rsi"] = round(100 - 100 / (1 + rs), 2)

        # ATR (14) — 단순 변동폭 근사 (고가-저가 없이 종가 변동 사용)
        if n >= 15:
            true_ranges = [abs(prices[i] - prices[i - 1]) for i in range(-14, 0)]
            result["atr"] = round(sum(true_ranges) / 14, 2)

        # MACD (12, 26, 9)
        if n >= 26:
            ema12 = self._ema(prices, 12)
            ema26 = self._ema(prices, 26)
            macd_line = ema12 - ema26
            result["macd"] = round(macd_line, 2)

            if n >= 35:
                macd_values = []
                for i in range(26, n):
                    e12 = self._ema(prices[: i + 1], 12)
                    e26 = self._ema(prices[: i + 1], 26)
                    macd_values.append(e12 - e26)
                if len(macd_values) >= 9:
                    signal = self._ema(macd_values, 9)
                    result["macd_signal"] = round(signal, 2)
                    result["macd_histogram"] = round(macd_line - signal, 2)

        # Bollinger Bands (20, 2σ)
        if n >= 20:
            window = prices[-20:]
            mean = sum(window) / 20
            variance = sum((p - mean) ** 2 for p in window) / 20
            std = variance ** 0.5
            result["bb_upper"] = round(mean + 2 * std, 2)
            result["bb_middle"] = round(mean, 2)
            result["bb_lower"] = round(mean - 2 * std, 2)

        return result

    @staticmethod
    def _ema(data: list, period: int) -> float:
        """지수이동평균(EMA)."""
        if len(data) < period:
            return sum(data) / len(data)
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
