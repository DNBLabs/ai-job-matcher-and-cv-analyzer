"""Tests for API ingress rate limiting."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.rate_limit import (
    API_INGRESS_IP_LIMIT,
    API_INGRESS_RATE_WINDOW,
    RateLimitExceeded,
    RateLimiter,
    api_ingress_ip_bucket,
    retry_after_seconds,
)
from app.config import Settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def rate_limit_db_session() -> Generator[Session, None, None]:
    """Provide an isolated in-memory database session for rate-limit unit tests."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ingress_test_app(auth_settings: Settings, rate_limit_db_session: Session):
    """Build a FastAPI app whose ingress middleware shares the test database."""
    from tests.auth.conftest import _bind_test_session_factory

    application = create_app(settings=auth_settings)
    _bind_test_session_factory(application, rate_limit_db_session)

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield rate_limit_db_session
        finally:
            pass

    application.dependency_overrides[get_db_session] = override_get_db_session
    return application


@pytest.fixture
async def ingress_client(ingress_test_app) -> AsyncClient:
    """Async HTTP client bound to the ingress rate-limit test application."""
    transport = ASGITransport(app=ingress_test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def test_api_ingress_rate_limit_raises_after_limit_with_fake_clock(
    rate_limit_db_session: Session,
) -> None:
    """The 101st ingress request within a minute exceeds the configured per-IP limit."""
    rate_limiter = RateLimiter(rate_limit_db_session)
    fixed_now = datetime(2026, 6, 8, 12, 0, 30, tzinfo=UTC)
    bucket_key = api_ingress_ip_bucket("203.0.113.10")

    for _ in range(API_INGRESS_IP_LIMIT):
        rate_limiter.check_and_increment(
            bucket_key=bucket_key,
            limit=API_INGRESS_IP_LIMIT,
            window=API_INGRESS_RATE_WINDOW,
            now=fixed_now,
        )

    with pytest.raises(RateLimitExceeded):
        rate_limiter.check_and_increment(
            bucket_key=bucket_key,
            limit=API_INGRESS_IP_LIMIT,
            window=API_INGRESS_RATE_WINDOW,
            now=fixed_now,
        )


def test_retry_after_seconds_returns_remaining_window_time() -> None:
    """Retry-After reflects seconds until the current one-minute window resets."""
    now = datetime(2026, 6, 8, 12, 0, 45, tzinfo=UTC)
    assert retry_after_seconds(now=now, window=API_INGRESS_RATE_WINDOW) == 15


@pytest.mark.asyncio
async def test_ingress_rate_limit_returns_429_with_retry_after_header(
    ingress_client: AsyncClient,
) -> None:
    """The API returns 429 with Retry-After when ingress limits are exceeded."""
    for _ in range(API_INGRESS_IP_LIMIT):
        response = await ingress_client.post("/auth/logout")
        assert response.status_code == 200

    limited_response = await ingress_client.post("/auth/logout")

    assert limited_response.status_code == 429
    assert limited_response.json()["detail"] == "Too many requests"
    assert limited_response.headers.get("Retry-After") is not None
    assert int(limited_response.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_health_endpoint_is_exempt_from_ingress_rate_limit(
    ingress_client: AsyncClient,
) -> None:
    """Health checks remain available even when other routes are rate limited."""
    for _ in range(API_INGRESS_IP_LIMIT + 5):
        response = await ingress_client.get("/health")
        assert response.status_code == 200
