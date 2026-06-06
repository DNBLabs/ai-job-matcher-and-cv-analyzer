"""Database engine and session factory helpers."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def get_engine():
    """Create a SQLAlchemy engine from application settings.

    Returns:
        Engine: Bound database engine.
    """
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory() -> sessionmaker[Session]:
    """Return a configured session factory for the application database.

    Returns:
        sessionmaker[Session]: Factory producing new ORM sessions.
    """
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


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
