"""Auth API tests (auth disabled by default)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_auth_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert "auth_enabled" in data
