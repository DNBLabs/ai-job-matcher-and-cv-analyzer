"""FastAPI dependency helpers for database access and authentication."""

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request, status
from sqlalchemy.orm import Session

from app.api.validation import NOT_FOUND_DETAIL, parse_uuid_path_param
from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService, is_valid_session_id
from app.config import Settings
from app.db.models import AnalysisRun, Cv, JobMatchResult, UserAccount
from app.db.repositories.analysis_run_repository import AnalysisRunRepository
from app.db.repositories.cv_repository import CvRepository
from app.db.repositories.job_match_result_repository import JobMatchResultRepository
from app.db.session import get_db_session


def get_settings_dependency(request: Request) -> Settings:
    """Return application settings stored on the FastAPI app instance.

    Args:
        request: Active HTTP request.

    Returns:
        Settings: Runtime configuration for the current application.
    """
    return request.app.state.settings


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
) -> UserAccount:
    """Resolve the authenticated User Account from the session cookie.

    Args:
        request: Active HTTP request carrying session cookies.
        db: Request-scoped database session.

    Returns:
        UserAccount: Authenticated Job Seeker or Admin account.

    Raises:
        HTTPException: When the session cookie is missing or invalid/expired.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id or not is_valid_session_id(session_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_service = SessionService(db)
    user = session_service.resolve_session(session_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(
    current_user: UserAccount = Depends(get_current_user),
) -> UserAccount:
    """Resolve an authenticated admin account or return a generic 404.

    Args:
        current_user: Authenticated User Account from the session cookie.

    Returns:
        UserAccount: Admin account permitted to access operator routes.

    Raises:
        HTTPException: When the authenticated user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return current_user


def get_owned_cv(
    cv_id: Annotated[str, Path()],
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Cv:
    """Return a CV owned by the authenticated user or respond with 404.

    Args:
        cv_id: CV identifier from the route path.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.

    Returns:
        Cv: Owner-scoped CV row.

    Raises:
        HTTPException: When the CV is missing, deleted, or owned by another account.
    """
    parsed_cv_id = parse_uuid_path_param(cv_id, field_name="cv_id")
    cv = CvRepository(db).get_by_id_for_user(parsed_cv_id, current_user.id)
    if cv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return cv


def get_owned_analysis_run(
    run_id: Annotated[str, Path()],
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> AnalysisRun:
    """Return an Analysis Run owned by the authenticated user or respond with 404.

    Args:
        run_id: Analysis Run identifier from the route path.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.

    Returns:
        AnalysisRun: Owner-scoped run row.

    Raises:
        HTTPException: When the run is missing or owned by another account.
    """
    parsed_run_id = parse_uuid_path_param(run_id, field_name="run_id")
    analysis_run = AnalysisRunRepository(db).get_by_id_for_user(parsed_run_id, current_user.id)
    if analysis_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return analysis_run


def get_owned_job_match_result(
    result_id: Annotated[str, Path()],
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> JobMatchResult:
    """Return a Job Match Result owned by the authenticated user or respond with 404.

    Args:
        result_id: Job Match Result identifier from the route path.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.

    Returns:
        JobMatchResult: Owner-scoped result row.

    Raises:
        HTTPException: When the result is missing or owned by another account.
    """
    parsed_result_id = parse_uuid_path_param(result_id, field_name="result_id")
    job_match_result = JobMatchResultRepository(db).get_by_id_for_user(parsed_result_id, current_user.id)
    if job_match_result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
    return job_match_result
