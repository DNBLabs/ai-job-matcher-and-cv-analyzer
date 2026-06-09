"""Analysis Run worker pipeline: fetch listings → score → persist results.

Drives the full pipeline lifecycle: QUEUED → SCRAPING → SCORING → COMPLETE | FAILED.
Fetches from every registered Job Source independently; a per-source failure is
isolated so listings from the healthy source are still scored (partial success).
Source failures are persisted on ``source_failures_json`` for the results UI banner.

Logging is deliberately PII-free: no CV text, prompts, or listing identity are
ever logged (CONTEXT §3).
"""

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, JobMatchResult
from app.domain.analysis_run import AnalysisRunStatus, resolve_terminal_status
from app.domain.job_search import JobSearch
from app.domain.scoring_schema import ScoredListing
from app.job_sources.base import JobSource, JobSourceError, NormalisedListing
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)

# Per-source listing cap (CONTEXT §Job Source): bound AI cost per Analysis Run.
_MAX_LISTINGS_PER_SOURCE = 50


def _breakdown_json(listing: ScoredListing) -> dict:
    """Compose the persisted breakdown payload expected by GET /runs/{id}/results.

    The results API (Task 11) reads match_score and interview_likelihood from
    ``breakdown_json`` alongside the breakdown arrays, so persist them together.

    Args:
        listing: Scored listing whose score and breakdown arrays are persisted.

    Returns:
        dict: JSON-serializable breakdown including the score fields and arrays.
    """
    return {
        "match_score": listing.match_score,
        "interview_likelihood": listing.interview_likelihood.value,
        **listing.breakdown_json,
    }


class AnalysisRunPipeline:
    """Drive a queued Analysis Run through scraping, scoring, and persistence.

    Fetches from every registered Job Source independently; a per-source failure
    is isolated so listings from healthy sources are still scored (partial success).
    """

    def __init__(
        self,
        *,
        job_sources: list[tuple[str, JobSource]],
        scoring_service: ScoringService,
        max_listings: int = _MAX_LISTINGS_PER_SOURCE,
    ) -> None:
        """Bind the pipeline to named Job Sources, a scoring service, and a per-source cap.

        Args:
            job_sources: Ordered list of (source_name, adapter) pairs to fetch from.
            scoring_service: Per-listing scoring with retry, cap, and FinOps totals.
            max_listings: Maximum listings to request per source (PRD cap: 50).
        """
        self._job_sources = job_sources
        self._scoring_service = scoring_service
        self._max_listings = max_listings

    def run(self, analysis_run: AnalysisRun, session: Session) -> None:
        """Execute the full pipeline for one queued run, committing as it progresses.

        Drives the lifecycle QUEUED → SCRAPING → SCORING → COMPLETE | FAILED.
        A missing CV or zero listings across all sources resolves to FAILED;
        one or more scored listings resolves to COMPLETE (partial success).

        Args:
            analysis_run: Queued run loaded by the handler (status assumed QUEUED).
            session: Active database session; the pipeline owns commits within it.
        """
        analysis_run.status = AnalysisRunStatus.SCRAPING
        session.commit()
        logger.info("analysis run %s → scraping", analysis_run.id)

        cv_text = self._load_cv_text(analysis_run, session)
        if cv_text is None:
            logger.warning("analysis run %s has no usable CV text — failing", analysis_run.id)
            self._finalize(analysis_run, session, scored=[], finops={}, source_failures=[])
            return

        listings, source_failures = self._fetch_all_listings(analysis_run)

        analysis_run.status = AnalysisRunStatus.SCORING
        session.commit()
        logger.info("analysis run %s → scoring (%d listings)", analysis_run.id, len(listings))

        result = self._scoring_service.score_run(cv_text=cv_text, listings=listings)
        self._finalize(
            analysis_run,
            session,
            scored=result.scored,
            finops=result.finops.model_dump(),
            source_failures=source_failures,
        )

    def _fetch_all_listings(
        self, analysis_run: AnalysisRun
    ) -> tuple[list[NormalisedListing], list[dict]]:
        """Fetch from all registered sources, deduping by URL and collecting failures.

        Each source is tried independently; a JobSourceError from one source does
        not prevent fetching from the others. Listings with the same URL across
        sources are deduped (first-seen wins, preserving source attribution).

        Args:
            analysis_run: Run providing the persisted Job Search criteria.

        Returns:
            tuple: (merged_listings, source_failures) where source_failures is a list
                of dicts with ``source`` and ``reason`` keys for any failed sources.
        """
        job_search = JobSearch.model_validate(analysis_run.job_search_json)
        all_listings: list[NormalisedListing] = []
        seen_urls: set[str] = set()
        failures: list[dict] = []

        for source_name, source in self._job_sources:
            try:
                listings = source.fetch_listings(job_search, max_results=self._max_listings)
                for listing in listings:
                    if listing.url not in seen_urls:
                        seen_urls.add(listing.url)
                        all_listings.append(listing)
            except JobSourceError:
                logger.warning("source %s failed for run %s", source_name, analysis_run.id)
                failures.append({"source": source_name, "reason": "scrape_failed"})

        return all_listings, failures

    @staticmethod
    def _load_cv_text(analysis_run: AnalysisRun, session: Session) -> str | None:
        """Return the run's parsed CV text, or None when it is unavailable.

        The CV may have been soft-deleted (parsed text cleared) between enqueue
        and processing, so the worker must tolerate a missing or blank CV.

        Args:
            analysis_run: Run referencing the CV by ``cv_id``.
            session: Active database session.

        Returns:
            str | None: Non-blank parsed CV text, or None when missing/blank.
        """
        cv = session.get(Cv, analysis_run.cv_id)
        if cv is None or cv.parsed_text is None or not cv.parsed_text.strip():
            return None
        return cv.parsed_text

    def _finalize(
        self,
        analysis_run: AnalysisRun,
        session: Session,
        *,
        scored: list[ScoredListing],
        finops: dict,
        source_failures: list[dict],
    ) -> None:
        """Persist results and FinOps, then set the terminal status and commit.

        Args:
            analysis_run: Run being finalized.
            session: Active database session.
            scored: Scored listings to persist (deduped by source + external id).
            finops: Per-run FinOps summary to store on ``finops_json``.
            source_failures: Failed sources from ``_fetch_all_listings``.
        """
        persisted = self._persist_results(analysis_run, session, scored)
        analysis_run.finops_json = finops
        analysis_run.source_failures_json = {"failures": source_failures} if source_failures else None
        analysis_run.status = resolve_terminal_status(scored_listing_count=persisted)
        analysis_run.completed_at = datetime.now(UTC)
        session.commit()
        logger.info(
            "analysis run %s → %s (%d results)",
            analysis_run.id,
            analysis_run.status,
            persisted,
        )

    @staticmethod
    def _persist_results(
        analysis_run: AnalysisRun, session: Session, scored: list[ScoredListing]
    ) -> int:
        """Insert Job Match Result rows, deduping by (source, external id).

        The external id is the SHA-256 of the listing URL: stable, non-guessable,
        and within the column length, satisfying the per-run uniqueness constraint
        and aligning with the URL-based dedup planned for multi-source runs.

        Args:
            analysis_run: Parent run for the persisted results.
            session: Active database session (added to but not committed here).
            scored: Scored listings to persist.

        Returns:
            int: Number of distinct results added.
        """
        seen: set[tuple[str, str]] = set()
        added = 0
        for listing in scored:
            external_id = hashlib.sha256(listing.url.encode("utf-8")).hexdigest()
            key = (listing.source, external_id)
            if key in seen:
                continue
            seen.add(key)
            session.add(
                JobMatchResult(
                    analysis_run_id=analysis_run.id,
                    source=listing.source,
                    external_id=external_id,
                    title=listing.title,
                    company=listing.company,
                    url=listing.url,
                    match_score=listing.match_score,
                    interview_likelihood=listing.interview_likelihood,
                    breakdown_json=_breakdown_json(listing),
                )
            )
            added += 1
        return added
