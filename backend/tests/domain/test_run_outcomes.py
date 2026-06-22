"""Unit tests for run outcome domain logic (Task 18).

Verifies classify_run_failure and failure_message_for against every branch of
the outcome matrix: complete run, failed-no-listings, failed-scrape-error.
"""

import pytest

from app.domain.analysis_run import AnalysisRunStatus
from app.domain.run_outcomes import RunFailureReason, classify_run_failure, failure_message_for


def test_classify_run_failure_returns_none_for_complete_run() -> None:
    """A COMPLETE run has no failure reason."""
    assert classify_run_failure(AnalysisRunStatus.COMPLETE, None) is None


def test_classify_run_failure_returns_none_for_active_statuses() -> None:
    """In-flight runs (queued, scraping, scoring) have no failure reason yet."""
    for status in (
        AnalysisRunStatus.QUEUED,
        AnalysisRunStatus.SCRAPING,
        AnalysisRunStatus.SCORING,
    ):
        assert classify_run_failure(status, None) is None


def test_classify_run_failure_returns_no_jobs_found_when_no_source_errors() -> None:
    """FAILED with no source errors means the search returned zero listings."""
    assert classify_run_failure(AnalysisRunStatus.FAILED, None) is RunFailureReason.NO_JOBS_FOUND


def test_classify_run_failure_returns_no_jobs_found_when_source_failures_empty() -> None:
    """FAILED with an empty failures list maps to NO_JOBS_FOUND."""
    assert (
        classify_run_failure(AnalysisRunStatus.FAILED, {"failures": []})
        is RunFailureReason.NO_JOBS_FOUND
    )


def test_classify_run_failure_returns_scrape_failed_when_sources_errored() -> None:
    """FAILED with at least one source error maps to SCRAPE_FAILED."""
    failures = {"failures": [{"source": "reed", "reason": "scrape_failed"}]}
    assert (
        classify_run_failure(AnalysisRunStatus.FAILED, failures)
        is RunFailureReason.SCRAPE_FAILED
    )


def test_classify_run_failure_scrape_failed_with_multiple_source_errors() -> None:
    """FAILED when both sources errored also maps to SCRAPE_FAILED."""
    failures = {
        "failures": [
            {"source": "adzuna", "reason": "scrape_failed"},
            {"source": "reed", "reason": "scrape_failed"},
        ]
    }
    assert (
        classify_run_failure(AnalysisRunStatus.FAILED, failures)
        is RunFailureReason.SCRAPE_FAILED
    )


def test_failure_message_for_returns_none_for_complete_run() -> None:
    """No failure message when the run completed successfully."""
    assert failure_message_for(AnalysisRunStatus.COMPLETE, None) is None


def test_failure_message_for_no_jobs_found() -> None:
    """FAILED with no source errors produces the empty-search message."""
    msg = failure_message_for(AnalysisRunStatus.FAILED, None)
    assert msg == "No jobs found for this search"


def test_failure_message_for_scrape_failed() -> None:
    """FAILED with a source error produces the scraping-problem message."""
    failures = {"failures": [{"source": "adzuna", "reason": "scrape_failed"}]}
    msg = failure_message_for(AnalysisRunStatus.FAILED, failures)
    assert msg == "Scraping failed — try again later"


# ---------------------------------------------------------------------------
# Mixed-source cases (issue #59) — at least one source OK + one failed
# ---------------------------------------------------------------------------


def test_classify_run_failure_no_jobs_found_when_one_source_ok_one_failed() -> None:
    """One source responded OK (0 results) and another failed → NO_JOBS_FOUND.

    The search genuinely returned nothing from the successful source; the other
    source's failure should not surface as SCRAPE_FAILED to the user.
    """
    payload = {
        "failures": [{"source": "reed", "reason": "scrape_failed"}],
        "successes": ["adzuna"],
    }
    assert (
        classify_run_failure(AnalysisRunStatus.FAILED, payload)
        is RunFailureReason.NO_JOBS_FOUND
    )


def test_classify_run_failure_scrape_failed_when_all_sources_fail_with_successes_empty() -> None:
    """All sources failed with an explicit empty successes list → SCRAPE_FAILED."""
    payload = {
        "failures": [
            {"source": "adzuna", "reason": "scrape_failed"},
            {"source": "reed", "reason": "scrape_failed"},
        ],
        "successes": [],
    }
    assert (
        classify_run_failure(AnalysisRunStatus.FAILED, payload)
        is RunFailureReason.SCRAPE_FAILED
    )


def test_failure_message_for_no_jobs_found_mixed_source() -> None:
    """Mixed OK+fail → user sees empty-search message, not scraping error."""
    payload = {
        "failures": [{"source": "reed", "reason": "scrape_failed"}],
        "successes": ["adzuna"],
    }
    assert failure_message_for(AnalysisRunStatus.FAILED, payload) == "No jobs found for this search"
