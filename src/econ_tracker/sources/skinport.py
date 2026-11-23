"""Skinport public API v1 adapter (EUR prices & release timestamps for Rust skins)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.domain.logic import classify_rust_item
from econ_tracker.domain.models import RawMarketQuote
from econ_tracker.sources.http_client import ResilientHttpClient


class SkinportRustSource:
    """Fetch Rust skin prices in EUR from Skinport public API (Brotli compressed)."""

    market_code = "skinport_rust"
    game_code = "rust"
    currency = "EUR"
    endpoint_url = "https://api.skinport.com/v1/items"

    def __init__(self, http_client: ResilientHttpClient, *, max_items: int = 350) -> None:
        self._http = http_client
        self._max_items = max_items

    async def fetch_quotes(self) -> Iterator[RawMarketQuote]:
        """Fetch Skinport Rust catalog and return a lazy RawMarketQuote generator."""
        payload: Any = await self._http.get_json(
            self.endpoint_url,
            headers={"Accept-Encoding": "br"},
            params={"app_id": 252490, "currency": self.currency},
        )
        if not isinstance(payload, list):
            raise ExternalSourceError("Unexpected response shape from Skinport API")

        collected_at = datetime.now(UTC)
        return self._iter_quotes(payload, collected_at)

    def _iter_quotes(
        self,
        raw_items: list[dict[str, Any]],
        collected_at: datetime,
    ) -> Iterator[RawMarketQuote]:
        for idx, row in enumerate(raw_items):
            if self._max_items > 0 and idx >= self._max_items:
                break
            name = str(row.get("market_hash_name") or "").strip()
            raw_price = row.get("min_price")
            if raw_price is None:
                raw_price = row.get("suggested_price")
            price = _parse_decimal(raw_price)
            volume = _parse_int(row.get("quantity"))
            released_at = _parse_unix_ts(row.get("created_at"))
            category, subcategory, rarity = classify_rust_item(name)
            yield RawMarketQuote(
                external_id=name,
                name=name,
                original_price=price,
                original_currency=self.currency,
                volume=volume,
                collected_at=collected_at,
                item_type=category,
                subcategory=subcategory,
                rarity=rarity,
                released_at=released_at,
            )


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_unix_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        ts = int(value)
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None
