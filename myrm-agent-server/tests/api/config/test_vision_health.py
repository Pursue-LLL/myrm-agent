"""Tests for POST /config/vision-health."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from myrm_agent_harness.toolkits.llms.vision.fallback_engine import VisionDescriptionError

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_vision_health_not_configured(client: TestClient) -> None:
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"defaultModelConfig": {}}

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_vision_fallback_model_config",
            return_value=None,
        ),
    ):
        response = client.post("/api/v1/config/vision-health")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["healthy"] is False


def test_vision_health_success(client: TestClient) -> None:
    mock_cfg = SimpleNamespace(
        model="openai/gpt-4o-mini",
        api_key="test-key",
        base_url="https://api.example.com/v1",
    )
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"defaultModelConfig": {"visionFallbackModel": {}}}

    mock_engine = MagicMock()
    mock_engine.describe_image_b64 = AsyncMock(return_value="ok")
    mock_engine.last_success_model = "openai/gpt-4o-mini"

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_vision_fallback_model_config",
            return_value=mock_cfg,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.build_vision_fallback_engine_from_providers",
            return_value=mock_engine,
        ),
    ):
        response = client.post("/api/v1/config/vision-health")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["healthy"] is True
    assert body["latency_ms"] is not None
    assert body["resolved_model"] is None
    mock_engine.describe_image_b64.assert_awaited_once()


def test_vision_health_reports_resolved_model_when_backup_succeeds(client: TestClient) -> None:
    mock_cfg = SimpleNamespace(
        model="openai/gpt-4o-mini",
        api_key="test-key",
        base_url="https://api.example.com/v1",
    )
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"defaultModelConfig": {"visionFallbackModel": {}}}

    mock_engine = MagicMock()
    mock_engine.describe_image_b64 = AsyncMock(return_value="ok")
    mock_engine.last_success_model = "openai/gpt-4o"

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_vision_fallback_model_config",
            return_value=mock_cfg,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.build_vision_fallback_engine_from_providers",
            return_value=mock_engine,
        ),
    ):
        response = client.post("/api/v1/config/vision-health")

    body = response.json()
    assert body["healthy"] is True
    assert body["model"] == "openai/gpt-4o-mini"
    assert body["resolved_model"] == "openai/gpt-4o"


def test_vision_health_failure_string_is_unhealthy(client: TestClient) -> None:
    mock_cfg = SimpleNamespace(
        model="openai/gpt-4o-mini",
        api_key="test-key",
        base_url="https://api.example.com/v1",
    )
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"defaultModelConfig": {"visionFallbackModel": {}}}

    mock_engine = MagicMock()
    mock_engine.describe_image_b64 = AsyncMock(
        side_effect=VisionDescriptionError("402 Payment Required"),
    )
    mock_engine.last_success_model = None

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_vision_fallback_model_config",
            return_value=mock_cfg,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.build_vision_fallback_engine_from_providers",
            return_value=mock_engine,
        ),
    ):
        response = client.post("/api/v1/config/vision-health")

    body = response.json()
    assert body["configured"] is True
    assert body["healthy"] is False
    assert "402 Payment Required" in (body["error"] or "")


def test_vision_health_failure_includes_endpoint(client: TestClient) -> None:
    mock_cfg = SimpleNamespace(
        model="dashscope/qwen-vl-plus",
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    mock_cfgs = MagicMock()
    mock_cfgs.providers_dict = {"defaultModelConfig": {"visionFallbackModel": {}}}

    mock_engine = MagicMock()
    mock_engine.describe_image_b64 = AsyncMock(side_effect=ConnectionError("Connection refused"))

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_cfgs,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_vision_fallback_model_config",
            return_value=mock_cfg,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.build_vision_fallback_engine_from_providers",
            return_value=mock_engine,
        ),
    ):
        response = client.post("/api/v1/config/vision-health")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["healthy"] is False
    assert body["model"] == "dashscope/qwen-vl-plus"
    assert body["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert "Connection refused" in (body["error"] or "")
