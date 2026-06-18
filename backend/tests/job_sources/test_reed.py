"""Tests for ReedJobSource field mapping, auth, retry logic, and registry resolution.

All tests use MagicMock to replace the injected httpx.Client — no live network calls.
The recorded fixture (reed_response.json) stands in for a real Reed search response.
"""

import json
import pathlib
from unittest.mock import MagicMock

import httpx
import pytest

from app.domain.job_search import JobSearch
from app.job_sources.base import JobSourceError, NormalisedListing
from app.job_sources.reed import _MAX_RETRIES, ReedJobSource
from app.job_sources.registry import JobSourceNotFoundError, JobSourceRegistry

_FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "reed_response.json"


def _load_fixture() -> dict:
    """Load the recorded Reed API response fixture."""
    return json.loads(_FIXTURE_PATH.read_text())


def _success_mock(fixture: dict) -> MagicMock:
    """Return a mock httpx.Client whose .get() succeeds with the given fixture data."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = fixture

    client = MagicMock()
    client.get.return_value = response
    return client


def _error_response_mock(status_code: int) -> httpx.HTTPStatusError:
    """Return an httpx.HTTPStatusError for the given status code."""
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
# NormalisedListing field mapping
# ---------------------------------------------------------------------------


def test_fetch_listings_maps_title_and_company() -> None:
    """ReedJobSource maps jobTitle->title and employerName->company."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())

    listings = reed.fetch_listings(_london_search())

    assert listings[0].title == "Senior Python Developer"
    assert listings[0].company == "TechCorp Ltd"


def test_fetch_listings_maps_location_url_description() -> None:
    """ReedJobSource maps locationName->location, jobUrl->url, jobDescription->description."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())

    listings = reed.fetch_listings(_london_search())

    assert listings[0].location == "London"
    assert listings[0].url == "https://www.reed.co.uk/jobs/senior-python-developer/54321001"
    assert "FastAPI" in listings[0].description


def test_fetch_listings_sets_source_to_reed() -> None:
    """Every NormalisedListing returned by ReedJobSource has source='reed'."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())

    listings = reed.fetch_listings(_london_search())

    assert all(l.source == "reed" for l in listings)


def test_fetch_listings_returns_normalised_listing_instances() -> None:
    """Each item returned is a NormalisedListing Pydantic model instance."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())

    listings = reed.fetch_listings(_london_search())

    assert all(isinstance(l, NormalisedListing) for l in listings)


def test_fetch_listings_tolerates_missing_optional_fields() -> None:
    """A result missing string fields normalises to empty strings, not None."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock({"results": [{"jobId": 1}], "totalResults": 1})

    listings = reed.fetch_listings(_london_search())

    assert listings[0].title == ""
    assert listings[0].company == ""
    assert listings[0].location == ""
    assert listings[0].url == ""
    assert listings[0].description == ""


# ---------------------------------------------------------------------------
# max_results cap
# ---------------------------------------------------------------------------


def test_fetch_listings_respects_max_results_cap() -> None:
    """fetch_listings caps the returned list to max_results even if the fixture has more."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())

    listings = reed.fetch_listings(_london_search(), max_results=2)

    assert len(listings) == 2


def test_fetch_listings_returns_all_when_results_fewer_than_max() -> None:
    """fetch_listings returns all results when the API returns fewer than max_results."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock(_load_fixture())  # 3 results

    listings = reed.fetch_listings(_london_search(), max_results=50)

    assert len(listings) == 3


def test_fetch_listings_returns_empty_list_when_no_results() -> None:
    """fetch_listings returns an empty list when the API returns zero listings."""
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = _success_mock({"results": [], "totalResults": 0})

    listings = reed.fetch_listings(_london_search())

    assert listings == []


# ---------------------------------------------------------------------------
# Authentication & query parameter construction
# ---------------------------------------------------------------------------


def test_fetch_listings_sends_api_key_as_basic_auth_username() -> None:
    """The Reed API key is sent as the HTTP Basic auth username with an empty password."""
    mock_client = _success_mock(_load_fixture())
    reed = ReedJobSource(api_key="my_secret_key")
    reed._http_client = mock_client

    reed.fetch_listings(_london_search())

    assert mock_client.get.call_args.kwargs["auth"] == ("my_secret_key", "")


def test_fetch_listings_sends_role_as_keywords_param() -> None:
    """The job_search.role value is sent as the Reed 'keywords' query parameter."""
    mock_client = _success_mock(_load_fixture())
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    reed.fetch_listings(JobSearch(role="Data Scientist", location="London", remote=False))

    params = mock_client.get.call_args.kwargs["params"]
    assert params["keywords"] == "Data Scientist"


def test_fetch_listings_sends_location_name_for_city_search() -> None:
    """A city-scoped search sends job_search.location as the Reed 'locationName' parameter."""
    mock_client = _success_mock(_load_fixture())
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    reed.fetch_listings(JobSearch(role="Engineer", location="Manchester", remote=False))

    params = mock_client.get.call_args.kwargs["params"]
    assert params["locationName"] == "Manchester"


def test_fetch_listings_omits_location_name_for_remote_search() -> None:
    """A remote search omits 'locationName' so Reed searches all of the UK."""
    mock_client = _success_mock(_load_fixture())
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    reed.fetch_listings(_remote_search())

    params = mock_client.get.call_args.kwargs["params"]
    assert "locationName" not in params


def test_fetch_listings_sends_results_to_take_capped() -> None:
    """resultsToTake is sent and never exceeds the requested max_results."""
    mock_client = _success_mock(_load_fixture())
    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    reed.fetch_listings(_london_search(), max_results=50)

    params = mock_client.get.call_args.kwargs["params"]
    assert params["resultsToTake"] == 50


# ---------------------------------------------------------------------------
# Retry logic — 429, 5xx, timeout
# ---------------------------------------------------------------------------


def test_fetch_listings_retries_once_on_429_then_succeeds() -> None:
    """A single 429 response causes one retry; success on second attempt returns listings."""
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = _load_fixture()

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(429)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    listings = reed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_retries_on_503_then_succeeds() -> None:
    """A 503 response causes one retry; success on second attempt returns listings."""
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = _load_fixture()

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(503)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    listings = reed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_retries_on_timeout_then_succeeds() -> None:
    """A timeout on the first attempt causes one retry; success on second attempt is returned."""
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = _load_fixture()

    mock_client = MagicMock()
    mock_client.get.side_effect = [
        httpx.TimeoutException("timed out"),
        success_response,
    ]

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    listings = reed.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_raises_job_source_error_after_all_retries_exhausted() -> None:
    """JobSourceError is raised when all 3 attempts (initial + 2 retries) fail."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError):
        reed.fetch_listings(_london_search())

    assert mock_client.get.call_count == 3  # initial + 2 retries


def test_fetch_listings_does_not_retry_on_400_bad_request() -> None:
    """Non-transient 4xx errors (except 429) are raised immediately without retry."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(400)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError):
        reed.fetch_listings(_london_search())

    assert mock_client.get.call_count == 1  # no retry


def test_fetch_listings_raises_immediately_on_401_unauthorized() -> None:
    """A 401 response is raised immediately without consuming retries."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(401)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError):
        reed.fetch_listings(_london_search())

    assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# Backoff between retries (issue #58 — zero-delay retries exhausted instantly)
# ---------------------------------------------------------------------------


def test_fetch_listings_sleeps_with_backoff_between_transient_retries() -> None:
    """Each transient retry is preceded by a backoff sleep (not a zero-delay retry)."""
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = _load_fixture()

    first = MagicMock()
    first.raise_for_status.side_effect = _error_response_mock(503)
    second = MagicMock()
    second.raise_for_status.side_effect = _error_response_mock(503)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first, second, success_response]

    delays: list[float] = []
    reed = ReedJobSource(api_key="test_key", sleep=delays.append)
    reed._http_client = mock_client

    reed.fetch_listings(_london_search())

    # Two transient failures before success -> two backoff sleeps.
    assert len(delays) == 2
    assert all(d >= 0.0 for d in delays)


def test_fetch_listings_does_not_sleep_after_final_failed_attempt() -> None:
    """No backoff sleep follows the last attempt when retries are exhausted."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    delays: list[float] = []
    reed = ReedJobSource(api_key="test_key", sleep=delays.append)
    reed._http_client = mock_client

    with pytest.raises(JobSourceError):
        reed.fetch_listings(_london_search())

    # 3 attempts -> sleep only between them (2 sleeps), never after the last.
    assert len(delays) == _MAX_RETRIES


def test_fetch_listings_does_not_sleep_on_non_transient_error() -> None:
    """A non-transient 4xx raises immediately with no backoff sleep."""
    first = MagicMock()
    first.raise_for_status.side_effect = _error_response_mock(400)

    mock_client = MagicMock()
    mock_client.get.return_value = first

    delays: list[float] = []
    reed = ReedJobSource(api_key="test_key", sleep=delays.append)
    reed._http_client = mock_client

    with pytest.raises(JobSourceError):
        reed.fetch_listings(_london_search())

    assert delays == []


# ---------------------------------------------------------------------------
# Failure reason (PII/secret-free) — logged by the worker pipeline
# ---------------------------------------------------------------------------


def test_fetch_listings_non_transient_error_sets_http_status_reason() -> None:
    """A non-transient 401 tags the JobSourceError with reason='http_401'."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(401)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        reed.fetch_listings(_london_search())

    assert exc_info.value.reason == "http_401"


def test_fetch_listings_exhausted_retries_sets_reason() -> None:
    """Exhausting all retries tags the JobSourceError with reason='exhausted_retries'."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    reed = ReedJobSource(api_key="test_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        reed.fetch_listings(_london_search())

    assert exc_info.value.reason == "exhausted_retries"


def test_fetch_listings_error_never_leaks_api_key_or_search_terms() -> None:
    """The raised error (message + reason) must not contain the API key or search terms.

    The pipeline logs this error's reason at WARNING; httpx's HTTPStatusError str
    embeds the full request URL, which carries the user's role/location as query
    params, and the API key rides in the Basic-auth header. Neither the message nor
    the reason may echo any of them (CONTEXT §3 PII/secret-free logging).
    """
    leaky = httpx.HTTPStatusError(
        "Client error '401 Unauthorized' for url "
        "'https://www.reed.co.uk/api/1.0/search"
        "?keywords=Quantum+Engineer&locationName=Bristol' with key my_secret_key",
        request=MagicMock(),
        response=MagicMock(status_code=401),
    )
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = leaky

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    reed = ReedJobSource(api_key="my_secret_key")
    reed._http_client = mock_client

    with pytest.raises(JobSourceError) as exc_info:
        reed.fetch_listings(JobSearch(role="Quantum Engineer", location="Bristol", remote=False))

    blob = f"{exc_info.value}|{exc_info.value.reason}"
    assert "my_secret_key" not in blob
    assert "Quantum Engineer" not in blob
    assert "Bristol" not in blob


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_registered_reed_source_by_name() -> None:
    """JobSourceRegistry.get returns the Reed source registered under 'reed'."""
    registry = JobSourceRegistry()
    source = ReedJobSource(api_key="key")
    registry.register("reed", source)

    resolved = registry.get("reed")

    assert resolved is source


def test_registry_raises_on_unknown_source_name() -> None:
    """JobSourceRegistry.get raises JobSourceNotFoundError for unregistered names."""
    registry = JobSourceRegistry()

    with pytest.raises(JobSourceNotFoundError):
        registry.get("indeed")
