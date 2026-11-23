"""Rust.tm public API v2 adapter (USD prices for Rust skins)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from econ_tracker.domain.exceptions import ExternalSourceError
from econ_tracker.domain.logic import classify_rust_item
from econ_tracker.domain.models import RawMarketQuote
from econ_tracker.sources.http_client import ResilientHttpClient


class RustTmSource:
    """Fetch Rust skin prices in USD from rust.tm public price list."""

    market_code = "rust_tm"
    game_code = "rust"
    currency = "USD"
    endpoint_url = "https://rust.tm/api/v2/prices/USD.json"

    def __init__(self, http_client: ResilientHttpClient, *, max_items: int = 350) -> None:
        self._http = http_client
        self._max_items = max_items

    async def fetch_quotes(self) -> Iterator[RawMarketQuote]:
        """Fetch payload and return a lazy generator of RawMarketQuote records."""
        payload: Any = await self._http.get_json(self.endpoint_url)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ExternalSourceError("Unexpected response shape from rust.tm API")

        collected_at = datetime.now(UTC)
        raw_items: list[dict[str, Any]] = payload["items"]
        return self._iter_quotes(raw_items, collected_at)

    def _iter_quotes(
        self,
        raw_items: list[dict[str, Any]],
        collected_at: datetime,
    ) -> Iterator[RawMarketQuote]:
        for idx, row in enumerate(raw_items):
            if self._max_items > 0 and idx >= self._max_items:
                break
            name = str(row.get("market_hash_name") or "").strip()
            price = _parse_decimal(row.get("price"))
            volume = _parse_int(row.get("volume"))
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
