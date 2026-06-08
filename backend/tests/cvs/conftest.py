"""Shared fixtures for CV upload integration tests."""

from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.adapters.local.memory_blob_store import MemoryBlobStore
from app.api.routes.cvs import get_blob_store
from tests.auth.conftest import _bind_test_session_factory, auth_settings, create_test_user, db_session
from app.config import Settings
from app.db.session import get_db_session
from app.main import create_app

__all__ = [
    "auth_settings",
    "create_test_user",
    "cv_client",
    "cv_test_app",
    "db_session",
    "memory_blob_store",
]


@pytest.fixture
def memory_blob_store() -> MemoryBlobStore:
    """Return an in-memory BlobStore scoped under the cvs/ prefix."""
    return MemoryBlobStore(key_prefix="cvs/")


@pytest.fixture
def cv_test_app(auth_settings: Settings, db_session: Session, memory_blob_store: MemoryBlobStore):
    """Build a FastAPI app with CV routes and an in-memory blob store override."""
    application = create_app(settings=auth_settings)
    _bind_test_session_factory(application, db_session)

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session
    application.dependency_overrides[get_blob_store] = lambda: memory_blob_store
    return application


@pytest.fixture
async def cv_client(cv_test_app) -> AsyncClient:
    """Async HTTP client bound to the CV upload test application."""
    transport = ASGITransport(app=cv_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
