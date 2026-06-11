"""Run outcome domain logic: failure classification and user-facing messages.

Provides helpers for determining *why* an Analysis Run failed so the API can
surface a distinct message for the two failure modes defined by the PRD:

- Zero listings from an empty search (no scraping errors)
- Zero listings because all sources errored after retries

No persistence logic lives here — only pure classification from existing state.
"""

from enum import StrEnum

from app.domain.analysis_run import AnalysisRunStatus


class RunFailureReason(StrEnum):
    """Reason a Failed Analysis Run returned zero scored listings."""

    NO_JOBS_FOUND = "no_jobs_found"
    SCRAPE_FAILED = "scrape_failed"


_FAILURE_MESSAGES: dict[RunFailureReason, str] = {
    RunFailureReason.NO_JOBS_FOUND: "No jobs found for this search",
    RunFailureReason.SCRAPE_FAILED: "Scraping failed — try again later",
}


def classify_run_failure(
    status: AnalysisRunStatus,
    source_failures_json: dict | None,
) -> RunFailureReason | None:
    """Return the failure reason for a Failed run, or None when not applicable.

    Args:
        status: Terminal or active status of the Analysis Run.
        source_failures_json: Persisted ``{"failures": [...]}`` payload, or None.

    Returns:
        RunFailureReason | None: SCRAPE_FAILED when at least one source errored;
            NO_JOBS_FOUND when the run failed but all sources responded cleanly;
            None for any non-FAILED status.
    """
    if status is not AnalysisRunStatus.FAILED:
        return None
    failures = (source_failures_json or {}).get("failures") or []
    if failures:
        return RunFailureReason.SCRAPE_FAILED
    return RunFailureReason.NO_JOBS_FOUND


def failure_message_for(
    status: AnalysisRunStatus,
    source_failures_json: dict | None,
) -> str | None:
    """Return the user-facing failure message for a Failed run, or None.

    Args:
        status: Terminal or active status of the Analysis Run.
        source_failures_json: Persisted ``{"failures": [...]}`` payload, or None.

    Returns:
        str | None: Localised failure string when the run failed; None otherwise.
    """
    reason = classify_run_failure(status, source_failures_json)
    if reason is None:
        return None
    return _FAILURE_MESSAGES[reason]
