"""API ingress rate-limit middleware backed by Postgres counters."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.errors import rate_limit_response
from app.auth.rate_limit import (
    API_INGRESS_IP_LIMIT,
    API_INGRESS_RATE_WINDOW,
    RateLimitExceeded,
    RateLimiter,
    api_ingress_ip_bucket,
    retry_after_seconds,
)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]
_EXEMPT_PATHS = frozenset({"/health"})


def _client_ip(request: Request) -> str:
    """Return the client IP address used for ingress rate limiting.

    Args:
        request: Incoming HTTP request.

    Returns:
        str: Observed client IP or a sentinel when unavailable.
    """
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


class IngressRateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-IP API ingress limits using Postgres ``rate_limit_counters``."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject requests that exceed the configured per-IP ingress threshold.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            Response: Rate-limit rejection or downstream handler response.
        """
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = _client_ip(request)
        session_factory = request.app.state.session_factory
        db = session_factory()
        try:
            rate_limiter = RateLimiter(db)
            rate_limiter.check_and_increment(
                bucket_key=api_ingress_ip_bucket(client_ip),
                limit=API_INGRESS_IP_LIMIT,
                window=API_INGRESS_RATE_WINDOW,
            )
        except RateLimitExceeded:
            retry_after = retry_after_seconds(
                now=datetime.now(UTC),
                window=API_INGRESS_RATE_WINDOW,
            )
            return rate_limit_response(retry_after_seconds=retry_after)
        finally:
            db.close()

        return await call_next(request)
