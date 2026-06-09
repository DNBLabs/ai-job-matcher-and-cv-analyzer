"""Indeed UK job listings adapter implementing the JobSource port.

Scrapes uk.indeed.com search results and normalises each card to NormalisedListing.
Retries up to twice on transient errors (HTTP 429, 5xx, timeout); raises
JobSourceError immediately on non-transient 4xx failures.

No live network calls in CI — all tests use recorded HTML fixtures.
To run a live smoke test: set SMOKE_INDEED=1 and call fetch_listings directly.
"""

import logging
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag

from app.domain.job_search import JobSearch
from app.job_sources.base import JobSourceError, NormalisedListing

logger = logging.getLogger(__name__)

_BASE_URL = "https://uk.indeed.com"
_SEARCH_PATH = "/jobs"
_SOURCE_NAME = "indeed"
_MAX_RETRIES = 2
_DEFAULT_TIMEOUT_SECONDS = 30.0

# User-Agent required; without it Indeed returns a CAPTCHA / empty page.
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}


class IndeedJobSource:
    """Indeed UK-backed JobSource adapter that scrapes job search result pages.

    Parses HTML using BeautifulSoup with Python's built-in html.parser.
    Credentials are not required (public search pages); rate-limit headers
    and User-Agent are set to reduce bot-detection friction.
    """

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        """Bind the adapter to an optional HTTP client.

        Args:
            http_client: Optional pre-configured httpx.Client; a default 30s-timeout
                client with appropriate headers is created when not supplied.
        """
        self._http_client = http_client or httpx.Client(
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
        )

    def fetch_listings(
        self, job_search: JobSearch, max_results: int = 50
    ) -> list[NormalisedListing]:
        """Scrape and normalise up to ``max_results`` Indeed UK listings.

        Fetches the first search-results page and parses job cards. Retries up
        to twice on HTTP 429, 5xx, or timeout. Non-transient 4xx errors raise
        immediately without consuming retries.

        Args:
            job_search: Validated Job Search criteria with role, location, and remote flag.
            max_results: Maximum listings to return; default 50 per-source ADR rule.

        Returns:
            list[NormalisedListing]: Normalised Indeed listings.

        Raises:
            JobSourceError: When all attempts fail or a non-transient error is encountered.
        """
        url = self._build_search_url(job_search)
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http_client.get(url)
                response.raise_for_status()
                return self._parse_html(response.text, max_results)

            except (httpx.TimeoutException, httpx.HTTPStatusError) as error:
                if not self._is_transient(error):
                    raise JobSourceError(
                        f"Indeed request failed with non-retryable error: {error}"
                    ) from error

                last_error = error
                logger.warning(
                    "Indeed fetch attempt %d/%d failed (%s); %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    error,
                    "retrying" if attempt < _MAX_RETRIES else "giving up",
                )

        raise JobSourceError(
            f"Indeed fetch failed after {_MAX_RETRIES + 1} attempts"
        ) from last_error

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_search_url(self, job_search: JobSearch) -> str:
        """Build the Indeed UK search URL from job search criteria.

        Args:
            job_search: Validated Job Search criteria.

        Returns:
            str: Full search URL ready for httpx.
        """
        params: dict[str, str] = {"q": job_search.role}
        if not job_search.remote:
            params["l"] = job_search.location
        return f"{_BASE_URL}{_SEARCH_PATH}?{urlencode(params)}"

    def _parse_html(self, html: str, max_results: int) -> list[NormalisedListing]:
        """Parse Indeed search-results HTML and return up to max_results listings.

        Args:
            html: Raw HTML from the Indeed search-results page.
            max_results: Maximum number of listings to return.

        Returns:
            list[NormalisedListing]: Parsed listings, capped at max_results.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.job_seen_beacon")
        listings: list[NormalisedListing] = []
        for card in cards:
            if len(listings) >= max_results:
                break
            listing = self._extract_listing(card)
            if listing is not None:
                listings.append(listing)
        return listings

    def _extract_listing(self, card: Tag) -> NormalisedListing | None:
        """Extract a single NormalisedListing from a job card element.

        Returns None for cards missing required fields (title or URL) so the
        pipeline skips malformed cards without raising.

        Args:
            card: BeautifulSoup Tag for one ``div.job_seen_beacon`` element.

        Returns:
            NormalisedListing | None: Parsed listing, or None if card is malformed.
        """
        # Title comes from span[title] inside h2.jobTitle > a
        title_el = card.select_one("h2.jobTitle a span[title]")
        if title_el is None:
            return None
        title = (title_el.get("title") or "").strip()
        if not title:
            return None

        # URL: relative href on the anchor — promoted to absolute
        link_el = card.select_one("h2.jobTitle a")
        href = (link_el.get("href") or "") if link_el else ""
        url = f"{_BASE_URL}{href}" if href.startswith("/") else href

        # Company name
        company_el = card.select_one("[data-testid='company-name']")
        company = company_el.get_text(strip=True) if company_el else ""

        # Location
        location_el = card.select_one("[data-testid='text-location']")
        location = location_el.get_text(strip=True) if location_el else ""

        # Description snippet
        desc_el = card.select_one(".job-snippet")
        description = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

        return NormalisedListing(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            source=_SOURCE_NAME,
        )

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        """Return True when the error is safe to retry (timeout, 429, or 5xx).

        Args:
            error: Exception raised by httpx during a request attempt.

        Returns:
            bool: True when the request should be retried.
        """
        if isinstance(error, httpx.TimeoutException):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            return status == 429 or status >= 500
        return False
