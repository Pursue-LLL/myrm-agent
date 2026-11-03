"""End-to-end tests for configuration readiness API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.e2e

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


def test_onboarding_complete() -> None:
    """Test marking onboarding as complete."""
    with TestClient(app) as client:
        response = client.post("/api/v1/config/onboarding/complete")
        assert response.status_code in (200, 201, 204)
