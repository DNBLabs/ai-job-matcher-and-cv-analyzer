"""Integration tests for GET /auth/me session-probe endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService
from tests.auth.conftest import create_test_user


@pytest.mark.asyncio
async def test_me_returns_current_user_for_valid_session(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """An authenticated session resolves the owning account identity."""
    user = create_test_user(db_session)
    session_record = SessionService(db_session).create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "is_admin": user.is_admin,
    }


@pytest.mark.asyncio
async def test_me_returns_401_without_session_cookie(
    client: AsyncClient,
) -> None:
    """Anonymous callers receive 401 so the SPA can route to sign-in."""
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_for_invalid_session_id(
    client: AsyncClient,
) -> None:
    """A malformed or unknown session id is rejected as unauthenticated."""
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-session-id")
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_reports_admin_flag(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Admin accounts surface is_admin=true for operator-only navigation."""
    user = create_test_user(db_session, email="operator@example.com")
    user.is_admin = True
    db_session.commit()
    session_record = SessionService(db_session).create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["is_admin"] is True
