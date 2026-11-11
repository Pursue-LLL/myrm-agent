"""Tests for /integrations/llm/model-info/batch and the speed-test streaming paths.

Covers the remaining llms.py branches with LLM/tooling calls mocked out,
including catalog-backed capability lookup.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

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


class TestModelInfoBatchEndpoint:
    """model-info/batch exact-match and fallback behavior."""

    def test_model_info_batch_mixed(self, client: TestClient) -> None:
        """Batch lookup mixes exact matches and empty capability fallbacks."""
        info = {"supports_vision": True, "max_input_tokens": 128000}
        with patch(
            "app.api.integrations.llms.model_info.model_facts",
            side_effect=lambda model: info if model == "known" else None,
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-info/batch",
                json={"models": ["known", "unknown"]},
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["known"]["supports_vision"] is True
        assert data["unknown"]["supports_vision"] is False


class TestSpeedTestStreamingPaths:
    """speed-test streaming success, no-token, and timeout branches."""

    def _post(self, client: TestClient) -> list[dict[str, object]]:
        response = client.post(
            "/api/v1/integrations/llm/speed-test",
            json={
                "models": [
                    {
                        "model": "gpt-4o-mini",
                        "api_key": "sk-test",
                        "base_url": "https://api.openai.com/v1",
                    }
                ]
            },
        )
        assert response.status_code == 200
        return response.json()["data"]

    def test_streaming_success(self, client: TestClient) -> None:
        """Streaming chunks produce ok status with TTFT/TPS metrics."""

        async def _chunks(*_args, **_kwargs):
            yield type("C", (), {"content": "a"})()
            yield type("C", (), {"content": "b"})()

        from unittest.mock import MagicMock

        llm = MagicMock()
        llm.astream = _chunks
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ):
            results = self._post(client)
        assert results[0]["status"] == "ok"
        assert results[0]["ttft_ms"] is not None
        assert results[0]["total_tokens"] == 2

    def test_streaming_no_tokens(self, client: TestClient) -> None:
        """Empty stream reports error without raising."""

        async def _chunks(*_args, **_kwargs):
            return
            yield  # pragma: no cover - makes this an async generator

        from unittest.mock import MagicMock

        llm = MagicMock()
        llm.astream = _chunks
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ):
            results = self._post(client)
        assert results[0]["status"] == "error"
        assert "No tokens received" in (results[0]["error"] or "")

    def test_streaming_timeout(self, client: TestClient) -> None:
        """Timeout is caught and reported as an error item."""
        from unittest.mock import MagicMock

        def _raise_timeout(*_args, **_kwargs):
            raise __import__("asyncio").TimeoutError

        llm = MagicMock()
        llm.astream = _raise_timeout
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(return_value=llm),
        ):
            results = self._post(client)
        assert results[0]["status"] == "error"
        assert "Timed out" in (results[0]["error"] or "")

    def test_streaming_generic_error(self, client: TestClient) -> None:
        """Generic model error is reported as an error item."""
        with patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm",
            new=AsyncMock(side_effect=ValueError("bad config")),
        ):
            results = self._post(client)
        assert results[0]["status"] == "error"
        assert "bad config" in (results[0]["error"] or "")
