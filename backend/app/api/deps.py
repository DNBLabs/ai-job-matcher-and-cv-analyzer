"""FastAPI dependency helpers for database access and authentication."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService, is_valid_session_id
from app.config import Settings
from app.db.models import UserAccount
from app.db.session import get_db_session


def get_settings_dependency(request: Request) -> Settings:
    """Return application settings stored on the FastAPI app instance.

    Args:
        request: Active HTTP request.

    Returns:
        Settings: Runtime configuration for the current application.
    """
    return request.app.state.settings


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
) -> UserAccount:
    """Resolve the authenticated User Account from the session cookie.

    Args:
        request: Active HTTP request carrying session cookies.
        db: Request-scoped database session.

    Returns:
        UserAccount: Authenticated Job Seeker or Admin account.

    Raises:
        HTTPException: When the session cookie is missing or invalid/expired.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id or not is_valid_session_id(session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_service = SessionService(db)
    user = session_service.resolve_session(session_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
