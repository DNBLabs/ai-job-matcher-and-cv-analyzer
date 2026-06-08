"""Integration tests for owner-scoped resource access and admin routing."""

from datetime import UTC, datetime

import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.api.deps import (
    get_owned_analysis_run,
    get_owned_cv,
    get_owned_job_match_result,
    require_admin,
)
from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService
from app.db.models import AnalysisRun, Cv, JobMatchResult, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood
from tests.auth.conftest import create_test_user


@pytest.fixture
def idor_test_app(test_app):
    """Extend the auth test app with owner-scoped and admin probe routes."""

    @test_app.get("/test/cvs/{cv_id}")
    async def get_cv_route(cv: Cv = Depends(get_owned_cv)) -> dict[str, str]:
        """Return a CV only when it belongs to the authenticated user."""
        return {"cv_id": str(cv.id)}

    @test_app.get("/test/runs/{run_id}")
    async def get_run_route(run: AnalysisRun = Depends(get_owned_analysis_run)) -> dict[str, str]:
        """Return an Analysis Run only when it belongs to the authenticated user."""
        return {"run_id": str(run.id)}

    @test_app.get("/test/results/{result_id}")
    async def get_result_route(
        result: JobMatchResult = Depends(get_owned_job_match_result),
    ) -> dict[str, str]:
        """Return a Job Match Result only when its parent run belongs to the user."""
        return {"result_id": str(result.id)}

    @test_app.get("/test/admin/probe")
    async def admin_probe_route(admin_user: UserAccount = Depends(require_admin)) -> dict[str, str]:
        """Return admin identity only for operator accounts."""
        return {"admin_id": str(admin_user.id)}

    return test_app


@pytest.fixture
async def idor_client(idor_test_app) -> AsyncClient:
    """Async HTTP client bound to the IDOR routing test application."""
    from httpx import ASGITransport

    transport = ASGITransport(app=idor_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def _authenticate_client(
    client: AsyncClient,
    db_session: Session,
    user: UserAccount,
) -> None:
    """Attach a valid session cookie for the given user to the test client."""
    session_record = SessionService(db_session).create_session(user.id)
    client.cookies.set(SESSION_COOKIE_NAME, session_record.id)


def _seed_cv_and_run(db_session: Session, owner: UserAccount) -> tuple[Cv, AnalysisRun]:
    """Create an owner-scoped CV and Analysis Run for IDOR routing tests."""
    now = datetime.now(UTC)
    cv = Cv(
        user_id=owner.id,
        name="Owner CV",
        blob_key=f"cvs/{owner.id}/owner.pdf",
        uploaded_at=now,
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)

    analysis_run = AnalysisRun(
        user_id=owner.id,
        cv_id=cv.id,
        status=AnalysisRunStatus.QUEUED,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=now,
    )
    db_session.add(analysis_run)
    db_session.commit()
    db_session.refresh(analysis_run)
    return cv, analysis_run


def _seed_result(db_session: Session, analysis_run: AnalysisRun) -> JobMatchResult:
    """Create a Job Match Result linked to the given Analysis Run."""
    result = JobMatchResult(
        analysis_run_id=analysis_run.id,
        source="indeed",
        external_id="job-123",
        title="Backend Engineer",
        company="Example Ltd",
        url="https://example.com/jobs/123",
        match_score=80,
        interview_likelihood=InterviewLikelihood.HIGH,
        breakdown_json={"skills": []},
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)
    return result


@pytest.mark.asyncio
async def test_foreign_cv_id_returns_404_for_authenticated_user(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Cross-account CV access returns 404 instead of revealing ownership."""
    owner = create_test_user(db_session, email="owner@example.com")
    other = create_test_user(db_session, email="other@example.com")
    cv, _ = _seed_cv_and_run(db_session, owner)

    _authenticate_client(idor_client, db_session, other)
    response = await idor_client.get(f"/test/cvs/{cv.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_foreign_run_id_returns_404_for_authenticated_user(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Cross-account Analysis Run access returns 404 instead of revealing ownership."""
    owner = create_test_user(db_session, email="owner@example.com")
    other = create_test_user(db_session, email="other@example.com")
    _, analysis_run = _seed_cv_and_run(db_session, owner)

    _authenticate_client(idor_client, db_session, other)
    response = await idor_client.get(f"/test/runs/{analysis_run.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_foreign_result_id_returns_404_for_authenticated_user(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Cross-account Job Match Result access returns 404 instead of revealing ownership."""
    owner = create_test_user(db_session, email="owner@example.com")
    other = create_test_user(db_session, email="other@example.com")
    _, analysis_run = _seed_cv_and_run(db_session, owner)
    result = _seed_result(db_session, analysis_run)

    _authenticate_client(idor_client, db_session, other)
    response = await idor_client.get(f"/test/results/{result.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_owner_can_access_owned_cv_run_and_result(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Authenticated owners can access their own CV, run, and result identifiers."""
    owner = create_test_user(db_session, email="owner@example.com")
    cv, analysis_run = _seed_cv_and_run(db_session, owner)
    result = _seed_result(db_session, analysis_run)
    _authenticate_client(idor_client, db_session, owner)

    cv_response = await idor_client.get(f"/test/cvs/{cv.id}")
    run_response = await idor_client.get(f"/test/runs/{analysis_run.id}")
    result_response = await idor_client.get(f"/test/results/{result.id}")

    assert cv_response.status_code == 200
    assert run_response.status_code == 200
    assert result_response.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_receives_404_on_admin_probe_route(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Admin routes return 404 for non-admin users to avoid role enumeration."""
    seeker = create_test_user(db_session, email="seeker@example.com")
    _authenticate_client(idor_client, db_session, seeker)

    response = await idor_client.get("/test/admin/probe")

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_admin_can_access_admin_probe_route(
    idor_client: AsyncClient,
    db_session: Session,
) -> None:
    """Operator accounts can access admin-only routes."""
    admin = create_test_user(db_session, email="admin@example.com")
    admin.is_admin = True
    db_session.commit()
    _authenticate_client(idor_client, db_session, admin)

    response = await idor_client.get("/test/admin/probe")

    assert response.status_code == 200
    assert response.json()["admin_id"] == str(admin.id)
