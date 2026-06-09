"""Owner-scoped persistence queries for Analysis Runs."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun


class AnalysisRunRepository:
    """Load and list Analysis Runs scoped to a single User Account."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an active SQLAlchemy session.

        Args:
            session: Unit-of-work session for database operations.
        """
        self._session = session

    def get_by_id_for_user(self, run_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisRun | None:
        """Return a run when it belongs to the given user, otherwise None.

        Args:
            run_id: Analysis Run primary key.
            user_id: Authenticated User Account id.

        Returns:
            AnalysisRun | None: Matching run or None for missing/IDOR cases.
        """
        statement = select(AnalysisRun).where(
            AnalysisRun.id == run_id,
            AnalysisRun.user_id == user_id,
        )
        return self._session.scalar(statement)

    def get_by_id(self, run_id: uuid.UUID) -> AnalysisRun | None:
        """Return a run by primary key without user-scoping, for internal worker use.

        Args:
            run_id: Analysis Run primary key.

        Returns:
            AnalysisRun | None: Matching run or None when not found.
        """
        statement = select(AnalysisRun).where(AnalysisRun.id == run_id)
        return self._session.scalar(statement)

    def list_for_user(self, user_id: uuid.UUID) -> list[AnalysisRun]:
        """Return all Analysis Runs owned by the user, newest first.

        Args:
            user_id: Authenticated User Account id.

        Returns:
            list[AnalysisRun]: Runs belonging to the user.
        """
        statement = (
            select(AnalysisRun)
            .where(AnalysisRun.user_id == user_id)
            .order_by(AnalysisRun.created_at.desc())
        )
        return list(self._session.scalars(statement))
