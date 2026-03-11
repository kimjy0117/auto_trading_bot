"""
Telethon 기반 텔레그램 채널 리스너.

설정된 채널에서 새 메시지를 수신하고,
종목 언급(종목명/6자리 코드)을 추출하여 콜백을 트리거한다.

인증 방식:
  - 최초 실행 전 반드시 `python scripts/telegram_auth.py` 로 세션 파일 생성 필요
  - 이후 autotrading_listener.session 파일로 자동 로그인 (입력 불필요)
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from backend.config import get_settings
from backend.redis_client import get_redis
from backend.utils.logger import logger

settings = get_settings()

# 6자리 숫자 종목코드 패턴
_CODE_PATTERN = re.compile(r"\b(\d{6})\b")

# 주식 종목명 패턴: 2~15자 한글+숫자 조합
# 단, 부동산/일반명사 등 노이즈 제거를 위해 최소 2자 한글로 시작
_NAME_PATTERN = re.compile(r"[가-힣]{2}[가-힣0-9]{0,13}")

# 노이즈 키워드: 이 단어가 포함된 메시지는 AI 분석 없이 스킵
_NOISE_KEYWORDS: frozenset[str] = frozenset({
    "아파트", "부동산", "재건축", "재개발", "전세", "월세", "분양",
    "강남", "강북", "서울시", "국토부",
    "날씨", "교통", "사고", "축구", "야구", "스포츠",
})

# 주식 관련 핵심 키워드: 이 단어 중 하나라도 있으면 종목명 미추출 시에도 AI에 전달
_STOCK_KEYWORDS: frozenset[str] = frozenset({
    "특징주", "급등", "급락", "상한가", "하한가", "수주", "실적",
    "M&A", "합병", "인수", "공시", "테마", "섹터", "호재", "악재",
    "수혜", "목표가", "신고가", "신저가",
})

OnNewMessageCallback = Callable[[dict[str, Any]], Awaitable[None]]


class TelegramListener:
    """텔레그램 채널 메시지 리스너."""

    def __init__(self, on_new_message: OnNewMessageCallback | None = None) -> None:
        self._client: TelegramClient | None = None
        self._running = False
        self.on_new_message = on_new_message

    async def start(self) -> None:
        if self._running:
            return

        if not settings.telegram_api_id or not settings.telegram_api_hash:
            logger.warning("텔레그램 API 자격 증명이 설정되지 않음 — 리스너 비활성화")
            return

        self._client = TelegramClient(
            "/app/sessions/autotrading_listener",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )

        try:
            # 세션 파일(autotrading_listener.session)로 자동 로그인
            # 세션 파일이 없으면 SessionPasswordNeededError 또는 연결 실패 발생
            # → 먼저 `python scripts/telegram_auth.py` 를 실행해 세션 파일을 생성해야 함
            await self._client.connect()

            if not await self._client.is_user_authorized():
                logger.error(
                    "텔레그램 세션 파일 없음 또는 만료됨. "
                    "`python scripts/telegram_auth.py` 를 먼저 실행하세요."
                )
                return

        except SessionPasswordNeededError:
            logger.error("텔레그램 2단계 인증 필요 — scripts/telegram_auth.py 에서 비밀번호 입력 후 재시도")
            return
        except Exception as exc:
            logger.error(f"텔레그램 연결 실패: {exc}")
            return

        channels = settings.telegram_channel_list
        if not channels:
            logger.warning("모니터링할 텔레그램 채널이 설정되지 않음")
            return

        @self._client.on(events.NewMessage(chats=channels))
        async def handler(event: events.NewMessage.Event) -> None:
            await self._handle_message(event)

        self._running = True
        logger.info(f"텔레그램 리스너 시작 — 채널: {channels}")

    async def stop(self) -> None:
        if self._client and self._running:
            await self._client.disconnect()
            self._running = False
            logger.info("텔레그램 리스너 중지")

    async def _handle_message(self, event: events.NewMessage.Event) -> None:
        """메시지에서 종목 정보를 추출하고 콜백을 호출."""
        try:
            text: str = event.raw_text or ""
            if not text.strip():
                return

            channel = getattr(event.chat, "title", None) or str(event.chat_id)

            # ── 1단계: 노이즈 사전 필터링 ──────────────────────────
            if any(kw in text for kw in _NOISE_KEYWORDS):
                # 노이즈 키워드가 있어도 주식 키워드도 함께 있으면 통과
                if not any(kw in text for kw in _STOCK_KEYWORDS):
                    logger.debug(f"노이즈 메시지 스킵 — {channel}")
                    return

            # ── 2단계: 종목 추출 ────────────────────────────────────
            stock_codes = _CODE_PATTERN.findall(text)
            stock_names = _NAME_PATTERN.findall(text)

            # 주식 키워드가 있으면 종목명이 없어도 AI에 전달 (특징주 요약 등)
            has_stock_keyword = any(kw in text for kw in _STOCK_KEYWORDS)
            is_priority = "특징주" in text  # 특징주 메시지는 우선 처리

            if not stock_codes and not stock_names and not has_stock_keyword:
                logger.debug(f"텔레그램 메시지 수신 (종목 없음) — {channel}")
                return

            # ── 3단계: Redis 저장 및 콜백 호출 ─────────────────────
            r = await get_redis()

            message_data: dict[str, Any] = {
                "source": "TELEGRAM",
                "channel": channel,
                "raw_text": text,
                "stock_codes": stock_codes,
                "stock_names": stock_names,
                "message_id": event.id,
                "timestamp": datetime.now().isoformat(),
                "is_priority": is_priority,
            }

            redis_key = "telegram:priority_messages" if is_priority else "telegram:raw_messages"
            await r.lpush(
                redis_key,
                f"{datetime.now().isoformat()}|{channel}|{text[:500]}",
            )
            await r.ltrim(redis_key, 0, 999)

            logger.info(
                f"{'[우선]' if is_priority else '[일반]'} 텔레그램 종목 감지 — "
                f"채널: {channel}, 코드: {stock_codes}, 이름: {stock_names[:5]}"
            )

            if self.on_new_message:
                await self.on_new_message(message_data)

        except Exception as exc:
            logger.error(f"텔레그램 메시지 처리 에러: {exc}")
