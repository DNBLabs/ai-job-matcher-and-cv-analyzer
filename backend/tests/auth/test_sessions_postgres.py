"""Postgres integration smoke tests for session persistence (CI after Alembic)."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.auth.session import SessionService
from app.db.models import SessionRecord, UserAccount


@pytest.fixture
def postgres_db_session() -> Session:
    """Yield a Postgres session when DATABASE_URL targets PostgreSQL.

    Skips locally when only SQLite is configured. CI sets DATABASE_URL to the
    ephemeral Postgres 16 service container.
    Source: https://docs.github.com/en/actions/using-containerized-services/creating-postgresql-service-containers
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("Requires PostgreSQL DATABASE_URL")

    engine = create_engine(database_url, pool_pre_ping=True)
    if "sessions" not in inspect(engine).get_table_names():
        engine.dispose()
        pytest.skip("sessions table missing; run alembic upgrade head first")

    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_session_service_persists_row_in_postgres_sessions_table(
    postgres_db_session: Session,
) -> None:
    """SessionService stores rows in the migrated Postgres sessions table in CI."""
    unique_email = f"postgres-session-{uuid.uuid4()}@example.com"
    user = UserAccount(email=unique_email)
    postgres_db_session.add(user)
    postgres_db_session.commit()
    postgres_db_session.refresh(user)

    service = SessionService(postgres_db_session)
    session_record = service.create_session(user.id)

    try:
        stored = postgres_db_session.get(SessionRecord, session_record.id)
        assert stored is not None
        assert stored.user_id == user.id
        assert stored.idle_expires_at is not None
        assert stored.absolute_expires_at is not None
    finally:
        postgres_db_session.delete(session_record)
        postgres_db_session.delete(user)
        postgres_db_session.commit()
