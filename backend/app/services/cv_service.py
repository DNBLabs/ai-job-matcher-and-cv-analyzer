"""Application service for CV upload, storage, listing, deletion, and metadata persistence."""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Cv, UserAccount
from app.db.repositories.cv_repository import CvRepository
from app.domain.validation import validate_cv_name
from app.ports.blob_store import BlobNotFoundError, BlobStore
from app.services.pdf_parser import PdfParseError, extract_text_from_pdf
from app.validation.pdf import PdfValidationError, validate_pdf_upload


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

    def list_cvs(self, user: UserAccount) -> list[Cv]:
        """Return active CV metadata rows for the authenticated user.

        Args:
            user: Authenticated User Account owning the CVs.

        Returns:
            list[Cv]: Non-deleted CV rows ordered by most recent upload first.
        """
        return CvRepository(self._session).list_active_for_user(user.id)

    def delete_cv(self, user: UserAccount, cv_id: uuid.UUID) -> bool:
        """Soft-delete an owned CV and remove its blob from storage.

        Args:
            user: Authenticated User Account owning the CV.
            cv_id: CV primary key to delete.

        Returns:
            bool: True when the CV existed for the owner (including idempotent re-delete).

        Raises:
            BlobNotFoundError: When the blob was already removed but metadata still exists.
        """
        repository = CvRepository(self._session)
        cv = repository.get_by_id_for_owner(cv_id, user.id)
        if cv is None:
            return False

        if cv.deleted_at is None:
            logical_blob_key = self._logical_blob_key_from_persisted(cv.blob_key)
            try:
                self._blob_store.delete(logical_blob_key)
            except BlobNotFoundError:
                pass
            repository.soft_delete_for_user(cv_id, user.id)
            return True

        return True

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
            PdfParseError: When safe PDF parsing fails.
            ValueError: When the CV name is invalid.
        """
        validated_name = validate_cv_name(name)
        validate_pdf_upload(pdf_bytes, content_type)
        parsed_text = extract_text_from_pdf(pdf_bytes)

        cv_id = uuid.uuid4()
        logical_blob_key = f"{user.id}/{cv_id}.pdf"
        persisted_blob_key = f"{self._blob_key_prefix}{logical_blob_key}"

        self._blob_store.put(logical_blob_key, pdf_bytes)
        return CvRepository(self._session).create(
            cv_id=cv_id,
            user_id=user.id,
            name=validated_name,
            blob_key=persisted_blob_key,
            parsed_text=parsed_text or None,
        )

    def _logical_blob_key_from_persisted(self, persisted_blob_key: str) -> str:
        """Convert a persisted blob key to the adapter logical key.

        Args:
            persisted_blob_key: Fully qualified blob key stored on the CV row.

        Returns:
            str: Logical key accepted by BlobStore adapters.
        """
        if self._blob_key_prefix and persisted_blob_key.startswith(self._blob_key_prefix):
            return persisted_blob_key[len(self._blob_key_prefix) :]
        return persisted_blob_key
