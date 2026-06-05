"""Tests for baseline API security headers, CORS, and error sanitization."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_security_headers_present_on_health_response() -> None:
    """Public responses include baseline security headers per security posture."""
    application = create_app()
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers.get("Permissions-Policy", "")


@pytest.mark.asyncio
async def test_hsts_header_set_in_production() -> None:
    """HSTS is enabled only when APP_ENV is production."""
    production_settings = Settings(app_env="production", allowed_origins="https://app.example.com")
    application = create_app(settings=production_settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="https://testserver") as client:
        response = await client.get("/health")

    hsts = response.headers.get("Strict-Transport-Security", "")
    assert "max-age=" in hsts


@pytest.mark.asyncio
async def test_unhandled_errors_do_not_expose_internals_in_production() -> None:
    """Unhandled exceptions return a generic message without stack or internal details."""
    production_settings = Settings(app_env="production", allowed_origins="https://app.example.com")
    application = create_app(settings=production_settings)

    @application.get("/test-boom")
    async def trigger_error() -> None:
        raise RuntimeError("postgresql://secret:credential@db.internal:5432")

    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/test-boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "postgresql" not in response.text


@pytest.mark.asyncio
async def test_cors_allows_configured_development_origin() -> None:
    """CORS permits only origins listed in ALLOWED_ORIGINS."""
    settings = Settings(allowed_origins="http://localhost:5173")
    application = create_app(settings=settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_openapi_docs_disabled_in_production() -> None:
    """OpenAPI schema is not exposed when APP_ENV is production."""
    production_settings = Settings(app_env="production", allowed_origins="https://app.example.com")
    application = create_app(settings=production_settings)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 404
