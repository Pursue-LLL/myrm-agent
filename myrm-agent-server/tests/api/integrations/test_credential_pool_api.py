"""Tests for credential pool stats and reset-cooldowns API endpoints.

Tests cover:
- GET /api/v1/integrations/llm/credential-pool/stats
- POST /api/v1/integrations/llm/credential-pool/reset-cooldowns (all keys and by suffix)
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.core.manager import LLMManager

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestCredentialPoolApi:
    """Test credential pool stats and cooldown reset API endpoints."""

    def test_get_pool_stats_empty(self, client: TestClient) -> None:
        """When no pools are cached, returns empty list."""
        with patch.object(LLMManager, "get_pool_stats", return_value=[]):
            response = client.get("/api/v1/integrations/llm/credential-pool/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"] == []

    def test_get_pool_stats_with_data(self, client: TestClient) -> None:
        """When pools exist, returns structured observability stats."""
        mock_stats = [
            {
                "cache_key": "openai:gpt-4",
                "model": "gpt-4",
                "stats": {
                    "strategy": "least_used",
                    "total_keys": 3,
                    "available_keys": 2,
                    "total_calls": 42,
                    "total_rate_limits": 2,
                    "max_consecutive_rate_limits": 1,
                    "total_errors": 2,
                    "keys": [
                        {
                            "suffix": "1234",
                            "calls": 20,
                            "rate_limits": 0,
                            "consecutive_rate_limits": 0,
                            "errors": 0,
                            "in_cooldown": False,
                            "cooldown_remaining_s": 0.0,
                        },
                        {
                            "suffix": "5678",
                            "calls": 22,
                            "rate_limits": 2,
                            "consecutive_rate_limits": 1,
                            "errors": 2,
                            "in_cooldown": True,
                            "cooldown_remaining_s": 45.2,
                        },
                    ],
                },
            }
        ]
        with patch.object(LLMManager, "get_pool_stats", return_value=mock_stats):
            response = client.get("/api/v1/integrations/llm/credential-pool/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["data"]) == 1
            assert data["data"][0]["model"] == "gpt-4"
            assert data["data"][0]["stats"]["total_keys"] == 3

    def test_reset_cooldowns_all(self, client: TestClient) -> None:
        """Reset all cooldowns across all pools."""
        with patch.object(LLMManager, "reset_pool_cooldowns", return_value=2) as mock_reset:
            response = client.post("/api/v1/integrations/llm/credential-pool/reset-cooldowns", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["reset_count"] == 2
            mock_reset.assert_called_once_with(key_suffix=None)

    def test_reset_cooldowns_by_suffix(self, client: TestClient) -> None:
        """Reset cooldowns for a specific key suffix."""
        with patch.object(LLMManager, "reset_pool_cooldowns", return_value=1) as mock_reset:
            response = client.post(
                "/api/v1/integrations/llm/credential-pool/reset-cooldowns",
                json={"key_suffix": "5678"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["reset_count"] == 1
            mock_reset.assert_called_once_with(key_suffix="5678")

    def test_validate_external_secret_valid(self, client: TestClient) -> None:
        """Validate resolution of an external secret reference."""
        with patch(
            "myrm_agent_harness.backends.secrets.resolve_external_secret",
            return_value="sk-real-secret-123456",
        ):
            response = client.post(
                "/api/v1/integrations/llm/credential-pool/validate-secret-reference",
                json={"reference": "op://Vault/OpenAI/credential"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["valid"] is True
            assert data["data"]["masked_preview"] == "sk-...456"

    def test_validate_external_secret_invalid_scheme(self, client: TestClient) -> None:
        """Reject non-URI strings."""
        response = client.post(
            "/api/v1/integrations/llm/credential-pool/validate-secret-reference",
            json={"reference": "sk-plain-text-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["valid"] is False
        assert "Not a recognized" in data["data"]["error"]
