"""Tests for IndeedJobSource HTML parsing, retry logic, and URL construction.

All tests use fixture HTML or MagicMock for httpx.Client — no live network calls.
Fixture: tests/fixtures/indeed_search.html (3 job cards).
"""

import pathlib
from unittest.mock import MagicMock

import httpx
import pytest

from app.domain.job_search import JobSearch
from app.job_sources.base import JobSourceError, NormalisedListing
from app.job_sources.indeed import IndeedJobSource

_FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "indeed_search.html"
_BASE_URL = "https://uk.indeed.com"


def _load_fixture() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def _success_mock(html: str) -> MagicMock:
    """Return a mock httpx.Client whose .get() returns the given HTML."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.text = html

    client = MagicMock()
    client.get.return_value = response
    return client


def _error_response_mock(status_code: int) -> httpx.HTTPStatusError:
    error_response = MagicMock()
    error_response.status_code = status_code
    return httpx.HTTPStatusError(
        str(status_code), request=MagicMock(), response=error_response
    )


def _london_search() -> JobSearch:
    return JobSearch(role="Python Developer", location="London", remote=False)


def _remote_search() -> JobSearch:
    return JobSearch(role="Python Developer", location="Remote", remote=True)


# ---------------------------------------------------------------------------
# Field extraction from fixture HTML
# ---------------------------------------------------------------------------


def test_parse_extracts_title_from_fixture() -> None:
    """IndeedJobSource extracts the job title from the span[title] attribute."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert listings[0].title == "Python Developer"


def test_parse_extracts_company_from_fixture() -> None:
    """IndeedJobSource extracts the company name from [data-testid='company-name']."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert listings[0].company == "Tech Solutions Ltd"


def test_parse_extracts_location_from_fixture() -> None:
    """IndeedJobSource extracts the location from [data-testid='text-location']."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert listings[0].location == "London"


def test_parse_extracts_full_url_from_fixture() -> None:
    """IndeedJobSource constructs a full uk.indeed.com URL from the relative href."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert listings[0].url.startswith(_BASE_URL)
    assert "aaa111bbb222ccc3" in listings[0].url


def test_parse_extracts_description_from_fixture() -> None:
    """IndeedJobSource extracts description text from .job-snippet."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert "Python" in listings[0].description


def test_source_field_is_indeed() -> None:
    """Every NormalisedListing returned by IndeedJobSource has source='indeed'."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert all(l.source == "indeed" for l in listings)


def test_fetch_returns_normalised_listing_instances() -> None:
    """Each item returned is a NormalisedListing Pydantic model instance."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert all(isinstance(l, NormalisedListing) for l in listings)


def test_parse_extracts_all_three_listings_from_fixture() -> None:
    """IndeedJobSource returns all 3 job cards present in the fixture."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert listings[1].company == "Global Finance Corp"
    assert listings[2].company == "StartupHub Ltd"


# ---------------------------------------------------------------------------
# max_results cap
# ---------------------------------------------------------------------------


def test_fetch_respects_max_results_cap() -> None:
    """fetch_listings caps the returned list to max_results."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search(), max_results=2)

    assert len(listings) == 2


def test_fetch_returns_all_when_fewer_than_max() -> None:
    """fetch_listings returns all results when the page has fewer than max_results."""
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(_load_fixture())

    listings = indeed.fetch_listings(_london_search(), max_results=50)

    assert len(listings) == 3


def test_fetch_returns_empty_list_when_no_cards() -> None:
    """fetch_listings returns an empty list when the HTML has no job cards."""
    empty_html = "<html><body><div id='mosaic-provider-jobcards'></div></body></html>"
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(empty_html)

    listings = indeed.fetch_listings(_london_search())

    assert listings == []


# ---------------------------------------------------------------------------
# Malformed cards
# ---------------------------------------------------------------------------


def test_parse_skips_card_with_no_title_element() -> None:
    """A job card missing the title element is silently skipped."""
    html_no_title = """
    <html><body>
    <div class="job_seen_beacon">
      <span data-testid="company-name">NoTitle Corp</span>
      <div data-testid="text-location">London</div>
      <div class="job-snippet">Some description.</div>
    </div>
    </body></html>
    """
    indeed = IndeedJobSource()
    indeed._http_client = _success_mock(html_no_title)

    listings = indeed.fetch_listings(_london_search())

    assert listings == []


# ---------------------------------------------------------------------------
# Query parameter construction
# ---------------------------------------------------------------------------


def test_fetch_sends_role_in_query_params() -> None:
    """The job_search.role is passed as the 'q' query parameter."""
    mock_client = _success_mock(_load_fixture())
    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    indeed.fetch_listings(JobSearch(role="Data Scientist", location="London", remote=False))

    call_url = mock_client.get.call_args[0][0]
    assert "q=Data+Scientist" in call_url or "q=Data%20Scientist" in call_url


def test_fetch_sends_location_for_city_search() -> None:
    """A city-scoped search includes the 'l' location query parameter."""
    mock_client = _success_mock(_load_fixture())
    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    indeed.fetch_listings(JobSearch(role="Engineer", location="Manchester", remote=False))

    call_url = mock_client.get.call_args[0][0]
    assert "l=Manchester" in call_url


def test_fetch_omits_location_for_remote_search() -> None:
    """A remote search omits the 'l' location query parameter."""
    mock_client = _success_mock(_load_fixture())
    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    indeed.fetch_listings(_remote_search())

    call_url = mock_client.get.call_args[0][0]
    assert "l=" not in call_url


# ---------------------------------------------------------------------------
# Retry logic — timeout, 5xx
# ---------------------------------------------------------------------------


def test_fetch_retries_on_timeout_then_succeeds() -> None:
    """A timeout on the first attempt causes one retry; success on second attempt."""
    html = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.text = html

    mock_client = MagicMock()
    mock_client.get.side_effect = [
        httpx.TimeoutException("timed out"),
        success_response,
    ]

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    listings = indeed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_retries_on_503_then_succeeds() -> None:
    """A 503 response causes one retry; success on second attempt returns listings."""
    html = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.text = html

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(503)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    listings = indeed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_raises_job_source_error_after_all_retries_exhausted() -> None:
    """JobSourceError raised when all 3 attempts (initial + 2 retries) fail."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    with pytest.raises(JobSourceError):
        indeed.fetch_listings(_london_search())

    assert mock_client.get.call_count == 3  # initial + 2 retries


def test_fetch_does_not_retry_on_400() -> None:
    """Non-transient 4xx errors (except 429) are raised immediately without retry."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(400)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    with pytest.raises(JobSourceError):
        indeed.fetch_listings(_london_search())

    assert mock_client.get.call_count == 1


def test_fetch_retries_on_429_then_succeeds() -> None:
    """A 429 response causes one retry; success on second attempt returns listings."""
    html = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.text = html

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(429)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    listings = indeed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


# ---------------------------------------------------------------------------
# Failure reason (PII/secret-free) — logged by the worker pipeline
# ---------------------------------------------------------------------------


def test_fetch_non_transient_error_sets_http_status_reason() -> None:
    """A non-transient 403 (Cloudflare block) tags the error with reason='http_403'."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(403)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        indeed.fetch_listings(_london_search())

    assert exc_info.value.reason == "http_403"


def test_fetch_exhausted_retries_sets_reason() -> None:
    """Exhausting all retries tags the JobSourceError with reason='exhausted_retries'."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        indeed.fetch_listings(_london_search())

    assert exc_info.value.reason == "exhausted_retries"


def test_fetch_error_never_leaks_search_terms() -> None:
    """The raised error must not echo the user's search query (PII-free logging).

    httpx's HTTPStatusError str embeds the request URL, which carries the role
    and location as query params. The pipeline logs this error's reason, so
    neither the message nor the reason may echo the search terms (CONTEXT §3).
    """
    leaky = httpx.HTTPStatusError(
        "Client error '403 Forbidden' for url "
        "'https://uk.indeed.com/jobs?q=Quantum+Cryptographer+Xyz&l=London'",
        request=MagicMock(),
        response=MagicMock(status_code=403),
    )
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = leaky

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    indeed = IndeedJobSource()
    indeed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        indeed.fetch_listings(
            JobSearch(role="Quantum Cryptographer Xyz", location="London", remote=False)
        )

    blob = f"{exc_info.value}|{exc_info.value.reason}"
    assert "Quantum Cryptographer Xyz" not in blob
