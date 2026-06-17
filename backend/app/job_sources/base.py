"""Job Source port and NormalisedListing schema for pluggable job board adapters.

Defines the protocol that all job source adapters (Adzuna, Indeed, …) must satisfy,
and the canonical NormalisedListing shape that the worker pipeline consumes.
"""

from typing import Protocol

from pydantic import BaseModel

from app.domain.job_search import JobSearch


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
