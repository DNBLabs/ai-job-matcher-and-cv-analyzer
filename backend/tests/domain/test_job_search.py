"""Behavior tests for Job Search schema validation."""

import pytest

from app.domain.job_search import (
    REMOTE_LOCATION,
    EmploymentType,
    ExperienceLevel,
    JobSearch,
    validate_job_search,
)


def test_validate_job_search_accepts_uk_city_with_remote_false() -> None:
    """On-site searches require a supported UK city and remote=false."""
    job_search = validate_job_search(
        {"role": "Python Developer", "location": "London", "remote": False},
    )

    assert job_search.role == "Python Developer"
    assert job_search.location == "London"
    assert job_search.remote is False


def test_validate_job_search_accepts_remote_search() -> None:
    """Remote searches require remote=true and location Remote."""
    job_search = validate_job_search(
        {"role": "Engineer", "location": REMOTE_LOCATION, "remote": True},
    )

    assert job_search.location == REMOTE_LOCATION
    assert job_search.remote is True


def test_validate_job_search_accepts_optional_filters() -> None:
    """Optional filters must use supported experience and employment enums."""
    job_search = validate_job_search(
        {
            "role": "Backend Engineer",
            "location": "Manchester",
            "remote": False,
            "filters": {
                "experience_level": ExperienceLevel.SENIOR.value,
                "employment_type": EmploymentType.CONTRACT.value,
            },
        },
    )

    assert job_search.filters is not None
    assert job_search.filters.experience_level == ExperienceLevel.SENIOR
    assert job_search.filters.employment_type == EmploymentType.CONTRACT


def test_validate_job_search_rejects_unknown_city() -> None:
    """Locations outside the UK city allowlist are rejected."""
    with pytest.raises(ValueError, match="UK city"):
        validate_job_search(
            {"role": "Engineer", "location": "Paris", "remote": False},
        )


def test_validate_job_search_rejects_remote_location_mismatch() -> None:
    """remote=true requires location Remote; remote=false rejects Remote."""
    with pytest.raises(ValueError, match="Remote"):
        validate_job_search(
            {"role": "Engineer", "location": "London", "remote": True},
        )
    with pytest.raises(ValueError, match="Remote"):
        validate_job_search(
            {"role": "Engineer", "location": REMOTE_LOCATION, "remote": False},
        )


def test_validate_job_search_rejects_empty_role() -> None:
    """Role keywords must be non-empty after trimming."""
    with pytest.raises(ValueError):
        validate_job_search({"role": "   ", "location": "London", "remote": False})


def test_validate_job_search_rejects_invalid_filter_enum() -> None:
    """Filter enums are validated at the Job Search boundary."""
    with pytest.raises(ValueError):
        validate_job_search(
            {
                "role": "Engineer",
                "location": "Leeds",
                "remote": False,
                "filters": {"experience_level": "wizard"},
            },
        )


def test_job_search_serializes_to_json_dict() -> None:
    """Validated Job Search values round-trip to persisted JSON."""
    job_search = JobSearch(
        role="Data Analyst",
        location="Edinburgh",
        remote=False,
        filters=None,
    )

    payload = job_search.to_storage_dict()

    assert payload == {
        "role": "Data Analyst",
        "location": "Edinburgh",
        "remote": False,
    }
