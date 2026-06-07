"""Shared fixtures for auth integration tests."""

from collections.abc import Generator

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.config import Settings
from app.db.base import Base
from app.db.models import UserAccount
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def auth_settings() -> Settings:
    """Return settings tuned for in-process auth tests."""
    return Settings(app_env="development", allowed_origins="http://localhost:5173")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a transactional in-memory SQLite session for auth tests."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_app(auth_settings: Settings, db_session: Session):
    """Build a FastAPI app with database dependency override and a protected route."""
    application = create_app(settings=auth_settings)

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session

    @application.get("/test/protected")
    async def protected_route(current_user: UserAccount = Depends(get_current_user)) -> dict[str, str]:
        """Return the authenticated User Account id for session verification tests."""
        return {"user_id": str(current_user.id)}

    return application


@pytest.fixture
async def client(test_app) -> AsyncClient:
    """Async HTTP client bound to the test application."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def create_test_user(db_session: Session, email: str = "seeker@example.com") -> UserAccount:
    """Insert a User Account row for session tests.

    Args:
        db_session: Active SQLAlchemy session.
        email: Email address for the new account.

    Returns:
        UserAccount: Persisted user row.
    """
    user = UserAccount(email=email)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
