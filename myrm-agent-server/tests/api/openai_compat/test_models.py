"""Tests for /v1/models endpoint.

Covers agent listing, provider model listing, and de-duplication logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.openai_compat.models import _collect_provider_models
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="openai_compat_only", openai_compat=True)
_MOCK_PROVIDERS_DICT: dict[str, object] = {
    "providers": [
        {
            "id": "anthropic",
            "isEnabled": True,
            "apiKeys": [{"key": "sk-test", "isActive": True}],
            "enabledModels": ["claude-sonnet-4-20250514", "claude-3-haiku"],
        },
        {
            "id": "openai",
            "isEnabled": True,
            "apiKeys": [{"key": "sk-test2", "isActive": True}],
            "enabledModels": ["gpt-4o"],
        },
        {
            "id": "disabled",
            "isEnabled": False,
            "apiKeys": [{"key": "sk-disabled", "isActive": True}],
            "enabledModels": ["disabled-model"],
        },
        {
            "id": "no-keys",
            "isEnabled": True,
            "apiKeys": [],
            "enabledModels": ["orphan"],
        },
    ]
}


class TestCollectProviderModels:
    """Unit tests for _collect_provider_models."""

    def test_collects_enabled_models(self):
        models = _collect_provider_models(_MOCK_PROVIDERS_DICT)
        ids = {m.id for m in models}
        assert "claude-sonnet-4-20250514" in ids
        assert "claude-3-haiku" in ids
        assert "gpt-4o" in ids

    def test_skips_disabled_provider(self):
        models = _collect_provider_models(_MOCK_PROVIDERS_DICT)
        ids = {m.id for m in models}
        assert "disabled-model" not in ids

    def test_skips_no_keys_provider(self):
        models = _collect_provider_models(_MOCK_PROVIDERS_DICT)
        ids = {m.id for m in models}
        assert "orphan" not in ids

    def test_empty_providers(self):
        models = _collect_provider_models({"providers": []})
        assert models == []

    def test_invalid_providers_key(self):
        models = _collect_provider_models({"providers": "not-a-list"})
        assert models == []

    def test_owned_by_includes_pid(self):
        models = _collect_provider_models(_MOCK_PROVIDERS_DICT)
        anthropic_models = [m for m in models if "claude" in m.id]
        assert all(m.owned_by == "provider/anthropic" for m in anthropic_models)


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
        """De-duplication: model IDs should be unique."""
        resp = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_includes_provider_models_when_available(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        """When provider config exists, provider models should appear."""
        mock_configs = MagicMock()
        mock_configs.providers_dict = _MOCK_PROVIDERS_DICT

        mock_record = MagicMock()
        mock_record.value = _MOCK_PROVIDERS_DICT

        with patch(
            "app.services.config.service.config_service.get",
            new_callable=AsyncMock,
            return_value=mock_record,
        ):
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )

        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        assert "gpt-4o" in ids
        assert "claude-sonnet-4-20250514" in ids

    @pytest.mark.asyncio
    async def test_provider_load_failure_graceful(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        """When provider config fails to load, endpoint should still return agents."""
        with patch(
            "app.services.config.service.config_service.get",
            new_callable=AsyncMock,
            side_effect=RuntimeError("config db down"),
        ):
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        ids = [m["id"] for m in data["data"]]
        assert "default" in ids
