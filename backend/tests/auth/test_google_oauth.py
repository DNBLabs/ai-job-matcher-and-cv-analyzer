"""Integration tests for Google OAuth sign-in routes."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.google_oauth import OAUTH_STATE_COOKIE
from app.auth.middleware import SESSION_COOKIE_NAME
from app.db.models import AuditLogEntry, SessionRecord, UserAccount
from tests.auth.conftest import create_test_user


@pytest.mark.asyncio
async def test_google_login_redirects_to_google_with_state_cookie(
    oauth_client: AsyncClient,
) -> None:
    """Login starts OAuth by redirecting to Google and storing the CSRF state nonce."""
    response = await oauth_client.get("/auth/google/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    query = parse_qs(urlparse(location).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["test-google-client-id"]
    assert query["redirect_uri"] == ["http://testserver/auth/google/callback"]
    assert query["scope"] == ["openid email profile"]
    assert len(query["state"][0]) >= 32

    set_cookie = response.headers.get("set-cookie", "")
    assert OAUTH_STATE_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert query["state"][0] in set_cookie


def test_oauth_state_cookie_is_same_site_secure_in_production(auth_settings) -> None:
    """OAuth-state cookie is SameSite=Lax everywhere (ADR-0011).

    Both the SPA (www.getmeajob.dnblabs.co.uk) and API (api.getmeajob.dnblabs.co.uk)
    share the dnblabs.co.uk eTLD+1, so the state cookie is same-site and Lax is
    sufficient. The Secure flag is still set in production (HTTPS only).
    """
    from starlette.responses import RedirectResponse

    from app.auth.google_oauth import apply_oauth_state_cookie

    dev_response = RedirectResponse(url="https://accounts.google.com")
    apply_oauth_state_cookie(dev_response, "state-nonce", auth_settings)
    dev_cookie = dev_response.headers.get("set-cookie", "")
    assert "samesite=lax" in dev_cookie.lower()
    assert "Secure" not in dev_cookie

    prod_response = RedirectResponse(url="https://accounts.google.com")
    prod_settings = auth_settings.model_copy(update={"app_env": "production"})
    apply_oauth_state_cookie(prod_response, "state-nonce", prod_settings)
    prod_cookie = prod_response.headers.get("set-cookie", "")
    assert "samesite=lax" in prod_cookie.lower()
    assert "Secure" in prod_cookie


@pytest.mark.asyncio
async def test_google_callback_rejects_invalid_state_with_audit_log(
    oauth_client: AsyncClient,
    db_session: Session,
) -> None:
    """Invalid or missing OAuth state returns 400 and records a login failure audit event."""
    response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "unused-code", "state": "wrong-state"},
        cookies={OAUTH_STATE_COOKIE: "expected-state"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid OAuth state"

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(OAUTH_STATE_COOKIE in header and ("Max-Age=0" in header or "max-age=0" in header.lower()) for header in set_cookie_headers)

    audit_entries = db_session.query(AuditLogEntry).all()
    assert len(audit_entries) == 1
    assert audit_entries[0].event_type == "auth.login.failure"
    assert audit_entries[0].metadata_json["method"] == "google_oauth"
    assert audit_entries[0].metadata_json["reason"] == "invalid_state"


def test_validate_post_auth_redirect_url_rejects_untrusted_origin() -> None:
    """Post-auth redirects must target an origin from the CORS allowlist."""
    from app.domain.validation import validate_post_auth_redirect_url

    with pytest.raises(ValueError, match="origin is not allowed"):
        validate_post_auth_redirect_url(
            "https://evil.example/phish",
            ["http://localhost:5173"],
        )


def _google_oauth_mock_transport() -> httpx.MockTransport:
    """Return an httpx transport that fakes Google token and userinfo endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={"access_token": "google-access-token", "token_type": "Bearer"},
            )
        if request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "sub": "google-sub-123",
                    "email": "alex@example.com",
                    "email_verified": True,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _patch_google_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace Google OAuth HTTP calls with an in-process mock transport."""
    original_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        return original_async_client(transport=_google_oauth_mock_transport())

    monkeypatch.setattr("app.auth.google_oauth.httpx.AsyncClient", factory)


@pytest.mark.asyncio
async def test_google_callback_creates_user_session_and_redirects_to_dashboard(
    oauth_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful OAuth callback upserts the user, rotates a session, and redirects to the dashboard."""
    login_response = await oauth_client.get("/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    oauth_state_cookie = login_response.cookies[OAUTH_STATE_COOKIE]

    _patch_google_http_client(monkeypatch)

    callback_response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "valid-auth-code", "state": state},
        cookies={OAUTH_STATE_COOKIE: oauth_state_cookie},
        follow_redirects=False,
    )

    assert callback_response.status_code == 307
    assert callback_response.headers["location"] == "http://localhost:5173/dashboard"
    assert SESSION_COOKIE_NAME in callback_response.headers.get("set-cookie", "")

    user = db_session.query(UserAccount).one()
    assert user.email == "alex@example.com"
    assert user.google_sub == "google-sub-123"

    session_count = db_session.query(SessionRecord).count()
    assert session_count == 1

    audit_entries = db_session.query(AuditLogEntry).all()
    assert len(audit_entries) == 1
    assert audit_entries[0].event_type == "auth.login.success"
    assert audit_entries[0].actor_user_id == user.id
    assert audit_entries[0].metadata_json["method"] == "google_oauth"


@pytest.mark.asyncio
async def test_google_callback_matches_existing_user_by_google_sub(
    oauth_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returning Google users are matched by ``google_sub`` without creating duplicate accounts."""
    existing = create_test_user(db_session, email="existing@example.com")
    existing.google_sub = "google-sub-123"
    db_session.commit()

    login_response = await oauth_client.get("/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _patch_google_http_client(monkeypatch)

    callback_response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "valid-auth-code", "state": state},
        cookies={OAUTH_STATE_COOKIE: login_response.cookies[OAUTH_STATE_COOKIE]},
        follow_redirects=False,
    )

    assert callback_response.status_code == 307
    assert db_session.query(UserAccount).count() == 1
    refreshed = db_session.get(UserAccount, existing.id)
    assert refreshed is not None
    assert refreshed.email == "existing@example.com"


@pytest.mark.asyncio
async def test_google_callback_links_existing_email_user_without_google_sub(
    oauth_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First Google sign-in for a magic-link-only account links ``google_sub`` on the existing email."""
    existing = create_test_user(db_session, email="alex@example.com")
    assert existing.google_sub is None

    login_response = await oauth_client.get("/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    _patch_google_http_client(monkeypatch)

    callback_response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "valid-auth-code", "state": state},
        cookies={OAUTH_STATE_COOKIE: login_response.cookies[OAUTH_STATE_COOKIE]},
        follow_redirects=False,
    )

    assert callback_response.status_code == 307
    assert db_session.query(UserAccount).count() == 1
    linked = db_session.get(UserAccount, existing.id)
    assert linked is not None
    assert linked.google_sub == "google-sub-123"


def _patch_google_http_client_with_userinfo(
    monkeypatch: pytest.MonkeyPatch,
    userinfo_payload: dict,
) -> None:
    """Replace Google OAuth HTTP calls with a transport returning custom userinfo."""
    original_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={"access_token": "google-access-token", "token_type": "Bearer"},
            )
        if request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json=userinfo_payload)
        return httpx.Response(404)

    def factory(*args, **kwargs):
        return original_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.auth.google_oauth.httpx.AsyncClient", factory)


@pytest.mark.asyncio
async def test_google_callback_rejects_unverified_email(
    oauth_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Google profiles with unverified email addresses cannot sign in."""
    login_response = await oauth_client.get("/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    _patch_google_http_client_with_userinfo(
        monkeypatch,
        {"sub": "google-sub-123", "email": "alex@example.com", "email_verified": False},
    )

    response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "valid-auth-code", "state": state},
        cookies={OAUTH_STATE_COOKIE: login_response.cookies[OAUTH_STATE_COOKIE]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Google sign-in failed"
    assert db_session.query(UserAccount).count() == 0
    audit_entries = db_session.query(AuditLogEntry).all()
    assert len(audit_entries) == 1
    assert audit_entries[0].metadata_json["reason"] == "token_exchange_failed"


@pytest.mark.asyncio
async def test_google_callback_rejects_conflicting_google_sub_for_existing_email(
    oauth_client: AsyncClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing accounts with a different linked google_sub cannot be hijacked by email match."""
    existing = create_test_user(db_session, email="alex@example.com")
    existing.google_sub = "existing-google-sub"
    db_session.commit()

    login_response = await oauth_client.get("/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    _patch_google_http_client(monkeypatch)

    response = await oauth_client.get(
        "/auth/google/callback",
        params={"code": "valid-auth-code", "state": state},
        cookies={OAUTH_STATE_COOKIE: login_response.cookies[OAUTH_STATE_COOKIE]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Google sign-in failed"
    assert db_session.query(UserAccount).count() == 1
    refreshed = db_session.get(UserAccount, existing.id)
    assert refreshed is not None
    assert refreshed.google_sub == "existing-google-sub"
