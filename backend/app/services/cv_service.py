"""Application service for CV upload, storage, and metadata persistence."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Cv, UserAccount
from app.db.repositories.cv_repository import CvRepository
from app.domain.validation import validate_cv_name
from app.ports.blob_store import BlobStore
from app.validation.pdf import PdfValidationError, ensure_pdf_parse_timeout_stub, validate_pdf_upload


class CvService:
    """Coordinate PDF validation, blob storage, and CV metadata persistence."""

    def __init__(self, session: Session, blob_store: BlobStore, blob_key_prefix: str = "cvs/") -> None:
        """Bind the service to a database session and blob storage adapter.

        Args:
            session: Request-scoped SQLAlchemy session.
            blob_store: BlobStore port for encrypted object storage.
            blob_key_prefix: Prefix persisted in CV metadata (matches adapter prefix).
        """
        self._session = session
        self._blob_store = blob_store
        normalized_prefix = blob_key_prefix.strip("/")
        self._blob_key_prefix = f"{normalized_prefix}/" if normalized_prefix else ""

    def upload_cv(
        self,
        user: UserAccount,
        name: str,
        pdf_bytes: bytes,
        content_type: str | None,
    ) -> Cv:
        """Validate, store, and persist an uploaded CV PDF for the authenticated user.

        Args:
            user: Authenticated User Account owning the CV.
            name: User-provided display name for the CV.
            pdf_bytes: Raw uploaded PDF bytes.
            content_type: Declared multipart content type from the client.

        Returns:
            Cv: Persisted CV metadata row.

        Raises:
            PdfValidationError: When PDF validation fails.
            ValueError: When the CV name is invalid.
        """
        validated_name = validate_cv_name(name)
        validate_pdf_upload(pdf_bytes, content_type)
        ensure_pdf_parse_timeout_stub(pdf_bytes)

        cv_id = uuid.uuid4()
        logical_blob_key = f"{user.id}/{cv_id}.pdf"
        persisted_blob_key = f"{self._blob_key_prefix}{logical_blob_key}"

        self._blob_store.put(logical_blob_key, pdf_bytes)
        return CvRepository(self._session).create(
            cv_id=cv_id,
            user_id=user.id,
            name=validated_name,
            blob_key=persisted_blob_key,
        )
