"""Tests for Vercel AI Gateway provider preset, attribution headers, and Hermes migration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model
from starlette.testclient import TestClient

from app.services.migration.source.source_model_migrator import (
    _PROVIDER_LITELLM_PREFIX,
    extract_hermes_auxiliary_config,
    migrate_hermes_auxiliary_models,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@asynccontextmanager
async def _mock_httpx_client(*_args: object, **_kwargs: object):
    yield object()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_discover_models_injects_attribution_headers_for_vercel_gateway(client: TestClient) -> None:
    captured_headers: dict[str, str] = {}

    async def _mock_secure_request(
        client_obj: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        allowed_internal_hosts: list[str] | None = None,
    ) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(headers)
        return httpx.Response(
            200,
            json={"data": [{"id": "anthropic/claude-3-5-sonnet"}]},
            request=httpx.Request("GET", url),
        )

    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch("app.api.integrations.llms.secure_request", side_effect=_mock_secure_request),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={
                "api_url": "https://ai-gateway.vercel.sh/v1",
                "api_key": "vca_test_secret",
            },
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["success"] is True
        assert "anthropic/claude-3-5-sonnet" in payload["models"]
        assert captured_headers.get("HTTP-Referer") == "https://myrm.ai"
        assert captured_headers.get("X-Title") == "Myrm Agent"
        assert captured_headers.get("Authorization") == "Bearer vca_test_secret"


def test_discover_models_does_not_inject_attribution_headers_for_other_endpoints(client: TestClient) -> None:
    captured_headers: dict[str, str] = {}

    async def _mock_secure_request(
        client_obj: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        allowed_internal_hosts: list[str] | None = None,
    ) -> httpx.Response:
        nonlocal captured_headers
        captured_headers = dict(headers)
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-4o"}]},
            request=httpx.Request("GET", url),
        )

    with (
        patch("app.api.integrations.llms.create_httpx_client", _mock_httpx_client),
        patch("app.api.integrations.llms.secure_request", side_effect=_mock_secure_request),
    ):
        response = client.post(
            "/api/v1/integrations/llm/discover-models",
            json={
                "api_url": "https://api.openai.com/v1",
                "api_key": "sk-openai-test",
            },
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["success"] is True
        assert "HTTP-Referer" not in captured_headers
        assert "X-Title" not in captured_headers


def test_create_litellm_model_auto_injects_attribution_headers() -> None:
    llm = create_litellm_model(
        model="openai/anthropic/claude-3-5-sonnet",
        base_url="https://ai-gateway.vercel.sh/v1",
        api_key="vca_test_key",
    )
    extra_headers = llm.model_kwargs.get("extra_headers", {})
    assert extra_headers.get("HTTP-Referer") == "https://myrm.ai"
    assert extra_headers.get("X-Title") == "Myrm Agent"


def test_hermes_auxiliary_migration_maps_ai_gateway_aliases() -> None:
    assert _PROVIDER_LITELLM_PREFIX["ai-gateway"] == "openai"
    assert _PROVIDER_LITELLM_PREFIX["aigateway"] == "openai"
    assert _PROVIDER_LITELLM_PREFIX["vercel"] == "openai"
    assert _PROVIDER_LITELLM_PREFIX["vercel_ai_gateway"] == "openai"

    hermes_cfg = {
        "auxiliary": {
            "compression": {
                "provider": "ai-gateway",
                "model": "meta-llama/llama-3.3-70b-instruct",
            },
            "vision": {
                "provider": "vercel",
                "model": "google/gemini-2.0-flash",
            },
        }
    }
    extracted = extract_hermes_auxiliary_config(hermes_cfg)
    assert extracted["compression"]["provider"] == "ai-gateway"
    assert extracted["vision"]["provider"] == "vercel"

    result = migrate_hermes_auxiliary_models(extracted)
    assert result.migrated_slots["long_doc_model"] == "openai/meta-llama/llama-3.3-70b-instruct"
    assert result.migrated_slots["vision_fallback_model"] == "openai/google/gemini-2.0-flash"
