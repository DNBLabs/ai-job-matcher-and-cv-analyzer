"""Run quota and concurrency rules for User Accounts."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.analysis_run import AnalysisRunStatus

DAILY_RUN_LIMIT = 3
ROLLING_WINDOW = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class RunQuotaDecision:
    """Outcome of evaluating whether a User Account may start an Analysis Run."""

    can_start: bool
    remaining_runs: int | None
    concurrent_blocked: bool


def evaluate_run_quota(
    *,
    is_unlimited: bool,
    runs_started_in_last_24h: int,
    has_active_run: bool,
) -> RunQuotaDecision:
    """Decide if a User Account may start a new Analysis Run.

    Unlimited accounts bypass the daily cap but still respect the one-concurrent-run rule.

    Args:
        is_unlimited: True when the account is on the unlimited allowlist.
        runs_started_in_last_24h: Non-cancelled runs started within the rolling 24h window.
        has_active_run: True when the user has a run in Queued, Scraping, or Scoring.

    Returns:
        RunQuotaDecision: Whether the run may start and remaining quota metadata.

    Raises:
        ValueError: When runs_started_in_last_24h is negative.
    """
    if runs_started_in_last_24h < 0:
        raise ValueError("runs_started_in_last_24h must be non-negative")

    if has_active_run:
        remaining = None if is_unlimited else max(DAILY_RUN_LIMIT - runs_started_in_last_24h, 0)
        return RunQuotaDecision(
            can_start=False,
            remaining_runs=remaining,
            concurrent_blocked=True,
        )

    if is_unlimited:
        return RunQuotaDecision(
            can_start=True,
            remaining_runs=None,
            concurrent_blocked=False,
        )

    remaining_runs = max(DAILY_RUN_LIMIT - runs_started_in_last_24h, 0)
    return RunQuotaDecision(
        can_start=remaining_runs > 0,
        remaining_runs=remaining_runs,
        concurrent_blocked=False,
    )


def count_runs_toward_quota(
    runs: list[tuple[datetime, AnalysisRunStatus]],
    *,
    as_of: datetime,
) -> int:
    """Count runs that consume daily quota within the rolling 24h window.

    Args:
        runs: Pairs of run start time and terminal/active status.
        as_of: Reference time for the rolling window (must be timezone-aware UTC).

    Returns:
        int: Number of non-cancelled runs started within the last 24 hours.

    Raises:
        ValueError: When as_of is naive or a run timestamp is naive.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    window_start = as_of - ROLLING_WINDOW
    count = 0
    for started_at, status in runs:
        if started_at.tzinfo is None:
            raise ValueError("run timestamps must be timezone-aware")
        if status is AnalysisRunStatus.CANCELLED:
            continue
        if started_at >= window_start:
            count += 1
    return count


def has_active_run_from_statuses(statuses: list[AnalysisRunStatus]) -> bool:
    """Return True when any run status is Queued, Scraping, or Scoring.

    Args:
        statuses: Status values for a user's Analysis Runs.

    Returns:
        bool: True when concurrency would block a new run.
    """
    from app.domain.analysis_run import is_active_status

    return any(is_active_status(status) for status in statuses)
