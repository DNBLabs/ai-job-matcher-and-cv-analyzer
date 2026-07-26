"""Behavior tests for owner-scoped database repositories."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AnalysisRun, Cv, JobMatchResult, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.db.repositories.cv_repository import CvRepository
from app.db.repositories.job_match_result_repository import (
    _INTERVIEW_LIKELIHOOD_RANK,
    _UNKNOWN_INTERVIEW_LIKELIHOOD_RANK,
    JobMatchResultRepository,
)
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood


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


def _create_run(session: Session, user: UserAccount) -> AnalysisRun:
    """Persist a completed Analysis Run (with its CV) for result-ordering tests."""
    now = datetime.now(UTC)
    cv = Cv(
        user_id=user.id,
        name="Engineer CV",
        blob_key=f"cvs/{user.id}/engineer.pdf",
        uploaded_at=now,
    )
    session.add(cv)
    session.commit()

    run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=AnalysisRunStatus.COMPLETE,
        job_search_json={"role": "Engineer", "location": "London", "remote": False},
        finops_json={},
        created_at=now,
    )
    session.add(run)
    session.commit()
    return run


def _add_result(
    session: Session,
    run: AnalysisRun,
    *,
    match_score: int,
    interview_likelihood: InterviewLikelihood,
    result_id: uuid.UUID | None = None,
    external_id: str | None = None,
) -> JobMatchResult:
    """Persist one Job Match Result under a run with controllable id and score."""
    result = JobMatchResult(
        id=result_id or uuid.uuid4(),
        analysis_run_id=run.id,
        source="adzuna",
        external_id=external_id or str(uuid.uuid4()),
        title="Backend Engineer",
        company="Acme Ltd",
        url="https://example.com/jobs/1",
        match_score=match_score,
        interview_likelihood=interview_likelihood,
        breakdown_json={},
    )
    session.add(result)
    session.commit()
    return result


def test_list_for_run_orders_by_match_score_descending(db_session: Session) -> None:
    """AC1: highest Match Score comes first."""
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)
    _add_result(db_session, run, match_score=40, interview_likelihood=InterviewLikelihood.HIGH)
    _add_result(db_session, run, match_score=90, interview_likelihood=InterviewLikelihood.HIGH)
    _add_result(db_session, run, match_score=65, interview_likelihood=InterviewLikelihood.HIGH)

    results = JobMatchResultRepository(db_session).list_for_run(run.id)

    assert [result.match_score for result in results] == [90, 65, 40]


def test_list_for_run_ranks_high_above_medium_on_equal_score(db_session: Session) -> None:
    """AC2: on an equal Match Score, HIGH Interview Likelihood ranks above MEDIUM."""
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)
    # Insert MEDIUM first so an order-by-score-only query would return it first.
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.MEDIUM)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.HIGH)

    results = JobMatchResultRepository(db_session).list_for_run(run.id)

    assert [result.interview_likelihood for result in results] == [
        InterviewLikelihood.HIGH,
        InterviewLikelihood.MEDIUM,
    ]


def test_list_for_run_ranks_medium_above_low_on_equal_score(db_session: Session) -> None:
    """AC3: on an equal Match Score, MEDIUM ranks above LOW.

    Alphabetically ``low`` < ``medium``, so a naive column sort would place LOW
    first — this test fails unless the explicit rank CASE is used.
    """
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)
    # Insert LOW first so both score-only and alphabetical sorts would lead with LOW.
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.LOW)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.MEDIUM)

    results = JobMatchResultRepository(db_session).list_for_run(run.id)

    assert [result.interview_likelihood for result in results] == [
        InterviewLikelihood.MEDIUM,
        InterviewLikelihood.LOW,
    ]


def test_list_for_run_breaks_full_ties_by_id_ascending(db_session: Session) -> None:
    """AC4: identical Match Score and Interview Likelihood tie-break on id ascending."""
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)
    lower_id = uuid.UUID(int=1)
    higher_id = uuid.UUID(int=2)
    # Insert the higher id first so insertion order is the reverse of id-ascending.
    _add_result(
        db_session,
        run,
        match_score=70,
        interview_likelihood=InterviewLikelihood.HIGH,
        result_id=higher_id,
    )
    _add_result(
        db_session,
        run,
        match_score=70,
        interview_likelihood=InterviewLikelihood.HIGH,
        result_id=lower_id,
    )

    results = JobMatchResultRepository(db_session).list_for_run(run.id)

    assert [result.id for result in results] == [lower_id, higher_id]


def test_list_for_run_is_a_stable_total_order_across_calls(db_session: Session) -> None:
    """AC5: repeated calls return the same fully-ordered id sequence.

    Mixes equal scores and likelihoods so the result is only deterministic when
    every sort key (score → likelihood rank → id) is applied in SQL.
    """
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)
    tie_a = uuid.UUID(int=10)
    tie_b = uuid.UUID(int=20)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.HIGH, result_id=tie_b)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.HIGH, result_id=tie_a)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.LOW)
    _add_result(db_session, run, match_score=70, interview_likelihood=InterviewLikelihood.MEDIUM)
    _add_result(db_session, run, match_score=95, interview_likelihood=InterviewLikelihood.LOW)

    repository = JobMatchResultRepository(db_session)
    first_call = [result.id for result in repository.list_for_run(run.id)]
    second_call = [result.id for result in repository.list_for_run(run.id)]

    assert first_call == second_call
    # 95 leads; then the 70s by likelihood; the HIGH pair tie-breaks on id ascending.
    assert first_call[0] != tie_a  # the score-95 row leads, not a 70
    assert first_call[1:3] == [tie_a, tie_b]


def test_list_for_run_returns_empty_list_when_no_results(db_session: Session) -> None:
    """AC6: a run with no scored listings yields an empty list."""
    owner = _create_user(db_session, "owner@example.com")
    run = _create_run(db_session, owner)

    results = JobMatchResultRepository(db_session).list_for_run(run.id)

    assert results == []


def test_interview_likelihood_rank_covers_every_enum_member() -> None:
    """Decision 1: every InterviewLikelihood member has a rank (completeness guard).

    If a member is added to the enum but not the rank map, this fails — surfacing
    the omission instead of letting the unmatched value silently sort last.
    """
    for member in InterviewLikelihood:
        assert member in _INTERVIEW_LIKELIHOOD_RANK


def test_unknown_interview_likelihood_rank_sorts_after_every_known_rank() -> None:
    """Decision 2: the sentinel rank is strictly greater than every real rank."""
    assert _UNKNOWN_INTERVIEW_LIKELIHOOD_RANK > max(_INTERVIEW_LIKELIHOOD_RANK.values())
