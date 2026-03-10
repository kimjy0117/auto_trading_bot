"""
텔레그램 최초 인증 스크립트.

서버 실행 전 딱 1회만 실행하면 됩니다.
실행 후 autotrading_listener.session 파일이 생성되며,
이후 서버는 세션 파일로 자동 로그인합니다.

사용법:
    python scripts/telegram_auth.py
"""

import asyncio
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (backend 패키지 임포트 가능하게)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv(".env")
    load_dotenv(f".env.{os.getenv('APP_ENV', 'local')}", override=True)
except ImportError:
    pass

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME = "autotrading_listener"


async def main() -> None:
    if not API_ID or not API_HASH:
        print("❌ TELEGRAM_API_ID / TELEGRAM_API_HASH 가 .env 에 설정되지 않았습니다.")
        return

    print("=" * 50)
    print("텔레그램 최초 인증")
    print("=" * 50)
    print(f"API_ID  : {API_ID}")
    print(f"세션 파일: {SESSION_NAME}.session")
    print()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ 이미 인증된 세션입니다 — {me.first_name} ({me.phone})")
        await client.disconnect()
        return

    phone = input("📱 텔레그램 가입 전화번호를 입력하세요 (예: +821012345678): ").strip()

    await client.send_code_request(phone)
    code = input("📩 텔레그램 앱/SMS로 받은 인증코드를 입력하세요: ").strip()

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        # 2단계 인증(클라우드 비밀번호)이 설정된 경우
        password = input("🔐 2단계 인증 비밀번호를 입력하세요: ").strip()
        await client.sign_in(password=password)

    me = await client.get_me()
    print()
    print(f"✅ 인증 완료! — {me.first_name} ({me.phone})")
    print(f"✅ 세션 파일 저장됨: {SESSION_NAME}.session")
    print()
    print("이제 서버를 시작할 수 있습니다:")
    print("  $env:APP_ENV='local'; uvicorn backend.main:app --reload")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
