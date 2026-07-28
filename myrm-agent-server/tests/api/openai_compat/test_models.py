"""Tests for /v1/models endpoint (Agent API — agents only)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="openai_compat_only", openai_compat=True)


class TestModelsEndpoint:
    """HTTP-level tests for /v1/models."""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    @pytest.fixture
    async def api_key(self, client: AsyncClient) -> str:
        resp = await client.post("/api/v1/api-keys", json={"name": "Models Test"})
        return resp.json()["key"]

    @pytest.mark.asyncio
    async def test_always_includes_default(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        resp = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        assert "default" in ids

    @pytest.mark.asyncio
    async def test_no_duplicate_model_ids(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        resp = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_does_not_list_raw_llm_provider_models(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        """Agent API lists agents only — not user-configured LLM model names."""
        resp = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        owned_by = {m["owned_by"] for m in data["data"]}
        assert not any(ob.startswith("provider/") for ob in owned_by)
