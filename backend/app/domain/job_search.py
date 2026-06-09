"""Job Search criteria validation for UK-scoped Analysis Runs."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

REMOTE_LOCATION = "Remote"
ROLE_MAX_LENGTH = 200
LOCATION_MAX_LENGTH = 100

UK_CITIES = frozenset(
    {
        "London",
        "Manchester",
        "Birmingham",
        "Leeds",
        "Glasgow",
        "Edinburgh",
        "Bristol",
        "Liverpool",
        "Newcastle",
        "Sheffield",
        "Cardiff",
        "Belfast",
        "Cambridge",
        "Oxford",
        "Brighton",
        "Nottingham",
        "Southampton",
        "Leicester",
        "Coventry",
        "Reading",
    },
)


class ExperienceLevel(StrEnum):
    """Supported experience-level filters for Job Search."""

    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    EXECUTIVE = "executive"


class EmploymentType(StrEnum):
    """Supported employment-type filters for Job Search."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"


class JobSearchFilters(BaseModel):
    """Optional Job Search filters persisted with an Analysis Run."""

    experience_level: ExperienceLevel | None = None
    employment_type: EmploymentType | None = None


class JobSearch(BaseModel):
    """Validated Job Search criteria pairing one CV with one Analysis Run."""

    role: str = Field(..., min_length=1, max_length=ROLE_MAX_LENGTH)
    location: str = Field(..., min_length=1, max_length=LOCATION_MAX_LENGTH)
    remote: bool
    filters: JobSearchFilters | None = None

    @field_validator("role", "location")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """Trim whitespace and reject empty role/location strings.

        Args:
            value: Raw role or location text from the API payload.

        Returns:
            str: Trimmed non-empty text.

        Raises:
            ValueError: When the field is blank after trimming.
        """
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be empty")
        return trimmed

    @model_validator(mode="after")
    def validate_location_remote_consistency(self) -> "JobSearch":
        """Ensure remote flag and location align with UK city allowlist rules.

        Returns:
            JobSearch: The validated model instance.

        Raises:
            ValueError: When remote/location combinations are inconsistent.
        """
        if self.remote:
            if self.location != REMOTE_LOCATION:
                raise ValueError("remote searches must use Remote location")
            return self

        if self.location == REMOTE_LOCATION:
            raise ValueError("on-site searches must not use Remote location")
        if self.location not in UK_CITIES:
            raise ValueError("location must be a supported UK city or Remote")
        return self

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize validated Job Search values for ``analysis_run.job_search_json``.

        Returns:
            dict[str, Any]: JSON-serializable Job Search payload without null filters.
        """
        return self.model_dump(mode="json", exclude_none=True)


def validate_job_search(raw: dict[str, Any]) -> JobSearch:
    """Validate and normalize Job Search input from API payloads.

    Args:
        raw: Untrusted Job Search object from ``POST /runs``.

    Returns:
        JobSearch: Parsed and validated Job Search criteria.

    Raises:
        ValueError: When the payload is not a JSON object or fails schema rules.
    """
    if not isinstance(raw, dict):
        raise ValueError("job_search must be a JSON object")

    try:
        return JobSearch.model_validate(raw)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(str(error)) from error
