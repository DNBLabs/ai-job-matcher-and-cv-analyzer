"""Unit tests for AnalysisOrchestrator quota, concurrency, and queue publish."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from app.services.analysis_orchestrator import (
    AnalysisOrchestrator,
    ConcurrentRunBlockedError,
    CvNotAvailableError,
    JobSearchValidationError,
    RunQuotaExceededError,
)
from tests.fakes.fake_job_queue import FakeJobQueue


def _create_user(db_session: Session, *, is_unlimited: bool = False) -> UserAccount:
    """Persist a User Account for orchestrator tests."""
    user = UserAccount(email=f"{uuid.uuid4()}@example.com", is_unlimited=is_unlimited)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_cv(db_session: Session, user: UserAccount) -> Cv:
    """Persist an active CV owned by the given user."""
    cv = Cv(
        user_id=user.id,
        name="Engineer CV",
        blob_key=f"cvs/{user.id}/engineer.pdf",
        parsed_text="Python developer.",
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


def _seed_run(
    db_session: Session,
    *,
    user: UserAccount,
    cv: Cv,
    status: AnalysisRunStatus,
    created_at: datetime,
) -> AnalysisRun:
    """Persist an Analysis Run with an explicit created_at timestamp."""
    run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=status,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=created_at,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _valid_job_search() -> dict[str, object]:
    """Return a minimal valid Job Search payload."""
    return {"role": "Software Engineer", "location": "London", "remote": False}


def test_start_analysis_run_creates_run_and_publishes_queue_message(
    api_test_db_session: Session,
) -> None:
    """Happy path persists a queued run and publishes analysis_run_id after commit."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    job_queue = FakeJobQueue()
    orchestrator = AnalysisOrchestrator(api_test_db_session, job_queue)

    run = orchestrator.start_analysis_run(user, cv.id, _valid_job_search())

    assert run.status == AnalysisRunStatus.QUEUED
    assert run.user_id == user.id
    assert run.cv_id == cv.id
    assert run.job_search_json["role"] == "Software Engineer"
    assert len(job_queue.published_messages) == 1
    assert job_queue.published_messages[0] == {"analysis_run_id": str(run.id)}


def test_start_analysis_run_rejects_quota_exhausted(api_test_db_session: Session) -> None:
    """Standard users cannot start a fourth run within the rolling 24h window."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    for hours_ago in (2, 4, 6):
        _seed_run(
            api_test_db_session,
            user=user,
            cv=cv,
            status=AnalysisRunStatus.COMPLETE,
            created_at=now - timedelta(hours=hours_ago),
        )
    orchestrator = AnalysisOrchestrator(api_test_db_session, FakeJobQueue())

    with pytest.raises(RunQuotaExceededError):
        orchestrator.start_analysis_run(user, cv.id, _valid_job_search(), as_of=now)


def test_start_analysis_run_unlimited_user_bypasses_daily_cap(
    api_test_db_session: Session,
) -> None:
    """Unlimited allowlist accounts skip the rolling 24h run limit."""
    user = _create_user(api_test_db_session, is_unlimited=True)
    cv = _create_cv(api_test_db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    for hours_ago in range(1, 6):
        _seed_run(
            api_test_db_session,
            user=user,
            cv=cv,
            status=AnalysisRunStatus.COMPLETE,
            created_at=now - timedelta(hours=hours_ago),
        )
    job_queue = FakeJobQueue()
    orchestrator = AnalysisOrchestrator(api_test_db_session, job_queue)

    run = orchestrator.start_analysis_run(user, cv.id, _valid_job_search(), as_of=now)

    assert run.status == AnalysisRunStatus.QUEUED
    assert len(job_queue.published_messages) == 1


def test_start_analysis_run_blocks_concurrent_active_run(api_test_db_session: Session) -> None:
    """Users may not start a new run while another is Queued, Scraping, or Scoring."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    _seed_run(
        api_test_db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.SCRAPING,
        created_at=now - timedelta(minutes=5),
    )
    orchestrator = AnalysisOrchestrator(api_test_db_session, FakeJobQueue())

    with pytest.raises(ConcurrentRunBlockedError):
        orchestrator.start_analysis_run(user, cv.id, _valid_job_search(), as_of=now)


def test_start_analysis_run_unlimited_user_still_blocked_by_concurrent_run(
    api_test_db_session: Session,
) -> None:
    """Even unlimited accounts respect the one-concurrent-run rule."""
    user = _create_user(api_test_db_session, is_unlimited=True)
    cv = _create_cv(api_test_db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    _seed_run(
        api_test_db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.QUEUED,
        created_at=now - timedelta(minutes=1),
    )
    orchestrator = AnalysisOrchestrator(api_test_db_session, FakeJobQueue())

    with pytest.raises(ConcurrentRunBlockedError):
        orchestrator.start_analysis_run(user, cv.id, _valid_job_search(), as_of=now)


def test_start_analysis_run_excludes_runs_outside_rolling_window(
    api_test_db_session: Session,
) -> None:
    """Runs older than 24 hours do not consume the daily quota."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    for hours_ago in (2, 4, 30):
        _seed_run(
            api_test_db_session,
            user=user,
            cv=cv,
            status=AnalysisRunStatus.COMPLETE,
            created_at=now - timedelta(hours=hours_ago),
        )
    job_queue = FakeJobQueue()
    orchestrator = AnalysisOrchestrator(api_test_db_session, job_queue)

    run = orchestrator.start_analysis_run(user, cv.id, _valid_job_search(), as_of=now)

    assert run.status == AnalysisRunStatus.QUEUED
    assert len(job_queue.published_messages) == 1


def test_start_analysis_run_rejects_deleted_cv(api_test_db_session: Session) -> None:
    """Deleted CVs cannot be used to start a new Analysis Run."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    cv.deleted_at = datetime.now(UTC)
    api_test_db_session.commit()
    orchestrator = AnalysisOrchestrator(api_test_db_session, FakeJobQueue())

    with pytest.raises(CvNotAvailableError):
        orchestrator.start_analysis_run(user, cv.id, _valid_job_search())


def test_start_analysis_run_rejects_invalid_job_search(api_test_db_session: Session) -> None:
    """Invalid Job Search payloads fail before quota checks or persistence."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    orchestrator = AnalysisOrchestrator(api_test_db_session, FakeJobQueue())

    with pytest.raises(JobSearchValidationError):
        orchestrator.start_analysis_run(
            user,
            cv.id,
            {"role": "Engineer", "location": "Paris", "remote": False},
        )
