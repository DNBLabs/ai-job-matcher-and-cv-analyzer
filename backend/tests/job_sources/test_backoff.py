"""Tests for the shared retry backoff helper used by Job Source adapters.

`backoff_delay_seconds` implements exponential backoff with full jitter
(random.uniform(0, capped exponential)), the canonical approach from the AWS
Architecture Blog "Exponential Backoff And Jitter". Adapters call it to space
out retries instead of hammering a throttling source with zero-delay attempts
(issue #58).
"""

from app.job_sources.base import (
    _BACKOFF_BASE_SECONDS,
    _BACKOFF_MAX_SECONDS,
    backoff_delay_seconds,
)


def test_delay_is_bounded_by_capped_exponential() -> None:
    """Each delay falls within [0, min(cap, base * 2**attempt)] (full jitter)."""
    for attempt in range(6):
        ceiling = min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2**attempt))
        # Sample repeatedly since the jitter is random.
        for _ in range(50):
            delay = backoff_delay_seconds(attempt)
            assert 0.0 <= delay <= ceiling


def test_jitter_upper_bound_grows_exponentially(monkeypatch) -> None:
    """With jitter pinned to its max, delays double per attempt up to the cap."""
    # Force random.uniform(low, high) to return its upper bound.
    monkeypatch.setattr(
        "app.job_sources.base.random.uniform", lambda low, high: high
    )

    delays = [backoff_delay_seconds(a) for a in range(5)]

    assert delays[0] == _BACKOFF_BASE_SECONDS
    assert delays[1] == _BACKOFF_BASE_SECONDS * 2
    assert delays[2] == _BACKOFF_BASE_SECONDS * 4
    # Later attempts are clamped to the ceiling.
    assert all(d <= _BACKOFF_MAX_SECONDS for d in delays)


def test_delay_can_be_zero_with_minimum_jitter(monkeypatch) -> None:
    """Full jitter permits a near-zero delay (lower bound of the range)."""
    monkeypatch.setattr(
        "app.job_sources.base.random.uniform", lambda low, high: low
    )

    assert backoff_delay_seconds(0) == 0.0
    assert backoff_delay_seconds(3) == 0.0
