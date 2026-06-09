"""Unit tests for ScoringService with a fake scoring LLM client."""

import pytest

from app.domain.divergence import InterviewLikelihood
from app.domain.scoring_schema import ScoringLlmOutput
from app.ports.llm_client import LlmClientError
from app.services.scoring_service import ScoringService, ScoringSkippedError
from tests.fakes.fake_scoring_llm_client import FakeScoringLlmClient, make_listing

_CV_TEXT = "Senior Python engineer with FastAPI and PostgreSQL experience."


def _valid_output(*, match_score: int = 82) -> ScoringLlmOutput:
    return ScoringLlmOutput(
        match_score=match_score,
        interview_likelihood=InterviewLikelihood.HIGH,
        matched_skills=["Python", "FastAPI"],
        skill_gaps=["Kubernetes"],
        red_flags=[],
        talking_points=["Discuss API scaling work"],
    )


def test_score_listing_returns_validated_scored_listing() -> None:
    """A valid LLM payload maps to a ScoredListing with breakdown and source identity."""
    listing = make_listing(source="adzuna")
    service = ScoringService(FakeScoringLlmClient(behaviours=[_valid_output()]))

    result = service.score_listing(cv_text=_CV_TEXT, listing=listing)

    assert result.match_score == 82
    assert result.interview_likelihood is InterviewLikelihood.HIGH
    assert result.source == "adzuna"
    assert result.title == listing.title
    assert result.url == listing.url
    assert result.breakdown_json["matched_skills"] == ["Python", "FastAPI"]
    assert result.breakdown_json["skill_gaps"] == ["Kubernetes"]


def test_score_listing_forwards_cv_text_not_bytes() -> None:
    """The parsed CV text is forwarded verbatim to the LLM client."""
    fake = FakeScoringLlmClient(behaviours=[_valid_output()])
    ScoringService(fake).score_listing(cv_text=_CV_TEXT, listing=make_listing())

    assert fake.seen_cv_texts == [_CV_TEXT]


def test_score_listing_rejects_blank_cv_text() -> None:
    """Blank CV text is rejected before any LLM call is made."""
    fake = FakeScoringLlmClient(behaviours=[_valid_output()])

    with pytest.raises(ValueError, match="CV text"):
        ScoringService(fake).score_listing(cv_text="   ", listing=make_listing())

    assert fake.call_count == 0


def test_score_listing_retries_once_then_succeeds() -> None:
    """A malformed first response is retried once and the retry result is returned."""
    fake = FakeScoringLlmClient(
        behaviours=[LlmClientError("malformed JSON"), _valid_output(match_score=55)]
    )

    result = ScoringService(fake).score_listing(cv_text=_CV_TEXT, listing=make_listing())

    assert result.match_score == 55
    assert fake.call_count == 2


def test_score_listing_skips_after_second_failure() -> None:
    """Two malformed responses raise ScoringSkippedError after exactly one retry."""
    fake = FakeScoringLlmClient(
        behaviours=[LlmClientError("bad 1"), LlmClientError("bad 2")]
    )
    service = ScoringService(fake)

    with pytest.raises(ScoringSkippedError):
        service.score_listing(cv_text=_CV_TEXT, listing=make_listing())

    assert fake.call_count == 2


def test_score_run_aggregates_tokens_and_cost() -> None:
    """score_run aggregates per-call usage into per-run FinOps totals."""
    listings = [make_listing(source="adzuna"), make_listing(source="adzuna")]
    fake = FakeScoringLlmClient(
        behaviours=[_valid_output(), _valid_output()],
        prompt_tokens=1000,
        completion_tokens=300,
    )

    result = ScoringService(fake).score_run(cv_text=_CV_TEXT, listings=listings)

    assert len(result.scored) == 2
    assert result.finops.listings_scored == 2
    assert result.finops.listings_skipped == 0
    assert result.finops.prompt_tokens == 2000
    assert result.finops.completion_tokens == 600
    assert result.finops.model == "gpt-4o"
    # 2000 input @ $2.50/1M + 600 output @ $10.00/1M = 0.005 + 0.006
    assert result.finops.estimated_usd == pytest.approx(0.011)


def test_score_run_skips_failed_listings_and_counts_them() -> None:
    """A listing that fails after retry is skipped; the rest are still scored."""
    listings = [make_listing(), make_listing()]
    fake = FakeScoringLlmClient(
        behaviours=[
            LlmClientError("bad"),
            LlmClientError("bad"),  # first listing exhausts retry → skipped
            _valid_output(),  # second listing succeeds
        ]
    )

    result = ScoringService(fake).score_run(cv_text=_CV_TEXT, listings=listings)

    assert len(result.scored) == 1
    assert result.finops.listings_scored == 1
    assert result.finops.listings_skipped == 1


def test_score_run_enforces_hard_cap_of_100_calls() -> None:
    """The 101st listing is never scored; the cap bounds both calls and results."""
    listings = [make_listing(external_id=f"ext-{i}") for i in range(101)]
    fake = FakeScoringLlmClient(behaviours=[_valid_output()])

    result = ScoringService(fake).score_run(cv_text=_CV_TEXT, listings=listings)

    assert len(result.scored) == 100
    assert result.finops.listings_scored == 100
    assert fake.call_count == 100


def test_score_run_cap_counts_retries_against_call_budget() -> None:
    """Retries consume the per-run call budget so total LLM calls never exceed it."""
    listings = [make_listing(), make_listing(), make_listing()]
    fake = FakeScoringLlmClient(
        behaviours=[
            LlmClientError("retry me"),  # listing 1 attempt 1 (call 1)
            _valid_output(),  # listing 1 attempt 2 (call 2) → scored
            _valid_output(),  # listing 2 attempt 1 (call 3) → scored, budget exhausted
            _valid_output(),  # would score listing 3, but no budget remains
        ]
    )

    result = ScoringService(fake, max_calls_per_run=3).score_run(
        cv_text=_CV_TEXT, listings=listings
    )

    assert fake.call_count == 3
    assert result.finops.listings_scored == 2
    assert len(result.scored) == 2
