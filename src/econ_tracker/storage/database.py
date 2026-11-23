"""Async SQLAlchemy 2.0 engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _unicode_lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _attach_sqlite_unicode_lower(dbapi_connection: Any) -> None:
    """Override SQLite's ASCII-only LOWER() with full Unicode case-folding."""
    for candidate in (
        dbapi_connection,
        getattr(dbapi_connection, "_connection", None),
        getattr(getattr(dbapi_connection, "_connection", None), "_conn", None),
        getattr(dbapi_connection, "_conn", None),
    ):
        create_fn = getattr(candidate, "create_function", None)
        if callable(create_fn):
            create_fn("LOWER", 1, _unicode_lower)
            return


def create_engine_and_sessionmaker(
    database_url: str,
    *,
    echo: bool = False,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create async SQLAlchemy engine tuned for PostgreSQL or SQLite."""
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict[str, Any] = {"echo": echo, "future": True}
    if not is_sqlite:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_recycle"] = 300
        if "-pooler." in database_url:
            kwargs["connect_args"] = {"statement_cache_size": 0}

    engine = create_async_engine(database_url, **kwargs)

    if is_sqlite:
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
            _attach_sqlite_unicode_lower(dbapi_connection)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


async def check_database_health(engine: AsyncEngine) -> bool:
    """Execute lightweight SELECT 1 probe against the configured database."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession and ensure proper cleanup."""
    async with session_factory() as session:
        yield session
