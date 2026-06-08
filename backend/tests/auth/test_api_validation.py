"""Unit tests for API-level request validation helpers."""

import uuid

import pytest
from fastapi import HTTPException

from app.api.validation import NOT_FOUND_DETAIL, parse_uuid_path_param, raise_not_found


def test_parse_uuid_path_param_accepts_valid_uuid() -> None:
    """Valid UUID strings are parsed for owner-scoped route dependencies."""
    value = str(uuid.uuid4())
    assert parse_uuid_path_param(value, field_name="cv_id") == uuid.UUID(value)


@pytest.mark.parametrize("invalid_value", ["", "not-a-uuid", "123", "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"])
def test_parse_uuid_path_param_rejects_invalid_values(invalid_value: str) -> None:
    """Malformed UUID path parameters return 422 at the API boundary."""
    with pytest.raises(HTTPException) as error:
        parse_uuid_path_param(invalid_value, field_name="run_id")

    assert error.value.status_code == 422
    assert error.value.detail == "Invalid run_id"


def test_raise_not_found_uses_generic_detail() -> None:
    """IDOR denials use a generic not-found message."""
    with pytest.raises(HTTPException) as error:
        raise_not_found()

    assert error.value.status_code == 404
    assert error.value.detail == NOT_FOUND_DETAIL
