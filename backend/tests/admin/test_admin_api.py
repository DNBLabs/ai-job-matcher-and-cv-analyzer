"""Integration tests for operator-only admin HTTP routes."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService
from app.db.models import AuditLogEntry, UserAccount
from tests.auth.conftest import create_test_user


def _authenticate_client(client: AsyncClient, db_session: Session, user: UserAccount) -> None:
    """Attach a valid session cookie for the given user to the test client."""
    session_record = SessionService(db_session).create_session(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)


def _create_admin(db_session: Session, email: str = "operator@example.com") -> UserAccount:
    """Persist an admin User Account."""
    admin = UserAccount(email=email, is_admin=True, is_unlimited=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_search_users_returns_email_matches(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /admin/users returns accounts whose email contains the query."""
    admin = _create_admin(db_session)
    create_test_user(db_session, email="alice@example.com")
    create_test_user(db_session, email="bob@other.com")
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.get("/admin/users", params={"email": "alice"})

    assert response.status_code == 200
    emails = [row["email"] for row in response.json()]
    assert emails == ["alice@example.com"]


@pytest.mark.asyncio
async def test_search_users_is_case_insensitive(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """Search matches regardless of case."""
    admin = _create_admin(db_session)
    create_test_user(db_session, email="carol@example.com")
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.get("/admin/users", params={"email": "CAROL"})

    assert response.status_code == 200
    assert [row["email"] for row in response.json()] == ["carol@example.com"]


@pytest.mark.asyncio
async def test_search_users_blank_query_returns_empty(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """A blank query must not dump every account."""
    admin = _create_admin(db_session)
    create_test_user(db_session, email="dave@example.com")
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.get("/admin/users", params={"email": ""})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_patch_user_toggles_unlimited_and_writes_audit(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """PATCH updates is_unlimited and appends an audit_log entry."""
    admin = _create_admin(db_session)
    target = create_test_user(db_session, email="erin@example.com")
    assert target.is_unlimited is False
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.patch(
        f"/admin/users/{target.id}",
        json={"is_unlimited": True},
    )

    assert response.status_code == 200
    assert response.json()["is_unlimited"] is True

    db_session.refresh(target)
    assert target.is_unlimited is True

    audit = db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "admin.user.unlimited_toggled")
    )
    assert audit is not None
    assert audit.actor_user_id == admin.id
    assert audit.subject_user_id == target.id
    assert audit.metadata_json == {"is_unlimited": True}


@pytest.mark.asyncio
async def test_patch_unknown_user_returns_404(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """PATCH against a missing account returns a generic 404."""
    admin = _create_admin(db_session)
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.patch(
        f"/admin/users/{uuid.uuid4()}",
        json={"is_unlimited": True},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_invalid_uuid_returns_422(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """A non-UUID path param is rejected before any lookup."""
    admin = _create_admin(db_session)
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.patch("/admin/users/not-a-uuid", json={"is_unlimited": True})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_unknown_fields(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """Extra body fields (e.g. is_admin) are rejected to prevent privilege escalation."""
    admin = _create_admin(db_session)
    target = create_test_user(db_session, email="frank@example.com")
    _authenticate_client(admin_client, db_session, admin)

    response = await admin_client.patch(
        f"/admin/users/{target.id}",
        json={"is_unlimited": True, "is_admin": True},
    )

    assert response.status_code == 422
    db_session.refresh(target)
    assert target.is_admin is False


@pytest.mark.asyncio
async def test_non_admin_gets_404_on_search(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """Non-admin authenticated users cannot discover admin routes."""
    seeker = create_test_user(db_session, email="seeker@example.com")
    _authenticate_client(admin_client, db_session, seeker)

    response = await admin_client.get("/admin/users", params={"email": "seeker"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_gets_404_on_patch(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """Non-admin users cannot toggle unlimited on any account."""
    seeker = create_test_user(db_session, email="seeker@example.com")
    target = create_test_user(db_session, email="victim@example.com")
    _authenticate_client(admin_client, db_session, seeker)

    response = await admin_client.patch(
        f"/admin/users/{target.id}",
        json={"is_unlimited": True},
    )

    assert response.status_code == 404
    db_session.refresh(target)
    assert target.is_unlimited is False


@pytest.mark.asyncio
async def test_anonymous_gets_401(
    admin_client: AsyncClient,
    db_session: Session,
) -> None:
    """Unauthenticated callers are rejected before admin checks."""
    response = await admin_client.get("/admin/users", params={"email": "x"})

    assert response.status_code == 401
