"""API-level request validation helpers for HTTP route boundaries."""

import uuid

from fastapi import HTTPException, status

NOT_FOUND_DETAIL = "Not found"


def parse_uuid_path_param(value: str, *, field_name: str = "id") -> uuid.UUID:
    """Parse and validate a UUID path or query parameter at the API boundary.

    Args:
        value: Raw identifier from the incoming request.
        field_name: Human-readable field name for validation errors.

    Returns:
        uuid.UUID: Parsed identifier safe for repository lookups.

    Raises:
        HTTPException: When the value is not a valid UUID string.
    """
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {field_name}",
        ) from error


def raise_not_found() -> None:
    """Raise a generic 404 response consistent with the IDOR policy.

    Raises:
        HTTPException: Always raised with a non-enumerating not-found message.
    """
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
