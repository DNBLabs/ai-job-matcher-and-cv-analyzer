"""Shared fixtures for admin operator API integration tests."""

from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from tests.auth.conftest import _bind_test_session_factory, auth_settings, db_session

__all__ = ["admin_client", "admin_test_app", "auth_settings", "db_session"]


@pytest.fixture
def admin_test_app(auth_settings: Settings, db_session: Session):
    """Build a FastAPI app with admin routes and an in-memory session override."""
    application = create_app(settings=auth_settings)
    _bind_test_session_factory(application, db_session)

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session
    return application


@pytest.fixture
async def admin_client(admin_test_app) -> AsyncClient:
    """Async HTTP client bound to the admin routes test application."""
    transport = ASGITransport(app=admin_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
