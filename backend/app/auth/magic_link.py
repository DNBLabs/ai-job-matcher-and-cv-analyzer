"""Magic-link token issuance and verification for passwordless sign-in."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MagicLinkToken, UserAccount
from app.domain.validation import normalize_email

MAGIC_LINK_TOKEN_ENTROPY_BYTES = 32
MAGIC_LINK_EXPIRY = timedelta(minutes=15)
MAGIC_LINK_TOKEN_MAX_LENGTH = 128
_MAGIC_LINK_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class MagicLinkError(ValueError):
    """Raised when magic-link input or token state fails security validation."""


def generate_magic_link_token() -> str:
    """Return a high-entropy single-use magic-link token.

    Uses ``secrets.token_urlsafe`` for at least 256 bits of entropy.
    Source: https://docs.python.org/3/library/secrets.html#secrets.token_urlsafe

    Returns:
        str: Plain token delivered to the user via email (never persisted).
    """
    return secrets.token_urlsafe(MAGIC_LINK_TOKEN_ENTROPY_BYTES)


def hash_magic_link_token(plain_token: str) -> str:
    """Hash a plain magic-link token for database storage.

    Args:
        plain_token: Token from the verification query string.

    Returns:
        str: Lowercase SHA-256 hex digest stored in ``magic_link_token``.
    """
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()


def validate_magic_link_token(plain_token: str) -> str:
    """Validate a magic-link token at the API boundary.

    Args:
        plain_token: Raw ``token`` query parameter from the verify route.

    Returns:
        str: Trimmed token safe for hashing and lookup.

    Raises:
        MagicLinkError: When the token is empty, oversize, or malformed.
    """
    normalized = plain_token.strip()
    if not normalized:
        raise MagicLinkError("magic link token must not be empty")
    if len(normalized) > MAGIC_LINK_TOKEN_MAX_LENGTH:
        raise MagicLinkError("magic link token exceeds maximum length")
    if not _MAGIC_LINK_TOKEN_PATTERN.match(normalized):
        raise MagicLinkError("magic link token contains invalid characters")
    return normalized


def build_magic_link_verify_url(*, api_base_url: str, plain_token: str) -> str:
    """Build the absolute verification URL emailed to the Job Seeker.

    Args:
        api_base_url: Public API origin used for auth callbacks.
        plain_token: Single-use token included in the query string.

    Returns:
        str: Absolute URL for ``GET /auth/magic-link/verify``.
    """
    base = api_base_url.rstrip("/")
    return f"{base}/auth/magic-link/verify?token={plain_token}"


def issue_magic_link_token(
    db: Session,
    email: str,
    *,
    now: datetime | None = None,
) -> tuple[str, MagicLinkToken]:
    """Persist a hashed magic-link token and return the plain token for email delivery.

    Args:
        db: Request-scoped database session.
        email: Normalized recipient email address.
        now: Optional clock override for deterministic tests.

    Returns:
        tuple[str, MagicLinkToken]: Plain token for email and persisted hash row.
    """
    current_time = _store_utc(now or datetime.now(UTC))
    plain_token = generate_magic_link_token()
    token_row = MagicLinkToken(
        email=email,
        token_hash=hash_magic_link_token(plain_token),
        expires_at=_store_utc(current_time + MAGIC_LINK_EXPIRY),
    )
    db.add(token_row)
    db.commit()
    db.refresh(token_row)
    return plain_token, token_row


def verify_magic_link_token(
    db: Session,
    plain_token: str,
    *,
    now: datetime | None = None,
) -> UserAccount:
    """Validate a magic-link token, mark it used, and return the authenticated user.

    Args:
        db: Request-scoped database session.
        plain_token: Token from the verification query string.
        now: Optional clock override for deterministic tests.

    Returns:
        UserAccount: Existing or newly created Job Seeker account.

    Raises:
        MagicLinkError: When the token is invalid, expired, or already used.
    """
    validated_token = validate_magic_link_token(plain_token)
    current_time = _as_utc(now or datetime.now(UTC))
    token_hash = hash_magic_link_token(validated_token)

    token_row = db.scalar(select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash))
    if token_row is None:
        raise MagicLinkError("magic link token not found")

    if token_row.used_at is not None:
        raise MagicLinkError("magic link token already used")

    expires_at = _as_utc(token_row.expires_at)
    if current_time >= expires_at:
        raise MagicLinkError("magic link token expired")

    token_row.used_at = _store_utc(current_time)
    user = upsert_user_from_magic_link_email(db, token_row.email)
    db.commit()
    db.refresh(token_row)
    return user


def upsert_user_from_magic_link_email(db: Session, email: str) -> UserAccount:
    """Create or match a User Account from a verified magic-link email.

    Args:
        db: Request-scoped database session.
        email: Normalized email from the verified token row.

    Returns:
        UserAccount: Persisted Job Seeker or Admin account.
    """
    normalized_email = normalize_email(email)
    existing_user = db.scalar(select(UserAccount).where(UserAccount.email == normalized_email))
    if existing_user is not None:
        return existing_user

    user = UserAccount(email=normalized_email)
    db.add(user)
    db.flush()
    return user


def _as_utc(value: datetime) -> datetime:
    """Normalize database datetimes to timezone-aware UTC values.

    Args:
        value: Datetime loaded from PostgreSQL or SQLite.

    Returns:
        datetime: UTC-aware datetime suitable for comparisons.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _store_utc(value: datetime) -> datetime:
    """Convert a datetime to naive UTC for database persistence.

    Args:
        value: UTC-aware or naive datetime to persist.

    Returns:
        datetime: Naive UTC datetime compatible with SQLite and PostgreSQL.
    """
    return _as_utc(value).replace(tzinfo=None)
