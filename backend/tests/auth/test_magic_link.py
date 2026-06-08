"""Integration tests for magic-link sign-in routes."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.db.models import AuditLogEntry, MagicLinkToken, SessionRecord, UserAccount
from tests.auth.conftest import create_test_user


class FakeNotificationPort:
    """In-memory NotificationPort capturing outbound magic-link emails."""

    def __init__(self) -> None:
        """Initialize an empty capture list."""
        self.sent_messages: list[dict[str, str]] = []

    def send_magic_link_email(self, *, to_email: str, verify_url: str) -> None:
        """Record a magic-link email instead of delivering it."""
        self.sent_messages.append({"to_email": to_email, "verify_url": verify_url})


@pytest.fixture
def notification_port() -> FakeNotificationPort:
    """Return a fake notification adapter for magic-link route tests."""
    return FakeNotificationPort()


@pytest.fixture
def magic_link_test_app(auth_settings, db_session: Session, notification_port: FakeNotificationPort):
    """Build a FastAPI app with magic-link dependencies overridden for tests."""
    from app.api.routes.auth import get_notification_port
    from app.main import create_app
    from app.db.session import get_db_session

    from tests.auth.conftest import _bind_test_session_factory

    application = create_app(settings=auth_settings)
    _bind_test_session_factory(application, db_session)

    def override_get_db_session():
        try:
            yield db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session
    application.dependency_overrides[get_notification_port] = lambda: notification_port
    return application


@pytest.fixture
async def magic_link_client(magic_link_test_app) -> AsyncClient:
    """Async HTTP client for magic-link route tests."""
    from httpx import ASGITransport

    transport = ASGITransport(app=magic_link_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def _extract_token_from_notification(notification_port: FakeNotificationPort) -> str:
    """Return the plain token embedded in the last captured verify URL."""
    verify_url = notification_port.sent_messages[-1]["verify_url"]
    query = parse_qs(urlparse(verify_url).query)
    return query["token"][0]


@pytest.mark.asyncio
async def test_magic_link_request_persists_hash_not_plain_token(
    magic_link_client: AsyncClient,
    db_session: Session,
    notification_port: FakeNotificationPort,
) -> None:
    """Issuing a magic link stores only the SHA-256 hash of the token in the database."""
    response = await magic_link_client.post(
        "/auth/magic-link",
        json={"email": "alex@example.com"},
    )

    assert response.status_code == 200
    assert len(notification_port.sent_messages) == 1

    plain_token = _extract_token_from_notification(notification_port)
    stored_rows = db_session.query(MagicLinkToken).all()
    assert len(stored_rows) == 1
    assert stored_rows[0].token_hash == hashlib.sha256(plain_token.encode()).hexdigest()
    assert stored_rows[0].token_hash != plain_token
    assert stored_rows[0].email == "alex@example.com"


@pytest.mark.asyncio
async def test_magic_link_verify_creates_session_and_redirects(
    magic_link_client: AsyncClient,
    db_session: Session,
    notification_port: FakeNotificationPort,
) -> None:
    """Successful verification creates a User Account, session cookie, and dashboard redirect."""
    issue_response = await magic_link_client.post(
        "/auth/magic-link",
        json={"email": "new.seeker@example.com"},
    )
    assert issue_response.status_code == 200

    plain_token = _extract_token_from_notification(notification_port)
    verify_response = await magic_link_client.get(
        "/auth/magic-link/verify",
        params={"token": plain_token},
        follow_redirects=False,
    )

    assert verify_response.status_code == 307
    assert verify_response.headers["location"] == "http://localhost:5173/dashboard"
    assert SESSION_COOKIE_NAME in verify_response.headers.get("set-cookie", "")

    user = db_session.query(UserAccount).filter_by(email="new.seeker@example.com").one()
    sessions = db_session.query(SessionRecord).filter_by(user_id=user.id).all()
    assert len(sessions) == 1

    token_row = db_session.query(MagicLinkToken).one()
    assert token_row.used_at is not None

    audit_events = {entry.event_type for entry in db_session.query(AuditLogEntry).all()}
    assert "auth.login.success" in audit_events


@pytest.mark.asyncio
async def test_magic_link_verify_rejects_second_use(
    magic_link_client: AsyncClient,
    notification_port: FakeNotificationPort,
) -> None:
    """A magic-link token cannot be verified twice."""
    await magic_link_client.post("/auth/magic-link", json={"email": "alex@example.com"})
    plain_token = _extract_token_from_notification(notification_port)

    first_response = await magic_link_client.get(
        "/auth/magic-link/verify",
        params={"token": plain_token},
        follow_redirects=False,
    )
    assert first_response.status_code == 307

    second_response = await magic_link_client.get(
        "/auth/magic-link/verify",
        params={"token": plain_token},
    )
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Invalid or expired magic link"


@pytest.mark.asyncio
async def test_magic_link_verify_rejects_expired_token(
    magic_link_client: AsyncClient,
    db_session: Session,
    notification_port: FakeNotificationPort,
) -> None:
    """Expired magic-link tokens are rejected at verification."""
    await magic_link_client.post("/auth/magic-link", json={"email": "alex@example.com"})
    plain_token = _extract_token_from_notification(notification_port)

    token_row = db_session.query(MagicLinkToken).one()
    token_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    response = await magic_link_client.get(
        "/auth/magic-link/verify",
        params={"token": plain_token},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired magic link"


@pytest.mark.asyncio
async def test_magic_link_rate_limit_returns_429_on_fourth_email_request(
    magic_link_client: AsyncClient,
    notification_port: FakeNotificationPort,
) -> None:
    """The fourth magic-link request for the same email within an hour returns 429."""
    for _ in range(3):
        response = await magic_link_client.post(
            "/auth/magic-link",
            json={"email": "heavy@example.com"},
        )
        assert response.status_code == 200

    fourth_response = await magic_link_client.post(
        "/auth/magic-link",
        json={"email": "heavy@example.com"},
    )
    assert fourth_response.status_code == 429
    assert fourth_response.json()["detail"] == "Too many magic-link requests"
    assert len(notification_port.sent_messages) == 3


@pytest.mark.asyncio
async def test_magic_link_existing_user_can_sign_in(
    magic_link_client: AsyncClient,
    db_session: Session,
    notification_port: FakeNotificationPort,
) -> None:
    """An existing User Account can sign in via magic link without creating a duplicate row."""
    existing_user = create_test_user(db_session, email="existing@example.com")

    await magic_link_client.post("/auth/magic-link", json={"email": "existing@example.com"})
    plain_token = _extract_token_from_notification(notification_port)

    verify_response = await magic_link_client.get(
        "/auth/magic-link/verify",
        params={"token": plain_token},
        follow_redirects=False,
    )
    assert verify_response.status_code == 307

    users = db_session.query(UserAccount).filter_by(email="existing@example.com").all()
    assert len(users) == 1
    assert users[0].id == existing_user.id


def test_hash_token_produces_sha256_hex() -> None:
    """Token hashing uses SHA-256 hex digest for database lookups."""
    from app.auth.magic_link import hash_magic_link_token

    plain = "test-token-value"
    assert hash_magic_link_token(plain) == hashlib.sha256(plain.encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", hash_magic_link_token(plain))
