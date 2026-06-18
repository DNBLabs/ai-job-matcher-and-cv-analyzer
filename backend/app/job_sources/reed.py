"""Reed UK job listings adapter implementing the JobSource port.

Calls the Reed Jobseeker search API and normalises each result to NormalisedListing.
Retries up to twice on transient errors (HTTP 429, 5xx, timeout), spacing attempts
with exponential backoff + jitter so a brief throttle is ridden out; raises
JobSourceError immediately on non-transient 4xx failures.

Auth is HTTP Basic: the API key is the username and the password is empty
(per Reed API spec). No scraping, no proxy — an official REST API tolerant of
server-to-server traffic (ADR-0009, supersedes the Indeed scrape source).

Source: https://www.reed.co.uk/developers/jobseeker
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.domain.job_search import JobSearch
from app.job_sources.base import (
    JobSourceError,
    NormalisedListing,
    backoff_delay_seconds,
)

logger = logging.getLogger(__name__)

_REED_SEARCH_URL = "https://www.reed.co.uk/api/1.0/search"
_SOURCE_NAME = "reed"
# Total attempts = initial + _MAX_RETRIES
_MAX_RETRIES = 2
_DEFAULT_TIMEOUT_SECONDS = 30.0
# Reed caps resultsToTake at 100; the per-source ADR rule caps us well below that.
_REED_RESULTS_LIMIT = 100


class ReedJobSource:
    """Reed-backed JobSource adapter that fetches UK job listings via their REST API.

    The API key is resolved once at construction time and forwarded as the HTTP
    Basic auth username (empty password) on every request, per the Reed API spec.
    """

    def __init__(
        self,
        *,
        api_key: str,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the adapter to a Reed API key and an optional HTTP client.

        Args:
            api_key: Reed API key (resolved from SecretProvider in prod). Sent as the
                HTTP Basic auth username with an empty password.
            http_client: Optional pre-configured httpx.Client; a default 30s-timeout
                client is created when not supplied (allows injection in tests).
            sleep: Callable used to pause between retries; defaults to ``time.sleep``.
                Tests inject a fake to avoid real delays and to assert backoff.
        """
        self._api_key = api_key
        self._http_client = http_client or httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS)
        self._sleep = sleep

    def fetch_listings(
        self, job_search: JobSearch, max_results: int = 50
    ) -> list[NormalisedListing]:
        """Fetch and normalise up to ``max_results`` Reed listings for the search criteria.

        Sends a single search request capped at ``max_results`` results. Retries up to
        twice on HTTP 429, 5xx, or timeout. Non-transient 4xx errors (e.g. 400, 401)
        raise immediately without consuming retries.

        Args:
            job_search: Validated Job Search criteria with role, location, and remote flag.
            max_results: Maximum listings to return; capped at 50 per-source ADR rule.

        Returns:
            list[NormalisedListing]: Normalised Reed listings as returned by the API.

        Raises:
            JobSourceError: When all attempts fail or a non-transient error is encountered.
        """
        params = self._build_params(job_search, max_results)
        auth = (self._api_key, "")
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._http_client.get(_REED_SEARCH_URL, params=params, auth=auth)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                raw_results: list[dict[str, Any]] = data.get("results", [])
                return [self._normalise(raw) for raw in raw_results[:max_results]]

            except (httpx.TimeoutException, httpx.HTTPStatusError) as error:
                if not self._is_transient(error):
                    reason = self._failure_reason(error)
                    raise JobSourceError(
                        f"Reed request failed ({reason})", reason=reason
                    ) from error

                last_error = error
                logger.warning(
                    "Reed fetch attempt %d/%d failed (%s); %s",
                    attempt + 1,
                    _MAX_RETRIES + 1,
                    self._failure_reason(error),
                    "retrying" if attempt < _MAX_RETRIES else "giving up",
                )
                if attempt < _MAX_RETRIES:
                    self._sleep(backoff_delay_seconds(attempt))

        raise JobSourceError(
            f"Reed fetch failed after {_MAX_RETRIES + 1} attempts",
            reason="exhausted_retries",
        ) from last_error

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_params(self, job_search: JobSearch, max_results: int) -> dict[str, Any]:
        """Build the Reed query-parameter dict from job search criteria.

        For remote searches, ``locationName`` is omitted so Reed searches all of the UK.

        Args:
            job_search: Validated Job Search criteria.
            max_results: Capped number of results to request.

        Returns:
            dict[str, Any]: URL parameters ready for httpx.
        """
        params: dict[str, Any] = {
            "keywords": job_search.role,
            "resultsToTake": min(max_results, _REED_RESULTS_LIMIT),
        }
        if not job_search.remote:
            params["locationName"] = job_search.location
        return params

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> NormalisedListing:
        """Map a single Reed API result dict to the canonical NormalisedListing shape.

        Missing string fields are replaced with empty strings so the worker pipeline
        always receives a complete, typed object.

        Args:
            raw: One element from the Reed ``results`` array.

        Returns:
            NormalisedListing: Fully populated listing ready for scoring.
        """
        return NormalisedListing(
            title=raw.get("jobTitle") or "",
            company=raw.get("employerName") or "",
            location=raw.get("locationName") or "",
            url=raw.get("jobUrl") or "",
            description=raw.get("jobDescription") or "",
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

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        """Return a PII/secret-free reason token for a request error.

        httpx error strings embed the request URL, which carries the user's role and
        location as query params, and a 401 may echo auth context — so only the
        exception category or HTTP status (never the raw error) is safe to log
        (CONTEXT §3 PII/secret-free logging).

        Args:
            error: Exception raised by httpx during a request attempt.

        Returns:
            str: A short token such as ``"http_401"`` or ``"timeout"``.
        """
        if isinstance(error, httpx.HTTPStatusError):
            return f"http_{error.response.status_code}"
        if isinstance(error, httpx.TimeoutException):
            return "timeout"
        return "request_failed"
