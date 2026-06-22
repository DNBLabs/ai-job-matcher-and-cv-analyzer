"""Centralized HTTP error handlers and response helpers."""

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings

logger = logging.getLogger(__name__)


def rate_limit_response(*, retry_after_seconds: int, detail: str = "Too many requests") -> JSONResponse:
    """Return a 429 response with ``Retry-After`` semantics for rate-limited clients.

    Args:
        retry_after_seconds: Seconds until the client may retry.
        detail: Generic client-facing error message.

    Returns:
        JSONResponse: Sanitized rate-limit payload with retry guidance.
    """
    return JSONResponse(
        status_code=429,
        content={"detail": detail},
        headers={"Retry-After": str(retry_after_seconds)},
    )


def register_exception_handlers(application: FastAPI, settings: Settings) -> None:
    """Register handlers that sanitize unhandled errors for clients.

    Args:
        application: FastAPI instance to attach handlers to.
        settings: Runtime configuration (reserved for future environment-specific behavior).
    """

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a generic 500 response while logging the failure server-side.

        Args:
            request: Request that triggered the failure.
            exc: Unhandled exception raised by a route or dependency.

        Returns:
            JSONResponse: Sanitized error payload without stack traces or secrets.
        """
        _ = settings
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        logger.error(
            json.dumps({"event": "http_5xx", "method": request.method, "path": request.url.path, "status_code": 500})
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
