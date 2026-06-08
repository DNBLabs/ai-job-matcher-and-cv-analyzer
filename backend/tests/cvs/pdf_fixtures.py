"""Shared PDF byte fixtures for CV upload and parser tests."""

from io import BytesIO

from pypdf import PdfWriter


def build_valid_test_pdf_bytes() -> bytes:
    """Build a minimal one-page PDF accepted by boundary validation and pypdf."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


VALID_PDF_BYTES = build_valid_test_pdf_bytes()
