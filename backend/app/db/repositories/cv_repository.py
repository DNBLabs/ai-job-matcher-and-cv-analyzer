"""Owner-scoped persistence queries for CV records."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Cv


class CvRepository:
    """Load and list CV metadata scoped to a single User Account."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an active SQLAlchemy session.

        Args:
            session: Unit-of-work session for database operations.
        """
        self._session = session

    def get_by_id_for_user(self, cv_id: uuid.UUID, user_id: uuid.UUID) -> Cv | None:
        """Return an active CV when it belongs to the given user, otherwise None.

        Soft-deleted CVs are treated as missing so callers can respond with 404.

        Args:
            cv_id: CV primary key.
            user_id: Authenticated User Account id.

        Returns:
            Cv | None: Matching CV or None for missing/IDOR cases.
        """
        statement = select(Cv).where(
            Cv.id == cv_id,
            Cv.user_id == user_id,
            Cv.deleted_at.is_(None),
        )
        return self._session.scalar(statement)

    def get_by_id_for_owner(self, cv_id: uuid.UUID, user_id: uuid.UUID) -> Cv | None:
        """Return a CV owned by the user, including soft-deleted rows.

        Args:
            cv_id: CV primary key.
            user_id: Authenticated User Account id.

        Returns:
            Cv | None: Matching CV or None when missing or owned by another account.
        """
        statement = select(Cv).where(Cv.id == cv_id, Cv.user_id == user_id)
        return self._session.scalar(statement)

    def create(
        self,
        *,
        cv_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        blob_key: str,
        parsed_text: str | None = None,
    ) -> Cv:
        """Persist a new CV metadata row for an uploaded PDF.

        Args:
            cv_id: Server-generated CV primary key.
            user_id: Owning User Account id.
            name: Display name for the CV.
            blob_key: Fully qualified blob storage key including prefix.
            parsed_text: Safe plain-text extraction from the uploaded PDF.

        Returns:
            Cv: Persisted CV row.
        """
        cv = Cv(
            id=cv_id,
            user_id=user_id,
            name=name,
            blob_key=blob_key,
            parsed_text=parsed_text,
        )
        self._session.add(cv)
        self._session.commit()
        self._session.refresh(cv)
        return cv

    def soft_delete_for_user(self, cv_id: uuid.UUID, user_id: uuid.UUID) -> Cv | None:
        """Soft-delete an owned CV, clearing parsed text while retaining metadata.

        Args:
            cv_id: CV primary key.
            user_id: Authenticated User Account id.

        Returns:
            Cv | None: Soft-deleted CV row, or None when missing or owned by another account.
        """
        cv = self.get_by_id_for_owner(cv_id, user_id)
        if cv is None:
            return None

        if cv.deleted_at is None:
            cv.deleted_at = datetime.now(UTC)
            cv.parsed_text = None

        self._session.commit()
        self._session.refresh(cv)
        return cv

    def list_active_for_user(self, user_id: uuid.UUID) -> list[Cv]:
        """Return non-deleted CVs for the user, most recently uploaded first.

        Args:
            user_id: Authenticated User Account id.

        Returns:
            list[Cv]: Active CV rows for the user.
        """
        statement = (
            select(Cv)
            .where(Cv.user_id == user_id, Cv.deleted_at.is_(None))
            .order_by(Cv.uploaded_at.desc())
        )
        return list(self._session.scalars(statement))
