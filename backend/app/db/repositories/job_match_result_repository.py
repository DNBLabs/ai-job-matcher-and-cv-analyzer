"""Owner-scoped persistence queries for Job Match Results."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, JobMatchResult


class JobMatchResultRepository:
    """Load Job Match Results scoped through Analysis Run ownership."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to an active SQLAlchemy session.

        Args:
            session: Unit-of-work session for database operations.
        """
        self._session = session

    def get_by_id_for_user(self, result_id: uuid.UUID, user_id: uuid.UUID) -> JobMatchResult | None:
        """Return a result when its parent run belongs to the given user, otherwise None.

        Args:
            result_id: Job Match Result primary key.
            user_id: Authenticated User Account id.

        Returns:
            JobMatchResult | None: Matching result or None for missing/IDOR cases.
        """
        statement = (
            select(JobMatchResult)
            .join(AnalysisRun, JobMatchResult.analysis_run_id == AnalysisRun.id)
            .where(
                JobMatchResult.id == result_id,
                AnalysisRun.user_id == user_id,
            )
        )
        return self._session.scalar(statement)
