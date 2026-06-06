"""Owner-scoped persistence queries for CV records."""

import uuid

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
