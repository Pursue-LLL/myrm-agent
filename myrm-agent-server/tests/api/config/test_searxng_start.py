"""Tests for POST /config/onboarding/searxng/start."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

from app.database.connection import init_database  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_test_database() -> None:
    asyncio.run(init_database())
    yield
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


@pytest.fixture
def local_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DEPLOY_MODE", "local")
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


def test_searxng_start_requires_local_mode(local_client: TestClient) -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=False):
        response = local_client.post("/api/v1/config/onboarding/searxng/start")
    assert response.status_code == 404


def test_searxng_start_success(local_client: TestClient) -> None:
    with patch(
        "app.services.config.searxng_setup.start_local_searxng_and_wait",
        new_callable=AsyncMock,
        return_value={
            "docker_invoked": True,
            "available": True,
            "base_url": "http://127.0.0.1:8081",
            "latency_ms": 10,
            "error": None,
        },
    ):
        response = local_client.post("/api/v1/config/onboarding/searxng/start")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert "8081" in data["base_url"]
