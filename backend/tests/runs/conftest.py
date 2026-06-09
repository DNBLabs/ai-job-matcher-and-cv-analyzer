"""Shared fixtures for Analysis Run API integration tests."""

from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.api.routes.runs import get_job_queue
from app.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from tests.auth.conftest import _bind_test_session_factory, auth_settings, db_session
from tests.fakes.fake_job_queue import FakeJobQueue

__all__ = ["auth_settings", "db_session", "fake_job_queue", "runs_client", "runs_test_app"]


@pytest.fixture
def fake_job_queue() -> FakeJobQueue:
    """Return an in-memory JobQueue that records published messages."""
    return FakeJobQueue()


@pytest.fixture
def runs_test_app(auth_settings: Settings, db_session: Session, fake_job_queue: FakeJobQueue):
    """Build a FastAPI app with run routes and a fake JobQueue override."""
    application = create_app(settings=auth_settings)
    _bind_test_session_factory(application, db_session)

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session
    application.dependency_overrides[get_job_queue] = lambda: fake_job_queue
    return application


@pytest.fixture
async def runs_client(runs_test_app) -> AsyncClient:
    """Async HTTP client bound to the run routes test application."""
    transport = ASGITransport(app=runs_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
