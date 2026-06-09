"""Tests for the Analysis Run worker entrypoint and message handler."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from worker.handlers.analysis_run import handle_analysis_run_message
from worker.main import startup_worker


def _create_user(db_session: Session) -> UserAccount:
    """Persist a User Account for worker handler tests."""
    user = UserAccount(email=f"{uuid.uuid4()}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_cv(db_session: Session, user: UserAccount) -> Cv:
    """Persist an active CV owned by the given user."""
    cv = Cv(
        user_id=user.id,
        name="Worker CV",
        blob_key=f"cvs/{user.id}/worker.pdf",
        parsed_text="Python developer.",
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


def _create_queued_run(db_session: Session, user: UserAccount, cv: Cv) -> AnalysisRun:
    """Persist a queued Analysis Run ready for worker processing."""
    run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=AnalysisRunStatus.QUEUED,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_worker_startup_signals_ready() -> None:
    """Worker startup reports ready before entering the consume loop."""
    assert startup_worker() == "ready"


def test_handler_transitions_queued_run_to_scoring(
    api_test_db_session: Session,
) -> None:
    """Handler receiving a valid run ID transitions status QUEUED → SCRAPING → SCORING."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)

    handle_analysis_run_message({"analysis_run_id": str(run.id)}, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.SCORING


def test_handler_acks_unknown_run_id_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise when analysis_run_id references a non-existent run."""
    unknown_id = str(uuid.uuid4())
    # Must not raise — poison messages must be acked, not requeued
    handle_analysis_run_message({"analysis_run_id": unknown_id}, api_test_db_session)


def test_handler_acks_missing_field_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise when message has no analysis_run_id field."""
    handle_analysis_run_message({"unrelated": "data"}, api_test_db_session)


def test_handler_acks_malformed_run_id_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise when analysis_run_id is not a valid UUID."""
    handle_analysis_run_message({"analysis_run_id": "not-a-uuid"}, api_test_db_session)


def test_handler_skips_run_in_unexpected_status(
    api_test_db_session: Session,
) -> None:
    """Handler does not modify a run that is already past QUEUED status."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    run.status = AnalysisRunStatus.SCORING
    api_test_db_session.commit()

    handle_analysis_run_message({"analysis_run_id": str(run.id)}, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.SCORING
