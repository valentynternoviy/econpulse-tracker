"""HTTP middleware for X-Request-ID correlation and structured access logging."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from econ_tracker.logging_config import get_logger, request_id_ctx

logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach correlation ID to every request context, log line, and response header."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        incoming_id = request.headers.get("X-Request-ID")
        req_id = (
            incoming_id.strip()[:64]
            if incoming_id and incoming_id.strip()
            else uuid.uuid4().hex[:16]
        )
        token = request_id_ctx.set(req_id)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = req_id
        return response
