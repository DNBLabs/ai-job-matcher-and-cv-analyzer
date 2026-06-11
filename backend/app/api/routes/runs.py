"""Analysis Run HTTP routes for starting runs and reading status and results."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.factory import create_job_queue
from app.api.deps import get_current_user, get_owned_analysis_run, get_settings_dependency
from app.config import Settings
from app.db.models import AnalysisRun, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.db.repositories.job_match_result_repository import JobMatchResultRepository
from app.db.session import get_db_session
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.divergence import InterviewLikelihood
from app.domain.job_search import JobSearch
from app.domain.run_outcomes import failure_message_for
from app.ports.job_queue import JobQueue
from app.services.analysis_orchestrator import (
    AnalysisOrchestrator,
    ConcurrentRunBlockedError,
    CvNotAvailableError,
    JobSearchValidationError,
    RunQuotaExceededError,
)

router = APIRouter(prefix="/runs", tags=["runs"])


class JobSearchFiltersResponse(BaseModel):
    """Optional Job Search filters returned with Analysis Run metadata."""

    experience_level: str | None = None
    employment_type: str | None = None


class JobSearchResponse(BaseModel):
    """Job Search criteria persisted on an Analysis Run."""

    role: str
    location: str
    remote: bool
    filters: JobSearchFiltersResponse | None = None


class RunResponse(BaseModel):
    """Public Analysis Run metadata returned by list and detail endpoints."""

    id: UUID
    cv_id: UUID
    status: AnalysisRunStatus
    job_search: JobSearchResponse
    source_failures: dict[str, Any] | None = None
    failure_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RunQuotaResponse(BaseModel):
    """Remaining daily quota and concurrency state for the authenticated user."""

    remaining: int | None
    concurrent_blocked: bool


class CreateRunRequest(BaseModel):
    """Payload for starting a new Analysis Run."""

    cv_id: UUID
    job_search: dict[str, Any]


class JobMatchBreakdownResponse(BaseModel):
    """AI breakdown fields stored on each Job Match Result."""

    match_score: int
    interview_likelihood: InterviewLikelihood
    matched_skills: list[str]
    skill_gaps: list[str]
    red_flags: list[str]
    talking_points: list[str]


class JobMatchResultResponse(BaseModel):
    """Scored listing returned by GET /runs/{id}/results."""

    id: UUID
    source: str
    external_id: str
    title: str
    company: str
    url: str
    match_score: int
    interview_likelihood: InterviewLikelihood
    breakdown: JobMatchBreakdownResponse
    created_at: datetime


def get_job_queue(settings: Settings = Depends(get_settings_dependency)) -> JobQueue:
    """Return the configured JobQueue adapter for Analysis Run enqueue.

    Args:
        settings: Runtime application settings.

    Returns:
        JobQueue: In-process or RabbitMQ-backed implementation.
    """
    return create_job_queue(settings)


def _job_search_to_response(job_search_json: dict[str, Any]) -> JobSearchResponse:
    """Map persisted Job Search JSON to the public API response shape.

    Args:
        job_search_json: Stored ``analysis_run.job_search_json`` payload.

    Returns:
        JobSearchResponse: Validated Job Search fields for API consumers.
    """
    job_search = JobSearch.model_validate(job_search_json)
    filters = None
    if job_search.filters is not None:
        filters = JobSearchFiltersResponse(
            experience_level=job_search.filters.experience_level,
            employment_type=job_search.filters.employment_type,
        )
    return JobSearchResponse(
        role=job_search.role,
        location=job_search.location,
        remote=job_search.remote,
        filters=filters,
    )


def _run_to_response(analysis_run: AnalysisRun) -> RunResponse:
    """Map an Analysis Run ORM row to the public API response shape.

    Args:
        analysis_run: Persisted Analysis Run row.

    Returns:
        RunResponse: API-safe run metadata without internal fields.
    """
    return RunResponse(
        id=analysis_run.id,
        cv_id=analysis_run.cv_id,
        status=analysis_run.status,
        job_search=_job_search_to_response(analysis_run.job_search_json),
        source_failures=analysis_run.source_failures_json,
        failure_message=failure_message_for(
            analysis_run.status, analysis_run.source_failures_json
        ),
        created_at=analysis_run.created_at,
        completed_at=analysis_run.completed_at,
    )


def _result_to_response(result) -> JobMatchResultResponse:
    """Map a Job Match Result ORM row to the public API response shape.

    Args:
        result: Persisted scored listing row.

    Returns:
        JobMatchResultResponse: API-safe result with breakdown JSON.
    """
    breakdown = JobMatchBreakdownResponse.model_validate(result.breakdown_json)
    return JobMatchResultResponse(
        id=result.id,
        source=result.source,
        external_id=result.external_id,
        title=result.title,
        company=result.company,
        url=result.url,
        match_score=result.match_score,
        interview_likelihood=result.interview_likelihood,
        breakdown=breakdown,
        created_at=result.created_at,
    )


@router.get("/quota", response_model=RunQuotaResponse)
async def get_run_quota(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    job_queue: JobQueue = Depends(get_job_queue),
) -> RunQuotaResponse:
    """Return remaining daily quota and whether a concurrent run blocks a new start.

    Args:
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        job_queue: JobQueue port for orchestrator construction.

    Returns:
        RunQuotaResponse: Remaining runs and concurrency metadata.
    """
    quota = AnalysisOrchestrator(db, job_queue).get_run_quota(current_user)
    return RunQuotaResponse(
        remaining=quota.remaining_runs,
        concurrent_blocked=quota.concurrent_blocked,
    )


@router.get("", response_model=list[RunResponse])
async def list_runs(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[RunResponse]:
    """List Analysis Runs for the authenticated user, newest first.

    Args:
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.

    Returns:
        list[RunResponse]: Owner-scoped run summaries.
    """
    runs = AnalysisRunRepository(db).list_for_user(current_user.id)
    return [_run_to_response(run) for run in runs]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RunResponse)
async def create_run(
    payload: CreateRunRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    job_queue: JobQueue = Depends(get_job_queue),
) -> RunResponse:
    """Start a new Analysis Run for an owned CV and Job Search criteria.

    Args:
        payload: CV id and Job Search criteria.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        job_queue: JobQueue port for worker enqueue.

    Returns:
        RunResponse: Newly created queued run metadata.

    Raises:
        HTTPException: When validation, quota, or concurrency rules fail.
    """
    orchestrator = AnalysisOrchestrator(db, job_queue)
    try:
        run = orchestrator.start_analysis_run(
            current_user,
            payload.cv_id,
            payload.job_search,
        )
    except CvNotAvailableError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from error
    except JobSearchValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ConcurrentRunBlockedError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error
    except RunQuotaExceededError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from error

    return _run_to_response(run)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    analysis_run: AnalysisRun = Depends(get_owned_analysis_run),
) -> RunResponse:
    """Return Analysis Run detail for the authenticated owner.

    Args:
        analysis_run: Owner-scoped run row resolved from the route path.

    Returns:
        RunResponse: Run metadata including Job Search and lifecycle status.
    """
    return _run_to_response(analysis_run)


@router.get("/{run_id}/results", response_model=list[JobMatchResultResponse])
async def get_run_results(
    analysis_run: AnalysisRun = Depends(get_owned_analysis_run),
    db: Session = Depends(get_db_session),
) -> list[JobMatchResultResponse]:
    """Return scored listings for a completed Analysis Run.

    Args:
        analysis_run: Owner-scoped run row resolved from the route path.
        db: Request-scoped database session.

    Returns:
        list[JobMatchResultResponse]: Ranked Job Match Results with breakdown JSON.

    Raises:
        HTTPException: When the run has not reached ``complete`` status.
    """
    if analysis_run.status is not AnalysisRunStatus.COMPLETE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Results are not available until the Analysis Run completes",
        )

    results = JobMatchResultRepository(db).list_for_run(analysis_run.id)
    return [_result_to_response(result) for result in results]
