"""CV HTTP routes for upload, listing, and deletion."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.factory import create_blob_store
from app.api.deps import get_current_user, get_settings_dependency
from app.api.validation import NOT_FOUND_DETAIL
from app.config import Settings
from app.db.models import Cv, UserAccount
from app.db.session import get_db_session
from app.ports.blob_store import BlobStore
from app.services.cv_service import CvService
from app.services.pdf_parser import PdfParseError
from app.validation.pdf import PdfValidationError

router = APIRouter(prefix="/cvs", tags=["cvs"])


class CvResponse(BaseModel):
    """Public CV metadata returned after upload or listing."""

    id: UUID
    name: str = Field(..., max_length=200)
    uploaded_at: datetime


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
