"""Tests for LLM speed test endpoint.

Tests cover:
- POST /api/v1/llm/speed-test (real streaming TTFT+TPS measurement)
- Error handling (invalid credentials)
- Timeout protection behavior
- Response schema validation
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.test_secrets import load_test_secrets


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestSpeedTestSchema:
    """Unit tests for request/response schema — no LLM required."""

    def test_empty_models_list(self, client: TestClient) -> None:
        """Empty models list should return empty results."""
        response = client.post("/api/v1/llm/speed-test", json={"models": []})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"] == []

    def test_missing_required_fields(self, client: TestClient) -> None:
        """Missing model name should return 422."""
        response = client.post(
            "/api/v1/llm/speed-test",
            json={"models": [{"api_key": "fake"}]},
        )
        assert response.status_code == 422

    def test_invalid_body(self, client: TestClient) -> None:
        """Invalid request body should return 422."""
        response = client.post("/api/v1/llm/speed-test", json={"invalid": True})
        assert response.status_code == 422


class TestSpeedTestErrorHandling:
    """Tests for error handling — uses invalid credentials."""

    def test_invalid_api_key(self, client: TestClient) -> None:
        """Invalid API key should return status=error with error message."""
        response = client.post(
            "/api/v1/llm/speed-test",
            json={
                "models": [
                    {
                        "model": "gpt-4o-mini",
                        "api_key": "sk-invalid-key-for-testing",
                        "base_url": "https://api.openai.com/v1",
                    }
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        results = data["data"]
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert results[0]["error"] is not None
        assert results[0]["model"] == "gpt-4o-mini"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestSpeedTestE2E:
    """Real E2E speed test using .env.test credentials."""

    def test_single_model_speed_test(self, client: TestClient) -> None:
        """Test real model returns valid TTFT and TPS metrics."""
        secrets = load_test_secrets()
        from myrm_agent_harness.agent.config.litellm_routing import (
            normalize_env_model_selection_string,
        )

        model = normalize_env_model_selection_string(secrets.basic_model)
        response = client.post(
            "/api/v1/llm/speed-test",
            json={
                "models": [
                    {
                        "model": model,
                        "api_key": secrets.basic_api_key,
                        "base_url": secrets.basic_base_url or None,
                    }
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        results = data["data"]
        assert len(results) == 1

        result = results[0]
        assert result["status"] == "ok", f"Speed test failed: {result.get('error')}"
        assert result["ttft_ms"] is not None
        assert result["ttft_ms"] > 0
        assert result["throughput_tps"] is not None
        assert result["throughput_tps"] > 0
        assert result["total_tokens"] is not None
        assert result["total_tokens"] > 0
        assert result["total_ms"] is not None
        assert result["total_ms"] >= result["ttft_ms"]

        print(f"\n  Model: {result['model']}")
        print(f"  TTFT: {result['ttft_ms']}ms")
        print(f"  TPS: {result['throughput_tps']} tokens/s")
        print(f"  Total tokens: {result['total_tokens']}")
        print(f"  Total time: {result['total_ms']}ms")

    def test_multi_model_speed_test(self, client: TestClient) -> None:
        """Test batch speed test with multiple models, results sorted by TTFT."""
        secrets = load_test_secrets()
        from myrm_agent_harness.agent.config.litellm_routing import (
            normalize_env_model_selection_string,
        )

        models_config = []

        basic_model = normalize_env_model_selection_string(secrets.basic_model)
        models_config.append(
            {
                "model": basic_model,
                "api_key": secrets.basic_api_key,
                "base_url": secrets.basic_base_url or None,
            }
        )

        if secrets.has_lite_credentials:
            lite_model = normalize_env_model_selection_string(secrets.lite_model)
            lite_key = secrets.lite_api_key or secrets.basic_api_key
            lite_base = secrets.lite_base_url or secrets.basic_base_url
            models_config.append(
                {
                    "model": lite_model,
                    "api_key": lite_key,
                    "base_url": lite_base or None,
                }
            )

        response = client.post(
            "/api/v1/llm/speed-test",
            json={"models": models_config},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        results = data["data"]
        assert len(results) == len(models_config)

        ok_results = [r for r in results if r["status"] == "ok"]
        assert len(ok_results) >= 1, f"At least one model should succeed: {results}"

        if len(ok_results) >= 2:
            ttft_values = [r["ttft_ms"] for r in ok_results]
            assert ttft_values == sorted(ttft_values), "Results should be sorted by TTFT"

        for r in ok_results:
            print(f"\n  {r['model']}: TTFT={r['ttft_ms']}ms, TPS={r['throughput_tps']}")

    def test_mixed_valid_invalid_models(self, client: TestClient) -> None:
        """Valid + invalid model: valid succeeds, invalid gets error status."""
        secrets = load_test_secrets()
        from myrm_agent_harness.agent.config.litellm_routing import (
            normalize_env_model_selection_string,
        )

        model = normalize_env_model_selection_string(secrets.basic_model)
        response = client.post(
            "/api/v1/llm/speed-test",
            json={
                "models": [
                    {
                        "model": model,
                        "api_key": secrets.basic_api_key,
                        "base_url": secrets.basic_base_url or None,
                    },
                    {
                        "model": "nonexistent-model-xyz",
                        "api_key": "sk-invalid",
                        "base_url": "https://api.openai.com/v1",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        results = data["data"]
        assert len(results) == 2

        statuses = {r["model"]: r["status"] for r in results}
        assert statuses[model] == "ok", f"Valid model failed: {results}"
        assert statuses["nonexistent-model-xyz"] == "error"
