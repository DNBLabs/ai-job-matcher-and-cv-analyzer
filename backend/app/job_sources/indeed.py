"""Indeed UK job listings adapter implementing the JobSource port.

Scrapes uk.indeed.com search results and normalises each card to NormalisedListing.
Retries up to twice on transient errors (HTTP 429, 5xx, timeout), spacing attempts
with exponential backoff + jitter so a brief throttle is ridden out; raises
JobSourceError immediately on non-transient 4xx failures.

Uses curl_cffi to impersonate Chrome at the TLS layer, bypassing Cloudflare's
JA3/JA4 fingerprinting that blocks plain httpx/requests.

No live network calls in CI — all tests use recorded HTML fixtures.
To run a live smoke test: set SMOKE_INDEED=1 and call fetch_listings directly.
"""

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag
from curl_cffi.requests import Session as CurlSession
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from curl_cffi.requests.exceptions import Timeout as CurlTimeout

from app.domain.job_search import JobSearch
from app.job_sources.base import (
    JobSourceError,
    NormalisedListing,
    backoff_delay_seconds,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://uk.indeed.com"
_SEARCH_PATH = "/jobs"
_SOURCE_NAME = "indeed"
_MAX_RETRIES = 2
_DEFAULT_TIMEOUT_SECONDS = 30.0

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
}


def _make_default_client() -> CurlSession:
    """Return a curl_cffi Session impersonating Chrome for TLS fingerprint bypass."""
    return CurlSession(
        impersonate="chrome124",
        headers=_DEFAULT_HEADERS,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
    )


class IndeedJobSource:
    """Indeed UK-backed JobSource adapter that scrapes job search result pages.

    Parses HTML using BeautifulSoup with Python's built-in html.parser.
    Uses curl_cffi with Chrome impersonation to bypass Cloudflare TLS fingerprinting.
    Credentials are not required (public search pages).
    """

    def __init__(
        self,
        *,
        http_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the adapter to an optional HTTP client.

        Args:
            http_client: Optional pre-configured client; a curl_cffi Chrome-impersonating
                session is created when not supplied. Tests may inject a mock here.
            sleep: Callable used to pause between retries; defaults to ``time.sleep``.
                Tests inject a fake to avoid real delays and to assert backoff.
        """
        self._http_client = http_client if http_client is not None else _make_default_client()
        self._sleep = sleep

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

            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                CurlTimeout,
                CurlHTTPError,
            ) as error:
                if not self._is_transient(error):
                    reason = self._failure_reason(error)
                    raise JobSourceError(
                        f"Indeed request failed ({reason})", reason=reason
                    ) from error

                last_error = error
                logger.warning(
                    "Indeed fetch attempt %d/%d failed (%s); %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    self._failure_reason(error),
                    "retrying" if attempt < _MAX_RETRIES else "giving up",
                )
                if attempt < _MAX_RETRIES:
                    self._sleep(backoff_delay_seconds(attempt))

        raise JobSourceError(
            f"Indeed fetch failed after {_MAX_RETRIES + 1} attempts",
            reason="exhausted_retries",
        ) from last_error

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_search_url(self, job_search: JobSearch) -> str:
        """Build the Indeed UK search URL from job search criteria.

        Args:
            job_search: Validated Job Search criteria.

        Returns:
            str: Full search URL ready for the HTTP client.
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
        title_el = card.select_one(".jobTitle a span[title]")
        if title_el is None:
            return None
        title = (title_el.get("title") or "").strip()
        if not title:
            return None

        link_el = card.select_one(".jobTitle a")
        href = (link_el.get("href") or "") if link_el else ""
        url = f"{_BASE_URL}{href}" if href.startswith("/") else href

        company_el = card.select_one("[data-testid='company-name']")
        company = company_el.get_text(strip=True) if company_el else ""

        location_el = card.select_one("[data-testid='text-location']")
        location = location_el.get_text(strip=True) if location_el else ""

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

        Handles both httpx exceptions (injected by tests) and curl_cffi exceptions
        (raised in production).

        Args:
            error: Exception raised by the HTTP client during a request attempt.

        Returns:
            bool: True when the request should be retried.
        """
        if isinstance(error, (httpx.TimeoutException, CurlTimeout)):
            return True
        if isinstance(error, (httpx.HTTPStatusError, CurlHTTPError)):
            status = error.response.status_code
            return status == 429 or status >= 500
        return False

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        """Return a PII/secret-free reason token for a request error.

        Error strings embed the request URL, which carries the user's role and
        location as query params — so only the exception category or HTTP status
        (never the raw error) is safe to log (CONTEXT §3).

        Args:
            error: Exception raised by the HTTP client during a request attempt.

        Returns:
            str: A short token such as ``"http_403"`` or ``"timeout"``.
        """
        if isinstance(error, (httpx.HTTPStatusError, CurlHTTPError)):
            return f"http_{error.response.status_code}"
        if isinstance(error, (httpx.TimeoutException, CurlTimeout)):
            return "timeout"
        return "request_failed"
