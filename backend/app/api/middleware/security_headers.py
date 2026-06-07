"""HTTP middleware that applies baseline security response headers."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]

_STRICT_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"
# FastAPI Swagger UI loads JS/CSS from jsDelivr in development.
# Source: https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/
_DEVELOPMENT_DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)
_OPENAPI_DOCUMENTATION_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security headers to every API response."""

    def __init__(self, app: object, settings: Settings) -> None:
        """Store settings used to decide production-only headers.

        Args:
            app: ASGI application wrapped by this middleware.
            settings: Runtime configuration for environment-specific headers.
        """
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Apply security headers after the downstream handler returns.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            Response: Outbound response with security headers set.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = self._content_security_policy_for(request)

        if self._settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response

    def _content_security_policy_for(self, request: Request) -> str:
        """Return CSP appropriate for API responses versus local OpenAPI documentation.

        Args:
            request: Incoming HTTP request.

        Returns:
            str: Content-Security-Policy header value.
        """
        if (
            not self._settings.is_production
            and request.url.path in _OPENAPI_DOCUMENTATION_PATHS
        ):
            return _DEVELOPMENT_DOCS_CONTENT_SECURITY_POLICY
        return _STRICT_CONTENT_SECURITY_POLICY
