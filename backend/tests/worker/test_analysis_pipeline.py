"""Integration tests for the Analysis Run worker pipeline (Tasks 15 + 17).

Exercises fetch → score → persist with fake Job Sources and a fake scoring LLM:
no live network or OpenAI calls. Asserts terminal status rules, result ordering,
FinOps persistence, stable external-id dedup, and multi-source partial failure.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, UserAccount
from app.db.repositories.job_match_result_repository import JobMatchResultRepository
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood
from app.domain.scoring_schema import ScoringLlmOutput
from app.job_sources.base import JobSourceError
from app.services.scoring_service import ScoringService
from tests.fakes.fake_job_source import FakeJobSource, make_listing
from tests.fakes.fake_notification_port import FakeNotificationPort
from tests.fakes.fake_scoring_llm_client import FakeScoringLlmClient
from worker.pipeline import AnalysisRunPipeline


def _create_user(db_session: Session) -> UserAccount:
    user = UserAccount(email=f"{uuid.uuid4()}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_cv(db_session: Session, user: UserAccount, *, parsed_text: str | None = "Python dev.") -> Cv:
    cv = Cv(
        user_id=user.id,
        name="Pipeline CV",
        blob_key=f"cvs/{user.id}/pipeline.pdf",
        parsed_text=parsed_text,
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


def _create_queued_run(db_session: Session, user: UserAccount, cv: Cv) -> AnalysisRun:
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


def _output(*, match_score: int = 82) -> ScoringLlmOutput:
    return ScoringLlmOutput(
        match_score=match_score,
        interview_likelihood=InterviewLikelihood.HIGH,
        matched_skills=["Python"],
        skill_gaps=[],
        red_flags=[],
        talking_points=["Discuss API work"],
    )


def _pipeline(job_source: FakeJobSource, llm: FakeScoringLlmClient, **kwargs) -> AnalysisRunPipeline:
    return AnalysisRunPipeline(
        job_sources=[("adzuna", job_source)],
        scoring_service=ScoringService(llm),
        **kwargs,
    )


def test_pipeline_completes_run_with_scored_results(api_test_db_session: Session) -> None:
    """A fetch-then-score run with listings reaches COMPLETE and persists one row per listing."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(
        listings=[
            make_listing(url="https://example.com/jobs/1"),
            make_listing(url="https://example.com/jobs/2"),
            make_listing(url="https://example.com/jobs/3"),
        ]
    )
    pipeline = _pipeline(source, FakeScoringLlmClient(behaviours=[_output()]))

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.COMPLETE
    assert run.completed_at is not None
    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert len(results) == 3


def test_pipeline_persists_results_sorted_by_match_score_desc(api_test_db_session: Session) -> None:
    """Stored results are returned highest match score first by the default query."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(
        listings=[
            make_listing(url="https://example.com/jobs/1"),
            make_listing(url="https://example.com/jobs/2"),
            make_listing(url="https://example.com/jobs/3"),
        ]
    )
    llm = FakeScoringLlmClient(
        behaviours=[_output(match_score=40), _output(match_score=90), _output(match_score=70)]
    )
    _pipeline(source, llm).run(run, api_test_db_session)

    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert [r.match_score for r in results] == [90, 70, 40]


def test_pipeline_marks_run_failed_when_no_listings(api_test_db_session: Session) -> None:
    """Zero listings after fetching yields a FAILED run with no persisted results."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    pipeline = _pipeline(FakeJobSource(listings=[]), FakeScoringLlmClient(behaviours=[_output()]))

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED
    assert JobMatchResultRepository(api_test_db_session).list_for_run(run.id) == []


def test_pipeline_marks_run_failed_when_source_errors(api_test_db_session: Session) -> None:
    """A Job Source failure (Adzuna-only) results in a FAILED run."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(error=JobSourceError("adzuna down"))
    pipeline = _pipeline(source, FakeScoringLlmClient(behaviours=[_output()]))

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED


def test_pipeline_writes_finops_metadata(api_test_db_session: Session) -> None:
    """The per-run FinOps summary is persisted on analysis_run.finops_json."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(listings=[make_listing()])
    llm = FakeScoringLlmClient(behaviours=[_output()], prompt_tokens=1000, completion_tokens=300)

    _pipeline(source, llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    finops = run.finops_json
    assert finops["listings_scored"] == 1
    assert finops["prompt_tokens"] == 1000
    assert finops["completion_tokens"] == 300
    assert finops["model"] == "gpt-4o"
    assert finops["estimated_usd"] > 0


def test_pipeline_caps_listings_at_max(api_test_db_session: Session) -> None:
    """The pipeline requests at most max_listings from the Job Source."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(listings=[make_listing()])
    pipeline = _pipeline(source, FakeScoringLlmClient(behaviours=[_output()]), max_listings=50)

    pipeline.run(run, api_test_db_session)

    assert source.fetch_calls == [50]


def test_pipeline_marks_run_failed_when_cv_text_missing(api_test_db_session: Session) -> None:
    """A run whose CV has no parsed text fails without invoking the scoring LLM."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user, parsed_text=None)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(listings=[make_listing()])
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _pipeline(source, llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED
    assert llm.call_count == 0


def test_pipeline_derives_stable_external_id_and_dedupes(api_test_db_session: Session) -> None:
    """external_id is the SHA-256 of the listing URL; duplicate URLs persist once."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    duplicate_url = "https://example.com/jobs/dup"
    source = FakeJobSource(
        listings=[make_listing(url=duplicate_url), make_listing(url=duplicate_url)]
    )
    _pipeline(source, FakeScoringLlmClient(behaviours=[_output()])).run(run, api_test_db_session)

    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert len(results) == 1
    assert results[0].external_id == hashlib.sha256(duplicate_url.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Task 17 — multi-source fan-out tests
# ---------------------------------------------------------------------------


def _multi_pipeline(
    sources: list[tuple[str, FakeJobSource]],
    llm: FakeScoringLlmClient,
    **kwargs,
) -> AnalysisRunPipeline:
    return AnalysisRunPipeline(
        job_sources=sources,
        scoring_service=ScoringService(llm),
        **kwargs,
    )


def test_pipeline_fetches_from_both_sources(api_test_db_session: Session) -> None:
    """With two sources registered, both are called and their listings merged."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(listings=[make_listing(url="https://a.com/1", source="adzuna")])
    reed = FakeJobSource(listings=[make_listing(url="https://b.com/1", source="reed")])
    llm = FakeScoringLlmClient(behaviours=[_output(), _output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    assert adzuna.fetch_calls == [50]
    assert reed.fetch_calls == [50]
    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.COMPLETE
    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert len(results) == 2


def test_pipeline_completes_when_one_source_fails(api_test_db_session: Session) -> None:
    """If one source fails but the other returns listings, the run reaches COMPLETE."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(listings=[make_listing(url="https://a.com/1", source="adzuna")])
    reed = FakeJobSource(error=JobSourceError("reed rate-limited"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.COMPLETE
    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert len(results) == 1


def test_pipeline_records_source_failure_metadata(api_test_db_session: Session) -> None:
    """A failed source is recorded in source_failures_json on the run."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(listings=[make_listing(url="https://a.com/1", source="adzuna")])
    reed = FakeJobSource(error=JobSourceError("reed unavailable"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    failures = run.source_failures_json
    assert failures is not None
    assert len(failures["failures"]) == 1
    assert failures["failures"][0]["source"] == "reed"


def test_pipeline_fails_when_all_sources_fail(api_test_db_session: Session) -> None:
    """When every source fails after retries, the run resolves to FAILED."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(error=JobSourceError("adzuna down"))
    reed = FakeJobSource(error=JobSourceError("reed down"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED


def test_pipeline_logs_source_failure_reason(
    api_test_db_session: Session, caplog
) -> None:
    """A failed source's PII-free reason is included in the worker WARNING log.

    Diagnosability gap behind #55: the per-source failure log omitted *why* the
    source failed, so an HTTP 401 from placeholder credentials was invisible.
    """
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(error=JobSourceError("adzuna rejected", reason="http_401"))
    pipeline = _pipeline(source, FakeScoringLlmClient(behaviours=[_output()]))

    with caplog.at_level(logging.WARNING, logger="worker.pipeline"):
        pipeline.run(run, api_test_db_session)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("http_401" in m and "adzuna" in m for m in warnings)


def test_pipeline_sends_completion_email_to_owner_on_complete(
    api_test_db_session: Session,
) -> None:
    """A COMPLETE run emails the owner a deep link to its results page."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(listings=[make_listing()])
    sink = FakeNotificationPort()
    pipeline = _pipeline(
        source,
        FakeScoringLlmClient(behaviours=[_output()]),
        notification_port=sink,
        frontend_base_url="https://app.test",
    )

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.COMPLETE
    assert len(sink.run_complete_emails) == 1
    message = sink.run_complete_emails[0]
    assert message["to_email"] == user.email
    assert message["results_url"] == f"https://app.test/runs/{run.id}"


def test_pipeline_sends_no_completion_email_on_failed(api_test_db_session: Session) -> None:
    """A FAILED run (no listings) sends no completion email."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    sink = FakeNotificationPort()
    pipeline = _pipeline(
        FakeJobSource(listings=[]),
        FakeScoringLlmClient(behaviours=[_output()]),
        notification_port=sink,
        frontend_base_url="https://app.test",
    )

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED
    assert sink.run_complete_emails == []


def test_pipeline_email_failure_does_not_change_terminal_status(
    api_test_db_session: Session,
) -> None:
    """A notification provider outage never demotes a COMPLETE run or loses results."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    source = FakeJobSource(listings=[make_listing()])
    sink = FakeNotificationPort(raise_on_send=True)
    pipeline = _pipeline(
        source,
        FakeScoringLlmClient(behaviours=[_output()]),
        notification_port=sink,
        frontend_base_url="https://app.test",
    )

    pipeline.run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.COMPLETE
    assert len(JobMatchResultRepository(api_test_db_session).list_for_run(run.id)) == 1


def test_pipeline_records_source_success_when_source_ok_with_zero_listings(
    api_test_db_session: Session,
) -> None:
    """A source that responds with 0 listings is recorded in source_failures_json successes."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(listings=[])  # responds OK but returns nothing
    reed = FakeJobSource(error=JobSourceError("reed 403"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    assert run.status == AnalysisRunStatus.FAILED
    meta = run.source_failures_json
    assert meta is not None
    assert "adzuna" in meta["successes"]
    assert meta["failures"][0]["source"] == "reed"


def test_pipeline_classifies_mixed_source_run_as_no_jobs_found(
    api_test_db_session: Session,
) -> None:
    """Mixed OK+fail run is classified NO_JOBS_FOUND by the domain classifier."""
    from app.domain.run_outcomes import RunFailureReason, classify_run_failure

    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(listings=[])
    reed = FakeJobSource(error=JobSourceError("reed unavailable"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    reason = classify_run_failure(run.status, run.source_failures_json)
    assert reason is RunFailureReason.NO_JOBS_FOUND


def test_pipeline_classifies_all_source_fail_as_scrape_failed(
    api_test_db_session: Session,
) -> None:
    """When all sources fail the classifier returns SCRAPE_FAILED (not NO_JOBS_FOUND)."""
    from app.domain.run_outcomes import RunFailureReason, classify_run_failure

    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    adzuna = FakeJobSource(error=JobSourceError("adzuna down"))
    reed = FakeJobSource(error=JobSourceError("reed down"))
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    api_test_db_session.refresh(run)
    reason = classify_run_failure(run.status, run.source_failures_json)
    assert reason is RunFailureReason.SCRAPE_FAILED


def test_pipeline_dedupes_same_url_across_sources(api_test_db_session: Session) -> None:
    """A URL returned by both sources is only scored and persisted once."""
    user = _create_user(api_test_db_session)
    cv = _create_cv(api_test_db_session, user)
    run = _create_queued_run(api_test_db_session, user, cv)
    shared_url = "https://shared.com/job/1"
    adzuna = FakeJobSource(listings=[make_listing(url=shared_url, source="adzuna")])
    reed = FakeJobSource(listings=[make_listing(url=shared_url, source="reed")])
    llm = FakeScoringLlmClient(behaviours=[_output()])

    _multi_pipeline([("adzuna", adzuna), ("reed", reed)], llm).run(run, api_test_db_session)

    results = JobMatchResultRepository(api_test_db_session).list_for_run(run.id)
    assert len(results) == 1
    assert llm.call_count == 1
