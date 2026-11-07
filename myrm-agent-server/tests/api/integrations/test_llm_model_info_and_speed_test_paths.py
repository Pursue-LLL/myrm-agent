"""Tests for /integrations/llm/model-info, batch model-info, and the speed-test streaming paths.

Covers the remaining llms.py branches with LLM/tooling calls mocked out,
including LiteLLM-backed capability lookup.
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


class TestModelInfoEndpoints:
    """model-info and model-info/batch exact-match and fallback behavior."""

    def test_model_info_exact_match(self, client: TestClient) -> None:
        """Exact LiteLLM match returns found=True with capabilities."""
        info = {
            "supports_vision": True,
            "supports_function_calling": True,
            "max_tokens": 8192,
        }
        with patch(
            "app.api.integrations.llms.model_info._try_get_model_info_exact",
            return_value=info,
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-info",
                json={"model": "gpt-4o"},
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["found"] is True
        assert data["capabilities"]["supports_vision"] is True

    def test_model_info_fuzzy_search(self, client: TestClient) -> None:
        """No exact match falls back to name search candidates."""
        from app.api.integrations.llms import (
            ModelCandidate,
            ModelCapabilities,
        )

        candidate = ModelCandidate(
            provider="openai",
            model_key="openai/gpt-4o-mini",
            capabilities=ModelCapabilities(supports_vision=False),
        )
        with (
            patch(
                "app.api.integrations.llms.model_info._try_get_model_info_exact",
                return_value=None,
            ),
            patch(
                "app.api.integrations.llms.model_info._search_models_by_name",
                return_value=[candidate],
            ),
        ):
            response = client.post(
                "/api/v1/integrations/llm/model-info",
                json={"model": "gpt-4o"},
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["found"] is False
        assert data["candidates"][0]["model_key"] == "openai/gpt-4o-mini"

    def test_model_info_batch_mixed(self, client: TestClient) -> None:
        """Batch lookup mixes exact matches and empty capability fallbacks."""
        info = {"supports_vision": True, "max_tokens": 128000}
        with patch(
            "app.api.integrations.llms.model_info._try_get_model_info_exact",
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


class TestLiteLLMBackedHelpers:
    """_try_get_model_info_exact and _search_models_by_name against mocked litellm."""

    def test_try_get_model_info_exact_returns_dict(self) -> None:
        """Exact lookup converts LiteLLM info dict when not present in model_cost."""
        from app.api.integrations.llms import _try_get_model_info_exact

        with (
            patch("litellm.model_cost", {}),
            patch(
                "litellm.get_model_info",
                return_value={"max_tokens": 8192},
            ),
        ):
            assert _try_get_model_info_exact("gpt-4o") == {"max_tokens": 8192}

    def test_try_get_model_info_exact_prefers_model_cost(self) -> None:
        """model_cost wins over get_model_info so pricing metadata is not lost."""
        from app.api.integrations.llms import _try_get_model_info_exact

        with (
            patch("litellm.model_cost", {"gpt-4o": {"max_tokens": 4096}}),
            patch(
                "litellm.get_model_info",
                side_effect=AssertionError("must not be reached"),
            ),
        ):
            assert _try_get_model_info_exact("gpt-4o") == {"max_tokens": 4096}

    def test_try_get_model_info_exact_handles_exception(self) -> None:
        """Unknown model or lookup failure degrades to None."""
        from app.api.integrations.llms import _try_get_model_info_exact

        with (
            patch("litellm.model_cost", {}),
            patch(
                "litellm.get_model_info",
                side_effect=KeyError("no such model"),
            ),
        ):
            assert _try_get_model_info_exact("nope/xyz") is None

    def test_try_get_model_info_exact_empty_info(self) -> None:
        """Empty info dict from LiteLLM resolves to None."""
        from app.api.integrations.llms import _try_get_model_info_exact

        with (
            patch("litellm.model_cost", {}),
            patch(
                "litellm.get_model_info",
                return_value=None,
            ),
        ):
            assert _try_get_model_info_exact("gpt-4o") is None

    def test_search_models_by_name_builds_candidates(self) -> None:
        """Name search iterates litellm.model_cost and builds candidate list."""
        from app.api.integrations.llms import _search_models_by_name

        fake_cost = {
            "openai/gpt-4o": {"max_tokens": 8192},
            "anthropic/claude-3.5": {"max_tokens": 200000},
            "openai/other": {},
        }
        with patch(
            "litellm.model_cost",
            fake_cost,
        ):
            candidates = _search_models_by_name("gpt-4o")
        assert len(candidates) == 1
        assert candidates[0].model_key == "openai/gpt-4o"
        assert candidates[0].provider == "openai"
        assert candidates[0].capabilities.max_tokens == 8192

    def test_search_models_by_name_no_provider_prefix(self) -> None:
        """Keys without a provider prefix resolve to 'unknown'."""
        from app.api.integrations.llms import _search_models_by_name

        with patch(
            "litellm.model_cost",
            {"plain-name": {"max_tokens": 4096}},
        ):
            candidates = _search_models_by_name("plain")
        assert len(candidates) == 1
        assert candidates[0].provider == "unknown"
        assert candidates[0].model_key == "plain-name"
