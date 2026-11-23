"""Consumer-side Protocols decoupling services from concrete external adapters."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Protocol

from econ_tracker.domain.models import RawMarketQuote


class MarketSourceProtocol(Protocol):
    """Contract any external marketplace adapter must satisfy."""

    market_code: str
    game_code: str
    currency: str

    async def fetch_quotes(self) -> Iterator[RawMarketQuote]:
        """Fetch quotes from upstream and yield them lazily."""
        ...


class FxProviderProtocol(Protocol):
    """Contract for fetching live currency conversion rates into USD."""

    async def get_rates_to_usd(self) -> dict[str, Decimal]:
        """Return mapping {CURRENCY_CODE: rate_to_usd}."""
        ...
