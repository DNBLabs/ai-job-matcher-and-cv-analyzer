"""Security boundary tests for Task 2 domain and persistence layers."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Cv, UserAccount
from app.db.repositories.audit_log_repository import AuditLogRepository
from app.db.repositories.cv_repository import CvRepository
from app.domain.divergence import InterviewLikelihood, get_divergence_badge
from app.domain.validation import normalize_email, validate_match_score


def test_normalize_email_rejects_injection_characters() -> None:
    """Email normalization rejects control characters and header-injection vectors."""
    with pytest.raises(ValueError, match="invalid characters"):
        normalize_email("user@example.com\nBcc: attacker@evil.com")


def test_normalize_email_rejects_overlong_addresses() -> None:
    """Email addresses are capped at 320 characters per RFC 5321 storage limits."""
    local = "a" * 310
    with pytest.raises(ValueError, match="maximum length"):
        normalize_email(f"{local}@example.com")


def test_validate_match_score_rejects_out_of_range_values() -> None:
    """Match Score must stay within the PRD 0–100 range at domain boundaries."""
    with pytest.raises(ValueError, match="between 0 and 100"):
        validate_match_score(101)
    with pytest.raises(ValueError, match="between 0 and 100"):
        validate_match_score(-1)


def test_divergence_badge_rejects_invalid_match_score() -> None:
    """Divergence helpers refuse scores outside the validated PRD range."""
    with pytest.raises(ValueError, match="between 0 and 100"):
        get_divergence_badge(match_score=150, interview_likelihood=InterviewLikelihood.LOW)


@pytest.fixture
def db_session() -> Session:
    """Provide an in-memory SQLite session for repository security tests."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_cv_repository_hides_soft_deleted_cv_on_owner_lookup(db_session: Session) -> None:
    """Deleted CVs return None on owner lookup so APIs can respond with 404."""
    user = UserAccount(email="owner@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    now = datetime.now(UTC)
    deleted_cv = Cv(
        user_id=user.id,
        name="Deleted CV",
        blob_key=f"cvs/{user.id}/deleted.pdf",
        uploaded_at=now,
        deleted_at=now,
    )
    db_session.add(deleted_cv)
    db_session.commit()

    repository = CvRepository(db_session)
    assert repository.get_by_id_for_user(deleted_cv.id, user.id) is None


def test_audit_log_repository_rejects_non_object_metadata(db_session: Session) -> None:
    """Audit metadata must be a JSON object to prevent log injection via odd types."""
    repository = AuditLogRepository(db_session)
    with pytest.raises(ValueError, match="JSON object"):
        repository.append_event(
            event_type="auth.login.success",
            metadata=["not", "an", "object"],
        )


def test_audit_log_repository_persists_append_only_events(db_session: Session) -> None:
    """Audit log writes are insert-only with structured metadata."""
    user = UserAccount(email="audit@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    repository = AuditLogRepository(db_session)
    entry = repository.append_event(
        event_type="admin.unlimited.toggled",
        actor_user_id=user.id,
        subject_user_id=user.id,
        metadata={"is_unlimited": True},
    )

    assert entry.id is not None
    assert entry.event_type == "admin.unlimited.toggled"
    assert json.loads(json.dumps(entry.metadata_json)) == {"is_unlimited": True}
