"""Lazy streaming validation & normalization pipeline with O(1) memory footprint."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal

from econ_tracker.domain.exceptions import DomainValidationError
from econ_tracker.domain.logic import validate_raw_quote
from econ_tracker.domain.models import RawMarketQuote, ValidatedQuote
from econ_tracker.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineStats:
    """Mutable counters updated lazily as records flow through the pipeline."""

    accepted: int = 0
    rejected: int = 0


def iter_validated_quotes(
    raw_quotes: Iterable[RawMarketQuote],
    *,
    rate_to_usd: Decimal,
    stats: PipelineStats,
) -> Iterator[ValidatedQuote]:
    """Lazily validate and normalize quotes without materializing the full input stream.

    Invalid records (negative/zero price, negative volume, missing name) are skipped
    and counted in ``stats.rejected`` so the pipeline never aborts on dirty upstream data.
    """
    for raw in raw_quotes:
        try:
            validated = validate_raw_quote(raw, rate_to_usd=rate_to_usd)
        except DomainValidationError as exc:
            stats.rejected += 1
            logger.debug("quote_rejected", item=raw.name, reason=exc.detail)
            continue
        stats.accepted += 1
        yield validated
