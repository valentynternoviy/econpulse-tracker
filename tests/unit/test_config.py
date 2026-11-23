"""Unit tests for configuration loading and database URL normalization."""

from __future__ import annotations

import pytest

from econ_tracker.config import Settings, normalize_database_url


@pytest.mark.unit
def test_normalize_database_url_neon_and_variants() -> None:
    neon_url = (
        "postgresql://user:secret@ep-demo-pooler.eu-central-1.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )
    assert normalize_database_url(neon_url) == (
        "postgresql+asyncpg://user:secret@ep-demo-pooler.eu-central-1.aws.neon.tech/"
        "neondb?ssl=require"
    )

    assert normalize_database_url("postgres://user:pass@db.example.com:5432/app") == (
        "postgresql+asyncpg://user:pass@db.example.com:5432/app"
    )
    assert normalize_database_url("postgresql://user:pass@localhost/db?sslmode=disable") == (
        "postgresql+asyncpg://user:pass@localhost/db?ssl=disable"
    )
    assert normalize_database_url("sqlite+aiosqlite:///./dev.db") == (
        "sqlite+aiosqlite:///./dev.db"
    )


@pytest.mark.unit
def test_settings_normalizes_database_url() -> None:
    settings = Settings(
        database_url=(
            "postgresql://owner:pass@ep-x-pooler.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        )
    )
    assert settings.database_url == (
        "postgresql+asyncpg://owner:pass@ep-x-pooler.aws.neon.tech/neondb?ssl=require"
    )
