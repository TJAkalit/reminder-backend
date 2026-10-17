from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./reminder.db"
    database_echo: bool = False
    # PostgreSQL only: schema for all tables (created by `reminder migrate` if missing).
    database_schema: str | None = None

    telegram_bot_token: str = ""
    # Who may use the bot is stored in the database (chat_access, D-020), not in the config.

    default_timezone: str = "Europe/Moscow"

    worker_tick_seconds: int = 30
    worker_grace_minutes: int = 120

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
