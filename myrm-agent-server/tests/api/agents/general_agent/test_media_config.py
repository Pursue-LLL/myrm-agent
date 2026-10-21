"""Tests for the media settings credential endpoints (`/agents/test-media-config`, `/agents/media-provider-status`)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

_LOAD_USER_CONFIGS = "app.core.channel_bridge.config_loader.load_user_configs"
_FAL_HEALTH_CHECK = "myrm_agent_harness.toolkits.llms.video.providers.fal_provider.FalVideoProvider.health_check"

app = build_minimal_app("agents_general")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _fal_providers(key: str) -> dict[str, object]:
    return {"providers": [{"id": "fal", "isEnabled": True, "apiKeys": [{"key": key, "isActive": True}]}]}


@contextmanager
def _user_configs(providers: dict[str, object] | None = None, voice: dict[str, object] | None = None) -> Iterator[None]:
    configs = SimpleNamespace(providers_dict=providers or {"providers": []}, voice_dict=voice)
    with patch(_LOAD_USER_CONFIGS, new_callable=AsyncMock, return_value=configs):
        yield


@contextmanager
def _unreadable_user_configs() -> Iterator[None]:
    with patch(_LOAD_USER_CONFIGS, new_callable=AsyncMock, side_effect=RuntimeError("config store offline")):
        yield


def test_media_provider_status_includes_fal(client: TestClient) -> None:
    """GET /api/v1/agents/media-provider-status must list fal with its models."""
    with (
        _user_configs(_fal_providers("test-key-123")),
        patch(_FAL_HEALTH_CHECK, new_callable=AsyncMock, return_value=True),
    ):
        resp = client.get("/api/v1/agents/media-provider-status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    fal_info = data["data"]["providers"]["fal"]
    assert "FAL.ai" in fal_info["name"]
    assert fal_info["hasApiKey"] is True
    assert fal_info["healthy"] is True
    assert fal_info["configured"] is True
    assert fal_info["defaultModel"] == "fal-ai/flux-3-video"
    model_ids = [m["id"] for m in fal_info["models"]]
    assert "fal-ai/flux-3-video" in model_ids
    assert any("kling" in mid for mid in model_ids)


def test_media_provider_status_degrades_when_configs_unreadable(client: TestClient) -> None:
    """An unreadable config store reports every provider as unconfigured instead of failing the request."""
    with _unreadable_user_configs():
        resp = client.get("/api/v1/agents/media-provider-status")

    assert resp.status_code == 200
    providers = resp.json()["data"]["providers"]
    assert providers
    assert all(info["hasApiKey"] is False and info["configured"] is False for info in providers.values())


def test_test_media_config_fal_no_key(client: TestClient) -> None:
    """POST /api/v1/agents/test-media-config fails gracefully when no key is set."""
    with _user_configs():
        resp = client.post("/api/v1/agents/test-media-config", json={"mediaType": "video", "provider": "fal"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "No API key found for provider 'fal'" in data["message"]


def test_test_media_config_fal_success(client: TestClient) -> None:
    """POST /api/v1/agents/test-media-config succeeds when the health check passes."""
    with (
        _user_configs(_fal_providers("test-key-456")),
        patch(_FAL_HEALTH_CHECK, new_callable=AsyncMock, return_value=True),
    ):
        resp = client.post("/api/v1/agents/test-media-config", json={"mediaType": "video", "provider": "fal"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "ok"


def test_test_media_config_tts_requires_key(client: TestClient) -> None:
    """The TTS branch is served by the live router and reports the missing credential."""
    with _user_configs():
        resp = client.post("/api/v1/agents/test-media-config", json={"mediaType": "tts", "provider": "openai"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "No API key found for TTS provider 'openai'" in data["message"]


def test_test_media_config_tts_prefers_voice_settings_key(client: TestClient) -> None:
    """Voice settings take precedence over the provider table for the TTS credential."""
    with (
        _user_configs(voice={"ttsProvider": "openai", "ttsApiKey": "voice-key"}),
        patch("app.api.agents.general_agent.media_config._probe_endpoint", new_callable=AsyncMock) as probe,
    ):
        probe.return_value = (True, "API key is valid")
        resp = client.post("/api/v1/agents/test-media-config", json={"mediaType": "tts", "provider": "openai"})

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ok"
    assert probe.await_args.args[1] == {"Authorization": "Bearer voice-key"}


def test_test_media_config_degrades_when_configs_unreadable(client: TestClient) -> None:
    """An unreadable config store surfaces as a missing key rather than a 500."""
    with _unreadable_user_configs():
        resp = client.post("/api/v1/agents/test-media-config", json={"mediaType": "video", "provider": "fal"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "No API key found for provider 'fal'" in data["message"]
