"""Behavior tests for owner-scoped database repositories."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AnalysisRun, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.db.repositories.cv_repository import CvRepository
from app.domain.analysis_run import AnalysisRunStatus


@pytest.fixture
def db_session() -> Session:
    """Provide a transactional in-memory SQLite session for repository tests."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _create_user(session: Session, email: str) -> UserAccount:
    user = UserAccount(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_analysis_run_repository_returns_run_only_for_owner(
    db_session: Session,
) -> None:
    """Cross-account run lookup returns None so the API can respond with 404."""
    from app.db.models import Cv

    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    repository = AnalysisRunRepository(db_session)
    now = datetime.now(UTC)

    cv = Cv(
        user_id=owner.id,
        name="Engineer CV",
        blob_key=f"cvs/{owner.id}/engineer.pdf",
        uploaded_at=now,
    )
    db_session.add(cv)
    db_session.commit()

    run = AnalysisRun(
        user_id=owner.id,
        cv_id=cv.id,
        status=AnalysisRunStatus.QUEUED,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=now,
    )
    db_session.add(run)
    db_session.commit()

    assert repository.get_by_id_for_user(run.id, owner.id) is not None
    assert repository.get_by_id_for_user(run.id, other.id) is None


def test_analysis_run_repository_lists_runs_for_owner_only(
    db_session: Session,
) -> None:
    """Run history queries never leak another User Account's Analysis Runs."""
    from app.db.models import Cv

    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    repository = AnalysisRunRepository(db_session)
    now = datetime.now(UTC)

    owner_cv = Cv(
        user_id=owner.id,
        name="Owner CV",
        blob_key=f"cvs/{owner.id}/owner.pdf",
        uploaded_at=now,
    )
    other_cv = Cv(
        user_id=other.id,
        name="Other CV",
        blob_key=f"cvs/{other.id}/other.pdf",
        uploaded_at=now,
    )
    db_session.add_all([owner_cv, other_cv])
    db_session.commit()

    owner_run = AnalysisRun(
        user_id=owner.id,
        cv_id=owner_cv.id,
        status=AnalysisRunStatus.COMPLETE,
        job_search_json={"role": "Engineer", "location": "Remote", "remote": True},
        finops_json={},
        created_at=now,
    )
    other_run = AnalysisRun(
        user_id=other.id,
        cv_id=other_cv.id,
        status=AnalysisRunStatus.QUEUED,
        job_search_json={"role": "Designer", "location": "Manchester", "remote": False},
        finops_json={},
        created_at=now,
    )
    db_session.add_all([owner_run, other_run])
    db_session.commit()

    owner_runs = repository.list_for_user(owner.id)
    assert len(owner_runs) == 1
    assert owner_runs[0].id == owner_run.id


def test_cv_repository_hides_deleted_cvs_from_owner_list(
    db_session: Session,
) -> None:
    """Soft-deleted CVs are excluded from the owner's active CV list."""
    from app.db.models import Cv

    owner = _create_user(db_session, "owner@example.com")
    repository = CvRepository(db_session)
    now = datetime.now(UTC)

    active_cv = Cv(
        user_id=owner.id,
        name="Active CV",
        blob_key=f"cvs/{owner.id}/active.pdf",
        uploaded_at=now,
    )
    deleted_cv = Cv(
        user_id=owner.id,
        name="Deleted CV",
        blob_key=f"cvs/{owner.id}/deleted.pdf",
        uploaded_at=now,
        deleted_at=now,
    )
    db_session.add_all([active_cv, deleted_cv])
    db_session.commit()

    cvs = repository.list_active_for_user(owner.id)
    assert len(cvs) == 1
    assert cvs[0].name == "Active CV"


def test_cv_repository_returns_none_for_wrong_owner(
    db_session: Session,
) -> None:
    """Owner-scoped CV fetch returns None for IDOR attempts."""
    from app.db.models import Cv

    owner = _create_user(db_session, "owner@example.com")
    other = _create_user(db_session, "other@example.com")
    repository = CvRepository(db_session)

    cv = Cv(
        user_id=owner.id,
        name="Private CV",
        blob_key=f"cvs/{owner.id}/private.pdf",
        uploaded_at=datetime.now(UTC),
    )
    db_session.add(cv)
    db_session.commit()

    assert repository.get_by_id_for_user(cv.id, owner.id) is not None
    assert repository.get_by_id_for_user(cv.id, other.id) is None
