"""Tests for AdzunaJobSource field mapping, retry logic, and registry resolution.

All tests use MagicMock to replace the injected httpx.Client — no live network calls.
"""

import json
import pathlib
from unittest.mock import MagicMock

import httpx
import pytest

from app.domain.job_search import JobSearch
from app.job_sources.adzuna import AdzunaJobSource
from app.job_sources.base import JobSourceError, NormalisedListing
from app.job_sources.registry import JobSourceNotFoundError, JobSourceRegistry

_FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "adzuna_response.json"


def _load_fixture() -> dict:
    """Load the recorded Adzuna API response fixture."""
    return json.loads(_FIXTURE_PATH.read_text())


def _success_mock(fixture: dict) -> MagicMock:
    """Return a mock httpx.Client whose .get() succeeds with the given fixture data."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = fixture

    client = MagicMock()
    client.get.return_value = response
    return client


def _error_response_mock(status_code: int) -> MagicMock:
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
    """AdzunaJobSource maps Adzuna title and company.display_name correctly."""
    fixture = _load_fixture()
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search())

    assert listings[0].title == "Senior Python Developer"
    assert listings[0].company == "TechCorp Ltd"


def test_fetch_listings_maps_location_url_description() -> None:
    """AdzunaJobSource maps location, redirect_url, and description correctly."""
    fixture = _load_fixture()
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search())

    assert listings[0].location == "London, Greater London"
    assert listings[0].url == "https://www.adzuna.co.uk/jobs/details/4521001"
    assert "FastAPI" in listings[0].description


def test_fetch_listings_sets_source_to_adzuna() -> None:
    """Every NormalisedListing returned by AdzunaJobSource has source='adzuna'."""
    fixture = _load_fixture()
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search())

    assert all(l.source == "adzuna" for l in listings)


def test_fetch_listings_returns_normalised_listing_instances() -> None:
    """Each item returned is a NormalisedListing Pydantic model instance."""
    fixture = _load_fixture()
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search())

    assert all(isinstance(l, NormalisedListing) for l in listings)


# ---------------------------------------------------------------------------
# max_results cap
# ---------------------------------------------------------------------------


def test_fetch_listings_respects_max_results_cap() -> None:
    """fetch_listings caps the returned list to max_results even if the fixture has more."""
    fixture = _load_fixture()
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search(), max_results=2)

    assert len(listings) == 2


def test_fetch_listings_returns_all_when_results_fewer_than_max() -> None:
    """fetch_listings returns all results when the API returns fewer than max_results."""
    fixture = _load_fixture()  # 3 results
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock(fixture)

    listings = adzuna.fetch_listings(_london_search(), max_results=50)

    assert len(listings) == 3


def test_fetch_listings_returns_empty_list_when_no_results() -> None:
    """fetch_listings returns an empty list when the API returns zero listings."""
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = _success_mock({"results": []})

    listings = adzuna.fetch_listings(_london_search())

    assert listings == []


# ---------------------------------------------------------------------------
# Query parameter construction
# ---------------------------------------------------------------------------


def test_fetch_listings_sends_app_credentials_in_params() -> None:
    """Adzuna app_id and app_key are forwarded as query parameters."""
    fixture = _load_fixture()
    mock_client = _success_mock(fixture)
    adzuna = AdzunaJobSource(app_id="my_id", app_key="my_key")
    adzuna._http_client = mock_client

    adzuna.fetch_listings(_london_search())

    params = mock_client.get.call_args.kwargs["params"]
    assert params["app_id"] == "my_id"
    assert params["app_key"] == "my_key"


def test_fetch_listings_sends_role_as_what_param() -> None:
    """The job_search.role value is sent as the Adzuna 'what' query parameter."""
    fixture = _load_fixture()
    mock_client = _success_mock(fixture)
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    adzuna.fetch_listings(JobSearch(role="Data Scientist", location="London", remote=False))

    params = mock_client.get.call_args.kwargs["params"]
    assert params["what"] == "Data Scientist"


def test_fetch_listings_sends_location_as_where_param_for_city_search() -> None:
    """A city-scoped search sends job_search.location as the Adzuna 'where' parameter."""
    fixture = _load_fixture()
    mock_client = _success_mock(fixture)
    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    adzuna.fetch_listings(JobSearch(role="Engineer", location="Manchester", remote=False))

    params = mock_client.get.call_args.kwargs["params"]
    assert params["where"] == "Manchester"


# ---------------------------------------------------------------------------
# Retry logic — 429, 5xx, timeout
# ---------------------------------------------------------------------------


def test_fetch_listings_retries_once_on_429_then_succeeds() -> None:
    """A single 429 response causes one retry; success on second attempt returns listings."""
    fixture = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = fixture

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(429)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    listings = adzuna.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_retries_on_503_then_succeeds() -> None:
    """A 503 response causes one retry; success on second attempt returns listings."""
    fixture = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = fixture

    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(503)

    mock_client = MagicMock()
    mock_client.get.side_effect = [first_response, success_response]

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    listings = adzuna.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_retries_on_timeout_then_succeeds() -> None:
    """A timeout on the first attempt causes one retry; success on second attempt is returned."""
    fixture = _load_fixture()
    success_response = MagicMock()
    success_response.raise_for_status.return_value = None
    success_response.json.return_value = fixture

    mock_client = MagicMock()
    mock_client.get.side_effect = [
        httpx.TimeoutException("timed out"),
        success_response,
    ]

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    listings = adzuna.fetch_listings(_london_search())

    assert len(listings) == 3
    assert mock_client.get.call_count == 2


def test_fetch_listings_raises_job_source_error_after_all_retries_exhausted() -> None:
    """JobSourceError is raised when all 3 attempts (initial + 2 retries) fail."""
    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    with pytest.raises(JobSourceError):
        adzuna.fetch_listings(_london_search())

    assert mock_client.get.call_count == 3  # initial + 2 retries


def test_fetch_listings_does_not_retry_on_400_bad_request() -> None:
    """Non-transient 4xx errors (except 429) are raised immediately without retry."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(400)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    with pytest.raises(JobSourceError):
        adzuna.fetch_listings(_london_search())

    assert mock_client.get.call_count == 1  # no retry


def test_fetch_listings_raises_immediately_on_401_unauthorized() -> None:
    """A 401 response is raised immediately without consuming retries."""
    first_response = MagicMock()
    first_response.raise_for_status.side_effect = _error_response_mock(401)

    mock_client = MagicMock()
    mock_client.get.return_value = first_response

    adzuna = AdzunaJobSource(app_id="test_id", app_key="test_key")
    adzuna._http_client = mock_client

    with pytest.raises(JobSourceError):
        adzuna.fetch_listings(_london_search())

    assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_resolves_registered_source_by_name() -> None:
    """JobSourceRegistry.get returns the source registered under the given name."""
    registry = JobSourceRegistry()
    source = AdzunaJobSource(app_id="id", app_key="key")
    registry.register("adzuna", source)

    resolved = registry.get("adzuna")

    assert resolved is source


def test_registry_raises_on_unknown_source_name() -> None:
    """JobSourceRegistry.get raises JobSourceNotFoundError for unregistered names."""
    registry = JobSourceRegistry()

    with pytest.raises(JobSourceNotFoundError):
        registry.get("indeed")


def test_registry_all_sources_returns_registered_values() -> None:
    """JobSourceRegistry.all_sources returns every registered source in insertion order."""
    registry = JobSourceRegistry()
    adzuna = AdzunaJobSource(app_id="id", app_key="key")
    registry.register("adzuna", adzuna)

    sources = registry.all_sources()

    assert sources == [adzuna]
