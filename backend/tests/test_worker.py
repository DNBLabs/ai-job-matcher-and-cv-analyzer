"""Tests for the Analysis Run worker entrypoint and message handler."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from worker.handlers.analysis_run import handle_analysis_run_message
from worker.main import startup_worker


class _RecordingPipeline:
    """Records the runs delegated to it so the handler's gating can be asserted."""

    def __init__(self) -> None:
        self.run_ids: list[uuid.UUID] = []

    def run(self, analysis_run: AnalysisRun, session: Session) -> None:
        """Record the delegated run id without performing any work."""
        _ = session
        self.run_ids.append(analysis_run.id)


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


def test_handler_delegates_queued_run_to_pipeline(
    api_test_db_session: Session,
) -> None:
    """Handler receiving a valid queued run delegates it to the pipeline."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    pipeline = _RecordingPipeline()

    handle_analysis_run_message(
        {"analysis_run_id": str(run.id)}, api_test_db_session, pipeline=pipeline
    )

    assert pipeline.run_ids == [run.id]


def test_handler_acks_unknown_run_id_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise nor delegate when the run does not exist."""
    pipeline = _RecordingPipeline()
    unknown_id = str(uuid.uuid4())
    # Must not raise — poison messages must be acked, not requeued
    handle_analysis_run_message(
        {"analysis_run_id": unknown_id}, api_test_db_session, pipeline=pipeline
    )

    assert pipeline.run_ids == []


def test_handler_acks_missing_field_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise when message has no analysis_run_id field."""
    pipeline = _RecordingPipeline()
    handle_analysis_run_message(
        {"unrelated": "data"}, api_test_db_session, pipeline=pipeline
    )

    assert pipeline.run_ids == []


def test_handler_acks_malformed_run_id_without_raising(
    api_test_db_session: Session,
) -> None:
    """Handler does not raise when analysis_run_id is not a valid UUID."""
    pipeline = _RecordingPipeline()
    handle_analysis_run_message(
        {"analysis_run_id": "not-a-uuid"}, api_test_db_session, pipeline=pipeline
    )

    assert pipeline.run_ids == []


def test_handler_skips_run_in_unexpected_status(
    api_test_db_session: Session,
) -> None:
    """Handler does not delegate a run that is already past QUEUED status."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    run.status = AnalysisRunStatus.SCORING
    api_test_db_session.commit()
    pipeline = _RecordingPipeline()

    handle_analysis_run_message(
        {"analysis_run_id": str(run.id)}, api_test_db_session, pipeline=pipeline
    )

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.SCORING
    assert pipeline.run_ids == []
