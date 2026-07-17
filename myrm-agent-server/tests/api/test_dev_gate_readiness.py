"""Tests for Dev Gate readiness API (localhost-only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dev_gate.readiness import is_loopback_client, router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/dev-gate")
    return TestClient(app)


def test_is_loopback_client_accepts_ipv4() -> None:
    class _Client:
        host = "127.0.0.1"

    class _Request:
        client = _Client()

    assert is_loopback_client(_Request()) is True  # type: ignore[arg-type]


def test_dev_gate_readiness_rejects_non_loopback(client: TestClient) -> None:
    with patch("app.api.dev_gate.readiness.is_loopback_client", return_value=False):
        response = client.get("/api/v1/dev-gate/readiness")
    assert response.status_code == 403


def test_dev_gate_readiness_aggregates_provider_and_edge_tts(client: TestClient) -> None:
    config_payload = {
        "provider": {"is_ready": True, "missing_items": []},
        "search": {"is_ready": True},
        "onboarding_completed": True,
        "degraded": False,
    }
    with (
        patch("app.api.dev_gate.readiness.is_loopback_client", return_value=True),
        patch(
            "app.api.config.router.get_config_readiness",
            new_callable=AsyncMock,
            return_value=config_payload,
        ),
        patch("app.api.health.router._check_edge_tts_installed", return_value=True),
        patch(
            "app.api.health.router.system_info",
            new_callable=AsyncMock,
            return_value={"deploy_mode": "local"},
        ),
    ):
        response = client.get("/api/v1/dev-gate/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["contract_version"] == "2"
    assert body["checks"]["provider_ready"] is True
    assert body["checks"]["edge_tts_available"] is True
