"""Safe PDF text extraction with page limits and processing timeouts."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from io import BytesIO

from pypdf import PdfReader

MAX_PDF_PAGES = 20
PARSE_TIMEOUT_SECONDS = 30


class PdfParseError(ValueError):
    """Raised when PDF text extraction fails boundary checks."""


def extract_text_from_pdf(
    pdf_bytes: bytes,
    *,
    max_pages: int = MAX_PDF_PAGES,
    timeout_seconds: int = PARSE_TIMEOUT_SECONDS,
) -> str:
    """Extract plain text from PDF bytes with page and timeout limits.

    Args:
        pdf_bytes: Validated PDF file bytes.
        max_pages: Maximum number of pages permitted in the document.
        timeout_seconds: Wall-clock limit for parsing before aborting.

    Returns:
        str: Extracted text joined across allowed pages (may be empty).

    Raises:
        PdfParseError: When the PDF exceeds page limits or parsing times out.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_extract_text_inner, pdf_bytes, max_pages)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as error:
            raise PdfParseError("PDF processing timed out") from error


def _extract_text_inner(pdf_bytes: bytes, max_pages: int) -> str:
    """Parse PDF bytes on a worker thread for timeout enforcement.

    Args:
        pdf_bytes: Validated PDF file bytes.
        max_pages: Maximum number of pages permitted in the document.

    Returns:
        str: Extracted text joined across allowed pages.

    Raises:
        PdfParseError: When the PDF exceeds page limits or cannot be parsed safely.
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
    except Exception as error:
        raise PdfParseError("Unable to parse PDF") from error

    page_count = len(reader.pages)
    if page_count > max_pages:
        raise PdfParseError(f"PDF exceeds maximum page limit of {max_pages}")

    extracted_pages: list[str] = []
    for page_index in range(page_count):
        page_text = reader.pages[page_index].extract_text() or ""
        extracted_pages.append(page_text)

    return "\n".join(extracted_pages).strip()
