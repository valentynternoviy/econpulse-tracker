"""Custom exception hierarchy mapped directly to RFC 9457 Problem Details."""

from __future__ import annotations


class EconTrackerError(Exception):
    """Base application error carrying stable RFC 9457 problem metadata."""

    problem_type: str = "urn:econ-tracker:error:internal"
    title: str = "Internal application error"
    status_code: int = 500

    def __init__(
        self,
        detail: str,
        *,
        problem_type: str | None = None,
        title: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if problem_type is not None:
            self.problem_type = problem_type
        if title is not None:
            self.title = title
        if status_code is not None:
            self.status_code = status_code


class DomainValidationError(EconTrackerError):
    """Domain invariant violation (HTTP 422)."""

    problem_type = "urn:econ-tracker:error:domain-validation"
    title = "Domain validation error"
    status_code = 422


class InsufficientPositionError(DomainValidationError):
    """Attempt to sell more items than currently held in portfolio (HTTP 422)."""

    problem_type = "urn:econ-tracker:error:insufficient-position"
    title = "Insufficient position quantity"
    status_code = 422


class ResourceNotFoundError(EconTrackerError):
    """Requested resource does not exist or is not owned by the caller (HTTP 404)."""

    problem_type = "urn:econ-tracker:error:not-found"
    title = "Resource not found"
    status_code = 404


class ConflictError(EconTrackerError):
    """Unique constraint or state conflict (HTTP 409)."""

    problem_type = "urn:econ-tracker:error:conflict"
    title = "Resource conflict"
    status_code = 409


class AuthenticationError(EconTrackerError):
    """Missing or invalid credentials / JWT token (HTTP 401)."""

    problem_type = "urn:econ-tracker:error:unauthenticated"
    title = "Authentication required"
    status_code = 401


class AuthorizationError(EconTrackerError):
    """Authenticated user lacks required role permissions (HTTP 403)."""

    problem_type = "urn:econ-tracker:error:forbidden"
    title = "Insufficient permissions"
    status_code = 403


class ExternalSourceError(EconTrackerError):
    """Upstream marketplace or FX provider failure (HTTP 502)."""

    problem_type = "urn:econ-tracker:error:external-source"
    title = "External data source unavailable"
    status_code = 502


class RateLimitError(ExternalSourceError):
    """Upstream rate limit exceeded (HTTP 429 / 503)."""

    problem_type = "urn:econ-tracker:error:rate-limit"
    title = "Upstream rate limit exceeded"
    status_code = 503
