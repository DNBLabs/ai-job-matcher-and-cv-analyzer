"""Authentication HTTP routes for Google OAuth and future magic-link flows."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.adapters.factory import create_secret_provider
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
from app.auth.middleware import SESSION_COOKIE_NAME, apply_session_cookie
from app.auth.session import SessionService
from app.api.deps import get_settings_dependency
from app.config import Settings
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.session import get_db_session
from app.ports.secret_provider import SecretNotFoundError, SecretProvider

router = APIRouter(prefix="/auth", tags=["auth"])


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
