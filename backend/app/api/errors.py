"""Centralized HTTP error handlers that avoid leaking internal details."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings

logger = logging.getLogger(__name__)


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
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
