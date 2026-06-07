"""Postgres-backed session lifecycle for HttpOnly session cookies."""

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.db.models import SessionRecord, UserAccount

SESSION_IDLE_TIMEOUT = timedelta(hours=24)
SESSION_ABSOLUTE_TIMEOUT = timedelta(days=7)
SESSION_ID_MAX_LENGTH = 128
SESSION_ID_MIN_LENGTH = 32
# Matches secrets.token_urlsafe output used by _generate_session_id.
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


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


def is_valid_session_id(session_id: str) -> bool:
    """Return True when a cookie value matches the expected opaque session format.

    Rejects oversize or malformed values at the API boundary before database lookup.
    Generated ids use ``secrets.token_urlsafe`` (URL-safe base64).
    Source: https://docs.python.org/3/library/secrets.html#secrets.token_urlsafe

    Args:
        session_id: Raw session cookie value from the incoming request.

    Returns:
        bool: True when the value is a plausible server-issued session identifier.
    """
    if not session_id or len(session_id) > SESSION_ID_MAX_LENGTH:
        return False
    if len(session_id) < SESSION_ID_MIN_LENGTH:
        return False
    return _SESSION_ID_PATTERN.match(session_id) is not None


class SessionService:
    """Create, validate, rotate, and clean up server-side session rows."""

    def __init__(self, db: Session) -> None:
        """Bind the service to an active SQLAlchemy session.

        Args:
            db: Unit-of-work session for database operations.
        """
        self._db = db

    def create_session(
        self,
        user_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> SessionRecord:
        """Create a new session row for a User Account.

        Args:
            user_id: Owner of the new session.
            now: Optional clock override for deterministic tests.

        Returns:
            SessionRecord: Persisted session with idle and absolute expiry timestamps.
        """
        current_time = _store_utc(now or datetime.now(UTC))
        session_record = SessionRecord(
            id=self._generate_session_id(),
            user_id=user_id,
            created_at=current_time,
            last_seen_at=current_time,
            idle_expires_at=_store_utc(current_time + SESSION_IDLE_TIMEOUT),
            absolute_expires_at=_store_utc(current_time + SESSION_ABSOLUTE_TIMEOUT),
        )
        self._db.add(session_record)
        self._db.commit()
        self._db.refresh(session_record)
        return session_record

    def rotate_session(
        self,
        user_id: uuid.UUID,
        *,
        existing_session_id: str | None = None,
        now: datetime | None = None,
    ) -> SessionRecord:
        """Issue a fresh session on successful authentication and drop the prior one.

        Args:
            user_id: User Account receiving the rotated session.
            existing_session_id: Optional prior session id to invalidate.
            now: Optional clock override for deterministic tests.

        Returns:
            SessionRecord: Newly created session row.
        """
        if existing_session_id and is_valid_session_id(existing_session_id):
            self.invalidate_session(existing_session_id)
        return self.create_session(user_id, now=now)

    def resolve_session(
        self,
        session_id: str,
        *,
        now: datetime | None = None,
    ) -> UserAccount | None:
        """Validate a session cookie value and return the authenticated user.

        Args:
            session_id: Opaque session identifier from the HttpOnly cookie.
            now: Optional clock override for deterministic tests.

        Returns:
            UserAccount | None: Authenticated user when valid; otherwise ``None``.
        """
        if not is_valid_session_id(session_id):
            return None

        current_time = _as_utc(now or datetime.now(UTC))
        session_record = self._db.get(SessionRecord, session_id)
        if session_record is None:
            return None

        absolute_expires_at = _as_utc(session_record.absolute_expires_at)
        idle_expires_at = _as_utc(session_record.idle_expires_at)
        if current_time >= absolute_expires_at or current_time >= idle_expires_at:
            self.invalidate_session(session_id)
            return None

        session_record.last_seen_at = _store_utc(current_time)
        refreshed_idle_expiry = current_time + SESSION_IDLE_TIMEOUT
        session_record.idle_expires_at = _store_utc(min(refreshed_idle_expiry, absolute_expires_at))
        self._db.commit()

        return self._db.get(UserAccount, session_record.user_id)

    def invalidate_session(self, session_id: str) -> None:
        """Delete a session row, for sign-out or failed validation.

        Args:
            session_id: Session identifier to remove from the store.
        """
        if not is_valid_session_id(session_id):
            return
        session_record = self._db.get(SessionRecord, session_id)
        if session_record is None:
            return
        self._db.delete(session_record)
        self._db.commit()

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        """Delete sessions whose idle or absolute expiry has passed.

        Args:
            now: Optional clock override for deterministic tests.

        Returns:
            int: Number of deleted session rows.
        """
        current_time = _store_utc(now or datetime.now(UTC))
        delete_statement = delete(SessionRecord).where(
            or_(
                SessionRecord.idle_expires_at <= current_time,
                SessionRecord.absolute_expires_at <= current_time,
            )
        )
        result = self._db.execute(delete_statement)
        self._db.commit()
        return result.rowcount or 0

    @staticmethod
    def _generate_session_id() -> str:
        """Return a high-entropy opaque session identifier.

        Returns:
            str: URL-safe token suitable for cookie storage.
        """
        return secrets.token_urlsafe(32)
