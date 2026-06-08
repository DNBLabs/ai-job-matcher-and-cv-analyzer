"""Integration tests for POST /auth/logout."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.db.models import SessionRecord
from app.db.models import AuditLogEntry
from tests.auth.conftest import create_test_user
from app.auth.session import SessionService


@pytest.mark.asyncio
async def test_logout_deletes_session_and_clears_cookie(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Sign-out removes the server-side session row and expires the session cookie."""
    user = create_test_user(db_session)
    service = SessionService(db_session)
    session_record = service.create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"detail": "Signed out"}
    assert db_session.get(SessionRecord, session_record.id) is None

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        SESSION_COOKIE_NAME in header and ("Max-Age=0" in header or "max-age=0" in header.lower())
        for header in set_cookie_headers
    )


@pytest.mark.asyncio
async def test_logout_without_session_cookie_succeeds(
    client: AsyncClient,
) -> None:
    """Sign-out is idempotent when no session cookie is present."""
    response = await client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"detail": "Signed out"}


@pytest.mark.asyncio
async def test_logout_invalidates_session_for_subsequent_requests(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Protected routes return 401 after sign-out."""
    user = create_test_user(db_session)
    service = SessionService(db_session)
    session_record = service.create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 200

    protected_response = await client.get("/test/protected")
    assert protected_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_appends_audit_log_event(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Successful sign-out records an auth.logout audit event."""
    user = create_test_user(db_session)
    service = SessionService(db_session)
    session_record = service.create_session(user.id)

    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)
    response = await client.post("/auth/logout")
    assert response.status_code == 200

    audit_events = db_session.query(AuditLogEntry).filter(AuditLogEntry.event_type == "auth.logout").all()
    assert len(audit_events) == 1
    assert audit_events[0].actor_user_id == user.id
