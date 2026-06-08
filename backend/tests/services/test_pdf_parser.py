"""Unit tests for safe PDF text extraction with page limits and timeouts."""

import time
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.pdf_parser import (
    MAX_PDF_PAGES,
    PARSE_TIMEOUT_SECONDS,
    PdfParseError,
    extract_text_from_pdf,
)
from tests.cvs.pdf_fixtures import VALID_PDF_BYTES


def _build_pdf_with_page_count(page_count: int) -> bytes:
    """Build an in-memory PDF with the requested number of blank pages."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_text_from_pdf_accepts_valid_pdf() -> None:
    """Valid PDF bytes are parsed without raising."""
    extract_text_from_pdf(VALID_PDF_BYTES)


def test_extract_text_from_pdf_rejects_excessive_page_count() -> None:
    """PDFs exceeding the page limit are rejected before full extraction."""
    oversized_pdf = _build_pdf_with_page_count(MAX_PDF_PAGES + 1)

    with pytest.raises(PdfParseError, match="page"):
        extract_text_from_pdf(oversized_pdf)


def test_extract_text_from_pdf_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runaway PDF processing is aborted after the configured timeout."""

    def slow_extract(_pdf_bytes: bytes, _max_pages: int) -> str:
        time.sleep(PARSE_TIMEOUT_SECONDS + 1)
        return "late"

    monkeypatch.setattr("app.services.pdf_parser._extract_text_inner", slow_extract)

    with pytest.raises(PdfParseError, match="timed out"):
        extract_text_from_pdf(VALID_PDF_BYTES, timeout_seconds=0.1)
