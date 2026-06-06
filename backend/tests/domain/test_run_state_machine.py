"""Behavior tests for Analysis Run status transitions and terminal outcomes."""

import pytest

from app.domain.analysis_run import (
    AnalysisRunStatus,
    can_transition,
    is_active_status,
    is_terminal_status,
    resolve_terminal_status,
)


def test_queued_run_advances_to_scraping() -> None:
    """A Queued Analysis Run may start worker processing by moving to Scraping."""
    assert can_transition(AnalysisRunStatus.QUEUED, AnalysisRunStatus.SCRAPING) is True


def test_scraping_run_advances_to_scoring() -> None:
    """After listings are fetched, the run enters the Scoring phase."""
    assert can_transition(AnalysisRunStatus.SCRAPING, AnalysisRunStatus.SCORING) is True


def test_scoring_run_completes_when_at_least_one_listing_scored() -> None:
    """Partial success still finishes as Complete when any listing was scored."""
    assert can_transition(AnalysisRunStatus.SCORING, AnalysisRunStatus.COMPLETE) is True
    assert resolve_terminal_status(scored_listing_count=1) is AnalysisRunStatus.COMPLETE


def test_scoring_run_fails_when_zero_listings_scored() -> None:
    """Zero scored listings after retries yields Failed, not Complete."""
    assert can_transition(AnalysisRunStatus.SCORING, AnalysisRunStatus.FAILED) is True
    assert resolve_terminal_status(scored_listing_count=0) is AnalysisRunStatus.FAILED


def test_terminal_statuses_cannot_transition_further() -> None:
    """Complete and Failed runs are terminal — no further lifecycle changes."""
    for terminal in (AnalysisRunStatus.COMPLETE, AnalysisRunStatus.FAILED, AnalysisRunStatus.CANCELLED):
        assert is_terminal_status(terminal) is True
        for target in AnalysisRunStatus:
            assert can_transition(terminal, target) is False


def test_active_statuses_include_queued_scraping_scoring() -> None:
    """Concurrency rules treat Queued, Scraping, and Scoring as in-flight runs."""
    assert is_active_status(AnalysisRunStatus.QUEUED) is True
    assert is_active_status(AnalysisRunStatus.SCRAPING) is True
    assert is_active_status(AnalysisRunStatus.SCORING) is True
    assert is_active_status(AnalysisRunStatus.COMPLETE) is False


def test_invalid_transitions_are_rejected() -> None:
    """Workers cannot skip phases or move backwards in the lifecycle."""
    assert can_transition(AnalysisRunStatus.QUEUED, AnalysisRunStatus.SCORING) is False
    assert can_transition(AnalysisRunStatus.SCRAPING, AnalysisRunStatus.QUEUED) is False
    assert can_transition(AnalysisRunStatus.SCORING, AnalysisRunStatus.SCRAPING) is False


def test_resolve_terminal_status_rejects_negative_counts() -> None:
    """Negative scored counts are invalid input at the domain boundary."""
    with pytest.raises(ValueError, match="scored_listing_count"):
        resolve_terminal_status(scored_listing_count=-1)
