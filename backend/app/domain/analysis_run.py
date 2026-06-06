"""Analysis Run lifecycle rules: status enum, transitions, and terminal outcomes."""

from enum import StrEnum


class AnalysisRunStatus(StrEnum):
    """Lifecycle states for an Analysis Run pipeline execution."""

    QUEUED = "queued"
    SCRAPING = "scraping"
    SCORING = "scoring"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


_VALID_TRANSITIONS: dict[AnalysisRunStatus, frozenset[AnalysisRunStatus]] = {
    AnalysisRunStatus.QUEUED: frozenset({AnalysisRunStatus.SCRAPING}),
    AnalysisRunStatus.SCRAPING: frozenset({AnalysisRunStatus.SCORING}),
    AnalysisRunStatus.SCORING: frozenset(
        {AnalysisRunStatus.COMPLETE, AnalysisRunStatus.FAILED},
    ),
    AnalysisRunStatus.COMPLETE: frozenset(),
    AnalysisRunStatus.FAILED: frozenset(),
    AnalysisRunStatus.CANCELLED: frozenset(),
}

_ACTIVE_STATUSES = frozenset(
    {
        AnalysisRunStatus.QUEUED,
        AnalysisRunStatus.SCRAPING,
        AnalysisRunStatus.SCORING,
    },
)

_TERMINAL_STATUSES = frozenset(
    {
        AnalysisRunStatus.COMPLETE,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.CANCELLED,
    },
)


def can_transition(current: AnalysisRunStatus, target: AnalysisRunStatus) -> bool:
    """Return True when the Analysis Run may move from current to target status.

    Args:
        current: Existing run status.
        target: Proposed next status.

    Returns:
        bool: True when the transition follows the PRD lifecycle.
    """
    return target in _VALID_TRANSITIONS[current]


def is_active_status(status: AnalysisRunStatus) -> bool:
    """Return True when the run counts toward the one-concurrent-run limit.

    Args:
        status: Run status to evaluate.

    Returns:
        bool: True for Queued, Scraping, or Scoring.
    """
    return status in _ACTIVE_STATUSES


def is_terminal_status(status: AnalysisRunStatus) -> bool:
    """Return True when the run has reached a terminal lifecycle state.

    Args:
        status: Run status to evaluate.

    Returns:
        bool: True for Complete, Failed, or Cancelled.
    """
    return status in _TERMINAL_STATUSES


def resolve_terminal_status(*, scored_listing_count: int) -> AnalysisRunStatus:
    """Map scored listing count to Complete (partial success) or Failed.

    Args:
        scored_listing_count: Number of listings successfully scored in the run.

    Returns:
        AnalysisRunStatus: COMPLETE when count >= 1, otherwise FAILED.

    Raises:
        ValueError: When scored_listing_count is negative.
    """
    if scored_listing_count < 0:
        raise ValueError("scored_listing_count must be non-negative")
    if scored_listing_count >= 1:
        return AnalysisRunStatus.COMPLETE
    return AnalysisRunStatus.FAILED
