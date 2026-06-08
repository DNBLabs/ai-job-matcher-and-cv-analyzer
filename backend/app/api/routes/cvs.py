"""CV HTTP routes for upload, listing, and deletion."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.factory import create_blob_store, create_llm_client, create_secret_provider
from app.api.deps import get_current_user, get_owned_cv, get_settings_dependency
from app.api.validation import NOT_FOUND_DETAIL
from app.config import Settings
from app.db.models import Cv, UserAccount
from app.db.session import get_db_session
from app.domain.title_suggestion import TitleSuggestionResponse
from app.ports.blob_store import BlobStore
from app.ports.llm_client import LlmClient, LlmClientError
from app.ports.secret_provider import SecretProvider
from app.services.cv_service import CvService
from app.services.pdf_parser import PdfParseError
from app.services.title_suggestion_service import (
    CvTextUnavailableError,
    TitleSuggestionResponseError,
    TitleSuggestionService,
)
from app.validation.pdf import PdfValidationError

router = APIRouter(prefix="/cvs", tags=["cvs"])


class CvResponse(BaseModel):
    """Public CV metadata returned after upload or listing."""

    id: UUID
    name: str = Field(..., max_length=200)
    uploaded_at: datetime


def get_secret_provider(settings: Settings = Depends(get_settings_dependency)) -> SecretProvider:
    """Return the configured SecretProvider adapter for runtime secrets.

    Args:
        settings: Runtime application settings.

    Returns:
        SecretProvider: Environment-backed implementation for local development.
    """
    return create_secret_provider(settings)


def get_llm_client(
    settings: Settings = Depends(get_settings_dependency),
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> LlmClient:
    """Return the configured LlmClient adapter for title suggestions.

    Args:
        settings: Runtime application settings.
        secret_provider: SecretProvider port for resolving OpenAI credentials.

    Returns:
        LlmClient: OpenAI-backed structured completion client.
    """
    return create_llm_client(settings, secret_provider)


def get_blob_store(settings: Settings = Depends(get_settings_dependency)) -> BlobStore:
    """Return the configured BlobStore adapter for CV PDF storage.

    Args:
        settings: Runtime application settings.

    Returns:
        BlobStore: Memory or Azurite-backed implementation.
    """
    return create_blob_store(settings)


def _cv_to_response(cv: Cv) -> CvResponse:
    """Map a CV ORM row to the public API response shape.

    Args:
        cv: Persisted CV metadata row.

    Returns:
        CvResponse: API-safe CV metadata without blob keys or parsed text.
    """
    return CvResponse(id=cv.id, name=cv.name, uploaded_at=cv.uploaded_at)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CvResponse)
async def upload_cv(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
    settings: Settings = Depends(get_settings_dependency),
) -> CvResponse:
    """Upload a named CV PDF for the authenticated user.

    Args:
        name: Display name for the CV.
        file: Multipart PDF file payload.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        blob_store: BlobStore port for encrypted PDF storage.
        settings: Runtime application settings.

    Returns:
        CvResponse: Created CV metadata.

    Raises:
        HTTPException: When validation fails or the user is unauthenticated.
    """
    pdf_bytes = await file.read()
    try:
        cv = CvService(db, blob_store, blob_key_prefix=settings.blob_key_prefix).upload_cv(
            user=current_user,
            name=name,
            pdf_bytes=pdf_bytes,
            content_type=file.content_type,
        )
    except PdfValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except PdfParseError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return _cv_to_response(cv)


@router.get("", response_model=list[CvResponse])
async def list_cvs(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
    settings: Settings = Depends(get_settings_dependency),
) -> list[CvResponse]:
    """List active CV metadata for the authenticated user.

    Args:
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        blob_store: BlobStore port for encrypted PDF storage.
        settings: Runtime application settings.

    Returns:
        list[CvResponse]: Non-deleted CV metadata ordered by upload date.
    """
    cvs = CvService(db, blob_store, blob_key_prefix=settings.blob_key_prefix).list_cvs(current_user)
    return [_cv_to_response(cv) for cv in cvs]


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cv(
    cv_id: UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
    settings: Settings = Depends(get_settings_dependency),
) -> None:
    """Soft-delete an owned CV and remove its blob plus parsed text.

    Args:
        cv_id: CV primary key from the route path.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        blob_store: BlobStore port for encrypted PDF storage.
        settings: Runtime application settings.

    Raises:
        HTTPException: When the CV is missing, deleted for another account, or unauthenticated.
    """
    deleted = CvService(db, blob_store, blob_key_prefix=settings.blob_key_prefix).delete_cv(
        current_user,
        cv_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


@router.post("/{cv_id}/suggest-titles", response_model=TitleSuggestionResponse)
async def suggest_titles(
    cv: Cv = Depends(get_owned_cv),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    llm_client: LlmClient = Depends(get_llm_client),
) -> TitleSuggestionResponse:
    """Return sync AI Suggested Job Titles for an owned CV.

    Args:
        cv: Owner-scoped CV row resolved from the route path.
        current_user: Authenticated User Account from the session cookie.
        db: Request-scoped database session.
        llm_client: Structured title suggestion provider.

    Returns:
        TitleSuggestionResponse: Three to five title suggestions with rationales.

    Raises:
        HTTPException: When CV text is unavailable or the LLM provider fails.
    """
    try:
        return TitleSuggestionService(db, llm_client).suggest_titles(current_user, cv)
    except CvTextUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except (LlmClientError, TitleSuggestionResponseError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Title suggestions are temporarily unavailable",
        ) from error
