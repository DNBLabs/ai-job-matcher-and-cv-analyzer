"""Application service to start Analysis Runs with quota and queue orchestration."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.db.repositories.cv_repository import CvRepository
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.job_search import JobSearch, validate_job_search
from app.domain.quota import (
    count_runs_toward_quota,
    evaluate_run_quota,
    has_active_run_from_statuses,
)
from app.ports.job_queue import JobQueue


class RunQuotaExceededError(Exception):
    """Raised when a standard user has exhausted the rolling 24h run quota."""


class ConcurrentRunBlockedError(Exception):
    """Raised when the user already has an active Analysis Run."""


class CvNotAvailableError(Exception):
    """Raised when the CV is missing, deleted, or not owned by the user."""


class JobSearchValidationError(ValueError):
    """Raised when Job Search input fails schema validation."""


class AnalysisOrchestrator:
    """Create Analysis Runs, enforce quota rules, and publish worker queue messages."""

    def __init__(self, session: Session, job_queue: JobQueue) -> None:
        """Bind the orchestrator to a database session and JobQueue port.

        Args:
            session: Request-scoped SQLAlchemy session.
            job_queue: Queue adapter for publishing ``analysis_run_id`` messages.
        """
        self._session = session
        self._job_queue = job_queue

    def start_analysis_run(
        self,
        user: UserAccount,
        cv_id: uuid.UUID,
        job_search_raw: dict[str, Any],
        *,
        as_of: datetime | None = None,
    ) -> AnalysisRun:
        """Validate inputs, enforce quota/concurrency, persist a run, and enqueue work.

        Args:
            user: Authenticated User Account starting the Analysis Run.
            cv_id: Owned CV primary key to analyze.
            job_search_raw: Untrusted Job Search payload from the API boundary.
            as_of: Reference time for rolling quota evaluation (defaults to UTC now).

        Returns:
            AnalysisRun: Newly created run in ``queued`` status.

        Raises:
            CvNotAvailableError: When the CV is missing or soft-deleted for the owner.
            JobSearchValidationError: When Job Search input fails schema validation.
            ConcurrentRunBlockedError: When another active run exists for the user.
            RunQuotaExceededError: When the daily quota is exhausted for standard users.
        """
        cv = CvRepository(self._session).get_by_id_for_user(cv_id, user.id)
        if cv is None:
            raise CvNotAvailableError("CV is not available for analysis")

        try:
            job_search = validate_job_search(job_search_raw)
        except ValueError as error:
            raise JobSearchValidationError(str(error)) from error

        reference_time = as_of or datetime.now(UTC)
        if reference_time.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")

        user_runs = AnalysisRunRepository(self._session).list_for_user(user.id)
        run_snapshots = [
            (self._as_utc(run.created_at), run.status) for run in user_runs
        ]
        runs_in_window = count_runs_toward_quota(run_snapshots, as_of=reference_time)
        active_blocked = has_active_run_from_statuses([status for _, status in run_snapshots])
        quota_decision = evaluate_run_quota(
            is_unlimited=user.is_unlimited,
            runs_started_in_last_24h=runs_in_window,
            has_active_run=active_blocked,
        )

        if not quota_decision.can_start:
            if quota_decision.concurrent_blocked:
                raise ConcurrentRunBlockedError("An Analysis Run is already in progress")
            raise RunQuotaExceededError("Daily Analysis Run quota exhausted")

        run = self._persist_run(user=user, cv_id=cv.id, job_search=job_search)
        self._job_queue.publish({"analysis_run_id": str(run.id)})
        return run

    def _persist_run(
        self,
        *,
        user: UserAccount,
        cv_id: uuid.UUID,
        job_search: JobSearch,
    ) -> AnalysisRun:
        """Persist a queued Analysis Run and commit before queue publish.

        Args:
            user: Owning User Account.
            cv_id: CV primary key for the run.
            job_search: Validated Job Search criteria.

        Returns:
            AnalysisRun: Committed run row in ``queued`` status.
        """
        run = AnalysisRun(
            user_id=user.id,
            cv_id=cv_id,
            status=AnalysisRunStatus.QUEUED,
            job_search_json=job_search.to_storage_dict(),
            finops_json={},
        )
        self._session.add(run)
        self._session.commit()
        self._session.refresh(run)
        return run

    @staticmethod
    def _as_utc(timestamp: datetime) -> datetime:
        """Normalize database timestamps to timezone-aware UTC for quota math.

        SQLite test fixtures may return naive datetimes; production Postgres stores
        timezone-aware values.

        Args:
            timestamp: Run ``created_at`` value from the database.

        Returns:
            datetime: UTC-aware timestamp suitable for rolling-window comparisons.
        """
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)
