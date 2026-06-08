"""Integration tests for GET /cvs, DELETE /cvs/{id}, and delete/run retention."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.api.deps import get_owned_analysis_run, get_owned_cv
from app.ports.blob_store import BlobNotFoundError
from app.db.models import AnalysisRun, Cv, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.domain.analysis_run import AnalysisRunStatus
from tests.auth.conftest import create_test_user
from tests.cvs.pdf_fixtures import VALID_PDF_BYTES
from tests.cvs.test_cv_upload import _authenticate_client


@pytest.fixture
def cv_routes_test_app(cv_test_app):
    """Extend the CV test app with run probe routes for delete retention checks."""

    @cv_test_app.get("/test/runs/{run_id}")
    async def get_run_route(run: AnalysisRun = Depends(get_owned_analysis_run)) -> dict[str, str]:
        """Return an Analysis Run only when it belongs to the authenticated user."""
        return {"run_id": str(run.id)}

    @cv_test_app.post("/test/runs/{cv_id}")
    async def create_run_probe(cv: Cv = Depends(get_owned_cv)) -> dict[str, str]:
        """Simulate run creation requiring an active owned CV."""
        return {"cv_id": str(cv.id)}

    return cv_test_app


@pytest.fixture
async def cv_routes_client(cv_routes_test_app) -> AsyncClient:
    """Async HTTP client bound to the CV list/delete test application."""
    from httpx import ASGITransport

    transport = ASGITransport(app=cv_routes_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def _upload_cv(
    client: AsyncClient,
    db_session: Session,
    user: UserAccount,
    *,
    name: str = "Engineer CV",
) -> Cv:
    """Upload a CV via POST /cvs and return the persisted ORM row."""
    _authenticate_client(client, db_session, user)
    response = await client.post(
        "/cvs",
        data={"name": name},
        files={"file": ("resume.pdf", VALID_PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 201
    cv_id = uuid.UUID(response.json()["id"])
    cv_row = db_session.scalar(select(Cv).where(Cv.id == cv_id))
    assert cv_row is not None
    return cv_row


def _seed_run(db_session: Session, user: UserAccount, cv: Cv) -> AnalysisRun:
    """Create a historical Analysis Run linked to the given CV."""
    analysis_run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=AnalysisRunStatus.COMPLETE,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=datetime.now(UTC),
    )
    db_session.add(analysis_run)
    db_session.commit()
    db_session.refresh(analysis_run)
    return analysis_run


@pytest.mark.asyncio
async def test_list_cvs_returns_non_deleted_uploads(
    cv_routes_client: AsyncClient,
    db_session: Session,
) -> None:
    """GET /cvs returns active CV metadata ordered by upload date."""
    user = create_test_user(db_session)
    cv_row = await _upload_cv(cv_routes_client, db_session, user)

    response = await cv_routes_client.get("/cvs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(cv_row.id)
    assert body[0]["name"] == "Engineer CV"
    assert "uploaded_at" in body[0]


@pytest.mark.asyncio
async def test_delete_cv_removes_blob_and_parsed_text(
    cv_routes_client: AsyncClient,
    db_session: Session,
    memory_blob_store: MemoryBlobStore,
) -> None:
    """DELETE /cvs/{id} soft-deletes the CV and removes blob plus parsed text."""
    user = create_test_user(db_session, email="delete@example.com")
    cv_row = await _upload_cv(cv_routes_client, db_session, user)
    cv_row.parsed_text = "parsed cv text"
    db_session.commit()

    response = await cv_routes_client.delete(f"/cvs/{cv_row.id}")

    assert response.status_code == 204
    db_session.refresh(cv_row)
    assert cv_row.deleted_at is not None
    assert cv_row.parsed_text is None

    logical_key = f"{user.id}/{cv_row.id}.pdf"
    with pytest.raises(BlobNotFoundError):
        memory_blob_store.get(logical_key)


@pytest.mark.asyncio
async def test_delete_cv_is_idempotent(
    cv_routes_client: AsyncClient,
    db_session: Session,
) -> None:
    """Repeating DELETE on the same CV succeeds without error."""
    user = create_test_user(db_session, email="idempotent@example.com")
    cv_row = await _upload_cv(cv_routes_client, db_session, user)

    first = await cv_routes_client.delete(f"/cvs/{cv_row.id}")
    second = await cv_routes_client.delete(f"/cvs/{cv_row.id}")

    assert first.status_code == 204
    assert second.status_code == 204


@pytest.mark.asyncio
async def test_delete_cv_retains_historical_run(
    cv_routes_client: AsyncClient,
    db_session: Session,
) -> None:
    """Soft-deleting a CV keeps past Analysis Runs accessible to the owner."""
    user = create_test_user(db_session, email="history@example.com")
    cv_row = await _upload_cv(cv_routes_client, db_session, user)
    analysis_run = _seed_run(db_session, user, cv_row)

    delete_response = await cv_routes_client.delete(f"/cvs/{cv_row.id}")
    run_response = await cv_routes_client.get(f"/test/runs/{analysis_run.id}")
    listed_runs = AnalysisRunRepository(db_session).list_for_user(user.id)

    assert delete_response.status_code == 204
    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == str(analysis_run.id)
    assert len(listed_runs) == 1
    assert listed_runs[0].id == analysis_run.id


@pytest.mark.asyncio
async def test_create_run_with_deleted_cv_returns_404(
    cv_routes_client: AsyncClient,
    db_session: Session,
) -> None:
    """New runs cannot reference a soft-deleted CV."""
    user = create_test_user(db_session, email="deleted-run@example.com")
    cv_row = await _upload_cv(cv_routes_client, db_session, user)
    delete_response = await cv_routes_client.delete(f"/cvs/{cv_row.id}")

    run_response = await cv_routes_client.post(f"/test/runs/{cv_row.id}")

    assert delete_response.status_code == 204
    assert run_response.status_code == 404
    assert run_response.json()["detail"] == "Not found"


@pytest.mark.asyncio
async def test_list_cvs_excludes_deleted_cv(
    cv_routes_client: AsyncClient,
    db_session: Session,
) -> None:
    """Deleted CVs no longer appear in GET /cvs results."""
    user = create_test_user(db_session, email="list@example.com")
    cv_row = await _upload_cv(cv_routes_client, db_session, user)

    await cv_routes_client.delete(f"/cvs/{cv_row.id}")
    response = await cv_routes_client.get("/cvs")

    assert response.status_code == 200
    assert response.json() == []
