"""Google OAuth 2.0 authorization-code sign-in helpers."""

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.config import Settings
from app.db.models import UserAccount
from app.domain.validation import (
    normalize_email,
    validate_post_auth_redirect_url as validate_allowed_post_auth_redirect_url,
)

# Source: https://developers.google.com/identity/protocols/oauth2/web-server
GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_SCOPES = "openid email profile"
OAUTH_STATE_COOKIE = "oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 600
GOOGLE_OAUTH_CLIENT_ID_SECRET = "GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_OAUTH_CLIENT_SECRET_SECRET = "GOOGLE_OAUTH_CLIENT_SECRET"
GOOGLE_SUB_MAX_LENGTH = 255
AUTHORIZATION_CODE_MAX_LENGTH = 512


class GoogleOAuthError(ValueError):
    """Raised when Google OAuth profile or callback input fails security validation."""


def validate_authorization_code(code: str) -> str:
    """Validate the OAuth authorization code at the API boundary.

    Args:
        code: Authorization code query parameter from Google's redirect.

    Returns:
        str: Non-empty code within expected length bounds.

    Raises:
        GoogleOAuthError: When the code is empty or oversize.
    """
    normalized = code.strip()
    if not normalized:
        raise GoogleOAuthError("authorization code must not be empty")
    if len(normalized) > AUTHORIZATION_CODE_MAX_LENGTH:
        raise GoogleOAuthError("authorization code exceeds maximum length")
    return normalized


def validate_google_sub(google_sub: str) -> str:
    """Validate Google ``sub`` claim before persistence or account lookup.

    Args:
        google_sub: Subject identifier from Google OpenID userinfo.

    Returns:
        str: Trimmed subject identifier safe for database storage.

    Raises:
        GoogleOAuthError: When the subject is empty, oversize, or malformed.
    """
    normalized = google_sub.strip()
    if not normalized:
        raise GoogleOAuthError("google sub must not be empty")
    if len(normalized) > GOOGLE_SUB_MAX_LENGTH:
        raise GoogleOAuthError("google sub exceeds maximum length")
    if any(character in normalized for character in ("\x00", "\n", "\r")):
        raise GoogleOAuthError("google sub contains invalid characters")
    return normalized


def validate_post_auth_redirect_url(redirect_url: str, allowed_origins: list[str]) -> str:
    """Validate dashboard redirect targets against the configured CORS allowlist.

    Args:
        redirect_url: Dashboard URL used after successful sign-in.
        allowed_origins: Parsed CORS allowlist from application settings.

    Returns:
        str: Validated redirect URL.

    Raises:
        GoogleOAuthError: When the redirect origin is not explicitly allowed.
    """
    try:
        return validate_allowed_post_auth_redirect_url(redirect_url, allowed_origins)
    except ValueError as error:
        raise GoogleOAuthError(str(error)) from error


@dataclass(frozen=True)
class GoogleUserProfile:
    """Normalized Google OpenID profile fields used for User Account upsert."""

    google_sub: str
    email: str


def generate_oauth_state() -> str:
    """Return a high-entropy OAuth ``state`` nonce for CSRF protection.

    Google recommends a unique random ``state`` value validated on callback.
    Source: https://developers.google.com/identity/protocols/oauth2/web-server

    Returns:
        str: URL-safe state token stored server-side until callback.
    """
    return secrets.token_urlsafe(32)


def build_google_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    """Build the Google authorization endpoint URL for the web-server flow.

    Args:
        client_id: OAuth client identifier from SecretProvider.
        redirect_uri: Registered callback URL for this application.
        state: CSRF nonce echoed by Google on redirect.

    Returns:
        str: Absolute URL to redirect the browser to Google sign-in.
    """
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": GOOGLE_OAUTH_SCOPES,
            "state": state,
            "access_type": "online",
            "include_granted_scopes": "true",
        }
    )
    return f"{GOOGLE_AUTHORIZATION_URL}?{query}"


def oauth_states_match(expected_state: str | None, received_state: str | None) -> bool:
    """Return True when callback ``state`` matches the stored OAuth nonce.

    Uses constant-time comparison to reduce timing side channels.

    Args:
        expected_state: Value previously stored in the OAuth state cookie.
        received_state: ``state`` query parameter from Google's redirect.

    Returns:
        bool: True when both values are present and equal.
    """
    if not expected_state or not received_state:
        return False
    return secrets.compare_digest(expected_state, received_state)


def apply_oauth_state_cookie(response: Response, state: str, settings: Settings) -> None:
    """Persist the OAuth CSRF nonce in a short-lived HttpOnly cookie.

    Source: https://fastapi.tiangolo.com/advanced/response-cookies/

    Args:
        response: Outgoing redirect response for the login route.
        state: Random nonce sent to Google and validated on callback.
        settings: Runtime configuration controlling Secure flag behavior.
    """
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_oauth_state_cookie(response: Response, settings: Settings) -> None:
    """Remove the OAuth state cookie after callback processing.

    Args:
        response: Outgoing redirect or error response.
        settings: Runtime configuration controlling Secure flag behavior.
    """
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


async def exchange_code_for_google_profile(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    http_client: httpx.AsyncClient | None = None,
) -> GoogleUserProfile:
    """Exchange an authorization code for Google profile data.

    Uses the OAuth 2.0 authorization code grant against Google's token endpoint,
    then loads OpenID userinfo. Source:
    https://developers.google.com/identity/protocols/oauth2/web-server

    Args:
        code: Authorization code from Google's callback query string.
        client_id: OAuth client identifier.
        client_secret: OAuth client secret.
        redirect_uri: Callback URL registered with Google.
        http_client: Optional HTTP client for tests.

    Returns:
        GoogleUserProfile: Google subject and verified email for upsert.

    Raises:
        httpx.HTTPStatusError: When Google token or userinfo requests fail.
        ValueError: When Google omits required profile fields.
    """
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10.0)
    try:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
        payload = userinfo_response.json()
    finally:
        if owns_client:
            await client.aclose()

    google_sub = payload.get("sub")
    email = payload.get("email")
    email_verified = payload.get("email_verified")
    if not google_sub or not email:
        raise ValueError("Google profile response missing required fields")
    if email_verified is not True:
        raise GoogleOAuthError("Google email address is not verified")

    return GoogleUserProfile(
        google_sub=validate_google_sub(str(google_sub)),
        email=normalize_email(str(email)),
    )


def upsert_user_from_google_profile(db: Session, profile: GoogleUserProfile) -> UserAccount:
    """Create or match a User Account from Google ``sub`` and email.

    Existing accounts match on ``google_sub`` first, then normalized email.
    Email matches without ``google_sub`` are linked on first Google sign-in.

    Args:
        db: Request-scoped database session.
        profile: Verified Google OpenID profile.

    Returns:
        UserAccount: Persisted Job Seeker or Admin account.
    """
    by_sub = db.scalar(select(UserAccount).where(UserAccount.google_sub == profile.google_sub))
    if by_sub is not None:
        return by_sub

    by_email = db.scalar(select(UserAccount).where(UserAccount.email == profile.email))
    if by_email is not None:
        if by_email.google_sub is not None and by_email.google_sub != profile.google_sub:
            raise GoogleOAuthError("existing account google_sub does not match Google profile")
        if by_email.google_sub is None:
            by_email.google_sub = profile.google_sub
            db.commit()
            db.refresh(by_email)
        return by_email

    user = UserAccount(email=profile.email, google_sub=profile.google_sub)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
