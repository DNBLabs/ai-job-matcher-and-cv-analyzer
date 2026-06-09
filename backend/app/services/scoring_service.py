"""Per-listing AI scoring service with retry, hard cap, and FinOps aggregation.

Implements the scoring half of ADR-0003: one structured LLM call per listing
producing a Match Score, Interview Likelihood band, and breakdown arrays. The
worker pipeline (Task 15) consumes RunScoringResult to persist job_match_result
rows and the per-run FinOps summary on analysis_run.finops_json.
"""

import logging
from dataclasses import dataclass

from app.domain.finops import estimate_gpt4o_usd
from app.domain.scoring_schema import (
    RunScoringResult,
    ScoredListing,
    ScoringFinops,
    ScoringLlmOutput,
)
from app.domain.validation import validate_match_score
from app.job_sources.base import NormalisedListing
from app.ports.llm_client import LlmClientError, LlmUsage, ScoringLlmClient

logger = logging.getLogger(__name__)

# PRD hard product cap: at most 100 scoring *calls* per Analysis Run (CONTEXT §4).
# Retries consume the same budget, so a run never exceeds this many LLM calls.
_MAX_SCORING_CALLS_PER_RUN = 100
# ADR-0003: at most one retry per listing on malformed output.
_MAX_ATTEMPTS_PER_LISTING = 2
_DEFAULT_SCORING_MODEL = "gpt-4o"


class ScoringSkippedError(Exception):
    """Raised when a listing cannot be scored after the single permitted retry."""


@dataclass(frozen=True)
class _ScoreAttempt:
    """Internal outcome of attempting to score one listing.

    Tracks calls_used so the per-run cap can be enforced against actual LLM calls
    (including retries), not merely the number of listings processed.
    """

    scored: ScoredListing | None
    usage: LlmUsage | None
    calls_used: int


class ScoringService:
    """Coordinate per-listing scoring, malformed-output retry, and FinOps totals."""

    def __init__(
        self,
        llm_client: ScoringLlmClient,
        *,
        max_calls_per_run: int = _MAX_SCORING_CALLS_PER_RUN,
        scoring_model: str = _DEFAULT_SCORING_MODEL,
    ) -> None:
        """Bind the service to a scoring LLM port, per-run call cap, and model label.

        Args:
            llm_client: Structured per-listing scoring provider.
            max_calls_per_run: Hard ceiling on scoring calls per run (PRD: 100).
            scoring_model: Model label used for FinOps when no call reports usage
                (e.g. an empty run where every listing is skipped).
        """
        self._llm_client = llm_client
        self._max_calls_per_run = max_calls_per_run
        self._scoring_model = scoring_model

    def score_listing(self, *, cv_text: str, listing: NormalisedListing) -> ScoredListing:
        """Score one listing, retrying once on malformed output before skipping.

        Args:
            cv_text: Parsed CV plain text; raw PDF bytes must never be passed.
            listing: Normalised listing to evaluate.

        Returns:
            ScoredListing: Validated score and breakdown for the listing.

        Raises:
            ValueError: When cv_text is blank.
            ScoringSkippedError: When the provider fails twice for this listing.
        """
        attempt = self._attempt_score(
            cv_text=cv_text, listing=listing, max_attempts=_MAX_ATTEMPTS_PER_LISTING
        )
        if attempt.scored is None:
            raise ScoringSkippedError("listing skipped after retry")
        return attempt.scored

    def score_run(
        self, *, cv_text: str, listings: list[NormalisedListing]
    ) -> RunScoringResult:
        """Score listings within the per-run call budget and aggregate FinOps.

        The cap bounds total LLM calls (retries included). Listings that fail after
        their retry are skipped and counted rather than aborting the run, matching
        the PRD partial-success policy.

        Args:
            cv_text: Parsed CV plain text shared across all listings in the run.
            listings: Normalised listings fetched from Job Sources for this run.

        Returns:
            RunScoringResult: Scored listings plus aggregated token/cost FinOps.

        Raises:
            ValueError: When cv_text is blank.
        """
        normalized_cv = self._require_cv_text(cv_text)

        scored: list[ScoredListing] = []
        skipped = 0
        prompt_tokens = 0
        completion_tokens = 0
        model = self._scoring_model
        calls_remaining = self._max_calls_per_run

        for listing in listings:
            if calls_remaining <= 0:
                break
            max_attempts = min(_MAX_ATTEMPTS_PER_LISTING, calls_remaining)
            attempt = self._attempt_score(
                cv_text=normalized_cv, listing=listing, max_attempts=max_attempts
            )
            calls_remaining -= attempt.calls_used

            if attempt.scored is None:
                skipped += 1
                continue
            scored.append(attempt.scored)
            if attempt.usage is not None:
                prompt_tokens += attempt.usage.prompt_tokens
                completion_tokens += attempt.usage.completion_tokens
                model = attempt.usage.model

        finops = ScoringFinops(
            model=model,
            listings_scored=len(scored),
            listings_skipped=skipped,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_usd=estimate_gpt4o_usd(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
        )
        return RunScoringResult(scored=scored, finops=finops)

    def _attempt_score(
        self, *, cv_text: str, listing: NormalisedListing, max_attempts: int
    ) -> _ScoreAttempt:
        """Score one listing within ``max_attempts`` LLM calls.

        Args:
            cv_text: Parsed CV plain text.
            listing: Listing under evaluation.
            max_attempts: Maximum LLM calls allowed for this listing (1 or 2).

        Returns:
            _ScoreAttempt: Result with the score (or None when all attempts failed)
            and the number of LLM calls actually consumed.

        Raises:
            ValueError: When cv_text is blank.
        """
        normalized_cv = self._require_cv_text(cv_text)

        calls_used = 0
        for attempt_index in range(max_attempts):
            calls_used += 1
            try:
                output, usage = self._llm_client.score_listing(
                    cv_text=normalized_cv, listing=listing
                )
                return _ScoreAttempt(
                    scored=self._to_scored_listing(output, listing),
                    usage=usage,
                    calls_used=calls_used,
                )
            except (LlmClientError, ValueError):
                # Do not log listing identity, CV text, or prompts (CONTEXT §3).
                logger.warning("scoring attempt %d failed", attempt_index + 1)

        return _ScoreAttempt(scored=None, usage=None, calls_used=calls_used)

    @staticmethod
    def _require_cv_text(cv_text: str) -> str:
        """Validate CV text is present, returning the original (untrimmed) value."""
        if not cv_text or not cv_text.strip():
            raise ValueError("CV text is required for scoring")
        return cv_text

    @staticmethod
    def _to_scored_listing(
        output: ScoringLlmOutput, listing: NormalisedListing
    ) -> ScoredListing:
        """Validate the model score range and map output to a ScoredListing."""
        return ScoredListing(
            source=listing.source,
            title=listing.title,
            company=listing.company,
            url=listing.url,
            match_score=validate_match_score(output.match_score),
            interview_likelihood=output.interview_likelihood,
            breakdown_json=output.breakdown(),
        )
