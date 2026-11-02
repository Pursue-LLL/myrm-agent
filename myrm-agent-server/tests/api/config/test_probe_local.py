"""Tests for the local search probe endpoint and the Ollama endpoint resolver.

Covers:
- probe_local_search() service function
- /config/onboarding/searxng/probe API endpoint
- get_ollama_base_url() environment resolution
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

from app.database.connection import init_database  # noqa: E402
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Initialize test database before tests."""
    asyncio.run(init_database())
    yield
    from tests.api.config.conftest import cleanup_shared_test_db

    cleanup_shared_test_db(TEST_DB)


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


class TestSearxngProbeEndpoint:
    """Integration tests for /config/onboarding/searxng/probe endpoint."""

    def test_searxng_probe_endpoint_reports_search_backends_only(self, probe_client: TestClient) -> None:
        """The payload carries the SearXNG probe and nothing about local model services."""
        response = probe_client.get("/api/v1/config/onboarding/searxng/probe")
        assert response.status_code == 200
        data = response.json()

        assert set(data) == {"search", "recommended_searxng_url"}
        assert isinstance(data["search"], list)

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


class TestGetOllamaBaseUrl:
    """Tests for get_ollama_base_url SSOT function."""

    def test_default_fallback_to_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.config.onboarding import get_ollama_base_url

        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("OLLAMA_HOST_URL", raising=False)

        assert get_ollama_base_url() == "http://localhost:11434"

    def test_base_url_with_protocol_and_trailing_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.config.onboarding import get_ollama_base_url

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
        assert get_ollama_base_url() == "http://host.docker.internal:11434"

    def test_bare_host_auto_prepends_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.config.onboarding import get_ollama_base_url

        monkeypatch.setenv("OLLAMA_BASE_URL", "192.168.1.50:11434")
        assert get_ollama_base_url() == "http://192.168.1.50:11434"

    def test_fallback_to_ollama_host_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.config.onboarding import get_ollama_base_url

        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.setenv("OLLAMA_HOST", "https://ollama.lan:11434")
        assert get_ollama_base_url() == "https://ollama.lan:11434"
