"""Integration tests for the public HTTP health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_health_returns_ok_status(api_test_app) -> None:
    """GET /health confirms the API process is running and reachable."""
    transport = ASGITransport(app=api_test_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
