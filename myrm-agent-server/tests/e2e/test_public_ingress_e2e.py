import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.connection import init_database
from tests.support.minimal_app import build_minimal_app

pytestmark = pytest.mark.e2e

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

app = build_minimal_app(preset="system")


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """E2E tests skip session init_database in conftest; init schema here."""
    asyncio.run(init_database())
    yield
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)


@pytest.fixture
def e2e_client():
    """Client for E2E testing without mocks."""
    # Ensure database and settings are initialized naturally.
    with TestClient(app) as client:
        yield client


def test_system_ingress_requirement_e2e(e2e_client):
    """Full-stack ingress-requirement without mocks (regression for deploy_capabilities import)."""
    response = e2e_client.get("/api/v1/system/ingress-requirement")
    assert response.status_code == 200
    body = response.json()
    assert "required" in body
    assert "has_public_ingress" in body
    assert isinstance(body["reasons"], list)
    assert isinstance(body["channels"], dict)


def test_system_ingress_url_e2e(e2e_client, monkeypatch):
    """End-to-end test for Public Ingress URL resolver.

    Sets the CP_PUBLIC_INGRESS_URL environment variable (simulating Plane injection)
    and verifies the full API stack returns the correct value.
    """
    # Simulate Control Plane injecting the URL via Env Var
    # The settings object uses validation_alias="CP_PUBLIC_INGRESS_URL"
    from app.config.settings import settings

    original_url = settings.cp_public_ingress_url

    settings.cp_public_ingress_url = "https://e2e-public.ngrok.app/"

    try:
        response = e2e_client.get("/api/v1/system/ingress-url")
        assert response.status_code == 200
        # Should be stripped of trailing slash
        assert response.json() == {"ingress_url": "https://e2e-public.ngrok.app"}
    finally:
        # Restore settings
        settings.cp_public_ingress_url = original_url
