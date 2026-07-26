"""Owner-scoped persistence queries for Job Match Results."""

import uuid

from sqlalchemy import ColumnElement, case, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, JobMatchResult
from app.domain.divergence import InterviewLikelihood

# Sort rank per Interview Likelihood, deriving from the enum so it stays the
# single source of truth. Smaller ranks sort first, so ascending order yields
# HIGH → MEDIUM → LOW (which the stored strings would otherwise sort
# alphabetically as high → low → medium — the bug this ordering fixes).
_INTERVIEW_LIKELIHOOD_RANK: dict[InterviewLikelihood, int] = {
    InterviewLikelihood.HIGH: 0,
    InterviewLikelihood.MEDIUM: 1,
    InterviewLikelihood.LOW: 2,
}
# Any value missing from the rank map — a future enum member added in only one
# place, or a malformed stored string — sorts after every known likelihood on
# purpose, surfacing the omission rather than silently reintroducing the bug.
_UNKNOWN_INTERVIEW_LIKELIHOOD_RANK: int = max(_INTERVIEW_LIKELIHOOD_RANK.values()) + 1


def build_interview_likelihood_rank_case() -> ColumnElement[int]:
    """Build a SQL CASE ranking Interview Likelihood HIGH → MEDIUM → LOW.

    Ranks come from ``_INTERVIEW_LIKELIHOOD_RANK`` so the enum is the one source
    of truth; unrecognised values fall to the sentinel rank and sort last.

    Returns:
        ColumnElement[int]: A CASE expression usable as an ORDER BY sort key.
    """
    # Compare against the column (not case(value=...)) so each WHEN inherits the
    # column's Enum type and binds each member to its stored string form.
    whens = [
        (JobMatchResult.interview_likelihood == likelihood, rank)
        for likelihood, rank in _INTERVIEW_LIKELIHOOD_RANK.items()
    ]
    return case(*whens, else_=_UNKNOWN_INTERVIEW_LIKELIHOOD_RANK)


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

    def list_for_run(self, run_id: uuid.UUID) -> list[JobMatchResult]:
        """Return scored listings for an Analysis Run in a deterministic total order.

        Ordering is applied in SQL so any later LIMIT/pagination inherits it:
        Match Score descending, then Interview Likelihood HIGH → MEDIUM → LOW,
        then id ascending as a final tie-break. The likelihood key uses an
        explicit rank CASE because the stored enum strings sort alphabetically
        (high, low, medium), which would place LOW above MEDIUM.

        Args:
            run_id: Parent Analysis Run primary key.

        Returns:
            list[JobMatchResult]: Results for the run in stable ranked order.
        """
        statement = (
            select(JobMatchResult)
            .where(JobMatchResult.analysis_run_id == run_id)
            .order_by(
                JobMatchResult.match_score.desc(),
                build_interview_likelihood_rank_case().asc(),
                JobMatchResult.id.asc(),
            )
        )
        return list(self._session.scalars(statement))
