import httpx
from backend.config import get_settings
from backend.utils.logger import logger

settings = get_settings()

TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


async def send_telegram_message(message: str, parse_mode: str = "HTML"):
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("텔레그램 봇 토큰 또는 채팅 ID가 설정되지 않음")
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                },
            )
            if resp.status_code != 200:
                logger.error(f"텔레그램 메시지 발송 실패: {resp.text}")
    except Exception as e:
        logger.error(f"텔레그램 메시지 발송 에러: {e}")


async def send_trade_alert(
    action: str,
    stock_name: str,
    stock_code: str,
    price: int,
    qty: int,
    exchange: str,
    session: str,
    reason: str = "",
):
    emoji = "🟢" if action == "BUY" else "🔴"
    msg = (
        f"{emoji} <b>{action}</b>\n"
        f"종목: {stock_name} ({stock_code})\n"
        f"가격: {price:,}원 × {qty}주\n"
        f"거래소: {exchange} | 세션: {session}\n"
    )
    if reason:
        msg += f"사유: {reason}\n"
    await send_telegram_message(msg)


async def send_daily_report(report: str):
    await send_telegram_message(f"📊 <b>일일 리포트</b>\n\n{report}")


async def send_error_alert(error: str):
    await send_telegram_message(f"🚨 <b>시스템 에러</b>\n\n{error}")
