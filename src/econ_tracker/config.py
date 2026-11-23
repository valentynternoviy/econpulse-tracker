"""Application configuration loaded strictly from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EconPulse"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False

    secret_key: SecretStr = Field(
        default=SecretStr("dev-only-secret-key-change-in-production-32chars"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    base_currency: str = "USD"

    database_url: str = "sqlite+aiosqlite:///./econ_tracker_dev.db"

    collect_enabled: bool = True
    collect_concurrency: int = Field(default=4, ge=1, le=16)
    collect_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    collect_max_retries: int = Field(default=3, ge=0, le=6)
    platinum_usd_rate: float = Field(default=0.04999, gt=0.0)
    anomaly_threshold_pct: float = Field(default=20.0, gt=0.0, le=500.0)

    log_level: str = "INFO"
    log_json: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
