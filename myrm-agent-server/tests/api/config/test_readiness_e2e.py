"""End-to-end tests for configuration readiness API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

from app.database.connection import init_database  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Initialize test database before tests."""
    asyncio.run(init_database())
    yield
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        (TEST_DB.parent / f"{TEST_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Bypass auth middleware by treating all requests as local."""
    if True:
        yield


def test_config_readiness_no_provider() -> None:
    """Test readiness check when no provider is configured."""
    with TestClient(app) as client:
        response = client.get("/api/v1/config/readiness")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "onboarding_completed" in data


def test_onboarding_recommendations() -> None:
    """Test getting onboarding recommendations."""
    with TestClient(app) as client:
        response = client.get("/api/v1/config/onboarding/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        providers = data["providers"]
        assert isinstance(providers, list)
        assert len(providers) >= 3

        if len(providers) > 0:
            rec = providers[0]
            assert "id" in rec
            assert "name" in rec
            assert "pros" in rec
            assert "cons" in rec
            assert "setup_steps" in rec


def test_onboarding_complete() -> None:
    """Test marking onboarding as complete."""
    with TestClient(app) as client:
        response = client.post("/api/v1/config/onboarding/complete")
        assert response.status_code in (200, 201, 204)
