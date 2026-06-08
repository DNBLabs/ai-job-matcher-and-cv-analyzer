"""Shared pytest fixtures for backend API integration tests."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.main import create_app

_SQLITE_DATABASE_URL = "sqlite+pysqlite:///:memory:"


def create_api_test_app(settings: Settings | None = None):
    """Build a FastAPI app with middleware-safe in-memory SQLite database access.

    Args:
        settings: Optional settings override for the application under test.

    Returns:
        FastAPI: Configured application with an in-memory session factory.
    """
    runtime_settings = settings or Settings(
        app_env="development",
        allowed_origins="http://localhost:5173",
        post_auth_redirect_url="http://localhost:5173/dashboard",
    )
    runtime_settings = runtime_settings.model_copy(update={"database_url": _SQLITE_DATABASE_URL})

    engine = create_engine(
        runtime_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    application = create_app(settings=runtime_settings)
    application.state.session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    return application


@pytest.fixture
def api_test_settings() -> Settings:
    """Return settings that keep middleware database access on in-memory SQLite."""
    return Settings(
        app_env="development",
        allowed_origins="http://localhost:5173",
        database_url=_SQLITE_DATABASE_URL,
        post_auth_redirect_url="http://localhost:5173/dashboard",
    )


@pytest.fixture
def api_test_app(api_test_settings: Settings):
    """Build a FastAPI app with middleware-safe in-memory database access."""
    return create_api_test_app(api_test_settings)


@pytest.fixture
def api_test_db_session(api_test_app) -> Generator[Session, None, None]:
    """Yield the shared in-memory session backing API integration tests."""
    session = api_test_app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
