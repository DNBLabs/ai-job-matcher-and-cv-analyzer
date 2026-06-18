"""Job Source port and NormalisedListing schema for pluggable job board adapters.

Defines the protocol that all job source adapters (Adzuna, Indeed, …) must satisfy,
and the canonical NormalisedListing shape that the worker pipeline consumes.
"""

import random
from typing import Protocol

from pydantic import BaseModel

from app.domain.job_search import JobSearch

# Retry backoff (shared by all adapters). A brief 503/429 throttle from a source
# is ridden out by spacing retries with exponential backoff + full jitter rather
# than firing all attempts in a few hundred milliseconds (issue #58).
# Full jitter — random.uniform(0, capped exponential) — spreads retries and avoids
# synchronised "thundering herd" pile-ups.
# Source: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 8.0


def backoff_delay_seconds(
    attempt: int,
    *,
    base: float = _BACKOFF_BASE_SECONDS,
    cap: float = _BACKOFF_MAX_SECONDS,
) -> float:
    """Return the seconds to wait before the retry following a failed ``attempt``.

    Exponential backoff with full jitter: a uniformly random value in
    ``[0, min(cap, base * 2**attempt)]``. The exponential ceiling rises per
    attempt (until capped); the jitter desynchronises concurrent retriers.

    Args:
        attempt: Zero-based index of the attempt that just failed (0 = first).
        base: Base delay in seconds for the first retry.
        cap: Maximum ceiling in seconds the exponential term is clamped to.

    Returns:
        float: Backoff delay in seconds, ``0.0`` ≤ delay ≤ ``min(cap, base * 2**attempt)``.
    """
    ceiling = min(cap, base * (2**attempt))
    return random.uniform(0, ceiling)


class JobSourceError(Exception):
    """Raised when a Job Source cannot return listings after exhausting retries.

    Carries an optional ``reason``: a short, PII/secret-free token (e.g.
    ``"http_401"``, ``"exhausted_retries"``) that the worker pipeline logs to
    explain *why* a source failed. The reason must never embed credentials,
    request URLs, or user search terms (CONTEXT §3 PII-free logging).
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        """Bind a human-readable message and an optional safe-to-log reason token.

        Args:
            message: Human-readable failure description (not logged by the pipeline).
            reason: Short PII/secret-free token logged by the worker; ``None`` when
                the source did not classify the failure.
        """
        super().__init__(message)
        self.reason = reason


class NormalisedListing(BaseModel):
    """A single job listing normalised from any Job Source into a canonical shape.

    All fields are required; adapters must provide fallback values for optional
    source-side fields (e.g. missing company name) rather than omitting them.
    """

    title: str
    company: str
    location: str
    url: str
    description: str
    source: str  # "adzuna" or "indeed"


class JobSource(Protocol):
    """Port contract for pluggable job board adapters.

    Each adapter fetches listings from a specific board and normalises them to
    NormalisedListing so the worker pipeline is decoupled from board-specific schemas.
    """

    def fetch_listings(
        self, job_search: JobSearch, max_results: int = 50
    ) -> list[NormalisedListing]:
        """Fetch and normalise job listings matching the given search criteria.

        Args:
            job_search: Validated Job Search criteria (role, location, remote flag).
            max_results: Maximum number of listings to return; default 50 per ADR cap.

        Returns:
            list[NormalisedListing]: Normalised listings, at most ``max_results`` items.

        Raises:
            JobSourceError: When the source fails after exhausting all retries.
        """
        ...
