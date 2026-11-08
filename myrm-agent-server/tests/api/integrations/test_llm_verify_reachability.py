"""Tests for /integrations/llm/verify and check-reachability.

Covers the llms.py verify and reachability branches with LLM/tooling calls mocked out,
including cache hit paths and failure paths.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.fallback.health_check import HealthProbeResult

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
# Any key must reach the provider: no value, however key-shaped, short-circuits verification or the probe.
_ARBITRARY_KEY = "sk-test-an-arbitrary-key-never-short-circuits-the-probe"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestVerifyLLMConnection:
    """verify endpoint: success, empty response, and failure paths."""

    def test_verify_success(self, client: TestClient) -> None:
        """Non-empty LLM response verifies successfully."""
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {"content": "pong"})()
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ):
            response = client.post(
                "/api/v1/integrations/llm/verify",
                json={
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                },
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["model_name"] == "gpt-4o-mini"

    def test_verify_empty_response_raises(self, client: TestClient) -> None:
        """Empty LLM response raises a structured MyrmError."""
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {"content": ""})()
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ):
            response = client.post(
                "/api/v1/integrations/llm/verify",
                json={
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                },
            )
        assert response.status_code == 502

    def test_verify_llm_error_raises(self, client: TestClient) -> None:
        """LLM invocation failure is classified and raised."""
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            response = client.post(
                "/api/v1/integrations/llm/verify",
                json={
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                },
            )
        assert response.status_code == 502

    def test_verify_does_not_bypass_llm_for_arbitrary_key(self, client: TestClient) -> None:
        """No api_key value short-circuits verification without a real LLM call."""
        llm = AsyncMock()
        llm.ainvoke.return_value = type("R", (), {"content": "pong"})()
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ) as get_llm:
            response = client.post(
                "/api/v1/integrations/llm/verify",
                json={
                    "model": "gpt-4o-mini",
                    "api_key": _ARBITRARY_KEY,
                },
            )
        assert response.status_code == 200
        assert response.json()["data"]["model_name"] == "gpt-4o-mini"
        get_llm.assert_awaited()


class TestCheckModelReachability:
    """check-reachability: cache hit, probe success/failure, failure classification."""

    def _post(self, client: TestClient, **overrides: object) -> dict:
        payload = {
            "model": "gpt-4o-mini",
            "api_key": "sk-test",
            "base_url": "https://api.openai.com/v1",
            **overrides,
        }
        return client.post("/api/v1/integrations/llm/check-reachability", json=payload).json()["data"]

    def test_reachable_probe(self, client: TestClient) -> None:
        """Healthy probe reports reachable with latency."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(return_value=HealthProbeResult(ok=True, error_kind="none", latency_ms=42)),
            ),
        ):
            data = self._post(client)
        assert data["reachable"] is True
        assert data["latency_ms"] == 42
        assert data["error_kind"] == "none"
        assert data["cached"] is False
        _reachability_cache.clear()

    def test_unreachable_probe(self, client: TestClient) -> None:
        """Unhealthy probe reports unreachable with an error."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(
                    return_value=HealthProbeResult(
                        ok=False,
                        error_kind="provider_error",
                        error="AuthenticationError: invalid api key",
                        latency_ms=120,
                    )
                ),
            ),
        ):
            data = self._post(client)
        assert data["reachable"] is False
        assert data["error"] is not None
        assert data["error_kind"] == "provider_error"
        assert "invalid api key" in data["error"]
        _reachability_cache.clear()

    def test_probe_timeout_is_classified_and_explained(self, client: TestClient) -> None:
        """A probe that ran out of time reports 'timeout' instead of a generic no-response."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(
                    return_value=HealthProbeResult(
                        ok=False,
                        error_kind="timeout",
                        error="No response within 15s",
                        latency_ms=15000,
                    )
                ),
            ),
        ):
            data = self._post(client)
        assert data["reachable"] is False
        assert data["error_kind"] == "timeout"
        assert "No response" in (data["error"] or "")
        _reachability_cache.clear()

    def test_probe_exception_reports_unreachable(self, client: TestClient) -> None:
        """Probe exception degrades to reachable=False with error text."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(side_effect=ConnectionError("timeout")),
            ),
        ):
            data = self._post(client)
        assert data["reachable"] is False
        assert "timeout" in (data["error"] or "")
        assert data["error_kind"] == "provider_error"
        _reachability_cache.clear()

    def test_cached_result_returned(self, client: TestClient) -> None:
        """Second probe within TTL serves the cached result."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(return_value=HealthProbeResult(ok=True, error_kind="none", latency_ms=7)),
            ),
        ):
            first = self._post(client)
            second = self._post(client)
        assert first["cached"] is False
        assert second["cached"] is True
        assert second["reachable"] is True
        _reachability_cache.clear()

    def test_no_key_short_circuits_probe(self, client: TestClient) -> None:
        """No api_key value returns a synthetic reachable result without probing."""
        from app.api.integrations.llms import _reachability_cache

        _reachability_cache.clear()
        with (
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
                new=AsyncMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.fallback.health_check.probe_llm_health",
                new=AsyncMock(return_value=HealthProbeResult(ok=True, error_kind="none", latency_ms=5)),
            ) as health_check,
        ):
            response = client.post(
                "/api/v1/integrations/llm/check-reachability",
                json={
                    "model": "gpt-4o-mini",
                    "api_key": _ARBITRARY_KEY,
                },
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["reachable"] is True
        health_check.assert_awaited()
        _reachability_cache.clear()
