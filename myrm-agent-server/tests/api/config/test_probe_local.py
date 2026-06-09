"""Tests for local model auto-detection (probe-local endpoint).

Covers:
- probe_local_models() service function
- /config/onboarding/probe-local API endpoint
- Edge cases: service unavailable, empty models, concurrent probing
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

from app.database.connection import init_database  # noqa: E402
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
from app.services.config.onboarding import (  # noqa: E402
    LocalProbeResult,
    _probe_lm_studio,
    _probe_ollama,
    probe_local_models,
)


def _make_httpx_response(json_data: dict[str, object]) -> httpx.Response:
    """Create a real httpx.Response with JSON body (avoids AsyncMock pitfalls)."""
    import json as _json

    return httpx.Response(
        status_code=200,
        content=_json.dumps(json_data).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "http://mock"),
    )


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Initialize test database before tests."""
    asyncio.run(init_database())
    yield
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


@pytest.fixture
def probe_client():
    """Fast TestClient with auth bypassed via loopback IP mock."""
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with (
        patch(
            "app.core.security.auth.identity.is_loopback_ip",
            return_value=True,
        ),
        TestClient(
            app,
            base_url="http://127.0.0.1",
            raise_server_exceptions=False,
        ) as client,
    ):
        yield client
    app.router.lifespan_context = original_lifespan


class TestProbeLocalModelsUnit:
    """Unit tests for probe_local_models service function."""

    @pytest.mark.asyncio
    async def test_probe_ollama_unavailable(self) -> None:
        """Ollama not running returns available=False."""
        result = await _probe_ollama("http://localhost:19999")
        assert result.provider == "ollama"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_probe_lm_studio_unavailable(self) -> None:
        """LM Studio not running returns available=False."""
        result = await _probe_lm_studio("http://localhost:19998")
        assert result.provider == "lm_studio"
        assert result.available is False
        assert result.error is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_probe_local_models_both_unavailable(self) -> None:
        """When both services are down, returns empty results."""
        with (
            patch(
                "app.services.config.onboarding._OLLAMA_DEFAULT_URL",
                "http://localhost:19999",
            ),
            patch(
                "app.services.config.onboarding._LM_STUDIO_DEFAULT_URL",
                "http://localhost:19998",
            ),
        ):
            results = await probe_local_models()
            assert len(results) == 2
            assert all(not r.available for r in results)

    @pytest.mark.asyncio
    async def test_probe_ollama_available_mock(self) -> None:
        """Mocked Ollama response returns correct models."""
        mock_response = _make_httpx_response(
            {
                "models": [
                    {"name": "llama3.2:latest", "size": 4_000_000_000},
                    {"name": "qwen2:7b", "size": 7_000_000_000},
                ]
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _probe_ollama()
            assert result.available is True
            assert result.provider == "ollama"
            assert len(result.models) == 2
            assert result.models[0].name == "llama3.2:latest"
            assert result.models[0].size_bytes == 4_000_000_000
            assert result.models[1].name == "qwen2:7b"

    @pytest.mark.asyncio
    async def test_probe_lm_studio_available_mock(self) -> None:
        """Mocked LM Studio response returns correct models."""
        mock_response = _make_httpx_response(
            {
                "data": [
                    {"id": "deepseek-coder-v2"},
                    {"id": "mistral-7b-instruct"},
                ]
            }
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _probe_lm_studio()
            assert result.available is True
            assert result.provider == "lm_studio"
            assert len(result.models) == 2
            assert result.models[0].name == "deepseek-coder-v2"

    @pytest.mark.asyncio
    async def test_probe_ollama_empty_models(self) -> None:
        """Ollama running but no models pulled."""
        mock_response = _make_httpx_response({"models": []})

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _probe_ollama()
            assert result.available is True
            assert len(result.models) == 0

    @pytest.mark.asyncio
    async def test_probe_result_model_validation(self) -> None:
        """LocalProbeResult Pydantic validation."""
        result = LocalProbeResult(
            provider="ollama",
            base_url="http://localhost:11434",
            available=True,
            latency_ms=42,
        )
        assert result.models == []
        assert result.error is None

        dumped = result.model_dump()
        assert dumped["provider"] == "ollama"
        assert dumped["latency_ms"] == 42

    @pytest.mark.asyncio
    async def test_probe_local_models_exception_recovery(self) -> None:
        """When a probe raises an unexpected exception, it is captured gracefully."""
        with (
            patch(
                "app.services.config.onboarding._probe_ollama",
                side_effect=RuntimeError("unexpected crash"),
            ),
            patch(
                "app.services.config.onboarding._probe_lm_studio",
                side_effect=RuntimeError("lm crash"),
            ),
        ):
            results = await probe_local_models()
            assert len(results) == 2
            assert all(not r.available for r in results)
            assert results[0].provider == "ollama"
            assert "unexpected crash" in (results[0].error or "")
            assert results[1].provider == "lm_studio"

    @pytest.mark.asyncio
    async def test_probe_local_models_with_available_service(self) -> None:
        """When a service is available, log info and compute recommended_model."""
        from app.services.config.onboarding import DetectedModel

        available_result = LocalProbeResult(
            provider="ollama",
            base_url="http://localhost:11434",
            available=True,
            latency_ms=10,
            models=[DetectedModel(name="qwen3:latest", size_bytes=4_000_000_000)],
        )
        unavailable_result = LocalProbeResult(
            provider="lm_studio",
            base_url="http://localhost:1234",
            available=False,
            latency_ms=0,
            error="Connection refused",
        )

        with (
            patch(
                "app.services.config.onboarding._probe_ollama",
                return_value=available_result,
            ),
            patch(
                "app.services.config.onboarding._probe_lm_studio",
                return_value=unavailable_result,
            ),
        ):
            results = await probe_local_models()
            assert len(results) == 2
            assert results[0].available is True
            assert results[0].models[0].name == "qwen3:latest"


class TestProbeLocalEndpoint:
    """Integration tests for /config/onboarding/probe-local endpoint."""

    def test_probe_local_endpoint_returns_200(self, probe_client: TestClient) -> None:
        """Endpoint responds with correct structure."""
        response = probe_client.get("/api/v1/config/onboarding/probe-local")
        assert response.status_code == 200
        data = response.json()

        assert "results" in data
        assert "has_available" in data
        assert "recommended_model" in data
        assert isinstance(data["results"], list)
        assert isinstance(data["has_available"], bool)

    def test_probe_local_endpoint_result_structure(self, probe_client: TestClient) -> None:
        """Each result has expected fields."""
        response = probe_client.get("/api/v1/config/onboarding/probe-local")
        data = response.json()

        for result in data["results"]:
            assert "provider" in result
            assert "base_url" in result
            assert "available" in result
            assert "models" in result
            assert result["provider"] in ("ollama", "lm_studio")

    def test_probe_local_endpoint_recommended_model(self, probe_client: TestClient) -> None:
        """recommended_model is None when no services are available."""
        response = probe_client.get("/api/v1/config/onboarding/probe-local")
        data = response.json()

        if not data["has_available"]:
            assert data["recommended_model"] is None
        else:
            assert isinstance(data["recommended_model"], str)
            assert len(data["recommended_model"]) > 0

    def test_probe_local_endpoint_includes_search_fields(self, probe_client: TestClient) -> None:
        """Search probe fields are present for one-click onboarding."""
        response = probe_client.get("/api/v1/config/onboarding/probe-local")
        assert response.status_code == 200
        data = response.json()

        assert "search" in data
        assert "search_has_available" in data
        assert "recommended_searxng_url" in data
        assert isinstance(data["search"], list)
        assert isinstance(data["search_has_available"], bool)

        for item in data["search"]:
            assert item["provider"] == "searxng"
            assert "available" in item
            assert "latency_ms" in item

        assert "8081" in data["recommended_searxng_url"]


class TestProbeLocalSearchUnit:
    """Unit tests for probe_local_search service function."""

    @pytest.mark.asyncio
    async def test_probe_local_search_returns_searxng_only(self) -> None:
        from app.services.config.onboarding import probe_local_search

        results = await probe_local_search()
        assert len(results) == 1
        assert results[0]["provider"] == "searxng"
