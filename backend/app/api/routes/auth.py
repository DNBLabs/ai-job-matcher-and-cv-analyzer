"""Authentication HTTP routes for Google OAuth and magic-link sign-in."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.factory import create_notification_port, create_secret_provider
from app.auth.google_oauth import (
    GOOGLE_OAUTH_CLIENT_ID_SECRET,
    GOOGLE_OAUTH_CLIENT_SECRET_SECRET,
    GoogleOAuthError,
    OAUTH_STATE_COOKIE,
    apply_oauth_state_cookie,
    build_google_authorization_url,
    clear_oauth_state_cookie,
    exchange_code_for_google_profile,
    generate_oauth_state,
    oauth_states_match,
    upsert_user_from_google_profile,
    validate_authorization_code,
    validate_post_auth_redirect_url,
)
from app.auth.magic_link import (
    MagicLinkError,
    build_magic_link_verify_url,
    issue_magic_link_token,
    verify_magic_link_token,
)
from app.auth.middleware import SESSION_COOKIE_NAME, apply_session_cookie
from app.auth.rate_limit import (
    MAGIC_LINK_EMAIL_LIMIT,
    MAGIC_LINK_IP_LIMIT,
    RateLimitExceeded,
    RateLimiter,
    magic_link_email_bucket,
    magic_link_ip_bucket,
)
from app.auth.session import SessionService
from app.api.deps import get_settings_dependency
from app.config import Settings
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.session import get_db_session
from app.domain.validation import normalize_email
from app.ports.notification import NotificationPort
from app.ports.secret_provider import SecretNotFoundError, SecretProvider

router = APIRouter(prefix="/auth", tags=["auth"])


class MagicLinkRequest(BaseModel):
    """Request body for issuing a passwordless sign-in link."""

    email: str = Field(..., min_length=1, max_length=320)


def get_notification_port(settings: Settings = Depends(get_settings_dependency)) -> NotificationPort:
    """Return the configured NotificationPort for transactional email delivery.

    Args:
        settings: Runtime application settings.

    Returns:
        NotificationPort: Backend used to send magic-link emails.
    """
    return create_notification_port(settings)


def get_secret_provider(settings: Settings = Depends(get_settings_dependency)) -> SecretProvider:
    """Return the configured SecretProvider for OAuth client credentials.

    Args:
        settings: Runtime application settings.

    Returns:
        SecretProvider: Backend used to resolve OAuth secrets at request time.
    """
    return create_secret_provider(settings)


def _resolve_google_oauth_client_id(secret_provider: SecretProvider) -> str:
    """Return the configured Google OAuth client id or raise a sanitized HTTP error.

    Args:
        secret_provider: Backend used to resolve OAuth secrets.

    Returns:
        str: Google OAuth client identifier.

    Raises:
        HTTPException: When OAuth client credentials are not configured.
    """
    try:
        return secret_provider.get(GOOGLE_OAUTH_CLIENT_ID_SECRET)
    except SecretNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        ) from error


def _resolve_google_oauth_client_secret(secret_provider: SecretProvider) -> str:
    """Return the configured Google OAuth client secret or raise a sanitized HTTP error.

    Args:
        secret_provider: Backend used to resolve OAuth secrets.

    Returns:
        str: Google OAuth client secret.

    Raises:
        HTTPException: When OAuth client credentials are not configured.
    """
    try:
        return secret_provider.get(GOOGLE_OAUTH_CLIENT_SECRET_SECRET)
    except SecretNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        ) from error


def _oauth_failure_response(
    *,
    status_code: int,
    detail: str,
    settings: Settings,
    db: Session,
    reason: str,
) -> JSONResponse:
    """Return a sanitized OAuth error and clear the short-lived state cookie.

    Args:
        status_code: HTTP status for the failure response.
        detail: Generic client-facing error message.
        settings: Runtime configuration for cookie attributes.
        db: Request-scoped database session for audit logging.
        reason: Stable audit metadata reason code.

    Returns:
        JSONResponse: Error payload with ``oauth_state`` cookie cleared.
    """
    AuditLogRepository(db).append_event(
        event_type="auth.login.failure",
        metadata={"method": "google_oauth", "reason": reason},
    )
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    clear_oauth_state_cookie(response, settings)
    return response


@router.get("/google/login")
async def google_login(
    settings: Settings = Depends(get_settings_dependency),
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> RedirectResponse:
    """Redirect the browser to Google OAuth with a CSRF ``state`` nonce.

    Stores ``state`` in an HttpOnly cookie validated on callback.
    Source: https://developers.google.com/identity/protocols/oauth2/web-server

    Args:
        settings: Runtime configuration including redirect URIs.
        secret_provider: Provider for ``GOOGLE_OAUTH_CLIENT_ID``.

    Returns:
        RedirectResponse: Temporary redirect to Google's authorization endpoint.
    """
    state = generate_oauth_state()
    client_id = _resolve_google_oauth_client_id(secret_provider)
    authorization_url = build_google_authorization_url(
        client_id=client_id,
        redirect_uri=settings.google_oauth_redirect_uri,
        state=state,
    )
    response = RedirectResponse(url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    apply_oauth_state_cookie(response, state, settings)
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    settings: Settings = Depends(get_settings_dependency),
    secret_provider: SecretProvider = Depends(get_secret_provider),
    db: Session = Depends(get_db_session),
) -> Response:
    """Complete Google OAuth, upsert the User Account, and issue a session cookie.

    Validates the OAuth ``state`` nonce, exchanges the authorization code with Google,
    and redirects to the configured dashboard URL on success.
    Source: https://developers.google.com/identity/protocols/oauth2/web-server

    Args:
        request: Incoming callback request carrying the OAuth state cookie.
        code: Authorization code from Google.
        state: CSRF nonce echoed by Google.
        settings: Runtime configuration including redirect targets.
        secret_provider: Provider for Google OAuth client credentials.
        db: Request-scoped database session.

    Returns:
        RedirectResponse on success, JSONResponse with sanitized errors otherwise.
    """
    stored_state = request.cookies.get(OAUTH_STATE_COOKIE)

    if not oauth_states_match(stored_state, state):
        return _oauth_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state",
            settings=settings,
            db=db,
            reason="invalid_state",
        )

    if not code:
        return _oauth_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
            settings=settings,
            db=db,
            reason="missing_code",
        )

    try:
        validated_code = validate_authorization_code(code)
        redirect_target = validate_post_auth_redirect_url(
            settings.post_auth_redirect_url,
            settings.cors_origins,
        )
    except GoogleOAuthError:
        return _oauth_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth callback request",
            settings=settings,
            db=db,
            reason="invalid_callback_input",
        )

    existing_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    client_id = _resolve_google_oauth_client_id(secret_provider)
    client_secret = _resolve_google_oauth_client_secret(secret_provider)

    try:
        profile = await exchange_code_for_google_profile(
            code=validated_code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
        )
        user = upsert_user_from_google_profile(db, profile)
    except (httpx.HTTPError, ValueError, KeyError, GoogleOAuthError):
        return _oauth_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google sign-in failed",
            settings=settings,
            db=db,
            reason="token_exchange_failed",
        )

    session_service = SessionService(db)
    session_record = session_service.rotate_session(user.id, existing_session_id=existing_session_id)
    AuditLogRepository(db).append_event(
        event_type="auth.login.success",
        actor_user_id=user.id,
        metadata={"method": "google_oauth"},
    )

    response = RedirectResponse(
        url=redirect_target,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    apply_session_cookie(response, session_record.id, settings)
    clear_oauth_state_cookie(response, settings)
    return response


def _client_ip(request: Request) -> str:
    """Return the client IP address used for magic-link rate limiting.

    Args:
        request: Incoming HTTP request.

    Returns:
        str: Observed client IP or a sentinel when unavailable.
    """
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def _magic_link_failure_response(
    *,
    status_code: int,
    detail: str,
    db: Session,
    reason: str,
) -> JSONResponse:
    """Return a sanitized magic-link verification error with audit logging.

    Args:
        status_code: HTTP status for the failure response.
        detail: Generic client-facing error message.
        db: Request-scoped database session for audit logging.
        reason: Stable audit metadata reason code.

    Returns:
        JSONResponse: Error payload without sensitive token details.
    """
    AuditLogRepository(db).append_event(
        event_type="auth.login.failure",
        metadata={"method": "magic_link", "reason": reason},
    )
    return JSONResponse(status_code=status_code, content={"detail": detail})


@router.post("/magic-link")
async def request_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    settings: Settings = Depends(get_settings_dependency),
    notification_port: NotificationPort = Depends(get_notification_port),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    """Issue a single-use magic-link token and deliver it via the notification port.

    Enforces per-email and per-IP rate limits and persists only the token hash.

    Args:
        payload: Request body containing the Job Seeker email address.
        request: Incoming HTTP request for client IP extraction.
        settings: Runtime configuration including API base URL.
        notification_port: Provider used to email the verification link.
        db: Request-scoped database session.

    Returns:
        JSONResponse: Generic success message that avoids email enumeration.
    """
    try:
        normalized_email = normalize_email(payload.email)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid email address"},
        )

    rate_limiter = RateLimiter(db)
    client_ip = _client_ip(request)
    try:
        rate_limiter.check_and_increment(
            bucket_key=magic_link_email_bucket(normalized_email),
            limit=MAGIC_LINK_EMAIL_LIMIT,
        )
        rate_limiter.check_and_increment(
            bucket_key=magic_link_ip_bucket(client_ip),
            limit=MAGIC_LINK_IP_LIMIT,
        )
    except RateLimitExceeded:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many magic-link requests"},
        )

    plain_token, _token_row = issue_magic_link_token(db, normalized_email)
    verify_url = build_magic_link_verify_url(
        api_base_url=settings.api_base_url,
        plain_token=plain_token,
    )
    notification_port.send_magic_link_email(to_email=normalized_email, verify_url=verify_url)
    AuditLogRepository(db).append_event(
        event_type="auth.magic_link.requested",
        metadata={"email_domain": normalized_email.split("@", 1)[-1]},
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"detail": "If that email is registered, a sign-in link has been sent."},
    )


@router.get("/magic-link/verify")
async def verify_magic_link(
    request: Request,
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings_dependency),
    db: Session = Depends(get_db_session),
) -> Response:
    """Verify a magic-link token, create a session, and redirect to the dashboard.

    Args:
        request: Incoming verification request carrying any existing session cookie.
        token: Single-use token from the emailed verification link.
        settings: Runtime configuration including redirect targets.
        db: Request-scoped database session.

    Returns:
        RedirectResponse on success, JSONResponse with sanitized errors otherwise.
    """
    if not token:
        return _magic_link_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired magic link",
            db=db,
            reason="missing_token",
        )

    try:
        redirect_target = validate_post_auth_redirect_url(
            settings.post_auth_redirect_url,
            settings.cors_origins,
        )
    except GoogleOAuthError:
        return _magic_link_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired magic link",
            db=db,
            reason="invalid_redirect_configuration",
        )

    existing_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        user = verify_magic_link_token(db, token)
    except MagicLinkError:
        return _magic_link_failure_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired magic link",
            db=db,
            reason="invalid_or_expired_token",
        )

    session_service = SessionService(db)
    session_record = session_service.rotate_session(user.id, existing_session_id=existing_session_id)
    AuditLogRepository(db).append_event(
        event_type="auth.login.success",
        actor_user_id=user.id,
        metadata={"method": "magic_link"},
    )

    response = RedirectResponse(
        url=redirect_target,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    apply_session_cookie(response, session_record.id, settings)
    return response
