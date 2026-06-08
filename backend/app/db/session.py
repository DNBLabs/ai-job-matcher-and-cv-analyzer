"""Database engine and session factory helpers."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def get_engine(settings: Settings | None = None):
    """Create a SQLAlchemy engine from application settings.

    Args:
        settings: Optional settings override; defaults to environment configuration.

    Returns:
        Engine: Bound database engine.
    """
    runtime_settings = settings or get_settings()
    return create_engine(runtime_settings.database_url, pool_pre_ping=True)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return a configured session factory for the application database.

    Args:
        settings: Optional settings override; defaults to environment configuration.

    Returns:
        sessionmaker[Session]: Factory producing new ORM sessions.
    """
    return sessionmaker(bind=get_engine(settings), autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a request-scoped database session for FastAPI dependencies.

    Yields:
        Session: Active SQLAlchemy session closed after use.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
