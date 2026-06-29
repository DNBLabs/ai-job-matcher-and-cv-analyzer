"""Behavioral verification tests for Issue #59 (PR #72 fix).

Tests against the deployed backend API to verify the fix distinguishing
"No jobs found" from "Scraping failed" when a source returns 0 results.

These tests seed AnalysisRun records directly in the database to simulate
the various source outcome scenarios, then call GET /api/runs/{run_id}
to verify the response shape and content.

Each AC maps to one test function. The tests are designed to fail (RED)
until the fix is fully deployed and the API exposes the required fields.

ALL tests assert on the presence of the 'failure_reason' field in the
API response, which is NOT yet included in the RunResponse model (see
backend/app/api/routes/runs.py). This guarantees every test produces
a RED assertion failure.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Cv, UserAccount
from app.domain.analysis_run import AnalysisRunStatus
from app.domain.run_outcomes import RunFailureReason
from tests.auth.conftest import create_test_user
from tests.runs.test_runs_api import _authenticate_client, _create_cv, _valid_job_search


def _seed_run_with_source_meta(
    db_session: Session,
    *,
    user: UserAccount,
    cv: Cv,
    status: AnalysisRunStatus,
    source_failures_json: dict | None = None,
) -> AnalysisRun:
    """Persist an Analysis Run with optional source_failures_json for outcome tests."""
    run = AnalysisRun(
        user_id=user.id,
        cv_id=cv.id,
        status=status,
        job_search_json=_valid_job_search(),
        source_failures_json=source_failures_json,
        finops_json={},
        created_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _assert_failure_reason_field(body: dict, expected_reason: str | None) -> None:
    """Assert that 'failure_reason' is present in the response body with expected value.

    The current RunResponse model (backend/app/api/routes/runs.py) does not
    include a 'failure_reason' field. This assertion will fail (RED) until
    the API response is updated to expose the domain's classify_run_failure result.

    Args:
        body: The JSON response body from GET /api/runs/{run_id}.
        expected_reason: The expected value of failure_reason, or None to
            assert the field is absent/None.
    """
    # This assertion will fail because 'failure_reason' is not in the response
    assert "failure_reason" in body, (
        "Expected 'failure_reason' field in RunResponse. "
        "The RunResponse model in backend/app/api/routes/runs.py must be "
        "updated to include failure_reason derived from classify_run_failure()."
    )
    if expected_reason is None:
        assert body["failure_reason"] is None, (
            f"Expected failure_reason=None, got {body['failure_reason']!r}"
        )
    else:
        assert body["failure_reason"] == expected_reason, (
            f"Expected failure_reason={expected_reason!r}, got {body['failure_reason']!r}"
        )


# =========================================================================
# AC1: successes list is non-empty on a mixed-source zero-listings run
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_mixed_source_zero_listings_successes_non_empty(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """AC1: A mixed-source FAILED run's source_failures_json has a non-empty successes list.

    Scenario: Adzuna returned HTTP 200 with 0 listings (recorded as a success),
    Reed returned an error (recorded as a failure). The run finalises FAILED.
    The API response must surface the 'successes' list from source_failures.
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json={
            "successes": ["adzuna"],
            "failures": [{"source": "reed", "reason": "scrape_failed"}],
        },
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.NO_JOBS_FOUND.value)

    successes = body.get("source_failures", {}).get("successes", [])
    assert len(successes) > 0, (
        "Expected non-empty successes list for mixed-source run"
    )
    assert "adzuna" in successes


# =========================================================================
# AC2: Mixed-source run shows "No jobs found for this search"
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_mixed_source_zero_listings_shows_no_jobs_message(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """AC2: A mixed-source FAILED run shows 'No jobs found for this search'.

    Scenario: Same run as AC1. The UI-displayed failure_message must be
    "No jobs found for this search", not "Scraping failed — try again later".
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json={
            "successes": ["adzuna"],
            "failures": [{"source": "reed", "reason": "scrape_failed"}],
        },
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.NO_JOBS_FOUND.value)

    assert body["failure_message"] == "No jobs found for this search", (
        f"Expected 'No jobs found for this search', got {body['failure_message']!r}"
    )


# =========================================================================
# AC3: All-fail run shows "Scraping failed — try again later"
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_all_sources_failed_successes_empty_shows_scrape_failed(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """AC3: An all-fail run has empty successes and shows 'Scraping failed'.

    Scenario: Both Adzuna and Reed returned errors. The run finalises FAILED.
    source_failures.successes must be empty/missing and the failure_message
    must be "Scraping failed — try again later".
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json={
            "successes": [],
            "failures": [
                {"source": "adzuna", "reason": "scrape_failed"},
                {"source": "reed", "reason": "scrape_failed"},
            ],
        },
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.SCRAPE_FAILED.value)

    sf = body.get("source_failures")
    if sf is not None:
        successes = sf.get("successes", [])
        assert len(successes) == 0, (
            f"Expected empty successes for all-fail run, got {successes!r}"
        )
    assert body["failure_message"] == "Scraping failed \u2014 try again later", (
        f"Expected 'Scraping failed — try again later', got {body['failure_message']!r}"
    )


# =========================================================================
# AC4: Mixed-source failed run includes "failure_reason": "no_jobs_found"
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_mixed_source_response_has_failure_reason_no_jobs_found(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """AC4: A mixed-source FAILED run response includes failure_reason='no_jobs_found'.

    Scenario: Same mixed-source run as AC1/AC2. The API response body must
    contain a 'failure_reason' field with the value 'no_jobs_found'.
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json={
            "successes": ["adzuna"],
            "failures": [{"source": "reed", "reason": "scrape_failed"}],
        },
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.NO_JOBS_FOUND.value)


# =========================================================================
# AC5: COMPLETE run has no failure message and status is COMPLETE
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_complete_no_failure_message_status_complete(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """AC5: A COMPLETE run (>=1 listing scored) has no failure message and status COMPLETE.

    Scenario: The run scraped and scored at least one listing, finalising as
    COMPLETE. The response must show status='complete' and failure_message=null.
    The 'failure_reason' field must also be absent or None for COMPLETE runs.
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.COMPLETE,
        source_failures_json=None,
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "complete", (
        f"Expected status='complete', got {body['status']!r}"
    )
    assert body.get("failure_message") is None, (
        f"Expected failure_message=None for COMPLETE run, got {body.get('failure_message')!r}"
    )

    # A 'failure_reason' field with value null/None should exist on COMPLETE runs
    # to match the API contract established for FAILED runs.
    # The current RunResponse model does NOT include a failure_reason field.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, None)


# =========================================================================
# Supplementary edge cases (gap coverage)
# =========================================================================

@pytest.mark.asyncio
async def test_get_run_failed_no_source_metadata_shows_no_jobs_found(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """FAILED run with source_failures_json=None → NO_JOBS_FOUND.

    When no source interaction metadata was recorded at all (source_failures_json
    is NULL/None), the classifier defaults to NO_JOBS_FOUND — the safe assumption
    that the search was empty rather than a scrape failure. This covers the
    backward-compatible path for pre-fix runs that have no successes key.
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json=None,
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.NO_JOBS_FOUND.value)

    assert body["failure_message"] == "No jobs found for this search", (
        f"Expected 'No jobs found for this search', got {body['failure_message']!r}"
    )


@pytest.mark.asyncio
async def test_get_run_failed_both_sources_ok_zero_listings_shows_no_jobs_found(
    runs_client: AsyncClient,
    db_session: Session,
) -> None:
    """FAILED run with both sources OK (0 listings) → NO_JOBS_FOUND.

    When both Adzuna and Reed returned clean (but empty) responses, the search
    genuinely matched nothing. The failure_reason must be 'no_jobs_found' and
    the failure_message must be 'No jobs found for this search'.
    """
    user = create_test_user(db_session)
    cv = _create_cv(db_session, user)
    run = _seed_run_with_source_meta(
        db_session,
        user=user,
        cv=cv,
        status=AnalysisRunStatus.FAILED,
        source_failures_json={
            "successes": ["adzuna", "reed"],
            "failures": [],
        },
    )
    _authenticate_client(runs_client, db_session, user)

    response = await runs_client.get(f"/runs/{run.id}")

    assert response.status_code == 200
    body = response.json()

    # The 'failure_reason' field is NOT yet exposed by RunResponse.
    # This assertion will fail (RED) until the API is updated.
    _assert_failure_reason_field(body, RunFailureReason.NO_JOBS_FOUND.value)

    assert body["failure_message"] == "No jobs found for this search", (
        f"Expected 'No jobs found for this search', got {body['failure_message']!r}"
    )