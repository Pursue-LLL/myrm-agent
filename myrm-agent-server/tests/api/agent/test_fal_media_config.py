"""Tests for FAL.ai media configuration and provider status endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.agents.media import (
    TestMediaConfigRequest,
    media_provider_status,
)
from app.api.agents.media import (
    test_media_config as exec_test_media_config,
)
from app.services.agent.params import _find_provider_api_key
from app.services.agent.params.providers import normalize_storage_provider_id


def test_fal_provider_id_normalization() -> None:
    assert normalize_storage_provider_id("fal") == "fal"
    assert normalize_storage_provider_id("fal_ai") == "fal"
    assert normalize_storage_provider_id("fal-ai") == "fal"


def test_find_fal_provider_api_key() -> None:
    providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [
                    {
                        "key": "fal-secret-key-123",
                        "isActive": True,
                    }
                ],
            }
        ]
    }
    assert _find_provider_api_key(providers_dict, "fal") == "fal-secret-key-123"
    assert _find_provider_api_key(providers_dict, "fal_ai") == "fal-secret-key-123"
    assert _find_provider_api_key(providers_dict, "fal-ai") == "fal-secret-key-123"


@pytest.mark.asyncio
async def test_test_media_config_fal_success() -> None:
    fake_configs = MagicMock()
    fake_configs.providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [
                    {
                        "key": "fal-secret-key",
                        "isActive": True,
                    }
                ],
            }
        ]
    }

    mock_provider = MagicMock()
    mock_provider.health_check = AsyncMock(return_value=True)

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_provider

    req = TestMediaConfigRequest(
        media_type="video",
        provider="fal",
        model="fal-ai/flux-3-video",
    )
    http_req = MagicMock()

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=fake_configs)),
        patch("myrm_agent_harness.toolkits.llms.video.providers.get_registry", return_value=mock_registry),
    ):
        resp = await exec_test_media_config(req, http_req)
        assert resp.status_code == 200
        import json
        body = json.loads(resp.body)
        assert body.get("success") is True
        assert body.get("data", {}).get("status") == "ok"


@pytest.mark.asyncio
async def test_media_provider_status_fal_included() -> None:
    fake_configs = MagicMock()
    fake_configs.providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [
                    {
                        "key": "fal-secret-key",
                        "isActive": True,
                    }
                ],
            }
        ]
    }

    mock_provider = MagicMock()
    mock_provider.health_check = AsyncMock(return_value=True)

    mock_registry = MagicMock()
    mock_registry.list_providers.return_value = [
        {
            "id": "fal",
            "name": "FAL.ai",
            "default_model": "fal-ai/flux-3-video",
            "models": [{"id": "fal-ai/flux-3-video", "name": "FLUX.3 Video"}],
        }
    ]
    mock_registry.get.return_value = mock_provider

    http_req = MagicMock()

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=fake_configs)),
        patch("myrm_agent_harness.toolkits.llms.video.providers.get_registry", return_value=mock_registry),
    ):
        resp = await media_provider_status(http_req)
        assert resp.status_code == 200
        import json
        body = json.loads(resp.body)
        assert body.get("success") is True
        providers = body.get("data", {}).get("providers", {})
        assert "fal" in providers
        assert providers["fal"]["hasApiKey"] is True
        assert providers["fal"]["healthy"] is True
        assert providers["fal"]["configured"] is True
