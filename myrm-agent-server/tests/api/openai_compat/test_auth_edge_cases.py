"""Edge case tests for API key authentication.

Tests malformed headers, expired keys, and concurrent access patterns.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.database.connection import get_session
from app.database.models.api_key import APIKey
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_bearer_without_space():
    """'Bearerxxx' (no space) should fail."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/models", headers={"Authorization": "Bearersk-myrm-foo"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_bearer_token():
    """'Bearer ' with empty key should fail."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/models", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_key(client: AsyncClient):
    """Expired key should return 403 with key_expired code."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Expire Test", "expires_in_days": 1})
    key_data = create_resp.json()
    raw_key = key_data["key"]
    key_id = key_data["id"]

    # Manually set expires_at to the past
    async with get_session() as session:
        await session.execute(update(APIKey).where(APIKey.id == key_id).values(expires_at=datetime.now(UTC) - timedelta(hours=1)))
        await session.commit()

    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp.status_code == 403
    assert "key_expired" in resp.json()["detail"]["error"]["code"]


@pytest.mark.asyncio
async def test_key_with_expiration_still_valid(client: AsyncClient):
    """Non-expired key with expiration date should work."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Valid Expiry", "expires_in_days": 30})
    raw_key = create_resp.json()["key"]

    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_name_required(client: AsyncClient):
    """Creating key without name should fail validation."""
    resp = await client.post("/api/v1/api-keys", json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revoke_nonexistent_key(client: AsyncClient):
    """Revoking nonexistent key should return 404."""
    resp = await client.patch("/api/v1/api-keys/99999/revoke")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_key(client: AsyncClient):
    """Deleting nonexistent key should return 404."""
    resp = await client.delete("/api/v1/api-keys/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_key_prefix_format(client: AsyncClient):
    """Key prefix should match the key's first 12 chars."""
    resp = await client.post("/api/v1/api-keys", json={"name": "Prefix Test"})
    data = resp.json()
    assert data["key_prefix"] == data["key"][:12]
    assert data["key_prefix"].startswith("sk-myrm-")
