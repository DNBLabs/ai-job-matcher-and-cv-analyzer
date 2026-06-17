"""Tests for the JobSource port's shared error type (JobSourceError).

JobSourceError carries an optional, PII/secret-free ``reason`` token so the
worker pipeline can log *why* a source failed without echoing credentials,
URLs, or user search terms (CONTEXT §3 PII-free logging).
"""

from app.job_sources.base import JobSourceError


def test_job_source_error_carries_reason() -> None:
    """A JobSourceError exposes the reason token it was constructed with."""
    error = JobSourceError("source unavailable", reason="http_401")

    assert error.reason == "http_401"
    assert str(error) == "source unavailable"


def test_job_source_error_reason_defaults_to_none() -> None:
    """A JobSourceError raised without a reason exposes reason=None."""
    error = JobSourceError("source unavailable")

    assert error.reason is None
