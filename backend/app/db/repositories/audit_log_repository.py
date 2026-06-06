"""Append-only persistence for audit_log entries."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLogEntry
from app.domain.validation import validate_audit_metadata


class AuditLogRepository:
    """Insert-only repository for security and admin audit events."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an active SQLAlchemy session.

        Args:
            session: Unit-of-work session for database operations.
        """
        self._session = session

    def append_event(
        self,
        *,
        event_type: str,
        metadata: dict,
        actor_user_id: uuid.UUID | None = None,
        subject_user_id: uuid.UUID | None = None,
    ) -> AuditLogEntry:
        """Append a new audit event. Updates and deletes are intentionally unsupported.

        Args:
            event_type: Stable event name (e.g. ``auth.login.success``).
            metadata: JSON-serializable context for the event.
            actor_user_id: Optional User Account performing the action.
            subject_user_id: Optional User Account affected by the action.

        Returns:
            AuditLogEntry: Persisted audit row.

        Raises:
            ValueError: When event_type is empty or metadata fails validation.
        """
        normalized_type = event_type.strip()
        if not normalized_type:
            raise ValueError("event_type must not be empty")

        entry = AuditLogEntry(
            event_type=normalized_type,
            actor_user_id=actor_user_id,
            subject_user_id=subject_user_id,
            metadata_json=validate_audit_metadata(metadata),
        )
        self._session.add(entry)
        self._session.commit()
        self._session.refresh(entry)
        return entry
