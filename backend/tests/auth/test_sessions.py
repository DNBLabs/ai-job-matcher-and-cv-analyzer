"""Integration and service tests for Postgres-backed session cookies."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME, apply_session_cookie, clear_session_cookie
from app.auth.session import SessionService, _as_utc, _store_utc
from app.db.models import SessionRecord, UserAccount
from tests.auth.conftest import create_test_user


def test_create_session_persists_row_with_expiry_timestamps(db_session: Session) -> None:
    """A new session is stored in Postgres with idle and absolute expiry columns."""
    user = create_test_user(db_session)
    now = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)

    session_record = service.create_session(user.id, now=now)

    assert session_record.id
    assert len(session_record.id) >= 32
    assert session_record.user_id == user.id
    assert _as_utc(session_record.idle_expires_at) == now + timedelta(hours=24)
    assert _as_utc(session_record.absolute_expires_at) == now + timedelta(days=7)

    stored = db_session.get(SessionRecord, session_record.id)
    assert stored is not None
    assert stored.user_id == user.id


@pytest.mark.asyncio
async def test_authenticated_request_to_protected_route_returns_user(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Valid session cookie resolves the owner User Account on protected routes."""
    user = create_test_user(db_session)
    service = SessionService(db_session)
    session_record = service.create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.get("/test/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}


@pytest.mark.asyncio
async def test_unauthenticated_request_to_protected_route_returns_401(
    client: AsyncClient,
) -> None:
    """Protected routes reject requests without a session cookie."""
    response = await client.get("/test/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_expired_idle_session_returns_401(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Sessions past idle expiry are rejected and removed from the store."""
    user = create_test_user(db_session)
    now = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)
    session_record = service.create_session(user.id, now=now)
    session_record.idle_expires_at = _store_utc(now - timedelta(seconds=1))
    db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.get("/test/protected")

    assert response.status_code == 401
    assert db_session.get(SessionRecord, session_record.id) is None


@pytest.mark.asyncio
async def test_expired_absolute_session_returns_401(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Sessions past absolute expiry are rejected even if idle window was extended."""
    user = create_test_user(db_session)
    now = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)
    session_record = service.create_session(user.id, now=now)
    session_record.absolute_expires_at = _store_utc(now - timedelta(seconds=1))
    session_record.idle_expires_at = _store_utc(now + timedelta(hours=1))
    db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.get("/test/protected")

    assert response.status_code == 401
    assert db_session.get(SessionRecord, session_record.id) is None


def test_session_rotation_invalidates_previous_session_id(db_session: Session) -> None:
    """Successful authentication rotates the session id and deletes the prior row."""
    user = create_test_user(db_session)
    now = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)
    original = service.create_session(user.id, now=now)

    rotated = service.rotate_session(user.id, existing_session_id=original.id, now=now)

    assert rotated.id != original.id
    assert db_session.get(SessionRecord, original.id) is None
    assert db_session.get(SessionRecord, rotated.id) is not None


def test_valid_session_extends_idle_expiry_on_use(db_session: Session) -> None:
    """Each authenticated request refreshes idle expiry up to the absolute cap."""
    user = create_test_user(db_session)
    created_at = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)
    session_record = service.create_session(user.id, now=created_at)

    touched_at = created_at + timedelta(hours=2)
    resolved_user = service.resolve_session(session_record.id, now=touched_at)

    assert resolved_user is not None
    assert resolved_user.id == user.id
    db_session.refresh(session_record)
    assert _as_utc(session_record.last_seen_at) == touched_at
    assert _as_utc(session_record.idle_expires_at) == touched_at + timedelta(hours=24)
    assert _as_utc(session_record.idle_expires_at) <= _as_utc(session_record.absolute_expires_at)


def test_cleanup_expired_sessions_removes_stale_rows(db_session: Session) -> None:
    """Expired session rows are deleted via the cleanup predicate."""
    user = create_test_user(db_session)
    now = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    service = SessionService(db_session)
    expired = service.create_session(user.id, now=now)
    expired_session_id = expired.id
    expired.idle_expires_at = _store_utc(now - timedelta(minutes=5))
    active = service.create_session(user.id, now=now)
    active_session_id = active.id
    db_session.commit()

    deleted_count = service.cleanup_expired(now=now)

    assert deleted_count == 1
    assert db_session.get(SessionRecord, expired_session_id) is None
    assert db_session.get(SessionRecord, active_session_id) is not None


def test_session_cookie_uses_required_security_attributes(auth_settings) -> None:
    """Session cookies are HttpOnly + SameSite=Lax in all environments (ADR-0011).

    Both the SPA (www.getmeajob.dnblabs.co.uk) and API (api.getmeajob.dnblabs.co.uk)
    share the dnblabs.co.uk eTLD+1, so Lax is the correct and more secure posture.
    The Secure flag is still set in production (HTTPS only).
    """
    from starlette.responses import JSONResponse

    response = JSONResponse(content={"status": "ok"})
    apply_session_cookie(response, "session-token-value", auth_settings)
    set_cookie = response.headers.get("set-cookie", "")

    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "Secure" not in set_cookie

    production_response = JSONResponse(content={"status": "ok"})
    production_settings = auth_settings.model_copy(update={"app_env": "production"})
    apply_session_cookie(production_response, "session-token-value", production_settings)
    production_cookie = production_response.headers.get("set-cookie", "")

    assert "samesite=lax" in production_cookie.lower()
    assert "Secure" in production_cookie
    assert SESSION_COOKIE_NAME in production_cookie


def test_clear_session_cookie_expires_client_cookie(auth_settings) -> None:
    """Sign-out clears the session cookie from the client."""
    from starlette.responses import JSONResponse

    response = JSONResponse(content={"status": "ok"})
    apply_session_cookie(response, "session-token-value", auth_settings)
    clear_session_cookie(response, auth_settings)
    set_cookie_headers = response.headers.getlist("set-cookie")

    assert any("Max-Age=0" in header or "max-age=0" in header.lower() for header in set_cookie_headers)
