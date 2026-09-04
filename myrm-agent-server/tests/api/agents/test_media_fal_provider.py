"""Integration and unit tests for FAL.ai video provider configuration and prebuilt skill."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("agents_media")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_media_provider_status_includes_fal(client: TestClient) -> None:
    """GET /api/v1/agents/media-provider-status must list fal with its models."""
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [{"key": "test-key-123", "isActive": True}],
            }
        ]
    }

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.video.providers.fal_provider.FalVideoProvider.health_check",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        resp = client.get("/api/v1/agents/media-provider-status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    providers = data["data"]["providers"]
    assert "fal" in providers
    fal_info = providers["fal"]
    assert "FAL.ai" in fal_info["name"]
    assert fal_info["hasApiKey"] is True
    assert fal_info["healthy"] is True
    assert fal_info["configured"] is True
    assert fal_info["defaultModel"] == "fal-ai/flux-3-video"
    model_ids = [m["id"] for m in fal_info["models"]]
    assert "fal-ai/flux-3-video" in model_ids
    assert any("kling" in mid for mid in model_ids)


def test_test_media_config_fal_no_key(client: TestClient) -> None:
    """POST /api/v1/agents/test-media-config fails gracefully when no key is set."""
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"providers": []}

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        new_callable=AsyncMock,
        return_value=mock_cfgs,
    ):
        resp = client.post(
            "/api/v1/agents/test-media-config",
            json={"mediaType": "video", "provider": "fal"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "No API key found for provider 'fal'" in data["message"]


def test_test_media_config_fal_success(client: TestClient) -> None:
    """POST /api/v1/agents/test-media-config succeeds when health check passes."""
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [{"key": "test-key-456", "isActive": True}],
            }
        ]
    }

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.video.providers.fal_provider.FalVideoProvider.health_check",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        resp = client.post(
            "/api/v1/agents/test-media-config",
            json={"mediaType": "video", "provider": "fal"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"


def test_flux3_prompting_guide_skill_valid() -> None:
    """Verify prebuilt skill flux3-prompting-guide exists and is well-formed."""
    from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter

    server_root = Path(__file__).resolve().parents[3]
    skill_file = server_root / "assets" / "prebuilt_skills" / "flux3-prompting-guide" / "SKILL.md"
    assert skill_file.is_file(), f"Skill file missing at {skill_file}"

    data = parse_skill_frontmatter(skill_file.read_text(encoding="utf-8"), "flux3-prompting-guide")
    assert data.name == "flux3-prompting-guide"
    assert data.version == "1.0.0"
    assert "video_tool" in data.allowed_tools


def test_fal_provider_id_normalization() -> None:
    from app.services.agent.params.providers import normalize_storage_provider_id

    assert normalize_storage_provider_id("fal") == "fal"
    assert normalize_storage_provider_id("fal_ai") == "fal"
    assert normalize_storage_provider_id("fal-ai") == "fal"


def test_find_fal_provider_api_key() -> None:
    from app.services.agent.params import _find_provider_api_key

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

