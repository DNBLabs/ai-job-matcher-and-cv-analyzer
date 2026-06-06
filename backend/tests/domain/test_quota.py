"""Behavior tests for Analysis Run quota and concurrency rules."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.analysis_run import AnalysisRunStatus
from app.domain.quota import DAILY_RUN_LIMIT, evaluate_run_quota


def test_standard_user_with_quota_remaining_may_start_run() -> None:
    """A Job Seeker under the daily cap and without an active run may start."""
    decision = evaluate_run_quota(
        is_unlimited=False,
        runs_started_in_last_24h=1,
        has_active_run=False,
    )

    assert decision.can_start is True
    assert decision.remaining_runs == 2
    assert decision.concurrent_blocked is False


def test_standard_user_blocked_at_daily_cap() -> None:
    """Three runs in a rolling 24h window blocks a fourth start."""
    decision = evaluate_run_quota(
        is_unlimited=False,
        runs_started_in_last_24h=DAILY_RUN_LIMIT,
        has_active_run=False,
    )

    assert decision.can_start is False
    assert decision.remaining_runs == 0
    assert decision.concurrent_blocked is False


def test_unlimited_user_bypasses_daily_cap() -> None:
    """Unlimited allowlist accounts skip the rolling 24h run limit."""
    decision = evaluate_run_quota(
        is_unlimited=True,
        runs_started_in_last_24h=100,
        has_active_run=False,
    )

    assert decision.can_start is True
    assert decision.remaining_runs is None
    assert decision.concurrent_blocked is False


def test_unlimited_user_still_blocked_by_concurrent_run() -> None:
    """Even unlimited accounts may only have one active Analysis Run."""
    decision = evaluate_run_quota(
        is_unlimited=True,
        runs_started_in_last_24h=0,
        has_active_run=True,
    )

    assert decision.can_start is False
    assert decision.concurrent_blocked is True


def test_concurrent_run_blocks_new_start_before_daily_cap() -> None:
    """An in-flight run prevents starting another regardless of remaining quota."""
    decision = evaluate_run_quota(
        is_unlimited=False,
        runs_started_in_last_24h=0,
        has_active_run=True,
    )

    assert decision.can_start is False
    assert decision.remaining_runs == DAILY_RUN_LIMIT
    assert decision.concurrent_blocked is True


def test_count_runs_in_rolling_window_excludes_cancelled() -> None:
    """Cancelled runs do not consume daily quota in the rolling window."""
    from app.domain.quota import count_runs_toward_quota

    now = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    runs = [
        (now - timedelta(hours=2), AnalysisRunStatus.COMPLETE),
        (now - timedelta(hours=4), AnalysisRunStatus.CANCELLED),
        (now - timedelta(hours=30), AnalysisRunStatus.COMPLETE),
    ]

    assert count_runs_toward_quota(runs, as_of=now) == 1


def test_count_runs_rejects_negative_inputs() -> None:
    """Domain quota helpers validate boundary inputs."""
    from app.domain.quota import count_runs_toward_quota

    now = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="runs_started_in_last_24h"):
        evaluate_run_quota(
            is_unlimited=False,
            runs_started_in_last_24h=-1,
            has_active_run=False,
        )
    with pytest.raises(ValueError, match="as_of"):
        count_runs_toward_quota([], as_of=now.replace(tzinfo=None))
