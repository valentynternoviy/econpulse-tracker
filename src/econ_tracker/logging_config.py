"""Structured JSON logging with correlation ID propagation and secret redaction."""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

import structlog

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "authorization",
        "cookie",
        "api_key",
        "database_url",
    }
)


def _add_request_id(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    event_dict.setdefault("request_id", request_id_ctx.get())
    return event_dict


def _redact_secrets(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if any(s in lowered for s in _SENSITIVE_KEYS):
            event_dict[key] = "***REDACTED***"
        elif isinstance(event_dict[key], dict):
            event_dict[key] = {
                k: "***REDACTED***" if any(s in k.lower() for s in _SENSITIVE_KEYS) else v
                for k, v in event_dict[key].items()
            }
    return event_dict


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure stdlib + structlog JSON pipeline."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        _redact_secrets,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
