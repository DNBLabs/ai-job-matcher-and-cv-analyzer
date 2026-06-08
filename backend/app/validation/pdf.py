"""PDF upload validation for MIME type, size, and magic-byte checks."""

PDF_MAGIC_BYTES = b"%PDF-"
MAX_PDF_BYTES = 5 * 1024 * 1024
ALLOWED_PDF_CONTENT_TYPE = "application/pdf"


class PdfValidationError(ValueError):
    """Raised when uploaded bytes fail PDF boundary validation."""


def validate_pdf_upload(content: bytes, content_type: str | None) -> None:
    """Validate PDF upload bytes and declared MIME type at the API boundary.

    Args:
        content: Raw uploaded file bytes.
        content_type: Declared multipart content type from the client.

    Raises:
        PdfValidationError: When the file is not a PDF, is too large, or has invalid magic bytes.
    """
    if content_type is None or content_type.lower() != ALLOWED_PDF_CONTENT_TYPE:
        raise PdfValidationError("File must be a PDF")
    if len(content) > MAX_PDF_BYTES:
        raise PdfValidationError("File too large")
    if len(content) < len(PDF_MAGIC_BYTES) or not content.startswith(PDF_MAGIC_BYTES):
        raise PdfValidationError("Invalid PDF file")
