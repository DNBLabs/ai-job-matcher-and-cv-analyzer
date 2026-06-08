"""Unit tests for PDF upload validation at the API trust boundary."""

import pytest

from app.validation.pdf import (
    MAX_PDF_BYTES,
    PdfValidationError,
    validate_pdf_upload,
)

from tests.cvs.pdf_fixtures import VALID_PDF_BYTES
EXE_BYTES = b"MZ\x90\x00fake executable content"


def test_validate_pdf_upload_accepts_valid_pdf() -> None:
    """Valid PDF bytes and MIME type pass boundary validation."""
    validate_pdf_upload(VALID_PDF_BYTES, "application/pdf")


def test_validate_pdf_upload_rejects_non_pdf_content_type() -> None:
    """Non-PDF MIME types are rejected even when magic bytes look valid."""
    with pytest.raises(PdfValidationError, match="PDF"):
        validate_pdf_upload(VALID_PDF_BYTES, "application/octet-stream")


def test_validate_pdf_upload_rejects_oversize_file() -> None:
    """Files larger than 5 MB are rejected."""
    oversized = b"%PDF-" + (b"x" * (MAX_PDF_BYTES - 4))

    with pytest.raises(PdfValidationError, match="large"):
        validate_pdf_upload(oversized, "application/pdf")


def test_validate_pdf_upload_rejects_invalid_magic_bytes() -> None:
    """Files without the PDF magic header are rejected."""
    with pytest.raises(PdfValidationError, match="PDF"):
        validate_pdf_upload(EXE_BYTES, "application/pdf")
