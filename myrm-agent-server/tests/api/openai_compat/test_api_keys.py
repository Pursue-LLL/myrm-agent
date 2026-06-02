"""Integration tests for API Key CRUD and authentication.

Tests the full lifecycle: create → list → revoke → authenticate → delete.
Uses real database (SQLite in-memory via conftest).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_create_api_key(client: AsyncClient):
    """Create a key and verify the response contains the secret."""
    resp = await client.post(
        "/api/v1/api-keys",
        json={"name": "Test Key", "note": "for testing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Key"
    assert data["key"].startswith("sk-myrm-")
    assert data["key_prefix"] == data["key"][:12]
    assert data["id"] > 0


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient):
    """List keys should return created keys without secrets."""
    await client.post("/api/v1/api-keys", json={"name": "List Test"})

    resp = await client.get("/api/v1/api-keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    found = [k for k in keys if k["name"] == "List Test"]
    assert len(found) == 1
    assert found[0]["is_active"] is True
    assert "key" not in found[0]


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient):
    """Revoked keys should be inactive."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Revoke Test"})
    key_id = create_resp.json()["id"]

    revoke_resp = await client.patch(f"/api/v1/api-keys/{key_id}/revoke")
    assert revoke_resp.status_code == 200

    list_resp = await client.get("/api/v1/api-keys")
    revoked = [k for k in list_resp.json() if k["id"] == key_id]
    assert revoked[0]["is_active"] is False


@pytest.mark.asyncio
async def test_delete_api_key(client: AsyncClient):
    """Deleted keys should disappear from list."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Delete Test"})
    key_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/api-keys/{key_id}")
    assert del_resp.status_code == 200

    list_resp = await client.get("/api/v1/api-keys")
    remaining = [k for k in list_resp.json() if k["id"] == key_id]
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_auth_missing_header(client: AsyncClient):
    """Missing Authorization header should return 401."""
    resp = await client.get("/v1/models")
    assert resp.status_code == 401
    assert "missing_api_key" in resp.json()["detail"]["error"]["code"]


@pytest.mark.asyncio
async def test_auth_invalid_key(client: AsyncClient):
    """Invalid key should return 401."""
    resp = await client.get(
        "/v1/models", headers={"Authorization": "Bearer sk-myrm-invalid123"}
    )
    assert resp.status_code == 401
    assert "invalid_key" in resp.json()["detail"]["error"]["code"]


@pytest.mark.asyncio
async def test_auth_valid_key(client: AsyncClient):
    """Valid key should pass authentication and return models."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Auth Test"})
    raw_key = create_resp.json()["key"]

    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert any(m["id"] == "default" for m in data["data"])


@pytest.mark.asyncio
async def test_auth_revoked_key(client: AsyncClient):
    """Revoked key should return 403."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Revoked Auth"})
    raw_key = create_resp.json()["key"]
    key_id = create_resp.json()["id"]

    await client.patch(f"/api/v1/api-keys/{key_id}/revoke")

    resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    assert resp.status_code == 403
    assert "key_revoked" in resp.json()["detail"]["error"]["code"]


@pytest.mark.asyncio
async def test_usage_counter_increments(client: AsyncClient):
    """Usage counter should increment on successful auth."""
    create_resp = await client.post("/api/v1/api-keys", json={"name": "Counter Test"})
    raw_key = create_resp.json()["key"]
    key_id = create_resp.json()["id"]

    await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})
    await client.get("/v1/models", headers={"Authorization": f"Bearer {raw_key}"})

    list_resp = await client.get("/api/v1/api-keys")
    matched = [k for k in list_resp.json() if k["id"] == key_id]
    assert matched[0]["usage_count"] >= 2
    assert matched[0]["last_used_at"] is not None
