"""Session cookie configuration helpers for FastAPI responses."""

from starlette.responses import Response

from app.auth.session import SESSION_ABSOLUTE_TIMEOUT
from app.config import Settings

SESSION_COOKIE_NAME = "session_id"


def apply_session_cookie(response: Response, session_id: str, settings: Settings) -> None:
    """Attach the HttpOnly session cookie to an outgoing response.

    Cookie attributes follow the security posture: HttpOnly always; SameSite=Lax +
    insecure in dev, SameSite=None + Secure in production (cross-origin SPA, ADR-0008).
    Source: https://fastapi.tiangolo.com/advanced/response-cookies/

    Args:
        response: Outgoing Starlette/FastAPI response.
        session_id: Opaque server-side session identifier.
        settings: Runtime configuration controlling SameSite/Secure behavior.
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=int(SESSION_ABSOLUTE_TIMEOUT.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Remove the session cookie from the client on sign-out.

    Args:
        response: Outgoing Starlette/FastAPI response.
        settings: Runtime configuration controlling Secure flag behavior.
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
