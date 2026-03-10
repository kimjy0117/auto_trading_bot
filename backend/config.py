import os
from pydantic_settings import BaseSettings
from functools import lru_cache

# APP_ENV 환경 변수로 프로필 지정 (기본값: local)
# 로컬 PC: APP_ENV=local  →  .env + .env.local 순서로 로드
# 운영 서버: APP_ENV=prod  →  .env + .env.prod 순서로 로드
APP_ENV = os.getenv("APP_ENV", "local")


class Settings(BaseSettings):
    # KIS OpenAPI
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_account_product: str = "01"
    kis_base_url: str = "https://openapi.koreainvestment.com:9443"
    kis_ws_url: str = "ws://ops.koreainvestment.com:21000"

    # OpenAI
    openai_api_key: str = ""

    # Telegram
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_channels: str = ""

    # DART
    dart_api_key: str = ""

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "autotrading"
    db_password: str = ""
    db_name: str = "autotrading"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # NXT
    nxt_enabled: bool = True
    nxt_pre_market_enabled: bool = True
    nxt_after_market_enabled: bool = True
    nxt_use_sor: bool = True

    # Schedule
    system_start_time: str = "07:55"
    system_stop_time: str = "20:10"
    holiday_check_enabled: bool = True

    # Risk
    max_daily_loss: int = 50000
    max_position_count: int = 3
    max_single_position_pct: int = 20
    cooldown_minutes: int = 30

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def telegram_channel_list(self) -> list[str]:
        return [ch.strip() for ch in self.telegram_channels.split(",") if ch.strip()]

    model_config = {
        # .env → 공통 시크릿(API 키 등)
        # .env.local / .env.prod → 환경별 값으로 덮어씀 (우선순위 높음)
        "env_file": (".env", f".env.{APP_ENV}"),
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
