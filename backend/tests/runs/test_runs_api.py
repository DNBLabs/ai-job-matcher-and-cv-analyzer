"""Integration tests for Analysis Run HTTP routes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService
from app.db.models import AnalysisRun, Cv, JobMatchResult, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood
from tests.auth.conftest import create_test_user
from tests.fakes.fake_job_queue import FakeJobQueue


def _authenticate_client(
    client: AsyncClient,
    db_session: Session,
    user: UserAccount,
) -> None:
    """Attach a valid session cookie for the given user to the test client."""
    session_record = SessionService(db_session).create_session(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)


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


def _valid_job_search() -> dict[str, object]:
    """Return a minimal valid Job Search payload."""
    return {"role": "Software Engineer", "location": "London", "remote": False}


def _seed_run(
    db_session: Session,
    *,
    user: UserAccount,
    cv: Cv,
    status: AnalysisRunStatus,
    created_at: datetime | None = None,
) -> AnalysisRun:
    """Persist an Analysis Run for route tests."""
    run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=status,
        job_search_json=_valid_job_search(),
        finops_json={},
        created_at=created_at or datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _seed_result(db_session: Session, analysis_run: AnalysisRun) -> JobMatchResult:
    """Persist a scored Job Match Result for the given run."""
    result = JobMatchResult(
        analysis_run_id=analysis_run.id,
        source="adzuna",
        external_id="listing-1",
        title="Backend Engineer",
        company="Acme Ltd",
        url="https://example.com/jobs/1",
        match_score=82,
        interview_likelihood=InterviewLikelihood.HIGH,
        breakdown_json={
            "match_score": 82,
            "interview_likelihood": "high",
            "matched_skills": ["Python"],
            "skill_gaps": [],
            "red_flags": [],
            "talking_points": ["Highlight API work"],
        },
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)
    return result


@pytest.mark.asyncio
async def test_post_runs_happy_path_creates_run_and_enqueues(
    runs_client: AsyncClient,
    db_session: Session,
    fake_job_queue: FakeJobQueue,
) -> None:
    """POST /runs persists a queued run and publishes analysis_run_id."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.post(
        "/runs",
        json={"cv_id": str(cv.id), "job_search": _valid_job_search()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["cv_id"] == str(cv.id)
    assert body["job_search"]["role"] == "Software Engineer"
    assert "id" in body
    assert "created_at" in body
    assert len(fake_job_queue.published_messages) == 1
    assert fake_job_queue.published_messages[0] == {"analysis_run_id": body["id"]}


@pytest.mark.asyncio
async def test_post_runs_quota_exhausted_returns_429(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """POST /runs returns 429 when the rolling 24h quota is exhausted."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    for hours_ago in (2, 4, 6):
        _seed_run(
            db_session,
            user=user,
            cv=cv,
            status=AnalysisRunStatus.COMPLETE,
            created_at=now - timedelta(hours=hours_ago),
        )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.post(
        "/runs",
        json={"cv_id": str(cv.id), "job_search": _valid_job_search()},
    )

    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_runs_quota_returns_remaining_and_concurrent_blocked(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /runs/quota exposes remaining quota and concurrency state."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    now = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
    _seed_run(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.SCRAPING,
        created_at=now - timedelta(minutes=5),
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get("/runs/quota")

    assert response.status_code == 200
    body = response.json()
    assert body["remaining"] == 2
    assert body["concurrent_blocked"] is True


@pytest.mark.asyncio
async def test_get_runs_lists_owner_runs_newest_first(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /runs returns owner-scoped run summaries ordered newest first."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    older = _seed_run(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.COMPLETE,
        created_at=datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
    )
    newer = _seed_run(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.QUEUED,
        created_at=datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get("/runs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == str(newer.id)
    assert body[1]["id"] == str(older.id)


@pytest.mark.asyncio
async def test_get_run_by_id_returns_owner_run(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /runs/{id} returns run detail for the authenticated owner."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run(db_session, user=user, cv=cv, status=AnalysisRunStatus.QUEUED)
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(run.id)
    assert body["status"] == "queued"
    assert body["job_search"]["location"] == "London"


@pytest.mark.asyncio
async def test_get_foreign_run_returns_404(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /runs/{id} returns 404 for another user's run."""
    owner = create_test_user(db_session, email="owner@example.com")
    other = create_test_user(db_session, email="other@example.com")
    cv = _create_cv(db_session, owner)
    run = _seed_run(db_session, user=owner, cv=cv, status=AnalysisRunStatus.QUEUED)
    _authenticate_client(runs_client, db_session, other)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_get_run_results_only_when_complete(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /runs/{id}/results rejects non-complete runs and returns scored listings."""
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    queued_run = _seed_run(db_session, user=user, cv=cv, status=AnalysisRunStatus.QUEUED)
    complete_run = _seed_run(db_session, user=user, cv=cv, status=AnalysisRunStatus.COMPLETE)
    _seed_result(db_session, complete_run)
    _authenticate_client(runs_client, db_session, user)

    pending_response = await runs_client.get(f"/runs/{queued_run.id}/results")
    assert pending_response.status_code == 409

    complete_response = await runs_client.get(f"/runs/{complete_run.id}/results")
    assert complete_response.status_code == 200
    results = complete_response.json()
    assert len(results) == 1
    assert results[0]["title"] == "Backend Engineer"
    assert results[0]["match_score"] == 82
    assert results[0]["breakdown"]["matched_skills"] == ["Python"]


@pytest.mark.asyncio
async def test_get_run_results_returns_pipeline_scored_count(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """After the worker pipeline scores a run, GET results returns the scored listings."""
    from app.domain.scoring_schema import ScoringLlmOutput
    from app.services.scoring_service import ScoringService
    from tests.fakes.fake_job_source import FakeJobSource, make_listing
    from tests.fakes.fake_scoring_llm_client import FakeScoringLlmClient
    from worker.pipeline import AnalysisRunPipeline

    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run(db_session, user=user, cv=cv, status=AnalysisRunStatus.QUEUED)
    _authenticate_client(runs_client, db_session, user)

    output = ScoringLlmOutput(
        match_score=88,
        interview_likelihood=InterviewLikelihood.HIGH,
        matched_skills=["Python"],
        skill_gaps=[],
        red_flags=[],
        talking_points=["Highlight API work"],
    )
    pipeline = AnalysisRunPipeline(
        job_sources=[
            (
                "adzuna",
                FakeJobSource(
                    listings=[
                        make_listing(url="https://example.com/jobs/1"),
                        make_listing(url="https://example.com/jobs/2"),
                    ]
                ),
            )
        ],
        scoring_service=ScoringService(FakeScoringLlmClient(behaviours=[output])),
    )
    pipeline.run(run, db_session)

    response = await runs_client.get(f"/runs/{run.id}/results")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert results[0]["match_score"] == 88


@pytest.mark.asyncio
async def test_openapi_schema_includes_run_contracts(runs_test_app) -> None:
    """Generated OpenAPI schema documents run endpoints and quota response."""
    schema = runs_test_app.openapi()
    paths = schema["paths"]

    assert "/runs" in paths
    assert "post" in paths["/runs"]
    assert "get" in paths["/runs"]
    assert "/runs/quota" in paths
    assert "/runs/{run_id}" in paths
    assert "/runs/{run_id}/results" in paths

    quota_schema = schema["components"]["schemas"]["RunQuotaResponse"]
    assert "remaining" in quota_schema["properties"]
    assert "concurrent_blocked" in quota_schema["properties"]
