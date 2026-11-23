"""Domain enumerations."""

from enum import StrEnum


class UserRole(StrEnum):
    """System access roles defined by specification."""

    GUEST = "guest"
    USER = "user"
    ANALYST = "analyst"
    ADMIN = "admin"


class WatchDirection(StrEnum):
    """Threshold crossing direction for price watches."""

    BELOW = "below"
    ABOVE = "above"


class TradeSide(StrEnum):
    """Portfolio trade direction."""

    BUY = "buy"
    SELL = "sell"


class AnomalyStatus(StrEnum):
    """Lifecycle state of a price anomaly event."""

    OPEN = "open"
    CLOSED = "closed"


class HistoryStep(StrEnum):
    """Time aggregation bucket for price history."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


class CollectionStatus(StrEnum):
    """Execution status of a market collection run."""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
