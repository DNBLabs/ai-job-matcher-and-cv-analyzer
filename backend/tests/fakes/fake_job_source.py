"""In-memory JobSource fake for deterministic worker pipeline tests."""

from app.domain.job_search import JobSearch
from app.job_sources.base import JobSourceError, NormalisedListing


class FakeJobSource:
    """Deterministic JobSource returning canned listings or raising on demand.

    Records the max_results passed by the pipeline so the per-source cap can be
    asserted, and can be configured to raise JobSourceError to exercise the
    failure-to-Failed path.
    """

    def __init__(
        self,
        *,
        listings: list[NormalisedListing] | None = None,
        error: JobSourceError | None = None,
    ) -> None:
        """Configure the listings to return or an error to raise.

        Args:
            listings: Listings returned by fetch_listings (defaults to empty).
            error: When set, fetch_listings raises this instead of returning listings.
        """
        self._listings = listings or []
        self._error = error
        self.fetch_calls: list[int] = []

    def fetch_listings(
        self, job_search: JobSearch, max_results: int = 50
    ) -> list[NormalisedListing]:
        """Return the canned listings (capped) or raise the configured error.

        Args:
            job_search: Validated Job Search criteria (unused; recorded for parity).
            max_results: Per-source cap recorded for assertions.

        Returns:
            list[NormalisedListing]: Canned listings truncated to max_results.

        Raises:
            JobSourceError: When configured with an error.
        """
        _ = job_search
        self.fetch_calls.append(max_results)
        if self._error is not None:
            raise self._error
        return list(self._listings[:max_results])


def make_listing(
    *,
    title: str = "Backend Engineer",
    company: str = "Acme Ltd",
    url: str = "https://example.com/jobs/1",
    source: str = "adzuna",
) -> NormalisedListing:
    """Build a NormalisedListing fixture for pipeline tests."""
    return NormalisedListing(
        title=title,
        company=company,
        location="London",
        url=url,
        description="Python, FastAPI, PostgreSQL.",
        source=source,
    )
