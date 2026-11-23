"""RFC 9457 (application/problem+json) centralized exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from econ_tracker.domain.exceptions import EconTrackerError
from econ_tracker.logging_config import get_logger, request_id_ctx
from econ_tracker.services.schemas import ProblemDetail

logger = get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ProblemDetail,
        "description": "Authentication required",
        "content": {
            PROBLEM_MEDIA_TYPE: {
                "example": {
                    "type": "urn:econ-tracker:error:unauthenticated",
                    "title": "Authentication required",
                    "status": 401,
                    "detail": "Missing or invalid bearer token",
                    "instance": "/api/v1/portfolio",
                    "request_id": "9f8c7b6a5e4d",
                }
            }
        },
    },
    403: {
        "model": ProblemDetail,
        "description": "Insufficient role permissions",
    },
    404: {
        "model": ProblemDetail,
        "description": "Resource not found (or not owned by caller)",
        "content": {
            PROBLEM_MEDIA_TYPE: {
                "example": {
                    "type": "urn:econ-tracker:error:not-found",
                    "title": "Resource not found",
                    "status": 404,
                    "detail": "Trade #42 not found",
                    "instance": "/api/v1/trades/42",
                    "request_id": "9f8c7b6a5e4d",
                }
            }
        },
    },
    422: {
        "model": ProblemDetail,
        "description": "Validation or business invariant violation",
        "content": {
            PROBLEM_MEDIA_TYPE: {
                "example": {
                    "type": "urn:econ-tracker:error:insufficient-position",
                    "title": "Insufficient position quantity",
                    "status": 422,
                    "detail": "Cannot sell 5 units: only 2 available",
                    "instance": "/api/v1/trades",
                    "request_id": "9f8c7b6a5e4d",
                }
            }
        },
    },
}


def _problem_response(
    *,
    request: Request,
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
) -> JSONResponse:
    body = ProblemDetail(
        type=problem_type,
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        request_id=request_id_ctx.get(),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach RFC 9457 error handlers ensuring 500 responses never leak stack traces."""

    @app.exception_handler(EconTrackerError)
    async def _handle_domain_error(request: Request, exc: EconTrackerError) -> JSONResponse:
        logger.warning(
            "application_error",
            problem_type=exc.problem_type,
            status=exc.status_code,
            detail=exc.detail,
            path=str(request.url.path),
        )
        return _problem_response(
            request=request,
            status_code=exc.status_code,
            problem_type=exc.problem_type,
            title=exc.title,
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        parts = [
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        detail = "; ".join(parts) if parts else "Request payload validation failed"
        return _problem_response(
            request=request,
            status_code=422,
            problem_type="urn:econ-tracker:error:validation",
            title="Request validation failed",
            detail=detail,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return _problem_response(
            request=request,
            status_code=exc.status_code,
            problem_type=f"urn:econ-tracker:error:http-{exc.status_code}",
            title=f"HTTP {exc.status_code}",
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_server_error", path=str(request.url.path), error=str(exc))
        # Strictly omit stack trace / internal details in HTTP 500 responses
        return _problem_response(
            request=request,
            status_code=500,
            problem_type="urn:econ-tracker:error:internal",
            title="Internal server error",
            detail="An unexpected server error occurred. Please retry or contact support.",
        )
