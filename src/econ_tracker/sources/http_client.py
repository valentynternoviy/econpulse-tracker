"""Resilient async HTTP client with timeout, per-host rate limiting, and exponential backoff."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from econ_tracker.domain.exceptions import ExternalSourceError, RateLimitError
from econ_tracker.logging_config import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ResilientHttpClient:
    """Async HTTP wrapper enforcing timeouts, polite rate limits, and retries."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.6,
        min_interval_seconds: float = 0.35,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds
        self._min_interval = min_interval_seconds
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            headers={
                "User-Agent": "EconPulse-CourseworkTracker/0.1 (+https://github.com/valentynternoviy)"
            },
        )
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def close(self) -> None:
        """Close owned httpx client."""
        if not self._external_client:
            await self._client.aclose()

    async def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last_request_at.get(host)
            if last is not None:
                wait = self._min_interval - (now - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_request_at[host] = time.monotonic()

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform GET request returning parsed JSON with retries and exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._throttle(url)
            try:
                response = await self._client.get(url, headers=headers, params=params)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.replace(".", "", 1).isdigit()
                        else self._base_backoff * (2**attempt)
                    )
                    logger.warning(
                        "upstream_retryable_status",
                        url=url,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        delay_s=round(delay, 2),
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(delay)
                        continue
                    if response.status_code == 429:
                        raise RateLimitError(f"Rate limit (429) from upstream {url}")
                    raise ExternalSourceError(
                        f"Upstream {url} returned HTTP {response.status_code} after retries"
                    )

                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                delay = self._base_backoff * (2**attempt)
                logger.warning(
                    "upstream_network_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                    delay_s=round(delay, 2),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise ExternalSourceError(
                    f"Network/timeout error calling {url}: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise ExternalSourceError(
                    f"HTTP {exc.response.status_code} error from {url}"
                ) from exc
            except ValueError as exc:
                raise ExternalSourceError(f"Invalid JSON payload from {url}") from exc

        raise ExternalSourceError(f"Failed to fetch {url}") from last_exc
