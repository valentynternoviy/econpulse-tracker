"""Application configuration loaded strictly from environment variables."""

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Normalize PostgreSQL URLs for asyncpg and managed pooler compatibility."""
    cleaned = url.strip()
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgres://") :]
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgresql://") :]

    if cleaned.startswith("postgresql+asyncpg://"):
        parts = urlsplit(cleaned)
        raw_params = parse_qsl(parts.query, keep_blank_values=True)
        has_ssl = any(key.lower() == "ssl" for key, _ in raw_params)
        ssl_mode_value: str | None = None
        filtered_params: list[tuple[str, str]] = []
        for key, value in raw_params:
            lowered = key.lower()
            if lowered == "channel_binding":
                continue
            if lowered == "sslmode":
                ssl_mode_value = value.lower()
                continue
            filtered_params.append((key, value))

        if ssl_mode_value is not None and not has_ssl:
            filtered_params.append(
                ("ssl", "disable" if ssl_mode_value == "disable" else "require")
            )

        cleaned = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(filtered_params),
                parts.fragment,
            )
        )

    return cleaned


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

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
