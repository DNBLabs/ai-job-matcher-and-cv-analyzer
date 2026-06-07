"""Security boundary tests for session cookie validation."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.auth.middleware import SESSION_COOKIE_NAME
from app.auth.session import SessionService, is_valid_session_id
from tests.auth.conftest import create_test_user


@pytest.mark.parametrize(
    "invalid_session_id",
    [
        "",
        "short",
        "a" * 129,
        "valid-looking-but-has-slash/here" + ("x" * 32),
        "valid-looking-but-has-space " + ("x" * 32),
        "'; DROP TABLE sessions; --" + ("x" * 16),
    ],
)
def test_is_valid_session_id_rejects_malformed_values(invalid_session_id: str) -> None:
    """Session ids must match the opaque token format before any database lookup."""
    assert is_valid_session_id(invalid_session_id) is False


def test_is_valid_session_id_accepts_generated_token() -> None:
    """Generated session ids pass boundary validation."""
    generated = SessionService._generate_session_id()
    assert is_valid_session_id(generated) is True


@pytest.mark.asyncio
async def test_malformed_session_cookie_returns_same_401_as_missing(
    client: AsyncClient,
) -> None:
    """Invalid session cookies return the same generic 401 to avoid enumeration."""
    missing_response = await client.get("/test/protected")
    client.cookies.set(SESSION_COOKIE_NAME, "'; DROP TABLE sessions; --")
    malformed_response = await client.get("/test/protected")

    assert missing_response.status_code == 401
    assert malformed_response.status_code == 401
    assert missing_response.json() == malformed_response.json()


@pytest.mark.asyncio
async def test_unknown_valid_format_session_returns_same_401_as_missing(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """Unknown but well-formed session ids return the same generic 401 as no cookie."""
    create_test_user(db_session)
    unknown_session_id = "Z" * 43

    missing_response = await client.get("/test/protected")
    client.cookies.set(SESSION_COOKIE_NAME, unknown_session_id)
    unknown_response = await client.get("/test/protected")

    assert is_valid_session_id(unknown_session_id) is True
    assert missing_response.status_code == 401
    assert unknown_response.status_code == 401
    assert missing_response.json() == unknown_response.json()
